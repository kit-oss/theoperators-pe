# pete_member_index.py

import pandas as pd
import json
from pathlib import Path

MEMBER_CSV = "data/theoperators_members.csv"
INDEX_FILE = "data/pete_member_index.json"


def build_member_index(csv_path: str = MEMBER_CSV) -> list:
    """
    Builds a lightweight index of members for match suggestions.
    Filters to actively networking members only.
    """
    df = pd.read_csv(csv_path)

    df = df[df["Networking Mindset"].isin([
        "Actively Networking",
        "Passively Networking",
        "Open to Outreach by Peers only",
    ])]

    df = df[~df["Tags"].str.contains("Not Trusted but Connected", na=False)]

    def safe(val):
        return val if pd.notna(val) else None

    index = []
    for _, row in df.iterrows():
        index.append({
            "uid": safe(row.get("UID")),
            "name": f"{safe(row.get('First Name', ''))} {safe(row.get('Last Name', ''))}".strip(),
            "headline": safe(row.get("Headline")),
            "current_status": safe(row.get("Current Status")),
            "roles": safe(row.get("Roles you feel comfortable working in")),
            "industries": safe(row.get("Industries You Have Worked In?")),
            "skills": safe(row.get("Skills?")),
            "networking_mindset": safe(row.get("Networking Mindset")),
            "location": safe(row.get("Location")),
            "pe_backed": safe(row.get("Have you ever been, or are you now, a PE-Backed Executive?")),
        })

    Path(INDEX_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_FILE, "w") as f:
        json.dump(index, f, indent=2)

    return index


def load_member_index() -> str:
    """Returns the index as a compact string for prompt injection."""
    if not Path(INDEX_FILE).exists():
        build_member_index()
    with open(INDEX_FILE) as f:
        index = json.load(f)

    lines = []
    for m in index:
        lines.append(
            f"[{m['uid']}] {m['name']} | {m['headline']} | "
            f"{m['current_status']} | {m['networking_mindset']} | "
            f"{m.get('location', '')}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    build_member_index()
    print("Member index built.")