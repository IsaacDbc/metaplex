"""
Scoring des entreprises pour prioriser les prospects cabinet de recrutement.
"""
from datetime import datetime, timedelta


def score_company(
    tech_jobs_count: int = 0,
    has_funding: bool = False,
    funding_amount_m: float = 0,
    funding_recency_days: int = 999,
    company_size: str = "",
    has_cto_job: bool = False,
    has_hr_job: bool = False,
    is_french_tech: bool = False,
) -> float:
    """
    Score 0-100 estimant l'intérêt d'une boîte pour un cabinet de recrutement.

    Critères:
    - Levée de fonds récente → besoin de recrutement immédiat
    - Nombre d'offres tech → volume potentiel de missions
    - Taille de boîte → trop petite = pas de budget, trop grande = DRH interne
    - Poste CTO/Head of Eng ouvert → besoin de profil senior
    - Label French Tech → boîte sérieuse avec croissance
    """
    score = 0.0

    # ─── Levée de fonds ──────────────────────────────────────────────────────
    if has_funding:
        score += 25  # Base: boîte qui a levé = budget pour recruter

        # Montant
        if funding_amount_m >= 50:
            score += 15
        elif funding_amount_m >= 20:
            score += 10
        elif funding_amount_m >= 5:
            score += 5
        elif funding_amount_m >= 1:
            score += 2

        # Récence de la levée
        if funding_recency_days <= 30:
            score += 20   # Très récente → window d'opportunité
        elif funding_recency_days <= 90:
            score += 12
        elif funding_recency_days <= 180:
            score += 6
        elif funding_recency_days <= 365:
            score += 2

    # ─── Offres tech actives ──────────────────────────────────────────────────
    if tech_jobs_count >= 20:
        score += 20
    elif tech_jobs_count >= 10:
        score += 15
    elif tech_jobs_count >= 5:
        score += 10
    elif tech_jobs_count >= 3:
        score += 5
    elif tech_jobs_count >= 1:
        score += 2

    # ─── Postes stratégiques ouverts ─────────────────────────────────────────
    if has_cto_job:
        score += 10  # Recrutement CTO → fait souvent appel à un cabinet
    if has_hr_job:
        score += 5   # Recrutent des RH → en plein scaling

    # ─── Taille optimale (10-500 pour cabinet) ───────────────────────────────
    size_map = {
        "1-10": -5,       # Trop petite
        "11-50": 8,
        "51-100": 12,
        "101-250": 15,    # Idéal
        "251-500": 12,
        "501-1000": 8,
        "1001-5000": 3,
        "+5000": -5,       # Trop grande (DRH interne)
    }
    score += size_map.get(company_size, 0)

    # ─── Label French Tech ────────────────────────────────────────────────────
    if is_french_tech:
        score += 8

    return min(100, max(0, round(score, 1)))


def get_priority(score: float) -> str:
    if score >= 70:
        return "🔥 Haute"
    elif score >= 45:
        return "🟡 Moyenne"
    elif score >= 20:
        return "🔵 Faible"
    else:
        return "⚪ Très faible"


def get_signal_summary(has_funding: bool, tech_jobs: int, funding_amount: float, days_ago: int) -> str:
    signals = []
    if has_funding:
        recency = f"il y a {days_ago}j" if days_ago < 365 else ""
        signals.append(f"💰 Levée {f'{funding_amount:.0f}M€ ' if funding_amount else ''}{recency}")
    if tech_jobs >= 10:
        signals.append(f"📈 {tech_jobs} offres tech actives")
    elif tech_jobs >= 3:
        signals.append(f"🔧 {tech_jobs} offres tech")
    return " | ".join(signals) if signals else "—"
