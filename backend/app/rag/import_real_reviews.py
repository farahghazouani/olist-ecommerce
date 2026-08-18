# backend/app/rag/import_real_reviews.py
import os
import zipfile
import pandas as pd
from app.database import get_db

ZIP_PATH = r"C:\Users\Farouha\Downloads\olist_order_reviews_dataset.csv.zip"
CSV_FILENAME = "olist_order_reviews_dataset.csv"

DATE_COLUMNS = ["review_creation_date", "review_answer_timestamp"]


def import_kaggle_reviews_to_mongo():
    print(f"Lecture du fichier officiel Kaggle dans : {ZIP_PATH}...")

    if not os.path.exists(ZIP_PATH):
        print(f"Fichier non trouve a l'emplacement : {ZIP_PATH}")
        return

    try:
        # 1. Lecture du CSV depuis le ZIP
        with zipfile.ZipFile(ZIP_PATH, "r") as z:
            with z.open(CSV_FILENAME) as f:
                df = pd.read_csv(f)

        print(f"{len(df):,} avis au total charges depuis Kaggle.")

        # 2. Nettoyage des doublons
        df = df.drop_duplicates(subset=["review_id"])

        # 3. FILTRAGE : Suppression stricte des commentaires NULL ou vides
        df_clean = df[
            df["review_comment_message"].notna()
            & (df["review_comment_message"].astype(str).str.strip() != "")
        ].copy()

        print(f"Nettoyage termine : {len(df_clean):,} avis avec du texte conserves (sur {len(df):,}).")

        # 4. Conversion des dates en vraies dates Mongo (BSON date), et des
        #    NaN restants en None (JSON/BSON ne connaissent pas NaN).
        for col in DATE_COLUMNS:
            if col in df_clean.columns:
                df_clean[col] = pd.to_datetime(df_clean[col], errors="coerce")
        df_clean = df_clean.where(pd.notnull(df_clean), None)

        print("Insertion dans MongoDB...")

        # 5. Insertion dans MongoDB 
        db = get_db()
        db.fact_reviews.drop()
        records = df_clean.to_dict(orient="records")
        if records:
            db.fact_reviews.insert_many(records)

        print("SUCCES ! La collection 'fact_reviews' contient desormais uniquement des vrais commentaires textuels.")

    except Exception as e:
        print(f"Erreur lors de l'importation : {e}")


if __name__ == "__main__":
    import_kaggle_reviews_to_mongo()
