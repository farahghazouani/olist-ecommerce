# backend/app/routers/kpi.py
from datetime import datetime
from flask import Blueprint, request, jsonify
from app.database import get_db


DATA_CUTOFF = datetime(2018, 9, 1)

kpi_bp = Blueprint("kpi", __name__)

MONTH_TRUNC = {"$dateFromParts": {
    "year": {"$year": "$order_purchase_timestamp"},
    "month": {"$month": "$order_purchase_timestamp"},
    "day": 1,
}}
WEEK_TRUNC = {"$dateFromParts": {
    "isoWeekYear": {"$isoWeekYear": "$order_purchase_timestamp"},
    "isoWeek": {"$isoWeek": "$order_purchase_timestamp"},
    "isoDayOfWeek": 1,  
}}


@kpi_bp.get("/summary")
def get_summary():
    """KPI globaux pour le dashboard executif."""
    db = get_db()
    pipeline = [
        {"$group": {
            "_id": None,
            "total_orders": {"$sum": 1},
            "total_revenue": {"$sum": {"$ifNull": ["$total_payment_value", 0]}},
            "avg_order_value": {"$avg": {"$ifNull": ["$total_payment_value", 0]}},
        }}
    ]
    result = next(iter(db.fact_orders.aggregate(pipeline)), None)
    if not result:
        return jsonify({"total_orders": 0, "total_revenue": 0.0, "avg_order_value": 0.0})

    return jsonify({
        "total_orders": result["total_orders"],
        "total_revenue": round(float(result["total_revenue"]), 2),
        "avg_order_value": round(float(result["avg_order_value"]), 2),
    })


@kpi_bp.get("/revenue-by-month")
def get_revenue_by_month():
    """CA mensuel pour le graphique d'evolution."""
    db = get_db()
    pipeline = [
        {"$group": {
            "_id": MONTH_TRUNC,
            "revenue": {"$sum": "$total_payment_value"},
        }},
        {"$sort": {"_id": 1}},
    ]
    rows = db.fact_orders.aggregate(pipeline)

    return jsonify([
        {
            "month": row["_id"].strftime("%Y-%m-%d") if row["_id"] else None,
            "revenue": round(float(row["revenue"]), 2),
        }
        for row in rows
    ])


@kpi_bp.get("/revenue-last-week")
def get_revenue_last_week():
    """
    CA reel de la derniere semaine COMPLETE et FIABLE connue.
    Exclut la periode de queue tronquee du dataset (apres 2018-08-31),
    coherent avec la fenetre stable utilisee pour toute la modelisation ML.
    """
    db = get_db()
    pipeline = [
        {"$match": {"order_purchase_timestamp": {"$lt": DATA_CUTOFF}}},
        {"$group": {
            "_id": WEEK_TRUNC,
            "revenue": {"$sum": {"$ifNull": ["$total_payment_value", 0]}},
            "n_orders": {"$sum": 1},
        }},
        {"$sort": {"_id": -1}},
        {"$limit": 1},
    ]
    result = next(iter(db.fact_orders.aggregate(pipeline)), None)
    if not result:
        return jsonify({"week": "N/A", "revenue": 0.0, "n_orders": 0})

    return jsonify({
        "week": result["_id"].strftime("%Y-%m-%d"),
        "revenue": round(float(result["revenue"]), 2),
        "n_orders": result["n_orders"],
    })


def _build_match(region, date_str):
    """Construit le filtre $match commun (region + date de depart) partage
    par /metrics et /risk-orders, pour que les deux widgets restent
    coherents avec les memes filtres appliques sur le dashboard."""
    match = {"order_purchase_timestamp": {"$lt": DATA_CUTOFF}}
    if region:
        match["customer_state"] = region
    if date_str:
        start = datetime.fromisoformat(date_str)
        match["order_purchase_timestamp"] = {"$lt": DATA_CUTOFF, "$gte": start}
    return match


@kpi_bp.get("/metrics")
def get_dashboard_metrics():
    """KPIs de la vue executive : GMV, taux de livraison a temps, CSAT,
    ratio fret/prix - avec variation vs le mois precedent dans le meme
    perimetre de filtre."""
    db = get_db()
    region = request.args.get("region")
    date_str = request.args.get("date")
    match = _build_match(region, date_str)

    agg_pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_gmv": {"$sum": {"$ifNull": ["$total_payment_value", 0]}},
            "on_time_rate": {"$avg": {"$cond": [{"$eq": ["$is_late", 0]}, 1.0, 0.0]}},
            "avg_csat": {"$avg": "$review_score"},
            "freight_ratio": {
                "$avg": {
                    "$cond": [
                        {"$and": [{"$ne": ["$total_price", 0]}, {"$ne": ["$total_price", None]}]},
                        {"$divide": ["$total_freight", "$total_price"]},
                        None,
                    ]
                }
            },
        }},
    ]
    agg = next(iter(db.fact_orders.aggregate(agg_pipeline)), None)

    trend_pipeline = [
        {"$match": match},
        {"$group": {
            "_id": MONTH_TRUNC,
            "revenue": {"$sum": {"$ifNull": ["$total_payment_value", 0]}},
            "on_time_rate": {"$avg": {"$cond": [{"$eq": ["$is_late", 0]}, 1.0, 0.0]}},
        }},
        {"$sort": {"_id": -1}},
        {"$limit": 2},
    ]
    trend_rows = list(db.fact_orders.aggregate(trend_pipeline))

    gmv_trend = "Pas assez de donnees"
    on_time_trend = "Pas assez de donnees"
    if len(trend_rows) == 2:
        latest, previous = trend_rows[0], trend_rows[1]
        if previous["revenue"]:
            pct = (float(latest["revenue"]) - float(previous["revenue"])) / float(previous["revenue"]) * 100
            gmv_trend = f"{pct:+.1f}% vs mois prec."
        delta_rate = (float(latest["on_time_rate"]) - float(previous["on_time_rate"])) * 100
        on_time_trend = f"{delta_rate:+.1f} pts vs mois prec."

    if not agg:
        return jsonify({
            "totalGmv": 0.0, "gmvTrend": gmv_trend, "onTimeRate": 0.0,
            "onTimeTrend": on_time_trend, "avgCsat": None, "freightRatio": 0.0,
        })

    freight_ratio = agg.get("freight_ratio")
    return jsonify({
        "totalGmv": round(float(agg["total_gmv"]), 2),
        "gmvTrend": gmv_trend,
        "onTimeRate": round(float(agg["on_time_rate"]) * 100, 1),
        "onTimeTrend": on_time_trend,
        "avgCsat": round(float(agg["avg_csat"]), 2) if agg.get("avg_csat") is not None else None,
        "freightRatio": round(float(freight_ratio) * 100, 1) if freight_ratio is not None else 0.0,
    })


@kpi_bp.get("/risk-orders")
def get_risk_orders():
    """Commandes en retard (is_late = 1), triees par retard decroissant,
    pour la table d'anomalies du dashboard executif."""
    db = get_db()
    region = request.args.get("region")
    date_str = request.args.get("date")
    limit = min(int(request.args.get("limit", 50)), 200)

    match = _build_match(region, date_str)
    match["is_late"] = 1


    cursor = (
        db.fact_orders.find(match, {
            "_id": 0, "order_id": 1, "customer_state": 1, "main_category": 1,
            "total_price": 1, "total_freight": 1, "delivery_delay_days": 1, "review_score": 1,
        })
        .sort("delivery_delay_days", -1)
        .limit(limit)
    )

    return jsonify([
        {
            "order_id": r.get("order_id"),
            "customer_state": r.get("customer_state"),
            "product_category_name": r.get("main_category"),
            "price": round(float(r["total_price"]), 2) if r.get("total_price") is not None else None,
            "freight_value": round(float(r["total_freight"]), 2) if r.get("total_freight") is not None else None,
            "delay_days": r.get("delivery_delay_days"),
            "review_score": r.get("review_score"),
        }
        for r in cursor
    ])


@kpi_bp.get("/revenue-by-week")
def get_revenue_by_week():
    """weeks_ago=0 -> derniere semaine complete connue, 1 -> celle d'avant, etc.
    (Index relatif, PAS un numero de semaine calendaire ISO.)"""
    db = get_db()
    weeks_ago = min(max(int(request.args.get("weeks_ago", 0)), 0), 104)

    pipeline = [
        {"$match": {"order_purchase_timestamp": {"$lt": DATA_CUTOFF}}},
        {"$group": {
            "_id": WEEK_TRUNC,
            "revenue": {"$sum": {"$ifNull": ["$total_payment_value", 0]}},
            "n_orders": {"$sum": 1},
        }},
        {"$sort": {"_id": -1}},
        {"$skip": weeks_ago},
        {"$limit": 1},
    ]
    result = next(iter(db.fact_orders.aggregate(pipeline)), None)
    if not result:
        return jsonify({"week": "N/A", "revenue": 0.0, "n_orders": 0})

    return jsonify({
        "week": result["_id"].strftime("%Y-%m-%d"),
        "revenue": round(float(result["revenue"]), 2),
        "n_orders": result["n_orders"],
        "weeks_ago": weeks_ago,
    })


@kpi_bp.get("/top-categories")
def get_top_categories():
    """Top categories par CA."""
    db = get_db()
    limit = int(request.args.get("limit", 10))

    pipeline = [
        {"$group": {
            "_id": "$product_category_name",
            "revenue": {"$sum": {"$add": ["$price", "$freight_value"]}},
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": limit},
    ]
    rows = db.fact_order_items.aggregate(pipeline)

    return jsonify([
        {"category": row["_id"], "revenue": round(float(row["revenue"]), 2)}
        for row in rows
    ])
