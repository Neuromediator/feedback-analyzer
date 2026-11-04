from fastapi import APIRouter, HTTPException, Request

from app.db import ThemeExists
from app.schemas import ThemeIn

router = APIRouter()


@router.get("/themes")
def list_themes(request: Request):
    return request.app.state.db.themes()


@router.post("/themes", status_code=201)
def add_theme(body: ThemeIn, request: Request):
    name = body.name.strip().lower()
    try:
        request.app.state.db.add_theme(name)
    except ThemeExists as e:
        raise HTTPException(409, str(e)) from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return request.app.state.db.themes()
