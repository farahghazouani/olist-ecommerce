# backend/scripts/test_connection.py
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("MONGODB_DB_NAME", "olist_bi")]

print("Nombre de commandes :", db.fact_orders.count_documents({}))
print("Nombre d'items :", db.fact_order_items.count_documents({}))
print("Nombre d'avis :", db.fact_reviews.count_documents({}))
