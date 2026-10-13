"""
Running a complete experiment.

In plain words: two entry points, both usable from the web UI and from the
command line (``scripts/run_evaluation.py``, ``scripts/calibrate_threshold.py``):

``run_evaluation``   the full study. For every seed it builds an identity-disjoint
                     protocol, measures every ablation variant on the calibration AND
                     test splits, applies the calibration-selected rules to the test
                     split, adds same-clothing-subset analysis, bootstrap intervals and
                     speed/memory measurements, and finally picks the "selected
                     configuration" using CALIBRATION numbers only.

``run_calibration``  the threshold-setting workflow. Uses ONLY the calibration split, never
                     the test split, and returns a proposed decision policy plus a
                     calibrated-confidence model - or reports that the target could not
                     be met.

Both return plain JSON-serialisable dictionaries that are stored with the run, so every
number on screen can be traced to a configuration, a seed and a model fingerprint.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torchvision

from ..core.errors import ModelUnavailable
from ..cv.embedding.extractor import OSNetExtractor
from ..cv.embedding.weights import read_checkpoint_metadata
from ..cv.geometry import pad_to_person_aspect
from ..cv.imaging import load_rgb_file
from ..cv.open_set.confidence import ConfidenceModel
from . import metrics as m
from . import sandbox
from .ablation import (
    DEFAULT_VARIANT_KEYS,
    VARIANT_BY_KEY,
    VARIANTS,
    evaluate_variant,
    summarise_seeds,
)
from .calibration import OperatingTarget, select_operating_point
from .datasets import DatasetInfo, ImageRecord, load_records
from .embedding_store import EvaluationCancelled, embed_records, normalise_rows
from .hard_subset import hard_query_mask
from .performance import environment_info, measure_embedding_latency, peak_memory_mb, percentiles
from .protocol import Protocol, ProtocolConfig, build_protocol
from .scoring import ScoredSplit, score_split

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str, float], None]
CancelFn = Callable[[], bool]
ExtractorFactory = Callable[[Path | None], OSNetExtractor]  # checkpoint (or None) -> extractor, flip OFF

SCHEMA_VERSION = 1


@dataclass
class EvaluationRequest:
    dataset: str
    seeds: tuple[int, ...] = (0,)
    target: OperatingTarget = field(default_factory=OperatingTarget)
    variants: tuple[str, ...] = DEFAULT_VARIANT_KEYS
    protocol: ProtocolConfig = field(default_factory=ProtocolConfig)
    bootstrap_samples: int = 300
    far_grid: tuple[float, ...] = (0.001, 0.01, 0.05, 0.10)
    hard_quantile: float = 0.75
    finetuned_checkpoint: Path | None = None

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "seeds": list(self.seeds),
            "target": self.target.__dict__,
            "variants": list(self.variants),
            "protocol": self.protocol.to_dict(),
            "bootstrap_samples": self.bootstrap_samples,
            "far_grid": list(self.far_grid),
            "hard_quantile": self.hard_quantile,
            "finetuned_checkpoint": self.finetuned_checkpoint.name if self.finetuned_checkpoint else None,
        }


def _noop_progress(stage: str, fraction: float) -> None:
    return None


def make_extractor_factory(model_name: str, weights_dir: Path, device, batch_size: int = 32, fold_bn: bool = False) -> ExtractorFactory:
    """Evaluation extractors: flip-TTA OFF (flip is built from cached 'mirrored' embeddings instead).

    ``checkpoint=None`` means the official pretrained weights, regardless of what the live app uses.
    """
    from ..cv.embedding.registry import get_spec

    spec = get_spec(model_name)

    def factory(checkpoint: Path | None) -> OSNetExtractor:
        return OSNetExtractor.load(spec, weights_dir, device, checkpoint=checkpoint,
                                   batch_size=batch_size, use_flip_tta=False, fold_bn=fold_bn)

    return factory


class _Context:
    """Everything shared by one run: records, protocols, and a way to fetch embeddings."""

    def __init__(self, info: DatasetInfo, request: EvaluationRequest, cache_dir: Path,
                 make_extractor: ExtractorFactory, progress: ProgressFn, cancelled: CancelFn):
        self.info, self.request, self.cache_dir = info, request, cache_dir
        self.make_extractor, self.progress, self.cancelled = make_extractor, progress, cancelled
        self.records = load_records(info)
        if not self.records:
            raise ValueError(f"Dataset '{info.name}' contains no readable images.")
        self.protocols: dict[int, Protocol] = {
            seed: build_protocol(self.records, replace(request.protocol, seed=seed)) for seed in request.seeds
        }
        self._embeddings: dict[str, np.ndarray] = {}
        self._row: dict[Path, int] = {}
        self.embedding_ms: list[float] = []

    # -- which images does the run need? --------------------------------------------------
    def _needed_records(self) -> list[ImageRecord]:
        unique: dict[Path, ImageRecord] = {}
        for protocol in self.protocols.values():
            for split in (protocol.calibration, protocol.test):
                for record in split.gallery + split.known_queries + split.unknown_queries:
                    unique.setdefault(record.path, record)
        return list(unique.values())

    def compute_embeddings(
        self,
        kinds: dict[str, tuple[Path | None, bool]],
        start: float,
        end: float,
        records: list[ImageRecord] | None = None,
    ) -> None:
        """``kinds``: name -> (checkpoint, mirrored). Computes (or loads from cache) each requested flavour.

        ``records`` limits the work to specific images (calibration passes only the calibration split).
        """
        needed = records if records is not None else self._needed_records()
        self._row = {record.path: i for i, record in enumerate(needed)}
        extractors: dict[Path | None, OSNetExtractor] = {}
        for index, (name, (checkpoint, mirrored)) in enumerate(kinds.items()):
            if checkpoint not in extractors:
                extractors[checkpoint] = self.make_extractor(checkpoint)
            span = (end - start) / len(kinds)
            base = start + index * span

            def on_progress(done: int, total: int, base=base, span=span, name=name) -> None:
                self.progress(f"Embedding images ({name})", base + span * (done / max(total, 1)))

            self._embeddings[name] = embed_records(
                needed, extractors[checkpoint], cache_dir=self.cache_dir, dataset=self.info.name,
                dataset_root=self.info.root, mirrored=mirrored, progress=on_progress, cancelled=self.cancelled,
                timings=self.embedding_ms if name == "plain" else None,
            )
        self._extractors = extractors

    def vectors(self, name: str, records: list[ImageRecord]) -> np.ndarray:
        matrix = self._embeddings[name]
        if not records:
            return np.zeros((0, matrix.shape[1]), dtype=np.float32)
        return matrix[[self._row[r.path] for r in records]]

    def source_vectors(self, source: str, records: list[ImageRecord]) -> np.ndarray:
        """Embeddings for a variant's embedding source: plain | flip | finetuned."""
        if source == "flip":
            return normalise_rows(self.vectors("plain", records) + self.vectors("mirrored", records))
        return self.vectors("finetuned" if source == "finetuned" else "plain", records)

    def score(self, protocol: Protocol, source: str) -> tuple[ScoredSplit, ScoredSplit]:
        scored = []
        for split in (protocol.calibration, protocol.test):
            scored.append(score_split(
                split,
                self.source_vectors(source, split.gallery),
                self.source_vectors(source, split.known_queries),
                self.source_vectors(source, split.unknown_queries),
                cross_camera=protocol.config.cross_camera,
            ))
        return scored[0], scored[1]


# --------------------------------------------------------------------------
# Full evaluation
# --------------------------------------------------------------------------


def _finetuned_problem(request: EvaluationRequest, info: DatasetInfo, protocols: dict[int, Protocol]) -> str | None:
    """Why a fine-tuned checkpoint must NOT be evaluated (None = it is safe).

    The danger is leakage: a network trained on a person has seen them, so scoring it on that person as a
    "stranger" or "known" would be meaningless. The checkpoint records the people it was trained on, and
    we refuse it if ANY of them is in the calibration or test split of ANY seed in this run.
    """
    path = request.finetuned_checkpoint
    if path is None:
        return "No fine-tuned checkpoint was supplied."
    if not path.is_file():
        return f"The checkpoint file {path.name} does not exist."
    try:
        meta = read_checkpoint_metadata(path)
    except ModelUnavailable as exc:
        return exc.message

    trained_on = set(meta.get("dev_identities") or [])
    if not trained_on:
        return "The checkpoint does not record which people it was trained on, so leakage into the test split cannot be ruled out."
    trained_dataset = (meta.get("config") or {}).get("dataset")
    if trained_dataset and trained_dataset != info.name:
        return f"The checkpoint was trained on dataset '{trained_dataset}', not '{info.name}'."
    for seed, protocol in protocols.items():
        evaluated = {
            r.identity for split in (protocol.calibration, protocol.test)
            for r in split.gallery + split.known_queries + split.unknown_queries
        }
        overlap = trained_on & evaluated
        if overlap:
            return (f"LEAKAGE: {len(overlap)} people it was trained on (e.g. {sorted(overlap)[:3]}) are in the calibration/test "
                    f"split for seed {seed}. Evaluate a fine-tuned checkpoint only with the seed and split it was trained for.")
    return None


def _source_for(variant_key: str) -> str:
    spec = VARIANT_BY_KEY[variant_key]
    return "finetuned" if spec.finetuned else ("flip" if spec.flip else "plain")


def run_evaluation(
    info: DatasetInfo,
    request: EvaluationRequest,
    *,
    cache_dir: Path,
    make_extractor: ExtractorFactory,
    progress: ProgressFn = _noop_progress,
    cancelled: CancelFn = lambda: False,
) -> dict:
    started = datetime.now(UTC)
    clock = time.perf_counter()
    request.target.validate()
    unknown_keys = [v for v in request.variants if v not in VARIANT_BY_KEY]
    if unknown_keys:
        raise ValueError(f"Unknown variants: {unknown_keys}")

    progress("Reading dataset and building splits", 0.02)
    ctx = _Context(info, request, cache_dir, make_extractor, progress, cancelled)

    warnings: list[str] = []
    if info.kind != "benchmark":
        warnings.append(
            f"'{info.name}' is a {info.kind.replace('_', ' ')} dataset. These numbers only verify that the "
            "pipeline runs end to end; they are NOT benchmark results and must not be quoted as performance."
        )

    # Work out which embedding flavours are needed.
    variants = [VARIANT_BY_KEY[key] for key in request.variants]
    kinds: dict[str, tuple[Path | None, bool]] = {"plain": (None, False)}
    if any(v.flip for v in variants):
        kinds["mirrored"] = (None, True)
    finetuned_problem = _finetuned_problem(request, info, ctx.protocols)  # None means the checkpoint is safe to use
    finetuned_ok = finetuned_problem is None
    if request.finetuned_checkpoint is not None and finetuned_problem is not None:
        warnings.append(f"The fine-tuned checkpoint was NOT used. {finetuned_problem}")
    if any(v.finetuned for v in variants) and finetuned_ok:
        kinds["finetuned"] = (request.finetuned_checkpoint, False)

    ctx.compute_embeddings(kinds, 0.05, 0.70)
    progress("Scoring variants", 0.72)

    per_variant: dict[str, list[dict]] = {v.key: [] for v in variants}
    protocol_summaries = {}
    sandbox_scores: tuple[ScoredSplit, ScoredSplit] | None = None  # first seed, plain embeddings: the threshold sandbox's table
    for step, seed in enumerate(request.seeds):
        if cancelled():
            raise EvaluationCancelled()
        protocol = ctx.protocols[seed]
        protocol_summaries[str(seed)] = protocol.summary()
        scored_cache: dict[str, tuple[ScoredSplit, ScoredSplit]] = {}
        base_cal, base_test = ctx.score(protocol, "plain")
        scored_cache["plain"] = (base_cal, base_test)
        if step == 0:
            sandbox_scores = (base_cal, base_test)

        # The hard subset depends only on the images, so it is identical for every variant.
        cal_hard, cal_hard_info = hard_query_mask(
            protocol.calibration, base_cal.query_records, base_cal.qs.is_known,
            dataset_root=info.root, quantile=request.hard_quantile)
        test_hard, test_hard_info = hard_query_mask(
            protocol.test, base_test.query_records, base_test.qs.is_known,
            dataset_root=info.root, quantile=request.hard_quantile)
        protocol_summaries[str(seed)]["hard_subset"] = {"calibration": cal_hard_info, "test": test_hard_info}

        for spec in variants:
            if spec.finetuned and not finetuned_ok:
                per_variant[spec.key].append({"variant": spec.key, "seed": seed, "status": "unavailable",
                                              "reason": finetuned_problem})
                continue
            source = _source_for(spec.key)
            if source not in scored_cache:
                scored_cache[source] = ctx.score(protocol, source)
            cal, test = scored_cache[source]
            try:
                per_variant[spec.key].append(evaluate_variant(
                    spec, cal, test, request.target, calibration_hard=cal_hard, test_hard=test_hard,
                    far_grid=request.far_grid, bootstrap_samples=request.bootstrap_samples, seed=seed,
                    fitted_on=f"dataset '{info.name}', calibration split, seed {seed}"))
            except (ValueError, np.linalg.LinAlgError) as exc:
                per_variant[spec.key].append({"variant": spec.key, "seed": seed, "status": "failed", "reason": str(exc)})
        progress("Scoring variants", 0.72 + 0.2 * (step + 1) / len(request.seeds))

    # ---- performance (measured, not assumed) ---------------------------------------
    progress("Measuring speed and memory", 0.94)
    performance = _measure_performance(ctx, ctx.protocols[request.seeds[0]])

    variant_results = {}
    for spec in variants:
        runs = per_variant[spec.key]
        ok = [r for r in runs if r.get("status") == "ok"]
        variant_results[spec.key] = {
            "label": spec.label, "description": spec.description, "parent": spec.parent,
            "status": "ok" if ok else (runs[0].get("status", "failed") if runs else "failed"),
            "reason": None if ok else (runs[0].get("reason") if runs else None),
            "per_seed": runs,
            "summary": summarise_seeds(ok) if ok else None,
        }

    result = {
        "schema_version": SCHEMA_VERSION,
        "kind": "evaluation",
        "metadata": {
            "started_at": started.isoformat(), "duration_seconds": round(time.perf_counter() - clock, 1),
            "request": request.to_dict(),
            "dataset": info.to_dict(),
            "is_benchmark": info.kind == "benchmark",
            "model": _model_info(ctx),
            "protocol": protocol_summaries,
            "software": {**environment_info(), "torchvision": torchvision.__version__},
            "operating_target": request.target.describe(),
        },
        "performance": performance,
        "variants": variant_results,
        "selected_variant": _select_variant(variant_results, request.target),
        "sandbox": _sandbox_payload(sandbox_scores, per_variant, request.seeds[0], info, ctx),
        "warnings": warnings,
    }
    progress("Done", 1.0)
    return result


def _sandbox_payload(scores: tuple[ScoredSplit, ScoredSplit] | None, per_variant: dict[str, list[dict]], seed: int,
                     info: DatasetInfo, ctx: _Context) -> dict | None:
    """The fixed table the threshold sandbox works on (see ``evaluation/sandbox.py``).

    The reference rule is the calibrated rule of the margin variant (or the plain threshold variant), because both
    are applied to the plain-embedding scores stored here. ``None`` if neither variant ran successfully.
    """
    if scores is None:
        return None
    for key in ("thr_margin", "thr"):
        first = (per_variant.get(key) or [None])[0]
        selected = first.get("selected") if first and first.get("status") == "ok" else None
        if selected and selected.get("threshold") is not None:
            reference = {
                "variant": key, "label": VARIANT_BY_KEY[key].label, "threshold": selected["threshold"],
                "min_margin": selected["min_margin"], "margin_action": "review",
                "target_achieved": selected["target_achieved"],
                "chosen_on": f"calibration split, seed {seed}",
            }
            return sandbox.build_payload(scores[0], scores[1], info.root, reference=reference, source="plain", seed=seed,
                                         model_fingerprint=getattr(ctx._extractors[None], "fingerprint", None))
    return None


def _model_info(ctx: _Context) -> dict:
    extractor = ctx._extractors[None]
    return {**extractor.info(), "fine_tuned_checkpoint_used": "finetuned" in ctx._embeddings}


def _select_variant(results: dict, target: OperatingTarget) -> dict:
    """Pick the final configuration using CALIBRATION numbers only (never the test split)."""
    candidates = []
    for key, data in results.items():
        spec = VARIANT_BY_KEY[key]
        summary = data.get("summary")
        if spec.rejection == "none" or not summary:
            continue
        if summary["targets_achieved"] < summary["n_seeds_total"]:
            continue  # only variants that actually reached the target on calibration are eligible
        far = summary["calibration_far"]["mean"]
        recall = summary["calibration_dir1"]["mean"]
        if far is None or recall is None:
            continue
        candidates.append((key, far, recall))
    if not candidates:
        return {"key": None, "selected_on": "calibration split",
                "reason": "No variant reached the requested operating point on the calibration data."}
    order = {v.key: i for i, v in enumerate(VARIANTS)}  # ties go to the simpler (earlier) variant
    if target.mode == "fixed_recall":
        best = min(candidates, key=lambda c: (round(c[1], 6), -c[2], order[c[0]]))
        criterion = "lowest calibration FAR among variants that reached the recall target"
    else:
        best = min(candidates, key=lambda c: (-round(c[2], 6), c[1], order[c[0]]))
        criterion = "highest calibration recall among variants that stayed under the FAR target"
    return {"key": best[0], "selected_on": "calibration split", "criterion": criterion,
            "calibration_far": best[1], "calibration_recall": best[2]}


def _measure_performance(ctx: _Context, protocol: Protocol) -> dict:
    """Latency of the embedding backbone (steady state), retrieval and process memory."""
    extractor = ctx._extractors[None]
    sample = (protocol.test.known_queries + protocol.test.unknown_queries)[:24]
    crops = [pad_to_person_aspect(load_rgb_file(r.path)) for r in sample]
    latency = measure_embedding_latency(extractor, crops)

    gallery = ctx.vectors("plain", protocol.test.gallery)
    query = ctx.vectors("plain", sample[:1]) if sample else gallery[:1]
    began = time.perf_counter()
    for _ in range(200):
        _ = np.max(query @ gallery.T)
    retrieval_ms = (time.perf_counter() - began) / 200 * 1000

    info = extractor.info()
    return {
        "embedding": latency,
        "retrieval_ms_per_query": round(retrieval_ms, 4),
        "retrieval_gallery_images": int(len(gallery)),
        "model_load_seconds": info["load_seconds"],
        "warmup_seconds": info["warmup_seconds"],
        "dataset_embedding_ms_per_image": percentiles(ctx.embedding_ms),
        "peak_memory_mb": peak_memory_mb(),
        "device": info["device"],
        "note": "Measured on this machine in steady state after warm-up; model load and warm-up are separate.",
    }


# --------------------------------------------------------------------------
# Threshold calibration (never touches the test split)
# --------------------------------------------------------------------------


@dataclass
class CalibrationRequest:
    dataset: str
    target: OperatingTarget = field(default_factory=OperatingTarget)
    use_margin: bool = True
    use_flip_tta: bool = False  # must match the LIVE model configuration
    seed: int = 0
    protocol: ProtocolConfig = field(default_factory=ProtocolConfig)
    checkpoint: Path | None = None  # must match the LIVE model configuration


def run_calibration(
    info: DatasetInfo,
    request: CalibrationRequest,
    *,
    cache_dir: Path,
    make_extractor: ExtractorFactory,
    progress: ProgressFn = _noop_progress,
    cancelled: CancelFn = lambda: False,
) -> dict:
    started = datetime.now(UTC)
    request.target.validate()
    progress("Reading dataset and building splits", 0.02)
    eval_request = EvaluationRequest(dataset=info.name, seeds=(request.seed,), target=request.target,
                                     protocol=request.protocol, finetuned_checkpoint=request.checkpoint)
    ctx = _Context(info, eval_request, cache_dir, make_extractor, progress, cancelled)
    protocol = ctx.protocols[request.seed]

    # ONLY the calibration split is embedded: the test split is never read.
    kinds: dict[str, tuple[Path | None, bool]] = {"plain": (request.checkpoint, False)}
    if request.use_flip_tta:
        kinds["mirrored"] = (request.checkpoint, True)
    ctx.compute_embeddings(kinds, 0.05, 0.85, records=_calibration_records(protocol))
    progress("Selecting the operating point", 0.88)

    source = "flip" if request.use_flip_tta else "plain"
    split = protocol.calibration
    scored = score_split(split, ctx.source_vectors(source, split.gallery), ctx.source_vectors(source, split.known_queries),
                         ctx.source_vectors(source, split.unknown_queries), cross_camera=protocol.config.cross_camera)

    selected = select_operating_point(scored.qs, request.target, use_margin=request.use_margin)
    confidence = None
    try:
        usable = np.isfinite(scored.qs.top1_score)
        confidence = ConfidenceModel.fit(
            scored.qs.top1_score[usable], np.where(np.isfinite(scored.qs.margin), scored.qs.margin, 0.0)[usable],
            (scored.qs.is_known & scored.qs.top1_correct)[usable],
            fitted_on=f"dataset '{info.name}', calibration split, seed {request.seed}")
    except ValueError as exc:
        logger.warning("Confidence model not fitted: %s", exc)

    warnings = []
    if info.kind != "benchmark":
        warnings.append("Calibrated on a smoke-test dataset: use the result only to check the workflow, not as a real operating point.")
    extractor = ctx._extractors[request.checkpoint]
    result = {
        "schema_version": SCHEMA_VERSION,
        "kind": "calibration",
        "metadata": {
            "started_at": started.isoformat(),
            "dataset": info.to_dict(), "is_benchmark": info.kind == "benchmark",
            "split_used": "calibration (the test split was not read)",
            "seed": request.seed, "protocol": protocol.summary(),
            "model": extractor.info(), "flip_tta": request.use_flip_tta,
            "operating_target": request.target.describe(),
            "software": environment_info(),
        },
        "proposed_policy": {
            "accept_threshold": selected.threshold,
            "min_margin": selected.min_margin,
            "margin_action": "review",
            "status": "calibrated" if selected.target_achieved else "experimental",
        },
        "selected": selected.to_dict(),
        "score_histogram": m.score_histogram(scored.qs),
        "confidence_model": confidence.to_dict() if confidence else None,
        # Same format as the LIVE extractor's fingerprint, so the policy can check it is used with the right model.
        "model_fingerprint": f"{extractor.name}-{extractor.weights_sha256[:12]}-flip{int(request.use_flip_tta)}",
        "warnings": warnings,
    }
    progress("Done", 1.0)
    return result


def _calibration_records(protocol: Protocol) -> list[ImageRecord]:
    unique: dict[Path, ImageRecord] = {}
    split = protocol.calibration
    for record in split.gallery + split.known_queries + split.unknown_queries:
        unique.setdefault(record.path, record)
    return list(unique.values())


__all__ = ["CalibrationRequest", "EvaluationCancelled", "EvaluationRequest", "run_calibration", "run_evaluation"]
