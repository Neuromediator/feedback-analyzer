from fastapi import APIRouter, HTTPException, Request

from app.schemas import SavedReview, SaveIn

router = APIRouter()


@router.post("/reviews")
def save_reviews(body: SaveIn, request: Request):
    saved, skipped = request.app.state.db.save_reviews(body.items)
    return {"saved": saved, "skipped": skipped}


@router.get("/reviews", response_model=list[SavedReview])
def list_reviews(request: Request, theme: str | None = None):
    return request.app.state.db.list_reviews(theme)


@router.delete("/reviews/{review_id}", status_code=204)
def delete_review(review_id: int, request: Request):
    if not request.app.state.db.delete_review(review_id):
        raise HTTPException(404, "Review not found.")
