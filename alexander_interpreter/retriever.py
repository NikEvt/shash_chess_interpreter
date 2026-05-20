"""
BM25-based retriever over the chess theory knowledge base.
Adapted for AlexanderResult: uses 14-zone Shashin keywords and eval trace hints.
"""
from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from .knowledge_base import CHUNKS
from .types import AlexanderResult
from . import shashin as shashin_mod
from .opening_book import lookup as _ob_lookup, lookup_with_depth as _ob_lookup_with_depth, eco_family_tokens as _eco_tokens

# ── Index (built once at import time) ─────────────────────────────────────────

def _build_index_text(chunk: dict) -> str:
    """Prepend tags to text so zone/style tags influence BM25 scoring."""
    return " ".join(chunk.get("tags", [])) + " " + chunk["text"]

_tokenized = [_build_index_text(chunk).lower().split() for chunk in CHUNKS]
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
    extra_tokens: list[str] | None = None,
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

    # Move quality — map centipawn delta to semantic synonyms for better retrieval
    if played_move and played_move != result.best_move_san:
        cp = abs(result.score_cp) if result.score_cp is not None else None
        if cp is None or cp <= 100:
            tokens += ["missed", "opportunity", "positional"]       # inaccuracy
        elif cp <= 200:
            tokens += ["error", "alternative", "better", "plan"]    # mistake
        else:
            tokens += ["tactical", "error", "decisive", "losing"]   # blunder

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

    # Opening book: inject ECO family tokens to improve BM25 retrieval.
    # Inject whenever the game came from a known opening (opening + early middlegame).
    # In deep opening, also add opening name tokens for more specific retrieval.
    if result.game_uci:
        entry, match_depth = _ob_lookup_with_depth(result.game_uci)
        if entry:
            tokens += _eco_tokens(entry.eco).split()
            game_length = len(result.game_uci.split())
            if game_length - match_depth <= 6:
                tokens += [w.lower() for w in entry.name.split()[:4] if len(w) > 3]

    # Structural anomaly tokens from detect_anomalies() (passivity, king safety, etc.)
    if extra_tokens:
        tokens += extra_tokens

    # Strip centipawn scores, WDL numbers, and square coordinates (e4, c6 etc.)
    tokens = [
        t for t in tokens
        if not re.match(r'^[a-h][1-8]$', t) and not t[0].isdigit()
    ]

    return tokens


# ── Public API ─────────────────────────────────────────────────────────────────

def retrieve(
    result: AlexanderResult,
    question: str,
    top_k: int = 2,
    played_move: str | None = None,
    extra_tokens: list[str] | None = None,
) -> list[str]:
    """Return top_k theory chunks most relevant to the position and question."""
    query = _build_query(result, question, played_move=played_move, extra_tokens=extra_tokens)
    scores = _bm25.get_scores(query)
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return [CHUNKS[i]["text"] for i in ranked[:top_k]]


def retrieve_opening_theory(result: AlexanderResult) -> str | None:
    """
    Return opening-specific theory from book if the game is still close to a book line.
    Returns None when the game has deviated more than 4 half-moves from any book entry
    (i.e. we are in the middlegame or the game left theory early).
    """
    if not result.game_uci:
        return None

    game_length = len(result.game_uci.split())
    entry, match_depth = _ob_lookup_with_depth(result.game_uci)
    if not entry:
        return None

    # If the game has moved more than 4 half-moves past the deepest book entry,
    # the position is out of theory — hand off to BM25 knowledge base.
    if game_length - match_depth > 4:
        return None

    # Return only the theory text — name/ECO are shown separately via include_opening_name
    return entry.text if entry.text else None
