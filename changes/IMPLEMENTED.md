# ShashChimera — Implementation Tracker

Status legend: ✅ Done | 🔄 In progress | ⬜ Pending

---

## ✅ — LLM Empty Commentary Fix

**File:** `alexander_interpreter/llm.py` → `ask()`  
**Date:** 2026-05-20

**Problem:** Commentary was missing for individual moves (gap between previous and next). The model sometimes outputs only a `<think>...</think>` block with no text after it. `_strip_think()` removes the block and returns `""`. Empty string propagates as commentary with no exception and no retry — silent gap in the UI.

Secondary bug: retry token budget `max(max_tokens_actual, 512)` didn't increase if budget was already ≥ 512.

**What was done:**
```python
result = _strip_think(content)
# Retry when: (a) truncated, or (b) only a <think> block was produced
if finish_reason == "length" or not result:
    retry_max_tokens = max_tokens_actual + 256  # always adds 256, no floor trap
    content2, _ = _call_lm(no_think_prompt, temperature, retry_max_tokens)
    result2 = _strip_think(content2)
    return result2 if result2 else result
return result
```
- Empty string now triggers a retry identically to truncation
- `/no_think` applied on both first attempt and retry (was only on retry before)
- Retry budget is `+256` on top of actual, not `max(actual, 512)`

**Tests (`tests/test_commentary_gaps.py`) — 17 cases:**
- `_strip_think()`: closed block alone, multiline, unclosed/truncated, text before/after, multiple blocks, no tags
- `ask()` retry: think-only triggers retry; truncation triggers retry; retry result preferred; both calls use `/no_think`; LMStudioError propagates cleanly

---

## ✅ — Opening→Middlegame Transition Fix

**Files:** `alexander_interpreter/opening_book.py`, `alexander_interpreter/retriever.py`  
**Date:** 2026-05-20

**Problem:** `retrieve_opening_theory()` used `_position_phase()` (piece count ≥ 28) to decide if we're in the opening. In closed games with few captures (KID, Nimzo-Indian), piece count stays ≥ 28 through move 20+, so opening book theory from move 8 was shown for positions that were clearly in the middlegame. At transition, BM25 also lost all ECO context because `_build_query()` only injected opening tokens when `phase == "opening"`.

**What was done:**

`opening_book.py` — added `lookup_with_depth`:
```python
def lookup_with_depth(game_uci: str) -> tuple[OpeningEntry | None, int]:
    """Like lookup() but also returns the number of UCI half-moves that matched."""
    moves = _normalise_uci(game_uci).split()
    for length in range(len(moves), 0, -1):
        entry = _BOOK.get(" ".join(moves[:length]))
        if entry is not None:
            return entry, length
    return None, 0
```

`retriever.py` — `retrieve_opening_theory`: replaced piece-count check with book-depth check:
```python
game_length = len(result.game_uci.split())
entry, match_depth = _ob_lookup_with_depth(result.game_uci)
if game_length - match_depth > 4:   # >4 half-moves past deepest book entry → use BM25
    return None
```

`retriever.py` — `_build_query`: ECO tokens now injected for any game from a known opening, not only when `phase == "opening"`:
```python
entry, match_depth = _ob_lookup_with_depth(result.game_uci)
if entry:
    tokens += _eco_tokens(entry.eco).split()
    if game_length - match_depth <= 6:   # opening name tokens only while still close to book
        tokens += [w.lower() for w in entry.name.split()[:4] if len(w) > 3]
```

**Effect:**
- A closed game with 30 pieces on move 18 that left theory on move 10 → BM25 (was: opening book theory from move 10)
- A Sicilian with many early captures, 27 pieces on move 12, still 2 moves past book → opening book (was: BM25 with no ECO context)
- BM25 queries in the early middlegame now get ECO family tokens for better chunk selection

**Tests (`tests/test_retriever.py`) — 25 cases:**
- Opening book: exact lookup, prefix/deepest-match, unknown opening, empty/whitespace UCI
- `eco_family_tokens()`: A00, B20 range, empty ECO
- `_position_phase()`: opening/middlegame/endgame by piece count
- `retrieve_opening_theory()`: exact match returns theory; 5+ moves past book → None; middlegame → None; no game_uci → None
- `retrieve()`: returns list, respects top_k, chunks non-empty, endgame position, blunder move tokens

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

## ✅ #4/#5 — Prompt/Eval Fit + Research Config Pipeline + Verbose Alexander Parsing + Enhanced PV Verbalization + Opening Theory Lookup

**Files:** `alexander_interpreter/prompt.py`, `alexander_interpreter/__init__.py`, `alexander_interpreter/eval_parser.py`, `alexander_interpreter/verbalizer.py`, `alexander_interpreter/retriever.py`, `alexander_interpreter/opening_book.py`, `webapp/backend/main.py`, `webapp/backend/stream.py`, `webapp/backend/commentary.py`, `webapp/frontend/src/components/ConfigPanel.jsx`, `webapp/frontend/src/components/Commentary.jsx`, `webapp/frontend/src/hooks/useAnalysis.js`, `webapp/frontend/src/App.jsx`, `webapp/frontend/src/App.css`  
**Date:** 2026-05-19

**Problems solved:**
1. `FULL_CONFIG` didn't enable Alexander eval sections. No medium preset. No research pipeline.
2. Alexander eval output (score table, pawn structure, space, Makogonov) was compact and hard for small LLMs to parse.
3. PV (principal variation) sequences lacked color attribution.
4. During opening phase, generic theory chunks were used instead of position-specific opening theory.
5. Pawn captures like "bxc3" crashed with `ValueError: 'bx' is not in list` when verbalizing.

**What was done:**

**System prompt instruction (`prompt.py`):**
- Changed `"Write exactly 2 sentences."` → `"Write exactly 4 sentences."` — gives the model room for a complete thought without exceeding the 350-token budget.

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
New `verbalize_pv_verbose()` — shows color for each move:
- **1 move:** `"Engine plans: Black pawn to e6"`
- **2 moves:** `"… — after White's knight to c3"`
- **3 moves:** `"… then Black's pawn to g6"`

Helps small LLMs understand whose turn it is.

**Opening theory lookup (`retriever.py` + `prompt.py`):**
- New function `retrieve_opening_theory(result)`:
  - Looks up `result.game_uci` in opening book via `lookup_with_depth()`
  - Uses **book-depth check**: if game is >4 half-moves past the deepest matching book entry → returns None (hand off to BM25)
  - Returns the matched entry's theory text if still close to book, else None
- Updated all three prompt builders to:
  1. Try `retrieve_opening_theory()` first when `include_theory` is on
  2. If found: use opening-specific theory
  3. If not found: fall back to BM25 retrieval (generic knowledge base)

**Research UI:**
- `ConfigPanel.jsx` with presets + individual toggles
- Config shown in debug panel with enabled sections
- Entire pipeline transparent and testable

**Pawn capture verbalization fix (`verbalizer.py`):**
- Bug: moves like "bxc3" (pawn from b-file captures on c3) crashed with `ValueError: 'bx' is not in list`
- Root cause: code tried to parse "bx" as a square name instead of extracting source file
- Fix: use `board_before.parse_san()` to properly extract source/target squares for pawn captures
- Result: now correctly verbalizes `"White's pawn captures knight on c3"` instead of crashing

---

## ✅ #2 — Anomaly Check via Parsing Eval

**Files:** new `alexander_interpreter/anomaly_detector.py`, `alexander_interpreter/prompt.py`, `alexander_interpreter/retriever.py`, `webapp/backend/commentary.py`, `tests/test_anomaly_detector.py`, `tests/eval_config.json`, `tests/eval_game.py`, `tests/analyze_eval.ipynb`  
**Date:** 2026-05-20

**Problems solved:**
1. `include_makogonov=True` showed worst-piece data during Opening — meaningless before piece deployment.
2. `include_score_table=True` showed score breakdown on every move regardless of eval shift — noise on quiet moves.
3. `include_pawn_structure`, `include_space`, `include_mobility` had no dynamic conditions — always shown or always hidden.
4. No structural defects (mobility gap, weak pawns, king exposure, space cramping, eval/win-prob contradiction) were injected as BM25 tokens.
5. No verbal remark when the game phase changed (Opening → Middlegame, etc.).

---

### Final `detect_anomalies()` signature

```python
def detect_anomalies(
    ev: EvalSections,
    prev_eval_cp: int | None,
    curr_eval_cp: int | None,
    score_jump_threshold_cp: int = 50,   # 0 = always show
    pawn_weakness_threshold: int = 2,    # 0 = always show
    space_imbalance_threshold: int = 4,  # 0 = always show
    mobility_score_threshold: int = 20,  # 0 = always show
    game_phase_suppress_opening: bool = False,
    prev_game_phase: str | None = None,
) -> AnomalyFlags
```

### `AnomalyFlags` dataclass

```python
@dataclass
class AnomalyFlags:
    show_score_table:        bool = False   # eval-jump gate
    show_game_phase:         bool = True    # suppress Opening label opt-in
    show_pawn_structure:     bool = True    # weakness threshold
    show_space:              bool = True    # imbalance threshold
    show_mobility:           bool = True    # activity threshold
    show_makogonov:          bool = False   # phase gate (Middlegame/Endgame only)
    phase_transition_remark: str  = ""      # verbal remark on phase change
    anomaly_tokens:   list[str]   = []      # extra BM25 tokens
    anomaly_summary:  str         = ""      # "Structural alerts: ..." prompt section
```

### Gate logic (all 6 Alexander sections)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         _build_tiny_sections()                              │
│                                                                             │
│  EvalSections ──► detect_anomalies() ──────────────────► AnomalyFlags      │
│                         │                                       │           │
│          ┌──────────────┼───────────────────┐         ┌────────▼────────┐  │
│     eval jump?     phase changed?     struct checks    │  Section gates  │  │
│     |Δcp|≥thr?    prev≠curr phase?   (Middlegame only) │                 │  │
│          │               │                  │          │ score_table:    │  │
│     show_score    phase_transition    tokens+summary   │   |Δcp|≥thr    │  │
│       _table        _remark                            │ game_phase:     │  │
│                                                        │   suppress opt  │  │
│          game_phase?  weakness?  imbalance?  activity? │ pawn_structure: │  │
│          suppress     max(W,B)   |W-B|≥thr  |mob|≥thr │   max≥thr      │  │
│          Opening      ≥ thr                            │ space: |W-B|≥  │  │
│                                                        │ mobility:|m|≥  │  │
│                                                        │ makogonov:     │  │
│                                                        │   mid/end only │  │
│                                                        └────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Threshold = 0 semantics
When any threshold is set to 0, the gate is disabled — the section always shows (when the config flag is `True`). Useful for ablation studies.

### Phase transition verbal remark
When `prev_game_phase != ev.game_phase`, `phase_transition_remark` is populated from a lookup table and injected as a dedicated **"Phase transition"** prompt section (always surfaced, no config flag needed):

```python
_TRANSITIONS = {
    ("opening",    "middlegame"): "The Opening is over — the Middlegame begins.",
    ("middlegame", "endgame"):    "This move transitions the game to the Endgame.",
    ("opening",    "endgame"):    "The game jumps directly from Opening to Endgame.",
}
# Unknown pair → generic fallback: "The game phase changed from X to Y."
```

### Structural anomaly checks (Middlegame only)

| Code | Trigger | BM25 tokens injected |
|------|---------|----------------------|
| M | `\|score_mobility\| > 30 cp` | `passive piece activity mobility outpost coordination` |
| W | `pawn_weaknesses ≥ 3` per side | `pawn weakness isolated doubled backward structure` |
| K | `\|score_king_safety\| > 40 cp` | `king safety attack shelter exposed assault` |
| S | `\|space_white − space_black\| ≥ 6` | `space cramped outpost restriction maneuvering` |
| C | `score_cp > 50` but `win_pct < 40` | `compensation imbalance counterplay dynamic initiative` |

### Files changed

**`anomaly_detector.py`** — new module (199 lines)

**`prompt.py`:**
- `PromptConfig` +5 fields: `score_jump_threshold_cp`, `pawn_weakness_threshold`, `space_imbalance_threshold`, `mobility_score_threshold`, `game_phase_suppress_opening`
- `_build_tiny_sections()` / `build_tiny_prompt()` / `build_tiny_prompt_sections()` +`prev_game_phase` param
- All 6 Alexander sections double-gated: `if cfg.include_X and anomaly.show_X`
- "Phase transition" section injected when `anomaly.phase_transition_remark` is non-empty
- `retrieve()` called with `extra_tokens=anomaly.anomaly_tokens`

**`retriever.py`:**
- `retrieve()` and `_build_query()` accept `extra_tokens: list[str] | None`
- Extra tokens prepended before the square-coordinate filter pass

**`commentary.py`:**
- Extracts `prev_game_phase` from `positions[idx-1].alexander_result.raw_eval_lines`
- Passes it through `shared_kwargs` to `build_tiny_prompt()`

**`eval_config.json`:**
```json
{
  "score_jump_threshold_cp":     50,
  "pawn_weakness_threshold":      2,
  "space_imbalance_threshold":    4,
  "mobility_score_threshold":    20,
  "game_phase_suppress_opening": false,
  "include_makogonov":           true
}
```

**`eval_game.py` — anomaly tracing:**
- `trace["anomaly"]` dict added per position: gate inputs (`eval_delta_cp`, `max_pawn_weaknesses`, `space_diff`, `score_mobility_abs`), flag states (all 6 `show_*`), `phase_transition_remark` bool, `anomaly_summary` bool, `thresholds` snapshot
- `print_summary()` extended with flag firing rates (bar-chart █/░) and per-move short codes (ST GP PW SP MO MK PT)

**`analyze_eval.ipynb` — 6 new cells:**
- Flag firing rate summary table (% of moves each gate fires)
- Heatmap (flags × moves, green=on/red=off) + step-plot timeline with phase-transition markers
- 2×2 threshold sensitivity sweep — % of moves with flag=True vs threshold value; red line = current config, gray dotted = p25/p50/p75 of input distribution
- 2D joint-firing matrix (Score table × Mobility thresholds)

**`alexander_interpreter/build_engine.sh` / `build_engine.bat`** — engine build scripts (Mac/Linux/Windows):
- Auto-detects platform/arch: Apple Silicon → `apple-silicon`+clang, Intel Mac → `x86-64-avx2`+clang, Linux ARM → `armv8-dotprod`+gcc, Linux x86 → `x86-64-sse41-popcnt`+gcc
- Patches Makefile to remove x86-only flags (`-mprefer-vector-width=256 -mno-avx512f`) before building — same fix as Dockerfile
- Windows script targets MSYS2/MinGW64 (`x86-64-avx2 COMP=mingw`)

### Tests (`tests/test_anomaly_detector.py`) — 38 cases

| Group | Count | What's tested |
|-------|-------|---------------|
| Score table gate | 5 | large/small jump, no prev eval, custom threshold, negative delta |
| Makogonov gate | 4 | Opening→hidden; Middlegame/Endgame→shown; unknown phase→hidden |
| Structural tokens | 7 | M/W/K/S/C each produce correct tokens; clean position→empty; multiple→combined |
| `game_phase` display gate | 4 | suppress=False always shows; suppress=True hides Opening/""; Middlegame always shown |
| Phase transition remark | 5 | Opening→Middlegame; Middlegame→Endgame; same phase→""; no prev→""; unknown pair→fallback |
| Pawn structure gate | 4 | above/below threshold; threshold=0; max-per-side logic |
| Space gate | 4 | above/below threshold; threshold=0; no data→suppress |
| Mobility gate | 4 | above/below threshold; threshold=0; no data→suppress |

---

## ✅ #1 — Opening Book + Theory Enrichment

**Files:** new `alexander_interpreter/opening_book.py`, `alexander_interpreter/knowledge_base.py`, `alexander_interpreter/retriever.py`, `alexander_interpreter/prompt.py`  
**Date:** 2026-05-19  
**Data source:** `archive/data/chess_openings_dataset_checkpoint.tsv` (500 openings, ECO A–E)

**Sub-task C1 — UCI→Book lookup (`opening_book.py`):**
- Parsed TSV at import time, keyed by normalized UCI move sequence; O(1) lookup
- `OpeningEntry(eco, name, pgn, text)` dataclass
- `lookup(game_uci) -> OpeningEntry | None` — finds the deepest matching prefix in `_BOOK`
- `lookup_with_depth(game_uci) -> (OpeningEntry | None, int)` — also returns matched depth (half-moves); used for transition detection
- `eco_family_tokens(eco) -> str` — BM25 query tokens by ECO letter (A–E) + 13 granular ECO range overrides
- `PromptConfig.include_opening_name = True` (default) — adds `OPENING: Sicilian Najdorf (B90)` section to prompt

**Sub-task C2 — BM25 opening theory corpus (`knowledge_base.py`):**
- Added 15 opening family chunks: Sicilian Najdorf, Sicilian Dragon, Ruy Lopez Berlin, Ruy Lopez Closed, French, Caro-Kann, English, QGD, Slav/Semi-Slav, King's Indian, Nimzo-Indian, Queen's Indian, Grünfeld, Italian/Giuoco, King's Gambit
- Tags include ECO codes (`"B90"`, `"C65"`), family names (`"sicilian"`, `"ruy-lopez"`), and style descriptors (`"sharp"`, `"Tal"`, `"Petrosian"`)
- Total corpus: 28 → 43 chunks

**`retriever.py` wiring:**
- `_build_query()`: injects ECO tokens for any game from a known opening (opening + early middlegame); opening name tokens only when `game_length - match_depth <= 6`
- `retrieve_opening_theory()`: uses `lookup_with_depth` + depth check (`> 4 half-moves` → BM25) instead of piece count

**`prompt.py` wiring:**
- `_build_tiny_sections()`: `include_opening_name` → `OPENING: Name (ECO)` section before Theory
- `SECTION_FLAGS` updated with `"include_opening_name"` for ConfigPanel UI toggle
- `game_uci` field added to `AlexanderResult` (set in `commentary.py`)

---

## ⬜ #3 — Endgame Theory Chunks

**File:** `knowledge_base.py`  
**Complexity:** 🟡

Add position-type-specific endgame chunks (KPK, R+P vs R, B vs N, Q vs R, pure pawn) with structured tags; add material-based phase signal to `_build_query()` when `phase == "endgame"`.

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

---

## Сводка: что сделано / что осталось

### ✅ Реализовано (все незафиксированные изменения в uncommitted diff)

| # | Модуль / файл | Суть |
|---|---------------|------|
| #11 | `retriever.py` | Фильтр числовых токенов и координат из BM25 запроса |
| #10 | `retriever.py` | Семантические токены по качеству хода (blunder/mistake/inaccuracy) |
| #9 | `retriever.py`, `knowledge_base.py` | Теги в BM25-индексе; 15 дебютных чанков (ECO A–E) |
| #6 | `prompt.py`, `verbalizer.py` | Правильный цвет хода в атрибуции; фикс краша на pawn captures |
| #4/#5 | `prompt.py`, `eval_parser.py` | Verbose Alexander-разборщик; FULL/MEDIUM/MINIMAL конфиги; 4 sentences в системном промпте |
| #1 | `opening_book.py`, `retriever.py`, `prompt.py` | Дебютная книга (500 дебютов); opening theory vs BM25; ECO-токены в запросе |
| — | `llm.py` | LLM-gap фикс: retry на think-only + `/no_think` с первой попытки |
| — | `commentary.py` | Opening→Middlegame transition фикс; `prev_game_phase` пробрасывается в промпт |
| #2 | `anomaly_detector.py`, `prompt.py` | 6 аномальных гейтов; phase transition remark; структурные BM25-токены |
| — | `tests/` | 76 тестов: `test_commentary_gaps` (17) + `test_retriever` (25) + `test_anomaly_detector` (38) |
| — | `tests/eval_game.py` | Полный eval-пайплайн: fixture-кеш, LLM-трейсер, аномальный трейсер, print_summary |
| — | `tests/analyze_eval.ipynb` | Ноутбук анализа: динамика промпта, аномальные флаги, threshold sensitivity sweep |
| — | `alexander_interpreter/build_engine.sh/.bat` | Скрипты сборки движка (macOS/Linux/Windows) |

### ⬜ Осталось сделать

| # | Задача | Сложность | Приоритет |
|---|--------|-----------|-----------|
| #3 | **Endgame Theory Chunks** — position-type chunks (KPK, R+P vs R, B vs N) в `knowledge_base.py` + материальный сигнал в `_build_query()` при `phase == "endgame"` | 🟡 | ⬆️ высокий |
| #7 | **deepeval Pipeline** — авто-оценка качества комментария по 7 критериям из `Опросник для тестов.txt`; ablation по feature-группам | 🔴 | ➡️ средний (для диплома) |
| #8 | **Visualizations** — радар-чарты, bar-charts по ablation, Wilcoxon-тест | 🟡 | ➡️ средний (для диплома) |
