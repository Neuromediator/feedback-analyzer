"""Jev analyzer: TypeSafe's decision model through the OpenRouter Decisions API.

One request per review with two typed questions: a 5-point score and a theme choice.
"""

import asyncio
from dataclasses import dataclass, field

import httpx

from app.analyzers.llm import THEME_GUIDE, CallStats
from app.openrouter import AnalyzerError, response_error
from app.schemas import RawResult, ReviewIn

URL = "https://openrouter.ai/api/alpha/decisions"
SCORE_LEVELS = [
    "Very negative: angry, would not return",
    "Negative: clearly disappointed",
    "Neutral or mixed",
    "Positive: satisfied",
    "Very positive: delighted, enthusiastic",
]


@dataclass
class JevAnalyzer:
    api_key: str
    model: str = "typesafe/jev-1.14"
    max_concurrent: int = 8
    timeout: float = 60
    client: httpx.AsyncClient | None = None
    total_cost: float = 0.0
    models_seen: set[str] = field(default_factory=set)
    stats: CallStats = field(default_factory=CallStats)

    def __post_init__(self):
        self._slots = asyncio.Semaphore(self.max_concurrent)

    async def aclose(self) -> None:
        if self.client:
            await self.client.aclose()

    async def analyze(self, batch: list[ReviewIn], themes: list[str]) -> list[RawResult]:
        """Analyze each review separately; reviews whose request failed are omitted."""
        self.stats.calls += 1
        questions = build_questions(themes)
        errors: list[AnalyzerError] = []
        try:
            found = await asyncio.gather(*(self._one(r, questions, errors) for r in batch))
            results = [r for r in found if r]
            if errors and not results:
                raise errors[0]
        except AnalyzerError:
            self.stats.imperfect_calls += 1
            raise
        if len(results) < len(batch):
            self.stats.imperfect_calls += 1
        return results

    async def _one(
        self, review: ReviewIn, questions: dict, errors: list[AnalyzerError]
    ) -> RawResult | None:
        """Return None on a retryable failure so the runner can retry; fatal errors propagate."""
        try:
            body = await self._post({"state": {"review": review.text}, "questions": questions})
        except AnalyzerError as e:
            if e.fatal:
                raise
            errors.append(e)
            return None
        self.total_cost += (body.get("usage") or {}).get("cost") or 0.0
        served = body.get("model") or self.model
        self.models_seen.add(served)
        try:
            theme = body["answers"]["theme"]["choice"]
            score = score_from_position(body["answers"]["score"]["score"])
        except (KeyError, TypeError):
            return None
        if theme not in questions["theme"]["criteria"]:
            return None
        return RawResult(id=review.id, score=score, theme=theme, model=served)

    async def _post(self, payload: dict) -> dict:
        if not self.api_key:
            raise AnalyzerError(
                "OPENROUTER_API_KEY is not set. Add it to the .env file.", fatal=True
            )
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=self.timeout)
        async with self._slots:
            try:
                resp = await self.client.post(
                    URL,
                    json={"model": self.model, **payload},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            except httpx.HTTPError as e:
                raise AnalyzerError(f"Could not reach OpenRouter: {type(e).__name__}") from e
        if resp.status_code != 200:
            raise response_error(resp)
        try:
            return resp.json()
        except ValueError:
            raise AnalyzerError("Jev returned an unusable response.") from None


def build_questions(themes: list[str]) -> dict:
    return {
        "score": {
            "type": "score",
            "instructions": "How satisfied is the customer with the restaurant?",
            "criteria": SCORE_LEVELS,
        },
        "theme": {
            "type": "choice",
            "instructions": "Which single topic is the review mostly about?",
            "criteria": {t: THEME_GUIDE.get(t, t) for t in themes},
        },
    }


def score_from_position(position: float) -> int:
    """Jev scores sit on the 0-4 scale position; map to a 1-5 score."""
    return min(5, max(1, round(position) + 1))
