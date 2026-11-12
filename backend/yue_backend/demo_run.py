from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .adapters.tts import TTSAdapter
from .config import Settings, get_settings
from .demo import build_ten_making_plan
from .packaging import build_package
from .render.timeline import build_timeline
from .render.video import render_video
from .validation import validate_plan


def generate_demo_video(
    settings: Settings | None = None,
    *,
    output_root: Path | None = None,
    progress: bool = True,
) -> dict:
    settings = settings or get_settings()
    plan = build_ten_making_plan()
    validation = validate_plan(plan)
    if not validation.ok:
        raise ValueError("demo plan is invalid: " + "; ".join(validation.errors))

    root = output_root or (settings.data_dir / "courses" / plan.planId / "v1")
    root.mkdir(parents=True, exist_ok=True)
    adapter = TTSAdapter(settings)
    placeholder = False

    narration_dir = root / "narration"
    audio_map: dict[str, Path] = {}
    for index, narration in enumerate(plan.narrations, start=1):
        result = adapter.synthesize(
            narration.text,
            language=narration.language,
            emotion=narration.emotion,
            out_path=narration_dir / f"{narration.id}.wav",
        )
        placeholder = placeholder or result.placeholder
        if progress:
            print(f"[tts {index}/{len(plan.narrations)}] {narration.id} {result.duration_ms}ms")
        audio_map[narration.id] = result.audio_path

    language = "en" if plan.question.subject == "english" else "zh"
    hint_audio: dict[str, Path] = {}
    explanation_audio: dict[str, Path] = {}
    for practice in plan.practice:
        for hint_index, hint in enumerate(practice.hints):
            result = adapter.synthesize(
                hint,
                language=language,
                emotion="explain",
                out_path=root / "audio" / f"{practice.practiceId}-hint-{hint_index}.wav",
            )
            placeholder = placeholder or result.placeholder
            hint_audio[f"{practice.practiceId}:hint:{hint_index}"] = result.audio_path
        result = adapter.synthesize(
            practice.explanation,
            language=language,
            emotion="encourage",
            out_path=root / "audio" / f"{practice.practiceId}-explanation.wav",
        )
        placeholder = placeholder or result.placeholder
        explanation_audio[practice.practiceId] = result.audio_path

    plan.meta.placeholderAudio = placeholder
    plan.meta.createdAt = datetime.now(UTC).isoformat()
    timings = build_timeline(plan, audio_map)

    last_reported = {"percent": -1}

    def _progress(fraction: float) -> None:
        percent = int(fraction * 100)
        if progress and percent >= last_reported["percent"] + 10:
            last_reported["percent"] = percent
            print(f"[render] {percent}%")

    video = render_video(plan, timings, root / "lesson.mp4", progress=_progress)
    package = build_package(
        plan,
        video,
        root / (plan.planId + ".yuepack"),
        hint_audio=hint_audio,
        explanation_audio=explanation_audio,
    )

    (root / "lesson.plan.json").write_text(
        json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    timeline_data = [
        {
            "sceneId": timing.scene.sceneId,
            "narrationId": timing.narration.id,
            "startMs": timing.start_ms,
            "durationMs": timing.duration_ms,
            "narrationStartMs": timing.narration_start_ms,
            "narrationEndMs": timing.narration_end_ms,
            "audio": str(timing.audio_path),
        }
        for timing in timings
    ]
    (root / "timeline.json").write_text(
        json.dumps(timeline_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "placeholderAudio": placeholder,
        "video": str(video.video_path),
        "subtitles": str(video.subtitle_path),
        "poster": str(video.poster_path),
        "package": str(package.package_path),
        "durationMs": video.duration_ms,
        "chapters": video.chapters,
        "media": video.probe,
    }
    (root / "media_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


__all__ = ["generate_demo_video", "get_settings"]
