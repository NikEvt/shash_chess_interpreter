"""
Verbalization utilities: convert chess moves and evaluations to readable English.
Used by build_tiny_prompt to avoid raw notation in LLM context.
"""
from __future__ import annotations

import re
from typing import Optional

import chess

_PIECE_NAMES: dict[str, str] = {
    "N": "knight",
    "B": "bishop",
    "R": "rook",
    "Q": "queen",
    "K": "king",
}


def _extract_target(san: str) -> str:
    """Return the target square (last two alphanumeric chars, ignoring =, +, #)."""
    s = san.rstrip("+#")
    s = re.sub(r"=[QRBNqrbn]$", "", s)
    return s[-2:] if len(s) >= 2 else s


def verbalize_san(
    san: str,
    color: str,
    board_before: Optional[chess.Board] = None,
) -> str:
    """
    Convert a SAN move to a plain-English phrase.

    If board_before is provided, capture moves include the name of the captured piece.
    color is "white" or "black".
    """
    if not san:
        return ""

    Color = color.capitalize()

    # Castling
    if san.startswith(("O-O-O", "0-0-0")):
        return f"{Color} castles queenside"
    if san.startswith(("O-O", "0-0")):
        return f"{Color} castles kingside"

    # Promotion
    promo = re.search(r"=([QRBNqrbn])", san)
    if promo:
        promo_piece = _PIECE_NAMES.get(promo.group(1).upper(), "queen")
        target = _extract_target(san)
        return f"{Color}'s pawn promotes to {promo_piece} on {target}"

    # Suffix
    if san.endswith("#"):
        suffix = " — checkmate"
    elif san.endswith("+"):
        suffix = " with check"
    else:
        suffix = ""

    is_capture = "x" in san
    target = _extract_target(san)

    # Piece type
    first = san[0]
    print(f"DEBUG: first char of SAN is '{first}'. А целиком епты  ХУЙНЯ: {san}")
    if first.isupper() and first in _PIECE_NAMES:
        piece = _PIECE_NAMES[first]
    else:
        initial_square = san[0:2]
        print(f"DEBUG: initial_square is '{initial_square}'")
        p = board_before.piece_at(chess.parse_square(initial_square)) if board_before else None
        if p:
            piece = chess.piece_name(p.piece_type)
        else:
            piece = "pawn"
    if is_capture:
        captured_name: Optional[str] = None
        if board_before is not None:
            try:
                sq = chess.parse_square(target)
                p = board_before.piece_at(sq)
                if p:
                    captured_name = chess.piece_name(p.piece_type)
            except Exception:
                pass
        if captured_name:
            action = f"captures {captured_name} on"
        else:
            action = "takes on"
    else:
        action = "moves to"

    return f"{Color}'s {piece} {action} {target}{suffix}"


def _piece_label(san: str) -> str:
    """Convert one SAN move to 'piece to square' form, stripping captures/checks."""
    if not san:
        return ""
    if san.startswith(("O-O-O", "0-0-0")):
        return "castling queenside"
    if san.startswith(("O-O", "0-0")):
        return "castling kingside"

    promo = re.search(r"=([QRBNqrbn])", san)
    if promo:
        promo_piece = _PIECE_NAMES.get(promo.group(1).upper(), "queen")
        target = _extract_target(san)
        return f"pawn promotes to {promo_piece} on {target}"

    s = san.rstrip("+#")
    s = re.sub(r"=[QRBNqrbn]$", "", s)
    target = s[-2:] if len(s) >= 2 else s

    first = san[0]
    if first.isupper() and first in _PIECE_NAMES:
        return f"{_PIECE_NAMES[first]} to {target}"
    return f"pawn to {target}"


def verbalize_pv(pv_san: list[str], stm: str) -> str:
    """
    Verbalize the first 3 moves of the engine PV as plain English.
    stm = side to move at the position being analyzed ("white" | "black").
    Returns empty string if pv_san is empty.
    """
    if not pv_san:
        return ""
    labels = [_piece_label(s) for s in pv_san[:3] if s]
    if not labels:
        return ""
    if len(labels) == 1:
        return f"engine plans {labels[0]}"
    if len(labels) == 2:
        return f"engine plans {labels[0]} — after {labels[1]}"
    return f"engine plans {labels[0]} — after {labels[1]}, then {labels[2]}"


def verbalize_eval(
    cp_white: Optional[int],
    mate_white: Optional[int],
    our_side: str,
) -> str:
    """
    5-level verbal scale from our_side's perspective.
    cp_white and mate_white are both from White's point of view
    (positive = good for White; negative = good for Black).
    """
    if mate_white is not None:
        our_mating = (mate_white > 0) if our_side == "white" else (mate_white < 0)
        return "forced mate" if our_mating else "getting mated"

    if cp_white is None:
        return "roughly equal"

    our_cp = cp_white if our_side == "white" else -cp_white

    if our_cp > 150:
        return "much better"
    if our_cp > 50:
        return "slightly better"
    if our_cp >= -50:
        return "roughly equal"
    if our_cp >= -150:
        return "slightly worse"
    return "much worse"


def verbalize_eval_delta(
    prev_cp_white: Optional[int],
    curr_cp_white: Optional[int],
    our_side: str,
) -> str:
    """
    Describe how the position changed after a move, from our_side's perspective.
    Inputs are both white-perspective centipawns.
    Returns a compact phrase like "significant loss for us" or "no significant change".
    """
    if prev_cp_white is None or curr_cp_white is None:
        return "position shifted"

    # Delta from our perspective (positive = we gained)
    our_delta = (curr_cp_white - prev_cp_white) * (1 if our_side == "white" else -1)
    abs_d = abs(our_delta)

    if abs_d < 10:
        return "no significant change"

    direction = "gain" if our_delta > 0 else "loss"

    if abs_d < 50:
        magnitude = "small"
    elif abs_d < 150:
        magnitude = "significant"
    else:
        magnitude = "decisive"

    return f"{magnitude} {direction} for us"
