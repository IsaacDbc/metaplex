"""
Source: Cadremploi — offres cadres tech en France.
Utilise l'API interne de carriere.fcms.io (clé publique embarquée dans le site).
"""
import re
import time
import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

CE_SEARCH_API = "https://ce-search-api.carriere.fcms.io/search"
CE_API_KEY = "AIzaSyBzIZ0NDDa-ey8Qg9U28OC1ud9JwRLPYEY"

TECH_KEYWORDS = [
    "ingénieur data",
    "développeur python",
    "développeur java",
    "développeur fullstack",
    "développeur backend",
    "machine learning",
    "intelligence artificielle",
    "data analyst",
    "devops",
    "cloud",
    "CTO",
    "directeur technique",
    "tech lead",
    "cybersécurité",
    "blockchain",
    "architecte logiciel",
    "ingénieur logiciel",
    "data science",
]

# Filter titles that are actually tech-related
TECH_TITLE_RE = re.compile(
    r"\b(data|python|java|javascript|typescript|react|angular|node|"
    r"devops|cloud|aws|gcp|azure|kubernetes|docker|"
    r"machine learning|deep learning|ia|intelligence artificielle|llm|"
    r"blockchain|solidity|web3|"
    r"cto|directeur technique|tech lead|vp engineering|head of engineering|"
    r"développeur|ingénieur (logiciel|data|cloud|sécurité|système)|"
    r"fullstack|backend|frontend|mobile|android|ios|"
    r"cybersécurité|sécurité informatique|siem|pentest|"
    r"architecte (logiciel|cloud|data|solution)|"
    r"data scientist|data engineer|data analyst|bi engineer|"
    r"platform engineer|sre|site reliability)\b",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://www.cadremploi.fr",
    "Referer": "https://www.cadremploi.fr/",
    "x-api-key": CE_API_KEY,
}


def search_cadremploi(keyword: str, page: int = 0, size: int = 50) -> list[dict]:
    """Search Cadremploi via internal API."""
    params = {
        "q": keyword,
        "site": "cadremploi",
        "page": page,
        "size": size,
    }
    try:
        r = requests.get(CE_SEARCH_API, params=params, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            logger.warning(f"[Cadremploi] HTTP {r.status_code} for '{keyword}'")
            return []

        data = r.json()
        items = data.get("data", [])
        jobs = []

        for item in items:
            titre = item.get("titre", "").strip()
            company = item.get("raisonSociale", "").strip()
            date_pub = item.get("datePublication", "")
            lien = item.get("lien", "")
            localisation = item.get("localisation", "France")

            if not titre or not company:
                continue
            # Filter: keep only tech jobs
            if not TECH_TITLE_RE.search(titre):
                continue

            # Parse ISO date
            pub_at = datetime.now().isoformat()
            if date_pub:
                try:
                    pub_at = datetime.fromisoformat(
                        date_pub.replace("Z", "+00:00").split("+")[0]
                    ).isoformat()
                except Exception:
                    pass

            jobs.append({
                "job_title": titre,
                "company_name": company,
                "location": localisation,
                "job_url": lien,
                "source": "cadremploi",
                "published_at": pub_at,
            })

        logger.info(f"[Cadremploi] '{keyword}' → {len(jobs)} offres")
        return jobs

    except Exception as e:
        logger.warning(f"[Cadremploi] Error for '{keyword}': {e}")
        return []


def run() -> list[dict]:
    """Collect tech jobs from Cadremploi."""
    all_jobs = []
    seen: set[tuple] = set()

    for kw in TECH_KEYWORDS:
        jobs = search_cadremploi(kw)
        for j in jobs:
            key = (j["company_name"].lower().strip(), j["job_title"].lower().strip())
            if key not in seen:
                seen.add(key)
                all_jobs.append(j)
        time.sleep(0.8)

    logger.info(f"[Cadremploi] Total: {len(all_jobs)} offres uniques")
    return all_jobs
