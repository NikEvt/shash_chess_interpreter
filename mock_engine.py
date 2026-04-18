"""
Mock engine data representing ShashChess UCI analysis output.
Each entry simulates what the real engine would return for a given position.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class EngineResult:
    fen: str
    best_move_uci: str       # UCI notation: e2e4
    best_move_san: str       # SAN notation: e4
    score_cp: Optional[int]  # centipawns (None if mate)
    mate_in: Optional[int]   # plies to mate (None if no mate)
    wdl_win: int             # 0-1000
    wdl_draw: int
    wdl_loss: int
    depth: int
    shashin_type: str        # Capablanca / Tal / Petrosian
    side_to_move: str        # "white" | "black"


def get_shashin_type(score_cp: Optional[int]) -> str:
    if score_cp is None:
        return "Tal"
    if abs(score_cp) < 50:
        return "Capablanca"
    if abs(score_cp) > 150:
        return "Tal" if score_cp > 0 else "Petrosian"
    return "Capablanca"


# --- Test positions ---

MOCK_POSITIONS: dict[str, EngineResult] = {
    # 1. Starting position after 1.e4 e5 2.Nf3 — equal, opening
    "opening_equal": EngineResult(
        fen="rnbqkb1r/pppp1ppp/5n2/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
        best_move_uci="f1b5",
        best_move_san="Bb5",
        score_cp=15,
        mate_in=None,
        wdl_win=312, wdl_draw=510, wdl_loss=178,
        depth=20,
        shashin_type="Capablanca",
        side_to_move="white",
    ),

    # 2. Sicilian — White has slight initiative
    "sicilian_white_edge": EngineResult(
        fen="rnbqkb1r/pp2pppp/3p1n2/2p5/3PP3/2N2N2/PPP2PPP/R1BQKB1R w KQkq - 0 5",
        best_move_uci="d4c5",
        best_move_san="dxc5",
        score_cp=55,
        mate_in=None,
        wdl_win=380, wdl_draw=470, wdl_loss=150,
        depth=18,
        shashin_type="Capablanca",
        side_to_move="white",
    ),

    # 3. Tactical — White has winning material advantage
    "winning_tactics": EngineResult(
        fen="r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 0 6",
        best_move_uci="e1g1",
        best_move_san="O-O",
        score_cp=200,
        mate_in=None,
        wdl_win=620, wdl_draw=310, wdl_loss=70,
        depth=22,
        shashin_type="Tal",
        side_to_move="white",
    ),

    # 4. Endgame — King and pawn, White winning
    "endgame_winning": EngineResult(
        fen="8/8/4k3/8/4K3/4P3/8/8 w - - 0 1",
        best_move_uci="e4d5",
        best_move_san="Kd5",
        score_cp=380,
        mate_in=None,
        wdl_win=850, wdl_draw=120, wdl_loss=30,
        depth=30,
        shashin_type="Tal",
        side_to_move="white",
    ),

    # 5. Mate in 2
    "mate_in_2": EngineResult(
        fen="6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1",
        best_move_uci="e1e8",
        best_move_san="Re8#",
        score_cp=None,
        mate_in=1,
        wdl_win=1000, wdl_draw=0, wdl_loss=0,
        depth=5,
        shashin_type="Tal",
        side_to_move="white",
    ),

    # 6. Defensive — Black under pressure
    "black_defensive": EngineResult(
        fen="r1bqkb1r/ppp2ppp/2np1n2/4p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R b KQkq - 0 6",
        best_move_uci="f8e7",
        best_move_san="Be7",
        score_cp=-80,
        mate_in=None,
        wdl_win=180, wdl_draw=460, wdl_loss=360,
        depth=19,
        shashin_type="Petrosian",
        side_to_move="black",
    ),
}


def get_mock_result(position_key: str) -> EngineResult:
    return MOCK_POSITIONS[position_key]
