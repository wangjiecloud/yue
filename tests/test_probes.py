import json

from yue_backend.models import TeachingPlan
from yue_backend.probes import (
    export_schemas,
    probe_deepseek,
    probe_environment,
    probe_tts,
    render_probe,
)
from yue_backend.validation import validate_plan


def test_environment_probe_reports_blocked_items(tmp_path):
    from tests.conftest import make_settings

    settings = make_settings(tmp_path)
    report = probe_environment(settings)
    assert report["status"] in {"pass", "pass_with_blocked_items"}
    assert report["machine"]["memoryBytes"] > 0
    assert report["machine"]["diskFreeBytes"] > 0
    assert "ffmpeg" in report["tools"]
    assert "deepseek" in report
    assert isinstance(report["notes"], list)
    assert report["deepseek"]["configured"] is False
    assert report["tts"]["ready"] is False or report["tts"]["ready"] is True


def test_deepseek_probe_is_blocked_without_credentials(tmp_path):
    from tests.conftest import make_settings

    settings = make_settings(tmp_path)
    report = probe_deepseek(settings)
    assert report["status"] == "blocked"
    assert "YUE_DEEPSEEK_BASE_URL" in report["reason"]


def test_tts_probe_reports_backend_status(tmp_path):
    from tests.conftest import FakeTTS, make_settings

    settings = make_settings(tmp_path)
    from yue_backend.adapters.tts import TTSAdapter

    class PatchedAdapter(TTSAdapter):
        def __init__(self, settings):
            super().__init__(settings)
            self._fake = FakeTTS()

        def backend_status(self):
            return {
                "ready": True,
                "macos_say": False,
                "cosyvoice_importable": False,
                "placeholder_allowed": True,
            }

        def synthesize(self, text, *, language, emotion, out_path):
            return self._fake.synthesize(
                text, language=language, emotion=emotion, out_path=out_path
            )

    import yue_backend.probes as probes

    original = probes.TTSAdapter
    probes.TTSAdapter = PatchedAdapter
    try:
        report = probe_tts(settings)
    finally:
        probes.TTSAdapter = original
    assert report["status"] == "pass_with_placeholder"
    assert len(report["samples"]) == 2
    assert {sample["language"] for sample in report["samples"]} == {"zh", "en"}


def test_render_probe_produces_media(tmp_path, monkeypatch):
    from tests.conftest import FakeTTS, make_settings

    settings = make_settings(tmp_path, allow_placeholder_tts=True)

    from yue_backend.adapters.tts import TTSAdapter
    from yue_backend.render.timeline import build_timeline as original_timeline

    class PatchedAdapter(TTSAdapter):
        def __init__(self, settings):
            super().__init__(settings)
            self._fake = FakeTTS()

        def backend_status(self):
            return {
                "ready": True,
                "macos_say": False,
                "cosyvoice_importable": False,
                "placeholder_allowed": True,
            }

        def synthesize(self, text, *, language, emotion, out_path):
            return self._fake.synthesize(
                text, language=language, emotion=emotion, out_path=out_path
            )

    import yue_backend.probes as probes

    monkeypatch.setattr(probes, "TTSAdapter", PatchedAdapter)

    def fast_timeline(plan, audio_map, **kwargs):
        return original_timeline(plan, audio_map, lead_ms=50, tail_ms=100, min_duration_ms=400)

    monkeypatch.setattr("yue_backend.render.timeline.build_timeline", fast_timeline)
    report = render_probe(settings)
    assert report["status"].startswith("pass"), report
    assert report["durationMs"] > 0
    assert report["media"]["streams"][0]["codec_name"] == "h264"


def test_exported_schema_round_trips_demo_plan(tmp_path):
    paths = export_schemas()
    assert any("teaching_plan.schema.json" in str(path) for path in paths)
    schema_path = next(path for path in paths if "teaching_plan" in path.name)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["title"] == "TeachingPlan"
    from yue_backend.demo import build_ten_making_plan

    plan = build_ten_making_plan()
    assert validate_plan(plan).ok
    assert TeachingPlan.model_validate(plan.model_dump(mode="json")).planId == plan.planId
