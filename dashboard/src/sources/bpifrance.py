"""
Source 3 : BPI France & La French Tech — données sur les startups financées.
Scrape les pages publiques de résultats et d'annonces de BPI France.
"""
import re
import time
import logging
from datetime import datetime
from typing import Iterator

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 Chrome/124",
    "Accept-Language": "fr-FR,fr;q=0.9",
})

TECH_KEYWORDS = re.compile(
    r"\b(tech|software|saas|ia\b|ai\b|data|cloud|digital|numérique|"
    r"blockchain|fintech|deeptech|healthtech|edtech|cybersécurité|"
    r"intelligence artificielle|machine learning|plateforme)\b",
    re.IGNORECASE,
)

AMOUNT_RE = re.compile(
    r"(\d+(?:[,\.]\d+)?)\s*(?:millions?|M)\s*(?:d['']euros?|€|\$|euros?|dollars?)?",
    re.IGNORECASE,
)


def scrape_lafrenchtech_120(max_pages: int = 3) -> Iterator[dict]:
    """
    Scrape La French Tech 120 / Next40 programme pages.
    These are curated lists of top French startups.
    """
    urls = [
        "https://lafrenchtech.com/fr/la-france-investit-dans-les-startups/french-tech-120/",
        "https://lafrenchtech.com/fr/la-france-investit-dans-les-startups/french-tech-next40/",
    ]

    for url in urls:
        try:
            r = SESSION.get(url, timeout=12)
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "lxml")
            # Find startup cards/names
            for el in soup.select("[class*='startup'], [class*='company'], h2, h3, li"):
                name = el.get_text(strip=True)
                if name and 3 < len(name) < 60 and not name.startswith(("La ", "Le ", "Les ")):
                    yield {
                        "company_name": name,
                        "source": "french_tech_programme",
                        "signal": "french_tech_label",
                        "published_at": datetime.now().isoformat(),
                    }
        except Exception as e:
            logger.warning(f"La French Tech scrape error: {e}")
        time.sleep(1)


def scrape_frenchweb_funding() -> Iterator[dict]:
    """Scrape Frenchweb funding news page."""
    urls = [
        "https://www.frenchweb.fr/category/levees-de-fonds",
        "https://www.maddyness.com/categorie/levee-de-fonds/",
    ]

    AMOUNT_RE = re.compile(
        r"(\d+(?:[,\.]\d+)?)\s*(?:millions?|M)\s*(?:d['']euros?|€|euros?)",
        re.IGNORECASE,
    )
    ROUND_RE = re.compile(
        r"\b(seed|pré-seed|série\s*[A-E]|series\s*[A-E]|bridge|growth|IPO)\b",
        re.IGNORECASE,
    )

    for url in urls:
        try:
            r = SESSION.get(url, timeout=12)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "lxml")

            # Extract article cards
            articles = soup.select("article, .post, .article-card, [class*='article']")
            for article in articles[:30]:
                title_el = article.select_one("h2, h3, h1, .title")
                link_el = article.select_one("a[href]")
                excerpt_el = article.select_one("p, .excerpt, .description")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                link = link_el.get("href", "") if link_el else ""
                excerpt = excerpt_el.get_text(strip=True) if excerpt_el else ""
                combined = title + " " + excerpt

                # Check if funding article
                if not any(kw in combined.lower() for kw in [
                    "lève", "levée", "financement", "tour de table", "millions"
                ]):
                    continue

                amount_m = 0.0
                am = AMOUNT_RE.search(combined)
                if am:
                    try:
                        amount_m = float(am.group(1).replace(",", "."))
                    except ValueError:
                        pass

                round_type = ""
                rm = ROUND_RE.search(combined)
                if rm:
                    round_type = rm.group(1)

                yield {
                    "company_name": "",  # Will be enriched
                    "amount_m": amount_m,
                    "round_type": round_type,
                    "article_title": title[:200],
                    "article_url": link,
                    "source": url.split("/")[2],
                    "published_at": datetime.now().isoformat(),
                    "is_tech": bool(TECH_KEYWORDS.search(combined)),
                }

        except Exception as e:
            logger.warning(f"Funding scrape error {url}: {e}")
        time.sleep(1.5)


def run() -> Iterator[dict]:
    """Aggregate all BPI/FrenchTech sources."""
    yield from scrape_frenchweb_funding()
