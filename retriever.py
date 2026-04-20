"""
BM25-based retriever over the chess theory knowledge base.
No embeddings, no neural networks — pure keyword matching.
~1 MB RAM, instantaneous retrieval.
"""
from __future__ import annotations

from rank_bm25 import BM25Okapi

from mamka.shash_chess_interpreter.knowledge_base import CHUNKS
from mamka.shash_chess_interpreter.mock_engine import EngineResult

# ── Index (built once at import time) ─────────────────────────────────────────

_tokenized = [chunk["text"].lower().split() for chunk in CHUNKS]
_bm25 = BM25Okapi(_tokenized)


# ── Query construction ─────────────────────────────────────────────────────────

_QUESTION_KEYWORDS = {
    "best_move": "best move plan tactics",
    "explain":   "explain position evaluation advantage",
    "plan":      "strategic plan strategy long-term",
}

_SHASHIN_KEYWORDS = {
    "Capablanca": "strategic positional balanced open file weak square outpost plan",
    "Tal":        "tactical attack sacrifice king safety kingside initiative",
    "Petrosian":  "defensive prophylaxis exchange blockade fortress solid draw",
}

_PHASE_KEYWORDS = {
    "opening":   "opening development center castle",
    "middlegame": "plan strategy middlegame attack",
    "endgame":   "endgame king pawn promotion rook",
}


def _position_phase(result: EngineResult) -> str:
    fen_board = result.fen.split()[0]
    piece_count = sum(1 for c in fen_board if c.isalpha())
    if piece_count >= 28:
        return "opening"
    if piece_count <= 14:
        return "endgame"
    return "middlegame"


def _build_query(result: EngineResult, question: str, played_move: str | None = None) -> list[str]:
    tokens: list[str] = []
    tokens += _QUESTION_KEYWORDS.get(question, "").split()
    tokens += _SHASHIN_KEYWORDS.get(result.shashin_type, "").split()
    tokens += _PHASE_KEYWORDS[_position_phase(result)].split()
    if result.mate_in is not None:
        tokens += ["tactics", "checkmate", "forced"]
    if played_move and played_move != result.best_move_san:
        tokens += ["mistake", "inaccuracy", "alternative", "better"]
    return tokens


# ── Public API ─────────────────────────────────────────────────────────────────

def retrieve(result: EngineResult, question: str, top_k: int = 2, played_move: str | None = None) -> list[str]:
    """Return top_k theory chunks most relevant to the position and question."""
    query = _build_query(result, question, played_move=played_move)
    scores = _bm25.get_scores(query)
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return [CHUNKS[i]["text"] for i in ranked[:top_k]]
