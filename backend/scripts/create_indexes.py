import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_db

"""
Cree les index MongoDB necessaires pour que les $lookup (jointures) utilises
dans products.py et rag/ingest.py restent rapides. A executer UNE SEULE FOIS
(ou a chaque fois que les collections sont rechargees depuis zero, puisque
recreer une collection avec .drop() supprime aussi ses index).

Usage (depuis backend/) :
    python scripts/create_indexes.py
"""
from app.database import get_db

db = get_db()

# order_id est la cle de jointure utilisee par :
# - products.py (/analytics, /top-reviews) : fact_order_items <-> fact_orders,
#                                              fact_reviews <-> fact_order_items
# - rag/ingest.py : fact_reviews <-> fact_orders
db.fact_orders.create_index("order_id")
db.fact_order_items.create_index("order_id")
db.fact_reviews.create_index("order_id")

# order_purchase_timestamp est utilise dans quasiment tous les $match par
# date (kpi.py, sales.py, products.py) : accelere aussi ces filtres.
db.fact_orders.create_index("order_purchase_timestamp")
db.fact_order_items.create_index("order_purchase_timestamp")

print("Index crees avec succes sur : fact_orders.order_id, "
      "fact_order_items.order_id, fact_reviews.order_id, "
      "fact_orders.order_purchase_timestamp, fact_order_items.order_purchase_timestamp")

print("\nIndex existants par collection :")
for name in ["fact_orders", "fact_order_items", "fact_reviews"]:
    print(f"  {name} :", list(db[name].index_information().keys()))