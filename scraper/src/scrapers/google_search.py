"""
Google/Bing search scraper.
Searches for recruiter contacts using advanced search operators (dorks).
"""
import os
import logging
import urllib.parse
from typing import Iterator

import requests
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import make_session, polite_sleep, safe_get, extract_emails, extract_phones
from models import Contact

logger = logging.getLogger(__name__)

BING_API_ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"


def build_search_queries(role: str, region: str, industry: str = "") -> list[str]:
    """Build a set of targeted search queries for a given role."""
    queries = []

    # Direct contact search
    queries.append(f'"{role}" {region} email contact')
    queries.append(f'"{role}" {region} "contact" site:linkedin.com/in')

    if industry:
        queries.append(f'"{role}" "{industry}" {region} email')

    # Company team pages
    queries.append(f'"{role}" {region} "notre équipe" OR "meet the team" email')

    # Press releases / interviews
    queries.append(f'"{role}" {region} interview recrutement tech contact')

    return queries


def search_bing_api(query: str, api_key: str, count: int = 10) -> list[dict]:
    """Use Bing Search API (requires key)."""
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {"q": query, "count": count, "mkt": "fr-FR"}
    try:
        resp = requests.get(BING_API_ENDPOINT, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("webPages", {}).get("value", [])
        return [{"url": r["url"], "title": r["name"], "snippet": r["snippet"]} for r in results]
    except Exception as e:
        logger.error(f"Bing API error: {e}")
        return []


def search_bing_html(query: str, session: requests.Session) -> list[dict]:
    """Scrape Bing search results (no API key needed)."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.bing.com/search?q={encoded}&count=20&setlang=fr"
    resp = safe_get(session, url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    results = []
    for li in soup.select("li.b_algo"):
        a_tag = li.select_one("h2 a")
        snippet_tag = li.select_one(".b_caption p")
        if a_tag:
            results.append({
                "url": a_tag.get("href", ""),
                "title": a_tag.get_text(strip=True),
                "snippet": snippet_tag.get_text(strip=True) if snippet_tag else "",
            })
    return results


def scrape_page_for_contacts(url: str, session: requests.Session, role: str, company_hint: str = "") -> list[Contact]:
    """Visit a page and extract contact information."""
    resp = safe_get(session, url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    text = soup.get_text(separator=" ")

    emails = extract_emails(text)
    phones = extract_phones(text)

    # Try to extract name from page title or meta
    name = ""
    title_tag = soup.find("title")
    if title_tag:
        name = title_tag.get_text(strip=True).split("|")[0].strip()

    contacts = []
    if emails or phones:
        c = Contact(
            full_name=name,
            job_title=role,
            company=company_hint,
            email=emails[0] if emails else "",
            phone=phones[0] if phones else "",
            linkedin_url=url if "linkedin.com" in url else "",
            source=url,
        )
        c.compute_score()
        contacts.append(c)

    return contacts


def run(roles: list[str], regions: list[str], industries: list[str], proxy: str = None) -> Iterator[Contact]:
    """
    Main entry point: search for contacts matching given roles/regions.
    Yields Contact objects.
    """
    bing_api_key = os.getenv("BING_API_KEY", "")
    session = make_session(proxy)

    for role in roles:
        for region in regions:
            for industry in industries[:2]:  # Limit combinations
                queries = build_search_queries(role, region, industry)
                for query in queries:
                    logger.info(f"Searching: {query}")
                    polite_sleep()

                    if bing_api_key:
                        results = search_bing_api(query, bing_api_key)
                    else:
                        results = search_bing_html(query, session)

                    for result in results:
                        url = result.get("url", "")
                        snippet = result.get("snippet", "")

                        # Quick check: extract emails/phones from snippet
                        snippet_emails = extract_emails(snippet)
                        snippet_phones = extract_phones(snippet)

                        if snippet_emails or snippet_phones:
                            c = Contact(
                                job_title=role,
                                email=snippet_emails[0] if snippet_emails else "",
                                phone=snippet_phones[0] if snippet_phones else "",
                                source=url,
                                notes=snippet[:200],
                            )
                            c.compute_score()
                            yield c

                        # Visit page for deeper extraction
                        if url and "linkedin.com" not in url:
                            polite_sleep()
                            page_contacts = scrape_page_for_contacts(url, session, role)
                            for c in page_contacts:
                                yield c
