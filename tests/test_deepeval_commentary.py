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
        "The chess commentary correctly identifies who stands better and why, "
        "grounded in chess principles: material balance, king safety, piece "
        "activity, pawn structure, space, and initiative. "
        "There are no false factual claims — wrong piece names, invented moves, "
        "or evaluations that contradict the engine data in the prompt."
    ),
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model=_judge,
    threshold=0.5,
)

COVERAGE = GEval(
    name="Coverage",
    criteria=(
        "The commentary covers the main positional factors that matter in this "
        "specific position for a 1800–2000 rated player: king safety, material "
        "imbalances, piece activity and coordination, pawn structure, space "
        "control, and initiative. "
        "No critical factor present in the prompt is completely ignored."
    ),
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model=_judge,
    threshold=0.5,
)

PLANS_AND_MOVES = GEval(
    name="PlansAndMoves",
    criteria=(
        "The commentary links the positional evaluation to concrete plans and "
        "best moves. It is clear what the stronger side intends to do next — "
        "which pieces to activate, which breakthroughs to prepare, which "
        "exchanges to seek or avoid. "
        "Engine recommendations from the prompt are explained in terms of plans, "
        "not just listed."
    ),
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model=_judge,
    threshold=0.5,
)

MOTIFS = GEval(
    name="Motifs",
    criteria=(
        "The commentary identifies key tactical and strategic motifs present in "
        "the position: pins, forks, undefended pieces, potential sacrifices, "
        "outposts, weak squares, bad or good bishops, and long-term pawn "
        "weaknesses. "
        "A 1800–2000 reader should understand both immediate tactical threats "
        "and long-term structural features."
    ),
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model=_judge,
    threshold=0.5,
)

STRUCTURE = GEval(
    name="Structure",
    criteria=(
        "The commentary is logically organised — either 'general conclusion then "
        "supporting arguments' or a systematic walk through key factors (king "
        "safety → material → pieces → pawns → plans). "
        "It is not a scattered list of observations; there is a clear thread "
        "from premise to conclusion."
    ),
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model=_judge,
    threshold=0.5,
)

PEDAGOGY = GEval(
    name="Pedagogy",
    criteria=(
        "The commentary helps a 1800–2000 player understand *how to think* in "
        "similar positions — not only what is better here and now. "
        "It contains generalisable principles or typical plans for this type of "
        "structure, avoids unexplained jargon, and models the reasoning process "
        "rather than merely stating conclusions."
    ),
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model=_judge,
    threshold=0.5,
)

ENGINE_CONSISTENCY = GEval(
    name="EngineConsistency",
    criteria=(
        "The commentary agrees with the engine conclusions provided in the "
        "prompt: it does not claim equality when the engine shows a large "
        "advantage, and does not invent winning advantages from a balanced "
        "position. "
        "Engine data is translated into human chess concepts (initiative, space, "
        "weak squares) rather than recited as raw numbers."
    ),
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model=_judge,
    threshold=0.5,
)

FAITHFULNESS = FaithfulnessMetric(
    threshold=0.7,
    model=_judge,
    # Checks that actual_output does not contradict retrieval_context (the
    # prompt sections). Validates the system instruction "Use only the facts below."
)

METRICS = [
    ACCURACY,
    COVERAGE,
    PLANS_AND_MOVES,
    MOTIFS,
    STRUCTURE,
    PEDAGOGY,
    ENGINE_CONSISTENCY,
    FAITHFULNESS,
]

# ---------------------------------------------------------------------------
# Trace loading
# ---------------------------------------------------------------------------

RESULTS_DIR = Path(__file__).parent / "results"


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
