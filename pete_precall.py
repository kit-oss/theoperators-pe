# pete_precall.py (v1.1)

from pathlib import Path
from pete_profile_loader import load_member_profile
from pete_linkedin_loader import summarize_linkedin_for_pete
from pete_prompt_builder import build_pete_prompt_injection
from pete_budget import can_take_call

BASE_PROMPT_PATH = Path("PETE_system_prompt.md")


def _load_base_prompt() -> str:
    if BASE_PROMPT_PATH.exists():
        return BASE_PROMPT_PATH.read_text()
    return """Your name is PETE — Private Equity's Trusted Envoy. You are an independent, neutral connector in the private equity ecosystem."""


BASE_SYSTEM_PROMPT = _load_base_prompt()


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
    # Budget gate: check before doing anything else
    approved, reason = can_take_call()
    if not approved:
        return {
            "approved": False,
            "reason": reason,
            "system_prompt": None,
        }

    # Profile lookup
    profile = None
    if identifier:
        profile = load_member_profile(identifier)
    if not profile and linkedin_url and person_name:
        profile = summarize_linkedin_for_pete(linkedin_url, person_name)

    # Build prompt
    if profile:
        injection = build_pete_prompt_injection(profile)
        full_prompt = injection + "\n\n---\n\n" + BASE_SYSTEM_PROMPT
    else:
        full_prompt = BASE_SYSTEM_PROMPT

    return {
        "approved": True,
        "reason": "",
        "system_prompt": full_prompt,
    }