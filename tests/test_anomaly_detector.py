"""
Tests for anomaly_detector.detect_anomalies():
  - Score table gate (eval jump threshold)
  - Makogonov phase gate
  - Structural anomaly token generation
  - Anomaly summary text

Run with:
    python3.12 -m pytest tests/test_anomaly_detector.py -v
"""
from __future__ import annotations

import sys
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from alexander_interpreter.eval_parser import EvalSections
from alexander_interpreter.anomaly_detector import detect_anomalies


# ── Score table gate ───────────────────────────────────────────────────────────

def _ev(**kwargs) -> EvalSections:
    s = EvalSections()
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def test_score_table_shown_on_large_jump():
    ev = _ev(game_phase="Middlegame")
    flags = detect_anomalies(ev, prev_eval_cp=10, curr_eval_cp=120, score_jump_threshold_cp=50)
    assert flags.show_score_table is True


def test_score_table_hidden_on_small_jump():
    ev = _ev(game_phase="Middlegame")
    flags = detect_anomalies(ev, prev_eval_cp=10, curr_eval_cp=40, score_jump_threshold_cp=50)
    assert flags.show_score_table is False


def test_score_table_hidden_on_no_prev_eval():
    ev = _ev(game_phase="Middlegame")
    flags = detect_anomalies(ev, prev_eval_cp=None, curr_eval_cp=200, score_jump_threshold_cp=50)
    assert flags.show_score_table is False


def test_score_table_respects_custom_threshold():
    ev = _ev(game_phase="Middlegame")
    # jump of 30 should pass threshold=20 but fail threshold=50
    assert detect_anomalies(ev, 0, 30, score_jump_threshold_cp=20).show_score_table is True
    assert detect_anomalies(ev, 0, 30, score_jump_threshold_cp=50).show_score_table is False


def test_score_table_negative_jump():
    """Eval can go negative (opponent plays well); absolute value is what matters."""
    ev = _ev(game_phase="Middlegame")
    flags = detect_anomalies(ev, prev_eval_cp=100, curr_eval_cp=-30, score_jump_threshold_cp=50)
    assert flags.show_score_table is True  # |100 - (-30)| = 130


# ── Makogonov phase gate ───────────────────────────────────────────────────────

def test_makogonov_hidden_in_opening():
    ev = _ev(game_phase="Opening")
    flags = detect_anomalies(ev, None, None)
    assert flags.show_makogonov is False


def test_makogonov_shown_in_middlegame():
    ev = _ev(game_phase="Middlegame")
    flags = detect_anomalies(ev, None, None)
    assert flags.show_makogonov is True


def test_makogonov_shown_in_endgame():
    ev = _ev(game_phase="Endgame")
    flags = detect_anomalies(ev, None, None)
    assert flags.show_makogonov is True


def test_makogonov_hidden_when_phase_unknown():
    """Empty game_phase (no eval available) → Makogonov suppressed."""
    ev = _ev(game_phase="")
    flags = detect_anomalies(ev, None, None)
    assert flags.show_makogonov is False


# ── Anomaly token generation ───────────────────────────────────────────────────

def test_no_tokens_in_opening():
    """Structural anomaly rules only fire in Middlegame; opening → no tokens."""
    ev = _ev(game_phase="Opening", score_mobility=-80, pawn_weaknesses_white=5)
    flags = detect_anomalies(ev, None, None)
    assert flags.anomaly_tokens == []
    assert flags.anomaly_summary == ""


def test_mobility_gap_generates_tokens():
    ev = _ev(game_phase="Middlegame", score_mobility=-50)
    flags = detect_anomalies(ev, None, None)
    assert "passive" in flags.anomaly_tokens
    assert "mobility" in flags.anomaly_tokens
    assert "White" in flags.anomaly_summary


def test_pawn_weakness_generates_tokens():
    ev = _ev(game_phase="Middlegame", pawn_weaknesses_black=4)
    flags = detect_anomalies(ev, None, None)
    assert "pawn" in flags.anomaly_tokens
    assert "weakness" in flags.anomaly_tokens
    assert "Black" in flags.anomaly_summary


def test_king_safety_generates_tokens():
    ev = _ev(game_phase="Middlegame", score_king_safety=-60)
    flags = detect_anomalies(ev, None, None)
    assert "king" in flags.anomaly_tokens
    assert "safety" in flags.anomaly_tokens
    assert "White" in flags.anomaly_summary


def test_space_cramping_generates_tokens():
    ev = _ev(game_phase="Middlegame", space_white=10, space_black=20)
    flags = detect_anomalies(ev, None, None)
    assert "cramped" in flags.anomaly_tokens
    assert "White" in flags.anomaly_summary


def test_zone_contradiction_generates_tokens():
    ev = _ev(game_phase="Middlegame", final_eval_cp=80, win_prob_pct=30)
    flags = detect_anomalies(ev, None, None)
    assert "compensation" in flags.anomaly_tokens
    assert "contradiction" in flags.anomaly_summary


def test_no_anomalies_on_clean_position():
    """A balanced position with no defects → empty tokens and no summary."""
    ev = _ev(
        game_phase="Middlegame",
        score_mobility=10,
        score_king_safety=5,
        pawn_weaknesses_white=1,
        pawn_weaknesses_black=1,
        space_white=14,
        space_black=16,
        final_eval_cp=20,
        win_prob_pct=55,
    )
    flags = detect_anomalies(ev, prev_eval_cp=15, curr_eval_cp=20, score_jump_threshold_cp=50)
    assert flags.anomaly_tokens == []
    assert flags.anomaly_summary == ""


def test_multiple_anomalies_combined():
    """Multiple defects → tokens from all rules, summary lists all issues."""
    ev = _ev(
        game_phase="Middlegame",
        score_mobility=-40,
        pawn_weaknesses_white=4,
        score_king_safety=-50,
    )
    flags = detect_anomalies(ev, None, None)
    assert "passive" in flags.anomaly_tokens
    assert "pawn" in flags.anomaly_tokens
    assert "king" in flags.anomaly_tokens
    # Summary should mention multiple issues
    assert flags.anomaly_summary.count(";") >= 1


# ── game_phase display gate ────────────────────────────────────────────────────

def test_game_phase_shown_by_default():
    """suppress_opening=False (default) → show_game_phase always True."""
    ev = _ev(game_phase="Opening")
    flags = detect_anomalies(ev, None, None, game_phase_suppress_opening=False)
    assert flags.show_game_phase is True


def test_game_phase_suppressed_in_opening():
    ev = _ev(game_phase="Opening")
    flags = detect_anomalies(ev, None, None, game_phase_suppress_opening=True)
    assert flags.show_game_phase is False


def test_game_phase_shown_in_middlegame_when_suppress():
    """suppress_opening=True only suppresses Opening; Middlegame still shown."""
    ev = _ev(game_phase="Middlegame")
    flags = detect_anomalies(ev, None, None, game_phase_suppress_opening=True)
    assert flags.show_game_phase is True


def test_game_phase_suppress_with_empty_phase():
    """Empty game_phase + suppress_opening=True → suppress (no data = treat as opening)."""
    ev = _ev(game_phase="")
    flags = detect_anomalies(ev, None, None, game_phase_suppress_opening=True)
    assert flags.show_game_phase is False


# ── Phase transition remark ────────────────────────────────────────────────────

def test_phase_transition_opening_to_middlegame():
    ev = _ev(game_phase="Middlegame")
    flags = detect_anomalies(ev, None, None, prev_game_phase="Opening")
    assert "Opening" in flags.phase_transition_remark
    assert "Middlegame" in flags.phase_transition_remark


def test_phase_transition_middlegame_to_endgame():
    ev = _ev(game_phase="Endgame")
    flags = detect_anomalies(ev, None, None, prev_game_phase="Middlegame")
    assert "Endgame" in flags.phase_transition_remark
    assert flags.phase_transition_remark != ""


def test_phase_transition_no_remark_when_same():
    ev = _ev(game_phase="Middlegame")
    flags = detect_anomalies(ev, None, None, prev_game_phase="Middlegame")
    assert flags.phase_transition_remark == ""


def test_phase_transition_no_remark_when_no_prev():
    ev = _ev(game_phase="Endgame")
    flags = detect_anomalies(ev, None, None, prev_game_phase=None)
    assert flags.phase_transition_remark == ""


def test_phase_transition_fallback_text():
    """Unknown transition combo → generic fallback phrase."""
    ev = _ev(game_phase="Endgame")
    flags = detect_anomalies(ev, None, None, prev_game_phase="Opening")
    # Known triple: Opening→Endgame has a specific phrase
    assert flags.phase_transition_remark != ""


# ── pawn_structure gate ────────────────────────────────────────────────────────

def test_pawn_structure_shown_above_threshold():
    ev = _ev(game_phase="Middlegame", pawn_weaknesses_white=1, pawn_weaknesses_black=3)
    flags = detect_anomalies(ev, None, None, pawn_weakness_threshold=2)
    assert flags.show_pawn_structure is True  # max(1,3)=3 >= 2


def test_pawn_structure_hidden_below_threshold():
    ev = _ev(game_phase="Middlegame", pawn_weaknesses_white=0, pawn_weaknesses_black=1)
    flags = detect_anomalies(ev, None, None, pawn_weakness_threshold=2)
    assert flags.show_pawn_structure is False  # max(0,1)=1 < 2


def test_pawn_structure_threshold_zero_always():
    ev = _ev(game_phase="Middlegame", pawn_weaknesses_white=0, pawn_weaknesses_black=0)
    flags = detect_anomalies(ev, None, None, pawn_weakness_threshold=0)
    assert flags.show_pawn_structure is True


def test_pawn_structure_uses_max_per_side():
    """White=1, Black=3 → max=3 >= threshold=2 → shown."""
    ev = _ev(pawn_weaknesses_white=1, pawn_weaknesses_black=3)
    flags = detect_anomalies(ev, None, None, pawn_weakness_threshold=2)
    assert flags.show_pawn_structure is True


# ── space gate ─────────────────────────────────────────────────────────────────

def test_space_shown_above_imbalance():
    ev = _ev(space_white=16, space_black=22)
    flags = detect_anomalies(ev, None, None, space_imbalance_threshold=4)
    assert flags.show_space is True  # |16-22|=6 >= 4


def test_space_hidden_below_imbalance():
    ev = _ev(space_white=17, space_black=18)
    flags = detect_anomalies(ev, None, None, space_imbalance_threshold=4)
    assert flags.show_space is False  # |17-18|=1 < 4


def test_space_threshold_zero_always():
    ev = _ev(space_white=14, space_black=14)
    flags = detect_anomalies(ev, None, None, space_imbalance_threshold=0)
    assert flags.show_space is True


def test_space_hidden_when_no_data():
    ev = _ev()  # space_white=None, space_black=None
    flags = detect_anomalies(ev, None, None, space_imbalance_threshold=4)
    assert flags.show_space is False


# ── mobility gate ──────────────────────────────────────────────────────────────

def test_mobility_shown_above_threshold():
    ev = _ev(score_mobility=-30)
    flags = detect_anomalies(ev, None, None, mobility_score_threshold=20)
    assert flags.show_mobility is True  # |-30|=30 >= 20


def test_mobility_hidden_below_threshold():
    ev = _ev(score_mobility=10)
    flags = detect_anomalies(ev, None, None, mobility_score_threshold=20)
    assert flags.show_mobility is False  # |10| < 20


def test_mobility_threshold_zero_always():
    ev = _ev(score_mobility=0)
    flags = detect_anomalies(ev, None, None, mobility_score_threshold=0)
    assert flags.show_mobility is True


def test_mobility_hidden_when_no_data():
    ev = _ev()  # score_mobility=None
    flags = detect_anomalies(ev, None, None, mobility_score_threshold=20)
    assert flags.show_mobility is False
