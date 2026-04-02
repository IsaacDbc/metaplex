"""
Configuration: target roles, industries, and search parameters.
"""

# Job titles to search for
TARGET_ROLES = [
    "DRH",
    "Directeur des Ressources Humaines",
    "Head of Talent",
    "Head of Talent Acquisition",
    "Head of Recruitment",
    "Talent Acquisition Manager",
    "Head of People",
    "Chief People Officer",
    "VP People",
    "VP HR",
    "Head of HR",
    "Head of Procurement",
    "Chief Human Resources Officer",
    "CHRO",
    "Responsable RH",
    "Directeur RH",
    "Talent Manager",
    "Head of Engineering Recruitment",
]

# Industries / company types that hire tech talent
TARGET_INDUSTRIES = [
    "startup tech",
    "SaaS",
    "fintech",
    "ESN",
    "SSII",
    "cabinet de recrutement tech",
    "scale-up",
    "unicorn",
    "deep tech",
    "software company",
    "e-commerce",
    "marketplace",
    "cybersecurity",
    "cloud computing",
    "AI startup",
]

# Countries/regions to target
TARGET_REGIONS = [
    "France",
    "Paris",
    "Lyon",
    "Bordeaux",
    "Toulouse",
    "Nantes",
    "Lille",
    "Marseille",
]

# Patterns to detect emails in raw text
EMAIL_PATTERNS = [
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
]

# Patterns to detect French phone numbers
PHONE_PATTERNS = [
    r"(?:(?:\+|00)33|0)\s*[1-9](?:[\s.\-]*\d{2}){4}",  # French format
    r"\+\d{1,3}[\s.\-]?\(?\d{1,4}\)?[\s.\-]?\d{1,4}[\s.\-]?\d{1,9}",  # International
]

# LinkedIn search URL template (via Google dork)
GOOGLE_LINKEDIN_DORK = 'site:linkedin.com/in "{role}" "{region}" email'

# Request settings
REQUEST_DELAY_MIN = 2.0  # seconds between requests
REQUEST_DELAY_MAX = 5.0

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]
