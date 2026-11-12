"""Build and safely inspect ``.yuepack`` course packages.

The container is a restricted ZIP with a manifest, one course definition and
only the media the App needs. Import treats every entry as untrusted: no
absolute paths, no traversal, no symlinks, no duplicates, bounded expansion and
checksum verification.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .models import (
    ChapterTime,
    Course,
    Lesson,
    LessonStep,
    Manifest,
    ManifestAsset,
    PracticeItem,
    TeachingPlan,
)
from .render.video import VideoResult
from .validation import validate_course, validate_plan

ALLOWED_SUFFIXES = {
    ".json",
    ".mp4",
    ".m4a",
    ".wav",
    ".aac",
    ".mp3",
    ".srt",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}
ALLOWED_ROOTS = {"manifest.json", "courses", "assets", "checksums.json"}


class PackageError(ValueError):
    pass


@dataclass
class PackageLimits:
    max_entries: int = 512
    max_file_bytes: int = 256 * 1024 * 1024
    max_total_bytes: int = 1024 * 1024 * 1024
    max_compression_ratio: float = 200.0
    max_path_length: int = 240


@dataclass
class BuildResult:
    package_path: Path
    manifest: Manifest
    course: Course
    files: list[str] = field(default_factory=list)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _interaction_step(practice: PracticeItem) -> LessonStep:
    hints = practice.hints
    first_hint = f"hint-{practice.practiceId}-0" if hints else f"assisted-{practice.practiceId}"
    return LessonStep(
        id=f"ask-{practice.practiceId}",
        type="interaction",
        prompt=practice.prompt,
        interaction={"practiceId": practice.practiceId},
        onCorrect=f"correct-{practice.practiceId}",
        onIncorrect=first_hint,
        maxAttempts=practice.maxAttempts,
        onAttemptsExhausted=f"assisted-{practice.practiceId}",
    )


def _hint_steps(practice: PracticeItem, available_audio: set[str]) -> list[LessonStep]:
    steps = []
    for index, hint in enumerate(practice.hints):
        asset_id = f"hint-audio-{practice.practiceId}-{index}"
        next_id = (
            f"hint-{practice.practiceId}-{index + 1}"
            if index + 1 < len(practice.hints)
            else f"ask-{practice.practiceId}"
        )
        steps.append(
            LessonStep(
                id=f"hint-{practice.practiceId}-{index}",
                type="display",
                text=hint,
                assetId=asset_id if asset_id in available_audio else None,
                nextStepId=next_id,
            )
        )
    return steps


def build_course(
    plan: TeachingPlan,
    chapters: list[dict],
    *,
    available_audio: set[str] | None = None,
) -> Course:
    available_audio = available_audio or set()
    practices = plan.practice
    course_mode = "interactive" if practices else "lectureOnly"
    steps: list[LessonStep] = [
        LessonStep(
            id="tutorial",
            type="video",
            assetId="lesson-video",
            nextStepId=f"ask-{practices[0].practiceId}" if practices else "reward-complete",
        )
    ]
    for index, practice in enumerate(practices):
        steps.append(_interaction_step(practice))
        steps.extend(_hint_steps(practice, available_audio))
        next_after = (
            f"ask-{practices[index + 1].practiceId}"
            if index + 1 < len(practices)
            else "reward-complete"
        )
        steps.append(
            LessonStep(
                id=f"correct-{practice.practiceId}",
                type="feedback",
                result="correct",
                text=practice.explanation,
                assetId=(
                    f"explanation-audio-{practice.practiceId}"
                    if f"explanation-audio-{practice.practiceId}" in available_audio
                    else None
                ),
                rewardKey=f"first-correct:{plan.question.questionId}:{practice.practiceId}",
                amount=1,
                nextStepId=next_after,
            )
        )
        steps.append(
            LessonStep(
                id=f"assisted-{practice.practiceId}",
                type="feedback",
                result="assisted",
                text=practice.explanation,
                assetId=(
                    f"explanation-audio-{practice.practiceId}"
                    if f"explanation-audio-{practice.practiceId}" in available_audio
                    else None
                ),
                nextStepId=next_after,
            )
        )
    steps.append(
        LessonStep(
            id="reward-complete",
            type="reward",
            rewardKey=f"lesson-complete:{plan.question.questionId}",
            amount=1,
            nextStepId="finish",
        )
    )
    steps.append(LessonStep(id="finish", type="finish"))

    lesson = Lesson(
        lessonId=f"lesson-{plan.question.questionId}",
        questionId=plan.question.questionId,
        questionRevision=plan.question.questionRevision,
        title=plan.question.stem,
        courseMode=course_mode,
        videoAssetId="lesson-video",
        durationMs=0,
        subtitleAssetId="lesson-subtitle",
        chapters=[ChapterTime.model_validate(chapter) for chapter in chapters],
        entryStepId="tutorial",
        steps=steps,
        practiceIds=[practice.practiceId for practice in practices],
    )
    return Course(
        courseId=plan.question.questionId,
        revision=plan.question.questionRevision,
        grade=plan.question.grade,
        subject=plan.question.subject,
        knowledgePoints=plan.question.knowledgePoints,
        lessons=[lesson],
        practices=practices,
    )


def build_package(
    plan: TeachingPlan,
    video: VideoResult,
    output_path: Path,
    *,
    hint_audio: dict[str, Path] | None = None,
    explanation_audio: dict[str, Path] | None = None,
    minimum_app_version: str = "0.1.0",
) -> BuildResult:
    hint_audio = hint_audio or {}
    explanation_audio = explanation_audio or {}
    plan_check = validate_plan(plan)
    if not plan_check.ok:
        raise PackageError("plan is invalid: " + "; ".join(plan_check.errors))
    available_audio = {
        f"hint-audio-{practice.practiceId}-{index}"
        for practice in plan.practice
        for index in range(len(practice.hints))
        if f"{practice.practiceId}:hint:{index}" in hint_audio
    }
    available_audio |= {
        f"explanation-audio-{practice.practiceId}"
        for practice in plan.practice
        if practice.practiceId in explanation_audio
    }
    course = build_course(plan, video.chapters, available_audio=available_audio)

    staging = output_path.parent / (output_path.stem + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "courses").mkdir(parents=True)
    (staging / "assets" / "videos").mkdir(parents=True)
    (staging / "assets" / "subtitles").mkdir(parents=True)
    (staging / "assets" / "images").mkdir(parents=True)
    (staging / "assets" / "audio").mkdir(parents=True)

    assets: list[ManifestAsset] = []
    files: dict[str, Path] = {}

    def add_asset(asset_id: str, kind: str, source: Path, relative: str, duration_ms=None) -> None:
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        assets.append(
            ManifestAsset(
                assetId=asset_id,
                path=relative,
                kind=kind,
                sha256=sha256_file(target),
                bytes=target.stat().st_size,
                durationMs=duration_ms,
            )
        )
        files[relative] = target

    add_asset(
        "lesson-video",
        "video",
        video.video_path,
        "assets/videos/lesson.mp4",
        video.duration_ms,
    )
    add_asset("lesson-subtitle", "subtitle", video.subtitle_path, "assets/subtitles/lesson.srt")
    add_asset("lesson-poster", "image", video.poster_path, "assets/images/lesson.poster.jpg")

    for practice in plan.practice:
        for index in range(len(practice.hints)):
            key = f"{practice.practiceId}:hint:{index}"
            source = hint_audio.get(key)
            if source:
                add_asset(
                    f"hint-audio-{practice.practiceId}-{index}",
                    "audio",
                    source,
                    f"assets/audio/{practice.practiceId}-hint-{index}.wav",
                )
        source = explanation_audio.get(practice.practiceId)
        if source:
            add_asset(
                f"explanation-audio-{practice.practiceId}",
                "audio",
                source,
                f"assets/audio/{practice.practiceId}-explanation.wav",
            )

    lesson_duration = video.duration_ms
    course.lessons[0].durationMs = lesson_duration

    course_payload = course.model_dump(mode="json")
    (staging / "courses" / "course.json").write_text(
        json.dumps(course_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    files["courses/course.json"] = staging / "courses" / "course.json"

    required = {"video.h264", "video.aac", "subtitle.srt"}
    for practice in plan.practice:
        required.add(f"interaction.{practice.kind}")
    manifest = Manifest(
        packageId=f"{course.courseId}-r{course.revision}",
        courseId=course.courseId,
        revision=course.revision,
        minimumAppVersion=minimum_app_version,
        courseMode="interactive" if plan.practice else "lectureOnly",
        requiredCapabilities=sorted(required),
        createdAt=datetime.now(UTC).isoformat(),
        assets=assets,
        totalUncompressedBytes=sum(asset.bytes for asset in assets)
        + (staging / "courses" / "course.json").stat().st_size,
    )
    course_check = validate_course(course, manifest)
    if not course_check.ok:
        shutil.rmtree(staging, ignore_errors=True)
        raise PackageError("course is invalid: " + "; ".join(course_check.errors))
    (staging / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    files["manifest.json"] = staging / "manifest.json"

    checksums = {relative: sha256_file(path) for relative, path in sorted(files.items())}
    (staging / "checksums.json").write_text(
        json.dumps({"algorithm": "sha256", "files": checksums}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging).as_posix())
    shutil.rmtree(staging)
    return BuildResult(
        package_path=output_path,
        manifest=manifest,
        course=course,
        files=sorted(files),
    )


@dataclass
class PackageInspection:
    manifest: Manifest
    course: Course
    entry_count: int
    total_uncompressed_bytes: int
    files: list[str] = field(default_factory=list)


def _safe_member_path(name: str, limits: PackageLimits) -> str:
    if not name or len(name) > limits.max_path_length:
        raise PackageError(f"invalid or overlong path: {name!r}")
    if name.startswith("/") or name.startswith("\\"):
        raise PackageError(f"absolute path is forbidden: {name!r}")
    if "\\" in name:
        raise PackageError(f"backslash path is forbidden: {name!r}")
    parts = name.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise PackageError(f"path traversal is forbidden: {name!r}")
    if parts[0] not in ALLOWED_ROOTS:
        raise PackageError(f"unexpected package root: {name!r}")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise PackageError(f"file type is not allowed: {name!r}")
    return "/".join(parts)


def inspect_package(package_path: Path, limits: PackageLimits | None = None) -> PackageInspection:
    limits = limits or PackageLimits()
    if not package_path.is_file():
        raise PackageError("package file does not exist")
    seen: set[str] = set()
    infos: list[zipfile.ZipInfo] = []
    total_uncompressed = 0
    with zipfile.ZipFile(package_path) as archive:
        infos = archive.infolist()
        if len(infos) > limits.max_entries:
            raise PackageError("package has too many entries")
        for info in infos:
            name = _safe_member_path(info.filename, limits)
            if name in seen:
                raise PackageError(f"duplicate package path: {name!r}")
            seen.add(name)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise PackageError(f"symlink entry is forbidden: {name!r}")
            if info.file_size > limits.max_file_bytes:
                raise PackageError(f"file exceeds size limit: {name!r}")
            total_uncompressed += info.file_size
            if total_uncompressed > limits.max_total_bytes:
                raise PackageError("package expands beyond the total size limit")
            if (
                info.compress_size > 0
                and info.file_size / info.compress_size > limits.max_compression_ratio
            ):
                raise PackageError(f"suspicious compression ratio: {name!r}")

        if "manifest.json" not in seen or "courses/course.json" not in seen:
            raise PackageError("package is missing manifest.json or courses/course.json")
        checksums = json.loads(archive.read("checksums.json"))
        declared = checksums.get("files")
        if not isinstance(declared, dict):
            raise PackageError("checksums.json is malformed")
        for name in seen:
            if name == "checksums.json":
                continue
            if name not in declared:
                raise PackageError(f"file is missing from checksums: {name!r}")
            digest = hashlib.sha256()
            with archive.open(name) as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != declared[name]:
                raise PackageError(f"checksum mismatch: {name!r}")

        manifest = Manifest.model_validate_json(archive.read("manifest.json"))
        course = Course.model_validate_json(archive.read("courses/course.json"))

    asset_paths = {asset.path for asset in manifest.assets}
    for asset in manifest.assets:
        if asset.path not in seen:
            raise PackageError(f"manifest asset is missing: {asset.path!r}")
        if asset.sha256 != declared[asset.path]:
            raise PackageError(f"manifest checksum mismatch: {asset.path!r}")
    for lesson in course.lessons:
        if lesson.videoAssetId not in {asset.assetId for asset in manifest.assets}:
            raise PackageError(f"lesson references unknown video asset: {lesson.videoAssetId!r}")
    if not asset_paths:
        raise PackageError("manifest has no assets")

    return PackageInspection(
        manifest=manifest,
        course=course,
        entry_count=len(infos),
        total_uncompressed_bytes=total_uncompressed,
        files=sorted(seen),
    )


def extract_package(
    package_path: Path,
    target_dir: Path,
    limits: PackageLimits | None = None,
) -> PackageInspection:
    limits = limits or PackageLimits()
    inspection = inspect_package(package_path, limits)
    disk = shutil.disk_usage(target_dir.parent if target_dir.parent.exists() else Path.cwd())
    if disk.free < inspection.total_uncompressed_bytes * 1.2:
        raise PackageError("not enough free space to extract this package")
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)
    written = 0
    with zipfile.ZipFile(package_path) as archive:
        for info in archive.infolist():
            name = _safe_member_path(info.filename, limits)
            destination = target_dir / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as sink:
                while True:
                    chunk = source.read(256 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > limits.max_total_bytes:
                        raise PackageError("extracted bytes exceed the limit")
                    sink.write(chunk)
    return inspection
