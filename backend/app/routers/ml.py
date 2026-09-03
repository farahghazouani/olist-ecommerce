# backend/app/routers/ml.py
import re
from pathlib import Path
import joblib
import pandas as pd
import numpy as np
from pydantic import BaseModel, ValidationError
from flask import Blueprint, request, jsonify, abort

from app.database import get_db

ml_bp = Blueprint("ml", __name__)


BASE_DIR = Path(__file__).resolve().parents[3]
MODELS_DIR = BASE_DIR / "data_science" / "models"


def safe_load(filename: str):
    filepath = MODELS_DIR / filename
    if filepath.exists():
        try:
            return joblib.load(filepath)
        except Exception as e:
            print(f"[ERREUR] Chargement de {filename}: {e}")
            return None
    print(f"[ATTENTION] Fichier modele introuvable : {filepath}")
    return None


delay_model = safe_load("model_delivery_delay_calibrated.pkl")
delay_model_is_calibrated = delay_model is not None
if delay_model is None:
    delay_model = safe_load("model_delivery_delay.pkl")
    if delay_model is not None:
        print("[ATTENTION] Modele de retard NON calibre charge (probabilites "
              "gonflees par class_weight='balanced' -- exporte "
              "model_delivery_delay_calibrated.pkl depuis le notebook des que possible).")
le_category = safe_load("label_encoder_category.pkl")
le_state = safe_load("label_encoder_state.pkl")
delay_feature_cols = safe_load("delay_model_features.pkl")
category_growth_model = safe_load("model_category_revenue_growth.pkl")
le_category_forecast = safe_load("label_encoder_category_forecast.pkl")
category_forecast_features = safe_load("category_forecast_features.pkl")
category_forecast_small_categories = safe_load("category_forecast_small_categories.pkl")

DATA_EXPORTS_DIR = BASE_DIR / "backend" / "data_exports"
_category_last_known = None
_category_state_share = None


def _load_category_forecast_data():
    global _category_last_known, _category_state_share
    if _category_last_known is None:
        path1 = DATA_EXPORTS_DIR / "category_monthly_last_known.csv"
        _category_last_known = pd.read_csv(path1, parse_dates=["month"]) if path1.exists() else pd.DataFrame()
    if _category_state_share is None:
        path2 = DATA_EXPORTS_DIR / "category_state_share.csv"
        _category_state_share = pd.read_csv(path2) if path2.exists() else pd.DataFrame()
    return _category_last_known, _category_state_share


class DelayRiskRequest(BaseModel):
    total_price: float
    total_freight: float
    n_items: int
    n_unique_products: int
    n_unique_sellers: int
    pct_same_state: float
    avg_product_weight_g: float
    max_product_weight_g: float
    n_payment_installments_max: int
    has_voucher: int
    category: str
    customer_state: str
    order_month: int


def _safe_encode(encoder, value: str) -> int:
    try:
        return int(encoder.transform([value])[0])
    except ValueError:
        return 0


def _get_top_factors(model, feature_cols, top_n=3):
    try:
        if hasattr(model, "feature_importances_"):
            base = model
        elif hasattr(model, "calibrated_classifiers_"):
            calibrated = model.calibrated_classifiers_[0]
            base = getattr(calibrated, "estimator", None) or getattr(calibrated, "base_estimator", None)
        else:
            base = None
        if base is None or not hasattr(base, "feature_importances_"):
            return []
        importances = dict(zip(feature_cols, base.feature_importances_))
        top = sorted(importances.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        return [f for f, _ in top]
    except Exception as e:
        print(f"⚠️ Impossible d'extraire les facteurs d'importance : {e}")
        return []


@ml_bp.post("/predict/delay-risk")
def predict_delay_risk():
    if delay_model is None or le_category is None or le_state is None or delay_feature_cols is None:
        abort(500, description="Le modele de retard n'est pas charge.")

    try:
        payload = DelayRiskRequest(**(request.get_json(force=True) or {}))
    except ValidationError as e:
        abort(422, description=str(e))

    row = {
        "total_price": payload.total_price,
        "total_freight": payload.total_freight,
        "n_items": payload.n_items,
        "n_unique_products": payload.n_unique_products,
        "n_unique_sellers": payload.n_unique_sellers,
        "pct_same_state": payload.pct_same_state,
        "avg_product_weight_g": payload.avg_product_weight_g,
        "max_product_weight_g": payload.max_product_weight_g,
        "n_payment_installments_max": payload.n_payment_installments_max,
        "has_voucher": payload.has_voucher,
        "category_enc": _safe_encode(le_category, payload.category),
        "state_enc": _safe_encode(le_state, payload.customer_state),
        "order_month_num": payload.order_month,
    }

    X = pd.DataFrame([row])[delay_feature_cols]
    proba_late = float(delay_model.predict_proba(X)[0][1])

    top_factors = _get_top_factors(delay_model, delay_feature_cols)

    return jsonify({
        "risk_probability": round(proba_late, 3),
        "risk_level": "Eleve" if proba_late >= 0.3 else ("Modere" if proba_late >= 0.15 else "Faible"),
        "top_factors": top_factors,
        "probability_calibrated": delay_model_is_calibrated,
    })


@ml_bp.get("/forecast/categories")
def list_forecast_categories():
    if le_category_forecast is None:
        abort(500, description="Le modele de prevision par categorie n'est pas charge.")
    return jsonify(sorted(le_category_forecast.classes_.tolist()))


MAX_FORECAST_MONTHS_AHEAD = 6


@ml_bp.get("/forecast/by-category")
def forecast_by_category():
    category = request.args.get("category")
    state = request.args.get("state")
    target_month = request.args.get("target_month")
    if not category:
        abort(400, description="Le parametre 'category' est requis.")

    if category_growth_model is None or le_category_forecast is None or category_forecast_features is None:
        abort(500, description="Le modele de prevision par categorie n'est pas charge.")

    last_known_df, share_df = _load_category_forecast_data()
    if last_known_df.empty:
        abort(404, description="category_monthly_last_known.csv introuvable.")

    small_cats = category_forecast_small_categories or []
    grouped_category = "Autres" if category in small_cats else category

    known_classes = set(le_category_forecast.classes_)
    if grouped_category not in known_classes:
        grouped_category = "Autres" if "Autres" in known_classes else None
    if grouped_category is None:
        abort(404, description=f"Categorie '{category}' inconnue du modele.")

    row = last_known_df[last_known_df["category_grouped"] == grouped_category]
    if row.empty:
        abort(404, description=f"Pas d'historique pour la categorie '{grouped_category}'.")
    r = row.iloc[0]
    last_known_month = pd.Timestamp(r["month"])
    category_enc = int(le_category_forecast.transform([grouped_category])[0])

    months_ahead = 1
    if target_month:
        if not re.fullmatch(r"\d{4}-\d{2}", target_month):
            abort(400, description=(
                f"target_month doit etre exactement au format 'YYYY-MM' (ex: '2018-10'), "
                f"reçu : '{target_month}'."
            ))
        try:
            target_ts = pd.Timestamp(f"{target_month}-01")
        except ValueError:
            abort(400, description=f"target_month invalide : '{target_month}' (mois hors de 01-12 ?).")
        months_ahead = (target_ts.year - last_known_month.year) * 12 + (target_ts.month - last_known_month.month)
        if months_ahead < 1:
            abort(400, description=(
                f"target_month ({target_month}) n'est pas dans le futur par rapport au dernier mois "
                f"connu ({last_known_month.date()})."
            ))
        if months_ahead > MAX_FORECAST_MONTHS_AHEAD:
            abort(400, description=(
                f"target_month trop eloigne : {months_ahead} mois d'ecart, maximum supporte = "
                f"{MAX_FORECAST_MONTHS_AHEAD} (au-dela, la prevision recursive n'est plus fiable)."
            ))

    lag1 = float(r["revenue"])
    lag2 = float(r["revenue_lag1"])
    roll3_history = [float(r["revenue_lag2"]), lag2, lag1]
    current_date = last_known_month
    predicted_revenue = lag1
    growth_ratio = 1.0

    for step in range(months_ahead):
        current_date = current_date + pd.DateOffset(months=1)
        roll3 = float(np.mean(roll3_history[-3:]))
        feature_row = pd.DataFrame([{
            "category_enc": category_enc,
            "month_index": int(r["month_index"]) + step + 1,
            "month_of_year": current_date.month,
            "revenue_lag1": lag1,
            "revenue_lag2": lag2,
            "revenue_roll3": roll3,
        }])[category_forecast_features]

        growth_ratio = max(float(category_growth_model.predict(feature_row)[0]), 0.0)
        predicted_revenue = growth_ratio * lag1

        roll3_history.append(predicted_revenue)
        lag2 = lag1
        lag1 = predicted_revenue

    result = {
        "category": category,
        "category_grouped": grouped_category,
        "last_known_month": str(last_known_month.date()),
        "forecast_month": str(current_date.date()),
        "predicted_revenue_total": round(predicted_revenue, 2),
        "growth_ratio": round(growth_ratio, 3),
        "months_ahead": months_ahead,
    }

    if state:
        if share_df.empty:
            abort(404, description="category_state_share.csv introuvable.")
        share_row = share_df[
            (share_df["category_grouped"] == grouped_category) & (share_df["customer_state"] == state)
        ]
        state_share = float(share_row.iloc[0]["state_share"]) if not share_row.empty else 0.0
        result["state"] = state
        result["state_share"] = round(state_share, 4)
        result["predicted_revenue_state"] = round(predicted_revenue * state_share, 2)

    return jsonify(result)


class DelayBatchMonteCarloRequest(BaseModel):
    orders: list[DelayRiskRequest]
    n_simulations: int = 10000


@ml_bp.post("/predict/delay-batch-montecarlo")
def delay_batch_montecarlo():
    if delay_model is None or le_category is None or le_state is None or delay_feature_cols is None:
        abort(500, description="Le modele de retard n'est pas charge.")
    if not delay_model_is_calibrated:
        print("[ATTENTION] Simulation lancee avec un modele NON calibre : "
              "le P10/mediane/P90 seront surestimes (cf. rapport).")

    try:
        payload = DelayBatchMonteCarloRequest(**(request.get_json(force=True) or {}))
    except ValidationError as e:
        abort(422, description=str(e))

    if not payload.orders:
        abort(400, description="La liste 'orders' est vide.")

    rows = []
    for o in payload.orders:
        rows.append({
            "total_price": o.total_price, "total_freight": o.total_freight,
            "n_items": o.n_items, "n_unique_products": o.n_unique_products,
            "n_unique_sellers": o.n_unique_sellers, "pct_same_state": o.pct_same_state,
            "avg_product_weight_g": o.avg_product_weight_g, "max_product_weight_g": o.max_product_weight_g,
            "n_payment_installments_max": o.n_payment_installments_max, "has_voucher": o.has_voucher,
            "category_enc": _safe_encode(le_category, o.category),
            "state_enc": _safe_encode(le_state, o.customer_state),
            "order_month_num": o.order_month,
        })

    X = pd.DataFrame(rows)[delay_feature_cols]
    probs = delay_model.predict_proba(X)[:, 1]

    n_sim = min(max(payload.n_simulations, 1000), 20000)
    simulated = np.random.binomial(1, probs, size=(n_sim, len(probs))).sum(axis=1)
    p10, median, p90 = (int(v) for v in np.percentile(simulated, [10, 50, 90]))

    return jsonify({
        "n_orders_in_batch": len(probs),
        "avg_probability_pct": round(float(probs.mean()) * 100, 1),
        "p10": p10, "median": median, "p90": p90,
        "probability_calibrated": delay_model_is_calibrated,
    })
