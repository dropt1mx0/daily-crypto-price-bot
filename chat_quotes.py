"""Parse chat price requests and format CoinPaprika conversions."""

from __future__ import annotations

import re
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from api import CoinPaprikaClient, MarketDataError
from config import ASSETS, MAX_QUOTE_AGE_SECONDS, TIMEZONE_NAME

FIAT_ALIASES = {
    "usd": ("USD", "us dollar"),
    "доллар": ("USD", "us dollar"),
    "доллара": ("USD", "us dollar"),
    "долларов": ("USD", "us dollar"),
    "доллары": ("USD", "us dollar"),
    "долларе": ("USD", "us dollar"),
    "долларах": ("USD", "us dollar"),
    "долларами": ("USD", "us dollar"),
    "долл": ("USD", "us dollar"),
    "бакс": ("USD", "us dollar"),
    "баксы": ("USD", "us dollar"),
    "usdt": ("USDT", "Tether"),
    "tether": ("USDT", "Tether"),
    "тезер": ("USDT", "Tether"),
    "тетер": ("USDT", "Tether"),
    "uah": ("UAH", "гривна"),
    "гривна": ("UAH", "гривна"),
    "гривны": ("UAH", "гривна"),
    "гривне": ("UAH", "гривна"),
    "гривну": ("UAH", "гривна"),
    "гривнах": ("UAH", "гривна"),
    "гривной": ("UAH", "гривна"),
    "грн": ("UAH", "гривна"),
    "rub": ("RUB", "рубль"),
    "руб": ("RUB", "рубль"),
    "рубль": ("RUB", "рубль"),
    "рубля": ("RUB", "рубль"),
    "рублей": ("RUB", "рубль"),
    "рублях": ("RUB", "рубль"),
    "рубле": ("RUB", "рубль"),
    "рублями": ("RUB", "рубль"),
}

ASSET_ALIASES = {
    "BTC": ("bitcoin", "биткоин", "биткоина", "биткоину", "биткоине", "биток", "бтс"),
    "ETH": ("ethereum", "ether", "эфириум", "эфириума", "эфиру", "эфир", "эфира", "эфире", "эф"),
    "SOL": ("solana", "солана", "соланы", "солане", "солану"),
    "XRP": ("ripple", "рипл", "рипла", "иксрп"),
    "BNB": ("binance coin", "binance", "бинанс", "бнб"),
    "DOGE": ("dogecoin", "doge", "догекоин", "догикоин", "доги", "дог"),
    "TRX": ("tron", "trx", "трон", "трона"),
    "ADA": ("cardano", "кардано"),
    "LINK": ("chainlink", "чейнлинк", "линк"),
    "AVAX": ("avalanche", "аваланш", "авакс", "авах"),
    "GRAM": ("gram", "грам", "грама", "грамма", "грамм", "граммов"),
}

STOP_WORDS = {
    "price", "курс", "цена", "цену", "сколько", "стоит", "узнать", "покажи", "дай",
    "how", "much", "is", "the", "of", "in", "to", "for", "convert", "конвертируй",
    "переведи", "перевести", "в", "по", "из", "на", "мне", "пожалуйста", "плиз",
}


@dataclass(frozen=True)
class Mention:
    start: int
    end: int
    kind: str
    value: str


@dataclass(frozen=True)
class ParsedRequest:
    base_query: str
    amount: Decimal
    target_query: str | None
    target_fiat: str | None


def _normal(value: str) -> str:
    return value.casefold().replace("ё", "е").strip()


def _known_asset_mentions(text: str) -> list[Mention]:
    aliases: dict[str, tuple[str, str]] = {}
    for asset in ASSETS:
        aliases[_normal(asset.symbol)] = ("coin", asset.symbol)
        aliases[_normal(asset.name)] = ("coin", asset.symbol)
        for alias in ASSET_ALIASES.get(asset.symbol, ()):
            aliases[_normal(alias)] = ("coin", asset.symbol)
    for alias, (symbol, _) in FIAT_ALIASES.items():
        aliases[_normal(alias)] = ("fiat", symbol)

    candidates: list[Mention] = []
    for alias, (kind, value) in aliases.items():
        pattern = re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.IGNORECASE)
        candidates.extend(
            Mention(match.start(), match.end(), kind, value)
            for match in pattern.finditer(text)
        )

    selected: list[Mention] = []
    for candidate in sorted(candidates, key=lambda item: (item.start, -(item.end - item.start))):
        if any(candidate.start < item.end and candidate.end > item.start for item in selected):
            continue
        selected.append(candidate)
    return sorted(selected, key=lambda item: item.start)


def parse_market_request(text: str) -> tuple[ParsedRequest | None, str | None]:
    """Return a structured request, or a user-facing command error."""
    raw = text.strip()
    is_command = raw.startswith("/")
    command_name = ""
    if is_command:
        first, _, remainder = raw.partition(" ")
        command_name = first.split("@", 1)[0].casefold()
        if command_name not in {"/price", "/convert"}:
            return None, None
        raw = remainder.strip()
        if not raw:
            return None, _usage(command_name)

    amount = Decimal("1")
    amount_match = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s+", raw)
    explicit_amount = amount_match is not None
    if amount_match:
        try:
            amount = Decimal(amount_match.group(1).replace(",", "."))
        except InvalidOperation:
            return None, "Не смог распознать количество монет. Пример: /convert 2 BTC UAH."
        raw = raw[amount_match.end():].strip()
        if not amount.is_finite() or amount <= 0:
            return None, "Количество должно быть больше нуля."

    normalized = _normal(raw)
    mentions = _known_asset_mentions(normalized)
    coin_mentions = [item for item in mentions if item.kind == "coin"]
    fiat_mentions = [item for item in mentions if item.kind == "fiat"]

    # A direct ticker or alias in a group is an intentional, compact query.
    compact = re.sub(r"[^\w]+", "", normalized)
    known_terms = {
        _normal(alias)
        for asset in ASSETS
        for alias in (asset.symbol, asset.name, *ASSET_ALIASES.get(asset.symbol, ()))
    }
    exact_known = compact in known_terms
    has_intent = any(word in normalized.split() for word in STOP_WORDS)
    is_bare_ticker = bool(re.fullmatch(r"[A-Z0-9_-]{2,16}", raw))
    if not is_command and not (
        (coin_mentions and (exact_known or has_intent or explicit_amount or len(coin_mentions) > 1 or fiat_mentions))
        or is_bare_ticker
        or explicit_amount
        or has_intent
    ):
        return None, None

    selected_base = coin_mentions[0].value if coin_mentions else ""
    selected_target = coin_mentions[1].value if len(coin_mentions) > 1 else None
    selected_fiat = fiat_mentions[0].value if fiat_mentions and selected_target is None else None

    if not selected_base:
        cleaned = list(normalized)
        for mention in sorted(mentions, key=lambda item: item.start, reverse=True):
            cleaned[mention.start:mention.end] = " " * (mention.end - mention.start)
        remainder = "".join(cleaned)
        remainder = re.sub(r"[^\w\s-]+", " ", remainder)
        tokens = [
            token for token in remainder.split()
            if token not in STOP_WORDS and not re.fullmatch(r"\d+(?:[.,]\d+)?", token)
        ]
        selected_base = " ".join(tokens).strip()
        if not selected_base and not is_command:
            return None, None

    if command_name == "/convert" and selected_target is None and selected_fiat is None:
        return None, _usage("/convert")

    return ParsedRequest(
        base_query=selected_base,
        amount=amount,
        target_query=selected_target,
        target_fiat=selected_fiat,
    ), None


def _usage(command: str) -> str:
    if command == "/convert":
        return "Пример: /convert 25 GRAM UAH или /convert 0.5 bitcoin eth."
    return "Пример: /price BTC, /price биткоин или /price GRAM UAH."


async def _resolve_coin(query: str, market: CoinPaprikaClient) -> tuple[dict[str, str] | None, str | None]:
    normalized = _normal(query)
    for asset in ASSETS:
        aliases = {asset.symbol, asset.name, *ASSET_ALIASES.get(asset.symbol, ())}
        if normalized in {_normal(alias) for alias in aliases}:
            return {
                "id": asset.coinpaprika_id,
                "name": asset.name,
                "symbol": asset.symbol,
            }, None

    results = await market.search_coins(query)
    exact_symbol = [item for item in results if item.get("symbol", "").casefold() == normalized]
    exact_name = [item for item in results if _normal(item.get("name", "")) == normalized]
    matches = exact_symbol or exact_name
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        choices = ", ".join(f"{item['symbol']} — {item['name']}" for item in matches[:4])
        return None, f"Нашёл несколько монет: {choices}. Уточни тикер или название."
    if len(results) == 1:
        return results[0], None
    if results:
        choices = ", ".join(f"{item['symbol']} — {item['name']}" for item in results[:4])
        return None, f"Неоднозначный запрос. Возможные варианты: {choices}. Уточни тикер."
    return None, f"Не нашёл монету «{query}». Проверь тикер или напиши /price BTC."


async def answer_market_request(text: str, market: CoinPaprikaClient) -> str | None:
    request, parse_error = parse_market_request(text)
    if parse_error:
        return parse_error
    if request is None:
        return None

    try:
        base_coin, error = await _resolve_coin(request.base_query, market)
        if error:
            return error
        if base_coin is None:
            return "Не смог распознать монету. Попробуй /price BTC."

        target_coin: dict[str, str] | None = None
        if request.target_query:
            target_coin, error = await _resolve_coin(request.target_query, market)
            if error:
                return error
            if target_coin is None:
                return "Не смог распознать валюту для конвертации."

        tickers, fetched_at = await market.fetch_chat_tickers()
        base_item = tickers.get(base_coin["id"])
        if base_item is None:
            return f"Для {base_coin['symbol']} сейчас нет котировки."

        base_updated = _parse_timestamp(base_item.get("last_updated"))
        if base_updated is None or _is_stale(base_updated, fetched_at):
            return f"Котировка {base_coin['symbol']} устарела. Попробуй немного позже."

        base_quotes = base_item.get("quotes")
        if not isinstance(base_quotes, dict):
            return f"CoinPaprika не вернул котировки для {base_coin['symbol']}."
        base_usd = _quote_price(base_quotes, "USD")
        if base_usd is None:
            return f"Нет котировки USD для {base_coin['symbol']}."

        values = {
            "USD": _quote_price(base_quotes, "USD"),
            "UAH": _quote_price(base_quotes, "UAH"),
            "RUB": _quote_price(base_quotes, "RUB"),
        }
        btc_item = tickers.get("btc-bitcoin")
        usdt_item = tickers.get("usdt-tether")
        btc_usd = (
            _quote_price(btc_item.get("quotes", {}), "USD")
            if isinstance(btc_item, dict) and _ticker_is_fresh(btc_item, fetched_at)
            else None
        )
        usdt_usd = (
            _quote_price(usdt_item.get("quotes", {}), "USD")
            if isinstance(usdt_item, dict) and _ticker_is_fresh(usdt_item, fetched_at)
            else None
        )
        if btc_usd:
            values["BTC"] = base_usd / btc_usd
        if usdt_usd:
            values["USDT"] = base_usd / usdt_usd

        if request.target_fiat:
            target_currency = request.target_fiat
            target_price = values.get(target_currency)
            if target_price is None:
                return f"Нет курса {target_currency} для {base_coin['symbol']}."
            result = request.amount * target_price
            lines = [
                f"{_format_amount(request.amount)} {base_coin['symbol']} ≈ {_format_value(result, target_currency)} {target_currency}"
            ]
        elif target_coin:
            target_item = tickers.get(target_coin["id"])
            target_quotes = target_item.get("quotes") if isinstance(target_item, dict) else None
            target_usd = _quote_price(target_quotes, "USD") if isinstance(target_quotes, dict) else None
            if isinstance(target_item, dict) and not _ticker_is_fresh(target_item, fetched_at):
                return f"Котировка {target_coin['symbol']} устарела. Попробуй немного позже."
            if target_usd is None or target_usd <= 0:
                return f"Нет котировки USD для {target_coin['symbol']}."
            result = request.amount * base_usd / target_usd
            lines = [
                f"{_format_amount(request.amount)} {base_coin['symbol']} ≈ {_format_value(result, target_coin['symbol'])} {target_coin['symbol']}"
            ]
            for currency in ("USD", "USDT", "UAH", "RUB"):
                unit_price = values.get(currency)
                if unit_price is not None:
                    lines.append(f"{_format_value(request.amount * unit_price, currency)} {currency}")
        else:
            amount = request.amount
            lines = [f"Цена {base_coin['name']} ({base_coin['symbol']}) за {_format_amount(amount)}:"]
            for currency in ("USD", "USDT", "UAH", "RUB", "BTC"):
                unit_price = values.get(currency)
                if unit_price is not None:
                    lines.append(f"{_format_value(amount * unit_price, currency)} {currency}")

        change = _quote_change(base_quotes)
        if change is not None:
            sign = "+" if change > 0 else ""
            lines.append(f"24ч: {sign}{change:.2f}%")
        local_time = fetched_at.astimezone(ZoneInfo(TIMEZONE_NAME)).strftime("%H:%M")
        lines.append(f"Обновлено: {local_time}")
        return "\n".join(lines)
    except MarketDataError as exc:
        return f"Не удалось получить цену: {exc}"


def _quote_price(quotes: object, currency: str) -> Decimal | None:
    if not isinstance(quotes, dict):
        return None
    quote = quotes.get(currency)
    if not isinstance(quote, dict):
        return None
    value = quote.get("price")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        return None
    return result if result.is_finite() and result >= 0 else None


def _quote_change(quotes: object) -> float | None:
    if not isinstance(quotes, dict):
        return None
    usd = quotes.get("USD")
    if not isinstance(usd, dict):
        return None
    change = usd.get("percent_change_24h")
    if not isinstance(change, (int, float)) or isinstance(change, bool):
        return None
    return float(change) if math.isfinite(change) else None


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def _is_stale(updated_at: datetime, fetched_at: datetime) -> bool:
    age = (fetched_at - updated_at).total_seconds()
    return age > MAX_QUOTE_AGE_SECONDS or age < -60


def _ticker_is_fresh(item: dict, fetched_at: datetime) -> bool:
    updated_at = _parse_timestamp(item.get("last_updated"))
    return updated_at is not None and not _is_stale(updated_at, fetched_at)


def _format_amount(value: Decimal) -> str:
    if value == 0:
        return "0"
    for decimals in (8, 10, 12):
        text = f"{value:,.{decimals}f}".rstrip("0").rstrip(".")
        if Decimal(text.replace(",", "")) != 0:
            return text
    return f"{value:,.12f}"


def _format_value(value: Decimal, currency: str) -> str:
    if currency in {"USD", "USDT", "UAH", "RUB"}:
        return f"{value:,.2f}"
    if value == 0:
        return "0"
    for decimals in (8, 10, 12):
        rounded = f"{value:,.{decimals}f}".rstrip("0").rstrip(".")
        if Decimal(rounded.replace(",", "")) != 0:
            return rounded
    return f"{value:,.12f}"
