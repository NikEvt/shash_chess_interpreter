# Chess Analysis Agent

Standalone LLM-agent: принимает данные от шахматного движка → возвращает объяснение позиции на английском.  
Designed for qwen3-0.6b via LM Studio. Работает локально, без интернета.

---

## Архитектура

```
EngineResult (mock / real UCI)
        │
        ▼
  retriever.py  ──── BM25 ────► knowledge_base.py
        │                        (28 теоретических чанков)
        ▼
   prompt.py   ──── собирает промпт (~150 токенов)
        │
        ▼
    llm.py     ──── POST /v1/chat/completions ──► LM Studio
        │
        ▼
   str response  (think-теги удалены)
```

**Потоки данных:**

| Файл | Роль |
|---|---|
| `mock_engine.py` | Входные данные: eval, best_move_san, WDL, shashin_type |
| `retriever.py` | BM25-поиск по knowledge_base, top-2 чанка |
| `shashin.py` | Словарь типов позиций (Tal/Capablanca/Petrosian → текст) |
| `prompt.py` | Сборка промпта; FEN намеренно исключён |
| `llm.py` | HTTP-клиент LM Studio, strip `<think>` |
| `config.py` | Все константы через env vars |

---

## Входные данные (`EngineResult`)

```python
EngineResult(
    fen="...",            # только для идентификации позиции, в промпт НЕ идёт
    best_move_uci="e1g1", # UCI — только для leak-проверки в тестах
    best_move_san="O-O",  # SAN — единственная нотация в промпте и ответе
    score_cp=200,         # centipawns; None если мат
    mate_in=1,            # плей до мата; None если нет
    wdl_win=620,          # 0–1000, сумма = 1000
    wdl_draw=310,
    wdl_loss=70,
    depth=22,
    shashin_type="Tal",   # "Tal" | "Capablanca" | "Petrosian"
    side_to_move="white", # "white" | "black"
)
```

Параметры пользователя: `level` (beginner/intermediate/advanced), `question` (best_move/explain/plan), `moves_history` (последние ходы в SAN).

---

## Расширение knowledge base

Добавить чанк в `knowledge_base.py`:

```python
{
    "id":   "unique_id",
    "tags": ["тема", "Shashin-тип", "ключевые слова для BM25"],
    "text": "Принцип, написанный одним абзацем на английском.",
},
```

**Правила:**
- Один чанк — один принцип. Длина: 2–5 предложений.
- `tags` влияют только на читаемость; BM25 ищет по `text`.
- Чем конкретнее термины в тексте, тем точнее поиск (пишите "isolated pawn", "rook on 7th rank", а не "weak piece").
- Индекс BM25 пересобирается автоматически при импорте `retriever.py`.

---

## Сильные стороны

- **Нет галлюцинаций о позиции** — модель не видит FEN, не "читает" доску; только структурированные факты от движка.
- **BM25 без зависимостей** — `rank_bm25` ~1 MB RAM, работает на любом телефоне.
- **Короткий промпт** (~150 токенов) — укладывается в контекст 0.6b-модели.
- **Легко тестируется** — `smoke_test.py --dry-run` не требует LM Studio.

## Слабые стороны

- **Качество ответа зависит от качества входных данных** — если движок даст плохой `best_move_san`, модель его и объяснит.
- **BM25 не понимает семантику** — запрос "endgame with rook" не найдёт чанк про "Philidor position" если там нет слова "rook". Лечится добавлением синонимов в `text` чанка.
- **`shashin_type` пока эвристический** — в `mock_engine.py` считается по `score_cp`, а не реальным выводом ShashChess. При интеграции с движком нужно парсить UCI-вывод.
- **Модель 0.6b не проверяет корректность хода** — она объясняет то, что ей сказали. Неверный `best_move_san` от движка не будет оспорен.

---

## Запуск

```bash
pip install httpx rank-bm25

# тесты без LM Studio
python3 smoke_test.py --dry-run

# тесты с живой моделью → пишет smoke_results.md
python3 smoke_test.py

# кастомный файл отчёта
python3 smoke_test.py -o my_report.md
```

Настройка через env vars: `ENGINE_PATH`, `LM_STUDIO_URL`, `MODEL_NAME`, `MAX_LLM_TOKENS`, `ENGINE_DEPTH`.
