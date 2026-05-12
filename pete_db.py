# pete_db.py
# Run once to initialise: python pete_db.py

import sqlite3
from pathlib import Path

DB_PATH = "data/pete_matchmaking.db"


def get_conn():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ── Members ──────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS members (
        uid             TEXT PRIMARY KEY,
        full_name       TEXT,
        email           TEXT,
        headline        TEXT,
        current_status  TEXT,
        persona         TEXT,
        linkedin_url    TEXT,
        location       TEXT,
        last_call_date  TEXT,
        profile_json    TEXT
    )
    """)

    # ── Needs ─────────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS needs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        member_uid      TEXT REFERENCES members(uid),
        category        TEXT,
        description     TEXT,
        sector          TEXT,
        geography      TEXT,
        urgency         TEXT,
        specifics_json  TEXT,
        status          TEXT DEFAULT 'open',
        created_at      TEXT,
        updated_at      TEXT,
        source_call_id  TEXT
    )
    """)

    # ── Offers ───────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS offers (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        member_uid      TEXT REFERENCES members(uid),
        category        TEXT,
        description     TEXT,
        sector          TEXT,
        geography      TEXT,
        availability   TEXT,
        specifics_json  TEXT,
        status          TEXT DEFAULT 'active',
        created_at      TEXT,
        updated_at      TEXT,
        source_call_id  TEXT
    )
    """)

    # ── Matches ───────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        need_id             INTEGER REFERENCES needs(id),
        offer_id            INTEGER REFERENCES offers(id),
        seeker_uid          TEXT,
        provider_uid        TEXT,
        match_rationale     TEXT,
        confidence          REAL,
        status              TEXT DEFAULT 'pending_confirmation',
        seeker_confirmed    INTEGER DEFAULT 0,
        provider_confirmed  INTEGER DEFAULT 0,
        seeker_token        TEXT,
        provider_token      TEXT,
        confirmation_sent_at TEXT,
        intro_sent_at       TEXT,
        outcome             TEXT,
        created_at          TEXT,
        updated_at          TEXT
    )
    """)

    # ── Community Recommendations ─────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS community_signals (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        member_uid      TEXT,
        theme           TEXT,
        verbatim        TEXT,
        actionability   TEXT,
        call_id         TEXT,
        created_at      TEXT
    )
    """)

    conn.commit()
    conn.close()
    print("PETE matchmaking database initialised.")


if __name__ == "__main__":
    init_db()