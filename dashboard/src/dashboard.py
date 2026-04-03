"""
Dashboard de veille recrutement tech France.
Vue principale : liste des boîtes à appeler avec leurs signaux.
"""
import sys
import os
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from storage import init_db, get_funding_df, get_jobs_df, get_conn

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Veille Recrutement Tech 🇫🇷",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .signal-funding { background: #1a3a1a; border-left: 4px solid #27ae60; padding: 2px 8px;
                      border-radius: 4px; color: #5dbb6e; font-size: 0.8rem; display: inline-block; }
    .signal-hiring  { background: #1a2a3a; border-left: 4px solid #2d9cdb; padding: 2px 8px;
                      border-radius: 4px; color: #5db8d4; font-size: 0.8rem; display: inline-block; }
    .signal-both    { background: #3a1a1a; border-left: 4px solid #e74c3c; padding: 2px 8px;
                      border-radius: 4px; color: #e87e77; font-size: 0.8rem; display: inline-block; }
    .stDataFrame { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def days_ago_str(date_val) -> str:
    if not date_val or str(date_val) in ("", "nan", "None"):
        return "—"
    try:
        dt_str = str(date_val).split("T")[0].split("+")[0].strip()
        dt = datetime.fromisoformat(dt_str)
        d = (datetime.now() - dt).days
        if d < 0:    return "Aujourd'hui"
        if d == 0:   return "Aujourd'hui"
        if d == 1:   return "Hier"
        if d <= 6:   return f"Il y a {d}j"
        if d <= 29:  return f"Il y a {d//7}sem"
        if d <= 365: return f"Il y a {d//30}mois"
        return f"Il y a {d//365}an"
    except Exception:
        return str(date_val)[:10] if date_val else "—"


def fmt_amount(m) -> str:
    try:
        m = float(m)
        if m <= 0: return ""
        return f"{m:.0f}M€" if m >= 1 else f"{m*1000:.0f}k€"
    except Exception:
        return ""


def run_pipeline_now():
    from pipeline import run_pipeline
    with st.spinner("🔄 Collecte en cours (WTTJ, Indeed, Cadremploi, RSS…)"):
        stats = run_pipeline(verbose=False)
    st.success(
        f"✅ Terminé — {stats['funding']} levées, {stats['jobs']} offres tech"
    )
    st.rerun()


# ─── Build call list ──────────────────────────────────────────────────────────

def get_call_list() -> pd.DataFrame:
    """
    One row per company. Columns:
    - name, signal, job_titles, n_jobs, job_sources, latest_job_date,
      funding_detail, latest_funding_date, latest_signal_date
    """
    with get_conn() as conn:
        # Aggregate jobs per company
        jobs_df = pd.read_sql("""
            SELECT
                company_name,
                COUNT(*) as n_jobs,
                GROUP_CONCAT(DISTINCT source) as job_sources,
                MAX(COALESCE(published_at, scraped_at)) as latest_job_date
            FROM tech_jobs
            GROUP BY company_name
        """, conn)

        # Job titles per company (top 5 most recent)
        titles_df = pd.read_sql("""
            SELECT company_name, job_title,
                   COALESCE(published_at, scraped_at) as dt
            FROM tech_jobs
            ORDER BY company_name, dt DESC
        """, conn)

        # Aggregate funding per company
        fund_df = pd.read_sql("""
            SELECT
                company_name,
                MAX(amount_m) as max_amount,
                MAX(round_type) as round_type,
                MAX(COALESCE(published_at, scraped_at)) as latest_funding_date
            FROM funding_events
            GROUP BY company_name
        """, conn)

    if jobs_df.empty and fund_df.empty:
        return pd.DataFrame()

    # Build job title lists per company
    if not titles_df.empty:
        title_map = (
            titles_df.groupby("company_name")["job_title"]
            .apply(lambda x: list(x.unique()[:8]))
            .reset_index()
            .rename(columns={"job_title": "job_titles_list"})
        )
    else:
        title_map = pd.DataFrame(columns=["company_name", "job_titles_list"])

    # Merge
    if not jobs_df.empty:
        df = jobs_df.merge(title_map, on="company_name", how="left")
    else:
        df = pd.DataFrame(columns=["company_name", "n_jobs", "job_sources", "latest_job_date", "job_titles_list"])

    if not fund_df.empty:
        df = df.merge(fund_df, on="company_name", how="outer") if not df.empty else fund_df.copy()
    else:
        df["max_amount"] = None
        df["round_type"] = None
        df["latest_funding_date"] = None

    # Determine signal
    def get_signal(row):
        has_jobs = pd.notna(row.get("n_jobs")) and int(row.get("n_jobs", 0) or 0) > 0
        has_fund = pd.notna(row.get("latest_funding_date")) and str(row.get("latest_funding_date", "")) not in ("", "nan", "None")
        if has_jobs and has_fund:
            return "both"
        if has_fund:
            return "funding"
        return "hiring"

    df["signal"] = df.apply(get_signal, axis=1)

    # Latest signal date (max of job date and funding date)
    def latest_date(row):
        dates = []
        for col in ["latest_job_date", "latest_funding_date"]:
            v = str(row.get(col, "") or "")
            if v and v not in ("nan", "None", ""):
                dates.append(v)
        return max(dates) if dates else ""

    df["latest_signal_date"] = df.apply(latest_date, axis=1)
    df = df.sort_values("latest_signal_date", ascending=False)
    df = df.fillna("")

    return df


# ─── Sidebar ──────────────────────────────────────────────────────────────────

def render_sidebar():
    st.sidebar.title("📞 Veille Recrutement")
    st.sidebar.caption("Boîtes tech France à appeler")
    st.sidebar.divider()

    # Last update
    with get_conn() as conn:
        last = conn.execute(
            "SELECT MAX(scraped_at) as lu FROM tech_jobs"
        ).fetchone()
    lu = last["lu"] if last and last["lu"] else None
    if lu:
        st.sidebar.caption(f"🕐 Dernière collecte : {days_ago_str(lu)}")
    else:
        st.sidebar.caption("⚠️ Aucune donnée — clique Actualiser")

    if st.sidebar.button("🔄 Actualiser maintenant", use_container_width=True, type="primary"):
        run_pipeline_now()

    st.sidebar.divider()
    st.sidebar.subheader("🔍 Filtres")

    signal_filter = st.sidebar.multiselect(
        "Signal",
        ["💼 Recrute (offres)", "💰 Levée de fonds", "🔥 Les deux"],
        default=["💼 Recrute (offres)", "💰 Levée de fonds", "🔥 Les deux"],
    )

    days_back = st.sidebar.selectbox(
        "Période",
        ["7 derniers jours", "14 derniers jours", "30 derniers jours", "90 derniers jours", "Tout"],
        index=2,
    )

    source_filter = st.sidebar.multiselect(
        "Sources d'offres",
        ["wttj_company", "indeed", "cadremploi"],
        default=["wttj_company", "indeed", "cadremploi"],
        format_func=lambda x: {
            "wttj_company": "Welcome to the Jungle",
            "indeed": "Indeed France",
            "cadremploi": "Cadremploi",
        }.get(x, x),
    )

    keyword = st.sidebar.text_input("🔎 Recherche entreprise ou poste", "")

    st.sidebar.divider()
    st.sidebar.caption(
        "**Sources actives :**\n"
        "- Welcome to the Jungle\n"
        "- Indeed France (RSS)\n"
        "- Cadremploi\n"
        "- Maddyness / Frenchweb (levées)"
    )

    return signal_filter, days_back, source_filter, keyword


# ─── Main call list tab ────────────────────────────────────────────────────────

def render_call_list(signal_filter, days_back, source_filter, keyword):
    st.subheader("📞 Boîtes à appeler maintenant")

    df = get_call_list()
    if df.empty:
        st.info("Aucune donnée. Clique **🔄 Actualiser maintenant** dans la sidebar.")
        return

    # Filter by period
    cutoff_map = {
        "7 derniers jours": 7,
        "14 derniers jours": 14,
        "30 derniers jours": 30,
        "90 derniers jours": 90,
        "Tout": 9999,
    }
    cutoff_days = cutoff_map.get(days_back, 30)
    cutoff_date = (datetime.now() - timedelta(days=cutoff_days)).isoformat()

    df = df[df["latest_signal_date"] >= cutoff_date]

    # Filter by signal
    signal_map = {
        "💼 Recrute (offres)": "hiring",
        "💰 Levée de fonds": "funding",
        "🔥 Les deux": "both",
    }
    if signal_filter:
        allowed = {signal_map[s] for s in signal_filter}
        df = df[df["signal"].isin(allowed)]

    # Filter by keyword
    if keyword:
        kw = keyword.lower()
        titles_mask = df["job_titles_list"].apply(
            lambda x: any(kw in t.lower() for t in (x if isinstance(x, list) else []))
        )
        df = df[df["company_name"].str.lower().str.contains(kw, na=False) | titles_mask]

    if df.empty:
        st.warning("Aucune entreprise avec ces filtres.")
        return

    # ── KPI row ──
    c1, c2, c3, c4 = st.columns(4)
    n_hiring = len(df[df["signal"].isin(["hiring", "both"])])
    n_funding = len(df[df["signal"].isin(["funding", "both"])])
    n_both = len(df[df["signal"] == "both"])

    for col, val, label, color in [
        (c1, len(df),     "🏢 Boîtes détectées", "#2d9cdb"),
        (c2, n_hiring,    "💼 En recrutement",    "#27ae60"),
        (c3, n_funding,   "💰 Ont levé des fonds","#f39c12"),
        (c4, n_both,      "🔥 Signal double",     "#e74c3c"),
    ]:
        with col:
            st.markdown(f"""
            <div style="background:{color}22;border:1px solid {color}66;
                        border-radius:8px;padding:14px;text-align:center;">
                <div style="font-size:1.8rem;font-weight:bold;color:{color};">{val}</div>
                <div style="font-size:0.8rem;color:#aaa;margin-top:2px;">{label}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Build display table ──
    rows = []
    for _, row in df.iterrows():
        signal = row.get("signal", "")

        # Signal badge
        if signal == "both":
            signal_label = "🔥 Levée + Recrute"
        elif signal == "funding":
            signal_label = "💰 Levée de fonds"
        else:
            signal_label = "💼 Recrute"

        # Job titles summary
        titles_list = row.get("job_titles_list") or []
        if isinstance(titles_list, str):
            import ast
            try:
                titles_list = ast.literal_eval(titles_list)
            except Exception:
                titles_list = [titles_list] if titles_list else []

        n_jobs = int(row.get("n_jobs", 0) or 0)
        if titles_list:
            shown = titles_list[:4]
            more = n_jobs - len(shown)
            titles_str = ", ".join(shown)
            if more > 0:
                titles_str += f" (+{more} autres)"
        else:
            titles_str = ""

        # Funding detail
        amt = fmt_amount(row.get("max_amount", ""))
        rtype = str(row.get("round_type", "") or "").strip()
        fund_str = ""
        if amt:
            fund_str = f"{amt}"
            if rtype and rtype.lower() not in ("", "nan", "none"):
                fund_str += f" — {rtype}"

        # Raison column combines both
        raison_parts = []
        if titles_str:
            raison_parts.append(f"Recrute : {titles_str}")
        if fund_str:
            raison_parts.append(f"Levée : {fund_str}")
        raison = " | ".join(raison_parts)

        # Sources
        sources_raw = str(row.get("job_sources", "") or "")
        source_names = {
            "wttj_company": "WTTJ",
            "indeed": "Indeed",
            "cadremploi": "Cadremploi",
            "wttj_algolia": "WTTJ",
        }
        sources_str = ", ".join(
            source_names.get(s.strip(), s.strip())
            for s in sources_raw.split(",")
            if s.strip()
        )

        rows.append({
            "Entreprise": row["company_name"],
            "Signal": signal_label,
            "Postes / Levée": raison,
            "Sources": sources_str,
            "Dernière activité": days_ago_str(row.get("latest_signal_date", "")),
            "_date": str(row.get("latest_signal_date", "")),
        })

    display = pd.DataFrame(rows)

    st.dataframe(
        display.drop(columns=["_date"]),
        use_container_width=True,
        hide_index=True,
        height=600,
        column_config={
            "Entreprise": st.column_config.TextColumn("Entreprise", width=160),
            "Signal": st.column_config.TextColumn("Signal", width=160),
            "Postes / Levée": st.column_config.TextColumn("Postes / Levée", width=500),
            "Sources": st.column_config.TextColumn("Sources", width=130),
            "Dernière activité": st.column_config.TextColumn("Dernière activité", width=140),
        },
    )

    # Download CSV
    csv = display.drop(columns=["_date"]).to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 Exporter liste d'appels CSV",
        data=csv,
        file_name=f"boites_a_appeler_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )


# ─── Tab 2 : Levées de fonds ──────────────────────────────────────────────────

def render_funding_tab():
    st.subheader("💰 Levées de fonds détectées")

    df = get_funding_df()
    if df.empty:
        st.info("Aucune levée détectée. Lance le pipeline.")
        return

    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")

    # Table
    display = df[[
        "company_name", "amount_m", "round_type", "source",
        "article_title", "article_url", "published_at"
    ]].copy().rename(columns={
        "company_name": "Entreprise",
        "amount_m": "Montant",
        "round_type": "Tour",
        "source": "Source",
        "article_title": "Article",
        "article_url": "Lien",
        "published_at": "Date",
    })

    display["Montant"] = display["Montant"].apply(fmt_amount)
    display["Date"] = display["Date"].apply(days_ago_str)

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Lien": st.column_config.LinkColumn("Lien", width=80),
            "Entreprise": st.column_config.TextColumn("Entreprise", width=180),
            "Article": st.column_config.TextColumn("Article", width=320),
        },
    )


# ─── Tab 3 : Toutes les offres ────────────────────────────────────────────────

def render_jobs_tab():
    st.subheader("💼 Toutes les offres tech collectées")

    df = get_jobs_df()
    if df.empty:
        st.info("Aucune offre. Lance le pipeline.")
        return

    # Stats by source
    c1, c2 = st.columns([1, 2])
    with c1:
        src_counts = df["source"].value_counts().reset_index()
        src_counts.columns = ["Source", "Offres"]
        src_counts["Source"] = src_counts["Source"].map({
            "wttj_company": "Welcome to the Jungle",
            "indeed": "Indeed France",
            "cadremploi": "Cadremploi",
            "wttj_algolia": "WTTJ Algolia",
        }).fillna(src_counts["Source"])
        fig = px.bar(
            src_counts, x="Offres", y="Source", orientation="h",
            title="Offres par source",
            color_discrete_sequence=["#2d9cdb"],
        )
        fig.update_layout(height=220, margin=dict(t=35, b=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        top = df.groupby("company_name").size().reset_index(name="n")
        top = top.sort_values("n", ascending=False).head(15)
        fig2 = px.bar(
            top, x="n", y="company_name", orientation="h",
            title="Top 15 entreprises",
            color_discrete_sequence=["#27ae60"],
        )
        fig2.update_layout(height=340, margin=dict(t=35, b=10), showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    # Searchable table
    search = st.text_input("🔎 Filtrer par entreprise ou poste", "")
    display = df[["company_name", "job_title", "location", "source", "job_url",
                  "published_at", "scraped_at"]].copy()
    display.columns = ["Entreprise", "Poste", "Ville", "Source", "Lien", "Publiée", "Collectée"]
    display["Publiée"] = display["Publiée"].apply(days_ago_str)
    display["Collectée"] = display["Collectée"].apply(days_ago_str)
    display["Source"] = display["Source"].map({
        "wttj_company": "WTTJ",
        "indeed": "Indeed",
        "cadremploi": "Cadremploi",
    }).fillna(display["Source"])

    if search:
        mask = (
            display["Entreprise"].str.contains(search, case=False, na=False)
            | display["Poste"].str.contains(search, case=False, na=False)
        )
        display = display[mask]

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=500,
        column_config={
            "Lien": st.column_config.LinkColumn("Lien", width=70),
            "Poste": st.column_config.TextColumn("Poste", width=280),
        },
    )


# ─── Tab 4 : CRM ──────────────────────────────────────────────────────────────

def render_crm_tab():
    st.subheader("📋 Suivi des prospects")

    with st.expander("➕ Ajouter un prospect", expanded=False):
        with st.form("add_prospect"):
            c1, c2 = st.columns(2)
            company = c1.text_input("Entreprise *")
            contact = c2.text_input("Nom du contact")
            email = c1.text_input("Email")
            linkedin = c2.text_input("LinkedIn URL")
            status = c1.selectbox(
                "Statut",
                ["new", "contacted", "replied", "deal", "lost"],
                format_func=lambda x: {
                    "new": "🆕 Nouveau", "contacted": "📤 Contacté",
                    "replied": "💬 Répondu", "deal": "✅ Deal", "lost": "❌ Perdu"
                }.get(x, x),
            )
            priority = c2.selectbox(
                "Priorité", ["high", "medium", "low"],
                format_func=lambda x: {"high": "🔥 Haute", "medium": "🟡 Moyenne", "low": "🔵 Faible"}.get(x, x)
            )
            notes = st.text_area("Notes")
            if st.form_submit_button("✅ Ajouter"):
                if company:
                    with get_conn() as conn:
                        conn.execute(
                            """INSERT OR IGNORE INTO prospects
                               (company_name, contact_name, contact_email, contact_linkedin,
                                status, priority, notes, created_at, updated_at)
                               VALUES (?,?,?,?,?,?,?,?,?)""",
                            (company, contact, email, linkedin, status, priority, notes,
                             datetime.now().isoformat(), datetime.now().isoformat()),
                        )
                    st.success(f"✅ {company} ajouté !")
                    st.rerun()

    with get_conn() as conn:
        df = pd.read_sql("SELECT * FROM prospects ORDER BY created_at DESC", conn)

    if df.empty:
        st.info("Aucun prospect. Ajoute-en un avec le formulaire ci-dessus.")
        return

    status_labels = {
        "new": ("🆕 Nouveaux", "#1a2a3a"),
        "contacted": ("📤 Contactés", "#1a2a1a"),
        "replied": ("💬 Ont répondu", "#2a1a2a"),
        "deal": ("✅ Deals", "#1a3a1a"),
        "lost": ("❌ Perdus", "#2a1a1a"),
    }
    cols = st.columns(len(status_labels))
    for col, (status, (label, bg)) in zip(cols, status_labels.items()):
        subset = df[df["status"] == status]
        col.markdown(f"**{label}** ({len(subset)})")
        for _, row in subset.iterrows():
            col.markdown(f"""
            <div style="background:{bg};border-radius:6px;padding:10px;
                        margin-bottom:6px;font-size:0.83rem;border-left:3px solid #555;">
                <b>{row['company_name']}</b><br>
                <span style="color:#aaa;">{row.get('contact_name','') or ''}</span><br>
                <span style="color:#888;font-size:0.75rem;">{(row.get('notes','') or '')[:60]}</span>
            </div>
            """, unsafe_allow_html=True)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    init_db()

    st.markdown("""
    <h1 style="text-align:center;font-size:2rem;margin-bottom:0;color:#fff;">
        📞 Veille Recrutement Tech France
    </h1>
    <p style="text-align:center;color:#888;margin-top:4px;margin-bottom:1rem;">
        Identifie les boîtes à appeler · Levées de fonds · Offres actives
    </p>
    """, unsafe_allow_html=True)

    signal_filter, days_back, source_filter, keyword = render_sidebar()

    tab1, tab2, tab3, tab4 = st.tabs([
        "📞 Boîtes à appeler",
        "💰 Levées de fonds",
        "💼 Toutes les offres",
        "📋 Suivi CRM",
    ])

    with tab1:
        render_call_list(signal_filter, days_back, source_filter, keyword)
    with tab2:
        render_funding_tab()
    with tab3:
        render_jobs_tab()
    with tab4:
        render_crm_tab()

    st.sidebar.caption(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}")


if __name__ == "__main__":
    main()
