"""
Smoke test for the Alexander chess interpreter package.

Tests:
  1. Prompt builder produces well-structured output (dry-run, no engine needed)
  2. AlexanderEngine connects to Alexander binary and returns valid data (live engine)
  3. LLM produces acceptable commentary (live LLM)

Run:
    python3 smoke_test_alexander.py                     # prompt + engine + LLM
    python3 smoke_test_alexander.py --dry-run           # prompt only (no engine, no LLM)
    python3 smoke_test_alexander.py --engine-only       # prompt + engine, skip LLM
    python3 smoke_test_alexander.py --engine PATH       # override engine binary path
    python3 smoke_test_alexander.py -o my_report.md     # custom report file
"""
import sys
import argparse
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent))

import chess

from alexander_interpreter import (
    AlexanderResult,
    AlexanderEngine,
    build_tiny_prompt,
    win_prob_to_shashin_zone,
    ENGINE_PATH,
    ENGINE_DEPTH,
    ENGINE_NUM_PV,
)
from alexander_interpreter.config import ENGINE_THREADS, ENGINE_HASH_MB
from alexander_interpreter.types import TopMove, EvalTrace
from alexander_interpreter.config import LM_STUDIO_URL, MODEL_NAME

try:
    from alexander_interpreter.llm import ask, LMStudioError
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

# ── Shared test positions (FEN + played move UCI) ────────────────────────────
# Converted from mock_engine.py, supplemented with Alexander-specific data.

_MOCK_POSITIONS: list[dict] = [
    # Equal opening
    {"fen": "rnbqkbnr/pppp1ppp/4p3/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
     "played_uci": "d2d4", "played_san": "d4", "label": "equal_opening"},
    # Balanced middlegame (Capablanca)
    {"fen": "rn1q1rk1/1b2bppp/p2ppn2/1p6/3NPP2/1BN1B3/PPP3PP/R2Q1RK1 w - - 0 1",
     "played_uci": "e4e5", "played_san": "e5", "label": "middlegame_balanced"},
    # Tactical (Tal) — White winning
    {"fen": "1r3rk1/3bqNbp/pp1p2p1/2pB4/P2PP1n1/2P1B3/1P1Q2PP/R4RK1 w - - 0 1",
     "played_uci": "f7d8", "played_san": "Nd8+", "label": "tactical_winning"},
    # Forced mate in 2
    {"fen": "8/8/8/8/5K2/3Q4/8/6k1 w - - 0 1",
     "played_uci": "f4g3", "played_san": "Kg3", "label": "mate_in_2"},
    # Defensive (Petrosian) — Black losing
    {"fen": "2N5/P7/2b2p2/3k3P/8/4K3/8/8 b - - 0 1",
     "played_uci": "d5e5", "played_san": "Ke5", "label": "defensive"},
    # Endgame — rook + pawn
    {"fen": "8/5ppk/1p3b2/p7/3Pq3/1KP1n1P1/7P/1R2R3 b - - 0 1",
     "played_uci": "e4c2", "played_san": "Qc2+", "label": "endgame_tactics"},
]


def _mock_result(pos: dict) -> AlexanderResult:
    """Build a plausible AlexanderResult from a mock position (no engine needed)."""
    board = chess.Board(pos["fen"])
    side = "white" if board.turn == chess.WHITE else "black"

    # Synthetic WDL based on expected position type
    label = pos["label"]
    if "winning" in label or "mate" in label:
        wdl_win, wdl_draw, wdl_loss = 950, 40, 10
        score_cp, mate_in = 450, None
    elif "defensive" in label:
        wdl_win, wdl_draw, wdl_loss = 20, 100, 880
        score_cp, mate_in = -400, None
    elif "endgame_tactics" in label:
        wdl_win, wdl_draw, wdl_loss = 900, 80, 20
        score_cp, mate_in = 600, None
    else:
        wdl_win, wdl_draw, wdl_loss = 450, 440, 110
        score_cp, mate_in = 30, None

    zone = win_prob_to_shashin_zone(wdl_win / 10.0)

    # Synthetic top moves
    top_moves = [
        TopMove(
            uci=pos["played_uci"], san=pos["played_san"],
            score_cp=score_cp, mate_in=mate_in,
            wdl_win=wdl_win, wdl_draw=wdl_draw, wdl_loss=wdl_loss,
            depth=20, seldepth=24, pv_san=[pos["played_san"], "Nf6", "d4"],
        ),
        TopMove(
            uci="e2e4", san="e4",
            score_cp=(score_cp or 0) - 30, mate_in=None,
            wdl_win=max(0, wdl_win - 80), wdl_draw=wdl_draw, wdl_loss=min(1000, wdl_loss + 80),
            depth=20, seldepth=24, pv_san=["e4", "e5"],
        ),
    ]

    return AlexanderResult(
        fen=pos["fen"],
        side_to_move=side,
        played_move=pos["played_san"],
        best_move_uci=pos["played_uci"],
        best_move_san=pos["played_san"],
        score_cp=score_cp,
        mate_in=mate_in,
        wdl_win=wdl_win,
        wdl_draw=wdl_draw,
        wdl_loss=wdl_loss,
        shashin_zone=zone,
        top_moves=top_moves,
        pv_san=[pos["played_san"], "Nf6", "d4"],
        depth=20,
        seldepth=24,
        eval_trace=EvalTrace(
            best_win_pct=float(wdl_win) / 10.0,
            components={"expansion_delta": 0.0, "best_activity": 52.0},
        ),
    )


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class CaseResult:
    label: str
    level: str
    question: str
    prompt: str
    response: str
    checks: list[CheckResult]
    engine_data: Optional[dict] = None
    raw_eval_lines: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)


# ── Checks ────────────────────────────────────────────────────────────────────

def check_non_empty(response: str, **_) -> CheckResult:
    ok = bool(response and response.strip())
    return CheckResult("non_empty", ok, "" if ok else "Empty response")


def check_length(response: str, **_) -> CheckResult:
    words = len(response.split())
    ok = 10 <= words <= 150
    return CheckResult("length_10_150_words", ok, f"{words} words")


def check_mentions_best_move(response: str, result: AlexanderResult, **_) -> CheckResult:
    san = result.best_move_san.rstrip("+#")
    if not san:
        return CheckResult("mentions_best_move", True, "no best move — skip")
    found = san.lower() in response.lower()
    return CheckResult("mentions_best_move", found, f"'{san}' {'found' if found else 'NOT found'}")


def check_no_fen_leak(response: str, result: AlexanderResult, **_) -> CheckResult:
    fragment = result.fen[:25]
    leaked = fragment in response
    return CheckResult("no_fen_leak", not leaked, "FEN fragment leaked" if leaked else "")


def check_no_uci_leak(response: str, result: AlexanderResult, **_) -> CheckResult:
    uci = result.best_move_uci
    if not uci:
        return CheckResult("no_uci_leak", True, "no UCI to check")
    leaked = uci in response
    return CheckResult("no_uci_leak", not leaked, f"UCI '{uci}' leaked" if leaked else "")


def check_english(response: str, **_) -> CheckResult:
    markers = {"the", "is", "a", "to", "and", "of", "in", "for", "move", "position"}
    hits = markers & set(response.lower().split())
    ok = len(hits) >= 3
    return CheckResult("is_english", ok, f"markers: {hits}")


def check_shashin_zone_valid(result: AlexanderResult, **_) -> CheckResult:
    from alexander_interpreter.shashin import ZONES
    valid = result.shashin_zone in ZONES
    return CheckResult(
        "shashin_zone_valid", valid,
        f"zone='{result.shashin_zone}'" + ("" if valid else " NOT IN ZONES"),
    )


def check_top_moves_present(result: AlexanderResult, **_) -> CheckResult:
    ok = len(result.top_moves) >= 1
    return CheckResult("top_moves_present", ok, f"{len(result.top_moves)} top moves")


def check_move_comparison(response: str, result: AlexanderResult, **_) -> CheckResult:
    played = result.played_move
    best = result.best_move_san
    if not played or played == best or not best:
        return CheckResult("move_comparison", True, "same move or no played move — skip")
    best_c = best.rstrip("+#")
    played_c = played.rstrip("+#")
    has_best = best_c.lower() in response.lower()
    has_played = played_c.lower() in response.lower()
    ok = has_best and has_played
    return CheckResult("move_comparison", ok, f"best={best_c}{'✓' if has_best else '✗'} played={played_c}{'✓' if has_played else '✗'}")


CHECKS: list[Callable] = [
    check_non_empty,
    check_length,
    check_mentions_best_move,
    check_no_fen_leak,
    check_no_uci_leak,
    check_english,
    check_shashin_zone_valid,
    check_top_moves_present,
    check_move_comparison,
]

PROMPT_ONLY_CHECKS = [check_shashin_zone_valid, check_top_moves_present]


# ── Auto level/question ───────────────────────────────────────────────────────

def _auto_level(r: AlexanderResult) -> str:
    if r.mate_in is not None:
        return "intermediate"
    if r.score_cp is None:
        return "beginner"
    if abs(r.score_cp) > 300:
        return "advanced"
    if abs(r.score_cp) > 100:
        return "intermediate"
    return "beginner"


def _auto_question(r: AlexanderResult) -> str:
    if r.played_move and r.best_move_san and r.played_move != r.best_move_san:
        return "best_move"
    if r.mate_in is not None:
        return "best_move"
    if "PETROSIAN" in r.shashin_zone:
        return "plan"
    if "TAL" in r.shashin_zone:
        return "best_move"
    return "explain"


# ── Runner ────────────────────────────────────────────────────────────────────

def run_case(
    pos: dict,
    dry_run: bool,
    use_engine: bool,
    engine: Optional[AlexanderEngine],
    our_side: str = "white",
) -> CaseResult:
    # Get AlexanderResult
    engine_data: Optional[dict] = None
    if use_engine and engine is not None:
        board = chess.Board(pos["fen"])
        result = engine.analyze(pos["fen"], pos["played_uci"], board)
        engine_data = {
            "zone": result.shashin_zone,
            "score": result.score_cp,
            "depth": result.depth,
            "num_pv": len(result.top_moves),
            "has_eval_trace": result.eval_trace is not None,
        }
    else:
        result = _mock_result(pos)

    question = _auto_question(result)
    # smoke_test has no prev position, pass None for prev_eval_cp
    prompt = build_tiny_prompt(
        result,
        prev_eval_cp=None,
        curr_eval_cp=result.score_cp,
        curr_eval_mate=result.mate_in,
        our_side=our_side,
        question_type=question,
        board_before=None,     # no prev board in smoke_test
        eval_loss=None,
    )

    if dry_run:
        response = "[DRY RUN]"
    else:
        try:
            response = ask(prompt, max_tokens=350)
        except Exception as e:
            response = f"[LLM ERROR: {e}]"

    prompt_only_fns = set(PROMPT_ONLY_CHECKS)
    checks = [
        c(response=response, result=result) if (not dry_run or c in prompt_only_fns)
        else CheckResult(c.__name__, True, "skipped (dry run)")
        for c in CHECKS
    ]

    return CaseResult(
        label=pos["label"],
        level="tiny",
        question=question,
        prompt=prompt,
        response=response,
        checks=checks,
        engine_data=engine_data,
        raw_eval_lines=result.raw_eval_lines,
    )


def print_case(case: CaseResult, verbose: bool) -> None:
    status = "PASS" if case.passed else "FAIL"
    engine_info = ""
    if case.engine_data:
        d = case.engine_data
        engine_info = f" | zone={d['zone']} depth={d['depth']} pv={d['num_pv']} trace={'✓' if d['has_eval_trace'] else '✗'}"
    print(f"\n[{status}] {case.label} | level={case.level} | q={case.question}{engine_info}")
    if case.raw_eval_lines:
        sep = "─" * 60
        print(f"  ┌{sep}┐")
        print(f"  │ Engine eval output ({len(case.raw_eval_lines)} lines){' ' * (60 - 26 - len(str(len(case.raw_eval_lines))))}│")
        print(f"  ├{sep}┤")
        for line in case.raw_eval_lines:
            # Truncate very long lines to keep output readable
            display = line if len(line) <= 100 else line[:97] + "..."
            print(f"  │ {display}")
        print(f"  └{sep}┘")
    if verbose or not case.passed:
        print("  Prompt:")
        for line in case.prompt.splitlines():
            print(f"    {line}")
        print("  Response:")
        print(textwrap.indent(case.response, "    "))
    for c in case.checks:
        mark = "✓" if c.passed else "✗"
        detail = f"  — {c.detail}" if c.detail else ""
        print(f"  {mark} {c.name}{detail}")


# ── Markdown report ───────────────────────────────────────────────────────────

def _write_report(results: list[CaseResult], path: Path, dry_run: bool, elapsed: float, mode: str) -> None:
    from alexander_interpreter import shashin as shashin_mod

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    icon = "✅" if passed == total else "❌"

    lines: list[str] = [
        "# Alexander Chess Interpreter — Smoke Test",
        "",
        f"**Date:** {ts}  ",
        f"**Mode:** {mode}  ",
        f"**Model:** {MODEL_NAME}  ",
        f"**Engine depth:** {ENGINE_DEPTH}  ",
        f"**MultiPV:** {ENGINE_NUM_PV}  ",
        f"**Result:** {icon} {passed}/{total} passed  ",
        f"**Time:** {elapsed:.1f}s",
        "",
        "---",
        "",
    ]

    _CHECK_LABELS = {
        "non_empty":             "Non-empty response",
        "length_10_150_words":   "Length 10–150 words",
        "mentions_best_move":    "Mentions best move",
        "no_fen_leak":           "No FEN leak",
        "no_uci_leak":           "No UCI notation leak",
        "is_english":            "Response in English",
        "shashin_zone_valid":    "Shashin zone is valid",
        "top_moves_present":     "Top moves present",
        "move_comparison":       "Compares played vs best move",
    }

    for case in results:
        status = "✅ PASS" if case.passed else "❌ FAIL"
        lines += [
            f"## {status} — {case.label}",
            "",
            f"| | |",
            f"|---|---|",
            f"| Position | `{case.label}` |",
            f"| Shashin zone | `{case.engine_data['zone'] if case.engine_data else 'mock'}` |",
            f"| Level | {case.level} |",
            f"| Question | {case.question} |",
        ]
        if case.engine_data:
            d = case.engine_data
            lines += [
                f"| Engine depth | {d['depth']} |",
                f"| Top moves | {d['num_pv']} |",
                f"| Eval trace | {'✅' if d['has_eval_trace'] else '—'} |",
            ]
        lines += ["", "### Checks", "", "| Check | Result | Detail |", "|---|---|---|"]
        for c in case.checks:
            label = _CHECK_LABELS.get(c.name, c.name)
            icon2 = "✅" if c.passed else "❌"
            lines.append(f"| {label} | {icon2} | {c.detail or '—'} |")

        lines += [
            "",
            "### Agent response",
            "",
            f"> {case.response.replace(chr(10), '  \\n> ')}",
            "",
            "<details>",
            "<summary>Prompt sent to model</summary>",
            "",
            "```",
            case.prompt,
            "```",
            "",
            "</details>",
            "",
            "---",
            "",
        ]

    path.write_text("\n".join(lines), encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for Alexander interpreter")
    parser.add_argument("--dry-run", action="store_true", help="No engine, no LLM — test prompt builder only")
    parser.add_argument("--engine-only", action="store_true", help="Engine + prompt, no LLM")
    parser.add_argument("--engine", default=ENGINE_PATH, help="Path to Alexander binary")
    parser.add_argument("--depth", type=int, default=ENGINE_DEPTH)
    parser.add_argument("--num-pv", type=int, default=ENGINE_NUM_PV)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("-o", "--output", default="smoke_results_alexander.md")
    parser.add_argument("--our-side", choices=["white", "black"], default="white",
                        help="Which side is the human player (affects commentary framing)")
    args = parser.parse_args()

    use_engine = not args.dry_run
    use_llm = not args.dry_run and not args.engine_only

    mode_parts = []
    if args.dry_run:
        mode_parts.append("dry-run (prompt only)")
    else:
        mode_parts.append(f"engine={Path(args.engine).name} depth={args.depth} pv={args.num_pv}")
        if not use_llm:
            mode_parts.append("no-LLM")
        else:
            mode_parts.append(f"LLM={MODEL_NAME}")
    mode = ", ".join(mode_parts)

    print(f"Mode          : {mode}")
    print(f"Our side      : {args.our_side}")
    print(f"Test cases    : {len(_MOCK_POSITIONS)}")
    print()

    engine: Optional[AlexanderEngine] = None
    if use_engine:
        engine_path = Path(args.engine)
        if not engine_path.exists():
            print(f"ERROR: Alexander binary not found at {engine_path}")
            print("Compile with: cd Alexander/src && make -j$(nproc) build ARCH=apple-silicon COMP=clang")
            print("Then set ALEXANDER_ENGINE_PATH or pass --engine PATH")
            print("Falling back to mock positions...")
            use_engine = False
        else:
            engine = AlexanderEngine(
                str(engine_path),
                depth=args.depth,
                num_pv=args.num_pv,
                threads=ENGINE_THREADS,
                hash_mb=ENGINE_HASH_MB,
            )
            engine.start()
            print(f"Engine        : {engine_path}")

    print("=" * 60)

    start = datetime.now()
    results: list[CaseResult] = []
    try:
        for pos in _MOCK_POSITIONS:
            case = run_case(pos, dry_run=not use_llm, use_engine=use_engine, engine=engine,
                            our_side=args.our_side)
            results.append(case)
            print_case(case, args.verbose)
    finally:
        if engine:
            engine.stop()

    elapsed = (datetime.now() - start).total_seconds()

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"Result: {passed}/{total} passed  ({elapsed:.1f}s)")

    out = Path(args.output)
    _write_report(results, out, not use_llm, elapsed, mode)
    print(f"Report → {out.resolve()}")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
