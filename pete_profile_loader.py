# pete_profile_loader.py

import pandas as pd
import json
from pathlib import Path

MEMBER_CSV = "data/theoperators_members.csv"


def load_member_profile(identifier: str) -> dict:
    """
    Loads a member profile from the community CSV by UID.
    Returns a dict with pete_profile structure.
    """
    if not Path(MEMBER_CSV).exists():
        return None

    df = pd.read_csv(MEMBER_CSV)
    row = df[df["UID"] == identifier]

    if row.empty:
        return None

    row = row.iloc[0]

    def safe(val):
        return val if pd.notna(val) else None

    profile = {
        "uid": safe(row.get("UID")),
        "full_name": f"{safe(row.get('First Name', ''))} {safe(row.get('Last Name', ''))}".strip(),
        "email": safe(row.get("Email")),
        "headline": safe(row.get("Headline")),
        "current_status": safe(row.get("Current Status")),
        "networking_mindset": safe(row.get("Networking Mindset")),
        "roles_comfortable_with": safe(row.get("Roles you feel comfortable working in")),
        "industries": safe(row.get("Industries You Have Worked In?")),
        "skills": safe(row.get("Skills?")),
        "linkedin_url": safe(row.get("Linkedin URL")),
        "location": safe(row.get("Location")),
        "pe_experience": safe(row.get("Have you ever been, or are you now, a PE-Backed Executive?")),
        "activity_score": safe(row.get("Activity score")),
        "is_member": True,
        "profile_source": "community_csv",
    }

    return {"pete_profile": profile}


def get_all_members() -> list:
    """Returns all members as a list of dicts."""
    if not Path(MEMBER_CSV).exists():
        return []

    df = pd.read_csv(MEMBER_CSV)
    return df.to_dict("records")