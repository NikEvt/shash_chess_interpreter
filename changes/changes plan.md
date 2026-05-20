# ShashChimera — Changes Plan

## Complexity / Impact Legend

| Symbol | Meaning |
|--------|---------|
| 🟢 | Low complexity |
| 🟡 | Medium complexity |
| 🔴 | High complexity |
| ⬆️ | High impact on output quality |
| ➡️ | Medium impact |
| ⬇️ | Low / indirect impact |

---

## Group A — BM25 Retriever improvements
*Files: `retriever.py`, `knowledge_base.py` — no new modules, no new dependencies*

### #11 Strip Numbers from BM25 Query ✅
**Complexity: 🟢 | Impact: ➡️**

Centipawn scores, WDL percentages, and square coordinates (e4, c6) are low-value BM25 tokens that dilute the query signal.

- Where: `_build_query()` in `retriever.py`, add one filter at the end
- Filter: drop tokens matching `^[a-h][1-8]$` or starting with a digit
- Why it matters: with a 28-chunk corpus even a few noisy tokens can mis-rank results

---

### #10 Move Quality Label Enrichment ✅
**Complexity: 🟢 | Impact: ➡️**

`_move_quality_label()` already maps centipawn delta → label, but the label is only used in the prompt, not in the BM25 query. Adding semantic synonyms per quality tier makes retrieval align with what the position actually needs.

- Where: `_build_query()` in `retriever.py`, extend the move-quality branch
- Add: `blunder` → `"tactical error decisive losing"`; `inaccuracy` → `"missed opportunity positional"`; `mistake` → `"error alternative better plan"`
- Dependency: `_move_quality_label()` already imported; just map its output to token sets

---

### #9 Tags as Index-Only Field ✅
**Complexity: 🟢 | Impact: ⬆️**

Tags (`"HIGH_TAL"`, `"ruy-lopez"`, `"Petrosian"`) are stored in `chunk["tags"]` but the BM25 index is built from `chunk["text"]` only, so zone-specific tags never influence scoring.

- Where: `retriever.py:15-16` — replace `chunk["text"].lower().split()` with `build_index_text(chunk).lower().split()`
- `build_index_text()`: `" ".join(chunk["tags"]) + " " + chunk["text"]`
- The public `retrieve()` still returns `chunk["text"]` only — tags never reach the prompt
- Impact: Shashin zone tokens (`HIGH_TAL`, `MIDDLE_TAL`, etc.) from `shashin_mod.retriever_keywords()` will now match against index tags directly

---

## Group B — Tech Debt: Alexander eval in prompt
*Files: `prompt.py` — targeted fixes*

### #6 Add Color of the Move in the Prompt ✅
**Complexity: 🟢 | Impact: ➡️**

`result.side_to_move` is who moves **next** (after the played move), so using it as "who played" is inverted. The fix is one line.

- Where: `prompt.py:362-363` — derive `color_who_played = "white" if result.side_to_move == "black" else "black"` and pass it to `verbalize_san()`
- Impact: commentary like "White's knight moves to d5" will stop being attributed to the wrong side

---

### #4/#5 Parse Alexander Eval / Prompt Fit ✅
**Complexity: 🟡 | Impact: ➡️**

`eval_parser.py` exists and `PromptConfig` already has flags for each section, but the default configs (`COMPACT_CONFIG`, `FULL_CONFIG`) leave most Alexander sections off. Need to:

- Decide which sections to enable per model size and expose sensible defaults
- Verify that `render_*` functions in `eval_parser.py` output fits token budget when all flags are on
- Add a `MEDIUM_CONFIG` preset for 1B–3B models with `score_table=True`, `pawn_structure=True`

---

## Group C — Opening Book (new module)
*New file: `opening_book.py` | Changes: `retriever.py`, `prompt.py`, `knowledge_base.py`*
*Source data: `changes/chess-openings/*.tsv` — ~3 700 lines, ECO + name + PGN*

### #1 Opening Book + Theory Enrichment
**Complexity: 🔴 | Impact: ⬆️**

Two independent sub-tasks:

**C1 — FEN→Book lookup** (`opening_book.py`)
- Parse TSV files at import time; for each row replay PGN moves with `python-chess` to compute terminal FEN
- Build `dict[fen → OpeningEntry(eco, name, pgn)]`
- Public API: `lookup(fen: str) -> OpeningEntry | None`
- In `prompt.py` `_build_tiny_sections()`: when `phase == "opening"` and lookup returns entry, add section `"Opening: {name} ({eco})"`
- Concern: replaying 3 700 PGN strings at import is ~0.3 s; can be pre-serialized to JSON

**C2 — BM25 opening theory corpus** (`knowledge_base.py`)
- Add ~40–60 chunks covering ECO families: Sicilian/Najdorf, Ruy Lopez/Berlin, Caro-Kann, French, English, QGD, King's Indian, Slav, Nimzo-Indian
- Each chunk: typical plans, key squares, common tactical motifs, style descriptor
- Tags: `["opening", "sicilian", "sharp"]` etc. — will feed into index via #9
- In `retriever.py` `_build_query()`: when phase is opening and book entry found, inject ECO family tokens

---

## Group D — Anomaly Detection (new module)
*New file: `anomaly_detector.py` | Changes: `retriever.py`, `prompt.py`*
*Full spec: `changes/Anomaly check via parsing eval.txt`*

### #2 Anomaly Check via Parsing Eval
**Complexity: 🟡 | Impact: ⬆️**

Alexander's eval text already exposes: mobility by area, space by area, weak squares, Makogonov worst-piece ranking, Shashin zone. An anomaly detector turns these into structured tags like `mobility_deficit_center` or `major_piece_restricted_white`.

- `parse_eval_text(text) -> EvalSnapshot` — regex over Alexander eval output (patterns documented in spec)
- `detect_anomalies(snapshot) -> list[str]` — 7 rules: M1 (per-area mobility gap), M2 (total mobility), S1 (space total), S2 (per-area space), W1 (weak squares), A1 (worst piece passive), A2 (major piece is worst), C1 (zone/score contradiction)
- Integration in `retriever.py`: anomaly tags → extra BM25 query tokens (e.g. `[A1] passive piece` → `"passive piece improve worst piece maneuvering"`)
- Integration in `prompt.py`: if anomalies detected, add one-line section `"Structural alerts: ..."` — compressed to stay within token budget
- Note: anomaly code is already written in the spec file — this is mostly a clean port + wiring

---

## Group E — Endgame Theory
*File: `knowledge_base.py`*

### #3 Endgame Pieces Matching with Ending Theory
**Complexity: 🟡 | Impact: ⬆️**

Current endgame chunks cover general principles (king activation, Lucena, Philidor, passed pawn, opposite bishops). Need position-type-specific chunks so retrieval matches the actual material on board.

- Detect material imbalance from `result.fen` or `result.eval_trace`
- Add chunks: KPK (opposition, rule of the square), Rook+Pawn vs Rook (bridge building, Philidor), Rook endgame with two connected pawns, Bishop vs Knight by position type (open vs closed), Queen vs Rook (Philidor defense), Pure pawn endgames (breakthrough, zugzwang)
- Tags: `["endgame", "rook_endgame"]`, `["endgame", "bishop_vs_knight"]`, etc.
- In `retriever.py`: add material-based phase signal to query when `phase == "endgame"`

---

## Group F — Testing & Evaluation Pipeline

### #7 Testing Pipeline with deepeval
**Complexity: 🔴 | Impact: ⬇️** *(indirect — validates everything else)*

Source: https://deepeval.com/docs/introduction
Evaluation rubric: `changes/Опросник для тестов.txt` (7 criteria for rating 1800–2000 audience)

- `scripts/eval_pipeline.py` — reads positions from `changes/Moves and Comments - Лист1.csv`, runs each through `build_tiny_prompt()` → LLM → response
- deepeval metrics mapped to the 7 criteria: Accuracy, Coverage, Plans & Moves, Motifs, Structure, Pedagogy, Engine/Human Consistency
- Ablation: run pipeline with each feature group on/off (opening book, anomaly detector, enriched BM25) to measure isolated contribution
- Output: scores per feature combination in CSV

---

### #8 Diagrams, Visualizations, Statistical Analysis
**Complexity: 🟡 | Impact: ⬇️** *(thesis presentation)*

- `scripts/visualize_eval.py` — radar chart (7 criteria) per model configuration using matplotlib/plotly
- Bar charts: per-feature ablation delta scores
- Statistical significance: paired t-test or Wilcoxon over eval samples
- Purpose: thesis chapter on ablation studies

---

## Implementation Order

| # | Task | Files touched | Complexity | Impact | Effort est. |
|---|------|--------------|------------|--------|-------------|
| 1 | #11 Strip numbers BM25 | `retriever.py` | 🟢 | ➡️ | 30 min | ✅ |
| 2 | #10 Quality label enrichment | `retriever.py` | 🟢 | ➡️ | 30 min | ✅ |
| 3 | #9 Tags as index field | `retriever.py`, `knowledge_base.py` | 🟢 | ⬆️ | 1 h | ✅ |
| 4 | #6 Color of move fix | `prompt.py` | 🟢 | ➡️ | 15 min | ✅ |
| 5 | #2 Anomaly detector | new `anomaly_detector.py`, `retriever.py`, `prompt.py` | 🟡 | ⬆️ | 3–4 h |
| 6 | #1 Opening book | new `opening_book.py`, `knowledge_base.py`, `retriever.py`, `prompt.py` | 🔴 | ⬆️ | 1–2 days |
| 7 | #3 Endgame theory chunks | `knowledge_base.py` | 🟡 | ⬆️ | 3–4 h |
| 8 | #4/#5 Prompt/eval fit | `prompt.py` | 🟡 | ➡️ | 2–3 h |
| 9 | #7 deepeval pipeline | `scripts/` | 🔴 | ⬇️ | 2–3 days |
| 10 | #8 Visualizations | `scripts/` | 🟡 | ⬇️ | 1 day |

---

## Quick Wins (start here)

Items #11, #10, #9, #6 are all in 1–2 files, require no new dependencies, and together take ~2–3 hours. They improve retrieval precision immediately and make all subsequent changes easier to evaluate.

## Highest ROI

Items #2 (anomaly detector) and #9 (tags in index) give the largest signal improvement per effort unit, because they make the BM25 query structurally aware of position defects that centipawn score alone doesn't capture.
