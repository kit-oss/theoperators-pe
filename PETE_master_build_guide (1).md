# PETE — Master Build Guide
## Sequenced Implementation for Claude Code

---

## How to use this guide

This is a step-by-step build sequence for Claude Code (PETE's development environment).
Each phase builds on the last. Do not skip ahead — later phases depend on earlier ones.

Every phase ends with a verification test. Do not proceed to the next phase until
the test passes.

All source documents are referenced by filename. Keep them open alongside this guide.

---

## Prerequisites

Before starting, confirm the following accounts and keys are in hand:

| Service | Purpose | Where to get it |
|---|---|---|
| Anthropic API key | Claude calls inside PETE | console.anthropic.com |
| Retell AI account + API key | Voice calls | retellai.com |
| ElevenLabs account + voice ID | PETE's voice | elevenlabs.io |
| Apify account + API token | LinkedIn profile lookup | apify.com |
| SendGrid account + API key | All outbound email | sendgrid.com |
| Domain / hosting | Web server for opt-in + dashboard | your choice |

Also confirm:
- Python 3.10+ installed
- Flask installed (`pip install flask`)
- SQLite available (ships with Python)
- A `data/` directory created at the project root

---

## Phase 1 — Foundation
### Files: `pete_db.py`, `pete_budget.py`
### Source: `PETE_matchmaking_db.md` Part 1, `PETE_profile_system_v1.1.md` Part 2

**What this phase does:**
Sets up the SQLite database and the call cost ledger.
Nothing else in the system works without these two files.

**Build steps:**

1. Create `pete_db.py` from `PETE_matchmaking_db.md` Part 1
2. Run `python pete_db.py` — confirm output: "PETE matchmaking database initialised."
3. Create `pete_budget.py` from `PETE_profile_system_v1.1.md` Part 2
4. Confirm `data/` directory now contains `pete_matchmaking.db`

**Verification test:**
```python
from pete_db import get_conn
from pete_budget import can_take_call, monthly_summary

conn = get_conn()
print("DB connected:", conn)

ok, reason = can_take_call()
print("Budget gate:", ok, reason)

print("Monthly summary:", monthly_summary())
```
Expected: DB connects, budget gate returns True, summary shows $0 spent.

---

## Phase 2 — Member Profile System
### Files: `pete_profile_loader.py`, `pete_linkedin_loader.py`, `pete_member_index.py`
### Source: `PETE_profile_system_v1.1.md` Parts 3, B; `PETE_matchmaking_db.md` Part 2

**What this phase does:**
Enables PETE to look up a member from your community CSV,
or fetch and summarize a LinkedIn profile for non-members.
Also builds the lightweight member index used for matching.

**Build steps:**

1. Place your community CSV at `data/community_members.csv`
   (this is the file you uploaded: `community_the_operators_...csv`)
2. Create `pete_profile_loader.py` from `PETE_profile_system_v1.1.md` Path A
3. Create `pete_linkedin_loader.py` from `PETE_profile_system_v1.1.md` Path B
   — replace `APIFY_API_TOKEN` with your real token
   — Actor ID to use: `get-leads~linkedin-scraper`
4. Create `pete_member_index.py` from `PETE_matchmaking_db.md` Part 2
5. Run `python pete_member_index.py` to build the initial index

**Verification test:**
```python
from pete_profile_loader import load_member_profile
from pete_member_index import load_member_index

# Use a real UID from your CSV
profile = load_member_profile("ilz9wMAg")
print("Profile loaded:", profile["pete_profile"]["full_name"])

index = load_member_index()
print("Index sample:", index[:200])
```
Expected: Kit Lisle's profile loads. Index returns a string of member entries.

---

## Phase 3 — Prompt Builder
### Files: `pete_prompt_builder.py`, `pete_precall.py`
### Source: `PETE_profile_system_v1.1.md` Parts C, D; `PETE_system_prompt.md`

**What this phase does:**
Takes a member profile and converts it into the natural language
briefing block that gets prepended to PETE's system prompt before
every call. Also runs the budget gate before doing any work.

**Build steps:**

1. Save `PETE_system_prompt.md` to the project root as `PETE_system_prompt.md`
2. Create `pete_prompt_builder.py` from `PETE_profile_system_v1.1.md` Path C
3. Create `pete_precall.py` from `PETE_profile_system_v1.1.md` Part D

**Verification test:**
```python
from pete_precall import prepare_pete_for_call

result = prepare_pete_for_call(identifier="ilz9wMAg")
print("Approved:", result["approved"])
print("Prompt preview (first 500 chars):")
print(result["system_prompt"][:500])
```
Expected: Approved = True. Prompt starts with "## What PETE already knows about Kit Lisle".

---

## Phase 4 — Retell Voice Integration
### Files: `pete_call_initiator.py`
### Source: `PETE_profile_system_v1.1.md` Part 5

**What this phase does:**
Connects PETE to Retell AI so he can actually make phone calls.
Also wires the call-ended webhook back to the budget ledger.

**Build steps:**

1. Log into retellai.com and create a new agent called "PETE"
   - Set the LLM to Claude (connect your Anthropic API key)
   - Connect ElevenLabs (select or design PETE's voice — see voice note below)
   - Add a dynamic variable called `pete_profile_context`
   - In the agent system prompt field, enter only: `{{pete_profile_context}}`
     (the full prompt is injected per-call at runtime)
   - Set max call duration to 25 minutes
   - Copy the Agent ID — you will need it

2. Create `pete_call_initiator.py` from `PETE_profile_system_v1.1.md` Part 5
   - Replace `RETELL_API_KEY` with your key
   - Replace `PETE_AGENT_ID` with the ID from step 1
   - Replace the `from_number` with your Retell phone number

3. Set up the call-ended webhook in Retell:
   - Go to Retell dashboard → Webhooks
   - Set the endpoint to: `https://yourdomain.com/api/pete/call-ended`

**Voice note:**
Before testing calls, go to ElevenLabs and either:
- Design a voice: mid-register, unhurried, warm, slight authority.
  Suggested settings: stability 0.65, similarity 0.75, style 0.3
- Or select from their library: "Adam" or "Daniel" are reasonable defaults
  for a professional male voice. Avoid anything that sounds robotic or overly
  bright.

**Verification test:**
This phase requires a real phone number to test properly.
Use your own mobile number for the first test call.

```python
from pete_precall import prepare_pete_for_call
from pete_call_initiator import initiate_pete_call

result = prepare_pete_for_call(identifier="ilz9wMAg")
if result["approved"]:
    call = initiate_pete_call(
        phone_number="+1YOURNUMBER",
        system_prompt=result["system_prompt"],
        member_uid="ilz9wMAg",
    )
    print("Call initiated:", call)
```
Expected: Retell returns a call object with a call_id. Your phone rings.
PETE introduces himself and begins the conversation.

---

## Phase 5 — Opt-In Flow
### Files: `pete_optin_api.py` (Flask app), `pete_optin.html`
### Source: `PETE_optin_system.md` Parts 1, 2; `pete_optin.html`

**What this phase does:**
Creates the web-facing pieces: the landing page members visit,
and the Flask API that handles their opt-in, runs the budget gate,
builds PETE's prompt, and fires the call.

**Build steps:**

1. Create `pete_optin_api.py` from `PETE_optin_system.md` Part 1
   - Fill in your SendGrid key and email addresses
   - This is your main Flask application file

2. Copy `pete_optin.html` to your web server's public directory
   - The form POSTs to `/api/pete/optin`
   - The `?uid=` URL parameter auto-loads the member profile

3. Generate your first cohort invite links:
   Create `generate_invite_links.py` from `PETE_optin_system.md` Part 5
   Run it to produce `data/cohort_invite_links.csv`

4. Start the Flask server: `flask --app pete_optin_api run --port 5000`

**Verification test:**
Open `pete_optin.html?uid=ilz9wMAg` in a browser.
Fill in your own phone number and a test intent sentence.
Submit the form.
Expected: Success screen appears. Your phone rings. PETE calls.

---

## Phase 6 — Post-Call Processing
### Files: `pete_transcript_analyzer.py`, `pete_owner_notify.py`, `pete_postcall.py`
### Source: `PETE_postcall_layer.md` Parts 1, 4, 5, 6

**What this phase does:**
After every call ends, fetches the transcript from Retell,
sends it to Claude for analysis, updates the member record,
and emails you a plain-English summary of what PETE learned.

**Build steps:**

1. Create `pete_transcript_analyzer.py` from `PETE_postcall_layer.md` Part 1
2. Create `pete_owner_notify.py` from `PETE_postcall_layer.md` Part 4
   - Fill in your SendGrid key and your email address
3. Create `pete_postcall.py` from `PETE_postcall_layer.md` Part 5
4. Update the call-ended webhook route in `pete_optin_api.py`
   using the replacement code in `PETE_postcall_layer.md` Part 6

**Verification test:**
After a test call completes, check your inbox.
Expected: An email from PETE with subject "PETE call: [Name] — [Date]"
containing the call summary, any introduction opportunities, and
any community signals extracted from the conversation.

---

## Phase 7 — Matchmaking Database
### Files: `pete_match_extractor.py`, `pete_matching_engine.py`
### Source: `PETE_matchmaking_db.md` Parts 2, 3, 7

**What this phase does:**
After every call, extracts structured needs and offers from the
transcript and saves them to the database. Then runs the matching
engine in both directions — new needs vs. existing offers,
new offers vs. existing needs.

**Build steps:**

1. Create `pete_match_extractor.py` from `PETE_matchmaking_db.md` Part 2
2. Create `pete_matching_engine.py` from `PETE_matchmaking_db.md` Part 3
3. Update `pete_postcall.py` with the additions in `PETE_matchmaking_db.md` Part 7
   (adds `upsert_member`, `extract_needs_and_offers`, `run_matching_for_member`)

**Verification test:**
After a test call, query the database:
```python
from pete_db import get_conn
conn = get_conn()
c = conn.cursor()
c.execute("SELECT * FROM needs")
print("Needs:", [dict(r) for r in c.fetchall()])
c.execute("SELECT * FROM offers")
print("Offers:", [dict(r) for r in c.fetchall()])
```
Expected: At least one need and one offer extracted from the call transcript.

---

## Phase 8 — Confirmation Flow
### Files: `pete_confirmation_flow.py`
### Source: `PETE_matchmaking_db.md` Parts 4, 5

**What this phase does:**
When the matching engine finds a strong match, it emails both
parties separately asking if they're open to an introduction.
When both confirm via their unique link, the intro email fires.

**Build steps:**

1. Create `pete_confirmation_flow.py` from `PETE_matchmaking_db.md` Part 4
   - Fill in your SendGrid key
   - Replace `BASE_URL` with your real domain
2. Add the `/pete/confirm` and `/pete/decline` routes to `pete_optin_api.py`
   from `PETE_matchmaking_db.md` Part 5

**Verification test:**
Manually insert a test match into the database and trigger confirmation:
```python
from pete_confirmation_flow import send_confirmation_emails
# Insert a test match row first, then:
send_confirmation_emails(match_id=1, seeker_token="test123", provider_token="test456")
```
Expected: Two confirmation emails received, each with a unique confirm/decline link.
Clicking both confirm links triggers the intro email.

---

## Phase 9 — Weekly Digest
### Files: `pete_digest.py`
### Source: `PETE_matchmaking_db.md` Part 6

**What this phase does:**
Every Monday morning, emails you a list of open needs that
have sat unmatched for 7+ days, the match pipeline status,
and the top community signals from the past week.

**Build steps:**

1. Create `pete_digest.py` from `PETE_matchmaking_db.md` Part 6
2. Schedule it with cron:
   ```
   0 8 * * 1 cd /path/to/pete && python pete_digest.py
   ```
   Or use a hosted scheduler (Railway, Render, etc.) if you're
   not self-hosting.

**Verification test:**
Run manually and confirm the email arrives:
```
python pete_digest.py
```

---

## Phase 10 — Dashboard
### Files: `pete_dashboard.html`, `pete_dashboard_api.py`
### Source: dashboard files

**What this phase does:**
Adds the read-only operator dashboard — a single page showing
call spend, match pipeline, community signals, recent calls,
and unmatched open needs. Auto-refreshes every 60 seconds.

**Build steps:**

1. Add the routes from `pete_dashboard_api.py` to `pete_optin_api.py`
2. Deploy `pete_dashboard.html` to a password-protected URL
   (this dashboard is for you only — protect it with HTTP basic auth
   or put it behind a login)
3. Confirm the `/api/pete/dashboard` endpoint returns valid JSON

**Verification test:**
Open the dashboard in a browser.
Expected: All four panels load with real data from the database.
Metrics, pipeline, signals, and unmatched needs all populate correctly.

---

## Phase 11 — Cohort Release
### Source: `PETE_profile_system_v1.1.md` Part 6, `PETE_optin_system.md` Part 4

**What this phase does:**
Selects your first cohort of members, generates personalised
invite links, and sends the invitation email and community post.

**Build steps:**

1. Run `pete_cohort_selector.py` to generate `data/cohort_invite_links.csv`
   — default cohort size: 20 for the first wave
2. Import the CSV into your email platform (ConvertKit, Mailchimp, etc.)
   using the invite link as a merge tag
3. Send the invitation email from `PETE_optin_system.md` Part 3
4. Post the community announcement from `PETE_optin_system.md` Part 4
5. Monitor the dashboard as opt-ins arrive

**First wave selection criteria (already in `pete_cohort_selector.py`):**
- Networking mindset: Actively Networking
- Active in last 30 days
- LinkedIn URL present
- Current status: Career Transition (highest urgency, highest value)
- Tags do NOT include "Not Trusted but Connected"

---

## Complete file inventory

When all phases are done, your project should contain:

```
pete/
├── data/
│   ├── community_members.csv
│   ├── pete_matchmaking.db
│   ├── pete_call_ledger.json
│   ├── pete_call_records.json
│   ├── pete_optin_log.json
│   ├── pete_waitlist.json
│   ├── pete_member_index.json
│   └── cohort_invite_links.csv
│
├── PETE_system_prompt.md
│
├── pete_db.py                    Phase 1
├── pete_budget.py                Phase 1
├── pete_profile_loader.py        Phase 2
├── pete_linkedin_loader.py       Phase 2
├── pete_member_index.py          Phase 2
├── pete_prompt_builder.py        Phase 3
├── pete_precall.py               Phase 3
├── pete_call_initiator.py        Phase 4
├── pete_optin_api.py             Phase 5  (main Flask app)
├── pete_transcript_analyzer.py   Phase 6
├── pete_owner_notify.py          Phase 6
├── pete_postcall.py              Phase 6
├── pete_match_extractor.py       Phase 7
├── pete_matching_engine.py       Phase 7
├── pete_confirmation_flow.py     Phase 8
├── pete_digest.py                Phase 9
├── pete_dashboard_api.py         Phase 10 (routes added to pete_optin_api.py)
│
└── public/
    ├── pete_optin.html           Phase 5
    └── pete_dashboard.html       Phase 10
```

---

## Environment variables

Never hardcode secrets in source files. Use a `.env` file and `python-dotenv`:

```
ANTHROPIC_API_KEY=sk-ant-...
RETELL_API_KEY=...
RETELL_AGENT_ID=...
ELEVENLABS_VOICE_ID=...
APIFY_API_TOKEN=...
SENDGRID_API_KEY=SG....
FROM_EMAIL=pete@theoperators.pe
OWNER_EMAIL=kit@theoperators.pe
BASE_URL=https://yoursite.com
MONTHLY_BUDGET_USD=200
INTRO_CONFIDENCE_THRESHOLD=0.85
```

---

## Known limitations to address before scaling

1. `get_recent_calls()` in the dashboard uses member_uid as the display name.
   Wire it to `load_member_profile()` to show real names.

2. `update_member_profile()` in `pete_postcall.py` logs updates but does not
   yet write them back to the CSV. Implement a proper database write when ready.

3. The confirmation flow has no expiry on tokens. Add a `confirmation_expires_at`
   field and a 7-day expiry check before the system goes to full scale.

4. The weekly digest cron assumes local server hosting. If using a managed
   platform (Railway, Render, Fly.io), use their built-in cron or a service
   like Inngest instead.

5. The dashboard has no authentication. Protect it before sharing the URL.

---

*PETE Master Build Guide v1.0*
*11 phases · ~20 files · Full system from zero to live*
