import json

import httpx
import pytest

from app.analyzers.jev import JevAnalyzer, score_from_position
from app.openrouter import AnalyzerError
from app.runner import analyze_reviews
from app.schemas import ReviewIn

THEMES = ["food", "service", "other"]


def make_jev(handler, key="k"):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return JevAnalyzer(key, "typesafe/jev-test", client=client)


def answer(score=3.9, theme="food", cost=0.00002):
    body = {
        "model": "typesafe/jev-test-2026",
        "usage": {"cost": cost},
        "answers": {
            "score": {"type": "score", "score": score},
            "theme": {"type": "choice", "choice": theme},
        },
    }
    return httpx.Response(200, json=body)


@pytest.mark.parametrize(
    "position,expected", [(0.0, 1), (0.6, 2), (1.99, 3), (2.4, 3), (3.65, 5), (3.99, 5), (4.0, 5)]
)
def test_score_from_position(position, expected):
    assert score_from_position(position) == expected


async def test_jev_success_and_request_shape():
    seen = []

    def handler(request):
        assert str(request.url).endswith("/api/alpha/decisions")
        seen.append(json.loads(request.content))
        return answer(score=3.99, theme="service")

    jev = make_jev(handler)
    out = await jev.analyze(
        [ReviewIn(id=7, text="Great waiter"), ReviewIn(id=8, text="ok")], THEMES
    )
    assert {r.id for r in out} == {7, 8}
    assert out[0].score == 5 and out[0].theme == "service" and out[0].model.endswith("2026")
    assert jev.total_cost == pytest.approx(0.00004)
    body = seen[0]
    assert body["model"] == "typesafe/jev-test" and body["state"] == {"review": "Great waiter"}
    assert body["questions"]["score"]["type"] == "score"
    assert len(body["questions"]["score"]["criteria"]) == 5
    assert list(body["questions"]["theme"]["criteria"]) == THEMES


async def test_jev_drops_unusable_answers():
    replies = iter(
        [
            answer(theme="parking"),  # theme not in the active list
            httpx.Response(200, json={"answers": {}}),  # wrong shape
            answer(score=0.7, theme="food"),
        ]
    )
    jev = make_jev(lambda r: next(replies))
    batch = [ReviewIn(id=i, text=f"review {i}") for i in range(3)]
    out = await jev.analyze(batch, THEMES)
    assert [r.id for r in out] == [2] and out[0].score == 2
    assert jev.stats.imperfect_calls == 1


async def test_jev_partial_failure_returns_the_rest():
    def handler(request):
        if json.loads(request.content)["state"]["review"] == "bad":
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        return answer()

    out = await make_jev(handler).analyze(
        [ReviewIn(id=0, text="good"), ReviewIn(id=1, text="bad")], THEMES
    )
    assert [r.id for r in out] == [0]


@pytest.mark.parametrize("status,fatal", [(401, True), (402, True), (429, False), (503, False)])
async def test_jev_http_errors_when_every_request_fails(status, fatal):
    jev = make_jev(lambda r: httpx.Response(status, json={"error": {"message": "nope"}}))
    with pytest.raises(AnalyzerError) as e:
        await jev.analyze([ReviewIn(id=0, text="x y")], THEMES)
    assert e.value.fatal is fatal and "nope" in str(e.value)


async def test_jev_fatal_error_wins_over_partial_success():
    def handler(request):
        if json.loads(request.content)["state"]["review"] == "bad":
            return httpx.Response(401, json={"error": {"message": "bad key"}})
        return answer()

    with pytest.raises(AnalyzerError, match="bad key"):
        await make_jev(handler).analyze(
            [ReviewIn(id=0, text="good"), ReviewIn(id=1, text="bad")], THEMES
        )


async def test_jev_missing_key_and_network_error():
    with pytest.raises(AnalyzerError, match="OPENROUTER_API_KEY") as e:
        await make_jev(lambda r: None, key="").analyze([ReviewIn(id=0, text="x y")], THEMES)
    assert e.value.fatal

    def boom(request):
        raise httpx.ConnectError("down")

    with pytest.raises(AnalyzerError) as e:
        await make_jev(boom).analyze([ReviewIn(id=0, text="x y")], THEMES)
    assert e.value.fatal is False


async def test_runner_retries_review_that_failed_once():
    failed_once = set()

    def handler(request):
        text = json.loads(request.content)["state"]["review"]
        if text == "review 2" and text not in failed_once:
            failed_once.add(text)
            return httpx.Response(503, json={"error": {"message": "busy"}})
        return answer()

    reviews = [ReviewIn(id=i, text=f"review {i}") for i in range(4)]
    got = await analyze_reviews(make_jev(handler), reviews, THEMES, backoff=0)
    assert sorted(got) == [0, 1, 2, 3]
