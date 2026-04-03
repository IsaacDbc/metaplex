# Veille Recrutement Tech 🎯

Tableau de bord de veille automatique pour identifier les startups et scale-ups françaises susceptibles de faire appel à un **cabinet de recrutement tech**.

## Ce que ça fait

| Source | Données collectées | Fréquence |
|--------|-------------------|-----------|
| **RSS** (Maddyness, Frenchweb, Tech.eu…) | Levées de fonds | Toutes les heures |
| **Welcome to the Jungle** | Offres tech actives par entreprise | Toutes les heures |
| **Scoring** | Priorité prospect (0-100) | À chaque refresh |

## Signaux détectés

- 💰 **Levée de fonds récente** → la boîte a du budget pour recruter
- 📈 **Recrutement tech actif** → beaucoup d'offres Data/IA/Soft Eng → possible besoin d'un cabinet
- 🔥 **Les deux** → prospect chaud, à contacter en priorité

## Installation

```bash
cd dashboard
pip install -r requirements.txt
cp .env.example .env
```

## Lancement

```bash
cd src

# Lancer le pipeline une fois (collecte + DB)
python run.py --once

# Lancer le dashboard + auto-refresh toutes les heures
python run.py --dashboard

# Ou séparément :
python run.py --once           # Pipeline
streamlit run dashboard.py     # Dashboard
```

Le dashboard est accessible sur **http://localhost:8501**

## Structure

```
dashboard/
├── src/
│   ├── dashboard.py       # Streamlit app (5 onglets)
│   ├── run.py             # CLI + APScheduler
│   ├── pipeline.py        # Orchestrateur de collecte
│   ├── storage.py         # SQLite (companies, funding, jobs, prospects)
│   ├── scoring.py         # Algorithme de scoring 0-100
│   ├── config.py          # Mots-clés, sources, paramètres
│   └── sources/
│       ├── funding_rss.py  # Veille levées via flux RSS
│       ├── wttj_jobs.py    # Offres tech Welcome to the Jungle
│       └── bpifrance.py    # Maddyness / Frenchweb funding pages
├── data/
│   └── dashboard.db       # SQLite (auto-créé)
├── requirements.txt
└── .env.example
```

## Onglets du dashboard

1. **🎯 Prospects** — liste triée par score avec filtres (signal, score min, période)
2. **💰 Levées de fonds** — timeline des levées + tableau avec liens articles
3. **💼 Offres tech** — top entreprises par volume d'offres + répartition des titres
4. **📋 Suivi CRM** — kanban statuts (nouveau → contacté → deal)
5. **📊 Analytiques** — histogrammes, camemberts, tendances

## Algorithme de scoring (0-100)

| Critère | Points max |
|---------|-----------|
| Levée de fonds récente (< 30 jours) | +45 |
| Montant > 20M€ | +10 |
| > 10 offres tech actives | +20 |
| Poste CTO / Head of Eng ouvert | +10 |
| Taille optimale (51-500 pers.) | +15 |

## Clés API optionnelles (`.env`)

- **`HUNTER_API_KEY`** → trouve les emails pro des contacts identifiés
- **`CRUNCHBASE_API_KEY`** → données de levées plus précises
- **`DEALROOM_API_KEY`** → base startups européennes enrichie
