# backend/app/database.py
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "olist_bi")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI introuvable dans le fichier .env")

# Contrairement a SQLAlchemy (create_engine + sessionmaker + get_db() par
# requete), un MongoClient gere lui-meme un pool de connexions et est
# thread-safe : on peut le creer une seule fois au chargement du module et
# le reutiliser partout, sans session a ouvrir/fermer a chaque requete Flask.
_client = MongoClient(MONGODB_URI)
db = _client[MONGODB_DB_NAME]


def get_db():
    """Retourne la base MongoDB courante. Conservee pour garder le meme
    point d'entree que l'ancien get_db() (SQLAlchemy) dans les routers,
    meme si ici il n'y a plus de session a gerer / fermer."""
    return db
