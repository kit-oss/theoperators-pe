# PETE — Profile System v1.1
## Updated: Apify LinkedIn Lookup + Cost Control Architecture

---

## What Changed in v1.1

- Proxycurl replaced with Apify (Proxycurl shut down July 2025)
- Retell AI recommended over Vapi for budget predictability
- Hard cost controls added throughout
- Call budget enforcer added as standalone module

---

## Part 1: Cost Control Architecture

### The Risk in Plain Terms

At ~$0.15/min all-in (platform + STT + LLM + TTS + telephony):
- A 25-minute PETE call costs roughly $3.75
- 50 calls/month = ~$187
- 200 calls/month = ~$750
- Uncapped community access = unpredictable and potentially ruinous

### The Five Controls

**Control 1 — Switch from Vapi to Retell AI**
Retell charges a flat $0.07/min with no hidden component fees.
Same Claude + ElevenLabs integration. Half the exposure.
Use Retell unless you have a specific reason to stay on Vapi.

**Control 2 — Hard monthly budget cap (in code)**
PETE checks a running call-cost ledger before every call.
If the monthly budget is exhausted, PETE sends a warm message
and adds the person to a waitlist. No exceptions.

**Control 3 — Hard call duration limit**
Every call is capped at 25 minutes at the telephony level,
not just in the prompt. Retell supports max_duration natively.

**Control 4 — Opt-in only, no outbound dialing**
PETE never initiates a call. Every call starts because a member
explicitly requested one. This is the most important control.
No outbound = no runaway bill from a bad loop or misconfiguration.

**Control 5 — Drip release, not open access**
Do not open PETE to all 1,405 members at once.
Release in cohorts of 20-30 per week. This gives you cost
visibility, lets you tune the conversation before scaling,
and creates scarcity (which in PE is a feature, not a bug).

---

## Part 2: Call Budget Enforcer

```python
# pete_budget.py
# Tracks call costs and enforces monthly limits.
# Uses a simple JSON ledger — swap for a database when you're ready.

import json
import os
from datetime import datetime
from pathlib import Path

BUDGET_FILE = "data/pete_call_ledger.json"
MONTHLY_BUDGET_USD = 200.00      # hard cap — change this
COST_PER_MINUTE = 0.07           # Retell AI flat rate
DEFAULT_CALL_MINUTES = 25        # max call duration
COST_PER_CALL_ESTIMATE = COST_PER_MINUTE * DEFAULT_CALL_MINUTES  # = $1.75


def _load_ledger() -> dict:
    if not Path(BUDGET_FILE).exists():
        return {"month": _current_month(), "total_spent": 0.0, "calls": []}
    with open(BUDGET_FILE) as f:
        ledger = json.load(f)
    # Reset if it's a new month
    if ledger.get("month") != _current_month():
        ledger = {"month": _current_month(), "total_spent": 0.0, "calls": []}
        _save_ledger(ledger)
    return ledger


def _save_ledger(ledger: dict):
    Path(BUDGET_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(BUDGET_FILE, "w") as f:
        json.dump(ledger, f, indent=2)


def _current_month() -> str:
    return datetime.now().strftime("%Y-%m")


def can_take_call() -> tuple[bool, str]:
    """
    Returns (True, "") if budget allows a call.
    Returns (False, reason) if budget is exhausted.
    """
    ledger = _load_ledger()
    projected = ledger["total_spent"] + COST_PER_CALL_ESTIMATE
    if projected > MONTHLY_BUDGET_USD:
        remaining = MONTHLY_BUDGET_USD - ledger["total_spent"]
        return False, (
            f"Monthly call budget of ${MONTHLY_BUDGET_USD:.0f} is nearly exhausted. "
            f"${remaining:.2f} remaining. Call added to waitlist."
        )
    return True, ""


def record_call(member_uid: str, duration_minutes: float):
    """Call this after every completed call to update the ledger."""
    ledger = _load_ledger()
    cost = round(duration_minutes * COST_PER_MINUTE, 4)
    ledger["total_spent"] = round(ledger["total_spent"] + cost, 4)
    ledger["calls"].append({
        "uid": member_uid,
        "date": datetime.now().isoformat(),
        "duration_min": duration_minutes,
        "cost_usd": cost,
    })
    _save_ledger(ledger)
    return cost


def monthly_summary() -> dict:
    ledger = _load_ledger()
    return {
        "month": ledger["month"],
        "total_calls": len(ledger["calls"]),
        "total_minutes": sum(c["duration_min"] for c in ledger["calls"]),
        "total_spent_usd": ledger["total_spent"],
        "budget_remaining_usd": round(MONTHLY_BUDGET_USD - ledger["total_spent"], 2),
        "budget_utilization_pct": round(
            ledger["total_spent"] / MONTHLY_BUDGET_USD * 100, 1
        ),
    }
```

---

## Part 3: Updated LinkedIn Loader (Apify)

Replaces the previous Proxycurl-based `pete_linkedin_loader.py`.

```python
# pete_linkedin_loader.py (v1.1 — Apify)

import anthropic
import json
import time
import requests

APIFY_API_TOKEN = "your_apify_token_here"

# Apify Actor ID for the All-in-One LinkedIn Scraper (no cookies required)
# https://apify.com/get-leads/linkedin-scraper
APIFY_ACTOR_ID = "get-leads~linkedin-scraper"


def fetch_linkedin_profile_apify(linkedin_url: str) -> dict:
    """
    Fetches a LinkedIn profile via Apify's All-in-One LinkedIn Scraper.
    No LinkedIn cookies or login required.
    Pay-per-result — costs ~$0.001-0.003 per profile lookup.
    """
    # Start the actor run
    run_url = f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}/runs"
    headers = {
        "Authorization": f"Bearer {APIFY_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "startUrls": [{"url": linkedin_url}],
        "scrapeMode": "Profile",  # Profile mode for person lookups
        "maxResults": 1,
    }

    response = requests.post(run_url, headers=headers, json=payload)
    run_data = response.json()
    run_id = run_data["data"]["id"]

    # Poll for completion (profiles take ~3-5 seconds)
    dataset_url = (
        f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items"
        f"?token={APIFY_API_TOKEN}"
    )
    for _ in range(15):  # max ~30 second wait
        time.sleep(2)
        result = requests.get(dataset_url).json()
        if result:
            return result[0]

    return {}  # timed out — return empty


def summarize_linkedin_for_pete(linkedin_url: str, person_name: str) -> dict:
    """
    Fetches a LinkedIn profile via Apify and uses Claude to
    summarize it into a PETE-compatible profile dict.
    """
    raw = fetch_linkedin_profile_apify(linkedin_url)

    if not raw:
        # Graceful fallback — PETE will fly with name only
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
        # Strip any accidental markdown fences and retry parse
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
```

---

## Part 4: Updated Pre-Call Setup (with budget gate)

```python
# pete_precall.py (v1.1)

from pete_profile_loader import load_member_profile
from pete_linkedin_loader import summarize_linkedin_for_pete
from pete_prompt_builder import build_pete_prompt_injection
from pete_budget import can_take_call

BASE_SYSTEM_PROMPT = open("PETE_system_prompt.md").read()


def prepare_pete_for_call(
    identifier: str = None,
    linkedin_url: str = None,
    person_name: str = None,
) -> dict:
    """
    Returns:
      {
        "approved": True/False,
        "reason": "" or decline message,
        "system_prompt": full prompt string if approved
      }
    """
    # --- Budget gate: check before doing anything else ---
    approved, reason = can_take_call()
    if not approved:
        return {
            "approved": False,
            "reason": reason,
            "system_prompt": None,
        }

    # --- Profile lookup ---
    profile = None
    if identifier:
        profile = load_member_profile(identifier)
    if not profile and linkedin_url and person_name:
        profile = summarize_linkedin_for_pete(linkedin_url, person_name)

    # --- Build prompt ---
    if profile:
        injection = build_pete_prompt_injection(profile)
        full_prompt = injection + "\n\n---\n\n" + BASE_SYSTEM_PROMPT
    else:
        full_prompt = BASE_SYSTEM_PROMPT  # name-only fallback

    return {
        "approved": True,
        "reason": "",
        "system_prompt": full_prompt,
    }
```

---

## Part 5: Retell AI Call Initiation (replaces Vapi for budget control)

```python
# pete_call_initiator.py
# Uses Retell AI ($0.07/min flat) instead of Vapi ($0.13-0.31/min)

import requests
import json

RETELL_API_KEY = "your_retell_api_key_here"
PETE_AGENT_ID = "your_pete_agent_id_here"   # created in Retell dashboard
MAX_CALL_DURATION_SECONDS = 25 * 60         # hard 25-minute cap


def initiate_pete_call(
    phone_number: str,
    system_prompt: str,
    member_uid: str,
) -> dict:
    """
    Initiates an outbound call via Retell AI with PETE's
    dynamically built system prompt injected per-call.
    Max duration enforced at the telephony level.
    """
    url = "https://api.retellai.com/v2/create-phone-call"
    headers = {
        "Authorization": f"Bearer {RETELL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "from_number": "+1XXXXXXXXXX",       # your Retell number
        "to_number": phone_number,
        "agent_id": PETE_AGENT_ID,
        "retell_llm_dynamic_variables": {
            "pete_profile_context": system_prompt,
        },
        "max_call_duration_ms": MAX_CALL_DURATION_SECONDS * 1000,
        "metadata": {
            "member_uid": member_uid,
        },
    }

    response = requests.post(url, headers=headers, json=payload)
    return response.json()


def handle_call_ended_webhook(webhook_payload: dict):
    """
    Call this from your webhook endpoint when Retell fires
    the call_ended event. Records cost to the budget ledger.
    """
    from pete_budget import record_call

    duration_ms = webhook_payload.get("duration_ms", 0)
    duration_min = round(duration_ms / 60000, 2)
    member_uid = webhook_payload.get("metadata", {}).get("member_uid", "unknown")

    cost = record_call(member_uid, duration_min)
    print(f"Call ended: {duration_min} min, ${cost:.4f} — UID: {member_uid}")
```

---

## Part 6: Drip Release Schedule (Recommended)

Rather than opening PETE to all 1,405 members at once,
use a controlled cohort release. This keeps costs visible,
lets you improve PETE's conversation before scaling,
and creates genuine scarcity in the community.

```
Week 1:  20 members  — hand-selected (most active, most networked)
Week 2:  30 members  — next tier, opt-in waitlist opens publicly
Week 3:  50 members  — refine based on call transcripts
Week 4+: 75/week    — until throughput matches budget
```

Suggested selection criteria for early cohorts:
- Networking Mindset = "Actively Networking"
- Last Active within 30 days
- Has LinkedIn URL (enables profile enrichment)
- Current Status = "Career Transition" (highest urgency, highest value)
- Tags do NOT include "Not Trusted but Connected"

```python
# pete_cohort_selector.py

import pandas as pd

def select_next_cohort(csv_path: str, cohort_size: int = 30) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    # Exclude already-called members
    # (you'd load a called_uids list from your ledger)
    called_uids = []  # load from pete_call_ledger.json
    df = df[~df["UID"].isin(called_uids)]

    # Exclude untrusted
    df = df[~df["Tags"].str.contains("Not Trusted but Connected", na=False)]

    # Prioritize by urgency and engagement
    df = df[df["Networking Mindset"] == "Actively Networking"]
    df = df[df["Active (Signed In Last 30 Days)"] == "Yes"]
    df = df[df["Linkedin URL"].notna()]

    # Sort: Career Transition first, then by activity score
    df["priority"] = (df["Current Status"] == "Career Transition").astype(int)
    df = df.sort_values(["priority", "Activity score"], ascending=[False, False])

    return df.head(cohort_size)[
        ["UID", "First Name", "Last Name", "Email", "Linkedin URL",
         "Current Status", "Networking Mindset", "Activity score"]
    ]
```

---

*PETE Profile System v1.1*
*Apify · Retell AI · Budget Controls · Cohort Release*
