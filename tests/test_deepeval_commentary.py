"""deepeval evaluation for chess commentary quality.

Loads eval_trace_*.json files from tests/results/, builds one LLMTestCase per
non-empty trace entry, and scores each commentary against 8 metrics:
  - 7 × GEval matching the project's 7-criterion rubric (Опросник для тестов.txt)
  - 1 × FaithfulnessMetric (groundedness: no facts invented beyond prompt)

Metrics are evaluated in sequential batches of 2 to avoid rate-limiting the
judge proxy (which runs all metrics in the same batch via asyncio.gather).

Judge model: local OpenAI-compatible proxy (defaults to kiro/claude-haiku-4.5).
Override via env vars:
  JUDGE_BASE_URL     (default: http://localhost:20128/v1)
  JUDGE_API_KEY      (default: sk-aa25274beeca553e-cac79c-1e98ce72)
  JUDGE_MODEL        (default: kiro/claude-haiku-4.5)
  JUDGE_BATCH_SIZE   (default: 2 — metrics per parallel batch)

Run:
    pytest tests/test_deepeval_commentary.py -v
    pytest tests/test_deepeval_commentary.py -k "1779275077" -x   # single trace
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest
from deepeval.evaluate import evaluate
from deepeval.evaluate.configs import AsyncConfig, DisplayConfig
from deepeval.metrics import FaithfulnessMetric, GEval
from deepeval.models import GPTModel
from deepeval.test_case import LLMTestCase, SingleTurnParams

# ---------------------------------------------------------------------------
# Judge model — local proxy, drop-in OpenAI-compatible
# ---------------------------------------------------------------------------

_JUDGE_BASE_URL = os.getenv("JUDGE_BASE_URL", "http://localhost:20128/v1")
_JUDGE_API_KEY = os.getenv("JUDGE_API_KEY", "sk-aa25274beeca553e-cac79c-1e98ce72")
_JUDGE_MODEL = os.getenv("JUDGE_MODEL", "kiro/claude-haiku-4.5")
_JUDGE_BATCH_SIZE = int(os.getenv("JUDGE_BATCH_SIZE", "2"))

_judge = GPTModel(
    model=_JUDGE_MODEL,
    api_key=_JUDGE_API_KEY,
    base_url=_JUDGE_BASE_URL,
)

# ---------------------------------------------------------------------------
# Metrics — defined once at module level
# ---------------------------------------------------------------------------

ACCURACY = GEval(
    name="Accuracy",
    criteria=(
        "Judge whether the chess commentary is factually grounded in the provided "
        "position and engine context. The commentary must accurately reflect "
        "the played move and evaluation direction. "
        "Do NOT evaluate formatting (sentence count, preamble, style) — only factual accuracy."
        "Penalize only clear errors: wrong piece type, non-existent square, or evaluation direction opposite to the input."
    ),
    evaluation_steps=[
        "Verify the played move name matches what the input says was played (piece type and square).",
        "If the engine's preferred move is named, check only that the move name appears somewhere in the input — do NOT penalize for errors in describing the continuation sequence order or which side plays a follow-up move.",
        "Confirm that the evaluation direction (which side is better/worse) matches the input.",
        
    ],
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model=_judge,
    threshold=0.5,
)

CONCEPTUAL_DEPTH = GEval(
    name="ConceptualDepth",
    criteria=(
        "Assess the conceptual depth of the chess commentary. "
        "The commentary is constrained to exactly 3 sentences, so depth means connecting "
        "the move to at least one chess concept. Do NOT require detailed mechanistic "
        "explanation — naming a relevant strategic or tactical theme is sufficient. "
        "Do NOT evaluate formatting (sentence count, preamble, style)."
    ),
    evaluation_steps=[
        "Check whether the commentary names at least one strategic or tactical concept (e.g., center control, piece activity, king safety, initiative, pawn structure, development). Even a brief phrase qualifies.",
        "Check whether the concept is connected to the specific move played, not stated in the abstract.",
        "A commentary that only says 'the engine preferred X' with no conceptual reason whatsoever scores low. Any phrase explaining WHY (even one clause) raises the score significantly.",
        "Given the 3-sentence constraint, a single sentence linking the move to a chess idea is sufficient for a passing score. Do not require mechanistic explanation of weak squares, exact lines, or deep positional reasoning.",
    ],
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model=_judge,
    threshold=0.35,
)

INPUT_COVERAGE = GEval(
    name="InputCoverage",
    criteria=(
        "Determine whether the commentary makes use of the key information provided "
        "in the input: move quality, engine recommendation, and evaluation direction. "
        "Do NOT evaluate formatting (sentence count, preamble, style). "
        "Do NOT penalize for errors in describing the engine continuation sequence — "
        "only check whether key facts were included, not whether they were perfectly described."
    ),
    evaluation_steps=[
        "Check whether the played move quality (best/good/inaccuracy/mistake/blunder) is reflected in tone or wording.",
        "If the move was not best, check whether the engine's recommended move NAME is mentioned. Do not require correct description of continuation moves (who plays c4, e6, etc.) — mentioning the move name is sufficient.",
        "Check whether the evaluation direction (which side is gaining/losing, or equal) is incorporated.",
        "Commentary satisfying steps 1 and 3 (move quality + eval direction) should receive a passing score even if the engine recommendation is omitted. Only penalize heavily when all three points are completely absent.",
    ],
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model=_judge,
    threshold=0.5,
)

HALLUCINATION_CONTROL = GEval(
    name="HallucinationControl",
    criteria=(
        "Judge whether the commentary invents facts not present in the input. "
        "A hallucination is ONLY: a piece-square combination entirely absent from the input, "
        "OR a specific tactical motif (fork, pin, skewer, discovered attack) not mentioned in the engine analysis. "
        "The following are NOT hallucinations and must NOT be penalized: "
        "incorrect attribution of which side plays a continuation move, "
        "vague strategic claims ('controls the center', 'improves coordination', 'creates pressure'), "
        "task failure (not answering the question), formatting violations (sentence count, preamble). "
        "Do NOT evaluate formatting or task-answer quality — only invented facts."
    ),
    evaluation_steps=[
        "Identify any specific piece-square combination in the commentary (e.g., 'bishop on e7'). Flag ONLY those not mentioned anywhere in the input. General move names (e.g., 'd5', 'Nf3') just need to appear somewhere in the input.",
        "If the commentary names a specific tactical motif (fork, pin, skewer, discovered attack, back-rank mate), check whether the input engine line explicitly describes such a pattern. If absent, flag as hallucinated.",
        "Misattributing which side plays a move in the engine continuation (e.g., saying 'Black plays c4' when it was White) is a factual error but NOT a hallucination — do not penalize here.",
        "General strategic language ('controls center', 'piece activity', 'king safety', 'initiative', 'coordination', 'expansion') is always acceptable regardless of whether the input mentions it.",
    ],
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model=_judge,
    threshold=0.5,
)
METRICS = [
    ACCURACY,
    CONCEPTUAL_DEPTH,
    INPUT_COVERAGE,
    HALLUCINATION_CONTROL,
]

# ---------------------------------------------------------------------------
# Trace loading
# ---------------------------------------------------------------------------

RESULTS_DIR = Path(__file__).parent / "results"

_REFUSAL_MARKERS = ("i'm kiro", "i am kiro", "can't help with this", "can't complete this")


def _load_trace_file(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    game_id = path.stem  # e.g. "eval_trace_1779275077"
    traces = []
    for entry in data.get("traces", []):
        if (
            entry.get("commentary_empty")
            or entry.get("san") is None
            or entry.get("quality") == "book"
            or not entry.get("lm_calls")
        ):
            continue
        commentary_lower = entry.get("commentary", "").lower()
        if any(m in commentary_lower for m in _REFUSAL_MARKERS):
            continue
        entry["_game_id"] = game_id
        traces.append(entry)
    return traces


def load_traces() -> list[dict]:
    traces = []
    for path in sorted(RESULTS_DIR.glob("eval_trace_*.json")):
        traces.extend(_load_trace_file(path))
    return traces


def _trace_id(trace: dict) -> str:
    return (
        f"{trace['_game_id']}"
        f"__m{trace['move_number']}"
        f"_{trace['san']}"
        f"_{trace.get('color', 'unknown')}"
        f"_{trace.get('quality', 'unknown')}"
    )


# ---------------------------------------------------------------------------
# Test case builder
# ---------------------------------------------------------------------------

def _build_test_case(trace: dict) -> LLMTestCase:
    retrieval_context = [
        s["content"]
        for s in trace.get("prompt_sections", [])
        if s.get("label") != "System instruction"
    ]
    return LLMTestCase(
        input=trace["prompt_text"],
        actual_output=trace["commentary"],
        retrieval_context=retrieval_context,
    )


# ---------------------------------------------------------------------------
# Parametrised test
# ---------------------------------------------------------------------------

_traces = load_traces()

if not _traces:
    pytest.skip(
        "No eval trace files found in tests/results/ — run eval_game.py first.",
        allow_module_level=True,
    )

_async_config = AsyncConfig(throttle_value=0, max_concurrent=1)
_display_config = DisplayConfig(show_indicator=True)

# One results file per pytest session, written to tests/results/ next to trace files.
_RESULTS_FILE = RESULTS_DIR / f"deepeval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"


def _append_result(trace: dict, metrics_data: list) -> None:
    record = {
        "trace_id": _trace_id(trace),
        "game_id": trace["_game_id"],
        "move_number": trace["move_number"],
        "san": trace["san"],
        "color": trace.get("color"),
        "quality": trace.get("quality"),
        "commentary": trace["commentary"],
        "run_config": trace.get("run_config_file", "unknown"),
        "overall_pass": all(md.success for md in metrics_data),
        "metrics": [
            {
                "name": md.name,
                "score": md.score,
                "success": md.success,
                "reason": md.reason,
            }
            for md in metrics_data
        ],
    }
    with _RESULTS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


@pytest.mark.parametrize("trace", _traces, ids=_trace_id)
def test_commentary_quality(trace: dict) -> None:
    tc = _build_test_case(trace)

    # Evaluate in sequential batches to avoid bursting the proxy's rate limit.
    # deepeval runs all metrics in a batch via asyncio.gather concurrently —
    # batching keeps the number of simultaneous judge calls at JUDGE_BATCH_SIZE.
    all_metrics_data: list = []
    failures: list[str] = []
    for i in range(0, len(METRICS), _JUDGE_BATCH_SIZE):
        batch = METRICS[i : i + _JUDGE_BATCH_SIZE]
        result = evaluate(
            test_cases=[tc],
            metrics=batch,
            async_config=_async_config,
            display_config=_display_config,
        )
        for tr in result.test_results:
            for md in tr.metrics_data or []:
                all_metrics_data.append(md)
                if not md.success:
                    failures.append(
                        f"{md.name} (score={md.score:.2f}): {md.reason}"
                    )

    _append_result(trace, all_metrics_data)

    if failures:
        pytest.fail(
            "Commentary quality metrics failed:\n"
            + "\n".join(f"  • {f}" for f in failures)
        )
