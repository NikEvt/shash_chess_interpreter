"""
Chess theory knowledge base for Alexander interpreter.

Data is loaded from archive/data/knowledge_base.json at import time.
Each chunk has: id (str), tags (list[str]), text (str).
"""
from __future__ import annotations

import json
from pathlib import Path

_JSON_PATH = Path(__file__).parent.parent / "archive" / "data" / "knowledge_base.json"


def _load() -> list[dict]:
    with _JSON_PATH.open(encoding="utf-8") as f:
        raw: list[dict] = json.load(f)
    return [{"id": item["id"], "tags": item["tags"], "text": item["text"]} for item in raw]


CHUNKS: list[dict] = _load()
