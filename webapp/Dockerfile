# ── Stage 1: Build ShashChess engine ──────────────────────────────────────────
FROM debian:bookworm-slim AS engine-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        make g++ libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the whole repo subtree so ../scripts/net.sh resolves correctly
COPY ShashChess/ /ShashChess/
WORKDIR /ShashChess/src

# ShashChess Makefile unconditionally adds x86-only flags on Linux — strip them for ARM.
RUN sed -i 's/-mprefer-vector-width=256 -mno-avx512f//' Makefile && make clean

# Valid ShashChess ARCH values: armv8-dotprod (ARM64), x86-64-sse41-popcnt (x86)
ARG TARGETARCH
RUN ARCH_FLAG="x86-64-sse41-popcnt"; \
    [ "$TARGETARCH" = "arm64" ] && ARCH_FLAG="armv8-dotprod"; \
    make -j"$(nproc)" build ARCH="$ARCH_FLAG" COMP=gcc \
    && echo "Built: $(ls -lh shashchess)"


# ── Stage 2: Build React frontend ─────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /frontend
COPY agent/webapp/frontend/package*.json ./
RUN npm ci
COPY agent/webapp/frontend/ ./
RUN npm run build


# ── Stage 3: Runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim

# Runtime dependency for ShashChess LIVEBOOK feature
RUN apt-get update && apt-get install -y --no-install-recommends libcurl4 \
    && rm -rf /var/lib/apt/lists/*

# Engine binary + NNUE networks (loaded at runtime from same dir)
COPY --from=engine-builder /ShashChess/src/shashchess  /app/engine/shashchess
COPY --from=engine-builder /ShashChess/src/*.nnue      /app/engine/
RUN chmod +x /app/engine/shashchess

# Compiled frontend
COPY --from=frontend-builder /frontend/dist    /app/static

# Backend and agent
COPY agent/webapp/backend/   /app/backend/
COPY agent/            /app/agent/

# Python dependencies (no venv needed — isolated container)
RUN pip install --no-cache-dir \
        fastapi \
        "uvicorn[standard]" \
        python-chess \
        pydantic \
        httpx \
        rank-bm25 \
        aiofiles

WORKDIR /app/backend

ENV ENGINE_PATH=/app/engine/shashchess
ENV AGENT_DIR=/app/agent
ENV STATIC_DIR=/app/static
ENV ANALYSIS_DEPTH=15
# ↓ Override these to point at your local LM Studio or Ollama (see README.md)
ENV LM_STUDIO_URL=http://host.docker.internal:1234/v1
ENV MODEL_NAME=qwen3-0.6b

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
