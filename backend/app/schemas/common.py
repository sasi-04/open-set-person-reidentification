"""Shared API shapes: errors and pagination."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable error code, e.g. 'not_found'.")
    message: str = Field(description="Human-readable explanation.")
    request_id: str = Field(description="Quote this when reporting a problem.")
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody
