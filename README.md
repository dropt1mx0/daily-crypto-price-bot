# Daily Crypto Price Bot

<p align="center">
  <strong>A Telegram bot for crypto prices, currency conversions, and a daily market snapshot.</strong>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11 or newer"></a>
  <a href="https://core.telegram.org/bots/api"><img src="https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white" alt="Telegram Bot API"></a>
  <a href="https://coinpaprika.com/api/"><img src="https://img.shields.io/badge/Market%20data-CoinPaprika-172B4D" alt="CoinPaprika market data"></a>
  <a href="https://render.com/"><img src="https://img.shields.io/badge/Deploy-Render-46E3B7?logo=render&logoColor=black" alt="Render deployment"></a>
</p>

<p align="center">
  <a href="README_RU.md">Русская версия</a>
</p>

<p align="center">
  <img src="assets/price-card-preview.jpg" alt="Preview of the generated crypto price card with synthetic demo prices" width="420">
</p>

> The preview uses synthetic sample values. It is included to show the layout and is never sent by the bot as a market quote.

## What it does

- Publishes a designed price card for **BTC, ETH, SOL, XRP, BNB, DOGE, TRX, ADA, LINK, AVAX, and GRAM**.
- Replies to ticker and coin-name requests in English and Russian, in private chats and groups.
- Converts crypto amounts to USD, USDT, UAH, and RUB, with BTC equivalents where requested.
- Posts on a daily Kyiv-time schedule or at a configurable interval.
- Supports manual updates from configured Telegram admins.
- Uses CoinPaprika without an API key, plus a short-lived cache for chat lookups.
- Serves `/healthz` for Render health checks and external uptime monitors.

## Try it in Telegram

| Request | Example |
| --- | --- |
| Price by ticker or name | `/price BTC`, `/price bitcoin`, `/price биткоин` |
| Convert an amount | `/convert 25 GRAM UAH` |
| Natural-language lookup | `грам биткоин` |
| Refresh the channel card | `/update` (configured admins only) |

Add the bot to a group to answer recognized price questions. To receive ordinary group messages, turn off Group Privacy Mode for the bot in [@BotFather](https://t.me/BotFather), then remove and re-add it to the group.

## Run locally

You need Python 3.11 or newer.

```bash
git clone https://github.com/dropt1mx0/daily-crypto-price-bot.git
cd daily-crypto-price-bot
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env
```

Edit `.env` and set the Telegram values:

```dotenv
TELEGRAM_BOT_TOKEN=replace-with-your-bot-token
TELEGRAM_CHANNEL_ID=@your_channel
TELEGRAM_ADMIN_USER_IDS=123456789
```

Add the bot to the target channel and grant it permission to post. Start it with:

```bash
python main.py
```

Send `/start` to the bot, then use `/update` from an authorized account to publish a card immediately.

## Configuration

| Variable | Required | Default | Description |
| --- | :---: | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Yes | — | Token from [@BotFather](https://t.me/BotFather). |
| `TELEGRAM_CHANNEL_ID` | Yes | — | Channel numeric ID or public `@username`. |
| `TELEGRAM_ADMIN_USER_IDS` | Yes | — | Comma-separated Telegram user IDs allowed to run `/update`. |
| `TIMEZONE` | No | `Europe/Kyiv` | Time zone for the schedule and image footer. |
| `SCHEDULE_MODE` | No | `daily` | `daily` or `interval`. |
| `PUBLISH_TIMES` | No | `23:10` | Comma-separated daily times, for example `09:00,18:30`. |
| `PUBLISH_INTERVAL_MINUTES` | No | — | Interval used when `SCHEDULE_MODE=interval`. |
| `MAX_QUOTE_AGE_SECONDS` | No | `1800` | Reject a card if its market snapshot is older than this. |

The full list of settings is documented in [`.env.example`](.env.example). CoinPaprika API availability and terms can change; check the provider's [API plans](https://coinpaprika.com/api/) before using the bot beyond personal use.

## Deploy on Render

The included [`render.yaml`](render.yaml) defines a Free Python web service. Connect this repository in Render as a Blueprint, then add the three required Telegram variables in the service's **Environment** settings. Keep all tokens out of Git and screenshots.

The bot uses Telegram long polling for updates. A small HTTP server exposes `GET /healthz` so Render can check that the process is responding. An external monitor can request this endpoint periodically to reduce idle spin-downs on Render Free. Render may still restart a service, and its free filesystem is temporary, so the local SQLite publication ledger is not durable across all restarts. Check the current [Render Free plan details](https://render.com/docs/free) for workspace limits and behavior.

## Preview the card renderer

With dependencies installed, run:

```bash
python image_generator.py
```

This writes `output/demo_preview.png` from synthetic quotes. It does not call the market API, start the Telegram bot, or publish to a channel.

## Project map

| File | Purpose |
| --- | --- |
| `main.py` | Application entry point. |
| `telegram_bot.py` | Telegram commands, group lookups, channel publishing, and health-server lifecycle. |
| `api.py` | CoinPaprika requests, snapshot validation, and market-data cache. |
| `chat_quotes.py` | English/Russian aliases, query parsing, conversion, and response formatting. |
| `image_generator.py` | Price-card rendering and synthetic preview generation. |
| `scheduler.py` | Daily or interval-based publishing schedule. |
| `publication_ledger.py` | SQLite duplicate-publication tracking. |
| `config.py` | Asset list, paths, colors, and image layout. |
| `assets/` | Banner template and round-cropped coin logos. |

## Data and limitations

- A card is generated only when every configured asset has a valid, fresh quote and 24-hour change.
- Prices in the banner are shown in USD. Chat conversions use provider quotes and derived BTC/USDT equivalents.
- SQLite state and local logs are runtime data; they are excluded from the repository.
- CoinPaprika's terms and permitted use depend on its current plan. Review the provider's terms before redistributing market data publicly.

## Русский

Описание и запуск на русском языке: [`README_RU.md`](README_RU.md).
