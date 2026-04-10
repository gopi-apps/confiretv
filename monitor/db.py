"""
SQLite database layer for ConFireTV.

Tables:
  sessions  — one row per continuous app-watching session
  limits    — per-app daily limit overrides (synced from config at startup)
"""

import sqlite3
import os
from datetime import date, datetime, timedelta
from contextlib import contextmanager
from typing import Optional


def get_db_path() -> str:
    import yaml
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    path = cfg["database"]["path"]
    # Make path relative to project root
    root = os.path.dirname(os.path.abspath(cfg_path))
    return os.path.join(root, path)


@contextmanager
def get_conn():
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                app_key     TEXT    NOT NULL,
                package     TEXT    NOT NULL,
                start_time  TEXT    NOT NULL,   -- ISO8601 UTC
                end_time    TEXT,               -- NULL if session still active
                duration_s  INTEGER             -- seconds, filled on session end
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_time);
            CREATE INDEX IF NOT EXISTS idx_sessions_app   ON sessions(app_key, start_time);

            CREATE TABLE IF NOT EXISTS limits (
                app_key         TEXT PRIMARY KEY,
                daily_limit_min INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)


# ---------------------------------------------------------------------------
# Session writes
# ---------------------------------------------------------------------------

def open_session(app_key: str, package: str, start_time: datetime) -> int:
    """Insert a new open session. Returns the session id."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (app_key, package, start_time) VALUES (?, ?, ?)",
            (app_key, package, start_time.isoformat()),
        )
        return cur.lastrowid


def close_session(session_id: int, end_time: datetime):
    """Close an open session and record duration."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT start_time FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return
        start = datetime.fromisoformat(row["start_time"])
        duration_s = max(0, int((end_time - start).total_seconds()))
        conn.execute(
            "UPDATE sessions SET end_time = ?, duration_s = ? WHERE id = ?",
            (end_time.isoformat(), duration_s, session_id),
        )


def close_all_open_sessions(end_time: datetime):
    """On startup/crash recovery, close any sessions left open."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, start_time FROM sessions WHERE end_time IS NULL"
        ).fetchall()
        for row in rows:
            start = datetime.fromisoformat(row["start_time"])
            duration_s = max(0, int((end_time - start).total_seconds()))
            conn.execute(
                "UPDATE sessions SET end_time = ?, duration_s = ? WHERE id = ?",
                (end_time.isoformat(), duration_s, row["id"]),
            )


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_daily_totals(for_date: Optional[date] = None) -> dict:
    """
    Returns dict of {app_key: total_seconds} for the given date (default today).
    Includes any currently open session up to now.
    """
    if for_date is None:
        for_date = date.today()

    day_start = datetime.combine(for_date, datetime.min.time()).isoformat()
    day_end   = datetime.combine(for_date + timedelta(days=1), datetime.min.time()).isoformat()
    now_iso   = datetime.now().isoformat()

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                app_key,
                SUM(
                    CASE
                        WHEN end_time IS NOT NULL THEN duration_s
                        ELSE CAST((julianday(?) - julianday(start_time)) * 86400 AS INTEGER)
                    END
                ) AS total_s
            FROM sessions
            WHERE start_time >= ? AND start_time < ?
            GROUP BY app_key
        """, (now_iso, day_start, day_end)).fetchall()

    return {row["app_key"]: (row["total_s"] or 0) for row in rows}


def get_session_log(for_date: Optional[date] = None, limit: int = 100) -> list:
    """Returns list of session dicts for the given date, newest first."""
    if for_date is None:
        for_date = date.today()

    day_start = datetime.combine(for_date, datetime.min.time()).isoformat()
    day_end   = datetime.combine(for_date + timedelta(days=1), datetime.min.time()).isoformat()
    now_iso   = datetime.now().isoformat()

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                id, app_key, package, start_time, end_time,
                CASE
                    WHEN end_time IS NOT NULL THEN duration_s
                    ELSE CAST((julianday(?) - julianday(start_time)) * 86400 AS INTEGER)
                END AS duration_s
            FROM sessions
            WHERE start_time >= ? AND start_time < ?
            ORDER BY start_time DESC
            LIMIT ?
        """, (now_iso, day_start, day_end, limit)).fetchall()

    return [dict(row) for row in rows]


def get_weekly_totals() -> list:
    """
    Returns last 7 days of per-app totals.
    List of {date, app_key, total_s} sorted by date asc.
    """
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                substr(start_time, 1, 10) AS day,
                app_key,
                SUM(COALESCE(duration_s, 0)) AS total_s
            FROM sessions
            WHERE start_time >= ? AND end_time IS NOT NULL
            GROUP BY day, app_key
            ORDER BY day ASC
        """, (seven_days_ago,)).fetchall()

    return [dict(row) for row in rows]


def get_active_session() -> Optional[dict]:
    """Returns the currently open session (no end_time), or None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE end_time IS NULL ORDER BY start_time DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

def upsert_limit(app_key: str, daily_limit_min: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO limits (app_key, daily_limit_min) VALUES (?, ?)",
            (app_key, daily_limit_min),
        )


def get_limits() -> dict:
    """Returns {app_key: daily_limit_min}."""
    with get_conn() as conn:
        rows = conn.execute("SELECT app_key, daily_limit_min FROM limits").fetchall()
    return {row["app_key"]: row["daily_limit_min"] for row in rows}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )


def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default
