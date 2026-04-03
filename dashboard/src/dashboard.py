"""
Tableau de bord Streamlit — Veille Recrutement Tech France
Mise à jour automatique toutes les heures via APScheduler.

Lancer avec : streamlit run dashboard.py
"""
import json
import sys
import os
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from storage import (
    init_db, get_companies_df, get_funding_df,
    get_jobs_df, get_prospects_df, get_stats, get_conn,
)
from scoring import get_priority, get_signal_summary

# ─── Config page ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Veille Recrutement Tech 🇫🇷",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS custom ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1e3a5f, #2d6a9f);
        border-radius: 12px;
        padding: 20px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .metric-card .value { font-size: 2.5rem; font-weight: bold; }
    .metric-card .label { font-size: 0.85rem; opacity: 0.85; margin-top: 4px; }
    .hot-badge {
        background: #ff4b4b; color: white; border-radius: 20px;
        padding: 2px 10px; font-size: 0.75rem; font-weight: bold;
    }
    .signal-badge {
        background: #ffd700; color: #333; border-radius: 20px;
        padding: 2px 10px; font-size: 0.75rem; font-weight: bold;
    }
    div[data-testid="stDataFrame"] { border-radius: 8px; }
    .stTabs [data-baseweb="tab"] { font-size: 1rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def format_amount(m: float) -> str:
    if not m or m == 0:
        return "—"
    return f"{m:.0f}M€" if m >= 1 else f"{m*1000:.0f}k€"


def days_ago_str(date_str: str) -> str:
    if not date_str:
        return "—"
    try:
        dt = datetime.fromisoformat(str(date_str).split("T")[0])
        d = (datetime.now() - dt).days
        if d == 0: return "Aujourd'hui"
        if d == 1: return "Hier"
        if d < 7: return f"Il y a {d}j"
        if d < 30: return f"Il y a {d//7}sem"
        if d < 365: return f"Il y a {d//30}mois"
        return f"Il y a {d//365}an"
    except Exception:
        return "—"


def run_pipeline_cached():
    """Run pipeline with spinner."""
    from pipeline import run_pipeline
    with st.spinner("🔄 Collecte des données en cours…"):
        stats = run_pipeline(verbose=False)
    st.success(f"✅ Terminé — {stats['funding']} levées, {stats['jobs']} offres tech")
    st.rerun()


# ─── Sidebar ──────────────────────────────────────────────────────────────────

def render_sidebar():
    st.sidebar.image(
        "https://img.icons8.com/color/96/000000/target.png",
        width=60,
    )
    st.sidebar.title("Veille Recrutement Tech")
    st.sidebar.caption("🇫🇷 Startups & Scale-ups France")

    st.sidebar.divider()

    # Last update
    with get_conn() as conn:
        last = conn.execute(
            "SELECT MAX(last_updated) as lu FROM companies"
        ).fetchone()
    last_update = last["lu"] if last and last["lu"] else None
    if last_update:
        st.sidebar.caption(f"🕐 Dernière MàJ : {days_ago_str(last_update)}")
    else:
        st.sidebar.caption("🕐 Aucune donnée — lance le pipeline")

    # Manual refresh
    if st.sidebar.button("🔄 Actualiser maintenant", use_container_width=True):
        run_pipeline_cached()

    st.sidebar.divider()

    # Filters
    st.sidebar.subheader("🔍 Filtres")

    score_min = st.sidebar.slider("Score minimum", 0, 100, 20, 5)
    signal_filter = st.sidebar.multiselect(
        "Signaux",
        ["💰 Levée de fonds", "📈 Recrutement actif", "🔥 Les deux"],
        default=["💰 Levée de fonds", "📈 Recrutement actif", "🔥 Les deux"],
    )
    days_filter = st.sidebar.selectbox(
        "Période",
        ["7 derniers jours", "30 derniers jours", "90 derniers jours", "Tout"],
        index=1,
    )

    st.sidebar.divider()
    st.sidebar.caption("💡 **Cabinet de recrutement tech**\nIdentifie les boîtes qui ont besoin de toi")

    return score_min, signal_filter, days_filter


# ─── KPI Cards ────────────────────────────────────────────────────────────────

def render_kpis(stats: dict):
    c1, c2, c3, c4, c5 = st.columns(5)
    kpis = [
        (c1, stats.get("hot_prospects", 0), "🔥 Prospects chauds", "#ff6b35"),
        (c2, stats.get("funding_events", 0), "💰 Levées détectées", "#2d9cdb"),
        (c3, stats.get("tech_jobs", 0), "💼 Offres tech", "#27ae60"),
        (c4, stats.get("companies", 0), "🏢 Entreprises", "#9b59b6"),
        (c5, 0, "📤 Contactées", "#e67e22"),
    ]
    for col, val, label, color in kpis:
        with col:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,{color}cc,{color}88);
                        border-radius:10px;padding:18px;text-align:center;color:white;
                        box-shadow:0 3px 10px rgba(0,0,0,0.15);">
                <div style="font-size:2rem;font-weight:bold;">{val}</div>
                <div style="font-size:0.8rem;opacity:0.9;margin-top:4px;">{label}</div>
            </div>
            """, unsafe_allow_html=True)


# ─── Tab 1 : Prospects ────────────────────────────────────────────────────────

def render_prospects_tab(score_min: int, signal_filter: list, days_filter: str):
    st.subheader("🎯 Entreprises à contacter")

    df = get_companies_df()
    if df.empty:
        st.info("Aucune donnée. Clique sur **🔄 Actualiser** dans la sidebar pour lancer la collecte.")
        return

    # Apply filters
    df = df[df["score"] >= score_min]

    # Signal filter
    signal_map = {
        "💰 Levée de fonds": "funding",
        "📈 Recrutement actif": "hiring_surge",
        "🔥 Les deux": "both",
    }
    if signal_filter:
        allowed = [signal_map[s] for s in signal_filter]
        df = df[df["signal"].isin(allowed) | df["signal"].isna().eq(False)]

    if df.empty:
        st.warning("Aucun prospect avec ces filtres.")
        return

    # Enrich with funding + jobs counts
    with get_conn() as conn:
        fund_counts = pd.read_sql(
            "SELECT company_name, COUNT(*) as n_funding, MAX(amount_m) as max_amount, "
            "MAX(published_at) as latest_funding FROM funding_events GROUP BY company_name",
            conn,
        )
        job_counts = pd.read_sql(
            "SELECT company_name, COUNT(*) as n_jobs FROM tech_jobs GROUP BY company_name",
            conn,
        )

    df = df.merge(fund_counts, left_on="name", right_on="company_name", how="left")
    df = df.merge(job_counts, left_on="name", right_on="company_name", how="left")
    df["n_funding"] = df["n_funding"].fillna(0).astype(int)
    df["n_jobs"] = df["n_jobs"].fillna(0).astype(int)
    df["max_amount"] = df["max_amount"].fillna(0)

    # Sort by score
    df = df.sort_values("score", ascending=False)

    # Display table
    display_df = df[[
        "name", "score", "signal", "location", "size_range",
        "n_funding", "max_amount", "n_jobs", "last_updated"
    ]].copy()

    display_df.columns = [
        "Entreprise", "Score", "Signal", "Localisation", "Taille",
        "Levées", "Max M€", "Offres tech", "Dernière MàJ"
    ]
    display_df["Score"] = display_df["Score"].apply(lambda x: f"{'🔥' if x>=70 else '🟡' if x>=45 else '🔵'} {x:.0f}/100")
    display_df["Signal"] = display_df["Signal"].map({
        "both": "💰📈 Levée + Recrutement",
        "funding": "💰 Levée de fonds",
        "hiring_surge": "📈 Recrutement actif",
    }).fillna("—")
    display_df["Max M€"] = display_df["Max M€"].apply(format_amount)
    display_df["Dernière MàJ"] = display_df["Dernière MàJ"].apply(days_ago_str)

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score": st.column_config.TextColumn("Score ↓", width="small"),
            "Entreprise": st.column_config.TextColumn("Entreprise", width="medium"),
        },
    )

    # Export CSV
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 Exporter CSV",
        data=csv,
        file_name=f"prospects_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )


# ─── Tab 2 : Levées de fonds ──────────────────────────────────────────────────

def render_funding_tab():
    st.subheader("💰 Levées de fonds détectées")

    df = get_funding_df()
    if df.empty:
        st.info("Aucune levée de fonds détectée. Lance le pipeline.")
        return

    # Timeline chart
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
    df_chart = df.dropna(subset=["published_at"]).copy()
    df_chart["week"] = df_chart["published_at"].dt.to_period("W").astype(str)

    if not df_chart.empty:
        weekly = df_chart.groupby("week").agg(
            nb_levees=("id", "count"),
            total_m=("amount_m", "sum"),
        ).reset_index()
        weekly["total_m"] = weekly["total_m"].fillna(0)

        fig = go.Figure()
        fig.add_bar(x=weekly["week"], y=weekly["nb_levees"],
                    name="Nb levées", marker_color="#2d9cdb")
        fig.add_scatter(x=weekly["week"], y=weekly["total_m"],
                        name="Total M€", yaxis="y2",
                        line=dict(color="#ff6b35", width=2), mode="lines+markers")
        fig.update_layout(
            title="Levées de fonds par semaine",
            yaxis=dict(title="Nombre de levées"),
            yaxis2=dict(title="Montant total M€", overlaying="y", side="right"),
            hovermode="x unified",
            height=300,
            margin=dict(t=40, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Table
    display = df[[
        "company_name", "amount_m", "round_type", "source",
        "article_title", "article_url", "published_at"
    ]].copy()
    display.columns = ["Entreprise", "Montant M€", "Tour", "Source",
                        "Article", "Lien", "Date"]
    display["Montant M€"] = display["Montant M€"].apply(format_amount)
    display["Date"] = display["Date"].apply(lambda x: days_ago_str(str(x)) if x else "—")

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Lien": st.column_config.LinkColumn("Lien", width="small"),
        },
    )


# ─── Tab 3 : Offres tech ──────────────────────────────────────────────────────

def render_jobs_tab():
    st.subheader("💼 Offres tech actives (WTTJ)")

    df = get_jobs_df()
    if df.empty:
        st.info("Aucune offre tech. Lance le pipeline.")
        return

    col1, col2 = st.columns(2)

    with col1:
        # Top companies by job count
        top = df.groupby("company_name").size().reset_index(name="nb_offres")
        top = top.sort_values("nb_offres", ascending=True).tail(20)
        fig = px.bar(
            top, x="nb_offres", y="company_name", orientation="h",
            title="Top 20 entreprises par offres tech",
            color="nb_offres", color_continuous_scale="Blues",
            labels={"nb_offres": "Offres", "company_name": ""},
        )
        fig.update_layout(height=400, margin=dict(t=40, b=20), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Job title distribution
        title_counts = df["job_title"].value_counts().head(15).reset_index()
        title_counts.columns = ["Titre", "Count"]
        fig2 = px.pie(
            title_counts, names="Titre", values="Count",
            title="Répartition des titres tech",
            hole=0.4,
        )
        fig2.update_layout(height=400, margin=dict(t=40, b=20))
        st.plotly_chart(fig2, use_container_width=True)

    # Table
    display = df[["company_name", "job_title", "location", "source", "job_url", "scraped_at"]].copy()
    display.columns = ["Entreprise", "Poste", "Ville", "Source", "Lien", "Ajouté le"]
    display["Ajouté le"] = display["Ajouté le"].apply(lambda x: days_ago_str(str(x)) if x else "—")

    # Search filter
    search = st.text_input("🔎 Filtrer par poste ou entreprise", "")
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
        column_config={
            "Lien": st.column_config.LinkColumn("Lien", width="small"),
        },
    )


# ─── Tab 4 : Suivi prospects ─────────────────────────────────────────────────

def render_crm_tab():
    st.subheader("📋 Suivi des prospects")

    # Add prospect form
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
                    "replied": "💬 Répondu", "deal": "✅ Deal",
                    "lost": "❌ Perdu"
                }.get(x, x),
            )
            priority = c2.selectbox("Priorité", ["high", "medium", "low"],
                                     format_func=lambda x: {"high": "🔥 Haute", "medium": "🟡 Moyenne", "low": "🔵 Faible"}.get(x, x))
            notes = st.text_area("Notes")

            if st.form_submit_button("✅ Ajouter"):
                if company:
                    from storage import get_conn
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

    # Kanban-style status view
    df = get_prospects_df()
    if df.empty:
        st.info("Aucun prospect suivi. Ajoute-en un avec le formulaire ci-dessus.")
        return

    status_labels = {
        "new": ("🆕 Nouveaux", "#e3f2fd"),
        "contacted": ("📤 Contactés", "#fff3e0"),
        "replied": ("💬 Ont répondu", "#e8f5e9"),
        "deal": ("✅ Deals", "#f3e5f5"),
        "lost": ("❌ Perdus", "#ffebee"),
    }

    cols = st.columns(len(status_labels))
    for col, (status, (label, bg)) in zip(cols, status_labels.items()):
        subset = df[df["status"] == status]
        col.markdown(f"**{label}** ({len(subset)})")
        for _, row in subset.iterrows():
            with col:
                st.markdown(f"""
                <div style="background:{bg};border-radius:8px;padding:10px;
                            margin-bottom:8px;font-size:0.85rem;border-left:3px solid #ccc;">
                    <b>{row['company_name']}</b><br>
                    {row.get('contact_name','') or ''}<br>
                    <span style="color:#666;">{row.get('notes','')[:60] if row.get('notes') else ''}</span>
                </div>
                """, unsafe_allow_html=True)


# ─── Tab 5 : Analytiques ──────────────────────────────────────────────────────

def render_analytics_tab():
    st.subheader("📊 Analytiques")

    df_companies = get_companies_df()
    df_funding = get_funding_df()
    df_jobs = get_jobs_df()

    if df_companies.empty:
        st.info("Pas encore de données.")
        return

    col1, col2 = st.columns(2)

    with col1:
        # Score distribution
        fig = px.histogram(
            df_companies[df_companies["score"] > 0],
            x="score", nbins=20,
            title="Distribution des scores",
            color_discrete_sequence=["#2d9cdb"],
            labels={"score": "Score"},
        )
        fig.update_layout(height=300, margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Signal breakdown
        if "signal" in df_companies.columns:
            signal_counts = df_companies["signal"].value_counts().reset_index()
            signal_counts.columns = ["Signal", "Count"]
            signal_counts["Signal"] = signal_counts["Signal"].map({
                "both": "💰📈 Levée + Recrutement",
                "funding": "💰 Levée seule",
                "hiring_surge": "📈 Recrutement seul",
            }).fillna("—")
            fig2 = px.pie(
                signal_counts, names="Signal", values="Count",
                title="Répartition des signaux",
                color_discrete_sequence=px.colors.qualitative.Set2,
                hole=0.4,
            )
            fig2.update_layout(height=300, margin=dict(t=40, b=20))
            st.plotly_chart(fig2, use_container_width=True)

    # Funding by round type
    if not df_funding.empty:
        rounds = df_funding.groupby("round_type").agg(
            count=("id", "count"), total_m=("amount_m", "sum")
        ).reset_index()
        rounds = rounds[rounds["round_type"] != ""]
        if not rounds.empty:
            fig3 = px.bar(
                rounds, x="round_type", y="count",
                title="Levées par type de tour",
                color="total_m",
                color_continuous_scale="Viridis",
                labels={"round_type": "Tour", "count": "Nombre", "total_m": "Total M€"},
            )
            fig3.update_layout(height=300, margin=dict(t=40, b=20))
            st.plotly_chart(fig3, use_container_width=True)

    # Top sectors
    if "industry" in df_companies.columns:
        sectors = df_companies[df_companies["industry"].notna()]["industry"].value_counts().head(10)
        if not sectors.empty:
            fig4 = px.bar(
                sectors.reset_index(),
                x="count", y="industry", orientation="h",
                title="Top secteurs",
                color="count",
                color_continuous_scale="Blues",
                labels={"industry": "", "count": "Nb entreprises"},
            )
            fig4.update_layout(height=350, margin=dict(t=40, b=20), showlegend=False)
            st.plotly_chart(fig4, use_container_width=True)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    init_db()

    # Header
    st.markdown("""
    <h1 style="text-align:center;background:linear-gradient(90deg,#1e3a5f,#2d9cdb);
               -webkit-background-clip:text;-webkit-text-fill-color:transparent;
               font-size:2.2rem;margin-bottom:0;">
        🎯 Veille Recrutement Tech France
    </h1>
    <p style="text-align:center;color:#666;margin-top:4px;">
        Levées de fonds · Offres tech actives · Prospects cabinet de recrutement
    </p>
    """, unsafe_allow_html=True)

    # Sidebar
    score_min, signal_filter, days_filter = render_sidebar()

    # KPIs
    stats = get_stats()
    render_kpis(stats)
    st.divider()

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🎯 Prospects",
        "💰 Levées de fonds",
        "💼 Offres tech",
        "📋 Suivi CRM",
        "📊 Analytiques",
    ])

    with tab1:
        render_prospects_tab(score_min, signal_filter, days_filter)
    with tab2:
        render_funding_tab()
    with tab3:
        render_jobs_tab()
    with tab4:
        render_crm_tab()
    with tab5:
        render_analytics_tab()

    # Auto-refresh indicator
    st.sidebar.divider()
    st.sidebar.caption(
        f"⚙️ Auto-refresh : toutes les heures\n"
        f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )


if __name__ == "__main__":
    main()
