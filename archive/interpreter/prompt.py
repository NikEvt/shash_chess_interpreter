"""
Builds a minimal, information-dense prompt for qwen3-0.6b.
The model cannot play chess — it interprets structured engine data + retrieved theory.
FEN is intentionally excluded: the model cannot parse it and it causes confusion.
"""
from mock_engine import EngineResult
from retriever import retrieve
from shashin import prompt_description

LEVEL_INSTRUCTIONS = {
    "beginner":     "Use simple language, avoid chess jargon.",
    "intermediate": "Brief technical terms are fine.",
    "advanced":     "Use chess terminology freely.",
}

QUESTION_TEMPLATES = {
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


def _move_quality_label(played: str, best_san: str, score_cp: int | None) -> str:
    if played == best_san:
        return "best move"
    if score_cp is None:
        return "alternative"
    delta = abs(score_cp)
    if delta < 20:
        return "excellent"
    if delta < 50:
        return "good"
    if delta < 100:
        return "inaccuracy"
    if delta < 200:
        return "mistake"
    return "blunder"


def _eval_str(r: EngineResult) -> str:
    if r.mate_in is not None:
        return f"Forced checkmate in {r.mate_in} move{'s' if r.mate_in != 1 else ''}"
    sign = "+" if r.score_cp >= 0 else ""
    pawns = r.score_cp / 100
    win_pct = round(r.wdl_win / 10)
    draw_pct = round(r.wdl_draw / 10)
    side = "White" if r.score_cp >= 0 else "Black"
    return f"{side} is better by {sign}{pawns:.1f} pawns ({win_pct}% win, {draw_pct}% draw)"


def build_prompt(
    result: EngineResult,
    moves_history: list[str],
    level: str,
    question: str,
) -> str:
    eval_text = _eval_str(result)
    moves_str = " ".join(moves_history[-5:]) if moves_history else "none"
    level_hint = LEVEL_INSTRUCTIONS.get(level, LEVEL_INSTRUCTIONS["intermediate"])
    question_text = QUESTION_TEMPLATES.get(question, question)

    played = getattr(result, "played_move", None)
    theory_chunks = retrieve(result, question, top_k=2, played_move=played)
    theory_text = "\n".join(f"- {chunk}" for chunk in theory_chunks)

    played_line = f"  Move played: {played}\n" if played else ""
    quality_label = _move_quality_label(played, result.best_move_san, result.score_cp) if played else None
    quality_line = f"  Move quality: {quality_label}\n" if quality_label else ""

    if played and played != result.best_move_san:
        comparison_block = (
            f"  Move comparison: The game continued with {played}, "
            f"but the engine recommends {result.best_move_san} as stronger. "
            f"In your answer, explain WHY {result.best_move_san} is better than {played}.\n"
        )
    elif played:
        comparison_block = (
            f"  Move comparison: The move played ({played}) matches the engine's best move. "
            f"Explain what makes it the strongest choice.\n"
        )
    else:
        comparison_block = ""

    return (
        f"You are a chess coach. {level_hint} "
        f"Answer the question in 2-3 sentences. Be specific — mention the best move by name.\n\n"
        f"Chess theory context:\n{theory_text}\n\n"
        f"Position info:\n"
        f"  Recent moves: {moves_str}\n"
        f"{played_line}"
        f"{quality_line}"
        f"  Side to move: {result.side_to_move.capitalize()}\n"
        f"  Engine evaluation: {eval_text}\n"
        f"  Best move: {result.best_move_san}\n"
        f"  Position style: {prompt_description(result.shashin_type)}\n"
        f"{comparison_block}"
        f"\nQuestion: {question_text}"
    )
