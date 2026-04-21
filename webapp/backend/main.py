import asyncio
import io
import json
import os
import sys
from typing import AsyncGenerator

import chess
import chess.engine
import chess.pgn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ── Agent imports (same stack as smoke_test) ──────────────────────────────────
AGENT_DIR = os.path.abspath(
    os.getenv("AGENT_DIR") or os.path.join(os.path.dirname(__file__), "../../agent")
)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from mock_engine import EngineResult, get_shashin_type  # noqa: E402
from prompt import build_prompt                          # noqa: E402
from llm import ask as llm_ask, LMStudioError           # noqa: E402

# ── Config ────────────────────────────────────────────────────────────────────
ENGINE_PATH = os.path.abspath(
    os.getenv(
        "ENGINE_PATH",
        os.path.join(os.path.dirname(__file__), "../../ShashChess/src/shashchess"),
    )
)
ANALYSIS_DEPTH = int(os.getenv("ANALYSIS_DEPTH", "15"))

app = FastAPI(title="Chess Analyzer")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    pgn: str


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


# ── Level / question selection (same logic as smoke_test) ─────────────────────

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
    shashin_type: str,
    played_move: str | None,
    best_move_san: str | None,
) -> str:
    if played_move and best_move_san and played_move != best_move_san:
        return "best_move"
    if mate_in is not None:
        return "best_move"
    if shashin_type == "Petrosian":
        return "plan"
    if shashin_type == "Tal":
        return "best_move"
    return "explain"


# ── Commentary via agent (same stack as smoke_test) ───────────────────────────

async def generate_commentary(
    positions: list[dict],
    idx: int,
    semaphore: asyncio.Semaphore,
) -> str:
    pos = positions[idx]

    if pos["san"] is None:
        return "The game begins. Both players will fight for central control and piece development."

    async with semaphore:
        # Build moves history with move numbers so the LLM knows who played what:
        # e.g. ["1.Nc3", "1...d5", "2.d4", "2...c6"]
        moves_history: list[str] = []
        for j in range(max(0, idx - 5), idx + 1):
            p = positions[j]
            if p["san"]:
                if p["color"] == "white":
                    moves_history.append(f"{p['move_number']}.{p['san']}")
                else:
                    moves_history.append(f"{p['move_number']}...{p['san']}")

        who_played = pos.get("color") or "white"

        # best_move must come from the PREVIOUS position (before this move was played)
        # so it represents what the same player could have played instead
        if idx > 0:
            prev = positions[idx - 1]
            prev_best_uci = prev.get("best_move_uci") or ""
            prev_best_san = prev.get("best_move_san") or "—"
        else:
            prev_best_uci = ""
            prev_best_san = "—"

        # Compare by UCI to avoid SAN notation differences (e.g. "Qd2" vs "Qxd2#")
        played_uci = pos.get("uci") or ""
        is_best = bool(played_uci and prev_best_uci and played_uci == prev_best_uci)
        best_san_for_prompt = pos["san"] if is_best else prev_best_san

        # score_cp from the played player's perspective (negate stm which is for the next player)
        stm_cp = pos.get("score_cp_stm")
        played_cp = (-stm_cp) if stm_cp is not None else None

        # WDL stored in pos is from the NEXT player's perspective (b.turn after move).
        # Flip win↔loss so it reflects who_played's chances.
        wdl_win  = pos.get("wdl_loss", 500)
        wdl_draw = pos.get("wdl_draw", 0)
        wdl_loss = pos.get("wdl_win", 500)

        # Build EngineResult (side_to_move = who played, best_move = what they could have played)
        result = EngineResult(
            fen=pos["fen"],
            best_move_uci=prev_best_uci,
            best_move_san=best_san_for_prompt,
            score_cp=played_cp,
            mate_in=pos.get("eval_mate"),
            wdl_win=wdl_win,
            wdl_draw=wdl_draw,
            wdl_loss=wdl_loss,
            depth=ANALYSIS_DEPTH,
            shashin_type=pos.get("shashin_type", "Capablanca"),
            side_to_move=who_played,
            played_move=pos["san"],
        )

        eval_loss = pos.get("eval_loss_cp")
        level = _auto_level(result.score_cp, result.mate_in)
        question = _auto_question(
            result.score_cp, result.mate_in,
            result.shashin_type,
            result.played_move, result.best_move_san,
        )

        prompt = build_prompt(result, moves_history, level, question, eval_loss=eval_loss)
        max_tokens = 450 if is_best else 600

        try:
            text = await asyncio.to_thread(llm_ask, prompt, max_tokens=max_tokens)
            return text
        except LMStudioError as e:
            return f"[LLM unavailable: {e}]"
        except Exception as e:
            return f"{pos['san']}."


# ── Main analysis stream ───────────────────────────────────────────────────────

async def stream_analysis(pgn_text: str) -> AsyncGenerator[str, None]:
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
        "eval_cp": None,       # white's perspective (for eval bar)
        "eval_mate": None,
        "score_cp_stm": None,  # side-to-move perspective (for EngineResult)
        "shashin_type": "Capablanca",
        "wdl_win": 500,
        "wdl_draw": 0,
        "wdl_loss": 500,
        "pv": [],
        "pv_san": [],
        "quality": "book",
        "eval_loss_cp": None,
        "commentary": None,
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
            "shashin_type": "Capablanca",
            "wdl_win": 500,
            "wdl_draw": 0,
            "wdl_loss": 500,
            "pv": [],
            "pv_san": [],
            "quality": None,
            "eval_loss_cp": None,
            "commentary": None,
        })

    total = len(positions)
    yield sse({"type": "start", "total": total})

    # ── Engine analysis ────────────────────────────────────────────────────────
    try:
        _, engine = await chess.engine.popen_uci(ENGINE_PATH)
    except Exception as e:
        yield sse({"type": "error", "message": f"Engine failed to start: {e}"})
        return

    try:
        await engine.configure({"UCI_ShowWDL": "true"})
    except Exception:
        pass  # not all builds support it

    try:
        for i, pos in enumerate(positions):
            b = chess.Board(pos["fen"])

            if b.is_game_over():
                yield sse({"type": "engine", "index": i, "position": pos})
                continue

            info = await engine.analyse(b, chess.engine.Limit(depth=ANALYSIS_DEPTH))
            pv    = info.get("pv", [])
            score = info.get("score")
            wdl   = info.get("wdl")
            best  = pv[0] if pv else None

            if score:
                white_score = score.white()
                if white_score.is_mate():
                    positions[i]["eval_cp"]   = None
                    positions[i]["eval_mate"] = white_score.mate()
                else:
                    positions[i]["eval_cp"]   = white_score.score()
                    positions[i]["eval_mate"] = None

                stm_score = score.pov(b.turn)
                if stm_score.is_mate():
                    positions[i]["score_cp_stm"] = None
                else:
                    positions[i]["score_cp_stm"] = stm_score.score()

                positions[i]["shashin_type"] = get_shashin_type(positions[i]["score_cp_stm"])

            if wdl:
                wdl_stm = wdl.pov(b.turn)
                positions[i]["wdl_win"]  = wdl_stm.wins
                positions[i]["wdl_draw"] = wdl_stm.draws
                positions[i]["wdl_loss"] = wdl_stm.losses

            if best:
                positions[i]["best_move_san"] = b.san(best)
                positions[i]["best_move_uci"] = best.uci()

            positions[i]["pv"] = [m.uci() for m in pv[:8]]

            pv_san, b_copy = [], b.copy()
            for pv_move in pv[:8]:
                try:
                    pv_san.append(b_copy.san(pv_move))
                    b_copy.push(pv_move)
                except Exception:
                    break
            positions[i]["pv_san"] = pv_san

            # Eval loss (white-perspective delta, clamped ≥ 0)
            if i > 0 and positions[i]["san"] is not None:
                prev_cp = positions[i - 1]["eval_cp"]
                curr_cp = positions[i]["eval_cp"]
                if prev_cp is not None and curr_cp is not None:
                    color = positions[i]["color"]
                    loss = (prev_cp - curr_cp) if color == "white" else (curr_cp - prev_cp)
                    eval_loss = max(0, loss)
                    positions[i]["eval_loss_cp"] = eval_loss
                    positions[i]["quality"]      = quality_from_loss(eval_loss)
                else:
                    positions[i]["quality"] = "good"

            yield sse({"type": "engine", "index": i, "position": positions[i]})

    finally:
        await engine.quit()

    # ── Commentary phase (agent: build_prompt + llm_ask) ──────────────────────
    yield sse({"type": "commentary_start", "total": total})

    semaphore = asyncio.Semaphore(3)  # LM Studio handles 1 request at a time, limit concurrency
    queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()

    async def run_one(i: int) -> None:
        text = await generate_commentary(positions, i, semaphore)
        positions[i]["commentary"] = text
        await queue.put((i, text))

    tasks = [asyncio.create_task(run_one(i)) for i in range(total)]

    for _ in range(total):
        i, text = await queue.get()
        yield sse({"type": "commentary", "index": i, "commentary": text})

    await asyncio.gather(*tasks)
    yield sse({"type": "complete"})


@app.post("/api/analyze")
async def analyze(request: AnalysisRequest):
    return StreamingResponse(
        stream_analysis(request.pgn),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# Serve compiled React frontend in production (Docker).
# Must be registered AFTER all API routes.
_static_dir = os.getenv("STATIC_DIR", "")
if _static_dir and os.path.isdir(_static_dir):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
