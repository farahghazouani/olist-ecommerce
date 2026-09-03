# backend/app/routers/analytics.py

from flask import Blueprint, jsonify, request
from app.database import get_db

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.get("/categories/count")
def category_count():
    """Nombre de categories de produits distinctes (fact_orders.main_category)."""
    db = get_db()
    categories = db.fact_orders.distinct("main_category")
    categories = sorted(c for c in categories if c)
    return jsonify({"count": len(categories), "categories": categories})


@analytics_bp.get("/states/count")
def state_count():
    """Nombre d'Etats clients distincts (fact_orders.customer_state)."""
    db = get_db()
    states = db.fact_orders.distinct("customer_state")
    states = sorted(s for s in states if s)
    return jsonify({"count": len(states), "states": states})


@analytics_bp.get("/categories/<category>/averages")
def category_averages(category):
    """Caracteristiques moyennes d'une categorie : prix, frais de port,
    delai de livraison, note moyenne -- sur TOUTE la periode disponible
    (pas un decoupage mensuel, voir garde-fou dans le template agent.py)."""
    db = get_db()
    pipeline = [
        {"$match": {"main_category": category}},
        {"$group": {
            "_id": None,
            "n_orders": {"$sum": 1},
            "avg_price": {"$avg": "$total_price"},
            "avg_freight": {"$avg": "$total_freight"},
            "avg_delivery_delay_days": {"$avg": "$delivery_delay_days"},
            "avg_review_score": {"$avg": "$review_score"},
            "pct_late": {"$avg": "$is_late"},
        }},
    ]
    result = list(db.fact_orders.aggregate(pipeline))
    if not result:
        known = sorted(c for c in db.fact_orders.distinct("main_category") if c)[:15]
        return jsonify({"detail": f"Catégorie '{category}' introuvable. Catégories connues (extrait) : {', '.join(known)}…"}), 404

    r = result[0]
    return jsonify({
        "category": category,
        "n_orders": r["n_orders"],
        "avg_price": round(r["avg_price"], 2) if r.get("avg_price") is not None else None,
        "avg_freight": round(r["avg_freight"], 2) if r.get("avg_freight") is not None else None,
        "avg_delivery_delay_days": round(r["avg_delivery_delay_days"], 1) if r.get("avg_delivery_delay_days") is not None else None,
        "avg_review_score": round(r["avg_review_score"], 2) if r.get("avg_review_score") is not None else None,
        "pct_late": round((r.get("pct_late") or 0) * 100, 1),
    })


@analytics_bp.get("/sellers/top")
def top_sellers():
    """Top vendeurs par CA, filtrable par etat et/ou ville du VENDEUR
    (seller_state/seller_city dans fact_order_items -- pas customer_state,
    qui est un champ different)."""
    db = get_db()
    state = request.args.get("state")
    city = request.args.get("city")
    limit = min(max(int(request.args.get("limit", 5)), 1), 50)

    match = {}
    if state:
        match["seller_state"] = state.strip().upper()
    if city:
        match["seller_city"] = {"$regex": f"^{city.strip()}$", "$options": "i"}

    pipeline = [
        {"$match": match} if match else {"$match": {}},
        {"$group": {
            "_id": "$seller_id",
            "revenue": {"$sum": "$total_item_value"},
            "n_orders": {"$sum": 1},
            "seller_state": {"$first": "$seller_state"},
            "seller_city": {"$first": "$seller_city"},
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": limit},
    ]
    results = list(db.fact_order_items.aggregate(pipeline))
    if not results:
        return jsonify({"detail": f"Aucun vendeur trouvé pour ces filtres (état={state}, ville={city})."}), 404

    return jsonify([{
        "seller_id": r["_id"], "revenue": round(r["revenue"], 2), "n_orders": r["n_orders"],
        "seller_state": r.get("seller_state"), "seller_city": r.get("seller_city"),
    } for r in results])
@analytics_bp.get("/states/revenue")
def states_revenue():
    """CA REEL par etat CLIENT, TOUS les etats (pas un top N)."""
    db = get_db()
    pipeline = [
        {"$group": {"_id": "$customer_state", "revenue": {"$sum": "$total_payment_value"}, "n_orders": {"$sum": 1}}},
        {"$sort": {"revenue": -1}},
    ]
    results = list(db.fact_orders.aggregate(pipeline))
    return jsonify([{"state": r["_id"], "revenue": round(r["revenue"], 2), "n_orders": r["n_orders"]} for r in results if r["_id"]])

@analytics_bp.get("/customers/top")
def top_customers():
    """Top clients par montant total depense, filtrable par etat et/ou
    ville du CLIENT (customer_state/customer_city dans fact_orders)."""
    db = get_db()
    state = request.args.get("state")
    city = request.args.get("city")
    limit = min(max(int(request.args.get("limit", 5)), 1), 50)

    match = {}
    if state:
        match["customer_state"] = state.strip().upper()
    if city:
        match["customer_city"] = {"$regex": f"^{city.strip()}$", "$options": "i"}

    pipeline = [
        {"$match": match} if match else {"$match": {}},
        {"$group": {
            "_id": "$customer_id",
            "total_spent": {"$sum": "$total_payment_value"},
            "n_orders": {"$sum": 1},
            "customer_state": {"$first": "$customer_state"},
            "customer_city": {"$first": "$customer_city"},
        }},
        {"$sort": {"total_spent": -1}},
        {"$limit": limit},
    ]
    results = list(db.fact_orders.aggregate(pipeline))
    if not results:
        return jsonify({"detail": f"Aucun client trouvé pour ces filtres (état={state}, ville={city})."}), 404

    return jsonify([{
        "customer_id": r["_id"], "total_spent": round(r["total_spent"], 2), "n_orders": r["n_orders"],
        "customer_state": r.get("customer_state"), "customer_city": r.get("customer_city"),
    } for r in results])
