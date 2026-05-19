# archive — старая система ShashChess

Эта папка содержит **первую версию** интерпретатора, написанную под движок ShashChess.
Она **заменена** пакетом `alexander_interpreter/`, который использует движок Alexander
с расширенным UCI (14 зон Шашина, MultiPV, eval trace).

## Структура

```
archive/
├── interpreter/     # Ядро ShashChess-интерпретатора
│   ├── config.py        — env-переменные (ENGINE_PATH, LM_STUDIO_URL, ...)
│   ├── knowledge_base.py — база знаний (3 зоны: Tal/Capablanca/Petrosian)
│   ├── mock_engine.py   — тип EngineResult + сгенерированные позиции ShashChess
│   ├── llm.py           — LM Studio клиент
│   ├── prompt.py        — построитель промптов для LLM
│   ├── retriever.py     — BM25-поиск по базе знаний
│   └── shashin.py       — описания 3 зон Шашина
│
├── data/            # Датасеты и позиции
│   ├── positions.py     — 60 FEN-позиций из CCC benchmark (с ходами, REF, GAC)
│   └── eval_dataset.csv — датасет для оценки качества комментариев
│
└── tools/           # Скрипты для генерации данных и оценки
    ├── smoke_test.py              — smoke-тест ShashChess-системы
    ├── generate_positions.py      — генерирует mock_engine.py из ShashChess
    ├── generate_from_positions.py — генерирует mock_engine.py из positions.py
    ├── build_csv.py               — собирает eval_dataset.csv
    └── run_eval_openrouter.py     — оценка через OpenRouter API
```

## Как запускать

Скрипты из `tools/` добавляют нужные пути в sys.path автоматически.
Запускать можно из любой директории:

```bash
python3 archive/tools/smoke_test.py --dry-run
python3 archive/tools/generate_from_positions.py --engine path/to/shashchess
```
