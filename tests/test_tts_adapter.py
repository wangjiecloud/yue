import shutil

import pytest
from tests.conftest import make_settings

from yue_backend.adapters.tts import TTSAdapter, TTSNotAvailable, wav_duration_ms


def test_backend_status_reports_missing_cosyvoice(tmp_path):
    settings = make_settings(tmp_path)
    adapter = TTSAdapter(settings)
    status = adapter.backend_status()
    assert status["ready"] is False
    assert status["cosyvoice_importable"] is False


def test_synthesize_fails_closed_without_backend(tmp_path):
    settings = make_settings(tmp_path, allow_placeholder_tts=False)
    adapter = TTSAdapter(settings)
    with pytest.raises(TTSNotAvailable):
        adapter.synthesize("测试", language="zh", emotion="explain", out_path=tmp_path / "a.wav")


@pytest.mark.skipif(shutil.which("say") is None, reason="macOS say is unavailable")
def test_placeholder_probe_is_explicitly_marked(tmp_path):
    settings = make_settings(tmp_path, allow_placeholder_tts=True)
    adapter = TTSAdapter(settings)
    result = adapter.synthesize(
        "小马陪你学数学。", language="zh", emotion="explain", out_path=tmp_path / "b.wav"
    )
    assert result.placeholder is True
    assert result.backend == "macos_say_placeholder"
    assert wav_duration_ms(result.audio_path) > 500
    assert result.audio_path.is_file()


@pytest.mark.skipif(shutil.which("say") is None, reason="macOS say is unavailable")
def test_placeholder_audio_is_cached(tmp_path):
    settings = make_settings(tmp_path, allow_placeholder_tts=True)
    adapter = TTSAdapter(settings)
    first = adapter.synthesize(
        "同一句话", language="zh", emotion="explain", out_path=tmp_path / "c1.wav"
    )
    second = adapter.synthesize(
        "同一句话", language="zh", emotion="explain", out_path=tmp_path / "c2.wav"
    )
    assert first.duration_ms == second.duration_ms
    assert first.audio_path.read_bytes() == second.audio_path.read_bytes()
