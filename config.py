"""Project configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # Preview generation can run with Pillow before dependencies are installed.
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

TIMEZONE_NAME = os.getenv("TIMEZONE", "Europe/Kyiv")
COINPAPRIKA_BASE_URL = os.getenv("COINPAPRIKA_BASE_URL", "https://api.coinpaprika.com/v1")
MAX_QUOTE_AGE_SECONDS = int(os.getenv("MAX_QUOTE_AGE_SECONDS", "1800"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
TELEGRAM_ADMIN_USER_IDS = frozenset(
    int(value.strip())
    for value in os.getenv("TELEGRAM_ADMIN_USER_IDS", "").split(",")
    if value.strip()
)

SCHEDULE_MODE = os.getenv("SCHEDULE_MODE", "daily").strip().lower()
PUBLISH_TIMES = tuple(
    value.strip() for value in os.getenv("PUBLISH_TIMES", "09:00").split(",") if value.strip()
)
PUBLISH_INTERVAL_MINUTES = int(os.getenv("PUBLISH_INTERVAL_MINUTES", "60"))

ASSETS_DIR = ROOT_DIR / "assets"
OUTPUT_DIR = ROOT_DIR / "output"
LOGS_DIR = ROOT_DIR / "logs"
STATE_DIR = ROOT_DIR / "state"
TEMPLATE_PATH = ASSETS_DIR / "template.png"
GREEN_BADGE_PATH = ASSETS_DIR / "green_badge.png"
GREEN_BADGE_RGBA_PATH = ASSETS_DIR / "green_badge_rgba.png"
RED_BADGE_PATH = ASSETS_DIR / "red_badge.png"
FONT_PATH = os.getenv("FONT_PATH", "").strip() or None

OUTPUT_IMAGE_PATH = OUTPUT_DIR / "crypto_prices.png"
PUBLICATION_DB_PATH = STATE_DIR / "publication_state.sqlite3"
LOG_PATH = LOGS_DIR / "bot.log"


@dataclass(frozen=True)
class Asset:
    symbol: str
    name: str
    coinpaprika_id: str


# IDs are explicit because ticker symbols are not unique on market-data APIs.
ASSETS = (
    Asset("BTC", "Bitcoin", "btc-bitcoin"),
    Asset("ETH", "Ethereum", "eth-ethereum"),
    Asset("SOL", "Solana", "sol-solana"),
    Asset("XRP", "XRP", "xrp-xrp"),
    Asset("BNB", "BNB", "bnb-binance-coin"),
    Asset("DOGE", "Dogecoin", "doge-dogecoin"),
    Asset("TRX", "TRON", "trx-tron"),
    Asset("ADA", "Cardano", "ada-cardano"),
    Asset("LINK", "Chainlink", "link-chainlink"),
    Asset("AVAX", "Avalanche", "avax-avalanche"),
    Asset("GRAM", "Gram", "toncoin-the-open-network"),
)

# Coordinates are based on the supplied 1219 x 1280 banner. The source file is
# smaller than the 1463 x 1536 size noted in the brief, so the asset's actual
# dimensions are authoritative. All coordinates live here, separate from the
# rendering logic.
TEMPLATE_SIZE = (1219, 1280)
ROW_CENTERS = (349, 424, 496, 567, 637, 706, 775, 844, 912, 981, 1051)
LOGO_CENTER_X = 284
PRICE_FIELD = (585, 319, 858, 381)
BADGE_FIELD = (864, 315, 1028, 382)
BADGE_INSET = 4
BADGE_HEIGHT = 56
BADGE_FONT_SIZE = 23
FOOTER_TIME_CENTER = (749, 1158)
FOOTER_PLACEHOLDER_BOX = (690, 1164, 813, 1175)
FOOTER_TEXT_BOX = (690, 1137, 813, 1183)
