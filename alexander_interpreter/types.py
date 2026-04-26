"""
Core data types for the Alexander chess engine interpreter.

AlexanderResult carries all data Alexander can expose beyond raw ShashChess:
  - 14-zone Shashin classification (computed from WDL, matches Alexander's own logic)
  - Top-3 moves from MultiPV with per-move WDL
  - PV continuation in SAN
  - Optional eval trace (material, mobility, king safety, etc.)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TopMove:
    uci: str
    san: str
    score_cp: Optional[int]
    mate_in: Optional[int]
    wdl_win: int   # 0-1000
    wdl_draw: int
    wdl_loss: int
    depth: int
    seldepth: int
    pv_san: list[str] = field(default_factory=list)

    @property
    def win_pct(self) -> float:
        return self.wdl_win / 10.0

    @property
    def draw_pct(self) -> float:
        return self.wdl_draw / 10.0

    def score_str(self) -> str:
        if self.mate_in is not None:
            return f"M{self.mate_in}"
        if self.score_cp is not None:
            sign = "+" if self.score_cp >= 0 else ""
            return f"{sign}{self.score_cp / 100:.1f}"
        return "?"


@dataclass
class EvalTrace:
    """
    Parsed output from Alexander's 'eval' command.
    Alexander uses Shashin/Makogonov metrics rather than Stockfish's term table.
    """
    # Best move win probability from eval (0-100)
    best_win_pct: Optional[float] = None
    # Free-form components extracted from eval output
    components: dict = field(default_factory=dict)

    def significant_factors(self, threshold: float = 1.0) -> list[tuple[str, float]]:
        """Return components sorted by absolute magnitude."""
        result = [(k, v) for k, v in self.components.items() if abs(v) >= threshold]
        return sorted(result, key=lambda x: abs(x[1]), reverse=True)


@dataclass
class AlexanderResult:
    """
    Full analysis result from Alexander engine for one position.
    Drop-in replacement for the old EngineResult, with richer fields.
    """
    fen: str
    side_to_move: str         # "white" | "black"
    played_move: str          # SAN of move played in game

    best_move_uci: str
    best_move_san: str
    score_cp: Optional[int]   # None when mate_in is set
    mate_in: Optional[int]

    wdl_win: int              # 0-1000, side-to-move perspective
    wdl_draw: int
    wdl_loss: int

    shashin_zone: str         # e.g. "CAPABLANCA", "HIGH_TAL", "LOW_PETROSIAN"

    top_moves: list[TopMove] = field(default_factory=list)
    pv_san: list[str] = field(default_factory=list)

    depth: int = 20
    seldepth: int = 20

    eval_trace: Optional[EvalTrace] = None
    raw_eval_lines: list[str] = field(default_factory=list)

    # --- convenience properties ---

    @property
    def win_pct(self) -> float:
        return self.wdl_win / 10.0

    @property
    def draw_pct(self) -> float:
        return self.wdl_draw / 10.0

    @property
    def loss_pct(self) -> float:
        return self.wdl_loss / 10.0

    @property
    def shashin_type(self) -> str:
        """3-category backward-compat alias (Tal/Capablanca/Petrosian)."""
        return _zone_to_category(self.shashin_zone)


# ── Shashin zone helpers ───────────────────────────────────────────────────────

# Thresholds match Alexander's shashin_types.h exactly
_ZONE_THRESHOLDS: list[tuple[int, str]] = [
    (5,   "HIGH_PETROSIAN"),
    (10,  "MIDDLE_HIGH_PETROSIAN"),
    (15,  "MIDDLE_PETROSIAN"),
    (20,  "MIDDLE_LOW_PETROSIAN"),
    (24,  "LOW_PETROSIAN"),
    (49,  "CAPABLANCA_PETROSIAN"),
    (50,  "CAPABLANCA"),
    (75,  "CAPABLANCA_TAL"),
    (79,  "LOW_TAL"),
    (84,  "MIDDLE_LOW_TAL"),
    (89,  "MIDDLE_TAL"),
    (94,  "MIDDLE_HIGH_TAL"),
    (100, "HIGH_TAL"),
]


def win_prob_to_shashin_zone(win_prob_pct: float) -> str:
    """Convert win probability (0-100) to Alexander's Shashin zone name."""
    for threshold, zone in _ZONE_THRESHOLDS:
        if win_prob_pct <= threshold:
            return zone
    return "HIGH_TAL"


def _zone_to_category(zone: str) -> str:
    if "TAL" in zone:
        return "Tal"
    if "PETROSIAN" in zone:
        return "Petrosian"
    return "Capablanca"
