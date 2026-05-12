# pete_intro_engine.py

import anthropic
import json
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pete_profile_loader import load_member_profile

client = anthropic.Anthropic()

INTRO_CONFIDENCE_THRESHOLD = 0.85
SMTP_HOST = "smtp.sendgrid.net"
SMTP_PORT = 587
SMTP_USER = "apikey"
SMTP_PASS = os.getenv("SENDGRID_API_KEY", "your_sendgrid_api_key")
FROM_EMAIL = os.getenv("FROM_EMAIL", "pete@theoperators.pe")


def draft_intro_email(
    caller_profile: dict,
    match_profile: dict,
    opportunity: dict,
) -> dict:
    """Uses Claude to draft a warm introduction email from PETE."""
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
    """Looks up the match, drafts the intro email, and sends it."""
    match_uid = opportunity.get("match_uid")
    if not match_uid:
        return {"ok": False, "reason": "No match UID provided."}

    match_record = load_member_profile(match_uid)
    if not match_record:
        return {"ok": False, "reason": f"Match UID {match_uid} not found in member database."}

    match_profile = match_record["pete_profile"]

    confidence = opportunity.get("confidence", 0.0)
    if confidence < INTRO_CONFIDENCE_THRESHOLD:
        return {
            "ok": False,
            "reason": f"Confidence {confidence:.2f} below threshold {INTRO_CONFIDENCE_THRESHOLD}. Flagged for owner review.",
            "flagged": True,
        }

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