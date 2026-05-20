"""
Dynamic section gating and structural anomaly detection from Alexander eval.

Rules
-----
All six Alexander eval sections now have anomaly-driven switches:

  game_phase     — optional suppress in Opening (game_phase_suppress_opening flag);
                   always emits a verbal remark when the phase changes (phase_transition_remark).
  score_table    — eval-jump gate: shown only when |curr_eval_cp - prev_eval_cp| >= threshold.
  pawn_structure — weakness gate: shown only when max(weaknesses_per_side) >= threshold.
  space          — imbalance gate: shown only when |white_sq - black_sq| >= threshold.
  mobility       — activity gate: shown only when |score_mobility| >= threshold cp.
  makogonov      — phase gate: suppressed during Opening (pieces undeveloped).

Structural anomalies (M/W/K/S/C checks) additionally produce:
  • BM25 extra tokens  → injected into retrieval query for better chunk selection
  • One-line summary   → compact "Structural alerts:" section in the prompt

All thresholds default to sensible values and are overridable via PromptConfig /
eval_config.json. Threshold = 0 disables the gate (field always shown when config flag is on).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .eval_parser import EvalSections

# ── Structural anomaly thresholds (internal, not user-configurable) ────────────

_MOBILITY_SCORE_THRESHOLD = 30   # cp: |score_mobility| above this → passive pieces alert
_KING_SAFETY_THRESHOLD    = 40   # cp: |score_king_safety| above this → king exposed alert
_PAWN_WEAKNESS_THRESHOLD  = 3    # count: pawn weaknesses per side above this → alert
_SPACE_DIFF_THRESHOLD     = 6    # squares: total space gap above this → cramped alert
_CONTRADICTION_EVAL_MIN   = 50   # cp: score_cp above this …
_CONTRADICTION_WIN_MAX    = 40   # %: … but win_prob below this → compensation alert

# ── Phase transition phrases ───────────────────────────────────────────────────

_TRANSITIONS: dict[tuple[str, str], str] = {
    ("opening",    "middlegame"): "The Opening is over — the Middlegame begins.",
    ("middlegame", "endgame"):    "This move transitions the game to the Endgame.",
    ("opening",    "endgame"):    "The game jumps directly from Opening to Endgame.",
}


# ── Output dataclass ───────────────────────────────────────────────────────────

@dataclass
class AnomalyFlags:
    """
    Gating decisions and BM25 signal produced by detect_anomalies().

    show_* fields: True = allow the section to render (config flag must also be True).
    phase_transition_remark: non-empty string = phase just changed; show as separate section.
    anomaly_tokens: extra BM25 tokens from structural defects.
    anomaly_summary: one-line "Structural alerts:" prompt section.
    """
    show_score_table:    bool = False
    show_game_phase:     bool = True
    show_pawn_structure: bool = True
    show_space:          bool = True
    show_mobility:       bool = True
    show_makogonov:      bool = False
    phase_transition_remark: str = ""
    anomaly_tokens: list[str] = field(default_factory=list)
    anomaly_summary: str = ""


# ── Main function ──────────────────────────────────────────────────────────────

def detect_anomalies(
    ev: EvalSections,
    prev_eval_cp: Optional[int],
    curr_eval_cp: Optional[int],
    score_jump_threshold_cp: int = 50,
    pawn_weakness_threshold: int = 2,
    space_imbalance_threshold: int = 4,
    mobility_score_threshold: int = 20,
    game_phase_suppress_opening: bool = False,
    prev_game_phase: Optional[str] = None,
) -> AnomalyFlags:
    """
    Compute gating flags and BM25 anomaly tokens from parsed eval sections.

    Parameters
    ----------
    ev                          : Parsed Alexander eval sections for this position.
    prev_eval_cp                : White-perspective centipawns from the previous move.
    curr_eval_cp                : White-perspective centipawns for this position.
    score_jump_threshold_cp     : Min |delta_cp| to show the score table (0 = always).
    pawn_weakness_threshold     : Min max(weaknesses_per_side) to show pawn structure (0 = always).
    space_imbalance_threshold   : Min |white_sq - black_sq| to show space section (0 = always).
    mobility_score_threshold    : Min |score_mobility| cp to show mobility section (0 = always).
    game_phase_suppress_opening : When True, suppress game_phase section during Opening.
    prev_game_phase             : Game phase of the previous position for transition detection.
    """
    flags = AnomalyFlags()
    phase = ev.game_phase.strip().lower() if ev.game_phase else ""

    # ── Score table gate: eval jump ───────────────────────────────────────────
    if prev_eval_cp is not None and curr_eval_cp is not None:
        flags.show_score_table = abs(curr_eval_cp - prev_eval_cp) >= score_jump_threshold_cp
    else:
        flags.show_score_table = False  # no delta → suppress

    # ── Makogonov gate: phase check ───────────────────────────────────────────
    # Meaningful only in middlegame/endgame; "" = no eval available → skip.
    flags.show_makogonov = phase in ("middlegame", "endgame")

    # ── Game phase display gate ───────────────────────────────────────────────
    if game_phase_suppress_opening:
        flags.show_game_phase = phase not in ("opening", "")
    else:
        flags.show_game_phase = True

    # ── Phase transition remark ───────────────────────────────────────────────
    if prev_game_phase and ev.game_phase:
        prev_lower = prev_game_phase.strip().lower()
        if prev_lower != phase and phase:
            flags.phase_transition_remark = _TRANSITIONS.get(
                (prev_lower, phase),
                f"The game phase changed from {prev_game_phase} to {ev.game_phase}.",
            )

    # ── Pawn structure gate: weakness threshold ───────────────────────────────
    if pawn_weakness_threshold > 0:
        w = ev.pawn_weaknesses_white or 0
        b = ev.pawn_weaknesses_black or 0
        flags.show_pawn_structure = max(w, b) >= pawn_weakness_threshold
    else:
        flags.show_pawn_structure = True

    # ── Space gate: imbalance threshold ──────────────────────────────────────
    if space_imbalance_threshold > 0:
        if ev.space_white is not None and ev.space_black is not None:
            flags.show_space = abs(ev.space_white - ev.space_black) >= space_imbalance_threshold
        else:
            flags.show_space = False  # no data → suppress
    else:
        flags.show_space = True

    # ── Mobility gate: activity threshold ─────────────────────────────────────
    if mobility_score_threshold > 0:
        if ev.score_mobility is not None:
            flags.show_mobility = abs(ev.score_mobility) >= mobility_score_threshold
        else:
            flags.show_mobility = False  # no data → suppress
    else:
        flags.show_mobility = True

    # ── Structural anomaly detection (BM25 tokens + summary) ─────────────────
    # Only fires in middlegame; opening/endgame positions have different baselines.
    if phase != "middlegame":
        return flags

    tokens: list[str] = []
    parts: list[str] = []

    # M: Mobility gap — passive pieces on one side
    if ev.score_mobility is not None and abs(ev.score_mobility) > _MOBILITY_SCORE_THRESHOLD:
        who = "White" if ev.score_mobility < 0 else "Black"
        tokens += ["passive", "piece", "activity", "mobility", "outpost", "coordination"]
        parts.append(f"{who} has passive pieces")

    # W: Pawn weakness overload
    for color, weak in (("White", ev.pawn_weaknesses_white), ("Black", ev.pawn_weaknesses_black)):
        if weak is not None and weak >= _PAWN_WEAKNESS_THRESHOLD:
            tokens += ["pawn", "weakness", "isolated", "doubled", "backward", "structure"]
            parts.append(f"{color} has {weak} pawn weaknesses")

    # K: King safety alarm
    if ev.score_king_safety is not None and abs(ev.score_king_safety) > _KING_SAFETY_THRESHOLD:
        who = "White" if ev.score_king_safety < 0 else "Black"
        tokens += ["king", "safety", "attack", "shelter", "exposed", "assault"]
        parts.append(f"{who} king is exposed")

    # S: Space cramping
    if ev.space_white is not None and ev.space_black is not None:
        diff = ev.space_white - ev.space_black
        if abs(diff) >= _SPACE_DIFF_THRESHOLD:
            cramped = "White" if diff < 0 else "Black"
            tokens += ["space", "cramped", "outpost", "restriction", "maneuvering"]
            parts.append(f"{cramped} is cramped")

    # C: Zone / score contradiction (score says winning but win% disagrees)
    if (ev.final_eval_cp is not None and ev.win_prob_pct is not None
            and ev.final_eval_cp > _CONTRADICTION_EVAL_MIN
            and ev.win_prob_pct < _CONTRADICTION_WIN_MAX):
        tokens += ["compensation", "imbalance", "counterplay", "dynamic", "initiative"]
        parts.append("eval/win-prob contradiction — dynamic compensation likely")

    flags.anomaly_tokens = tokens
    if parts:
        flags.anomaly_summary = "Structural alerts: " + "; ".join(parts) + "."

    return flags
