"""Derive the sentiment label from a 1-5 score."""

from app.schemas import Sentiment


def sentiment_from_score(score: int) -> Sentiment:
    """1-2 negative, 3 neutral, 4-5 positive."""
    if score <= 2:
        return "negative"
    if score == 3:
        return "neutral"
    return "positive"
