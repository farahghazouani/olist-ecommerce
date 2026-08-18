# Backend - Agent Conversationnel BI & Plateforme Analytics (Olist E-Commerce)

Ce dépôt contient la partie **Backend** de la plateforme de Business Intelligence (BI) et d'analyse prédictive pour le marketplace **Olist**. 

Le cœur du système repose sur un **Agent IA local (LLM Ollama Llama 3.1 8B)** capable de réaliser du *Function Calling* (appel d'outils analytiques), du *RAG* (synthèse d'avis clients) et de lire dynamiquement le contexte des graphiques du Dashboard.

---

## Architecture du Projet

Le projet suit une architecture modulaire et scalable basée sur **Flask** et **Python 3.13** :

```text
ecommerceolist_backend/
└── backend/
    ├── app/
    │   ├── agent/                 # Orchestration de l'Agent IA (LLM)
    │   │   ├── __init__.py
    │   │   ├── agent.py          # Boucle principale, gestion des prompts, templates & lock Thread
    │   │   └── tools.py          # Définition et exécution des fonctions métiers (Function Calling)
    │   ├── rag/                   # Module de recherche vectorielle / avis clients
    │   │   └── ...               # Moteur RAG pour les retours utilisateurs
    │   ├── routers/               # Endpoints REST API (Flask Blueprints)
    │   │   ├── __init__.py
    │   │   ├── chat.py           # API /api/chat pour l'agent conversationnel
    │   │   ├── customers.py      # API segmentation clients (RFM)
    │   │   ├── kpi.py            # API pour les métriques de ventes & CA
    │   │   └── ml.py             # API pour les prévisions & modèles de risque
    │   ├── main.py               # Point d'entrée Flask & enregistrement des routes
    │   └── load_data.py          # Scripts d'initialisation de la base de données
    ├── tests/
    │   └── test_chatbot_scenarios.py # Script d'évaluation automatique (27 scénarios BI)
    └── requirements.txt
