from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..models import TeachingPlan
from .scenes import SceneContext, ScenePainter
from .theme import FPS, HEIGHT, WIDTH
from .timeline import NarrationTiming, build_audio_track, build_chapters, write_srt


class RenderCancelled(RuntimeError):
    pass


@dataclass
class VideoResult:
    video_path: Path
    audio_path: Path
    subtitle_path: Path
    poster_path: Path
    duration_ms: int
    chapters: list[dict]
    probe: dict


def probe_media(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,"
            "r_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def render_video(
    plan: TeachingPlan,
    timings: list[NarrationTiming],
    output_path: Path,
    *,
    fps: int = FPS,
    progress: Callable[[float], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> VideoResult:
    if not timings:
        raise ValueError("timeline is empty")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path = output_path.with_name(output_path.stem + ".narration.wav")
    subtitle_path = output_path.with_suffix(".srt")
    poster_path = output_path.with_suffix(".poster.jpg")

    total_duration = build_audio_track(timings, audio_path)
    write_srt(timings, subtitle_path)
    chapters = build_chapters(timings)

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        "-i",
        str(audio_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdin is not None

    total_frames = sum(max(1, round(timing.duration_ms * fps / 1000)) for timing in timings)
    written = 0
    poster_saved = False
    try:
        for timing in timings:
            context = SceneContext(
                plan=plan,
                scene=timing.scene,
                narration=timing.narration,
                duration_ms=timing.duration_ms,
                chapter_title=timing.chapter_title,
            )
            painter = ScenePainter(context)
            frame_count = max(1, round(timing.duration_ms * fps / 1000))
            for index in range(frame_count):
                if is_cancelled and is_cancelled():
                    raise RenderCancelled("render cancelled")
                t_ms = int(index * 1000 / fps)
                image = painter.render(t_ms)
                if not poster_saved and t_ms >= 900:
                    image.save(poster_path, quality=88)
                    poster_saved = True
                process.stdin.write(image.tobytes())
                written += 1
                if progress and written % 15 == 0:
                    progress(min(0.99, written / total_frames))
        process.stdin.close()
        stderr = process.stderr.read() if process.stderr else b""
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"ffmpeg failed: {stderr.decode('utf-8', 'replace')[:2000]}")
    except Exception:
        process.kill()
        process.wait()
        raise
    finally:
        if not poster_saved:
            image = ScenePainter(
                SceneContext(
                    plan=plan,
                    scene=timings[0].scene,
                    narration=timings[0].narration,
                    duration_ms=timings[0].duration_ms,
                    chapter_title=timings[0].chapter_title,
                )
            ).render(0)
            image.save(poster_path, quality=88)

    if progress:
        progress(1.0)
    return VideoResult(
        video_path=output_path,
        audio_path=audio_path,
        subtitle_path=subtitle_path,
        poster_path=poster_path,
        duration_ms=total_duration,
        chapters=chapters,
        probe=probe_media(output_path),
    )
