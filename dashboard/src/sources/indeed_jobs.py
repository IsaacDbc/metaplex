"""
Source: Indeed France — offres tech via RSS feed.
Collecte les offres postées ces 14 derniers jours.
"""
import re
import time
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger(__name__)

TECH_KEYWORDS = [
    "data engineer",
    "data scientist",
    "machine learning engineer",
    "software engineer france",
    "développeur python",
    "AI engineer",
    "MLops",
    "data analyst tech",
    "devops france",
    "CTO startup france",
    "backend engineer france",
    "platform engineer",
    "blockchain developer france",
    "ingénieur IA",
    "head of engineering",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def fetch_rss(keyword: str, days: int = 14) -> list[dict]:
    """Fetch Indeed France RSS feed for a keyword."""
    url = "https://fr.indeed.com/rss"
    params = {
        "q": keyword,
        "l": "France",
        "sort": "date",
        "fromage": str(days),
        "lang": "fr",
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            logger.warning(f"[Indeed] HTTP {r.status_code} for '{keyword}'")
            return []

        root = ET.fromstring(r.content)
        jobs = []

        for item in root.findall(".//item"):
            title_raw = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub_date = item.findtext("pubDate", "").strip()

            # Source tag gives company name on Indeed RSS
            source_el = item.find("source")
            company = source_el.text.strip() if source_el is not None and source_el.text else ""

            # Title format: "Job Title - Company - Ville, Région"
            parts = [p.strip() for p in title_raw.split(" - ")]
            job_title = parts[0] if parts else title_raw
            if not company and len(parts) >= 2:
                company = parts[1]
            location = parts[2] if len(parts) >= 3 else "France"

            # Parse publication date
            pub_at = datetime.now().isoformat()
            if pub_date:
                try:
                    pub_at = parsedate_to_datetime(pub_date).isoformat()
                except Exception:
                    pass

            if job_title and company and len(company) > 1:
                jobs.append({
                    "job_title": job_title,
                    "company_name": company,
                    "location": location,
                    "job_url": link,
                    "source": "indeed",
                    "published_at": pub_at,
                })

        logger.info(f"[Indeed] '{keyword}' → {len(jobs)} offres")
        return jobs

    except ET.ParseError:
        logger.warning(f"[Indeed] XML parse error for '{keyword}'")
        return []
    except Exception as e:
        logger.warning(f"[Indeed] Error for '{keyword}': {e}")
        return []


def run() -> list[dict]:
    """Collect tech jobs from Indeed France RSS feeds."""
    all_jobs = []
    seen: set[tuple] = set()

    for kw in TECH_KEYWORDS:
        jobs = fetch_rss(kw, days=14)
        for j in jobs:
            key = (j["company_name"].lower().strip(), j["job_title"].lower().strip())
            if key not in seen:
                seen.add(key)
                all_jobs.append(j)
        time.sleep(1.5)  # be polite

    logger.info(f"[Indeed] Total: {len(all_jobs)} offres uniques")
    return all_jobs
