# backend/app/agent/tools.py
import requests
from app.rag.search import search_customer_reviews

BASE_URL = "http://localhost:8000"


def get_kpi_summary():
    """Récupère les KPI globaux : nombre de commandes, CA total, panier moyen."""
    try:
        return requests.get(f"{BASE_URL}/api/dashboard/summary").json()
    except Exception as e:
        return {"error": f"Impossible de contacter l'API KPI : {str(e)}"}


def get_revenue_for_week(weeks_ago: int = 0):
    """Recupere le CA reel d'une semaine passee (weeks_ago=0 = derniere semaine
    connue, 1 = celle d'avant, 2 = encore avant...)."""
    try:
        return requests.get(
            f"{BASE_URL}/api/dashboard/revenue-by-week", params={"weeks_ago": weeks_ago}
        ).json()
    except Exception as e:
        return {"error": f"Impossible de contacter l'API KPI : {str(e)}"}


def get_revenue_by_month():
    """Récupère l'évolution du chiffre d'affaires mois par mois."""
    try:
        return requests.get(f"{BASE_URL}/api/dashboard/revenue-by-month").json()
    except Exception as e:
        return {"error": f"Impossible de contacter l'API KPI : {str(e)}"}


def get_revenue_last_week():
    """Récupère le chiffre d'affaires réel de la dernière semaine complète connue."""
    try:
        return requests.get(f"{BASE_URL}/api/dashboard/revenue-last-week").json()
    except Exception as e:
        return {"error": f"Impossible de contacter l'API KPI : {str(e)}"}


def get_top_categories(limit: int = 5):
    """Récupère les catégories de produits générant le plus de chiffre d'affaires."""
    try:
        return requests.get(
            f"{BASE_URL}/api/dashboard/top-categories", params={"limit": limit}
        ).json()
    except Exception as e:
        return {"error": f"Impossible de contacter l'API KPI : {str(e)}"}


def search_reviews(query: str, category: str = None):
    """Recherche dans les avis textuels laisses par les clients, avec filtre
    optionnel par categorie."""
    result = search_customer_reviews(query=query, n_results=5, category=category)
    return {
        "query": query,
        "category": category,
        "category_matched": result["category_matched"],
        "retrieved_reviews": result["documents"],
    }


def explain_category_complaints(category: str):
    """Va chercher specifiquement les avis NEGATIFS (note <= 2) d'une
    categorie pour expliquer un taux d'avis negatifs eleve -- relie le
    signal quantitatif (bad_reviews_pct de la page Catalogue) a une
    explication qualitative issue des vrais avis clients."""
    result = search_customer_reviews(
        query="problème qualité livraison retard défaut produit cassé",
        n_results=8,
        category=category,
        max_score=2,
    )
    if not result["documents"]:
        return {"category": category, "found": False, "reviews": []}
    return {
        "category": category,
        "found": True,
        # False = le nom de categorie transmis ne correspondait a aucune
        # metadonnee reelle ; les avis ci-dessous sont donc GENERAUX
        # (toutes categories), pas specifiques a la categorie demandee.
        "category_matched": result["category_matched"],
        "reviews": result["documents"],
    }


def forecast_category_revenue(category: str, state: str = None):
    """Prevision de CA pour une categorie (et optionnellement un etat)."""
    try:
        params = {"category": category}
        if state:
            params["state"] = state
        return requests.get(f"{BASE_URL}/api/ml/forecast/by-category", params=params).json()
    except Exception as e:
        return {"error": f"Impossible de contacter l'API ML : {str(e)}"}


def predict_delivery_risk(
    category: str, customer_state: str, order_month: int,
    total_price: float = 150, total_freight: float = 20, n_items: int = 1,
    n_unique_products: int = 1, n_unique_sellers: int = 1, pct_same_state: float = 0.5,
    avg_product_weight_g: float = 800, max_product_weight_g: float = 800,
    n_payment_installments_max: int = 3, has_voucher: int = 0,
):
    """Estime le risque de retard de livraison pour une commande hypothetique."""
    payload = {
        "category": category, "customer_state": customer_state, "order_month": order_month,
        "total_price": total_price, "total_freight": total_freight, "n_items": n_items,
        "n_unique_products": n_unique_products, "n_unique_sellers": n_unique_sellers,
        "pct_same_state": pct_same_state, "avg_product_weight_g": avg_product_weight_g,
        "max_product_weight_g": max_product_weight_g,
        "n_payment_installments_max": n_payment_installments_max, "has_voucher": has_voucher,
    }
    try:
        return requests.post(f"{BASE_URL}/api/ml/predict/delay-risk", json=payload).json()
    except Exception as e:
        return {"error": f"Impossible de contacter l'API ML : {str(e)}"}


def get_customer_segments():
    """Recupere le profil et la taille de chaque segment client (RFM/KMeans)."""
    try:
        return requests.get(f"{BASE_URL}/api/customers/segments/summary").json()
    except Exception as e:
        return {"error": f"Impossible de contacter l'API clients : {str(e)}"}


def predict_customer_segment(recency: float, frequency: float, monetary: float):
    """Predit EN DIRECT le segment RFM/KMeans (Champions, Dormants, ...) pour
    un profil client hypothetique (recency en jours, frequency = nombre de
    commandes, monetary = montant total depense), en symetrie avec
    predict_delivery_risk et forecast_category_revenue."""
    payload = {"recency": recency, "frequency": frequency, "monetary": monetary}
    try:
        return requests.post(f"{BASE_URL}/api/customers/predict-segment", json=payload).json()
    except Exception as e:
        return {"error": f"Impossible de contacter l'API clients : {str(e)}"}



TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "explain_category_complaints",
            "description": (
                "Explique pourquoi une categorie de produit a un taux d'avis negatifs eleve, "
                "en citant les motifs recurrents trouves dans les vrais avis clients de cette categorie. "
                "Utilise cet outil quand l'utilisateur demande POURQUOI une categorie est mal notee."
            ),
            "parameters": {
                "type": "object",
                "properties": {"category": {"type": "string"}},
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_kpi_summary",
            "description": (
                "Récupère les indicateurs clés globaux : nombre total de"
                " commandes, chiffre d'affaires total, panier moyen."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_revenue_for_week",
            "description": (
                "Recupere le CA reel d'une semaine passee specifique, en comptant "
                "en arriere depuis la derniere semaine connue (weeks_ago=0 = la "
                "derniere, 1 = celle d'avant, 2 = encore avant...). Utilise cet "
                "outil des que l'utilisateur precise 'il y a N semaines' ou "
                "compare plusieurs semaines. Ne correspond PAS a un numero de "
                "semaine calendaire ISO."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "weeks_ago": {
                        "type": "integer",
                        "description": "0 = derniere semaine connue, 1 = celle d'avant, etc.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_revenue_by_month",
            "description": (
                "Récupère l'évolution mensuelle du chiffre d'affaires, utile"
                " pour les questions de tendance/évolution."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_revenue_last_week",
            "description": (
                "Récupère le chiffre d'affaires RÉEL déjà réalisé la semaine dernière "
                "(pas une prévision). Utilise cet outil pour toute question sur "
                "le CA de 'la semaine dernière', 'la semaine précédente', 'cette semaine passée'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_categories",
            "description": (
                "Récupère les catégories de produits les plus vendues en"
                " chiffre d'affaires."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Nombre de catégories à retourner",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forecast_category_revenue",
            "description": "Prevision de chiffre d'affaires pour une categorie de produit specifique, avec repartition par etat optionnelle.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Nom de la categorie en anglais, ex: 'bed_bath_table'"},
                    "state": {"type": "string", "description": "Code etat client optionnel, ex: 'SP'"},
                },
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "predict_delivery_risk",
            "description": "Estime la probabilite de retard de livraison d'une commande selon sa categorie, l'etat client et le mois.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "customer_state": {"type": "string"},
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
            "description": "Recupere les segments clients (Champions, Dormants, etc.) avec leur taille et profil, pour le ciblage marketing.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "predict_customer_segment",
            "description": (
                "Predit EN DIRECT a quel segment RFM/KMeans (Champions, "
                "Dormants, Nouveaux/petits paniers, Gros acheteurs one-shot) "
                "appartiendrait un client hypothetique, a partir de sa recence "
                "(jours depuis le dernier achat), sa frequence (nombre de "
                "commandes) et son montant total depense. Utilise cet outil "
                "pour un scenario 'et si un client avait tel profil ?', pas "
                "pour un client deja connu dans la base (utiliser plutot "
                "get_customer_segments)."
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
            "description": (
                "Recherche dans les commentaires et avis textuels des clients"
                " (qualitatif : problèmes de livraison, qualité produit,"
                " satisfaction)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Termes de recherche dans les avis"},
                    "category": {"type": "string", "description": "Filtre optionnel par categorie de produit"},
                },
                "required": ["query"],
            },
        },
    },
]

AVAILABLE_FUNCTIONS = {
    "get_kpi_summary": get_kpi_summary,
    "get_revenue_for_week": get_revenue_for_week,
    "get_revenue_by_month": get_revenue_by_month,
    "get_revenue_last_week": get_revenue_last_week,
    "get_top_categories": get_top_categories,
    "search_reviews": search_reviews,
    "forecast_category_revenue": forecast_category_revenue,
    "predict_delivery_risk": predict_delivery_risk,
    "get_customer_segments": get_customer_segments,
    "predict_customer_segment": predict_customer_segment,
    "explain_category_complaints": explain_category_complaints,
}