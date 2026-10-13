"""The built-in example demo: an open-set analysis on bundled public-domain photos. Read-only for the real gallery."""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter
from fastapi.responses import FileResponse

from ...schemas.demo import DemoCaseResult, DemoInfo, DemoPrepared
from ...services import demo_service
from ..deps import RuntimeDep, SessionDep, ViewerRole

router = APIRouter(prefix="/api/demo", tags=["example demo"])


@router.get("", response_model=DemoInfo, summary="The example's people, photos and the rules it is judged under")
def info(runtime: RuntimeDep, session: SessionDep, _: ViewerRole) -> DemoInfo:
    return demo_service.info(runtime, session)


@router.post("/prepare", response_model=DemoPrepared, summary="Build the private example gallery (in memory; nothing is saved)")
def prepare(runtime: RuntimeDep, session: SessionDep, _: ViewerRole) -> DemoPrepared:
    return demo_service.prepare(runtime, session)


@router.post("/cases/{case_id}", response_model=DemoCaseResult, summary="Analyse one example photo (face + body, and clothes only)")
def analyse(case_id: str, runtime: RuntimeDep, session: SessionDep, _: ViewerRole) -> DemoCaseResult:
    return demo_service.analyse_case(runtime, session, case_id)


@router.delete("/sandbox", summary="Forget the private example gallery")
def forget(runtime: RuntimeDep, _: ViewerRole) -> dict:
    demo_service.forget(runtime)
    return {"ok": True}


@router.get("/files/{relative_path:path}", summary="One of the example photos (only files named in the manifest)")
def files(relative_path: str, runtime: RuntimeDep, _: ViewerRole) -> FileResponse:
    path = demo_service.served_file(runtime, relative_path)
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "image/jpeg", headers={"Cache-Control": "private, max-age=300"})
