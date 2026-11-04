"""Generate the labeled synthetic review set: eval/dataset.jsonl.

Ground truth is known by construction: each spec fixes the score and theme, and the generator
model writes a fictional review that fits it. Run: uv run python -m eval.generate_dataset
"""

import asyncio
import json
import random
from pathlib import Path

from app.config import settings
from app.openrouter import OpenRouterClient

GENERATOR_MODEL = "google/gemini-4-argon"  # a different vendor than the evaluated candidates
OUT = Path(__file__).parent / "dataset.jsonl"
THEMES = ["food", "service", "wait", "price", "cleanliness", "ambiance", "portions"]

# kind -> (count, instruction for the writer)
KINDS = {
    "normal": (45, "A plain, realistic review."),
    "sarcasm": (8, "Sarcastic: sounds positive on the surface but is really negative."),
    "mixed": (
        10,
        "Mixed: mention one clearly opposite minor aspect, but the given theme dominates.",
    ),
    "typos": (8, "Written quickly with several spelling mistakes and no punctuation care."),
    "emoji": (6, "Informal, uses a few emoji."),
    "short": (8, "Very short: one to four words."),
    "non_english": (
        8,
        "Written in a non-English language (vary: Finnish, Spanish, German, French, Estonian).",
    ),
    "no_theme": (
        7,
        (
            "About nothing specific to the restaurant (generic, off-topic or empty of detail); "
            "theme is other."
        ),
    ),
}

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

SYSTEM = """You write fictional restaurant reviews as test data. For each spec, write one review that
a real customer might post. Rules: the review must clearly deserve the given score
(1 very negative, 2 negative, 3 neutral or mixed, 4 positive, 5 very positive) and be mostly about the
given theme (theme 'other' means no restaurant aspect dominates). Follow the style instruction.
Never state the score number or the theme name as a label. Invent details; vary wording and length.
Return one review per spec id."""


def build_specs(rng: random.Random) -> list[dict]:
    specs = []
    for kind, (count, note) in KINDS.items():
        for _ in range(count):
            if kind == "sarcasm":
                score = rng.choice([1, 2])
            elif kind == "mixed" or kind == "no_theme":
                score = rng.choice([2, 3, 4])
            else:
                score = rng.choice([1, 1, 2, 2, 3, 4, 4, 5, 5])
            theme = "other" if kind == "no_theme" else rng.choice(THEMES)
            specs.append({"kind": kind, "score": score, "theme": theme, "style": note})
    rng.shuffle(specs)
    for i, spec in enumerate(specs):
        spec["id"] = i
    return specs


async def write_chunk(llm: OpenRouterClient, chunk: list[dict]) -> dict[int, str]:
    user = "\n".join(
        f"id={s['id']} score={s['score']} theme={s['theme']} style={s['style']}" for s in chunk
    )
    reply = await llm.chat_json(SYSTEM, user, "reviews", SCHEMA)
    return {item["id"]: item["text"].strip() for item in reply.data["items"]}


async def main() -> None:
    specs = build_specs(random.Random(42))
    llm = OpenRouterClient(settings.openrouter_api_key, GENERATOR_MODEL)
    chunks = [specs[i : i + 20] for i in range(0, len(specs), 20)]
    parts = await asyncio.gather(*(write_chunk(llm, c) for c in chunks))
    texts = {k: v for part in parts for k, v in part.items()}
    await llm.aclose()
    rows = [
        {
            "id": s["id"],
            "text": texts[s["id"]],
            "score": s["score"],
            "theme": s["theme"],
            "kind": s["kind"],
        }
        for s in specs
        if texts.get(s["id"])
    ]
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    print(f"Wrote {len(rows)} reviews to {OUT} (cost ${llm.total_cost:.4f})")


if __name__ == "__main__":
    asyncio.run(main())
