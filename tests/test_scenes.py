from pathlib import Path

import pytest

from yue_backend.demo import build_ten_making_plan
from yue_backend.models import NarrationSegment, Scene
from yue_backend.render.scenes import SceneContext, ScenePainter
from yue_backend.render.theme import HEIGHT, WIDTH


def context_for(template: str, plan=None) -> SceneContext:
    plan = plan or build_ten_making_plan()
    scene = next(item for item in plan.scenes if item.template == template)
    narration = next(item for item in plan.narrations if item.id == scene.narrationId)
    return SceneContext(
        plan=plan,
        scene=scene,
        narration=narration,
        duration_ms=4000,
        chapter_title="读题",
    )


@pytest.mark.parametrize(
    "template",
    [
        "title",
        "questionBoard",
        "tenFrame",
        "summaryBoard",
        "closing",
    ],
)
def test_every_template_renders_a_full_frame(template):
    painter = ScenePainter(context_for(template))
    early = painter.render(100)
    late = painter.render(3800)
    for image in (early, late):
        assert image.size == (WIDTH, HEIGHT)
        assert image.mode == "RGB"
    assert list(early.getdata()) != list(late.getdata())


def test_ten_frame_moves_expected_number_of_stars():
    painter = ScenePainter(context_for("tenFrame"))
    start = painter.render(900)
    end = painter.render(3999)
    assert painter.ctx.scene.operands == [8, 5]
    assert start.size == end.size


def test_subtitle_band_is_drawn():
    ctx = context_for("title")
    ctx.narration = NarrationSegment(id="n", text="测试字幕内容", language="zh")
    painter = ScenePainter(ctx)
    image = painter.render(500)
    bottom = image.crop((0, HEIGHT - 120, WIDTH, HEIGHT))
    colors = {color for _, color in bottom.getcolors(maxcolors=100000) or []}
    assert any(sum(color) < 300 for color in colors)


def test_word_pair_and_pinyin_templates_render():
    plan = build_ten_making_plan()
    plan.scenes.append(
        Scene(
            sceneId="s-words",
            template="wordPairBoard",
            narrationId=plan.narrations[0].id,
            chapterId=plan.chapters[0].chapterId,
            title="词语配对",
            expressions=["苹果| apple", "香蕉| banana"],
        )
    )
    plan.scenes.append(
        Scene(
            sceneId="s-pinyin",
            template="pinyinBoard",
            narrationId=plan.narrations[0].id,
            chapterId=plan.chapters[0].chapterId,
            title="拼音练习",
            expressions=["mā", "má"],
        )
    )
    for scene in plan.scenes[-2:]:
        narration = next(item for item in plan.narrations if item.id == scene.narrationId)
        painter = ScenePainter(
            SceneContext(
                plan=plan, scene=scene, narration=narration, duration_ms=3000, chapter_title="练习"
            )
        )
        image = painter.render(1000)
        assert image.size == (WIDTH, HEIGHT)


def test_rendered_frames_are_deterministic(tmp_path: Path):
    painter = ScenePainter(context_for("summaryBoard"))
    first = painter.render(2000)
    second = ScenePainter(context_for("summaryBoard")).render(2000)
    assert first.tobytes() == second.tobytes()
