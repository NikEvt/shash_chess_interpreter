"""
Tests for the opening book lookup and BM25 retriever.

Run with:
    python3.12 -m pytest tests/test_retriever.py -v
    # or from repo root:
    python3.12 -m pytest tests/ -v
"""
from __future__ import annotations

import sys
import pathlib

# Make sure repo root is on the path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest
from alexander_interpreter.opening_book import lookup, book_size, eco_family_tokens
from alexander_interpreter.retriever import retrieve, retrieve_opening_theory, _position_phase
from alexander_interpreter.types import AlexanderResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_result(
    fen: str,
    game_uci: str = "",
    shashin_zone: int = 7,
    score_cp: int = 0,
) -> AlexanderResult:
    """Minimal AlexanderResult for retriever tests (no engine needed)."""
    return AlexanderResult(
        fen=fen,
        side_to_move="white",
        played_move=None,
        best_move_uci="e2e4",
        best_move_san="e4",
        score_cp=score_cp,
        mate_in=None,
        wdl_win=333,
        wdl_draw=334,
        wdl_loss=333,
        shashin_zone=shashin_zone,
        top_moves=[],
        pv_san=[],
        depth=18,
        game_uci=game_uci or None,
    )


STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# FEN after 1.Nh3 d5 2.g3 e5 3.f4  (Amar Paris Gambit — all 32 pieces)
PARIS_GAMBIT_FEN = "rnbqkbnr/ppp2ppp/8/3pp3/5P2/6PN/PPPPP2P/RNBQKB1R b KQkq - 0 3"
PARIS_GAMBIT_UCI = "g1h3 d7d5 g2g3 e7e5 f2f4"

# FEN in a typical middlegame — 26 pieces (< 28 threshold), some exchanges done
MIDDLEGAME_FEN = "r1bq1rk1/pp3ppp/2n2n2/3p4/3P4/2N2N2/PP3PPP/R1BQ1RK1 w - - 0 10"

# FEN in a late endgame (~8 pieces)
ENDGAME_FEN = "8/8/4k3/4p3/4P3/4K3/8/8 w - - 0 1"


# ── Opening book: book_size ────────────────────────────────────────────────────

def test_book_loaded():
    assert book_size() > 0, "Opening book must not be empty"


# ── Opening book: exact match ─────────────────────────────────────────────────

def test_lookup_exact_paris_gambit():
    e = lookup(PARIS_GAMBIT_UCI)
    assert e is not None
    assert "Paris Gambit" in e.name
    assert e.eco == "A00"
    assert e.text  # must have theory text


def test_lookup_exact_nh3_only():
    e = lookup("g1h3")
    assert e is not None
    assert "Amar Opening" in e.name


# ── Opening book: prefix matching (the main fix) ──────────────────────────────

def test_lookup_prefix_intermediate_position():
    """After g3 (3 half-moves into the Paris Gambit), should still find Amar Opening."""
    e = lookup("g1h3 d7d5 g2g3")
    assert e is not None
    assert "Amar" in e.name


def test_lookup_prefix_after_opening_ends():
    """After Bxh3 (move 6, past the Paris Gambit terminal), should return Paris Gambit."""
    e = lookup("g1h3 d7d5 g2g3 e7e5 f2f4 c8h3")
    assert e is not None
    assert "Paris Gambit" in e.name


def test_lookup_prefix_gent_gambit_full_line():
    """Full Gent Gambit line should match the Gent Gambit entry (deeper than Paris)."""
    gent_uci = "g1h3 d7d5 g2g3 e7e5 f2f4 c8h3 f1h3 e5f4 e1g1 f4g3 h2g3"
    e = lookup(gent_uci)
    assert e is not None
    assert "Gent" in e.name


def test_lookup_prefix_prefers_deepest_match():
    """When multiple prefixes match, return the longest (most specific) one."""
    # After 7 moves of the Gent line we still have Paris Gambit (5 moves) AND
    # Amar Opening (1 move) as candidates — must pick Paris Gambit (longer).
    e = lookup("g1h3 d7d5 g2g3 e7e5 f2f4 c8h3 f1h3")
    assert e is not None
    assert "Paris Gambit" in e.name, f"Expected Paris Gambit, got {e.name}"


def test_lookup_unknown_returns_none_or_fallback():
    """A made-up position has no book match."""
    e = lookup("a2a4 a7a5 b2b4 b7b5 c2c4 c7c5 d2d4 d7d5 e2e4 e7e5 f2f4 f7f5")
    # Either None (no match at any prefix) or a very generic 1-move entry is ok.
    # The important thing: it must not crash.
    assert e is None or isinstance(e.name, str)


def test_lookup_empty_string():
    assert lookup("") is None


def test_lookup_whitespace_only():
    assert lookup("   ") is None


# ── eco_family_tokens ─────────────────────────────────────────────────────────

def test_eco_tokens_a00():
    tokens = eco_family_tokens("A00")
    assert tokens  # not empty


def test_eco_tokens_b20_range():
    tokens = eco_family_tokens("B45")
    assert "sicilian" in tokens.lower()


def test_eco_tokens_empty():
    assert eco_family_tokens("") == ""


# ── retriever: _position_phase ────────────────────────────────────────────────

def test_phase_opening():
    r = make_result(STARTING_FEN)
    assert _position_phase(r) == "opening"


def test_phase_opening_paris_gambit():
    r = make_result(PARIS_GAMBIT_FEN)
    assert _position_phase(r) == "opening"


def test_phase_middlegame():
    r = make_result(MIDDLEGAME_FEN)
    assert _position_phase(r) == "middlegame"


def test_phase_endgame():
    r = make_result(ENDGAME_FEN)
    assert _position_phase(r) == "endgame"


# ── retrieve_opening_theory ───────────────────────────────────────────────────

def test_opening_theory_paris_gambit_exact():
    """After exactly 5 moves, must return Paris Gambit theory."""
    r = make_result(PARIS_GAMBIT_FEN, game_uci=PARIS_GAMBIT_UCI)
    theory = retrieve_opening_theory(r)
    assert theory is not None
    assert "Paris Gambit" in theory or "Amar" in theory or "f4" in theory


def test_opening_theory_prefix_after_opening():
    """After move 6 (Bxh3), must still return opening book theory (not None)."""
    r = make_result(PARIS_GAMBIT_FEN, game_uci="g1h3 d7d5 g2g3 e7e5 f2f4 c8h3")
    theory = retrieve_opening_theory(r)
    assert theory is not None, "Should return Paris Gambit theory even after 6th move"


def test_opening_theory_middlegame_returns_none():
    """Middlegame position → opening theory must not be returned."""
    r = make_result(MIDDLEGAME_FEN, game_uci="e2e4 e7e5 g1f3 b8c6 f1c4 f8c5")
    theory = retrieve_opening_theory(r)
    assert theory is None, "Middlegame position should never return opening theory"


def test_opening_theory_no_game_uci():
    """If game_uci is empty/None, must return None gracefully."""
    r = make_result(PARIS_GAMBIT_FEN, game_uci="")
    theory = retrieve_opening_theory(r)
    assert theory is None


# ── retrieve (BM25) ───────────────────────────────────────────────────────────

def test_retrieve_returns_list():
    r = make_result(MIDDLEGAME_FEN)
    chunks = retrieve(r, "best_move", top_k=2)
    assert isinstance(chunks, list)
    assert len(chunks) <= 2


def test_retrieve_top_k_respected():
    r = make_result(MIDDLEGAME_FEN)
    for k in (1, 2, 3):
        chunks = retrieve(r, "explain", top_k=k)
        assert len(chunks) <= k


def test_retrieve_non_empty_chunks():
    r = make_result(MIDDLEGAME_FEN)
    chunks = retrieve(r, "plan", top_k=1)
    assert chunks
    assert all(isinstance(c, str) and len(c) > 0 for c in chunks)


def test_retrieve_endgame_position():
    r = make_result(ENDGAME_FEN)
    chunks = retrieve(r, "plan", top_k=1)
    assert chunks


def test_retrieve_with_played_move_blunder():
    """Blunder scenario: played move != best move with large cp difference."""
    r = make_result(MIDDLEGAME_FEN, score_cp=300)
    r = r.__class__(
        **{**r.__dict__,
           "best_move_san": "Nf3",
           "played_move": "Nd2",
           "score_cp": 300}
    )
    chunks = retrieve(r, "best_move", top_k=1, played_move="Nd2")
    assert chunks
