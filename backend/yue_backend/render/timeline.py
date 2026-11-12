from __future__ import annotations

import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

from ..models import NarrationSegment, Scene, TeachingPlan

SAMPLE_RATE = 22050


@dataclass
class NarrationTiming:
    scene: Scene
    narration: NarrationSegment
    chapter_title: str
    audio_path: Path
    audio_duration_ms: int
    start_ms: int
    duration_ms: int
    narration_start_ms: int
    narration_end_ms: int


def _sample_count(ms: int, rate: int = SAMPLE_RATE) -> int:
    return int(round(ms * rate / 1000))


def build_timeline(
    plan: TeachingPlan,
    audio_map: dict[str, Path],
    *,
    lead_ms: int = 350,
    tail_ms: int = 650,
    min_duration_ms: int = 1800,
) -> list[NarrationTiming]:
    narrations = {segment.id: segment for segment in plan.narrations}
    chapters = {chapter.chapterId: chapter.title for chapter in plan.chapters}
    timings: list[NarrationTiming] = []
    cursor_ms = 0
    for scene in plan.scenes:
        narration = narrations[scene.narrationId]
        audio_path = audio_map.get(narration.id)
        if audio_path is None:
            raise ValueError(f"missing audio for narration {narration.id}")
        audio_duration = wav_duration_ms(audio_path)
        duration = max(min_duration_ms, lead_ms + audio_duration + tail_ms)
        timings.append(
            NarrationTiming(
                scene=scene,
                narration=narration,
                chapter_title=chapters.get(scene.chapterId, ""),
                audio_path=audio_path,
                audio_duration_ms=audio_duration,
                start_ms=cursor_ms,
                duration_ms=duration,
                narration_start_ms=cursor_ms + lead_ms,
                narration_end_ms=cursor_ms + lead_ms + audio_duration,
            )
        )
        cursor_ms += duration
    return timings


def wav_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        if rate <= 0:
            raise ValueError(f"invalid sample rate in {path}")
        return int(round(handle.getnframes() * 1000 / rate))


def _normalized_wav(path: Path) -> Path:
    with wave.open(str(path), "rb") as handle:
        if (
            handle.getnchannels() == 1
            and handle.getsampwidth() == 2
            and handle.getframerate() == SAMPLE_RATE
        ):
            return path
    target = Path(tempfile.mkstemp(suffix=".wav")[1])
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            str(target),
        ],
        check=True,
        capture_output=True,
    )
    return target


def build_audio_track(timings: list[NarrationTiming], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_files: list[Path] = []
    try:
        with wave.open(str(output_path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(SAMPLE_RATE)
            for timing in timings:
                lead_samples = _sample_count(timing.narration_start_ms - timing.start_ms)
                out.writeframes(b"\x00\x00" * lead_samples)
                source = _normalized_wav(timing.audio_path)
                if source != timing.audio_path:
                    temp_files.append(source)
                with wave.open(str(source), "rb") as handle:
                    out.writeframes(handle.readframes(handle.getnframes()))
                consumed = lead_samples + _sample_count(timing.audio_duration_ms)
                tail_samples = max(0, _sample_count(timing.duration_ms) - consumed)
                out.writeframes(b"\x00\x00" * tail_samples)
    finally:
        for path in temp_files:
            path.unlink(missing_ok=True)
    return wav_duration_ms(output_path)


def build_chapters(timings: list[NarrationTiming]) -> list[dict]:
    chapters: list[dict] = []
    seen: set[str] = set()
    for timing in timings:
        chapter_id = timing.scene.chapterId
        if chapter_id in seen:
            continue
        seen.add(chapter_id)
        chapters.append(
            {
                "chapterId": chapter_id,
                "title": timing.chapter_title,
                "startMs": timing.start_ms,
            }
        )
    return chapters


def _srt_time(ms: int) -> str:
    hours, rest = divmod(max(0, ms), 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def write_srt(timings: list[NarrationTiming], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, timing in enumerate(timings, start=1):
        lines.append(str(index))
        lines.append(
            f"{_srt_time(timing.narration_start_ms)} --> {_srt_time(timing.narration_end_ms)}"
        )
        lines.append(timing.narration.text)
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
