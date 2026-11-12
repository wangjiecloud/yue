import json
import zipfile
from pathlib import Path

import pytest

from yue_backend.demo import build_ten_making_plan
from yue_backend.models import Course, LessonStep
from yue_backend.packaging import (
    PackageError,
    PackageLimits,
    build_course,
    build_package,
    inspect_package,
)
from yue_backend.render.video import VideoResult
from yue_backend.validation import validate_course


def make_video_result(tmp_path: Path) -> VideoResult:
    root = tmp_path / "media"
    root.mkdir(parents=True, exist_ok=True)
    video = root / "lesson.mp4"
    video.write_bytes(b"fake-mp4-bytes")
    subtitle = root / "lesson.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\n测试\n", encoding="utf-8")
    poster = root / "lesson.poster.jpg"
    poster.write_bytes(b"fake-jpg-bytes")
    return VideoResult(
        video_path=video,
        audio_path=root / "lesson.narration.wav",
        subtitle_path=subtitle,
        poster_path=poster,
        duration_ms=1234,
        chapters=[
            {"chapterId": "c1", "title": "读题", "startMs": 0},
            {"chapterId": "c2", "title": "总结", "startMs": 700},
        ],
        probe={},
    )


def test_build_course_steps_are_reachable_and_finishable(tmp_path):
    plan = build_ten_making_plan()
    video = make_video_result(tmp_path)
    result = build_package(plan, video, tmp_path / "lesson.yuepack")
    course = result.course
    check = validate_course(course, result.manifest)
    assert check.ok, check.errors
    assert course.lessons[0].courseMode == "interactive"
    assert course.lessons[0].practiceIds == [p.practiceId for p in plan.practice]
    step_ids = {step.id for step in course.lessons[0].steps}
    assert {"tutorial", "finish", "reward-complete"} <= step_ids


def test_lecture_only_when_no_practice(tmp_path):
    plan = build_ten_making_plan()
    plan.practice = []
    video = make_video_result(tmp_path)
    result = build_package(plan, video, tmp_path / "lecture.yuepack")
    assert result.course.lessons[0].courseMode == "lectureOnly"
    assert result.manifest.courseMode == "lectureOnly"


def test_package_inspection_roundtrip(tmp_path):
    plan = build_ten_making_plan()
    video = make_video_result(tmp_path)
    built = build_package(plan, video, tmp_path / "lesson.yuepack")
    inspection = inspect_package(built.package_path)
    assert inspection.manifest.courseId == plan.question.questionId
    assert inspection.manifest.courseMode == "interactive"
    assert "assets/videos/lesson.mp4" in inspection.files
    assert any(asset.kind == "video" for asset in inspection.manifest.assets)


def test_checksum_mismatch_is_rejected(tmp_path):
    plan = build_ten_making_plan()
    video = make_video_result(tmp_path)
    built = build_package(plan, video, tmp_path / "lesson.yuepack")
    target = tmp_path / "tampered.yuepack"
    with (
        zipfile.ZipFile(built.package_path) as source,
        zipfile.ZipFile(target, "w") as output,
    ):
        for name in source.namelist():
            data = source.read(name)
            if name == "assets/subtitles/lesson.srt":
                data = data + b"tampered"
            output.writestr(name, data)
    with pytest.raises(PackageError):
        inspect_package(target)


def _evil_package(tmp_path: Path, entries: list[tuple[str, bytes]], name="evil.yuepack"):
    target = tmp_path / name
    with zipfile.ZipFile(target, "w") as archive:
        for entry_name, data in entries:
            archive.writestr(entry_name, data)
    return target


def test_path_traversal_is_rejected(tmp_path):
    package = _evil_package(tmp_path, [("../evil.txt", b"nope")])
    with pytest.raises(PackageError):
        inspect_package(package)


def test_absolute_path_and_backslash_are_rejected(tmp_path):
    with pytest.raises(PackageError):
        inspect_package(_evil_package(tmp_path, [("/etc/evil.txt", b"x")], "abs.yuepack"))
    with pytest.raises(PackageError):
        inspect_package(_evil_package(tmp_path, [("a\\b.txt", b"x")], "back.yuepack"))


def test_duplicate_entries_are_rejected(tmp_path):
    package = _evil_package(tmp_path, [("manifest.json", b"{}"), ("manifest.json", b"{}")])
    with pytest.raises(PackageError):
        inspect_package(package)


def test_disallowed_file_type_is_rejected(tmp_path):
    package = _evil_package(tmp_path, [("assets/evil.js", b"alert(1)")])
    with pytest.raises(PackageError):
        inspect_package(package)


def test_symlink_entry_is_rejected(tmp_path):
    target = tmp_path / "link.yuepack"
    info = zipfile.ZipInfo("assets/link.png")
    info.create_system = 3
    info.external_attr = 0o120777 << 16
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr(info, "manifest.json")
    with pytest.raises(PackageError):
        inspect_package(target, PackageLimits(max_entries=10))


def test_valid_course_requires_existing_practices(tmp_path):
    plan = build_ten_making_plan()
    video = make_video_result(tmp_path)
    course = build_course(plan, video.chapters)
    course.practices = []
    broken = course.model_dump(mode="json")
    broken["lessons"][0]["steps"] = [
        step for step in broken["lessons"][0]["steps"] if step["type"] != "finish"
    ]
    rebuilt = Course.model_validate(broken)
    result = validate_course(rebuilt)
    assert any("unknown practice" in error for error in result.errors)


def test_dead_end_step_is_reported(tmp_path):
    plan = build_ten_making_plan()
    video = make_video_result(tmp_path)
    course = build_course(plan, video.chapters)
    broken = course.model_dump(mode="json")
    lesson = broken["lessons"][0]
    lesson["steps"] = [dict(step) for step in lesson["steps"]]
    for step in lesson["steps"]:
        if step["id"] == "reward-complete":
            step["nextStepId"] = "missing-step"
    rebuilt = Course.model_validate(broken)
    result = validate_course(rebuilt)
    assert any("references unknown step missing-step" in error for error in result.errors)


def test_manifest_json_is_consistent(tmp_path):
    plan = build_ten_making_plan()
    video = make_video_result(tmp_path)
    built = build_package(plan, video, tmp_path / "lesson.yuepack")
    with zipfile.ZipFile(built.package_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        checksums = json.loads(archive.read("checksums.json"))
        course = json.loads(archive.read("courses/course.json"))
    assert manifest["courseId"] == course["courseId"]
    assert manifest["revision"] == course["revision"]
    for asset in manifest["assets"]:
        assert asset["path"] in checksums["files"]
        assert asset["sha256"] == checksums["files"][asset["path"]]
    assert manifest["totalUncompressedBytes"] >= sum(asset["bytes"] for asset in manifest["assets"])


def test_build_course_marks_video_duration(tmp_path):
    plan = build_ten_making_plan()
    video = make_video_result(tmp_path)
    course = build_course(plan, video.chapters)
    course.lessons[0].durationMs = video.duration_ms
    assert course.lessons[0].durationMs == 1234
    assert isinstance(course.lessons[0].steps[0], LessonStep)


def test_extract_package_writes_only_expected_files(tmp_path):
    plan = build_ten_making_plan()
    video = make_video_result(tmp_path)
    built = build_package(plan, video, tmp_path / "lesson.yuepack")
    target = tmp_path / "extracted"
    inspection = inspect_package(built.package_path)
    from yue_backend.packaging import extract_package

    result = extract_package(built.package_path, target)
    assert result.entry_count == inspection.entry_count
    names = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
    assert names == set(inspection.files)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["courseId"] == plan.question.questionId
    assert (target / "assets" / "videos" / "lesson.mp4").read_bytes() == b"fake-mp4-bytes"


def test_extract_rejects_zip_bomb_ratio(tmp_path):
    target = tmp_path / "bomb.yuepack"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("assets/bomb.png", b"\x00" * 2_000_000)
    info = zipfile.ZipFile(target).getinfo("assets/bomb.png")
    assert info.file_size / info.compress_size > 200
    with pytest.raises(PackageError):
        inspect_package(target)
