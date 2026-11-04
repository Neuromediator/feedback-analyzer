"""Batching, concurrency and retry around an Analyzer."""

import asyncio
from collections.abc import Callable

from app.analyzers.base import Analyzer
from app.openrouter import AnalyzerError
from app.schemas import RawResult, ReviewIn


async def analyze_reviews(
    analyzer: Analyzer,
    items: list[ReviewIn],
    themes: list[str],
    *,
    batch_size: int = 25,
    concurrency: int = 4,
    retries: int = 2,
    backoff: float = 1.0,
    on_batch_done: Callable[[int], None] | None = None,
) -> dict[int, RawResult]:
    """Analyze all items; return results by id. Items that never succeed are simply absent.

    Raises AnalyzerError only for fatal errors (bad key, no credits).
    """
    batches = [items[i : i + batch_size] for i in range(0, len(items), batch_size)]
    gate = asyncio.Semaphore(concurrency)
    got: dict[int, RawResult] = {}

    async def run_batch(batch: list[ReviewIn]) -> None:
        async with gate:
            pending = batch
            for attempt in range(retries + 1):
                if attempt:
                    await asyncio.sleep(backoff * 2 ** (attempt - 1))
                try:
                    for result in await analyzer.analyze(pending, themes):
                        got[result.id] = result
                except AnalyzerError as e:
                    if e.fatal:
                        raise
                pending = [r for r in batch if r.id not in got]
                if not pending:
                    break
        if on_batch_done:
            on_batch_done(len(batch))

    try:
        async with asyncio.TaskGroup() as group:
            for batch in batches:
                group.create_task(run_batch(batch))
    except* AnalyzerError as group_error:
        raise group_error.exceptions[0] from None
    return got
