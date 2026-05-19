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
