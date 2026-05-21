"""
Prompt builder for Alexander engine interpreter.

Uses all data Alexander exposes beyond basic UCI:
  - 14-zone Shashin position classification with win probability
  - Top-3 moves from MultiPV with per-move WDL
  - PV continuation in SAN (planned sequence)
  - Full Alexander eval sections (score table, pawn structure, space,
    mobility/Kasparov, Makogonov worst-piece ranking)
  - Move quality delta between played move and engine recommendation

PromptConfig controls which sections are included (for token budget tuning).
FEN is intentionally excluded — the model cannot parse it.

Token budget reference (600-token target):
  Fixed sections (system, last move, eval change, engine rec, question): ~130
  Theory (1 chunk):                                                       ~50
  Alexander eval sections (all on):                                       ~70
  Headroom:                                                              ~350
"""
from __future__ import annotations

import dataclasses as _dc
from dataclasses import dataclass
from typing import Optional

import chess

from .types import AlexanderResult
from .retriever import retrieve, retrieve_opening_theory, retrieve_with_score
from .opening_book import lookup as _ob_lookup
from . import shashin as shashin_mod
from .verbalizer import (
    verbalize_san,
    verbalize_pv,
    verbalize_pv_verbose,
    verbalize_eval,
    verbalize_eval_delta,
)
from .eval_parser import (
    EvalSections,
    parse_eval_sections,
    render_score_table,
    render_pawn_structure,
    render_space,
    render_mobility,
    render_makogonov,
    render_score_table_verbose,
    render_pawn_structure_verbose,
    render_space_verbose,
    render_makogonov_verbose,
)
from .anomaly_detector import detect_anomalies


# ── Prompt configuration ───────────────────────────────────────────────────────

@dataclass
class PromptConfig:
    """
    Controls which sections appear in build_tiny_prompt.

    Defaults target ≤300 tokens (0.6B models).
    Set max_tokens=600 and flip booleans for larger models.
    """
    max_tokens: int = 600

    # Fixed sections — disable only for very small models
    include_system: bool = True
    include_last_move: bool = True
    include_eval_change: bool = True
    include_question: bool = True

    # Engine search sections
    include_engine_recommendation: bool = True
    include_pv_continuation: bool = True

    # Alexander eval sections (require raw_eval_lines from eval command)
    include_game_phase: bool = True
    include_score_table: bool = False     # compact one-line score breakdown
    include_pawn_structure: bool =False  # weakness counts + center type
    include_space: bool = False           # space totals + expansion delta
    include_mobility: bool = False        # Kasparov principle + initiative
    include_makogonov: bool = False       # worst unit per side

    # Opening book
    include_opening_name: bool = True   # "Opening: Sicilian Najdorf (B90)"

    # Theory (BM25 retrieval fallback + opening theory)
    include_theory: bool = True
    theory_chunks: int = 1
    # Max characters of opening theory to include in the prompt.
    # Opening theory chunks are ~500-800 chars each; mistake/blunder path
    # returns 2 chunks combined (~1000-1300 chars).
    # 0.6B models: 400 chars  |  1B-3B: 800  |  7B+: 1600
    theory_max_chars: int = 800
    # Minimum normalized BM25 score (0.0–1.0) to include BM25-fallback theory.
    # 0.0 = always include; ~0.3 = moderate gate; 1.0 = never include fallback.
    # Opening-book theory (retrieve_opening_theory) is always trusted (score=1.0).
    theory_relevance_threshold: float = 0.0

    # Anomaly gating thresholds (0 = always show when config flag is True)
    # score_jump_threshold_cp : min |delta_cp| to show the score table
    # pawn_weakness_threshold : min max(weaknesses_per_side) to show pawn structure
    # space_imbalance_threshold: min |white_sq - black_sq| to show space section
    # mobility_score_threshold : min |score_mobility| cp to show mobility section
    # game_phase_suppress_opening: when True, suppress game_phase in Opening phase
    score_jump_threshold_cp:     int  = 50
    pawn_weakness_threshold:     int  = 2
    space_imbalance_threshold:   int  = 4
    mobility_score_threshold:    int  = 20
    game_phase_suppress_opening: bool = False


# Default configs for common use cases

COMPACT_CONFIG = PromptConfig(
    max_tokens=300,
    include_score_table=False,
    include_pawn_structure=False,
    include_space=False,
    include_mobility=False,
    include_makogonov=False,
    theory_max_chars=400,
)

# All Alexander eval sections on — use for 7B+ models
FULL_CONFIG = PromptConfig(
    max_tokens=600,
    include_score_table=True,
    include_pawn_structure=True,
    include_space=True,
    include_mobility=True,
    include_makogonov=True,
    theory_max_chars=1600,
)

# Balanced preset for 1B–3B models
MEDIUM_CONFIG = PromptConfig(
    max_tokens=450,
    include_score_table=True,
    include_pawn_structure=True,
    include_mobility=True,
    include_space=False,
    include_makogonov=False,
    theory_max_chars=800,
)

# Ablation baseline: core sections only, no Alexander eval, no theory
MINIMAL_CONFIG = PromptConfig(
    max_tokens=200,
    include_pv_continuation=False,
    include_game_phase=False,
    include_score_table=False,
    include_pawn_structure=False,
    include_space=False,
    include_mobility=False,
    include_makogonov=False,
    include_theory=False,
)

# Named presets ordered from least to most information
CONFIG_PRESETS: dict[str, PromptConfig] = {
    "minimal": MINIMAL_CONFIG,
    "compact": COMPACT_CONFIG,
    "medium":  MEDIUM_CONFIG,
    "full":    FULL_CONFIG,
}

# Section flags for UI toggle: (dataclass_field_name, display_label, group)
SECTION_FLAGS: list[tuple[str, str, str]] = [
    ("include_system",                "System instruction",  "core"),
    ("include_last_move",             "Last move",           "core"),
    ("include_eval_change",           "Eval change",         "core"),
    ("include_engine_recommendation", "Engine rec.",         "core"),
    ("include_pv_continuation",       "PV continuation",     "core"),
    ("include_opening_name",          "Opening name",        "core"),
    ("include_theory",                "Theory",              "core"),
    ("include_game_phase",            "Game phase",          "alexander"),
    ("include_score_table",           "Score table",         "alexander"),
    ("include_pawn_structure",        "Pawn structure",      "alexander"),
    ("include_space",                 "Space",               "alexander"),
    ("include_mobility",              "Mobility",            "alexander"),
    ("include_makogonov",             "Makogonov",           "alexander"),
]


def build_config(preset: str = "full", overrides: dict[str, bool] | None = None) -> PromptConfig:
    """Build a PromptConfig from a named preset + optional per-field overrides.

    Used for research/ablation: pick a baseline preset then flip individual flags.
    Unknown override keys are silently ignored.
    """
    base = CONFIG_PRESETS.get(preset, FULL_CONFIG)
    if overrides:
        valid = {k: v for k, v in overrides.items()
                 if k in {f.name for f in _dc.fields(base)}}
        if valid:
            base = _dc.replace(base, **valid)
    return base

LEVEL_INSTRUCTIONS: dict[str, str] = {
    "beginner":     "Use simple language, avoid chess jargon.",
    "intermediate": "Brief technical terms are fine.",
    "advanced":     "Use chess terminology freely.",
}

QUESTION_TEMPLATES: dict[str, str] = {
    "best_move": (
        "What is the best move and why? "
        "Compare it to the move actually played in the game."
    ),
    "explain": (
        "Explain the current position and evaluate the move played "
        "versus the engine's recommendation."
    ),
    "plan": (
        "What is the strategic plan for the side to move? Discuss whether the move played "
        "fits that plan or if the engine's suggestion is superior."
    ),
} 


def _move_quality_label(played: str, best_san: str, score_cp: int | None, eval_loss: int | None = None) -> str:
    if played == best_san:
        return "best move"
    # Prefer explicit eval_loss (delta from previous position) if available
    delta = eval_loss if eval_loss is not None else (abs(score_cp) if score_cp is not None else None)
    if delta is None:
        return "played"
    if delta <= 5:
        return "best"
    if delta <= 20:
        return "excellent"
    if delta <= 50:
        return "good"
    if delta <= 100:
        return "inaccuracy"
    if delta <= 200:
        return "mistake"
    return "blunder"


def _eval_str(result: AlexanderResult) -> str:
    if result.mate_in is not None:
        n = result.mate_in
        return f"Forced checkmate in {n} move{'s' if n != 1 else ''}"
    if result.score_cp is None:
        return "Evaluation unavailable"
    sign = "+" if result.score_cp >= 0 else ""
    pawns = result.score_cp / 100
    side = "White" if result.score_cp >= 0 else "Black"
    return (
        f"{side} is better by {sign}{pawns:.1f} pawns — "
        f"win {result.win_pct:.0f}% / draw {result.draw_pct:.0f}% / loss {result.loss_pct:.0f}%"
    )


def _top_moves_block(result: AlexanderResult) -> str:
    if not result.top_moves:
        return f"  1. {result.best_move_san} (best)"
    lines: list[str] = []
    for i, m in enumerate(result.top_moves[:3], 1):
        score = m.score_str()
        wdl = f"{m.win_pct:.0f}%/{m.draw_pct:.0f}%"
        lines.append(f"  {i}. {m.san}  [{score}, win {wdl}]")
    return "\n".join(lines)


def _pv_block(result: AlexanderResult) -> str:
    pv = result.pv_san[:5]
    if not pv:
        return ""
    return "  Best continuation: " + " ".join(pv)


def _eval_trace_block(result: AlexanderResult) -> str:
    if not result.eval_trace:
        return ""
    t = result.eval_trace
    parts = []
    if t.best_win_pct is not None:
        parts.append(f"win probability {t.best_win_pct:.0f}%")
    for name, val in t.significant_factors()[:2]:
        sign = "+" if val > 0 else ""
        parts.append(f"{name.replace('_', ' ')} {sign}{val:.1f}")
    if not parts:
        return ""
    return "  Key eval factors: " + ", ".join(parts)


def build_prompt_sections(
    result: AlexanderResult,
    moves_history: list[str],
    level: str,
    question: str,
    eval_loss: int | None = None,
) -> list[dict]:
    """Return the prompt broken into labeled sections for debug display."""
    level_hint = LEVEL_INSTRUCTIONS.get(level, LEVEL_INSTRUCTIONS["intermediate"])
    question_text = QUESTION_TEMPLATES.get(question, question)

    played = result.played_move or None
    quality_label = _move_quality_label(played or "", result.best_move_san, result.score_cp, eval_loss) if played else None
    opening_theory = retrieve_opening_theory(result, move_quality=quality_label)
    if opening_theory:
        theory_text = opening_theory
    else:
        theory_chunks = retrieve(result, question, top_k=2, played_move=played)
        theory_text = "\n".join(f"- {chunk}" for chunk in theory_chunks) or "(none)"

    moves_str = " ".join(moves_history[-6:]) if moves_history else "none"

    zone_lbl = shashin_mod.zone_label(result.shashin_zone)
    zone_desc = shashin_mod.prompt_description(result.shashin_zone)
    zone_win_range = shashin_mod.win_range(result.shashin_zone)

    position_lines = [f"Recent moves: {moves_str}"]
    if played:
        position_lines.append(f"Move played: {played} ({quality_label})")
    position_lines += [
        f"Side to move: {result.side_to_move.capitalize()}",
        f"Evaluation: {_eval_str(result)}",
        f"Shashin zone: {zone_lbl} ({zone_win_range}) — {zone_desc}",
    ]
    if result.top_moves:
        tm_lines = []
        for i, m in enumerate(result.top_moves[:3], 1):
            score = m.score_str()
            wdl = f"{m.win_pct:.0f}%/{m.draw_pct:.0f}%"
            tm_lines.append(f"  {i}. {m.san}  [{score}, win {wdl}]")
        position_lines.append("Engine top moves:\n" + "\n".join(tm_lines))
    pv = result.pv_san[:5]
    if pv:
        position_lines.append("Best continuation: " + " ".join(pv))
    eval_trace_line = _eval_trace_block(result)
    if eval_trace_line.strip():
        position_lines.append(eval_trace_line.strip())

    if played and played != result.best_move_san:
        comparison = (
            f"Game continued with {played}, engine recommends {result.best_move_san} as stronger. "
            f"Explain WHY {result.best_move_san} is better than {played}."
        )
    elif played:
        comparison = f"{played} matches the engine's best move. Explain what makes it the strongest choice."
    else:
        comparison = None

    sections = [
        {"label": "System instruction", "content": f"You are a chess coach. {level_hint} Answer in 2-3 sentences. Be specific — mention moves by name."},
        {"label": "Chess theory", "content": theory_text},
        {"label": "Position info", "content": "\n".join(position_lines)},
    ]
    if comparison:
        sections.append({"label": "Move comparison", "content": comparison})
    sections.append({"label": "Question", "content": question_text})
    return sections


def build_prompt(
    result: AlexanderResult,
    moves_history: list[str],
    level: str,
    question: str,
    eval_loss: int | None = None,
) -> str:
    level_hint = LEVEL_INSTRUCTIONS.get(level, LEVEL_INSTRUCTIONS["intermediate"])
    question_text = QUESTION_TEMPLATES.get(question, question)

    played = result.played_move or None
    quality_label = _move_quality_label(played or "", result.best_move_san, result.score_cp, eval_loss) if played else None
    opening_theory = retrieve_opening_theory(result, move_quality=quality_label)
    if opening_theory:
        theory_text = opening_theory
    else:
        theory_chunks = retrieve(result, question, top_k=2, played_move=played)
        theory_text = "\n".join(f"- {chunk}" for chunk in theory_chunks)

    moves_str = " ".join(moves_history[-6:]) if moves_history else "none"

    # Shashin zone info
    zone_lbl = shashin_mod.zone_label(result.shashin_zone)
    zone_desc = shashin_mod.prompt_description(result.shashin_zone)
    zone_win_range = shashin_mod.win_range(result.shashin_zone)

    # Move quality
    quality_label = _move_quality_label(played or "", result.best_move_san, result.score_cp, eval_loss) if played else None

    # Build blocks
    played_line = f"  Move played: {played} ({quality_label})\n" if played else ""

    if played and played != result.best_move_san:
        comparison_block = (
            f"  Move comparison: Game continued with {played}, "
            f"engine recommends {result.best_move_san} as stronger. "
            f"Explain WHY {result.best_move_san} is better than {played}.\n"
        )
    elif played:
        comparison_block = (
            f"  Move comparison: {played} matches the engine's best move. "
            f"Explain what makes it the strongest choice.\n"
        )
    else:
        comparison_block = ""

    eval_trace_line = _eval_trace_block(result)
    pv_line = _pv_block(result)
    top_moves_block = _top_moves_block(result)

    return (
        f"You are a chess coach. {level_hint} "
        f"Answer in 2-3 sentences. Be specific — mention moves by name.\n\n"
        f"Chess theory:\n{theory_text}\n\n"
        f"  Recent moves: {moves_str}\n"
        f"{played_line}"
        f"  Side to move: {result.side_to_move.capitalize()}\n"
        f"  Evaluation: {_eval_str(result)}\n"
        f"  Shashin zone: {zone_lbl} ({zone_win_range}) — {zone_desc}\n"
        f"\n  Engine top moves:\n{top_moves_block}\n"
        f"{pv_line}\n" if pv_line else ""
        f"{eval_trace_line}\n" if eval_trace_line else ""
        f"\n{comparison_block}"
        f"\nQuestion: {question_text}"
    )


# ── Tiny prompt pipeline (≤300 tokens, for 0.6B models) ───────────────────────

_QUALITY_WORD = {
    "best move": "best",
    "best":      "best",
    "excellent": "good",
    "good":      "good",
    "inaccuracy":"inaccuracy",
    "mistake":   "mistake",
    "blunder":   "blunder",
    "alternative":"alternative",
    "played":     "played",
}

_QUESTION_TEXTS: dict[str, str] = {
    "best_move": (
        "Why did the engine prefer a different move, and what would it have accomplished?"
    ),
    "explain": (
        "Briefly explain the significance of the last move and its impact on the position."
    ),
    "plan": (
        "What is the strategic idea behind the last move, and does it fit the position?"
    ),
}


def _tiny_quality(played: str, best_san: str, score_cp: Optional[int], eval_loss: Optional[int]) -> str:
    """Return a simplified 1-word quality label for the tiny prompt."""
    raw = _move_quality_label(played, best_san, score_cp, eval_loss)
    return _QUALITY_WORD.get(raw, raw)


def _build_tiny_sections(
    result: AlexanderResult,
    prev_eval_cp: Optional[int],
    curr_eval_cp: Optional[int],
    curr_eval_mate: Optional[int],
    our_side: str,
    question_type: str,
    board_before: Optional[chess.Board] = None,
    eval_loss: Optional[int] = None,
    config: Optional[PromptConfig] = None,
    prev_game_phase: Optional[str] = None,
) -> list[dict]:
    """
    Internal builder — returns labeled sections for the tiny prompt.
    All eval inputs are from White's perspective (positive = good for White).
    Alexander-specific sections are gated by config flags.
    """
    cfg = config or FULL_CONFIG
    Our_Side = our_side.capitalize()
    played = result.played_move or ""
    # side_to_move is who moves NEXT, so who just played is the opposite
    color_who_played = "black" if result.side_to_move == "white" else "white"
    best_san = result.best_move_san or ""

    # Build question text — anchor "plan" and "explain" to the specific move so the
    # model doesn't substitute general opening theory for a concrete answer.
    if question_type == "plan" and played:
        question_text = f"What is the strategic idea behind {played}, and does it fit the position?"
    elif question_type == "explain" and played:
        question_text = f"Explain {played} and its impact on the position."
    else:
        question_text = _QUESTION_TEXTS.get(question_type, _QUESTION_TEXTS["explain"])

    # When the played move matched the engine's top choice, "why did the engine prefer
    # a different move?" is contradictory — switch to a neutral explain question.
    if question_type == "best_move" and played and best_san and played == best_san:
        question_text = _QUESTION_TEXTS["explain"]

    # Parse Alexander eval sections (no-op if raw_eval_lines is empty)
    ev = parse_eval_sections(result.raw_eval_lines)

    # Dynamic gating: all six Alexander sections have anomaly-driven switches
    anomaly = detect_anomalies(
        ev,
        prev_eval_cp=prev_eval_cp,
        curr_eval_cp=curr_eval_cp,
        score_jump_threshold_cp=cfg.score_jump_threshold_cp,
        pawn_weakness_threshold=cfg.pawn_weakness_threshold,
        space_imbalance_threshold=cfg.space_imbalance_threshold,
        mobility_score_threshold=cfg.mobility_score_threshold,
        game_phase_suppress_opening=cfg.game_phase_suppress_opening,
        prev_game_phase=prev_game_phase,
    )

    sections: list[dict] = []

    # 1. System instruction
    if cfg.include_system:
        system = (
            f"You are a chess commentator. Our side: {Our_Side}. "
            f"{color_who_played.capitalize()} just played this move. "
            f"Rephrase the Context below into exactly 3 commentary sentences. Stick to what the Context states. "
            f"Output only the 3 sentences. Do not write 'Okay', 'Here is', 'Sure' or any preamble. Do not add closing remarks."
        )
        sections.append({"label": "System instruction", "content": system})

    # 2. Last move + quality
    if cfg.include_last_move:
        verb_played = verbalize_san(played, color_who_played, board_before) if played else "(none)"
        quality_word = _tiny_quality(played, best_san, result.score_cp, eval_loss) if played else ""
        content = f"{verb_played} ({quality_word})." if quality_word else verb_played
        sections.append({"label": "Last move", "content": content})

    # 3. Eval change
    if cfg.include_eval_change:
        curr_eval_str = verbalize_eval(curr_eval_cp, curr_eval_mate, our_side)
        if played and best_san and played == best_san:
            # Best move played — delta is unreliable (depth variation); show only absolute.
            content = f"position is {curr_eval_str}."
        else:
            delta_str = verbalize_eval_delta(prev_eval_cp, curr_eval_cp, our_side)
            if delta_str == "no significant change":
                # Combining "no change" with a severe absolute eval is contradictory.
                content = f"position is {curr_eval_str}."
            else:
                content = f"{delta_str} — position is {curr_eval_str}."
        sections.append({"label": "Eval change", "content": content})

    # 4. Engine recommendation
    if cfg.include_engine_recommendation and played and best_san:
        opponent = "black" if color_who_played == "white" else "white"
        if played == best_san:
            engine_content = "This matched the engine's top choice."
        else:
            # Check whether best_san is a legal move for the player who just moved.
            # If not, the engine data contains the opponent's best reply instead.
            # Default to False (opponent's response): when board_before is None we have
            # no position to validate against, and the engine's best_move_san comes from
            # the current position (side_to_move = opponent), so it is their move, not
            # an alternative for the player who just moved.
            is_player_move = False
            if board_before:
                try:
                    board_before.parse_san(best_san)
                    is_player_move = True
                except Exception:
                    is_player_move = False

            if is_player_move:
                verb_best = verbalize_san(best_san, color_who_played, board_before)
                engine_content = f"{verb_best} would have been stronger."
            else:
                # Verbalize as opponent's best response, not a player alternative.
                verb_reply = verbalize_san(best_san, opponent, board_before)
                engine_content = f"Engine's best reply for {opponent.capitalize()}: {verb_reply}."

        sections.append({"label": "Engine recommendation", "content": engine_content})

    # 5. Continuation (PV)
    if cfg.include_pv_continuation:
        pv_fn = verbalize_pv_verbose if cfg.max_tokens >= 400 else verbalize_pv
        pv_str = pv_fn(result.pv_san, result.side_to_move)
        if pv_str:
            sections.append({"label": "Continuation", "content": pv_str + "."})

    # ── Alexander eval sections ────────────────────────────────────────────────

    # ── Alexander eval sections — all gated by config flag AND anomaly switch ──

    # game_phase: suppressed in Opening when game_phase_suppress_opening=True
    if cfg.include_game_phase and ev.game_phase and anomaly.show_game_phase:
        sections.append({"label": "Game phase", "content": ev.game_phase})

    # Phase transition remark — no config flag: always emitted when the phase changes
    if anomaly.phase_transition_remark:
        sections.append({"label": "Phase transition", "content": anomaly.phase_transition_remark})

    # score_table: shown only when eval jumped enough
    if cfg.include_score_table and anomaly.show_score_table:
        score_line = render_score_table_verbose(ev) if cfg.max_tokens >= 400 else render_score_table(ev)
        if score_line:
            sections.append({"label": "Score breakdown", "content": score_line})

    # pawn_structure: shown only when ≥1 side has significant weaknesses
    if cfg.include_pawn_structure and anomaly.show_pawn_structure:
        pawn_line = render_pawn_structure_verbose(ev) if cfg.max_tokens >= 400 else render_pawn_structure(ev)
        if pawn_line:
            sections.append({"label": "Pawn structure", "content": pawn_line})

    # space: shown only when there is a meaningful space imbalance
    if cfg.include_space and anomaly.show_space:
        space_line = render_space_verbose(ev) if cfg.max_tokens >= 400 else render_space(ev)
        if space_line:
            sections.append({"label": "Space", "content": space_line})

    # mobility: shown only when one side is clearly more active
    if cfg.include_mobility and anomaly.show_mobility:
        mob_line = render_mobility(ev)
        if mob_line:
            sections.append({"label": "Mobility", "content": mob_line})

    # makogonov: suppressed during Opening phase (pieces not yet deployed)
    if cfg.include_makogonov and anomaly.show_makogonov:
        mak_line = render_makogonov_verbose(ev) if cfg.max_tokens >= 400 else render_makogonov(ev)
        if mak_line:
            sections.append({"label": "Makogonov", "content": mak_line})

    # Structural anomaly summary (auto-generated; always included when non-empty)
    if anomaly.anomaly_summary:
        sections.append({"label": "Structural alerts", "content": anomaly.anomaly_summary})

    # ── Opening book ──────────────────────────────────────────────────────────

    if cfg.include_opening_name:
        ob_entry = _ob_lookup(result.game_uci) if result.game_uci else None
        if ob_entry:
            sections.append({"label": "Opening", "content": ob_entry.name})

    # ── Theory ────────────────────────────────────────────────────────────────

    if cfg.include_theory:
        theory = ""
        quality_word = _tiny_quality(played, best_san, result.score_cp, eval_loss) if played else None
        opening_theory = retrieve_opening_theory(result, move_quality=quality_word)
        if opening_theory:
            # Opening-book theory is always trusted — no relevance gate needed.
            theory = opening_theory[:cfg.theory_max_chars]
        else:
            # BM25 fallback: gate on normalized relevance score so generic chunks
            # that don't relate to the current position are suppressed.
            chunks_scored = retrieve_with_score(
                result, question_type,
                top_k=cfg.theory_chunks,
                played_move=played or None,
                extra_tokens=anomaly.anomaly_tokens,
            )
            if chunks_scored:
                text, score = chunks_scored[0]
                if score >= cfg.theory_relevance_threshold:
                    theory = text

        if theory:
            sections.append({"label": "Theory", "content": theory})

    if cfg.include_question:
        sections.append({"label": "Question", "content": question_text})

    return sections


def _derive_focus(by_label: dict) -> str:
    """
    Return the single most important point for the model to address.

    Priority order:
    1. Structural alerts from anomaly_detector (most specific and positional)
    2. Move quality (blunder/mistake/inaccuracy) → explain the error
    3. Phase transition (notable game-state event)
    """
    alerts = by_label.get("Structural alerts", "")
    if alerts:
        return alerts.removeprefix("Structural alerts: ")

    last_move = by_label.get("Last move", "").lower()
    engine_rec = by_label.get("Engine recommendation", "")
    matched = "matched" in engine_rec.lower()
    for quality in ("blunder", "mistake", "inaccuracy"):
        if quality in last_move:
            article = "an" if quality == "inaccuracy" else "a"
            if engine_rec and not matched:
                return f"This was {article} {quality}. {engine_rec}"
            return f"This was {article} {quality} — explain what went wrong."

    phase_trans = by_label.get("Phase transition", "")
    if phase_trans:
        return phase_trans

    return ""


def _merge_engine_block(engine_rec: str, continuation: str) -> str:
    """
    Merge engine recommendation + PV continuation into one prose sentence.

    Avoids repeating the best-move name that already appears in both inputs:
    for the "stronger" case, strips the first move token from the continuation
    (it duplicates the rec) and keeps only the "after …" tail.
    For the "matched" case, keeps the full continuation as the plan detail.
    """
    if not engine_rec and not continuation:
        return ""
    if not continuation:
        return engine_rec
    if not engine_rec:
        return continuation

    # Strip "Engine plans: " prefix
    cont_body = continuation
    if cont_body.lower().startswith("engine plans:"):
        cont_body = cont_body[len("engine plans:"):].strip()
    cont_body = cont_body.rstrip(".")

    rec_stripped = engine_rec.rstrip(".")

    if "matched" in engine_rec.lower():
        # e.g. "This matched … — planning knight to f3 — after pawn to e5."
        return f"{rec_stripped} — planning {cont_body}."
    else:
        # cont_body: "bishop to c4 — after pawn to e5, then knight to f3"
        # Drop the first segment (repeats the rec move); keep the "after …" tail.
        if " — " in cont_body:
            _, tail = cont_body.split(" — ", 1)
            return f"{rec_stripped} — {tail}."
        # No tail (single-move PV): just append the continuation as-is.
        return f"{rec_stripped} — {cont_body}."


def _render_prose_prompt(sections: list[dict]) -> str:
    """
    Convert labeled sections into explicit labeled lines + Focus directive + Task.

    Each game event gets its own labeled line so 0.6B models cannot confuse
    the played move with the engine recommendation or PV continuation.

    Format:
        Played: <move> (<quality>) — <eval delta> — position is <eval>.
        Engine: <rec> — after <pv tail>.   (or "Matched. Engine line: <pv>.")
        Opening: <name> — <phase>.
        Position: <structural alerts / score / pawn / space / mobility>.
        Background: <theory first sentence>.

        Focus: <single most important point>

        Task: <question>
    """
    by_label = {s["label"]: s["content"] for s in sections}
    lines: list[str] = []

    # System instruction
    if "System instruction" in by_label:
        lines.append(by_label["System instruction"])
        lines.append("")

    # ── Played move (own line) ────────────────────────────────────────────────
    last_move = by_label.get("Last move", "")
    eval_change = by_label.get("Eval change", "")
    if last_move and eval_change:
        played_line = f"Played: {last_move.rstrip('.')} — {eval_change}"
    elif last_move:
        played_line = f"Played: {last_move}"
    else:
        played_line = ""
    if played_line:
        lines.append(played_line if played_line.endswith(".") else played_line + ".")

    # ── Engine recommendation + continuation (own line) ───────────────────────
    engine_rec = by_label.get("Engine recommendation", "")
    continuation = by_label.get("Continuation", "")

    def _strip_engine_prefix(s: str) -> str:
        if s.lower().startswith("engine plans:"):
            return s[len("engine plans:"):].strip()
        return s

    if engine_rec or continuation:
        if engine_rec and "matched" in engine_rec.lower():
            # Two sub-sentences: rec + continuation on one labeled line
            rec_part = engine_rec.rstrip(".")
            if continuation:
                cont_body = _strip_engine_prefix(continuation).rstrip(".")
                engine_line = f"Engine: {rec_part}. Engine line: {cont_body}."
            else:
                engine_line = f"Engine: {rec_part}."
        elif engine_rec and continuation:
            engine_line = f"Engine: {_merge_engine_block(engine_rec, continuation)}"
        elif engine_rec:
            rec = engine_rec.rstrip(".")
            engine_line = f"Engine: {rec}."
        else:
            cont_body = _strip_engine_prefix(continuation).rstrip(".")
            engine_line = f"Engine line: {cont_body}."
        lines.append(engine_line)

    # ── Opening + phase (own line, only when present) ─────────────────────────
    opening_parts: list[str] = []
    if "Opening" in by_label:
        opening_parts.append(by_label["Opening"])
    phase_trans = by_label.get("Phase transition", "")
    game_phase = by_label.get("Game phase", "")
    if phase_trans:
        opening_parts.append(phase_trans)
    elif game_phase and game_phase.lower() != "opening":
        # "Opening" phase is already implied by the opening name; only show
        # when the phase carries new information (Middlegame, Endgame, etc.)
        opening_parts.append(game_phase)
    if opening_parts:
        op_line = " — ".join(opening_parts)
        lines.append(f"Opening: {op_line}.")

    # ── Structural / Alexander sections (own line if any present) ─────────────
    structural: list[str] = []
    for label in ("Score breakdown", "Pawn structure", "Space", "Mobility", "Makogonov"):
        val = by_label.get(label, "")
        if val:
            structural.append(val)
    if structural:
        lines.append("Position: " + "; ".join(structural) + ".")

    # ── Theory → Background (own line, first sentence only) ───────────────────
    theory_raw = by_label.get("Theory", "")
    if theory_raw:
        first_sentence = theory_raw.split(". ")[0].strip().rstrip(".")
        if first_sentence:
            lines.append(f"Background: {first_sentence}.")

    # ── Focus directive ───────────────────────────────────────────────────────
    focus = _derive_focus(by_label)
    if focus:
        lines.append("")
        lines.append(f"Focus: {focus}")

    # ── Task ──────────────────────────────────────────────────────────────────
    task = by_label.get("Question", "")
    if task:
        lines.append("")
        task_line = f"Task: {task}"
        if focus:
            task_line += " Address the Focus specifically."
        lines.append(task_line)

    return "\n".join(lines)


def build_tiny_prompt(
    result: AlexanderResult,
    prev_eval_cp: Optional[int],
    curr_eval_cp: Optional[int],
    curr_eval_mate: Optional[int],
    our_side: str,
    question_type: str,
    board_before: Optional[chess.Board] = None,
    eval_loss: Optional[int] = None,
    config: Optional[PromptConfig] = None,
    prev_game_phase: Optional[str] = None,
) -> str:
    """
    Prompt for LLM commentary (default: FULL_CONFIG, ~300 tokens with Alexander sections).

    prev_eval_cp, curr_eval_cp, curr_eval_mate: White-perspective centipawns / mate.
    our_side: "white" | "black" — which side is the human player.
    board_before: chess.Board BEFORE the played move (for capture verbalization).
    config: PromptConfig controlling which sections to include.
    prev_game_phase: game phase of the previous position (for phase transition remark).
    """
    sections = _build_tiny_sections(
        result, prev_eval_cp, curr_eval_cp, curr_eval_mate,
        our_side, question_type, board_before, eval_loss, config,
        prev_game_phase=prev_game_phase,
    )
    return _render_prose_prompt(sections)


def build_tiny_prompt_sections(
    result: AlexanderResult,
    prev_eval_cp: Optional[int],
    curr_eval_cp: Optional[int],
    curr_eval_mate: Optional[int],
    our_side: str,
    question_type: str,
    board_before: Optional[chess.Board] = None,
    eval_loss: Optional[int] = None,
    config: Optional[PromptConfig] = None,
    prev_game_phase: Optional[str] = None,
) -> list[dict]:
    """Return the prompt as labeled sections (for debug display in the UI)."""
    return _build_tiny_sections(
        result, prev_eval_cp, curr_eval_cp, curr_eval_mate,
        our_side, question_type, board_before, eval_loss, config,
        prev_game_phase=prev_game_phase,
    )
