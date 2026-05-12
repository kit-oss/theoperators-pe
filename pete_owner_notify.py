# pete_owner_notify.py

import smtplib
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

SMTP_HOST = "smtp.sendgrid.net"
SMTP_PORT = 587
SMTP_USER = "apikey"
SMTP_PASS = os.getenv("SENDGRID_API_KEY", "your_sendgrid_api_key")
FROM_EMAIL = os.getenv("FROM_EMAIL", "pete@theoperators.pe")
OWNER_EMAIL = os.getenv("OWNER_EMAIL", "kit@theoperators.pe")


def send_owner_summary(
    member_profile: dict,
    analysis: dict,
    intros_sent: list,
    intros_flagged: list,
    call_duration_min: float,
    call_cost_usd: float,
):
    """
    Sends Kit a post-call email summary.
    """
    name = member_profile.get("full_name", "Unknown")
    summary = analysis.get("call_summary", "No summary available.")
    quality = analysis.get("overall_call_quality", "—")
    confidence = analysis.get("pete_confidence_in_member", 0.0)
    quotes = analysis.get("notable_quotes", [])
    red_flags = analysis.get("red_flags", [])
    community_recs = analysis.get("community_recommendations", [])
    intros = analysis.get("introduction_opportunities", [])

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