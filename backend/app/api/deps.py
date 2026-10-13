"""
Shared dependencies for the API routes.

In plain words: small helpers that every route file uses - "give me the
runtime", "give me a database session", "read this upload but refuse files that
are too big".
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request, UploadFile
from sqlalchemy.orm import Session

from ..core.errors import PayloadTooLarge
from ..core.security import Role, current_role, require_role
from ..services.gallery_service import UploadedFile
from ..services.runtime import Runtime


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def get_session(runtime: Annotated[Runtime, Depends(get_runtime)]) -> Iterator[Session]:
    session = runtime.session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
SessionDep = Annotated[Session, Depends(get_session)]

AnyRole = Annotated[Role, Depends(current_role)]
ViewerRole = Annotated[Role, Depends(require_role(Role.VIEWER))]
OperatorRole = Annotated[Role, Depends(require_role(Role.OPERATOR))]
AdminRole = Annotated[Role, Depends(require_role(Role.ADMIN))]


def read_upload(file: UploadFile, limit_bytes: int) -> UploadedFile:
    """Read at most ``limit_bytes`` of an upload; bigger files are refused without reading the rest."""
    data = file.file.read(limit_bytes + 1)
    if len(data) > limit_bytes:
        raise PayloadTooLarge(f"'{file.filename}' is larger than the {limit_bytes // 2**20} MB limit.")
    return UploadedFile(filename=file.filename or "upload", content_type=file.content_type, data=data)
