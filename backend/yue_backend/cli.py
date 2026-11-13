from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import get_settings


def _print(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _write(path: Path | None, data: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yue-probe", description="Yue generation backend probes")
    sub = parser.add_subparsers(dest="command", required=True)

    env = sub.add_parser("probe-env", help="record machine/tool/model environment")
    env.add_argument("--out", type=Path, default=None)

    ds = sub.add_parser("probe-deepseek", help="send one question image to the model")
    ds.add_argument("--image", type=Path, default=None)
    ds.add_argument("--grade", type=int, default=1)
    ds.add_argument("--out", type=Path, default=None)

    tts = sub.add_parser("probe-tts", help="synthesize Chinese and English samples")
    tts.add_argument("--out", type=Path, default=None)

    render = sub.add_parser("render-probe", help="render the hand-authored demo plan to MP4")
    render.add_argument("--out", type=Path, default=None)

    demo = sub.add_parser("demo", help="generate the demo lesson video and artifacts")
    demo.add_argument("--out", type=Path, default=None)

    demo_pack = sub.add_parser(
        "demo-pack", help="build the offline demo package embedded in the Android app"
    )
    demo_pack.add_argument(
        "--dest",
        type=Path,
        default=Path("mobile/assets/demo/course.yuepack"),
    )

    sub.add_parser("export-schemas", help="write JSON Schemas from the pydantic models")

    validate = sub.add_parser("validate", help="validate a teaching plan JSON file")
    validate.add_argument("plan", type=Path)

    serve = sub.add_parser("serve", help="run the local studio API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "probe-env":
        from .probes import probe_environment

        report = probe_environment(settings)
        _print(report)
        _write(args.out or settings.data_dir / "reports" / "env_probe.json", report)
        return 0

    if args.command == "probe-deepseek":
        from .probes import probe_deepseek

        report = probe_deepseek(settings, image_path=args.image, grade=args.grade)
        _print(report)
        _write(args.out or settings.data_dir / "reports" / "deepseek_probe.json", report)
        return 0 if report["status"] == "pass" else 1

    if args.command == "probe-tts":
        from .probes import probe_tts

        report = probe_tts(settings)
        _print(report)
        _write(args.out or settings.data_dir / "reports" / "tts_probe.json", report)
        return 0 if report["status"].startswith("pass") else 1

    if args.command == "render-probe":
        from .probes import render_probe

        report = render_probe(settings)
        _print(report)
        _write(args.out or settings.data_dir / "reports" / "render_probe.json", report)
        return 0 if report["status"].startswith("pass") else 1

    if args.command == "demo":
        from .demo_run import generate_demo_video

        demo_settings = settings.model_copy(update={"allow_placeholder_tts": True})
        report = generate_demo_video(demo_settings)
        _print(report)
        _write(args.out, report)
        return 0

    if args.command == "demo-pack":
        import shutil

        from .demo_run import generate_demo_video

        demo_settings = settings.model_copy(update={"allow_placeholder_tts": True})
        report = generate_demo_video(demo_settings, progress=False)
        source = Path(report["package"])
        target = args.dest.expanduser()
        if not target.is_absolute():
            target = Path.cwd() / target
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        print(f"wrote {target} ({target.stat().st_size} bytes, source {source})")
        return 0

    if args.command == "export-schemas":
        from .probes import export_schemas

        for path in export_schemas():
            print(f"wrote {path}")
        return 0

    if args.command == "validate":
        from .models import TeachingPlan
        from .validation import validate_plan

        plan = TeachingPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
        result = validate_plan(plan)
        _print({"ok": result.ok, "errors": result.errors, "warnings": result.warnings})
        return 0 if result.ok else 1

    if args.command == "serve":
        from .api import serve as run_serve

        print(f"serving on http://{args.host}:{args.port} (local only)")
        run_serve(args.host, args.port)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
