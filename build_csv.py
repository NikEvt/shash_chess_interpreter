"""
Build evaluation CSV combining:
  - positions.py  : FEN, move, REF, GAC
  - mock_engine.py: engine eval, best_move, shashin_type, wdl, played_move
  - smoke_results.md: LLM-generated agent response

Output: eval_dataset.csv
"""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from positions import FENS, MOVES, REF, GAC, move_san as extract_san
from mamka.shash_chess_interpreter.mock_engine import MOCK_POSITIONS


# ── Parse smoke_results.md ─────────────────────────────────────────────────────

def parse_smoke_results(md_path: Path) -> dict[str, str]:
    """Return {pos_key: agent_response_text}."""
    text = md_path.read_text(encoding="utf-8")

    responses: dict[str, str] = {}
    # Each section starts with "## ✅ PASS — pos_XX" or "## ❌ FAIL — pos_XX"
    # Agent response is the blockquote after "### Agent response"
    sections = re.split(r"\n---\n", text)

    for section in sections:
        key_m = re.search(r"##\s+[✅❌]\s+(?:PASS|FAIL)\s+[—–-]\s+(pos_\d+)", section)
        if not key_m:
            continue
        key = key_m.group(1)

        # Extract blockquote lines (lines starting with "> ")
        resp_m = re.search(r"### Agent response\s*\n((?:>.*\n?)+)", section)
        if resp_m:
            raw = resp_m.group(1)
            # Strip "> " prefix and markdown bold markers
            lines = []
            for line in raw.splitlines():
                line = re.sub(r"^>\s?", "", line)
                line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)  # **bold** → bold
                lines.append(line.strip())
            responses[key] = " ".join(l for l in lines if l)
        else:
            responses[key] = ""

    return responses


# ── Build CSV ──────────────────────────────────────────────────────────────────

def build_csv(out_path: Path) -> None:
    md_path = Path(__file__).parent / "smoke_results.md"
    if not md_path.exists():
        print(f"ERROR: {md_path} not found. Run smoke_test.py first.", file=sys.stderr)
        sys.exit(1)

    agent_responses = parse_smoke_results(md_path)

    fieldnames = [
        "pos_id",
        "idx",
        "fen",
        "move_full",
        "move_san",
        "side_to_move",
        "score_cp",
        "mate_in",
        "wdl_win",
        "wdl_draw",
        "wdl_loss",
        "shashin_type",
        "engine_best_move",
        "played_move",
        "ref",
        "gac",
        "agent_response",
    ]

    rows = []
    missing_keys = []

    for i in range(len(FENS)):
        key = f"pos_{i:02d}"
        eng = MOCK_POSITIONS.get(key)
        if eng is None:
            missing_keys.append(key)
            continue

        rows.append({
            "pos_id":          key,
            "idx":             i,
            "fen":             FENS[i],
            "move_full":       MOVES[i],
            "move_san":        extract_san(MOVES[i]),
            "side_to_move":    eng.side_to_move,
            "score_cp":        "" if eng.score_cp is None else eng.score_cp,
            "mate_in":         "" if eng.mate_in  is None else eng.mate_in,
            "wdl_win":         eng.wdl_win,
            "wdl_draw":        eng.wdl_draw,
            "wdl_loss":        eng.wdl_loss,
            "shashin_type":    eng.shashin_type,
            "engine_best_move":eng.best_move_san,
            "played_move":     eng.played_move,
            "ref":             REF[i].strip(),
            "gac":             GAC[i].strip(),
            "agent_response":  agent_responses.get(key, ""),
        })

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Written {len(rows)} rows → {out_path}")
    if missing_keys:
        print(f"WARNING: missing engine data for: {missing_keys}")

    # Quick stats
    n_agent = sum(1 for r in rows if r["agent_response"])
    n_match = sum(1 for r in rows if r["engine_best_move"] == r["played_move"])
    print(f"Agent responses present : {n_agent}/{len(rows)}")
    print(f"Engine agrees with play : {n_match}/{len(rows)} ({100*n_match//len(rows)}%)")


if __name__ == "__main__":
    out = Path(__file__).parent / "eval_dataset.csv"
    build_csv(out)
