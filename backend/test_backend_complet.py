"""
Teste tous les endpoints du backend contre le VRAI serveur (localhost:8000),
avec tes vraies donnees MongoDB. Lance ce script PENDANT que `python -m app.main`
tourne dans un autre terminal.

Usage :
    pip install requests
    python test_backend_complet.py
"""
import requests

BASE = "http://localhost:8000/api"

# Payload d'exemple reutilise pour tous les tests lies au retard de livraison
SAMPLE_ORDER = {
    "total_price": 150.0, "total_freight": 25.0, "n_items": 2,
    "n_unique_products": 2, "n_unique_sellers": 1, "pct_same_state": 1.0,
    "avg_product_weight_g": 800.0, "max_product_weight_g": 1200.0,
    "n_payment_installments_max": 3, "has_voucher": 0,
    "category": "informatica_acessorios", "customer_state": "SP", "order_month": 11,
}

TESTS = [
    ("GET", "/dashboard/summary", None),
    ("GET", "/dashboard/revenue-by-month", None),
    ("GET", "/dashboard/revenue-last-week", None),
    ("GET", "/dashboard/metrics", None),
    ("GET", "/dashboard/risk-orders?limit=5", None),
    ("GET", "/dashboard/top-categories", None),
    ("GET", "/sales/metrics", None),
    ("GET", "/sales/revenue-by-state", None),
    ("GET", "/sales/top-sellers", None),
    ("GET", "/sales/best-seller-by-season", None),
    ("GET", "/products/analytics", None),
    ("GET", "/customers/segments/summary", None),
    ("GET", "/customers/states", None),
    ("POST", "/customers/predict-segment", {"recency_days": 60, "frequency": 3, "monetary": 450.0}),
    ("GET", "/ml/forecast/categories", None),
    ("GET", "/ml/forecast/by-category?category=informatica_acessorios", None),
    ("POST", "/ml/predict/delay-risk", SAMPLE_ORDER),
    ("POST", "/ml/predict/delay-batch-montecarlo", {"orders": [SAMPLE_ORDER] * 200, "n_simulations": 3000}),
    ("POST", "/chat/message", {"message": "Bonjour, peux-tu me donner un resume des ventes ?"}),
]

print(f"Test de {len(TESTS)} endpoints sur {BASE}\n")
failures = []

for method, path, body in TESTS:
    url = BASE + path
    # /chat/message appelle le LLM (Ollama) : premiere reponse potentiellement
    # lente (chargement du modele en memoire), contrairement aux autres
    # endpoints qui ne font que de la lecture DB / inference d'un .pkl.
    timeout = 120 if path == "/chat/message" else 15
    try:
        resp = requests.request(method, url, json=body, timeout=timeout)
        ok = resp.status_code < 400
        status = "OK  " if ok else "FAIL"
        preview = str(resp.json())[:150] if resp.headers.get("content-type", "").startswith("application/json") else resp.text[:150]
        print(f"[{status}] {method:4} {path:55} -> {resp.status_code}  {preview}")
        if not ok:
            failures.append((method, path, resp.status_code, resp.text[:300]))
    except requests.exceptions.ConnectionError:
        print(f"[FAIL] {method:4} {path:55} -> IMPOSSIBLE DE JOINDRE LE SERVEUR (verifie qu'il tourne)")
        failures.append((method, path, "N/A", "Connexion refusee"))
    except Exception as e:
        print(f"[FAIL] {method:4} {path:55} -> ERREUR : {e}")
        failures.append((method, path, "N/A", str(e)))

print("\n--- Resume ---")
if failures:
    print(f"{len(failures)} endpoint(s) en echec sur {len(TESTS)} :")
    for method, path, code, detail in failures:
        print(f"  {method} {path} -> {code}")
        print(f"    {detail}")
else:
    print(f"Tous les {len(TESTS)} endpoints repondent correctement !")
