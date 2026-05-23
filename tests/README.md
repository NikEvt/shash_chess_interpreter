# Test Suite

This directory contains two categories of validation assets:

- **Pytest-based unit tests**, which run without external services.
- **Evaluation scripts**, which require a working chess engine and an LLM endpoint such as LM Studio.

## Quick Start

```bash
# Run all unit tests (no engine, no LLM required)
python3.12 -m pytest tests/ -v

# Run a full game evaluation (requires engine + LM Studio)
python tests/eval_game.py
python tests/eval_game.py --pgn my_game.pgn --config medium --out trace.json
```

## Contents

### `test_retriever.py` — BM25 Retriever and Opening Book

Unit tests for retrieval logic that do not depend on external services.

| Group | Coverage |
|------|----------|
| `test_book_loaded` | Verifies that the TSV opening book is loaded and non-empty. |
| `test_lookup_exact_*` | Checks exact matching of UCI move sequences against the opening book. |
| `test_lookup_prefix_*` | Verifies shortest-prefix matching and preference for deeper matches. |
| `test_eco_tokens_*` | Confirms that `eco_family_tokens()` returns the expected ECO-derived tokens. |
| `test_phase_*` | Validates `_position_phase()` classification into opening, middlegame, or endgame based on remaining material. |
| `test_opening_theory_*` | Ensures `retrieve_opening_theory()` returns theory only while the game remains close to book (within 4 plies of a known line), otherwise `None`. |
| `test_retrieve_*` | Verifies BM25 `retrieve()` behavior, including list output, `top_k` handling, and support across all game phases. |

```bash
python3.12 -m pytest tests/test_retriever.py -v
```

### `test_commentary_gaps.py` — LLM Retry Logic and Empty Commentary Protection

Unit tests that cover failure handling in the commentary pipeline without requiring external dependencies.

These tests were introduced as a regression guard for a case where the model returned only a `<think>...</think>` block, `_strip_think()` produced an empty string, and the commentary was silently dropped.

| Group | Coverage |
|------|----------|
| `test_strip_think_*` | Verifies that `_strip_think()` removes both closed and unclosed `<think>` blocks while preserving surrounding text. |
| `test_ask_retries_when_think_only` | Regression test for the key failure mode: an empty result after stripping must trigger a retry. |
| `test_ask_retries_on_truncation` | Verifies retry behavior when `finish_reason == "length"`. |
| `test_ask_retry_budget_is_plus_256` | Confirms that the retry token budget is `max_tokens + 256`, not `max(max_tokens, 512)`. |
| `test_ask_no_retry_when_response_is_fine` | Ensures a normal response completes in a single call. |
| `test_ask_fallback_to_empty_if_both_attempts_think_only` | Ensures the function returns a string and does not fail even if both attempts are think-only. |

```bash
python3.12 -m pytest tests/test_commentary_gaps.py -v
```

### `eval_game.py` — End-to-End Evaluation Pipeline

This script is not a pytest test. It runs a complete chess game through the real Alexander engine and a real LLM, while collecting a detailed trace of each step.

**Requirements:**

- The engine binary must be available at `Alexander/src/alexander`, or provided through `ALEXANDER_ENGINE_PATH`.
- LM Studio must be available at `http://localhost:1234`, or configured through `LM_STUDIO_URL`.

### Engine Fixture Cache

On the first run, the script executes the engine and stores its outputs in `tests/fixtures/alekhine_bogoljubov_1942.json`.
Subsequent runs reuse this fixture and skip the engine phase, so only the LLM is required.

```bash
# First run — requires the engine and creates the fixture
python tests/eval_game.py

# Later runs — only the LLM is required
python tests/eval_game.py

# Force a fresh engine pass
python tests/eval_game.py --rerun-engine

# Use a custom fixture path
python tests/eval_game.py --fixture tests/fixtures/my_game.json
```

The fixture stores, for each position, fields such as `eval_cp`, `eval_mate`, `shashin_zone`, WDL values, `best_move_san`, `best_move_uci`, `pv_san`, `engine_summary`, `eval_loss_cp`, `quality`, and the serialized `AlexanderResult`.

### Console Output

```text
── Engine analysis (depth=20) ──
  [  1/64] e4       cp=  +18  zone=CAPABLANCA
  [  2/64] e5       cp=  +15  zone=CAPABLANCA
  ...

── Commentary (LLM) ──
  [  1/64] e4        1.3s  calls=1    len= 142
  [  2/64] e5        2.1s  calls=2 ↺  len= 138   ⚠ THINK-ONLY (retry)
  ...

══════════════════════════════════════════════
  EVAL SUMMARY — Alexander Alekhine vs Efim Bogoljubov
  Positions analysed :  64
  Empty commentaries :   0  ✓
  LLM retries        :   7
  Avg prompt  tokens : 284
  Avg raw resp chars : 312
  Avg commentary len : 156 chars
  Avg LLM latency    : 1.8 s
```

### JSON Output

The script writes a trace file named `eval_trace_<timestamp>.json` with detailed engine, prompt, and LLM-call metadata for each analysed move.

Example structure:

```jsonc
{
  "game": { "White": "Alexander Alekhine", ... },
  "traces": [
    {
      "san": "e4",
      "eval_cp": 18,
      "shashin_zone": "CAPABLANCA",
      "question_type": "explain",
      "prompt_sections": [{"label": "System instruction", "content": "..."}],
      "prompt_text": "...",
      "lm_calls": [
        {
          "attempt": 1,
          "raw_response": "<think>...</think>",
          "finish_reason": "stop",
          "stripped_response": "",
          "is_think_only": true,
          "elapsed_s": 0.9
        },
        {
          "attempt": 2,
          "raw_response": "Alekhine opens with e4...",
          "finish_reason": "stop",
          "stripped_response": "Alekhine opens with e4...",
          "elapsed_s": 1.4
        }
      ],
      "retried": true,
      "commentary": "Alekhine opens with e4..."
    }
  ]
}
```

### Related Files

- `eval_game_raw.py` — lower-level or raw evaluation flow.
- `test_anomaly_detector.py` — tests for anomaly detection logic.
- `test_deepeval_commentary.py` — evaluation checks for commentary quality.
- `analyze_eval.ipynb` and `analyze_deepeval.ipynb` — notebooks for trace inspection and result analysis.

## Recommended Usage

For everyday development, start with the pure unit tests to validate retrieval and commentary behavior quickly.
Use `eval_game.py` when validating the full engine-to-LLM pipeline or when investigating output quality, latency, and retry behavior.
