"""
Full 14-zone Shashin position classification for Alexander engine.

Zones map to win probability ranges (0-100%) from Alexander's shashin_types.h.
Each zone has descriptions calibrated for use in LLM prompts vs human reports.
"""

# ── Zone definitions ───────────────────────────────────────────────────────────

ZONES: dict[str, dict] = {
    "HIGH_PETROSIAN": {
        "label":    "High Petrosian",
        "short":    "desperate defense, fortress, survival",
        "win_range": "0–5%",
        "report":  "🛡️🛡️ Desperate Defense (win prob 0–5%) — "
                   "Position is near hopeless. The only plan is to build a fortress, "
                   "eliminate attacking pieces, and create stalemate chances.",
        "prompt":  "near-lost position — build a fortress, trade attacking pieces, seek stalemate",
        "retriever_keywords": "fortress stalemate desperate defense draw technique survive",
    },
    "MIDDLE_HIGH_PETROSIAN": {
        "label":    "Middle-High Petrosian",
        "short":    "passive defense, damage limitation",
        "win_range": "5–10%",
        "report":  "🛡️🛡️ Passive Defense (win prob 5–10%) — "
                   "Very difficult position requiring accurate passive defense. "
                   "Avoid weaknesses, minimize material losses, hold key squares.",
        "prompt":  "very difficult defense — avoid weaknesses, hold key squares, minimize damage",
        "retriever_keywords": "passive defense blockade neutralize prophylaxis solid",
    },
    "MIDDLE_PETROSIAN": {
        "label":    "Middle Petrosian",
        "short":    "solid defense, fighting for draw",
        "win_range": "10–15%",
        "report":  "🛡️ Solid Defense (win prob 10–15%) — "
                   "Inferior position requiring solid defensive play. "
                   "Prophylaxis, piece exchanges, and blockade are key.",
        "prompt":  "solid defense — prophylaxis, exchange pieces, blockade passed pawns",
        "retriever_keywords": "prophylaxis exchange blockade defensive solid draw",
    },
    "MIDDLE_LOW_PETROSIAN": {
        "label":    "Middle-Low Petrosian",
        "short":    "slight disadvantage, active defense",
        "win_range": "15–20%",
        "report":  "🛡️ Active Defense (win prob 15–20%) — "
                   "Slightly worse position that requires active defensive play "
                   "and counterplay to equalize.",
        "prompt":  "slightly worse — seek counterplay, activate pieces, fight for equality",
        "retriever_keywords": "counterplay active defense equality fighting defensive",
    },
    "LOW_PETROSIAN": {
        "label":    "Low Petrosian",
        "short":    "small disadvantage, fighting for equality",
        "win_range": "20–24%",
        "report":  "⚖️🛡️ Small Disadvantage (win prob 20–24%) — "
                   "Slightly inferior position. Focus on active piece play "
                   "and strategic exchanges to reach equality.",
        "prompt":  "small disadvantage — active piece play, strategic exchanges, fight for equality",
        "retriever_keywords": "equality fighting defensive counterplay exchanges",
    },
    "CAPABLANCA_PETROSIAN": {
        "label":    "Capablanca-Petrosian",
        "short":    "slightly worse but holdable, strategic fight",
        "win_range": "24–49%",
        "report":  "⚖️ Near-Equal but Slightly Worse (win prob 24–49%) — "
                   "Position is holdable with accurate play. The key is to "
                   "neutralize opponent's initiative and seek piece activity.",
        "prompt":  "near-equal but slightly worse — neutralize initiative, activate pieces, solid play",
        "retriever_keywords": "strategic plan neutralize initiative solid positional",
    },
    "CAPABLANCA": {
        "label":    "Capablanca",
        "short":    "true equality, strategic balance",
        "win_range": "~50%",
        "report":  "⚖️ True Equality (win prob ~50%) — "
                   "Perfectly balanced position. Strategic subtlety decides. "
                   "Focus on piece coordination, weak squares, and long-term plans.",
        "prompt":  "equal position — piece coordination, weak squares, long-term strategic plans",
        "retriever_keywords": "strategic positional balanced plan weak square outpost coordination",
    },
    "CAPABLANCA_TAL": {
        "label":    "Capablanca-Tal",
        "short":    "slight advantage, strategic pressure",
        "win_range": "50–75%",
        "report":  "⚖️⚔️ Slight Advantage (win prob 50–75%) — "
                   "Small but real edge. Convert through strategic pressure, "
                   "exploit weak squares, and improve piece activity.",
        "prompt":  "slight advantage — strategic pressure, exploit weak squares, improve piece activity",
        "retriever_keywords": "advantage strategic plan pressure weak square initiative positional",
    },
    "LOW_TAL": {
        "label":    "Low Tal",
        "short":    "clear advantage, convert to win",
        "win_range": "75–79%",
        "report":  "⚔️ Clear Advantage (win prob 75–79%) — "
                   "Significant advantage. Look for concrete ways to convert: "
                   "exploit weaknesses, create passed pawns, or launch a decisive attack.",
        "prompt":  "clear advantage — exploit weaknesses, create passed pawns, convert to win",
        "retriever_keywords": "advantage convert winning technique passed pawn exploit",
    },
    "MIDDLE_LOW_TAL": {
        "label":    "Middle-Low Tal",
        "short":    "solid advantage, winning technique",
        "win_range": "79–84%",
        "report":  "⚔️ Solid Winning Advantage (win prob 79–84%) — "
                   "Dominant position. The focus is on technique: "
                   "simplify to a winning endgame or press the attack.",
        "prompt":  "dominant position — technique, simplify to winning endgame or press the attack",
        "retriever_keywords": "winning technique endgame simplify dominant convert",
    },
    "MIDDLE_TAL": {
        "label":    "Middle Tal",
        "short":    "large advantage, attack, tactics",
        "win_range": "84–89%",
        "report":  "⚔️⚔️ Large Advantage (win prob 84–89%) — "
                   "Major advantage, likely winning with correct play. "
                   "Aggressive piece coordination, attack, or decisive tactical shot.",
        "prompt":  "large advantage — aggressive piece coordination, look for decisive tactical shots",
        "retriever_keywords": "tactical attack sacrifice combination decisive attack king",
    },
    "MIDDLE_HIGH_TAL": {
        "label":    "Middle-High Tal",
        "short":    "winning, tactical fireworks",
        "win_range": "89–94%",
        "report":  "⚔️⚔️ Winning Position (win prob 89–94%) — "
                   "Near-decisive advantage. Look for forcing moves, "
                   "king attacks, and combinations to convert.",
        "prompt":  "winning position — find forcing moves, king attacks, combinations to convert",
        "retriever_keywords": "forcing combination king attack checkmate decisive tactics",
    },
    "HIGH_TAL": {
        "label":    "High Tal",
        "short":    "decisive advantage, combinations, checkmate",
        "win_range": "94–100%",
        "report":  "⚔️⚔️⚔️ Decisive Advantage (win prob 94–100%) — "
                   "Position is essentially won. Find the fastest path to "
                   "checkmate or material win.",
        "prompt":  "decisive advantage — find fastest checkmate or material win, calculate accurately",
        "retriever_keywords": "checkmate forced mate decisive combination sacrifice win",
    },
    "TAL_CAPABLANCA_PETROSIAN": {
        "label":    "Chaotic / Undefined",
        "short":    "complex, dynamically unclear",
        "win_range": "?",
        "report":  "🌀 Chaotic Position — dynamic balance, hard to evaluate. "
                   "Both sides have chances, sharp play required.",
        "prompt":  "complex chaotic position — dynamic balance, sharp tactical play, concrete calculation",
        "retriever_keywords": "tactics attack defense complex dynamic sharp",
    },
}


def prompt_description(zone: str) -> str:
    """Short description for use inside the LLM prompt."""
    entry = ZONES.get(zone, ZONES.get("CAPABLANCA"))
    return entry["prompt"]


def report_description(zone: str) -> str:
    """Full description for use in the human-readable report."""
    entry = ZONES.get(zone, ZONES.get("CAPABLANCA"))
    return entry["report"]


def zone_label(zone: str) -> str:
    entry = ZONES.get(zone, ZONES.get("CAPABLANCA"))
    return entry["label"]


def retriever_keywords(zone: str) -> str:
    entry = ZONES.get(zone, ZONES.get("CAPABLANCA"))
    return entry.get("retriever_keywords", "")


def win_range(zone: str) -> str:
    entry = ZONES.get(zone, ZONES.get("CAPABLANCA"))
    return entry.get("win_range", "?")
