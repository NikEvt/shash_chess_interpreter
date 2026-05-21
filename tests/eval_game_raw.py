#!/usr/bin/env python3
"""
Raw baseline eval: commentary from system instruction + raw Alexander output.

Identical pipeline to eval_game.py, except prompt building is replaced:
instead of build_tiny_prompt, the LLM receives only a system instruction
and the raw Alexander eval text (UCI search lines stripped).

Purpose: deepeval baseline — measures LLM quality when given unprocessed
engine output rather than the structured prompt built by the interpreter.

Usage:
    python tests/eval_game_raw.py
    python tests/eval_game_raw.py --fixture tests/fixtures/my_game.json
    python tests/eval_game_raw.py --out results/my_raw_trace.json
    python tests/eval_game_raw.py --run-config tests/eval_config.json
    python tests/eval_game_raw.py --rerun-engine

Output trace files are named eval_trace_raw_<timestamp>.json so they sit
alongside eval_trace_*.json files and are loaded by test_deepeval_commentary.py.
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
TESTS = ROOT / "tests"
BACKEND = ROOT / "webapp" / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(TESTS))

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

import alexander_interpreter.llm as _llm_mod  # noqa: E402

# Re-use shared infrastructure from eval_game
import eval_game as _eg  # noqa: E402


# ── Raw prompt builder ────────────────────────────────────────────────────────

_QUALITY_WORD = {
    "best move":   "best",
    "best":        "best",
    "excellent":   "good",
    "good":        "good",
    "inaccuracy":  "inaccuracy",
    "mistake":     "mistake",
    "blunder":     "blunder",
    "alternative": "alternative",
    "played":      "played",
}


def _move_quality_label(
    played: str, best_san: str,
    score_cp: int | None, eval_loss: int | None,
) -> str:
    if played == best_san:
        return "best move"
    delta = eval_loss if eval_loss is not None else (abs(score_cp) if score_cp is not None else None)
    if delta is None:
        return "played"
    if delta <= 5:   return "best"
    if delta <= 20:  return "excellent"
    if delta <= 50:  return "good"
    if delta <= 100: return "inaccuracy"
    if delta <= 200: return "mistake"
    return "blunder"


def _filter_eval_lines(lines: list[str]) -> list[str]:
    """Keep only the Alexander eval section; drop UCI search output."""
    filtered = []
    for line in lines:
        if line.strip() == "--- search ---":
            break
        filtered.append(line)
    # Trim trailing blank lines
    while filtered and not filtered[-1].strip():
        filtered.pop()
    return filtered


def _build_raw_prompt_sections(
    pos: dict,
    prev_pos: dict | None,
    our_side: str,
    ar: AlexanderResult,
    eval_loss: int | None,
) -> list[dict]:
    """Return two prompt sections: system instruction + raw Alexander output."""
    Our_Side = our_side.capitalize()
    played = pos.get("san") or ""
    color_who_played = "black" if ar.side_to_move == "white" else "white"
    best_san = ar.best_move_san or ""

    quality_raw = _move_quality_label(played, best_san, ar.score_cp, eval_loss) if played else ""
    quality_word = _QUALITY_WORD.get(quality_raw, quality_raw)

    system = (
        f"You are a chess commentator. Our side: {Our_Side}. "
        f"{color_who_played.capitalize()} just played this move. "
        f"Rephrase the Context below into exactly 3 commentary sentences. Stick to what the Context states. "
        f"Output only the 3 sentences. Do not write 'Okay', 'Here is', 'Sure' or any preamble. "
        f"Do not add closing remarks."
    )

    # Minimal header so the model knows which move was played and its quality
    move_header_lines = []
    if played:
        move_header_lines.append(f"Move played: {played} ({quality_word})")
    if best_san and best_san != played:
        move_header_lines.append(f"Engine best move: {best_san}")
    move_header = "\n".join(move_header_lines)

    eval_lines = _filter_eval_lines(ar.raw_eval_lines)
    raw_block = "\n".join(eval_lines).strip()

    raw_content = (move_header + "\n\n" + raw_block).strip() if raw_block else move_header

    return [
        {"label": "System instruction", "content": system},
        {"label": "Raw engine output",  "content": raw_content},
    ]


def _build_raw_prompt(sections: list[dict]) -> str:
    """Assemble sections into a single prompt string."""
    system = next((s["content"] for s in sections if s["label"] == "System instruction"), "")
    body_parts = [s["content"] for s in sections if s["label"] != "System instruction"]
    body = "\n\n".join(p for p in body_parts if p)
    return f"{system}\n\nContext:\n{body}"


# ── Position trace builder (raw variant) ─────────────────────────────────────

def build_raw_position_trace(
    positions: list[dict],
    idx: int,
    our_side: str,
    config: PromptConfig,
    tracer,
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

    prev_pos = positions[idx - 1] if idx > 0 else None
    prev_eval_cp: int | None = prev_pos.get("eval_cp") if prev_pos else None
    prev_best_san = (prev_pos.get("best_move_san") or "") if prev_pos else ""
    prev_best_uci = (prev_pos.get("best_move_uci") or "") if prev_pos else ""

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

    eval_loss = pos.get("eval_loss_cp")
    sections = _build_raw_prompt_sections(pos, prev_pos, our_side, ar, eval_loss)
    prompt   = _build_raw_prompt(sections)

    trace["prompt_sections"]   = sections
    trace["prompt_text"]       = prompt
    trace["prompt_chars"]      = len(prompt)
    trace["prompt_tokens_est"] = len(prompt.split())

    tracer.pop_calls()

    try:
        commentary = _llm_mod.ask(prompt, max_tokens=config.max_tokens)
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


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Raw baseline eval: system instruction + raw Alexander output"
    )
    p.add_argument("--pgn",           default=None)
    p.add_argument("--fixture",       default=str(_eg._DEFAULT_FIXTURE))
    p.add_argument("--rerun-engine",  action="store_true")
    p.add_argument("--run-config",    default=str(_eg._DEFAULT_RUN_CONFIG))
    p.add_argument("--out",           default=None)
    p.add_argument("--thinking",      action="store_true",  default=False)
    p.add_argument("--no-thinking",   dest="thinking", action="store_false")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    fixture_path    = pathlib.Path(args.fixture)
    run_config_path = pathlib.Path(args.run_config)

    if not run_config_path.exists():
        print(f"[WARN] Run config not found at {run_config_path}, using defaults.")
        rc = dict(_eg._RUN_CONFIG_DEFAULTS)
    else:
        rc = _eg.load_run_config(run_config_path)
        print(f"Run config: {run_config_path.name}")

    engine_timeout = int(rc["engine_timeout"])
    our_side       = rc["our_side"]
    overrides      = {k: rc[k] for k in _eg._SECTION_KEYS if not rc[k]}
    thinking       = args.thinking or bool(rc.get("thinking", False))

    pgn_text = pathlib.Path(args.pgn).read_text() if args.pgn else _eg._DEFAULT_PGN
    game = parse_input(pgn_text)
    if game is None:
        print("ERROR: cannot parse PGN input")
        sys.exit(1)

    game_header = dict(game.headers)
    print(f"\nGame: {game_header.get('White','?')} vs {game_header.get('Black','?')}"
          f"  [{game_header.get('Event','?')}, {game_header.get('Date','?')}]")

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
    config_label   = "raw_baseline"
    thinking_label = "ON (/think)" if thinking else "OFF (/no_think)"
    print(f"Config: {config_label}  |  max_tokens={config.max_tokens}  |  thinking={thinking_label}")

    positions = build_positions(game)
    print(f"Positions: {len(positions)} ({len(positions)-1} moves)")

    use_fixture = fixture_path.exists() and not args.rerun_engine
    if use_fixture:
        print(f"\n── Engine results: loading fixture ({fixture_path.name}) ──")
        _eg.load_fixture(fixture_path, positions)
        print(f"  Loaded {len(positions)} positions from fixture.")
    else:
        reason = "fixture not found" if not fixture_path.exists() else "--rerun-engine"
        print(f"\n── Engine analysis (depth={ANALYSIS_DEPTH}, {reason}) ──")
        _eg.run_engine_phase(positions, timeout=engine_timeout)
        _eg.save_fixture(positions, fixture_path)

    _llm_mod.set_thinking(thinking)

    tracer = _eg.LLMTracer(_llm_mod._call_lm)
    _llm_mod._call_lm = tracer

    print(f"\n── Commentary (LLM, raw prompt) ──")
    traces: list[dict] = []
    for i in range(len(positions)):
        san = positions[i].get("san") or "start"
        print(f"  [{i:>3}/{len(positions)-1}] {san:<8}", end="", flush=True)
        t0 = time.perf_counter()
        trace = build_raw_position_trace(positions, i, our_side, config, tracer)
        elapsed = time.perf_counter() - t0
        traces.append(trace)

        pos_calls = trace.get("lm_calls", [])
        flags = ""
        if len(pos_calls) > 1: flags += "↺ "
        if trace.get("commentary_empty"): flags += "⚠EMPTY "
        if any(c.get("is_think_only") for c in pos_calls): flags += "⚠THINK"
        print(f"  {elapsed:5.1f}s  calls={len(pos_calls)}  "
              f"len={trace.get('commentary_chars',0):>4}  {flags}")

    _llm_mod._call_lm = tracer._real

    _eg.print_summary(traces, game_header, config_label)

    if args.out:
        out_path = pathlib.Path(args.out)
    else:
        results_dir = ROOT / "tests" / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        out_path = results_dir / f"eval_trace_raw_{int(time.time())}.json"

    def _serialise(obj):
        if isinstance(obj, dict):
            return {k: _serialise(v) for k, v in obj.items() if k != "alexander_result"}
        if isinstance(obj, list):
            return [_serialise(v) for v in obj]
        return obj

    out_path.write_text(json.dumps({
        "game":            game_header,
        "run_config":      rc,
        "run_config_file": str(run_config_path),
        "config":          config_label,
        "thinking":        thinking,
        "max_tokens":      config.max_tokens,
        "analysis_depth":  ANALYSIS_DEPTH,
        "fixture":         str(fixture_path),
        "traces":          [_serialise(t) for t in traces],
    }, ensure_ascii=False, indent=2))
    print(f"LLM trace saved → {out_path}")


if __name__ == "__main__":
    main()
