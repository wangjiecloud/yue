"""Local-only FastAPI service for the browser studio.

The service binds to the loopback interface. It rejects non-local Host/Origin
values and requires a local session token for every mutating request. Question
images and model output are treated as untrusted data everywhere.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .adapters.tts import TTSAdapter
from .config import Settings, get_settings
from .db import JobStore
from .packaging import PackageError, inspect_package
from .pipeline import Analyzer, run_job, run_queue

logger = logging.getLogger(__name__)

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
ALLOWED_IMAGE_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"RIFF", "image/webp", ".webp"),
)
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class JobCreateRequest(BaseModel):
    uploadId: str | None = None
    grade: int | None = Field(default=None, ge=1, le=3)
    subjectHint: str | None = Field(default=None, max_length=16)
    demo: bool = False


class AssetCreateRequest(BaseModel):
    assetId: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=32)
    path: str = Field(min_length=1, max_length=1024)
    sourceNote: str = Field(default="", max_length=500)
    rightsStatus: str = Field(default="未确认", max_length=64)
    allowedUses: str = Field(default="", max_length=500)
    transcript: str = Field(default="", max_length=1000)
    language: str = Field(default="", max_length=8)
    emotion: str = Field(default="", max_length=32)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _detect_image(data: bytes) -> tuple[str, str] | None:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    for magic, mime, suffix in ALLOWED_IMAGE_MAGIC:
        if data.startswith(magic):
            return mime, suffix
    return None


def create_app(
    settings: Settings | None = None,
    *,
    analyzer: Analyzer | None = None,
    tts_adapter: TTSAdapter | None = None,
    start_worker: bool = True,
    require_token: bool = True,
) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_dirs()
    store = JobStore(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.store = store
        app.state.analyzer = analyzer
        app.state.tts = tts_adapter
        app.state.token = secrets.token_urlsafe(24)
        token_file = settings.data_dir / "reports" / "session_token.txt"
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(app.state.token, encoding="utf-8")
        token_file.chmod(0o600)
        app.state.worker_stop = threading.Event()
        app.state.worker_wake = threading.Event()
        if start_worker:
            thread = threading.Thread(target=_worker_loop, args=(app,), daemon=True)
            thread.start()
            app.state.worker_thread = thread
        yield
        app.state.worker_stop.set()
        app.state.worker_wake.set()

    def _worker_loop(app: FastAPI) -> None:
        while not app.state.worker_stop.is_set():
            try:
                run_queue(
                    store,
                    settings,
                    analyzer=analyzer,
                    tts=tts_adapter,
                    stop=app.state.worker_stop,
                )
            except Exception:  # noqa: BLE001
                logger.exception("worker iteration failed")
            app.state.worker_wake.wait(timeout=1.0)
            app.state.worker_wake.clear()

    app = FastAPI(title="Yue Studio API", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host and host not in LOCAL_HOSTS:
            return JSONResponse({"detail": "local access only"}, status_code=403)
        origin = request.headers.get("origin")
        if origin:
            from urllib.parse import urlparse

            origin_host = urlparse(origin).hostname or ""
            if origin_host not in LOCAL_HOSTS:
                return JSONResponse(
                    {"detail": "cross-origin requests are not allowed"}, status_code=403
                )
        if request.method in MUTATING_METHODS and require_token:
            provided = request.headers.get("x-yue-token", "")
            expected = getattr(request.app.state, "token", None)
            if not expected or not secrets.compare_digest(provided, expected):
                return JSONResponse(
                    {"detail": "missing or invalid local session token"}, status_code=401
                )
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "deepseekConfigured": settings.deepseek_configured,
            "tts": TTSAdapter(settings).backend_status()
            if tts_adapter is None
            else tts_adapter.backend_status(),
            "dataDir": str(settings.data_dir),
        }

    @app.get("/api/session")
    def session():
        if require_token:
            return {"token": app.state.token}
        return {"token": None}

    @app.post("/api/uploads")
    async def create_upload(file: UploadFile):
        data = await file.read(21 * 1024 * 1024)
        detected = _detect_image(data)
        if detected is None:
            raise _error(
                415, "unsupported_media", "only JPEG/PNG/WebP question images are accepted"
            )
        mime, suffix = detected
        if len(data) > 20 * 1024 * 1024:
            raise _error(413, "too_large", "image exceeds the 20MB upload limit")
        digest = hashlib.sha256(data).hexdigest()
        target_dir = settings.data_dir / "uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{digest[:24]}{suffix}"
        path.write_bytes(data)
        upload_id = store.create_upload(path, mime, len(data), digest)
        return {"uploadId": upload_id, "mime": mime, "bytes": len(data), "sha256": digest}

    @app.get("/api/uploads/{upload_id}")
    def get_upload(upload_id: str):
        upload = store.get_upload(upload_id)
        if upload is None:
            raise _error(404, "not_found", "unknown upload")
        return {
            "uploadId": upload["upload_id"],
            "bytes": upload["bytes"],
            "sha256": upload["sha256"],
            "createdAt": upload["created_at"],
        }

    @app.post("/api/jobs")
    def create_job(payload: JobCreateRequest):
        if not payload.demo:
            if not payload.uploadId:
                raise _error(422, "upload_required", "a non-demo job requires an uploadId")
            if store.get_upload(payload.uploadId) is None:
                raise _error(404, "not_found", "unknown upload")
            if not settings.deepseek_configured:
                raise _error(
                    409,
                    "model_not_configured",
                    "DeepSeek endpoint is not configured; set YUE_DEEPSEEK_BASE_URL and YUE_DEEPSEEK_API_KEY",
                )
        job = store.create_job(
            upload_id=payload.uploadId or "",
            grade=payload.grade,
            subject_hint=payload.subjectHint,
            demo=payload.demo,
        )
        app.state.worker_wake.set()
        return _job_response(job)

    @app.get("/api/jobs")
    def list_jobs():
        return [_job_response(job) for job in store.list_jobs()]

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = store.get_job(job_id)
        if job is None:
            raise _error(404, "not_found", "unknown job")
        return _job_response(job)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        job = store.get_job(job_id)
        if job is None:
            raise _error(404, "not_found", "unknown job")
        if job["status"] in {"succeeded", "failed", "cancelled", "waitingReview"}:
            raise _error(409, "not_cancellable", f"job is already {job['status']}")
        store.request_cancel(job_id)
        return _job_response(store.get_job(job_id))

    @app.post("/api/jobs/{job_id}/run")
    def run_job_now(job_id: str):
        job = store.get_job(job_id)
        if job is None:
            raise _error(404, "not_found", "unknown job")
        if job["status"] not in {"queued"}:
            raise _error(409, "not_queued", f"job is {job['status']}")
        run_job(store, settings, job_id, analyzer=analyzer, tts=tts_adapter)
        return _job_response(store.get_job(job_id))

    @app.get("/api/jobs/{job_id}/plan")
    def get_plan(job_id: str):
        job = store.get_job(job_id)
        if job is None or not job["plan_path"]:
            raise _error(404, "not_found", "plan not available")
        return json.loads(Path(job["plan_path"]).read_text(encoding="utf-8"))

    @app.get("/api/jobs/{job_id}/video")
    def get_video(job_id: str, request: Request):
        job = store.get_job(job_id)
        if job is None or not job["video_path"]:
            raise _error(404, "not_found", "video not available")
        path = Path(job["video_path"])
        if not path.is_file():
            raise _error(404, "not_found", "video file is missing")
        return _serve_with_range(path, "video/mp4", request)

    @app.get("/api/jobs/{job_id}/subtitles")
    def get_subtitles(job_id: str):
        job = store.get_job(job_id)
        if job is None or not job["subtitle_path"]:
            raise _error(404, "not_found", "subtitles not available")
        path = Path(job["subtitle_path"])
        if not path.is_file():
            raise _error(404, "not_found", "subtitle file is missing")
        return FileResponse(path, media_type="application/x-subrip")

    @app.post("/api/jobs/{job_id}/exports")
    def export_package(job_id: str):
        job = store.get_job(job_id)
        if job is None:
            raise _error(404, "not_found", "unknown job")
        if job["status"] != "waitingReview":
            raise _error(409, "not_ready", "job is not waiting for review")
        if not job["package_path"]:
            raise _error(404, "not_found", "package not available")
        package = Path(job["package_path"])
        try:
            inspect_package(package)
        except PackageError as exc:
            raise _error(409, "invalid_package", str(exc)) from exc
        exports = settings.data_dir / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        target = exports / package.name
        target.write_bytes(package.read_bytes())
        return {"downloadUrl": f"/api/jobs/{job_id}/package", "path": str(target)}

    @app.get("/api/jobs/{job_id}/package")
    def download_package(job_id: str):
        job = store.get_job(job_id)
        if job is None or not job["package_path"]:
            raise _error(404, "not_found", "package not available")
        path = Path(job["package_path"])
        if not path.is_file():
            raise _error(404, "not_found", "package file is missing")
        return FileResponse(path, media_type="application/zip", filename=path.name)

    @app.get("/api/assets")
    def list_assets():
        return store.list_assets()

    @app.post("/api/assets")
    def create_asset(payload: AssetCreateRequest):
        path = Path(payload.path).expanduser()
        if not path.is_file():
            raise _error(422, "missing_file", "asset file does not exist")
        store.add_asset(
            asset_id=payload.assetId,
            kind=payload.kind,
            path=str(path),
            source_note=payload.sourceNote,
            rights_status=payload.rightsStatus,
            allowed_uses=payload.allowedUses,
            transcript=payload.transcript,
            language=payload.language,
            emotion=payload.emotion,
            checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        return {"assetId": payload.assetId, "registered": True}

    def _job_response(job: dict) -> dict:
        return {
            "jobId": job["job_id"],
            "uploadId": job["upload_id"],
            "status": job["status"],
            "stage": job["stage"],
            "progress": job["progress"],
            "demo": job["demo"],
            "error": job["error"],
            "planPath": job["plan_path"],
            "videoPath": job["video_path"],
            "packagePath": job["package_path"],
            "createdAt": job["created_at"],
            "updatedAt": job["updated_at"],
        }

    def _serve_with_range(path: Path, media_type: str, request: Request):
        size = path.stat().st_size
        range_header = request.headers.get("range")
        if not range_header:
            return FileResponse(path, media_type=media_type)
        try:
            unit, _, specification = range_header.partition("=")
            if unit.strip().lower() != "bytes":
                raise ValueError
            start_text, _, end_text = specification.partition("-")
            start = int(start_text) if start_text else 0
            end = int(end_text) if end_text else size - 1
        except ValueError:
            return JSONResponse(
                {"detail": "invalid range"},
                status_code=416,
                headers={"Content-Range": f"bytes */{size}"},
            )
        start = max(0, min(start, size - 1))
        end = max(start, min(end, size - 1))
        length = end - start + 1

        def iterator():
            with path.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = handle.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iterator(),
            status_code=206,
            media_type=media_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
            },
        )

    studio_dist = Path(__file__).resolve().parents[2] / "studio" / "dist"
    if studio_dist.is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=studio_dist, html=True), name="studio")

    return app


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:  # pragma: no cover
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host=host, port=port, log_level="info")
