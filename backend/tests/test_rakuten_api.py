from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from app.clients.rakuten_api import (
    RANKING_ENDPOINT,
    SEARCH_ENDPOINT,
    RakutenApiClient,
    RakutenApiError,
)

RANKING_ITEM = {
    "rank": 3,
    "itemCode": "shop1:0001",
    "itemName": "テスト商品",
    "itemPrice": 1980,
    "itemUrl": "https://item.rakuten.co.jp/shop1/0001/",
    "affiliateUrl": "https://hb.afl.rakuten.co.jp/xxx",
    "shopCode": "shop1",
    "shopName": "テストショップ",
    "genreId": 100227,
    "reviewCount": 120,
    "reviewAverage": 4.32,
    "pointRate": 1,
    "mediumImageUrls": [{"imageUrl": "https://image.example/1.jpg"}],
}

RANKING_PAYLOAD = {"items": [{"item": RANKING_ITEM}]}


def _fake_response(status_code: int, payload: dict | None = None) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = payload or {}
    response.text = str(payload)
    return response


def _build_client() -> RakutenApiClient:
    return RakutenApiClient(
        application_id="app-id", affiliate_id="aff-id", client=MagicMock(spec=httpx.Client)
    )


def test_get_ranking_parses_items_and_sends_credentials() -> None:
    client = _build_client()
    client._client.get.return_value = _fake_response(200, RANKING_PAYLOAD)

    with patch("app.clients.rakuten_api.time.sleep"):
        items = client.get_ranking(genre_id="100227")

    assert len(items) == 1
    item = items[0]
    assert item.item_code == "shop1:0001"
    assert item.item_price == 1980
    assert item.genre_id == "100227"
    assert item.rank == 3
    assert item.affiliate_url == "https://hb.afl.rakuten.co.jp/xxx"
    assert item.medium_image_urls[0].image_url == "https://image.example/1.jpg"

    call_args = client._client.get.call_args
    assert call_args.args[0] == RANKING_ENDPOINT
    params = call_args.kwargs["params"]
    assert params["applicationId"] == "app-id"
    assert params["affiliateId"] == "aff-id"
    assert params["genreId"] == "100227"


def test_search_items_hits_search_endpoint_and_allows_missing_rank() -> None:
    client = _build_client()
    item_without_rank = {k: v for k, v in RANKING_ITEM.items() if k != "rank"}
    client._client.get.return_value = _fake_response(200, {"items": [{"item": item_without_rank}]})

    with patch("app.clients.rakuten_api.time.sleep"):
        items = client.search_items(genre_id="100227")

    assert items[0].rank is None
    assert client._client.get.call_args.args[0] == SEARCH_ENDPOINT


def test_waits_between_requests_when_called_too_soon() -> None:
    client = _build_client()
    client._client.get.return_value = _fake_response(200, RANKING_PAYLOAD)

    monotonic_values = iter([0.0, 0.5, 1.1])
    with (
        patch("app.clients.rakuten_api.time.monotonic", side_effect=lambda: next(monotonic_values)),
        patch("app.clients.rakuten_api.time.sleep") as mock_sleep,
    ):
        client.get_ranking(genre_id="100227")
        client.get_ranking(genre_id="100227")

    mock_sleep.assert_called_once()
    waited = mock_sleep.call_args.args[0]
    assert waited == pytest.approx(0.6, abs=1e-6)


def test_retries_with_exponential_backoff_on_429_then_succeeds() -> None:
    client = _build_client()
    client._client.get.side_effect = [
        _fake_response(429),
        _fake_response(200, RANKING_PAYLOAD),
    ]

    with (
        patch("app.clients.rakuten_api.time.sleep") as mock_sleep,
        patch("app.clients.rakuten_api.time.monotonic", return_value=0.0),
    ):
        items = client.get_ranking(genre_id="100227")

    assert len(items) == 1
    mock_sleep.assert_called_once_with(1.0)


def test_retries_on_5xx_and_raises_after_exhausting_backoff() -> None:
    client = _build_client()
    client._client.get.return_value = _fake_response(500)

    with (
        patch("app.clients.rakuten_api.time.sleep") as mock_sleep,
        patch("app.clients.rakuten_api.time.monotonic", return_value=0.0),
    ):
        with pytest.raises(RakutenApiError):
            client.get_ranking(genre_id="100227")

    assert mock_sleep.call_args_list == [call(1.0), call(4.0), call(16.0)]
    assert client._client.get.call_count == 4


def test_non_retryable_status_raises_immediately() -> None:
    client = _build_client()
    client._client.get.return_value = _fake_response(400)

    with (
        patch("app.clients.rakuten_api.time.sleep") as mock_sleep,
        patch("app.clients.rakuten_api.time.monotonic", return_value=0.0),
    ):
        with pytest.raises(RakutenApiError):
            client.get_ranking(genre_id="100227")

    mock_sleep.assert_not_called()
    assert client._client.get.call_count == 1
