# ── Stage 1: Build Alexander engine ───────────────────────────────────────────
FROM debian:bookworm-slim AS engine-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        make g++ libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY Alexander/ /Alexander/
WORKDIR /Alexander/src

# Strip x86-only flags that break compilation on ARM64
RUN sed -i 's/-mprefer-vector-width=256//g; s/-mno-avx512f//g' Makefile && make clean

ARG TARGETARCH
RUN ARCH_FLAG="x86-64-sse41-popcnt"; \
    [ "$TARGETARCH" = "arm64" ] && ARCH_FLAG="armv8-dotprod"; \
    make -j"$(nproc)" build ARCH="$ARCH_FLAG" COMP=gcc \
    && echo "Built: $(ls -lh alexander)"


# ── Stage 2: Build React frontend ─────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /frontend
COPY webapp/frontend/package*.json ./
RUN npm ci
COPY webapp/frontend/ ./
RUN npm run build


# ── Stage 3: Runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends libcurl4 \
    && rm -rf /var/lib/apt/lists/*

# Engine binary
COPY --from=engine-builder /Alexander/src/alexander /app/engine/alexander
RUN chmod +x /app/engine/alexander

# Compiled frontend
COPY --from=frontend-builder /frontend/dist /app/static

# Backend + alexander_interpreter package
COPY webapp/backend/      /app/backend/
COPY alexander_interpreter/ /app/alexander_interpreter/
COPY archive/data/chess_openings_dataset_checkpoint.tsv /app/archive/data/chess_openings_dataset_checkpoint.tsv
COPY archive/data/knowledge_base.json                  /app/archive/data/knowledge_base.json
COPY archive/data/openings/openings_text_checkpoint.tsv /app/archive/data/openings/openings_text_checkpoint.tsv

# Python dependencies
RUN pip install --no-cache-dir \
        fastapi \
        "uvicorn[standard]" \
        python-chess \
        pydantic \
        httpx \
        rank-bm25 \
        aiofiles

WORKDIR /app/backend

ENV PYTHONPATH=/app
ENV ALEXANDER_ENGINE_PATH=/app/engine/alexander
ENV STATIC_DIR=/app/static
ENV ANALYSIS_DEPTH=15
ENV LM_STUDIO_URL=http://host.docker.internal:1234/v1
ENV MODEL_NAME=qwen3-0.6b

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
