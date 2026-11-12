"""Local text-to-speech adapters.

Production narration comes from local FunAudioLLM/Fun-CosyVoice3-0.5B-2512
weights executed in an isolated virtualenv worker process, so the inference
stack never mixes into the API process. macOS ``say`` is available only as an
explicitly marked engineering probe (``YUE_ALLOW_PLACEHOLDER_TTS=1``) and must
never be presented as course narration in an accepted package.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings

WORKER_PATH = Path(__file__).resolve().parents[1] / "cosyvoice_worker.py"


class TTSNotAvailable(RuntimeError):
    pass


class TTSGenerationError(RuntimeError):
    pass


@dataclass
class TTSResult:
    audio_path: Path
    duration_ms: int
    backend: str
    placeholder: bool


def wav_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as handle:
        frames = handle.getnframes()
        rate = handle.getframerate()
        if rate <= 0:
            raise TTSGenerationError(f"invalid WAV sample rate in {path}")
        return int(round(frames * 1000 / rate))


def _ffmpeg_to_wav(source: Path, target: Path, sample_rate: int = 22050) -> None:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        str(target),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


class _CosyVoiceWorker:
    """Persistent subprocess wrapper around cosyvoice_worker.py."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._process: subprocess.Popen | None = None

    def _env(self) -> dict:
        env = os.environ.copy()
        env["YUE_COSYVOICE_MODEL_DIR"] = str(self.settings.cosyvoice_model_dir or "")
        if self.settings.cosyvoice_code_dir:
            env["YUE_COSYVOICE_CODE_DIR"] = str(self.settings.cosyvoice_code_dir)
        return env

    def _start(self) -> subprocess.Popen:
        if not self.settings.cosyvoice_python:
            raise TTSNotAvailable(
                "YUE_COSYVOICE_PYTHON must point to the CosyVoice virtualenv interpreter"
            )
        process = subprocess.Popen(
            [str(self.settings.cosyvoice_python), str(WORKER_PATH)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self._env(),
        )
        self._process = process
        return process

    def synthesize(self, request: dict) -> dict:
        for attempt in range(2):
            process = self._process or self._start()
            assert process.stdin is not None and process.stdout is not None
            try:
                process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                process.stdin.flush()
                line = process.stdout.readline()
                if not line:
                    raise TTSGenerationError("cosyvoice worker exited unexpectedly")
                response = json.loads(line)
                if response.get("ok"):
                    return response
                raise TTSGenerationError(response.get("error", "cosyvoice worker failed"))
            except (BrokenPipeError, json.JSONDecodeError) as exc:
                self.close()
                if attempt == 1:
                    raise TTSGenerationError(f"cosyvoice worker failed: {exc}") from exc
        raise TTSGenerationError("cosyvoice worker failed")

    def close(self) -> None:
        if self._process is None:
            return
        process, self._process = self._process, None
        try:
            if process.stdin:
                process.stdin.close()
            process.wait(timeout=15)
        except Exception:  # noqa: BLE001 - best effort cleanup
            process.kill()
            process.wait()

    def __del__(self):  # pragma: no cover - interpreter shutdown
        with contextlib.suppress(Exception):
            self.close()


class TTSAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache_dir = settings.data_dir / "media" / "tts_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._worker: _CosyVoiceWorker | None = None

    def backend_status(self) -> dict:
        settings = self.settings
        model_dir_ok = bool(
            settings.cosyvoice_model_dir and Path(settings.cosyvoice_model_dir).is_dir()
        )
        python_ok = bool(settings.cosyvoice_python and Path(settings.cosyvoice_python).is_file())
        code_dir_ok = not settings.cosyvoice_code_dir or Path(settings.cosyvoice_code_dir).is_dir()
        reference_ok = bool(
            settings.cosyvoice_reference_audio
            and Path(settings.cosyvoice_reference_audio).is_file()
            and settings.cosyvoice_reference_text
        )
        status = {
            "cosyvoice_model_dir": str(settings.cosyvoice_model_dir or ""),
            "cosyvoice_dir_exists": model_dir_ok,
            "cosyvoice_python": str(settings.cosyvoice_python or ""),
            "cosyvoice_python_exists": python_ok,
            "cosyvoice_code_dir": str(settings.cosyvoice_code_dir or ""),
            "cosyvoice_reference_ok": reference_ok,
            "cosyvoice_importable": _cosyvoice_importable(),
            "macos_say": shutil.which("say") is not None,
            "placeholder_allowed": settings.allow_placeholder_tts,
        }
        status["ready"] = bool(model_dir_ok and python_ok and code_dir_ok and reference_ok)
        return status

    def _cache_key(self, text: str, language: str, emotion: str) -> str:
        payload = "\x1f".join(
            [
                "cosyvoice3-0.5b-2512",
                str(self.settings.cosyvoice_model_dir or ""),
                str(self.settings.cosyvoice_reference_audio or ""),
                self.settings.cosyvoice_reference_text,
                language,
                emotion,
                text,
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    def synthesize(
        self,
        text: str,
        *,
        language: str,
        emotion: str,
        out_path: Path,
    ) -> TTSResult:
        if not text.strip():
            raise TTSGenerationError("cannot synthesize empty text")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        cache_path = self.cache_dir / f"{self._cache_key(text, language, emotion)}.wav"
        if cache_path.exists():
            shutil.copyfile(cache_path, out_path)
            return TTSResult(
                audio_path=out_path,
                duration_ms=wav_duration_ms(out_path),
                backend="cosyvoice",
                placeholder=False,
            )

        status = self.backend_status()
        if status["ready"]:
            self._synthesize_cosyvoice(text, out_path)
            shutil.copyfile(out_path, cache_path)
            return TTSResult(
                audio_path=out_path,
                duration_ms=wav_duration_ms(out_path),
                backend="cosyvoice",
                placeholder=False,
            )

        if self.settings.allow_placeholder_tts and status["macos_say"]:
            self._synthesize_macos_say(text, language, out_path)
            return TTSResult(
                audio_path=out_path,
                duration_ms=wav_duration_ms(out_path),
                backend="macos_say_placeholder",
                placeholder=True,
            )

        raise TTSNotAvailable(
            "CosyVoice3 is not ready; check YUE_COSYVOICE_MODEL_DIR, "
            "YUE_COSYVOICE_PYTHON and the reference audio/text, or enable "
            "placeholder TTS only for an engineering probe"
        )

    def close(self) -> None:
        if self._worker is not None:
            self._worker.close()
            self._worker = None

    def _synthesize_cosyvoice(self, text: str, out_path: Path) -> None:
        if self._worker is None:
            self._worker = _CosyVoiceWorker(self.settings)
        request = {
            "text": text,
            "out_path": str(out_path),
            "reference_audio": str(self.settings.cosyvoice_reference_audio),
            "reference_text": self.settings.cosyvoice_reference_text,
            "language": "zh",
            "emotion": "neutral",
        }
        response = self._worker.synthesize(request)
        if not Path(response["out_path"]).is_file():
            raise TTSGenerationError("cosyvoice worker reported success but no file exists")

    def _synthesize_macos_say(self, text: str, language: str, out_path: Path) -> None:
        MacOSSayProbe.synthesize(text, language, out_path)


def _cosyvoice_importable() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("cosyvoice") is not None
    except (ImportError, ValueError):
        return False


class MacOSSayProbe:
    """Engineering-only synthesizer. Never used for accepted courses."""

    _VOICES = {"zh": "Tingting", "en": "Samantha"}

    @classmethod
    def synthesize(cls, text: str, language: str, out_path: Path) -> None:
        if shutil.which("say") is None:
            raise TTSNotAvailable("macOS say is unavailable")
        aiff = out_path.with_suffix(".aiff")
        voice = cls._VOICES.get(language, cls._VOICES["zh"])
        subprocess.run(
            ["say", "-v", voice, "-o", str(aiff), text],
            check=True,
            capture_output=True,
        )
        _ffmpeg_to_wav(aiff, out_path)
        aiff.unlink(missing_ok=True)
