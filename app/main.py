"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.analyzers.llm import LLMAnalyzer
from app.config import Settings
from app.db import Db
from app.jobs import JobManager
from app.openrouter import OpenRouterClient
from app.routes import files, jobs, reviews, themes
from app.suggester import Suggester


def create_app(settings: Settings | None = None, analyzer=None, suggester=None, **runner_options):
    """Build the app. Pass a fake analyzer/suggester in tests."""
    settings = settings or Settings()
    llm = OpenRouterClient(
        settings.openrouter_api_key,
        settings.openrouter_model,
        settings.openrouter_reasoning or None,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await llm.aclose()

    app = FastAPI(title="Feedback Analyzer", lifespan=lifespan)
    app.state.db = Db(settings.db_path)
    app.state.key_configured = bool(settings.openrouter_api_key)
    app.state.jobs = JobManager(
        analyzer or LLMAnalyzer(llm), suggester or Suggester(llm), **runner_options
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "api_key_configured": app.state.key_configured}

    for module in (files, jobs, reviews, themes):
        app.include_router(module.router)
    return app
