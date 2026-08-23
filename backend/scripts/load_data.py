import os
import re
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

try:
    import certifi
    ca_file = certifi.where()
except ImportError:
    ca_file = None

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "olist_bi")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI ou MONGO_URI introuvable dans le fichier .env")

client_kwargs = {}
if ca_file:
    client_kwargs["tlsCAFile"] = ca_file

client = MongoClient(MONGODB_URI, **client_kwargs)
db = client[MONGODB_DB_NAME]

collections = {
    'fact_orders': 'data_exports/fact_orders.csv',
    'fact_order_items': 'data_exports/fact_order_items.csv',
    'dim_customers': 'data_exports/dim_customers.csv',
    'dim_products': 'data_exports/dim_products.csv',
    'dim_sellers': 'data_exports/dim_sellers.csv',
}

DATE_COLUMN_PATTERN = re.compile(r"(date|timestamp)", re.IGNORECASE)


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    date_cols = [c for c in df.columns if DATE_COLUMN_PATTERN.search(c)]
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce")
        df[col] = df[col].astype(object).where(df[col].notna(), None)
    return df


def _to_mongo_records(df: pd.DataFrame) -> list[dict]:
    records = df.to_dict(orient="records")
    for record in records:
        for key, value in record.items():
            if value is None:
                continue
            if isinstance(value, pd.Timestamp):
                record[key] = value.to_pydatetime()
            elif pd.api.types.is_scalar(value) and pd.isna(value):
                record[key] = None
    return records


BATCH_SIZE = 5000

for collection_name, csv_path in collections.items():
    if os.path.exists(csv_path):
        print(f"Chargement de {csv_path}...")
        df = pd.read_csv(csv_path)
        df = _parse_dates(df)
        records = _to_mongo_records(df)

        db[collection_name].drop()

        if records:
            for i in range(0, len(records), BATCH_SIZE):
                batch = records[i:i + BATCH_SIZE]
                db[collection_name].insert_many(batch)
                print(f"  -> {min(i + BATCH_SIZE, len(records))}/{len(records)} inseres...")

        server_count = db[collection_name].count_documents({})
        if server_count != len(records):
            print(f"[ATTENTION] '{collection_name}' attendu {len(records)}, trouve {server_count} cote serveur.")
        else:
            print(f"[OK] Collection '{collection_name}' chargee et verifiee ({server_count} documents)\n")
    else:
        print(f"[!] Fichier introuvable : {csv_path}")

# --------------------------------------------------------------------------
# Recreation des index : .drop() ci-dessus supprime aussi les index existants
# sur chaque collection, pas seulement les documents. Sans cette etape, les
# jointures ($lookup) utilisees par products.py et rag/ingest.py redeviennent
# tres lentes (scan complet de la collection a chaque jointure) -- on la fait
# donc automatiquement ici, pour ne plus jamais avoir a y penser separement.
# --------------------------------------------------------------------------
print("Creation des index...")
db.fact_orders.create_index("order_id")
db.fact_order_items.create_index("order_id")
db.fact_reviews.create_index("order_id")
db.fact_orders.create_index("order_purchase_timestamp")
db.fact_order_items.create_index("order_purchase_timestamp")
print("[OK] Index recrees sur fact_orders, fact_order_items, fact_reviews (order_id "
      "+ order_purchase_timestamp).")