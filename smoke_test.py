"""
Smoke tests for the chess analysis agent.

Checks:
  1. Prompt builder produces non-empty, well-structured output
  2. LLM returns a non-empty response
  3. Response length is within expected range (not truncated, not hallucinated wall of text)
  4. Response mentions the best move (key factual anchor)
  5. Response does not contain raw FEN or UCI notation leaking into user-facing text
  6. Response is in English

Run:
    cd agent && python3 smoke_test.py               # live, writes smoke_results.md
    cd agent && python3 smoke_test.py --dry-run     # skips LLM calls
    cd agent && python3 smoke_test.py -o report.md  # custom output file
"""

import sys
import argparse
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from mamka.shash_chess_interpreter.mock_engine import MOCK_POSITIONS, EngineResult
from mamka.shash_chess_interpreter.prompt import build_prompt
from mamka.shash_chess_interpreter.shashin import report_description
from mamka.shash_chess_interpreter.config import LM_STUDIO_URL, MODEL_NAME

try:
    from mamka.shash_chess_interpreter.llm import ask, LMStudioError
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False


# ── result types ─────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class CaseResult:
    position_key: str
    level: str
    question: str
    prompt: str
    response: str
    checks: list[CheckResult]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)


# ── checks ────────────────────────────────────────────────────────────────────

def check_non_empty(response: str, **_) -> CheckResult:
    ok = bool(response and response.strip())
    return CheckResult("non_empty", ok, "" if ok else "Response is empty")


def check_length(response: str, **_) -> CheckResult:
    words = len(response.split())
    ok = 10 <= words <= 120
    return CheckResult("length_10_120_words", ok, f"{words} words")


def check_mentions_best_move(response: str, result: EngineResult, **_) -> CheckResult:
    san = result.best_move_san.rstrip("+#")
    # Accept either SAN (Bb5) or the piece name in lowercase
    found = san.lower() in response.lower() or san in response
    return CheckResult(
        "mentions_best_move",
        found,
        f"Expected '{san}' in response" if not found else f"Found '{san}'",
    )


def check_no_fen_leak(response: str, result: EngineResult, **_) -> CheckResult:
    # FEN contains slashes and spaces in a telltale pattern — flag if >20 chars of FEN appear
    fen_fragment = result.fen[:25]
    leaked = fen_fragment in response
    return CheckResult("no_fen_leak", not leaked, "FEN fragment found in response" if leaked else "")


def check_no_uci_leak(response: str, result: EngineResult, **_) -> CheckResult:
    # UCI moves are 4-5 lowercase chars like "e2e4" or "e1g1" — model should use SAN
    uci = result.best_move_uci
    leaked = uci in response
    return CheckResult("no_uci_leak", not leaked, f"UCI move '{uci}' found in response" if leaked else "")


def check_english(response: str, **_) -> CheckResult:
    # Heuristic: common English words must appear
    markers = {"the", "is", "a", "to", "and", "of", "in", "for", "move", "position"}
    words_lower = set(response.lower().split())
    hits = markers & words_lower
    ok = len(hits) >= 3
    return CheckResult("is_english", ok, f"English markers found: {hits}" if ok else f"Too few markers: {hits}")


def check_mentions_move_comparison(response: str, result: EngineResult, **_) -> CheckResult:
    played = getattr(result, "played_move", None)
    best = result.best_move_san
    if not played or played == best:
        return CheckResult("mentions_move_comparison", True, "moves identical — skip")
    best_clean = best.rstrip("+#")
    played_clean = played.rstrip("+#")
    has_best = best_clean.lower() in response.lower() or best_clean in response
    has_played = played_clean.lower() in response.lower() or played_clean in response
    passed = has_best and has_played
    detail = f"best='{best_clean}' {'✓' if has_best else '✗'}, played='{played_clean}' {'✓' if has_played else '✗'}"
    return CheckResult("mentions_move_comparison", passed, detail)


CHECKS: list[Callable[..., CheckResult]] = [
    check_non_empty,
    check_length,
    check_mentions_best_move,
    check_no_fen_leak,
    check_no_uci_leak,
    check_english,
    check_mentions_move_comparison,
]


# ── test cases ────────────────────────────────────────────────────────────────

def _auto_level(score_cp, mate_in):
    """Assign player level based on position complexity."""
    if mate_in is not None:
        return "intermediate"
    if score_cp is None:
        return "beginner"
    if abs(score_cp) > 300:
        return "advanced"
    if abs(score_cp) > 100:
        return "intermediate"
    return "beginner"


def _auto_question(score_cp, mate_in, shashin_type, played_move=None, best_move_san=None):
    if played_move and best_move_san and played_move != best_move_san:
        return "best_move"
    if mate_in is not None:
        return "best_move"
    if shashin_type == "Petrosian":
        return "plan"
    if shashin_type == "Tal":
        return "best_move"
    return "explain"


# Build TEST_MATRIX from all positions in mock_engine.py
from mamka.shash_chess_interpreter.mock_engine import MOCK_POSITIONS
TEST_MATRIX = [
    (key, [r.played_move], _auto_level(r.score_cp, r.mate_in), _auto_question(r.score_cp, r.mate_in, r.shashin_type, r.played_move, r.best_move_san))
    for key, r in MOCK_POSITIONS.items()
]


# ── runner ────────────────────────────────────────────────────────────────────

def run_case(
    position_key: str,
    moves: list[str],
    level: str,
    question: str,
    dry_run: bool,
) -> CaseResult:
    result = MOCK_POSITIONS[position_key]
    prompt = build_prompt(result, moves, level, question)

    if dry_run:
        response = "[DRY RUN — no LLM call]"
    else:
        try:
            tokens = 450 if result.played_move == result.best_move_san else 600
            response = ask(prompt, max_tokens=tokens)
        except LMStudioError as e:
            response = f"[LLM ERROR: {e}]"

    checks = [c(response=response, result=result) for c in CHECKS]

    # In dry-run mode skip checks that require a real response
    if dry_run:
        checks = [CheckResult(c.name, True, "skipped (dry run)") for c in checks]

    return CaseResult(position_key, level, question, prompt, response, checks)


def print_case(case: CaseResult, verbose: bool) -> None:
    status = "PASS" if case.passed else "FAIL"
    print(f"\n[{status}] {case.position_key} | level={case.level} | q={case.question}")

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


# ── markdown report ───────────────────────────────────────────────────────────

_CHECK_LABELS = {
    "non_empty":               "Non-empty response",
    "length_10_120_words":     "Length 10–120 words",
    "mentions_best_move":      "Mentions best move",
    "no_fen_leak":             "No FEN leak",
    "no_uci_leak":             "No UCI leak",
    "is_english":              "Response in English",
    "mentions_move_comparison": "Compares played vs best move",
}

_POSITION_DESCRIPTIONS = {
    "opening_equal":       "Equal opening after 1.e4 e5 2.Nf3 (Ruy Lopez)",
    "sicilian_white_edge": "Sicilian Defence, White has slight initiative",
    "winning_tactics":     "Italian Game, White has +2.0 advantage",
    "endgame_winning":     "King & pawn endgame, White winning",
    "mate_in_2":           "Forced checkmate in 1",
    "black_defensive":     "Black in defensive Petrosian setup",
}


def _write_report(
    results: list[CaseResult],
    path: Path,
    dry_run: bool,
    elapsed: float,
) -> None:
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    mode = "dry-run" if dry_run else "live"
    summary_icon = "✅" if passed == total else "❌"

    lines: list[str] = [
        f"# Chess Agent — Smoke Test Report",
        f"",
        f"**Date:** {ts}  ",
        f"**Mode:** {mode}  ",
        f"**Model:** {MODEL_NAME}  ",
        f"**Result:** {summary_icon} {passed}/{total} passed  ",
        f"**Total time:** {elapsed:.1f}s",
        f"",
        "---",
        "",
    ]

    for case in results:
        engine_result = MOCK_POSITIONS[case.position_key]
        status = "✅ PASS" if case.passed else "❌ FAIL"
        desc = _POSITION_DESCRIPTIONS.get(case.position_key, case.position_key)
        shashin_desc = report_description(engine_result.shashin_type)
        lines += [
            f"## {status} — {desc}",
            f"",
            f"| | |",
            f"|---|---|",
            f"| Position | `{case.position_key}` |",
            f"| Position type | {shashin_desc} |",
            f"| Level | {case.level} |",
            f"| Question | {case.question} |",
            f"",
        ]

        # Checks table
        lines += [
            "### Checks",
            "",
            "| Check | Result | Detail |",
            "|---|---|---|",
        ]
        for c in case.checks:
            icon = "✅" if c.passed else "❌"
            label = _CHECK_LABELS.get(c.name, c.name)
            detail = c.detail or "—"
            lines.append(f"| {label} | {icon} | {detail} |")

        lines += [""]

        # Agent response (the main thing a human wants to read)
        lines += [
            "### Agent response",
            "",
            f"> {case.response.replace(chr(10), '  \\n> ')}",
            "",
        ]

        # Prompt — collapsed so it doesn't clutter but is available
        lines += [
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


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke tests for chess analysis agent")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls, test prompts only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print prompt and response for all cases")
    parser.add_argument("-o", "--output", default="smoke_results.md", help="Report output file (default: smoke_results.md)")
    args = parser.parse_args()

    if not args.dry_run:
        print(f"LM Studio URL : {LM_STUDIO_URL}")
        print(f"Model         : {MODEL_NAME}")
    print(f"Mode          : {'dry-run' if args.dry_run else 'live'}")
    print(f"Test cases    : {len(TEST_MATRIX)}\n")
    print("=" * 60)

    start = datetime.now()
    results: list[CaseResult] = []
    for position_key, moves, level, question in TEST_MATRIX:
        case = run_case(position_key, moves, level, question, args.dry_run)
        results.append(case)
        print_case(case, args.verbose)
    elapsed = (datetime.now() - start).total_seconds()

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"Result: {passed}/{total} passed  ({elapsed:.1f}s)")

    out = Path(args.output)
    _write_report(results, out, args.dry_run, elapsed)
    print(f"Report written → {out.resolve()}")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
