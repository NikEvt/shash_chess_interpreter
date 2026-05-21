import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

# config.py must be imported first — it adjusts sys.path for alexander_interpreter
from config import STATIC_DIR  # noqa: E402
from stream import stream_analysis  # noqa: E402
from alexander_interpreter import SECTION_FLAGS  # noqa: E402


# ── Logging ───────────────────────────────────────────────────────────────────

def _setup_logging() -> None:
    log = logging.getLogger("webapp.analysis")
    if not log.handlers:
        fh = logging.FileHandler("engine.log")
        fh.setLevel(logging.INFO)
        log.addHandler(fh)
        log.setLevel(logging.INFO)
        log.propagate = False

_setup_logging()


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="Chess Analyzer — Alexander")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    pgn: str
    our_side: str = "white"        # "white" | "black"
    config_preset: str = "full"    # "minimal" | "compact" | "medium" | "full" | "custom"
    config_flags: dict[str, bool] = {}  # per-section overrides (used when preset="custom" or partial override)
    thinking: bool = False         # Qwen3 /think vs /no_think


@app.get("/api/config/sections")
async def get_config_sections():
    """Return available prompt section flags for the UI config panel."""
    return JSONResponse({
        "sections": [
            {"key": key, "label": label, "group": group}
            for key, label, group in SECTION_FLAGS
        ]
    })


@app.post("/api/analyze")
async def analyze(request: AnalysisRequest):
    our_side = request.our_side if request.our_side in ("white", "black") else "white"
    return StreamingResponse(
        stream_analysis(request.pgn, our_side, request.config_preset, request.config_flags, request.thinking),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "Connection":       "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Static frontend (production / Docker) ────────────────────────────────────

if STATIC_DIR and os.path.isdir(STATIC_DIR):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
