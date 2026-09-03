# backend/app/rag/ingest.py
import os
import chromadb
from chromadb.utils import embedding_functions
from app.database import get_db

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "../../chroma_db")

embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="paraphrase-multilingual-MiniLM-L12-v2"
)


def build_vector_store(limit: int = 10000):
    print("Connexion a MongoDB pour extraire les vrais avis...")
    db = get_db()

    pipeline = [
        {"$match": {"review_comment_message": {"$nin": [None, ""]}}},
        {"$lookup": {
            "from": "fact_orders",
            "localField": "order_id",
            "foreignField": "order_id",
            "as": "order_info",
        }},
        {"$unwind": {"path": "$order_info", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 0,
            "review_id": 1,
            "review_comment_message": 1,
            "review_score": 1,
            "category": {"$ifNull": ["$order_info.main_category", None]},
        }},
        {"$limit": limit},
    ]
    results = list(db.fact_reviews.aggregate(pipeline))

    print(f"{len(results):,} vrais commentaires textuels recuperes (avec categorie). Initialisation de ChromaDB...")

    client = chromadb.PersistentClient(path=CHROMA_PATH)

    if "olist_reviews" in [c.name for c in client.list_collections()]:
        client.delete_collection("olist_reviews")

    collection = client.create_collection(
        name="olist_reviews", embedding_function=embedding_fn
    )

    batch_size = 1000
    total = len(results)

    for i in range(0, total, batch_size):
        batch = results[i: i + batch_size]
        documents = [row["review_comment_message"] for row in batch]
        ids = [str(row["review_id"]) for row in batch]
        metadatas = [
            {
                "category": row["category"] or "inconnue",
                "review_score": int(row["review_score"]) if row.get("review_score") is not None else 0,
            }
            for row in batch
        ]
        collection.add(documents=documents, ids=ids, metadatas=metadatas)
        print(f"  Lot {i // batch_size + 1} indexe ({len(batch)} avis)")

    print(f"Indexation terminee : {total:,} avis dans ChromaDB.")


if __name__ == "__main__":
    build_vector_store()
