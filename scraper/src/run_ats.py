"""
ATS-based recruiter contact scraper.
Scrapes Greenhouse, Lever, Workable, Teamtailor public APIs for recruiter emails.
"""
import re, time, csv, os, json, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import requests

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(?:(?:\+|00)33|0)\s*[1-9](?:[\s.\-]*\d{2}){4}")
FAKE_DOMAINS = {
    "example.com","test.com","greenhouse.io","workable.com","lever.co",
    "email.com","sentry.io","schema.org","google.com","w3.org",
    "microsoft.com","apple.com","noreply.com","no-reply.com",
}
HR_KEYWORDS = [
    "talent","rh","hr","people","drh","recrutement","recruitment",
    "human resources","ressources humaines","staffing","workforce",
    "hiring","onboarding","chro",
]
GENERIC_PREFIXES = {"hr","rh","jobs","careers","recruitment","no-reply","noreply",
                    "info","contact","hello","team","support","privacy","legal",
                    "reasonable","accommodations","dataprivacy","rgpd","gdpr"}


def is_personal_email(email: str) -> bool:
    local = email.split("@")[0].lower()
    if local in GENERIC_PREFIXES: return False
    if any(kw in local for kw in ["noreply","no-reply","info","support","help",
                                   "privacy","legal","jobs","careers"]): return False
    # Must look like a name (has a dot or contains letters only)
    return True


def is_hr_context(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in HR_KEYWORDS)


def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    })
    return s


SESSION = make_session()


def safe_get(url, timeout=12):
    try:
        r = SESSION.get(url, timeout=timeout)
        return r if r.status_code == 200 else None
    except Exception:
        return None


# ─── Greenhouse ──────────────────────────────────────────────────────────────

def greenhouse_scrape(slug: str, company_name: str) -> list[dict]:
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
        content = job.get("content", "")
        all_text = content + " " + json.dumps(job.get("metadata", []))

        emails = EMAIL_RE.findall(all_text)
        phones = PHONE_RE.findall(all_text)

        for email in emails:
            email = email.lower()
            domain = email.split("@")[-1]
            if domain in FAKE_DOMAINS: continue
            if not is_personal_email(email): continue
            if email in contacts: continue

            contacts[email] = {
                "full_name": "",
                "job_title": "Talent/Recruteur",
                "company": company_name,
                "email": email,
                "phone": phones[0] if phones else "",
                "linkedin_url": "",
                "source": f"greenhouse:{slug}",
                "job_listing": job.get("title", ""),
                "scraped_at": datetime.now().strftime("%Y-%m-%d"),
                "score": 0.45,
            }

    return list(contacts.values())


# ─── Lever ───────────────────────────────────────────────────────────────────

def lever_scrape(slug: str, company_name: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=50"
    r = safe_get(url)
    if not r:
        return []

    try:
        jobs = r.json()
    except Exception:
        return []

    contacts = {}
    for job in jobs:
        text = json.dumps(job)
        emails = EMAIL_RE.findall(text)
        for email in emails:
            email = email.lower()
            if email.split("@")[-1] in FAKE_DOMAINS: continue
            if not is_personal_email(email): continue
            if email in contacts: continue
            contacts[email] = {
                "full_name": "",
                "job_title": "Talent/Recruteur",
                "company": company_name,
                "email": email,
                "phone": "",
                "linkedin_url": "",
                "source": f"lever:{slug}",
                "job_listing": job.get("text", ""),
                "scraped_at": datetime.now().strftime("%Y-%m-%d"),
                "score": 0.45,
            }

    return list(contacts.values())


# ─── Teamtailor ──────────────────────────────────────────────────────────────

def teamtailor_scrape(slug: str, company_name: str) -> list[dict]:
    url = f"https://api.teamtailor.com/v1/jobs?filter[status]=published&include=recruiter"
    # Teamtailor requires API key, but the public job embed pages have recruiter info
    url2 = f"https://{slug}.teamtailor.com/jobs.json"
    r = safe_get(url2)
    if not r:
        # Try embed
        r = safe_get(f"https://jobs.teamtailor.com/{slug}")
        if not r:
            return []

    contacts = {}
    try:
        data = r.json()
        jobs = data if isinstance(data, list) else data.get("jobs", [])
        for job in jobs:
            text = json.dumps(job)
            emails = EMAIL_RE.findall(text)
            for email in emails:
                email = email.lower()
                if email.split("@")[-1] in FAKE_DOMAINS: continue
                if not is_personal_email(email): continue
                contacts[email] = {
                    "full_name": "",
                    "job_title": "Talent/Recruteur",
                    "company": company_name,
                    "email": email,
                    "phone": "",
                    "linkedin_url": "",
                    "source": f"teamtailor:{slug}",
                    "scraped_at": datetime.now().strftime("%Y-%m-%d"),
                    "score": 0.45,
                }
    except Exception:
        pass

    return list(contacts.values())


# ─── Welcome to the Jungle (public API) ──────────────────────────────────────

def wttj_scrape(slug: str, company_name: str) -> list[dict]:
    """Welcome to the Jungle - company profile + jobs."""
    url = f"https://www.welcometothejungle.com/api/v3/organizations/{slug}/jobs?page=1&per_page=20"
    r = safe_get(url)
    if not r:
        return []

    contacts = {}
    try:
        data = r.json()
        for job in data.get("data", []):
            text = json.dumps(job)
            emails = EMAIL_RE.findall(text)
            for email in emails:
                email = email.lower()
                if email.split("@")[-1] in FAKE_DOMAINS: continue
                if not is_personal_email(email): continue
                contacts[email] = {
                    "full_name": job.get("recruiter", {}).get("name", "") if isinstance(job.get("recruiter"), dict) else "",
                    "job_title": "Talent/Recruteur",
                    "company": company_name,
                    "email": email,
                    "phone": "",
                    "linkedin_url": "",
                    "source": f"wttj:{slug}",
                    "scraped_at": datetime.now().strftime("%Y-%m-%d"),
                    "score": 0.45,
                }
    except Exception:
        pass

    return list(contacts.values())


# ─── Company list ─────────────────────────────────────────────────────────────

# (company_name, greenhouse_slug, lever_slug, teamtailor_slug, wttj_slug)
COMPANIES = [
    # Licornes / scale-ups FR
    ("Doctolib",              "doctolib",         None,               None,           "doctolib"),
    ("Dataiku",               "dataiku",           None,               None,           "dataiku"),
    ("Contentsquare",         "content-square",    "contentsquare",    None,           "contentsquare"),
    ("Payfit",                None,                "payfit",           None,           "payfit"),
    ("Pennylane",             "pennylane",         None,               None,           "pennylane"),
    ("Spendesk",              None,                "spendesk",         "spendesk",     "spendesk"),
    ("Qonto",                 "qonto",             None,               None,           "qonto"),
    ("Alan",                  None,                "alan",             None,           "alan"),
    ("Back Market",           None,                "back-market",      None,           "back-market"),
    ("Mirakl",                None,                "mirakl",           None,           "mirakl"),
    ("Swile",                 "swile",             None,               None,           "swile"),
    ("360Learning",           "360learning",       "360learning",      None,           "360learning"),
    ("Ledger",                "ledger",            None,               None,           "ledger-hq"),
    ("Teads",                 "teads",             None,               None,           "teads"),
    ("Kyriba",                "kyriba",            None,               None,           "kyriba"),
    ("Mistral AI",            "mistralai",         None,               None,           "mistral-ai"),
    ("Owkin",                 "owkin",             None,               None,           "owkin"),
    ("Nabla",                 "nabla",             None,               None,           "nabla"),
    ("Shine",                 None,                "shine",            None,           "shine"),
    ("Lydia",                 None,                None,               "lydia",        "lydia"),
    ("Younited Credit",       "younited",          None,               None,           "younited-credit"),
    ("Mango Pay",             None,                "mangopay",         None,           "mangopay"),
    ("Livestorm",             None,                "livestorm",        None,           "livestorm"),
    ("Brevo",                 None,                "sendinblue",       None,           "brevo"),
    ("Aircall",               "aircall",           None,               None,           "aircall"),
    ("Ringover",              None,                "ringover",         None,           "ringover"),
    ("Dougs",                 None,                None,               "dougs",        "dougs"),
    ("Malt",                  "malt",              None,               None,           "malt"),
    ("Brigad",                None,                None,               "brigad",       "brigad"),
    ("Stuart",                "stuart",            None,               None,           "stuart"),
    ("Convelio",              None,                None,               "convelio",     "convelio"),
    ("Sekoia",                None,                None,               "sekoia",       "sekoia-io"),
    ("Stormshield",           None,                None,               None,           "stormshield"),
    ("Gymlib",                None,                None,               None,           "gymlib"),
    ("Worklife",              None,                None,               None,           "worklife"),
    ("Lucca",                 None,                None,               "lucca",        "lucca"),
    ("Sopra Steria",          "soprasteria",       None,               None,           "sopra-steria"),
    ("Capgemini France",      "capgemini",         None,               None,           "capgemini"),
    ("Alten",                 "alten",             None,               None,           "alten"),
    ("Devoteam",              "devoteam",          None,               None,           "devoteam"),
    ("Aubay",                 None,                None,               None,           "aubay"),
    ("Wavestone",             "wavestone",         None,               None,           "wavestone"),
    ("Slite",                 None,                "slite",            None,           "slite"),
    ("Modjo",                 None,                "modjo",            None,           "modjo"),
    ("Talkspirit",            None,                None,               None,           "talkspirit"),
    ("Vestiaire Collective",  "vestiaire-collective", None,            None,           "vestiaire-collective"),
    ("Vinted",                "vinted",            None,               None,           "vinted"),
    ("Leboncoin",             "leboncoin",         None,               None,           "leboncoin"),
    ("Bioptimus",             None,                "bioptimus",        None,           "bioptimus"),
    ("LegalPlace",            None,                None,               None,           "legalplace"),
    ("Indy",                  None,                None,               "indy",         "indy"),
    ("Lifen",                 None,                None,               "lifen",        "lifen"),
    ("Synapse Medicine",      None,                None,               None,           "synapse-medicine"),
    ("Javelo",                None,                None,               None,           "javelo"),
    ("Elevo",                 None,                None,               None,           "elevo"),
    ("Maki People",           None,                None,               None,           "maki-people"),
    ("Doctrine",              None,                None,               None,           "doctrine"),
    ("Inato",                 None,                None,               None,           "inato"),
    ("Luko",                  None,                "luko",             None,           "luko"),
    ("Hays France",           None,                None,               None,           "hays-france"),
    ("Welcome to the Jungle", None,                None,               None,           None),
    ("Talent.io",             None,                None,               None,           None),
    ("Axeptio",               None,                None,               None,           "axeptio"),
    ("Crisp",                 None,                None,               None,           "crisp"),
    ("Pennylane",             "pennylane",         None,               None,           "pennylane"),
    ("Alma",                  None,                "almapay",          None,           "alma"),
    ("Comet",                 None,                None,               None,           "comet"),
    ("Joko",                  None,                None,               None,           "joko"),
    ("Swello",                None,                None,               None,           None),
    ("OVHcloud",              None,                None,               None,           "ovhcloud"),
    ("Scaleway",              None,                None,               None,           "scaleway"),
    ("Withings",              "withings",          None,               None,           "withings"),
    ("Blablacar",             None,                None,               None,           "blablacar"),
    ("Meero",                 None,                None,               None,           "meero"),
    ("Klaxoon",               None,                None,               None,           "klaxoon"),
    ("Theodo",                None,                None,               "theodo",       "theodo"),
    ("Agicap",                None,                "agicap",           None,           "agicap"),
    ("Pennylane",             "pennylane",         None,               None,           None),
    ("Leocare",               None,                None,               None,           "leocare"),
    ("Yousign",               None,                None,               None,           "yousign"),
    ("Deepki",                None,                None,               None,           "deepki"),
    ("Sivo",                  None,                None,               None,           None),
    ("Particeep",             None,                None,               None,           None),
]

# Deduplicate
seen = set()
COMPANIES_CLEAN = []
for c in COMPANIES:
    if c[0] not in seen:
        seen.add(c[0])
        COMPANIES_CLEAN.append(c)
COMPANIES = COMPANIES_CLEAN


def scrape_company(entry):
    name, gh, lever, tt, wttj = entry
    contacts = []

    if gh:
        time.sleep(0.5)
        contacts += greenhouse_scrape(gh, name)

    if lever:
        time.sleep(0.5)
        contacts += lever_scrape(lever, name)

    if tt:
        time.sleep(0.5)
        contacts += teamtailor_scrape(tt, name)

    # Deduplicate within company
    seen_emails = set()
    out = []
    for c in contacts:
        e = c.get("email", "")
        if e not in seen_emails:
            seen_emails.add(e)
            out.append(c)

    return name, out


def save_csv(contacts: list[dict], path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fields = [
        "full_name", "job_title", "company", "email", "phone",
        "linkedin_url", "score", "source", "job_listing", "scraped_at",
    ]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for c in sorted(contacts, key=lambda x: (x.get("company",""), x.get("email",""))):
            w.writerow(c)
    print(f"\n✓ {len(contacts)} contacts saved → {path}")


def main():
    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "output", "contacts_tech_hr.csv"
    )
    print(f"Scraping {len(COMPANIES)} companies via ATS APIs …\n")

    all_contacts = []
    total_done = 0

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(scrape_company, entry): entry[0] for entry in COMPANIES}
        for f in as_completed(futures):
            company_name = futures[f]
            try:
                name, contacts = f.result()
                all_contacts.extend(contacts)
                total_done += 1
                n = len(contacts)
                bar = ("■" * n + "·" * max(0, 5 - n))[:5]
                flag = " ← contacts trouvés!" if n > 0 else ""
                print(f"  [{total_done:02d}/{len(COMPANIES)}] {name:<30} {bar} {n}{flag}")
            except Exception as e:
                total_done += 1
                print(f"  [{total_done:02d}/{len(COMPANIES)}] {futures[f]:<30} ERROR: {e}")

    # Final deduplicate
    seen_emails = set()
    unique = []
    for c in all_contacts:
        e = c.get("email","").lower()
        if e and e not in seen_emails:
            seen_emails.add(e)
            unique.append(c)
        elif not e:
            unique.append(c)

    print(f"\nTotal unique contacts: {len(unique)}")

    # Show results
    if unique:
        print("\n--- Sample contacts ---")
        for c in unique[:20]:
            print(f"  {c['company']:<20} {c['email']:<45} [{c['source']}]")

    save_csv(unique, out_path)
    return out_path, unique


if __name__ == "__main__":
    main()
