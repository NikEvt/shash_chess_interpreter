"""
Raw subprocess UCI wrapper for Alexander engine.

Used by offline tools (generate_from_positions.py, smoke_test_alexander.py).
The webapp uses python-chess async interface instead (see webapp/backend/main.py).

Features beyond basic UCI:
  - Keeps engine process alive between analyses (no spawn-per-position overhead)
  - MultiPV=3: fetches top-3 moves with WDL and PV continuation
  - 'eval' command: parses Alexander's evaluation trace for components
  - Computes Shashin zone from WDL win probability (matches Alexander's own logic)
"""
from __future__ import annotations

import re
import subprocess
import threading
from typing import Optional
from logging import Logger
import logging
from logging import INFO
import chess

from .types import AlexanderResult, EvalTrace, TopMove, win_prob_to_shashin_zone

_log = logging.getLogger("alexander_engine")
if not _log.handlers:
    _fh = logging.FileHandler("engine.log")
    _fh.setLevel(INFO)
    _log.addHandler(_fh)
    _log.setLevel(INFO)
    _log.propagate = False


class AlexanderEngine:
    """
    Blocking subprocess wrapper for Alexander.
    Use as a context manager:

        with AlexanderEngine(path, depth=20, num_pv=3) as engine:
            result = engine.analyze(fen, played_move_uci, board)
    """

    def __init__(
        self,
        engine_path: str,
        depth: int = 15,
        num_pv: int = 3,
        threads: int = 8,
        hash_mb: int = 256,
    ):
        self.engine_path = engine_path
        self.depth = depth
        self.num_pv = num_pv
        self.threads = threads
        self.hash_mb = hash_mb
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def __enter__(self) -> "AlexanderEngine":
        self.start()
        return self

    def __exit__(self, *_) -> None:
        self.stop()

    def start(self) -> None:
        self._proc = subprocess.Popen(
            [self.engine_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._send("uci")
        self._wait_for("uciok")
        self._send(f"setoption name Threads value {self.threads}")
        self._send(f"setoption name Hash value {self.hash_mb}")
        self._send("setoption name UCI_ShowWDL value true")
        self._send(f"setoption name MultiPV value {self.num_pv}")
        self._send("isready")
        self._wait_for("readyok")

    def stop(self) -> None:
        if self._proc:
            try:
                if self._is_alive():
                    self._send("quit")
                    self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

    # ── public API ─────────────────────────────────────────────────────────────

    def analyze(
        self,
        fen: str,
        played_move_uci: Optional[str],
        board: chess.Board,
    ) -> AlexanderResult:
        with self._lock:
            return self._analyze(fen, played_move_uci, board)

    # ── internals ──────────────────────────────────────────────────────────────

    def _is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _send(self, cmd: str) -> None:
        if not self._is_alive():
            raise BrokenPipeError("Engine process has exited")
        try:
            self._proc.stdin.write(cmd + "\n")
            self._proc.stdin.flush()
        except BrokenPipeError:
            self._proc = None
            raise

    def _wait_for(self, prefix: str) -> list[str]:
        lines: list[str] = []
        for line in self._proc.stdout:
            line = line.rstrip()
            lines.append(line)
            if line.startswith(prefix):
                break
        return lines

    def _read_until_bestmove(self) -> list[str]:
        lines: list[str] = []
        for line in self._proc.stdout:
            line = line.rstrip()
            lines.append(line)
            if line.startswith("bestmove"):
                break
        return lines

    def _read_eval_output(self) -> list[str]:
        """Read Alexander's eval output until the 'Best move:' terminator line."""
        lines: list[str] = []
        for line in self._proc.stdout:
            line = line.rstrip()
            lines.append(line)
            # Alexander's eval ends with "Best move: ..." — reliable terminator
            if line.startswith("Best move:"):
                break
            if len(lines) > 150:
                break
        return lines

    def _analyze(
        self,
        fen: str,
        played_move_uci: Optional[str],
        board: chess.Board,
    ) -> AlexanderResult:
        # Restart engine if it died
        if not self._is_alive():
            self.start()

        # Reset and set position
        self._send("ucinewgame")
        self._send("isready")
        self._wait_for("readyok")
        self._send(f"position fen {fen}")

        # eval BEFORE go — calling eval after go crashes Alexander
        eval_trace: Optional[EvalTrace] = None
        raw_eval_lines: list[str] = []
        if not board.is_game_over():
            self._send("eval")
            eval_lines = self._read_eval_output()
            raw_eval_lines = eval_lines
            _log.info("eval output:\n%s", "\n".join(eval_lines))
            eval_trace = self._parse_eval_trace(eval_lines)
        
        

        # Run search (position is still set — go works after eval)
        self._send(f"go depth {self.depth}")
        info_lines = self._read_until_bestmove()
        _log.info("search output:\n%s", "\n".join(info_lines))

        # Parse MultiPV results
        top_moves = self._parse_multipv(info_lines, board)

        # Derive primary result from best move (multipv 1)
        best = top_moves[0] if top_moves else None

        score_cp = best.score_cp if best else None
        mate_in = best.mate_in if best else None
        wdl_win = best.wdl_win if best else 500
        wdl_draw = best.wdl_draw if best else 0
        wdl_loss = best.wdl_loss if best else 500
        depth = best.depth if best else self.depth
        seldepth = best.seldepth if best else self.depth
        pv_san = best.pv_san if best else []

        # Shashin zone from WDL (matches Alexander's internal computation)
        shashin_zone = win_prob_to_shashin_zone(wdl_win / 10.0)

        # best move from bestmove line (authoritative)
        bestmove_line = next((l for l in info_lines if l.startswith("bestmove")), "")
        parts = bestmove_line.split()
        best_move_uci = parts[1] if len(parts) > 1 and parts[1] not in ("(none)", "0000") else ""
        if not best_move_uci and top_moves:
            best_move_uci = top_moves[0].uci

        best_move_san = _uci_to_san(best_move_uci, board)
        played_move_san = _uci_to_san(played_move_uci or "", board) if played_move_uci else ""

        side_to_move = "white" if board.turn == chess.WHITE else "black"

        _log.info(
            "=== position result ===\n"
            "  side=%s  played=%s  best=%s (%s)\n"
            "  score=%s  mate=%s  WDL=%s/%s/%s  zone=%s  depth=%s\n"
            "  top moves: %s\n"
            "  PV: %s",
            side_to_move, played_move_san, best_move_san, best_move_uci,
            score_cp, mate_in, wdl_win, wdl_draw, wdl_loss, shashin_zone, depth,
            "  ".join(
                f"{m.san}({m.score_str()} W{m.wdl_win/10:.0f}%)"
                for m in top_moves
            ),
            " ".join(pv_san),
        )

        return AlexanderResult(
            fen=fen,
            side_to_move=side_to_move,
            played_move=played_move_san,
            best_move_uci=best_move_uci,
            best_move_san=best_move_san,
            score_cp=score_cp,
            mate_in=mate_in,
            wdl_win=wdl_win,
            wdl_draw=wdl_draw,
            wdl_loss=wdl_loss,
            shashin_zone=shashin_zone,
            top_moves=top_moves,
            pv_san=pv_san,
            depth=depth,
            seldepth=seldepth,
            eval_trace=eval_trace,
            raw_eval_lines=raw_eval_lines,
        )

    def _parse_multipv(self, lines: list[str], board: chess.Board) -> list[TopMove]:
        """Collect last info line per multipv index, convert to TopMove."""
        # last info seen for each pv index
        pv_map: dict[int, dict] = {}

        for line in lines:
            if not line.startswith("info"):
                continue
            # Only process lines with pv data
            if " pv " not in line:
                continue

            m = re.search(r"\bmultipv (\d+)\b", line)
            pv_idx = int(m.group(1)) if m else 1

            score_cp: Optional[int] = None
            mate_in: Optional[int] = None
            sm = re.search(r"\bscore (cp|mate) (-?\d+)", line)
            if sm:
                if sm.group(1) == "cp":
                    score_cp = int(sm.group(2))
                else:
                    mate_in = int(sm.group(2))

            wdl_win, wdl_draw, wdl_loss = 500, 0, 500
            wm = re.search(r"\bwdl (\d+) (\d+) (\d+)", line)
            if wm:
                wdl_win = int(wm.group(1))
                wdl_draw = int(wm.group(2))
                wdl_loss = int(wm.group(3))

            dm = re.search(r"\bdepth (\d+)\b", line)
            depth = int(dm.group(1)) if dm else self.depth

            sdm = re.search(r"\bseldepth (\d+)\b", line)
            seldepth = int(sdm.group(1)) if sdm else depth

            pv_match = re.search(r"\bpv (.+)$", line)
            pv_uci = pv_match.group(1).split() if pv_match else []

            pv_map[pv_idx] = dict(
                score_cp=score_cp, mate_in=mate_in,
                wdl_win=wdl_win, wdl_draw=wdl_draw, wdl_loss=wdl_loss,
                depth=depth, seldepth=seldepth, pv_uci=pv_uci,
            )

        result: list[TopMove] = []
        for idx in sorted(pv_map):
            d = pv_map[idx]
            pv_uci: list[str] = d["pv_uci"]
            uci_move = pv_uci[0] if pv_uci else ""

            # Convert PV to SAN
            pv_san: list[str] = []
            temp = board.copy()
            for uci in pv_uci[:6]:
                try:
                    m = temp.parse_uci(uci)
                    pv_san.append(temp.san(m))
                    temp.push(m)
                except Exception:
                    break

            move_san = _uci_to_san(uci_move, board)

            result.append(TopMove(
                uci=uci_move,
                san=move_san,
                score_cp=d["score_cp"],
                mate_in=d["mate_in"],
                wdl_win=d["wdl_win"],
                wdl_draw=d["wdl_draw"],
                wdl_loss=d["wdl_loss"],
                depth=d["depth"],
                seldepth=d["seldepth"],
                pv_san=pv_san,
            ))

        return result

    def _parse_eval_trace(self, lines: list[str]) -> Optional[EvalTrace]:
        """
        Parse Alexander's eval command output.
        Alexander format (different from Stockfish):
          - "Delta Expansion (White-Black): 0.00"
          - "Makogonov White: Improve Rook on a1 (activity: -2)"
          - "Legal moves sorted by activity: e2e4(57%/56), d2d4(56%/52), ..."
          - "Best move: e2e4 (Win Probability: 57%, Activity: 56)"
        """
        trace: dict[str, float] = {}
        components: dict[str, float] = {}

        for line in lines:
            lower = line.lower()

            # "Delta Expansion (White-Black): 0.00"
            m = re.search(r"delta expansion.*?:\s*([+-]?\d+\.?\d*)", lower)
            if m:
                try:
                    components["expansion_delta"] = float(m.group(1))
                except ValueError:
                    pass

            # "Best move: e2e4 (Win Probability: 57%, Activity: 56)"
            m = re.search(r"win probability:\s*(\d+)%.*activity:\s*([+-]?\d+)", lower)
            if m:
                try:
                    trace["best_win_pct"] = float(m.group(1))
                    components["best_activity"] = float(m.group(2))
                except ValueError:
                    pass

            # "Legal moves sorted by static activity ...: e2e3(58%/61), e2e4(57%/56), ..."
            if "legal moves sorted" in lower and "%" in line:
                move_scores = re.findall(r"\w+\((\d+)%/([+-]?\d+)\)", line)
                if move_scores:
                    win_pcts = [float(w) for w, _ in move_scores]
                    activities = [float(a) for _, a in move_scores]
                    if win_pcts:
                        components["avg_move_win_pct"] = sum(win_pcts) / len(win_pcts)
                        components["top_move_win_pct"] = win_pcts[0]
                    if activities:
                        components["top_move_activity"] = activities[0]

        if not trace and not components:
            return None

        return EvalTrace(
            best_win_pct=trace.get("best_win_pct"),
            components=components,
        )


# ── helpers ────────────────────────────────────────────────────────────────────

def _uci_to_san(uci: str, board: chess.Board) -> str:
    if not uci or uci in ("(none)", "0000"):
        return ""
    try:
        move = board.parse_uci(uci)
        return board.san(move)
    except Exception:
        return uci
