"""
Human-readable descriptions of Shashin position types.
Used in both the LLM prompt and the smoke test report.
"""

DESCRIPTIONS: dict[str, dict] = {
    "Tal": {
        "label":   "Tactical / Attacking",
        "short":   "sharp, tactical, attacking",
        "report":  "⚔️ Tactical / Attacking — sharp position with piece activity and threats. "
                   "Look for combinations, sacrifices, and direct attacks on the king.",
        "prompt":  "sharp tactical position — attacks, sacrifices, and king safety are key",
    },
    "Capablanca": {
        "label":   "Strategic / Balanced",
        "short":   "balanced, strategic, positional",
        "report":  "⚖️ Strategic / Balanced — quiet positional play. "
                   "Focus on piece improvement, weak squares, pawn structure, and long-term plans.",
        "prompt":  "balanced strategic position — focus on piece coordination, weak squares, and long-term plans",
    },
    "Petrosian": {
        "label":   "Defensive / Solid",
        "short":   "defensive, solid, prophylactic",
        "report":  "🛡️ Defensive / Solid — one side must hold a difficult position. "
                   "Prophylaxis, exchanges, blockades, and neutralizing opponent's threats are the priority.",
        "prompt":  "defensive position — prophylaxis, safe exchanges, and neutralizing threats are the priority",
    },
}


def prompt_description(shashin_type: str) -> str:
    """Short description for use inside the LLM prompt."""
    return DESCRIPTIONS.get(shashin_type, {}).get("prompt", shashin_type)


def report_description(shashin_type: str) -> str:
    """Full description for use in the human-readable report."""
    return DESCRIPTIONS.get(shashin_type, {}).get("report", shashin_type)
