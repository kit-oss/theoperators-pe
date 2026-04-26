# PETE — Matchmaking Database v1.0
## Schema · Extraction · Matching Engine · Confirmation Flow · Oversight Digest

---

## The Core Idea

Every call produces two things for the matchmaking database:
- A **needs record** — what this person is looking for right now
- One or more **offer records** — what they can provide to others

These sit in a persistent database. Every time a new member calls,
PETE checks their profile and needs against all existing open records.
Every time a new offer is added, PETE checks it against all open needs.

The result: a PE investor who tells PETE he needs a sourcing expert for
perishable foods doesn't disappear into a file. His request stays open
and active until it's fulfilled — or he closes it.

---

## Part 1: Database Schema

Use SQLite for simplicity. Swap for Postgres when you're ready to scale.

```python
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
        persona         TEXT,   -- GP, Operator, Advisor, Talent Leader, etc.
        linkedin_url    TEXT,
        location        TEXT,
        last_call_date  TEXT,
        profile_json    TEXT    -- full pete_profile as JSON string
    )
    """)

    # ── Needs ─────────────────────────────────────────────────────────────
    # What someone is looking for. One record per distinct need.
    c.execute("""
    CREATE TABLE IF NOT EXISTS needs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        member_uid      TEXT REFERENCES members(uid),
        category        TEXT,   -- talent / capital / diligence / deal_flow / advisor / peer / other
        description     TEXT,   -- plain English: "CFO for healthcare patient care center, PE-backed"
        sector          TEXT,   -- e.g. "healthcare", "perishable foods"
        geography       TEXT,
        urgency         TEXT,   -- high / medium / low
        specifics_json  TEXT,   -- structured details as JSON
        status          TEXT DEFAULT 'open',  -- open / matched / closed
        created_at      TEXT,
        updated_at      TEXT,
        source_call_id  TEXT    -- which call produced this need
    )
    """)

    # ── Offers ────────────────────────────────────────────────────────────
    # What someone can provide to others. One record per distinct offer.
    c.execute("""
    CREATE TABLE IF NOT EXISTS offers (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        member_uid      TEXT REFERENCES members(uid),
        category        TEXT,   -- same taxonomy as needs
        description     TEXT,   -- plain English: "CFO with PE-backed healthcare experience"
        sector          TEXT,
        geography       TEXT,
        availability    TEXT,   -- immediate / 3-6 months / advisory only / not looking
        specifics_json  TEXT,
        status          TEXT DEFAULT 'active',  -- active / matched / inactive
        created_at      TEXT,
        updated_at      TEXT,
        source_call_id  TEXT
    )
    """)

    # ── Matches ───────────────────────────────────────────────────────────
    # A proposed match between a need and an offer.
    c.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        need_id             INTEGER REFERENCES needs(id),
        offer_id            INTEGER REFERENCES offers(id),
        seeker_uid          TEXT,   -- who has the need
        provider_uid        TEXT,   -- who has the offer
        match_rationale     TEXT,   -- PETE's one-sentence explanation
        confidence          REAL,
        status              TEXT DEFAULT 'pending_confirmation',
        -- pending_confirmation / seeker_confirmed / provider_confirmed
        -- both_confirmed / intro_sent / accepted / declined / gone_quiet
        seeker_confirmed    INTEGER DEFAULT 0,  -- 0/1
        provider_confirmed  INTEGER DEFAULT 0,  -- 0/1
        seeker_token        TEXT,   -- unique confirmation token
        provider_token      TEXT,
        confirmation_sent_at TEXT,
        intro_sent_at       TEXT,
        outcome             TEXT,   -- filled in later: hired / connected / no_fit / unknown
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
```

---

## Part 2: Extracting Needs and Offers from Transcripts

This replaces and extends the transcript analyzer's introduction logic.
PETE now extracts structured needs and offers — not just match signals.

```python
# pete_match_extractor.py

import anthropic
import json
from datetime import datetime
from pete_db import get_conn

client = anthropic.Anthropic()


def extract_needs_and_offers(
    transcript: str,
    member_profile: dict,
    call_id: str,
) -> dict:
    """
    Extracts structured needs and offers from a call transcript.
    Returns a dict with 'needs' and 'offers' lists.
    """
    name = member_profile.get("full_name", "this person")

    prompt = f"""
You are PETE's matchmaking analyst. You have just spoken with {name},
a member of The Operators PE community.

Your job is to extract two things from this transcript:

1. NEEDS — what they are actively looking for help with right now
2. OFFERS — what they can genuinely provide to others in the ecosystem

Be specific. "Looking for a CFO" is not specific enough.
"Looking for a CFO with PE-backed healthcare experience, $50M+ EBITDA,
comfortable with a 100-day integration plan" is specific.

Category taxonomy (use exactly these values):
  talent        — looking for / can offer an executive or operator
  capital       — looking for / can offer investment or co-investment
  diligence     — looking for / can provide due diligence expertise
  deal_flow     — looking for / can provide deal introductions
  advisor       — looking for / can serve as a board member or advisor
  peer          — looking for a peer connection or sounding board
  other         — anything that doesn't fit above

## Member Profile
{json.dumps(member_profile, indent=2)}

## Call Transcript
{transcript}

---

Return ONLY a valid JSON object. No preamble. No markdown fences.

{{
  "needs": [
    {{
      "category": "",
      "description": "",
      "sector": "",
      "geography": "",
      "urgency": "high / medium / low",
      "specifics": {{
        "role_title": null,
        "ebitda_range": null,
        "experience_required": null,
        "fund_type": null,
        "any_other_detail": null
      }}
    }}
  ],
  "offers": [
    {{
      "category": "",
      "description": "",
      "sector": "",
      "geography": "",
      "availability": "immediate / 3-6 months / advisory only / not looking",
      "specifics": {{
        "role_title": null,
        "ebitda_range": null,
        "years_experience": null,
        "notable_achievements": null,
        "any_other_detail": null
      }}
    }}
  ]
}}

If there are no needs or no offers, return an empty list for that key.
"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip().replace("```json","").replace("```","").strip()
    extracted = json.loads(raw)

    # Save to database
    save_needs_and_offers(
        member_uid=member_profile.get("uid"),
        extracted=extracted,
        call_id=call_id,
    )

    return extracted


def save_needs_and_offers(member_uid: str, extracted: dict, call_id: str):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().isoformat()

    for need in extracted.get("needs", []):
        c.execute("""
            INSERT INTO needs
            (member_uid, category, description, sector, geography,
             urgency, specifics_json, status, created_at, updated_at, source_call_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
        """, (
            member_uid,
            need.get("category"),
            need.get("description"),
            need.get("sector"),
            need.get("geography"),
            need.get("urgency"),
            json.dumps(need.get("specifics", {})),
            now, now, call_id,
        ))

    for offer in extracted.get("offers", []):
        c.execute("""
            INSERT INTO offers
            (member_uid, category, description, sector, geography,
             availability, specifics_json, status, created_at, updated_at, source_call_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """, (
            member_uid,
            offer.get("category"),
            offer.get("description"),
            offer.get("sector"),
            offer.get("geography"),
            offer.get("availability"),
            json.dumps(offer.get("specifics", {})),
            now, now, call_id,
        ))

    conn.commit()
    conn.close()
```

---

## Part 3: Matching Engine

Runs in two directions after every call:
- New needs → checked against all active offers
- New offers → checked against all open needs

```python
# pete_matching_engine.py

import anthropic
import json
import secrets
from datetime import datetime
from pete_db import get_conn
from pete_profile_loader import load_member_profile

client = anthropic.Anthropic()
MATCH_CONFIDENCE_THRESHOLD = 0.80


def run_matching_for_member(member_uid: str):
    """
    After a call, run matching in both directions for this member:
    - Their new needs vs all active offers
    - Their new offers vs all open needs
    """
    conn = get_conn()
    c = conn.cursor()

    # Get this member's open needs (just added this call)
    c.execute("""
        SELECT * FROM needs
        WHERE member_uid = ? AND status = 'open'
        ORDER BY created_at DESC LIMIT 10
    """, (member_uid,))
    my_needs = [dict(row) for row in c.fetchall()]

    # Get this member's active offers (just added this call)
    c.execute("""
        SELECT * FROM offers
        WHERE member_uid = ? AND status = 'active'
        ORDER BY created_at DESC LIMIT 10
    """, (member_uid,))
    my_offers = [dict(row) for row in c.fetchall()]

    # Get all other members' active offers
    c.execute("""
        SELECT o.*, m.full_name, m.email, m.headline
        FROM offers o JOIN members m ON o.member_uid = m.uid
        WHERE o.status = 'active' AND o.member_uid != ?
    """, (member_uid,))
    all_offers = [dict(row) for row in c.fetchall()]

    # Get all other members' open needs
    c.execute("""
        SELECT n.*, m.full_name, m.email, m.headline
        FROM needs n JOIN members m ON n.member_uid = m.uid
        WHERE n.status = 'open' AND n.member_uid != ?
    """, (member_uid,))
    all_needs = [dict(row) for row in c.fetchall()]

    conn.close()

    proposed_matches = []

    # My needs vs available offers
    for need in my_needs:
        matches = score_need_against_offers(need, all_offers, member_uid)
        proposed_matches.extend(matches)

    # My offers vs open needs
    for offer in my_offers:
        matches = score_offer_against_needs(offer, all_needs, member_uid)
        proposed_matches.extend(matches)

    # Deduplicate and save
    for match in proposed_matches:
        if match["confidence"] >= MATCH_CONFIDENCE_THRESHOLD:
            save_proposed_match(match)

    return proposed_matches


def score_need_against_offers(need: dict, offers: list, seeker_uid: str) -> list:
    """Uses Claude to score a need against a list of offers."""
    if not offers:
        return []

    offers_text = "\n".join([
        f"[OFFER {o['id']}] {o['full_name']} | {o['description']} | "
        f"Sector: {o['sector']} | Availability: {o['availability']}"
        for o in offers
    ])

    prompt = f"""
You are PETE's matching engine. Score how well each offer matches this need.

NEED: {need['description']}
Sector: {need['sector']} | Urgency: {need['urgency']}
Details: {need['specifics_json']}

AVAILABLE OFFERS:
{offers_text}

Return ONLY a JSON array. No preamble. No markdown fences.
Only include offers with genuine fit (confidence >= 0.70).

[
  {{
    "offer_id": 0,
    "confidence": 0.0,
    "rationale": "one sentence explaining why this is a good match"
  }}
]
"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip().replace("```json","").replace("```","").strip()
    scored = json.loads(raw)

    # Build match proposals
    offer_map = {o["id"]: o for o in offers}
    results = []
    for s in scored:
        offer = offer_map.get(s["offer_id"])
        if offer:
            results.append({
                "need_id": need["id"],
                "offer_id": s["offer_id"],
                "seeker_uid": seeker_uid,
                "provider_uid": offer["member_uid"],
                "match_rationale": s["rationale"],
                "confidence": s["confidence"],
            })
    return results


def score_offer_against_needs(offer: dict, needs: list, provider_uid: str) -> list:
    """Uses Claude to score an offer against a list of open needs."""
    if not needs:
        return []

    needs_text = "\n".join([
        f"[NEED {n['id']}] {n['full_name']} | {n['description']} | "
        f"Sector: {n['sector']} | Urgency: {n['urgency']}"
        for n in needs
    ])

    prompt = f"""
You are PETE's matching engine. Score how well this offer matches each open need.

OFFER: {offer['description']}
Sector: {offer['sector']} | Availability: {offer['availability']}
Details: {offer['specifics_json']}

OPEN NEEDS:
{needs_text}

Return ONLY a JSON array. No preamble. No markdown fences.
Only include needs with genuine fit (confidence >= 0.70).

[
  {{
    "need_id": 0,
    "confidence": 0.0,
    "rationale": "one sentence explaining why this is a good match"
  }}
]
"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip().replace("```json","").replace("```","").strip()
    scored = json.loads(raw)

    need_map = {n["id"]: n for n in needs}
    results = []
    for s in scored:
        need = need_map.get(s["need_id"])
        if need:
            results.append({
                "need_id": s["need_id"],
                "offer_id": offer["id"],
                "seeker_uid": need["member_uid"],
                "provider_uid": provider_uid,
                "match_rationale": s["rationale"],
                "confidence": s["confidence"],
            })
    return results


def save_proposed_match(match: dict):
    """Saves a proposed match and fires confirmation emails."""
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().isoformat()

    # Check for duplicate
    c.execute("""
        SELECT id FROM matches
        WHERE need_id = ? AND offer_id = ?
        AND status NOT IN ('declined', 'gone_quiet')
    """, (match["need_id"], match["offer_id"]))
    if c.fetchone():
        conn.close()
        return  # Already proposed

    seeker_token = secrets.token_urlsafe(24)
    provider_token = secrets.token_urlsafe(24)

    c.execute("""
        INSERT INTO matches
        (need_id, offer_id, seeker_uid, provider_uid, match_rationale,
         confidence, status, seeker_token, provider_token,
         confirmation_sent_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'pending_confirmation', ?, ?, ?, ?, ?)
    """, (
        match["need_id"], match["offer_id"],
        match["seeker_uid"], match["provider_uid"],
        match["match_rationale"], match["confidence"],
        seeker_token, provider_token,
        now, now, now,
    ))

    match_id = c.lastrowid
    conn.commit()
    conn.close()

    # Send confirmation emails to both parties
    from pete_confirmation_flow import send_confirmation_emails
    send_confirmation_emails(match_id, seeker_token, provider_token)
```

---

## Part 4: Confirmation Flow

PETE emails both parties separately. Each gets a unique link.
When both confirm, the intro email goes automatically.

```python
# pete_confirmation_flow.py

import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pete_db import get_conn
from pete_profile_loader import load_member_profile

SMTP_HOST = "smtp.sendgrid.net"
SMTP_PORT = 587
SMTP_USER = "apikey"
SMTP_PASS = "your_sendgrid_api_key"
FROM_EMAIL = "pete@theoperators.pe"
BASE_URL = "https://yoursite.com"  # your domain


def send_confirmation_emails(match_id: int, seeker_token: str, provider_token: str):
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        SELECT m.*, 
               n.description as need_desc, n.sector as need_sector,
               o.description as offer_desc,
               sm.full_name as seeker_name, sm.email as seeker_email,
               pm.full_name as provider_name, pm.email as provider_email
        FROM matches m
        JOIN needs n ON m.need_id = n.id
        JOIN offers o ON m.offer_id = o.id
        JOIN members sm ON m.seeker_uid = sm.uid
        JOIN members pm ON m.provider_uid = pm.uid
        WHERE m.id = ?
    """, (match_id,))

    match = dict(c.fetchone())
    conn.close()

    seeker_name  = match["seeker_name"]
    provider_name = match["provider_name"]
    rationale = match["match_rationale"]

    seeker_link   = f"{BASE_URL}/pete/confirm?token={seeker_token}&match={match_id}"
    provider_link = f"{BASE_URL}/pete/confirm?token={provider_token}&match={match_id}"
    decline_seeker   = f"{BASE_URL}/pete/decline?token={seeker_token}&match={match_id}"
    decline_provider = f"{BASE_URL}/pete/confirm?token={provider_token}&match={match_id}"

    # Email to the seeker (person with the need)
    seeker_body = f"""Hi {seeker_name.split()[0]},

PETE here.

I've been thinking about a conversation I had with you, and I'd like
to introduce you to someone — but I want to ask first.

{provider_name} is someone I've spoken with who I think could be
genuinely useful to you. {rationale}

Before I make the introduction, I want to make sure you're open to it.

If you'd like me to connect you:
→ Yes, I'm interested: {seeker_link}

If now isn't the right time:
→ Not right now: {decline_seeker}

Either answer is completely fine. I'll only send the introduction
if you both say yes.

PETE
Private Equity's Trusted Envoy
"""

    # Email to the provider (person with the offer/expertise)
    provider_body = f"""Hi {provider_name.split()[0]},

PETE here.

I'd like to introduce you to {seeker_name} — but I want to check
with you before I do.

{rationale}

I think there's a real reason for you two to talk. But I always
ask both people first.

If you're open to an introduction:
→ Yes, connect us: {provider_link}

If now isn't the right time:
→ Not right now: {decline_provider}

No pressure either way.

PETE
Private Equity's Trusted Envoy
"""

    _send_email(match["seeker_email"],  "PETE would like to make an introduction", seeker_body)
    _send_email(match["provider_email"], "PETE would like to make an introduction", provider_body)
    print(f"[CONFIRM] Confirmation emails sent for match {match_id}")


def handle_confirmation(token: str, match_id: int) -> str:
    """
    Called when someone clicks their confirmation link.
    Returns 'waiting' or 'intro_sent'.
    """
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().isoformat()

    c.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
    match = dict(c.fetchone())

    if token == match["seeker_token"]:
        c.execute("""
            UPDATE matches SET seeker_confirmed = 1,
            status = 'seeker_confirmed', updated_at = ?
            WHERE id = ?
        """, (now, match_id))

    elif token == match["provider_token"]:
        c.execute("""
            UPDATE matches SET provider_confirmed = 1,
            status = 'provider_confirmed', updated_at = ?
            WHERE id = ?
        """, (now, match_id))

    conn.commit()

    # Re-fetch to check if both have confirmed
    c.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
    updated = dict(c.fetchone())
    conn.close()

    if updated["seeker_confirmed"] and updated["provider_confirmed"]:
        _fire_introduction(match_id)
        return "intro_sent"

    return "waiting"


def handle_decline(token: str, match_id: int):
    """Called when someone clicks the decline link."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE matches SET status = 'declined', updated_at = ?
        WHERE id = ?
    """, (datetime.now().isoformat(), match_id))
    conn.commit()
    conn.close()
    print(f"[CONFIRM] Match {match_id} declined.")


def _fire_introduction(match_id: int):
    """Both confirmed — send the actual intro email."""
    from pete_intro_engine import draft_intro_email, _send_email as send_email_direct

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT m.*,
               sm.full_name as seeker_name, sm.email as seeker_email,
               pm.full_name as provider_name, pm.email as provider_email,
               n.description as need_desc, o.description as offer_desc
        FROM matches m
        JOIN members sm ON m.seeker_uid = sm.uid
        JOIN members pm ON m.provider_uid = pm.uid
        JOIN needs n ON m.need_id = n.id
        JOIN offers o ON m.offer_id = o.id
        WHERE m.id = ?
    """, (match_id,))
    match = dict(c.fetchone())

    seeker_profile  = load_member_profile(match["seeker_uid"])["pete_profile"]
    provider_profile = load_member_profile(match["provider_uid"])["pete_profile"]

    opportunity = {
        "why_this_match": match["match_rationale"],
        "caller_need": match["need_desc"],
    }

    email = draft_intro_email(seeker_profile, provider_profile, opportunity)

    send_email_direct(
        to=f"{match['seeker_email']}, {match['provider_email']}",
        subject=email["subject"],
        body=email["body"],
    )

    now = datetime.now().isoformat()
    c.execute("""
        UPDATE matches
        SET status = 'intro_sent', intro_sent_at = ?, updated_at = ?
        WHERE id = ?
    """, (now, now, match_id))

    # Mark need and offer as matched
    c.execute("UPDATE needs SET status = 'matched', updated_at = ? WHERE id = ?",
              (now, match["need_id"]))
    c.execute("UPDATE offers SET status = 'matched', updated_at = ? WHERE id = ?",
              (now, match["offer_id"]))

    conn.commit()
    conn.close()
    print(f"[INTRO] Introduction fired for match {match_id}.")


def _send_email(to: str, subject: str, body: str):
    msg = MIMEMultipart()
    msg["From"] = f"PETE <{FROM_EMAIL}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
```

---

## Part 5: Confirmation Webhook Routes

Add these two routes to `pete_optin_api.py`:

```python
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
```

---

## Part 6: Weekly Unmatched Digest

Runs every Monday. Emails you every open need that has
sat unmatched for 7+ days, so you can source manually.

```python
# pete_digest.py
# Schedule with cron: 0 8 * * 1 python pete_digest.py

import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pete_db import get_conn

FROM_EMAIL = "pete@theoperators.pe"
OWNER_EMAIL = "kit@theoperators.pe"
SMTP_HOST = "smtp.sendgrid.net"
SMTP_PORT = 587
SMTP_USER = "apikey"
SMTP_PASS = "your_sendgrid_api_key"


def send_weekly_digest():
    conn = get_conn()
    c = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()

    # Open needs older than 7 days with no pending or completed match
    c.execute("""
        SELECT n.*, m.full_name, m.email, m.headline
        FROM needs n
        JOIN members m ON n.member_uid = m.uid
        WHERE n.status = 'open'
          AND n.created_at < ?
          AND n.id NOT IN (
              SELECT need_id FROM matches
              WHERE status NOT IN ('declined', 'gone_quiet')
          )
        ORDER BY n.urgency DESC, n.created_at ASC
    """, (cutoff,))
    unmatched_needs = [dict(row) for row in c.fetchall()]

    # Match pipeline summary
    c.execute("""
        SELECT status, COUNT(*) as count
        FROM matches GROUP BY status
    """)
    pipeline = {row["status"]: row["count"] for row in c.fetchall()}

    # Community signals this week
    c.execute("""
        SELECT theme, COUNT(*) as count, actionability
        FROM community_signals
        WHERE created_at > ?
        GROUP BY theme
        ORDER BY count DESC
        LIMIT 10
    """, (cutoff,))
    signals = [dict(row) for row in c.fetchall()]

    conn.close()

    if not unmatched_needs and not signals:
        print("[DIGEST] Nothing to report this week.")
        return

    lines = []
    lines.append(f"PETE WEEKLY DIGEST — {datetime.now().strftime('%B %d, %Y')}")
    lines.append("")
    lines.append("MATCH PIPELINE")
    lines.append("")
    for status, count in pipeline.items():
        lines.append(f"  {status.replace('_',' ').title()}: {count}")
    lines.append("")
    lines.append("─" * 60)
    lines.append("")

    if unmatched_needs:
        lines.append(f"OPEN NEEDS WITH NO MATCH ({len(unmatched_needs)})")
        lines.append("These have been sitting open for 7+ days.")
        lines.append("Consider sourcing manually or broadening the search.")
        lines.append("")
        for need in unmatched_needs:
            age_days = (datetime.now() - datetime.fromisoformat(need["created_at"])).days
            lines.append(f"  [{need['urgency'].upper()}]  {need['full_name']}")
            lines.append(f"  {need['description']}")
            lines.append(f"  Sector: {need['sector']} | Open for {age_days} days")
            lines.append("")
    else:
        lines.append("No unmatched open needs this week. PETE is on top of it.")
        lines.append("")

    if signals:
        lines.append("─" * 60)
        lines.append("")
        lines.append("COMMUNITY SIGNALS THIS WEEK")
        lines.append("")
        for s in signals:
            lines.append(f"  [{s['actionability'].upper()}]  {s['theme']}  (mentioned {s['count']}x)")
        lines.append("")

    body = "\n".join(lines)

    msg = MIMEMultipart()
    msg["From"] = f"PETE <{FROM_EMAIL}>"
    msg["To"] = OWNER_EMAIL
    msg["Subject"] = f"PETE Weekly Digest — {datetime.now().strftime('%b %d')}"
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

    print(f"[DIGEST] Weekly digest sent. {len(unmatched_needs)} unmatched needs reported.")


if __name__ == "__main__":
    send_weekly_digest()
```

---

## Part 7: Updated Post-Call Orchestrator

Add these calls to `pete_postcall.py` after transcript analysis:

```python
# In process_call(), after analyze_transcript():

from pete_match_extractor import extract_needs_and_offers
from pete_matching_engine import run_matching_for_member
from pete_db import get_conn

# 5a. Upsert member record
upsert_member(member_uid, member_profile)

# 5b. Extract and save needs + offers
extract_needs_and_offers(transcript, member_profile, call_id)

# 5c. Run matching engine
proposed = run_matching_for_member(member_uid)
high_confidence = [m for m in proposed if m["confidence"] >= 0.80]
flagged = [m for m in proposed if m["confidence"] < 0.80]

print(f"[MATCHING] {len(high_confidence)} confirmation(s) sent, {len(flagged)} below threshold.")


def upsert_member(uid: str, profile: dict):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO members (uid, full_name, email, headline,
            current_status, linkedin_url, location, last_call_date, profile_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(uid) DO UPDATE SET
            full_name = excluded.full_name,
            headline = excluded.headline,
            current_status = excluded.current_status,
            last_call_date = excluded.last_call_date,
            profile_json = excluded.profile_json
    """, (
        uid,
        profile.get("full_name"),
        profile.get("email"),
        profile.get("headline"),
        profile.get("current_status"),
        profile.get("linkedin_url"),
        profile.get("location"),
        datetime.now().isoformat(),
        json.dumps(profile),
    ))
    conn.commit()
    conn.close()
```

---

*PETE Matchmaking Database v1.0*
*Schema · Extraction · Matching Engine · Confirmation Flow · Weekly Digest*
