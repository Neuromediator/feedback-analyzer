from fastapi import APIRouter, HTTPException, Request

from app.ingest import InputError, clean_reviews
from app.schemas import JobCreate, JobOut

router = APIRouter()


def _get_job(request: Request, job_id: str):
    job = request.app.state.jobs.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")
    return job


@router.post("/jobs", status_code=202)
async def create_job(body: JobCreate, request: Request):
    try:
        cleaned = clean_reviews(body.reviews)
    except InputError as e:
        raise HTTPException(422, str(e)) from None
    state = request.app.state
    job = state.jobs.start(cleaned.reviews, state.db.themes(), cleaned.duplicates_removed)
    return {"job_id": job.id}


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str, request: Request):
    return _get_job(request, job_id).to_out()


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
async def retry_job(job_id: str, request: Request):
    job = _get_job(request, job_id)
    if job.status == "running":
        raise HTTPException(409, "The job is still running.")
    if not job.indices("failed"):
        raise HTTPException(409, "No failed reviews to retry.")
    request.app.state.jobs.retry(job)
    return job.to_out()
