def quality_from_loss(loss_cp: int) -> str:
    if loss_cp <= 5:   return "best"
    if loss_cp <= 20:  return "excellent"
    if loss_cp <= 50:  return "good"
    if loss_cp <= 100: return "inaccuracy"
    if loss_cp <= 200: return "mistake"
    return "blunder"


def auto_level(score_cp: int | None, mate_in: int | None) -> str:
    if mate_in is not None:          return "intermediate"
    if score_cp is None:             return "beginner"
    if abs(score_cp) > 300:          return "advanced"
    if abs(score_cp) > 100:          return "intermediate"
    return "beginner"


def auto_question(
    score_cp: int | None,
    mate_in: int | None,
    shashin_zone: str,
    played_move: str | None,
    best_move_san: str | None,
    eval_loss: int | None = None,
) -> str:
    if mate_in is not None:
        return "best_move"
    # Only ask "what was the mistake" when the move was actually a real error (> 50 cp loss).
    # Small divergences from the engine's top choice are stylistic, not mistakes.
    if played_move and best_move_san and played_move != best_move_san:
        if eval_loss is None or eval_loss > 50:
            return "best_move"
    if "PETROSIAN" in shashin_zone:
        return "plan"
    if "TAL" in shashin_zone:
        # Only ask "best move" in TAL when there's a real alternative to discuss
        if played_move and best_move_san and played_move != best_move_san:
            return "best_move"
    return "explain"
