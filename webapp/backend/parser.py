import io

import chess
import chess.pgn


def parse_input(text: str) -> chess.pgn.Game | None:
    """Parse PGN or FEN string into a chess.pgn.Game. Returns None on failure."""
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


def build_positions(game: chess.pgn.Game) -> list[dict]:
    """Walk game mainline and return a list of position dicts (starting position first)."""
    board = game.board()
    positions: list[dict] = [_empty_position(0, board.fen(), san=None, uci=None,
                                              move_number=0, color=None, quality="book")]

    for move in game.mainline_moves():
        san = board.san(move)
        color = "white" if board.turn == chess.WHITE else "black"
        move_number = board.fullmove_number
        board.push(move)
        positions.append(_empty_position(
            index=len(positions),
            fen=board.fen(),
            san=san,
            uci=move.uci(),
            move_number=move_number,
            color=color,
            quality=None,
        ))

    return positions


def _empty_position(
    index: int, fen: str, san, uci, move_number: int, color, quality
) -> dict:
    return {
        "index":          index,
        "fen":            fen,
        "san":            san,
        "uci":            uci,
        "move_number":    move_number,
        "color":          color,
        "best_move_san":  None,
        "best_move_uci":  None,
        "eval_cp":        None,
        "eval_mate":      None,
        "score_cp_stm":   None,
        "shashin_zone":   "CAPABLANCA",
        "wdl_win":        500,
        "wdl_draw":       0,
        "wdl_loss":       500,
        "top_moves":      [],
        "pv_san":         [],
        "quality":        quality,
        "eval_loss_cp":   None,
        "commentary":     None,
        "engine_summary": [],
        "prompt_sections": None,
        "alexander_result": None,
    }
