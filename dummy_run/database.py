"""
SQLite database layer.

In production this is replaced by Supabase (PostgreSQL).
The table schema here is identical to what you would create in Supabase —
only the connection string and client library differ.

Supabase production equivalent:
  from supabase import create_client
  client = create_client(SUPABASE_URL, SUPABASE_KEY)
  client.table("actuals_monthly").insert(row).execute()

SQLite is used here so you can run the full system with zero cloud dependencies.
The output/financepulse.db file can be opened in DB Browser for SQLite
(free desktop app) to inspect all stored data.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "output" / "financepulse.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize() -> None:
    """Create all tables on first run. Safe to call repeatedly (IF NOT EXISTS)."""
    conn = _connect()
    conn.executescript("""
    -- One row per client. In production: Supabase `clients` table.
    CREATE TABLE IF NOT EXISTS clients (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL UNIQUE,
        industry    TEXT,
        currency    TEXT    DEFAULT 'ZAR',
        created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
    );

    -- One row per monthly processing run.
    CREATE TABLE IF NOT EXISTS runs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id   INTEGER NOT NULL,
        period      TEXT    NOT NULL,       -- "April 2026"
        run_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
        status      TEXT    DEFAULT 'completed',
        report_path TEXT,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    );

    -- Income statement actuals, budget, prior — one row per line item per run.
    CREATE TABLE IF NOT EXISTS actuals_monthly (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id          INTEGER NOT NULL,
        period          TEXT    NOT NULL,
        line_item       TEXT    NOT NULL,
        actual          REAL,
        budget          REAL,
        prior           REAL,
        vs_budget       REAL,
        vs_budget_pct   REAL,
        vs_prior        REAL,
        vs_prior_pct    REAL,
        FOREIGN KEY (run_id) REFERENCES runs(id)
    );

    -- One row per KPI per run.
    CREATE TABLE IF NOT EXISTS kpis (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      INTEGER NOT NULL,
        period      TEXT    NOT NULL,
        kpi_key     TEXT    NOT NULL,
        kpi_label   TEXT,
        value       REAL,
        target      REAL,
        budget      REAL,
        unit        TEXT,
        status      TEXT,   -- 'green' | 'amber' | 'red'
        FOREIGN KEY (run_id) REFERENCES runs(id)
    );

    -- Triggered alerts — one row per alert per run.
    CREATE TABLE IF NOT EXISTS alerts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      INTEGER NOT NULL,
        period      TEXT    NOT NULL,
        kpi_label   TEXT    NOT NULL,
        severity    TEXT,   -- 'HIGH' | 'MEDIUM'
        message     TEXT,
        sent_at     TEXT,
        FOREIGN KEY (run_id) REFERENCES runs(id)
    );

    -- AI-generated commentary — one row per run.
    CREATE TABLE IF NOT EXISTS commentary (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      INTEGER NOT NULL,
        source      TEXT,
        word_count  INTEGER,
        raw_text    TEXT,
        FOREIGN KEY (run_id) REFERENCES runs(id)
    );

    -- Balance sheet snapshots — one row per line item per run.
    CREATE TABLE IF NOT EXISTS balance_sheet_monthly (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      INTEGER NOT NULL,
        period      TEXT    NOT NULL,
        account_name TEXT   NOT NULL,
        account_type TEXT,  -- 'current_asset' | 'noncurrent_asset' | etc.
        amount      REAL,
        FOREIGN KEY (run_id) REFERENCES runs(id)
    );
    """)
    conn.commit()
    conn.close()


def store_results(normalized: dict, variances: dict, kpis: dict,
                  commentary: dict, alerts: list,
                  report_path: str = "") -> tuple[int, dict]:
    """
    Persist all results for one processing run.
    Returns (run_id, summary_counts).
    """
    conn = _connect()
    c    = conn.cursor()

    client  = normalized["client"]
    period  = normalized["period"]["label"]
    now_iso = datetime.now().isoformat(timespec="seconds")

    # ── Upsert client ─────────────────────────────────────────────────────────
    c.execute(
        "INSERT OR IGNORE INTO clients (name, industry, currency) VALUES (?, ?, ?)",
        (client["name"], client["industry"], client["currency"]),
    )
    client_id = c.execute(
        "SELECT id FROM clients WHERE name = ?", (client["name"],)
    ).fetchone()[0]

    # ── Create run record ─────────────────────────────────────────────────────
    c.execute(
        "INSERT INTO runs (client_id, period, run_at, report_path) VALUES (?, ?, ?, ?)",
        (client_id, period, now_iso, report_path),
    )
    run_id = c.lastrowid

    # ── Income statement lines ────────────────────────────────────────────────
    IS_LINES = [
        "revenue", "cogs", "gross_profit", "gross_margin_pct",
        "salaries", "rent", "transport", "marketing", "admin", "depreciation",
        "total_opex", "ebit", "ebitda", "ebitda_margin_pct",
        "finance_costs", "net_profit", "net_margin_pct",
    ]
    is_count = 0
    for line in IS_LINES:
        if line not in variances:
            continue
        v = variances[line]
        c.execute(
            """INSERT INTO actuals_monthly
               (run_id, period, line_item, actual, budget, prior,
                vs_budget, vs_budget_pct, vs_prior, vs_prior_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id, period, line,
                v.get("actual"),  v.get("budget"),  v.get("prior"),
                v.get("vs_budget"), v.get("vs_budget_pct"),
                v.get("vs_prior"),  v.get("vs_prior_pct"),
            ),
        )
        is_count += 1

    # ── KPIs ──────────────────────────────────────────────────────────────────
    for key, kpi in kpis.items():
        c.execute(
            """INSERT INTO kpis
               (run_id, period, kpi_key, kpi_label, value, target, budget, unit, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id, period, key, kpi["label"],
                kpi["value"], kpi.get("target"), kpi.get("budget"),
                kpi.get("unit"), kpi["status"],
            ),
        )

    # ── Alerts ────────────────────────────────────────────────────────────────
    for alert in alerts:
        c.execute(
            """INSERT INTO alerts (run_id, period, kpi_label, severity, message, sent_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, period, alert["kpi"], alert["severity"], alert["message"], now_iso),
        )

    # ── Commentary ────────────────────────────────────────────────────────────
    c.execute(
        "INSERT INTO commentary (run_id, source, word_count, raw_text) VALUES (?, ?, ?, ?)",
        (run_id, commentary["source"], commentary["words"], commentary["raw"]),
    )

    # ── Balance sheet ─────────────────────────────────────────────────────────
    bs = normalized["balance_sheet"]
    bs_count = 0
    for acct_type, accounts in [
        ("current_asset",         bs["current_assets"]),
        ("noncurrent_asset",      bs["noncurrent_assets"]),
        ("current_liability",     bs["current_liabilities"]),
        ("noncurrent_liability",  bs["noncurrent_liabilities"]),
        ("equity",                bs["equity"]),
    ]:
        for name, amount in accounts.items():
            c.execute(
                """INSERT INTO balance_sheet_monthly
                   (run_id, period, account_name, account_type, amount)
                   VALUES (?, ?, ?, ?, ?)""",
                (run_id, period, name, acct_type, amount),
            )
            bs_count += 1

    conn.commit()
    conn.close()

    counts = {
        "income_statement_lines": is_count,
        "kpis":                   len(kpis),
        "alerts":                 len(alerts),
        "balance_sheet_lines":    bs_count,
    }
    return run_id, counts


def get_run_history(client_name: str) -> list[dict]:
    """Retrieve all past runs for a client (for dashboard trend data)."""
    conn = _connect()
    rows = conn.execute(
        """SELECT r.id, r.period, r.run_at, r.status, r.report_path
           FROM runs r
           JOIN clients c ON c.id = r.client_id
           WHERE c.name = ?
           ORDER BY r.id DESC""",
        (client_name,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
