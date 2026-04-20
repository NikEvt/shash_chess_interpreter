"""
GCC evaluation script — OpenRouter variant (z-ai/glm-4.5-air:free).

Usage:
    export OPENROUTER_API_KEY=sk-or-...
    python3 run_eval_openrouter.py
    python3 run_eval_openrouter.py --csv eval_dataset.csv --out results/eval_scores_or.json
"""

import argparse
import csv
import json
import os
import re
import time
from pathlib import Path

import numpy as np
from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────

MODEL    = "openrouter/elephant-alpha"
BASE_URL = "https://openrouter.ai/api/v1"

# Free tier: ~20 req/min — sleep between requests to avoid 429s
REQUEST_DELAY = 3.5  # seconds

# ── Engine eval string from CSV columns ───────────────────────────────────────

def build_engine_eval(row: dict) -> str:
    played  = row.get("played_move", "").strip()
    best    = row.get("engine_best_move", "").strip()
    cp      = row.get("score_cp", "").strip()
    mate    = row.get("mate_in", "").strip()
    wdl_w   = row.get("wdl_win", "").strip()
    wdl_d   = row.get("wdl_draw", "").strip()
    wdl_l   = row.get("wdl_loss", "").strip()
    style   = row.get("shashin_type", "").strip()

    if mate:
        score_str = f"Mate in {mate}"
    elif cp:
        score_str = f"{cp}cp"
    else:
        score_str = "unknown"

    wdl_str   = f"WDL {wdl_w}/{wdl_d}/{wdl_l}" if wdl_w else ""
    style_str = f"style: {style}" if style else ""

    parts = [
        f"played move: {played}",
        f"engine best move: {best}" if best and best != played else "",
        f"score after played move: {score_str}",
        wdl_str,
        style_str,
    ]
    return ", ".join(p for p in parts if p)

# ── Scoring ───────────────────────────────────────────────────────────────────

def soft_score(response) -> float:
    """Weighted score from logprobs over tokens '1'..'5', falls back to text parse."""
    try:
        top = response.choices[0].logprobs.content[0].top_logprobs
        token_probs = [(t.token, np.exp(t.logprob)) for t in top]
        valid = [(int(t), p) for t, p in token_probs if t in ("1", "2", "3", "4", "5")]
        if not valid:
            text = (response.choices[0].message.content or "").strip()
            m = re.search(r"[1-5]", text)
            return float(m.group()) if m else 3.0
        norm = sum(p for _, p in valid)
        return sum(s * p / norm for s, p in valid)
    except Exception:
        text = (response.choices[0].message.content or "").strip()
        m = re.search(r"[1-5]", text)
        return float(m.group()) if m else 3.0


def _call(client, messages) -> object:
    # OpenRouter doesn't support chat_template_kwargs — omit extra_body
    for attempt in range(5):
        try:
            r = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                logprobs=True,
                top_logprobs=10,
                temperature=0.0,
            )
            time.sleep(REQUEST_DELAY)
            return r
        except Exception as e:
            if "429" in str(e):
                wait = REQUEST_DELAY * (2 ** attempt)
                print(f"  429 rate-limit, retrying in {wait:.0f}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Max retries exceeded")


def score_relevance(client, fen, move_full, comment, ref, engine_eval):
    return soft_score(_call(client, [
        {"role": "system", "content": (
            "You will be given two comments about a chess move.\n"
            "Rate the target comment on Relevance (1-5): how relevant it is to "
            "important aspects of the chess move. Use the reference comment and "
            "engine evaluation as hints."
        )},
        {"role": "user", "content": (
            f"position:\n{fen}\n\nmove:\n{move_full}\n\n"
            f"target comment:\n\n{comment}\n\n"
            f"reference comment:\n\n{ref}\n\n"
            f"engine evaluation:\n\n{engine_eval}\n\n"
            "Score(1-5, score ONLY): "
        )},
    ]))


def score_completeness(client, fen, move_full, comment, engine_eval):
    return soft_score(_call(client, [
        {"role": "system", "content": (
            "Rate the comment on Completeness (1-5): does it cover all critical "
            "points on the chess board without overlooking important factors? "
            "Engine evaluation is a hint."
        )},
        {"role": "user", "content": (
            f"position:\n{fen}\n\nmove:\n{move_full}\n\n"
            f"comment:\n\n{comment}\n\n"
            f"engine evaluation:\n\n{engine_eval}\n\n"
            "Score(1-5, score ONLY): "
        )},
    ]))


def score_clarity(client, fen, move_full, comment):
    return soft_score(_call(client, [
        {"role": "system", "content": (
            "Rate the comment on Clarity (1-5): is it clear and detailed, "
            "without vague or ambiguous statements?"
        )},
        {"role": "user", "content": (
            f"position:\n{fen}\n\nmove:\n{move_full}\n\n"
            f"comment:\n\n{comment}\n\n"
            "Score(1-5, score ONLY): "
        )},
    ]))


def score_fluency(client, comment):
    return soft_score(_call(client, [
        {"role": "system", "content": (
            "Rate the comment on Fluency (1-5): is it coherently organized "
            "with well-structured language?"
        )},
        {"role": "user", "content": (
            f"target comment:\n\n{comment}\n\n"
            "Score(1-5, score ONLY): "
        )},
    ]))

# ── Helpers ───────────────────────────────────────────────────────────────────

def avg(lst):
    return round(sum(lst) / len(lst), 4) if lst else None


def print_table(averages: dict):
    sources = ["ref", "gac", "agent"]
    metrics = list(averages.keys())
    col_w = 10

    header = f"{'metric':<14}" + "".join(f"{s:>{col_w}}" for s in sources)
    print("\n" + "=" * (14 + col_w * len(sources)))
    print("AVERAGES")
    print("=" * (14 + col_w * len(sources)))
    print(header)
    print("-" * (14 + col_w * len(sources)))
    for m in metrics:
        row = f"{m:<14}"
        for s in sources:
            val = averages[m].get(s)
            row += f"{val:>{col_w}.3f}" if val is not None else f"{'—':>{col_w}}"
        print(row)
    print("=" * (14 + col_w * len(sources)))

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global MODEL
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv",     default="eval_dataset.csv")
    parser.add_argument("--out",     default="results/eval_scores_or.json")
    parser.add_argument("--model",   default=MODEL)
    parser.add_argument("--metrics", default="relevance,completeness,clarity,fluency")
    args = parser.parse_args()
    MODEL = args.model

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("WARNING: OPENROUTER_API_KEY not set")
    client = OpenAI(base_url=BASE_URL, api_key=api_key)
    metrics = [m.strip() for m in args.metrics.split(",")]

    with open(args.csv, newline="", encoding="utf-8") as f:
        records = list(csv.DictReader(f))
    print(f"Loaded {len(records)} records from {args.csv}")
    n_requests = len(records) * len(metrics) * 3
    eta_min = n_requests * REQUEST_DELAY / 60
    print(f"~{n_requests} requests, ETA ~{eta_min:.0f} min at {REQUEST_DELAY}s/req delay")

    scores: dict[str, dict[str, list]] = {
        m: {"ref": [], "gac": [], "agent": []}
        for m in metrics
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    for idx, rec in enumerate(records):
        fen       = rec["fen"].strip()
        move_full = rec["move_full"].strip()
        ref       = rec["ref"].strip()

        engine_eval = build_engine_eval(rec)

        sources = {
            "ref":   ref,
            "gac":   (rec.get("gac") or "").strip(),
            "agent": (rec.get("agent_response") or "").strip(),
        }

        print(f"\n[{idx+1}/{len(records)}] {move_full}  |  {engine_eval}")

        for source_name, comment in sources.items():
            if not comment:
                continue
            try:
                if "relevance" in metrics:
                    s = score_relevance(client, fen, move_full, comment, ref, engine_eval)
                    scores["relevance"][source_name].append(s)
                    print(f"  relevance    [{source_name}]: {s:.3f}")

                if "completeness" in metrics:
                    s = score_completeness(client, fen, move_full, comment, engine_eval)
                    scores["completeness"][source_name].append(s)
                    print(f"  completeness [{source_name}]: {s:.3f}")

                if "clarity" in metrics:
                    s = score_clarity(client, fen, move_full, comment)
                    scores["clarity"][source_name].append(s)
                    print(f"  clarity      [{source_name}]: {s:.3f}")

                if "fluency" in metrics:
                    s = score_fluency(client, comment)
                    scores["fluency"][source_name].append(s)
                    print(f"  fluency      [{source_name}]: {s:.3f}")

            except Exception as e:
                print(f"  Error [{source_name}]: {e}")
                time.sleep(5)

        with open(args.out, "w") as f:
            json.dump(scores, f, indent=2)

    averages = {}
    for metric, src_scores in scores.items():
        averages[metric] = {src: avg(vals) for src, vals in src_scores.items() if vals}

    print_table(averages)

    with open(args.out, "w") as f:
        json.dump({"scores": scores, "averages": averages}, f, indent=2)
    print(f"\nSaved to {args.out}")


if __name__ == "__main__":
    main()
