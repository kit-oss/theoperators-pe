# pete_prompt_builder.py

import json


def build_pete_prompt_injection(profile: dict) -> str:
    """
    Takes a pete_profile dict and converts it into the natural language
    briefing block that gets prepended to PETE's system prompt before
    every call.
    """
    p = profile.get("pete_profile", profile)

    lines = []
    lines.append(f"## What PETE already knows about {p.get('full_name', 'this person')}")
    lines.append("")

    if p.get("headline"):
        lines.append(f"**Headline:** {p['headline']}")
        lines.append("")

    if p.get("current_status"):
        lines.append(f"**Current Status:** {p['current_status']}")
        lines.append("")

    if p.get("networking_mindset"):
        lines.append(f"**Networking Mindset:** {p['networking_mindset']}")
        lines.append("")

    if p.get("roles_comfortable_with"):
        lines.append(f"**Roles Comfortable With:** {p['roles_comfortable_with']}")
        lines.append("")

    if p.get("industries"):
        lines.append(f"**Industries:** {p['industries']}")
        lines.append("")

    if p.get("skills"):
        lines.append(f"**Skills:** {p['skills']}")
        lines.append("")

    if p.get("location"):
        lines.append(f"**Location:** {p['location']}")
        lines.append("")

    if p.get("pe_experience"):
        lines.append(f"**PE Experience:** {p['pe_experience']}")
        lines.append("")

    lines.append("")
    lines.append("Use this context to guide the conversation naturally.")
    lines.append("")

    return "\n".join(lines)