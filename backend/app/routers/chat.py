# backend/app/routers/chat.py
import traceback
from flask import Blueprint, request, jsonify
from app.agent.agent import run_agent

chat_bp = Blueprint("chat", __name__)


@chat_bp.post("/message")
def chat():
    data = request.get_json(force=True) or {}
    message = data.get("message", "")

    chart_context = data.get("context")
    # Historique de conversation (liste de {"role": "user"|"assistant",
    # "content": str}), envoye par le frontend a chaque message pour que
    # l'agent comprenne les questions de suivi ("que signifie ce chiffre ?").
    history = data.get("history")
    try:
        reply = run_agent(message, chart_context=chart_context, history=history)
        return jsonify({"reply": reply})
    except Exception as e:
        traceback.print_exc()  # affiche la vraie erreur dans le terminal Flask
        return jsonify({"reply": f"Erreur backend : {str(e)}"})
