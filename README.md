# shash_chess_interpreter

`shash_chess_interpreter` is a chess analysis and commentary project that combines the **Alexander** engine, Shashin-style evaluation zones, BM25-based retrieval, and an LLM layer to turn raw engine output into readable move-by-move explanations.[web:1]
The repository includes the core Python package, evaluation scripts, tests for retrieval and commentary robustness, and a full-stack web application for interactive PGN/FEN analysis.[page:1]

## Features

- Engine-driven analysis through the `alexander_interpreter` package, including engine orchestration, evaluation parsing, Shashin zone labeling, opening knowledge, prompting, and verbalization logic.[page:1]
- Retrieval-augmented commentary with BM25 search over chess knowledge chunks plus opening-theory lookup for book-adjacent positions.[page:1]
- LLM commentary generation with retry safeguards for empty or think-only outputs, based on the test suite and evaluation scripts in `tests/`.[page:1]
- A web application that streams engine analysis and commentary to the frontend with Server-Sent Events for PGN and FEN inputs.[page:1]
- Utility scripts and notebooks for smoke testing, regression testing, and deeper commentary evaluation workflows.[page:1]

## Repository layout

```text
.
├── alexander_interpreter/   # Core package: engine, retrieval, prompting, verbalization
├── webapp/                  # FastAPI + frontend application for interactive analysis
├── tests/                   # Unit tests and end-to-end evaluation scripts
├── scripts/                 # Smoke tests and helper scripts
├── archive/                 # Older notes / archived materials
└── requirements.txt         # Python dependencies
```

## Core components

### `alexander_interpreter/`

The main package contains the project logic for parsing engine output, assigning Shashin-style strategic zones, retrieving opening knowledge, and generating natural-language commentary around each position.[page:1]
Important modules visible in the repository include `engine.py`, `eval_parser.py`, `retriever.py`, `opening_book.py`, `opening_theory_kb.py`, `shashin.py`, `prompt.py`, `llm.py`, and `verbalizer.py`.[page:1]

### `webapp/`

The web application is described as a full-stack analyzer that accepts PGN or FEN input, runs sequential engine analysis, and then launches concurrent commentary generation through an LLM API.[page:1]
Its documented architecture uses a FastAPI backend, Server-Sent Events streaming, an Alexander engine subprocess, and an OpenAI-compatible LLM endpoint such as LM Studio, Ollama, or vLLM.[page:1]

### `tests/`

The test suite mixes lightweight pytest-based unit tests with full evaluation scripts that require a real engine and LLM endpoint.[page:1]
Documented tests cover BM25 retrieval, opening-book lookup, phase detection, commentary retry behavior, anomaly detection, and Deepeval-based commentary checks.[page:1]

## Installation

### Prerequisites

- Python 3.12 recommended by the documented test commands.[page:1]
- Access to the Alexander engine binary for full analysis workflows.[page:1]
- An OpenAI-compatible local or remote LLM endpoint for commentary generation, such as LM Studio.[page:1]

### Install dependencies

```bash
python3.12 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Current declared Python dependencies are `httpx`, `rank-bm25`, and `deepeval`.[page:1]

## Quick start

### Run unit tests

```bash
python3.12 -m pytest tests/ -v
```

This runs the lightweight test suite without requiring the chess engine or an LLM backend.[page:1]

### Run a full game evaluation

```bash
python tests/eval_game.py
python tests/eval_game.py --pgn my_game.pgn --config medium --out trace.json
```

The evaluation script runs a real game through Alexander and an LLM, then records traces including prompts, retries, engine outputs, and final commentary.[page:1]

### Run the web app

Start from the `webapp/` directory and follow its local or Docker setup, as the included app is designed for interactive analysis of arbitrary games and positions.[page:1]
A dedicated `webapp/README.md` already documents architecture, backend/frontend roles, local startup, Docker deployment, configuration, and API behavior.[page:1]

## How it works

1. Input is provided as a PGN game or a FEN position through scripts or the web app.[page:1]
2. The system parses positions and sends them to the Alexander engine through a UCI subprocess interface.[page:1]
3. Engine output is converted into structured fields such as centipawn or mate scores, best moves, WDL estimates, principal variations, and Shashin zones.[page:1]
4. Retrieval modules add opening-book or theory context, while the prompt builder assembles a compact explanation request for the LLM.[page:1]
5. The LLM returns move commentary, and retry logic handles truncated or think-only responses before final text is emitted or streamed.[page:1]

## Configuration

The repository exposes configuration through package modules such as `config.py`, and the tests mention environment variables like `ALEXANDER_ENGINE_PATH` and `LM_STUDIO_URL` for engine and model connectivity.[page:1]
For the web application, consult `webapp/README.md` for exact runtime and deployment settings.[page:1]

## Development notes

- Use `scripts/smoke_test_alexander.py` to verify the engine path and basic engine integration.[page:1]
- Use `tests/test_retriever.py` to validate retrieval logic independently from the LLM stack.[page:1]
- Use `tests/test_commentary_gaps.py` to regression-test commentary retry behavior and empty-output handling.[page:1]
- Use the notebooks in `tests/` for deeper analysis of evaluation traces and commentary quality.[page:1]

## Suggested environment variables

```bash
export ALEXANDER_ENGINE_PATH=/path/to/alexander
export LM_STUDIO_URL=http://localhost:1234
```

These names are explicitly referenced in the repository test documentation for full evaluation runs.[page:1]

## Roadmap ideas

- Add a top-level CLI entry point for PGN/FEN analysis.
- Document expected engine build steps and supported binaries in the main README.
- Add sample screenshots or GIFs for the web application.
- Provide a minimal `.env.example` for engine and LLM configuration.
- Include an example analysis output JSON for quicker onboarding.

## Related docs

- See [`webapp/README.md`](./webapp/README.md) for the application architecture and deployment details.
- See [`tests/README.md`](./tests/README.md) for test categories and evaluation scripts.
- See [`archive/README.md`](./archive/README.md) for archived project notes.

## License

No license file was visible in the inspected repository snapshot, so usage terms should be clarified before external redistribution or commercial reuse.[page:1]
