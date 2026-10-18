import httpx
import pytest
import respx

from exceptions import FaceNotDetectedError, MLServiceUnavailableError
from services import cv_client, nlp_client, recsys_client

CV = "http://mock-cv:9999"
NLP = "http://mock-nlp:9999"
RECSYS = "http://mock-recsys:9999"


@pytest.fixture(autouse=True)
def _ml_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "ml_cv_url", CV)
    monkeypatch.setattr(settings, "ml_nlp_url", NLP)
    monkeypatch.setattr(settings, "ml_recsys_url", RECSYS)


@respx.mock
async def test_recsys_list_payload() -> None:
    respx.post(f"{RECSYS}/recommend").respond(json=[{"movie_id": 1, "score": 0.9}])
    assert await recsys_client.get_recommendations([{"movie_id": 2, "score": 4.0}], 5) == [
        {"movie_id": 1, "score": 0.9}
    ]


@respx.mock
@pytest.mark.parametrize("key", ["results", "items"])
async def test_recsys_dict_payload(key: str) -> None:
    respx.post(f"{RECSYS}/recommend").respond(json={key: [{"movie_id": 7}]})
    assert await recsys_client.get_recommendations([], 5) == [{"movie_id": 7}]


@respx.mock
async def test_recsys_unavailable() -> None:
    respx.post(f"{RECSYS}/recommend").respond(status_code=500)
    with pytest.raises(MLServiceUnavailableError):
        await recsys_client.get_recommendations([], 5)


@respx.mock
async def test_recsys_connect_error() -> None:
    respx.post(f"{RECSYS}/recommend").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(MLServiceUnavailableError):
        await recsys_client.get_recommendations([], 5)


@respx.mock
async def test_nlp_search_flattens_filters() -> None:
    route = respx.post(f"{NLP}/search").respond(json={"items": [{"movie_id": 3}]})
    result = await nlp_client.search(
        "heist", 4, {"year_from": 1990, "year_to": None, "min_rating": 3.5, "genres": ["x"]}
    )
    assert result == [{"movie_id": 3}]
    sent = route.calls.last.request.read()
    assert b'"year_from":1990' in sent.replace(b" ", b"")
    assert b"genres" not in sent
    assert b"year_to" not in sent


@respx.mock
async def test_nlp_search_bare_list() -> None:
    respx.post(f"{NLP}/search").respond(json=[{"movie_id": 1}])
    assert await nlp_client.search("x", 1) == [{"movie_id": 1}]


@respx.mock
async def test_nlp_unavailable() -> None:
    respx.post(f"{NLP}/search").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(MLServiceUnavailableError):
        await nlp_client.search("x", 1)


@respx.mock
async def test_cv_detect_emotion() -> None:
    respx.post(f"{CV}/detect").respond(json={"emotion": "happy", "confidence": 0.8})
    assert await cv_client.detect_emotion(b"img") == {"emotion": "happy", "confidence": 0.8}


@respx.mock
@pytest.mark.parametrize(
    "body",
    [
        {"detail": {"code": "FACE_NOT_DETECTED"}},
        {"error": {"code": "FACE_NOT_DETECTED"}},
    ],
)
async def test_cv_face_not_detected(body: dict[str, object]) -> None:
    respx.post(f"{CV}/detect").respond(status_code=422, json=body)
    with pytest.raises(FaceNotDetectedError):
        await cv_client.detect_emotion(b"img")


@respx.mock
async def test_cv_unprocessable_other_reason_is_unavailable() -> None:
    respx.post(f"{CV}/detect").respond(status_code=422, content=b"not json")
    with pytest.raises(MLServiceUnavailableError):
        await cv_client.detect_emotion(b"img")


@respx.mock
async def test_cv_connect_error() -> None:
    respx.post(f"{CV}/detect").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(MLServiceUnavailableError):
        await cv_client.detect_emotion(b"img")
