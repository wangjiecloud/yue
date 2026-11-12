from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1280
HEIGHT = 720
FPS = 30

INK = (43, 45, 66)
MUTED = (108, 112, 134)
PINK = (255, 107, 157)
VIOLET = (108, 92, 231)
YELLOW = (255, 209, 102)
GREEN = (6, 214, 160)
BLUE = (72, 149, 239)
WHITE = (255, 255, 255)
CREAM = (255, 250, 240)
NIGHT = (32, 34, 58)

_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
)


@lru_cache(maxsize=64)
def font(size: int) -> ImageFont.FreeTypeFont:
    last_error: Exception | None = None
    for path in _FONT_CANDIDATES:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except OSError as exc:  # pragma: no cover - platform specific
                last_error = exc
    raise RuntimeError(f"no usable CJK font found: {last_error}")


def text_width(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont) -> float:
    return draw.textlength(text, font=fnt)


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    fnt: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int | None = None,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        if char == "\n":
            lines.append(current)
            current = ""
            continue
        candidate = current + char
        if text_width(draw, candidate, fnt) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = char
    if current or not lines:
        lines.append(current)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and text_width(draw, last + "…", fnt) > max_width:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    fnt: ImageFont.FreeTypeFont,
    xy: tuple[int, int],
    max_width: int,
    *,
    fill=INK,
    line_gap: int = 12,
    max_lines: int | None = None,
    align: str = "left",
) -> int:
    x, y = xy
    lines = wrap_text(draw, text, fnt, max_width, max_lines)
    line_height = fnt.size + line_gap
    for line in lines:
        width = text_width(draw, line, fnt)
        if align == "center":
            draw.text((x + (max_width - width) / 2, y), line, font=fnt, fill=fill)
        elif align == "right":
            draw.text((x + max_width - width, y), line, font=fnt, fill=fill)
        else:
            draw.text((x, y), line, font=fnt, fill=fill)
        y += line_height
    return y


def rounded_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    radius: int = 28,
    fill=WHITE,
    outline=None,
    width: int = 2,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def star_points(cx: float, cy: float, outer: float, inner: float, points: int = 5):
    from math import cos, pi, sin

    result = []
    for index in range(points * 2):
        angle = -pi / 2 + index * pi / points
        radius = outer if index % 2 == 0 else inner
        result.append((cx + cos(angle) * radius, cy + sin(angle) * radius))
    return result


def draw_star(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    radius: float,
    *,
    fill=YELLOW,
    outline=(230, 170, 40),
    width: int = 2,
) -> None:
    draw.polygon(star_points(cx, cy, radius, radius * 0.45), fill=fill, outline=outline)
    draw.line(
        star_points(cx, cy, radius, radius * 0.45) + [star_points(cx, cy, radius, radius * 1.0)[0]],
        fill=outline,
        width=width,
    )


def draw_heart(draw: ImageDraw.ImageDraw, cx: float, cy: float, size: float, fill=PINK) -> None:
    draw.ellipse((cx - size, cy - size * 0.6, cx, cy + size * 0.4), fill=fill)
    draw.ellipse((cx, cy - size * 0.6, cx + size, cy + size * 0.4), fill=fill)
    draw.polygon(
        [(cx - size * 0.95, cy), (cx + size * 0.95, cy), (cx, cy + size * 1.15)], fill=fill
    )


def draw_mascot(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    scale: float = 1.0,
    *,
    wave: float = 0.0,
) -> None:
    """Neutral placeholder companion. Not an imitation of any licensed character."""
    s = scale
    body = (int(x), int(y), int(x + 210 * s), int(y + 170 * s))
    draw.ellipse(body, fill=(255, 226, 240), outline=(222, 170, 200), width=3)
    head_cx, head_cy = x + 155 * s, y + 55 * s + wave * 4
    draw.ellipse(
        (head_cx - 62 * s, head_cy - 55 * s, head_cx + 62 * s, head_cy + 55 * s),
        fill=(255, 240, 248),
        outline=(222, 170, 200),
        width=3,
    )
    draw.polygon(
        [
            (head_cx - 48 * s, head_cy - 42 * s),
            (head_cx - 20 * s, head_cy - 92 * s),
            (head_cx - 2 * s, head_cy - 44 * s),
        ],
        fill=(255, 226, 240),
        outline=(222, 170, 200),
    )
    draw.polygon(
        [
            (head_cx + 12 * s, head_cy - 46 * s),
            (head_cx + 36 * s, head_cy - 90 * s),
            (head_cx + 52 * s, head_cy - 38 * s),
        ],
        fill=(255, 226, 240),
        outline=(222, 170, 200),
    )
    for offset in (-24, 20):
        draw.ellipse(
            (
                head_cx + offset * s - 6 * s,
                head_cy - 6 * s,
                head_cx + offset * s + 6 * s,
                head_cy + 6 * s,
            ),
            fill=NIGHT,
        )
        draw.ellipse(
            (
                head_cx + offset * s - 2 * s,
                head_cy - 3 * s,
                head_cx + offset * s + 2 * s,
                head_cy + 1 * s,
            ),
            fill=WHITE,
        )
    draw.arc(
        (head_cx - 18 * s, head_cy + 10 * s, head_cx + 22 * s, head_cy + 34 * s),
        start=15,
        end=165,
        fill=(120, 80, 100),
        width=max(2, int(3 * s)),
    )
    draw.ellipse(
        (head_cx - 40 * s, head_cy + 12 * s, head_cx - 20 * s, head_cy + 24 * s),
        fill=(255, 180, 200),
    )
    draw.ellipse(
        (head_cx + 20 * s, head_cy + 12 * s, head_cx + 40 * s, head_cy + 24 * s),
        fill=(255, 180, 200),
    )
    draw_star(draw, x + 55 * s, y + 105 * s, 16 * s, fill=YELLOW)


def make_background(accent=VIOLET) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), CREAM)
    draw = ImageDraw.Draw(image)
    top = (238, 246, 255)
    bottom = (248, 241, 255)
    for y in range(HEIGHT):
        ratio = y / (HEIGHT - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line([(0, y), (WIDTH, y)], fill=color)
    draw.ellipse((-160, -190, 360, 250), fill=(224, 238, 255))
    draw.ellipse((980, 520, 1420, 900), fill=(255, 232, 243))
    for cx, cy, radius in ((180, 600, 9), (1130, 140, 7), (1050, 610, 5), (90, 180, 5)):
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=accent)
    return image


def ease_in_out(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
