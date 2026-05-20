"""
Regression tests for the "think-only gap" bug:
  when the LLM outputs only a <think>...</think> block, _strip_think() returns "",
  which propagated silently as an empty commentary with no retry.

Covers _strip_think() edge cases and ask() retry logic.

Full-game integration (real engine + LLM trace) → tests/eval_game.py

Run with:
    python3.12 -m pytest tests/test_commentary_gaps.py -v
"""
from __future__ import annotations

import sys
import pathlib
from unittest.mock import patch

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from alexander_interpreter.llm import _strip_think, ask


# ── _strip_think edge cases ────────────────────────────────────────────────────

def test_strip_think_closed_block_alone():
    """A response that is only a closed <think> block → empty string (the bug trigger)."""
    assert _strip_think("<think>some reasoning</think>") == ""


def test_strip_think_multiline_closed_block_alone():
    assert _strip_think("<think>\nlong\nreasoning\n</think>") == ""


def test_strip_think_unclosed_block_alone():
    """Truncated mid-think → also empty (model ran out of tokens while thinking)."""
    assert _strip_think("<think>truncated mid-sentence") == ""


def test_strip_think_preserves_text_before_block():
    result = _strip_think("Alekhine plays Qg4.<think>let me reconsider</think>")
    assert result == "Alekhine plays Qg4."


def test_strip_think_preserves_text_after_block():
    result = _strip_think("<think>reasoning</think> Alekhine plays Qg4.")
    assert result == "Alekhine plays Qg4."


def test_strip_think_no_tags_unchanged():
    text = "White's queen sacrifice forces resignation."
    assert _strip_think(text) == text


def test_strip_think_multiple_closed_blocks():
    result = _strip_think("<think>a</think>commentary<think>b</think>")
    assert result == "commentary"


# ── ask() retry logic ──────────────────────────────────────────────────────────

@patch("alexander_interpreter.llm._call_lm")
def test_ask_retries_when_think_only(mock_call):
    """Core regression: think-only → empty after strip → retry must be triggered."""
    mock_call.side_effect = [
        ("<think>reasoning</think>", "stop"),
        ("Alekhine's knight sacrifice decides the game.", "stop"),
    ]
    result = ask("analyse this")
    assert result == "Alekhine's knight sacrifice decides the game."
    assert mock_call.call_count == 2, "Expected exactly 1 retry"


@patch("alexander_interpreter.llm._call_lm")
def test_ask_retries_on_truncation(mock_call):
    mock_call.side_effect = [
        ("Truncated respon", "length"),
        ("Full response text.", "stop"),
    ]
    result = ask("analyse this")
    assert result == "Full response text."
    assert mock_call.call_count == 2


@patch("alexander_interpreter.llm._call_lm")
def test_ask_retry_budget_is_plus_256(mock_call):
    """Retry budget = max_tokens + 256 (not max(max_tokens, 512))."""
    mock_call.side_effect = [
        ("<think>thinking</think>", "stop"),
        ("Answer.", "stop"),
    ]
    ask("test", max_tokens=100)
    first_budget = mock_call.call_args_list[0][0][2]
    retry_budget = mock_call.call_args_list[1][0][2]
    assert first_budget == 100
    assert retry_budget == 356, f"Expected 356 (100+256), got {retry_budget}"


@patch("alexander_interpreter.llm._call_lm")
def test_ask_no_retry_when_response_is_fine(mock_call):
    """Normal response → no retry, called exactly once."""
    mock_call.side_effect = [("Good commentary.", "stop")]
    result = ask("test")
    assert result == "Good commentary."
    assert mock_call.call_count == 1


@patch("alexander_interpreter.llm._call_lm")
def test_ask_fallback_to_empty_if_both_attempts_think_only(mock_call):
    """If retry also returns think-only, return "" rather than crashing."""
    mock_call.side_effect = [
        ("<think>thinking</think>", "stop"),
        ("<think>still thinking</think>", "stop"),
    ]
    result = ask("test")
    assert isinstance(result, str)  # must not raise
