import asyncio
import io
import json
import logging
import os
import sys
from typing import AsyncGenerator

import chess
import chess.pgn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ── Alexander interpreter package ─────────────────────────────────────────────
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from alexander_interpreter import (  # noqa: E402
    AlexanderResult,
    build_tiny_prompt,
    build_tiny_prompt_sections,
    ask as llm_ask,
    LMStudioError,
    win_prob_to_shashin_zone,
    ENGINE_DEPTH,
    ENGINE_NUM_PV,
)
from alexander_interpreter.engine import AlexanderEngine  # noqa: E402

# ── Config ─────────────────────────────────────────────────────────────────────
ENGINE_PATH = os.path.abspath(
    os.getenv(
        "ALEXANDER_ENGINE_PATH",
        os.path.join(REPO_ROOT, "Alexander/src/alexander"),
    )
)
ANALYSIS_DEPTH = int(os.getenv("ANALYSIS_DEPTH", str(ENGINE_DEPTH)))
NUM_PV = int(os.getenv("ENGINE_NUM_PV", str(ENGINE_NUM_PV)))

_log = logging.getLogger("webapp.analysis")
if not _log.handlers:
    _fh = logging.FileHandler("engine.log")
    _fh.setLevel(logging.INFO)
    _log.addHandler(_fh)
    _log.setLevel(logging.INFO)
    _log.propagate = False

app = FastAPI(title="Chess Analyzer — Alexander")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    pgn: str
    our_side: str = "white"   # "white" | "black"


# ── Helpers ───────────────────────────────────────────────────────────────────

def quality_from_loss(loss_cp: int) -> str:
    if loss_cp <= 5:   return "best"
    if loss_cp <= 20:  return "excellent"
    if loss_cp <= 50:  return "good"
    if loss_cp <= 100: return "inaccuracy"
    if loss_cp <= 200: return "mistake"
    return "blunder"


def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def parse_input(text: str) -> chess.pgn.Game | None:
    text = text.strip()
    game = chess.pgn.read_game(io.StringIO(text))
    if game is not None:
        return game
    try:
        board = chess.Board(text)
        game = chess.pgn.Game()
        game.setup(board)
        return game
    except ValueError:
        return None


# ── Level / question selection ────────────────────────────────────────────────

def _auto_level(score_cp: int | None, mate_in: int | None) -> str:
    if mate_in is not None:
        return "intermediate"
    if score_cp is None:
        return "beginner"
    if abs(score_cp) > 300:
        return "advanced"
    if abs(score_cp) > 100:
        return "intermediate"
    return "beginner"


def _auto_question(
    score_cp: int | None,
    mate_in: int | None,
    shashin_zone: str,
    played_move: str | None,
    best_move_san: str | None,
) -> str:
    if played_move and best_move_san and played_move != best_move_san:
        return "best_move"
    if mate_in is not None:
        return "best_move"
    if "PETROSIAN" in shashin_zone:
        return "plan"
    if "TAL" in shashin_zone:
        return "best_move"
    return "explain"




# ── Commentary via agent ───────────────────────────────────────────────────────

async def generate_commentary(
    positions: list[dict],
    idx: int,
    semaphore: asyncio.Semaphore,
    our_side: str = "white",
) -> str:
    import dataclasses

    pos = positions[idx]

    if pos["san"] is None:
        return "The game begins. Both players will fight for central control and piece development."

    async with semaphore:
        # Engine recommendation from the PREVIOUS position (what should have been played)
        prev_best_san = ""
        prev_best_uci = ""
        prev_eval_cp: int | None = None
        board_before: chess.Board | None = None
        if idx > 0:
            prev = positions[idx - 1]
            prev_best_uci = prev.get("best_move_uci") or ""
            prev_best_san = prev.get("best_move_san") or ""
            prev_eval_cp = prev.get("eval_cp")
            try:
                board_before = chess.Board(prev["fen"])
            except Exception:
                pass

        played_uci = pos.get("uci") or ""
        is_best = bool(played_uci and prev_best_uci and played_uci == prev_best_uci)

        # Current position evals (White-perspective)
        curr_eval_cp: int | None = pos.get("eval_cp")
        curr_eval_mate: int | None = pos.get("eval_mate")
        eval_loss: int | None = pos.get("eval_loss_cp")

        # Build AlexanderResult and FIX best_move_san to be the PREV position's recommendation
        result = pos.get("alexander_result")
        if result is None:
            stm_cp = pos.get("score_cp_stm")
            played_cp = (-stm_cp) if stm_cp is not None else None
            wdl_win = pos.get("wdl_loss", 500)
            wdl_draw = pos.get("wdl_draw", 0)
            wdl_loss = pos.get("wdl_win", 500)
            shashin_zone = win_prob_to_shashin_zone(wdl_win / 10.0)
            result = AlexanderResult(
                fen=pos["fen"],
                side_to_move=pos.get("color") or "white",
                played_move=pos["san"],
                best_move_uci=prev_best_uci,
                best_move_san=prev_best_san or pos["san"],
                score_cp=played_cp,
                mate_in=pos.get("eval_mate"),
                wdl_win=wdl_win,
                wdl_draw=wdl_draw,
                wdl_loss=wdl_loss,
                shashin_zone=shashin_zone,
                top_moves=pos.get("top_moves", []),
                pv_san=pos.get("pv_san", []),
                depth=ANALYSIS_DEPTH,
            )
            print(f"DEBUG: side_to_move: {result.side_to_move}")
        else:
            # Fix: replace best_move_san with prev position's recommendation
            corrected_best = prev_best_san or result.best_move_san
            result = dataclasses.replace(result, best_move_san=corrected_best)

        if result.side_to_move == "white":
            result = dataclasses.replace(result, side_to_move="black")
        else:
            result = dataclasses.replace(result, side_to_move="white")

        question = _auto_question(
            result.score_cp, result.mate_in,
            result.shashin_zone,
            result.played_move, result.best_move_san,
        )

        prompt = build_tiny_prompt(
            result,
            prev_eval_cp=prev_eval_cp,
            curr_eval_cp=curr_eval_cp,
            curr_eval_mate=curr_eval_mate,
            our_side=our_side,
            question_type=question,
            board_before=board_before,
            eval_loss=eval_loss,
        )
        sections = build_tiny_prompt_sections(
            result,
            prev_eval_cp=prev_eval_cp,
            curr_eval_cp=curr_eval_cp,
            curr_eval_mate=curr_eval_mate,
            our_side=our_side,
            question_type=question,
            board_before=board_before,
            eval_loss=eval_loss,
        )
        positions[idx]["prompt_sections"] = sections
        max_tokens = 350

        try:
            text = await asyncio.to_thread(llm_ask, prompt, max_tokens=max_tokens)
            return text
        except LMStudioError as e:
            return f"[LLM unavailable: {e}]"
        except Exception:
            return f"{pos['san']}."


# ── Main analysis stream ───────────────────────────────────────────────────────

async def stream_analysis(pgn_text: str, our_side: str = "white") -> AsyncGenerator[str, None]:
    game = parse_input(pgn_text)
    if game is None:
        yield sse({"type": "error", "message": "Cannot parse input as PGN or FEN."})
        return

    positions: list[dict] = []
    board = game.board()

    positions.append({
        "index": 0,
        "fen": board.fen(),
        "san": None,
        "uci": None,
        "move_number": 0,
        "color": None,
        "best_move_san": None,
        "best_move_uci": None,
        "eval_cp": None,
        "eval_mate": None,
        "score_cp_stm": None,
        "shashin_zone": "CAPABLANCA",
        "wdl_win": 500,
        "wdl_draw": 0,
        "wdl_loss": 500,
        "top_moves": [],
        "pv_san": [],
        "quality": "book",
        "eval_loss_cp": None,
        "commentary": None,
        "engine_summary": [],
        "prompt_sections": None,
        "alexander_result": None,
    })

    for move in game.mainline_moves():
        san = board.san(move)
        color = "white" if board.turn == chess.WHITE else "black"
        move_number = board.fullmove_number
        board.push(move)
        positions.append({
            "index": len(positions),
            "fen": board.fen(),
            "san": san,
            "uci": move.uci(),
            "move_number": move_number,
            "color": color,
            "best_move_san": None,
            "best_move_uci": None,
            "eval_cp": None,
            "eval_mate": None,
            "score_cp_stm": None,
            "shashin_zone": "CAPABLANCA",
            "wdl_win": 500,
            "wdl_draw": 0,
            "wdl_loss": 500,
            "top_moves": [],
            "pv_san": [],
            "quality": None,
            "eval_loss_cp": None,
            "commentary": None,
            "engine_summary": [],
            "prompt_sections": None,
            "alexander_result": None,
        })

    total = len(positions)
    yield sse({"type": "start", "total": total})

    # ── Engine analysis with Alexander (subprocess wrapper — runs eval + go) ────
    engine = AlexanderEngine(
        ENGINE_PATH,
        depth=ANALYSIS_DEPTH,
        num_pv=NUM_PV,
        threads=int(os.getenv("ENGINE_THREADS", "8")),
        hash_mb=int(os.getenv("ENGINE_HASH_MB", "256")),
    )
    try:
        await asyncio.to_thread(engine.start)
    except Exception as e:
        yield sse({"type": "error", "message": f"Alexander engine failed to start: {e}"})
        return

    try:
        for i, pos in enumerate(positions):
            b = chess.Board(pos["fen"])

            if b.is_game_over():
                yield sse({"type": "engine", "index": i, "position": _serialise(pos)})
                continue

            ar: AlexanderResult = await asyncio.to_thread(
                engine.analyze, pos["fen"], pos["uci"], b
            )

            # White-perspective eval for the frontend eval bar
            if ar.mate_in is not None:
                positions[i]["eval_cp"] = None
                positions[i]["eval_mate"] = ar.mate_in if ar.side_to_move == "white" else -ar.mate_in
            else:
                positions[i]["eval_cp"] = ar.score_cp if ar.side_to_move == "white" else (
                    -ar.score_cp if ar.score_cp is not None else None
                )
                positions[i]["eval_mate"] = None
            positions[i]["score_cp_stm"] = ar.score_cp

            _log.info(
                "=== move %d (%s) ===\n"
                "  side=%s  played=%s  best=%s (%s)\n"
                "  score=%s  mate=%s  WDL=%s/%s/%s  zone=%s  depth=%s\n"
                "  top moves: %s\n"
                "  PV: %s\n"
                "  eval lines: %d",
                pos["move_number"], pos["color"] or "—",
                ar.side_to_move, ar.played_move or "—", ar.best_move_san, ar.best_move_uci,
                ar.score_cp, ar.mate_in, ar.wdl_win, ar.wdl_draw, ar.wdl_loss,
                ar.shashin_zone, ar.depth,
                "  ".join(
                    f"{m.san}({m.score_str()} W{m.wdl_win/10:.0f}%)"
                    for m in ar.top_moves
                ),
                " ".join(ar.pv_san),
                len(ar.raw_eval_lines),
            )

            positions[i]["shashin_zone"]    = ar.shashin_zone
            positions[i]["wdl_win"]         = ar.wdl_win
            positions[i]["wdl_draw"]        = ar.wdl_draw
            positions[i]["wdl_loss"]        = ar.wdl_loss
            positions[i]["best_move_san"]   = ar.best_move_san
            positions[i]["best_move_uci"]   = ar.best_move_uci
            positions[i]["pv_san"]          = ar.pv_san
            positions[i]["top_moves"]       = [
                {"san": m.san, "score": m.score_str(), "win_pct": m.win_pct}
                for m in ar.top_moves
            ]
            positions[i]["engine_summary"]  = ar.raw_eval_lines
            positions[i]["alexander_result"] = ar

            # Eval loss vs previous position (white-perspective delta)
            if i > 0 and pos["san"] is not None:
                prev_cp = positions[i - 1]["eval_cp"]
                curr_cp = positions[i]["eval_cp"]
                if prev_cp is not None and curr_cp is not None:
                    color = pos["color"]
                    loss = (prev_cp - curr_cp) if color == "white" else (curr_cp - prev_cp)
                    eval_loss = max(0, loss)
                    positions[i]["eval_loss_cp"] = eval_loss
                    positions[i]["quality"]      = quality_from_loss(eval_loss)
                else:
                    positions[i]["quality"] = "good"

            yield sse({"type": "engine", "index": i, "position": _serialise(pos)})

    finally:
        await asyncio.to_thread(engine.stop)

    # ── Commentary phase ───────────────────────────────────────────────────────
    yield sse({"type": "commentary_start", "total": total})

    semaphore = asyncio.Semaphore(3)
    queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()

    async def run_one(i: int) -> None:
        text = await generate_commentary(positions, i, semaphore, our_side)
        positions[i]["commentary"] = text
        await queue.put((i, text))

    tasks = [asyncio.create_task(run_one(i)) for i in range(total)]
    for _ in range(total):
        i, text = await queue.get()
        yield sse({
            "type": "commentary",
            "index": i,
            "commentary": text,
            "prompt_sections": positions[i].get("prompt_sections"),
        })

    await asyncio.gather(*tasks)
    yield sse({"type": "complete"})



def _serialise(pos: dict) -> dict:
    """Remove non-serialisable fields before sending as SSE JSON."""
    out = {k: v for k, v in pos.items() if k != "alexander_result"}
    return out


@app.post("/api/analyze")
async def analyze(request: AnalysisRequest):
    our_side = request.our_side if request.our_side in ("white", "black") else "white"
    return StreamingResponse(
        stream_analysis(request.pgn, our_side),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# Serve compiled React frontend in production (Docker).
_static_dir = os.getenv("STATIC_DIR", "")
if _static_dir and os.path.isdir(_static_dir):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
