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
import wave
from pathlib import Path


def _log(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}), flush=True)


def main() -> int:
    model_dir = os.environ.get("YUE_COSYVOICE_MODEL_DIR", "")
    if not model_dir or not Path(model_dir).is_dir():
        _log("YUE_COSYVOICE_MODEL_DIR is not set or missing")
        return 2
    code_dir = os.environ.get("YUE_COSYVOICE_CODE_DIR", "")
    if code_dir:
        sys.path.insert(0, code_dir)

    try:
        import torch
        import torchaudio
        from cosyvoice.cli.cosyvoice import CosyVoice3
        from cosyvoice.utils.file_utils import load_wav
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
            prompt = load_wav(reference, 16000)
            chunks = []
            for output in model.inference_zero_shot(
                request["text"], reference_text, prompt, stream=False
            ):
                chunks.append(output["tts_speech"])
            if not chunks:
                raise ValueError("cosyvoice produced no audio")
            audio = torch.cat(chunks, dim=1)
            out_path = Path(request["out_path"])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            torchaudio.save(str(out_path), audio, model.sample_rate)
            with wave.open(str(out_path), "rb") as handle:
                duration_ms = int(round(handle.getnframes() * 1000 / handle.getframerate()))
            print(
                json.dumps({"ok": True, "out_path": str(out_path), "duration_ms": duration_ms}),
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            _log(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
