"""Shared market quote model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Quote:
    symbol: str
    name: str
    provider_id: str
    price_usd: float
    change_24h: float
    updated_at: datetime
