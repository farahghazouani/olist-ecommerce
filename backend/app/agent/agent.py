# backend/app/agent/agent.py
import inspect
import threading
import ollama
from langdetect import detect, LangDetectException
from app.agent.tools import AVAILABLE_FUNCTIONS, TOOLS_SPEC

# threaded=True sur Flask (app/main.py) est bon pour ne pas bloquer les
# AUTRES routes (dashboard, ml, customers) pendant qu'un chat est en cours --
# mais Ollama local (llama3.1:8b, un seul processus, CPU/RAM limites) n'est
# pas concu pour traiter plusieurs completions en parallele : deux appels
# simultanes se disputent la meme ressource, ralentissent enormement (voir
# les 200s+ observes en test) et peuvent planter (502). Ce verrou garantit
# qu'un seul appel ollama.chat() s'execute a la fois, peu importe combien de
# requetes Flask arrivent en meme temps -- les autres attendent leur tour au
# lieu de faire ramer/planter Ollama.
_ollama_lock = threading.Lock()


def _ollama_chat(**kwargs):
    with _ollama_lock:
        return ollama.chat(**kwargs)


SYSTEM_PROMPT = """Tu es un assistant BI pour une plateforme e-commerce (marketplace Olist).

RÈGLES :
1. Pour une question portant sur des CHIFFRES ou des DONNÉES DE L'ENTREPRISE
   (ventes, CA, prévisions, performance, avis clients), tu DOIS utiliser le ou
   les outils appropriés — appelle TOUS les outils nécessaires, y compris
   plusieurs à la fois si la question en combine plusieurs (ex: "prévision ET
   classification" = 2 outils dans la même réponse).
2. Pour une salutation, une question sur toi-même, ou une conversation générale
   qui ne concerne PAS les données de l'entreprise, réponds normalement SANS
   utiliser d'outil.
3. N'ajoute JAMAIS de paramètre à un outil s'il n'est pas défini dans sa signature.
4. Les données HISTORIQUES disponibles couvrent uniquement la période de
   septembre 2016 à août 2018 (dataset Olist). Si l'utilisateur demande un
   chiffre HISTORIQUE (CA réalisé, commandes passées, avis) pour une date ou
   une année clairement en dehors de cette période (ex: 2020, 2028), N'APPELLE
   AUCUN outil et réponds directement que les données ne couvrent que
   sept. 2016 - août 2018. Cette règle NE s'applique PAS aux questions de
   PRÉVISION (ex: "CA prévu semaine prochaine", "prévision pour telle
   catégorie") : ce sont des questions sur le futur par nature, utilise les
   outils de prévision normalement, sans te soucier de la date.
5. Si le message de l'utilisateur est ambigu, trop court pour avoir un sens
   clair, ou ne correspond à aucune des règles ci-dessus (ex: un mot isolé
   sans contexte comme "cv", "test", "ok", "salut ça va", OU un mot générique
   seul sans précision comme "ventes", "chiffres", "données", "dis-moi tout"),
   N'APPELLE AUCUN outil. Réponds normalement en demandant une clarification,
   comme dans une conversation humaine normale — ne devine JAMAIS une
   intention pour justifier un appel d'outil.
6. AVANT d'appeler un outil, vérifie si l'information nécessaire est DÉJÀ
   présente dans l'historique de conversation ci-dessus (une réponse que TU
   as déjà donnée). Si oui — par exemple une question de suivi comme "que
   signifie ce chiffre ?", "pourquoi ?", "et donc ?", "c'est bien ou pas ?"
   qui porte sur un résultat déjà affiché plus haut — N'APPELLE AUCUN outil :
   relis et interprète directement ce résultat déjà présent dans l'historique.
   N'appelle un outil que si la question porte sur une donnée qui n'a PAS
   encore été récupérée dans cette conversation.
"""

TEMPLATES_FR = {
    "forecast_category_revenue": lambda r: (
        f"La prévision de CA pour la catégorie **{r['category']}** ({r['forecast_month']}) est de "
        f"{r['predicted_revenue_total']:,.2f} R$"
        + (f", dont {r['predicted_revenue_state']:,.2f} R$ pour {r['state']}." if r.get('state') else ".")
    ),
    "predict_delivery_risk": lambda r: (
        f"Risque de retard estimé : **{r['risk_level']}** ({r['risk_probability']*100:.1f}%). "
        f"Facteurs principaux : {', '.join(r['top_factors'])}."
    ),
    "get_customer_segments": lambda r: (
        "Segments clients : " + "; ".join(f"{s['segment_name']} ({s['pct']}%)" for s in r)
    ),
    "get_kpi_summary": lambda r: (
        f"Le chiffre d'affaires total est de {r['total_revenue']:,.2f} R$ "
        f"sur {r['total_orders']:,} commandes, avec un panier moyen de {r['avg_order_value']:.2f} R$."
    ),
    "get_revenue_for_week": lambda r: (
        f"Le chiffre d'affaires de la semaine du {r['week']} est de "
        f"{r['revenue']:,.2f} R$ sur {r['n_orders']} commandes."
    ),
    "get_revenue_by_month": lambda r: (
        f"Voici l'évolution du chiffre d'affaires sur {len(r)} mois "
        f"(du {r[0]['month']} au {r[-1]['month']})."
    )
    if isinstance(r, list) and len(r) > 0
    else "Aucune donnée d'évolution mensuelle disponible.",
    "get_revenue_last_week": lambda r: (
        f"Le chiffre d'affaires réalisé la semaine du {r['week']} est de "
        f"{r['revenue']:,.2f} R$ sur {r['n_orders']} commandes."
    ),
    "get_top_categories": lambda r: (
        "Voici le classement : "
        + "; ".join(
            f"{i+1}. {c['category']} ({c['revenue']:,.2f} R$)"
            for i, c in enumerate(r)
        )
    ),
}

TEMPLATES_EN = {
    "get_kpi_summary": lambda r: (
        f"Total revenue is {r['total_revenue']:,.2f} R$ "
        f"across {r['total_orders']:,} orders, with an average order value of {r['avg_order_value']:.2f} R$."
    ),
    "get_revenue_for_week": lambda r: (
        f"Le chiffre d'affaires de la semaine du {r['week']} est de "
        f"{r['revenue']:,.2f} R$ sur {r['n_orders']} commandes."
    ),
    "get_revenue_by_month": lambda r: (
        f"Here is the revenue evolution over {len(r)} months "
        f"(from {r[0]['month']} to {r[-1]['month']})."
    )
    if isinstance(r, list) and len(r) > 0
    else "No monthly revenue data available.",
    "get_revenue_last_week": lambda r: (
        f"The realized revenue for the week of {r['week']} is "
        f"{r['revenue']:,.2f} R$ across {r['n_orders']} orders."
    ),
    "get_top_categories": lambda r: (
        "Top categories: "
        + "; ".join(
            f"{i+1}. {c['category']} ({c['revenue']:,.2f} R$)"
            for i, c in enumerate(r)
        )
    ),
    "forecast_next_week": lambda r: (
        f"The revenue forecast for next week (after {r['last_known_week']}) "
        f"is {r['predicted_next_week_revenue']:,.2f} R$."
    ),
    "classify_next_week": lambda r: (
        f"The predicted business performance for next week is "
        f"**{r['predicted_performance']}** (confidence: {r['confidence']*100:.1f}%)."
    ),
}


def detect_lang(text: str) -> str:
    """Détecte la langue de la question ('fr' par défaut si indétectable)."""
    try:
        code = detect(text)
        return "en" if code == "en" else "fr"
    except LangDetectException:
        return "fr"


def call_tool_safely(fn_name: str, fn_args: dict):
    fn = AVAILABLE_FUNCTIONS.get(fn_name)
    if fn is None:
        return {"error": f"Outil inconnu : {fn_name}"}
    valid_params = set(inspect.signature(fn).parameters.keys())
    filtered_args = {k: v for k, v in fn_args.items() if k in valid_params}
    try:
        return fn(**filtered_args)
    except Exception as e:
        return {"error": f"Erreur lors de l'exécution de {fn_name} : {str(e)}"}


# En dessous de 3 caracteres, aucun LLM ne peut fiablement distinguer une
# vraie question ("CA" pour chiffre d'affaires) d'un test/salutation
# informelle ("cc", "cv", "ok") -- on court-circuite Ollama entierement
# pour ces cas : plus rapide, et surtout 100% previsible (contrairement a
# une regle de prompt, qui reste probabiliste avec un petit modele local).
MIN_MESSAGE_LENGTH = 3


def _build_context_message(chart_context: dict, lang: str) -> str:
    """Transforme le contexte envoye par le frontend (graphique actuellement
    affiche + filtres actifs) en un message que le LLM peut lire directement,
    sans avoir besoin d'appeler un outil pour retrouver ces donnees -- elles
    sont deja exactement celles affichees a l'ecran, filtres inclus."""
    title = chart_context.get("chart_title", "un graphique")
    page = chart_context.get("page", "")
    filters = chart_context.get("filters") or {}
    data = chart_context.get("data")
    filters_str = ", ".join(f"{k}={v}" for k, v in filters.items()) if filters else ("none" if lang == "en" else "aucun")

    if lang == "en":
        return (
            f"The user is currently looking at a chart titled '{title}' on the '{page}' page. "
            f"Active filters: {filters_str}. Here is the EXACT data currently displayed (JSON): {data}\n"
            f"Base your answer ONLY on this data -- do not call a tool to re-fetch it, it is already provided above."
        )
    return (
        f"L'utilisateur regarde actuellement un graphique intitule « {title} » sur la page « {page} ». "
        f"Filtres actifs : {filters_str}. Voici les donnees EXACTES actuellement affichees (JSON) : {data}\n"
        f"Base ta reponse UNIQUEMENT sur ces donnees -- n'appelle pas d'outil pour les retrouver, "
        f"elles sont deja fournies ci-dessus."
    )


def run_agent(
    user_message: str,
    chart_context: dict | None = None,
    history: list | None = None,
    model: str = "llama3.1:8b",
    max_iterations: int = 2,
) -> str:
    lang = detect_lang(user_message)
    templates = TEMPLATES_EN if lang == "en" else TEMPLATES_FR

    if len(user_message.strip()) < MIN_MESSAGE_LENGTH and not chart_context:
        return (
            "Could you clarify your question? I can help with sales, forecasts, or customer reviews."
            if lang == "en"
            else "Peux-tu préciser ta question ? Je peux t'aider sur les ventes, les prévisions ou les avis clients."
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    if history:
        for turn in history[-10:]:  # 10 messages = ~5 echanges user/assistant
            role = "user" if turn.get("role") == "user" else "assistant"
            content = turn.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
    if chart_context:
        # Message systeme supplementaire : donne au modele les donnees EXACTES
        # deja affichees a l'ecran, pour une interpretation fidele a ce que
        # l'utilisateur voit reellement (et non une re-derivation approximative).
        messages.append({"role": "system", "content": _build_context_message(chart_context, lang)})
    messages.append({"role": "user", "content": user_message})

    if chart_context:
        # Court-circuite completement l'appel d'outils : les donnees
        # necessaires sont deja dans le message systeme ci-dessus (donnees
        # EXACTES affichees a l'ecran). Passer quand meme TOOLS_SPEC ici
        # laissait le modele appeler un outil (souvent search_reviews /
        # explain_category_complaints) au lieu de lire le contexte fourni,
        # ce qui produisait "Aucun avis client pertinent trouve" sur des
        # questions n'ayant rien a voir avec les avis (ex: "Explique ce
        # graphique", "c'est bon ou pas ce ratio ?").
        response = _ollama_chat(
            model=model,
            messages=messages,
            options={"temperature": 0, "num_predict": 300},
            keep_alive="30m",
        )
        return response["message"]["content"]

    facts = []
    rag_context = ""
    need_rag_synthesis = False
    called_tools = set()

    for iteration in range(max_iterations):
        response = _ollama_chat(
            model=model,
            messages=messages,
            tools=TOOLS_SPEC,
            options={"temperature": 0, "num_predict": 200},
            keep_alive="30m",
        )
        tool_calls = response["message"].get("tool_calls")

        if not tool_calls:
            if iteration == 0:
                return response["message"]["content"]
            break

        messages.append(response["message"])

        for tool_call in tool_calls:
            fn_name = tool_call["function"]["name"]
            fn_args = tool_call["function"]["arguments"]

            call_signature = f"{fn_name}({fn_args})"
            if call_signature in called_tools:
                messages.append(
                    {"role": "tool", "content": "Déjà exécuté précédemment."}
                )
                continue
            called_tools.add(call_signature)

            result = call_tool_safely(fn_name, fn_args)
            print(f"🔧 [{lang}] {fn_name}({fn_args}) → {result}")

            messages.append({"role": "tool", "content": str(result)})

            if isinstance(result, dict) and "error" in result:
                facts.append(
                    f"Une erreur est survenue en récupérant cette information ({fn_name})."
                )
            elif fn_name in ("search_reviews", "explain_category_complaints"):
                need_rag_synthesis = True
                reviews = result.get("retrieved_reviews") or result.get("reviews", [])
                category_matched = result.get("category_matched", True)
                if not reviews:
                    facts.append(
                        "Aucun avis client pertinent trouvé."
                        if lang == "fr"
                        else "No relevant customer reviews found."
                    )
                else:
                    caveat = ""
                    if not category_matched and fn_args.get("category"):
                        caveat = (
                            f" (aucun avis trouve specifiquement pour la categorie "
                            f"'{fn_args.get('category')}' -- avis toutes categories confondues ci-dessous)"
                            if lang == "fr"
                            else f" (no reviews found specifically for category "
                                 f"'{fn_args.get('category')}' -- showing reviews across all categories)"
                        )
                    rag_context += (
                        f"\nReviews found for '{fn_args.get('query', '')}'{caveat}:\n"
                    )
                    for i, rev in enumerate(reviews, 1):
                        rag_context += f'{i}. "{rev}"\n'
            elif fn_name in templates:
                try:
                    facts.append(templates[fn_name](result))
                except Exception as e:
                    print(
                        f"⚠️ Erreur de template pour {fn_name} : {e} | résultat brut : {result}"
                    )
                    facts.append(str(result))
            else:
                facts.append(str(result))

    if need_rag_synthesis and rag_context:
        lang_instruction = (
            "Answer STRICTLY in English. Do not use French."
            if lang == "en"
            else "Réponds STRICTEMENT en français. N'utilise pas l'anglais."
        )
        synthesis_prompt = (
            f'User question: "{user_message}"\n\n'
            f"Relevant customer reviews found (originally in Portuguese):\n{rag_context}\n\n"
            f"Instructions:\n"
            f"1. {lang_instruction}\n"
            f"2. Provide a clear, synthesized business answer — do not translate word-for-word,"
            f" summarize the key points raised by customers."
        )
        synthesis_response = _ollama_chat(
            model=model,
            messages=[{"role": "user", "content": synthesis_prompt}],
            options={"temperature": 0},
            keep_alive="30m",
        )
        facts.append(synthesis_response["message"]["content"])

    return (
        "\n\n".join(facts)
        if facts
        else (
            "I couldn't retrieve the requested information."
            if lang == "en"
            else "Je n'ai pas pu récupérer l'information demandée."
        )
    )