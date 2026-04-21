# Chess Analyzer — Docker & AI Setup

## Quick start

```bash
cd chess_report/webapp

# Default: LM Studio on localhost:1234
docker compose up --build

# Open http://localhost:8080
```

The first build compiles ShashChess from source (~3–5 min).  
Subsequent builds use the Docker layer cache.

---

## Connecting a local AI model

The commentary agent calls an **OpenAI-compatible** `/v1/chat/completions` endpoint.  
Both LM Studio and Ollama expose this API.

Set two environment variables before running:

| Variable | Default | Description |
|---|---|---|
| `LM_STUDIO_URL` | `http://host.docker.internal:1234/v1` | Base URL of the API |
| `MODEL_NAME` | `qwen3-0.6b` | Model identifier sent in each request |

---

### Option A — LM Studio

1. Download **LM Studio** from [lmstudio.ai](https://lmstudio.ai)
2. Load a model (recommended: `Qwen3-0.6B`, `Qwen3-1.7B`, or any instruction model)
3. Go to **Local Server** tab → click **Start Server**  
   Default port: `1234`
4. Run the container (no extra config needed — default URL already points to LM Studio):

```bash
docker compose up --build
```

To use a different model:

```bash
MODEL_NAME="qwen3-1.7b" docker compose up
```

---

### Option B — Ollama

1. Install **Ollama** from [ollama.com](https://ollama.com)
2. Pull a model:

```bash
ollama pull qwen3:0.6b
# or a larger model for better commentary:
ollama pull qwen3:1.7b
```

3. Start Ollama (it runs on port `11434` by default):

```bash
ollama serve   # usually already running as a service
```

4. Run the container pointing at Ollama:

```bash
LM_STUDIO_URL=http://host.docker.internal:11434/v1 \
MODEL_NAME=qwen3:0.6b \
docker compose up --build
```

Or set them permanently in a `.env` file next to `docker-compose.yml`:

```env
LM_STUDIO_URL=http://host.docker.internal:11434/v1
MODEL_NAME=qwen3:0.6b
```

Then just:

```bash
docker compose up
```

> **Linux note:** `host.docker.internal` resolves automatically via the  
> `extra_hosts: host.docker.internal:host-gateway` line in `docker-compose.yml`.  
> No extra configuration needed.

---

### Option C — Remote / cloud model

Any OpenAI-compatible server works. Example with a self-hosted vLLM instance:

```env
LM_STUDIO_URL=http://192.168.1.50:8000/v1
MODEL_NAME=Qwen/Qwen3-4B-Instruct
```

---

## Engine settings

| Variable | Default | Description |
|---|---|---|
| `ANALYSIS_DEPTH` | `15` | ShashChess search depth (higher = slower but stronger) |

```bash
ANALYSIS_DEPTH=18 docker compose up
```

---

## Build for a specific platform

```bash
# Apple Silicon (ARM)
docker buildx build --platform linux/arm64 -t chess-analyzer .

# x86-64
docker buildx build --platform linux/amd64 -t chess-analyzer .
```

---

## Without Docker (development)

```bash
# Terminal 1 — backend
cd webapp/backend
.venv/bin/uvicorn main:app --reload --port 8000

# Terminal 2 — frontend (with hot reload)
cd webapp/frontend
npm run dev

# Open http://localhost:5173
```

Or use the convenience script:

```bash
cd webapp && ./start.sh
```
