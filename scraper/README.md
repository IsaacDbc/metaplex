# Recruiter Contact Scraper

Scraper Python pour trouver les contacts RH (DRH, Head of Talent, Head of Procurement, etc.) dans les boîtes tech qui recrutent.

## Sources de données

| Source | Données récupérées | Prérequis |
|--------|-------------------|-----------|
| **Google/Bing** | Emails, téléphones depuis pages publiques | Aucun (ou clé API Bing optionnelle) |
| **LinkedIn** | Noms, titres, profils | Cookie `li_at` LinkedIn |
| **Hunter.io** | Emails professionnels vérifiés | Clé API Hunter.io (gratuit: 25/mois) |
| **Sites entreprises** | Emails/téléphones depuis pages /team, /about | Aucun |

## Installation

```bash
cd scraper
pip install -r requirements.txt
cp .env.example .env
# Editer .env avec vos clés API
```

## Utilisation

### Recherche basique (pas de clés API nécessaires)
```bash
cd src
python main.py \
  --roles "Head of Talent" "DRH" "Responsable RH" \
  --regions "Paris" "Lyon" \
  --industries "startup tech" "SaaS" "fintech"
```

### Avec Hunter.io (meilleure qualité d'emails)
```bash
# Renseigner HUNTER_API_KEY dans .env, puis:
python main.py \
  --hunter-domains stripe.com doctolib.fr contentsquare.com dataiku.com \
  --roles "Head of Talent" "DRH"
```

### Scraper les sites web d'entreprises spécifiques
```bash
python main.py \
  --company-urls https://www.contentsquare.com https://www.dataiku.com https://www.doctrine.fr \
  --no-google --no-linkedin
```

### Pipeline complet avec enrichissement
```bash
python main.py \
  --roles "Head of Talent" "DRH" "CHRO" \
  --regions "Paris" "France" \
  --industries "startup tech" "SaaS" "fintech" \
  --hunter-domains doctolib.fr contentsquare.com \
  --company-urls https://www.payfit.com https://www.pennylane.com \
  --enrich \
  --min-score 0.3 \
  --output mes_contacts.csv \
  --json \
  -v
```

### Toutes les options
```
--roles ROLE [ROLE ...]         Titres de postes à chercher
--regions REGION [REGION ...]   Régions géographiques
--industries INDUSTRY [...]     Secteurs d'activité
--no-google                     Désactiver la recherche Google/Bing
--no-linkedin                   Désactiver le scraper LinkedIn
--hunter-domains DOMAIN [...]   Domaines à chercher sur Hunter.io
--company-urls URL [...]        URLs d'entreprises à scraper
--enrich                        Enrichir avec Hunter.io email finder
--output FILENAME               Nom du fichier CSV de sortie
--output-dir DIR                Dossier de sortie (défaut: ./output)
--json                          Exporter aussi en JSON
--min-score 0.0-1.0             Score minimum de confiance
--proxy URL                     Proxy HTTP (ex: http://user:pass@host:port)
--max-pages N                   Pages max LinkedIn par requête
-v, --verbose                   Logs détaillés
```

## Configuration des clés API

Copier `.env.example` vers `.env` et remplir :

```ini
# Hunter.io — 25 recherches/mois gratuites
HUNTER_API_KEY=votre_cle_ici

# Bing Search API — optionnel, améliore les recherches web
BING_API_KEY=votre_cle_ici

# LinkedIn — cookie de session (récupéré dans le navigateur)
# DevTools → Application → Cookies → li_at
LINKEDIN_LI_AT=votre_cookie_ici
```

## Format de sortie (CSV)

| Colonne | Description |
|---------|-------------|
| `full_name` | Nom complet |
| `first_name` / `last_name` | Prénom / Nom |
| `job_title` | Titre du poste |
| `company` | Entreprise |
| `company_website` | Site web |
| `email` | Email professionnel |
| `phone` | Téléphone |
| `linkedin_url` | Profil LinkedIn |
| `location` | Localisation |
| `source` | Source du contact |
| `confidence_score` | Score 0-1 (qualité des données) |
| `scraped_at` | Date de collecte |

## Architecture

```
scraper/
├── src/
│   ├── main.py              # Point d'entrée CLI
│   ├── config.py            # Rôles, régions, secteurs cibles
│   ├── models.py            # Modèle Contact
│   ├── utils.py             # HTTP session, extraction regex, dédup
│   ├── export.py            # Export CSV/JSON
│   └── scrapers/
│       ├── google_search.py  # Recherche Google/Bing + scraping pages
│       ├── linkedin_scraper.py # LinkedIn people search
│       ├── hunter_io.py      # Hunter.io API
│       └── company_websites.py # Scraping sites entreprises
├── output/                  # Fichiers générés
├── requirements.txt
└── .env.example
```

## Limitations & bonnes pratiques

- **Respect des ToS** : LinkedIn interdit le scraping. Utiliser avec modération.
- **Rate limiting** : Des délais aléatoires (2-5s) sont intégrés entre les requêtes.
- **RGPD** : Les données collectées sont des données personnelles professionnelles. Respecter la réglementation applicable.
- **Qualité** : Utiliser `--min-score 0.3` pour ne garder que les contacts avec email ou LinkedIn.
