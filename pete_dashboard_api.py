# pete_dashboard_api.py
# Add this route to pete_optin_api.py
# Serves all dashboard data from a single endpoint

from flask import jsonify
from pete_db import get_conn
from pete_budget import _load_ledger, MONTHLY_BUDGET_USD
from datetime import datetime, timedelta
import json


@app.route('/api/pete/dashboard', methods=['GET'])
def dashboard():
    return jsonify({
        "budget":           get_budget_summary(),
        "pipeline":         get_pipeline_summary(),
        "recent_calls":     get_recent_calls(limit=5),
        "community_signals": get_community_signals(limit=6),
        "unmatched_needs":  get_unmatched_needs(),
        "open_needs_count": get_open_needs_count(),
    })


def get_budget_summary() -> dict:
    ledger = _load_ledger()
    calls = ledger.get("calls", [])
    total_spent = ledger.get("total_spent", 0.0)
    durations = [c.get("duration_min", 0) for c in calls]
    avg_dur = sum(durations) / len(durations) if durations else 0
    avg_cost = total_spent / len(calls) if calls else 0

    waitlist_file = "data/pete_waitlist.json"
    try:
        with open(waitlist_file) as f:
            waitlisted = len(json.load(f))
    except Exception:
        waitlisted = 0

    return {
        "total_calls": len(calls),
        "total_spent_usd": round(total_spent, 2),
        "monthly_budget_usd": MONTHLY_BUDGET_USD,
        "budget_remaining_usd": round(MONTHLY_BUDGET_USD - total_spent, 2),
        "avg_duration_min": round(avg_dur, 1),
        "avg_cost_per_call": round(avg_cost, 2),
        "waitlisted": waitlisted,
    }


def get_pipeline_summary() -> dict:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT status, COUNT(*) as n FROM matches GROUP BY status")
    rows = {row["status"]: row["n"] for row in c.fetchall()}
    conn.close()

    return {
        "pending_confirmation": rows.get("pending_confirmation", 0),
        "partial_confirmed":    rows.get("seeker_confirmed", 0) + rows.get("provider_confirmed", 0),
        "intro_sent":           rows.get("intro_sent", 0),
        "accepted":             rows.get("accepted", 0),
        "declined":             rows.get("declined", 0),
    }


def get_recent_calls(limit: int = 5) -> list:
    records_file = "data/pete_call_records.json"
    try:
        with open(records_file) as f:
            records = json.load(f)
    except Exception:
        return []

    records = sorted(records, key=lambda r: r.get("date", ""), reverse=True)
    result = []
    for r in records[:limit]:
        analysis = r.get("analysis", {})
        intros = [o for o in analysis.get("introduction_opportunities", [])
                  if o.get("confidence", 0) >= 0.85]
        signals = len(analysis.get("community_recommendations", []))
        profile = r.get("analysis", {})
        result.append({
            "name":         r.get("member_uid"),  # swap for name lookup
            "headline":     "",
            "date":         r.get("date", "")[:10],
            "duration_min": r.get("duration_min", 0),
            "cost_usd":     r.get("cost_usd", 0),
            "intros_sent":  len(intros),
            "signals":      signals,
        })
    return result


def get_community_signals(limit: int = 6) -> list:
    conn = get_conn()
    c = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    c.execute("""
        SELECT theme, COUNT(*) as count, actionability
        FROM community_signals
        WHERE created_at > ?
        GROUP BY theme
        ORDER BY count DESC
        LIMIT ?
    """, (cutoff, limit))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def get_unmatched_needs() -> list:
    conn = get_conn()
    c = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    c.execute("""
        SELECT n.id, n.description, n.sector, n.urgency, n.created_at,
               m.full_name as member_name, m.headline as member_headline
        FROM needs n
        JOIN members m ON n.member_uid = m.uid
        WHERE n.status = 'open'
          AND n.created_at < ?
          AND n.id NOT IN (
              SELECT need_id FROM matches
              WHERE status NOT IN ('declined', 'gone_quiet')
          )
        ORDER BY
          CASE n.urgency WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
          n.created_at ASC
    """, (cutoff,))
    rows = []
    for row in c.fetchall():
        r = dict(row)
        created = datetime.fromisoformat(r["created_at"])
        r["age_days"] = (datetime.now() - created).days
        rows.append(r)
    conn.close()
    return rows


def get_open_needs_count() -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as n FROM needs WHERE status = 'open'")
    n = c.fetchone()["n"]
    conn.close()
    return n
