"""
The Lookalike Failure Lab: where does the matcher go wrong, and why?

In plain words
--------------
Person re-identification fails in a very particular way: two DIFFERENT people who
look alike (same colours, same build, similar clothing) get a high similarity score,
so a stranger is accepted as an enrolled person. This module goes looking for those
cases on labelled data instead of waiting for them to happen:

  1. MINE      list the pairs of different people the model finds most alike.
  2. CHALLENGE turn those pairs (plus ordinary genuine same-person pairs) into a fixed,
               reproducible "challenge set" and measure the matcher on it.
  3. COMPARE   run the same challenge pairs through a second model (a fine-tuned
               checkpoint), if one exists, so the two are compared on the SAME examples.
  4. INSPECT   list the real query-level mistakes (strangers accepted, enrolled people
               turned away) with the recorded evidence and clearly-labelled HYPOTHESES.

What this is NOT: it is not a new learning algorithm and it proves nothing by itself. It is
a diagnostic tool; the numbers it prints are measurements on one dataset sample.

Honesty rules built into the code
---------------------------------
* The operating threshold is chosen on the CALIBRATION split only. The mining/inspection
  split (default: test) is looked at afterwards and never feeds back into that choice.
* A "challenge" false-accept rate is measured on pairs that were SELECTED for being hard, so
  it is far higher than the real-world rate. Next to it we always print the false-accept rate
  over ALL different-person pairs ("all-pairs reference") so nobody mistakes one for the other.
* "Embeddings look alike" and "clothing looks alike" are two separate things. Each pair
  carries both: the model similarity and an independent clothing-COLOUR similarity (a
  label-free proxy; the dataset has no clothing labels).
* An observed fact (score 0.81, threshold 0.78) and a hypothesis about its cause ("clothing
  colours are very close") are stored in separate fields and the hypothesis is always labelled
  as unproven.
* A second model is only compared if it passes the leakage guard (it must never have been
  trained on the people being evaluated). Otherwise the result says "unavailable" and why;
  nothing is invented.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torchvision

from ..cv.geometry import pad_to_person_aspect
from ..cv.imaging import load_rgb_file
from ..cv.quality import assess_crop
from . import metrics as m
from . import sandbox
from .calibration import OperatingTarget, select_operating_point
from .datasets import DatasetInfo, ImageRecord
from .embedding_store import EvaluationCancelled
from .hard_subset import colour_similarity, describe_records
from .performance import environment_info, measure_embedding_latency
from .runner import (
    CancelFn,
    EvaluationRequest,
    ExtractorFactory,
    ProgressFn,
    _Context,
    _finetuned_problem,
    _noop_progress,
)
from .protocol import Protocol, ProtocolConfig
from .scoring import ScoredSplit

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
MINING_SPLITS = ("dev", "calibration", "test")
NEAR_THRESHOLD = 0.05  # "within 0.05 of the threshold" - used only to word hypotheses, never to decide anything
LOW_MARGIN = 0.02
COLOUR_QUANTILE = 0.75  # clothing-colour proxy: the most colour-alike quarter of all different-person pairs


@dataclass
class LookalikeRequest:
    dataset: str
    seed: int = 0
    target: OperatingTarget = field(default_factory=OperatingTarget)
    protocol: ProtocolConfig = field(default_factory=ProtocolConfig)
    mining_split: str = "test"  # which people to search for look-alikes: dev | calibration | test
    top_pairs: int = 40  # how many most-confusable identity pairs to list (and to build the challenge set from)
    images_per_pair: int = 3  # image comparisons taken from each identity pair
    max_genuine_pairs: int = 4000  # cap on same-person comparisons (seeded sample when there are more)
    max_failures: int = 40  # failures listed per category (counts always cover ALL of them)
    use_margin: bool = True
    finetuned_checkpoint: Path | None = None

    def validate(self) -> None:
        self.target.validate()
        if self.mining_split not in MINING_SPLITS:
            raise ValueError(f"mining_split must be one of {MINING_SPLITS}")

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset, "seed": self.seed, "target": self.target.__dict__, "protocol": self.protocol.to_dict(),
            "mining_split": self.mining_split, "top_pairs": self.top_pairs, "images_per_pair": self.images_per_pair,
            "max_genuine_pairs": self.max_genuine_pairs, "max_failures": self.max_failures, "use_margin": self.use_margin,
            "finetuned_checkpoint": self.finetuned_checkpoint.name if self.finetuned_checkpoint else None,
        }


# =====================================================================================
# Step 1 - mining look-alike identity pairs
# =====================================================================================
@dataclass
class MiningSet:
    """The images being searched, ordered so each person's photos are contiguous."""

    records: list[ImageRecord]
    identities: list[str]  # sorted person ids
    identity_index: np.ndarray  # (n,) which person each image belongs to
    starts: np.ndarray  # (I,) first image row of each person
    ends: np.ndarray  # (I,) one past the last image row of each person

    @classmethod
    def build(cls, records: list[ImageRecord]) -> MiningSet:
        ordered = sorted(records, key=lambda r: (r.identity, r.path.name))
        identities = sorted({r.identity for r in ordered})
        code = {name: i for i, name in enumerate(identities)}
        index = np.array([code[r.identity] for r in ordered], dtype=int)
        starts = np.array([int(np.flatnonzero(index == i)[0]) for i in range(len(identities))], dtype=int)
        ends = np.append(starts[1:], len(ordered))
        return cls(ordered, identities, index, starts, ends)


def mining_records(ctx: _Context, protocol: Protocol, split: str) -> list[ImageRecord]:
    """The photos of every person in the chosen split (already capped per person by the protocol)."""
    if split == "dev":
        cap = protocol.config.max_images_per_identity
        by_identity: dict[str, list[ImageRecord]] = {}
        for record in ctx.records:
            if record.identity in protocol.dev_ids:
                by_identity.setdefault(record.identity, []).append(record)
        chosen: list[ImageRecord] = []
        for photos in by_identity.values():
            photos = sorted(photos, key=lambda r: r.path.name)
            chosen += photos if cap is None else photos[:cap]  # deterministic: first N by file name
        return chosen
    part = protocol.calibration if split == "calibration" else protocol.test
    unique: dict[Path, ImageRecord] = {}
    for record in part.gallery + part.known_queries + part.unknown_queries:
        unique.setdefault(record.path, record)
    return list(unique.values())


def scan_identity_pairs(embeddings: np.ndarray, mining: MiningSet, threshold: float, block: int = 512) -> dict:
    """Compare every image with every image of OTHER people, in blocks (so memory stays small).

    Returns
      pair_max   (I, I) for each two people, the highest similarity between any photo of one and any photo of the other
      above/total   how many of ALL different-person image pairs reach ``threshold`` (the "all-pairs reference" FAR)
    """
    n, n_ids = len(embeddings), len(mining.identities)
    pair_max = np.full((n_ids, n_ids), -np.inf, dtype=np.float32)
    above = total = 0
    columns = np.arange(n)[None, :]
    for first in range(0, n, block):
        last = min(n, first + block)
        similarity = embeddings[first:last] @ embeddings.T  # (rows, n)
        rows_identity = mining.identity_index[first:last]
        same_person = rows_identity[:, None] == mining.identity_index[None, :]
        counted_once = (columns > np.arange(first, last)[:, None]) & ~same_person  # each unordered pair counted once
        above += int(((similarity >= threshold) & counted_once).sum())
        total += int(counted_once.sum())
        per_person = np.maximum.reduceat(np.where(same_person, -np.inf, similarity), mining.starts, axis=1)
        np.maximum.at(pair_max, rows_identity, per_person)
    np.fill_diagonal(pair_max, -np.inf)
    return {"pair_max": pair_max, "above": above, "total": total}


def top_identity_pairs(pair_max: np.ndarray, count: int) -> list[tuple[int, int, float]]:
    """The ``count`` most alike pairs of different people (each pair once), most alike first."""
    n_ids = pair_max.shape[0]
    first, second = np.triu_indices(n_ids, k=1)
    values = pair_max[first, second]
    order = np.argsort(-values, kind="stable")[:count]
    return [(int(first[i]), int(second[i]), float(values[i])) for i in order if np.isfinite(values[i])]


def _best_image_pairs(embeddings: np.ndarray, mining: MiningSet, a: int, b: int, count: int) -> list[tuple[int, int]]:
    """The ``count`` most similar (photo of A, photo of B) combinations, as global image rows."""
    rows_a, rows_b = np.arange(mining.starts[a], mining.ends[a]), np.arange(mining.starts[b], mining.ends[b])
    similarity = embeddings[rows_a] @ embeddings[rows_b].T
    flat = np.argsort(-similarity, axis=None, kind="stable")[:count]
    return [(int(rows_a[i // len(rows_b)]), int(rows_b[i % len(rows_b)])) for i in flat]


def genuine_pairs(mining: MiningSet, limit: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Same-person photo pairs from DIFFERENT cameras (or any two photos when cameras are unknown).

    Using different cameras mirrors the real task - recognising a person in a new place - and avoids
    flattering the model with two near-identical frames from the same camera.
    """
    first_rows: list[int] = []
    second_rows: list[int] = []
    for person in range(len(mining.identities)):
        rows = np.arange(mining.starts[person], mining.ends[person])
        for position, i in enumerate(rows):
            for j in rows[position + 1 :]:
                cam_i, cam_j = mining.records[i].camera, mining.records[j].camera
                if cam_i is None or cam_j is None or cam_i != cam_j:
                    first_rows.append(int(i))
                    second_rows.append(int(j))
    first, second = np.array(first_rows, dtype=int), np.array(second_rows, dtype=int)
    if len(first) > limit:
        keep = np.sort(np.random.default_rng(seed).choice(len(first), size=limit, replace=False))
        first, second = first[keep], second[keep]
    return first, second


def pair_similarity(embeddings: np.ndarray, first: np.ndarray, second: np.ndarray) -> np.ndarray:
    return np.einsum("ij,ij->i", embeddings[first], embeddings[second]).astype(np.float64)


# =====================================================================================
# Step 2 - measuring the challenge set
# =====================================================================================
def challenge_measurement(genuine: np.ndarray, impostor: np.ndarray, threshold: float, reference: dict) -> dict:
    """Counts and rates of one model on the challenge pairs, at its own calibrated threshold."""
    true_accept = int((genuine >= threshold).sum())
    false_accept = int((impostor >= threshold).sum())
    n_gen, n_imp = len(genuine), len(impostor)
    return {
        "threshold": float(threshold),
        "genuine_pairs": n_gen, "impostor_pairs": n_imp,
        "true_accepts": true_accept, "false_rejects": n_gen - true_accept,
        "false_accepts": false_accept, "true_rejects": n_imp - false_accept,
        "tar": true_accept / n_gen if n_gen else None,
        "far_on_challenge_set": false_accept / n_imp if n_imp else None,
        "far_on_challenge_set_upper_bound_95": m.wilson_upper_bound(false_accept, n_imp),
        "far_all_pairs_reference": reference["above"] / reference["total"] if reference["total"] else None,
        "all_pairs_compared": int(reference["total"]),
        "note": "The challenge-set FAR is measured on pairs chosen BECAUSE they are hard, so it is much higher than "
                "the false-accept rate of normal use. Compare it with the all-pairs reference, not with a target FAR.",
    }


def pair_curve(genuine: np.ndarray, impostor: np.ndarray, points: int = 60) -> list[dict]:
    """TAR and FAR at a spread of thresholds (the pair-level ROC / "threshold effects" table)."""
    if len(genuine) == 0 or len(impostor) == 0:
        return []
    everything = np.concatenate([genuine, impostor])
    thresholds = np.unique(np.quantile(everything, np.linspace(0, 1, points)))[::-1]
    sorted_g, sorted_i = np.sort(genuine), np.sort(impostor)
    far = 1 - np.searchsorted(sorted_i, thresholds, side="left") / len(impostor)
    tar = 1 - np.searchsorted(sorted_g, thresholds, side="left") / len(genuine)
    return [{"threshold": round(float(t), 5), "far": round(float(f), 5), "tar": round(float(r), 5)}
            for t, f, r in zip(thresholds, far, tar, strict=True)]


# =====================================================================================
# Step 4 - inspecting real mistakes
# =====================================================================================
CATEGORY_LABELS = {
    "incorrect_acceptance": "Stranger accepted as an enrolled person",
    "wrong_identity_accepted": "Enrolled person accepted as a different enrolled person",
    "genuine_rejected": "Enrolled person not accepted",
}
HYPOTHESIS_STATUS = "hypothesis - not proven"


def _hypothesis(cause: str, text: str, evidence: str) -> dict:
    return {"cause": cause, "text": text, "evidence": evidence, "status": HYPOTHESIS_STATUS}


def explain_failure(category: str, observed: dict, *, colour_cutoff: float) -> list[dict]:
    """Possible causes, each tied to a recorded number. These are ideas to check, never conclusions."""
    out: list[dict] = []
    gap = observed["score_minus_threshold"]
    if category in ("incorrect_acceptance", "wrong_identity_accepted"):
        if gap is not None and gap <= NEAR_THRESHOLD:
            out.append(_hypothesis(
                "threshold_too_permissive",
                "The threshold may be too permissive for this operating point: a slightly stricter value would have rejected this query.",
                f"similarity {observed['top1_score']:.3f} is only {gap:.3f} above the threshold {observed['threshold']:.3f}. "
                "The price of a stricter threshold is lower recall - see the threshold sandbox."))
        margin = observed.get("margin")
        if observed.get("min_margin") is None and margin is not None and margin <= LOW_MARGIN:
            out.append(_hypothesis(
                "ambiguous_ranking",
                "The ranking was ambiguous: another enrolled person scored almost the same. A minimum-margin rule would flag this for review.",
                f"margin to the runner-up is {margin:.3f}; no margin rule was active."))
    else:  # genuine_rejected
        if gap is not None and gap < 0 and -gap <= NEAR_THRESHOLD:
            out.append(_hypothesis(
                "threshold_too_strict",
                "The query narrowly missed the threshold; a slightly looser value would have accepted this person.",
                f"similarity {observed['top1_score']:.3f} is {-gap:.3f} below the threshold {observed['threshold']:.3f}."))
        if observed["outcome"] == "review_required":
            out.append(_hypothesis(
                "ambiguous_ranking",
                "The match was sent to review because the winner did not lead the runner-up by the required margin.",
                f"margin {observed['margin']:.3f} < required {observed['min_margin']:.3f}."))
        if observed.get("true_identity_rank") and observed["true_identity_rank"] > 1:
            out.append(_hypothesis(
                "model_or_dataset_limitation",
                "Another enrolled person looked more like this photo than the true person did.",
                f"the true person ranked #{observed['true_identity_rank']} (score {observed['true_identity_score']:.3f}, "
                f"best score {observed['top1_score']:.3f})."))

    if observed.get("quality_flags"):
        out.append(_hypothesis(
            "insufficient_image_quality",
            "Image quality may have weakened the evidence.",
            "quality checks flagged: " + ", ".join(observed["quality_flags"]) + f" (sharpness {observed['sharpness']:.1f})."))
    colour = observed.get("clothing_colour_similarity")
    if category != "genuine_rejected" and colour is not None and colour >= colour_cutoff:
        out.append(_hypothesis(
            "similar_clothing_colours",
            "The two people wear very similar colours, which leaves little for the model to tell them apart.",
            f"torso/leg colour similarity {colour:.2f} is in the top quarter of all different-person pairs (cut-off {colour_cutoff:.2f}). "
            "This is a colour proxy, not an annotation of identical clothing."))
    if not out:
        out.append(_hypothesis(
            "model_or_dataset_limitation",
            "No simple cause is visible in the recorded evidence. This may be a limitation of the model or the data for this pair of people.",
            "the score is not close to the threshold, the image quality checks passed and the clothing colours are not unusually close."))
    return out


def inspect_failures(scored: ScoredSplit, rule: dict, root: Path, colour_cutoff: float, limit: int) -> dict:
    """List the real mistakes of one model on one scored split (counts cover all of them, the list is capped)."""
    qs = scored.qs
    threshold, min_margin = rule["threshold"], rule.get("min_margin")
    outcome = sandbox.decide_rows(qs.top1_score, qs.margin, threshold, min_margin, rule.get("margin_action", "review"))
    accepted = outcome == sandbox.ACCEPTED
    known = qs.is_known

    groups = {
        "incorrect_acceptance": np.flatnonzero(accepted & ~known),
        "wrong_identity_accepted": np.flatnonzero(accepted & known & ~qs.top1_correct),
        "genuine_rejected": np.flatnonzero(~accepted & known),
    }
    counts = {name: int(len(rows)) for name, rows in groups.items()}
    counts["queries"] = int(len(qs))
    counts["genuine_sent_to_review"] = int(((outcome == sandbox.REVIEW) & known).sum())
    counts["strangers_sent_to_review"] = int(((outcome == sandbox.REVIEW) & ~known).sum())

    def relative(path: Path) -> str:
        return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name

    listed: list[dict] = []
    for category, rows in groups.items():
        # Most instructive first: accepted mistakes by highest score; rejected enrolled people by highest score.
        ordered = sorted(rows.tolist(), key=lambda i: -qs.top1_score[i])[:limit]
        for position, i in enumerate(ordered, start=1):
            record, matched = scored.query_records[i], scored.top1_gallery_record[i]
            crop = pad_to_person_aspect(load_rgb_file(record.path))
            quality = assess_crop(crop)
            colour = None
            if matched is not None:
                colour = float(colour_similarity(describe_records([record]), describe_records([matched]))[0, 0])
            true_score = None if scored.true_score is None or not np.isfinite(scored.true_score[i]) else float(scored.true_score[i])
            observed = {
                "outcome": str(outcome[i]),
                "top1_score": float(qs.top1_score[i]), "threshold": float(threshold),
                "score_minus_threshold": float(qs.top1_score[i] - threshold),
                "margin": None if not np.isfinite(qs.margin[i]) else float(qs.margin[i]), "min_margin": min_margin,
                "true_identity_rank": int(qs.true_rank[i]) if known[i] else None, "true_identity_score": true_score,
                "quality_flags": quality.flags, "sharpness": float(quality.metrics.get("sharpness", 0.0)),
                "clothing_colour_similarity": None if colour is None else round(colour, 4),
            }
            listed.append({
                "id": f"{category[:2].upper()}-{position:03d}",
                "category": category, "category_label": CATEGORY_LABELS[category],
                "query": {"ref": relative(record.path), "identity": record.identity, "camera": record.camera, "is_known": bool(known[i])},
                "matched": {"identity": scored.top1_identity[i], "ref": relative(matched.path) if matched else None,
                            "camera": matched.camera if matched else None},
                "observed": observed,
                "possible_causes": explain_failure(category, observed, colour_cutoff=colour_cutoff),
            })
    return {"counts": counts, "listed": listed, "rule": rule,
            "note": "'observed' holds recorded measurements. 'possible_causes' are hypotheses worded from those "
                    "measurements; they have not been tested and must not be read as the proven reason."}


# =====================================================================================
# The whole experiment
# =====================================================================================
def run_lookalike(
    info: DatasetInfo,
    request: LookalikeRequest,
    *,
    cache_dir: Path,
    make_extractor: ExtractorFactory,
    experiment_id: str = "",
    progress: ProgressFn = _noop_progress,
    cancelled: CancelFn = lambda: False,
) -> dict:
    request.validate()
    started, clock = datetime.now(UTC), time.perf_counter()
    progress("Reading dataset and building splits", 0.02)
    eval_request = EvaluationRequest(dataset=info.name, seeds=(request.seed,), target=request.target, protocol=request.protocol,
                                     finetuned_checkpoint=request.finetuned_checkpoint)
    ctx = _Context(info, eval_request, cache_dir, make_extractor, progress, cancelled)
    protocol = ctx.protocols[request.seed]

    warnings: list[str] = []
    if info.kind != "benchmark":
        warnings.append(
            f"'{info.name}' is a {info.kind.replace('_', ' ')} dataset: these results only show that the lab runs end to end. "
            "They are NOT benchmark results and must not be quoted as performance.")

    # ---- is a second model allowed? -------------------------------------------------------------
    improved_state: dict = {"status": "unavailable"}
    use_improved = False
    if request.finetuned_checkpoint is None:
        improved_state["reason"] = ("No fine-tuned checkpoint was selected. None is shipped with this project; "
                                    "scripts/finetune_triplet.py trains one on the development people.")
    elif request.mining_split == "dev":
        improved_state["reason"] = ("The 'dev' people are the ones a fine-tuned model is trained on, so comparing models on "
                                    "them would reward memorisation. Choose the calibration or test split.")
    else:
        problem = _finetuned_problem(eval_request, info, ctx.protocols)
        if problem:
            improved_state["reason"] = problem
        else:
            use_improved = True

    # ---- embeddings (cached on disk; only new images are run through the network) ----------
    mining_set = MiningSet.build(mining_records(ctx, protocol, request.mining_split))
    if len(mining_set.identities) < 2:
        raise ValueError("The chosen split has fewer than two people, so there are no different-person pairs to mine.")
    needed: dict[Path, ImageRecord] = {}
    for part in (protocol.calibration, protocol.test):
        for record in part.gallery + part.known_queries + part.unknown_queries:
            needed.setdefault(record.path, record)
    for record in mining_set.records:
        needed.setdefault(record.path, record)
    kinds = {"plain": (None, False)}
    if use_improved:
        kinds["finetuned"] = (request.finetuned_checkpoint, False)
    ctx.compute_embeddings(kinds, 0.05, 0.62, records=list(needed.values()))

    # ---- model-independent clothing-colour descriptors (the "look-alike clothing" proxy) ------
    progress("Measuring clothing-colour similarity", 0.64)
    colours = describe_records(mining_set.records)
    sample_rng = np.random.default_rng(request.seed)
    sample_a = sample_rng.integers(0, len(mining_set.records), 20000)
    sample_b = sample_rng.integers(0, len(mining_set.records), 20000)
    different = mining_set.identity_index[sample_a] != mining_set.identity_index[sample_b]
    colour_cutoff = float(np.quantile((colours[sample_a[different]] * colours[sample_b[different]]).sum(axis=1) / 2.0, COLOUR_QUANTILE))

    # ---- per model: threshold on CALIBRATION, then everything else on the frozen rule --------
    sources = {"baseline": "plain", **({"improved": "finetuned"} if use_improved else {})}
    labels = {"baseline": "Baseline (official pretrained weights)", "improved": "Improved (fine-tuned checkpoint)"}
    per_model: dict[str, dict] = {}
    scored_test: dict[str, ScoredSplit] = {}
    scored_cal: dict[str, ScoredSplit] = {}
    for step, (name, source) in enumerate(sources.items()):
        if cancelled():
            raise EvaluationCancelled()
        progress(f"Calibrating the threshold ({name})", 0.66 + 0.06 * step)
        calibration_scores, test_scores = ctx.score(protocol, source)
        scored_cal[name], scored_test[name] = calibration_scores, test_scores
        selected = select_operating_point(calibration_scores.qs, request.target, use_margin=request.use_margin)
        if not selected.target_achieved:
            warnings.append(f"The {name} model could not reach the requested operating point on the calibration people "
                            f"({request.target.describe()}). Its threshold is a best-effort fallback, not a calibrated one.")
        rule = {"threshold": selected.threshold, "min_margin": selected.min_margin, "margin_action": "review"}
        per_model[name] = {
            "status": "ok", "label": labels[name], "embedding_source": source,
            "calibration": selected.to_dict(), "rule": rule,
            "test_query_level": m.operating_point(test_scores.qs, selected.threshold, selected.min_margin),
        }
        per_model[name]["test_query_level"]["far_upper_bound_95"] = m.wilson_upper_bound(
            per_model[name]["test_query_level"]["counts"]["unknown_accepted"], test_scores.qs.n_unknown)
    if cancelled():
        raise EvaluationCancelled()

    # ---- mining and the challenge set (pairs are chosen with the BASELINE model) --------------
    progress("Searching for look-alike pairs", 0.78)
    embeddings = {name: ctx.vectors("finetuned" if src == "finetuned" else "plain", mining_set.records) for name, src in sources.items()}
    base_threshold = per_model["baseline"]["rule"]["threshold"]
    scan = scan_identity_pairs(embeddings["baseline"], mining_set, base_threshold)
    pairs = top_identity_pairs(scan["pair_max"], request.top_pairs)

    impostor_first: list[int] = []
    impostor_second: list[int] = []
    pair_of_comparison: list[int] = []
    for rank, (a, b, _) in enumerate(pairs):
        for i, j in _best_image_pairs(embeddings["baseline"], mining_set, a, b, request.images_per_pair):
            impostor_first.append(i), impostor_second.append(j), pair_of_comparison.append(rank)
    imp_first, imp_second = np.array(impostor_first, dtype=int), np.array(impostor_second, dtype=int)
    gen_first, gen_second = genuine_pairs(mining_set, request.max_genuine_pairs, request.seed)
    if len(gen_first) == 0:
        warnings.append("No same-person pairs from different cameras exist in this split, so recall on the challenge set is undefined.")

    progress("Measuring the challenge set", 0.86)
    all_pair_reference = {"baseline": scan}
    if use_improved:
        all_pair_reference["improved"] = scan_identity_pairs(embeddings["improved"], mining_set, per_model["improved"]["rule"]["threshold"])
    pair_scores: dict[str, np.ndarray] = {}
    for name in sources:
        threshold = per_model[name]["rule"]["threshold"]
        impostor = pair_similarity(embeddings[name], imp_first, imp_second) if len(imp_first) else np.zeros(0)
        genuine = pair_similarity(embeddings[name], gen_first, gen_second) if len(gen_first) else np.zeros(0)
        pair_scores[name] = impostor
        per_model[name]["challenge"] = {
            **challenge_measurement(genuine, impostor, threshold, all_pair_reference[name]),
            "curve": pair_curve(genuine, impostor),
            "hardest_genuine_pairs": _hardest_genuine(genuine, gen_first, gen_second, mining_set, root=info.root, limit=12,
                                                      threshold=threshold),
        }

    # ---- the listed identity pairs --------------------------------------------------------------
    colour_pair = {}
    for rank, (a, b, _) in enumerate(pairs):
        block = (colours[mining_set.starts[a]:mining_set.ends[a]] @ colours[mining_set.starts[b]:mining_set.ends[b]].T) / 2.0
        colour_pair[rank] = float(block.max())

    def ref(row: int) -> str:
        path = mining_set.records[row].path
        return path.relative_to(info.root).as_posix() if path.is_relative_to(info.root) else path.name

    listed_pairs = []
    for rank, (a, b, similarity) in enumerate(pairs):
        comparisons = [k for k, owner in enumerate(pair_of_comparison) if owner == rank]
        best = comparisons[0]
        first_row, second_row = int(imp_first[best]), int(imp_second[best])
        by_model = {}
        for name in sources:
            score = float(pair_scores[name][best])
            by_model[name] = {"similarity": round(score, 5),
                              "decision": "false_accept" if score >= per_model[name]["rule"]["threshold"] else "correct_reject"}
        listed_pairs.append({
            "rank": rank + 1, "comparison_type": "different_identities",
            "split": request.mining_split, "identity_a": mining_set.identities[a], "identity_b": mining_set.identities[b],
            "similarity": round(similarity, 5), "by_model": by_model,
            "image_a": ref(first_row), "image_b": ref(second_row),
            "camera_a": mining_set.records[first_row].camera, "camera_b": mining_set.records[second_row].camera,
            "clothing_colour_similarity": round(colour_pair[rank], 4),
            "similar_clothing_proxy": bool(colour_pair[rank] >= colour_cutoff),
            "comparisons_in_challenge_set": len(comparisons),
        })

    # ---- real mistakes of the matcher on the test split -------------------------------------------
    progress("Inspecting failures", 0.92)
    failures = {}
    for name in sources:
        failures[name] = inspect_failures(scored_test[name], per_model[name]["rule"], info.root, colour_cutoff, request.max_failures)

    # ---- speed: measured, never assumed ------------------------------------------------------------
    progress("Measuring speed", 0.96)
    crops = [pad_to_person_aspect(load_rgb_file(r.path)) for r in mining_set.records[:: max(1, len(mining_set.records) // 12)][:12]]
    for name, source in sources.items():
        extractor = ctx._extractors[request.finetuned_checkpoint if source == "finetuned" else None]
        per_model[name]["model"] = extractor.info()
        per_model[name]["latency"] = measure_embedding_latency(extractor, crops, single_runs=12, batch_size=min(8, len(crops)))

    if use_improved:
        improved_state = {**per_model["improved"]}
    result = {
        "schema_version": SCHEMA_VERSION,
        "kind": "lookalike",
        "metadata": {
            "experiment_id": experiment_id, "started_at": started.isoformat(),
            "duration_seconds": round(time.perf_counter() - clock, 1),
            "request": request.to_dict(), "dataset": info.to_dict(), "is_benchmark": info.kind == "benchmark",
            "operating_target": request.target.describe(),
            "protocol": protocol.summary(), "software": {**environment_info(), "torchvision": torchvision.__version__},
            "reproducibility": ("Same dataset files, same seed and the same settings give the same splits, pairs and numbers. "
                                "The fingerprint of each model is recorded under 'models'."),
        },
        "challenge_set": {
            "definition": {
                "source": f"dataset '{info.name}' ({info.layout} layout), split '{request.mining_split}', seed {request.seed}",
                "identities_searched": len(mining_set.identities), "images_searched": len(mining_set.records),
                "impostor_comparisons": ("different-person photo pairs. For each of the "
                                         f"{len(pairs)} most alike pairs of people (ranked by their single most similar pair of photos, "
                                         f"using the baseline model) the {request.images_per_pair} most similar photo pairs are taken."),
                "genuine_comparisons": ("same-person photo pairs from different cameras (all of them, or a seeded sample of "
                                        f"{request.max_genuine_pairs} when there are more)."),
                "inclusion_criteria": "The impostor side is selected BY the baseline model's similarity, so it is hard for that model by construction. "
                                      "Another model is compared on the very same pairs, which is a fair stress test but not a random sample.",
                "model_vs_clothing": "'Similar' for mining means similar EMBEDDINGS. Clothing similarity is measured separately "
                                     "(colour histograms, label-free proxy) and reported per pair; the two are not assumed to coincide.",
                "clothing_proxy_cutoff": round(colour_cutoff, 4),
                "clothing_proxy_rule": f"colour similarity in the top {int((1 - COLOUR_QUANTILE) * 100)}% of a seeded sample of all different-person photo pairs",
                "splits": "people are divided into dev / calibration / test with no person in two groups; "
                          "the threshold is chosen on calibration people only.",
            },
            "counts": {"identity_pairs": len(pairs), "impostor_comparisons": int(len(imp_first)),
                       "genuine_comparisons": int(len(gen_first)), "all_pairs_compared": int(scan["total"])},
            "identity_pairs": listed_pairs,
        },
        "models": {
            "baseline": per_model["baseline"],
            "improved": improved_state,
        },
        "comparison": _comparison_table(per_model) if use_improved else None,
        "failures": failures,
        "sandbox": sandbox.build_payload(
            scored_cal["baseline"], scored_test["baseline"], info.root,
            reference={"variant": "baseline", "label": labels["baseline"], **per_model["baseline"]["rule"],
                       "target_achieved": per_model["baseline"]["calibration"]["target_achieved"],
                       "chosen_on": f"calibration split, seed {request.seed}"},
            source="plain", seed=request.seed, model_fingerprint=getattr(ctx._extractors[None], "fingerprint", None)),
        "limitations": _limitations(info, request, use_improved),
        "warnings": warnings,
    }
    progress("Done", 1.0)
    return result


def _hardest_genuine(genuine: np.ndarray, first: np.ndarray, second: np.ndarray, mining: MiningSet, *, root: Path,
                     limit: int, threshold: float) -> list[dict]:
    """Same-person pairs the model finds LEAST alike - the other side of the look-alike problem."""
    if len(genuine) == 0:
        return []

    def ref(row: int) -> str:
        path = mining.records[row].path
        return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name

    order = np.argsort(genuine, kind="stable")[:limit]
    return [{
        "comparison_type": "same_identity", "identity": mining.records[int(first[i])].identity,
        "similarity": round(float(genuine[i]), 5), "decision": "false_reject" if genuine[i] < threshold else "correct_accept",
        "image_a": ref(int(first[i])), "image_b": ref(int(second[i])),
        "camera_a": mining.records[int(first[i])].camera, "camera_b": mining.records[int(second[i])].camera,
    } for i in order]


def _comparison_table(per_model: dict[str, dict]) -> list[dict]:
    """Baseline and improved model side by side, each at its OWN calibrated threshold, on identical examples."""
    rows = []
    for name in ("baseline", "improved"):
        model = per_model[name]
        test, challenge = model["test_query_level"], model["challenge"]
        rows.append({
            "model": name, "label": model["label"], "threshold": model["rule"]["threshold"],
            "test_far": test["far"], "test_recall_dir1": test["dir_at_rank"]["1"], "test_unknown_accepted": test["counts"]["unknown_accepted"],
            "test_unknown_queries": test["counts"]["unknown_queries"],
            "challenge_far": challenge["far_on_challenge_set"], "challenge_tar": challenge["tar"],
            "challenge_false_accepts": challenge["false_accepts"], "challenge_impostor_pairs": challenge["impostor_pairs"],
            "single_crop_ms_p50": (model.get("latency") or {}).get("single_crop_ms", {}).get("p50"),
        })
    return rows


def _limitations(info: DatasetInfo, request: LookalikeRequest, has_improved: bool) -> list[str]:
    items = [
        "Results are measurements on one sample of people. A threshold chosen on one calibration set does not guarantee the same false-accept rate on new people.",
        "The challenge set is selected by the baseline model, so its false-accept rate is not comparable with a normal FAR; use the all-pairs reference for that.",
        "Clothing similarity is a colour-histogram proxy. The datasets carry no clothing labels, so 'similar clothing' is not ground truth.",
        "Possible causes listed for each mistake are hypotheses derived from recorded numbers; none has been tested by changing the input.",
    ]
    if info.kind != "benchmark":
        items.append(f"The dataset '{info.name}' is a {info.kind.replace('_', ' ')} set, not a public benchmark; its numbers verify the software only.")
    if not has_improved:
        items.append("No improved model was compared, so this run makes no claim that any training method improves results.")
    if request.mining_split == "test":
        items.append("The test split was searched for look-alikes after the threshold was fixed on calibration people. Do not adjust the model or threshold in response and then reuse the same test split for a final number.")
    return items


__all__ = ["LookalikeRequest", "run_lookalike"]
