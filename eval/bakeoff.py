"""Compare candidate models on the labeled dataset.

Run: uv run python -m eval.bakeoff [candidate name ...]
Writes docs/bakeoff.md and prints the table.
"""

import asyncio
import json
import sys
import time
import tomllib
from collections import defaultdict
from pathlib import Path

from app.analyzers.jev import JevAnalyzer
from app.analyzers.llm import LLMAnalyzer
from app.config import settings
from app.db import DEFAULT_THEMES
from app.openrouter import AnalyzerError, OpenRouterClient
from app.runner import analyze_reviews
from app.schemas import ReviewIn
from app.sentiment import sentiment_from_score

HERE = Path(__file__).parent
REPORT = HERE.parent / "docs" / "bakeoff.md"
# Targets from docs/spec.md section 4
TARGETS = {"label": 0.90, "score": 0.85, "theme": 0.80, "clean": 0.99, "cost": 0.05, "seconds": 30}


def load_dataset() -> list[dict]:
    return [json.loads(line) for line in (HERE / "dataset.jsonl").read_text().splitlines()]


async def evaluate(candidate: dict, rows: list[dict]) -> dict:
    if candidate.get("analyzer") == "jev":
        analyzer = llm = JevAnalyzer(settings.openrouter_api_key, candidate["model"])
    else:
        llm = OpenRouterClient(
            settings.openrouter_api_key, candidate["model"], candidate.get("reasoning") or None
        )
        analyzer = LLMAnalyzer(llm)
    items = [ReviewIn(id=r["id"], text=r["text"]) for r in rows]
    start = time.perf_counter()
    try:
        got = await analyze_reviews(analyzer, items, DEFAULT_THEMES)
    except AnalyzerError as e:
        await llm.aclose()
        return {"name": candidate["name"], "error": str(e)[:120]}
    seconds = time.perf_counter() - start
    await llm.aclose()

    n = len(rows)
    label = score = theme = 0
    by_kind: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        res = got.get(r["id"])
        hit = bool(res) and sentiment_from_score(res.score) == sentiment_from_score(r["score"])
        label += hit
        score += bool(res) and abs(res.score - r["score"]) <= 1
        theme += bool(res) and res.theme == r["theme"]
        by_kind[r["kind"]].append(int(hit))
    calls = analyzer.stats.calls
    return {
        "name": candidate["name"],
        "model": candidate["model"],
        "label": label / n,
        "score": score / n,
        "theme": theme / n,
        "failed": n - len(got),
        "clean": 1 - analyzer.stats.imperfect_calls / calls,
        "cost": llm.total_cost / n * 100,
        "seconds": seconds,
        "served": ", ".join(sorted(llm.models_seen)),
        "by_kind": {k: sum(v) / len(v) for k, v in by_kind.items()},
    }


def meets_all(r: dict) -> bool:
    return (
        r["label"] >= TARGETS["label"]
        and r["score"] >= TARGETS["score"]
        and r["theme"] >= TARGETS["theme"]
        and r["clean"] >= TARGETS["clean"]
        and r["cost"] < TARGETS["cost"]
        and r["seconds"] < TARGETS["seconds"]
    )


def render(results: list[dict], n: int) -> str:
    good = [r for r in results if "error" not in r]
    lines = [
        "# Model bake-off",
        "",
        (
            f"Dataset: {n} synthetic reviews (`eval/dataset.jsonl`), batches of 25, 4 concurrent, "
            "default theme list. Targets: label >= 90%, score +/-1 >= 85%, theme >= 80%, "
            "clean batches >= 99%, cost < $0.05 per 100 reviews, time < 30 s."
        ),
        "",
        (
            "| Candidate | Label acc | Score +/-1 | Theme acc | Failed | Clean calls | "
            "Cost / 100 | Time | Meets all | Served by |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if "error" in r:
            lines.append(f"| {r['name']} | error: {r['error']} | | | | | | | no | |")
            continue
        lines.append(
            f"| {r['name']} | {r['label']:.0%} | {r['score']:.0%} | {r['theme']:.0%} | "
            f"{r['failed']} | {r['clean']:.0%} | ${r['cost']:.4f} | {r['seconds']:.1f} s | "
            f"{'yes' if meets_all(r) else 'no'} | {r['served']} |"
        )
    kinds = sorted({k for r in good for k in r["by_kind"]})
    lines += [
        "",
        "Label accuracy by review kind:",
        "",
        "| Candidate | " + " | ".join(kinds) + " |",
        "|---|" + "---|" * len(kinds),
    ]
    for r in good:
        lines.append(
            f"| {r['name']} | " + " | ".join(f"{r['by_kind'][k]:.0%}" for k in kinds) + " |"
        )
    winners = sorted((r for r in good if meets_all(r)), key=lambda r: (r["cost"], r["seconds"]))
    lines += [
        "",
        (
            f"Default-model rule (cheapest that meets all targets): "
            f"**{winners[0]['name'] if winners else 'none meets all targets'}**"
        ),
        "",
    ]
    return "\n".join(lines)


async def main(names: list[str]) -> None:
    candidates = tomllib.loads((HERE / "candidates.toml").read_text())["candidate"]
    if names:
        candidates = [c for c in candidates if c["name"] in names]
    rows = load_dataset()
    results = []
    for c in candidates:
        print(f"running {c['name']} ...", flush=True)
        results.append(await evaluate(c, rows))
    report = render(results, len(rows))
    REPORT.write_text(report)
    print(report)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
