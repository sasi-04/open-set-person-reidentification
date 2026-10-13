"""Health, readiness, access control, error format, headers, limits."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import KEYS, make_settings
from tests.fakes import FakeDetector, FakeExtractor, crop_png


def test_health_is_public_and_cheap(env):
    response = env.client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_lists_every_component(env):
    body = env.client.get("/api/readiness").json()
    assert body["status"] == "ready"
    assert set(body["components"]) >= {"database", "embedding_model", "detector", "gallery_index", "device", "auth"}
    assert body["components"]["embedding_model"]["embedding_dim"] == 16


def test_missing_key_is_401_with_a_structured_error(env):
    response = env.client.get("/api/gallery")
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "unauthorized" and error["request_id"] and error["message"]


def test_wrong_key_is_401(env):
    assert env.client.get("/api/gallery", headers={"X-API-Key": "nope"}).status_code == 401


def test_whoami_reports_the_role_of_the_key(env):
    for role in ("viewer", "operator", "admin"):
        assert env.get("/api/auth/me", role=role).json() == {"role": role, "auth_required": True}


def test_roles_are_enforced_on_sensitive_routes(env):
    # viewer: cannot manage the gallery
    assert env.enroll("p-1", (220, 30, 30), role="viewer").status_code == 403
    # operator: cannot change thresholds, run evaluations, reset or clean up
    body = {"accept_threshold": 0.8, "confirm": True}
    assert env.post("/api/config/thresholds", role="operator", json=body).status_code == 403
    assert env.post("/api/evaluation/run", role="operator", json={"dataset": "x"}).status_code == 403
    assert env.post("/api/gallery/reset", role="operator", json={"confirm": "RESET DEMO GALLERY"}).status_code == 403
    assert env.post("/api/maintenance/cleanup", role="operator").status_code == 403
    assert env.get("/api/audit", role="operator").status_code == 403
    # admin: allowed
    assert env.post("/api/config/thresholds", role="admin", json=body).status_code == 200


def test_error_messages_never_leak_secret_keys(env):
    text = env.client.get("/api/gallery", headers={"X-API-Key": "wrong"}).text
    assert all(secret not in text for secret in KEYS.values())


def test_unknown_route_returns_json_not_html(env):
    response = env.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_request_id_header_matches_error_body(env):
    response = env.client.get("/api/gallery")
    assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]


def test_validation_errors_are_422_with_field_details(env):
    response = env.post("/api/config/thresholds", json={"accept_threshold": 7, "confirm": True})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_failed" and error["details"]["errors"]


def test_security_headers_present(env):
    headers = env.client.get("/api/health").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Cache-Control"] == "no-store"


def test_cors_is_limited_to_configured_origins(env):
    allowed = env.client.options("/api/health", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    blocked = env.client.options("/api/health", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in blocked.headers


def test_oversized_request_is_refused_before_it_is_read(tmp_path):
    settings = make_settings(tmp_path, max_upload_mb=1, max_enroll_files=1)  # body cap = 2 MB
    app = create_app(settings, extractor=FakeExtractor(), detector=FakeDetector())
    with TestClient(app) as client:
        big = b"0" * (3 * 1024 * 1024)
        response = client.post("/api/reid/predict", headers={"X-API-Key": KEYS["viewer"]},
                               files={"image": ("big.png", big, "image/png")})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_access_keys_are_off_unless_someone_switches_them_on():
    """The shipped default: nobody has to type a key on a single-user local demo."""
    assert Settings(_env_file=None).auth_required is False


def test_without_access_keys_everyone_is_admin_and_the_interface_is_told_so(tmp_path):
    settings = make_settings(tmp_path, auth_required=False)
    app = create_app(settings, extractor=FakeExtractor(), detector=FakeDetector())
    with TestClient(app) as client:
        assert client.get("/api/gallery").status_code == 200  # no key needed
        assert client.get("/api/auth/me").json() == {"role": "admin", "auth_required": False}
        # even an admin-only route is open, and a stray key is simply ignored
        body = {"accept_threshold": 0.8, "confirm": True}
        assert client.post("/api/config/thresholds", json=body).status_code == 200
        assert client.get("/api/audit", headers={"X-API-Key": "whatever"}).status_code == 200


def test_server_starts_but_reports_not_ready_when_the_model_is_missing(tmp_path):
    app = create_app(make_settings(tmp_path), load_models=False)  # no weights, no fakes
    with TestClient(app) as client:
        readiness = client.get("/api/readiness")
        assert readiness.status_code == 503 and readiness.json()["status"] == "not_ready"
        response = client.post("/api/reid/predict", headers={"X-API-Key": KEYS["viewer"]},
                               data={"mode": "crop"}, files={"image": ("q.png", crop_png((200, 30, 30)), "image/png")})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "model_unavailable"


def test_missing_weights_file_gives_an_actionable_message(tmp_path):
    from app.core.errors import ModelUnavailable
    from app.cv.embedding.registry import get_spec
    from app.cv.embedding.weights import locate_official_weights

    with pytest.raises(ModelUnavailable, match="download_weights"):
        locate_official_weights(get_spec("osnet_ain_x1_0"), tmp_path)


def test_corrupted_weights_are_rejected_by_checksum(tmp_path):
    from app.core.errors import ModelUnavailable
    from app.cv.embedding.registry import get_spec
    from app.cv.embedding.weights import locate_official_weights

    spec = get_spec("osnet_ain_x1_0")
    (tmp_path / spec.weights.filename).write_bytes(b"not the real weights")
    with pytest.raises(ModelUnavailable, match="SHA-256 mismatch"):
        locate_official_weights(spec, tmp_path)


def test_invalid_checkpoint_file_is_handled_gracefully(tmp_path):
    from app.core.errors import ModelUnavailable
    from app.cv.embedding.weights import load_state_dict

    broken = tmp_path / "broken.pt"
    broken.write_bytes(b"garbage")
    with pytest.raises(ModelUnavailable, match="Could not read"):
        load_state_dict(broken)
