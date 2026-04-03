"""
Source: ATS (Applicant Tracking Systems) — Greenhouse et Lever.
Collecte les offres tech depuis les APIs publiques des ATS.
Fonctionne pour toutes les boîtes qui utilisent Greenhouse ou Lever.
"""
import re
import time
import json
import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
})

TECH_KW_RE = re.compile(
    r"\b(data engineer|data scientist|machine learning|deep learning|llm|"
    r"software engineer|développeur|ingénieur|devops|sre|platform|cloud|"
    r"backend|frontend|fullstack|mobile|android|ios|"
    r"cto|vp engineering|head of engineering|tech lead|"
    r"python|golang|rust|java|typescript|react|node|"
    r"cybersecurity|blockchain|web3|solidity|"
    r"data analyst|bi engineer|analytics|"
    r"ai|artificial intelligence|mlops)\b",
    re.IGNORECASE,
)

# (company_name, greenhouse_slug, lever_slug)
COMPANIES_ATS = [
    ("Doctolib",           "doctolib",          None),
    ("Dataiku",            "dataiku",            None),
    ("Contentsquare",      "content-square",     "contentsquare"),
    ("Payfit",             None,                 "payfit"),
    ("Pennylane",          "pennylane",          None),
    ("Spendesk",           None,                 "spendesk"),
    ("Qonto",              "qonto",              None),
    ("Alan",               None,                 "alan"),
    ("Back Market",        None,                 "back-market"),
    ("Mirakl",             None,                 "mirakl"),
    ("Swile",              "swile",              None),
    ("360Learning",        "360learning",        "360learning"),
    ("Ledger",             "ledger",             None),
    ("Mistral AI",         "mistralai",          None),
    ("Owkin",              "owkin",              None),
    ("Shine",              None,                 "shine"),
    ("Livestorm",          None,                 "livestorm"),
    ("Brevo",              None,                 "sendinblue"),
    ("Aircall",            "aircall",            None),
    ("Malt",               "malt",               None),
    ("Stuart",             "stuart",             None),
    ("Vestiaire Collective","vestiaire-collective", None),
    ("Vinted",             "vinted",             None),
    ("Leboncoin",          "leboncoin",          None),
    ("Withings",           "withings",           None),
    ("Sopra Steria",       "soprasteria",        None),
    ("Capgemini",          "capgemini",          None),
    ("Alten",              "alten",              None),
    ("Devoteam",           "devoteam",           None),
    ("Wavestone",          "wavestone",          None),
    ("Bioptimus",          None,                 "bioptimus"),
    ("Luko",               None,                 "luko"),
    ("Alma",               None,                 "almapay"),
    ("Agicap",             None,                 "agicap"),
    ("Ringover",           None,                 "ringover"),
    ("Blablacar",          None,                 None),
    ("Teads",              "teads",              None),
    ("Kyriba",             "kyriba",             None),
    ("Nabla",              "nabla",              None),
    ("Yousign",            None,                 None),
]


def _greenhouse_jobs(slug: str, company_name: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false"
    try:
        r = SESSION.get(url, timeout=12)
        if r.status_code != 200:
            return []
        jobs = r.json().get("jobs", [])
    except Exception as e:
        logger.debug(f"[Greenhouse] {slug}: {e}")
        return []

    results = []
    for job in jobs:
        title = job.get("title", "").strip()
        if not TECH_KW_RE.search(title):
            continue
        location = ""
        loc = job.get("location", {})
        if isinstance(loc, dict):
            location = loc.get("name", "")
        results.append({
            "company_name": company_name,
            "job_title": title,
            "location": location or "France",
            "job_url": job.get("absolute_url", ""),
            "source": "greenhouse",
            "published_at": job.get("updated_at", datetime.now().isoformat())[:19],
        })
    return results


def _lever_jobs(slug: str, company_name: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=100"
    try:
        r = SESSION.get(url, timeout=12)
        if r.status_code != 200:
            return []
        jobs = r.json()
        if not isinstance(jobs, list):
            return []
    except Exception as e:
        logger.debug(f"[Lever] {slug}: {e}")
        return []

    results = []
    for job in jobs:
        title = job.get("text", "").strip()
        if not TECH_KW_RE.search(title):
            continue
        location = ""
        locs = job.get("categories", {})
        if isinstance(locs, dict):
            location = locs.get("location", "")
        results.append({
            "company_name": company_name,
            "job_title": title,
            "location": location or "France",
            "job_url": job.get("hostedUrl", ""),
            "source": "lever",
            "published_at": datetime.now().isoformat()[:19],
        })
    return results


def run() -> list[dict]:
    """Collect tech jobs from Greenhouse and Lever APIs."""
    all_jobs = []
    seen: set[tuple] = set()

    for company_name, gh_slug, lever_slug in COMPANIES_ATS:
        jobs = []
        if gh_slug:
            jobs += _greenhouse_jobs(gh_slug, company_name)
            time.sleep(0.4)
        if lever_slug:
            jobs += _lever_jobs(lever_slug, company_name)
            time.sleep(0.4)

        new = 0
        for j in jobs:
            key = (j["company_name"].lower(), j["job_title"].lower())
            if key not in seen:
                seen.add(key)
                all_jobs.append(j)
                new += 1

        if new > 0:
            logger.info(f"[ATS] {company_name}: {new} tech jobs")

    logger.info(f"[ATS] Total: {len(all_jobs)} offres tech")
    return all_jobs
