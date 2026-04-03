"""
Configuration : secteurs tech, mots-clés, sources de données.
"""

# ─── Mots-clés tech qui indiquent un besoin de recrutement ───────────────────
TECH_ROLES = [
    # Engineering
    "Software Engineer", "Développeur", "Ingénieur Logiciel",
    "Backend", "Frontend", "Full Stack", "Fullstack",
    "DevOps", "SRE", "Platform Engineer", "Infrastructure",
    # Data / AI
    "Data Engineer", "Data Scientist", "ML Engineer",
    "Machine Learning", "Deep Learning", "NLP", "LLM",
    "AI Engineer", "Intelligence Artificielle", "Data Analyst",
    "Data Architect", "Data Platform",
    # Management tech
    "CTO", "VP Engineering", "Head of Engineering",
    "Engineering Manager", "Tech Lead", "Lead Developer",
    # Blockchain / Web3
    "Blockchain", "Smart Contract", "Web3", "Solidity",
    "Crypto", "DeFi",
    # Product / Design
    "Product Manager", "CPO", "Product Lead",
    # Security
    "Cybersecurity", "Security Engineer", "CISO",
    # Cloud
    "Cloud Architect", "AWS", "GCP", "Azure",
]

TECH_TAGS = [
    "software", "data", "ia", "ai", "machine learning", "deep learning",
    "blockchain", "web3", "cloud", "devops", "python", "react", "node",
    "backend", "frontend", "fullstack", "mobile", "android", "ios",
    "cybersecurity", "infrastructure", "platform", "mlops", "llm",
]

# ─── Sources RSS levées de fonds France ──────────────────────────────────────
FUNDING_RSS_FEEDS = [
    ("Maddyness", "https://www.maddyness.com/feed/"),
    ("Frenchweb", "https://www.frenchweb.fr/feed"),
    ("BFM Business Tech", "https://www.bfmtv.com/tech/rss/news/"),
    ("Tech.eu France", "https://tech.eu/tag/france/feed/"),
    ("Sifted", "https://sifted.eu/feed/"),
    ("Les Echos Start", "https://start.lesechos.fr/feed"),
    ("Journal du Net Startups", "https://www.journaldunet.com/rss.xml"),
    ("Usine Digitale", "https://www.usine-digitale.fr/rss/toutes-les-actualites.xml"),
]

FUNDING_KEYWORDS = [
    "lève", "levée", "levee", "funding", "raise", "series", "seed",
    "tour de table", "financement", "investissement", "million",
    "millions d'euros", "M€", "M$", "venture", "capital-risque",
]

# ─── WTTJ tech categories ─────────────────────────────────────────────────────
WTTJ_TECH_CATEGORIES = [
    "engineering",
    "data",
    "product",
    "design",
    "cybersecurity",
]

WTTJ_TECH_TAGS = [
    "software-development",
    "data-engineering",
    "machine-learning",
    "artificial-intelligence",
    "blockchain",
    "cloud",
    "devops",
    "cybersecurity",
    "mobile-development",
    "backend",
    "frontend",
]

# ─── Seuil de score pour dashboard ──────────────────────────────────────────
MIN_TECH_JOBS_THRESHOLD = 3      # Min offres tech pour être affiché
MIN_FUNDING_AMOUNT_M = 1         # Min 1M€ pour être pertinent

# ─── Régions cibles ──────────────────────────────────────────────────────────
TARGET_REGIONS = ["France", "Paris", "Lyon", "Bordeaux", "Toulouse",
                  "Nantes", "Lille", "Marseille", "Grenoble", "Strasbourg"]

# ─── Taille d'entreprise cible pour cabinet de recrutement ──────────────────
# (les boîtes de 10-500 pers. font souvent appel à des cabinets)
TARGET_SIZE_MIN = 10
TARGET_SIZE_MAX = 5000

# ─── Refresh interval (minutes) ──────────────────────────────────────────────
REFRESH_INTERVAL_MINUTES = 60
