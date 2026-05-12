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