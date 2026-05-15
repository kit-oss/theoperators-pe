# pete_optin_api.py
# Run with: gunicorn pete_optin_api:app --bind 0.0.0.0:$PORT

import json
import os
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify
import anthropic

from pete_precall import prepare_pete_for_call
from pete_call_initiator import initiate_pete_call
from pete_budget import can_take_call
from pete_profile_loader import load_member_profile

app = Flask(__name__)

_claude_client = None

def _get_claude_client():
    global _claude_client
    if _claude_client is None:
        _claude_client = anthropic.Anthropic()
    return _claude_client
active_call_prompts = {}

WAITLIST_FILE = "data/pete_waitlist.json"
 

def _load_waitlist() -> list:
    if not Path(WAITLIST_FILE).exists():
        return []
    with open(WAITLIST_FILE) as f:
        return json.load(f)


def _save_to_waitlist(entry: dict):
    waitlist = _load_waitlist()
    waitlist.append(entry)
    Path(WAITLIST_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(WAITLIST_FILE, "w") as f:
        json.dump(waitlist, f, indent=2)


def log_optin(uid, phone, intent, call_result):
    log_file = Path("data/pete_optin_log.json")
    log = json.loads(log_file.read_text()) if log_file.exists() else []
    log.append({
        "uid": uid,
        "phone": phone,
        "intent": intent,
        "opted_in_at": datetime.now().isoformat(),
        "call_result": call_result,
    })
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(json.dumps(log, indent=2))


def notify_owner_waitlist(uid, intent):
    print(f"[WAITLIST] UID: {uid} | Intent: {intent}")


# ─────────────────────────────────────────────────────────────────────────
# LLM Endpoint for Custom LLM integration with Retell
# ─────────────────────────────────────────────────────────────────────────

@app.route('/api/pete/llm', methods=['POST'])
def pete_llm():
    """PETE's brain. Retell calls this on every conversational turn."""
    try:
        data = request.get_json()
        call_id = data.get('call_id', '')
        messages = data.get('messages', [])

        system_prompt = active_call_prompts.get(call_id, '')

        if not system_prompt:
        system_prompt = open('PETE_system_prompt.md').read() if Path('PETE_system_prompt.md').exists() else ""

        clean_messages = [
        m for m in messages
        if m.get('role') in ('user', 'assistant')
        ]

        if not clean_messages or clean_messages[-1].get('role') == 'assistant':
            return jsonify({"content": ""})
     
        response = _get_claude_client().messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=150,
            system=system_prompt,
            messages=clean_messages,
        )

        reply = response.content[0].text.strip()
        return jsonify({"content": reply})
         except Exception as e:
            print(f"[ERROR] pete_llm: {e}")
            return jsonify({"content": "I'm sorry, I had trouble processing that. Could you say that again?"}), 200

@app.route('/api/pete/llm/store-prompt', methods=['POST'])
def store_call_prompt():
    """Stores the pre-built system prompt keyed by call_id."""
    data = request.get_json()
    call_id = data.get('call_id')
    system_prompt = data.get('system_prompt')

    if call_id and system_prompt:
        active_call_prompts[call_id] = system_prompt
        return jsonify({"ok": True})

    return jsonify({"ok": False, "reason": "Missing call_id or system_prompt"}), 400


@app.route('/api/pete/llm/clear-prompt', methods=['POST'])
def clear_call_prompt():
    """Cleans up memory after call ends."""
    data = request.get_json()
    call_id = data.get('call_id')
    if call_id in active_call_prompts:
        del active_call_prompts[call_id]
    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────────────
# Opt-In Endpoint
# ─────────────────────────────────────────────────────────────────────────

@app.route("/api/pete/optin", methods=["POST"])
def pete_optin():
    data = request.get_json()
    phone = data.get("phone", "").strip()
    intent = data.get("intent", "").strip()
    member_uid = data.get("member_uid", "").strip()

    if not phone or not intent:
        return jsonify({"ok": False, "message": "Phone and intent are required."}), 400

    approved, reason = can_take_call()
    if not approved:
        _save_to_waitlist({
            "member_uid": member_uid,
            "phone": phone,
            "intent": intent,
            "waitlisted_at": datetime.now().isoformat(),
            "reason": reason,
        })
        notify_owner_waitlist(member_uid, intent)
        return jsonify({
            "ok": True,
            "status": "waitlisted",
            "message": "Added to waitlist.",
        })

    result = prepare_pete_for_call(
        identifier=member_uid or None,
        linkedin_url=None,
        person_name=None,
    )

    if not result["approved"]:
        _save_to_waitlist({
            "member_uid": member_uid,
            "phone": phone,
            "intent": intent,
            "waitlisted_at": datetime.now().isoformat(),
            "reason": result["reason"],
        })
        notify_owner_waitlist(member_uid, intent)
        return jsonify({"ok": True, "status": "waitlisted"})

    system_prompt = result["system_prompt"]
    system_prompt += f"\n\n## What they said they're hoping to get from this call\n\n\"{intent}\"\n\nUse this to open the conversation naturally."

    call_result = initiate_pete_call(
        phone_number=phone,
        system_prompt=system_prompt,
        member_uid=member_uid,
    )

    log_optin(member_uid, phone, intent, call_result)

    return jsonify({"ok": True, "status": "call_initiated"})


# ─────────────────────────────────────────────────────────────────────────
# Call Ended Webhook
# ─────────────────────────────────────────────────────────────────────────

@app.route("/api/pete/call-ended", methods=["POST"])
def call_ended_webhook():
    """Retell fires this when a call completes."""
    try:
        from pete_postcall import process_call
        payload = request.get_json()
        process_call(payload)
        return jsonify({"ok": True})
    except Exception as e:
        print(f"[ERROR] call-ended: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────
# Confirmation Routes
# ─────────────────────────────────────────────────────────────────────────

@app.route("/pete/confirm", methods=["GET"])
def confirm_match():
    from pete_confirmation_flow import handle_confirmation
    token = request.args.get("token")
    match_id = int(request.args.get("match", 0))
    result = handle_confirmation(token, match_id)
    if result == "intro_sent":
        return """<html><body style="font-family:Georgia;max-width:480px;margin:4rem auto;text-align:center;">
        <h2>You're connected.</h2>
        <p>PETE has sent the introduction. The rest is up to you.</p>
        </body></html>"""
    return """<html><body style="font-family:Georgia;max-width:480px;margin:4rem auto;text-align:center;">
        <h2>Got it.</h2>
        <p>PETE is waiting for the other person to confirm.
        You'll hear from us as soon as they do.</p>
        </body></html>"""


@app.route("/pete/decline", methods=["GET"])
def decline_match():
    from pete_confirmation_flow import handle_decline
    token = request.args.get("token")
    match_id = int(request.args.get("match", 0))
    handle_decline(token, match_id)
    return """<html><body style="font-family:Georgia;max-width:480px;margin:4rem auto;text-align:center;">
        <h2>Understood.</h2>
        <p>No introduction will be made. PETE will keep you in mind
        for the right moment.</p>
        </body></html>"""


# ─────────────────────────────────────────────────────────────────────────
# Dashboard API
# ─────────────────────────────────────────────────────────────────────────

@app.route('/api/pete/dashboard', methods=['GET'])
def dashboard():
    from pete_budget import _load_ledger, MONTHLY_BUDGET_USD
    from pete_db import get_conn
    import json

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

    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT status, COUNT(*) as n FROM matches GROUP BY status")
    pipeline = {row["status"]: row["n"] for row in c.fetchall()}

    c.execute("SELECT theme, COUNT(*) as c, actionability FROM community_signals GROUP BY theme ORDER BY c DESC LIMIT 6")
    signals = [dict(row) for row in c.fetchall()]

    c.execute("""
        SELECT n.*, m.full_name FROM needs n
        JOIN members m ON n.member_uid = m.uid
        WHERE n.status = 'open'
        ORDER BY n.urgency DESC, n.created_at ASC LIMIT 10
    """)
    unmatched = [dict(row) for row in c.fetchall()]

    c.execute("SELECT COUNT(*) as c FROM needs WHERE status = 'open'")
    open_needs_count = c.fetchone()["c"]

    conn.close()

    return jsonify({
        "budget": {
            "total_calls": len(calls),
            "total_spent_usd": round(total_spent, 2),
            "monthly_budget_usd": MONTHLY_BUDGET_USD,
            "budget_remaining_usd": round(MONTHLY_BUDGET_USD - total_spent, 2),
            "avg_duration_min": round(avg_dur, 1),
            "avg_cost_per_call": round(avg_cost, 2),
            "waitlisted": waitlisted,
        },
        "pipeline": pipeline,
        "recent_calls": calls[-5:] if calls else [],
        "community_signals": signals,
        "unmatched_needs": unmatched,
        "open_needs_count": open_needs_count,
    })


if __name__ == "__main__":
    app.run(debug=False, port=5000)
