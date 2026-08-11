# backend/app/routers/products.py
import random
from datetime import datetime
from flask import Blueprint, request, jsonify
from app.database import get_db

DATA_CUTOFF = datetime(2018, 9, 1)

products_bp = Blueprint("products", __name__)


@products_bp.get("/analytics")
def get_products_analytics():
    """Vraie performance par categorie, calculee depuis fact_order_items,
    enrichie par un $lookup vers fact_orders pour recuperer review_score
    (colonne absente de fact_order_items, exactement comme le JOIN SQL
    original)."""
    db = get_db()
    pipeline = [
        {"$match": {
            "order_purchase_timestamp": {"$lt": DATA_CUTOFF},
            "product_category_name": {"$ne": None},
        }},
        {"$lookup": {
            "from": "fact_orders",
            "localField": "order_id",
            "foreignField": "order_id",
            "as": "order_info",
        }},
        {"$unwind": {"path": "$order_info", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": "$product_category_name",
            "volume": {"$sum": 1},
            "margin": {"$avg": "$estimated_margin"},
            "freight_ratio": {"$avg": "$freight_ratio"},
            "avg_delay_days": {"$avg": "$delivery_delay_days"},
            "bad_reviews_pct": {
                "$avg": {"$cond": [{"$lte": ["$order_info.review_score", 2]}, 1.0, 0.0]}
            },
        }},
        {"$sort": {"volume": -1}},
        {"$limit": 15},
    ]
    rows = db.fact_order_items.aggregate(pipeline)

    return jsonify([
        {
            "category_name": row["_id"],
            "volume": row["volume"],
            "margin": round(float(row["margin"]), 2) if row.get("margin") is not None else None,
            "freight_ratio": round(float(row["freight_ratio"]) * 100, 1) if row.get("freight_ratio") is not None else None,
            "avg_delay_days": round(float(row["avg_delay_days"]), 1) if row.get("avg_delay_days") is not None else None,
            "bad_reviews_pct": round(float(row["bad_reviews_pct"]) * 100, 1) if row.get("bad_reviews_pct") is not None else None,
        }
        for row in rows
    ])


@products_bp.get("/top-reviews")
def get_top_positive_reviews():
    """Quelques avis positifs (note >= 4) pour une categorie, pour comprendre
    pourquoi elle plait. Texte original (portugais)."""
    db = get_db()
    category = request.args.get("category")
    limit = int(request.args.get("limit", 3))

    
    pipeline = [
        {"$lookup": {
            "from": "fact_order_items",
            "localField": "order_id",
            "foreignField": "order_id",
            "as": "item",
        }},
        {"$unwind": "$item"},
        {"$match": {
            "item.product_category_name_english": category,
            "review_score": {"$gte": 4},
            "review_comment_message": {"$nin": [None, ""]},
        }},
        {"$group": {"_id": "$review_comment_message"}},  # equivalent DISTINCT
    ]
    distinct_comments = [row["_id"] for row in db.fact_reviews.aggregate(pipeline)]

    sample_size = min(limit, len(distinct_comments))
    return jsonify(random.sample(distinct_comments, sample_size) if sample_size else [])
