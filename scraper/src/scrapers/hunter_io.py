"""
Hunter.io API integration.
Finds professional email addresses for a given person + company domain.

Free tier: 25 searches/month. Paid plans available.
Sign up: https://hunter.io
"""
import os
import logging
from typing import Optional

import requests

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import polite_sleep
from models import Contact

logger = logging.getLogger(__name__)

HUNTER_DOMAIN_SEARCH = "https://api.hunter.io/v2/domain-search"
HUNTER_EMAIL_FINDER = "https://api.hunter.io/v2/email-finder"
HUNTER_EMAIL_VERIFIER = "https://api.hunter.io/v2/email-verifier"


def domain_search(domain: str, role_keywords: list[str] = None) -> list[dict]:
    """
    Search all emails for a company domain.
    Optionally filter by role keywords (e.g. 'HR', 'talent').
    """
    api_key = os.getenv("HUNTER_API_KEY", "")
    if not api_key:
        logger.warning("HUNTER_API_KEY not set.")
        return []

    params = {
        "domain": domain,
        "api_key": api_key,
        "limit": 100,
        "type": "personal",  # personal or generic
    }

    try:
        resp = requests.get(HUNTER_DOMAIN_SEARCH, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        emails = data.get("emails", [])
    except Exception as e:
        logger.error(f"Hunter domain search error for {domain}: {e}")
        return []

    if role_keywords:
        # Filter: keep only people whose title matches role keywords
        kw_lower = [k.lower() for k in role_keywords]
        filtered = []
        for e in emails:
            position = (e.get("position") or "").lower()
            if any(kw in position for kw in kw_lower):
                filtered.append(e)
        return filtered

    return emails


def find_email(first_name: str, last_name: str, domain: str) -> Optional[str]:
    """
    Find the email address for a specific person at a company.
    Returns email string or None.
    """
    api_key = os.getenv("HUNTER_API_KEY", "")
    if not api_key:
        return None

    params = {
        "first_name": first_name,
        "last_name": last_name,
        "domain": domain,
        "api_key": api_key,
    }

    try:
        resp = requests.get(HUNTER_EMAIL_FINDER, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        email = data.get("email")
        confidence = data.get("confidence", 0)
        if email and confidence > 50:
            return email
    except Exception as e:
        logger.error(f"Hunter email finder error: {e}")

    return None


def verify_email(email: str) -> dict:
    """
    Verify if an email address is valid and deliverable.
    Returns dict with 'status', 'score', 'disposable', etc.
    """
    api_key = os.getenv("HUNTER_API_KEY", "")
    if not api_key:
        return {}

    params = {"email": email, "api_key": api_key}

    try:
        resp = requests.get(HUNTER_EMAIL_VERIFIER, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", {})
    except Exception as e:
        logger.error(f"Hunter email verification error: {e}")
        return {}


def enrich_contact_with_hunter(contact: Contact, role_keywords: list[str] = None) -> Contact:
    """
    Try to find or verify the email for a contact using Hunter.io.
    """
    # If we have a company website domain
    domain = ""
    if contact.company_website:
        domain = contact.company_website.replace("https://", "").replace("http://", "").split("/")[0]
    elif contact.company:
        # Guess domain from company name (naive)
        domain = contact.company.lower().replace(" ", "") + ".com"

    if not domain:
        return contact

    # If we have a name but no email, try email finder
    if contact.first_name and contact.last_name and not contact.email:
        polite_sleep()
        email = find_email(contact.first_name, contact.last_name, domain)
        if email:
            contact.email = email
            logger.info(f"Hunter found email {email} for {contact.full_name}")

    # Verify existing email
    if contact.email:
        polite_sleep()
        verification = verify_email(contact.email)
        status = verification.get("status", "")
        if status == "invalid":
            logger.info(f"Hunter marked {contact.email} as invalid, clearing.")
            contact.email = ""
        elif status == "valid":
            contact.notes += f" [Hunter verified: {status}]"

    contact.compute_score()
    return contact


def run_domain_search(domains: list[str], role_keywords: list[str] = None) -> list[Contact]:
    """
    Search Hunter.io for all contacts matching role keywords across given domains.
    """
    all_contacts = []
    role_kw = role_keywords or ["hr", "talent", "people", "recruitment", "rh", "drh", "procurement"]

    for domain in domains:
        logger.info(f"Hunter domain search: {domain}")
        polite_sleep()
        emails_data = domain_search(domain, role_kw)

        for entry in emails_data:
            full_name = f"{entry.get('first_name', '')} {entry.get('last_name', '')}".strip()
            parts = full_name.split(" ", 1)
            c = Contact(
                full_name=full_name,
                first_name=entry.get("first_name", ""),
                last_name=entry.get("last_name", ""),
                job_title=entry.get("position", ""),
                company=entry.get("organization", ""),
                company_website=f"https://{domain}",
                email=entry.get("value", ""),
                linkedin_url=entry.get("linkedin", ""),
                phone=entry.get("phone_number", ""),
                source=f"hunter.io:{domain}",
                confidence_score=entry.get("confidence", 0) / 100,
            )
            all_contacts.append(c)

    return all_contacts
