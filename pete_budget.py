# pete_budget.py
# Tracks call costs and enforces monthly limits.

import json
import os
from datetime import datetime
from pathlib import Path

BUDGET_FILE = "data/pete_call_ledger.json"
MONTHLY_BUDGET_USD = float(os.getenv("MONTHLY_BUDGET_USD", "200.00"))
COST_PER_MINUTE = 0.07
DEFAULT_CALL_MINUTES = 25
COST_PER_CALL_ESTIMATE = COST_PER_MINUTE * DEFAULT_CALL_MINUTES


def _load_ledger() -> dict:
    if not Path(BUDGET_FILE).exists():
        return {"month": _current_month(), "total_spent": 0.0, "calls": []}
    with open(BUDGET_FILE) as f:
        ledger = json.load(f)
    if ledger.get("month") != _current_month():
        ledger = {"month": _current_month(), "total_spent": 0.0, "calls": []}
        _save_ledger(ledger)
    return ledger


def _save_ledger(ledger: dict):
    Path(BUDGET_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(BUDGET_FILE, "w") as f:
        json.dump(ledger, f, indent=2)


def _current_month() -> str:
    return datetime.now().strftime("%Y-%m")


def can_take_call() -> tuple[bool, str]:
    """
    Returns (True, "") if budget allows a call.
    Returns (False, reason) if budget is exhausted.
    """
    ledger = _load_ledger()
    projected = ledger["total_spent"] + COST_PER_CALL_ESTIMATE
    if projected > MONTHLY_BUDGET_USD:
        remaining = MONTHLY_BUDGET_USD - ledger["total_spent"]
        return False, (
            f"Monthly call budget of ${MONTHLY_BUDGET_USD:.0f} is nearly exhausted. "
            f"${remaining:.2f} remaining. Call added to waitlist."
        )
    return True, ""


def record_call(member_uid: str, duration_minutes: float):
    """Call this after every completed call to update the ledger."""
    ledger = _load_ledger()
    cost = round(duration_minutes * COST_PER_MINUTE, 4)
    ledger["total_spent"] = round(ledger["total_spent"] + cost, 4)
    ledger["calls"].append({
        "uid": member_uid,
        "date": datetime.now().isoformat(),
        "duration_min": duration_minutes,
        "cost_usd": cost,
    })
    _save_ledger(ledger)
    return cost


def monthly_summary() -> dict:
    ledger = _load_ledger()
    return {
        "month": ledger["month"],
        "total_calls": len(ledger["calls"]),
        "total_minutes": sum(c["duration_min"] for c in ledger["calls"]),
        "total_spent_usd": ledger["total_spent"],
        "budget_remaining_usd": round(MONTHLY_BUDGET_USD - ledger["total_spent"], 2),
        "budget_utilization_pct": round(
            ledger["total_spent"] / MONTHLY_BUDGET_USD * 100, 1
        ),
    }