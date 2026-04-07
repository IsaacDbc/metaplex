"""
Générateur du digest email quotidien Techunt.
Construit un email HTML avec :
- Top 5 boîtes à appeler aujourd'hui
- Nouvelles levées de fonds (24h)
- Nouvelles offres tech (24h)
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from storage import get_conn

SOURCE_LABELS = {
    "wttj_company": "WTTJ",
    "indeed": "Indeed",
    "cadremploi": "Cadremploi",
    "greenhouse": "Greenhouse",
    "lever": "Lever",
}

SIGNAL_LABELS = {
    "both": "💰📈 Levée + Recrutement",
    "funding": "💰 Levée de fonds",
    "hiring": "📈 Recrutement actif",
    "hiring_surge": "📈 Recrutement actif",
}


def _days_ago(date_str: str) -> str:
    if not date_str or str(date_str) in ("", "nan", "None"):
        return ""
    try:
        dt = datetime.fromisoformat(str(date_str).split("T")[0].split("+")[0])
        d = (datetime.now() - dt).days
        if d <= 0:  return "Aujourd'hui"
        if d == 1:  return "Hier"
        if d <= 6:  return f"Il y a {d}j"
        if d <= 29: return f"Il y a {d//7}sem"
        return f"Il y a {d//30}mois"
    except Exception:
        return ""


def _fmt_amount(m) -> str:
    try:
        m = float(m or 0)
        if m <= 0: return ""
        return f"{m:.0f}M€" if m >= 1 else f"{m*1000:.0f}k€"
    except Exception:
        return ""


def get_digest_data(days_back: int = 1) -> dict:
    """Fetch data from the last N days for the digest."""
    cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()

    with get_conn() as conn:
        # New funding events
        new_funding = conn.execute("""
            SELECT company_name, amount_m, round_type, article_title, article_url,
                   source, published_at
            FROM funding_events
            WHERE COALESCE(published_at, scraped_at) >= ?
            ORDER BY COALESCE(published_at, scraped_at) DESC
            LIMIT 20
        """, (cutoff,)).fetchall()

        # New tech jobs
        new_jobs = conn.execute("""
            SELECT company_name, job_title, source, job_url,
                   COALESCE(published_at, scraped_at) as dt
            FROM tech_jobs
            WHERE COALESCE(published_at, scraped_at) >= ?
            ORDER BY dt DESC
            LIMIT 100
        """, (cutoff,)).fetchall()

        # Top 5 companies to call (most signals in last 7 days)
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        top_companies_raw = conn.execute("""
            SELECT
                company_name,
                COUNT(DISTINCT job_title) as n_jobs,
                GROUP_CONCAT(DISTINCT job_title) as job_titles,
                GROUP_CONCAT(DISTINCT source) as sources,
                MAX(COALESCE(published_at, scraped_at)) as latest_job_date
            FROM tech_jobs
            WHERE COALESCE(published_at, scraped_at) >= ?
            GROUP BY company_name
            ORDER BY n_jobs DESC
            LIMIT 5
        """, (week_ago,)).fetchall()

        # Funding for top companies
        funding_by_company = {}
        for row in conn.execute("""
            SELECT company_name, MAX(amount_m) as amount, MAX(round_type) as round_type,
                   MAX(COALESCE(published_at, scraped_at)) as dt
            FROM funding_events
            GROUP BY company_name
        """).fetchall():
            funding_by_company[row["company_name"]] = dict(row)

        # Stats
        total_companies = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        total_jobs = conn.execute("SELECT COUNT(*) FROM tech_jobs").fetchone()[0]
        total_funding = conn.execute("SELECT COUNT(*) FROM funding_events").fetchone()[0]

    # Build top companies list
    top_companies = []
    for row in top_companies_raw:
        name = row["company_name"]
        titles = [t.strip() for t in (row["job_titles"] or "").split(",") if t.strip()][:5]
        sources = [SOURCE_LABELS.get(s.strip(), s.strip()) for s in (row["sources"] or "").split(",") if s.strip()]
        fund = funding_by_company.get(name, {})
        top_companies.append({
            "name": name,
            "n_jobs": row["n_jobs"],
            "job_titles": titles,
            "sources": list(set(sources)),
            "latest_job_date": row["latest_job_date"],
            "funding_amount": _fmt_amount(fund.get("amount", 0)),
            "funding_round": fund.get("round_type", ""),
        })

    return {
        "date": datetime.now().strftime("%A %d %B %Y").capitalize(),
        "new_funding": [dict(r) for r in new_funding],
        "new_jobs_by_company": _aggregate_jobs(new_jobs),
        "top_companies": top_companies,
        "stats": {
            "total_companies": total_companies,
            "total_jobs": total_jobs,
            "total_funding": total_funding,
            "new_funding_count": len(new_funding),
            "new_jobs_count": len(new_jobs),
        },
    }


def _aggregate_jobs(rows) -> list[dict]:
    """Group jobs by company."""
    from collections import defaultdict
    by_co: dict = defaultdict(lambda: {"titles": [], "sources": set(), "latest": ""})
    for row in rows:
        co = row["company_name"]
        by_co[co]["titles"].append(row["job_title"])
        by_co[co]["sources"].add(SOURCE_LABELS.get(row["source"] or "", row["source"] or ""))
        dt = str(row["dt"] or "")
        if dt > by_co[co]["latest"]:
            by_co[co]["latest"] = dt

    result = []
    for name, data in sorted(by_co.items(), key=lambda x: x[1]["latest"], reverse=True):
        result.append({
            "name": name,
            "titles": list(dict.fromkeys(data["titles"]))[:5],  # unique, keep order
            "n_jobs": len(data["titles"]),
            "sources": list(data["sources"]),
            "latest": _days_ago(data["latest"]),
        })
    return result


def build_html(data: dict) -> str:
    """Build the full HTML email."""
    date_str = data["date"]
    stats = data["stats"]
    top = data["top_companies"]
    new_funding = data["new_funding"]
    new_jobs = data["new_jobs_by_company"]

    # ── Top companies rows
    top_rows = ""
    for i, co in enumerate(top, 1):
        titles_str = ", ".join(co["job_titles"])
        if co["n_jobs"] > len(co["job_titles"]):
            titles_str += f" (+{co['n_jobs'] - len(co['job_titles'])} autres)"
        fund_badge = ""
        if co["funding_amount"]:
            fund_badge = f' <span style="background:#27ae60;color:#fff;border-radius:4px;padding:1px 6px;font-size:11px;">{co["funding_amount"]}</span>'
        sources_str = " · ".join(co["sources"])
        top_rows += f"""
        <tr style="border-bottom:1px solid #2a2a3a;">
          <td style="padding:10px 8px;font-weight:bold;color:#fff;width:28%;">
            {i}. {co["name"]}{fund_badge}
          </td>
          <td style="padding:10px 8px;color:#b0b8c8;font-size:13px;">{titles_str}</td>
          <td style="padding:10px 8px;color:#7a8a9a;font-size:12px;white-space:nowrap;">{sources_str}</td>
          <td style="padding:10px 8px;color:#5d9cdb;font-size:12px;white-space:nowrap;">{_days_ago(co["latest_job_date"])}</td>
        </tr>"""

    # ── New funding rows
    funding_rows = ""
    for f in new_funding[:10]:
        amt = _fmt_amount(f.get("amount_m", 0))
        amt_badge = f'<span style="background:#27ae60;color:#fff;border-radius:4px;padding:1px 6px;font-size:11px;margin-left:6px;">{amt}</span>' if amt else ""
        rtype = f.get("round_type", "") or ""
        link = f.get("article_url", "") or "#"
        title = (f.get("article_title", "") or f.get("company_name", ""))[:60]
        source = f.get("source", "")
        funding_rows += f"""
        <tr style="border-bottom:1px solid #2a2a3a;">
          <td style="padding:8px;font-weight:bold;color:#fff;">{f["company_name"]}{amt_badge}</td>
          <td style="padding:8px;color:#7a8a9a;font-size:12px;">{rtype}</td>
          <td style="padding:8px;font-size:12px;"><a href="{link}" style="color:#5d9cdb;text-decoration:none;">{title}</a></td>
          <td style="padding:8px;color:#7a8a9a;font-size:12px;">{source}</td>
          <td style="padding:8px;color:#5d9cdb;font-size:12px;">{_days_ago(f.get("published_at",""))}</td>
        </tr>"""

    if not funding_rows:
        funding_rows = '<tr><td colspan="5" style="padding:12px;color:#555;text-align:center;">Aucune levée détectée aujourd\'hui</td></tr>'

    # ── New jobs rows
    jobs_rows = ""
    for co in new_jobs[:15]:
        titles_str = ", ".join(co["titles"])
        if co["n_jobs"] > len(co["titles"]):
            titles_str += f" +{co['n_jobs'] - len(co['titles'])}"
        sources_str = " · ".join(co["sources"])
        jobs_rows += f"""
        <tr style="border-bottom:1px solid #2a2a3a;">
          <td style="padding:8px;font-weight:bold;color:#fff;">{co["name"]}</td>
          <td style="padding:8px;color:#b0b8c8;font-size:13px;">{titles_str}</td>
          <td style="padding:8px;color:#7a8a9a;font-size:12px;">{sources_str}</td>
          <td style="padding:8px;color:#5d9cdb;font-size:12px;">{co["latest"]}</td>
        </tr>"""

    if not jobs_rows:
        jobs_rows = '<tr><td colspan="4" style="padding:12px;color:#555;text-align:center;">Aucune nouvelle offre aujourd\'hui</td></tr>'

    new_funding_count = stats["new_funding_count"]
    new_jobs_count = stats["new_jobs_count"]
    subject_hint = f"{new_funding_count} levée{'s' if new_funding_count != 1 else ''}, {new_jobs_count} offre{'s' if new_jobs_count != 1 else ''}"

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Techunt Veille — {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#0e1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#0e1117;padding:24px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;">

  <!-- HEADER -->
  <tr>
    <td style="background:linear-gradient(135deg,#1e3a5f,#1a6a9f);border-radius:12px 12px 0 0;padding:28px 32px;">
      <div style="font-size:11px;color:#7ac0ef;letter-spacing:2px;text-transform:uppercase;margin-bottom:6px;">Techunt · Veille recrutement</div>
      <h1 style="margin:0;font-size:22px;color:#fff;font-weight:700;">📞 Boîtes à appeler aujourd'hui</h1>
      <div style="margin-top:6px;color:#a8cce8;font-size:14px;">{date_str} · {subject_hint}</div>
    </td>
  </tr>

  <!-- KPI ROW -->
  <tr>
    <td style="background:#141824;padding:0 0 2px 0;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td width="33%" style="padding:16px;text-align:center;border-right:1px solid #1e2535;">
            <div style="font-size:28px;font-weight:bold;color:#e74c3c;">{new_funding_count}</div>
            <div style="font-size:12px;color:#7a8a9a;margin-top:3px;">💰 Nouvelles levées</div>
          </td>
          <td width="33%" style="padding:16px;text-align:center;border-right:1px solid #1e2535;">
            <div style="font-size:28px;font-weight:bold;color:#27ae60;">{new_jobs_count}</div>
            <div style="font-size:12px;color:#7a8a9a;margin-top:3px;">💼 Nouvelles offres tech</div>
          </td>
          <td width="33%" style="padding:16px;text-align:center;">
            <div style="font-size:28px;font-weight:bold;color:#2d9cdb;">{len(top)}</div>
            <div style="font-size:12px;color:#7a8a9a;margin-top:3px;">🎯 Top boîtes à appeler</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- TOP 5 TO CALL -->
  <tr>
    <td style="background:#141824;padding:24px 32px 16px;">
      <h2 style="margin:0 0 14px;font-size:15px;color:#fff;border-left:3px solid #e74c3c;padding-left:10px;">
        🔥 Top {len(top)} boîtes à appeler cette semaine
      </h2>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
        <tr style="background:#1a2235;">
          <th style="padding:8px;text-align:left;color:#7a8a9a;font-size:11px;font-weight:600;text-transform:uppercase;">Entreprise</th>
          <th style="padding:8px;text-align:left;color:#7a8a9a;font-size:11px;font-weight:600;text-transform:uppercase;">Postes ouverts</th>
          <th style="padding:8px;text-align:left;color:#7a8a9a;font-size:11px;font-weight:600;text-transform:uppercase;">Source</th>
          <th style="padding:8px;text-align:left;color:#7a8a9a;font-size:11px;font-weight:600;text-transform:uppercase;">Quand</th>
        </tr>
        {top_rows if top_rows else '<tr><td colspan="4" style="padding:12px;color:#555;text-align:center;">Lance le pipeline pour collecter les données</td></tr>'}
      </table>
    </td>
  </tr>

  <!-- DIVIDER -->
  <tr><td style="background:#141824;padding:0 32px;"><hr style="border:none;border-top:1px solid #1e2535;"></td></tr>

  <!-- NEW FUNDING -->
  <tr>
    <td style="background:#141824;padding:16px 32px;">
      <h2 style="margin:0 0 14px;font-size:15px;color:#fff;border-left:3px solid #27ae60;padding-left:10px;">
        💰 Nouvelles levées de fonds
      </h2>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
        <tr style="background:#1a2235;">
          <th style="padding:8px;text-align:left;color:#7a8a9a;font-size:11px;font-weight:600;text-transform:uppercase;">Entreprise</th>
          <th style="padding:8px;text-align:left;color:#7a8a9a;font-size:11px;font-weight:600;text-transform:uppercase;">Tour</th>
          <th style="padding:8px;text-align:left;color:#7a8a9a;font-size:11px;font-weight:600;text-transform:uppercase;">Article</th>
          <th style="padding:8px;text-align:left;color:#7a8a9a;font-size:11px;font-weight:600;text-transform:uppercase;">Source</th>
          <th style="padding:8px;text-align:left;color:#7a8a9a;font-size:11px;font-weight:600;text-transform:uppercase;">Date</th>
        </tr>
        {funding_rows}
      </table>
    </td>
  </tr>

  <!-- DIVIDER -->
  <tr><td style="background:#141824;padding:0 32px;"><hr style="border:none;border-top:1px solid #1e2535;"></td></tr>

  <!-- NEW JOBS -->
  <tr>
    <td style="background:#141824;padding:16px 32px 24px;">
      <h2 style="margin:0 0 14px;font-size:15px;color:#fff;border-left:3px solid #2d9cdb;padding-left:10px;">
        💼 Nouvelles offres tech
      </h2>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
        <tr style="background:#1a2235;">
          <th style="padding:8px;text-align:left;color:#7a8a9a;font-size:11px;font-weight:600;text-transform:uppercase;">Entreprise</th>
          <th style="padding:8px;text-align:left;color:#7a8a9a;font-size:11px;font-weight:600;text-transform:uppercase;">Postes</th>
          <th style="padding:8px;text-align:left;color:#7a8a9a;font-size:11px;font-weight:600;text-transform:uppercase;">Source</th>
          <th style="padding:8px;text-align:left;color:#7a8a9a;font-size:11px;font-weight:600;text-transform:uppercase;">Quand</th>
        </tr>
        {jobs_rows}
      </table>
    </td>
  </tr>

  <!-- FOOTER -->
  <tr>
    <td style="background:#0a0e18;border-radius:0 0 12px 12px;padding:20px 32px;border-top:1px solid #1e2535;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="color:#555;font-size:12px;">
            Techunt · Veille Recrutement Tech France<br>
            <span style="font-size:11px;">Base : {stats["total_companies"]} entreprises · {stats["total_jobs"]} offres · {stats["total_funding"]} levées</span>
          </td>
          <td align="right">
            <span style="color:#7a8a9a;font-size:11px;">Envoyé automatiquement à 8h00</span>
          </td>
        </tr>
      </table>
    </td>
  </tr>

</table>
</td></tr>
</table>

</body>
</html>"""


def get_subject(data: dict) -> str:
    stats = data["stats"]
    n_f = stats["new_funding_count"]
    n_j = stats["new_jobs_count"]
    parts = []
    if n_f > 0:
        parts.append(f"{n_f} levée{'s' if n_f > 1 else ''}")
    if n_j > 0:
        parts.append(f"{n_j} offre{'s' if n_j > 1 else ''} tech")
    summary = " · ".join(parts) if parts else "Veille du jour"
    return f"📞 Techunt — {summary} · {datetime.now().strftime('%d/%m/%Y')}"
