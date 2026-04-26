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

from dataclasses import dataclass
from typing import Optional

import chess

from .types import AlexanderResult
from .retriever import retrieve
from . import shashin as shashin_mod
from .verbalizer import (
    verbalize_san,
    verbalize_pv,
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
)


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

    # Theory (BM25 retrieval)
    include_theory: bool = True
    theory_chunks: int = 1


# Default configs for common use cases
COMPACT_CONFIG = PromptConfig(
    max_tokens=300,
    include_score_table=False,
    include_space=False,
    include_makogonov=False,
)

FULL_CONFIG = PromptConfig(max_tokens=600)

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
        return "alternative"
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
    theory_chunks = retrieve(result, question, top_k=2, played_move=played)
    theory_text = "\n".join(f"- {chunk}" for chunk in theory_chunks) or "(none)"

    moves_str = " ".join(moves_history[-6:]) if moves_history else "none"

    zone_lbl = shashin_mod.zone_label(result.shashin_zone)
    zone_desc = shashin_mod.prompt_description(result.shashin_zone)
    zone_win_range = shashin_mod.win_range(result.shashin_zone)

    quality_label = _move_quality_label(played or "", result.best_move_san, result.score_cp, eval_loss) if played else None

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
}

_QUESTION_TEXTS: dict[str, str] = {
    "best_move": (
        "Why was the last move a mistake and what would the engine recommendation have accomplished?"
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
) -> list[dict]:
    """
    Internal builder — returns labeled sections for the tiny prompt.
    All eval inputs are from White's perspective (positive = good for White).
    Alexander-specific sections are gated by config flags.
    """
    cfg = config or FULL_CONFIG
    Our_Side = our_side.capitalize()
    played = result.played_move or ""
    color = result.side_to_move  # who just moved (produced this position)
    best_san = result.best_move_san or ""
    question_text = _QUESTION_TEXTS.get(question_type, _QUESTION_TEXTS["explain"])

    # Parse Alexander eval sections (no-op if raw_eval_lines is empty)
    ev = parse_eval_sections(result.raw_eval_lines)

    sections: list[dict] = []

    # 1. System instruction
    if cfg.include_system:
        system = (
            f"You are a chess commentator. Our side: {Our_Side}. "
            f"Write exactly 2 sentences. "
            f"Use only the facts below. Do not invent moves or evaluations."
        )
        sections.append({"label": "System instruction", "content": system})

    # 2. Last move + quality
    if cfg.include_last_move:
        verb_played = verbalize_san(played, color, board_before) if played else "(none)"
        quality_word = _tiny_quality(played, best_san, result.score_cp, eval_loss) if played else ""
        content = f"{verb_played} ({quality_word})." if quality_word else verb_played
        sections.append({"label": "Last move", "content": content})

    # 3. Eval change
    if cfg.include_eval_change:
        delta_str = verbalize_eval_delta(prev_eval_cp, curr_eval_cp, our_side)
        curr_eval_str = verbalize_eval(curr_eval_cp, curr_eval_mate, our_side)
        sections.append({"label": "Eval change", "content": f"{delta_str} — position is now {curr_eval_str}."})

    # 4. Engine recommendation
    if cfg.include_engine_recommendation and played and best_san:
        if played == best_san:
            engine_content = "This matched the engine's top choice."
        else:
            verb_best = verbalize_san(best_san, color, board_before)
            engine_content = f"{verb_best} would have been stronger."
        sections.append({"label": "Engine recommendation", "content": engine_content})

    # 5. Continuation (PV)
    if cfg.include_pv_continuation:
        pv_str = verbalize_pv(result.pv_san, result.side_to_move)
        if pv_str:
            sections.append({"label": "Continuation", "content": pv_str + "."})

    # ── Alexander eval sections ────────────────────────────────────────────────

    if cfg.include_game_phase and ev.game_phase:
        sections.append({"label": "Game phase", "content": ev.game_phase})

    if cfg.include_score_table:
        score_line = render_score_table(ev)
        if score_line:
            sections.append({"label": "Score breakdown", "content": score_line})

    if cfg.include_pawn_structure:
        pawn_line = render_pawn_structure(ev)
        if pawn_line:
            sections.append({"label": "Pawn structure", "content": pawn_line})

    if cfg.include_space:
        space_line = render_space(ev)
        if space_line:
            sections.append({"label": "Space", "content": space_line})

    if cfg.include_mobility:
        mob_line = render_mobility(ev)
        if mob_line:
            sections.append({"label": "Mobility", "content": mob_line})

    if cfg.include_makogonov:
        mak_line = render_makogonov(ev)
        if mak_line:
            sections.append({"label": "Makogonov", "content": mak_line})

    # ── Theory ────────────────────────────────────────────────────────────────

    if cfg.include_theory:
        theory_chunks = retrieve(result, question_type, top_k=cfg.theory_chunks, played_move=played or None)
        theory = theory_chunks[0] if theory_chunks else ""
        if theory:
            sections.append({"label": "Theory", "content": theory})

    if cfg.include_question:
        sections.append({"label": "Question", "content": question_text})

    return sections


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
) -> str:
    """
    Prompt for LLM commentary (default: FULL_CONFIG, ~300 tokens with Alexander sections).

    prev_eval_cp, curr_eval_cp, curr_eval_mate: White-perspective centipawns / mate.
    our_side: "white" | "black" — which side is the human player.
    board_before: chess.Board BEFORE the played move (for capture verbalization).
    config: PromptConfig controlling which sections to include.
    """
    sections = _build_tiny_sections(
        result, prev_eval_cp, curr_eval_cp, curr_eval_mate,
        our_side, question_type, board_before, eval_loss, config,
    )

    print("DEBUG prompts: played move:", result.played_move)
    print("DEBUG prompts: side to move:", result.side_to_move)
    print("DEBUG prompts: our_side:", our_side)

    # System instruction is always first if present
    if sections and sections[0]["label"] == "System instruction":
        system_content = sections[0]["content"]
        body = sections[1:]
    else:
        system_content = ""
        body = sections

    lines = []
    if system_content:
        lines += [system_content, ""]
    for s in body:
        key = s["label"].upper().replace(" ", "_")
        lines.append(f"{key}: {s['content']}")
    return "\n".join(lines)


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
) -> list[dict]:
    """Return the prompt as labeled sections (for debug display in the UI)."""
    return _build_tiny_sections(
        result, prev_eval_cp, curr_eval_cp, curr_eval_mate,
        our_side, question_type, board_before, eval_loss, config,
    )
