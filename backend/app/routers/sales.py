# backend/app/routers/sales.py
from datetime import datetime
from flask import Blueprint, request, jsonify
from app.database import get_db

DATA_CUTOFF = datetime(2018, 9, 1)

sales_bp = Blueprint("sales", __name__)


@sales_bp.get("/metrics")
def get_sales_metrics():
    """Vraies metriques de vente - retourne des NOMBRES, jamais des chaines formatees."""
    db = get_db()
    pipeline = [
        {"$match": {"order_purchase_timestamp": {"$lt": DATA_CUTOFF}}},
        {"$group": {
            "_id": None,
            "total_margin": {"$sum": {"$ifNull": ["$estimated_margin", 0]}},
            "sum_price": {"$sum": {"$ifNull": ["$price", 0]}},
            "freight_ratio": {"$avg": "$freight_ratio"},
            "same_state_ratio": {"$avg": "$same_state_delivery"},
        }},
    ]
    result = next(iter(db.fact_order_items.aggregate(pipeline)), None)
    if not result:
        return jsonify({"totalMargin": 0.0, "freightRatio": 0.0, "sameStateRatio": 0.0})

    freight_ratio = float(result["freight_ratio"]) if result["sum_price"] > 0 and result.get("freight_ratio") is not None else 0.0
    same_state_ratio = float(result["same_state_ratio"]) if result.get("same_state_ratio") is not None else 0.0

    return jsonify({
        "totalMargin": round(float(result["total_margin"]), 2),
        "freightRatio": round(freight_ratio * 100, 1),
        "sameStateRatio": round(same_state_ratio * 100, 1),
    })


@sales_bp.get("/revenue-by-state")
def get_revenue_by_state():
    """CA par etat client, pour un graphique de repartition geographique des ventes."""
    db = get_db()
    pipeline = [
        {"$match": {"order_purchase_timestamp": {"$lt": DATA_CUTOFF}}},
        {"$group": {"_id": "$customer_state", "revenue": {"$sum": "$total_item_value"}}},
        {"$sort": {"revenue": -1}},
        {"$limit": 10},
    ]
    rows = db.fact_order_items.aggregate(pipeline)
    return jsonify([{"state": row["_id"], "revenue": round(float(row["revenue"]), 2)} for row in rows])


@sales_bp.get("/top-sellers")
def get_top_sellers():
    """Top vendeurs par CA genere, avec leur etat d'origine."""
    db = get_db()
    limit = int(request.args.get("limit", 10))

    pipeline = [
        {"$match": {"order_purchase_timestamp": {"$lt": DATA_CUTOFF}}},
        {"$group": {
            "_id": {"seller_id": "$seller_id", "seller_state": "$seller_state"},
            "revenue": {"$sum": "$total_item_value"},
            "n_items": {"$sum": 1},
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": limit},
    ]
    rows = db.fact_order_items.aggregate(pipeline)

    return jsonify([
        {
            "seller_id": row["_id"]["seller_id"][:8] + "...",
            "seller_state": row["_id"]["seller_state"],
            "revenue": round(float(row["revenue"]), 2),
            "n_items": row["n_items"],
        }
        for row in rows
    ])


@sales_bp.get("/best-seller-by-season")
def get_best_seller_by_season():
    """Categorie generant le plus de CA pour chaque saison, sur toute la
    periode stable. Saisons = hemisphere sud (Bresil) : ete = dec-fev,
    automne = mar-mai, hiver = juin-aout, printemps = sep-nov."""
    db = get_db()
    pipeline = [
        {"$match": {
            "order_purchase_timestamp": {"$lt": DATA_CUTOFF},
            "product_category_name_english": {"$ne": None},
        }},
        {"$project": {
            "product_category_name_english": 1,
            "total_item_value": 1,
            "month": {"$month": "$order_purchase_timestamp"},
            "year": {"$year": "$order_purchase_timestamp"},
        }},
        {"$group": {
            "_id": {
                "season_year": {
                    "$cond": [{"$eq": ["$month", 12]}, {"$add": ["$year", 1]}, "$year"]
                },
                "season": {
                    "$switch": {
                        "branches": [
                            {"case": {"$in": ["$month", [12, 1, 2]]}, "then": "Été"},
                            {"case": {"$in": ["$month", [3, 4, 5]]}, "then": "Automne"},
                            {"case": {"$in": ["$month", [6, 7, 8]]}, "then": "Hiver"},
                        ],
                        "default": "Printemps",
                    }
                },
                "category": "$product_category_name_english",
            },
            "revenue": {"$sum": "$total_item_value"},
        }},
    ]
    rows = list(db.fact_order_items.aggregate(pipeline))

    season_order = {"Été": 0, "Automne": 1, "Hiver": 2, "Printemps": 3}
    best = {}
    for r in rows:
        key = (r["_id"]["season_year"], r["_id"]["season"])
        revenue = float(r["revenue"])
        if key not in best or revenue > best[key]["revenue"]:
            best[key] = {"category": r["_id"]["category"], "revenue": revenue}

    result = [
        {
            "label": f"{season} {season_year}",
            "season_year": season_year,
            "season": season,
            "category": data["category"],
            "revenue": round(data["revenue"], 2),
        }
        for (season_year, season), data in best.items()
    ]
    result.sort(key=lambda x: (x["season_year"], season_order.get(x["season"], 9)))
    return jsonify(result)
