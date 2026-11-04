from fastapi import APIRouter, Form, HTTPException, UploadFile

from app.ingest import InputError, parse_file

router = APIRouter()


@router.post("/files/parse")
async def parse_upload(file: UploadFile, column: str | None = Form(None)):
    """Turn an uploaded file into reviews, or ask which column holds them."""
    try:
        parsed = parse_file(file.filename or "", await file.read(), column or None)
    except InputError as e:
        raise HTTPException(422, str(e)) from None
    return {"reviews": parsed.reviews, "columns": parsed.columns}
