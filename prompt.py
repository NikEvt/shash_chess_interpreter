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
    "best_move": "What is the best move and why?",
    "explain":   "Explain the current position.",
    "plan":      "What is the strategic plan for the side to move?",
}


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

    theory_chunks = retrieve(result, question, top_k=2)
    theory_text = "\n".join(f"- {chunk}" for chunk in theory_chunks)

    played = getattr(result, "played_move", None)
    played_line = f"  Move played: {played}\n" if played else ""

    return (
        f"You are a chess coach. {level_hint} "
        f"Answer the question in 2-3 sentences. Be specific — mention the best move by name.\n\n"
        f"Chess theory context:\n{theory_text}\n\n"
        f"Position info:\n"
        f"  Recent moves: {moves_str}\n"
        f"{played_line}"
        f"  Side to move: {result.side_to_move.capitalize()}\n"
        f"  Engine evaluation: {eval_text}\n"
        f"  Best move: {result.best_move_san}\n"
        f"  Position style: {prompt_description(result.shashin_type)}\n\n"
        f"Question: {question_text}"
    )
