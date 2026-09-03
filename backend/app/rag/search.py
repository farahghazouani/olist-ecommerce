# backend/app/rag/search.py
import os
import chromadb
from chromadb.utils import embedding_functions

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "../../chroma_db")

embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="paraphrase-multilingual-MiniLM-L12-v2"
)


def _build_where(category: str | None, max_score: int | None):
    conditions = []
    if category:
        conditions.append({"category": category})
    if max_score is not None:
        conditions.append({"review_score": {"$lte": max_score}})
    if len(conditions) == 1:
        return conditions[0]
    if len(conditions) > 1:
        return {"$and": conditions}
    return None


def search_customer_reviews(
    query: str, n_results: int = 5, category: str | None = None, max_score: int | None = None
) -> dict:
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collection = client.get_collection(name="olist_reviews", embedding_function=embedding_fn)

        where_filter = _build_where(category, max_score)
        results = collection.query(query_texts=[query], n_results=n_results, where=where_filter)
        documents = results.get("documents", [[]])[0]

        category_matched = True
        if not documents and category:
            fallback_filter = _build_where(None, max_score)
            results = collection.query(query_texts=[query], n_results=n_results, where=fallback_filter)
            documents = results.get("documents", [[]])[0]
            category_matched = False

        return {"documents": documents, "category_matched": category_matched}
    except Exception as e:
        print(f"⚠️ Erreur lors de la recherche RAG : {e}")
        return {"documents": [], "category_matched": False}