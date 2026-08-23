"""
Smoke test : verifie que chaque endpoint Flask migre s'execute sans erreur
contre une base MongoDB simulee en memoire (mongomock), avec un petit jeu
de donnees synthetique reproduisant la structure des 6 collections.

Usage : python scripts/smoke_test.py
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGODB_DB_NAME", "olist_bi_test")

import mongomock
import app.database as database_module

# --- 0. Stub chromadb : evite de telecharger un vrai modele d'embedding
#     pendant ce test, qui ne verifie que la couche MongoDB/Flask, pas le RAG.
import types
_fake_chromadb = types.ModuleType("chromadb")
_fake_chromadb_utils = types.ModuleType("chromadb.utils")


class _FakeEmbeddingFunctions:
    def SentenceTransformerEmbeddingFunction(self, model_name=None):
        return lambda texts: [[0.0] * 8 for _ in texts]


_fake_chromadb_utils.embedding_functions = _FakeEmbeddingFunctions()
_fake_chromadb.utils = _fake_chromadb_utils
_fake_chromadb.PersistentClient = lambda path=None: None
sys.modules["chromadb"] = _fake_chromadb
sys.modules["chromadb.utils"] = _fake_chromadb_utils

# --- 1. Remplace la vraie connexion Mongo par une base simulee en memoire ---
_fake_client = mongomock.MongoClient()
_fake_db = _fake_client["olist_bi_test"]
database_module.db = _fake_db
database_module.get_db = lambda: _fake_db

# --- 2. Jeu de donnees synthetique (quelques documents par collection) ---
orders = [
    {
        "order_id": "ORD_1", "customer_id": "CUST_1", "customer_state": "SP",
        "total_payment_value": 150.0, "total_price": 120.0, "total_freight": 30.0,
        "main_category": "electronics", "review_score": 5, "is_late": 0,
        "delivery_delay_days": -2, "order_purchase_timestamp": datetime(2018, 3, 5),
    },
    {
        "order_id": "ORD_2", "customer_id": "CUST_2", "customer_state": "RJ",
        "total_payment_value": 80.0, "total_price": 60.0, "total_freight": 20.0,
        "main_category": "toys", "review_score": 2, "is_late": 1,
        "delivery_delay_days": 4, "order_purchase_timestamp": datetime(2018, 3, 12),
    },
    {
        "order_id": "ORD_3", "customer_id": "CUST_3", "customer_state": "SP",
        "total_payment_value": 220.0, "total_price": 200.0, "total_freight": 20.0,
        "main_category": "electronics", "review_score": 4, "is_late": 0,
        "delivery_delay_days": -1, "order_purchase_timestamp": datetime(2018, 4, 2),
    },
]
items = [
    {
        "order_id": "ORD_1", "product_id": "P1", "seller_id": "S1",
        "price": 100.0, "freight_value": 20.0, "product_category_name": "electronics",
        "product_category_name_english": "electronics", "customer_state": "SP",
        "seller_state": "SP", "total_item_value": 120.0, "estimated_margin": 15.0,
        "freight_ratio": 0.16, "same_state_delivery": 1,
        "order_purchase_timestamp": datetime(2018, 3, 5),
    },
    {
        "order_id": "ORD_2", "product_id": "P2", "seller_id": "S2",
        "price": 60.0, "freight_value": 20.0, "product_category_name": "toys",
        "product_category_name_english": "toys", "customer_state": "RJ",
        "seller_state": "SP", "total_item_value": 80.0, "estimated_margin": 5.0,
        "freight_ratio": 0.25, "same_state_delivery": 0,
        "order_purchase_timestamp": datetime(2018, 3, 12),
    },
]
reviews = [
    {"review_id": "R1", "order_id": "ORD_1", "review_score": 5, "review_comment_message": "Muito bom, rapido!"},
    {"review_id": "R2", "order_id": "ORD_2", "review_score": 2, "review_comment_message": "Atrasou muito."},
]
customers = [
    {"customer_id": "CUST_1", "customer_unique_id": "U1", "customer_state": "SP", "customer_city": "sao paulo"},
    {"customer_id": "CUST_2", "customer_unique_id": "U2", "customer_state": "RJ", "customer_city": "rio"},
    {"customer_id": "CUST_3", "customer_unique_id": "U3", "customer_state": "SP", "customer_city": "campinas"},
]

_fake_db.fact_orders.insert_many(orders)
_fake_db.fact_order_items.insert_many(items)
_fake_db.fact_reviews.insert_many(reviews)
_fake_db.dim_customers.insert_many(customers)

# --- 3. Construit l'app Flask et exerce chaque endpoint ---
from app.main import create_app  # noqa: E402

app = create_app()
client = app.test_client()

ENDPOINTS = [
    ("GET", "/api/dashboard/summary", None),
    ("GET", "/api/dashboard/revenue-by-month", None),
    ("GET", "/api/dashboard/revenue-last-week", None),
    ("GET", "/api/dashboard/metrics", None),
    ("GET", "/api/dashboard/risk-orders", None),
    ("GET", "/api/dashboard/revenue-by-week?weeks_ago=0", None),
    ("GET", "/api/dashboard/top-categories", None),
    ("GET", "/api/sales/metrics", None),
    ("GET", "/api/sales/revenue-by-state", None),
    ("GET", "/api/sales/top-sellers", None),
    ("GET", "/api/sales/best-seller-by-season", None),
    ("GET", "/api/products/analytics", None),
    ("GET", "/api/products/top-reviews?category=electronics&limit=3", None),
    ("GET", "/api/customers/states", None),
]

failures = []
for method, path, body in ENDPOINTS:
    resp = client.open(path, method=method, json=body)
    status = "OK " if resp.status_code < 400 else "FAIL"
    print(f"[{status}] {method} {path} -> {resp.status_code} {resp.get_json()}")
    if resp.status_code >= 400:
        failures.append((path, resp.status_code, resp.get_json()))

print("\n--- Resume ---")
if failures:
    print(f"{len(failures)} endpoint(s) en echec :")
    for path, code, body in failures:
        print(f"  {path} -> {code} : {body}")
    sys.exit(1)
else:
    print(f"Tous les {len(ENDPOINTS)} endpoints testes repondent correctement.")
