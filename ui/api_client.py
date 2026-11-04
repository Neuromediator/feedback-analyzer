"""Thin HTTP client for the FastAPI backend."""

import os

import httpx

BASE_URL = os.environ.get("API_URL", "http://localhost:8000")


class ApiError(Exception):
    """An error message that is safe to show to the owner."""


def _request(method: str, path: str, **kwargs):
    try:
        resp = httpx.request(method, BASE_URL + path, timeout=30, **kwargs)
    except httpx.HTTPError:
        raise ApiError(
            f"Cannot reach the API at {BASE_URL}. "
            "Start it with: uv run uvicorn app.main:create_app --factory"
        ) from None
    if resp.status_code >= 400:
        detail = (
            resp.json().get("detail")
            if resp.headers.get("content-type", "").startswith("application/json")
            else None
        )
        raise ApiError(
            detail if isinstance(detail, str) else f"Request failed ({resp.status_code})."
        )
    return resp.json() if resp.content else None


def get_themes() -> list[str]:
    return _request("GET", "/themes")


def add_theme(name: str) -> list[str]:
    return _request("POST", "/themes", json={"name": name})


def parse_file(filename: str, data: bytes, column: str | None = None) -> dict:
    return _request(
        "POST",
        "/files/parse",
        files={"file": (filename, data)},
        data={"column": column} if column else None,
    )


def create_job(reviews: list[str]) -> str:
    return _request("POST", "/jobs", json={"reviews": reviews})["job_id"]


def get_job(job_id: str) -> dict:
    return _request("GET", f"/jobs/{job_id}")


def retry_job(job_id: str) -> dict:
    return _request("POST", f"/jobs/{job_id}/retry")


def save_reviews(items: list[dict]) -> dict:
    return _request("POST", "/reviews", json={"items": items})


def list_reviews(theme: str | None = None) -> list[dict]:
    return _request("GET", "/reviews", params={"theme": theme} if theme else None)


def delete_review(review_id: int) -> None:
    _request("DELETE", f"/reviews/{review_id}")
