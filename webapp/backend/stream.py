import asyncio
import json
import logging
from typing import AsyncGenerator

import chess

from alexander_interpreter import AlexanderResult, build_config
from alexander_interpreter.engine import AlexanderEngine
from alexander_interpreter.llm import set_thinking

from config import (
    ENGINE_PATH, ANALYSIS_DEPTH, NUM_PV,
    ENGINE_THREADS, ENGINE_HASH_MB, ENGINE_TIMEOUT,
    COMMENTARY_CONCURRENCY,
)
from parser import parse_input, build_positions
from quality import quality_from_loss
from commentary import generate_commentary

_log = logging.getLogger("webapp.analysis")


# ── SSE helpers ───────────────────────────────────────────────────────────────

def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _serialise(pos: dict) -> dict:
    """Strip non-JSON-serialisable fields before sending over SSE."""
    return {k: v for k, v in pos.items() if k != "alexander_result"}


# ── Engine phase ──────────────────────────────────────────────────────────────

def _make_engine() -> AlexanderEngine:
    return AlexanderEngine(
        ENGINE_PATH,
        depth=ANALYSIS_DEPTH,
        num_pv=NUM_PV,
        threads=ENGINE_THREADS,
        hash_mb=ENGINE_HASH_MB,
    )


async def _restart_engine(old_engine: AlexanderEngine) -> AlexanderEngine:
    """Kill the timed-out engine and return a fresh started replacement.

    After TimeoutError the asyncio.to_thread task continues running and holds
    old_engine._lock.  Calling old_engine.stop() terminates the subprocess,
    which causes the blocked readline() in that thread to return EOF and
    release the lock.  We create a *new* AlexanderEngine instance (with its
    own lock and process) so we don't race against the dying thread.
    """
    try:
        await asyncio.to_thread(old_engine.stop)
    except Exception:
        pass
    new_engine = _make_engine()
    await asyncio.to_thread(new_engine.start)
    return new_engine


async def _engine_phase(positions: list[dict]) -> AsyncGenerator[str, None]:
    engine = _make_engine()
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

            try:
                ar: AlexanderResult = await asyncio.wait_for(
                    asyncio.to_thread(engine.analyze, pos["fen"], pos["uci"], b),
                    timeout=ENGINE_TIMEOUT,
                )
            except asyncio.TimeoutError:
                _log.warning(
                    "Engine timeout at position %d (%s) — restarting and retrying",
                    i, pos.get("san"),
                )
                # Restart engine; if that fails we can't continue at all
                try:
                    engine = await _restart_engine(engine)
                except Exception as restart_err:
                    _log.error("Engine restart failed: %s", restart_err)
                    yield sse({"type": "error", "message": f"Engine restart failed: {restart_err}"})
                    return
                # Retry once; if it times out again, skip just this position
                try:
                    ar = await asyncio.wait_for(
                        asyncio.to_thread(engine.analyze, pos["fen"], pos["uci"], b),
                        timeout=ENGINE_TIMEOUT,
                    )
                except (asyncio.TimeoutError, Exception) as retry_err:
                    _log.error(
                        "Engine retry failed at position %d (%s): %s — skipping",
                        i, pos.get("san"), retry_err,
                    )
                    yield sse({"type": "engine", "index": i, "position": _serialise(pos)})
                    continue

            _apply_engine_result(positions, i, ar)
            _log_engine_result(i, positions[i], ar)
            yield sse({"type": "engine", "index": i, "position": _serialise(positions[i])})
    finally:
        await asyncio.to_thread(engine.stop)


def _apply_engine_result(positions: list[dict], i: int, ar: AlexanderResult) -> None:
    """Write AlexanderResult fields into the position dict (mutates in place)."""
    pos = positions[i]

    if ar.mate_in is not None:
        positions[i]["eval_cp"]   = None
        positions[i]["eval_mate"] = ar.mate_in if ar.side_to_move == "white" else -ar.mate_in
    else:
        positions[i]["eval_cp"]   = ar.score_cp if ar.side_to_move == "white" else (
            -ar.score_cp if ar.score_cp is not None else None
        )
        positions[i]["eval_mate"] = None

    positions[i].update({
        "score_cp_stm":     ar.score_cp,
        "shashin_zone":     ar.shashin_zone,
        "wdl_win":          ar.wdl_win,
        "wdl_draw":         ar.wdl_draw,
        "wdl_loss":         ar.wdl_loss,
        "best_move_san":    ar.best_move_san,
        "best_move_uci":    ar.best_move_uci,
        "pv_san":           ar.pv_san,
        "top_moves":        [{"san": m.san, "score": m.score_str(), "win_pct": m.win_pct}
                             for m in ar.top_moves],
        "engine_summary":   ar.raw_eval_lines,
        "alexander_result": ar,
    })

    if i > 0 and pos["san"] is not None:
        prev_cp = positions[i - 1]["eval_cp"]
        curr_cp = positions[i]["eval_cp"]
        if prev_cp is not None and curr_cp is not None:
            loss = (prev_cp - curr_cp) if pos["color"] == "white" else (curr_cp - prev_cp)
            eval_loss = max(0, loss)
            positions[i]["eval_loss_cp"] = eval_loss
            positions[i]["quality"]      = quality_from_loss(eval_loss)
        else:
            positions[i]["quality"] = "good"


def _log_engine_result(i: int, pos: dict, ar: AlexanderResult) -> None:
    _log.info(
        "=== move %d (%s) ===\n"
        "  side=%s  played=%s  best=%s (%s)\n"
        "  score=%s  mate=%s  WDL=%s/%s/%s  zone=%s  depth=%s\n"
        "  top: %s\n  PV: %s\n  lines: %d",
        pos["move_number"], pos["color"] or "—",
        ar.side_to_move, ar.played_move or "—", ar.best_move_san, ar.best_move_uci,
        ar.score_cp, ar.mate_in, ar.wdl_win, ar.wdl_draw, ar.wdl_loss,
        ar.shashin_zone, ar.depth,
        "  ".join(f"{m.san}({m.score_str()} W{m.wdl_win/10:.0f}%)" for m in ar.top_moves),
        " ".join(ar.pv_san),
        len(ar.raw_eval_lines),
    )


# ── Commentary phase ──────────────────────────────────────────────────────────

async def _commentary_phase(
    positions: list[dict], our_side: str, prompt_config=None, config_preset: str = "full",
) -> AsyncGenerator[str, None]:
    total     = len(positions)
    semaphore = asyncio.Semaphore(COMMENTARY_CONCURRENCY)
    queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()

    async def run_one(i: int) -> None:
        text = await generate_commentary(positions, i, semaphore, our_side, prompt_config)
        positions[i]["commentary"] = text
        await queue.put((i, text))

    tasks = [asyncio.create_task(run_one(i)) for i in range(total)]
    for _ in range(total):
        i, text = await queue.get()
        yield sse({
            "type":            "commentary",
            "index":           i,
            "commentary":      text,
            "prompt_sections": positions[i].get("prompt_sections"),
            "full_prompt":     positions[i].get("full_prompt"),
            "config_preset":   config_preset,
        })
    await asyncio.gather(*tasks)


# ── Top-level orchestrator ────────────────────────────────────────────────────

async def stream_analysis(
    pgn_text: str,
    our_side: str = "white",
    config_preset: str = "full",
    config_flags: dict | None = None,
    thinking: bool = False,
) -> AsyncGenerator[str, None]:
    game = parse_input(pgn_text)
    if game is None:
        yield sse({"type": "error", "message": "Cannot parse input as PGN or FEN."})
        return

    set_thinking(thinking)
    prompt_config = build_config(config_preset, config_flags or {})

    positions = build_positions(game)
    yield sse({"type": "start", "total": len(positions)})

    async for event in _engine_phase(positions):
        yield event

    yield sse({"type": "commentary_start", "total": len(positions)})

    async for event in _commentary_phase(positions, our_side, prompt_config, config_preset):
        yield event

    yield sse({"type": "complete"})
