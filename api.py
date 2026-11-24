"""CoinPaprika market-data client with bounded retries and strict validation."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from config import (
    ASSETS,
    COINPAPRIKA_BASE_URL,
    MAX_QUOTE_AGE_SECONDS,
)
from models import Quote

logger = logging.getLogger(__name__)


class MarketDataError(RuntimeError):
    """Raised when market data is missing, invalid, or unavailable."""


class CoinPaprikaClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=COINPAPRIKA_BASE_URL.rstrip("/"),
            headers={"accept": "application/json"},
            timeout=httpx.Timeout(20.0, connect=8.0),
        )
        self._chat_tickers: tuple[datetime, dict[str, dict]] | None = None
        self._chat_tickers_lock = asyncio.Lock()
        self._search_cache: dict[str, tuple[datetime, list[dict[str, str]]]] = {}

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_quotes(self) -> tuple[dict[str, Quote], datetime]:
        response = await self._get_with_retries("/tickers", params={"quotes": "USD"})
        try:
            payload = response.json()
        except ValueError as exc:
            raise MarketDataError("CoinPaprika returned invalid JSON") from exc
        if not isinstance(payload, list):
            raise MarketDataError("CoinPaprika returned an unexpected response format")

        by_id = {item.get("id"): item for item in payload if isinstance(item, dict)}
        missing = [asset for asset in ASSETS if asset.coinpaprika_id not in by_id]
        if missing:
            labels = ", ".join(f"{asset.symbol} ({asset.coinpaprika_id})" for asset in missing)
            raise MarketDataError(f"CoinPaprika has no market data for: {labels}")

        received_at = datetime.now(UTC)
        quotes: dict[str, Quote] = {}
        for asset in ASSETS:
            item = by_id[asset.coinpaprika_id]
            quote_currencies = item.get("quotes")
            usd_quote = quote_currencies.get("USD") if isinstance(quote_currencies, dict) else None
            if not isinstance(usd_quote, dict):
                raise MarketDataError(f"Missing USD market data for {asset.symbol}")
            price = usd_quote.get("price")
            change = usd_quote.get("percent_change_24h")
            updated_at = _parse_timestamp(item.get("last_updated"))
            if not _finite_number(price) or price < 0:
                raise MarketDataError(f"Invalid USD price for {asset.symbol}")
            if not _finite_number(change):
                raise MarketDataError(f"Missing or invalid 24-hour change for {asset.symbol}")
            if updated_at is None:
                raise MarketDataError(f"Missing quote timestamp for {asset.symbol}")
            age_seconds = (received_at - updated_at).total_seconds()
            if age_seconds > MAX_QUOTE_AGE_SECONDS:
                raise MarketDataError(
                    f"Quote for {asset.symbol} is stale ({int(age_seconds)} seconds old)"
                )
            if age_seconds < -60:
                raise MarketDataError(f"Quote timestamp for {asset.symbol} is in the future")

            quotes[asset.symbol] = Quote(
                symbol=asset.symbol,
                name=asset.name,
                provider_id=asset.coinpaprika_id,
                price_usd=float(price),
                change_24h=float(change),
                updated_at=updated_at,
            )

        logger.info("Received %d fresh market quotes from CoinPaprika", len(quotes))
        return quotes, received_at

    async def fetch_chat_tickers(self) -> tuple[dict[str, dict], datetime]:
        """Get fiat quote rows for chat lookups, cached to limit API calls."""
        now = datetime.now(UTC)
        if self._chat_tickers and (now - self._chat_tickers[0]).total_seconds() < 300:
            return self._chat_tickers[1], self._chat_tickers[0]

        async with self._chat_tickers_lock:
            now = datetime.now(UTC)
            if self._chat_tickers and (now - self._chat_tickers[0]).total_seconds() < 300:
                return self._chat_tickers[1], self._chat_tickers[0]

            response = await self._get_with_retries(
                "/tickers", params={"quotes": "USD,UAH,RUB"}
            )
            try:
                payload = response.json()
            except ValueError as exc:
                raise MarketDataError("CoinPaprika returned invalid JSON") from exc
            if not isinstance(payload, list):
                raise MarketDataError("CoinPaprika returned an unexpected response format")

            by_id = {
                item["id"]: item
                for item in payload
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
            fetched_at = datetime.now(UTC)
            self._chat_tickers = (fetched_at, by_id)
            return by_id, fetched_at

    async def search_coins(self, query: str) -> list[dict[str, str]]:
        normalized = query.strip().casefold()
        now = datetime.now(UTC)
        cached = self._search_cache.get(normalized)
        if cached and (now - cached[0]).total_seconds() < 3600:
            return cached[1]

        response = await self._get_with_retries(
            "/search/",
            params={"q": query.strip(), "c": "currencies", "limit": "10"},
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise MarketDataError("CoinPaprika returned invalid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("currencies"), list):
            raise MarketDataError("CoinPaprika returned an unexpected search format")

        currencies = [
            {
                key: item[key]
                for key in ("id", "name", "symbol")
                if isinstance(item.get(key), str)
            }
            for item in payload["currencies"]
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and item.get("is_active") is True
            and isinstance(item.get("name"), str)
            and isinstance(item.get("symbol"), str)
        ]
        self._search_cache[normalized] = (datetime.now(UTC), currencies)
        return currencies

    async def _get_with_retries(
        self, path: str, *, params: dict[str, str], attempts: int = 3
    ) -> httpx.Response:
        for attempt in range(1, attempts + 1):
            try:
                response = await self._client.get(path, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < attempts:
                        delay = _retry_delay(response, attempt)
                        logger.warning(
                            "CoinPaprika returned HTTP %s; retrying in %.1f seconds (%d/%d)",
                            response.status_code,
                            delay,
                            attempt,
                            attempts,
                        )
                        await asyncio.sleep(delay)
                        continue
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                raise MarketDataError(
                    f"CoinPaprika request failed with HTTP {exc.response.status_code}"
                ) from exc
            except httpx.RequestError as exc:
                if attempt == attempts:
                    raise MarketDataError(f"CoinPaprika request failed: {exc}") from exc
                delay = min(2**(attempt - 1), 8)
                logger.warning(
                    "CoinPaprika request error; retrying in %d seconds (%d/%d): %s",
                    delay,
                    attempt,
                    attempts,
                    exc,
                )
                await asyncio.sleep(delay)
        raise MarketDataError("CoinPaprika request failed after retrying")


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("retry-after", "")
    try:
        return max(0.0, min(float(retry_after), 10.0))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(retry_after)
            return max(0.0, min((retry_at - datetime.now(UTC)).total_seconds(), 10.0))
        except (TypeError, ValueError, OverflowError):
            return float(min(2 ** (attempt - 1), 8))
