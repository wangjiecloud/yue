"""P0 probes: record what actually works on this machine.

Probe results are never upgraded into claims about model quality, rights, or
real-device acceptance. A blocked probe reports why it is blocked.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from .adapters.deepseek import DeepSeekClient, ModelNotConfigured, ModelRequestError
from .adapters.tts import TTSAdapter, TTSNotAvailable
from .config import PROJECT_ROOT, Settings, get_settings
from .demo import build_ten_making_plan
from .models import Course, Manifest, TeachingPlan
from .validation import validate_plan


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _tool_version(command: list[str]) -> dict:
    path = shutil.which(command[0])
    if not path:
        return {"available": False, "path": None, "version": None}
    try:
        result = subprocess.run([*command, "--version"], capture_output=True, text=True, timeout=15)
        first = (result.stdout or result.stderr).strip().splitlines()
        return {"available": True, "path": path, "version": first[0] if first else ""}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": True, "path": path, "version": None, "error": str(exc)}


def _module_version(name: str) -> dict:
    spec = importlib.util.find_spec(name)
    if spec is None:
        return {"installed": False, "version": None}
    try:
        module = __import__(name)
        return {"installed": True, "version": getattr(module, "__version__", "unknown")}
    except Exception as exc:  # pragma: no cover - environment specific
        return {"installed": True, "version": None, "error": str(exc)}


def probe_environment(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    mem_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    disk = shutil.disk_usage(str(PROJECT_ROOT))
    gpu: dict = {"available": False, "detail": None}
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            lines = [
                line.strip()
                for line in result.stdout.splitlines()
                if "Chipset Model" in line or "Total Number of Cores" in line
            ]
            gpu = {"available": bool(lines), "detail": "; ".join(lines) or None}
        except (OSError, subprocess.SubprocessError) as exc:
            gpu = {"available": False, "detail": str(exc)}

    report = {
        "probe": "environment",
        "generatedAt": _now(),
        "status": "pass",
        "machine": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor() or "unknown",
            "python": sys.version,
            "pythonExecutable": sys.executable,
            "cpuCount": os.cpu_count(),
            "memoryBytes": mem_bytes,
            "diskTotalBytes": disk.total,
            "diskFreeBytes": disk.free,
            "gpu": gpu,
        },
        "tools": {
            "python3": _tool_version(["python3"]),
            "ffmpeg": _tool_version(["ffmpeg"]),
            "ffprobe": _tool_version(["ffprobe"]),
            "node": _tool_version(["node"]),
            "npm": _tool_version(["npm"]),
            "bun": _tool_version(["bun"]),
            "adb": _tool_version(["adb"]),
            "java": _tool_version(["java"]),
            "say": _tool_version(["say"]),
        },
        "pythonModules": {
            name: _module_version(name)
            for name in ("fastapi", "uvicorn", "pydantic", "httpx", "PIL", "torch", "cosyvoice")
        },
        "deepseek": {
            "baseUrlConfigured": bool(settings.deepseek_base_url),
            "apiKeyConfigured": bool(settings.deepseek_api_key),
            "model": settings.deepseek_model,
            "workspace": settings.deepseek_workspace or None,
            "configured": settings.deepseek_configured,
        },
        "tts": TTSAdapter(settings).backend_status(),
        "androidSdk": {
            "env": os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT"),
            "adbAvailable": shutil.which("adb") is not None,
        },
        "notes": [],
    }
    if not report["deepseek"]["configured"]:
        report["notes"].append(
            "DeepSeek endpoint/key not configured: image-understanding call is blocked."
        )
    if not report["tts"]["ready"]:
        report["notes"].append(
            "CosyVoice3 runtime/weights not detected: production narration is blocked."
        )
    if not report["tools"]["node"]["available"]:
        report["notes"].append("Node.js is missing: Vue studio and Expo mobile are blocked.")
    if not report["tools"]["adb"]["available"]:
        report["notes"].append("adb/Android SDK is missing: real-device acceptance is blocked.")
    if not report["androidSdk"]["env"]:
        report["notes"].append("ANDROID_HOME/ANDROID_SDK_ROOT is not set.")
    if platform.system() == "Darwin" and not gpu["available"]:
        report["notes"].append("No NVIDIA GPU detected; CUDA-only paths are unavailable.")

    report["status"] = "pass_with_blocked_items" if report["notes"] else "pass"
    return report


def _synthetic_question_image() -> Path:
    from PIL import Image, ImageDraw

    from .render.theme import draw_star, font

    image = Image.new("RGB", (900, 500), "white")
    draw = ImageDraw.Draw(image)
    draw.text((60, 50), "8 + 5 = ?", font=font(70), fill=(30, 30, 30))
    for index in range(8):
        draw_star(draw, 100 + index * 55, 240, 18)
    draw.text((60, 300), "8 颗", font=font(36), fill=(80, 80, 80))
    for index in range(5):
        draw_star(draw, 120 + index * 55, 400, 18)
    draw.text((450, 300), "5 颗", font=font(36), fill=(80, 80, 80))
    target = get_settings().data_dir / "tmp" / "synthetic-question.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return target


def probe_deepseek(
    settings: Settings | None = None,
    *,
    image_path: Path | None = None,
    grade: int | None = 1,
) -> dict:
    settings = settings or get_settings()
    report: dict = {
        "probe": "deepseek-image",
        "generatedAt": _now(),
        "status": "blocked",
        "model": settings.deepseek_model,
        "syntheticImage": image_path is None,
    }
    if not settings.deepseek_configured:
        report["reason"] = "YUE_DEEPSEEK_BASE_URL and YUE_DEEPSEEK_API_KEY are required"
        return report
    if image_path is None:
        image_path = _synthetic_question_image()
    report["image"] = str(image_path)

    client = DeepSeekClient(settings)
    started = time.monotonic()
    try:
        result = client.analyze_image(
            image_path.read_bytes(), mime_type="image/png", grade=grade, max_attempts=1
        )
    except ModelNotConfigured as exc:
        report["reason"] = str(exc)
        return report
    except ModelRequestError as exc:
        report["status"] = "fail"
        report["reason"] = str(exc)
        report["httpStatus"] = exc.status
        return report
    except Exception as exc:  # noqa: BLE001 - probe must report, not crash
        report["status"] = "fail"
        report["reason"] = f"{type(exc).__name__}: {exc}"
        return report

    report["elapsedMs"] = int((time.monotonic() - started) * 1000)
    report["attempts"] = result.attempts
    report["rawResponsePath"] = str(
        _write_json(
            settings.data_dir / "reports" / "deepseek_response.json",
            result.raw,
        )
    )
    try:
        plan = TeachingPlan.model_validate(result.raw)
    except Exception as exc:  # noqa: BLE001
        report["status"] = "fail"
        report["reason"] = f"schema validation failed: {exc}"
        return report
    validation = validate_plan(plan)
    report["planValid"] = validation.ok
    report["validationErrors"] = validation.errors
    report["validationWarnings"] = validation.warnings
    report["question"] = plan.question.model_dump()
    report["status"] = "pass" if validation.ok else "fail"
    return report


def probe_tts(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    adapter = TTSAdapter(settings)
    out_dir = settings.data_dir / "reports" / "tts_probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "probe": "local-tts",
        "generatedAt": _now(),
        "status": "blocked",
        "backend": adapter.backend_status(),
        "samples": [],
    }
    samples = [
        ("zh", "小马陪你学数学。先凑十，再加剩下的。"),
        ("en", "Let us make ten first, then add the rest."),
    ]
    try:
        for language, text in samples:
            path = out_dir / f"sample-{language}.wav"
            result = adapter.synthesize(text, language=language, emotion="explain", out_path=path)
            report["samples"].append(
                {
                    "language": language,
                    "text": text,
                    "path": str(path),
                    "durationMs": result.duration_ms,
                    "backend": result.backend,
                    "placeholder": result.placeholder,
                }
            )
    except (TTSNotAvailable, Exception) as exc:  # noqa: BLE001
        report["reason"] = f"{type(exc).__name__}: {exc}"
        report["status"] = "blocked"
        return report

    placeholder = any(sample["placeholder"] for sample in report["samples"])
    report["placeholder"] = placeholder
    report["status"] = "pass_with_placeholder" if placeholder else "pass"
    if placeholder:
        report["notes"] = [
            "Samples were produced by macOS say for pipeline probing only. "
            "They are not accepted course narration."
        ]
    return report


def render_probe(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    from .render.timeline import build_timeline
    from .render.video import render_video

    report: dict = {
        "probe": "render-mp4",
        "generatedAt": _now(),
        "status": "blocked",
    }
    plan = build_ten_making_plan()
    validation = validate_plan(plan)
    if not validation.ok:
        report["status"] = "fail"
        report["reason"] = "demo plan failed validation"
        report["validationErrors"] = validation.errors
        return report
    adapter = TTSAdapter(settings)
    out_dir = settings.data_dir / "reports" / "render_probe"
    audio_dir = out_dir / "narration"
    audio_map: dict[str, Path] = {}
    placeholder = False
    try:
        for narration in plan.narrations:
            result = adapter.synthesize(
                narration.text,
                language=narration.language,
                emotion=narration.emotion,
                out_path=audio_dir / f"{narration.id}.wav",
            )
            placeholder = placeholder or result.placeholder
            audio_map[narration.id] = result.audio_path
        timings = build_timeline(plan, audio_map)
        video = render_video(plan, timings, out_dir / "render-probe.mp4")
    except Exception as exc:  # noqa: BLE001
        report["status"] = "fail"
        report["reason"] = f"{type(exc).__name__}: {exc}"
        return report

    report.update(
        {
            "status": "pass_with_placeholder" if placeholder else "pass",
            "placeholderAudio": placeholder,
            "video": str(video.video_path),
            "subtitles": str(video.subtitle_path),
            "poster": str(video.poster_path),
            "durationMs": video.duration_ms,
            "chapters": video.chapters,
            "media": video.probe,
        }
    )
    return report


def export_schemas() -> list[Path]:
    schemas_dir = PROJECT_ROOT / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "teaching_plan.schema.json": TeachingPlan,
        "course.schema.json": Course,
        "manifest.schema.json": Manifest,
    }
    written: list[Path] = []
    for name, model in outputs.items():
        target = schemas_dir / name
        _write_json(target, model.model_json_schema())
        written.append(target)
    return written


def _write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
