"""
Opening book: maps terminal FEN position → ECO entry.

Data source: archive/data/chess_openings_dataset_checkpoint.tsv
Columns: eco, name, pgn, uci, epd, text

At import time we replay the UCI moves from the `uci` column using python-chess
to derive the correct terminal FEN (including en passant square). This is more
reliable than the precomputed `epd` field which always stores '-' for en passant.

Public API:
    lookup(fen) -> OpeningEntry | None
    eco_family_tokens(eco) -> str   # BM25 injection tokens
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

_TSV_PATH = Path(__file__).parent.parent / "archive" / "data" / "chess_openings_dataset_checkpoint.tsv"


@dataclass(frozen=True)
class OpeningEntry:
    eco: str
    name: str
    pgn: str
    text: str


def _normalise_uci(uci_str: str) -> str:
    """Lowercase and collapse whitespace in a UCI move sequence."""
    return " ".join(uci_str.lower().split())


# ── ECO letter → BM25 query tokens ────────────────────────────────────────────

_ECO_FAMILY_TOKENS: dict[str, str] = {
    "A": "flank opening irregular queenside development indian",
    "B": "sicilian caro-kann pirc alekhine modern sharp defense",
    "C": "open game ruy-lopez berlin italian giuoco spanish development",
    "D": "queens-gambit slav semi-slav grunfeld closed queenside pawn",
    "E": "nimzo-indian kings-indian queens-indian catalan benoni dynamic indian",
}

_ECO_RANGE_TOKENS: list[tuple[str, str, str]] = [
    ("B20", "B99", "sicilian najdorf dragon classical scheveningen sharp"),
    ("C60", "C99", "ruy-lopez berlin spanish endgame open center"),
    ("C00", "C19", "french defense advance exchange classical steinitz"),
    ("C20", "C59", "open game italian giuoco evans bishop center"),
    ("D10", "D29", "slav semi-slav meran anti-meran queens-gambit"),
    ("D30", "D69", "queens-gambit QGD nimzowitsch tarrasch"),
    ("D70", "D99", "grunfeld kings-indian russian classical exchange"),
    ("E00", "E59", "nimzo-indian queens-indian catalan reticulation bogo"),
    ("E60", "E99", "kings-indian benoni fianchetto samisch averbakh"),
    ("A10", "A39", "english opening symmetrical reversed sicilian"),
    ("A40", "A79", "queen-pawn indian defense catalan old benoni"),
    ("A80", "A99", "dutch defense leningrad stonewall classical"),
]


def _eco_range_tokens(eco: str) -> str | None:
    if len(eco) < 3:
        return None
    for start, end, tokens in _ECO_RANGE_TOKENS:
        if start[:1] == eco[0] and start[1:] <= eco[1:] <= end[1:]:
            return tokens
    return None


def eco_family_tokens(eco: str) -> str:
    """Return BM25 query tokens for the given ECO code (letter-level + range)."""
    if not eco:
        return ""
    specific = _eco_range_tokens(eco)
    general = _ECO_FAMILY_TOKENS.get(eco[0].upper(), "")
    if specific:
        return specific + " " + general
    return general


# ── Book dict (built once at import) ─────────────────────────────────────────

_BOOK: dict[str, OpeningEntry] = {}


def _load() -> None:
    if not _TSV_PATH.exists():
        return
    with _TSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            uci = row.get("uci", "").strip()
            if not uci:
                continue
            key = _normalise_uci(uci)
            _BOOK[key] = OpeningEntry(
                eco=row.get("eco", "").strip(),
                name=row.get("name", "").strip(),
                pgn=row.get("pgn", "").strip(),
                text=row.get("text", "").strip(),
            )


_load()


def lookup(game_uci: str) -> OpeningEntry | None:
    """Return the most specific OpeningEntry whose UCI sequence is a prefix of
    (or exactly matches) game_uci.  Tries the longest prefix first so that a
    deeper variation beats a shallower one.  Returns None if no prefix matches.
    """
    moves = _normalise_uci(game_uci).split()
    for length in range(len(moves), 0, -1):
        entry = _BOOK.get(" ".join(moves[:length]))
        if entry is not None:
            return entry
    return None


def lookup_with_depth(game_uci: str) -> tuple[OpeningEntry | None, int]:
    """Like lookup() but also returns the number of UCI half-moves that matched."""
    moves = _normalise_uci(game_uci).split()
    for length in range(len(moves), 0, -1):
        entry = _BOOK.get(" ".join(moves[:length]))
        if entry is not None:
            return entry, length
    return None, 0


def book_size() -> int:
    return len(_BOOK)
