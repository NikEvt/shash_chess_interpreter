"""
Parser for Alexander engine's 'eval' command output.

Turns raw_eval_lines (180+ lines) into EvalSections — a structured dataclass
with one field per meaningful fact. Prompt builder reads from EvalSections
instead of raw text; PromptConfig controls which fields reach the LLM.

Section detection is line-by-line regex; order in the file does not matter.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ── Parsed eval sections ───────────────────────────────────────────────────────

@dataclass
class EvalSections:
    # General
    game_phase: str = ""               # "Opening" / "Middlegame" / "Endgame"
    final_eval_cp: Optional[int] = None
    win_prob_pct: Optional[int] = None

    # Score table — total column (centipawns, side-to-move perspective)
    score_material: Optional[int] = None
    score_imbalances: Optional[int] = None
    score_pawns: Optional[int] = None
    score_knights: Optional[int] = None
    score_bishops: Optional[int] = None
    score_rooks: Optional[int] = None
    score_king_safety: Optional[int] = None
    score_threats: Optional[int] = None
    score_mobility: Optional[int] = None
    score_space: Optional[int] = None

    # Pawn structure
    pawn_islands_white: Optional[int] = None
    pawn_islands_black: Optional[int] = None
    pawn_weaknesses_white: Optional[int] = None
    pawn_weaknesses_black: Optional[int] = None
    pawn_doubled_white: Optional[int] = None
    pawn_doubled_black: Optional[int] = None
    pawn_isolated_white: Optional[int] = None
    pawn_isolated_black: Optional[int] = None
    center_type: str = ""              # "Dynamic Center", "Closed Center", …

    # Space
    space_white: Optional[int] = None
    space_black: Optional[int] = None
    delta_expansion: Optional[float] = None   # positive = white expands more

    # Mobility
    mobility_initiative: str = ""      # "White" | "Black" | ""
    mobility_kasparov: str = ""        # "attack on the queen side" etc.

    # Makogonov (weakest units)
    makogonov_white: str = ""          # "Bishop on c1 (activity: -2)"
    makogonov_black: str = ""          # "Pawn on a7 (activity: 3)"

    # Top moves by static activity (from "Legal moves sorted" line)
    activity_moves: list[tuple[str, int, int]] = field(default_factory=list)
    # [(uci, win_pct, activity), ...]  — first 5 only


# ── Parser ─────────────────────────────────────────────────────────────────────

# Score-table row pattern: "     Material |    -7   -64    -8 |"
_SCORE_ROW = re.compile(
    r"^\s*([\w\s]+?)\s*\|\s*([+-]?\d+)\s+([+-]?\d+)\s+([+-]?\d+)\s*\|",
)
_SCORE_NAMES: dict[str, str] = {
    "material":   "score_material",
    "imbalances": "score_imbalances",
    "pawns":      "score_pawns",
    "knights":    "score_knights",
    "bishops":    "score_bishops",
    "rooks":      "score_rooks",
    "king safety":"score_king_safety",
    "threats":    "score_threats",
    "mobility":   "score_mobility",
    "space":      "score_space",
}


def parse_eval_sections(lines: list[str]) -> EvalSections:
    """Parse raw_eval_lines into EvalSections. Tolerant of missing sections."""
    s = EvalSections()

    for line in lines:
        raw = line.strip()
        lower = raw.lower()

        # Game phase
        if lower.startswith("game phase:"):
            s.game_phase = raw.split(":", 1)[1].strip()
            continue

        # Final evaluation: -52 (Win Probability: 46%)
        m = re.search(r"final evaluation:\s*([+-]?\d+)\s*\(win probability:\s*(\d+)%\)", lower)
        if m:
            s.final_eval_cp = int(m.group(1))
            s.win_prob_pct = int(m.group(2))
            continue

        # Score table row
        m = _SCORE_ROW.match(raw)
        if m:
            name = m.group(1).strip().lower()
            total = int(m.group(4))
            attr = _SCORE_NAMES.get(name)
            if attr:
                setattr(s, attr, total)
            continue

        # Pawn islands
        m = re.match(r"white:\s*(\d+)\s+islands?", lower)
        if m:
            s.pawn_islands_white = int(m.group(1))
            continue
        m = re.match(r"black:\s*(\d+)\s+islands?", lower)
        if m:
            s.pawn_islands_black = int(m.group(1))
            continue

        # Pawn weaknesses — "White pawn weaknesses: 0 (Doubled: 0, Isolated: 0, Backward: 0, Hanging: 0)"
        m = re.match(
            r"(white|black) pawn weaknesses:\s*(\d+)\s*\(doubled:\s*(\d+),\s*isolated:\s*(\d+)",
            lower,
        )
        if m:
            side, total, doubled, isolated = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
            if side == "white":
                s.pawn_weaknesses_white = total
                s.pawn_doubled_white = doubled
                s.pawn_isolated_white = isolated
            else:
                s.pawn_weaknesses_black = total
                s.pawn_doubled_black = doubled
                s.pawn_isolated_black = isolated
            continue

        # Center type — "Center Type: Dynamic Center"
        m = re.match(r"center type:\s*(.+)", lower)
        if m:
            # Preserve original capitalisation
            idx = raw.lower().index("center type:")
            s.center_type = raw[idx + len("center type:"):].strip()
            continue

        # Space total — "Total Space: White 16 - Black 22"
        m = re.search(r"total space:\s*white\s*(\d+)\s*-\s*black\s*(\d+)", lower)
        if m:
            s.space_white = int(m.group(1))
            s.space_black = int(m.group(2))
            continue

        # Delta expansion — "Delta Expansion (White-Black): -0.59"
        m = re.search(r"delta expansion.*?:\s*([+-]?\d+\.?\d*)", lower)
        if m:
            try:
                s.delta_expansion = float(m.group(1))
            except ValueError:
                pass
            continue

        # Mobility initiative — "Black has the initiative. Kasparov Principle: ..."
        m = re.search(r"(white|black) has the initiative", lower)
        if m:
            s.mobility_initiative = m.group(1).capitalize()
            # Try to grab Kasparov advice from same line
            km = re.search(r"kasparov principle:\s*try to (.+?)(?:;|$)", lower)
            if km:
                s.mobility_kasparov = km.group(1).strip()
            continue

        # Makogonov — "Makogonov White: Improve Bishop on c1 (activity: -2)"
        m = re.match(r"makogonov (white|black):\s*improve\s+(.+)", lower)
        if m:
            side = m.group(1)
            # Preserve original capitalisation for piece names
            idx = raw.lower().index("improve")
            detail = raw[idx + len("improve"):].strip()
            if side == "white":
                s.makogonov_white = detail
            else:
                s.makogonov_black = detail
            continue

        # Legal moves sorted by activity — first 5
        if "legal moves sorted" in lower and "%" in raw:
            pairs = re.findall(r"(\w{4,5})\((\d+)%/([+-]?\d+)\)", raw)
            s.activity_moves = [(uci, int(w), int(a)) for uci, w, a in pairs[:5]]
            continue

    return s


# ── Compact text renderers ─────────────────────────────────────────────────────

def render_score_table(s: EvalSections) -> str:
    """
    One-line compact score table: fields with non-zero totals only.
    Example: "Mat:-0.1 Mob:-0.3 KSaf:+0.1 Pawn:-0.1 Spc:-0.1"
    """
    mapping = [
        ("Mat",  s.score_material),
        ("Mob",  s.score_mobility),
        ("KSaf", s.score_king_safety),
        ("Pawn", s.score_pawns),
        ("Spc",  s.score_space),
        ("Thr",  s.score_threats),
    ]
    parts = []
    for label, val in mapping:
        if val is not None and val != 0:
            sign = "+" if val > 0 else ""
            parts.append(f"{label}:{sign}{val / 100:.2f}")
    return " ".join(parts) if parts else ""


def render_pawn_structure(s: EvalSections) -> str:
    """
    Compact pawn summary + center type.
    Example: "W:0weak(2isl) B:4weak(3isl,2dbl,2iso) | Dynamic Center"
    """
    def _side(weak, islands, dbl, iso):
        parts = []
        if islands is not None:
            parts.append(f"{islands}isl")
        if dbl:
            parts.append(f"{dbl}dbl")
        if iso:
            parts.append(f"{iso}iso")
        inner = ",".join(parts)
        w = weak if weak is not None else "?"
        return f"{w}weak({inner})"

    w = _side(s.pawn_weaknesses_white, s.pawn_islands_white, s.pawn_doubled_white, s.pawn_isolated_white)
    b = _side(s.pawn_weaknesses_black, s.pawn_islands_black, s.pawn_doubled_black, s.pawn_isolated_black)
    result = f"W:{w} B:{b}"
    if s.center_type:
        result += f" | {s.center_type}"
    return result


def render_space(s: EvalSections) -> str:
    """Example: "W16–B22 | expansion Δ-0.59 (Black expanding)" """
    parts = []
    if s.space_white is not None and s.space_black is not None:
        parts.append(f"W{s.space_white}–B{s.space_black}")
    if s.delta_expansion is not None:
        d = s.delta_expansion
        who = "White" if d > 0 else "Black"
        parts.append(f"Δ{d:+.2f} ({who} expanding)")
    return " | ".join(parts)


def render_mobility(s: EvalSections) -> str:
    """Example: "Black initiative | attack on the queen side" """
    parts = []
    if s.mobility_initiative:
        parts.append(f"{s.mobility_initiative} initiative")
    if s.mobility_kasparov:
        parts.append(s.mobility_kasparov)
    return " | ".join(parts)


def render_makogonov(s: EvalSections) -> str:
    """Example: "W:Bishop on c1(-2) B:Pawn on a7(+3)" """
    parts = []
    if s.makogonov_white:
        parts.append(f"W:{s.makogonov_white}")
    if s.makogonov_black:
        parts.append(f"B:{s.makogonov_black}")
    return " | ".join(parts)
