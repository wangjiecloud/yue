from __future__ import annotations

import json
import logging
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageFilter, ImageOps, ImageStat

from ..adapters.deepseek import DeepSeekClient
from ..adapters.tts import TTSAdapter, TTSNotAvailable
from ..config import Settings
from ..db import JobStore
from ..demo import build_ten_making_plan
from ..models import TeachingPlan
from ..packaging import build_package
from ..render.timeline import build_timeline
from ..render.video import RenderCancelled, render_video
from ..validation import validate_plan

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MIN_IMAGE_SIDE = 160
MAX_IMAGE_PIXELS = 40_000_000


class JobCancelled(RuntimeError):
    pass


class Analyzer(Protocol):
    def __call__(
        self,
        image_bytes: bytes,
        *,
        grade: int | None = None,
        subject_hint: str | None = None,
        extra_feedback: str | None = None,
    ) -> dict: ...


def default_analyzer(settings: Settings) -> Analyzer:
    client = DeepSeekClient(settings)

    def _analyze(
        image_bytes: bytes,
        *,
        grade: int | None = None,
        subject_hint: str | None = None,
        extra_feedback: str | None = None,
    ) -> dict:
        return client.analyze_image(
            image_bytes,
            grade=grade,
            subject_hint=subject_hint,
            extra_feedback=extra_feedback,
            max_attempts=2,
        ).raw

    return _analyze


def _job_dir(settings: Settings, job_id: str) -> Path:
    path = settings.data_dir / "jobs" / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def preprocess_image(source: Path, destination: Path) -> list[str]:
    warnings: list[str] = []
    if not source.is_file():
        raise ValueError("upload file is missing")
    if source.stat().st_size > MAX_UPLOAD_BYTES:
        raise ValueError("image exceeds the upload size limit")
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError("image resolution is too large")
        if min(image.width, image.height) < MIN_IMAGE_SIDE:
            raise ValueError("image is too small to read the question reliably")
        gray = image.convert("L")
        edges = gray.filter(ImageFilter.FIND_EDGES)
        variance = ImageStat.Stat(edges).var[0]
        if variance < 8:
            warnings.append("image may be blurry or blank; recognition result needs review")
        image.convert("RGB").save(destination, "JPEG", quality=92)
    return warnings


def _synthesize(adapter: TTSAdapter, text: str, language: str, emotion: str, path: Path):
    return adapter.synthesize(text, language=language, emotion=emotion, out_path=path)


def _cancelled(store: JobStore, job_id: str) -> bool:
    return store.cancel_requested(job_id)


def run_job(
    store: JobStore,
    settings: Settings,
    job_id: str,
    *,
    analyzer: Analyzer | None = None,
    tts: TTSAdapter | None = None,
    demo: bool | None = None,
) -> dict:
    job = store.get_job(job_id)
    if job is None:
        raise ValueError(f"unknown job {job_id}")
    if _cancelled(store, job_id):
        store.update_job(job_id, status="cancelled", stage="cancelled")
        return store.get_job(job_id) or job

    work_dir = _job_dir(settings, job_id)
    store.update_job(job_id, status="running", stage="preprocess", progress=0.05)
    try:
        warnings: list[str] = []
        use_demo = job["demo"] if demo is None else demo
        if use_demo:
            plan = build_ten_making_plan()
            plan.meta.generator = "yue-demo-handcrafted"
            plan.meta.placeholderAudio = True
            plan_path = work_dir / "plan.json"
            plan_path.write_text(
                json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            upload = store.get_upload(job["upload_id"]) if job["upload_id"] else None
            if upload is None:
                raise ValueError("upload is missing")
            normalized = work_dir / "input.jpg"
            warnings.extend(preprocess_image(Path(upload["path"]), normalized))
            if _cancelled(store, job_id):
                raise JobCancelled("cancelled before recognition")
            store.update_job(job_id, stage="recognize", progress=0.2)
            if analyzer is None:
                analyzer = default_analyzer(settings)
            grade = (job.get("meta") or {}).get("grade")
            subject_hint = (job.get("meta") or {}).get("subjectHint")
            raw = analyzer(normalized.read_bytes(), grade=grade, subject_hint=subject_hint)
            try:
                plan = TeachingPlan.model_validate(raw)
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"model output failed schema validation: {exc}") from exc
            check = validate_plan(plan)
            if not check.ok and not any("uncertain" in error for error in check.errors):
                repair = (
                    "上次输出未通过本地校验，请只修正下列问题并重新输出完整 JSON："
                    + "; ".join(check.errors)[:1500]
                )
                raw = analyzer(
                    normalized.read_bytes(),
                    grade=grade,
                    subject_hint=subject_hint,
                    extra_feedback=repair,
                )
                plan = TeachingPlan.model_validate(raw)
                check = validate_plan(plan)
            if not check.ok:
                raise ValueError("plan validation failed: " + "; ".join(check.errors))
            warnings.extend(check.warnings)
            plan.meta.createdAt = datetime.now(UTC).isoformat()
            plan_path = work_dir / "plan.json"
            plan_path.write_text(
                json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        store.update_job(job_id, plan_path=str(plan_path), stage="tts", progress=0.35)
        adapter = tts or TTSAdapter(settings)
        audio_dir = work_dir / "audio"
        narrations_dir = audio_dir / "narration"
        narration_audio: dict[str, Path] = {}
        placeholder = False
        for narration in plan.narrations:
            if _cancelled(store, job_id):
                raise JobCancelled("cancelled during narration")
            result = _synthesize(
                adapter,
                narration.text,
                narration.language,
                narration.emotion,
                narrations_dir / f"{narration.id}.wav",
            )
            placeholder = placeholder or result.placeholder
            narration_audio[narration.id] = result.audio_path

        language = "en" if plan.question.subject == "english" else "zh"
        hint_audio: dict[str, Path] = {}
        explanation_audio: dict[str, Path] = {}
        for practice in plan.practice:
            if _cancelled(store, job_id):
                raise JobCancelled("cancelled during practice audio")
            for index, hint in enumerate(practice.hints):
                result = _synthesize(
                    adapter,
                    hint,
                    language,
                    "explain",
                    audio_dir / f"{practice.practiceId}-hint-{index}.wav",
                )
                placeholder = placeholder or result.placeholder
                hint_audio[f"{practice.practiceId}:hint:{index}"] = result.audio_path
            result = _synthesize(
                adapter,
                practice.explanation,
                language,
                "encourage",
                audio_dir / f"{practice.practiceId}-explanation.wav",
            )
            placeholder = placeholder or result.placeholder
            explanation_audio[practice.practiceId] = result.audio_path

        plan.meta.placeholderAudio = plan.meta.placeholderAudio or placeholder
        store.update_job(job_id, stage="render", progress=0.5)
        timings = build_timeline(plan, narration_audio)

        def _progress(fraction: float) -> None:
            store.update_job(job_id, progress=0.5 + fraction * 0.4)

        video = render_video(
            plan,
            timings,
            work_dir / "lesson.mp4",
            progress=_progress,
            is_cancelled=lambda: _cancelled(store, job_id),
        )
        store.update_job(
            job_id,
            video_path=str(video.video_path),
            subtitle_path=str(video.subtitle_path),
            stage="package",
            progress=0.94,
        )
        result = build_package(
            plan,
            video,
            work_dir / (plan.planId + ".yuepack"),
            hint_audio=hint_audio,
            explanation_audio=explanation_audio,
        )
        store.update_job(
            job_id,
            package_path=str(result.package_path),
            status="waitingReview",
            stage="done",
            progress=1.0,
            error=None,
        )
        if warnings:
            logger.warning("job %s warnings: %s", job_id, warnings)
        return store.get_job(job_id) or job
    except JobCancelled:
        store.update_job(job_id, status="cancelled", stage="cancelled", error=None)
        return store.get_job(job_id) or job
    except RenderCancelled:
        store.update_job(job_id, status="cancelled", stage="cancelled", error=None)
        return store.get_job(job_id) or job
    except TTSNotAvailable as exc:
        store.update_job(job_id, status="failed", stage="tts", error=str(exc))
        return store.get_job(job_id) or job
    except Exception as exc:  # noqa: BLE001
        logger.exception("job %s failed", job_id)
        store.update_job(
            job_id,
            status="failed",
            stage=store.get_job(job_id)["stage"] if store.get_job(job_id) else "unknown",
            error=f"{type(exc).__name__}: {exc}"[:2000],
        )
        return store.get_job(job_id) or job


def run_queue(
    store: JobStore,
    settings: Settings,
    *,
    analyzer: Analyzer | None = None,
    tts: TTSAdapter | None = None,
    stop: threading.Event | None = None,
) -> None:
    while True:
        job = store.next_queued()
        if job is None:
            return
        run_job(store, settings, job["job_id"], analyzer=analyzer, tts=tts)
        if stop and stop.is_set():
            return


def copy_for_export(package_path: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(package_path, target)
    return target
