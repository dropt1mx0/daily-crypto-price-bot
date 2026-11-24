"""HTTP health endpoint used by Render and an external keep-alive check."""

from __future__ import annotations

import logging
import os

from aiohttp import web

logger = logging.getLogger(__name__)


async def start_health_server() -> web.AppRunner:
    app = web.Application()

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app.router.add_get("/healthz", health)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()

    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logger.info("Health check server listening on port %d", port)
    return runner
