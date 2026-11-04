"""The analyzer contract the runner depends on."""

from typing import Protocol

from app.schemas import RawResult, ReviewIn


class Analyzer(Protocol):
    async def analyze(self, batch: list[ReviewIn], themes: list[str]) -> list[RawResult]:
        """Return valid results for the reviews it could analyze; omit the rest."""
        ...
