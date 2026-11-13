from yue_backend.packaging import inspect_package
from yue_backend.validation import validate_course


def test_health(app_client):
    response = app_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["deepseekConfigured"] is False


def test_session_token_is_issued(app_client):
    body = app_client.get("/api/session").json()
    assert body["token"]


def test_mutating_requests_require_token(app_client):
    response = app_client.post("/api/jobs", json={"demo": True})
    assert response.status_code == 401
    token = app_client.get("/api/session").json()["token"]
    response = app_client.post("/api/jobs", json={"demo": True}, headers={"X-Yue-Token": token})
    assert response.status_code == 200


def test_non_local_host_is_rejected(tmp_path, fake_analyzer, fake_tts):
    from fastapi.testclient import TestClient
    from tests.conftest import make_settings

    from yue_backend.api import create_app

    settings = make_settings(tmp_path)
    app = create_app(settings, analyzer=fake_analyzer, tts_adapter=fake_tts, start_worker=False)
    with TestClient(app, base_url="http://evil.example") as client:
        assert client.get("/api/health").status_code == 403


def test_cross_origin_is_rejected(app_client):
    token = app_client.get("/api/session").json()["token"]
    response = app_client.post(
        "/api/jobs",
        json={"demo": True},
        headers={"X-Yue-Token": token, "Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_upload_rejects_non_images(app_client):
    token = app_client.get("/api/session").json()["token"]
    response = app_client.post(
        "/api/uploads",
        files={"file": ("note.txt", b"hello world", "text/plain")},
        headers={"X-Yue-Token": token},
    )
    assert response.status_code == 415


def test_upload_accepts_png(app_client, tmp_path):
    from tests.conftest import make_question_png

    token = app_client.get("/api/session").json()["token"]
    image = make_question_png(tmp_path / "q.png")
    response = app_client.post(
        "/api/uploads",
        files={"file": ("q.png", image.read_bytes(), "image/png")},
        headers={"X-Yue-Token": token},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["uploadId"].startswith("up-")
    assert body["bytes"] > 0


def test_job_requires_configuration_or_demo(app_client):
    token = app_client.get("/api/session").json()["token"]
    response = app_client.post(
        "/api/jobs", json={"uploadId": "up-missing"}, headers={"X-Yue-Token": token}
    )
    assert response.status_code == 404

    class _Store:
        pass

    response = app_client.post("/api/jobs", json={}, headers={"X-Yue-Token": token})
    assert response.status_code == 422


def test_non_demo_job_blocked_without_model(app_client, tmp_path):
    from tests.conftest import make_question_png

    token = app_client.get("/api/session").json()["token"]
    image = make_question_png(tmp_path / "q.png")
    upload = app_client.post(
        "/api/uploads",
        files={"file": ("q.png", image.read_bytes(), "image/png")},
        headers={"X-Yue-Token": token},
    ).json()
    response = app_client.post(
        "/api/jobs", json={"uploadId": upload["uploadId"]}, headers={"X-Yue-Token": token}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "model_not_configured"


def test_demo_job_full_pipeline(app_client, monkeypatch):
    token = app_client.get("/api/session").json()["token"]

    def fast_timeline(plan, audio_map, **kwargs):
        from yue_backend.render.timeline import build_timeline as original

        return original(plan, audio_map, lead_ms=50, tail_ms=100, min_duration_ms=400)

    monkeypatch.setattr("yue_backend.pipeline.orchestrator.build_timeline", fast_timeline)
    job = app_client.post("/api/jobs", json={"demo": True}, headers={"X-Yue-Token": token}).json()
    assert job["status"] == "queued"
    finished = app_client.post(f"/api/jobs/{job['jobId']}/run", headers={"X-Yue-Token": token})
    assert finished.status_code == 200
    body = finished.json()
    assert body["status"] == "waitingReview", body
    assert body["stage"] == "done"

    plan = app_client.get(f"/api/jobs/{job['jobId']}/plan").json()
    assert plan["question"]["stem"] == "8 + 5 = ?"

    video = app_client.get(f"/api/jobs/{job['jobId']}/video")
    assert video.status_code == 200
    assert video.headers["content-type"].startswith("video/mp4")

    ranged = app_client.get(f"/api/jobs/{job['jobId']}/video", headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206
    assert ranged.headers["content-range"].startswith("bytes 0-99/")

    subtitles = app_client.get(f"/api/jobs/{job['jobId']}/subtitles")
    assert subtitles.status_code == 200

    exported = app_client.post(f"/api/jobs/{job['jobId']}/exports", headers={"X-Yue-Token": token})
    assert exported.status_code == 200
    package_url = exported.json()["downloadUrl"]
    package = app_client.get(package_url)
    assert package.status_code == 200
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        names = archive.namelist()
    assert "manifest.json" in names
    assert "courses/course.json" in names

    inspection = inspect_package(
        app_client.settings.data_dir / "exports" / "plan-demo-8-plus-5.yuepack"
    )
    check = validate_course(inspection.course, inspection.manifest)
    assert check.ok, check.errors


def test_cancel_before_run(app_client):
    token = app_client.get("/api/session").json()["token"]
    job = app_client.post("/api/jobs", json={"demo": True}, headers={"X-Yue-Token": token}).json()
    response = app_client.post(f"/api/jobs/{job['jobId']}/cancel", headers={"X-Yue-Token": token})
    assert response.status_code == 200
    body = app_client.get(f"/api/jobs/{job['jobId']}").json()
    assert body["status"] == "cancelled"
    run_again = app_client.post(f"/api/jobs/{job['jobId']}/run", headers={"X-Yue-Token": token})
    assert run_again.status_code == 409


def test_assets_registration(app_client, tmp_path):
    from tests.conftest import make_question_png

    from yue_backend.packaging import sha256_file

    token = app_client.get("/api/session").json()["token"]
    image = make_question_png(tmp_path / "asset.png")
    response = app_client.post(
        "/api/assets",
        json={
            "assetId": "ast-1",
            "kind": "image",
            "path": str(image),
            "sourceNote": "家庭自制占位图",
            "rightsStatus": "允许指定用途",
            "allowedUses": "本地家庭教学演示",
        },
        headers={"X-Yue-Token": token},
    )
    assert response.status_code == 200
    listing = app_client.get("/api/assets")
    assert listing.status_code == 200
    assets = listing.json()
    assert assets[0]["asset_id"] == "ast-1"
    assert assets[0]["checksum"] == sha256_file(image)

    missing = app_client.post(
        "/api/assets",
        json={"assetId": "ast-2", "kind": "image", "path": "/nonexistent/file.png"},
        headers={"X-Yue-Token": token},
    )
    assert missing.status_code == 422


def test_regenerate_requires_terminal_state(app_client):
    token = app_client.get("/api/session").json()["token"]
    job = app_client.post("/api/jobs", json={"demo": True}, headers={"X-Yue-Token": token}).json()
    response = app_client.post(
        f"/api/jobs/{job['jobId']}/regenerate",
        json={"mode": "simpler"},
        headers={"X-Yue-Token": token},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "not_regenerable"


def test_regenerate_demo_job_carries_feedback(app_client):
    token = app_client.get("/api/session").json()["token"]
    job = app_client.post("/api/jobs", json={"demo": True}, headers={"X-Yue-Token": token}).json()
    app_client.post(f"/api/jobs/{job['jobId']}/cancel", headers={"X-Yue-Token": token})

    response = app_client.post(
        f"/api/jobs/{job['jobId']}/regenerate",
        json={"mode": "simpler", "feedback": "第二行再慢一点"},
        headers={"X-Yue-Token": token},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["regenerationOf"] == job["jobId"]
    assert "更简单" in body["extraFeedback"]
    assert "第二行再慢一点" in body["extraFeedback"]
    assert body["status"] == "queued"
    assert body["demo"] is True

    missing = app_client.post(
        "/api/jobs/job-missing/regenerate",
        json={},
        headers={"X-Yue-Token": token},
    )
    assert missing.status_code == 404


def test_unknown_job_returns_404(app_client):
    assert app_client.get("/api/jobs/job-missing").status_code == 404
