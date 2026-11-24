"""Aiogram integration, channel publisher, and manual /update command."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from api import CoinPaprikaClient, MarketDataError
from chat_quotes import answer_market_request
from config import (
    ASSETS,
    OUTPUT_IMAGE_PATH,
    PUBLICATION_DB_PATH,
    TELEGRAM_ADMIN_USER_IDS,
    TELEGRAM_CHANNEL_ID,
    TELEGRAM_BOT_TOKEN,
)
from health_server import start_health_server
from image_generator import format_change_number, format_price, render_banner
from publication_ledger import PublicationLedger
from scheduler import create_scheduler

logger = logging.getLogger(__name__)


class Publisher:
    def __init__(self, market: CoinPaprikaClient, bot: Bot) -> None:
        self.market = market
        self.bot = bot
        self.ledger = PublicationLedger(PUBLICATION_DB_PATH)
        self._lock = asyncio.Lock()

    async def publish(self, origin: str, schedule_key: str | None = None) -> str:
        async with self._lock:
            try:
                quotes, fetched_at = await self.market.fetch_quotes()
                publication_key = (
                    f"scheduled:{schedule_key}"
                    if origin == "scheduled" and schedule_key
                    else f"manual:{_quote_fingerprint(quotes)}"
                )
                if self.ledger.was_published(publication_key):
                    logger.info("Skipped duplicate %s publication (%s)", origin, publication_key)
                    return "duplicate"

                image_path = render_banner(quotes, fetched_at, OUTPUT_IMAGE_PATH)
                message = await self.bot.send_photo(
                    chat_id=TELEGRAM_CHANNEL_ID,
                    photo=FSInputFile(image_path),
                )
                self.ledger.mark_published(publication_key, message.message_id)
                logger.info("Published %s snapshot as Telegram message %s", origin, message.message_id)
                return "published"
            except (MarketDataError, TelegramAPIError, OSError, ValueError):
                logger.exception("Could not publish %s crypto snapshot", origin)
                return "failed"


def _quote_fingerprint(quotes: dict) -> str:
    snapshot = [
        (
            asset.symbol,
            format_price(quotes[asset.symbol].price_usd),
            format_change_number(quotes[asset.symbol].change_24h),
            1 if quotes[asset.symbol].change_24h > 0 else -1 if quotes[asset.symbol].change_24h < 0 else 0,
        )
        for asset in ASSETS
    ]
    encoded = json.dumps(snapshot, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_dispatcher(publisher: Publisher) -> Dispatcher:
    router = Router()

    @router.message(Command("start"))
    async def start_command(message: Message) -> None:
        await message.answer(
            "Crypto Price Bot is running.\n"
            "Price: /price BTC or /price биткоин\n"
            "Convert: /convert 25 GRAM UAH\n"
            "You can also write a query like «грам биткоин».\n"
            "Channel update: /update"
        )

    @router.message(Command("update"))
    async def update_command(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else None
        if not TELEGRAM_ADMIN_USER_IDS or user_id not in TELEGRAM_ADMIN_USER_IDS:
            await message.answer("This command is limited to configured bot administrators.")
            return
        await message.answer("Fetching the latest quotes and publishing…")
        result = await publisher.publish(origin="manual")
        replies = {
            "published": "The market snapshot was published to the channel.",
            "duplicate": "This exact quote snapshot was already published.",
            "failed": "The update failed. Check the bot log for details.",
        }
        await message.answer(replies[result])

    @router.message(F.text)
    async def price_query(message: Message) -> None:
        if not message.text:
            return
        answer = await answer_market_request(message.text, publisher.market)
        if answer:
            await message.answer(answer)

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


async def run_bot() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    if not TELEGRAM_CHANNEL_ID:
        raise RuntimeError("TELEGRAM_CHANNEL_ID is required")

    market = CoinPaprikaClient()
    async with Bot(token=TELEGRAM_BOT_TOKEN) as bot:
        publisher = Publisher(market, bot)
        dispatcher = create_dispatcher(publisher)
        scheduler = create_scheduler(publisher)
        health_runner = None
        try:
            if os.getenv("RENDER") or os.getenv("PORT"):
                health_runner = await start_health_server()
            scheduler.start()
            await dispatcher.start_polling(bot)
        finally:
            if scheduler.running:
                scheduler.shutdown(wait=False)
            if health_runner is not None:
                await health_runner.cleanup()
            await market.close()
