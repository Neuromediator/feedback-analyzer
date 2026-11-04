import pytest

from app.openrouter import AnalyzerError
from app.schemas import RawResult


class FakeAnalyzer:
    """Scores by keyword. `drop` ids are omitted once; `always_drop` ids never succeed."""

    def __init__(self, drop=(), always_drop=(), fatal=None, junk=False):
        self.drop, self.always_drop, self.fatal, self.junk = (
            set(drop),
            set(always_drop),
            fatal,
            junk,
        )
        self.calls = []

    async def analyze(self, batch, themes):
        self.calls.append([r.id for r in batch])
        if self.fatal:
            raise AnalyzerError(self.fatal, fatal=True)
        out = []
        for r in batch:
            if r.id in self.always_drop or r.id in self.drop:
                continue
            text = r.text.lower()
            score = 1 if "bad" in text else 5 if "great" in text else 3
            theme = "wait" if "slow" in text else "food"
            out.append(RawResult(id=r.id, score=score, theme=theme, model="fake/model"))
        self.drop.clear()
        return out


class FakeSuggester:
    async def suggest(self, items):
        return {i: f"Fix: {theme}" for i, _, theme in items}


@pytest.fixture
def fake():
    return FakeAnalyzer
