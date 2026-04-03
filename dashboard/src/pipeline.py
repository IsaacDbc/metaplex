"""
Pipeline principal de collecte de données.
Lance toutes les sources, normalise et stocke dans SQLite.
"""
import re
import json
import time
import logging
from datetime import datetime, timedelta
from collections import defaultdict

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from storage import init_db, upsert_company, insert_funding, insert_job, get_conn
from scoring import score_company, get_priority, get_signal_summary
import sources.funding_rss as funding_rss
import sources.wttj_jobs as wttj_jobs
import sources.bpifrance as bpifrance
import sources.indeed_jobs as indeed_jobs
import sources.cadremploi_jobs as cadremploi_jobs
import sources.ats_jobs as ats_jobs

logger = logging.getLogger(__name__)
console = Console()

CTO_RE = re.compile(
    r"\b(cto|vp engineering|head of engineering|chief technology|tech lead senior|"
    r"vp of engineering|principal engineer|staff engineer)\b",
    re.IGNORECASE,
)
HR_RE = re.compile(
    r"\b(head of talent|head of people|drh|talent acquisition|responsable rh|"
    r"chief people|vp people|head of hr|chro)\b",
    re.IGNORECASE,
)

# Map to normalize company names
def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).title()


def days_since(date_str: str) -> int:
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00").split("+")[0])
        return (datetime.now() - dt).days
    except Exception:
        return 999


def run_pipeline(verbose: bool = True) -> dict:
    """
    Execute the full data collection pipeline.
    Returns summary stats.
    """
    init_db()
    stats = {"funding": 0, "jobs": 0, "companies": 0, "new": 0}

    # ─── Tracking per company ─────────────────────────────────────────────────
    company_jobs = defaultdict(list)       # name → [job dicts]
    company_funding = defaultdict(list)    # name → [funding dicts]

    # ─── Step 1: RSS Funding ──────────────────────────────────────────────────
    if verbose:
        console.rule("[bold yellow]📡 Veille levées de fonds (RSS)")

    for event in funding_rss.run():
        company_name = normalize_name(event.get("company_name", ""))
        if not company_name or len(company_name) < 3:
            company_name = event.get("article_title", "")[:40]

        is_new = insert_funding(
            company_name,
            amount_m=event.get("amount_m", 0),
            round_type=event.get("round_type", ""),
            article_title=event.get("article_title", ""),
            article_url=event.get("article_url", ""),
            source=event.get("source", ""),
            published_at=event.get("published_at", ""),
        )
        if is_new:
            stats["funding"] += 1
            company_funding[company_name].append(event)
            if verbose:
                amt = f"{event['amount_m']:.0f}M€" if event.get("amount_m") else ""
                console.print(f"  💰 [green]{company_name}[/green] {amt} — {event.get('source','')}")

    if verbose:
        console.print(f"[cyan]→ {stats['funding']} nouveaux événements de financement[/cyan]")

    # ─── Step 2: BPI France / Frenchweb ──────────────────────────────────────
    if verbose:
        console.rule("[bold yellow]🏦 Sources BPI / Frenchweb")

    for event in bpifrance.run():
        if not event.get("is_tech", True):
            continue
        company_name = normalize_name(event.get("company_name", ""))
        if not company_name:
            company_name = event.get("article_title", "")[:40]
        is_new = insert_funding(
            company_name,
            amount_m=event.get("amount_m", 0),
            round_type=event.get("round_type", ""),
            article_title=event.get("article_title", ""),
            article_url=event.get("article_url", ""),
            source=event.get("source", ""),
            published_at=event.get("published_at", ""),
        )
        if is_new:
            stats["funding"] += 1
            company_funding[company_name].append(event)

    # ─── Step 3: WTTJ Tech Jobs ───────────────────────────────────────────────
    if verbose:
        console.rule("[bold yellow]💼 Offres tech WTTJ")

    job_count = 0
    for job in wttj_jobs.run(max_pages=3):
        company_name = normalize_name(job.get("company_name", ""))
        if not company_name:
            continue

        is_new = insert_job(
            company_name,
            job_title=job.get("job_title", ""),
            tech_tags=job.get("tech_tags", ""),
            location=job.get("location", ""),
            job_url=job.get("job_url", ""),
            source=job.get("source", "wttj"),
            published_at=job.get("published_at", datetime.now().isoformat()),
        )
        if is_new:
            stats["jobs"] += 1
            company_jobs[company_name].append(job)
            job_count += 1
            if verbose and job_count % 50 == 0:
                console.print(f"  📋 {job_count} offres tech collectées...")

    if verbose:
        console.print(f"[cyan]→ {stats['jobs']} nouvelles offres tech[/cyan]")

    # ─── Step 3b: ATS (Greenhouse + Lever) ───────────────────────────────────
    if verbose:
        console.rule("[bold yellow]💼 Offres tech ATS (Greenhouse / Lever)")

    for job in ats_jobs.run():
        company_name = normalize_name(job.get("company_name", ""))
        if not company_name:
            continue
        is_new = insert_job(
            company_name,
            job_title=job.get("job_title", ""),
            tech_tags="[]",
            location=job.get("location", ""),
            job_url=job.get("job_url", ""),
            source=job.get("source", "ats"),
            published_at=job.get("published_at", datetime.now().isoformat()),
        )
        if is_new:
            stats["jobs"] += 1
            company_jobs[company_name].append(job)

    # ─── Step 3c: Indeed France ───────────────────────────────────────────────
    if verbose:
        console.rule("[bold yellow]💼 Offres tech Indeed France")

    for job in indeed_jobs.run():
        company_name = normalize_name(job.get("company_name", ""))
        if not company_name:
            continue
        is_new = insert_job(
            company_name,
            job_title=job.get("job_title", ""),
            tech_tags="[]",
            location=job.get("location", ""),
            job_url=job.get("job_url", ""),
            source="indeed",
            published_at=job.get("published_at", datetime.now().isoformat()),
        )
        if is_new:
            stats["jobs"] += 1
            company_jobs[company_name].append(job)

    # ─── Step 3c: Cadremploi ──────────────────────────────────────────────────
    if verbose:
        console.rule("[bold yellow]💼 Offres tech Cadremploi")

    for job in cadremploi_jobs.run():
        company_name = normalize_name(job.get("company_name", ""))
        if not company_name:
            continue
        is_new = insert_job(
            company_name,
            job_title=job.get("job_title", ""),
            tech_tags="[]",
            location=job.get("location", ""),
            job_url=job.get("job_url", ""),
            source="cadremploi",
            published_at=job.get("published_at", datetime.now().isoformat()),
        )
        if is_new:
            stats["jobs"] += 1
            company_jobs[company_name].append(job)

    if verbose:
        console.print(f"[cyan]→ {stats['jobs']} nouvelles offres tech au total[/cyan]")

    # ─── Step 4: Update company signals ──────────────────────────────────────
    if verbose:
        console.rule("[bold yellow]🎯 Calcul des scores")

    # Aggregate all known companies
    all_companies = set(list(company_jobs.keys()) + list(company_funding.keys()))

    for company_name in all_companies:
        jobs = company_jobs.get(company_name, [])
        funding_events = company_funding.get(company_name, [])

        # Job analysis
        tech_jobs_count = len(jobs)
        has_cto = any(CTO_RE.search(j.get("job_title", "")) for j in jobs)
        has_hr = any(HR_RE.search(j.get("job_title", "")) for j in jobs)

        # Funding analysis
        has_funding = len(funding_events) > 0
        max_funding = max((e.get("amount_m", 0) for e in funding_events), default=0)
        latest_funding = min(
            (days_since(e.get("published_at", "")) for e in funding_events), default=999
        )

        # Get company meta from jobs
        company_meta = next((j for j in jobs if j.get("company_slug")), {})
        size = company_meta.get("company_size", "")
        sector = company_meta.get("company_sector", "")
        desc = company_meta.get("company_description", "")
        slug = company_meta.get("company_slug", "")
        location = company_meta.get("location", "France")

        # Score
        s = score_company(
            tech_jobs_count=tech_jobs_count,
            has_funding=has_funding,
            funding_amount_m=max_funding,
            funding_recency_days=latest_funding,
            company_size=size,
            has_cto_job=has_cto,
            has_hr_job=has_hr,
        )

        signal = None
        if has_funding and tech_jobs_count >= 3:
            signal = "both"
        elif has_funding:
            signal = "funding"
        elif tech_jobs_count >= 3:
            signal = "hiring_surge"

        company_id = upsert_company(
            company_name,
            domain="",
            location=location,
            size_range=size,
            industry=sector,
            description=desc[:300] if desc else "",
            wttj_slug=slug,
            score=s,
            signal=signal,
        )

        stats["companies"] += 1
        if verbose and s >= 40:
            priority = get_priority(s)
            sig = get_signal_summary(has_funding, tech_jobs_count, max_funding, latest_funding)
            console.print(f"  {priority} [bold]{company_name}[/bold] score={s} | {sig}")

    # ─── Also score companies already in DB from previous runs ───────────────
    with get_conn() as conn:
        existing = conn.execute("SELECT id, name FROM companies WHERE score = 0").fetchall()

    for row in existing:
        company_name = row["name"]
        with get_conn() as conn:
            jobs = conn.execute(
                "SELECT job_title, tech_tags FROM tech_jobs WHERE company_name = ?",
                (company_name,),
            ).fetchall()
            fundings = conn.execute(
                "SELECT amount_m, published_at FROM funding_events WHERE company_name = ?",
                (company_name,),
            ).fetchall()

        tech_count = len(jobs)
        has_cto = any(CTO_RE.search(j["job_title"] or "") for j in jobs)
        has_hr = any(HR_RE.search(j["job_title"] or "") for j in jobs)
        has_funding = len(fundings) > 0
        max_fund = max((f["amount_m"] or 0 for f in fundings), default=0)
        days_ago = min(
            (days_since(f["published_at"] or "") for f in fundings), default=999
        )

        s = score_company(
            tech_jobs_count=tech_count, has_funding=has_funding,
            funding_amount_m=max_fund, funding_recency_days=days_ago,
            has_cto_job=has_cto, has_hr_job=has_hr,
        )
        with get_conn() as conn:
            conn.execute(
                "UPDATE companies SET score = ? WHERE id = ?", (s, row["id"])
            )

    if verbose:
        console.rule("[bold green]✅ Pipeline terminé")
        console.print(f"  Levées de fonds : [bold]{stats['funding']}[/bold] nouvelles")
        console.print(f"  Offres tech     : [bold]{stats['jobs']}[/bold] nouvelles")
        console.print(f"  Entreprises     : [bold]{stats['companies']}[/bold] mises à jour")

    return stats
