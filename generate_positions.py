"""
Generates mock_engine.py from real ShashChess UCI analysis.

Usage:
    cd agent
    python3 generate_positions.py --engine ../ShashChess/src/shashchess
    python3 generate_positions.py --engine ../ShashChess/src/shashchess --depth 18 --out mock_engine.py
"""
import subprocess
import re
import sys
import argparse
from pathlib import Path

# ── 50 seed FENs ──────────────────────────────────────────────────────────────
# Diverse set: openings, middlegames, endgames, tactical positions.
# side_to_move and position_key are metadata — engine re-confirms the side from FEN.

SEED_POSITIONS = [
    # key,                          FEN
    # ── Openings ────────────────────────────────────────────────────────────
    ("opening_equal",           "rnbqkb1r/pppp1ppp/5n2/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"),
    ("sicilian_white_edge",     "rnbqkb1r/pp2pppp/3p1n2/2p5/3PP3/2N2N2/PPP2PPP/R1BQKB1R w KQkq - 0 5"),
    ("french_classical",        "rnbqkb1r/ppp2ppp/4pn2/3p2B1/3PP3/2N5/PPP2PPP/R2QKBNR b KQkq - 1 4"),
    ("caro_kann",               "rn1qkbnr/pp2pppp/2p5/5b2/3PN3/8/PPP2PPP/R1BQKBNR w KQkq - 1 5"),
    ("qgd_classical",           "rnbqk2r/ppp1bppp/4pn2/3p2B1/2PP4/2N5/PP2PPPP/R2QKBNR w KQkq - 2 5"),
    ("kings_indian",            "rnbq1rk1/ppp1ppbp/3p1np1/8/2PPP3/2N2N2/PP3PPP/R1BQKB1R w KQ - 2 6"),
    ("nimzo_indian",            "rnbqk2r/pppp1ppp/4pn2/8/1bPP4/2N5/PP2PPPP/R1BQKBNR w KQkq - 2 4"),
    ("ruy_berlin",              "r1bqkb1r/pppp1ppp/2n5/1B2p3/3Pn3/5N2/PPP2PPP/RNBQR1K1 b kq - 0 6"),
    ("english_opening",         "r1bqkb1r/pppp1ppp/2n2n2/4p3/2P5/2N2N2/PP1PPPPP/R1BQKB1R w KQkq - 4 4"),
    ("grunfeld",                "rnbqkb1r/ppp1pp1p/6p1/8/3PP3/2p5/PP3PPP/R1BQKBNR w KQkq - 0 6"),
    ("catalan",                 "rnbq1rk1/ppp1bppp/4pn2/3p4/2PP4/5NP1/PP2PPBP/RNBQ1RK1 b - - 3 6"),
    ("slav_defence",            "rnbqkb1r/pp2pppp/2p2n2/8/2pP4/2N2N2/PP2PPPP/R1BQKB1R w KQkq - 0 5"),
    # ── Middlegame strategic ─────────────────────────────────────────────────
    ("italian_strategic",       "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 0 6"),
    ("isolated_pawn_white",     "r1bqr1k1/pp3ppp/2n1pn2/3p4/3P4/2NBP3/PP2NPPP/R2QR1K1 w - - 2 11"),
    ("open_file_rooks",         "2rr2k1/pp3ppp/2n1pn2/q7/3P4/2N1BN2/PP1Q1PPP/2RR2K1 w - - 0 15"),
    ("knight_outpost_d5",       "r2q1rk1/pp1b1ppp/2n1pn2/3pN3/3P4/2PBP3/PP3PPP/R1BQR1K1 w - - 2 12"),
    ("minority_attack",         "r2qr1k1/pp1b1ppp/2n1pn2/3p4/1P1P4/2N1PN2/P4PPP/R1BQR1K1 w - - 0 13"),
    ("bishop_pair_open",        "r4rk1/pp1q1ppp/2n1pn2/3p4/3P2b1/2NBP3/PP2BPPP/R2Q1RK1 w - - 2 13"),
    ("two_weaknesses",          "5rk1/pp3ppp/2n1p3/q2p4/3P4/2N1P3/PP2QPPP/4R1K1 w - - 0 18"),
    ("queenside_majority",      "2r3k1/5ppp/p3p3/1p1n4/3P4/P3P3/1P1N1PPP/2R3K1 w - - 0 22"),
    # ── Middlegame tactical ──────────────────────────────────────────────────
    ("kingside_pawn_storm",     "r1bq1rk1/pp3ppp/2nbpn2/3p4/2PP4/2N1PN2/PP3PPP/R1BQK2R w KQ - 0 9"),
    ("greek_gift_setup",        "r1bq1rk1/ppp2ppp/2n1pn2/3p4/2PP4/2N1PN2/PP3PPP/R1BQK2R w KQ - 2 8"),
    ("exchange_sacrifice_pos",  "r3r1k1/pp1q1ppp/2n1pn2/3p4/3P4/2NBPN2/PP3PPP/R2QR1K1 w - - 2 14"),
    ("double_pawn_sacrifice",   "r1bqr1k1/pp3ppp/2n1pn2/3p4/2PP4/2N1PN2/PP3PPP/R1BQK2R w KQ d6 0 10"),
    ("open_efile_attack",       "r1bqk2r/ppp2ppp/2n1pn2/3p4/3PP3/2N2N2/PPP2PPP/R1BQK2R b KQkq - 0 7"),
    ("knight_fork_threat",      "r1bqr1k1/ppp2ppp/2n5/3pn3/3P4/2N2N2/PPP2PPP/R1BQR1K1 w - - 0 12"),
    ("discovered_attack",       "r1bqr1k1/ppp2ppp/5n2/3Np3/8/2N5/PPP2PPP/R1BQR1K1 w - - 0 13"),
    ("winning_tactics",         "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 0 6"),
    # ── Middlegame defensive ─────────────────────────────────────────────────
    ("black_defensive",         "r1bqkb1r/ppp2ppp/2np1n2/4p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R b KQkq - 0 6"),
    ("prophylaxis",             "r2q1rk1/ppp1bppp/2n1pn2/3p4/3P4/2N1PN2/PPQ1BPPP/R4RK1 b - - 2 11"),
    ("bad_bishop_exchange",     "r4rk1/pp2bppp/2q1pn2/3pB3/3P4/2N2N2/PP2QPPP/R4RK1 b - - 0 14"),
    ("fortress_defense",        "5rk1/pp4pp/4p3/3p4/3P4/1P2P3/P5PP/3R2K1 b - - 0 28"),
    ("trade_active_pieces",     "r2qr1k1/pp1bbppp/2n1pn2/3p4/3P4/2N1PN2/PP1BBPPP/R2QR1K1 b - - 4 12"),
    ("passive_waiting",         "r3r1k1/pp1q1ppp/2n1pn2/3p4/3P4/2N1PN2/PP1Q1PPP/R3R1K1 b - - 2 14"),
    # ── Endgames ────────────────────────────────────────────────────────────
    ("endgame_winning",         "8/8/4k3/8/4K3/4P3/8/8 w - - 0 1"),
    ("lucena_position",         "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1"),
    ("philidor_draw",           "4k3/8/8/4p3/8/8/4K3/R4r2 b - - 0 1"),
    ("queen_vs_rook",           "4k3/8/4K3/8/8/8/8/3Q1r2 w - - 0 1"),
    ("wrong_color_bishop",      "8/6k1/6P1/8/7B/8/6K1/8 b - - 0 1"),
    ("knight_endgame",          "8/3k4/8/3N4/8/3K4/3P4/8 w - - 0 1"),
    ("rook_pawn_draw",          "8/8/k7/P7/K7/8/8/8 w - - 0 1"),
    ("pawn_race",               "8/k1P5/8/8/8/8/5Kp1/8 w - - 0 1"),
    ("opp_color_bishops",       "8/3k4/3p4/8/3P4/3K4/8/2b1B3 b - - 0 1"),
    ("rook_pawn_endgame",       "8/8/2k5/8/8/2K3R1/6P1/r7 w - - 0 1"),
    # ── Mate / forced ────────────────────────────────────────────────────────
    ("mate_in_2",               "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"),
    ("smothered_mate",          "6rk/6pp/8/8/8/8/8/R5NK w - - 0 1"),
    ("mate_in_3_battery",       "r1bqk2r/pppp1Qpp/2n2n2/2b1p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 6"),
    ("zugzwang_kp",             "8/8/3k4/3P4/3K4/8/8/8 b - - 0 1"),
    ("arabian_mate",            "7k/8/5N2/8/8/8/8/6RK w - - 0 1"),
    ("perpetual_check_draw",    "6k1/5ppp/8/8/8/8/5PPP/3Q2K1 w - - 0 1"),
]

# ── UCI engine wrapper ────────────────────────────────────────────────────────

def uci_analyze(engine_path: str, fen: str, depth: int) -> dict | None:
    """
    Analyze a FEN with the engine via UCI protocol.
    Uses Popen + line-by-line reading so we wait for 'bestmove' properly.
    """
    try:
        proc = subprocess.Popen(
            [engine_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except FileNotFoundError:
        print(f"ERROR: Engine not found at '{engine_path}'", file=sys.stderr)
        sys.exit(1)

    def send(cmd: str) -> None:
        proc.stdin.write(cmd + "\n")
        proc.stdin.flush()

    def read_until(keyword: str, timeout: float = 10.0) -> list[str]:
        import select, time
        lines = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ready = select.select([proc.stdout], [], [], 0.1)[0]
            if ready:
                line = proc.stdout.readline().rstrip("\n")
                lines.append(line)
                if keyword in line:
                    return lines
        return lines  # timeout — return what we have

    # Handshake
    send("uci")
    send("setoption name UCI_ShowWDL value true")
    read_until("uciok", timeout=5.0)
    send("isready")
    read_until("readyok", timeout=5.0)

    # Analyze
    send("ucinewgame")
    send(f"position fen {fen}")
    send(f"go depth {depth}")
    search_lines = read_until("bestmove", timeout=30.0)

    send("quit")
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()

    # Parse results — use last info line (highest depth)
    result = {
        "score_cp": 0, "mate_in": None,
        "wdl_win": 500, "wdl_draw": 0, "wdl_loss": 500,
        "best_move_uci": "", "depth": depth,
    }
    last_score_cp = None
    last_mate = None
    last_wdl = None

    for line in search_lines:
        if "info" in line:
            m = re.search(r"score (cp|mate) (-?\d+)", line)
            if m:
                if m.group(1) == "cp":
                    last_score_cp = int(m.group(2)); last_mate = None
                else:
                    last_mate = int(m.group(2)); last_score_cp = None
            m = re.search(r"wdl (\d+) (\d+) (\d+)", line)
            if m:
                last_wdl = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r"bestmove (\S+)", line)
        if m:
            uci_move = m.group(1)
            if uci_move not in ("(none)", "0000"):
                result["best_move_uci"] = uci_move

    if last_score_cp is not None:
        result["score_cp"] = last_score_cp
    if last_mate is not None:
        result["mate_in"] = last_mate
        result["score_cp"] = None
    if last_wdl:
        result["wdl_win"], result["wdl_draw"], result["wdl_loss"] = last_wdl

    return result


def uci_to_san(best_move_uci: str, fen: str) -> str:
    """
    Convert UCI move (e2e4) to a readable SAN approximation.
    Full SAN requires a chess library; this gives a good enough label for mock data.
    """
    if not best_move_uci or best_move_uci in ("(none)", "0000"):
        return "—"

    # Castling
    if best_move_uci == "e1g1": return "O-O"
    if best_move_uci == "e1c1": return "O-O-O"
    if best_move_uci == "e8g8": return "O-O"
    if best_move_uci == "e8c8": return "O-O-O"

    # Pawn promotion
    if len(best_move_uci) == 5:
        promo = best_move_uci[4].upper()
        return f"{best_move_uci[2]}{best_move_uci[3]}={promo}"

    from_sq = best_move_uci[:2]
    to_sq   = best_move_uci[2:4]

    # Read the piece from FEN
    piece_map = _fen_to_piece_map(fen)
    piece = piece_map.get(from_sq, "?")

    if piece in ("P", "p"):
        # Pawn capture vs push
        if from_sq[0] != to_sq[0]:
            return f"{from_sq[0]}x{to_sq}"
        return to_sq
    else:
        capture = "x" if to_sq in piece_map else ""
        return f"{piece.upper()}{capture}{to_sq}"


def _fen_to_piece_map(fen: str) -> dict[str, str]:
    """Build square→piece map from FEN board string."""
    board_str = fen.split()[0]
    result = {}
    rank = 8
    for row in board_str.split("/"):
        file_idx = 0
        for ch in row:
            if ch.isdigit():
                file_idx += int(ch)
            else:
                sq = chr(ord("a") + file_idx) + str(rank)
                result[sq] = ch
                file_idx += 1
        rank -= 1
    return result


def shashin_type(score_cp):
    if score_cp is None:
        return "Tal"
    if abs(score_cp) < 50:
        return "Capablanca"
    if abs(score_cp) > 150:
        return "Tal" if score_cp > 0 else "Petrosian"
    return "Capablanca"


# ── Code generator ────────────────────────────────────────────────────────────

def generate_mock_engine_py(positions: list[dict], out_path: Path) -> None:
    lines = [
        '"""',
        'Mock engine data — generated by generate_positions.py from real ShashChess analysis.',
        'Do not edit manually; re-run generate_positions.py to refresh.',
        '"""',
        'from dataclasses import dataclass',
        'from typing import Optional',
        '',
        '',
        '@dataclass',
        'class EngineResult:',
        '    fen: str',
        '    best_move_uci: str',
        '    best_move_san: str',
        '    score_cp: Optional[int]',
        '    mate_in: Optional[int]',
        '    wdl_win: int',
        '    wdl_draw: int',
        '    wdl_loss: int',
        '    depth: int',
        '    shashin_type: str',
        '    side_to_move: str',
        '',
        '',
        'def get_shashin_type(score_cp):',
        '    if score_cp is None: return "Tal"',
        '    if abs(score_cp) < 50: return "Capablanca"',
        '    if abs(score_cp) > 150: return "Tal" if score_cp > 0 else "Petrosian"',
        '    return "Capablanca"',
        '',
        '',
        'MOCK_POSITIONS: dict[str, EngineResult] = {',
    ]

    for p in positions:
        score_repr = f"None" if p["score_cp"] is None else str(p["score_cp"])
        mate_repr  = f"None" if p["mate_in"]  is None else str(p["mate_in"])
        lines += [
            f'    # {p["key"]}',
            f'    "{p["key"]}": EngineResult(',
            f'        fen="{p["fen"]}",',
            f'        best_move_uci="{p["best_move_uci"]}",',
            f'        best_move_san="{p["best_move_san"]}",',
            f'        score_cp={score_repr}, mate_in={mate_repr},',
            f'        wdl_win={p["wdl_win"]}, wdl_draw={p["wdl_draw"]}, wdl_loss={p["wdl_loss"]},',
            f'        depth={p["depth"]}, shashin_type="{p["shashin_type"]}",',
            f'        side_to_move="{p["side_to_move"]}",',
            f'    ),',
            '',
        ]

    lines += [
        '}',
        '',
        '',
        'def get_mock_result(position_key: str) -> EngineResult:',
        '    return MOCK_POSITIONS[position_key]',
        '',
    ]

    out_path.write_text("\n".join(lines))
    print(f"Written {len(positions)} positions → {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate mock_engine.py from ShashChess UCI")
    parser.add_argument("--engine", required=True, help="Path to shashchess binary")
    parser.add_argument("--depth",  type=int, default=15, help="Search depth (default 15)")
    parser.add_argument("--out",    default="mock_engine.py", help="Output file (default mock_engine.py)")
    args = parser.parse_args()

    engine_path = Path(args.engine).expanduser().resolve()
    out_path    = Path(args.out)

    if not engine_path.exists():
        print(f"ERROR: Engine binary not found: {engine_path}", file=sys.stderr)
        print("Compile first:\n  cd ShashChess/src && make -j4 ARCH=apple-silicon", file=sys.stderr)
        sys.exit(1)

    print(f"Engine : {engine_path}")
    print(f"Depth  : {args.depth}")
    print(f"Output : {out_path}")
    print(f"Positions: {len(SEED_POSITIONS)}")
    print()

    results = []
    for i, (key, fen) in enumerate(SEED_POSITIONS, 1):
        side = "white" if fen.split()[1] == "w" else "black"
        print(f"[{i:02d}/{len(SEED_POSITIONS)}] {key} ... ", end="", flush=True)

        data = uci_analyze(str(engine_path), fen, args.depth)
        if data is None:
            print("SKIP (timeout)")
            continue

        best_san = uci_to_san(data["best_move_uci"], fen)
        stype    = shashin_type(data["score_cp"])

        results.append({
            "key":            key,
            "fen":            fen,
            "best_move_uci":  data["best_move_uci"],
            "best_move_san":  best_san,
            "score_cp":       data["score_cp"],
            "mate_in":        data["mate_in"],
            "wdl_win":        data["wdl_win"],
            "wdl_draw":       data["wdl_draw"],
            "wdl_loss":       data["wdl_loss"],
            "depth":          data["depth"],
            "shashin_type":   stype,
            "side_to_move":   side,
        })

        score_str = f"mate {data['mate_in']}" if data["mate_in"] else f"cp {data['score_cp']}"
        print(f"{data['best_move_uci']} ({best_san})  score: {score_str}  [{stype}]")

    generate_mock_engine_py(results, out_path)
    print(f"\nDone. Run smoke tests:\n  python3 smoke_test.py --dry-run")


if __name__ == "__main__":
    main()
