"""Shared fixtures: a real FastAPI app wired to fake networks and a throw-away database."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.fakes import FakeDetector, FakeExtractor, FakeFaceEngine

KEYS = {"viewer": "viewer-secret", "operator": "operator-secret", "admin": "admin-secret"}


def make_settings(tmp_path, **overrides) -> Settings:
    values = dict(
        data_dir=tmp_path / "data", weights_dir=tmp_path / "weights", datasets_dir=tmp_path / "datasets",
        auth_required=True,  # the default is OFF; most tests exercise the key/role checks, so they switch it on
        viewer_key=KEYS["viewer"], operator_key=KEYS["operator"], admin_key=KEYS["admin"],
        default_accept_threshold=0.70, max_upload_mb=1, query_retention_hours=24,
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)  # _env_file=None: never read a developer's real .env in tests


@dataclass
class Env:
    client: TestClient
    extractor: FakeExtractor
    detector: FakeDetector
    settings: Settings
    runtime: object
    face_engine: FakeFaceEngine | None = None

    def headers(self, role: str = "admin") -> dict[str, str]:
        return {"X-API-Key": KEYS[role]}

    def get(self, path: str, role: str = "viewer", **kwargs):
        return self.client.get(path, headers=self.headers(role), **kwargs)

    def post(self, path: str, role: str = "admin", **kwargs):
        return self.client.post(path, headers=self.headers(role), **kwargs)

    def delete(self, path: str, role: str = "admin", **kwargs):
        return self.client.delete(path, headers=self.headers(role), **kwargs)

    # -- convenience for the most common set-up step ------------------------------------
    def enroll(self, reference_id: str, colour, *, n: int = 2, label: str | None = None, role: str = "operator"):
        from tests.fakes import crop_png

        files = [("images", (f"{reference_id}-{i}.png", crop_png(colour, seed=i), "image/png")) for i in range(n)]
        data = {"reference_id": reference_id, "consent_confirmed": "true", "images_are_crops": "true"}
        if label:
            data["label"] = label
        return self.post("/api/gallery/enroll", role=role, data=data, files=files)

    def enroll_person(self, reference_id: str, body, face, *, n: int = 2, face_px: int = 60, role: str = "operator"):
        """Enrol someone with a body colour and (optionally) a face - see ``tests.fakes.person_png``."""
        from tests.fakes import person_png

        files = [("images", (f"{reference_id}-{i}.png", person_png(body, face, seed=i, face_px=face_px), "image/png")) for i in range(n)]
        data = {"reference_id": reference_id, "consent_confirmed": "true", "images_are_crops": "true"}
        return self.post("/api/gallery/enroll", role=role, data=data, files=files)

    def predict(self, png: bytes, *, mode: str = "crop", role: str = "viewer", **form):
        return self.post("/api/reid/predict", role=role, data={"mode": mode, **form}, files={"image": ("q.png", png, "image/png")})

    def set_policy(self, **fields):
        """Create a new policy version (admin). Defaults keep the body threshold at 0.70."""
        body = {"accept_threshold": 0.70, "confirm": True, **fields}
        return self.post("/api/config/thresholds", json=body)


@pytest.fixture()
def env(tmp_path):
    """Body-only world: the face models are 'not loaded', exactly as on a machine that never downloaded them."""
    settings = make_settings(tmp_path)
    extractor, detector = FakeExtractor(), FakeDetector()
    app = create_app(settings, extractor=extractor, detector=detector)
    with TestClient(app) as client:
        yield Env(client, extractor, detector, settings, app.state.runtime)


@pytest.fixture()
def face_env(tmp_path):
    """Face + body world: fake face engine loaded and the default policy (which asks for face matching)."""
    settings = make_settings(tmp_path)
    extractor, detector, faces = FakeExtractor(), FakeDetector(), FakeFaceEngine()
    app = create_app(settings, extractor=extractor, detector=detector, face_engine=faces)
    with TestClient(app) as client:
        yield Env(client, extractor, detector, settings, app.state.runtime, faces)
