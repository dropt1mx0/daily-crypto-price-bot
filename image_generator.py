"""Render the supplied banner template with current quote data."""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import (
    ASSETS,
    ASSETS_DIR,
    BADGE_FIELD,
    BADGE_FONT_SIZE,
    BADGE_HEIGHT,
    BADGE_INSET,
    FONT_PATH,
    FOOTER_PLACEHOLDER_BOX,
    FOOTER_TEXT_BOX,
    FOOTER_TIME_CENTER,
    LOGO_CENTER_X,
    PRICE_FIELD,
    ROW_CENTERS,
    TEMPLATE_PATH,
    TEMPLATE_SIZE,
    TIMEZONE_NAME,
)
from models import Quote

logger = logging.getLogger(__name__)


def format_price(price: float) -> str:
    if price >= 1:
        return f"${price:,.2f}"
    if price >= 0.01:
        return f"${price:.4f}"
    return f"${price:.6f}"


def format_change_number(change: float) -> str:
    magnitude = abs(change)
    if magnitude >= 10_000:
        return f"{magnitude:,.0f}"
    if magnitude >= 1_000:
        return f"{magnitude:.0f}"
    decimals = 2 if magnitude >= 0.1 else 3 if magnitude >= 0.01 else 4
    return f"{magnitude:.{decimals}f}"


def render_banner(
    quotes: dict[str, Quote],
    fetched_at: datetime,
    destination: Path,
) -> Path:
    expected = {asset.symbol for asset in ASSETS}
    missing = expected.difference(quotes)
    if missing:
        raise ValueError("Cannot render an incomplete quote set: " + ", ".join(sorted(missing)))
    if fetched_at.tzinfo is None:
        raise ValueError("fetched_at must be timezone-aware")

    with Image.open(TEMPLATE_PATH) as source:
        canvas = source.convert("RGBA")
    if canvas.size != TEMPLATE_SIZE:
        logger.warning("Template size differs from configured coordinates: %s", canvas.size)
    _draw_asset_icons(canvas)
    draw = ImageDraw.Draw(canvas)

    left, top, right, bottom = PRICE_FIELD
    price_box = (left + 7, top + 5, right - 7, bottom - 5)
    badge_left, badge_top, badge_right, badge_bottom = BADGE_FIELD
    badge_box = (badge_left + 1, badge_top + 1, badge_right - 1, badge_bottom - 1)

    for asset, center_y in zip(ASSETS, ROW_CENTERS, strict=True):
        quote = quotes[asset.symbol]
        price = format_price(quote.price_usd)
        price_font = _fit_font(draw, price, price_box, max_size=29, min_size=13)
        _draw_centered(draw, price, ((price_box[0] + price_box[2]) / 2, center_y), price_font, "white")

        _draw_change_cell(canvas, quote.change_24h, badge_box, center_y)

    _clear_footer_placeholder(canvas)
    draw = ImageDraw.Draw(canvas)
    local_time = fetched_at.astimezone(ZoneInfo(TIMEZONE_NAME)).strftime("%H:%M")
    footer_font = _fit_font(draw, local_time, FOOTER_TEXT_BOX, max_size=30, min_size=16)
    _draw_centered(draw, local_time, FOOTER_TIME_CENTER, footer_font, (25, 25, 25, 255))

    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(destination, "PNG", optimize=True)
    return destination


def _draw_change_cell(
    canvas: Image.Image,
    change: float,
    field: tuple[int, int, int, int],
    center_y: int,
) -> None:
    draw = ImageDraw.Draw(canvas)
    # Nudge the colored cells down slightly so they sit optically in each row.
    center_y += 2
    x0, _, x1, _ = field
    x0 += BADGE_INSET
    x1 -= BADGE_INSET
    y0 = center_y - BADGE_HEIGHT // 2
    y1 = y0 + BADGE_HEIGHT

    if change > 0:
        top_color = (197, 240, 203)
        bottom_color = (135, 213, 150)
        text_color = (24, 76, 39, 255)
        label = f"+{format_change_number(change)}%"
    elif change < 0:
        top_color = (255, 215, 211)
        bottom_color = (239, 151, 146)
        text_color = (112, 37, 37, 255)
        label = f"-{format_change_number(change)}%"
    else:
        # Keep the supplied white cell neutral when the 24-hour change is zero.
        text_color = (36, 36, 36, 255)
        label = "0.00%"
        number_font = _fit_font(
            draw,
            label,
            field,
            max_size=BADGE_FONT_SIZE,
            min_size=18,
        )
        _draw_centered(draw, label, ((field[0] + field[2]) / 2, center_y), number_font, text_color)
        return

    badge = _gradient_pill(x1 - x0, BADGE_HEIGHT, top_color, bottom_color)
    canvas.alpha_composite(badge, (x0, y0))
    draw = ImageDraw.Draw(canvas)
    text_box = (x0 + 4, y0 + 2, x1 - 4, y1 - 2)
    number_font = _fit_font(draw, label, text_box, max_size=BADGE_FONT_SIZE, min_size=18)
    _draw_centered(draw, label, ((x0 + x1) / 2, center_y), number_font, text_color)


def _draw_asset_icons(canvas: Image.Image) -> None:
    """Replace the template's perspective-distorted row logos with clean icons."""
    for asset, center_y in zip(ASSETS, ROW_CENTERS, strict=True):
        icon = _make_asset_icon(asset.symbol)
        canvas.alpha_composite(icon, (LOGO_CENTER_X - icon.width // 2, center_y - icon.height // 2))


def _make_asset_icon(symbol: str) -> Image.Image:
    """Draw a round, anti-aliased token mark at a fixed aspect ratio."""
    scale = 4
    size = 88
    center = size / 2
    tile = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))

    shadow = Image.new("RGBA", tile.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.ellipse(
        (7 * scale, 8 * scale, 81 * scale, 82 * scale),
        fill=(90, 45, 14, 48),
    )
    tile.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3 * scale)))

    draw = ImageDraw.Draw(tile)
    draw.ellipse(
        (5 * scale, 4 * scale, 83 * scale, 82 * scale),
        fill=(255, 250, 249, 255),
        outline=(242, 225, 223, 255),
        width=scale,
    )
    supplied_logo = ASSETS_DIR / "token_logos" / f"{symbol.lower()}.png"
    if supplied_logo.is_file():
        with Image.open(supplied_logo) as source:
            logo = source.convert("RGBA").resize((64 * scale, 64 * scale), Image.Resampling.LANCZOS)
        tile.alpha_composite(logo, (12 * scale, 12 * scale))
        return tile.resize((size, size), Image.Resampling.LANCZOS)

    colors = {
        "BTC": (243, 147, 45, 255),
        "ETH": (79, 95, 158, 255),
        "SOL": (31, 27, 58, 255),
        "XRP": (35, 35, 39, 255),
        "BNB": (244, 185, 34, 255),
        "DOGE": (180, 145, 50, 255),
        "TRX": (224, 39, 54, 255),
        "ADA": (37, 82, 213, 255),
        "LINK": (37, 99, 235, 255),
        "AVAX": (229, 54, 62, 255),
        "GRAM": (42, 151, 231, 255),
    }
    fill = colors.get(symbol, (70, 90, 150, 255))
    draw.ellipse((12 * scale, 12 * scale, 76 * scale, 76 * scale), fill=fill)
    draw.ellipse(
        (12 * scale, 12 * scale, 76 * scale, 76 * scale),
        outline=(255, 255, 255, 62),
        width=scale,
    )
    _draw_token_mark(draw, symbol, center, scale, fill)
    return tile.resize((size, size), Image.Resampling.LANCZOS)


def _draw_token_mark(
    draw: ImageDraw.ImageDraw,
    symbol: str,
    center: float,
    scale: int,
    background: tuple[int, int, int, int],
) -> None:
    """Draw simplified, recognizable token marks using vector-like primitives."""
    white = (255, 255, 255, 255)
    c = center

    def point(x: float, y: float) -> tuple[int, int]:
        return round(x * scale), round(y * scale)

    def polygon(points: list[tuple[float, float]], color: tuple[int, int, int, int]) -> None:
        draw.polygon([point(x, y) for x, y in points], fill=color)

    def line(points: list[tuple[float, float]], color: tuple[int, int, int, int], width: float) -> None:
        draw.line([point(x, y) for x, y in points], fill=color, width=round(width * scale), joint="curve")

    if symbol == "BTC":
        font = _load_font(44 * scale)
        draw.text(point(c, c + 1), "B", font=font, fill=white, anchor="mm")
        line([(c - 9, 27), (c - 9, 61)], white, 2.2)
        line([(c - 5, 27), (c - 5, 61)], white, 2.2)
    elif symbol == "ETH":
        polygon([(c, 22), (c - 13, 43), (c, 50)], (239, 242, 255, 255))
        polygon([(c, 22), (c, 50), (c + 13, 43)], (181, 192, 230, 255))
        polygon([(c - 13, 46), (c, 54), (c, 66)], (204, 212, 239, 255))
        polygon([(c, 54), (c + 13, 46), (c, 66)], (148, 162, 211, 255))
    elif symbol == "SOL":
        polygon([(31, 30), (59, 30), (54, 36), (26, 36)], (154, 244, 220, 255))
        polygon([(31, 41), (59, 41), (53, 47), (25, 47)], (190, 106, 255, 255))
        polygon([(31, 52), (59, 52), (53, 58), (25, 58)], (35, 210, 232, 255))
    elif symbol == "XRP":
        line([(29, 33), (37, 33), (44, 40), (51, 33), (59, 33)], white, 4)
        line([(29, 55), (37, 55), (44, 48), (51, 55), (59, 55)], white, 4)
    elif symbol == "BNB":
        polygon([(44, 26), (51, 33), (44, 40), (37, 33)], white)
        polygon([(33, 37), (39, 43), (33, 49), (27, 43)], white)
        polygon([(55, 37), (61, 43), (55, 49), (49, 43)], white)
        polygon([(44, 46), (51, 53), (44, 60), (37, 53)], white)
        polygon([(44, 37), (50, 43), (44, 49), (38, 43)], white)
    elif symbol == "DOGE":
        font = _load_font(39 * scale)
        draw.text(point(c, c + 1), "Ð", font=font, fill=white, anchor="mm")
    elif symbol == "TRX":
        polygon([(44, 25), (62, 57), (26, 57)], white)
        polygon([(44, 34), (54, 52), (34, 52)], background)
        line([(44, 26), (44, 57)], white, 2.2)
        line([(34, 35), (54, 35)], white, 2.2)
    elif symbol == "ADA":
        dots = [
            (44, 44, 3.0), (44, 34, 2.0), (44, 54, 2.0), (34, 44, 2.0), (54, 44, 2.0),
            (37, 37, 1.7), (51, 37, 1.7), (37, 51, 1.7), (51, 51, 1.7),
            (44, 27, 1.4), (44, 61, 1.4), (27, 44, 1.4), (61, 44, 1.4),
            (31, 31, 1.2), (57, 31, 1.2), (31, 57, 1.2), (57, 57, 1.2),
        ]
        for x, y, radius in dots:
            px, py = point(x, y)
            r = round(radius * scale)
            draw.ellipse((px - r, py - r, px + r, py + r), fill=white)
    elif symbol == "LINK":
        points = [(44, 27), (59, 35.5), (59, 52.5), (44, 61), (29, 52.5), (29, 35.5), (44, 27)]
        line(points, white, 4.5)
    elif symbol == "AVAX":
        polygon([(44, 27), (62, 59), (50, 59), (44, 48), (38, 59), (26, 59)], white)
        polygon([(44, 40), (48, 48), (40, 48)], background)
    elif symbol == "GRAM":
        polygon(
            [(44, 25), (49, 39), (63, 44), (49, 49), (44, 63), (39, 49), (25, 44), (39, 39)],
            white,
        )


def _gradient_pill(
    width: int,
    height: int,
    top_color: tuple[int, int, int],
    bottom_color: tuple[int, int, int],
) -> Image.Image:
    """Create a soft color fill that follows the rounded cell shape."""
    gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = gradient.load()
    for y in range(height):
        fraction = y / max(1, height - 1)
        color = tuple(round(top + (bottom - top) * fraction) for top, bottom in zip(top_color, bottom_color))
        for x in range(width):
            pixels[x, y] = (*color, 255)

    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=height // 2, fill=255)
    gradient.putalpha(mask)
    return gradient


def _font_candidates() -> list[str]:
    candidates = [
        FONT_PATH,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    return [candidate for candidate in candidates if candidate]


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    *,
    max_size: int,
    min_size: int,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    width, height = box[2] - box[0], box[3] - box[1]
    for size in range(max_size, min_size - 1, -1):
        font = _load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= width and bbox[3] - bbox[1] <= height:
            return font
    return _load_font(min_size)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _font_candidates():
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    center: tuple[float, float],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: str | tuple[int, int, int, int],
    *,
    stroke_width: int = 0,
    stroke_fill: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> None:
    draw.text(
        center,
        text,
        font=font,
        fill=fill,
        anchor="mm",
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )


def _clear_footer_placeholder(canvas: Image.Image) -> None:
    """Replace the printed placeholder with a sampled local background gradient."""
    left, top, right, bottom = FOOTER_PLACEHOLDER_BOX
    pixels = canvas.load()
    width, height = canvas.size
    for y in range(max(0, top), min(height, bottom)):
        left_color = pixels[max(0, left - 3), y]
        right_color = pixels[min(width - 1, right + 3), y]
        for x in range(max(0, left), min(width, right)):
            fraction = (x - left) / max(1, right - left - 1)
            pixels[x, y] = tuple(
                round(a + (b - a) * fraction) for a, b in zip(left_color, right_color, strict=True)
            )


def create_demo_preview(destination: Path | None = None) -> Path:
    """Render visibly synthetic values for local visual inspection only."""
    now = datetime.now(UTC)
    demo_quotes = {
        asset.symbol: Quote(
            symbol=asset.symbol,
            name=asset.name,
            provider_id=asset.coinpaprika_id,
            price_usd=price,
            change_24h=change,
            updated_at=now,
        )
        for asset, (price, change) in zip(
            ASSETS,
            (
                (98_450.25, 2.45),
                (3_420.50, -1.32),
                (185.12, 4.81),
                (2.4102, -0.88),
                (612.75, 0.0),
                (0.1825, 7.02),
                (0.2876, -2.16),
                (0.7354, 0.54),
                (14.82, -0.21),
                (36.42, 3.11),
                (5.24, -0.73),
            ),
            strict=True,
        )
    }
    return render_banner(demo_quotes, now, destination or Path("output/demo_preview.png"))


if __name__ == "__main__":
    path = create_demo_preview()
    print(f"Created synthetic preview (not market data): {path}")
