"""Lookalike Failure Lab routes: start an experiment, read it, export it, look at its images."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from ...core.errors import NotFound
from ...cv.imaging import encode_jpeg, load_rgb_file
from ...schemas.evaluation import LookalikeRunRequest, RunDetail, RunsPage
from ...services import evaluation_service
from ..deps import AdminRole, RuntimeDep, SessionDep, ViewerRole

router = APIRouter(prefix="/api/lookalike", tags=["lookalike failure lab"])


def _lookalike_run(session, run_id: str):
    run = evaluation_service.get_run(session, run_id)
    if run.kind != "lookalike":
        raise NotFound("No such look-alike experiment.")
    return run


@router.post("/run", response_model=RunDetail, status_code=status.HTTP_202_ACCEPTED,
             summary="Start a look-alike experiment (runs in the background)")
def start(body: LookalikeRunRequest, runtime: RuntimeDep, session: SessionDep, role: AdminRole) -> RunDetail:
    """Mines the most alike pairs of different people, builds a reproducible challenge set, measures the matcher on it,
    and lists its real mistakes. The threshold is chosen on the calibration people only."""
    return evaluation_service.to_detail(runtime.jobs.submit_lookalike(session, body, role.name))


@router.get("/runs", response_model=RunsPage, summary="Past look-alike experiments")
def runs(session: SessionDep, _: ViewerRole,
         limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0) -> RunsPage:
    items, total = evaluation_service.list_runs(session, "lookalike", limit, offset)
    return RunsPage(items=[evaluation_service.to_summary(r) for r in items], total=total)


@router.get("/runs/{run_id}", response_model=RunDetail, summary="Progress and (when finished) the full experiment")
def detail(run_id: str, session: SessionDep, _: ViewerRole) -> RunDetail:
    return evaluation_service.to_detail(_lookalike_run(session, run_id))


@router.get("/runs/{run_id}/export", summary="Download the experiment: JSON (everything), pairs/failures/summary CSV, or Markdown")
def export(run_id: str, session: SessionDep, _: ViewerRole,
           format: Annotated[Literal["json", "md", "pairs_csv", "failures_csv", "summary_csv"], Query()] = "json") -> Response:
    run = _lookalike_run(session, run_id)
    body, media_type = evaluation_service.render_report(run, format)
    return Response(body, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{evaluation_service.report_filename(run, format)}"'})


@router.get("/runs/{run_id}/image", summary="A dataset image this experiment refers to (served as a re-encoded JPEG)")
def image(run_id: str, runtime: RuntimeDep, session: SessionDep, _: ViewerRole,
          ref: Annotated[str, Query(min_length=1, max_length=300)]) -> Response:
    """Only image paths the experiment itself recorded can be fetched - never an arbitrary file name."""
    path = evaluation_service.dataset_image_path(runtime, _lookalike_run(session, run_id), ref)
    return Response(encode_jpeg(load_rgb_file(path), quality=85), media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=600"})
