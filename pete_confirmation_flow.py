# pete_confirmation_flow.py

import smtplib
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pete_db import get_conn
from pete_profile_loader import load_member_profile

SMTP_HOST = "smtp.sendgrid.net"
SMTP_PORT = 587
SMTP_USER = "apikey"
SMTP_PASS = os.getenv("SENDGRID_API_KEY", "your_sendgrid_api_key")
FROM_EMAIL = os.getenv("FROM_EMAIL", "pete@theoperators.pe")
BASE_URL = os.getenv("BASE_URL", "https://yoursite.com")


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

    seeker_name = match["seeker_name"]
    provider_name = match["provider_name"]
    rationale = match["match_rationale"]

    seeker_link = f"{BASE_URL}/pete/confirm?token={seeker_token}&match={match_id}"
    provider_link = f"{BASE_URL}/pete/confirm?token={provider_token}&match={match_id}"
    decline_seeker = f"{BASE_URL}/pete/decline?token={seeker_token}&match={match_id}"
    decline_provider = f"{BASE_URL}/pete/decline?token={provider_token}&match={match_id}"

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

    _send_email(match["seeker_email"], "PETE would like to make an introduction", seeker_body)
    _send_email(match["provider_email"], "PETE would like to make an introduction", provider_body)
    print(f"[CONFIRM] Confirmation emails sent for match {match_id}")


def handle_confirmation(token: str, match_id: int) -> str:
    """Called when someone clicks their confirmation link."""
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
    from pete_intro_engine import draft_intro_email

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

    seeker_profile = load_member_profile(match["seeker_uid"])["pete_profile"]
    provider_profile = load_member_profile(match["provider_uid"])["pete_profile"]

    opportunity = {
        "why_this_match": match["match_rationale"],
        "caller_need": match["need_desc"],
    }

    email = draft_intro_email(seeker_profile, provider_profile, opportunity)

    _send_email(
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