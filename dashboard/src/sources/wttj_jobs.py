"""
Source 2 : Welcome to the Jungle — offres d'emploi tech en France.
Détecte les boîtes qui recrutent massivement en tech (Data, IA, Soft Eng, Blockchain…)
et qui sont donc susceptibles de faire appel à un cabinet de recrutement.
"""
import re
import json
import time
import logging
from datetime import datetime
from typing import Iterator
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import TECH_ROLES, TECH_TAGS, TARGET_REGIONS

logger = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
})

# ─── WTTJ Algolia search (clés publiques embarquées dans le site) ─────────────
WTTJ_ALGOLIA_APP = "O9ZUQGVHUL"      # App ID public WTTJ
WTTJ_ALGOLIA_KEY = "4fcb7d50f4e12a1c8e1b83cbfa8e2eed"  # Search-only public key
WTTJ_ALGOLIA_INDEX = "wttj_jobs_production_en"
WTTJ_ALGOLIA_URL = f"https://{WTTJ_ALGOLIA_APP}-dsn.algolia.net/1/indexes/{WTTJ_ALGOLIA_INDEX}/query"

TECH_KW_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in TECH_TAGS + [
        "engineer", "developer", "développeur", "ingénieur",
        "data", "machine learning", "deep learning", "llm", "gpt",
        "blockchain", "web3", "solidity", "crypto",
        "devops", "sre", "platform", "cloud", "aws", "gcp", "azure",
        "cto", "vp engineering", "head of engineering",
        "python", "rust", "golang", "java", "typescript", "react", "node",
        "android", "ios", "mobile", "flutter",
        "cybersecurity", "security", "siem", "soc",
    ]) + r")\b",
    re.IGNORECASE,
)


def algolia_search(query: str, page: int = 0, hits_per_page: int = 50) -> dict:
    """Query WTTJ Algolia index."""
    payload = {
        "query": query,
        "hitsPerPage": hits_per_page,
        "page": page,
        "filters": "published:true AND office.country_code:FR",
        "attributesToRetrieve": [
            "name", "slug", "company.name", "company.slug", "company.size",
            "company.sector", "company.description", "contract_type",
            "office.city", "office.country", "published_at",
            "tags", "department", "profession", "salary_min", "salary_max",
        ],
    }
    headers = {
        "X-Algolia-Application-Id": WTTJ_ALGOLIA_APP,
        "X-Algolia-API-Key": WTTJ_ALGOLIA_KEY,
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(WTTJ_ALGOLIA_URL, json=payload, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json()
        else:
            logger.warning(f"Algolia error {r.status_code}")
            return {}
    except Exception as e:
        logger.warning(f"Algolia request failed: {e}")
        return {}


def scrape_wttj_html_search(query: str, page: int = 1) -> list[dict]:
    """Fallback: scrape WTTJ job search HTML page."""
    url = (
        f"https://www.welcometothejungle.com/fr/jobs"
        f"?query={quote_plus(query)}"
        f"&page={page}"
        f"&aroundQuery=France"
        f"&refinementList%5Boffice.country_code%5D%5B%5D=FR"
    )
    r = SESSION.get(url, timeout=15)
    if r.status_code != 200:
        return []

    soup = BeautifulSoup(r.text, "lxml")
    jobs = []

    # Extract job cards
    for card in soup.select("li[data-role='job-item'], article, [class*='sc-']"):
        title_el = card.select_one("h2, h3, [class*='title']")
        company_el = card.select_one("[class*='company'], [class*='organization']")
        link_el = card.select_one("a[href]")

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        company = company_el.get_text(strip=True) if company_el else ""
        href = link_el["href"] if link_el else ""

        if title and any(re.search(kw, title, re.IGNORECASE) for kw in TECH_TAGS[:20]):
            jobs.append({
                "job_title": title,
                "company_name": company,
                "job_url": f"https://www.welcometothejungle.com{href}" if href.startswith("/") else href,
                "source": "wttj_html",
            })

    return jobs


def parse_algolia_hit(hit: dict) -> dict:
    """Extract job data from an Algolia hit."""
    company = hit.get("company", {}) or {}
    office = hit.get("office", {}) or {}
    tags = hit.get("tags", []) or []
    tag_names = [t.get("name", "") for t in tags if isinstance(t, dict)]

    return {
        "job_title": hit.get("name", ""),
        "company_name": company.get("name", ""),
        "company_slug": company.get("slug", ""),
        "company_size": company.get("size", ""),
        "company_sector": company.get("sector", ""),
        "company_description": (company.get("description", "") or "")[:300],
        "location": office.get("city", ""),
        "tech_tags": json.dumps(tag_names),
        "job_url": f"https://www.welcometothejungle.com/fr/companies/{company.get('slug','')}/jobs/{hit.get('slug','')}",
        "source": "wttj_algolia",
        "published_at": hit.get("published_at", ""),
    }


def scrape_wttj_jobs_page(query: str, page: int = 1) -> list[dict]:
    """Scrape WTTJ HTML job search results."""
    from urllib.parse import quote_plus
    url = (
        f"https://www.welcometothejungle.com/fr/jobs"
        f"?query={quote_plus(query)}&page={page}"
        f"&aroundQuery=France"
        f"&refinementList%5Boffice.country_code%5D%5B%5D=FR"
    )
    try:
        r = SESSION.get(url, timeout=15)
        if r.status_code != 200:
            return []
    except Exception as e:
        logger.warning(f"WTTJ HTML error: {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")
    jobs = []

    # WTTJ uses React with data embedded in <script> tags
    # Try to extract from JSON-LD or structured data
    for sc in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(sc.string or "")
            if isinstance(data, dict) and data.get("@type") == "JobPosting":
                company = data.get("hiringOrganization", {})
                jobs.append({
                    "job_title": data.get("title", ""),
                    "company_name": company.get("name", "") if isinstance(company, dict) else "",
                    "company_slug": "",
                    "company_size": "",
                    "company_sector": "",
                    "company_description": "",
                    "location": data.get("jobLocation", {}).get("address", {}).get("addressLocality", "") if isinstance(data.get("jobLocation"), dict) else "",
                    "tech_tags": "[]",
                    "job_url": data.get("url", ""),
                    "source": "wttj_html",
                    "published_at": data.get("datePosted", ""),
                })
        except Exception:
            pass

    # Fallback: parse visible card elements
    if not jobs:
        for article in soup.select("li[data-testid], article, [class*='ais-Hits']"):
            h3 = article.select_one("h3, h2, [class*='title']")
            company_el = article.select_one("[class*='company'], [class*='organization'], span + span")
            link = article.select_one("a[href*='/jobs/']")
            if not h3:
                continue
            title = h3.get_text(strip=True)
            if not TECH_KW_RE.search(title):
                continue
            jobs.append({
                "job_title": title,
                "company_name": company_el.get_text(strip=True) if company_el else "",
                "company_slug": "",
                "company_size": "",
                "company_sector": "",
                "company_description": "",
                "location": "France",
                "tech_tags": "[]",
                "job_url": ("https://www.welcometothejungle.com" + link["href"]) if link else "",
                "source": "wttj_html",
                "published_at": datetime.now().isoformat(),
            })

    return jobs


KNOWN_COMPANIES = [
    ("Doctolib", "doctolib"), ("Payfit", "payfit"), ("Qonto", "qonto"),
    ("Alan", "alan"), ("Spendesk", "spendesk"), ("Brevo", "brevo"),
    ("Aircall", "aircall"), ("Swile", "swile"), ("Malt", "malt"),
    ("360Learning", "360learning"), ("Mirakl", "mirakl"), ("Back Market", "back-market"),
    ("Teads", "teads"), ("Kyriba", "kyriba"), ("Mistral AI", "mistral-ai"),
    ("Owkin", "owkin"), ("Ledger", "ledger-hq"), ("Contentsquare", "contentsquare"),
    ("Dataiku", "dataiku"), ("Pennylane", "pennylane"), ("Shine", "shine"),
    ("Luko", "luko"), ("Livestorm", "livestorm"), ("Stuart", "stuart"),
    ("Convelio", "convelio"), ("Blablacar", "blablacar"), ("OVHcloud", "ovhcloud"),
    ("Withings", "withings"), ("Agicap", "agicap"), ("Yousign", "yousign"),
    ("Deepki", "deepki"), ("Alma", "alma"), ("Comet", "comet-network"),
    ("Theodo", "theodo"), ("Lucca", "lucca-software"), ("Sekoia", "sekoia-io"),
    ("Vestiaire Collective", "vestiaire-collective"), ("Vinted", "vinted"),
    ("Leboncoin", "leboncoin"), ("Bioptimus", "bioptimus"), ("LegalPlace", "legalplace"),
    ("Doctrine", "doctrine"), ("Inato", "inato"), ("Nabla", "nabla"),
    ("Sopra Steria", "sopra-steria"), ("Capgemini", "capgemini"),
    ("Wavestone", "wavestone"), ("Devoteam", "devoteam"),
    ("Younited Credit", "younited-credit"), ("Ringover", "ringover"),
    ("Dougs", "dougs"), ("Brigad", "brigad"), ("Gymlib", "gymlib"),
    ("Javelo", "javelo"), ("Elevo", "elevo-app"), ("Indy", "indy"),
    ("Crisp", "crisp-im"), ("Modjo", "modjo-ai"), ("Slite", "slite"),
    ("Leocare", "leocare"), ("Maki People", "maki-people"),
    ("Lydia", "lydia-solutions"), ("Scaleway", "scaleway"),
    ("Meero", "meero"), ("Klaxoon", "klaxoon"), ("Joko", "joko-app"),
    ("Worklife", "worklife"), ("Talent.io", "talent-io"),
    ("Welcome to the Jungle", "welcometothejungle"),
    ("Pigment", "pigment"), ("Pennylane", "pennylane"),
    ("Photoroom", "photoroom"), ("Lifen", "lifen"),
    ("Synapse Medicine", "synapse-medicine"), ("Edenred", "edenred"),
    ("Comet", "comet-network"), ("Mirakl", "mirakl"),
    ("Iziwork", "iziwork"), ("Hivebrite", "hivebrite"),
    ("Spendesk", "spendesk"), ("Bankin", "bankin"),
]


def scrape_company_jobs(company_name: str, slug: str) -> list[dict]:
    """Scrape a WTTJ company jobs page (server-rendered)."""
    url = f"https://www.welcometothejungle.com/fr/companies/{slug}/jobs"
    try:
        r = SESSION.get(url, timeout=12)
        if r.status_code != 200:
            return []
    except Exception as e:
        logger.warning(f"WTTJ {slug}: {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")
    jobs = []

    # Extract job titles from links matching /jobs/ pattern
    job_links = soup.find_all("a", href=re.compile(r"/fr/companies/.+/jobs/.+"))
    for a in job_links:
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if not title or len(title) < 4:
            continue
        # Deduplicate by href
        full_url = f"https://www.welcometothejungle.com{href}"
        jobs.append({
            "job_title": title,
            "company_name": company_name,
            "company_slug": slug,
            "company_size": "",
            "company_sector": "",
            "company_description": "",
            "location": "France",
            "tech_tags": "[]",
            "job_url": full_url,
            "source": "wttj_company",
            "published_at": datetime.now().isoformat(),
        })

    # Deduplicate by URL
    seen_urls = set()
    unique = []
    for j in jobs:
        if j["job_url"] not in seen_urls:
            seen_urls.add(j["job_url"])
            unique.append(j)

    return unique


def run(max_pages: int = 5) -> Iterator[dict]:
    """
    Search WTTJ for tech job listings in France.
    Tries Algolia first, falls back to HTML scraping.
    """
    seen = set()

    # Scrape known companies' job pages directly (server-rendered, works reliably)
    for company_name, slug in KNOWN_COMPANIES:
        logger.info(f"WTTJ jobs: {company_name}")
        jobs = scrape_company_jobs(company_name, slug)
        tech_jobs = [j for j in jobs if TECH_KW_RE.search(j["job_title"])]
        for job in tech_jobs:
            key = f"{job['company_name']}|{job['job_title']}"
            if key not in seen:
                seen.add(key)
                yield job
        if tech_jobs:
            logger.info(f"  → {len(tech_jobs)} offres tech sur {len(jobs)} total")
        time.sleep(0.8)


def get_company_tech_jobs_count(company_slug: str) -> int:
    """Get the count of active tech job listings for a company."""
    data = algolia_search(company_slug, hits_per_page=100)
    if not data:
        return 0
    return data.get("nbHits", 0)
