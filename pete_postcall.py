# pete_postcall.py

import json
import requests
import os
from pathlib import Path
from datetime import datetime

from pete_transcript_analyzer import analyze_transcript
from pete_member_index import load_member_index
from pete_owner_notify import send_owner_summary
from pete_budget import record_call
from pete_profile_loader import load_member_profile
from pete_db import get_conn

RETELL_API_KEY = os.getenv("RETELL_API_KEY")
CALL_RECORDS_FILE = "data/pete_call_records.json"


def fetch_retell_transcript(call_id: str) -> tuple:
    """Fetches the full transcript from Retell's API."""
    url = f"https://api.retellai.com/v2/get-call/{call_id}"
    headers = {"Authorization": f"Bearer {RETELL_API_KEY}"}
    response = requests.get(url, headers=headers)
    data = response.json()

    transcript = data.get("transcript", "")
    if not transcript:
        turns = data.get("transcript_object", [])
        lines = []
        for turn in turns:
            role = "PETE" if turn.get("role") == "agent" else "MEMBER"
            lines.append(f"{role}: {turn.get('content', '')}")
        transcript = "\n".join(lines)

    return transcript, data


def process_call(webhook_payload: dict):
    """
    Master orchestrator. Called by the Retell webhook handler.
    """
    call_id = webhook_payload.get("call_id")
    member_uid = webhook_payload.get("metadata", {}).get("member_uid", "unknown")
    duration_ms = webhook_payload.get("duration_ms", 0)
    duration_min = round(duration_ms / 60000, 2)

    print(f"[POST-CALL] Processing call {call_id} for UID {member_uid}")

    # 1. Record cost
    cost = record_call(member_uid, duration_min)

    # 2. Fetch transcript
    transcript, raw_call_data = fetch_retell_transcript(call_id)
    if not transcript:
        print(f"[POST-CALL] No transcript available for call {call_id}")
        return

    # 3. Load member profile
    member_record = load_member_profile(member_uid)
    member_profile = member_record["pete_profile"] if member_record else {
        "full_name": "Unknown", "uid": member_uid
    }

    # 4. Load member index for match suggestions
    member_index = load_member_index()

    # 5. Analyze transcript
    print(f"[POST-CALL] Analyzing transcript...")
    analysis = analyze_transcript(transcript, member_profile, member_index)

    # 6. Save full call record
    save_call_record(call_id, member_uid, transcript, analysis, duration_min, cost)

    # 7. Update member profile with new signals
    update_member_profile(member_uid, analysis.get("profile_updates", {}))

    # 8. Process introductions
    intros_sent = []
    intros_flagged = []
    opportunities = analysis.get("introduction_opportunities", [])

    for opp in opportunities:
        confidence = opp.get("confidence", 0.0)
        if confidence >= 0.85:
            from pete_intro_engine import send_introduction
            result = send_introduction(member_profile, opp)
            if result.get("ok"):
                intros_sent.append(opp)
                print(f"[INTRO] Sent: {opp.get('match_name')} ({confidence:.0%})")
            else:
                intros_flagged.append(opp)
                print(f"[INTRO] Failed: {result.get('reason')}")
        else:
            intros_flagged.append(opp)
            print(f"[INTRO] Flagged (low confidence): {opp.get('match_name')} ({confidence:.0%})")

    # 9. Send owner summary
    send_owner_summary(
        member_profile=member_profile,
        analysis=analysis,
        intros_sent=intros_sent,
        intros_flagged=intros_flagged,
        call_duration_min=duration_min,
        call_cost_usd=cost,
    )

    print(f"[POST-CALL] Complete. {len(intros_sent)} intro(s) sent, {len(intros_flagged)} flagged.")


def save_call_record(call_id, member_uid, transcript, analysis, duration_min, cost):
    path = Path(CALL_RECORDS_FILE)
    records = json.loads(path.read_text()) if path.exists() else []
    records.append({
        "call_id": call_id,
        "member_uid": member_uid,
        "date": datetime.now().isoformat(),
        "duration_min": duration_min,
        "cost_usd": cost,
        "transcript": transcript,
        "analysis": analysis,
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2))


def update_member_profile(member_uid: str, updates: dict):
    """Applies non-null profile updates from the call analysis."""
    clean = {k: v for k, v in updates.items() if v is not None}
    if clean:
        print(f"[PROFILE UPDATE] UID {member_uid}: {list(clean.keys())}")