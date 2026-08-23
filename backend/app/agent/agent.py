# backend/app/agent/agent.py
"""
Architecture "routeur LLM" -- lis ceci avant de modifier quoi que ce soit.

PRINCIPE : le choix de l'outil pour N'IMPORTE QUELLE question sur les
donnees Olist est TOUJOURS decide par un LLM (tool-calling natif Ollama),
jamais par une regex qui devine une intention. C'est la difference avec les
versions precedentes de ce fichier, qui accumulaient des patterns par
mot-cle -- ca ne generalisait a aucune formulation non anticipee, et ca
niait le role reel de l'agent.

Pour tenir cette promesse SANS latence catastrophique, on separe deux
modeles (pattern standard de "model routing" en prod) :

  - ROUTER_MODEL (petit, rapide) : choisit l'outil et ses parametres pour
    TOUTE question, a chaque fois. C'est le chemin chaud.
  - SYNTHESIS_MODEL : uniquement pour synthetiser/traduire les avis
    clients trouves par le RAG. Par defaut IDENTIQUE a ROUTER_MODEL --
    sur une machine CPU contrainte, deux modeles differents charges en
    meme temps se disputent les memes coeurs et ralentissent TOUT, y
    compris les questions triviales (mesure : 2 modeles simultanes = plus
    lent que chacun seul, voir historique de debug).

Les templates Python deterministes (TEMPLATES_FR/EN) ne sont PAS une
reduction du role du LLM : c'est du grounding standard en prod -- un LLM ne
doit jamais reformuler un chiffre exact (risque d'hallucination/arrondi),
il se contente de choisir QUEL chiffre aller chercher. Le LLM garde donc son
role reel : decider, pas calculer.
"""
import inspect
import json
import os
import re
import threading
import time

import requests
from langdetect import detect, LangDetectException
from app.agent.tools import AVAILABLE_FUNCTIONS, TOOLS_SPEC

# ============================================================================
# Configuration Ollama -- DEUX modeles, deux roles (voir docstring)
# ============================================================================
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

ROUTER_MODEL = os.environ.get("ROUTER_MODEL", "qwen2.5:3b-instruct")

# Par defaut IDENTIQUE a ROUTER_MODEL -- voir docstring : sur une machine
# CPU contrainte, deux modeles differents charges en meme temps se
# disputent les memes coeurs et ralentissent TOUT, y compris les questions
# triviales (mesure : 2 modeles simultanes = plus lent que chacun seul).
SYNTHESIS_MODEL = os.environ.get("SYNTHESIS_MODEL", ROUTER_MODEL)

_ollama_lock = threading.Lock()

ROUTER_TIMEOUT_SECONDS = int(os.environ.get("ROUTER_TIMEOUT_SECONDS", "60"))
SYNTHESIS_TIMEOUT_SECONDS = int(os.environ.get("SYNTHESIS_TIMEOUT_SECONDS", "120"))

# IMPORTANT -- Ollama garde un modele charge en RAM pendant "keep_alive"
# INDEPENDAMMENT du cycle de vie de Flask : redemarrer `python -m app.main`
# NE decharge PAS un modele deja resident dans Ollama (c'est un processus a
# part, qui tourne en arriere-plan independamment). Si SYNTHESIS_MODEL !=
# ROUTER_MODEL a un moment donne (ancien test, script, env var oubliee dans
# un autre terminal), le modele reste en memoire jusqu'a expiration de ce
# delai -- meme apres avoir corrige le code et redemarre Flask. C'est ce qui
# explique un "ca marche, puis ca replante sans rien avoir change" : la
# contention RAM revient des qu'un ancien modele encore resident se
# reactive. On raccourcit donc le delai par defaut (30min -> 5min) pour
# limiter la fenetre de contention residuelle possible. Le cout en echange
# est un rechargement (quelques secondes) si le modele reste inactif plus
# de 5 min -- meilleur compromis que 30 min de contention silencieuse sur
# une machine a RAM limitee.
#
# VERIFICATION MANUELLE RECOMMANDEE avant toute session de test :
#   ollama ps                    -> liste ce qui est REELLEMENT charge la
#   ollama stop <nom_du_modele>  -> le decharger immediatement si besoin
# Ne jamais supposer qu'un redemarrage de Flask suffit a lui seul.
KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "5m")


def _ollama_chat(messages, tools=None, model=ROUTER_MODEL, options=None, keep_alive=None, timeout_seconds=45):
    """Appelle POST /api/chat sur Ollama en HTTP streaming, avec un timeout
    qui ferme REELLEMENT la connexion en cas de depassement (contrairement a
    un pattern ThreadPoolExecutor, qui attend en silence meme apres un
    TimeoutError -- ne jamais reintroduire ce bug, voir historique)."""
    payload = {
        "model": model,
        "messages": messages,
        "options": options or {},
        "keep_alive": keep_alive or KEEP_ALIVE,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools

    start = time.time()
    with _ollama_lock:
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat", json=payload, stream=True, timeout=(5, timeout_seconds + 10)
            )
        except requests.exceptions.Timeout:
            return None, "timeout"
        except requests.exceptions.RequestException as e:
            return None, f"connection:{e}"

        message = {"role": "assistant", "content": ""}
        timed_out = False
        try:
            for line in resp.iter_lines():
                if time.time() - start > timeout_seconds:
                    timed_out = True
                    break
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg_chunk = chunk.get("message", {})
                if msg_chunk.get("content"):
                    message["content"] += msg_chunk["content"]
                if msg_chunk.get("tool_calls"):
                    message["tool_calls"] = msg_chunk["tool_calls"]
                if chunk.get("done"):
                    break
        except requests.exceptions.RequestException:
            timed_out = True
        finally:
            resp.close()

    if timed_out:
        return None, "timeout"
    return {"message": message}, None


SYSTEM_PROMPT = """Tu es un assistant BI pour une plateforme e-commerce (marketplace Olist).

RÈGLES :
1. Pour une question portant sur des CHIFFRES ou des DONNÉES DE L'ENTREPRISE
   (ventes, CA, prévisions, performance, avis clients), tu DOIS utiliser le ou
   les outils appropriés. Si le message contient PLUSIEURS demandes de
   données distinctes, tu DOIS appeler un outil pour CHACUNE d'entre elles
   dans la MÊME réponse.
2. Pour une salutation ou une conversation générale ne concernant PAS les
   données de l'entreprise, réponds normalement SANS utiliser d'outil.
3. N'INVENTE JAMAIS un paramètre absent du schéma d'un outil. Un outil peut
   avoir des paramètres OPTIONNELS (absents de "required") : tu n'es JAMAIS
   obligé de les fournir — appelle l'outil avec les paramètres "required"
   que tu connais, le serveur gère le reste et le signale toujours.
4. Les données HISTORIQUES couvrent uniquement septembre 2016 à août 2018.
   Pour un chiffre HISTORIQUE hors de cette période, N'APPELLE AUCUN outil et
   dis-le. Cette règle NE s'applique PAS aux PRÉVISIONS.
5. Si le message est ambigu, trop court, ou un mot générique isolé, N'APPELLE
   AUCUN outil — demande une clarification, ne devine jamais une intention.
6. AVANT d'appeler un outil, vérifie si l'info est DÉJÀ dans l'historique OU
   dans le contexte de graphique fourni, ET si ce contexte est réellement
   pertinent. Si oui, N'APPELLE AUCUN outil. Le contexte de graphique n'est
   PAS toujours pertinent — s'il ne répond pas à la question, IGNORE-le et
   appelle l'outil approprié.
7. Ne traduis/reformule JAMAIS un nom de catégorie fourni par l'utilisateur.
8. Un code d'État brésilien N'EST JAMAIS une catégorie de produit.
9. RÈGLE CRITIQUE, SOUVENT MAL APPLIQUÉE : si la question actuelle porte sur
   les MÊMES paramètres (catégorie, état, mois, montants...) qu'une question
   précédente dans l'historique, tu PEUX réutiliser la réponse déjà donnée
   SANS rappeler l'outil. MAIS si NE SERAIT-CE QU'UN SEUL paramètre diffère
   de la question précédente (catégorie différente, état différent, mois
   différent, montant différent...), tu DOIS IMPÉRATIVEMENT rappeler l'outil
   avec les NOUVELLES valeurs — ne recopie JAMAIS un résultat numérique
   précédent pour des paramètres différents, même si la question ressemble
   à une question déjà posée.

EXEMPLES :
- "Risque de retard pour meubles à SP en novembre ?" puis "et pour beleza_saude à SP en mars ?" → DEUX appels séparés à predict_delivery_risk, avec des paramètres DIFFÉRENTS à chaque fois (catégorie et mois ont changé) — ne jamais renvoyer le même chiffre pour les deux.
- "Pourquoi meubles est mal notée ?" → explain_category_complaints(category="meubles")
- "Que disent les clients de meubles ?" → search_reviews(query="avis meubles", category="meubles")
- "Quel segment pour un client avec 5 commandes et 2000 R$ ?" → predict_customer_segment(recency=0, frequency=5, monetary=2000)
- "Quel a été le CA en février 2017 ?" → get_revenue_for_period(month="2017-02")
- "Combien on a fait la semaine dernière ?" → get_revenue_for_period(weeks_ago=0)
- "Quelles sont les catégories les plus rentables ?" → get_top_categories()
- "Combien de commandes ont été passées ?" / "chiffre d'affaires global/total" → get_kpi_summary()
"""

def _format_revenue_by_month(r, lang: str) -> str:
    """Affiche REELLEMENT les chiffres mois par mois, plus le meilleur et le
    pire mois (calcules en Python via max()/min(), aucun risque
    d'invention -- ce sont des faits exacts issus de l'API). L'ancienne
    version se contentait de dire 'voici l'evolution sur X mois' SANS
    jamais montrer un seul chiffre -- inutile comme reponse a une question
    qui demande justement de voir les donnees."""
    if not (isinstance(r, list) and len(r) > 0):
        return "Aucune donnée d'évolution mensuelle disponible." if lang == "fr" else "No monthly revenue data available."

    best = max(r, key=lambda m: m["revenue"])
    worst = min(r, key=lambda m: m["revenue"])
    lines = "\n".join(f"- {m['month'][:7]} : {m['revenue']:,.2f} R$" for m in r)

    if lang == "en":
        return (
            f"Revenue evolution over {len(r)} months ({r[0]['month'][:7]} to {r[-1]['month'][:7]}):\n{lines}\n\n"
            f"Best month: {best['month'][:7]} ({best['revenue']:,.2f} R$). "
            f"Lowest month: {worst['month'][:7]} ({worst['revenue']:,.2f} R$)."
        )
    return (
        f"Évolution du chiffre d'affaires sur {len(r)} mois ({r[0]['month'][:7]} à {r[-1]['month'][:7]}) :\n{lines}\n\n"
        f"Meilleur mois : {best['month'][:7]} ({best['revenue']:,.2f} R$). "
        f"Mois le plus faible : {worst['month'][:7]} ({worst['revenue']:,.2f} R$)."
    )


TEMPLATES_FR = {
    "get_kpi_summary": lambda r: (
        f"Le chiffre d'affaires total est de {r['total_revenue']:,.2f} R$ "
        f"sur {r['total_orders']:,} commandes, avec un panier moyen de {r['avg_order_value']:.2f} R$."
    ),
    "get_revenue_for_period": lambda r: (
        f"Le chiffre d'affaires de la semaine du {r['week']} est de "
        f"{r['revenue']:,.2f} R$ sur {r['n_orders']} commandes."
    ) if "week" in r else (
        f"Le chiffre d'affaires de {r['month']} est de {r['revenue']:,.2f} R$."
    ),
    "get_revenue_by_month": lambda r: _format_revenue_by_month(r, "fr"),
    "get_top_categories": lambda r: (
        "Voici le classement : " + "; ".join(f"{i+1}. {c['category']} ({c['revenue']:,.2f} R$)" for i, c in enumerate(r))
    ),
    "forecast_category_revenue": lambda r: (
        f"La prévision de CA pour la catégorie **{r['category']}** ({r['forecast_month']}) est de "
        f"{r['predicted_revenue_total']:,.2f} R$"
        + (f", dont {r['predicted_revenue_state']:,.2f} R$ pour {r['state']}." if r.get('state') else ".")
    ),
    "predict_delivery_risk": lambda r: (
        f"Risque de retard estimé : **{r['risk_level']}** ({r['risk_probability']*100:.1f}%)."
        + (f" Facteurs principaux : {', '.join(r['top_factors'])}." if r.get('top_factors') else "")
    ),
    "get_customer_segments": lambda r: (
        "Segments clients : " + "; ".join(f"{s['segment_name']} ({s['pct']}%)" for s in r)
    ),
    "predict_customer_segment": lambda r: (
        f"Un client avec ce profil appartiendrait au segment **{r['segment']}**."
    ),
}

TEMPLATES_EN = {
    "get_kpi_summary": lambda r: (
        f"Total revenue is {r['total_revenue']:,.2f} R$ "
        f"across {r['total_orders']:,} orders, with an average order value of {r['avg_order_value']:.2f} R$."
    ),
    "get_revenue_for_period": lambda r: (
        f"Revenue for the week of {r['week']} was {r['revenue']:,.2f} R$ across {r['n_orders']} orders."
    ) if "week" in r else (
        f"Revenue for {r['month']} was {r['revenue']:,.2f} R$."
    ),
    "get_revenue_by_month": lambda r: _format_revenue_by_month(r, "en"),
    "get_top_categories": lambda r: (
        "Top categories: " + "; ".join(f"{i+1}. {c['category']} ({c['revenue']:,.2f} R$)" for i, c in enumerate(r))
    ),
    "forecast_category_revenue": lambda r: (
        f"The revenue forecast for category **{r['category']}** ({r['forecast_month']}) is "
        f"{r['predicted_revenue_total']:,.2f} R$"
        + (f", of which {r['predicted_revenue_state']:,.2f} R$ for {r['state']}." if r.get('state') else ".")
    ),
    "predict_delivery_risk": lambda r: (
        f"Estimated delay risk: **{r['risk_level']}** ({r['risk_probability']*100:.1f}%)."
        + (f" Main factors: {', '.join(r['top_factors'])}." if r.get('top_factors') else "")
    ),
    "get_customer_segments": lambda r: (
        "Customer segments: " + "; ".join(f"{s['segment_name']} ({s['pct']}%)" for s in r)
    ),
    "predict_customer_segment": lambda r: (
        f"A customer with this profile would fall into the **{r['segment']}** segment."
    ),
}

RAG_TOOLS = {"search_reviews", "explain_category_complaints"}
_all_tool_names = {t["function"]["name"] for t in TOOLS_SPEC}
_template_required = _all_tool_names - RAG_TOOLS
_missing_fr = _template_required - set(TEMPLATES_FR)
_missing_en = _template_required - set(TEMPLATES_EN)
_stale_fr = set(TEMPLATES_FR) - _all_tool_names
_stale_en = set(TEMPLATES_EN) - _all_tool_names
if _missing_fr or _missing_en or _stale_fr or _stale_en:
    raise RuntimeError(
        "Configuration agent invalide -- TOOLS_SPEC/TEMPLATES desynchronises : "
        f"manquants FR={_missing_fr or 'aucun'}, manquants EN={_missing_en or 'aucun'}, "
        f"obsoletes FR={_stale_fr or 'aucun'}, obsoletes EN={_stale_en or 'aucun'}"
    )


def detect_lang(text: str) -> str:
    words = text.strip().split()
    if len(words) < 4:
        return None
    try:
        return "en" if detect(text) == "en" else "fr"
    except LangDetectException:
        return None


def call_tool_safely(fn_name: str, fn_args: dict):
    fn = AVAILABLE_FUNCTIONS.get(fn_name)
    if fn is None:
        return {"error": f"Outil inconnu : {fn_name}"}

    sig = inspect.signature(fn)
    valid_params = set(sig.parameters.keys())
    filtered_args = {k: v for k, v in (fn_args or {}).items() if k in valid_params}

    missing = [
        name for name, p in sig.parameters.items()
        if p.default is inspect.Parameter.empty and name not in filtered_args
    ]
    if missing:
        return {"missing_params": missing, "tool": fn_name}

    defaulted = [
        name for name, p in sig.parameters.items()
        if p.default is not inspect.Parameter.empty and name not in filtered_args
    ]

    try:
        result = fn(**filtered_args)
    except Exception as e:
        return {"error": f"Erreur lors de l'exécution de {fn_name} : {e}"}

    if isinstance(result, dict) and "error" not in result and defaulted:
        result = {**result, "_defaulted_params": defaulted}
    return result


MIN_MESSAGE_LENGTH = 3


def _has_usable_context(chart_context: dict | None) -> bool:
    if not chart_context:
        return False
    data = chart_context.get("data")
    if data is None:
        return False
    if isinstance(data, (list, dict)) and len(data) == 0:
        return False
    return True


def _build_context_message(chart_context: dict, lang: str) -> str:
    title = chart_context.get("chart_title", "un graphique")
    page = chart_context.get("page", "")
    filters = chart_context.get("filters") or {}
    data = chart_context.get("data")
    filters_str = ", ".join(f"{k}={v}" for k, v in filters.items()) if filters else ("none" if lang == "en" else "aucun")

    relevance_note = (
        "This context may or may not be relevant to the question below -- use it ONLY if it "
        "genuinely answers the question. If not, IGNORE it and call the appropriate tool instead."
        if lang == "en" else
        "Ce contexte peut ne PAS être pertinent pour la question ci-dessous -- utilise-le "
        "UNIQUEMENT s'il répond réellement à la question. Sinon, IGNORE-le et appelle l'outil approprié."
    )
    if lang == "en":
        return (
            f"The user is looking at a chart titled '{title}' on the '{page}' page. "
            f"Active filters: {filters_str}. Exact data currently displayed (JSON): {data}\n{relevance_note}"
        )
    return (
        f"L'utilisateur regarde un graphique intitulé « {title} » sur la page « {page} ». "
        f"Filtres actifs : {filters_str}. Données EXACTES affichées (JSON) : {data}\n{relevance_note}"
    )


_STATUS_FR = {
    "thinking": "🧠 Choix de l'outil approprié…",
    "tool_call": "🔧 Récupération de « {label} »…",
    "synthesizing": "✍️ Rédaction de la réponse…",
}
_STATUS_EN = {
    "thinking": "🧠 Choosing the right tool…",
    "tool_call": "🔧 Fetching '{label}'…",
    "synthesizing": "✍️ Writing the answer…",
}
_TOOL_LABELS = {
    "get_kpi_summary": "indicateurs clés", "get_revenue_for_period": "CA sur une période",
    "get_revenue_by_month": "évolution mensuelle du CA",
    "get_top_categories": "top catégories", "forecast_category_revenue": "prévision de CA",
    "predict_delivery_risk": "risque de retard", "get_customer_segments": "segments clients",
    "predict_customer_segment": "segment client", "search_reviews": "avis clients",
    "explain_category_complaints": "analyse des avis négatifs",
}

# ============================================================================
# ROUTAGE DETERMINISTE -- UNIQUEMENT pour les outils SANS AUCUN PARAMETRE.
# ============================================================================
_ZERO_ARG_TOOLS = {
    name for name, fn in AVAILABLE_FUNCTIONS.items()
    if len(inspect.signature(fn).parameters) == 0
}

_ZERO_ARG_PATTERNS = [
    (re.compile(r"\bkpi\b|panier moyen|chiffre d'affaires (total|global)|ca (total|global)|"
                r"total revenue|average order|"
                r"combien\s+(?:de\s+commandes|avons[- ]nous\s+vendu)|"
                r"nombre\s+de\s+commandes|how many orders", re.I),
     "get_kpi_summary"),
    (re.compile(r"[ée]volution|tendance mensuelle|par mois|monthly revenue|au fil du temps", re.I),
     "get_revenue_by_month"),
    (re.compile(r"segments? client|customer segment", re.I),
     "get_customer_segments"),
]
_stale_zero_arg = {tool for _, tool in _ZERO_ARG_PATTERNS} - _ZERO_ARG_TOOLS
if _stale_zero_arg:
    raise RuntimeError(
        f"Routage deterministe invalide -- ces outils ne sont plus zero-parametre : {_stale_zero_arg}"
    )

_COMPOSITE_MARKERS = re.compile(r"\bet\s+(?:les?|la|le|des)\b|\bcompare\b|\bainsi que\b|\blien entre\b", re.I)


def _try_deterministic_route(message: str):
    if _COMPOSITE_MARKERS.search(message):
        return None
    for pattern, tool in _ZERO_ARG_PATTERNS:
        if pattern.search(message):
            return tool
    return None


def run_agent(user_message, chart_context=None, history=None, max_iterations=3) -> str:
    for event in _run_agent_events(user_message, chart_context, history, max_iterations):
        if event["event"] == "final":
            return event["reply"]
    return "Je n'ai pas pu récupérer l'information demandée."


def run_agent_stream(user_message, chart_context=None, history=None, max_iterations=3):
    yield from _run_agent_events(user_message, chart_context, history, max_iterations)


def _resolve_lang(message: str, history: list | None) -> str:
    detected = detect_lang(message)
    if detected:
        return detected
    if history:
        for turn in reversed(history):
            if turn.get("role") == "assistant" and turn.get("content"):
                prev = detect_lang(turn["content"])
                if prev:
                    return prev
    return "fr"


# Fenetre d'historique reduite (etait 10) : chaque message supplementaire
# grossit le prompt envoye a CHAQUE appel du routeur, ce qui ralentit
# progressivement un petit modele CPU au fil d'une longue conversation --
# c'est la cause la plus probable des timeouts qui reapparaissent apres
# plusieurs echanges reussis. 6 messages = ~3 echanges, suffisant pour le
# suivi conversationnel courant sans laisser le prompt grossir sans limite.
HISTORY_WINDOW = 6


def _run_agent_events(user_message, chart_context, history, max_iterations):
    t0 = time.time()
    message = (user_message or "").strip()
    lang = _resolve_lang(message, history)
    templates = TEMPLATES_EN if lang == "en" else TEMPLATES_FR
    status_labels = _STATUS_EN if lang == "en" else _STATUS_FR
    has_context = _has_usable_context(chart_context)

    if len(message) < MIN_MESSAGE_LENGTH and not has_context:
        yield {"event": "final", "reply": (
            "Could you clarify your question? I can help with sales, forecasts, or customer reviews."
            if lang == "en" else
            "Peux-tu préciser ta question ? Je peux t'aider sur les ventes, les prévisions ou les avis clients."
        ), "elapsed": round(time.time() - t0, 2)}
        return

    # Le routage deterministe s'applique QUE LE CONTEXTE DE GRAPHIQUE SOIT
    # PRESENT OU NON. Le frontend envoie ce contexte en PERMANENCE des qu'un
    # graphique est affiche (donc quasiment tout le temps sur le dashboard)
    # -- le gater derriere "if not has_context" neutralise le routage
    # deterministe en usage reel (deja corrige une fois avant sur l'ancien
    # fast-path regex, reintroduit ici par erreur). Ces 3 outils sont
    # zero-parametre et leurs mots-cles sont sans ambiguite : peu importe
    # quel graphique est affiche a l'ecran, "evolution du CA par mois" veut
    # dire la meme chose. Seuls les marqueurs de composition/comparaison
    # (_COMPOSITE_MARKERS) doivent desactiver ce routage.
    det_tool = _try_deterministic_route(message)
    if det_tool:
        yield {"event": "status", "message": status_labels["tool_call"].format(label=_TOOL_LABELS.get(det_tool, det_tool))}
        result = call_tool_safely(det_tool, {})
        print(f"⚡ [deterministe] {det_tool}() → {result}")
        if isinstance(result, dict) and "error" in result:
            reply = (f"Une erreur est survenue en récupérant cette information ({det_tool})."
                     if lang == "fr" else f"An error occurred retrieving this information ({det_tool}).")
        else:
            try:
                reply = templates[det_tool](result)
            except Exception:
                reply = str(result)
        yield {"event": "final", "reply": reply, "elapsed": round(time.time() - t0, 2)}
        return

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        for turn in history[-HISTORY_WINDOW:]:
            role = "user" if turn.get("role") == "user" else "assistant"
            content = turn.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
    if has_context:
        messages.append({"role": "system", "content": _build_context_message(chart_context, lang)})
    messages.append({"role": "user", "content": message})

    facts = []
    rag_context = ""
    need_rag_synthesis = False
    called_tools = set()

    yield {"event": "status", "message": status_labels["thinking"]}

    for iteration in range(max_iterations):
        response, error = _ollama_chat(
            messages=messages, tools=TOOLS_SPEC, model=ROUTER_MODEL,
            options={"temperature": 0, "num_predict": 120},
            timeout_seconds=ROUTER_TIMEOUT_SECONDS,
        )
        if error == "timeout":
            yield {"event": "final", "reply": (
                f"⚠️ Le modèle de routage ({ROUTER_MODEL}) met trop de temps à répondre "
                f"(>{ROUTER_TIMEOUT_SECONDS}s). Vérifie qu'Ollama tourne normalement (`ollama ps`)."
                if lang == "fr" else
                f"⚠️ The routing model ({ROUTER_MODEL}) is taking too long (>{ROUTER_TIMEOUT_SECONDS}s). "
                "Check that Ollama is running normally (`ollama ps`)."
            ), "elapsed": round(time.time() - t0, 2)}
            return
        if error:
            yield {"event": "final", "reply": (
                f"⚠️ Impossible de contacter Ollama sur {OLLAMA_HOST} ({error}). Vérifie qu'Ollama est démarré."
            ), "elapsed": round(time.time() - t0, 2)}
            return

        tool_calls = response["message"].get("tool_calls")
        if not tool_calls:
            if iteration == 0:
                yield {"event": "final", "reply": response["message"]["content"], "elapsed": round(time.time() - t0, 2)}
                return
            break

        messages.append(response["message"])

        unique_calls = []
        for tool_call in tool_calls:
            fn_name = tool_call["function"]["name"]
            fn_args = tool_call["function"]["arguments"]
            sig = f"{fn_name}({fn_args})"
            if sig in called_tools:
                messages.append({"role": "tool", "content": "Déjà exécuté précédemment."})
                continue
            called_tools.add(sig)
            unique_calls.append((fn_name, fn_args))

        for fn_name, _ in unique_calls:
            yield {"event": "status", "message": status_labels["tool_call"].format(label=_TOOL_LABELS.get(fn_name, fn_name))}

        results = []
        if unique_calls:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(len(unique_calls), 5)) as executor:
                futures = {
                    executor.submit(call_tool_safely, fn_name, fn_args): (fn_name, fn_args)
                    for fn_name, fn_args in unique_calls
                }
                for future in futures:
                    fn_name, fn_args = futures[future]
                    results.append((fn_name, fn_args, future.result()))

        for fn_name, fn_args, result in results:
            print(f"🔧 [{lang}] {fn_name}({fn_args}) → {result}")
            messages.append({"role": "tool", "content": str(result)})

            if isinstance(result, dict) and "missing_params" in result:
                missing = result["missing_params"]
                facts.append(
                    f"Pour répondre précisément, il me manque : {', '.join(missing)}. Peux-tu préciser ?"
                    if lang == "fr" else
                    f"To answer precisely, I still need: {', '.join(missing)}. Could you specify?"
                )
            elif isinstance(result, dict) and "clarification_needed" in result:
                facts.append(result["clarification_needed"])
            elif isinstance(result, dict) and "error" in result:
                facts.append(f"Une erreur est survenue en récupérant cette information ({fn_name}).")
            elif fn_name in RAG_TOOLS:
                need_rag_synthesis = True
                reviews = result.get("retrieved_reviews") or result.get("reviews", [])
                category_matched = result.get("category_matched", True)
                if not reviews:
                    facts.append("Aucun avis client pertinent trouvé." if lang == "fr" else "No relevant customer reviews found.")
                else:
                    caveat = ""
                    if not category_matched and fn_args.get("category"):
                        caveat = (
                            f" (aucun avis spécifique à '{fn_args.get('category')}' -- toutes catégories confondues ci-dessous)"
                            if lang == "fr" else
                            f" (no reviews specific to '{fn_args.get('category')}' -- showing all categories)"
                        )
                    rag_context += (
                        f"\nAvis trouvés{caveat} :\n" if lang == "fr" else f"\nReviews found{caveat}:\n"
                    )
                    for i, rev in enumerate(reviews, 1):
                        rag_context += f'{i}. "{rev}"\n'
            elif fn_name in templates:
                try:
                    defaulted = result.get("_defaulted_params") if isinstance(result, dict) else None
                    clean_result = {k: v for k, v in result.items() if k != "_defaulted_params"} if isinstance(result, dict) else result
                    fact = templates[fn_name](clean_result)
                    if defaulted:
                        fact += (
                            f" ⚠️ Estimation basée sur des valeurs moyennes pour : {', '.join(defaulted)}."
                            if lang == "fr" else
                            f" ⚠️ Estimate based on average values for: {', '.join(defaulted)}."
                        )
                    facts.append(fact)
                except Exception as e:
                    print(f"⚠️ Erreur de template pour {fn_name} : {e} | résultat brut : {result}")
                    facts.append(str(result))
            else:
                facts.append(str(result))

    if need_rag_synthesis and rag_context:
        yield {"event": "status", "message": status_labels["synthesizing"]}
        lang_instruction = "Answer STRICTLY in English." if lang == "en" else "Réponds STRICTEMENT en français."
        synthesis_prompt = (
            f'Question : "{message}"\n\nAvis clients trouvés (originaux en portugais) :\n{rag_context}\n\n'
            f"{lang_instruction} Synthétise une réponse métier claire — ne traduis pas mot à mot, "
            "résume les points clés soulevés par les clients."
        )
        response, error = _ollama_chat(
            messages=[{"role": "user", "content": synthesis_prompt}], model=SYNTHESIS_MODEL,
            options={"temperature": 0, "num_predict": 180},
            timeout_seconds=SYNTHESIS_TIMEOUT_SECONDS,
        )
        if not error:
            facts.append(response["message"]["content"])
        else:
            facts.append(rag_context)

    reply = "\n\n".join(facts) if facts else (
        "I couldn't retrieve the requested information." if lang == "en" else "Je n'ai pas pu récupérer l'information demandée."
    )
    yield {"event": "final", "reply": reply, "elapsed": round(time.time() - t0, 2)}