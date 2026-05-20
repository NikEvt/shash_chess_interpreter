"""
Opening theory knowledge base built from openings_text_checkpoint.tsv.

Each opening entry is split into three focused chunks:
  - best_moves:   principal continuation with explanation
  - alternatives: reasonable but suboptimal moves (important_alternatives column)
  - mistakes:     moves to avoid with explanation (critical_mistakes column)

Chunk selection is driven by move quality so the model sees the most relevant
theory for the position:
  - best / excellent / good / unknown  → best_moves
  - inaccuracy                         → alternatives  (fallback: best_moves)
  - mistake / blunder                  → mistakes + best_moves  (combined)

Public API:
    lookup_chunks(name: str) -> OpeningTheoryEntry | None
    select_chunk(entry, move_quality) -> str
    name_to_key(name: str) -> str
"""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

_TSV_PATH = (
    Path(__file__).parent.parent
    / "archive" / "data" / "openings" / "openings_text_checkpoint.tsv"
)


@dataclass(frozen=True)
class OpeningTheoryEntry:
    best_moves: str
    alternatives: str
    mistakes: str


def name_to_key(name: str) -> str:
    """Convert an opening name to its URL-slug opening_key.

    'Ruy Lopez: Berlin Defense, l'Hermet Variation'
    → 'ruy-lopez/berlin-defense/lhermet-variation'
    """
    normalized = unicodedata.normalize("NFD", name)
    name = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    name = name.lower()
    name = re.sub(r"[:\,]\s*", "/", name)
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"[^a-z0-9/\-]", "", name)
    return name.strip("/")


def _parent_keys(key: str) -> list[str]:
    parts = key.split("/")
    return ["/".join(parts[:i]) for i in range(len(parts) - 1, 0, -1)]


# ── Dataset (loaded once at import) ────────────────────────────────────────────

_KB: dict[str, OpeningTheoryEntry] = {}


def _load() -> None:
    if not _TSV_PATH.exists():
        return
    with _TSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            key = row.get("opening_key", "").strip()
            bm = row.get("best_moves", "").strip()
            ia = row.get("important_alternatives", "").strip()
            cm = row.get("critical_mistakes", "").strip()
            if key and (bm or ia or cm):
                _KB[key] = OpeningTheoryEntry(
                    best_moves=bm,
                    alternatives=ia,
                    mistakes=cm,
                )


_load()


def lookup_chunks(name: str) -> OpeningTheoryEntry | None:
    """Return the three theory chunks for an opening name, with parent-key fallback."""
    key = name_to_key(name)
    entry = _KB.get(key)
    if entry:
        return entry
    for parent in _parent_keys(key):
        entry = _KB.get(parent)
        if entry:
            return entry
    return None


# Quality labels that map to each chunk type
_MISTAKES_QUALITIES = {"mistake", "blunder"}
_ALTERNATIVES_QUALITIES = {"inaccuracy"}


def select_chunk(entry: OpeningTheoryEntry, move_quality: str | None) -> str:
    """Return the theory text most relevant for this move quality.

    mistake/blunder  → mistakes chunk followed by best_moves (so model sees both
                       what went wrong and what was correct).
    inaccuracy       → alternatives (fallback to best_moves if empty).
    everything else  → best_moves.
    """
    q = (move_quality or "").lower()

    if q in _MISTAKES_QUALITIES:
        parts = [p for p in (entry.mistakes, entry.best_moves) if p]
        return "\n\n".join(parts)

    if q in _ALTERNATIVES_QUALITIES:
        return entry.alternatives or entry.best_moves

    return entry.best_moves or entry.alternatives


def kb_size() -> int:
    return len(_KB)
