# Chess Analyzer — Alexander + AI Commentary

Full-stack web application that combines the **Alexander chess engine** with an **LLM** to produce move-by-move analysis and natural language commentary for any PGN game or FEN position.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Data Flow](#data-flow)
3. [Backend Modules](#backend-modules)
4. [Frontend Components](#frontend-components)
5. [Running Locally](#running-locally)
6. [Docker Deployment](#docker-deployment)
7. [Connecting an LLM](#connecting-an-llm)
8. [Configuration Reference](#configuration-reference)
9. [API Reference](#api-reference)

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                          Browser                               │
│                                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │AnalysisInput │  │  MoveList    │  │     Commentary       │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ ProgressBars │  │  Navigation  │  │   Board + EvalBar    │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │             useAnalysis (React hook)                     │  │
│  │  SSE reader · positions state · phase / progress state  │  │
│  └──────────────────────────────┬───────────────────────────┘  │
└─────────────────────────────────┼──────────────────────────────┘
                                  │  POST /api/analyze
                                  │  ← Server-Sent Events (SSE)
┌─────────────────────────────────▼──────────────────────────────┐
│                      FastAPI Backend                           │
│                                                                │
│  main.py ──► stream.py ──► parser.py                          │
│                    │                                           │
│                    ├──► _engine_phase()                        │
│                    │         └── AlexanderEngine (subprocess)  │
│                    │                                           │
│                    └──► _commentary_phase()                    │
│                              └── commentary.py                 │
│                                    └── build_tiny_prompt()     │
└────────────────────────────────────────────────────────────────┘
          │ subprocess (UCI)               │ HTTP
          ▼                               ▼
┌─────────────────────┐        ┌──────────────────────────┐
│  Alexander Engine   │        │  LLM API                 │
│  (chess engine)     │        │  (LM Studio / Ollama /   │
│  depth 15+, top-N   │        │   vLLM — OpenAI-compat.) │
└─────────────────────┘        └──────────────────────────┘
```

---

## Data Flow

```
User pastes PGN / FEN
        │
        ▼
  parse_input(text)
        │  python-chess reads PGN or board.fen()
        ▼
  build_positions(game)
        │  returns [{index, fen, san, uci, move_number, color, …}]
        │  starting position is index 0 (san=None)
        ▼
─── Engine Phase ────────────────────────────────────────────────
  for each position (sequential, single engine process):
        │
        ├── chess.Board.is_game_over() → skip if true
        │
        └── AlexanderEngine.analyze(fen, uci, board)
                │  UCI: "position fen … moves …"  →  "go depth N"
                │  reads "info depth … score cp … multipv …"
                ▼
           AlexanderResult
            ├── eval_cp / eval_mate   (White-perspective for UI)
            ├── score_cp_stm          (side-to-move perspective)
            ├── best_move_san / uci
            ├── wdl_win / draw / loss
            ├── shashin_zone
            ├── top_moves[]
            ├── pv_san[]
            └── raw_eval_lines[]

        quality = quality_from_loss(prev_eval_cp − curr_eval_cp)

        → SSE: {"type":"engine", "index":i, "position":{…}}
─────────────────────────────────────────────────────────────────
        → SSE: {"type":"commentary_start"}
─── Commentary Phase ────────────────────────────────────────────
  all positions dispatched concurrently (max 3 at a time):
        │
        └── generate_commentary(positions, idx)
                │
                ├── build_tiny_prompt_sections()  →  debug sections
                ├── build_tiny_prompt()           →  system + user prompt
                │
                └── llm_ask(prompt) via HTTP → commentary text

        → SSE: {"type":"commentary", "index":i, "commentary":"…"}
─────────────────────────────────────────────────────────────────
        → SSE: {"type":"complete"}
```

### Move Quality Thresholds

| Centipawn loss | Label       | Symbol |
|---------------|-------------|--------|
| ≤ 5           | Best move   | ✓      |
| ≤ 20          | Excellent   | !      |
| ≤ 50          | Good        | —      |
| ≤ 100         | Inaccuracy  | ?!     |
| ≤ 200         | Mistake     | ?      |
| > 200         | Blunder     | ??     |

---

## Backend Modules

```
webapp/backend/
├── main.py         FastAPI app, CORS, /api/analyze route, static file mount
├── config.py       All env-var settings (engine path, depth, LLM URL, …)
├── stream.py       stream_analysis orchestrator, _engine_phase, _commentary_phase
├── parser.py       parse_input (PGN/FEN → game), build_positions (game → list[dict])
├── quality.py      quality_from_loss, auto_level, auto_question
├── commentary.py   generate_commentary — builds prompt, calls LLM
└── requirements.txt
```

### Module dependency graph

```
main.py
  ├── config.py          (env vars + sys.path for alexander_interpreter)
  └── stream.py
        ├── config.py
        ├── parser.py    ──► stdlib (io, chess)
        ├── quality.py   ──► (no local deps)
        └── commentary.py
              ├── config.py
              ├── quality.py
              └── alexander_interpreter  (build_tiny_prompt, llm_ask, …)
```

---

## Frontend Components

```
webapp/frontend/src/
│
├── constants.js          QUALITY_SYMBOLS, QUALITY_LABEL, QUALITY_BADGE_CLASS,
│                         QUALITY_SYMBOL_CLASS, QUALITY_BG_CLASS, ARROW_* colours
│
├── utils/
│   └── eval.js           evalToPercent(cp, mate)  ·  formatEval(cp, mate, short?)
│
├── hooks/
│   └── useAnalysis.js    All SSE state: positions, phase, progress, analyze()
│
├── App.jsx               Layout only — wires hook → components
│
└── components/
    ├── AnalysisInput.jsx  PGN textarea + Analyze button + side toggle
    ├── ProgressBars.jsx   Engine / Commentary progress bars (hidden when idle/done)
    ├── Navigation.jsx     ⏮ ◀ Move N/total ▶ ⏭ controls
    ├── Board.jsx          react-chessboard wrapper (arrows, non-interactive)
    ├── EvalBar.jsx        Vertical White/Black win-probability bar
    ├── MoveList.jsx       Two-column move grid with quality highlights
    └── Commentary.jsx     Eval · best move · LLM text · engine line · debug panel
```

### Component tree

```
App
├── AnalysisInput
├── ProgressBars
└── main-layout
    ├── board-section
    │   ├── EvalBar
    │   ├── Board
    │   ├── Navigation
    │   └── legend
    └── analysis-section
        ├── MoveList
        └── Commentary
            └── DebugPanel (collapsible)
                ├── engine UCI output
                └── LLM prompt sections (accordion)
```

### SSE event types

| Event              | Payload fields                             | Frontend action                      |
|--------------------|--------------------------------------------|--------------------------------------|
| `start`            | `total`                                    | Set total, phase → `engine`          |
| `engine`           | `index`, `position`                        | Upsert position, inc engineProgress  |
| `commentary_start` | `total`                                    | phase → `commentary`                 |
| `commentary`       | `index`, `commentary`, `prompt_sections`   | Patch position commentary            |
| `complete`         | —                                          | phase → `done`                       |
| `error`            | `message`                                  | Show error banner                    |

---

## Running Locally

**Requirements:** Python 3.11+, Node 18+, Alexander binary, OpenAI-compatible LLM server.

### Backend

```bash
cd webapp/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd webapp/frontend
npm install
npm run dev          # http://localhost:5173 — proxies /api → localhost:8000
```

### Convenience script

```bash
cd webapp && ./start.sh
```

---

## Docker Deployment

The Dockerfile uses a **3-stage build**:

```
Stage 1: engine-builder  (debian:bookworm-slim)
  └── compiles Alexander from source (auto-detects arm64 / x86-64)

Stage 2: frontend-builder  (node:20-slim)
  └── npm ci + npm run build → /frontend/dist

Stage 3: runtime  (python:3.12-slim)
  ├── engine binary  →  /app/engine/alexander
  ├── frontend dist  →  /app/static  (served by FastAPI)
  └── backend + alexander_interpreter package
```

```bash
# Build and start on port 8080
docker compose up --build

# Custom model
MODEL_NAME="qwen3-1.7b" docker compose up
```

### Build for a specific platform

```bash
# Apple Silicon (ARM)
docker buildx build --platform linux/arm64 -t chess-analyzer .

# x86-64
docker buildx build --platform linux/amd64 -t chess-analyzer .
```

---

## Connecting an LLM

The commentary agent calls any **OpenAI-compatible** `/v1/chat/completions` endpoint.

### Option A — LM Studio

1. Download LM Studio, load a model (e.g. `Qwen3-0.6B`), start the Local Server (port `1234`).
2. Run Docker with default settings — `LM_STUDIO_URL` already points there.

### Option B — Ollama

```bash
ollama pull qwen3:0.6b
ollama serve
```

```bash
LM_STUDIO_URL=http://host.docker.internal:11434/v1 \
MODEL_NAME=qwen3:0.6b \
docker compose up --build
```

### Option C — Remote / vLLM

```env
LM_STUDIO_URL=http://192.168.1.50:8000/v1
MODEL_NAME=Qwen/Qwen3-4B-Instruct
```

> **Linux note:** `host.docker.internal` resolves via `extra_hosts: host.docker.internal:host-gateway` in `docker-compose.yml`.

---

## Configuration Reference

| Variable               | Default                                       | Description                            |
|------------------------|-----------------------------------------------|----------------------------------------|
| `ALEXANDER_ENGINE_PATH`| `<repo>/Alexander/src/alexander`              | Path to Alexander engine binary        |
| `ANALYSIS_DEPTH`       | `15`                                          | Engine search depth (higher = stronger)|
| `ENGINE_NUM_PV`        | `3`                                           | Top moves per position                 |
| `ENGINE_THREADS`       | `8`                                           | Engine thread count                    |
| `ENGINE_HASH_MB`       | `256`                                         | Engine hash table size (MB)            |
| `ENGINE_TIMEOUT`       | `60`                                          | Per-position timeout (seconds)         |
| `LM_STUDIO_URL`        | `http://host.docker.internal:1234/v1`         | OpenAI-compatible LLM endpoint         |
| `MODEL_NAME`           | `qwen3-0.6b`                                  | LLM model ID                           |
| `STATIC_DIR`           | `""` (disabled)                               | Path to compiled frontend (Docker)     |

---

## API Reference

### `POST /api/analyze`

Streams a Server-Sent Events response for the given game.

**Request body** (JSON):

```json
{
  "pgn":      "1. e4 e5 2. Nf3 Nc6 ...",
  "our_side": "white"
}
```

`pgn` accepts a full PGN string **or** a single FEN position.  
`our_side` controls the commentary perspective — `"white"` or `"black"`.

**Response:** `Content-Type: text/event-stream`

Each event:
```
data: {"type": "engine", "index": 3, "position": {...}}\n\n
```

See [SSE event types](#sse-event-types) above for the full list.
