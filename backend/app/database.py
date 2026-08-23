# backend/app/database.py
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "olist_bi")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI introuvable dans le fichier .env")

_client = MongoClient(MONGODB_URI)
db = _client[MONGODB_DB_NAME]


def get_db():
    """Retourne la base MongoDB courante. Conservee pour garder le meme
    point d'entree que l'ancien get_db() (SQLAlchemy) dans les routers,
    meme si ici il n'y a plus de session a gerer / fermer."""
    return db
