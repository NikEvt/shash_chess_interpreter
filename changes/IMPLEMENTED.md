# ShashChimera — Implementation Tracker

Status legend: ✅ Done | 🔄 In progress | ⬜ Pending

---

## ✅ #11 — Strip Numbers from BM25 Query

**File:** `alexander_interpreter/retriever.py` → `_build_query()`  
**Date:** 2026-05-19

**Problem:** Centipawn scores, WDL percentages, and square coordinates (e4, c6) ended up as BM25 query tokens, diluting the signal in a 28-chunk corpus.

**What was done:**
```python
# End of _build_query(), after all tokens are assembled:
tokens = [
    t for t in tokens
    if not re.match(r'^[a-h][1-8]$', t) and not t[0].isdigit()
]
```
Drops tokens that match chess square format (`[a-h][1-8]`) or start with a digit. `import re` moved to module top.

---

## ✅ #10 — Move Quality Label Enrichment

**File:** `alexander_interpreter/retriever.py` → `_build_query()`  
**Date:** 2026-05-19

**Problem:** When a non-best move was played, the query always got the same generic tokens (`["mistake", "inaccuracy", "alternative", "better"]`) regardless of how bad the move was.

**What was done:**
```python
if played_move and played_move != result.best_move_san:
    cp = abs(result.score_cp) if result.score_cp is not None else None
    if cp is None or cp <= 100:
        tokens += ["missed", "opportunity", "positional"]     # inaccuracy
    elif cp <= 200:
        tokens += ["error", "alternative", "better", "plan"] # mistake
    else:
        tokens += ["tactical", "error", "decisive", "losing"] # blunder
```
Centipawn thresholds match `_move_quality_label()` in `prompt.py` (≤100 = inaccuracy, ≤200 = mistake, >200 = blunder). Did not import from `prompt.py` to avoid circular import (`prompt` already imports `retriever`).

---

## ✅ #9 — Tags as Index-Only Field

**File:** `alexander_interpreter/retriever.py` — index build section  
**Date:** 2026-05-19

**Problem:** BM25 index was built from `chunk["text"]` only. Tags like `"HIGH_TAL"`, `"ruy-lopez"`, `"Capablanca"` stored in `chunk["tags"]` never influenced scoring, so Shashin zone keywords from `shashin_mod.retriever_keywords()` couldn't match chunk zones directly.

**What was done:**
```python
def _build_index_text(chunk: dict) -> str:
    return " ".join(chunk.get("tags", [])) + " " + chunk["text"]

_tokenized = [_build_index_text(chunk).lower().split() for chunk in CHUNKS]
_bm25 = BM25Okapi(_tokenized)
```
Tags are prepended to text at index time. `retrieve()` still returns only `chunk["text"]` — tags never reach the LLM prompt.

---

## ✅ #6 — Fix Color of Move Attribution

**File:** `alexander_interpreter/prompt.py` → `_build_tiny_sections()`  
**Date:** 2026-05-19

**Problem:** `result.side_to_move` is who moves **next** (after the played move). The code was using it directly as the color who just moved, so "White's knight moves to d5" was attributed to the wrong side.

**What was done:**
```python
# Before:
color = result.side_to_move  # wrong — this is who moves NEXT

# After:
color_who_played = "black" if result.side_to_move == "white" else "white"
```
Updated both `verbalize_san(played, ...)` and `verbalize_san(best_san, ...)` calls to use `color_who_played`.

---

## ✅ #4/#5 — Prompt/Eval Fit + Research Config Pipeline + Verbose Alexander Parsing + Enhanced PV Verbalization

**Files:** `alexander_interpreter/prompt.py`, `alexander_interpreter/__init__.py`, `alexander_interpreter/eval_parser.py`, `alexander_interpreter/verbalizer.py`, `webapp/backend/main.py`, `webapp/backend/stream.py`, `webapp/backend/commentary.py`, `webapp/frontend/src/components/ConfigPanel.jsx`, `webapp/frontend/src/components/Commentary.jsx`, `webapp/frontend/src/hooks/useAnalysis.js`, `webapp/frontend/src/App.jsx`, `webapp/frontend/src/App.css`  
**Date:** 2026-05-19

**Problems solved:**
1. `FULL_CONFIG` didn't enable Alexander eval sections. No medium preset. No research pipeline.
2. Alexander eval output (score table, pawn structure, space, Makogonov) was compact and hard for small LLMs to parse.
3. PV (principal variation) sequences lacked color attribution — "pawn to e6 after knight to c3" didn't clarify whose pieces were moving.

**What was done:**

**Config presets (`prompt.py`):**
- Fixed `FULL_CONFIG`: enables all 5 Alexander sections
- Added `MEDIUM_CONFIG` (1B–3B): score_table + pawn_structure + mobility
- Added `MINIMAL_CONFIG`: core only (ablation baseline)
- `CONFIG_PRESETS`, `SECTION_FLAGS`, `build_config()` for transparent field ablation

**Verbose Alexander parsers (`eval_parser.py`):**
Auto-selects based on token budget (verbose if `max_tokens >= 400`, compact otherwise):

| Field | Example compact | Example verbose |
|-------|---------|---------|
| **Score breakdown** | `"Mat:-0.1 Mob:-0.3"` | `"Material: White advantage +0.10 pawns \| Mobility: Black advantage +0.30 pawns"` |
| **Pawn structure** | `"W:0weak(2isl)"` | `"White: 0 pawn weaknesses (2 pawn islands) \| Center: Dynamic Center"` |
| **Space** | `"W16–B22"` | `"White controls 16 squares, Black controls 22 squares"` |
| **Makogonov** | `"W:Bishop c1(-2)"` | `"White's weakest piece: Bishop on c1 (activity: -2)"` |

**Verbose PV verbalization (`verbalizer.py`):**
New `verbalize_pv_verbose()` — shows color for each move in the sequence:

| Format | Example compact | Example verbose |
|--------|---------|---------|
| **1 move** | `"engine plans pawn to e6"` | `"Engine plans: Black pawn to e6"` |
| **2 moves** | `"… — after knight to c3"` | `"… — after White's knight to c3"` |
| **3 moves** | `"… then pawn to g6"` | `"… then Black's pawn to g6"` |

Full example:
- **Compact:** "engine plans pawn to e6 — after knight to c3, then pawn to g6"
- **Verbose:** "Engine plans: Black pawn to e6 — after White's knight to c3, then Black's pawn to g6"

This helps small LLMs understand whose turn it is at each step.

**Research UI:**
- `ConfigPanel.jsx` with presets + individual toggles
- Config shown in debug panel with enabled sections
- Entire config → backend → LLM pipeline is transparent and testable

---

## ⬜ #2 — Anomaly Check via Parsing Eval

**File:** new `anomaly_detector.py`, `retriever.py`, `prompt.py`  
**Complexity:** 🟡 | **Spec:** `changes/Anomaly check via parsing eval.txt`

Detect structural defects from Alexander eval text (mobility gaps, passive pieces, weak squares, zone/score contradictions) → inject as BM25 tokens + one-line prompt section.

---

## ⬜ #1 — Opening Book + Theory Enrichment

**Files:** new `opening_book.py`, `knowledge_base.py`, `retriever.py`, `prompt.py`  
**Complexity:** 🔴 | **Data:** `changes/chess-openings/*.tsv`

Two sub-tasks: FEN→ECO lookup at prompt build time; ~40–60 new opening theory chunks with family tags feeding into the enriched BM25 index.

---

## ⬜ #3 — Endgame Theory Chunks

**File:** `knowledge_base.py`  
**Complexity:** 🟡

Add position-type-specific endgame chunks (KPK, R+P vs R, B vs N, Q vs R, pure pawn) with structured tags; add material-based phase signal to `_build_query()` when `phase == "endgame"`.

---

## ⬜ #4/#5 — Prompt/Eval Fit (Alexander Sections)

**File:** `prompt.py`  
**Complexity:** 🟡

Enable Alexander eval sections (`score_table`, `pawn_structure`, etc.) in default configs; add `MEDIUM_CONFIG` preset for 1B–3B models; verify token budget with all flags on.

---

## ⬜ #7 — deepeval Testing Pipeline

**Files:** `scripts/eval_pipeline.py`  
**Complexity:** 🔴 | **Data:** `changes/Moves and Comments - Лист1.csv`  
**Rubric:** `changes/Опросник для тестов.txt` (7 criteria)

Read positions from CSV → run through `build_tiny_prompt()` → LLM → score with deepeval metrics → ablation across feature groups.

---

## ⬜ #8 — Visualizations & Statistical Analysis

**Files:** `scripts/visualize_eval.py`  
**Complexity:** 🟡

Radar charts (7 criteria), per-feature ablation bar charts, paired t-test / Wilcoxon. For thesis chapter on ablation studies.
