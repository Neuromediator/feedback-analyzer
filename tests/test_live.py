"""Calls the real OpenRouter API. Run with: uv run pytest -m live"""

import pytest

from app.analyzers.llm import LLMAnalyzer
from app.config import Settings
from app.openrouter import OpenRouterClient
from app.schemas import ReviewIn
from app.suggester import Suggester

pytestmark = pytest.mark.live
THEMES = ["food", "service", "wait", "other"]


async def test_live_analyze_and_suggest():
    s = Settings()
    llm = OpenRouterClient(s.openrouter_api_key, s.openrouter_model, s.openrouter_reasoning or None)
    batch = [
        ReviewIn(id=0, text="Amazing pasta, loved it"),
        ReviewIn(id=1, text="We waited an hour for cold soup"),
    ]
    results = await LLMAnalyzer(llm).analyze(batch, THEMES)
    by_id = {r.id: r for r in results}
    assert by_id[0].score >= 4 and by_id[1].score <= 2
    suggestions = await Suggester(llm).suggest([(1, batch[1].text, by_id[1].theme)])
    assert suggestions[1]
    await llm.aclose()
