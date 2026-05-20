"""
Opening theory knowledge base built from openings_text_checkpoint.tsv.

Indexed by opening_key (URL slug, e.g. 'ruy-lopez/berlin-defense').
Provides lookup by opening name (e.g. 'Ruy Lopez: Berlin Defense') with
automatic parent-key fallback for variations not in the dataset.

Public API:
    lookup_by_name(name: str) -> str | None
    name_to_key(name: str) -> str
"""
from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

_TSV_PATH = (
    Path(__file__).parent.parent
    / "archive" / "data" / "openings" / "openings_text_checkpoint.tsv"
)


def name_to_key(name: str) -> str:
    """Convert an opening name to its URL-slug opening_key.

    'Ruy Lopez: Berlin Defense, l'Hermet Variation'
    → 'ruy-lopez/berlin-defense/lhermet-variation'
    """
    # Strip accents (ü→u, á→a, é→e …)
    normalized = unicodedata.normalize("NFD", name)
    name = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    name = name.lower()
    # Separator patterns: ': ' and ', ' → '/'
    name = re.sub(r"[:\,]\s*", "/", name)
    # Spaces → hyphens
    name = re.sub(r"\s+", "-", name)
    # Strip anything that's not alphanumeric, hyphen, or slash
    name = re.sub(r"[^a-z0-9/\-]", "", name)
    return name.strip("/")


def _parent_keys(key: str) -> list[str]:
    """Return progressively shorter parent keys, e.g. a/b/c → [a/b, a]."""
    parts = key.split("/")
    return ["/".join(parts[:i]) for i in range(len(parts) - 1, 0, -1)]


# ── Dataset (loaded once at import) ────────────────────────────────────────────

_KB: dict[str, str] = {}   # opening_key → text


def _load() -> None:
    if not _TSV_PATH.exists():
        return
    with _TSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            key = row.get("opening_key", "").strip()
            text = row.get("text", "").strip()
            if key and text:
                _KB[key] = text


_load()


def lookup_by_name(name: str) -> str | None:
    """Return theory text for an opening name, with parent-key fallback.

    Returns None when the opening is not in the dataset or has no text.
    """
    key = name_to_key(name)
    text = _KB.get(key)
    if text:
        return text
    for parent in _parent_keys(key):
        text = _KB.get(parent)
        if text:
            return text
    return None


def kb_size() -> int:
    return len(_KB)
