# backend/app/main.py
from flask import Flask, jsonify
from flask_cors import CORS

from app.routers.kpi import kpi_bp
from app.routers.ml import ml_bp
from app.routers.chat import chat_bp
from app.routers.products import products_bp
from app.routers.customers import customers_bp
from app.routers.sales import sales_bp


def create_app():
    app = Flask(__name__)

    CORS(app, resources={r"/api/*": {"origins": [
        "http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173",
    ]}})

    
    app.register_blueprint(kpi_bp, url_prefix="/api/dashboard")
    app.register_blueprint(products_bp, url_prefix="/api/products")
    app.register_blueprint(customers_bp, url_prefix="/api/customers")
    app.register_blueprint(sales_bp, url_prefix="/api/sales")

    #pour lesmodules ml a inclure par la suite desqu'ils seront prets 
    app.register_blueprint(ml_bp, url_prefix="/api/ml")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"detail": getattr(e, "description", "Not found")}), 404

    @app.errorhandler(422)
    def unprocessable(e):
        return jsonify({"detail": getattr(e, "description", "Unprocessable entity")}), 422

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"detail": getattr(e, "description", "Internal server error")}), 500

    @app.get("/")
    def root():
        return jsonify({"message": "Olist BI Platform API", "status": "running"})

    _warm_up_ollama_models()

    return app


def _warm_up_ollama_models():
    """Precharge ROUTER_MODEL et SYNTHESIS_MODEL en memoire des le demarrage
    du serveur, dans un thread separe (ne bloque pas le lancement de
    Flask). Sans ca, la PREMIERE question de chaque utilisateur (ou apres
    chaque redemarrage en dev) paie le cout du chargement du modele en RAM
    en plus du temps d'inference -- ce qui peut a lui seul depasser le
    timeout et ressembler a une panne, alors que le modele n'est simplement
    pas encore charge."""
    import threading
    import requests as _requests
    from app.agent.agent import OLLAMA_HOST, ROUTER_MODEL, SYNTHESIS_MODEL, KEEP_ALIVE

    def _warm(model_name):
        try:
            _requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={"model": model_name, "messages": [{"role": "user", "content": "ok"}],
                      "options": {"num_predict": 1}, "keep_alive": KEEP_ALIVE, "stream": False},
                timeout=180,
            )
            print(f"✅ Modele '{model_name}' prechauffe et charge en memoire.")
        except Exception as e:
            print(f"⚠️ Impossible de prechauffer '{model_name}' ({e}) -- il se chargera au premier vrai appel.")

    for model_name in {ROUTER_MODEL, SYNTHESIS_MODEL}:
        threading.Thread(target=_warm, args=(model_name,), daemon=True).start()


app = create_app()

if __name__ == "__main__":
  
    app.run(host="0.0.0.0", port=8000, debug=True, threaded=True)