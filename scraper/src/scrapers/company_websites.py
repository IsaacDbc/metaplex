"""
Company website scraper.
Visits /team, /about, /careers pages of tech companies to extract HR contacts.
"""
import re
import logging
from typing import Iterator
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import make_session, polite_sleep, safe_get, extract_emails, extract_phones, clean_text
from models import Contact

logger = logging.getLogger(__name__)

# Pages that typically list team/HR contacts
TEAM_PAGE_PATHS = [
    "/team",
    "/about",
    "/about-us",
    "/equipe",
    "/notre-equipe",
    "/company/team",
    "/careers",
    "/jobs",
    "/contact",
    "/nous-contacter",
    "/recrutement",
]

# Keywords that indicate HR/talent roles
HR_KEYWORDS = [
    "drh", "directeur rh", "directrice rh",
    "head of talent", "head of hr", "head of people",
    "talent acquisition", "talent manager",
    "chief people officer", "vp people", "vp hr",
    "responsable rh", "chargée rh", "chargé rh",
    "recruitment", "recrutement",
    "head of procurement",
    "chro",
]


def is_hr_role(text: str) -> bool:
    """Check if a text string mentions an HR/talent role."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in HR_KEYWORDS)


def extract_contacts_from_team_page(url: str, session: requests.Session) -> list[Contact]:
    """
    Scrape a team/about page and extract HR contact cards.
    """
    resp = safe_get(session, url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    contacts = []
    domain = urlparse(url).netloc

    # Strategy 1: Find person cards (common HTML patterns)
    person_selectors = [
        "div.team-member",
        "div.person",
        "div.employee",
        "article.team",
        "li.team-member",
        "div[class*='team']",
        "div[class*='member']",
        "div[class*='person']",
        "div[class*='staff']",
        "div[class*='equipe']",
    ]

    found_cards = []
    for sel in person_selectors:
        cards = soup.select(sel)
        if cards:
            found_cards = cards
            break

    for card in found_cards:
        card_text = card.get_text(separator=" ", strip=True)
        if not is_hr_role(card_text):
            continue

        # Name: look for heading tags
        name = ""
        for tag in ["h1", "h2", "h3", "h4", "strong", "b"]:
            el = card.find(tag)
            if el:
                name = clean_text(el.get_text())
                break

        # Title: often in a paragraph or span after the name
        title = ""
        title_candidates = card.select("p, span, div")
        for el in title_candidates:
            t = clean_text(el.get_text())
            if is_hr_role(t) and len(t) < 80:
                title = t
                break

        emails = extract_emails(card_text)
        phones = extract_phones(card_text)

        c = Contact(
            full_name=name,
            job_title=title,
            company_website=f"https://{domain}",
            email=emails[0] if emails else "",
            phone=phones[0] if phones else "",
            source=url,
        )
        c.compute_score()
        contacts.append(c)

    # Strategy 2: Full page text extraction (fallback)
    if not contacts:
        full_text = soup.get_text(separator="\n")
        emails = extract_emails(full_text)
        phones = extract_phones(full_text)

        # Only keep if HR keywords present on page
        if emails and is_hr_role(full_text):
            c = Contact(
                company_website=f"https://{domain}",
                email=emails[0] if emails else "",
                phone=phones[0] if phones else "",
                source=url,
            )
            c.compute_score()
            contacts.append(c)

    return contacts


def discover_team_pages(base_url: str, session: requests.Session) -> list[str]:
    """
    Discover team/contact pages from a company homepage.
    Returns list of URLs to scrape.
    """
    found = []

    # Check known paths
    for path in TEAM_PAGE_PATHS:
        url = urljoin(base_url, path)
        resp = safe_get(session, url)
        if resp and resp.status_code == 200:
            found.append(url)
            polite_sleep()

    # Also parse homepage links
    resp = safe_get(session, base_url)
    if resp:
        soup = BeautifulSoup(resp.text, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            if any(kw in href for kw in ["team", "equipe", "about", "contact", "careers", "recrutement"]):
                full_url = urljoin(base_url, a["href"])
                if urlparse(full_url).netloc == urlparse(base_url).netloc:
                    if full_url not in found:
                        found.append(full_url)

    return found[:10]  # Cap at 10 pages per company


def run(company_urls: list[str], proxy: str = None) -> Iterator[Contact]:
    """
    Scrape a list of company websites for HR/talent contacts.
    """
    session = make_session(proxy)

    for base_url in company_urls:
        logger.info(f"Scraping company site: {base_url}")

        pages = discover_team_pages(base_url, session)
        if not pages:
            pages = [base_url]  # Fallback to homepage

        for page_url in pages:
            polite_sleep()
            logger.info(f"  -> {page_url}")
            contacts = extract_contacts_from_team_page(page_url, session)
            for c in contacts:
                if not c.company:
                    c.company = urlparse(base_url).netloc
                yield c
