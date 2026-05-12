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
    After a call, run matching in both directions for this member.
    """
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        SELECT * FROM needs
        WHERE member_uid = ? AND status = 'open'
        ORDER BY created_at DESC LIMIT 10
    """, (member_uid,))
    my_needs = [dict(row) for row in c.fetchall()]

    c.execute("""
        SELECT * FROM offers
        WHERE member_uid = ? AND status = 'active'
        ORDER BY created_at DESC LIMIT 10
    """, (member_uid,))
    my_offers = [dict(row) for row in c.fetchall()]

    c.execute("""
        SELECT o.*, m.full_name, m.email, m.headline
        FROM offers o JOIN members m ON o.member_uid = m.uid
        WHERE o.status = 'active' AND o.member_uid != ?
    """, (member_uid,))
    all_offers = [dict(row) for row in c.fetchall()]

    c.execute("""
        SELECT n.*, m.full_name, m.email, m.headline
        FROM needs n JOIN members m ON n.member_uid = m.uid
        WHERE n.status = 'open' AND n.member_uid != ?
    """, (member_uid,))
    all_needs = [dict(row) for row in c.fetchall()]

    conn.close()

    proposed_matches = []

    for need in my_needs:
        matches = score_need_against_offers(need, all_offers, member_uid)
        proposed_matches.extend(matches)

    for offer in my_offers:
        matches = score_offer_against_needs(offer, all_needs, member_uid)
        proposed_matches.extend(matches)

    for match in proposed_matches:
        if match["confidence"] >= MATCH_CONFIDENCE_THRESHOLD:
            save_proposed_match(match)

    return proposed_matches


def score_need_against_offers(need: dict, offers: list, seeker_uid: str) -> list:
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

    c.execute("""
        SELECT id FROM matches
        WHERE need_id = ? AND offer_id = ?
        AND status NOT IN ('declined', 'gone_quiet')
    """, (match["need_id"], match["offer_id"]))
    if c.fetchone():
        conn.close()
        return

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

    from pete_confirmation_flow import send_confirmation_emails
    send_confirmation_emails(match_id, seeker_token, provider_token)