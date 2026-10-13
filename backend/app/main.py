"""
The FastAPI application.

In plain words: ``create_app()`` assembles the server. At startup (the
"lifespan") it opens the database, loads the models ONCE, rebuilds the
in-memory gallery index, makes sure a decision policy exists, tidies old
data, and starts the background-job worker. Middleware adds a request ID to
every call, safe response headers, and refuses obviously oversized uploads
before reading them. All errors - ours, validation errors, even unknown URLs -
come back in the same JSON shape.

Run it with:  uvicorn app.main:app --port 8000     (from the backend folder; or scripts/start.ps1)
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .api.routes import config as config_routes
from .api.routes import demo as demo_routes
from .api.routes import evaluation as evaluation_routes
from .api.routes import gallery as gallery_routes
from .api.routes import health as health_routes
from .api.routes import lookalike as lookalike_routes
from .api.routes import reid as reid_routes
from .api.routes import video as video_routes
from .core.config import REPO_ROOT, Settings, get_settings
from .core.errors import AppError
from .core.logging import configure_logging, request_id_var
from .core.security import warn_if_misconfigured
from .db.database import init_db, make_engine, make_session_factory
from .services import face_service, maintenance_service, policy_service
from .services.evaluation_service import EvaluationJobs
from .services.runtime import Runtime

logger = logging.getLogger(__name__)
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def create_app(
    settings: Settings | None = None, *, load_models: bool = True, extractor=None, detector=None, face_engine=None,
) -> FastAPI:
    """``extractor`` / ``detector`` / ``face_engine`` let tests inject fakes instead of loading real networks."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        settings.ensure_directories()
        warn_if_misconfigured(settings)

        engine = make_engine(settings.effective_database_url)
        init_db(engine)
        session_factory = make_session_factory(engine)
        runtime = Runtime.create(settings, session_factory, load_models=load_models, extractor=extractor, detector=detector,
                                 face_engine=face_engine)
        runtime.jobs = EvaluationJobs(runtime)

        with session_factory() as session:
            policy_service.ensure_default_policy(session, settings)
            session.commit()
            runtime.jobs.recover_interrupted(session)
            session.commit()
            runtime.sync_gallery(session)  # build the in-memory index (marks stale embeddings)
            session.commit()
            if runtime.face_engine is not None:  # galleries enrolled before face matching existed get their faces analysed once
                face_service.analyse_missing_faces(session, runtime, "system", limit=face_service.STARTUP_ANALYSIS_LIMIT)
            maintenance_service.run_cleanup(session, runtime, "system")

        app.state.runtime = runtime
        logger.info("OpenID Vision %s ready (embedding model: %s)", __version__, runtime.fingerprint or "UNAVAILABLE")
        yield
        runtime.jobs.shutdown()
        engine.dispose()

    app = FastAPI(
        title="OpenID Vision API",
        version=__version__,
        description=(
            "Research prototype: open-set person re-identification under low inter-class variance. "
            "Retrieval is NOT identification - every match is accepted, rejected or sent to review by an explicit, "
            "versioned policy. Not a production surveillance or identity-verification service."
        ),
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"], allow_headers=["X-API-Key", "Content-Type"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    # Reject absurdly large uploads from the Content-Length header before reading any of the body.
    max_body = (settings.max_upload_bytes * settings.max_enroll_files) + 2**20
    max_video_body = settings.max_video_bytes + 2**20  # only the video upload route may carry a request this large

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500  # what we log if the request blows up before a response exists
        try:
            declared = request.headers.get("content-length")
            limit = max_video_body if request.url.path == "/api/video/analyze" else max_body
            if declared and declared.isdigit() and int(declared) > limit:
                response = _error_response(413, "payload_too_large", "The request body is too large.", request_id)
            else:
                response = await call_next(request)
            status_code = response.status_code
        finally:
            logger.info("%s %s -> %s in %.0f ms", request.method, request.url.path, status_code,
                        (time.perf_counter() - started) * 1000)
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    # ---------------------------------------------------------- uniform errors
    def rid(request: Request) -> str:
        return getattr(request.state, "request_id", "-")

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, rid(request), exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        problems = [{"field": ".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]), "problem": e["msg"]} for e in exc.errors()]
        message = "; ".join(f"{p['field']}: {p['problem']}" for p in problems[:3])
        return _error_response(422, "validation_failed", f"Invalid request - {message}", rid(request), {"errors": problems})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _error_response(exc.status_code, code, str(exc.detail), rid(request))

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")  # full traceback goes to the log, never to the client
        return _error_response(500, "internal_error", "Something went wrong on the server.", rid(request))

    for module in (health_routes, reid_routes, gallery_routes, evaluation_routes, lookalike_routes, video_routes, config_routes, demo_routes):
        app.include_router(module.router)

    _mount_frontend(app)
    return app


def _error_response(status: int, code: str, message: str, request_id: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id, "details": details or {}}},
    )


def _mount_frontend(app: FastAPI) -> None:
    """If the frontend has been built (npm run build) serve it from the same port - handy for demos."""
    if not (FRONTEND_DIST / "index.html").is_file():
        return
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise StarletteHTTPException(404, "Not found")
        candidate = (FRONTEND_DIST / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(FRONTEND_DIST.resolve()):
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")  # client-side routing


app = create_app()
