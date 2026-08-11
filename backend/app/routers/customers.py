# backend/app/routers/customers.py
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from pydantic import BaseModel, ValidationError
from flask import Blueprint, request, jsonify, abort
from app.database import get_db

customers_bp = Blueprint("customers", __name__)

BASE_DIR = Path(__file__).resolve().parents[3]
SEGMENTS_CSV = BASE_DIR / "backend" / "data_exports" / "customer_segments.csv"
MODELS_DIR = BASE_DIR / "data_science" / "models"

_segments_df = None


def _load_segments():
    """Charge le CSV une seule fois en memoire (96k lignes, quelques Mo -
    pas besoin d'une collection Mongo dediee pour ca ; ce point ne change
    pas par rapport a la version PostgreSQL, aucune base ne fait ce travail)."""
    global _segments_df
    if _segments_df is None:
        if SEGMENTS_CSV.exists():
            _segments_df = pd.read_csv(SEGMENTS_CSV)
        else:
            _segments_df = pd.DataFrame()
    return _segments_df


def _safe_load(filename):
    path = MODELS_DIR / filename
    if path.exists():
        try:
            return joblib.load(path)
        except Exception as e:
            print(f"[ERREUR] Chargement de {filename}: {e}")
            return None
    print(f"[ATTENTION] Fichier modele introuvable : {path}")
    return None


# Modele K-Means (Section 9 du notebook) charge en direct, pour scorer un
# profil RFM qui n'est pas forcement deja dans customer_segments.csv
# (nouveau client, ou simulation "et si ce client avait ce profil").
kmeans_model = _safe_load("kmeans_customer_segments.pkl")
scaler_rfm = _safe_load("scaler_rfm.pkl")

_segment_label_map = None


def _get_segment_label_map():
    """Deduit la correspondance cluster_id -> nom de segment a partir de
    customer_segments.csv, plutot que de coder les noms en dur : si le
    clustering est reentraine, les numeros de cluster peuvent changer de
    sens (ce n'est PAS garanti stable d'un entrainement a l'autre)."""
    global _segment_label_map
    if _segment_label_map is not None:
        return _segment_label_map

    df = _load_segments()
    cluster_col = next(
        (c for c in ["cluster", "cluster_id", "segment_id", "km_cluster"] if c in df.columns),
        None,
    )
    if df.empty or cluster_col is None or "segment_name" not in df.columns:
        _segment_label_map = {}
    else:
        _segment_label_map = (
            df.groupby(cluster_col)["segment_name"]
            .agg(lambda s: s.mode().iloc[0])
            .to_dict()
        )
    return _segment_label_map


class SegmentPredictRequest(BaseModel):
    recency_days: float
    frequency: int
    monetary: float


@customers_bp.post("/predict-segment")
def predict_segment():
    """Segmentation en direct avec le meme modele K-Means que la Section 9
    du notebook (symetrique avec /predict/delay-risk et /forecast/by-category,
    qui font aussi de l'inference live plutot que de rejouer un CSV)."""
    if kmeans_model is None or scaler_rfm is None:
        abort(500, description="Le modele de segmentation (K-Means) n'est pas charge.")

    try:
        payload = SegmentPredictRequest(**(request.get_json(force=True) or {}))
    except ValidationError as e:
        abort(422, description=str(e))

    # Memes transformations que dans le notebook (features = [recency,
    # frequency_log, monetary_log], standardisees par scaler_rfm) : l'ordre
    # doit rester identique a celui utilise a l'entrainement.
    frequency_log = float(np.log1p(payload.frequency))
    monetary_log = float(np.log1p(payload.monetary))
    X = scaler_rfm.transform([[payload.recency_days, frequency_log, monetary_log]])
    cluster_id = int(kmeans_model.predict(X)[0])

    label_map = _get_segment_label_map()
    return jsonify({
        "cluster_id": cluster_id,
        "segment_name": label_map.get(cluster_id, f"Segment {cluster_id}"),
        "segment_name_is_mapped": cluster_id in label_map,
    })


@customers_bp.get("/segments/summary")
def get_segments_summary():
    """Profil et taille de chaque segment client (Module 5 : ciblage marketing)."""
    df = _load_segments()
    if df.empty:
        abort(404, description="customer_segments.csv introuvable dans backend/data_exports/.")

    summary = df.groupby("segment_name").agg(
        n_customers=("customer_unique_id", "count"),
        avg_recency_days=("recency", "mean"),
        avg_frequency=("frequency", "mean"),
        avg_monetary=("monetary", "mean"),
    ).reset_index()
    summary["pct"] = (summary["n_customers"] / len(df) * 100).round(1)
    summary = summary.round(2)

    return jsonify(summary.to_dict(orient="records"))


@customers_bp.get("/segments/<customer_unique_id>")
def get_customer_segment(customer_unique_id):
    """Segment d'un client precis, pour une fiche client dans le dashboard."""
    df = _load_segments()
    row = df[df["customer_unique_id"] == customer_unique_id]
    if row.empty:
        abort(404, description="Client non trouve dans la segmentation.")

    r = row.iloc[0]
    return jsonify({
        "customer_unique_id": customer_unique_id,
        "segment": r["segment_name"],
        "recency_days": int(r["recency"]),
        "frequency": int(r["frequency"]),
        "monetary": round(float(r["monetary"]), 2),
    })


@customers_bp.get("/states")
def get_customers_states():
    """Repartition geographique reelle des clients."""
    db = get_db()
    total = db.dim_customers.count_documents({})
    if not total:
        return jsonify([])

    pipeline = [
        {"$group": {"_id": "$customer_state", "total_customers": {"$sum": 1}}},
        {"$sort": {"total_customers": -1}},
        {"$limit": 10},
    ]
    rows = db.dim_customers.aggregate(pipeline)

    return jsonify([
        {
            "state": row["_id"],
            "total_customers": row["total_customers"],
            "percentage": round(row["total_customers"] / total * 100, 1),
        }
        for row in rows
    ])
