from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from ..models import NarrationSegment, Scene, TeachingPlan
from .theme import (
    BLUE,
    GREEN,
    HEIGHT,
    INK,
    MUTED,
    PINK,
    VIOLET,
    WHITE,
    WIDTH,
    YELLOW,
    clamp,
    draw_mascot,
    draw_star,
    draw_text_block,
    ease_in_out,
    font,
    make_background,
    rounded_card,
    text_width,
    wrap_text,
)

SUBJECT_LABEL = {"math": "数学", "chinese": "语文", "english": "英语"}
GRADE_LABEL = {1: "一年级", 2: "二年级", 3: "三年级"}


@dataclass
class SceneContext:
    plan: TeachingPlan
    scene: Scene
    narration: NarrationSegment
    duration_ms: int
    chapter_title: str


def _header(draw: ImageDraw.ImageDraw, ctx: SceneContext) -> None:
    chapter_font = font(24)
    label = ctx.chapter_title
    width = text_width(draw, label, chapter_font) + 48
    rounded_card(
        draw, (64, 36, 64 + int(width), 84), radius=24, fill=(238, 233, 255), outline=VIOLET
    )
    draw.text((88, 46), label, font=chapter_font, fill=VIOLET)

    meta_font = font(22)
    meta = f"{GRADE_LABEL.get(ctx.plan.question.grade, '')} · {SUBJECT_LABEL.get(ctx.plan.question.subject, '')}"
    meta_width = text_width(draw, meta, meta_font)
    draw.text((WIDTH - 72 - meta_width, 48), meta, font=meta_font, fill=MUTED)

    tag_font = font(20)
    draw.rounded_rectangle(
        (WIDTH - 72 - meta_width - 190, 40, WIDTH - 72 - meta_width - 24, 80),
        radius=20,
        fill=(255, 243, 214),
    )
    draw.text((WIDTH - 72 - meta_width - 172, 47), "教学旁白", font=tag_font, fill=(160, 110, 20))


def _subtitle(draw: ImageDraw.ImageDraw, ctx: SceneContext, image: Image.Image) -> None:
    text = ctx.narration.text
    subtitle_font = font(31)
    lines = wrap_text(draw, text, subtitle_font, 1090, max_lines=2)
    box_height = 34 + len(lines) * 44
    top = HEIGHT - 28 - box_height
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle(
        (72, top, WIDTH - 72, HEIGHT - 20), radius=22, fill=(28, 30, 48, 205)
    )
    image.alpha_composite(overlay) if image.mode == "RGBA" else image.paste(
        Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    )
    y = top + 16
    for line in lines:
        width = text_width(draw, line, subtitle_font)
        draw.text(((WIDTH - width) / 2, y), line, font=subtitle_font, fill=WHITE)
        y += 44


def _sparkles(draw: ImageDraw.ImageDraw, t_ms: int, cx: int, cy: int, radius: int) -> None:
    import math

    for index in range(7):
        angle = index * (2 * math.pi / 7) + t_ms / 1800
        pulse = 0.7 + 0.3 * math.sin(t_ms / 320 + index)
        x = cx + math.cos(angle) * radius
        y = cy + math.sin(angle) * radius * 0.6
        draw_star(draw, x, y, 7 * pulse, fill=(255, 236, 160), outline=(240, 190, 60), width=1)


def _render_title(
    draw: ImageDraw.ImageDraw, ctx: SceneContext, t_ms: int, image: Image.Image
) -> None:
    progress = ease_in_out(t_ms / 900)
    mascot_x = int(-240 + progress * 340)
    draw_mascot(draw, mascot_x, 250, 1.15, wave=t_ms / 400)
    _sparkles(draw, t_ms, 1050, 200, 150)

    title_font = font(64)
    title = ctx.scene.title or "小马陪你学数学"
    title_width = text_width(draw, title, title_font)
    x = (WIDTH - title_width) / 2 + 180
    draw.text((x, 240), title, font=title_font, fill=INK)

    stem_font = font(40)
    stem = ctx.plan.question.stem
    lines = wrap_text(draw, stem, stem_font, 760, max_lines=2)
    y = 340
    for line in lines:
        width = text_width(draw, line, stem_font)
        draw.text((x + 10 + (700 - width) / 2, y), line, font=stem_font, fill=VIOLET)
        y += 58

    chip_font = font(26)
    chip = f"{GRADE_LABEL.get(ctx.plan.question.grade, '')} · {SUBJECT_LABEL.get(ctx.plan.question.subject, '')}"
    chip_width = text_width(draw, chip, chip_font)
    rounded_card(
        draw,
        (int(WIDTH - 220 - chip_width), 500, WIDTH - 180, 556),
        radius=26,
        fill=(232, 255, 245),
        outline=GREEN,
    )
    draw.text((WIDTH - 200 - chip_width, 514), chip, font=chip_font, fill=(8, 130, 100))


def _draw_counter_group(
    draw: ImageDraw.ImageDraw,
    positions: list[tuple[int, int]],
    radius: int,
    *,
    color=YELLOW,
    outline=(226, 166, 32),
) -> None:
    for cx, cy in positions:
        draw_star(draw, cx, cy, radius, fill=color, outline=outline)


def _render_question(
    draw: ImageDraw.ImageDraw, ctx: SceneContext, t_ms: int, image: Image.Image
) -> None:
    rounded_card(
        draw, (110, 150, WIDTH - 110, 570), radius=36, fill=WHITE, outline=(226, 232, 245), width=3
    )
    stem_font = font(52)
    lines = wrap_text(draw, ctx.plan.question.stem, stem_font, 940, max_lines=2)
    y = 200
    for line in lines:
        width = text_width(draw, line, stem_font)
        draw.text(((WIDTH - width) / 2, y), line, font=stem_font, fill=INK)
        y += 70

    arithmetic = ctx.plan.question.arithmetic
    if arithmetic and arithmetic[0].op == "+" and arithmetic[0].a <= 10 and arithmetic[0].b <= 10:
        fact = arithmetic[0]
        appear_a = _stars_visible(fact.a, t_ms, 200, 900)
        appear_b = _stars_visible(fact.b, t_ms, 1100, 900)
        _counter_row(draw, appear_a, 360, 380, "先数一数", VIOLET)
        _counter_row(draw, appear_b, 820, 380, "再数一数", BLUE)
        draw.text((570, 380), "+", font=font(56), fill=MUTED)
        draw.text((1010, 380), "= ?", font=font(56), fill=PINK)
    draw_text_block(
        draw,
        "看一看题目，想一想可以怎样算。",
        font(28),
        (190, 505),
        900,
        fill=MUTED,
        align="center",
    )


def _stars_visible(count: int, t_ms: int, start_ms: int, window_ms: int) -> int:
    if count <= 0 or t_ms <= start_ms:
        return 0
    if t_ms >= start_ms + window_ms:
        return count
    return min(count, int(count * (t_ms - start_ms) / window_ms) + 1)


def _counter_row(draw: ImageDraw.ImageDraw, count: int, x: int, y: int, label: str, color) -> None:
    label_font = font(24)
    draw.text((x, y - 50), f"{label}：{count} 颗", font=label_font, fill=color)
    per_row = 5
    radius = 15
    for index in range(count):
        row = index // per_row
        col = index % per_row
        draw_star(draw, x + 18 + col * 42, y + 20 + row * 44, radius, fill=YELLOW)


def _ten_frame_layout():
    cell = 78
    gap = 8
    left = 250
    top = 250
    positions = []
    for index in range(10):
        row = index // 5
        col = index % 5
        positions.append((left + col * (cell + gap), top + row * (cell + gap)))
    return cell, gap, positions


def _right_group_positions(count: int, cell: int, gap: int):
    left = 790
    top = 238
    positions = []
    per_row = 5
    for index in range(count):
        row = index // per_row
        col = index % per_row
        positions.append((left + col * (cell + gap), top + row * (cell + gap)))
    return positions


def _render_ten_frame(
    draw: ImageDraw.ImageDraw, ctx: SceneContext, t_ms: int, image: Image.Image
) -> None:
    operands = ctx.scene.operands or [0, 0]
    a, b = operands
    need = max(0, 10 - a)
    moving = min(need, b)
    remainder = b - moving

    duration = max(ctx.duration_ms, 1)
    highlight_start = 0.20 * duration
    move_start = 0.36 * duration
    move_end = 0.70 * duration
    progress = clamp((t_ms - move_start) / max(1.0, move_end - move_start), 0.0, 1.0)
    eased = ease_in_out(progress)

    cell, gap, frame_positions = _ten_frame_layout()
    right_positions = _right_group_positions(b, cell, gap)

    rounded_card(
        draw, (120, 140, WIDTH - 120, 580), radius=36, fill=WHITE, outline=(226, 232, 245), width=3
    )

    title_font = font(30)
    draw.text((170, 168), "凑十法：先凑成 10，再加剩下的", font=title_font, fill=INK)

    for index, (x, y) in enumerate(frame_positions):
        fill = (245, 248, 255) if index >= a else (238, 246, 255)
        draw.rounded_rectangle(
            (x, y, x + cell, y + cell), radius=14, fill=fill, outline=(170, 190, 230), width=2
        )

    for index in range(min(a, 10)):
        x, y = frame_positions[index]
        draw_star(draw, x + cell / 2, y + cell / 2, cell * 0.34)

    for index, (x, y) in enumerate(right_positions):
        cx, cy = x + cell / 2, y + cell / 2
        if index < moving and progress <= 0:
            pass
        if index < moving:
            if highlight_start <= t_ms < move_start:
                pulse = 1.0 + 0.08 * abs(__import__("math").sin((t_ms - highlight_start) / 140))
                draw.ellipse(
                    (cx - 30 * pulse, cy - 30 * pulse, cx + 30 * pulse, cy + 30 * pulse),
                    outline=PINK,
                    width=4,
                )
            if t_ms >= move_start:
                target_x, target_y = frame_positions[a + index]
                tx = target_x + cell / 2
                ty = target_y + cell / 2
                cx = cx + (tx - cx) * eased
                cy = cy + (ty - cy) * eased
                draw_star(draw, cx, cy, cell * 0.34, fill=(255, 220, 120))
                continue
        draw_star(draw, cx, cy, cell * 0.34)

    draw.text((200, 470), f"左边有 {a} 颗", font=font(26), fill=VIOLET)
    draw.text((790, 470), f"右边有 {b} 颗", font=font(26), fill=BLUE)

    if t_ms < move_start:
        hint = f"从 {b} 颗里拿 {moving} 颗，放进十格"
    elif t_ms < move_end:
        hint = f"{a} + {moving} = 10"
    else:
        hint = f"10 + {remainder} = {a + b}"
    badge_font = font(34)
    width = text_width(draw, hint, badge_font)
    rounded_card(
        draw,
        (int((WIDTH - width) / 2 - 28), 495, int((WIDTH + width) / 2 + 28), 556),
        radius=26,
        fill=(255, 243, 214),
        outline=(240, 190, 70),
    )
    draw.text(((WIDTH - width) / 2, 508), hint, font=badge_font, fill=(150, 100, 20))

    if t_ms >= move_end:
        draw_star(draw, WIDTH - 190, 180, 26, fill=GREEN, outline=(6, 150, 110))


def _render_summary(
    draw: ImageDraw.ImageDraw, ctx: SceneContext, t_ms: int, image: Image.Image
) -> None:
    rounded_card(
        draw, (140, 140, WIDTH - 140, 570), radius=36, fill=WHITE, outline=(226, 232, 245), width=3
    )
    title_font = font(36)
    draw.text((190, 170), ctx.scene.title or "一起总结", font=title_font, fill=INK)

    expressions = ctx.scene.expressions or [
        step.expression for step in ctx.plan.solution.steps if step.expression
    ]
    if not expressions:
        expressions = [ctx.plan.solution.finalAnswer]
    duration = max(ctx.duration_ms, 1)
    row_font = font(46)
    y = 250
    for index, expression in enumerate(expressions[:4]):
        appear = 0.10 + index * (0.55 / max(1, min(len(expressions), 4)))
        if t_ms / duration < appear:
            continue
        is_final = index == len(expressions[:4]) - 1
        box_fill = (255, 243, 214) if is_final else (244, 248, 255)
        outline = (240, 190, 70) if is_final else (200, 214, 240)
        rounded_card(draw, (210, y, WIDTH - 210, y + 72), radius=20, fill=box_fill, outline=outline)
        width = text_width(draw, expression, row_font)
        draw.text(
            ((WIDTH - width) / 2, y + 10),
            expression,
            font=row_font,
            fill=(150, 100, 20) if is_final else INK,
        )
        draw_star(draw, WIDTH - 255, y + 36, 18, fill=GREEN if is_final else YELLOW)
        y += 82


def _render_closing(
    draw: ImageDraw.ImageDraw, ctx: SceneContext, t_ms: int, image: Image.Image
) -> None:
    _sparkles(draw, t_ms, WIDTH // 2, 210, 260)
    draw_mascot(draw, 220, 280, 1.1, wave=t_ms / 350)
    title_font = font(64)
    title = ctx.scene.title or "你学会啦！"
    width = text_width(draw, title, title_font)
    draw.text(((WIDTH + 120 - width) / 2, 300), title, font=title_font, fill=INK)
    text_font = font(34)
    subtitle = ctx.scene.text or "记住：先凑十，再加剩下的。"
    lines = wrap_text(draw, subtitle, text_font, 700, max_lines=2)
    y = 400
    for line in lines:
        line_width = text_width(draw, line, text_font)
        draw.text(((WIDTH + 120 - line_width) / 2, y), line, font=text_font, fill=VIOLET)
        y += 48
    for index in range(3):
        draw_star(
            draw,
            660 + index * 90,
            530,
            24 + 3 * __import__("math").sin(t_ms / 260 + index),
            fill=YELLOW,
        )


def _render_word_pair(
    draw: ImageDraw.ImageDraw, ctx: SceneContext, t_ms: int, image: Image.Image
) -> None:
    rounded_card(
        draw, (130, 140, WIDTH - 130, 570), radius=36, fill=WHITE, outline=(226, 232, 245), width=3
    )
    title_font = font(34)
    draw.text((180, 170), ctx.scene.title or "词语配对", font=title_font, fill=INK)
    items = ctx.scene.expressions or (ctx.scene.text or "").split("|")
    items = [item.strip() for item in items if item.strip()]
    card_font = font(38)
    columns = 2
    card_w = 420
    card_h = 86
    for index, item in enumerate(items[:8]):
        col = index % columns
        row = index // columns
        x = 230 + col * 480
        y = 260 + row * 110
        appear = index * 0.08
        if t_ms / max(ctx.duration_ms, 1) < appear:
            continue
        rounded_card(
            draw,
            (x, y, x + card_w, y + card_h),
            radius=20,
            fill=(244, 248, 255),
            outline=(200, 214, 240),
        )
        width = text_width(draw, item, card_font)
        draw.text((x + (card_w - width) / 2, y + 18), item, font=card_font, fill=INK)
    draw.text((180, 520), "读一读，找一找它们的关系。", font=font(26), fill=MUTED)


def _render_pinyin(
    draw: ImageDraw.ImageDraw, ctx: SceneContext, t_ms: int, image: Image.Image
) -> None:
    rounded_card(
        draw, (130, 140, WIDTH - 130, 570), radius=36, fill=WHITE, outline=(226, 232, 245), width=3
    )
    draw.text((180, 170), ctx.scene.title or "拼音练习", font=font(34), fill=INK)
    items = ctx.scene.expressions or (ctx.scene.text or "").split("|")
    items = [item.strip() for item in items if item.strip()]
    item_font = font(56)
    rounded_card(draw, (260, 260, WIDTH - 260, 430), radius=28, fill=(232, 255, 245), outline=GREEN)
    line = "   ".join(items[:4]) if items else (ctx.scene.text or "")
    lines = wrap_text(draw, line, item_font, WIDTH - 600, max_lines=2)
    y = 300
    for text_line in lines:
        width = text_width(draw, text_line, item_font)
        draw.text(((WIDTH - width) / 2, y), text_line, font=item_font, fill=(8, 130, 100))
        y += 70
    draw.text((180, 510), "跟着旁白读一读。", font=font(26), fill=MUTED)


class ScenePainter:
    _RENDERERS = {
        "title": _render_title,
        "questionBoard": _render_question,
        "tenFrame": _render_ten_frame,
        "summaryBoard": _render_summary,
        "closing": _render_closing,
        "wordPairBoard": _render_word_pair,
        "pinyinBoard": _render_pinyin,
    }

    def __init__(self, ctx: SceneContext):
        self.ctx = ctx
        self.background = make_background()

    def render(self, t_ms: int) -> Image.Image:
        image = self.background.copy().convert("RGB")
        draw = ImageDraw.Draw(image)
        _header(draw, self.ctx)
        renderer = self._RENDERERS[self.ctx.scene.template]
        renderer(draw, self.ctx, t_ms, image)
        _subtitle(draw, self.ctx, image)
        return image
