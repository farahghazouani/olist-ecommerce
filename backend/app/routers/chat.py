# backend/app/routers/chat.py
import json
import traceback

from flask import Blueprint, request, jsonify, Response, stream_with_context
from app.agent.agent import run_agent, run_agent_stream

chat_bp = Blueprint("chat", __name__)


@chat_bp.post("/message")
def chat():
    """Endpoint legacy, conserve pour compatibilite (reponse unique, pas de
    statuts intermediaires). Prefere /message/stream cote frontend."""
    data = request.get_json(force=True) or {}
    message = data.get("message", "")
    chart_context = data.get("context")
    history = data.get("history")
    try:
        reply = run_agent(message, chart_context=chart_context, history=history)
        return jsonify({"reply": reply})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"reply": f"Erreur backend : {str(e)}"})


@chat_bp.post("/message/stream")
def chat_stream():
    """Endpoint SSE : emet des evenements de statut au fur et a mesure
    ('recherche des top categories...', etc.) puis un evenement final avec
    la reponse complete et le temps ecoule reel. Objectif : que
    l'utilisateur voie IMMEDIATEMENT que sa question a ete comprise et ce
    que fait l'agent, au lieu d'un spinner muet pendant 10-30+ secondes."""
    data = request.get_json(force=True) or {}
    message = data.get("message", "")
    chart_context = data.get("context")
    history = data.get("history")

    def generate():
        try:
            for event in run_agent_stream(message, chart_context=chart_context, history=history):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            traceback.print_exc()
            err_event = {"event": "final", "reply": f"Erreur backend : {str(e)}"}
            yield f"data: {json.dumps(err_event, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # desactive le buffering si un reverse-proxy nginx est ajoute plus tard
        },
    )
