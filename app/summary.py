"""Aggregate analyzed reviews into the summary shown to the owner."""

from collections import Counter

from app.schemas import ReviewResult, Summary

OTHER = "other"


def _top(counter: Counter) -> str | None:
    """Most common theme, ties broken alphabetically, 'other' excluded."""
    ranked = sorted((-n, name) for name, n in counter.items() if name != OTHER)
    return ranked[0][1] if ranked else None


def compute_summary(results: list[ReviewResult]) -> Summary:
    ok = [r for r in results if r.status == "ok"]
    themes = Counter(r.theme for r in ok)
    complaints = Counter(r.theme for r in ok if r.sentiment == "negative")
    if not ok:
        return Summary(
            total=0,
            average_score=None,
            percent_positive=None,
            top_theme=None,
            top_complaint_theme=None,
            theme_counts={},
        )
    positive = sum(1 for r in ok if r.sentiment == "positive")
    return Summary(
        total=len(ok),
        average_score=round(sum(r.score for r in ok) / len(ok), 1),
        percent_positive=round(100 * positive / len(ok)),
        top_theme=_top(themes),
        top_complaint_theme=_top(complaints),
        theme_counts=dict(themes.most_common()),
    )
