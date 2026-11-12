import wave
from pathlib import Path

from yue_backend.demo import build_ten_making_plan
from yue_backend.render.timeline import (
    SAMPLE_RATE,
    build_audio_track,
    build_chapters,
    build_timeline,
    wav_duration_ms,
    write_srt,
)


def write_silence(path: Path, ms: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(SAMPLE_RATE * ms / 1000)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(b"\x00\x00" * frames)
    return path


def test_timeline_uses_real_audio_durations(tmp_path):
    plan = build_ten_making_plan()
    audio_map = {
        narration.id: write_silence(tmp_path / f"{narration.id}.wav", 1000)
        for narration in plan.narrations
    }
    timings = build_timeline(plan, audio_map)
    assert len(timings) == len(plan.scenes)
    for timing in timings:
        assert timing.duration_ms >= 1800
        assert timing.audio_duration_ms == 1000
    starts = [timing.start_ms for timing in timings]
    assert starts == sorted(starts)
    for earlier, later in zip(timings, timings[1:], strict=False):
        assert earlier.start_ms + earlier.duration_ms == later.start_ms


def test_audio_track_length_matches_timeline(tmp_path):
    plan = build_ten_making_plan()
    audio_map = {
        narration.id: write_silence(tmp_path / f"{narration.id}.wav", 500)
        for narration in plan.narrations
    }
    timings = build_timeline(plan, audio_map, lead_ms=100, tail_ms=200, min_duration_ms=900)
    track_path = tmp_path / "track.wav"
    duration = build_audio_track(timings, track_path)
    expected = sum(timing.duration_ms for timing in timings)
    assert abs(duration - expected) <= 20
    assert track_path.is_file()
    assert abs(wav_duration_ms(track_path) - expected) <= 20


def test_chapters_are_ordered_and_deduplicated(tmp_path):
    plan = build_ten_making_plan()
    audio_map = {
        narration.id: write_silence(tmp_path / f"{narration.id}.wav", 300)
        for narration in plan.narrations
    }
    timings = build_timeline(plan, audio_map)
    chapters = build_chapters(timings)
    assert [chapter["chapterId"] for chapter in chapters] == ["c-read", "c-demo", "c-summary"]
    starts = [chapter["startMs"] for chapter in chapters]
    assert starts == sorted(starts)


def test_srt_contains_all_narrations(tmp_path):
    plan = build_ten_making_plan()
    audio_map = {
        narration.id: write_silence(tmp_path / f"{narration.id}.wav", 300)
        for narration in plan.narrations
    }
    timings = build_timeline(plan, audio_map)
    srt_path = tmp_path / "lesson.srt"
    write_srt(timings, srt_path)
    content = srt_path.read_text(encoding="utf-8")
    for narration in plan.narrations:
        assert narration.text in content
    assert "-->" in content
