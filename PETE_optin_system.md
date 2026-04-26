# PETE — Opt-In System
## Backend Handler · Email Copy · Community Post Copy

---

## Part 1: Backend Handler (Flask)

This is the API endpoint that the opt-in page POSTs to.
It runs the budget check, builds PETE's prompt, and either
schedules the call or adds the member to the waitlist.

```python
# pete_optin_api.py
# Run with: flask --app pete_optin_api run
# Or mount under your existing web server

from flask import Flask, request, jsonify
from pete_precall import prepare_pete_for_call
from pete_call_initiator import initiate_pete_call
from pete_budget import can_take_call
from pete_profile_loader import load_member_profile
import json
from datetime import datetime
from pathlib import Path

app = Flask(__name__)

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


@app.route("/api/pete/optin", methods=["POST"])
def pete_optin():
    data = request.get_json()
    phone = data.get("phone", "").strip()
    intent = data.get("intent", "").strip()
    member_uid = data.get("member_uid", "").strip()

    # Basic validation
    if not phone or not intent:
        return jsonify({"ok": False, "message": "Phone and intent are required."}), 400

    # Budget check first — before any expensive operations
    approved, reason = can_take_call()
    if not approved:
        _save_to_waitlist({
            "member_uid": member_uid,
            "phone": phone,
            "intent": intent,
            "waitlisted_at": datetime.now().isoformat(),
            "reason": reason,
        })
        # Still return 200 — the member sees the success screen.
        # You get notified separately (see notify_owner below).
        notify_owner_waitlist(member_uid, intent)
        return jsonify({
            "ok": True,
            "status": "waitlisted",
            "message": "Added to waitlist.",
        })

    # Build PETE's prompt
    result = prepare_pete_for_call(
        identifier=member_uid or None,
        linkedin_url=None,   # populated later if not a member
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

    # Inject the member's stated intent into PETE's prompt
    system_prompt = result["system_prompt"]
    system_prompt += f"\n\n## What they said they're hoping to get from this call\n\n\"{intent}\"\n\nUse this to open the conversation naturally — reference it early without reading it back verbatim."

    # Initiate the call via Retell
    call_result = initiate_pete_call(
        phone_number=phone,
        system_prompt=system_prompt,
        member_uid=member_uid,
    )

    # Log the opt-in
    log_optin(member_uid, phone, intent, call_result)

    return jsonify({"ok": True, "status": "call_initiated"})


@app.route("/api/pete/call-ended", methods=["POST"])
def call_ended_webhook():
    """Retell fires this when a call completes."""
    from pete_call_initiator import handle_call_ended_webhook
    payload = request.get_json()
    handle_call_ended_webhook(payload)
    return jsonify({"ok": True})


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
    """
    Placeholder — swap in SendGrid, email, Slack, or SMS
    to notify you when someone gets waitlisted.
    """
    print(f"[WAITLIST] UID: {uid} | Intent: {intent}")
    # Example with SendGrid:
    # send_email(
    #     to="kit@theoperators.pe",
    #     subject="PETE waitlisted a member",
    #     body=f"UID: {uid}\nIntent: {intent}"
    # )


if __name__ == "__main__":
    app.run(debug=False, port=5000)
```

---

## Part 2: Injecting Intent into the Prompt

The member's one-sentence intent gets appended to PETE's
system prompt as its own section, right before the call.
This is handled in the backend above, but shown here for clarity:

```
## What they said they're hoping to get from this call

"I'm quietly exploring CFO roles in PE-backed healthcare businesses in the Southeast."

Use this to open the conversation naturally — reference it early
without reading it back verbatim.
```

PETE will use this to open the call with genuine context rather
than starting cold with "so what brings you here today."

---

## Part 3: Invitation Email Copy

Send this individually or via your email platform (ConvertKit, etc.).
The `?uid=` parameter in the link is what tells PETE who's calling
so the member profile auto-loads — it's important to include it.

---

**Subject:** PETE would like to meet you.

---

[First Name],

I'd like to introduce you to PETE — Private Equity's Trusted Envoy.

PETE is an AI that does one thing: it has real conversations with
operators, advisors, and PE professionals to understand who they are
and what they need — and then makes introductions that matter.

Not a recruiter. Not a search firm. Not a database.
A genuine conversation, followed by a thoughtful connection.

PETE already knows your Operators profile. He just wants to hear
it in your own words — and ask a few questions you probably haven't
been asked before.

The call takes 20–25 minutes. There's no pitch, no obligation,
and no one trying to place you. Just a conversation.

If you're open to it:

→ Request your call with PETE:
[YOUR DOMAIN]/pete/call?uid=[MEMBER_UID]

Warmly,
Kit

P.S. PETE is in limited release right now — available to a small
cohort of members before we open it more broadly. If this isn't
the right moment, no pressure. There'll be another wave.

---

## Part 4: Community Post Copy

Post this in your Circle community — works as an announcement
or pinned post in a relevant space. Keep it brief and slightly
mysterious. PE people respond to scarcity and exclusivity.

---

**A quiet introduction.**

I've been working on something I'd like a few of you to try.

His name is PETE — Private Equity's Trusted Envoy. He's an AI
that has real conversations with operators and PE professionals,
asks better questions than most people in this industry, and then
makes introductions he actually believes in.

He's not a recruiter. He has no placement fees and no fund
affiliation. He's just very good at figuring out who should
know who — and then making that happen.

PETE is available to a small cohort of members this month.
If you'd like a conversation, drop your name below or
request a call directly here:

→ [YOUR DOMAIN]/pete/call

He already knows your profile. He just wants to hear you tell it.

---

## Part 5: UID-Linked Invitation (how to personalise at scale)

When sending to your cohort CSV (from `pete_cohort_selector.py`),
loop through and generate a personalised link per member:

```python
# generate_invite_links.py

import pandas as pd
from pete_cohort_selector import select_next_cohort

BASE_URL = "https://yoursite.com/pete/call"

cohort = select_next_cohort("data/community_members.csv", cohort_size=30)

cohort["invite_link"] = BASE_URL + "?uid=" + cohort["UID"]

# Export for use in your email platform
cohort[["First Name", "Last Name", "Email", "invite_link"]].to_csv(
    "data/cohort_invite_links.csv", index=False
)

print(f"Generated {len(cohort)} invite links.")
print(cohort[["First Name", "invite_link"]].head(5).to_string(index=False))
```

This produces a CSV you can upload to ConvertKit, Mailchimp,
or any email platform that supports merge tags — each member
gets a link pre-loaded with their UID so PETE knows who's calling.

---

*PETE Opt-In System v1.0*
*Landing Page · Backend · Email · Community Post · UID Linking*
