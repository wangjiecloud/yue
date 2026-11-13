from __future__ import annotations

import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yue_backend.adapters.tts import TTSResult
from yue_backend.config import Settings
from yue_backend.demo import build_ten_making_plan


class FakeTTS:
    """Deterministic stand-in used by tests. Never touches real engines."""

    def __init__(self, duration_ms: int = 200):
        self.duration_ms = duration_ms
        self.calls: list[tuple[str, str, str]] = []

    def backend_status(self) -> dict:
        return {
            "ready": True,
            "macos_say": False,
            "cosyvoice_importable": False,
            "placeholder_allowed": True,
        }

    def synthesize(self, text: str, *, language: str, emotion: str, out_path: Path) -> TTSResult:
        self.calls.append((text, language, emotion))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        rate = 22050
        frames = int(rate * self.duration_ms / 1000)
        with wave.open(str(out_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(b"\x00\x00" * frames)
        return TTSResult(
            audio_path=out_path,
            duration_ms=self.duration_ms,
            backend="fake",
            placeholder=True,
        )


class FakeAnalyzer:
    def __init__(self, plan=None, raw=None):
        self.plan = plan or build_ten_making_plan()
        self.raw = raw
        self.calls = 0

    def __call__(self, image_bytes: bytes, *, grade=None, subject_hint=None, extra_feedback=None):
        self.calls += 1
        if self.raw is not None:
            return self.raw
        data = self.plan.model_dump(mode="json")
        if extra_feedback is None:
            return data
        raise AssertionError("fake analyzer received unexpected repair request")


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "data_dir": tmp_path / "data",
        "allow_placeholder_tts": False,
        "cosyvoice_model_dir": None,
        "cosyvoice_code_dir": None,
        "cosyvoice_python": None,
        "cosyvoice_reference_audio": None,
        "cosyvoice_reference_text": "",
        "deepseek_base_url": "",
        "deepseek_api_key": "",
    }
    values.update(overrides)
    settings = Settings(_env_file=None, **values)
    settings.ensure_dirs()
    return settings


def make_question_png(path: Path, size: tuple[int, int] = (480, 360)) -> Path:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 20), "8 + 5 = ?", fill="black")
    draw.rectangle((40, 80, 200, 200), outline="black", width=3)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


@pytest.fixture()
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture()
def fake_tts():
    return FakeTTS()


@pytest.fixture()
def fake_analyzer():
    return FakeAnalyzer()


@pytest.fixture()
def app_client(tmp_path, fake_analyzer, fake_tts, monkeypatch):
    from yue_backend.api import create_app

    settings = make_settings(tmp_path)
    app = create_app(
        settings,
        analyzer=fake_analyzer,
        tts_adapter=fake_tts,
        start_worker=False,
        require_token=True,
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.settings = settings
        client.fake_analyzer = fake_analyzer
        client.fake_tts = fake_tts
        yield client
