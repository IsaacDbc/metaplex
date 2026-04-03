"""
SQLite storage for companies, funding events, and job listings.
"""
import sqlite3
import os
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "dashboard.db"


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            domain TEXT,
            location TEXT,
            size_range TEXT,
            industry TEXT,
            description TEXT,
            wttj_slug TEXT,
            linkedin_url TEXT,
            website TEXT,
            score REAL DEFAULT 0,
            signal TEXT,          -- 'funding' | 'hiring_surge' | 'both'
            first_seen TEXT,
            last_updated TEXT,
            UNIQUE(name, domain)
        );

        CREATE TABLE IF NOT EXISTS funding_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER REFERENCES companies(id),
            company_name TEXT NOT NULL,
            amount_m REAL,          -- montant en millions €
            round_type TEXT,        -- Seed, Series A, B, C…
            investors TEXT,
            article_title TEXT,
            article_url TEXT,
            source TEXT,
            published_at TEXT,
            scraped_at TEXT,
            UNIQUE(company_name, article_url)
        );

        CREATE TABLE IF NOT EXISTS tech_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER REFERENCES companies(id),
            company_name TEXT NOT NULL,
            job_title TEXT,
            tech_tags TEXT,          -- JSON array
            location TEXT,
            job_url TEXT,
            source TEXT,             -- 'wttj' | 'lever' | 'greenhouse'
            published_at TEXT,
            scraped_at TEXT,
            UNIQUE(company_name, job_title, source)
        );

        CREATE TABLE IF NOT EXISTS prospects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER REFERENCES companies(id),
            company_name TEXT NOT NULL,
            status TEXT DEFAULT 'new',  -- new | contacted | replied | deal | lost
            priority TEXT DEFAULT 'medium',
            notes TEXT,
            contact_name TEXT,
            contact_email TEXT,
            contact_linkedin TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """)
    print(f"[DB] Initialized at {DB_PATH}")


def upsert_company(name: str, **kwargs) -> int:
    """Insert or update a company, return its id."""
    kwargs["last_updated"] = datetime.now().isoformat()
    if "first_seen" not in kwargs:
        kwargs["first_seen"] = datetime.now().isoformat()

    cols = ["name"] + list(kwargs.keys())
    vals = [name] + list(kwargs.values())
    placeholders = ", ".join(["?"] * len(vals))
    col_names = ", ".join(cols)
    update_clause = ", ".join(
        f"{k} = excluded.{k}" for k in kwargs if k != "first_seen"
    )

    with get_conn() as conn:
        conn.execute(
            f"""INSERT INTO companies ({col_names}) VALUES ({placeholders})
                ON CONFLICT(name, domain) DO UPDATE SET {update_clause}""",
            vals,
        )
        row = conn.execute(
            "SELECT id FROM companies WHERE name = ?", (name,)
        ).fetchone()
        return row["id"] if row else -1


def insert_funding(company_name: str, **kwargs) -> bool:
    kwargs["company_name"] = company_name
    kwargs["scraped_at"] = datetime.now().isoformat()
    cols = list(kwargs.keys())
    vals = list(kwargs.values())
    placeholders = ", ".join(["?"] * len(vals))
    col_names = ", ".join(cols)
    with get_conn() as conn:
        try:
            conn.execute(
                f"INSERT OR IGNORE INTO funding_events ({col_names}) VALUES ({placeholders})",
                vals,
            )
            return conn.total_changes > 0
        except Exception as e:
            return False


def insert_job(company_name: str, **kwargs) -> bool:
    kwargs["company_name"] = company_name
    kwargs["scraped_at"] = datetime.now().isoformat()
    cols = list(kwargs.keys())
    vals = list(kwargs.values())
    placeholders = ", ".join(["?"] * len(vals))
    col_names = ", ".join(cols)
    with get_conn() as conn:
        try:
            conn.execute(
                f"INSERT OR IGNORE INTO tech_jobs ({col_names}) VALUES ({placeholders})",
                vals,
            )
            return conn.total_changes > 0
        except Exception as e:
            return False


def get_companies_df():
    import pandas as pd
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM companies ORDER BY score DESC, last_updated DESC", conn)


def get_funding_df():
    import pandas as pd
    with get_conn() as conn:
        return pd.read_sql(
            "SELECT * FROM funding_events ORDER BY published_at DESC LIMIT 200", conn
        )


def get_jobs_df():
    import pandas as pd
    with get_conn() as conn:
        return pd.read_sql(
            "SELECT * FROM tech_jobs ORDER BY scraped_at DESC LIMIT 500", conn
        )


def get_prospects_df():
    import pandas as pd
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM prospects ORDER BY created_at DESC", conn)


def get_stats():
    with get_conn() as conn:
        companies = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        funding = conn.execute("SELECT COUNT(*) FROM funding_events").fetchone()[0]
        jobs = conn.execute("SELECT COUNT(*) FROM tech_jobs").fetchone()[0]
        prospects = conn.execute(
            "SELECT COUNT(*) FROM companies WHERE signal IS NOT NULL"
        ).fetchone()[0]
        return {
            "companies": companies,
            "funding_events": funding,
            "tech_jobs": jobs,
            "hot_prospects": prospects,
        }
