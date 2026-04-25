# PETE — Post-Call Layer v1.0
## Transcript Analysis · Owner Email · Automatic Introductions · Community Insights

---

## Architecture Overview

```
Retell webhook (call_ended)
        │
        ├── 1. Fetch full transcript from Retell
        │
        ├── 2. Claude analyzes transcript → extracts:
        │         a. Introduction opportunities
        │         b. Community improvement signals
        │         c. Updated profile fields
        │         d. Confidence score + red flags
        │
        ├── 3. Save analysis to member record
        │
        ├── 4. Email summary → Kit
        │
        └── 5. If match confidence ≥ threshold:
                  └── Claude drafts intro email → sends automatically
```

---

## Part 1: Transcript Analyzer

```python
# pete_transcript_analyzer.py

import anthropic
import json

client = anthropic.Anthropic()


def analyze_transcript(
    transcript: str,
    member_profile: dict,
    all_members_summary: str,
) -> dict:
    """
    Analyzes a PETE call transcript and returns structured insights.

    transcript:           Full text of the call from Retell
    member_profile:       The pete_profile dict for this member
    all_members_summary:  A lightweight index of other members
                          (name, role, current status, key skills)
                          used for match suggestions
    """

    prompt = f"""
You are PETE's post-call analyst. You have just completed a conversation
with a member of The Operators community. Your job is to extract structured
intelligence from the transcript and identify the most valuable next actions.

## Member Profile (what we knew going in)
{json.dumps(member_profile, indent=2)}

## Call Transcript
{transcript}

## Other Community Members (for match suggestions)
{all_members_summary}

---

Analyze this call and return a JSON object with EXACTLY this structure.
No preamble. No markdown fences. Valid JSON only.

{{
  "introduction_opportunities": [
    {{
      "match_uid": "uid of the member to introduce",
      "match_name": "their full name",
      "caller_need": "one sentence: what the caller is trying to accomplish",
      "why_this_match": "one sentence: why this specific person",
      "confidence": 0.0,
      "intro_urgency": "high / medium / low"
    }}
  ],
  "community_recommendations": [
    {{
      "theme": "short label e.g. 'More CFO-specific content'",
      "verbatim_signal": "direct quote or close paraphrase from the call",
      "actionability": "high / medium / low"
    }}
  ],
  "profile_updates": {{
    "current_status": null,
    "networking_mindset": null,
    "roles_comfortable_with": null,
    "industries": null,
    "skills": null,
    "willing_to_relocate": null,
    "personal_brand": null
  }},
  "call_summary": "2-3 sentence plain English summary of who this person is and what they need right now",
  "notable_quotes": ["direct quote 1", "direct quote 2"],
  "red_flags": [],
  "overall_call_quality": "strong / adequate / thin",
  "pete_confidence_in_member": 0.0
}}

Scoring guidance:
- confidence: 0.0–1.0. Only suggest matches you genuinely believe in.
  0.85+ = send automatically. Below that = flag for review.
- pete_confidence_in_member: 0.0–1.0. How well did PETE understand
  this person? Low score = transcript was too thin to act on.
- red_flags: list any concerns (e.g. "seemed unaware they're in a
  confidential process", "name-dropped in a way that felt performative").
  Empty list if none.
- profile_updates: only include fields where the call revealed something
  meaningfully different or more specific than the existing profile.
  Use null for fields with no new signal.
"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip any accidental markdown fences
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)
```

---

## Part 2: Member Index Builder

This builds the lightweight member summary that the analyzer
uses for match suggestions — avoids sending the full 1,400-row
CSV into every Claude call (expensive and unnecessary).

```python
# pete_member_index.py

import pandas as pd
import json
from pathlib import Path

MEMBER_CSV = "data/community_members.csv"
INDEX_FILE = "data/pete_member_index.json"


def build_member_index(csv_path: str = MEMBER_CSV) -> list:
    """
    Builds a lightweight index of members for match suggestions.
    Filters to actively networking members only.
    """
    df = pd.read_csv(csv_path)

    # Only include members who want to be found
    df = df[df["Networking Mindset"].isin([
        "Actively Networking",
        "Passively Networking",
        "Open to Outreach by Peers only",
    ])]

    # Exclude untrusted
    df = df[~df["Tags"].str.contains("Not Trusted but Connected", na=False)]

    def safe(val):
        return val if pd.notna(val) else None

    index = []
    for _, row in df.iterrows():
        index.append({
            "uid": safe(row.get("UID")),
            "name": f"{safe(row.get('First Name', ''))} {safe(row.get('Last Name', ''))}".strip(),
            "headline": safe(row.get("Headline")),
            "current_status": safe(row.get("Current Status")),
            "roles": safe(row.get("Roles you feel comfortable working in")),
            "industries": safe(row.get("Industries You Have Worked In?")),
            "skills": safe(row.get("Skills?")),
            "networking_mindset": safe(row.get("Networking Mindset")),
            "location": safe(row.get("Location")),
            "pe_backed": safe(row.get("Have you ever been, or are you now, a PE-Backed Executive?")),
        })

    # Cache to disk — rebuild weekly or when CSV changes
    Path(INDEX_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_FILE, "w") as f:
        json.dump(index, f, indent=2)

    return index


def load_member_index() -> str:
    """Returns the index as a compact string for prompt injection."""
    if not Path(INDEX_FILE).exists():
        build_member_index()
    with open(INDEX_FILE) as f:
        index = json.load(f)

    # Format compactly — one line per member
    lines = []
    for m in index:
        lines.append(
            f"[{m['uid']}] {m['name']} | {m['headline']} | "
            f"{m['current_status']} | {m['networking_mindset']} | "
            f"{m.get('location', '')}"
        )
    return "\n".join(lines)
```

---

## Part 3: Automatic Introduction Engine

```python
# pete_intro_engine.py

import anthropic
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pete_profile_loader import load_member_profile

client = anthropic.Anthropic()

INTRO_CONFIDENCE_THRESHOLD = 0.85  # below this, flag for your review
SMTP_HOST = "smtp.sendgrid.net"
SMTP_PORT = 587
SMTP_USER = "apikey"
SMTP_PASS = "your_sendgrid_api_key"
FROM_EMAIL = "pete@theoperators.pe"
OWNER_EMAIL = "kit@theoperators.pe"


def draft_intro_email(
    caller_profile: dict,
    match_profile: dict,
    opportunity: dict,
) -> dict:
    """
    Uses Claude to draft a warm introduction email from PETE.
    Returns subject + body for each of the two parties.
    """
    prompt = f"""
You are PETE — Private Equity's Trusted Envoy. You are writing
a warm introduction email connecting two members of The Operators.

You have just spoken with {caller_profile.get('full_name')} and
believe they should meet {match_profile.get('full_name')}.

## Person A (just spoke with PETE)
{json.dumps(caller_profile, indent=2)}

## Person B (being introduced)
{json.dumps(match_profile, indent=2)}

## Why PETE is making this introduction
{opportunity.get('why_this_match')}
{opportunity.get('caller_need')}

---

Write ONE email that introduces both parties to each other simultaneously.
PETE is on the from line. Both are on the to line.

Rules:
- Warm, unhurried, relationship-first tone — not transactional
- Lead with the quality of the people, not their titles
- One short paragraph on each person, then one sentence on why PETE
  thinks they should talk
- No bullet points
- No more than 200 words total
- Close by stepping back: "I'll leave the rest to you."
- Sign off as PETE

Return ONLY a JSON object:
{{
  "subject": "email subject line",
  "body": "full email body"
}}

No preamble. No markdown fences. Valid JSON only.
"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip().replace("```json","").replace("```","").strip()
    return json.loads(raw)


def send_introduction(
    caller_profile: dict,
    opportunity: dict,
    dry_run: bool = False,
) -> dict:
    """
    Looks up the match, drafts the intro email, and sends it.
    dry_run=True logs the email without sending — useful for testing.
    """
    match_uid = opportunity.get("match_uid")
    if not match_uid:
        return {"ok": False, "reason": "No match UID provided."}

    match_record = load_member_profile(match_uid)
    if not match_record:
        return {"ok": False, "reason": f"Match UID {match_uid} not found in member database."}

    match_profile = match_record["pete_profile"]

    # Check confidence threshold
    confidence = opportunity.get("confidence", 0.0)
    if confidence < INTRO_CONFIDENCE_THRESHOLD:
        return {
            "ok": False,
            "reason": f"Confidence {confidence:.2f} below threshold {INTRO_CONFIDENCE_THRESHOLD}. Flagged for owner review.",
            "flagged": True,
        }

    # Draft the intro
    email = draft_intro_email(caller_profile, match_profile, opportunity)

    caller_email = caller_profile.get("email")
    match_email = match_profile.get("email")

    if not caller_email or not match_email:
        return {"ok": False, "reason": "Missing email address for one or both parties."}

    if dry_run:
        print(f"\n--- DRY RUN INTRO EMAIL ---")
        print(f"To: {caller_email}, {match_email}")
        print(f"Subject: {email['subject']}")
        print(f"\n{email['body']}\n")
        return {"ok": True, "dry_run": True, "email": email}

    # Send
    msg = MIMEMultipart()
    msg["From"] = f"PETE <{FROM_EMAIL}>"
    msg["To"] = f"{caller_email}, {match_email}"
    msg["Subject"] = email["subject"]
    msg.attach(MIMEText(email["body"], "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return {"ok": True, "email": email}
    except Exception as e:
        return {"ok": False, "reason": str(e)}
```

---

## Part 4: Owner Email Summary

```python
# pete_owner_notify.py

import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

SMTP_HOST = "smtp.sendgrid.net"
SMTP_PORT = 587
SMTP_USER = "apikey"
SMTP_PASS = "your_sendgrid_api_key"
FROM_EMAIL = "pete@theoperators.pe"
OWNER_EMAIL = "kit@theoperators.pe"


def send_owner_summary(
    member_profile: dict,
    analysis: dict,
    intros_sent: list,
    intros_flagged: list,
    call_duration_min: float,
    call_cost_usd: float,
):
    """
    Sends Kit a post-call email summary with everything PETE learned
    and every action taken.
    """
    name = member_profile.get("full_name", "Unknown")
    summary = analysis.get("call_summary", "No summary available.")
    quality = analysis.get("overall_call_quality", "—")
    confidence = analysis.get("pete_confidence_in_member", 0.0)
    quotes = analysis.get("notable_quotes", [])
    red_flags = analysis.get("red_flags", [])
    community_recs = analysis.get("community_recommendations", [])
    intros = analysis.get("introduction_opportunities", [])

    # Build email body
    lines = []
    lines.append(f"PETE just finished a call with {name}.")
    lines.append(f"Duration: {call_duration_min:.1f} min  |  Cost: ${call_cost_usd:.2f}  |  Call quality: {quality}  |  PETE confidence: {confidence:.0%}")
    lines.append("")
    lines.append("─" * 60)
    lines.append("")
    lines.append("WHAT THEY NEED")
    lines.append("")
    lines.append(summary)
    lines.append("")

    if quotes:
        lines.append("WHAT THEY SAID")
        lines.append("")
        for q in quotes[:3]:
            lines.append(f'  "{q}"')
        lines.append("")

    lines.append("─" * 60)
    lines.append("")
    lines.append("INTRODUCTION OPPORTUNITIES")
    lines.append("")
    if intros:
        for opp in intros:
            status = "✓ Sent" if opp in intros_sent else ("⚑ Flagged for review" if opp in intros_flagged else "— Not sent")
            lines.append(f"  {status}  |  {opp.get('match_name')}  |  Confidence: {opp.get('confidence', 0):.0%}")
            lines.append(f"  Need: {opp.get('caller_need')}")
            lines.append(f"  Why: {opp.get('why_this_match')}")
            lines.append("")
    else:
        lines.append("  No strong matches identified on this call.")
        lines.append("")

    if intros_flagged:
        lines.append("  Flagged intros (confidence below threshold — your call):")
        for opp in intros_flagged:
            lines.append(f"  → {opp.get('match_name')}  ({opp.get('confidence', 0):.0%})")
            lines.append(f"     {opp.get('why_this_match')}")
        lines.append("")

    lines.append("─" * 60)
    lines.append("")
    lines.append("COMMUNITY RECOMMENDATIONS")
    lines.append("")
    if community_recs:
        for rec in community_recs:
            lines.append(f"  [{rec.get('actionability', '—').upper()}]  {rec.get('theme')}")
            lines.append(f"  \"{rec.get('verbatim_signal')}\"")
            lines.append("")
    else:
        lines.append("  Nothing notable raised.")
        lines.append("")

    if red_flags:
        lines.append("─" * 60)
        lines.append("")
        lines.append("⚠  RED FLAGS")
        lines.append("")
        for flag in red_flags:
            lines.append(f"  • {flag}")
        lines.append("")

    body = "\n".join(lines)

    msg = MIMEMultipart()
    msg["From"] = f"PETE <{FROM_EMAIL}>"
    msg["To"] = OWNER_EMAIL
    msg["Subject"] = f"PETE call: {name} — {datetime.now().strftime('%b %d, %Y')}"
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print(f"[NOTIFY] Owner summary sent for {name}")
    except Exception as e:
        print(f"[NOTIFY ERROR] {e}")
```

---

## Part 5: Master Post-Call Orchestrator

This is the single function called by the Retell webhook.
It runs every step in sequence.

```python
# pete_postcall.py

import json
import requests
from pathlib import Path
from datetime import datetime

from pete_transcript_analyzer import analyze_transcript
from pete_member_index import load_member_index
from pete_intro_engine import send_introduction, INTRO_CONFIDENCE_THRESHOLD
from pete_owner_notify import send_owner_summary
from pete_budget import record_call
from pete_profile_loader import load_member_profile

RETELL_API_KEY = "your_retell_api_key_here"
CALL_RECORDS_FILE = "data/pete_call_records.json"


def fetch_retell_transcript(call_id: str) -> str:
    """Fetches the full transcript from Retell's API."""
    url = f"https://api.retellai.com/v2/get-call/{call_id}"
    headers = {"Authorization": f"Bearer {RETELL_API_KEY}"}
    response = requests.get(url, headers=headers)
    data = response.json()

    transcript = data.get("transcript", "")
    if not transcript:
        # Fallback: build from transcript_object if available
        turns = data.get("transcript_object", [])
        lines = []
        for turn in turns:
            role = "PETE" if turn.get("role") == "agent" else "MEMBER"
            lines.append(f"{role}: {turn.get('content', '')}")
        transcript = "\n".join(lines)

    return transcript, data


def process_call(webhook_payload: dict):
    """
    Master orchestrator. Called by the Retell webhook handler
    in pete_optin_api.py when call_ended fires.
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
        if confidence >= INTRO_CONFIDENCE_THRESHOLD:
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
    """
    Applies non-null profile updates from the call analysis
    back to the member CSV record.
    Placeholder — in production, write to your database.
    """
    clean = {k: v for k, v in updates.items() if v is not None}
    if clean:
        print(f"[PROFILE UPDATE] UID {member_uid}: {list(clean.keys())}")
        # TODO: write clean fields back to your member database
```

---

## Part 6: Updated Webhook Handler

Replace the `call_ended_webhook` in `pete_optin_api.py` with this:

```python
@app.route("/api/pete/call-ended", methods=["POST"])
def call_ended_webhook():
    """Retell fires this when a call completes."""
    from pete_postcall import process_call
    payload = request.get_json()
    # Run async in production so the webhook returns immediately
    process_call(payload)
    return jsonify({"ok": True})
```

---

## Part 7: What a Owner Summary Email Looks Like

```
From: PETE <pete@theoperators.pe>
To: kit@theoperators.pe
Subject: PETE call: Sarah Chen — Apr 22, 2026

PETE just finished a call with Sarah Chen.
Duration: 22.4 min  |  Cost: $1.57  |  Call quality: strong  |  PETE confidence: 87%

────────────────────────────────────────────────────────────

WHAT THEY NEED

Sarah is a two-time PE-backed CFO in healthcare services who is
quietly looking for her next role. She's done with $5-25M EBITDA
companies and wants to move upmarket — $50M+ — with a fund that
invests in the hold period, not just at entry and exit.

WHAT THEY SAID

  "The last fund I worked with was great on the deal side but
   disappeared the moment the 100-day plan was done."

  "I want a sponsor who actually wants to hear from the CFO."

────────────────────────────────────────────────────────────

INTRODUCTION OPPORTUNITIES

  ✓ Sent  |  Marcus Webb  |  Confidence: 91%
  Need: CFO role in PE-backed healthcare, $50M+ EBITDA, engaged sponsor
  Why: Marcus is Head of Talent at Ridgeline Partners — mid-market
       healthcare focus, known for operator engagement

  ⚑ Flagged for review  |  James Okafor  |  Confidence: 78%
  Need: Same as above
  Why: James is a sitting CFO who may be transitioning — could be
       a peer connection rather than an opportunity

────────────────────────────────────────────────────────────

COMMUNITY RECOMMENDATIONS

  [HIGH]  More content on sponsor-operator dynamics post-close
  "Nobody talks about what happens after the 100-day plan. That's
   when it either works or it doesn't."

  [MEDIUM]  CFO-specific peer group or subspace
  "I don't always want to be in a room with CEOs. The CFO lens
   is different."
```

---

*PETE Post-Call Layer v1.0*
*Transcript Analysis · Profile Updates · Auto Intros · Owner Summaries*
