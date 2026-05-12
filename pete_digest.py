# pete_digest.py
# Schedule with cron: 0 8 * * 1 python pete_digest.py

import smtplib
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pete_db import get_conn

FROM_EMAIL = os.getenv("FROM_EMAIL", "pete@theoperators.pe")
OWNER_EMAIL = os.getenv("OWNER_EMAIL", "kit@theoperators.pe")
SMTP_HOST = "smtp.sendgrid.net"
SMTP_PORT = 587
SMTP_USER = "apikey"
SMTP_PASS = os.getenv("SENDGRID_API_KEY", "your_sendgrid_api_key")


def send_weekly_digest():
    conn = get_conn()
    c = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()

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

    c.execute("""
        SELECT status, COUNT(*) as count
        FROM matches GROUP BY status
    """)
    pipeline = {row["status"]: row["count"] for row in c.fetchall()}

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

    with smtplib.SMTP(SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

    print(f"[DIGEST] Weekly digest sent. {len(unmatched_needs)} unmatched needs reported.")


if __name__ == "__main__":
    send_weekly_digest()