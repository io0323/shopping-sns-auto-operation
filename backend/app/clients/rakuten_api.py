import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SEARCH_ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
RANKING_ENDPOINT = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"

MIN_REQUEST_INTERVAL_SECONDS = 1.1
BACKOFF_SECONDS: tuple[float, ...] = (1.0, 4.0, 16.0)


class RakutenApiError(Exception):
    pass


class RakutenImageUrl(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    image_url: str = Field(alias="imageUrl")


class RakutenItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, coerce_numbers_to_str=True)

    item_code: str = Field(alias="itemCode")
    item_name: str = Field(alias="itemName")
    item_price: int = Field(alias="itemPrice")
    item_url: str = Field(alias="itemUrl")
    affiliate_url: str | None = Field(default=None, alias="affiliateUrl")
    shop_code: str = Field(alias="shopCode")
    shop_name: str = Field(alias="shopName")
    genre_id: str = Field(alias="genreId")
    review_count: int = Field(default=0, alias="reviewCount")
    review_average: float = Field(default=0.0, alias="reviewAverage")
    point_rate: int = Field(default=1, alias="pointRate")
    medium_image_urls: list[RakutenImageUrl] = Field(default_factory=list, alias="mediumImageUrls")
    rank: int | None = Field(default=None, alias="rank")


class _RakutenItemWrapper(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    item: RakutenItem = Field(alias="item")


class _RakutenApiResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[_RakutenItemWrapper] = Field(default_factory=list, alias="items")


class RakutenApiClient:
    def __init__(
        self,
        application_id: str | None = None,
        affiliate_id: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self._application_id = application_id or settings.rakuten_app_id
        self._affiliate_id = affiliate_id or settings.rakuten_affiliate_id
        self._client = client or httpx.Client(timeout=10.0)
        self._last_request_at: float | None = None

    def get_ranking(self, genre_id: str, page: int = 1) -> list[RakutenItem]:
        params = {"genreId": genre_id, "page": page}
        return self._fetch(RANKING_ENDPOINT, params)

    def search_items(
        self, genre_id: str, hits: int = 30, sort: str = "-reviewCount", page: int = 1
    ) -> list[RakutenItem]:
        params = {"genreId": genre_id, "hits": hits, "sort": sort, "page": page}
        return self._fetch(SEARCH_ENDPOINT, params)

    def _fetch(self, url: str, params: dict[str, Any]) -> list[RakutenItem]:
        full_params = {
            **params,
            "applicationId": self._application_id,
            "affiliateId": self._affiliate_id,
            "format": "json",
        }
        response = self._request_with_retry(url, full_params)
        parsed = _RakutenApiResponse.model_validate(response.json())
        return [wrapper.item for wrapper in parsed.items]

    def _request_with_retry(self, url: str, params: dict[str, Any]) -> httpx.Response:
        self._respect_rate_limit()
        attempt = 0
        while True:
            response = self._client.get(url, params=params)
            self._last_request_at = time.monotonic()
            if response.status_code == 200:
                return response

            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= len(BACKOFF_SECONDS):
                    raise RakutenApiError(
                        f"rakuten api request failed after retries: status={response.status_code}"
                    )
                logger.warning(
                    "rakuten api request failed, retrying: status=%s attempt=%s",
                    response.status_code,
                    attempt,
                )
                time.sleep(BACKOFF_SECONDS[attempt])
                attempt += 1
                continue

            raise RakutenApiError(
                f"rakuten api request failed: status={response.status_code} body={response.text}"
            )

    def _respect_rate_limit(self) -> None:
        if self._last_request_at is not None:
            elapsed = time.monotonic() - self._last_request_at
            wait_seconds = MIN_REQUEST_INTERVAL_SECONDS - elapsed
            if wait_seconds > 0:
                time.sleep(wait_seconds)
