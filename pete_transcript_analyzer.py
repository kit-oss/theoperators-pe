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
- pete_confidence_in_member: 0.0–1.0. How well did PETE understand this person?
- red_flags: list any concerns. Empty list if none.
- profile_updates: only include fields where the call revealed something new.
"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)