"""
Fast batch scraper using DuckDuckGo HTML search.
Finds HR/Talent contacts at tech companies.
"""
import os, sys, re, time, random, logging, csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.WARNING)

# ─── Boîtes cibles ───────────────────────────────────────────────────────────
COMPANIES = [
    "Doctolib", "Contentsquare", "Dataiku", "Payfit", "Pennylane",
    "Spendesk", "Qonto", "Alan", "Back Market", "Mirakl",
    "Swile", "360Learning", "Ledger", "Doctrine", "Teads",
    "Kyriba", "Inato", "Mistral AI", "Owkin", "Nabla",
    "Shine", "Lydia", "Luko", "Younited Credit", "Mango Pay",
    "Livestorm", "Brevo", "Aircall", "Ringover", "Dougs",
    "Malt", "Brigad", "Stuart", "Convelio", "Sekoia",
    "Vade Secure", "Stormshield", "Gymlib", "Worklife", "Lucca",
    "Talent.io", "Welcome to the Jungle", "Hays France", "Michael Page",
    "Robert Walters France", "Sopra Steria", "Capgemini France",
    "Alten", "Devoteam", "Aubay", "SQLI", "Wavestone",
    "Slite", "Brevo", "Aircall", "Axeptio", "Talkspirit", "Modjo",
    "Vestiaire Collective", "Vinted France", "Leboncoin",
    "Bioptimus", "LegalPlace", "Jow", "Indy",
    "Lifen", "Synapse Medicine", "Javelo", "Elevo", "Maki People",
    "Pennylane", "Payfit", "Spendesk", "Qonto", "Alan",
]
# Deduplicate companies
COMPANIES = list(dict.fromkeys(COMPANIES))

ROLES_QUERIES = [
    '"Head of Talent"',
    '"DRH" OR "Directeur RH" OR "Directrice RH"',
    '"Head of People" OR "Chief People Officer"',
    '"Talent Acquisition Manager" OR "Head of Recruitment"',
    '"VP People" OR "VP HR" OR "CHRO"',
    '"Head of Procurement"',
    '"Responsable RH" OR "Responsable Recrutement"',
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(
    r"(?:(?:\+|00)33|0)\s*[1-9](?:[\s.\-]*\d{2}){4}|"
    r"\+\d{1,3}[\s.\-]?\(?\d{1,4}\)?[\s.\-]?\d{1,4}[\s.\-]?\d{1,9}"
)
FAKE_DOMAINS = {
    "example.com", "test.com", "domain.com", "email.com", "sentry.io",
    "w3.org", "schema.org", "google.com", "microsoft.com", "apple.com",
    "yourcompany.com", "gmail.com", "yahoo.com", "hotmail.com",
}

DDG_SESSION = requests.Session()
DDG_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
})


def ddg_search(query: str, max_results: int = 10) -> list[dict]:
    """Search DuckDuckGo HTML and parse results."""
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}&kl=fr-fr"
    try:
        time.sleep(random.uniform(1.2, 2.5))
        r = DDG_SESSION.get(url, timeout=15)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        results = []
        for res in soup.select(".result")[:max_results]:
            a = res.select_one(".result__a")
            snip = res.select_one(".result__snippet")
            url_tag = res.select_one(".result__url")
            if a:
                href = a.get("href", "")
                # DDG uses redirect URLs, extract real URL
                real_url = ""
                if "uddg=" in href:
                    from urllib.parse import unquote, parse_qs, urlparse
                    qs = parse_qs(urlparse(href).query)
                    real_url = unquote(qs.get("uddg", [""])[0])
                elif href.startswith("http"):
                    real_url = href
                elif url_tag:
                    real_url = "https://" + url_tag.get_text(strip=True)

                results.append({
                    "url": real_url,
                    "title": a.get_text(strip=True),
                    "snippet": snip.get_text(strip=True) if snip else "",
                })
        return results
    except Exception as e:
        return []


def extract_emails(text: str) -> list[str]:
    found = EMAIL_RE.findall(text)
    return [e.lower() for e in found
            if e.split("@")[-1] not in FAKE_DOMAINS
            and not e.startswith("no-reply")
            and not e.startswith("noreply")]


def extract_phones(text: str) -> list[str]:
    return list(set(PHONE_RE.findall(text)))


def extract_name_from_title(title: str, company: str) -> str:
    """Extract person name from page title."""
    # Clean company name
    title = re.sub(re.escape(company), "", title, flags=re.IGNORECASE)
    # Split on separators
    parts = re.split(r"[-–|·•@]", title)
    for part in parts:
        candidate = part.strip()
        words = candidate.split()
        # Name: 2-4 words, mostly alpha, not all caps keywords
        if (2 <= len(words) <= 4
                and candidate.replace(" ", "").replace("-", "").isalpha()
                and not any(kw in candidate.lower() for kw in
                            ["email", "phone", "contact", "linkedin", "director",
                             "head of", "manager", "officer", "responsable"])):
            return candidate
    return ""


def detect_role_from_text(text: str) -> str:
    roles_map = [
        ("DRH", ["drh", "directeur des ressources humaines", "directrice des ressources humaines"]),
        ("Directeur RH", ["directeur rh", "directrice rh"]),
        ("Head of Talent", ["head of talent"]),
        ("Head of Talent Acquisition", ["head of talent acquisition", "director talent acquisition"]),
        ("Head of People", ["head of people"]),
        ("Chief People Officer", ["chief people officer", "cpo"]),
        ("VP People", ["vp people", "vp of people"]),
        ("VP HR", ["vp hr", "vp of hr"]),
        ("CHRO", ["chro"]),
        ("Talent Acquisition Manager", ["talent acquisition manager", "talent acquisition"]),
        ("Head of Recruitment", ["head of recruitment", "head of recruitement"]),
        ("Responsable RH", ["responsable rh", "responsable recrutement"]),
        ("Head of Procurement", ["head of procurement"]),
        ("Talent Manager", ["talent manager"]),
        ("Head of HR", ["head of hr"]),
    ]
    text_l = text.lower()
    for role_name, keywords in roles_map:
        if any(kw in text_l for kw in keywords):
            return role_name
    return ""


def compute_score(c: dict) -> float:
    s = 0.0
    if c.get("full_name"): s += 0.2
    if c.get("job_title"): s += 0.15
    if c.get("company"): s += 0.15
    if c.get("email"): s += 0.35
    if c.get("phone"): s += 0.05
    if c.get("linkedin_url"): s += 0.1
    return round(s, 2)


def search_company(company: str) -> list[dict]:
    contacts = []
    seen_emails = set()

    for role_q in ROLES_QUERIES:
        query = f'"{company}" {role_q} email contact'
        results = ddg_search(query, max_results=8)

        for r in results:
            combined = r["title"] + " " + r["snippet"]
            emails = extract_emails(combined)
            phones = extract_phones(combined)
            role = detect_role_from_text(combined)
            name = extract_name_from_title(r["title"], company)
            is_li = "linkedin.com/in" in r["url"]

            # Skip results with no useful data
            if not emails and not phones and not (is_li and (name or role)):
                continue

            # Deduplicate by email
            primary_email = emails[0] if emails else ""
            if primary_email and primary_email in seen_emails:
                continue
            if primary_email:
                seen_emails.add(primary_email)

            contact = {
                "full_name": name,
                "job_title": role,
                "company": company,
                "email": primary_email,
                "all_emails": ", ".join(emails),
                "phone": phones[0] if phones else "",
                "linkedin_url": r["url"] if is_li else "",
                "source_url": r["url"],
                "snippet": r["snippet"][:250],
                "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "score": 0.0,
            }
            contact["score"] = compute_score(contact)
            contacts.append(contact)

    return contacts


def deduplicate(contacts: list[dict]) -> list[dict]:
    seen_emails, seen_linkedin = set(), set()
    out = []
    for c in contacts:
        e = c.get("email", "").lower()
        li = c.get("linkedin_url", "")
        if e and e in seen_emails:
            continue
        if li and li in seen_linkedin:
            continue
        if e:
            seen_emails.add(e)
        if li:
            seen_linkedin.add(li)
        out.append(c)
    return out


def save_csv(contacts: list[dict], path: str):
    if not contacts:
        print("No contacts to save.")
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fields = [
        "full_name", "job_title", "company", "email", "all_emails",
        "phone", "linkedin_url", "score", "source_url", "snippet", "scraped_at",
    ]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for c in contacts:
            w.writerow(c)
    print(f"\n✓ {len(contacts)} contacts saved → {path}")


def main():
    out_path = os.path.join(
        os.path.dirname(__file__), "..", "output", "contacts_tech_hr.csv"
    )
    print(f"Searching {len(COMPANIES)} companies …")

    all_contacts: list[dict] = []
    total_done = 0

    # Sequential to avoid DDG rate limiting (4 workers still fine with 1-2s delay each)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(search_company, co): co for co in COMPANIES}
        for f in as_completed(futures):
            company = futures[f]
            try:
                results = f.result()
                all_contacts.extend(results)
                total_done += 1
                found = len(results)
                bar = "■" * found + "·" * max(0, 5 - found)
                print(f"  [{total_done:02d}/{len(COMPANIES)}] {company:<25} {bar} {found} contacts")
            except Exception as e:
                total_done += 1
                print(f"  [{total_done:02d}/{len(COMPANIES)}] {company:<25} ERROR: {e}")

    all_contacts = deduplicate(all_contacts)
    all_contacts.sort(key=lambda x: x["score"], reverse=True)
    print(f"\nTotal unique contacts: {len(all_contacts)}")

    save_csv(all_contacts, out_path)
    return out_path


if __name__ == "__main__":
    main()
