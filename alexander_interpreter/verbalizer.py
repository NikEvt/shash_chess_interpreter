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
    if first.isupper() and first in _PIECE_NAMES:
        piece = _PIECE_NAMES[first]
    else:
        # Pawn move: try to infer from board or SAN context
        piece = "pawn"
        # For pawn captures like "bxc3", we need the board to find the source square
        if board_before and is_capture:
            try:
                move = board_before.parse_san(san)
                source_sq = chess.square_name(move.from_square)
                target_sq = chess.square_name(move.to_square)
                target_piece = board_before.piece_at(move.to_square)
                if target_piece:
                    captured_name = chess.piece_name(target_piece.piece_type)
                    action = f"captures {captured_name} on"
                    return f"{Color}'s {piece} {action} {target_sq}{suffix}"
            except (ValueError, AttributeError):
                pass

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


def verbalize_pv_verbose(pv_san: list[str], stm: str) -> str:
    """
    Verbose PV: shows who moves at each step with explicit color attribution.
    Helps small LLMs understand the sequence and whose turn it is.

    Example: "Engine plans: Black pawn to e6 — after White's knight to c3,
             then Black's pawn to g6"

    stm = side to move ("white" | "black")
    """
    if not pv_san:
        return ""

    # Track whose turn it is for each move in the sequence
    moves_with_color = []
    current_color = stm
    for san in pv_san[:3]:
        if san:
            label = _piece_label(san)
            if label:
                Color = current_color.capitalize()
                moves_with_color.append((Color, label))
            current_color = "black" if current_color == "white" else "white"

    if not moves_with_color:
        return ""

    if len(moves_with_color) == 1:
        color, label = moves_with_color[0]
        return f"Engine plans: {color} {label}"

    if len(moves_with_color) == 2:
        color1, label1 = moves_with_color[0]
        color2, label2 = moves_with_color[1]
        return f"Engine plans: {color1} {label1} — after {color2}'s {label2}"

    color1, label1 = moves_with_color[0]
    color2, label2 = moves_with_color[1]
    color3, label3 = moves_with_color[2]
    return f"Engine plans: {color1} {label1} — after {color2}'s {label2}, then {color3}'s {label3}"


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

    our_delta = (curr_cp_white - prev_cp_white) * (1 if our_side == "white" else -1)
    abs_d = abs(our_delta)

    if abs_d < 10:
        return "no significant change"

    beneficiary = our_side if our_delta > 0 else ("black" if our_side == "white" else "white")
    Beneficiary = beneficiary.capitalize()

    if abs_d < 50:
        magnitude = "small"
    elif abs_d < 150:
        magnitude = "significant"
    else:
        magnitude = "decisive"

    direction = "gain"
    return f"{magnitude} {direction} for {Beneficiary}"
