import asyncio
import dataclasses

import chess

# config must be imported before alexander_interpreter (sets sys.path)
from config import ANALYSIS_DEPTH, MAX_TOKENS  # noqa: E402
from alexander_interpreter import (
    AlexanderResult,
    PromptConfig,
    build_tiny_prompt,
    build_tiny_prompt_sections,
    ask as llm_ask,
    LMStudioError,
    win_prob_to_shashin_zone,
)
from alexander_interpreter.eval_parser import parse_eval_sections as _parse_eval_sections
from quality import auto_question


async def generate_commentary(
    positions: list[dict],
    idx: int,
    semaphore: asyncio.Semaphore,
    our_side: str = "white",
    prompt_config: PromptConfig | None = None,
) -> str:
    pos = positions[idx]

    if pos["san"] is None:
        return "The game begins. Both players will fight for central control and piece development."

    async with semaphore:
        prev_best_san = ""
        prev_best_uci = ""
        prev_eval_cp: int | None = None
        board_before: chess.Board | None = None
        prev_game_phase: str | None = None

        if idx > 0:
            prev = positions[idx - 1]
            prev_best_uci  = prev.get("best_move_uci") or ""
            prev_best_san  = prev.get("best_move_san") or ""
            prev_eval_cp   = prev.get("eval_cp")
            try:
                board_before = chess.Board(prev["fen"])
            except Exception:
                pass
            # Extract previous game phase for phase-transition remark
            prev_ar = prev.get("alexander_result")
            if prev_ar and prev_ar.raw_eval_lines:
                gp = _parse_eval_sections(prev_ar.raw_eval_lines).game_phase
                prev_game_phase = gp or None

        curr_eval_cp:   int | None = pos.get("eval_cp")
        curr_eval_mate: int | None = pos.get("eval_mate")
        eval_loss:      int | None = pos.get("eval_loss_cp")

        result = pos.get("alexander_result")
        if result is None:
            # Fallback when engine analysis failed or timed out for this position.
            # side_to_move = who is to move NEXT = opposite of who played.
            played_color = pos.get("color") or "black"
            stm = "black" if played_color == "white" else "white"
            result = AlexanderResult(
                fen=pos["fen"],
                side_to_move=stm,
                played_move=pos["san"],
                best_move_uci=prev_best_uci,
                best_move_san=prev_best_san or pos["san"],
                score_cp=pos.get("score_cp_stm"),
                mate_in=pos.get("eval_mate"),
                wdl_win=pos.get("wdl_win", 500),
                wdl_draw=pos.get("wdl_draw", 0),
                wdl_loss=pos.get("wdl_loss", 500),
                shashin_zone=win_prob_to_shashin_zone(pos.get("wdl_win", 500) / 10.0),
                top_moves=pos.get("top_moves", []),
                pv_san=pos.get("pv_san", []),
                depth=ANALYSIS_DEPTH,
            )
        else:
            # Fix played_move: engine.analyze receives board-after-move so UCI→SAN
            # conversion fails and returns the raw UCI string. Use the correct SAN
            # already computed in build_positions.
            # Fix best_move_san: replace with the PREVIOUS position's recommendation —
            # that is what the engine considered optimal before this move was played.
            result = dataclasses.replace(
                result,
                played_move=pos["san"] or result.played_move,
                best_move_san=prev_best_san or result.best_move_san,
            )

        # Accumulate the game's UCI moves up to this position for opening book lookup
        game_uci = " ".join(p["uci"] for p in positions[:idx + 1] if p.get("uci"))
        result = dataclasses.replace(result, game_uci=game_uci)

        # IMPORTANT: do NOT flip side_to_move here.
        # build_tiny_prompt/_build_tiny_sections expects side_to_move = "who moves NEXT"
        # (the value the engine naturally returns).  It internally derives
        # color_who_played = opposite(side_to_move).  A flip here would double-invert
        # and make the attribution wrong (e.g., "Black's pawn moves to e4" when White played).

        question = auto_question(
            result.score_cp, result.mate_in,
            result.shashin_zone,
            result.played_move, result.best_move_san,
            eval_loss=eval_loss,
        )

        shared_kwargs = dict(
            prev_eval_cp=prev_eval_cp,
            curr_eval_cp=curr_eval_cp,
            curr_eval_mate=curr_eval_mate,
            our_side=our_side,
            question_type=question,
            board_before=board_before,
            eval_loss=eval_loss,
            config=prompt_config,
            prev_game_phase=prev_game_phase,
        )

        positions[idx]["prompt_sections"] = build_tiny_prompt_sections(result, **shared_kwargs)

        prompt = build_tiny_prompt(result, **shared_kwargs)
        positions[idx]["full_prompt"] = prompt
        try:
            raw = await asyncio.to_thread(llm_ask, prompt, max_tokens=MAX_TOKENS)
            if result.best_move_san:
                return f"Best move: {result.best_move_san}.\n{raw}"
            return raw
        except LMStudioError as e:
            return f"[LLM unavailable: {e}]"
        except Exception:
            return f"{pos['san']}."
