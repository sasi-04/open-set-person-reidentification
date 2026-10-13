"""Evaluation routes: datasets, runs, calibration, reports."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from ...evaluation.datasets import discover_datasets
from ...schemas.evaluation import (
    CalibrationRunRequest,
    CheckpointModel,
    DatasetModel,
    EvaluationRunRequest,
    RunDetail,
    RunsPage,
    SandboxRequest,
)
from ...services import evaluation_service
from ..deps import AdminRole, RuntimeDep, SessionDep, ViewerRole

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.get("/datasets", response_model=list[DatasetModel], summary="Datasets found in the datasets/ folder")
def datasets(runtime: RuntimeDep, _: ViewerRole) -> list[DatasetModel]:
    return [DatasetModel(**info.to_dict()) for info in discover_datasets(runtime.settings.datasets_dir)]


@router.get("/checkpoints", response_model=list[CheckpointModel], summary="Fine-tuned backbones available for evaluation")
def checkpoints(runtime: RuntimeDep, _: ViewerRole) -> list[CheckpointModel]:
    return evaluation_service.list_checkpoints(runtime)


@router.post("/run", response_model=RunDetail, status_code=status.HTTP_202_ACCEPTED,
             summary="Start a full evaluation (runs in the background)")
def start_evaluation(body: EvaluationRunRequest, runtime: RuntimeDep, session: SessionDep, role: AdminRole) -> RunDetail:
    run = runtime.jobs.submit_evaluation(session, body, role.name)
    return evaluation_service.to_detail(run)


@router.post("/calibrate", response_model=RunDetail, status_code=status.HTTP_202_ACCEPTED,
             summary="Select a threshold on the calibration split (never reads the test split)")
def start_calibration(body: CalibrationRunRequest, runtime: RuntimeDep, session: SessionDep, role: AdminRole) -> RunDetail:
    run = runtime.jobs.submit_calibration(session, body, role.name)
    return evaluation_service.to_detail(run)


@router.get("/runs", response_model=RunsPage, summary="Run history")
def runs(
    session: SessionDep, _: ViewerRole,
    kind: Annotated[Literal["evaluation", "calibration", "lookalike"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunsPage:
    items, total = evaluation_service.list_runs(session, kind, limit, offset)
    return RunsPage(items=[evaluation_service.to_summary(r) for r in items], total=total)


@router.get("/runs/{run_id}", response_model=RunDetail, summary="Status, progress and (when finished) results of a run")
def run_detail(run_id: str, session: SessionDep, _: ViewerRole) -> RunDetail:
    return evaluation_service.to_detail(evaluation_service.get_run(session, run_id))


@router.post("/runs/{run_id}/cancel", response_model=RunDetail, summary="Cancel a queued or running job")
def cancel(run_id: str, runtime: RuntimeDep, session: SessionDep, role: AdminRole) -> RunDetail:
    return evaluation_service.to_detail(runtime.jobs.request_cancel(session, run_id, role.name))


@router.get("/runs/{run_id}/report", summary="Download the report of a finished run")
def report(
    run_id: str, session: SessionDep, _: ViewerRole,
    format: Annotated[Literal["json", "md", "html", "pairs_csv", "failures_csv", "summary_csv", "frames_csv"], Query()] = "html",
) -> Response:
    run = evaluation_service.get_run(session, run_id)
    body, media_type = evaluation_service.render_report(run, format)
    return Response(body, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{evaluation_service.report_filename(run, format)}"'})


@router.get("/runs/{run_id}/sandbox", summary="Threshold sandbox: what this run lets you explore")
def sandbox_info(run_id: str, session: SessionDep, _: ViewerRole) -> dict:
    return evaluation_service.sandbox_info(evaluation_service.get_run(session, run_id))


@router.post("/runs/{run_id}/sandbox", summary="Threshold sandbox: try a trial rule on the run's fixed per-query scores")
def sandbox_explore(run_id: str, body: SandboxRequest, session: SessionDep, _: ViewerRole) -> dict:
    """Re-counts the stored table under a trial threshold/margin. Never changes the active decision policy."""
    return evaluation_service.sandbox_explore(evaluation_service.get_run(session, run_id), body)
