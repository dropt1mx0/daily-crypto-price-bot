"""Create a separate RGBA working copy for the RGB green badge."""

from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image

from config import GREEN_BADGE_PATH, GREEN_BADGE_RGBA_PATH, RED_BADGE_PATH, TEMPLATE_PATH


def prepare_green_badge(
    source: Path = GREEN_BADGE_PATH,
    destination: Path = GREEN_BADGE_RGBA_PATH,
    background_threshold: int = 40,
) -> Path:
    """Remove only edge-connected near-black matte pixels, preserving the source.

    The green asset is RGB with a black matte. A flood fill starts at the image
    border and only visits near-black pixels. Dark details enclosed by the badge
    are not touched. Partially covered edge pixels get soft alpha to retain the
    original glow and antialiasing.
    """
    image = Image.open(source).convert("RGB")
    width, height = image.size
    pixels = image.load()
    visited = bytearray(width * height)
    queue: deque[int] = deque()

    def seed(x: int, y: int) -> None:
        index = y * width + x
        if not visited[index] and max(pixels[x, y]) <= background_threshold:
            visited[index] = 1
            queue.append(index)

    for x in range(width):
        seed(x, 0)
        seed(x, height - 1)
    for y in range(height):
        seed(0, y)
        seed(width - 1, y)

    while queue:
        index = queue.popleft()
        x, y = index % width, index // width
        if x > 0:
            seed(x - 1, y)
        if x + 1 < width:
            seed(x + 1, y)
        if y > 0:
            seed(x, y - 1)
        if y + 1 < height:
            seed(x, y + 1)

    rgba = image.convert("RGBA")
    rgba_pixels = rgba.load()
    for index, is_background in enumerate(visited):
        if not is_background:
            continue
        x, y = index % width, index // width
        red, green, blue, _ = rgba_pixels[x, y]
        matte_strength = max(red, green, blue)
        alpha = round(255 * matte_strength / background_threshold)
        if alpha:
            # Undo the black matte on antialiased boundary pixels.
            rgba_pixels[x, y] = (
                min(255, round(red * 255 / alpha)),
                min(255, round(green * 255 / alpha)),
                min(255, round(blue * 255 / alpha)),
                alpha,
            )
        else:
            rgba_pixels[x, y] = (red, green, blue, 0)

    destination.parent.mkdir(parents=True, exist_ok=True)
    rgba.save(destination, "PNG", optimize=True)
    return destination


def inspect_assets() -> list[str]:
    report: list[str] = []
    for path in (TEMPLATE_PATH, GREEN_BADGE_PATH, RED_BADGE_PATH):
        with Image.open(path) as image:
            alpha = image.getchannel("A") if "A" in image.getbands() else None
            transparency = "no alpha channel"
            if alpha is not None:
                lo, hi = alpha.getextrema()
                transparency = f"alpha {lo}..{hi}"
            report.append(f"{path.name}: {image.width}x{image.height}, {image.mode}, {transparency}")
    return report


if __name__ == "__main__":
    print("Asset inspection:")
    for line in inspect_assets():
        print(f"- {line}")
    prepared = prepare_green_badge()
    print(f"- Created working copy: {prepared.relative_to(prepared.parent.parent)}")

