# backend/app/agent/tools.py
"""
Outils de l'agent BI.

Principe de conception : chaque fonction retourne soit un dict/liste de
donnees brutes (jamais reformulees par un LLM -- voir agent.py), soit
{"error": {...}} en cas d'echec. Aucune fonction n'utilise une valeur par
defaut Python SILENCIEUSE pour masquer un manque d'info.
"""
import time
import requests
from app.rag.search import search_customer_reviews

BASE_URL = "http://localhost:8000"

_INTERNAL_HTTP_TIMEOUT = 15

_cache = {}
_CACHE_TTL = 300


def _cached_get(url: str, params: dict | None = None):
    key = f"{url}?{params}"
    now = time.time()
    cached = _cache.get(key)
    if cached and (now - cached[1] < _CACHE_TTL):
        return cached[0]
    response = requests.get(url, params=params, timeout=_INTERNAL_HTTP_TIMEOUT).json()
    _cache[key] = (response, now)
    return response


def get_kpi_summary():
    """Recupere les KPI globaux : nombre de commandes, CA total, panier moyen."""
    try:
        return _cached_get(f"{BASE_URL}/api/dashboard/summary")
    except Exception as e:
        return {"error": f"Impossible de contacter l'API KPI : {e}"}


def get_revenue_by_month():
    """Recupere l'evolution du chiffre d'affaires mois par mois (serie
    COMPLETE, non filtree, sans aucun parametre). Pour une periode PRECISE
    -> get_revenue_for_period."""
    try:
        return _cached_get(f"{BASE_URL}/api/dashboard/revenue-by-month")
    except Exception as e:
        return {"error": f"Impossible de contacter l'API KPI : {e}"}


def get_revenue_for_period(weeks_ago: int = None, month: str = None):
    """CA REEL sur UNE PERIODE PRECISE. UN SEUL des deux parametres :
    weeks_ago (0=derniere semaine, 1=celle d'avant...) OU month ('YYYY-MM').
    Pour la serie complete -> get_revenue_by_month."""
    if month:
        try:
            data = _cached_get(f"{BASE_URL}/api/dashboard/revenue-by-month")
        except Exception as e:
            return {"error": f"Impossible de contacter l'API KPI : {e}"}
        if isinstance(data, dict) and "error" in data:
            return data
        month_norm = month.strip()[:7]
        matches = [m for m in data if m.get("month", "").startswith(month_norm)]
        if not matches:
            bounds = f"{data[0]['month']} à {data[-1]['month']}" if data else "aucune donnée"
            return {"error": f"Aucune donnée pour '{month}'. Période disponible : {bounds}."}
        return matches[0]

    if weeks_ago is not None:
        if weeks_ago < 0:
            return {"error": "weeks_ago doit etre >= 0 (0 = derniere semaine connue)."}
        weeks_ago = min(weeks_ago, 200)
        try:
            return _cached_get(f"{BASE_URL}/api/dashboard/revenue-by-week", {"weeks_ago": weeks_ago})
        except Exception as e:
            return {"error": f"Impossible de contacter l'API KPI : {e}"}

    return {"clarification_needed": (
        "Précise soit une semaine (ex: 'la semaine dernière', 'il y a 3 semaines'), "
        "soit un mois précis (ex: 'février 2017')."
    )}


def get_top_categories(limit: int = 5):
    """Recupere les categories de produits generant le plus de CA. Le LLM
    doit passer 'limit' explicitement si l'utilisateur demande un nombre
    different de 5 (top 10, top 3...) -- ce n'est PAS plafonne cote serveur
    a 5, c'est juste la valeur par defaut si rien n'est precise."""
    limit = max(1, min(limit, 50))
    try:
        return _cached_get(f"{BASE_URL}/api/dashboard/top-categories", {"limit": limit})
    except Exception as e:
        return {"error": f"Impossible de contacter l'API KPI : {e}"}


def get_revenue_for_category(category: str):
    """CA REEL total (TOUTE la periode disponible, PAS un decoupage mensuel)
    pour UNE categorie precise. Pour un classement -> get_top_categories."""
    try:
        data = _cached_get(f"{BASE_URL}/api/dashboard/top-categories", {"limit": 100})
    except Exception as e:
        return {"error": f"Impossible de contacter l'API KPI : {e}"}
    if isinstance(data, dict) and "error" in data:
        return data
    match = next((c for c in data if c.get("category", "").strip().lower() == category.strip().lower()), None)
    if not match:
        available = ", ".join(c["category"] for c in data[:15])
        return {"error": f"Catégorie '{category}' introuvable. Catégories connues (extrait) : {available}…"}
    return match


def get_revenue_for_state(state: str):
    """CA REEL total pour UN etat CLIENT precis (customer_state), parmi le
    top 10 par CA."""
    try:
        data = _cached_get(f"{BASE_URL}/api/sales/revenue-by-state")
    except Exception as e:
        return {"error": f"Impossible de contacter l'API des ventes : {e}"}
    if isinstance(data, dict) and "error" in data:
        return data
    state_norm = state.strip().upper()
    match = next((s for s in data if s.get("state", "").strip().upper() == state_norm), None)
    if not match:
        available = ", ".join(s["state"] for s in data)
        return {"error": f"Aucune donnée pour l'état '{state}' (hors du top 10 par CA). États disponibles : {available}."}
    return match


def forecast_category_revenue(category: str, state: str = None, target_month: str = None):
    """Prevision de CA. Sans target_month, prevoit UNIQUEMENT le mois
    suivant les dernieres donnees connues. Avec target_month ('YYYY-MM'),
    prevision RECURSIVE (incertitude croissante), plafonnee cote API."""
    try:
        params = {"category": category}
        if state:
            params["state"] = state
        if target_month:
            params["target_month"] = target_month
        result = _cached_get(f"{BASE_URL}/api/ml/forecast/by-category", params)
        if isinstance(result, dict) and "detail" in result and "predicted_revenue_total" not in result:
            return {"error": result["detail"]}
        return result
    except Exception as e:
        return {"error": f"Impossible de contacter l'API ML : {e}"}


def predict_delivery_risk(
    category: str, customer_state: str, order_month: int,
    total_price: float = 150, total_freight: float = 20, n_items: int = 1,
    n_unique_products: int = 1, n_unique_sellers: int = 1, pct_same_state: float = 0.5,
    avg_product_weight_g: float = 800, max_product_weight_g: float = 800,
    n_payment_installments_max: int = 3, has_voucher: int = 0,
):
    """Estime le risque de retard de livraison pour une commande hypothetique.
    Seuls category/customer_state/order_month sont requis."""
    if not (1 <= order_month <= 12):
        return {"error": "order_month doit etre un entier entre 1 et 12."}
    payload = {
        "category": category, "customer_state": customer_state, "order_month": order_month,
        "total_price": total_price, "total_freight": total_freight, "n_items": n_items,
        "n_unique_products": n_unique_products, "n_unique_sellers": n_unique_sellers,
        "pct_same_state": pct_same_state, "avg_product_weight_g": avg_product_weight_g,
        "max_product_weight_g": max_product_weight_g,
        "n_payment_installments_max": n_payment_installments_max, "has_voucher": has_voucher,
    }
    try:
        return requests.post(f"{BASE_URL}/api/ml/predict/delay-risk", json=payload, timeout=_INTERNAL_HTTP_TIMEOUT).json()
    except Exception as e:
        return {"error": f"Impossible de contacter l'API ML : {e}"}


def predict_customer_segment(recency: float, frequency: float, monetary: float):
    """Predit EN DIRECT le segment RFM/KMeans pour un profil client
    hypothetique. Les 3 parametres sont necessaires.

    BUG CORRIGE ICI : l'API /api/customers/predict-segment attend le champ
    'recency_days' (voir SegmentPredictRequest cote backend), pas 'recency'
    -- l'ancien payload envoyait la mauvaise cle, provoquant un 422 Pydantic
    systematique ("recency_days Field required") malgre une valeur bien
    fournie par l'agent."""
    try:
        payload = {"recency_days": recency, "frequency": frequency, "monetary": monetary}
        return requests.post(f"{BASE_URL}/api/customers/predict-segment", json=payload, timeout=_INTERNAL_HTTP_TIMEOUT).json()
    except Exception as e:
        return {"error": f"Impossible de contacter l'API clients : {e}"}


def get_customer_segments():
    """Recupere le profil et la taille de chaque segment client (RFM/KMeans)."""
    try:
        return _cached_get(f"{BASE_URL}/api/customers/segments/summary")
    except Exception as e:
        return {"error": f"Impossible de contacter l'API clients : {e}"}



def get_category_count():
    """Nombre de categories de produits DISTINCTES dans tout le catalogue
    (pas juste le top N affiche par get_top_categories)."""
    try:
        return _cached_get(f"{BASE_URL}/api/analytics/categories/count")
    except Exception as e:
        return {"error": f"Impossible de contacter l'API analytics : {e}"}


def get_state_count():
    """Nombre d'Etats clients DISTINCTS dans toutes les commandes."""
    try:
        return _cached_get(f"{BASE_URL}/api/analytics/states/count")
    except Exception as e:
        return {"error": f"Impossible de contacter l'API analytics : {e}"}


def get_category_averages(category: str):
    """Caracteristiques MOYENNES d'une categorie : prix moyen, frais de port
    moyen, delai de livraison moyen, note moyenne, % de retard -- sur toute
    la periode disponible. Different de get_revenue_for_category (qui donne
    un TOTAL, pas des moyennes)."""
    try:
        data = _cached_get(f"{BASE_URL}/api/analytics/categories/{category}/averages")
        if isinstance(data, dict) and "detail" in data and "avg_price" not in data:
            return {"error": data["detail"]}
        return data
    except Exception as e:
        return {"error": f"Impossible de contacter l'API analytics : {e}"}


def get_top_sellers(state: str = None, city: str = None, limit: int = 5):
    """Top VENDEURS par chiffre d'affaires, filtrable par l'etat et/ou la
    ville DU VENDEUR (pas du client -- pour ca, get_top_customers)."""
    try:
        params = {"limit": limit}
        if state:
            params["state"] = state
        if city:
            params["city"] = city
        data = _cached_get(f"{BASE_URL}/api/analytics/sellers/top", params)
        if isinstance(data, dict) and "detail" in data:
            return {"error": data["detail"]}
        return data
    except Exception as e:
        return {"error": f"Impossible de contacter l'API analytics : {e}"}


def get_top_customers(state: str = None, city: str = None, limit: int = 5):
    """Top CLIENTS par montant total depense, filtrable par etat et/ou ville
    DU CLIENT (pas du vendeur -- pour ca, get_top_sellers)."""
    try:
        params = {"limit": limit}
        if state:
            params["state"] = state
        if city:
            params["city"] = city
        data = _cached_get(f"{BASE_URL}/api/analytics/customers/top", params)
        if isinstance(data, dict) and "detail" in data:
            return {"error": data["detail"]}
        return data
    except Exception as e:
        return {"error": f"Impossible de contacter l'API analytics : {e}"}


_BR_STATE_CODES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


def search_reviews(query: str, category: str = None):
    """Recherche generale dans les avis clients (positifs, negatifs, neutres)."""
    if category and category.strip().upper() in _BR_STATE_CODES:
        return {"clarification_needed": (
            f"'{category}' est un code d'État brésilien, pas une catégorie de produit. "
            "Précise plutôt quelle catégorie t'intéresse (ex: meubles, informatica_acessorios)."
        )}
    result = search_customer_reviews(query=query, n_results=5, category=category)
    return {
        "query": query,
        "category": category,
        "category_matched": result["category_matched"],
        "retrieved_reviews": result["documents"],
    }


def explain_category_complaints(category: str):
    """Va chercher specifiquement les avis NEGATIFS (note <= 2) d'une
    categorie pour expliquer un taux d'avis negatifs eleve."""
    if category and category.strip().upper() in _BR_STATE_CODES:
        return {"clarification_needed": (
            f"'{category}' est un code d'État brésilien, pas une catégorie de produit. "
            "Précise plutôt quelle catégorie t'intéresse (ex: meubles, informatica_acessorios)."
        )}
    result = search_customer_reviews(
        query="problème qualité livraison retard défaut produit cassé",
        n_results=8, category=category, max_score=2,
    )
    if not result["documents"]:
        return {"category": category, "found": False, "reviews": []}
    return {
        "category": category,
        "found": True,
        "category_matched": result["category_matched"],
        "reviews": result["documents"],
    }


TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "get_kpi_summary",
            "description": "Indicateurs cles globaux : commandes, CA total, panier moyen.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_revenue_by_month",
            "description": "Evolution mensuelle COMPLETE du CA (serie entiere). Pour un mois/semaine precis -> get_revenue_for_period.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_revenue_for_period",
            "description": (
                "CA reel sur UNE periode precise : 'weeks_ago' (0=derniere semaine, 1=celle d'avant) "
                "OU 'month' (format 'YYYY-MM'). Un seul des deux, jamais les deux."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "weeks_ago": {"type": "integer", "description": "0=derniere semaine, 1=celle d'avant, etc."},
                    "month": {"type": "string", "description": "Format YYYY-MM"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_categories",
            "description": "Classement des categories les plus vendues en CA. Passe 'limit' si l'utilisateur precise un nombre (top 10, top 3...), sinon 5 par defaut.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "Nombre a retourner, ex: 10 pour 'top 10'"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_revenue_for_category",
            "description": "CA REEL total (toute la periode) d'UNE categorie precise -- pas un classement.",
            "parameters": {
                "type": "object",
                "properties": {"category": {"type": "string", "description": "Categorie telle que formulee par l'utilisateur"}},
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_revenue_for_state",
            "description": "CA REEL total pour UN etat CLIENT precis (ex: 'SP', 'RJ'), parmi le top 10 par CA.",
            "parameters": {
                "type": "object",
                "properties": {"state": {"type": "string", "description": "Code etat, ex: 'SP'"}},
                "required": ["state"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_category_count",
            "description": "Nombre TOTAL de categories de produits distinctes dans le catalogue (question 'combien de categories avons-nous').",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_state_count",
            "description": "Nombre TOTAL d'Etats clients distincts (question 'combien d'etats avons-nous').",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_category_averages",
            "description": "Caracteristiques MOYENNES d'une categorie (prix moyen, frais de port moyen, delai de livraison moyen, note moyenne) -- PAS un total (pour ca, get_revenue_for_category).",
            "parameters": {
                "type": "object",
                "properties": {"category": {"type": "string", "description": "Categorie telle que formulee par l'utilisateur"}},
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_sellers",
            "description": "Top VENDEURS par CA, filtrable par etat et/ou ville DU VENDEUR (seller_state/seller_city). Pas les clients -> get_top_customers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {"type": "string", "description": "Code etat du vendeur, optionnel, ex: 'SP'"},
                    "city": {"type": "string", "description": "Ville du vendeur, optionnelle"},
                    "limit": {"type": "integer", "description": "Nombre a retourner, defaut 5"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_customers",
            "description": "Top CLIENTS par montant depense, filtrable par etat et/ou ville DU CLIENT. Pas les vendeurs -> get_top_sellers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {"type": "string", "description": "Code etat du client, optionnel, ex: 'SP'"},
                    "city": {"type": "string", "description": "Ville du client, optionnelle"},
                    "limit": {"type": "integer", "description": "Nombre a retourner, defaut 5"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forecast_category_revenue",
            "description": (
                "Prevision de CA. 'category' = terme exact de l'utilisateur (jamais traduit). "
                "'state' optionnel. 'target_month' (format 'YYYY-MM') si un mois cible est precise -- "
                "sans lui, prevoit seulement le mois suivant les dernieres donnees connues."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Categorie telle que formulee par l'utilisateur"},
                    "state": {"type": "string", "description": "Code etat optionnel, ex: 'SP'"},
                    "target_month": {"type": "string", "description": "Mois cible optionnel, format 'YYYY-MM'"},
                },
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "predict_delivery_risk",
            "description": (
                "Risque de retard de livraison. SEULS category/customer_state/order_month "
                "necessaires -- jamais refuser pour prix/poids/etc. manquants."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Categorie telle que formulee par l'utilisateur"},
                    "customer_state": {"type": "string", "description": "Code etat, ex: 'SP'"},
                    "order_month": {"type": "integer", "description": "Mois 1-12"},
                },
                "required": ["category", "customer_state", "order_month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_segments",
            "description": "Segments clients existants (Champions, Dormants...) avec taille et profil.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "predict_customer_segment",
            "description": (
                "Predit le segment d'un client HYPOTHETIQUE, a partir de recency/frequency/monetary. "
                "Pour un client deja connu -> get_customer_segments."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "recency": {"type": "number", "description": "Jours depuis le dernier achat"},
                    "frequency": {"type": "number", "description": "Nombre de commandes passees"},
                    "monetary": {"type": "number", "description": "Montant total depense"},
                },
                "required": ["recency", "frequency", "monetary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_reviews",
            "description": "Recherche generale dans les avis clients.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Termes de recherche"},
                    "category": {"type": "string", "description": "Filtre optionnel par categorie"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_category_complaints",
            "description": "Pourquoi une categorie a un taux d'avis negatifs eleve. Pas pour un avis general -> search_reviews.",
            "parameters": {
                "type": "object",
                "properties": {"category": {"type": "string"}},
                "required": ["category"],
            },
        },
    },
]

AVAILABLE_FUNCTIONS = {
    "get_kpi_summary": get_kpi_summary,
    "get_revenue_by_month": get_revenue_by_month,
    "get_revenue_for_period": get_revenue_for_period,
    "get_top_categories": get_top_categories,
    "get_revenue_for_category": get_revenue_for_category,
    "get_revenue_for_state": get_revenue_for_state,
    "get_category_count": get_category_count,
    "get_state_count": get_state_count,
    "get_category_averages": get_category_averages,
    "get_top_sellers": get_top_sellers,
    "get_top_customers": get_top_customers,
    "forecast_category_revenue": forecast_category_revenue,
    "predict_delivery_risk": predict_delivery_risk,
    "get_customer_segments": get_customer_segments,
    "predict_customer_segment": predict_customer_segment,
    "search_reviews": search_reviews,
    "explain_category_complaints": explain_category_complaints,
}
