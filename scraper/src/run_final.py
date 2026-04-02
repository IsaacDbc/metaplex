"""
Final comprehensive scraper:
1. WTTJ → HR names + titles (works great)
2. Greenhouse API → recruiter emails (works)
3. Ecosia search → last names + LinkedIn + emails for WTTJ contacts
4. Compile everything into CSV
"""
import re, time, csv, os, json, random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(?:(?:\+|00)33|0)\s*[1-9](?:[\s.\-]*\d{2}){4}")
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.|fr\.)?linkedin\.com/in/([\w\-%À-ÿ]+)")
FAKE_DOMAINS = {
    "example.com", "test.com", "greenhouse.io", "workable.com", "lever.co",
    "email.com", "sentry.io", "schema.org", "google.com", "microsoft.com",
    "apple.com", "noreply.com", "ecosia.org", "yahoo.com", "gmail.com",
    "hotmail.com", "outlook.com", "w3.org",
}
GENERIC_PREFIXES = {
    "hr", "rh", "jobs", "careers", "recruitment", "no-reply", "noreply",
    "info", "contact", "hello", "team", "support", "privacy", "legal",
    "reasonable", "accommodations", "dataprivacy", "rgpd", "gdpr",
}
HR_KW = [
    "talent", "rh", "hr", "people", "drh", "recrutement", "recruitment",
    "ressources humaines", "chief people", "vp people", "head of",
    "hiring", "onboarding", "chro", "talent acquisition",
    "responsable rh", "directeur rh",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8",
})


def safe_get(url, timeout=12):
    try:
        r = SESSION.get(url, timeout=timeout)
        return r if r.status_code in (200, 301, 302) else None
    except Exception:
        return None


def is_personal_email(email: str) -> bool:
    local = email.split("@")[0].lower()
    if local in GENERIC_PREFIXES:
        return False
    return "." in local or (len(local) > 4 and local.isalpha())


def filter_emails(emails):
    return [e.lower() for e in emails
            if e.split("@")[-1].lower() not in FAKE_DOMAINS
            and is_personal_email(e)]


# ─── SOURCE 1: Welcome to the Jungle ─────────────────────────────────────────

NAME_ROLE_RE = re.compile(r"Rencontrez\s+(\w[\w\-]+),\s*([^\n\"<]{5,80})")

WTTJ_COMPANIES = [
    ("Doctolib", "doctolib", "doctolib.fr"),
    ("Payfit", "payfit", "payfit.com"),
    ("Qonto", "qonto", "qonto.com"),
    ("Alan", "alan", "alan.com"),
    ("Spendesk", "spendesk", "spendesk.com"),
    ("Brevo", "brevo", "brevo.com"),
    ("Aircall", "aircall", "aircall.io"),
    ("Swile", "swile", "swile.co"),
    ("Malt", "malt", "malt.fr"),
    ("360Learning", "360learning", "360learning.com"),
    ("Mirakl", "mirakl", "mirakl.com"),
    ("Back Market", "back-market", "backmarket.com"),
    ("Teads", "teads", "teads.com"),
    ("Kyriba", "kyriba", "kyriba.com"),
    ("Mistral AI", "mistral-ai", "mistral.ai"),
    ("Owkin", "owkin", "owkin.com"),
    ("Ledger", "ledger-hq", "ledger.com"),
    ("Contentsquare", "contentsquare", "contentsquare.com"),
    ("Dataiku", "dataiku", "dataiku.com"),
    ("Pennylane", "pennylane", "pennylane.com"),
    ("Shine", "shine", "shine.fr"),
    ("Luko", "luko", "luko.eu"),
    ("Livestorm", "livestorm", "livestorm.co"),
    ("Stuart", "stuart", "stuart.com"),
    ("Convelio", "convelio", "convelio.com"),
    ("Blablacar", "blablacar", "blablacar.com"),
    ("OVHcloud", "ovhcloud", "ovhcloud.com"),
    ("Withings", "withings", "withings.com"),
    ("Agicap", "agicap", "agicap.com"),
    ("Yousign", "yousign", "yousign.com"),
    ("Deepki", "deepki", "deepki.com"),
    ("Alma", "alma", "getalma.eu"),
    ("Comet", "comet-network", "comet.co"),
    ("Theodo", "theodo", "theodo.fr"),
    ("Lucca", "lucca-software", "lucca.fr"),
    ("Sekoia", "sekoia-io", "sekoia.io"),
    ("Vestiaire Collective", "vestiaire-collective", "vestiairecollective.com"),
    ("Vinted", "vinted", "vinted.fr"),
    ("Leboncoin", "leboncoin", "leboncoin.fr"),
    ("Bioptimus", "bioptimus", "bioptimus.com"),
    ("LegalPlace", "legalplace", "legalplace.fr"),
    ("Doctrine", "doctrine", "doctrine.fr"),
    ("Inato", "inato", "inato.com"),
    ("Nabla", "nabla", "nabla.com"),
    ("Sopra Steria", "sopra-steria", "soprasteria.com"),
    ("Capgemini", "capgemini", "capgemini.com"),
    ("Wavestone", "wavestone", "wavestone.com"),
    ("Devoteam", "devoteam", "devoteam.com"),
    ("Hays France", "hays-france", "hays.fr"),
    ("Younited Credit", "younited-credit", "younited-credit.com"),
    ("Ringover", "ringover", "ringover.com"),
    ("Dougs", "dougs", "dougs.fr"),
    ("Brigad", "brigad", "brigad.co"),
    ("Gymlib", "gymlib", "gymlib.com"),
    ("Worklife", "worklife", "worklife.eu"),
    ("Javelo", "javelo", "javelo.io"),
    ("Elevo", "elevo-app", "elevo.fr"),
    ("Indy", "indy", "indy.fr"),
    ("Lifen", "lifen", "lifen.fr"),
    ("Crisp", "crisp-im", "crisp.chat"),
    ("Modjo", "modjo-ai", "modjo.ai"),
    ("Slite", "slite", "slite.com"),
    ("Axeptio", "axeptio", "axeptio.eu"),
    ("Joko", "joko-app", "joko.com"),
    ("Leocare", "leocare", "leocare.eu"),
    ("Maki People", "maki-people", "maki-people.com"),
    ("Lydia", "lydia-solutions", "lydia-app.com"),
    ("Scaleway", "scaleway", "scaleway.com"),
    ("Talent.io", "talent-io", "talent.io"),
    ("Meero", "meero", "meero.com"),
    ("BlaBlaCar", "blablacar", "blablacar.com"),
    ("Pennylane", "pennylane", "pennylane.com"),
    ("Luko", "luko", "luko.eu"),
]


def scrape_wttj(company_name, slug, domain):
    url = f"https://www.welcometothejungle.com/fr/companies/{slug}"
    r = safe_get(url)
    if not r or r.status_code != 200:
        return []

    soup = BeautifulSoup(r.text, "lxml")
    text = soup.get_text(separator="\n")
    matches = NAME_ROLE_RE.findall(text)

    contacts = []
    for first_name, role in matches:
        role = role.strip().rstrip('"').strip()
        if any(kw in role.lower() for kw in HR_KW):
            contacts.append({
                "full_name": first_name,
                "first_name": first_name,
                "last_name": "",
                "job_title": role,
                "company": company_name,
                "company_domain": domain,
                "email": "",
                "phone": "",
                "linkedin_url": "",
                "source": f"wttj:{slug}",
                "scraped_at": datetime.now().strftime("%Y-%m-%d"),
                "score": 0.35,
            })
    return contacts


# ─── SOURCE 2: Greenhouse API ─────────────────────────────────────────────────

GH_COMPANIES = [
    ("Doctolib", "doctolib", "doctolib.fr"),
    ("Dataiku", "dataiku", "dataiku.com"),
    ("Pennylane", "pennylane", "pennylane.com"),
    ("Swile", "swile", "swile.co"),
    ("Stuart", "stuart", "stuart.com"),
    ("Teads", "teads", "teads.com"),
    ("Kyriba", "kyriba", "kyriba.com"),
    ("360Learning", "360learning", "360learning.com"),
    ("Malt", "malt", "malt.fr"),
    ("Vestiaire Collective", "vestiaire-collective", "vestiairecollective.com"),
    ("Vinted", "vinted", "vinted.fr"),
    ("Leboncoin", "leboncoin", "leboncoin.fr"),
    ("Sopra Steria", "soprasteria", "soprasteria.com"),
    ("Alten", "alten", "alten.com"),
    ("Wavestone", "wavestone", "wavestone.com"),
    ("Withings", "withings", "withings.com"),
    ("Owkin", "owkin", "owkin.com"),
    ("Airbnb Paris", "airbnb", "airbnb.com"),
    ("Payfit", "payfit", "payfit.com"),
    ("Alan", "alan", "alan.com"),
    ("Qonto", "qonto", "qonto.com"),
    ("Spendesk", "spendesk", "spendesk.com"),
    ("Brevo", "brevo", "brevo.com"),
    ("Aircall", "aircall", "aircall.io"),
    ("Ringover", "ringover", "ringover.com"),
    ("Mirakl", "mirakl", "mirakl.com"),
    ("Mistral AI", "mistralai", "mistral.ai"),
    ("Back Market", "back-market", "backmarket.com"),
    ("Doctolib", "doctolib", "doctolib.fr"),
    ("Ledger", "ledger", "ledger.com"),
    ("Younited Credit", "younited", "younited-credit.com"),
    ("Contentsquare", "content-square", "contentsquare.com"),
]


def scrape_greenhouse(company_name, slug, domain):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    r = safe_get(url)
    if not r:
        return []

    try:
        jobs = r.json().get("jobs", [])
    except Exception:
        return []

    contacts = {}
    for job in jobs:
        content = job.get("content", "") + " " + json.dumps(job.get("metadata", []))
        emails = EMAIL_RE.findall(content)
        for email in emails:
            email = email.lower()
            if email.split("@")[-1] in FAKE_DOMAINS:
                continue
            if not is_personal_email(email):
                continue
            if email in contacts:
                continue
            contacts[email] = {
                "full_name": "",
                "first_name": "",
                "last_name": "",
                "job_title": "Recruteur/Talent",
                "company": company_name,
                "company_domain": domain,
                "email": email,
                "phone": "",
                "linkedin_url": "",
                "source": f"greenhouse:{slug}",
                "job_listing": job.get("title", "")[:80],
                "scraped_at": datetime.now().strftime("%Y-%m-%d"),
                "score": 0.5,
            }

    return list(contacts.values())


# ─── SOURCE 3: Ecosia search to enrich WTTJ contacts ─────────────────────────

def ecosia_search(query, max_results=8):
    """Search Ecosia and return text snippets."""
    url = f"https://www.ecosia.org/search?method=index&q={quote_plus(query)}"
    time.sleep(random.uniform(2.5, 4.5))
    r = safe_get(url, timeout=15)
    if not r or r.status_code != 200:
        return []

    soup = BeautifulSoup(r.text, "lxml")
    results = []

    # Ecosia result containers
    for item in soup.select(".result, .web-result, article, [class*='result']")[:max_results]:
        title_el = item.select_one("h2, h3, .result-title, a")
        snip_el = item.select_one("p, .result-description, .snippet")
        href_el = item.select_one("a[href]")

        title = title_el.get_text(strip=True) if title_el else ""
        snip = snip_el.get_text(strip=True) if snip_el else ""
        href = href_el.get("href", "") if href_el else ""

        if title:
            results.append({"title": title, "snippet": snip, "url": href})

    # Fallback: extract all text
    if not results:
        text = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.splitlines() if 10 < len(l.strip()) < 200]
        # Take lines that look like search result descriptions
        for i, line in enumerate(lines[5:40]):
            results.append({"title": line, "snippet": "", "url": ""})

    return results


def enrich_contact_with_ecosia(contact: dict) -> dict:
    """Try to find last name, email, LinkedIn for a contact using Ecosia."""
    first_name = contact.get("first_name", "")
    role = contact.get("job_title", "")
    company = contact.get("company", "")
    domain = contact.get("company_domain", "")

    if not first_name or not company:
        return contact

    # Search for the person
    query = f'"{first_name}" "{company}" "{role}" linkedin email'
    results = ecosia_search(query)

    for result in results:
        combined = result.get("title", "") + " " + result.get("snippet", "")

        # Extract emails
        emails = filter_emails(EMAIL_RE.findall(combined))
        if emails:
            contact["email"] = emails[0]
            contact["score"] = min(contact.get("score", 0.35) + 0.3, 0.9)

        # Extract LinkedIn URL
        li_matches = LINKEDIN_RE.findall(combined)
        if li_matches and not contact.get("linkedin_url"):
            contact["linkedin_url"] = f"https://linkedin.com/in/{li_matches[0]}"
            contact["score"] = min(contact.get("score", 0.35) + 0.1, 0.9)

        # Try to infer last name from title like "Prénom Nom - Role @ Company"
        name_match = re.search(
            rf"{re.escape(first_name)}\s+([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][a-zàâäéèêëîïôöùûüç\-]+)",
            combined
        )
        if name_match and not contact.get("last_name"):
            contact["last_name"] = name_match.group(1)
            contact["full_name"] = f"{first_name} {contact['last_name']}"
            contact["score"] = min(contact.get("score", 0.35) + 0.1, 0.9)

        # Extract phone
        phones = PHONE_RE.findall(combined)
        if phones and not contact.get("phone"):
            contact["phone"] = phones[0]

    return contact


# ─── KNOWN CONTACTS (from earlier successful DDG scrape) ──────────────────────

KNOWN_CONTACTS = [
    {
        "full_name": "Jordan Defas",
        "first_name": "Jordan",
        "last_name": "Defas",
        "job_title": "Head of Talent Development",
        "company": "Doctolib",
        "company_domain": "doctolib.fr",
        "email": "jordan.defas@doctolib.com",
        "phone": "",
        "linkedin_url": "",
        "source": "contactout (via DDG)",
        "scraped_at": "2026-04-02",
        "score": 0.85,
    },
    {
        "full_name": "Salomé Amsler",
        "first_name": "Salomé",
        "last_name": "Amsler",
        "job_title": "Director Talent Acquisition",
        "company": "Doctolib",
        "company_domain": "doctolib.fr",
        "email": "",
        "phone": "",
        "linkedin_url": "https://fr.linkedin.com/in/salomé-amsler-b3ab8655",
        "source": "linkedin (via DDG)",
        "scraped_at": "2026-04-02",
        "score": 0.60,
    },
    {
        "full_name": "Hélène Lepelletier",
        "first_name": "Hélène",
        "last_name": "Lepelletier",
        "job_title": "Talent/Recruteur",
        "company": "Doctolib",
        "company_domain": "doctolib.fr",
        "email": "helene.lepelletier@doctolib.com",
        "phone": "",
        "linkedin_url": "",
        "source": "greenhouse:doctolib",
        "scraped_at": "2026-04-02",
        "score": 0.65,
    },
    {
        "full_name": "Mégane Breton",
        "first_name": "Mégane",
        "last_name": "Breton",
        "job_title": "Talent/Recruteur",
        "company": "Doctolib",
        "company_domain": "doctolib.fr",
        "email": "megane.breton@doctolib.com",
        "phone": "",
        "linkedin_url": "",
        "source": "greenhouse:doctolib",
        "scraped_at": "2026-04-02",
        "score": 0.65,
    },
]


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def compute_score(c: dict) -> float:
    s = 0.0
    if c.get("full_name") and len(c.get("full_name", "")) > 3: s += 0.2
    if c.get("last_name"): s += 0.05
    if c.get("job_title"): s += 0.15
    if c.get("company"): s += 0.1
    if c.get("email"): s += 0.35
    if c.get("phone"): s += 0.05
    if c.get("linkedin_url"): s += 0.1
    return round(s, 2)


def deduplicate(contacts):
    seen_emails, seen_li = set(), set()
    out = []
    for c in contacts:
        e = c.get("email", "").lower()
        li = c.get("linkedin_url", "")
        key = f"{c.get('full_name','').lower()}|{c.get('company','').lower()}"
        if e and e in seen_emails:
            continue
        if li and li in seen_li:
            continue
        if e:
            seen_emails.add(e)
        if li:
            seen_li.add(li)
        out.append(c)
    return out


def save_csv(contacts, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fields = [
        "full_name", "first_name", "last_name", "job_title", "company",
        "company_domain", "email", "phone", "linkedin_url",
        "score", "source", "job_listing", "scraped_at",
    ]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for c in sorted(contacts, key=lambda x: x.get("score", 0), reverse=True):
            w.writerow(c)
    print(f"\n✓ {len(contacts)} contacts saved → {path}")


def main():
    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "output", "contacts_tech_hr.csv"
    )
    all_contacts = list(KNOWN_CONTACTS)

    # ─── Step 1: WTTJ ───────────────────────────────────────────────────────
    print(f"\n═══ Step 1: Welcome to the Jungle ({len(WTTJ_COMPANIES)} companies) ═══")
    seen_slugs = set()
    wttj_contacts = []
    for company_name, slug, domain in WTTJ_COMPANIES:
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        contacts = scrape_wttj(company_name, slug, domain)
        if contacts:
            print(f"  {company_name}: {len(contacts)} HR contacts")
            for c in contacts:
                print(f"    → {c['full_name']} : {c['job_title']}")
        wttj_contacts.extend(contacts)
        time.sleep(0.8)

    all_contacts.extend(wttj_contacts)
    print(f"\nWTTJ total: {len(wttj_contacts)} contacts")

    # ─── Step 2: Greenhouse ──────────────────────────────────────────────────
    print(f"\n═══ Step 2: Greenhouse ATS API ({len(GH_COMPANIES)} companies) ═══")
    gh_contacts = []
    seen_gh = set()
    for company_name, slug, domain in GH_COMPANIES:
        if slug in seen_gh:
            continue
        seen_gh.add(slug)
        contacts = scrape_greenhouse(company_name, slug, domain)
        if contacts:
            print(f"  {company_name}: {len(contacts)} emails")
            for c in contacts:
                print(f"    → {c['email']} [{c['job_listing'][:40]}]")
        gh_contacts.extend(contacts)
        time.sleep(0.5)

    all_contacts.extend(gh_contacts)
    print(f"\nGreenhouse total: {len(gh_contacts)} contacts")

    # ─── Step 3: Enrich WTTJ contacts via Ecosia ────────────────────────────
    print(f"\n═══ Step 3: Enriching {len(wttj_contacts)} WTTJ contacts via Ecosia ═══")
    for i, contact in enumerate(wttj_contacts):
        print(f"  [{i+1}/{len(wttj_contacts)}] {contact['full_name']} @ {contact['company']} ...")
        enriched = enrich_contact_with_ecosia(contact)
        if enriched.get("last_name") or enriched.get("email") or enriched.get("linkedin_url"):
            print(f"    → name: {enriched.get('full_name')}, "
                  f"email: {enriched.get('email','')}, "
                  f"li: {enriched.get('linkedin_url','')[:40]}")

    # Recompute scores
    for c in all_contacts:
        c["score"] = compute_score(c)

    # ─── Final ───────────────────────────────────────────────────────────────
    all_contacts = deduplicate(all_contacts)
    all_contacts.sort(key=lambda x: x.get("score", 0), reverse=True)

    print(f"\n\n══════════════════════════════════════")
    print(f"TOTAL UNIQUE CONTACTS: {len(all_contacts)}")
    print("══════════════════════════════════════")
    print(f"\n{'Company':<25} {'Name':<25} {'Title':<35} {'Email':<40} {'Score'}")
    print("-" * 135)
    for c in all_contacts:
        print(f"{c.get('company',''):<25} {c.get('full_name',''):<25} "
              f"{c.get('job_title','')[:34]:<35} {c.get('email',''):<40} "
              f"{c.get('score',0):.2f}")

    save_csv(all_contacts, out_path)
    return out_path, all_contacts


if __name__ == "__main__":
    main()
