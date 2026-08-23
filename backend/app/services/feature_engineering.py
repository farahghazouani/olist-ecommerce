# backend/app/services/feature_engineering.py
from datetime import datetime
import pandas as pd
import numpy as np

STABLE_START = datetime(2017, 1, 1)
STABLE_END = datetime(2018, 8, 31)

_ORDERS_PROJECTION = {"_id": 0, "order_id": 1, "order_purchase_timestamp": 1, "total_payment_value": 1}
_ITEMS_PROJECTION = {"_id": 0, "order_purchase_timestamp": 1, "seller_id": 1, "product_id": 1}


def build_weekly_features(db) -> pd.DataFrame:
    """
    Reconstruit exactement le meme dataset hebdomadaire que celui utilise
    a l'entrainement (Section 7.8 du notebook), directement depuis MongoDB.
    Toute evolution de cette logique doit etre repercutee ICI UNIQUEMENT,
    puis le modele reentraine en consequence.
    """
    date_filter = {"order_purchase_timestamp": {"$gte": STABLE_START, "$lte": STABLE_END}}

    orders_df = pd.DataFrame(list(db.fact_orders.find(date_filter, _ORDERS_PROJECTION)))
    if orders_df.empty:
        return pd.DataFrame(columns=["week"] + FEATURE_COLS)
    orders_df["order_purchase_timestamp"] = pd.to_datetime(orders_df["order_purchase_timestamp"])

    items_df = pd.DataFrame(list(db.fact_order_items.find(date_filter, _ITEMS_PROJECTION)))
    if not items_df.empty:
        items_df["order_purchase_timestamp"] = pd.to_datetime(items_df["order_purchase_timestamp"])

    # --- Agregation hebdomadaire du CA (identique a l'entrainement) ---
    weekly = (
        orders_df.set_index("order_purchase_timestamp").resample("W")
        .agg(revenue=("total_payment_value", "sum"), n_orders=("order_id", "count"))
        .reset_index().rename(columns={"order_purchase_timestamp": "week"})
    )
    weekly = weekly.iloc[1:-1].reset_index(drop=True)
    weekly["week"] = weekly["week"].dt.to_period("W").dt.start_time

    # --- Features temporelles ---
    weekly["week_index"] = np.arange(len(weekly))
    weekly["week_of_year"] = weekly["week"].dt.isocalendar().week.astype(int)
    weekly["revenue_lag1"] = weekly["revenue"].shift(1)
    weekly["revenue_lag4"] = weekly["revenue"].shift(4)
    weekly["revenue_roll4"] = weekly["revenue"].shift(1).rolling(4).mean()
    weekly["n_orders_lag1"] = weekly["n_orders"].shift(1)
    weekly["month"] = weekly["week"].dt.month
    weekly["is_black_friday_period"] = weekly["month"].isin([11]).astype(int)

    # --- Activite de l'offre (decalee d'une semaine, comme validee sans fuite) ---
    if not items_df.empty:
        supply = (
            items_df.assign(week=lambda d: d["order_purchase_timestamp"].dt.to_period("W").dt.start_time)
            .groupby("week").agg(n_active_sellers=("seller_id", "nunique"), n_active_products=("product_id", "nunique"))
            .reset_index()
        )
        weekly = weekly.merge(supply, on="week", how="left")
    else:
        weekly["n_active_sellers"] = np.nan
        weekly["n_active_products"] = np.nan

    weekly["n_active_sellers_lag1"] = weekly["n_active_sellers"].shift(1)
    weekly["n_active_products_lag1"] = weekly["n_active_products"].shift(1)

    return weekly.dropna().reset_index(drop=True)


FEATURE_COLS = ["week_index", "week_of_year", "revenue_lag1", "revenue_lag4", "revenue_roll4",
                "n_orders_lag1", "is_black_friday_period", "n_active_sellers_lag1", "n_active_products_lag1"]
