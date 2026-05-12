# pete_call_initiator.py
# Uses Retell AI ($0.07/min flat) with Custom LLM endpoint

import requests
import os

RETELL_API_KEY = os.getenv("RETELL_API_KEY")
PETE_AGENT_ID = os.getenv("RETELL_AGENT_ID")
BASE_URL = os.getenv("BASE_URL")
FROM_NUMBER = os.getenv("RETELL_FROM_NUMBER", "+1XXXXXXXXXX")
MAX_CALL_DURATION_SECONDS = 25 * 60


def initiate_pete_call(
    phone_number: str,
    system_prompt: str,
    member_uid: str,
) -> dict:
    """
    Initiates a call via Retell, pointing the LLM at PETE's
    Custom LLM endpoint on Railway.
    """
    url = "https://api.retellai.com/v2/create-phone-call"
    headers = {
        "Authorization": f"Bearer {RETELL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "from_number": FROM_NUMBER,
        "to_number": phone_number,
        "agent_id": PETE_AGENT_ID,
        "override_agent_llm_websocket_url": f"{BASE_URL}/api/pete/llm",
        "max_call_duration_ms": MAX_CALL_DURATION_SECONDS * 1000,
        "metadata": {
            "member_uid": member_uid,
        },
    }

    response = requests.post(url, headers=headers, json=payload)
    call_data = response.json()
    call_id = call_data.get("call_id")

    if not call_id:
        return {"ok": False, "reason": "Retell did not return a call_id", "raw": call_data}

    # Store the system prompt server-side keyed to call_id
    store_response = requests.post(
        f"{BASE_URL}/api/pete/llm/store-prompt",
        json={"call_id": call_id, "system_prompt": system_prompt},
    )

    return {"ok": True, "call_id": call_id, "retell": call_data}


def handle_call_ended_webhook(webhook_payload: dict):
    """
    Records cost and cleans up the in-memory prompt store.
    """
    from pete_budget import record_call

    call_id = webhook_payload.get("call_id", "")
    duration_ms = webhook_payload.get("duration_ms", 0)
    duration_min = round(duration_ms / 60000, 2)
    member_uid = webhook_payload.get("metadata", {}).get("member_uid", "unknown")

    cost = record_call(member_uid, duration_min)

    # Clean up prompt from memory
    if BASE_URL:
        requests.post(
            f"{BASE_URL}/api/pete/llm/clear-prompt",
            json={"call_id": call_id},
        )

    print(f"Call ended: {duration_min} min, ${cost:.4f} — UID: {member_uid}")