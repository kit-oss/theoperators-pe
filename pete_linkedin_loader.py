# pete_linkedin_loader.py (v1.1 — Apify)

import anthropic
import json
import time
import requests
import os

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "your_apify_token_here")
APIFY_ACTOR_ID = "get-leads~linkedin-scraper"


def fetch_linkedin_profile_apify(linkedin_url: str) -> dict:
    """
    Fetches a LinkedIn profile via Apify's All-in-One LinkedIn Scraper.
    No LinkedIn cookies or login required.
    """
    run_url = f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}/runs"
    headers = {
        "Authorization": f"Bearer {APIFY_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "startUrls": [{"url": linkedin_url}],
        "scrapeMode": "Profile",
        "maxResults": 1,
    }

    response = requests.post(run_url, headers=headers, json=payload)
    run_data = response.json()
    run_id = run_data["data"]["id"]

    dataset_url = (
        f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items"
        f"?token={APIFY_API_TOKEN}"
    )
    for _ in range(15):
        time.sleep(2)
        result = requests.get(dataset_url).json()
        if result:
            return result[0]

    return {}


def summarize_linkedin_for_pete(linkedin_url: str, person_name: str) -> dict:
    """
    Fetches a LinkedIn profile via Apify and uses Claude to
    summarize it into a PETE-compatible profile dict.
    """
    raw = fetch_linkedin_profile_apify(linkedin_url)

    if not raw:
        return {
            "pete_profile": {
                "full_name": person_name,
                "linkedin_url": linkedin_url,
                "is_member": False,
                "profile_source": "linkedin_summary",
                "headline": None,
                "pe_experience_inferred": "Could not retrieve LinkedIn profile.",
            }
        }

    client = anthropic.Anthropic()

    prompt = f"""
You are preparing a briefing for PETE, a private equity talent connector.

Below is structured LinkedIn profile data for {person_name}.
Extract and return ONLY a valid JSON object with these fields.
Use null for anything not present. No preamble. No markdown fences.

{{
  "headline": "",
  "location": "",
  "company": "",
  "current_status": "",
  "roles_comfortable_with": [],
  "industries": [],
  "skills": [],
  "personal_brand": "",
  "pe_experience_inferred": "",
  "notable_career_moments": ""
}}

PROFILE DATA:
{json.dumps(raw, indent=2)[:5000]}
"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        summary = json.loads(message.content[0].text)
    except json.JSONDecodeError:
        clean = message.content[0].text.replace("```json", "").replace("```", "").strip()
        summary = json.loads(clean)

    return {
        "pete_profile": {
            "full_name": person_name,
            "linkedin_url": linkedin_url,
            "is_member": False,
            "profile_source": "linkedin_summary",
            **summary,
        }
    }