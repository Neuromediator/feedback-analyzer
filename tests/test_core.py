import pytest

from app.ingest import InputError, clean_reviews, parse_file, text_hash
from app.schemas import ReviewResult
from app.sentiment import sentiment_from_score
from app.summary import compute_summary


@pytest.mark.parametrize(
    "score,label",
    [(1, "negative"), (2, "negative"), (3, "neutral"), (4, "positive"), (5, "positive")],
)
def test_sentiment(score, label):
    assert sentiment_from_score(score) == label


def test_clean_drops_blank_short_and_duplicates():
    c = clean_reviews(["Great food", "", "   ", "x", "great   FOOD", "Slow service"])
    assert c.reviews == ["Great food", "Slow service"]
    assert c.duplicates_removed == 1


def test_clean_truncates_long_review():
    assert len(clean_reviews(["a" * 5000]).reviews[0]) == 2000


def test_clean_empty_raises():
    with pytest.raises(InputError, match="No reviews"):
        clean_reviews(["", "  "])


def test_clean_cap():
    with pytest.raises(InputError, match="Too many reviews: 101"):
        clean_reviews([f"review number {i}" for i in range(101)])
    assert len(clean_reviews([f"review number {i}" for i in range(100)]).reviews) == 100


def test_hash_ignores_case_and_spacing():
    assert text_hash("Good  Food") == text_hash(" good food ")


def test_txt_lines_and_paragraphs():
    assert parse_file("a.txt", b"one review\n\ntwo review\n").reviews == [
        "one review",
        "two review",
    ]
    para = b"first line\nsecond line\n\nanother one\n"
    assert parse_file("a.txt", para).reviews == ["first line second line", "another one"]


def test_csv_autodetects_column_and_handles_newlines():
    data = b'date,rating,Review\n2024-01-01,5,"Great\nfood"\n2024-01-02,1,Cold soup\n'
    assert parse_file("r.csv", data).reviews == ["Great food", "Cold soup"]


def test_csv_ambiguous_returns_columns_then_accepts_choice():
    data = b"a,b\nfirst,second\n"
    assert parse_file("r.csv", data).columns == ["a", "b"]
    assert parse_file("r.csv", data, column="b").reviews == ["second"]


def test_csv_semicolon_and_bom():
    data = "﻿text;stars\nNice place;5\n".encode()
    assert parse_file("r.csv", data).reviews == ["Nice place"]


def test_json_shapes():
    assert parse_file("r.json", b'["a review", "b review"]').reviews == ["a review", "b review"]
    objs = b'[{"stars": 5, "text": "good"}, {"stars": 1, "text": "bad"}]'
    assert parse_file("r.json", objs).reviews == ["good", "bad"]
    wrapped = b'{"business": "x", "reviews": [{"reviewText": "tasty"}]}'
    assert parse_file("r.json", wrapped).reviews == ["tasty"]
    lines = b'{"text": "one"}\n{"text": "two"}\n'
    assert parse_file("r.jsonl", lines).reviews == ["one", "two"]


def test_json_ambiguous_fields():
    assert parse_file("r.json", b'[{"a": "x", "b": "y"}]').columns == ["a", "b"]


@pytest.mark.parametrize(
    "name,data,msg",
    [
        ("r.pdf", b"x", "Unsupported"),
        ("r.txt", b"\xff\xfe\x00", "UTF-8"),
        ("r.json", b"{not json", "not valid JSON"),
        ("r.json", b'{"a": 1}', "Could not find a list"),
        ("r.txt", b"\n\n  \n", "No reviews"),
        ("r.csv", b"", "no header"),
        ("r.txt", b"x" * (5 * 1024 * 1024 + 1), "5 MB"),
    ],
)
def test_bad_files(name, data, msg):
    with pytest.raises(InputError, match=msg):
        parse_file(name, data)


def _ok(i, score, theme):
    from app.sentiment import sentiment_from_score as s

    return ReviewResult(id=i, text="t", status="ok", score=score, sentiment=s(score), theme=theme)


def test_summary():
    results = [
        _ok(0, 1, "wait"),
        _ok(1, 2, "wait"),
        _ok(2, 5, "food"),
        _ok(3, 5, "food"),
        _ok(4, 4, "food"),
        _ok(5, 3, "other"),
        ReviewResult(id=6, text="t", status="failed"),
    ]
    s = compute_summary(results)
    assert s.total == 6
    assert s.average_score == 3.3
    assert s.percent_positive == 50
    assert s.top_theme == "food"
    assert s.top_complaint_theme == "wait"
    assert s.theme_counts == {"food": 3, "wait": 2, "other": 1}


def test_summary_no_complaints_and_ties_and_empty():
    s = compute_summary([_ok(0, 5, "service"), _ok(1, 5, "food")])
    assert s.top_complaint_theme is None
    assert s.top_theme == "food"  # tie broken alphabetically
    empty = compute_summary([])
    assert empty.total == 0 and empty.average_score is None
