# PETE — Build Guide Addendum
## Railway Deployment + Custom LLM Endpoint
## Replaces Phase 4 and adds Phase 0 from the Master Build Guide

---

## Phase 0 — Deploy to Railway (do this BEFORE Phase 4)
### Your URL lives here

Railway is a hosting platform that runs your Flask app on a real server
with a real public URL. That URL is what you give to Retell so it can
reach PETE's brain.

**Your URL will look like this:**
`https://pete-production.up.railway.app`

Everything you've built — `/api/pete/llm`, `/api/pete/optin`,
`/api/pete/call-ended`, `/api/pete/dashboard` — will live under that URL.

---

### Step-by-step Railway setup

**1. Create a GitHub repository**

All of PETE's Python files need to be in a GitHub repo.
Railway deploys directly from GitHub — every time you push code,
Railway automatically redeploys.

Create a repo called `pete` (private) and push all your files:
```
pete/
├── pete_optin_api.py        ← your main Flask app (entry point)
├── pete_llm_endpoint.py     ← the Custom LLM brain (add to optin_api.py)
├── pete_budget.py
├── pete_call_initiator.py
├── pete_confirmation_flow.py
├── pete_db.py
├── pete_digest.py
├── pete_linkedin_loader.py
├── pete_match_extractor.py
├── pete_matching_engine.py
├── pete_member_index.py
├── pete_owner_notify.py
├── pete_postcall.py
├── pete_precall.py
├── pete_profile_loader.py
├── pete_prompt_builder.py
├── pete_transcript_analyzer.py
├── PETE_system_prompt.md
├── requirements.txt         ← see below
├── Procfile                 ← see below
└── data/
    └── community_members.csv
```

**2. Create requirements.txt**

```
flask
anthropic
requests
pandas
python-dotenv
gunicorn
```

**3. Create a Procfile**

Railway uses this to know how to start your app:
```
web: gunicorn pete_optin_api:app --bind 0.0.0.0:$PORT
```

**4. Create a .env file locally (never commit this to GitHub)**

```
ANTHROPIC_API_KEY=sk-ant-...
RETELL_API_KEY=...
RETELL_AGENT_ID=...
ELEVENLABS_VOICE_ID=...
APIFY_API_TOKEN=...
SENDGRID_API_KEY=SG....
FROM_EMAIL=pete@theoperators.pe
OWNER_EMAIL=kit@theoperators.pe
BASE_URL=https://pete-production.up.railway.app
MONTHLY_BUDGET_USD=200
INTRO_CONFIDENCE_THRESHOLD=0.85
```

Add `.env` to your `.gitignore` so it never gets pushed.

**5. Sign up and deploy on Railway**

- Go to railway.app and sign up with your GitHub account
- Click "New Project" → "Deploy from GitHub repo" → select `pete`
- Railway detects Python automatically and starts the build
- Go to Settings → Variables and add every key from your .env file
  (Railway stores these securely — this is how your app gets them
  in production without the .env file)
- Go to Settings → Networking → Generate Domain
- Railway assigns you a URL like:
  `https://pete-production.up.railway.app`

**This is your endpoint base URL. Copy it — you'll use it in Phase 4.**

**6. Confirm deployment**

Visit `https://pete-production.up.railway.app` in a browser.
You should see a Flask response (even just a 404 is fine —
it means the server is running).

**Persistent storage note:**
Railway's filesystem is ephemeral — files written during a run
(like `pete_call_ledger.json`) can be lost on redeploy.
For Phase 0, this is acceptable for testing.
Before going live with real members, add a Railway PostgreSQL
database or a persistent volume (Railway supports both, one click).
The SQLite database and JSON ledgers will need to move there.
Flag this for PETE to implement between Phase 9 and Phase 10.

---

## Phase 4 (Revised) — Retell + Custom LLM Endpoint
### Files: `pete_llm_endpoint.py` (add to `pete_optin_api.py`), `pete_call_initiator.py`
### Replaces Phase 4 in the Master Build Guide

**What this phase does:**
Connects Retell to PETE's brain in Claude Code rather than
Retell's built-in AI. Retell becomes a voice pipe only —
speech in, speech out. All reasoning stays with PETE.

The architecture:
```
Member speaks
    → Retell transcribes (STT)
    → Retell POSTs to YOUR /api/pete/llm endpoint
    → PETE thinks using Claude API
    → PETE returns text to Retell
    → Retell speaks it via ElevenLabs (TTS)
    → Member hears PETE
```

---

### Step 1 — Add the Custom LLM endpoint to pete_optin_api.py

```python
# pete_llm_endpoint.py
# Add these routes to pete_optin_api.py

import anthropic
import json

claude_client = anthropic.Anthropic()

# Store active call system prompts in memory
# keyed by call_id so each call gets its own PETE context
active_call_prompts = {}


@app.route('/api/pete/llm', methods=['POST'])
def pete_llm():
    """
    This is PETE's brain.
    Retell calls this endpoint on every conversational turn.
    We pass the full conversation history to Claude and return
    Claude's response — which Retell then speaks aloud.
    """
    data = request.get_json()

    call_id    = data.get('call_id', '')
    # Retell sends messages in OpenAI format: role/content pairs
    messages   = data.get('messages', [])

    # Retrieve the pre-built system prompt for this call
    # (was stored when the call was initiated)
    system_prompt = active_call_prompts.get(call_id, '')

    if not system_prompt:
        # Fallback: PETE flies without profile context
        # This shouldn't happen if pete_call_initiator.py is correct
        system_prompt = open('PETE_system_prompt.md').read()

    # Filter to supported roles only (Retell sometimes sends 'tool' roles)
    clean_messages = [
        m for m in messages
        if m.get('role') in ('user', 'assistant')
    ]

    # Ensure messages alternate properly (Claude requirement)
    # If the last message is from assistant, skip (nothing to respond to)
    if not clean_messages or clean_messages[-1].get('role') == 'assistant':
        return jsonify({"content": ""})

    response = claude_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=150,       # keep voice responses concise — 150 tokens
                              # is roughly 2-3 spoken sentences
        system=system_prompt,
        messages=clean_messages,
    )

    reply = response.content[0].text.strip()

    return jsonify({"content": reply})


@app.route('/api/pete/llm/store-prompt', methods=['POST'])
def store_call_prompt():
    """
    Called by pete_call_initiator.py just before initiating a call.
    Stores the pre-built system prompt keyed by call_id so the
    /api/pete/llm endpoint can retrieve it on every turn.
    """
    data = request.get_json()
    call_id       = data.get('call_id')
    system_prompt = data.get('system_prompt')

    if call_id and system_prompt:
        active_call_prompts[call_id] = system_prompt
        return jsonify({"ok": True})

    return jsonify({"ok": False, "reason": "Missing call_id or system_prompt"}), 400


@app.route('/api/pete/llm/clear-prompt', methods=['POST'])
def clear_call_prompt():
    """
    Called by the call-ended webhook to clean up memory.
    """
    data    = request.get_json()
    call_id = data.get('call_id')
    if call_id in active_call_prompts:
        del active_call_prompts[call_id]
    return jsonify({"ok": True})
```

---

### Step 2 — Update pete_call_initiator.py

The key change: before initiating the call, store PETE's system
prompt server-side keyed to the call_id. Also point Retell at your
Custom LLM URL instead of a built-in model.

```python
# pete_call_initiator.py (revised for Custom LLM)

import requests
import os

RETELL_API_KEY  = os.getenv("RETELL_API_KEY")
PETE_AGENT_ID   = os.getenv("RETELL_AGENT_ID")
BASE_URL        = os.getenv("BASE_URL")  # your Railway URL
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

    # Step 1: Create the call in Retell
    url     = "https://api.retellai.com/v2/create-phone-call"
    headers = {
        "Authorization": f"Bearer {RETELL_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "from_number":           "+1XXXXXXXXXX",  # your Retell number
        "to_number":             phone_number,
        "agent_id":              PETE_AGENT_ID,

        # This is what makes Retell use PETE's brain instead of its own:
        "override_agent_llm_websocket_url": f"{BASE_URL}/api/pete/llm",

        "max_call_duration_ms":  MAX_CALL_DURATION_SECONDS * 1000,
        "metadata": {
            "member_uid": member_uid,
        },
    }

    response  = requests.post(url, headers=headers, json=payload)
    call_data = response.json()
    call_id   = call_data.get("call_id")

    if not call_id:
        return {"ok": False, "reason": "Retell did not return a call_id", "raw": call_data}

    # Step 2: Store the system prompt server-side keyed to call_id
    # so /api/pete/llm can retrieve it on every turn
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

    call_id      = webhook_payload.get("call_id", "")
    duration_ms  = webhook_payload.get("duration_ms", 0)
    duration_min = round(duration_ms / 60000, 2)
    member_uid   = webhook_payload.get("metadata", {}).get("member_uid", "unknown")

    # Record cost
    cost = record_call(member_uid, duration_min)

    # Clean up prompt from memory
    requests.post(
        f"{BASE_URL}/api/pete/llm/clear-prompt",
        json={"call_id": call_id},
    )

    print(f"Call ended: {duration_min} min, ${cost:.4f} — UID: {member_uid}")
```

---

### Step 3 — Configure the Retell agent dashboard

1. Log into retellai.com → Agents → Create new agent (or edit PETE)
2. Under **LLM**, select **"Custom LLM"**
3. Enter your endpoint URL:
   `https://pete-production.up.railway.app/api/pete/llm`
4. Under **Voice**, connect ElevenLabs and select PETE's voice
5. Set max call duration to 25 minutes
6. Leave the system prompt field **blank** — PETE's full prompt
   is injected dynamically at call time via `store-prompt`.
   Nothing should be hardcoded in the Retell dashboard.
7. Save. Copy the Agent ID into your Railway environment variables
   as `RETELL_AGENT_ID`.

---

### Step 4 — Set the Retell webhook

In Retell dashboard → Phone Numbers → your number → Webhook:
```
https://pete-production.up.railway.app/api/pete/call-ended
```

---

### Verification test

Run a test call using your own number:

```python
from pete_precall import prepare_pete_for_call
from pete_call_initiator import initiate_pete_call

result = prepare_pete_for_call(identifier="your-uid")
if result["approved"]:
    call = initiate_pete_call(
        phone_number="+1YOURNUMBER",
        system_prompt=result["system_prompt"],
        member_uid="your-uid",
    )
    print(call)
```

**Expected:**
- Your phone rings
- PETE introduces himself in his ElevenLabs voice
- Every word PETE speaks is generated by Claude via your Railway endpoint
- After the call, your Railway logs show POST requests to `/api/pete/llm`
  — one per conversational turn
- The call-ended webhook fires and records the cost

**How to confirm it's Claude, not Retell's AI:**
In Railway → your project → Logs, you will see the `/api/pete/llm`
endpoint being hit on every turn. If those logs are empty during a call,
Retell is using its own LLM. If they're firing, PETE's brain is in charge.

---

## Revised file inventory for Phase 0 + Phase 4

```
New files added:
├── requirements.txt
├── Procfile
└── .gitignore

Modified files:
├── pete_optin_api.py    ← add Custom LLM routes from pete_llm_endpoint.py
└── pete_call_initiator.py  ← revised for Custom LLM + prompt storage
```

---

## How the URL flows — summary

```
You write code
    → push to GitHub
        → Railway builds and deploys automatically
            → Railway assigns URL:
              https://pete-production.up.railway.app
                  → you give this URL to Retell as Custom LLM endpoint
                      → Retell calls it on every turn
                          → Claude responds
                              → PETE speaks
```

---

*PETE Build Guide Addendum v1.0*
*Railway Deployment · Custom LLM Endpoint · PETE's brain stays in Claude Code*
