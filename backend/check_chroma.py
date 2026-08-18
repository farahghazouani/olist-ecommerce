

import os
import chromadb

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")

print(f"1) Dossier chroma_db : {CHROMA_PATH}")
if not os.path.isdir(CHROMA_PATH):
    print("   -> N'EXISTE PAS. Il faut lancer l'ingestion :")
    print("      python -m app.rag.ingest")
    raise SystemExit(1)
print("   -> existe.")

client = chromadb.PersistentClient(path=CHROMA_PATH)
collections = [c.name for c in client.list_collections()]
print(f"2) Collections trouvees : {collections}")

if "olist_reviews" not in collections:
    print("   -> La collection 'olist_reviews' N'EXISTE PAS. Il faut lancer :")
    print("      python -m app.rag.ingest")
    raise SystemExit(1)

collection = client.get_collection("olist_reviews")
count = collection.count()
print(f"3) Nombre de documents dans 'olist_reviews' : {count}")

if count == 0:
    print("   -> Collection VIDE. Meme commande a relancer : python -m app.rag.ingest")
else:
    print("   -> OK, la collection est peuplee. Le probleme de search.py est ailleurs "
          "(filtre 'where' trop strict, nom de categorie qui ne correspond pas exactement, etc.)")
    # Test rapide d'une requete sans filtre, pour confirmer que la recherche marche
    res = collection.query(query_texts=["livraison en retard"], n_results=3)
    docs = res.get("documents", [[]])[0]
    print(f"   Exemple de requete libre ('livraison en retard') -> {len(docs)} resultat(s).")
