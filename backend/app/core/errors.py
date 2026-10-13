"""
Application errors.

In plain words: whenever something goes wrong in a way the *user* should know
about (bad upload, unknown identity, model not ready ...) the code raises one
of these small exception classes. A single handler in ``main.py`` turns them
into the same JSON shape every time:

    {"error": {"code": "not_found", "message": "...", "request_id": "...", "details": {...}}}

That keeps the API predictable and keeps HTTP details out of the business logic.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class. Subclasses only set the HTTP status and a stable machine code."""

    status_code: int = 400
    code: str = "bad_request"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_failed"


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class PayloadTooLarge(AppError):
    status_code = 413
    code = "payload_too_large"


class UnsupportedImage(AppError):
    status_code = 415
    code = "unsupported_image"


class NoPersonDetected(AppError):
    status_code = 422
    code = "no_person_detected"


class ModelUnavailable(AppError):
    """A model (embedding backbone or detector) is not loaded and cannot be used."""

    status_code = 503
    code = "model_unavailable"


class ProcessingFailed(AppError):
    status_code = 500
    code = "processing_failed"
