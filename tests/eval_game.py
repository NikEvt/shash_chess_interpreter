#!/usr/bin/env python3
"""
Eval pipeline for alexander_interpreter.

Runs a full game through the real engine + real LLM, captures a complete trace:
  - AlexanderResult fields for every position
  - Prompt sections and full prompt text
  - Every _call_lm invocation: raw response, finish_reason, elapsed time
  - After-strip response, retry flag
  - Summary stats: empty responses, retries, lengths, estimated token counts

Engine results are saved to a fixture file after the first run so subsequent
runs skip the engine and only call the LLM.

Research parameters (preset, sections, tokens, etc.) live in a JSON config file
so you can version and compare different setups without touching the CLI.
Default config: tests/eval_config.json

Usage:
    # First run — requires engine; saves fixture automatically
    python tests/eval_game.py

    # Subsequent runs — skips engine, loads fixture
    python tests/eval_game.py

    # Force re-run of engine even if fixture exists
    python tests/eval_game.py --rerun-engine

    # Custom fixture path
    python tests/eval_game.py --fixture tests/fixtures/my_game.json

    # Custom PGN
    python tests/eval_game.py --pgn path/to/game.pgn

    # Custom research config (copy eval_config.json and edit)
    python tests/eval_game.py --run-config tests/my_experiment.json

    # Save LLM trace to a specific file
    python tests/eval_game.py --out trace.json

Requires engine: Alexander binary at Alexander/src/alexander (or ALEXANDER_ENGINE_PATH env).
Requires LLM:    LM Studio at http://localhost:1234 (or LM_STUDIO_URL env).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).parent.parent
BACKEND = ROOT / "webapp" / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

# config.py must be imported before alexander_interpreter to set sys.path
from config import (  # noqa: E402
    ENGINE_PATH, ANALYSIS_DEPTH, NUM_PV,
    ENGINE_THREADS, ENGINE_HASH_MB, ENGINE_TIMEOUT, MAX_TOKENS,
)

import chess  # noqa: E402
from parser import parse_input, build_positions  # noqa: E402
from quality import auto_question, quality_from_loss  # noqa: E402

from alexander_interpreter import (  # noqa: E402
    AlexanderResult, PromptConfig, build_config, win_prob_to_shashin_zone,
)
from alexander_interpreter.types import TopMove, EvalTrace  # noqa: E402
from alexander_interpreter.engine import AlexanderEngine  # noqa: E402
from alexander_interpreter.prompt import (  # noqa: E402
    build_tiny_prompt, build_tiny_prompt_sections,
)
import alexander_interpreter.llm as _llm_mod  # noqa: E402
from alexander_interpreter.eval_parser import parse_eval_sections as _parse_eval_sections  # noqa: E402
from alexander_interpreter.anomaly_detector import detect_anomalies as _detect_anomalies  # noqa: E402


_DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "alekhine_bogoljubov_1942.json"

_DEFAULT_PGN = """\
[Event "It"]
[Site "Salzburg (Austria)"]
[Date "1942.??.??"]
[Round "?"]
[White "Alexander Alekhine"]
[Black "Efim Bogoljubov"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nf6 3. Nxe5 d6 4. Nf3 Nxe4 5. d3 Nf6 6. d4 d5 7. c4 Nc6 8. Nc3
Bg4 9. Be3 Be7 10. h3 Bh5 11. c5 O-O 12. Bb5 Ne4 13. Qa4 Nxc3 14. bxc3 Bxf3 15.
gxf3 Qd7 16. Rb1 Qf5 17. Qd1 Bg5 18. Bd3 Qe6 19. Qe2 Bxe3 20. fxe3 b6 21. c4
dxc4 22. Bxc4 Qh6 23. Rd1 Rae8 24. f4 Qh4+ 25. Kf1 Ne7 26. Qg4 Qf6 27. Kf2 bxc5
28. dxc5 Qc6 29. Rc1 g6 30. Qf3 Qf6 31. e4 Rb8 32. Bb3 Rb4 33. Rhd1 Nc6 34. Rc4
Rxc4 35. Bxc4 Qb2+ 36. Qe2 Qb4 37. Bd5 Ne7 38. Bb3 Qxc5+ 39. Qe3 Qc6 40. Rc1 Qb7
41. Qd4 c6 42. Qd6 a5 43. Kf3 Qa7 44. h4 a4 45. Bc4 Qa5 46. Qxe7 Qd2 47. Qc5 Rd8
48. Qe3 Qh2 49. Qf2 Qh3+ 50. Qg3 Qd7 51. f5 Qe7 52. fxg6 Qa3+ 53. Kg2 Rd2+ 54.
Kh3 Qxg3+ 55. Kxg3 hxg6 56. Rf1 Rd7 57. Rf6 Rc7 58. e5 Kg7 59. Kf4 Rd7 60. Rxc6
Rd4+ 61. Kf3 Rxh4 62. Rc7 Rh3+ 63. Kg4 Rc3 64. e6 1-0
"""


# ── Fixture: serialize / deserialize AlexanderResult ─────────────────────────

def _ar_to_dict(ar: AlexanderResult) -> dict:
    """Recursively convert AlexanderResult (and nested dataclasses) to a plain dict."""
    return dataclasses.asdict(ar)


def _ar_from_dict(d: dict) -> AlexanderResult:
    """Reconstruct AlexanderResult from a plain dict (inverse of _ar_to_dict)."""
    d = dict(d)  # shallow copy — we'll pop keys
    top_moves = [TopMove(**m) for m in d.pop("top_moves", [])]
    et = d.pop("eval_trace", None)
    eval_trace = EvalTrace(**et) if et else None
    return AlexanderResult(**d, top_moves=top_moves, eval_trace=eval_trace)


def save_fixture(positions: list[dict], path: pathlib.Path) -> None:
    """
    Serialize all engine results from positions to a JSON fixture file.
    Saved fields: everything written by _apply_engine_result plus the base
    position fields from build_positions (fen, san, uci, color, move_number).
    """
    rows = []
    for pos in positions:
        ar = pos.get("alexander_result")
        rows.append({
            # Base position fields
            "index":       pos["index"],
            "fen":         pos["fen"],
            "san":         pos["san"],
            "uci":         pos["uci"],
            "move_number": pos["move_number"],
            "color":       pos["color"],
            # Engine result fields
            "eval_cp":       pos.get("eval_cp"),
            "eval_mate":     pos.get("eval_mate"),
            "score_cp_stm":  pos.get("score_cp_stm"),
            "shashin_zone":  pos.get("shashin_zone"),
            "wdl_win":       pos.get("wdl_win"),
            "wdl_draw":      pos.get("wdl_draw"),
            "wdl_loss":      pos.get("wdl_loss"),
            "best_move_san": pos.get("best_move_san"),
            "best_move_uci": pos.get("best_move_uci"),
            "pv_san":        pos.get("pv_san", []),
            "engine_summary": pos.get("engine_summary", []),
            "eval_loss_cp":  pos.get("eval_loss_cp"),
            "quality":       pos.get("quality"),
            # Full AlexanderResult for prompt building (None if engine was skipped)
            "alexander_result": _ar_to_dict(ar) if ar is not None else None,
        })

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"Fixture saved → {path}")


def load_fixture(path: pathlib.Path, positions: list[dict]) -> None:
    """
    Load engine results from a fixture file into an already-built positions list.
    Mutates positions in-place; positions must match the fixture by index.
    """
    rows = json.loads(path.read_text())
    if len(rows) != len(positions):
        raise ValueError(
            f"Fixture has {len(rows)} rows but game has {len(positions)} positions. "
            "Re-run with --rerun-engine to regenerate the fixture."
        )
    for pos, row in zip(positions, rows):
        pos.update({
            "eval_cp":       row.get("eval_cp"),
            "eval_mate":     row.get("eval_mate"),
            "score_cp_stm":  row.get("score_cp_stm"),
            "shashin_zone":  row.get("shashin_zone"),
            "wdl_win":       row.get("wdl_win"),
            "wdl_draw":      row.get("wdl_draw"),
            "wdl_loss":      row.get("wdl_loss"),
            "best_move_san": row.get("best_move_san"),
            "best_move_uci": row.get("best_move_uci"),
            "pv_san":        row.get("pv_san", []),
            "engine_summary": row.get("engine_summary", []),
            "eval_loss_cp":  row.get("eval_loss_cp"),
            "quality":       row.get("quality"),
            "alexander_result": (
                _ar_from_dict(row["alexander_result"])
                if row.get("alexander_result") is not None
                else None
            ),
        })


# ── LLM call tracer ───────────────────────────────────────────────────────────

class LLMTracer:
    """
    Wraps _call_lm: forwards every call to the real function and records
    the full input/output for later analysis.
    """

    def __init__(self, real_call_lm):
        self._real = real_call_lm
        self._log: list[dict] = []

    def __call__(self, prompt: str, temperature: float, max_tokens: int):
        t0 = time.perf_counter()
        raw, finish_reason = self._real(prompt, temperature, max_tokens)
        elapsed = time.perf_counter() - t0
        self._log.append({
            "prompt_chars":      len(prompt),
            "prompt_tokens_est": len(prompt.split()),
            "max_tokens":        max_tokens,
            "raw_response":      raw,
            "finish_reason":     finish_reason,
            "elapsed_s":         round(elapsed, 3),
        })
        return raw, finish_reason

    def pop_calls(self) -> list[dict]:
        calls, self._log = self._log, []
        return calls


# ── Engine phase (synchronous) ────────────────────────────────────────────────

def run_engine_phase(positions: list[dict], timeout: int = ENGINE_TIMEOUT) -> None:
    """Run Alexander engine on every position. Mutates positions in-place."""
    if not os.path.exists(ENGINE_PATH):
        print(f"[WARN] Engine not found at {ENGINE_PATH} — skipping engine phase.")
        print("       Set ALEXANDER_ENGINE_PATH env to override.")
        return

    engine = AlexanderEngine(
        ENGINE_PATH,
        depth=ANALYSIS_DEPTH,
        num_pv=NUM_PV,
        threads=ENGINE_THREADS,
        hash_mb=ENGINE_HASH_MB,
    )
    engine.start()
    try:
        for i, pos in enumerate(positions):
            b = chess.Board(pos["fen"])
            if b.is_game_over() or pos["san"] is None:
                continue
            try:
                ar: AlexanderResult = engine.analyze(pos["fen"], pos["uci"], b)
                _apply_engine_result(positions, i, ar)
                print(f"  [{i:>3}/{len(positions)-1}] {pos['san']:<8} "
                      f"cp={ar.score_cp:+5}  zone={ar.shashin_zone}", flush=True)
            except Exception as e:
                print(f"  [{i:>3}] {pos.get('san','?')} — engine error: {e}")
    finally:
        engine.stop()


def _apply_engine_result(positions: list[dict], i: int, ar: AlexanderResult) -> None:
    pos = positions[i]
    if ar.mate_in is not None:
        positions[i]["eval_cp"]   = None
        positions[i]["eval_mate"] = ar.mate_in if ar.side_to_move == "white" else -ar.mate_in
    else:
        positions[i]["eval_cp"]   = ar.score_cp if ar.side_to_move == "white" else (
            -ar.score_cp if ar.score_cp is not None else None
        )
        positions[i]["eval_mate"] = None

    positions[i].update({
        "score_cp_stm":    ar.score_cp,
        "shashin_zone":    ar.shashin_zone,
        "wdl_win":         ar.wdl_win,
        "wdl_draw":        ar.wdl_draw,
        "wdl_loss":        ar.wdl_loss,
        "best_move_san":   ar.best_move_san,
        "best_move_uci":   ar.best_move_uci,
        "pv_san":          ar.pv_san,
        "engine_summary":  ar.raw_eval_lines,
        "alexander_result": ar,
    })

    if i > 0 and pos["san"] is not None:
        prev_cp = positions[i - 1]["eval_cp"]
        curr_cp = positions[i]["eval_cp"]
        if prev_cp is not None and curr_cp is not None:
            loss = (prev_cp - curr_cp) if pos["color"] == "white" else (curr_cp - prev_cp)
            positions[i]["eval_loss_cp"] = max(0, loss)
            positions[i]["quality"]      = quality_from_loss(max(0, loss))
        else:
            positions[i]["quality"] = "good"


# ── Commentary phase (sequential, with full trace) ────────────────────────────

def build_position_trace(
    positions: list[dict],
    idx: int,
    our_side: str,
    config: PromptConfig,
    tracer: LLMTracer,
) -> dict:
    pos = positions[idx]

    trace: dict[str, Any] = {
        "index":        idx,
        "move_number":  pos.get("move_number"),
        "san":          pos.get("san"),
        "color":        pos.get("color"),
        "fen":          pos.get("fen"),
        "quality":      pos.get("quality"),
        "eval_cp":      pos.get("eval_cp"),
        "eval_mate":    pos.get("eval_mate"),
        "eval_loss_cp": pos.get("eval_loss_cp"),
    }

    if pos["san"] is None:
        trace.update(commentary="The game begins.", lm_calls=[],
                     retried=False, prompt_sections=[], prompt_text="")
        return trace

    prev_best_san = ""
    prev_best_uci = ""
    prev_eval_cp: int | None = None
    board_before: chess.Board | None = None
    prev_game_phase: str | None = None

    if idx > 0:
        prev = positions[idx - 1]
        prev_best_uci = prev.get("best_move_uci") or ""
        prev_best_san = prev.get("best_move_san") or ""
        prev_eval_cp  = prev.get("eval_cp")
        try:
            board_before = chess.Board(prev["fen"])
        except Exception:
            pass
        prev_ar_obj = prev.get("alexander_result")
        if prev_ar_obj and prev_ar_obj.raw_eval_lines:
            gp = _parse_eval_sections(prev_ar_obj.raw_eval_lines).game_phase
            prev_game_phase = gp or None

    ar = pos.get("alexander_result")
    if ar is None:
        played_color = pos.get("color") or "black"
        stm = "black" if played_color == "white" else "white"
        ar = AlexanderResult(
            fen=pos["fen"],
            side_to_move=stm,
            played_move=pos["san"],
            best_move_uci=prev_best_uci,
            best_move_san=prev_best_san or pos["san"],
            score_cp=pos.get("score_cp_stm"),
            mate_in=pos.get("eval_mate"),
            wdl_win=pos.get("wdl_win", 500),
            wdl_draw=pos.get("wdl_draw", 0),
            wdl_loss=pos.get("wdl_loss", 500),
            shashin_zone=win_prob_to_shashin_zone(pos.get("wdl_win", 500) / 10.0),
            top_moves=[],
            pv_san=[],
            depth=ANALYSIS_DEPTH,
        )
    else:
        ar = dataclasses.replace(
            ar,
            played_move=pos["san"] or ar.played_move,
            best_move_san=prev_best_san or ar.best_move_san,
        )

    game_uci = " ".join(p["uci"] for p in positions[:idx + 1] if p.get("uci"))
    ar = dataclasses.replace(ar, game_uci=game_uci)

    trace["engine"] = {
        "shashin_zone":          ar.shashin_zone,
        "score_cp":              ar.score_cp,
        "mate_in":               ar.mate_in,
        "wdl":                   [ar.wdl_win, ar.wdl_draw, ar.wdl_loss],
        "best_move_san":         ar.best_move_san,
        "top_moves":             [{"san": m.san, "score": m.score_str()} for m in ar.top_moves],
        "pv_san":                ar.pv_san[:5],
        "depth":                 ar.depth,
        "raw_eval_lines_count":  len(ar.raw_eval_lines),
    }

    question = auto_question(
        ar.score_cp, ar.mate_in, ar.shashin_zone,
        ar.played_move, ar.best_move_san,
        eval_loss=pos.get("eval_loss_cp"),
    )
    trace["question_type"] = question

    curr_eval_cp = pos.get("eval_cp")

    shared = dict(
        prev_eval_cp=prev_eval_cp,
        curr_eval_cp=curr_eval_cp,
        curr_eval_mate=pos.get("eval_mate"),
        our_side=our_side,
        question_type=question,
        board_before=board_before,
        eval_loss=pos.get("eval_loss_cp"),
        config=config,
        prev_game_phase=prev_game_phase,
    )

    sections = build_tiny_prompt_sections(ar, **shared)
    prompt   = build_tiny_prompt(ar, **shared)

    trace["prompt_sections"]   = sections
    trace["prompt_text"]       = prompt
    trace["prompt_chars"]      = len(prompt)
    trace["prompt_tokens_est"] = len(prompt.split())

    # ── Anomaly detector trace ────────────────────────────────────────────────
    # Parse eval sections and call detect_anomalies with current config thresholds.
    # Stores both raw gate inputs (for threshold sweep in analyze_eval.ipynb)
    # and the resulting flag states.
    ev = _parse_eval_sections(ar.raw_eval_lines)
    _af = _detect_anomalies(
        ev,
        prev_eval_cp=prev_eval_cp,
        curr_eval_cp=curr_eval_cp,
        score_jump_threshold_cp=config.score_jump_threshold_cp,
        pawn_weakness_threshold=config.pawn_weakness_threshold,
        space_imbalance_threshold=config.space_imbalance_threshold,
        mobility_score_threshold=config.mobility_score_threshold,
        game_phase_suppress_opening=config.game_phase_suppress_opening,
        prev_game_phase=prev_game_phase,
    )

    # Raw numeric inputs — used by the notebook for threshold sweep plots
    _delta_cp = (
        abs(curr_eval_cp - prev_eval_cp)
        if curr_eval_cp is not None and prev_eval_cp is not None else None
    )
    _space_diff = (
        abs(ev.space_white - ev.space_black)
        if ev.space_white is not None and ev.space_black is not None else None
    )

    trace["anomaly"] = {
        # Gate inputs (raw values for sweep analysis)
        "eval_delta_cp":       _delta_cp,
        "max_pawn_weaknesses": max(ev.pawn_weaknesses_white or 0, ev.pawn_weaknesses_black or 0),
        "space_diff":          _space_diff,
        "score_mobility_abs":  abs(ev.score_mobility) if ev.score_mobility is not None else None,
        "game_phase":          ev.game_phase,
        "prev_game_phase":     prev_game_phase,
        # Gate results (with current config thresholds)
        "show_score_table":    _af.show_score_table,
        "show_game_phase":     _af.show_game_phase,
        "show_pawn_structure": _af.show_pawn_structure,
        "show_space":          _af.show_space,
        "show_mobility":       _af.show_mobility,
        "show_makogonov":      _af.show_makogonov,
        "phase_transition_remark": bool(_af.phase_transition_remark),
        "anomaly_summary":     bool(_af.anomaly_summary),
        # Thresholds used (reference for notebook plots)
        "thresholds": {
            "score_jump_threshold_cp":     config.score_jump_threshold_cp,
            "pawn_weakness_threshold":     config.pawn_weakness_threshold,
            "space_imbalance_threshold":   config.space_imbalance_threshold,
            "mobility_score_threshold":    config.mobility_score_threshold,
            "game_phase_suppress_opening": config.game_phase_suppress_opening,
        },
    }

    tracer.pop_calls()  # clear any stale entries before this position

    try:
        commentary = _llm_mod.ask(prompt, max_tokens=config.max_tokens)
        if ar.best_move_san:
            commentary = f"Best move: {ar.best_move_san}.\n{commentary}"
    except _llm_mod.LMStudioError as e:
        commentary = f"[LLM unavailable: {e}]"
    except Exception as e:
        commentary = f"[error: {e}]"

    lm_calls = tracer.pop_calls()

    from alexander_interpreter.llm import _strip_think
    for call in lm_calls:
        call["stripped_response"] = _strip_think(call["raw_response"])
        call["response_chars"]    = len(call["raw_response"])
        call["stripped_chars"]    = len(call["stripped_response"])
        call["is_think_only"]     = (
            not call["stripped_response"] and bool(call["raw_response"].strip())
        )

    trace["lm_calls"]         = lm_calls
    trace["retried"]          = len(lm_calls) > 1
    trace["commentary"]       = commentary
    trace["commentary_chars"] = len(commentary)
    trace["commentary_empty"] = not commentary.strip()

    return trace


# ── Summary ────────────────────────────────────────────────────────────────────

def print_summary(traces: list[dict], game_header: dict, config_name: str) -> None:
    move_traces = [t for t in traces if t.get("san") is not None]
    all_calls   = [c for t in move_traces for c in t.get("lm_calls", [])]

    def avg(lst): return round(sum(lst) / len(lst), 1) if lst else 0

    empty_count  = sum(1 for t in move_traces if t.get("commentary_empty"))
    retry_count  = sum(1 for t in move_traces if t.get("retried"))
    think_only   = sum(1 for c in all_calls if c.get("is_think_only"))
    truncated    = sum(1 for c in all_calls if c.get("finish_reason") == "length")

    commentary_chars = [t["commentary_chars"] for t in move_traces if not t["commentary_empty"]]
    prompt_tokens    = [t.get("prompt_tokens_est", 0) for t in move_traces]
    response_chars   = [c["response_chars"] for c in all_calls]
    elapsed_times    = [c["elapsed_s"] for c in all_calls]

    w = game_header.get("White", "?")
    b = game_header.get("Black", "?")

    print()
    print("═" * 62)
    print(f"  EVAL SUMMARY — {w} vs {b}")
    print(f"  Config: {config_name}")
    print("═" * 62)
    print(f"  Positions analysed : {len(move_traces)}")
    print(f"  Empty commentaries : {empty_count}  {'✓' if empty_count == 0 else '✗ GAPS!'}")
    print(f"  LLM retries        : {retry_count}  (think-only or truncated)")
    print(f"  Think-only calls   : {think_only}")
    print(f"  Truncated calls    : {truncated}")
    print(f"  Total LLM calls    : {len(all_calls)}")
    print()
    print(f"  Avg prompt  tokens : {avg(prompt_tokens)}")
    print(f"  Avg raw resp chars : {avg(response_chars)}")
    print(f"  Avg commentary len : {avg(commentary_chars)} chars")
    print(f"  Avg LLM latency    : {avg(elapsed_times)} s")
    print()

    # Anomaly flag firing rates
    _FLAG_SHORT = {
        "show_score_table":    "ST",
        "show_game_phase":     "GP",
        "show_pawn_structure": "PW",
        "show_space":          "SP",
        "show_mobility":       "MO",
        "show_makogonov":      "MK",
    }
    anm_traces = [t for t in move_traces if "anomaly" in t]
    if anm_traces:
        print()
        print(f"  Anomaly flags  (N={len(anm_traces)} positions with eval data):")
        for flag, short in _FLAG_SHORT.items():
            count = sum(1 for t in anm_traces if t["anomaly"].get(flag))
            pct   = count / len(anm_traces) * 100
            bar   = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            print(f"    [{short}] {flag:<22} {bar} {count:>3}/{len(anm_traces)}  {pct:5.1f}%")
        phase_tr = sum(1 for t in anm_traces if t["anomaly"].get("phase_transition_remark"))
        print(f"    [PT] phase_transition_remark     "
              f"{'█' * int(phase_tr/len(anm_traces)*20)}"
              f"{'░' * (20-int(phase_tr/len(anm_traces)*20))}"
              f" {phase_tr:>3}/{len(anm_traces)}")
        print()

    print(f"  {'#':>3}  {'Move':<8}  {'CP':>6}  {'Zone':<22}  {'Q':>5}  {'Len':>4}  Flags  Anomaly")
    print("  " + "─" * 72)
    for t in move_traces:
        flags = ""
        if t.get("retried"):          flags += "↺"
        if t.get("commentary_empty"): flags += "⚠MT"
        if any(c.get("is_think_only") for c in t.get("lm_calls", [])):
            flags += "⚠TH"

        # Compact anomaly flag indicator: show which flags fired as short codes
        anm_str = ""
        if "anomaly" in t:
            a = t["anomaly"]
            fired = [sh for flag, sh in _FLAG_SHORT.items() if a.get(flag)]
            if a.get("phase_transition_remark"):
                fired.append("PT")
            anm_str = ",".join(fired) if fired else "—"

        cp_str = (
            f"{t['eval_cp']:+}" if t.get("eval_cp") is not None else
            f"M{t['eval_mate']}" if t.get("eval_mate") is not None else "  —"
        )
        eng  = t.get("engine") or {}
        zone = eng.get("shashin_zone", "—")[:22]
        q    = t.get("question_type", "—")[:5]
        col  = "W" if t.get("color") == "white" else "B"
        print(f"  {t.get('move_number',0):>3}{col}  {t['san']:<8}  {cp_str:>6}  "
              f"{zone:<22}  {q:>5}  {t.get('commentary_chars',0):>4}  {flags:<6} {anm_str}")

    print("═" * 62)
    print()


# ── Run config (JSON) ─────────────────────────────────────────────────────────

_DEFAULT_RUN_CONFIG = ROOT / "tests" / "eval_config.json"

_RUN_CONFIG_DEFAULTS: dict = {
    "preset":    "full",
    "our_side":  "white",
    "max_tokens":    MAX_TOKENS,
    "engine_timeout": ENGINE_TIMEOUT,
    # core sections
    "include_system":                True,
    "include_last_move":             True,
    "include_eval_change":           True,
    "include_engine_recommendation": True,
    "include_pv_continuation":       True,
    "include_opening_name":          True,
    "include_theory":                True,
    # alexander eval sections
    "include_game_phase":     True,
    "include_score_table":    True,
    "include_pawn_structure": True,
    "include_space":          True,
    "include_mobility":       True,
    "include_makogonov":      True,
    # anomaly gating thresholds
    "score_jump_threshold_cp":     50,
    "pawn_weakness_threshold":      2,
    "space_imbalance_threshold":    4,
    "mobility_score_threshold":    20,
    "game_phase_suppress_opening": False,
    # LLM thinking mode (Qwen3 /think vs /no_think)
    "thinking": False,
}

_SECTION_KEYS = {
    "include_system", "include_last_move", "include_eval_change",
    "include_engine_recommendation", "include_pv_continuation",
    "include_opening_name", "include_theory",
    "include_game_phase", "include_score_table", "include_pawn_structure",
    "include_space", "include_mobility", "include_makogonov",
}


def load_run_config(path: pathlib.Path) -> dict:
    raw = json.loads(path.read_text())
    unknown = {k for k in raw if not k.startswith("_") and k not in _RUN_CONFIG_DEFAULTS}
    if unknown:
        print(f"[WARN] Unknown keys in run config: {unknown}")
    cfg = {**_RUN_CONFIG_DEFAULTS}
    cfg.update({k: v for k, v in raw.items() if not k.startswith("_")})
    return cfg


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Eval pipeline for alexander_interpreter")
    p.add_argument("--pgn",        default=None, help="Path to PGN file")
    p.add_argument("--fixture",    default=str(_DEFAULT_FIXTURE),
                   help="Path to engine fixture JSON (created on first run)")
    p.add_argument("--rerun-engine", action="store_true",
                   help="Re-run engine even if fixture already exists")
    p.add_argument("--run-config", default=str(_DEFAULT_RUN_CONFIG),
                   help="Path to research JSON config (preset, sections, tokens, etc.)")
    p.add_argument("--out",        default=None, help="Save LLM trace JSON to this file")
    p.add_argument("--thinking",   action="store_true", default=False,
                   help="Enable Qwen3 thinking mode (/think). Overrides run-config 'thinking'.")
    p.add_argument("--no-thinking", dest="thinking", action="store_false",
                   help="Force disable thinking mode regardless of run-config.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    fixture_path   = pathlib.Path(args.fixture)
    run_config_path = pathlib.Path(args.run_config)

    # ── Load research config ──────────────────────────────────────────────────
    if not run_config_path.exists():
        print(f"[WARN] Run config not found at {run_config_path}, using defaults.")
        rc = dict(_RUN_CONFIG_DEFAULTS)
    else:
        rc = load_run_config(run_config_path)
        print(f"Run config: {run_config_path.name}")

    engine_timeout  = int(rc["engine_timeout"])
    our_side        = rc["our_side"]
    overrides       = {k: rc[k] for k in _SECTION_KEYS if not rc[k]}
    # --thinking flag wins; otherwise fall back to run-config value
    thinking        = args.thinking or bool(rc.get("thinking", False))

    # ── Load PGN ──────────────────────────────────────────────────────────────
    pgn_text = pathlib.Path(args.pgn).read_text() if args.pgn else _DEFAULT_PGN
    game = parse_input(pgn_text)
    if game is None:
        print("ERROR: cannot parse PGN input")
        sys.exit(1)

    game_header = dict(game.headers)
    print(f"\nGame: {game_header.get('White','?')} vs {game_header.get('Black','?')}"
          f"  [{game_header.get('Event','?')}, {game_header.get('Date','?')}]")

    # ── Build prompt config ───────────────────────────────────────────────────
    config = build_config(rc["preset"], overrides)
    config = dataclasses.replace(
        config,
        max_tokens=int(rc["max_tokens"]),
        score_jump_threshold_cp=int(rc["score_jump_threshold_cp"]),
        pawn_weakness_threshold=int(rc["pawn_weakness_threshold"]),
        space_imbalance_threshold=int(rc["space_imbalance_threshold"]),
        mobility_score_threshold=int(rc["mobility_score_threshold"]),
        game_phase_suppress_opening=bool(rc["game_phase_suppress_opening"]),
    )
    config_label = rc["preset"] + (f"+overrides={overrides}" if overrides else "")
    thinking_label = "ON (/think)" if thinking else "OFF (/no_think)"
    print(f"Config: {config_label}  |  max_tokens={config.max_tokens}  |  thinking={thinking_label}")

    # ── Build positions ───────────────────────────────────────────────────────
    positions = build_positions(game)
    print(f"Positions: {len(positions)} ({len(positions)-1} moves)")

    # ── Engine phase: load fixture or run engine ───────────────────────────────
    use_fixture = fixture_path.exists() and not args.rerun_engine
    if use_fixture:
        print(f"\n── Engine results: loading fixture ({fixture_path.name}) ──")
        load_fixture(fixture_path, positions)
        print(f"  Loaded {len(positions)} positions from fixture.")
    else:
        reason = "fixture not found" if not fixture_path.exists() else "--rerun-engine"
        print(f"\n── Engine analysis (depth={ANALYSIS_DEPTH}, {reason}) ──")
        run_engine_phase(positions, timeout=engine_timeout)
        save_fixture(positions, fixture_path)

    # ── Apply thinking mode ───────────────────────────────────────────────────
    _llm_mod.set_thinking(thinking)

    # ── Install LLM tracer ────────────────────────────────────────────────────
    tracer = LLMTracer(_llm_mod._call_lm)
    _llm_mod._call_lm = tracer

    # ── Commentary phase ──────────────────────────────────────────────────────
    print(f"\n── Commentary (LLM) ──")
    traces: list[dict] = []
    for i in range(len(positions)):
        san = positions[i].get("san") or "start"
        print(f"  [{i:>3}/{len(positions)-1}] {san:<8}", end="", flush=True)
        t0 = time.perf_counter()
        trace = build_position_trace(positions, i, our_side, config, tracer)
        elapsed = time.perf_counter() - t0
        traces.append(trace)

        pos_calls = trace.get("lm_calls", [])
        flags = ""
        if len(pos_calls) > 1: flags += "↺ "
        if trace.get("commentary_empty"): flags += "⚠EMPTY "
        if any(c.get("is_think_only") for c in pos_calls): flags += "⚠THINK"
        print(f"  {elapsed:5.1f}s  calls={len(pos_calls)}  "
              f"len={trace.get('commentary_chars',0):>4}  {flags}")

    _llm_mod._call_lm = tracer._real  # restore

    # ── Summary ───────────────────────────────────────────────────────────────
    print_summary(traces, game_header, config_label)

    # ── Save LLM trace ────────────────────────────────────────────────────────
    if args.out:
        out_path = pathlib.Path(args.out)
    else:
        results_dir = ROOT / "tests" / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        out_path = results_dir / f"eval_trace_{int(time.time())}.json"

    def _serialise(obj):
        if isinstance(obj, dict):
            return {k: _serialise(v) for k, v in obj.items() if k != "alexander_result"}
        if isinstance(obj, list):
            return [_serialise(v) for v in obj]
        return obj

    out_path.write_text(json.dumps({
        "game":           game_header,
        "run_config":     rc,
        "run_config_file": str(run_config_path),
        "config":         config_label,
        "thinking":       thinking,
        "max_tokens":     config.max_tokens,
        "analysis_depth": ANALYSIS_DEPTH,
        "fixture":        str(fixture_path),
        "traces":         [_serialise(t) for t in traces],
    }, ensure_ascii=False, indent=2))
    print(f"LLM trace saved → {out_path}")

    # ── Save engine analysis ──────────────────────────────────────────────────
    engine_rows = []
    for pos in positions:
        if pos.get("san") is None:
            continue
        top_moves = []
        ar = pos.get("alexander_result")
        if ar is not None:
            top_moves = [
                {"san": m.san, "uci": m.uci, "score": m.score_str()}
                for m in ar.top_moves
            ]
        engine_rows.append({
            "index":        pos["index"],
            "move_number":  pos["move_number"],
            "san":          pos["san"],
            "uci":          pos["uci"],
            "color":        pos["color"],
            "fen":          pos["fen"],
            "eval_cp":      pos.get("eval_cp"),
            "eval_mate":    pos.get("eval_mate"),
            "score_cp_stm": pos.get("score_cp_stm"),
            "shashin_zone": pos.get("shashin_zone"),
            "wdl_win":      pos.get("wdl_win"),
            "wdl_draw":     pos.get("wdl_draw"),
            "wdl_loss":     pos.get("wdl_loss"),
            "best_move_san":pos.get("best_move_san"),
            "best_move_uci":pos.get("best_move_uci"),
            "pv_san":       pos.get("pv_san", []),
            "eval_loss_cp": pos.get("eval_loss_cp"),
            "quality":      pos.get("quality"),
            "top_moves":    top_moves,
        })

    engine_out = out_path.parent / out_path.name.replace("eval_trace_", "engine_analysis_")
    engine_out.write_text(json.dumps({
        "game":           game_header,
        "analysis_depth": ANALYSIS_DEPTH,
        "fixture":        str(fixture_path),
        "positions":      engine_rows,
    }, ensure_ascii=False, indent=2))
    print(f"Engine analysis saved → {engine_out}\n")


if __name__ == "__main__":
    main()
