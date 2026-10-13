"""
The numbers on the Overview dashboard.

In plain words: every figure is computed from the database right now. Each one
states its denominator and time window, and a figure that has no data behind it
is returned as ``None`` so the UI can say "Not evaluated" instead of showing a
made-up zero.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import EvaluationRun, Identity, InferenceRecord, InferenceResult, ReferenceImage
from ..evaluation.datasets import discover_datasets
from . import evaluation_service, policy_service
from .runtime import Runtime

LATENCY_WINDOW = 200  # average latency is taken over the most recent N requests


def build_overview(session: Session, runtime: Runtime) -> dict:
    outcomes = dict(session.execute(select(InferenceResult.outcome, func.count()).group_by(InferenceResult.outcome)).all())
    decided = sum(outcomes.get(k, 0) for k in ("accepted", "unknown", "review_required"))
    recent_latency = list(session.scalars(
        select(InferenceRecord.total_ms).order_by(InferenceRecord.created_at.desc()).limit(LATENCY_WINDOW)))

    benchmark = session.scalar(
        select(EvaluationRun).where(EvaluationRun.kind == "evaluation", EvaluationRun.status == "succeeded",
                                    EvaluationRun.dataset_kind == "benchmark").order_by(EvaluationRun.finished_at.desc()).limit(1))
    any_eval = session.scalar(
        select(EvaluationRun).where(EvaluationRun.kind == "evaluation", EvaluationRun.status == "succeeded")
        .order_by(EvaluationRun.finished_at.desc()).limit(1))
    latest = evaluation_service.headline(benchmark) if benchmark else None

    recent_requests = session.scalars(select(InferenceRecord).order_by(InferenceRecord.created_at.desc()).limit(6))
    recent_runs, _ = evaluation_service.list_runs(session, None, 5, 0)
    policy_row = policy_service.get_active(session)

    return {
        "gallery": {
            "identities": session.scalar(select(func.count()).select_from(Identity)) or 0,
            "images": session.scalar(select(func.count()).select_from(ReferenceImage)) or 0,
        },
        "inference": {
            "requests": session.scalar(select(func.count()).select_from(InferenceRecord)) or 0,
            "people_processed": sum(outcomes.values()),
            "outcomes": outcomes,
            "unknown_or_rejected": outcomes.get("unknown", 0),
            "acceptance_rate": (outcomes.get("accepted", 0) / decided) if decided else None,
            "acceptance_rate_definition": "accepted people / people that received a decision "
                                          "(accepted + unknown + review required; processing errors excluded), all time",
            "average_latency_ms": (sum(recent_latency) / len(recent_latency)) if recent_latency else None,
            "latency_window": f"last {LATENCY_WINDOW} requests (pipeline time, excluding the database write)",
        },
        "latest_evaluation": {
            "benchmark_available": benchmark is not None,
            "far": latest["far"] if latest else None,
            "recall": latest["recall"] if latest else None,
            "run_id": benchmark.id if benchmark else None,
            "dataset": benchmark.dataset_name if benchmark else None,
            "note": None if benchmark else (
                "Only smoke-test runs exist - they do not count as benchmark results." if any_eval else "Not evaluated."),
            "definition": "Test-split FAR and DIR@1 (mean over seeds) of the configuration selected on calibration data.",
        },
        "policy": {"version": policy_row.version, "status": policy_row.status, "accept_threshold": policy_row.accept_threshold,
                   "min_margin": policy_row.min_margin,
                   "matching_mode": "face_body" if policy_row.multicue else "body",
                   "face_accept_threshold": (policy_row.multicue or {}).get("face_accept_threshold"),
                   # What is actually in force: a face policy with no face models matches on the body only.
                   "face_matching_active": bool(policy_row.multicue) and runtime.face_engine is not None},
        "readiness": {"embedding_model": runtime.extractor is not None, "detector": runtime.detector is not None,
                      "face_models": runtime.face_engine is not None},
        "datasets": [d.to_dict() for d in discover_datasets(runtime.settings.datasets_dir)],
        "recent_requests": [
            {"request_id": r.request_id, "created_at": r.created_at, "n_people": r.n_people, "total_ms": r.total_ms,
             "outcomes": [x.outcome for x in r.results]} for r in recent_requests
        ],
        "recent_runs": [evaluation_service.to_summary(r).model_dump(mode="json") for r in recent_runs],
    }
