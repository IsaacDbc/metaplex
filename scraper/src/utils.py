"""
Shared utilities: HTTP session, contact extraction from text, deduplication.
"""
import re
import time
import random
import logging
from typing import Optional

import requests
from fake_useragent import UserAgent
from dotenv import load_dotenv

from config import EMAIL_PATTERNS, PHONE_PATTERNS, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX

load_dotenv()
logger = logging.getLogger(__name__)


def make_session(proxy: Optional[str] = None) -> requests.Session:
    """Create a requests session with rotating user agent."""
    try:
        ua = UserAgent()
        user_agent = ua.random
    except Exception:
        user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

    session = requests.Session()
    session.headers.update({
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
    })
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    return session


def polite_sleep():
    """Random delay to avoid hammering servers."""
    delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
    time.sleep(delay)


def extract_emails(text: str) -> list[str]:
    """Extract email addresses from raw text."""
    emails = []
    for pattern in EMAIL_PATTERNS:
        found = re.findall(pattern, text, re.IGNORECASE)
        emails.extend(found)
    # Filter out common false positives
    blacklist = {"example.com", "test.com", "domain.com", "email.com", "yourcompany.com"}
    return list({e.lower() for e in emails if e.split("@")[-1] not in blacklist})


def extract_phones(text: str) -> list[str]:
    """Extract phone numbers from raw text."""
    phones = []
    for pattern in PHONE_PATTERNS:
        found = re.findall(pattern, text)
        phones.extend(found)
    return list(set(phones))


def clean_text(text: str) -> str:
    """Remove excess whitespace from text."""
    return re.sub(r"\s+", " ", text).strip()


def deduplicate_contacts(contacts: list) -> list:
    """Remove duplicate contacts by email or (name + company)."""
    seen_emails = set()
    seen_names = set()
    unique = []
    for c in contacts:
        key_email = c.email.lower() if c.email else None
        key_name = f"{c.full_name.lower()}|{c.company.lower()}"
        if key_email and key_email in seen_emails:
            continue
        if not key_email and key_name in seen_names:
            continue
        if key_email:
            seen_emails.add(key_email)
        seen_names.add(key_name)
        unique.append(c)
    return unique


def safe_get(session: requests.Session, url: str, timeout: int = 15) -> Optional[requests.Response]:
    """GET request with error handling."""
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP {e.response.status_code} for {url}")
    except requests.exceptions.ConnectionError:
        logger.warning(f"Connection error for {url}")
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout for {url}")
    except Exception as e:
        logger.warning(f"Error fetching {url}: {e}")
    return None
