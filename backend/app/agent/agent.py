# backend/app/agent/agent.py
"""


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
SYNTHESIS_MODEL = os.environ.get("SYNTHESIS_MODEL", ROUTER_MODEL)

_ollama_lock = threading.Lock()

ROUTER_TIMEOUT_SECONDS = int(os.environ.get("ROUTER_TIMEOUT_SECONDS", "75"))
SYNTHESIS_TIMEOUT_SECONDS = int(os.environ.get("SYNTHESIS_TIMEOUT_SECONDS", "120"))

KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "5m")


def _ollama_chat(messages, tools=None, model=ROUTER_MODEL, options=None, keep_alive=None, timeout_seconds=45):
    """Appelle POST /api/chat sur Ollama en HTTP streaming, avec un timeout
    qui ferme REELLEMENT la connexion en cas de depassement."""
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




SYSTEM_PROMPT = """Assistant BI e-commerce (Olist). Règles :
1. Question sur des données/chiffres -> utilise le(s) outil(s) approprié(s). Plusieurs demandes distinctes -> un appel par demande, même réponse.
2. Salutation/discussion générale -> réponds normalement, sans outil.
3. N'invente jamais un paramètre hors du schéma. Paramètres optionnels non fournis -> le serveur les complète, ne refuse jamais un outil pour ça.
4. Données réelles : sept 2016 à août 2018 seulement. Hors période -> pas d'outil, dis-le. Ne s'applique pas aux prévisions.
5. Message ambigu/trop court -> pas d'outil, demande une clarification.
6. Vérifie d'abord l'historique et le contexte de graphique fourni -- utilise-le SEULEMENT s'il répond vraiment à la question posée. S'il ne répond pas à la question (autre sujet, autre métrique), IGNORE-le et appelle l'outil approprié.
7. Ne traduis jamais un nom de catégorie donné par l'utilisateur.
8. Un code d'État brésilien (SP, RJ...) n'est jamais une catégorie.
9. Si la question porte sur un sujet, une catégorie, un état, un mois ou un montant DIFFÉRENT d'une question précédente -- même si le type de question se ressemble -- rappelle l'outil correspondant avec les nouvelles valeurs. Ne recopie JAMAIS un résultat déjà donné pour un sujet différent (ex: le CA d'une catégorie n'est pas le CA d'un état).
10. Un mot comme "prévision/prévois/forecast" -> forecast_category_revenue. Si un mois ET une année sont mentionnés (ex: septembre 2018), passe-les en target_month au format YYYY-MM.
11. Ne mentionne JAMAIS un nom d'outil, ni ton raisonnement sur quel outil utiliser, dans ta réponse à l'utilisateur -- décide en silence, puis réponds directement avec le résultat ou l'explication, jamais en décrivant le processus.
12. "Acheteur"/"client"/"costumer"/"buyer" désignent TOUJOURS le client (get_top_customers) ; "vendeur"/"seller" désigne TOUJOURS le vendeur (get_top_sellers) -- ne jamais confondre les deux.

Exemples : "risque retard meubles SP novembre" -> predict_delivery_risk(category="meubles", customer_state="SP", order_month=11) ; "pourquoi meubles mal notée" -> explain_category_complaints(category="meubles") ; "CA février 2017" -> get_revenue_for_period(month="2017-02") ; "prévision beleza_saude pour décembre 2018" -> forecast_category_revenue(category="beleza_saude", target_month="2018-12") ; "segment client 5 commandes 2000 R$" -> predict_customer_segment(recency=0, frequency=5, monetary=2000) ; "combien de catégories" -> get_category_count() ; "top vendeurs à SP" -> get_top_sellers(state="SP") ; "top acheteurs" -> get_top_customers() ; "top vendeurs" -> get_top_sellers().
"""


def _format_revenue_by_month(r, lang: str) -> str:
    """Affiche REELLEMENT les chiffres mois par mois, plus le meilleur et le
    pire mois (calcules en Python via max()/min(), aucun risque
    d'invention)."""
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


def _format_forecast(r: dict, lang: str) -> str:
    """Formate la prevision -- TOUJOURS avec le mois REELLEMENT prevu en
    evidence, et un avertissement si la prevision est recursive (months_ahead > 1)."""
    months_ahead = r.get("months_ahead", 1)
    state_part = ""
    if r.get("state"):
        state_part = (
            f", dont {r['predicted_revenue_state']:,.2f} R$ pour {r['state']}"
            if lang == "fr" else
            f", of which {r['predicted_revenue_state']:,.2f} R$ for {r['state']}"
        )

    if lang == "en":
        base = (
            f"The revenue forecast for category **{r['category']}** ({r['forecast_month']}) is "
            f"{r['predicted_revenue_total']:,.2f} R${state_part}."
        )
        if months_ahead > 1:
            base += (
                f" ⚠️ This forecast projects {months_ahead} months ahead by chaining monthly "
                "predictions -- uncertainty increases with the horizon, treat it as indicative "
                "rather than precise."
            )
        return base

    base = (
        f"La prévision de CA pour la catégorie **{r['category']}** ({r['forecast_month']}) est de "
        f"{r['predicted_revenue_total']:,.2f} R${state_part}."
    )
    if months_ahead > 1:
        base += (
            f" ⚠️ Cette prévision projette {months_ahead} mois à l'avance en chaînant des "
            "prédictions mensuelles successives -- l'incertitude augmente avec l'horizon, à "
            "prendre comme indicatif plutôt que précis."
        )
    return base



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
    "get_revenue_for_category": lambda r: (
        f"Le chiffre d'affaires TOTAL (toute la période disponible, sept. 2016 – août 2018, "
        f"pas un découpage mensuel) de la catégorie **{r['category']}** est de {r['revenue']:,.2f} R$."
    ),
    "get_revenue_for_state": lambda r: (
        f"Le chiffre d'affaires TOTAL (toute la période disponible) pour l'état **{r['state']}** "
        f"est de {r['revenue']:,.2f} R$."
    ),
    "get_category_count": lambda r: (
        f"Il y a **{r['count']}** catégories de produits distinctes : "
        + ", ".join(sorted(r["categories"])) + "."
    ),
    "get_state_count": lambda r: (
        f"Il y a **{r['count']}** États clients distincts : "
        + ", ".join(sorted(r["states"])) + "."
    ),
    "get_category_averages": lambda r: (
        f"Caractéristiques moyennes de la catégorie **{r['category']}** ({r['n_orders']:,} commandes) : "
        f"prix moyen {r['avg_price']:,.2f} R$, frais de port moyen {r['avg_freight']:,.2f} R$, "
        f"délai de livraison moyen {r['avg_delivery_delay_days']:+.1f} j (négatif = livré en avance), "
        f"note moyenne {r['avg_review_score']:.2f}/5, {r['pct_late']:.1f}% de commandes en retard."
    ),
    "get_top_sellers": lambda r: (
        "Top vendeurs par CA : " + "; ".join(
            f"{i+1}. {s['seller_id'][:8]}… ({s['revenue']:,.2f} R$, {s.get('seller_state', '?')})"
            for i, s in enumerate(r)
        )
    ),
    "get_top_customers": lambda r: (
        "Top clients par montant dépensé : " + "; ".join(
            f"{i+1}. {c['customer_id'][:8]}… ({c['total_spent']:,.2f} R$, {c.get('customer_state', '?')})"
            for i, c in enumerate(r)
        )
    ),
    "forecast_category_revenue": lambda r: _format_forecast(r, "fr"),
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
    "get_revenue_for_category": lambda r: (
        f"TOTAL revenue (full available period, Sept 2016 – Aug 2018, not a monthly breakdown) "
        f"for category **{r['category']}** is {r['revenue']:,.2f} R$."
    ),
    "get_revenue_for_state": lambda r: (
        f"TOTAL revenue (full available period) for state **{r['state']}** is {r['revenue']:,.2f} R$."
    ),
    "get_category_count": lambda r: (
        f"There are **{r['count']}** distinct product categories: "
        + ", ".join(sorted(r["categories"])) + "."
    ),
    "get_state_count": lambda r: (
        f"There are **{r['count']}** distinct customer states: "
        + ", ".join(sorted(r["states"])) + "."
    ),
    "get_category_averages": lambda r: (
        f"Average characteristics for category **{r['category']}** ({r['n_orders']:,} orders): "
        f"avg price {r['avg_price']:,.2f} R$, avg freight {r['avg_freight']:,.2f} R$, "
        f"avg delivery delay {r['avg_delivery_delay_days']:+.1f} days (negative = delivered early), "
        f"avg review score {r['avg_review_score']:.2f}/5, {r['pct_late']:.1f}% of orders late."
    ),
    "get_top_sellers": lambda r: (
        "Top sellers by revenue: " + "; ".join(
            f"{i+1}. {s['seller_id'][:8]}… ({s['revenue']:,.2f} R$, {s.get('seller_state', '?')})"
            for i, s in enumerate(r)
        )
    ),
    "get_top_customers": lambda r: (
        "Top customers by amount spent: " + "; ".join(
            f"{i+1}. {c['customer_id'][:8]}… ({c['total_spent']:,.2f} R$, {c.get('customer_state', '?')})"
            for i, c in enumerate(r)
        )
    ),
    "forecast_category_revenue": lambda r: _format_forecast(r, "en"),
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


# ============================================================================
# INDICE MOIS/ANNEE PRECALCULE -- allege le raisonnement du routeur, PAS
# une decision d'outil a sa place.
# ============================================================================
_MONTHS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
}
_MONTHS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_MONTH_YEAR_PATTERN = re.compile(
    r"\b(" + "|".join(list(_MONTHS_FR) + list(_MONTHS_EN)) + r")\b\D{0,10}(\d{4})\b", re.I
)
_ISO_DATE_PATTERN = re.compile(r"\b(\d{4})-(\d{2})(?:-\d{2})?\b")


def _detect_month_year_hint(message: str) -> str | None:
    iso_match = _ISO_DATE_PATTERN.search(message)
    if iso_match:
        year, month = iso_match.group(1), iso_match.group(2)
        if 1 <= int(month) <= 12:
            return f"{year}-{month}"

    match = _MONTH_YEAR_PATTERN.search(message)
    if not match:
        return None
    month_word, year = match.group(1).lower(), match.group(2)
    month_num = _MONTHS_FR.get(month_word) or _MONTHS_EN.get(month_word)
    if not month_num:
        return None
    return f"{year}-{month_num:02d}"


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
    "get_top_categories": "top catégories", "get_revenue_for_category": "CA d'une catégorie",
    "get_revenue_for_state": "CA d'un état",
    "get_category_count": "nombre de catégories", "get_state_count": "nombre d'états",
    "get_category_averages": "moyennes d'une catégorie",
    "get_top_sellers": "top vendeurs", "get_top_customers": "top clients",
    "forecast_category_revenue": "prévision de CA",
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
    (re.compile(r"combien\s+(?:de\s+)?cat[ée]gories|nombre\s+de\s+cat[ée]gories|how many categories", re.I),
     "get_category_count"),
    (re.compile(r"combien\s+(?:d'|de\s+)?[ée]tats|nombre\s+d'[ée]tats|how many states", re.I),
     "get_state_count"),
]
_stale_zero_arg = {tool for _, tool in _ZERO_ARG_PATTERNS} - _ZERO_ARG_TOOLS
if _stale_zero_arg:
    raise RuntimeError(
        f"Routage deterministe invalide -- ces outils ne sont plus zero-parametre : {_stale_zero_arg}"
    )

_COMPOSITE_MARKERS = re.compile(r"\bet\s+(?:les?|la|le|des)\b|\bcompare\b|\bainsi que\b|\blien entre\b", re.I)

_TOP_CATEGORIES_PATTERN = re.compile(r"cat[ée]gories?\s+(les\s+)?plus\s+(rentables?|vendues?)|top\s*cat[ée]gories?", re.I)
_HAS_NUMBER = re.compile(r"\d")


def _try_deterministic_route(message: str):
    if _COMPOSITE_MARKERS.search(message):
        return None
    for pattern, tool in _ZERO_ARG_PATTERNS:
        if pattern.search(message):
            return tool
    if _TOP_CATEGORIES_PATTERN.search(message) and not _HAS_NUMBER.search(message):
        return "get_top_categories"
    return None


# ============================================================================
# REPONSE FIXE POUR LES QUESTIONS SUR L'IDENTITE DU SYSTEME.
# ============================================================================
_IDENTITY_QUESTION_PATTERN = re.compile(
    r"quel\s+(?:llm|mod[èe]le)\s+(?:utilises|utilise|tu utilises)|"
    r"which\s+(?:llm|model)\s+(?:do you use|are you)|what\s+(?:llm|model)\s+(?:are you|is this)",
    re.I,
)

_IDENTITY_ANSWER_FR = (
    "Je suis un assistant BI construit sur un modèle de langage local (Qwen 2.5, 3B, via Ollama) "
    "pour choisir les outils et extraire les paramètres de tes questions -- pas Claude ni un autre "
    "modèle propriétaire. Un modèle local sert aussi à synthétiser les avis clients trouvés."
)
_IDENTITY_ANSWER_EN = (
    "I'm a BI assistant built on a local language model (Qwen 2.5, 3B, via Ollama) that chooses "
    "tools and extracts parameters from your questions -- not Claude or another proprietary model. "
    "A local model also synthesizes customer reviews it retrieves."
)


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


HISTORY_WINDOW = 4
HISTORY_MESSAGE_MAX_CHARS = 300


def _truncate_for_history(content: str) -> str:
    if len(content) <= HISTORY_MESSAGE_MAX_CHARS:
        return content
    return content[:HISTORY_MESSAGE_MAX_CHARS] + " […]"


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

    if _IDENTITY_QUESTION_PATTERN.search(message):
        yield {"event": "final", "reply": _IDENTITY_ANSWER_EN if lang == "en" else _IDENTITY_ANSWER_FR,
               "elapsed": round(time.time() - t0, 2)}
        return

    det_tool = _try_deterministic_route(message)
    if det_tool:
        yield {"event": "status", "message": status_labels["tool_call"].format(label=_TOOL_LABELS.get(det_tool, det_tool))}
        result = call_tool_safely(det_tool, {})
        print(f"⚡ [deterministe] {det_tool}() → {result}")
        if isinstance(result, dict) and "error" in result:
            reply = str(result["error"])
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
                messages.append({"role": role, "content": _truncate_for_history(content)})
    if has_context:
        messages.append({"role": "system", "content": _build_context_message(chart_context, lang)})

    month_hint = _detect_month_year_hint(message)
    if month_hint:
        hint_text = (
            f"(Indice calcule automatiquement, pas une instruction : si tu utilises un outil de "
            f"prevision, le mois mentionne dans la question correspond a target_month='{month_hint}'. "
            f"Tu restes libre de l'utiliser ou non selon la question.)"
            if lang == "fr" else
            f"(Auto-computed hint, not an instruction: if you use a forecasting tool, the month "
            f"mentioned in the question corresponds to target_month='{month_hint}'. Use it or not "
            f"based on the actual question.)"
        )
        messages.append({"role": "system", "content": hint_text})

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
                facts.append(str(result["error"]))
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
