"""Clean review text and parse uploaded files into lists of reviews."""

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass

MAX_REVIEWS = 100
MAX_CHARS = 2000
MIN_CHARS = 2
MAX_FILE_BYTES = 5 * 1024 * 1024
COLUMN_CANDIDATES = ("review", "text", "comment", "content", "body", "review_text", "reviewtext")


class InputError(ValueError):
    """A user-fixable input problem; the message is shown to the owner."""


def squash(text: str) -> str:
    """Collapse all whitespace runs, including line breaks, into single spaces."""
    return " ".join(text.split())


def normalize(text: str) -> str:
    return squash(text).lower()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode()).hexdigest()


@dataclass
class Cleaned:
    reviews: list[str]
    duplicates_removed: int


def clean_reviews(lines: list[str]) -> Cleaned:
    """Drop blanks and duplicates, truncate long reviews, enforce the cap."""
    seen: set[str] = set()
    reviews: list[str] = []
    duplicates = 0
    for line in lines:
        text = squash(line)
        if len(text) < MIN_CHARS:
            continue
        key = normalize(text)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        reviews.append(text[:MAX_CHARS])
    if not reviews:
        raise InputError("No reviews found. Paste at least one review.")
    if len(reviews) > MAX_REVIEWS:
        raise InputError(
            f"Too many reviews: {len(reviews)} after removing duplicates. The limit is {MAX_REVIEWS}."
        )
    return Cleaned(reviews, duplicates)


@dataclass
class Parsed:
    """Either the reviews, or the candidate columns when the review column is ambiguous."""

    reviews: list[str] | None = None
    columns: list[str] | None = None


def parse_file(filename: str, data: bytes, column: str | None = None) -> Parsed:
    """Parse a .txt, .csv, .json or .jsonl upload."""
    if len(data) > MAX_FILE_BYTES:
        raise InputError("The file is larger than 5 MB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputError("The file must be UTF-8 text.") from None
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    parsers = {"txt": _parse_txt, "csv": _parse_csv, "json": _parse_json, "jsonl": _parse_json}
    if ext not in parsers:
        raise InputError("Unsupported file type. Use .txt, .csv or .json.")
    parsed = parsers[ext](text, column)
    if parsed.reviews is not None and not parsed.reviews:
        raise InputError("No reviews found in the file.")
    return parsed


def _parse_txt(text: str, column: str | None) -> Parsed:
    """One review per line, or per paragraph when paragraphs span several lines."""
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    multiline = any(len(p.strip().splitlines()) > 1 for p in paragraphs)
    units = paragraphs if len(paragraphs) > 1 and multiline else text.splitlines()
    return Parsed(reviews=[squash(u) for u in units if u.strip()])


def _pick_column(columns: list[str], requested: str | None) -> str | None:
    if requested:
        if requested not in columns:
            raise InputError(f"Column '{requested}' not found in the file.")
        return requested
    for name in columns:
        if name.strip().lower() in COLUMN_CANDIDATES:
            return name
    return columns[0] if len(columns) == 1 else None


def _parse_csv(text: str, column: str | None) -> Parsed:
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise InputError("The CSV file has no header row.")
    picked = _pick_column(list(reader.fieldnames), column)
    if picked is None:
        return Parsed(columns=list(reader.fieldnames))
    return Parsed(
        reviews=[squash(row[picked]) for row in reader if (row.get(picked) or "").strip()]
    )


def _load_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    except json.JSONDecodeError:
        raise InputError("The file is not valid JSON or JSON Lines.") from None


def _find_list(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    raise InputError("Could not find a list of reviews in the JSON file.")


def _parse_json(text: str, column: str | None) -> Parsed:
    items = _find_list(_load_json(text))
    strings = [squash(i) for i in items if isinstance(i, str) and i.strip()]
    objects = [i for i in items if isinstance(i, dict)]
    if not objects:
        return Parsed(reviews=strings)
    keys = list(objects[0].keys())
    picked = _pick_column(keys, column)
    if picked is None:
        return Parsed(columns=keys)
    values = [o.get(picked) for o in objects]
    return Parsed(reviews=strings + [squash(v) for v in values if isinstance(v, str) and v.strip()])
