"""
Source 1 : Veille levées de fonds via flux RSS (Maddyness, Frenchweb, Tech.eu, etc.)
Détecte les articles mentionnant des levées de fonds de startups tech françaises.
"""
import re
import logging
from datetime import datetime
from typing import Iterator

import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import FUNDING_RSS_FEEDS, FUNDING_KEYWORDS, TECH_TAGS

logger = logging.getLogger(__name__)

# ─── Extraction du montant ────────────────────────────────────────────────────
AMOUNT_RE = re.compile(
    r"(\d+(?:[,\.]\d+)?)\s*(?:millions?|M)\s*(?:d['']euros?|€|\$|euros?)",
    re.IGNORECASE,
)
AMOUNT_RE2 = re.compile(r"(\d+)\s*M[€$]", re.IGNORECASE)
ROUND_RE = re.compile(
    r"\b(seed|pré-seed|pre-seed|série\s*[A-E]|series\s*[A-E]|serie\s*[A-E]|"
    r"tour\s*de\s*table|bridge|growth|late.stage|IPO|introduction\s*en\s*bourse)\b",
    re.IGNORECASE,
)

# ─── Extraction du nom de la startup ─────────────────────────────────────────
# Patterns communs : "Startup lève X M€", "X millions pour Startup"
COMPANY_FROM_TITLE_RE = [
    re.compile(r"^([A-ZÀ-Ü][A-Za-zÀ-ÿ0-9\.\-]+(?:\s+[A-Za-zÀ-ÿ0-9\.\-]+){0,3})\s+(?:lève|leve|annonce|boucle|finalise|réalise|signe)", re.IGNORECASE),
    re.compile(r"(?:la startup|la scale-up|la fintech|la deeptech|la licorne|l'entreprise|la société)\s+([A-ZÀ-Ü][A-Za-zÀ-ÿ0-9\-\.]+)", re.IGNORECASE),
    re.compile(r"pour\s+([A-ZÀ-Ü][A-Za-zÀ-ÿ0-9\-\.]+)\s*[:,]", re.IGNORECASE),
]

FRENCH_TECH_WORDS = re.compile(
    r"\b(tech|startup|scale.up|fintech|healthtech|edtech|deeptech|saas|"
    r"logiciel|software|data|ia\b|ai\b|intelligence artificielle|"
    r"numérique|digital|cloud|blockchain|cybersécurité|plateforme|marketplace)\b",
    re.IGNORECASE,
)


def extract_amount_m(text: str) -> float:
    """Extract funding amount in millions €."""
    for pattern in [AMOUNT_RE, AMOUNT_RE2]:
        m = pattern.search(text)
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except ValueError:
                pass
    return 0.0


def extract_round_type(text: str) -> str:
    m = ROUND_RE.search(text)
    return m.group(1).title() if m else "Inconnu"


def extract_company_from_title(title: str) -> str:
    for pattern in COMPANY_FROM_TITLE_RE:
        m = pattern.search(title)
        if m:
            return m.group(1).strip()
    return ""


def is_funding_article(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in [
        "lève", "levée", "levee", "funding", "raises", "tour de table",
        "financement", "investissement", "series a", "series b", "série",
        "seed", "venture", "capital", "millions d'euros", "m€",
    ])


def is_tech_related(title: str, summary: str) -> bool:
    text = title + " " + summary
    return bool(FRENCH_TECH_WORDS.search(text))


def parse_date(date_str: str) -> str:
    """Parse RSS date string to ISO format."""
    if not date_str:
        return datetime.now().isoformat()
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).isoformat()
    except Exception:
        return datetime.now().isoformat()


def fetch_rss(url: str) -> list[dict]:
    """Fetch and parse an RSS feed using stdlib xml parser."""
    try:
        r = requests.get(url, timeout=12, headers={
            "User-Agent": "Mozilla/5.0 Chrome/124",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        })
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = []

        # RSS 2.0
        for item in root.findall(".//item"):
            def t(tag):
                el = item.find(tag)
                return el.text.strip() if el is not None and el.text else ""
            entries.append({
                "title": t("title"),
                "summary": t("description"),
                "link": t("link"),
                "published": parse_date(t("pubDate")),
            })

        # Atom
        for item in root.findall(".//atom:entry", ns):
            def ta(tag):
                el = item.find(f"atom:{tag}", ns)
                return (el.text or "").strip() if el is not None else ""
            link_el = item.find("atom:link", ns)
            href = link_el.get("href", "") if link_el is not None else ""
            entries.append({
                "title": ta("title"),
                "summary": ta("summary") or ta("content"),
                "link": href,
                "published": parse_date(ta("updated") or ta("published")),
            })
        return entries
    except Exception as e:
        logger.warning(f"RSS parse error {url}: {e}")
        return []


def scrape_article_details(url: str) -> dict:
    """Fetch article body for more details (company name, amount, etc.)."""
    try:
        r = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 Chrome/124",
            "Accept-Language": "fr-FR,fr;q=0.9",
        })
        soup = BeautifulSoup(r.text, "lxml")
        # Get main article text
        for tag in soup.find_all(["script", "style", "nav", "footer"]):
            tag.decompose()
        body = soup.get_text(separator=" ", strip=True)
        return {
            "amount_m": extract_amount_m(body),
            "round_type": extract_round_type(body),
            "company_name": extract_company_from_title(soup.title.get_text() if soup.title else ""),
            "body_preview": body[:500],
        }
    except Exception:
        return {}


def run() -> Iterator[dict]:
    """
    Fetch all funding RSS feeds and yield funding event dicts.
    """
    for source_name, feed_url in FUNDING_RSS_FEEDS:
        logger.info(f"Fetching RSS: {source_name}")
        entries = fetch_rss(feed_url)

        for entry in entries:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            url = entry.get("link", "")
            published = entry.get("published", datetime.now().isoformat())

            if not is_funding_article(title, summary):
                continue
            if not is_tech_related(title, summary):
                continue

            amount_m = extract_amount_m(title + " " + summary)
            round_type = extract_round_type(title + " " + summary)
            company_name = extract_company_from_title(title)

            yield {
                "company_name": company_name,
                "amount_m": amount_m,
                "round_type": round_type,
                "article_title": title[:200],
                "article_url": url,
                "article_summary": summary[:500],
                "source": source_name,
                "published_at": published,
            }
