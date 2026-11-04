"""In-memory analysis jobs executed in the background."""

import asyncio
import uuid

from app.analyzers.base import Analyzer
from app.openrouter import AnalyzerError
from app.runner import analyze_reviews
from app.schemas import JobOut, ReviewIn, ReviewResult
from app.sentiment import sentiment_from_score
from app.summary import compute_summary


class Job:
    def __init__(self, texts: list[str], themes: list[str], duplicates_removed: int):
        self.id = uuid.uuid4().hex[:12]
        self.themes = themes
        self.duplicates_removed = duplicates_removed
        self.results = [ReviewResult(id=i, text=t) for i, t in enumerate(texts)]
        self.status = "running"
        self.stage = "analyzing"
        self.done = 0
        self.error: str | None = None

    def indices(self, status: str) -> list[int]:
        return [r.id for r in self.results if r.status == status]

    def to_out(self) -> JobOut:
        return JobOut(
            id=self.id,
            status=self.status,
            stage=self.stage,
            total=len(self.results),
            done=self.done,
            failed=len(self.indices("failed")),
            duplicates_removed=self.duplicates_removed,
            error=self.error,
            results=self.results,
            summary=compute_summary(self.results),
        )


class JobManager:
    def __init__(self, analyzer: Analyzer, suggester, **runner_options):
        self.analyzer = analyzer
        self.suggester = suggester
        self.runner_options = runner_options
        self.jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()

    def start(self, texts: list[str], themes: list[str], duplicates_removed: int) -> Job:
        job = Job(texts, themes, duplicates_removed)
        self.jobs[job.id] = job
        self._spawn(job, list(range(len(texts))))
        return job

    def retry(self, job: Job) -> None:
        """Re-run the failed reviews of a finished job."""
        indices = job.indices("failed")
        for i in indices:
            job.results[i] = ReviewResult(id=i, text=job.results[i].text)
        job.status, job.stage, job.error = "running", "analyzing", None
        job.done = len(job.results) - len(indices)
        self._spawn(job, indices)

    def _spawn(self, job: Job, indices: list[int]) -> None:
        task = asyncio.create_task(self._run(job, indices))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, job: Job, indices: list[int]) -> None:
        items = [ReviewIn(id=i, text=job.results[i].text) for i in indices]
        try:
            got = await analyze_reviews(
                self.analyzer,
                items,
                job.themes,
                on_batch_done=lambda n: setattr(job, "done", job.done + n),
                **self.runner_options,
            )
            for i in indices:
                _apply(job, i, got.get(i))
            job.stage = "suggesting"
            await self._add_suggestions(job, indices)
            job.status = "done"
        except AnalyzerError as e:
            job.error, job.status = str(e), "error"
            for i in indices:
                if job.results[i].status == "pending":
                    job.results[i].status = "failed"
            job.done = len(job.results)
        job.stage = "finished"

    async def _add_suggestions(self, job: Job, indices: list[int]) -> None:
        negatives = [
            job.results[i]
            for i in indices
            if job.results[i].status == "ok" and job.results[i].sentiment == "negative"
        ]
        if not negatives:
            return
        found = await self.suggester.suggest([(r.id, r.text, r.theme) for r in negatives])
        for r in negatives:
            r.suggestion = found.get(r.id)


def _apply(job: Job, index: int, raw) -> None:
    result = job.results[index]
    if raw is None:
        result.status = "failed"
        return
    result.status = "ok"
    result.score = raw.score
    result.sentiment = sentiment_from_score(raw.score)
    result.theme = raw.theme
    result.model = raw.model
