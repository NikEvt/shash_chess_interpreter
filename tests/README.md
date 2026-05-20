# tests/

Два типа файлов: pytest-тесты (без внешних зависимостей) и eval-скрипт (требует движок + LM Studio).

---

## Быстрый старт

```bash
# Все unit-тесты (без движка, без LLM)
python3.12 -m pytest tests/ -v

# Полный eval партии (нужны движок и LM Studio)
python tests/eval_game.py
python tests/eval_game.py --pgn my_game.pgn --config medium --out trace.json
```

---

## Файлы

### `test_retriever.py` — BM25 retriever и opening book

Unit-тесты без внешних зависимостей.

| Группа | Что проверяет |
|--------|---------------|
| `test_book_loaded` | TSV загрузился, книга непустая |
| `test_lookup_exact_*` | Точное совпадение UCI последовательности с книгой |
| `test_lookup_prefix_*` | Матч по кратчайшему префиксу; предпочитает более глубокое совпадение |
| `test_eco_tokens_*` | `eco_family_tokens()` возвращает токены по коду ECO |
| `test_phase_*` | `_position_phase()` по числу фигур: opening / middlegame / endgame |
| `test_opening_theory_*` | `retrieve_opening_theory()`: возвращает теорию пока игра близко к книге (≤4 полухода от книжной линии), иначе None |
| `test_retrieve_*` | BM25 `retrieve()`: возвращает список чанков, уважает `top_k`, работает для всех фаз |

```bash
python3.12 -m pytest tests/test_retriever.py -v
```

---

### `test_commentary_gaps.py` — LLM retry и защита от пустых комментариев

Unit-тесты без внешних зависимостей. Регрессия на баг: модель выдаёт только `<think>...</think>` блок, `_strip_think()` возвращает `""`, комментарий молча пропускается.

| Группа | Что проверяет |
|--------|---------------|
| `test_strip_think_*` | `_strip_think()`: убирает закрытые и незакрытые `<think>` блоки; сохраняет текст до/после блока |
| `test_ask_retries_when_think_only` | **Ключевая регрессия**: пустой результат после strip → retry срабатывает |
| `test_ask_retries_on_truncation` | `finish_reason == "length"` → retry |
| `test_ask_retry_budget_is_plus_256` | Бюджет retry = `max_tokens + 256`, не `max(max_tokens, 512)` |
| `test_ask_no_retry_when_response_is_fine` | Нормальный ответ → ровно один вызов |
| `test_ask_fallback_to_empty_if_both_attempts_think_only` | Оба вызова think-only → возвращает `str`, не падает |

```bash
python3.12 -m pytest tests/test_commentary_gaps.py -v
```

---

### `eval_game.py` — полный eval пайплайн

Скрипт (не pytest). Прогоняет партию через реальный движок Alexander и реальный LLM, собирает полный трейс каждого вызова.

**Требует:** движок по пути `Alexander/src/alexander` (или `ALEXANDER_ENGINE_PATH`) и LM Studio на `http://localhost:1234` (или `LM_STUDIO_URL`).

**Fixture (кеш движка):**

Первый запуск прогоняет движок и сохраняет результаты в `tests/fixtures/alekhine_bogoljubov_1942.json`. Все последующие запуски загружают этот файл и пропускают движок — требуется только LM Studio.

```bash
# Первый запуск — нужен движок, создаёт fixture
python tests/eval_game.py

# Все следующие — только LLM
python tests/eval_game.py

# Принудительно перегнать через движок
python tests/eval_game.py --rerun-engine

# Кастомный путь к fixture
python tests/eval_game.py --fixture tests/fixtures/my_game.json
```

Fixture сохраняет для каждой позиции: `eval_cp`, `eval_mate`, `shashin_zone`, WDL, `best_move_san/uci`, `pv_san`, `engine_summary` (сырые строки eval), `eval_loss_cp`, `quality` и полный `AlexanderResult` (сериализован через `dataclasses.asdict`).

**Что пишет в консоль:**

```
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

**Что сохраняет в JSON** (`eval_trace_<timestamp>.json`):

```jsonc
{
  "game": { "White": "Alexander Alekhine", ... },
  "traces": [
    {
      "san": "e4", "eval_cp": 18, "shashin_zone": "CAPABLANCA",
      "question_type": "explain",
      "prompt_sections": [{"label": "System instruction", "content": "..."}, ...],
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

**CLI:**

```bash
# Партия по умолчанию (Алехин–Боголюбов 1942), конфиг full
python tests/eval_game.py

# Своя партия (fixture будет создан рядом по --fixture)
python tests/eval_game.py --pgn path/to/game.pgn --fixture tests/fixtures/my_game.json

# Пресет конфига: minimal | compact | medium | full
python tests/eval_game.py --config medium

# Отключить отдельные секции поверх пресета
python tests/eval_game.py --config full --no-theory --no-opening-name --no-pv

# Принудительно перегнать через движок
python tests/eval_game.py --rerun-engine

# Сохранить LLM-трейс в конкретный файл
python tests/eval_game.py --out results/my_trace.json

# Все флаги
python tests/eval_game.py \
    --pgn game.pgn \
    --fixture tests/fixtures/game.json \
    --config full \
    --our-side white \
    --no-theory \
    --no-opening-name \
    --no-score-table \
    --no-pawn-structure \
    --no-mobility \
    --no-pv \
    --engine-timeout 30 \
    --out trace.json
```

### `fixtures/`

Директория для кешированных результатов движка. Файлы сюда записывает `eval_game.py` при первом прогоне. Зафиксированная партия (`alekhine_bogoljubov_1942.json`) хранится в репозитории — позволяет запускать eval и LLM-тесты без движка.
