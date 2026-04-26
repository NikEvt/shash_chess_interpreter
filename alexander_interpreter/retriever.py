"""
BM25-based retriever over the chess theory knowledge base.
Adapted for AlexanderResult: uses 14-zone Shashin keywords and eval trace hints.
"""
from __future__ import annotations

from rank_bm25 import BM25Okapi

from .knowledge_base import CHUNKS
from .types import AlexanderResult
from . import shashin as shashin_mod

# ── Index (built once at import time) ─────────────────────────────────────────

_tokenized = [chunk["text"].lower().split() for chunk in CHUNKS]
_bm25 = BM25Okapi(_tokenized)


# ── Query construction ─────────────────────────────────────────────────────────

_QUESTION_KEYWORDS: dict[str, str] = {
    "best_move": "best move plan tactics forcing",
    "explain":   "explain position evaluation advantage disadvantage",
    "plan":      "strategic plan strategy long-term",
}

_PHASE_KEYWORDS: dict[str, str] = {
    "opening":    "opening development center castle",
    "middlegame": "plan strategy middlegame attack",
    "endgame":    "endgame king pawn promotion rook",
}

_EVAL_COMPONENT_KEYWORDS: dict[str, str] = {
    "mobility":     "piece activity mobility outpost coordination",
    "king_safety":  "king attack defense shelter pawn",
    "pawns":        "pawn structure weakness passed pawn",
    "threats":      "threat tactical attack fork pin",
    "passed_pawns": "passed pawn advance promotion rook",
}


def _position_phase(result: AlexanderResult) -> str:
    fen_board = result.fen.split()[0]
    piece_count = sum(1 for c in fen_board if c.isalpha())
    if piece_count >= 28:
        return "opening"
    if piece_count <= 14:
        return "endgame"
    return "middlegame"


def _build_query(
    result: AlexanderResult,
    question: str,
    played_move: str | None = None,
) -> list[str]:
    tokens: list[str] = []

    # Question type keywords
    tokens += _QUESTION_KEYWORDS.get(question, "").split()

    # Shashin zone keywords (14-zone, more specific than 3-category)
    tokens += shashin_mod.retriever_keywords(result.shashin_zone).split()

    # Position phase
    tokens += _PHASE_KEYWORDS[_position_phase(result)].split()

    # Mate
    if result.mate_in is not None:
        tokens += ["tactics", "checkmate", "forced", "combination"]

    # Move quality
    if played_move and played_move != result.best_move_san:
        tokens += ["mistake", "inaccuracy", "alternative", "better"]

    # Eval trace hints (use the most significant components)
    if result.eval_trace:
        factors = result.eval_trace.significant_factors(threshold=0.2)
        for name, _ in factors[:2]:
            key = name.replace(" ", "_")
            tokens += _EVAL_COMPONENT_KEYWORDS.get(key, "").split()

    # WDL-based tactical vs strategic hint
    if result.win_pct > 79 or result.loss_pct > 79:
        tokens += ["tactics", "forcing", "decisive"]
    elif 40 <= result.win_pct <= 60:
        tokens += ["strategic", "plan", "positional"]

    return tokens


# ── Public API ─────────────────────────────────────────────────────────────────

def retrieve(
    result: AlexanderResult,
    question: str,
    top_k: int = 2,
    played_move: str | None = None,
) -> list[str]:
    """Return top_k theory chunks most relevant to the position and question."""
    query = _build_query(result, question, played_move=played_move)
    scores = _bm25.get_scores(query)
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return [CHUNKS[i]["text"] for i in ranked[:top_k]]
