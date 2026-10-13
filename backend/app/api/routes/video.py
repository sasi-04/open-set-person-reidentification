"""Video Explorer routes: upload a prerecorded clip, follow its progress, read per-frame decisions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from sqlalchemy import delete

from ...core.errors import Conflict, NotFound
from ...db.models import EvaluationRun
from ...schemas.evaluation import RunDetail, RunsPage
from ...services import evaluation_service, video_service
from ...services.audit import record_audit
from ..deps import OperatorRole, RuntimeDep, SessionDep, ViewerRole

router = APIRouter(prefix="/api/video", tags=["video explorer"])


def _video_job(session, run_id: str) -> EvaluationRun:
    run = evaluation_service.get_run(session, run_id)
    if run.kind != "video":
        raise NotFound("No such video job.")
    return run


@router.get("/limits", summary="What the video upload accepts")
def limits(runtime: RuntimeDep, _: ViewerRole) -> dict:
    s = runtime.settings
    return {
        "max_megabytes": s.max_video_mb, "max_seconds": s.max_video_seconds, "max_frames": s.max_video_frames,
        "max_frame_side": s.max_video_side, "extensions": list(video_service.ALLOWED_EXTENSIONS),
        "detector_ready": runtime.detector is not None, "embedding_ready": runtime.extractor is not None,
        "frame_previews_kept_hours": s.query_retention_hours,
        "scope": "Frame-by-frame re-identification of a prerecorded clip. It is not multi-object tracking.",
    }


@router.post("/analyze", response_model=RunDetail, status_code=status.HTTP_202_ACCEPTED,
             summary="Upload a video and re-identify the people in sampled frames (runs in the background)")
def analyze(
    runtime: RuntimeDep, session: SessionDep, role: ViewerRole,
    video: Annotated[UploadFile, File(description="MP4/MOV, AVI, MKV or WebM")],
    every_seconds: Annotated[float, Form(description="Take one frame every N seconds")] = 1.0,
    max_frames: Annotated[int, Form(description="Stop after this many sampled frames")] = 30,
) -> RunDetail:
    runtime.require_extractor()
    runtime.require_detector()
    video_service.validate_sampling(runtime.settings, every_seconds, max_frames)
    path, container, _size = video_service.save_upload(runtime.settings, video)
    try:
        probe = video_service.probe_video(path, runtime.settings, container)
    except BaseException:
        path.unlink(missing_ok=True)  # an unusable video is deleted on the spot
        raise
    run = runtime.jobs.submit_video(
        session, stored_path=path, original_name=video_service.safe_display_name(video.filename), probe=probe,
        every_seconds=every_seconds, max_frames=max_frames, role_name=role.name,
    )
    return evaluation_service.to_detail(run)


@router.get("/jobs", response_model=RunsPage, summary="Past video jobs")
def jobs(session: SessionDep, _: ViewerRole,
         limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0) -> RunsPage:
    items, total = evaluation_service.list_runs(session, "video", limit, offset)
    return RunsPage(items=[evaluation_service.to_summary(r) for r in items], total=total)


@router.get("/jobs/{run_id}", response_model=RunDetail, summary="Progress and (when finished) every frame's decisions")
def job(run_id: str, session: SessionDep, _: ViewerRole) -> RunDetail:
    return evaluation_service.to_detail(_video_job(session, run_id))


@router.post("/jobs/{run_id}/cancel", response_model=RunDetail, summary="Stop a queued or running video job")
def cancel(run_id: str, runtime: RuntimeDep, session: SessionDep, role: ViewerRole) -> RunDetail:
    _video_job(session, run_id)
    return evaluation_service.to_detail(runtime.jobs.request_cancel(session, run_id, role.name))


@router.delete("/jobs/{run_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a finished video job and its frame previews")
def delete_job(run_id: str, runtime: RuntimeDep, session: SessionDep, role: OperatorRole) -> Response:
    run = _video_job(session, run_id)
    if run.status in evaluation_service.ACTIVE_STATES:
        raise Conflict("The job is still running. Cancel it first.")
    video_service.delete_artifacts(runtime.settings, run_id)
    session.execute(delete(EvaluationRun).where(EvaluationRun.id == run_id))
    record_audit(session, role.name, "video.delete", run_id)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/jobs/{run_id}/frames/{index}", summary="Preview of one sampled frame (only during the retention window)")
def frame(run_id: str, index: int, runtime: RuntimeDep, session: SessionDep, _: ViewerRole) -> Response:
    _video_job(session, run_id)
    path = video_service.frame_path(runtime.settings, run_id, index)
    return Response(path.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@router.get("/jobs/{run_id}/export", summary="Download the per-frame decisions (JSON or CSV)")
def export(run_id: str, session: SessionDep, _: ViewerRole,
           format: Annotated[str, Query(pattern="^(json|frames_csv)$")] = "json") -> Response:
    run = _video_job(session, run_id)
    body, media_type = evaluation_service.render_report(run, format)
    return Response(body, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{evaluation_service.report_filename(run, format)}"'})
