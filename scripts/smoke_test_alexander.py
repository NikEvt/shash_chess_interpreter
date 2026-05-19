"""
Smoke test for the Alexander chess interpreter package.

Tests:
  1. Prompt builder produces well-structured output (dry-run, no engine needed)
  2. AlexanderEngine connects to Alexander binary and returns valid data (live engine)
  3. LLM produces acceptable commentary (live LLM)

Run:
    python3 scripts/smoke_test_alexander.py --dry-run           # prompt only
    python3 scripts/smoke_test_alexander.py --engine-only       # engine + prompt, no LLM
    python3 scripts/smoke_test_alexander.py                     # full: engine + LLM
    python3 scripts/smoke_test_alexander.py --engine PATH       # override binary path
    python3 scripts/smoke_test_alexander.py -o report.md        # custom output file
"""
import sys
import argparse
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

# Allow running from scripts/ — insert project root so alexander_interpreter is found
sys.path.insert(0, str(Path(__file__).parent.parent))

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
from alexander_interpreter.config import ENGINE_THREADS, ENGINE_HASH_MB, LM_STUDIO_URL, MODEL_NAME
from alexander_interpreter.types import TopMove, EvalTrace

try:
    from alexander_interpreter.llm import ask, LMStudioError
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False


# ── Test positions ─────────────────────────────────────────────────────────────
# 10 positions covering all major Shashin zones: High/Middle Tal, Capablanca,
# Low/Middle/High Petrosian, and transitions.

_POSITIONS: list[dict] = [
    # 1. Equal opening — CAPABLANCA (~50%)
    {
        "fen": "rnbqkbnr/pppp1ppp/4p3/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
        "played_uci": "d2d4", "played_san": "d4",
        "label": "equal_opening",
    },
    # 2. Balanced middlegame — CAPABLANCA_PETROSIAN (strategic, equal)
    {
        "fen": "rn1q1rk1/1b2bppp/p2ppn2/1p6/3NPP2/1BN1B3/PPP3PP/R2Q1RK1 w - - 0 1",
        "played_uci": "e4e5", "played_san": "e5",
        "label": "middlegame_balanced",
    },
    # 3. Slight White advantage — CAPABLANCA_TAL (60% win), d5 pawn push
    {
        "fen": "r1bq1rk1/1pp2ppp/p1np1n2/4p3/1bBPP3/2N2N2/PP3PPP/R1BQR1K1 w - - 2 9",
        "played_uci": "d4d5", "played_san": "d5",
        "label": "strategic_d5_push",
    },
    # 4. QGD development — CAPABLANCA (near-equal, positional)
    {
        "fen": "rnbq1rk1/ppp1bppp/4pn2/3p4/2PP4/2NBP3/PP3PPP/R1BQK1NR w KQ - 4 7",
        "played_uci": "g1f3", "played_san": "Nf3",
        "label": "qgd_development",
    },
    # 5. Tactical — MIDDLE_TAL (84-89%), bishop captures key defender
    {
        "fen": "r2qkb1r/ppp2ppp/2np1n2/4p1B1/4P3/3P1N2/PPP2PPP/RN1QKB1R w KQkq - 2 7",
        "played_uci": "g5f6", "played_san": "Bxf6",
        "label": "bishop_captures_knight",
    },
    # 6. Tactical winning — HIGH_TAL (95%), piece sacrifice with attack
    {
        "fen": "1r3rk1/3bqNbp/pp1p2p1/2pB4/P2PP1n1/2P1B3/1P1Q2PP/R4RK1 w - - 0 1",
        "played_uci": "f7d8", "played_san": "Nd8+",
        "label": "tactical_winning",
    },
    # 7. Forced mate — HIGH_TAL (97%), queen + king mating net
    {
        "fen": "8/8/8/8/5K2/3Q4/8/6k1 w - - 0 1",
        "played_uci": "f4g3", "played_san": "Kg3",
        "label": "forced_mate",
    },
    # 8. Rook endgame conversion — LOW_TAL (77%), rook cuts off king
    {
        "fen": "8/5k2/R7/5P2/8/8/8/5K2 w - - 0 1",
        "played_uci": "a6a7", "played_san": "Ra7",
        "label": "rook_endgame_win",
    },
    # 9. Slight disadvantage — LOW_PETROSIAN (22%), Black must defend actively
    {
        "fen": "r1b2rk1/pp1nqppp/2p1pn2/3p2B1/2PP4/2N2NP1/PP2PPBP/R2Q1RK1 b - - 0 10",
        "played_uci": "f6h5", "played_san": "Nh5",
        "label": "positional_disadvantage",
    },
    # 10. Defensive — HIGH_PETROSIAN (2%), must build fortress
    {
        "fen": "2N5/P7/2b2p2/3k3P/8/4K3/8/8 b - - 0 1",
        "played_uci": "d5e5", "played_san": "Ke5",
        "label": "fortress_defense",
    },
]


# ── Mock result builder ────────────────────────────────────────────────────────
# WDL and score_cp for each position when running in dry-run / without engine.
# Format: (wdl_win, wdl_draw, wdl_loss, score_cp, mate_in)

_MOCK_WDL: dict[str, tuple[int, int, int, Optional[int], Optional[int]]] = {
    "equal_opening":            (450, 440, 110,   30, None),
    "middlegame_balanced":      (450, 440, 110,   25, None),
    "strategic_d5_push":        (610, 280, 110,   80, None),
    "qgd_development":          (520, 380, 100,   25, None),
    "bishop_captures_knight":   (580, 290, 130,   70, None),
    "tactical_winning":         (950,  40,  10,  450, None),
    "forced_mate":              (970,  20,  10, None,    2),
    "rook_endgame_win":         (770, 160,  70,  250, None),
    "positional_disadvantage":  (220, 360, 420,  -90, None),
    "fortress_defense":         ( 20, 100, 880, -400, None),
}


def _mock_result(pos: dict) -> AlexanderResult:
    """Build a plausible AlexanderResult without a live engine."""
    board = chess.Board(pos["fen"])
    side = "white" if board.turn == chess.WHITE else "black"

    wdl_win, wdl_draw, wdl_loss, score_cp, mate_in = _MOCK_WDL[pos["label"]]
    zone = win_prob_to_shashin_zone(wdl_win / 10.0)

    alt_score = (score_cp or 0) - 30
    top_moves = [
        TopMove(
            uci=pos["played_uci"], san=pos["played_san"],
            score_cp=score_cp, mate_in=mate_in,
            wdl_win=wdl_win, wdl_draw=wdl_draw, wdl_loss=wdl_loss,
            depth=20, seldepth=24, pv_san=[pos["played_san"]],
        ),
        TopMove(
            uci="e2e4", san="e4",
            score_cp=alt_score, mate_in=None,
            wdl_win=max(0, wdl_win - 80), wdl_draw=wdl_draw,
            wdl_loss=min(1000, wdl_loss + 80),
            depth=20, seldepth=24, pv_san=["e4"],
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
        pv_san=[pos["played_san"]],
        depth=20,
        seldepth=24,
        eval_trace=EvalTrace(
            best_win_pct=float(wdl_win) / 10.0,
            components={"mobility": 0.5, "king_safety": -0.3},
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
    return CheckResult("non_empty", ok, "" if ok else "empty response")


def check_length(response: str, **_) -> CheckResult:
    words = len(response.split())
    ok = 10 <= words <= 150
    return CheckResult("length_10_150_words", ok, f"{words} words")


def check_mentions_best_move(response: str, result: AlexanderResult, **_) -> CheckResult:
    san = result.best_move_san.rstrip("+#")
    if not san:
        return CheckResult("mentions_best_move", True, "no best move — skip")
    found = san.lower() in response.lower()
    return CheckResult("mentions_best_move", found,
                       f"'{san}' {'found' if found else 'NOT found'}")


def check_no_fen_leak(response: str, result: AlexanderResult, **_) -> CheckResult:
    leaked = result.fen[:20] in response
    return CheckResult("no_fen_leak", not leaked,
                       "FEN fragment leaked" if leaked else "")


def check_no_uci_leak(response: str, result: AlexanderResult, **_) -> CheckResult:
    uci = result.best_move_uci
    if not uci:
        return CheckResult("no_uci_leak", True, "no UCI to check")
    leaked = uci in response
    return CheckResult("no_uci_leak", not leaked,
                       f"UCI '{uci}' leaked" if leaked else "")


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
        return CheckResult("move_comparison", True, "same move or no played — skip")
    best_c = best.rstrip("+#")
    played_c = played.rstrip("+#")
    has_best = best_c.lower() in response.lower()
    has_played = played_c.lower() in response.lower()
    ok = has_best and has_played
    return CheckResult(
        "move_comparison", ok,
        f"best={best_c}{'✓' if has_best else '✗'} played={played_c}{'✓' if has_played else '✗'}",
    )


# Checks that run even in dry-run (don't need LLM response)
_PROMPT_CHECKS: set[Callable] = {check_shashin_zone_valid, check_top_moves_present}

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


# ── Question / level selection ─────────────────────────────────────────────────

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
    prompt = build_tiny_prompt(
        result,
        prev_eval_cp=None,
        curr_eval_cp=result.score_cp,
        curr_eval_mate=result.mate_in,
        our_side=our_side,
        question_type=question,
        board_before=None,
        eval_loss=None,
    )

    if dry_run:
        response = "[DRY RUN]"
    else:
        try:
            response = ask(prompt, max_tokens=350)
        except Exception as e:
            response = f"[LLM ERROR: {e}]"

    checks = [
        c(response=response, result=result)
        if (not dry_run or c in _PROMPT_CHECKS)
        else CheckResult(c.__name__, True, "skipped (dry run)")
        for c in CHECKS
    ]

    return CaseResult(
        label=pos["label"],
        level=_auto_level(result),
        question=question,
        prompt=prompt,
        response=response,
        checks=checks,
        engine_data=engine_data,
        raw_eval_lines=result.raw_eval_lines,
    )


# ── Console output ────────────────────────────────────────────────────────────

def print_case(case: CaseResult, verbose: bool) -> None:
    status = "PASS" if case.passed else "FAIL"
    engine_info = ""
    if case.engine_data:
        d = case.engine_data
        engine_info = (
            f" | zone={d['zone']} depth={d['depth']}"
            f" pv={d['num_pv']} trace={'✓' if d['has_eval_trace'] else '✗'}"
        )
    print(f"\n[{status}] {case.label} | level={case.level} | q={case.question}{engine_info}")

    if case.raw_eval_lines:
        sep = "─" * 60
        print(f"  ┌{sep}┐")
        print(f"  │ Engine eval ({len(case.raw_eval_lines)} lines)")
        print(f"  ├{sep}┤")
        for line in case.raw_eval_lines:
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


def _write_report(
    results: list[CaseResult],
    path: Path,
    dry_run: bool,
    elapsed: float,
    mode: str,
) -> None:
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

    for case in results:
        status = "✅ PASS" if case.passed else "❌ FAIL"
        zone = case.engine_data["zone"] if case.engine_data else "mock"
        lines += [
            f"## {status} — {case.label}",
            "",
            "| | |",
            "|---|---|",
            f"| Position | `{case.label}` |",
            f"| Shashin zone | `{zone}` |",
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
    parser.add_argument("--dry-run", action="store_true",
                        help="No engine, no LLM — test prompt builder only")
    parser.add_argument("--engine-only", action="store_true",
                        help="Engine + prompt, skip LLM")
    parser.add_argument("--engine", default=ENGINE_PATH,
                        help="Path to Alexander binary")
    parser.add_argument("--depth", type=int, default=ENGINE_DEPTH)
    parser.add_argument("--num-pv", type=int, default=ENGINE_NUM_PV)
    parser.add_argument("--our-side", choices=["white", "black"], default="white",
                        help="Which side is the human player")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("-o", "--output", default="smoke_results_alexander.md")
    args = parser.parse_args()

    use_engine = not args.dry_run
    use_llm = not args.dry_run and not args.engine_only

    mode_parts = []
    if args.dry_run:
        mode_parts.append("dry-run (prompt only)")
    else:
        mode_parts.append(
            f"engine={Path(args.engine).name} depth={args.depth} pv={args.num_pv}"
        )
        mode_parts.append("no-LLM" if not use_llm else f"LLM={MODEL_NAME}")
    mode = ", ".join(mode_parts)

    print(f"Mode          : {mode}")
    print(f"Our side      : {args.our_side}")
    print(f"Test cases    : {len(_POSITIONS)}")
    print()

    engine: Optional[AlexanderEngine] = None
    if use_engine:
        engine_path = Path(args.engine)
        if not engine_path.exists():
            print(f"WARNING: Alexander binary not found at {engine_path}")
            print("  Compile: cd Alexander/src && make -j$(nproc) build ARCH=apple-silicon COMP=clang")
            print("  Or set ALEXANDER_ENGINE_PATH / pass --engine PATH")
            print("  Falling back to mock positions...\n")
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
        for pos in _POSITIONS:
            case = run_case(
                pos,
                dry_run=not use_llm,
                use_engine=use_engine,
                engine=engine,
                our_side=args.our_side,
            )
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
