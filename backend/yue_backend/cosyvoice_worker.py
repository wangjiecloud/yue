"""CosyVoice3 synthesis worker.

Runs inside the dedicated CosyVoice virtualenv (see .env.example) so the heavy
inference stack never leaks into the API process. It reads one JSON request per
line from stdin and writes one JSON response per line to stdout.

Request fields: text, out_path, reference_audio, reference_text, language,
emotion. Responses: {"ok": true, "out_path": ..., "duration_ms": ...} or
{"ok": false, "error": ...}.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_PROTOCOL = sys.stdout


def _log(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}), file=_PROTOCOL, flush=True)


def main() -> int:
    # Third-party stacks (modelscope, lightning) print to stdout while loading.
    # Keep stdout reserved for the JSON protocol and move their noise to stderr.
    sys.stdout = sys.stderr

    # Executed as a standalone script, so sys.path[0] is this package directory.
    # That makes yue_backend/packaging.py shadow the PyPI ``packaging`` module
    # used by modelscope (same failure mode as the repo-root logging.py).
    script_dir = Path(__file__).resolve().parent
    sys.path[:] = [entry for entry in sys.path if Path(entry or ".").resolve() != script_dir]

    model_dir = os.environ.get("YUE_COSYVOICE_MODEL_DIR", "")
    if not model_dir or not Path(model_dir).is_dir():
        _log("YUE_COSYVOICE_MODEL_DIR is not set or missing")
        return 2
    code_dir = os.environ.get("YUE_COSYVOICE_CODE_DIR", "")
    if code_dir:
        sys.path.insert(0, code_dir)
        matcha_dir = Path(code_dir) / "third_party" / "Matcha-TTS"
        if matcha_dir.is_dir():
            sys.path.insert(0, str(matcha_dir))

    try:
        import torch
        import torchaudio
        from cosyvoice.cli.cosyvoice import CosyVoice3
    except Exception as exc:  # noqa: BLE001
        _log(f"cosyvoice import failed: {exc}")
        return 2

    try:
        model = CosyVoice3(model_dir)
    except Exception as exc:  # noqa: BLE001
        _log(f"cosyvoice init failed: {exc}")
        return 2

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            reference = request["reference_audio"]
            reference_text = request["reference_text"]
            if not reference or not Path(reference).is_file() or not reference_text:
                raise ValueError("reference audio/text is required for zero-shot synthesis")
            chunks = []
            for output in model.inference_zero_shot(
                request["text"], reference_text, reference, stream=False
            ):
                chunks.append(output["tts_speech"])
            if not chunks:
                raise ValueError("cosyvoice produced no audio")
            audio = torch.cat(chunks, dim=1)
            out_path = Path(request["out_path"])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            torchaudio.save(
                str(out_path),
                audio,
                model.sample_rate,
                encoding="PCM_S",
                bits_per_sample=16,
            )
            duration_ms = int(round(audio.shape[-1] * 1000 / model.sample_rate))
            print(
                json.dumps({"ok": True, "out_path": str(out_path), "duration_ms": duration_ms}),
                file=_PROTOCOL,
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            _log(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
