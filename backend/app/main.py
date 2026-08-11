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

    return app


app = create_app()

if __name__ == "__main__":
  
    app.run(host="0.0.0.0", port=8000, debug=True, threaded=True)
