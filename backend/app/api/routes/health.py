"""Health, readiness, "who am I" and the dashboard overview."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ... import __version__
from ...services import overview_service
from ..deps import AnyRole, RuntimeDep, SessionDep, ViewerRole

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", summary="Is the server process alive?")
def health() -> dict:
    """Always cheap and always public: it only says the process is running."""
    return {"status": "ok", "service": "open-set-reid-lab", "version": __version__, "time": datetime.now(UTC)}


@router.get("/readiness", summary="Can the server actually do re-identification right now?")
def readiness(runtime: RuntimeDep) -> JSONResponse:
    settings = runtime.settings
    database_ok = True
    try:
        with runtime.session_factory() as session:
            session.execute(text("SELECT 1"))
    except Exception:  # reported, not hidden
        database_ok = False

    embedding_ok = runtime.extractor is not None
    detector_ok = runtime.detector is not None
    snapshot = runtime.index.snapshot
    status = "ready" if (embedding_ok and database_ok and detector_ok) else ("degraded" if embedding_ok and database_ok else "not_ready")
    body = {
        "status": status,
        "components": {
            "database": {"ok": database_ok},
            "embedding_model": {"ok": embedding_ok, **(runtime.extractor.info() if embedding_ok else {"error": runtime.extractor_error})},
            "detector": {"ok": detector_ok, **(runtime.detector.info() if detector_ok else {"error": runtime.detector_error})},
            "gallery_index": {"version": snapshot.version, "identities": snapshot.n_identities, "images": snapshot.n_images},
            # Optional: without the face models the system matches on the body only (and says so) - it is never "not ready" for that.
            "face_models": {"ok": runtime.face_engine is not None, "enabled": settings.face_matching,
                            **(runtime.face_engine.info() if runtime.face_engine else {"error": runtime.face_error})},
            "device": runtime.device_info,
            "auth": {"required": settings.auth_required},
        },
        "notes": (["'degraded' means the person detector is missing: crop and box modes still work."] if status == "degraded" else [])
        + ([f"Face models are not loaded - matching uses the body only. {runtime.face_error}"] if settings.face_matching and runtime.face_engine is None else []),
    }
    return JSONResponse(body, status_code=200 if status != "not_ready" else 503)


@router.get("/auth/me", summary="Which role do I have, and does this server ask for an access key at all?")
def whoami(role: AnyRole, runtime: RuntimeDep) -> dict:
    # With keys switched off (the default) every caller is an admin and the interface never shows a key screen.
    return {"role": role.name.lower(), "auth_required": runtime.settings.auth_required}


@router.get("/overview", summary="Real numbers for the dashboard")
def overview(session: SessionDep, runtime: RuntimeDep, _: ViewerRole) -> dict:
    return overview_service.build_overview(session, runtime)
