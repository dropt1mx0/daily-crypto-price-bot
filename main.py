"""Application entry point for Crypto Price Bot."""

from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler

from config import LOG_PATH, LOGS_DIR
from telegram_bot import run_bot


def configure_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = RotatingFileHandler(LOG_PATH, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)


async def main() -> None:
    configure_logging()
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
