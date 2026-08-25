# backend/app/agent/tools.py
"""
Outils de l'agent BI.

Principe de conception : chaque fonction retourne soit un dict/liste de
donnees brutes (jamais reformulees par un LLM -- voir agent.py), soit
{"error": {...}} en cas d'echec. Aucune fonction n'utilise une valeur par
defaut Python SILENCIEUSE pour masquer un manque d'info : les parametres
REQUIS n'ont pas de defaut (donc call_tool_safely() dans agent.py detecte
leur absence et demande une clarification a l'utilisateur) ; les parametres
optionnels ont une valeur de reference explicite, et leur usage est
TOUJOURS signale dans la reponse finale (jamais une estimation ne se fait
passer pour une valeur exacte sans le dire).
"""
import time
import requests
from app.rag.search import search_customer_reviews

BASE_URL = "http://localhost:8000"

# Timeout sur TOUS les appels HTTP internes (agent -> notre propre API
# Flask). Sans ca, un endpoint interne qui bloque bloque l'agent
# indefiniment, sans meme laisser une chance au timeout Ollama de
# s'appliquer (ce n'est pas le meme appel).
_INTERNAL_HTTP_TIMEOUT = 15

# Cache memoire simple avec TTL, applique UNIQUEMENT aux outils en lecture
# seule (KPI/dashboard) -- jamais aux endpoints ML de prediction, qui
# doivent refleter exactement les parametres de chaque appel.
_cache = {}
_CACHE_TTL = 300  # 5 min -- les donnees Olist sont historiques/figees


def _cached_get(url: str, params: dict | None = None):
    key = f"{url}?{params}"
    now = time.time()
    cached = _cache.get(key)
    if cached and (now - cached[1] < _CACHE_TTL):
        return cached[0]
    response = requests.get(url, params=params, timeout=_INTERNAL_HTTP_TIMEOUT).json()
    _cache[key] = (response, now)
    return response


# ---------------------------------------------------------------------------
# Outils "factuels" (lecture seule, reponse formatee par un template Python
# deterministe -- voir TEMPLATES_FR/EN dans agent.py)
# ---------------------------------------------------------------------------

def get_kpi_summary():
    """Recupere les KPI globaux : nombre de commandes, CA total, panier moyen."""
    try:
        return _cached_get(f"{BASE_URL}/api/dashboard/summary")
    except Exception as e:
        return {"error": f"Impossible de contacter l'API KPI : {e}"}


def get_revenue_by_month():
    """Recupere l'evolution du chiffre d'affaires mois par mois (serie
    COMPLETE, non filtree, sans aucun parametre). Pour une periode PRECISE
    (une semaine ou un mois donne) -> get_revenue_for_period."""
    try:
        return _cached_get(f"{BASE_URL}/api/dashboard/revenue-by-month")
    except Exception as e:
        return {"error": f"Impossible de contacter l'API KPI : {e}"}


def get_revenue_for_period(weeks_ago: int = None, month: str = None):
    """CA REEL sur UNE PERIODE PRECISE -- UN SEUL outil flexible plutot que
    plusieurs outils par grain temporel (semaine vs mois vs...), qui ne
    ferait que reporter a l'infini le meme probleme a chaque nouvelle
    granularite. Fournis UN SEUL des deux parametres, jamais les deux :
    - weeks_ago (semaine, en remontant depuis la derniere connue : 0 =
      derniere semaine, 1 = celle d'avant, 2 = encore avant...)
    - month (mois precis, format 'YYYY-MM', ex: '2017-02' pour fevrier 2017)
    Les DEUX etant optionnels en Python, cet outil n'est jamais route de
    facon deterministe -- c'est au LLM d'extraire, depuis la formulation
    naturelle de l'utilisateur, LEQUEL des deux s'applique et sa valeur.
    Pour la serie complete sans filtre -> get_revenue_by_month."""
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
    """Recupere les categories de produits generant le plus de CA."""
    limit = max(1, min(limit, 20))
    try:
        return _cached_get(f"{BASE_URL}/api/dashboard/top-categories", {"limit": limit})
    except Exception as e:
        return {"error": f"Impossible de contacter l'API KPI : {e}"}


def get_customer_segments():
    """Recupere le profil et la taille de chaque segment client (RFM/KMeans)."""
    try:
        return _cached_get(f"{BASE_URL}/api/customers/segments/summary")
    except Exception as e:
        return {"error": f"Impossible de contacter l'API clients : {e}"}


def forecast_category_revenue(category: str, state: str = None, target_month: str = None):
    """Prevision de CA pour une categorie (et optionnellement un etat et un
    mois cible). Sans target_month, prevoit UNIQUEMENT le mois suivant les
    dernieres donnees connues -- avec target_month (format 'YYYY-MM'), une
    prevision RECURSIVE (mois par mois, incertitude croissante avec
    l'horizon) est faite jusqu'a ce mois. Plafonnee cote API a 6 mois
    d'ecart max."""
    try:
        params = {"category": category}
        if state:
            params["state"] = state
        if target_month:
            params["target_month"] = target_month
        result = _cached_get(f"{BASE_URL}/api/ml/forecast/by-category", params)
        # Flask abort() renvoie {"detail": "..."} sur une erreur HTTP (400,
        # 404...) -- _cached_get ne verifie pas le code de statut, donc on
        # normalise ici pour que agent.py le traite comme une vraie erreur
        # au lieu d'essayer (et d'echouer) de le passer dans un template.
        if isinstance(result, dict) and "detail" in result and "predicted_revenue_total" not in result:
            return {"error": result["detail"]}
        return result
    except Exception as e:
        return {"error": f"Impossible de contacter l'API ML : {e}"}


# ---------------------------------------------------------------------------
# Outils de prediction ML -- PAS de cache (chaque appel doit refleter
# exactement ses parametres). Les parametres REQUIS (sans defaut Python)
# forcent call_tool_safely() a demander une clarification s'ils manquent ;
# les parametres optionnels ont une valeur de reference, signalee
# automatiquement dans la reponse.
# ---------------------------------------------------------------------------

def predict_delivery_risk(
    category: str, customer_state: str, order_month: int,
    total_price: float = 150, total_freight: float = 20, n_items: int = 1,
    n_unique_products: int = 1, n_unique_sellers: int = 1, pct_same_state: float = 0.5,
    avg_product_weight_g: float = 800, max_product_weight_g: float = 800,
    n_payment_installments_max: int = 3, has_voucher: int = 0,
):
    """Estime le risque de retard de livraison pour une commande hypothetique.
    Seuls category/customer_state/order_month sont requis -- les autres ont
    une valeur de reference (commande Olist moyenne), signalee automatiquement
    par call_tool_safely() si non fournie par l'appelant."""
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
    hypothetique. Les 3 parametres sont necessaires (pas de valeur de
    reference pertinente pour un profil client) -- si l'un manque,
    call_tool_safely() demandera une clarification plutot que d'inventer."""
    try:
        payload = {"recency": recency, "frequency": frequency, "monetary": monetary}
        return requests.post(f"{BASE_URL}/api/customers/predict-segment", json=payload, timeout=_INTERNAL_HTTP_TIMEOUT).json()
    except Exception as e:
        return {"error": f"Impossible de contacter l'API clients : {e}"}


# ---------------------------------------------------------------------------
# Outils RAG (avis clients, ChromaDB) -- reponse synthetisee par un 2e appel
# LLM dans agent.py (contenu qualitatif/texte libre, pas de template possible).
# ---------------------------------------------------------------------------

_BR_STATE_CODES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


def search_reviews(query: str, category: str = None):
    """Recherche generale dans les avis clients (positifs, negatifs, neutres)."""
    # Validation de parametre (meme niveau que "1 <= order_month <= 12" dans
    # predict_delivery_risk) : un code d'Etat n'est jamais une categorie de
    # produit. Ce n'est pas l'outil qu'on choisit ici, juste une valeur
    # invalide pour CET outil -- le LLM reste seul decideur du CHOIX d'outil.
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


# ---------------------------------------------------------------------------
# TOOLS_SPEC : ce que le LLM lit reellement pour choisir un outil. DOIT
# rester en phase avec AVAILABLE_FUNCTIONS et TEMPLATES_FR/EN (agent.py) --
# le garde-fou de synchronisation dans agent.py plante au demarrage sinon.
# ---------------------------------------------------------------------------
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
            "description": "Categories de produits les plus vendues en CA.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "Nombre a retourner"}},
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
                "necessaires -- jamais refuser pour prix/poids/etc. manquants, valeurs par defaut utilisees."
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
                "Predit le segment d'un client HYPOTHETIQUE (scenario 'et si'), a partir de "
                "recency/frequency/monetary. Pour un client deja connu -> get_customer_segments."
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
            "description": "Pourquoi une categorie a un taux d'avis negatifs eleve (motifs recurrents). Pas pour un avis general -> search_reviews.",
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
    "forecast_category_revenue": forecast_category_revenue,
    "predict_delivery_risk": predict_delivery_risk,
    "get_customer_segments": get_customer_segments,
    "predict_customer_segment": predict_customer_segment,
    "search_reviews": search_reviews,
    "explain_category_complaints": explain_category_complaints,
}