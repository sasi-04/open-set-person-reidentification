"""
Background evaluation and calibration jobs.

In plain words: an evaluation can take minutes on a CPU, so it must never block
the web server. Submitting a job writes a ``queued`` row and hands the work to a
single background thread. That thread updates the SAME row as it goes (stage,
progress 0-1) so the browser can poll real progress. A job can be cancelled
(checked between batches), can fail (the error is stored, the server keeps
running), and is marked as interrupted if the server restarts while it runs.

One worker is deliberate: two evaluations at once would only fight over the
same CPU cores and slow each other down.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.device import resolve_device
from ..core.errors import Conflict, NotFound, ValidationFailed
from ..db.database import session_scope
from ..db.models import EvaluationRun
from ..evaluation import lookalike_export, sandbox
from ..evaluation.ablation import DEFAULT_VARIANT_KEYS
from ..evaluation.calibration import OperatingTarget
from ..evaluation.datasets import DatasetInfo, find_dataset
from ..evaluation.embedding_store import EvaluationCancelled
from ..evaluation.lookalike import LookalikeRequest, run_lookalike
from ..evaluation.protocol import ProtocolConfig
from ..evaluation.report import render_html, render_markdown
from ..evaluation.runner import (
    CalibrationRequest,
    EvaluationRequest,
    make_extractor_factory,
    run_calibration,
    run_evaluation,
)
from ..schemas.evaluation import (
    CalibrationRunRequest,
    CheckpointModel,
    EvaluationRunRequest,
    LookalikeRunRequest,
    ProtocolOptions,
    RunDetail,
    RunSummary,
    SandboxRequest,
    TargetOptions,
)
from . import video_service
from .audit import record_audit
from .runtime import Runtime

logger = logging.getLogger(__name__)

ACTIVE_STATES = ("queued", "running")


def _aware(moment: datetime | None) -> datetime | None:
    return None if moment is None else (moment if moment.tzinfo else moment.replace(tzinfo=UTC))


# ---------------------------------------------------------------------------------
# Translating API options into runner requests
# ---------------------------------------------------------------------------------
def _protocol(options: ProtocolOptions, seed: int = 0) -> ProtocolConfig:
    return ProtocolConfig(
        seed=seed, dev_fraction=options.dev_fraction, calibration_fraction=options.calibration_fraction,
        gallery_shots=options.gallery_shots, max_identities_per_split=options.max_identities_per_split,
        max_images_per_identity=options.max_images_per_identity, cross_camera=options.cross_camera,
    )


def _target(options: TargetOptions) -> OperatingTarget:
    return OperatingTarget(options.mode, options.target_recall, options.target_far, options.recall_metric)


def _require_dataset(runtime: Runtime, name: str) -> DatasetInfo:
    info = find_dataset(runtime.settings.datasets_dir, name)
    if info is None:
        raise NotFound(
            f"Dataset '{name}' was not found in {runtime.settings.datasets_dir}. "
            "See the README section 'Dataset acquisition'."
        )
    if not info.available:
        raise ValidationFailed(f"Dataset '{name}' cannot be used: {' '.join(info.problems)}")
    return info


class EvaluationJobs:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="evaluation")
        self._cancel: dict[str, threading.Event] = {}

    # ------------------------------------------------------------ lifecycle
    def recover_interrupted(self, session: Session) -> int:
        """Jobs that were running when the server stopped can never finish: say so."""
        stuck = list(session.scalars(select(EvaluationRun).where(EvaluationRun.status.in_(ACTIVE_STATES))))
        for run in stuck:
            run.status, run.error, run.finished_at = "failed", "Interrupted: the server restarted while this job was running.", datetime.now(UTC)
        return len(stuck)

    def shutdown(self) -> None:
        for event in self._cancel.values():
            event.set()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------ submitting
    def _submit(self, session: Session, *, kind: str, dataset_name: str, dataset_kind: str, config: dict,
                role_name: str) -> EvaluationRun:
        """Queue one job. Only ONE job runs at a time: two would just fight over the same few CPU cores."""
        if session.scalar(select(func.count()).select_from(EvaluationRun).where(EvaluationRun.status.in_(ACTIVE_STATES))):
            raise Conflict("Another job (evaluation, calibration, look-alike analysis or video) is already running. "
                           "Wait for it to finish, or cancel it.")
        run = EvaluationRun(
            id=uuid.uuid4().hex, kind=kind, status="queued", stage="Queued", progress=0.0, config=config,
            dataset_name=dataset_name, dataset_kind=dataset_kind, created_by=role_name.lower(),
        )
        session.add(run)
        record_audit(session, role_name, f"{kind}.start", run.id, dataset=dataset_name)
        session.commit()
        self._cancel[run.id] = threading.Event()
        self._pool.submit(self._execute, run.id)
        return run

    def submit_evaluation(self, session: Session, body: EvaluationRunRequest, role_name: str) -> EvaluationRun:
        dataset = _require_dataset(self.runtime, body.dataset)
        checkpoint = self._checkpoint_path(body.finetuned_checkpoint)
        variants = tuple(body.variants) if body.variants else DEFAULT_VARIANT_KEYS
        if checkpoint is not None and "thr_margin_finetuned" not in variants:
            variants += ("thr_margin_finetuned",)
        config = body.model_dump()
        config["variants"] = list(variants)
        return self._submit(session, kind="evaluation", dataset_name=dataset.name, dataset_kind=dataset.kind,
                            config=config, role_name=role_name)

    def submit_calibration(self, session: Session, body: CalibrationRunRequest, role_name: str) -> EvaluationRun:
        dataset = _require_dataset(self.runtime, body.dataset)
        self.runtime.require_extractor()  # calibration must match the LIVE model, so it has to be loaded
        return self._submit(session, kind="calibration", dataset_name=dataset.name, dataset_kind=dataset.kind,
                            config=body.model_dump(), role_name=role_name)

    def submit_lookalike(self, session: Session, body: LookalikeRunRequest, role_name: str) -> EvaluationRun:
        dataset = _require_dataset(self.runtime, body.dataset)
        self._checkpoint_path(body.finetuned_checkpoint)  # fail now, not after minutes of embedding, if the name is wrong
        return self._submit(session, kind="lookalike", dataset_name=dataset.name, dataset_kind=dataset.kind,
                            config=body.model_dump(), role_name=role_name)

    def submit_video(self, session: Session, *, stored_path: Path, original_name: str, probe: video_service.VideoProbe,
                     every_seconds: float, max_frames: int, role_name: str) -> EvaluationRun:
        """Queue a prerecorded video. The job owns ``stored_path`` and deletes it when it ends."""
        config = {"stored_name": stored_path.name, "original_name": original_name, "every_seconds": every_seconds,
                  "max_frames": max_frames, "probe": probe.to_dict()}
        try:
            return self._submit(session, kind="video", dataset_name=original_name[:120], dataset_kind="video",
                                config=config, role_name=role_name)
        except Exception:
            stored_path.unlink(missing_ok=True)  # refused (e.g. another job is running): do not keep the upload
            raise

    def _checkpoint_path(self, name: str | None) -> Path | None:
        if name is None:
            return None
        folder = (self.runtime.settings.weights_dir / "finetuned").resolve()
        path = (folder / name).resolve()
        if path.parent != folder or not path.is_file():  # a bare file name inside one folder, nothing else
            raise ValidationFailed(f"Fine-tuned checkpoint '{name}' was not found in {folder}.")
        return path

    def request_cancel(self, session: Session, run_id: str, role_name: str) -> EvaluationRun:
        run = session.get(EvaluationRun, run_id)
        if run is None:
            raise NotFound("No such run.")
        if run.status not in ACTIVE_STATES:
            raise Conflict(f"The run is already {run.status}; it cannot be cancelled.")
        run.cancel_requested = True
        run.stage = "Cancelling..."
        record_audit(session, role_name, "evaluation.cancel", run_id)
        session.commit()
        if event := self._cancel.get(run_id):
            event.set()
        return run

    # ------------------------------------------------------------ the worker
    def _update(self, run_id: str, **fields) -> None:
        with session_scope(self.runtime.session_factory) as session:
            run = session.get(EvaluationRun, run_id)
            if run:
                for key, value in fields.items():
                    setattr(run, key, value)

    def _execute(self, run_id: str) -> None:
        event = self._cancel.get(run_id, threading.Event())
        factory = self.runtime.session_factory
        try:
            with session_scope(factory) as session:
                run = session.get(EvaluationRun, run_id)
                if run is None or run.status != "queued":
                    return
                if run.cancel_requested:
                    run.status, run.stage, run.finished_at = "cancelled", "Cancelled before it started", datetime.now(UTC)
                    return
                run.status, run.stage, run.started_at = "running", "Starting", datetime.now(UTC)
                kind, config, dataset_name = run.kind, dict(run.config), run.dataset_name

            last = {"stage": "", "fraction": -1.0}

            def progress(stage: str, fraction: float) -> None:
                if stage != last["stage"] or fraction - last["fraction"] >= 0.01:
                    last.update(stage=stage, fraction=fraction)
                    self._update(run_id, stage=stage, progress=round(min(max(fraction, 0.0), 0.999), 4))

            result = self._run(run_id, kind, config, dataset_name, progress, event.is_set)
            self._save_report_files(run_id, result)
            self._update(run_id, status="succeeded", stage="Done", progress=1.0, result=result, finished_at=datetime.now(UTC))
        except EvaluationCancelled:
            self._update(run_id, status="cancelled", stage="Cancelled", finished_at=datetime.now(UTC))
            if kind == "video":
                video_service.delete_artifacts(self.runtime.settings, run_id)  # a cancelled video keeps no previews
        except Exception as exc:  # the job fails; the server does not
            logger.exception("Job %s failed", run_id)
            message = getattr(exc, "message", None) or str(exc) or exc.__class__.__name__
            self._update(run_id, status="failed", stage="Failed", error=message[:800], finished_at=datetime.now(UTC))
        finally:
            self._cancel.pop(run_id, None)

    def _run(self, run_id: str, kind: str, config: dict, dataset_name: str, progress, cancelled) -> dict:
        settings = self.runtime.settings
        if kind == "video":
            path = settings.video_upload_dir / config["stored_name"]
            try:
                return video_service.process_video(self.runtime, run_id, config, path, progress, cancelled)
            finally:
                path.unlink(missing_ok=True)  # the original upload is never kept, whatever happened

        info = _require_dataset(self.runtime, dataset_name)
        device = self.runtime.device or resolve_device(settings.device)
        factory = make_extractor_factory(
            settings.embedding_model, settings.weights_dir, device, settings.embedding_batch_size, settings.fold_batch_norm
        )

        if kind == "calibration":
            body = CalibrationRunRequest(**config)
            request = CalibrationRequest(
                dataset=info.name, target=_target(body.target), use_margin=body.use_margin,
                use_flip_tta=settings.use_flip_tta, seed=body.seed, protocol=_protocol(body.protocol, body.seed),
                checkpoint=settings.embedding_checkpoint,
            )
            return run_calibration(info, request, cache_dir=settings.cache_dir, make_extractor=factory,
                                   progress=progress, cancelled=cancelled)

        if kind == "lookalike":
            body = LookalikeRunRequest(**config)
            request = LookalikeRequest(
                dataset=info.name, seed=body.seed, target=_target(body.target), protocol=_protocol(body.protocol, body.seed),
                mining_split=body.mining_split, top_pairs=body.top_pairs, images_per_pair=body.images_per_pair,
                max_genuine_pairs=body.max_genuine_pairs, max_failures=body.max_failures, use_margin=body.use_margin,
                finetuned_checkpoint=self._checkpoint_path(body.finetuned_checkpoint),
            )
            return run_lookalike(info, request, cache_dir=settings.cache_dir, make_extractor=factory, experiment_id=run_id,
                                 progress=progress, cancelled=cancelled)

        body = EvaluationRunRequest(**config)
        request = EvaluationRequest(
            dataset=info.name, seeds=tuple(body.seeds), target=_target(body.target), variants=tuple(body.variants or DEFAULT_VARIANT_KEYS),
            protocol=_protocol(body.protocol), bootstrap_samples=body.bootstrap_samples,
            finetuned_checkpoint=self._checkpoint_path(body.finetuned_checkpoint),
        )
        return run_evaluation(info, request, cache_dir=settings.cache_dir, make_extractor=factory,
                              progress=progress, cancelled=cancelled)

    def _save_report_files(self, run_id: str, result: dict) -> None:
        folder = self.runtime.settings.report_dir
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{run_id}.json").write_text(json.dumps(result), encoding="utf-8")
        kind = result.get("kind")
        if kind == "video":
            return  # the JSON is the record; there is no written report for a video
        writer = lookalike_export.render_markdown if kind == "lookalike" else render_markdown
        (folder / f"{run_id}.md").write_text(writer(result), encoding="utf-8")


# ---------------------------------------------------------------------------------
# Reading runs
# ---------------------------------------------------------------------------------
def headline(run: EvaluationRun) -> dict | None:
    result = run.result
    if run.status != "succeeded" or not result:
        return None
    if run.kind == "video":
        summary = result["summary"]
        return {"frames_processed": summary["frames_processed"], "people_detected": summary["people_detected"],
                "outcomes": summary["outcomes"], "is_benchmark": False}
    if run.kind == "lookalike":
        baseline = result["models"]["baseline"]
        challenge = baseline["challenge"]
        return {
            "mining_split": result["metadata"]["request"]["mining_split"], "target_achieved": baseline["calibration"]["target_achieved"],
            "threshold": baseline["rule"]["threshold"], "challenge_far": challenge["far_on_challenge_set"],
            "all_pairs_far": challenge["far_all_pairs_reference"], "challenge_tar": challenge["tar"],
            "improved_status": result["models"]["improved"]["status"], "is_benchmark": result["metadata"]["is_benchmark"],
        }
    if run.kind == "calibration":
        selected = result["selected"]
        return {
            "target_achieved": selected["target_achieved"], "threshold": selected["threshold"],
            "min_margin": selected["min_margin"], "calibration_far": selected["calibration"]["far"],
            "calibration_recall": selected["calibration"]["dir_at_rank"]["1"],
            "model_fingerprint": result["model_fingerprint"], "is_benchmark": result["metadata"]["is_benchmark"],
            "target": result["metadata"]["operating_target"],
        }
    chosen = (result.get("selected_variant") or {}).get("key")
    summary = (result["variants"].get(chosen) or {}).get("summary") if chosen else None
    return {
        "selected_variant": chosen,
        "far": summary["far"]["mean"] if summary else None,
        "recall": summary["dir1"]["mean"] if summary else None,
        "rank1": summary["rank1"]["mean"] if summary else None,
        "mAP": summary["mAP"]["mean"] if summary else None,
        "is_benchmark": result["metadata"]["is_benchmark"],
    }


def to_summary(run: EvaluationRun) -> RunSummary:
    return RunSummary(
        run_id=run.id, kind=run.kind, status=run.status, stage=run.stage, progress=run.progress, dataset=run.dataset_name,
        dataset_kind=run.dataset_kind, created_at=_aware(run.created_at), started_at=_aware(run.started_at),
        finished_at=_aware(run.finished_at), headline=headline(run), error=run.error,
    )


def to_detail(run: EvaluationRun) -> RunDetail:
    result = run.result
    if result and "sandbox" in result:
        # The stored per-query table can be large and the screens do not draw it: it is served by the sandbox
        # endpoint instead. The full stored result (with the table) is still what the JSON report contains.
        result = {**{k: v for k, v in result.items() if k != "sandbox"}, "sandbox_available": result["sandbox"] is not None}
    return RunDetail(**to_summary(run).model_dump(), config=run.config, result=result, cancel_requested=run.cancel_requested)


def list_checkpoints(runtime: Runtime) -> list[CheckpointModel]:
    """Fine-tuned checkpoints available for the "triplet fine-tuned backbone" ablation variant.

    The details come from the small ``.json`` file written next to each checkpoint, so listing never has to
    load a neural network. Only file names inside one folder are ever exposed.
    """
    folder = runtime.settings.weights_dir / "finetuned"
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob("*.pt")):
        details: dict = {}
        sidecar = path.with_suffix(".json")
        if sidecar.is_file():
            try:
                details = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                details = {}
        config = details.get("config") or {}
        found.append(CheckpointModel(
            name=path.name, dataset=config.get("dataset"), seed=config.get("seed"),
            trained_people=len(details.get("dev_identities") or []) or None, training_images=details.get("training_images"),
            validated=bool(details.get("validated", False)), size_mb=round(path.stat().st_size / 2**20, 1),
            modified=datetime.fromtimestamp(path.stat().st_mtime, UTC),
        ))
    return found


def get_run(session: Session, run_id: str) -> EvaluationRun:
    run = session.get(EvaluationRun, run_id)
    if run is None:
        raise NotFound("No such run.")
    return run


def list_runs(session: Session, kind: str | None, limit: int, offset: int) -> tuple[list[EvaluationRun], int]:
    """Experiment history. Video jobs have their own list (``/api/video/jobs``) and are left out unless asked for."""
    query = select(EvaluationRun)
    count = select(func.count()).select_from(EvaluationRun)
    condition = EvaluationRun.kind == kind if kind else EvaluationRun.kind != "video"
    query, count = query.where(condition), count.where(condition)
    runs = list(session.scalars(query.order_by(EvaluationRun.created_at.desc()).limit(limit).offset(offset)))
    return runs, session.scalar(count) or 0


REPORT_FORMATS = {
    "evaluation": ("json", "md", "html"), "calibration": ("json", "md", "html"),
    "lookalike": ("json", "md", "pairs_csv", "failures_csv", "summary_csv"), "video": ("json", "frames_csv"),
}
_EXTENSION = {"json": "json", "md": "md", "html": "html", "pairs_csv": "pairs.csv", "failures_csv": "failures.csv",
              "summary_csv": "summary.csv", "frames_csv": "frames.csv"}


def report_filename(run: EvaluationRun, fmt: str) -> str:
    return f"{run.kind}-{run.id[:8]}.{_EXTENSION[fmt]}"


def render_report(run: EvaluationRun, fmt: str) -> tuple[str, str]:
    """Return (body, media type) for a finished run. Each kind of run offers the formats that make sense for it."""
    if run.status != "succeeded" or not run.result:
        raise Conflict("A report is only available for runs that finished successfully.")
    allowed = REPORT_FORMATS.get(run.kind, ("json",))
    if fmt not in allowed:
        raise ValidationFailed(f"A {run.kind} run can be exported as: {', '.join(allowed)}.")
    result = run.result
    if fmt == "json":
        return json.dumps(result, indent=2), "application/json"
    if fmt == "md":
        text = lookalike_export.render_markdown(result) if run.kind == "lookalike" else render_markdown(result)
        return text, "text/markdown; charset=utf-8"
    if fmt == "html":
        return render_html(result), "text/html; charset=utf-8"
    if fmt == "frames_csv":
        return video_service.frames_csv(result), "text/csv; charset=utf-8"
    builders = {"pairs_csv": lookalike_export.pairs_csv, "failures_csv": lookalike_export.failures_csv,
                "summary_csv": lookalike_export.summary_csv}
    return builders[fmt](result), "text/csv; charset=utf-8"


# ---------------------------------------------------------------------------------
# The threshold sandbox
# ---------------------------------------------------------------------------------
def _sandbox_payload(run: EvaluationRun) -> dict:
    payload = (run.result or {}).get("sandbox") if run.status == "succeeded" else None
    if not payload:
        raise NotFound("This run has no threshold sandbox. Only finished evaluation and look-alike runs keep the per-query scores it needs.")
    return payload


def sandbox_info(run: EvaluationRun) -> dict:
    payload = _sandbox_payload(run)
    return {
        "run_id": run.id, "kind": run.kind, "dataset": run.dataset_name, "reference": payload["reference"],
        "embedding_source": payload["embedding_source"], "model_fingerprint": payload["model_fingerprint"],
        "splits": {name: rows["n"] for name, rows in payload["splits"].items()},
        "score_range": sandbox.threshold_range(payload), "is_benchmark": (run.result or {})["metadata"]["is_benchmark"],
        "writes_policy": False,
        "explanation": ("A fixed table of the per-query results of this run. Trying a different threshold only re-counts that table - "
                        "no model is re-run and the active decision policy is never changed."),
    }


def sandbox_explore(run: EvaluationRun, body: SandboxRequest) -> dict:
    payload = _sandbox_payload(run)
    result = sandbox.explore(payload, body.split, threshold=body.threshold, min_margin=body.min_margin, margin_action=body.margin_action)
    result["run_id"] = run.id
    result["is_benchmark"] = (run.result or {})["metadata"]["is_benchmark"]
    return result


def dataset_image_path(runtime: Runtime, run: EvaluationRun, ref: str):
    """The file behind an image reference of a look-alike run - only references that the run itself recorded are served."""
    result = run.result or {}
    if run.status != "succeeded" or result.get("kind") != "lookalike":
        raise NotFound("No such image.")
    if ref not in lookalike_export.recorded_refs(result):
        raise NotFound("No such image in this experiment.")
    info = find_dataset(runtime.settings.datasets_dir, run.dataset_name)
    if info is None:
        raise NotFound("The dataset of this experiment is no longer installed.")
    root = info.root.resolve()
    path = (root / ref).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise NotFound("No such image.")
    return path
