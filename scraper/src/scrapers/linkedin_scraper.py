"""
LinkedIn scraper — uses session cookie (li_at) to search profiles.

Usage:
  Set LINKEDIN_LI_AT in .env with your LinkedIn session cookie.
  LinkedIn's ToS prohibits scraping; use responsibly and only for your own leads.
"""
import os
import re
import logging
from typing import Iterator

import requests
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import make_session, polite_sleep, safe_get, extract_emails, extract_phones
from models import Contact

logger = logging.getLogger(__name__)

LINKEDIN_SEARCH_URL = "https://www.linkedin.com/search/results/people/"


def get_linkedin_session(li_at_cookie: str) -> requests.Session:
    session = make_session()
    session.cookies.set("li_at", li_at_cookie, domain=".linkedin.com")
    session.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Referer": "https://www.linkedin.com/",
    })
    return session


def build_linkedin_search_url(role: str, region: str, page: int = 1) -> str:
    """Build LinkedIn people search URL."""
    params = {
        "keywords": role,
        "geoUrn": "",  # Would need geo URN for precise location filtering
        "origin": "GLOBAL_SEARCH_HEADER",
        "page": page,
    }
    query_string = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    return f"{LINKEDIN_SEARCH_URL}?{query_string}"


def parse_linkedin_search_results(html: str) -> list[dict]:
    """Parse LinkedIn search results page."""
    soup = BeautifulSoup(html, "lxml")
    people = []

    # LinkedIn search results structure (may change)
    cards = soup.select("li.reusable-search__result-container")
    if not cards:
        # Try alternative selectors
        cards = soup.select("div.entity-result")

    for card in cards:
        person = {}

        # Name
        name_el = card.select_one("span.entity-result__title-text a span[aria-hidden='true']")
        if not name_el:
            name_el = card.select_one("a.app-aware-link span")
        if name_el:
            person["name"] = name_el.get_text(strip=True)

        # Title
        title_el = card.select_one("div.entity-result__primary-subtitle")
        if title_el:
            person["title"] = title_el.get_text(strip=True)

        # Location
        location_el = card.select_one("div.entity-result__secondary-subtitle")
        if location_el:
            person["location"] = location_el.get_text(strip=True)

        # Profile URL
        link_el = card.select_one("a.app-aware-link")
        if link_el:
            person["linkedin_url"] = link_el.get("href", "").split("?")[0]

        # Snippet / summary
        summary_el = card.select_one("p.entity-result__summary")
        if summary_el:
            person["summary"] = summary_el.get_text(strip=True)

        if person.get("name"):
            people.append(person)

    return people


def scrape_linkedin_profile(url: str, session: requests.Session) -> dict:
    """
    Visit a LinkedIn profile page and extract contact info.
    Note: LinkedIn hides contact info behind login walls and
    sometimes behind 'Contact Info' modal — this gets what's visible.
    """
    clean_url = url.split("?")[0]
    resp = safe_get(session, clean_url)
    if not resp:
        return {}

    soup = BeautifulSoup(resp.text, "lxml")
    text = soup.get_text(separator=" ")

    info = {
        "email": "",
        "phone": "",
        "website": "",
    }

    # Emails sometimes appear in the About section
    emails = extract_emails(text)
    if emails:
        info["email"] = emails[0]

    phones = extract_phones(text)
    if phones:
        info["phone"] = phones[0]

    # Company
    company_el = soup.select_one("div.pv-text-details__right-panel span.text-body-medium")
    if company_el:
        info["company"] = company_el.get_text(strip=True)

    return info


def run(roles: list[str], regions: list[str], max_pages: int = 3, proxy: str = None) -> Iterator[Contact]:
    """
    Scrape LinkedIn people search for given roles.
    Requires LINKEDIN_LI_AT cookie in environment.
    """
    li_at = os.getenv("LINKEDIN_LI_AT", "")
    if not li_at:
        logger.warning("LINKEDIN_LI_AT not set — skipping LinkedIn scraper.")
        return

    session = get_linkedin_session(li_at)
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}

    for role in roles:
        for region in regions:
            search_query = f"{role} {region}"
            for page in range(1, max_pages + 1):
                url = build_linkedin_search_url(search_query, region, page)
                logger.info(f"LinkedIn search: '{search_query}' page {page}")
                polite_sleep()

                resp = safe_get(session, url)
                if not resp:
                    break

                people = parse_linkedin_search_results(resp.text)
                if not people:
                    logger.info("No more results or blocked.")
                    break

                for person in people:
                    profile_url = person.get("linkedin_url", "")
                    extra = {}
                    if profile_url:
                        polite_sleep()
                        extra = scrape_linkedin_profile(profile_url, session)

                    full_name = person.get("name", "")
                    parts = full_name.split(" ", 1)

                    c = Contact(
                        full_name=full_name,
                        first_name=parts[0] if parts else "",
                        last_name=parts[1] if len(parts) > 1 else "",
                        job_title=person.get("title", role),
                        company=extra.get("company", ""),
                        email=extra.get("email", ""),
                        phone=extra.get("phone", ""),
                        linkedin_url=profile_url,
                        location=person.get("location", region),
                        source="linkedin",
                    )
                    c.compute_score()
                    yield c
