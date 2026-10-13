"""
Exporting a Lookalike Failure Lab experiment.

In plain words: the experiment's full result is stored as JSON (that is the complete,
machine-readable record). This module turns it into the files people actually open:

  pairs.csv      one row per look-alike pair of people (and the hardest same-person pairs)
  failures.csv   one row per listed mistake, with the observed numbers and the unproven hypotheses
  summary.csv    the headline numbers, one row per model, plus the reproducibility details
  a Markdown report that reads top to bottom for a reviewer

CSV safety: a spreadsheet treats a cell that starts with = + - or @ as a formula. Dataset labels
come from file names we do not control, so text cells that start that way are prefixed with an
apostrophe before they are written.
"""

from __future__ import annotations

import csv
import io

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _cell(value):
    if isinstance(value, str) and value.startswith(_FORMULA_STARTS):
        return "'" + value
    return "" if value is None else value


def _csv(header: list[str], rows: list[list]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_cell(v) for v in row])
    return out.getvalue()


def pairs_csv(result: dict) -> str:
    models = [name for name, model in result["models"].items() if model.get("status") == "ok"]
    header = ["rank", "comparison_type", "split", "identity_a", "identity_b", "baseline_similarity_best_pair"]
    header += [f"{name}_{field}" for name in models for field in ("pair_similarity", "decision")]
    header += ["clothing_colour_similarity", "similar_clothing_proxy", "image_a", "image_b", "camera_a", "camera_b"]
    rows = []
    for pair in result["challenge_set"]["identity_pairs"]:
        row = [pair["rank"], pair["comparison_type"], pair["split"], pair["identity_a"], pair["identity_b"], pair["similarity"]]
        for name in models:
            by_model = pair["by_model"][name]
            row += [by_model["similarity"], by_model["decision"]]
        rows.append(row + [pair["clothing_colour_similarity"], pair["similar_clothing_proxy"], pair["image_a"], pair["image_b"],
                           pair["camera_a"], pair["camera_b"]])
    for name in models:  # the other side of the coin: same-person pairs the model finds least alike
        for pair in result["models"][name]["challenge"]["hardest_genuine_pairs"]:
            blank = [""] * (2 * len(models))
            rows.append(["", pair["comparison_type"] + f" (hardest, {name})", result["metadata"]["request"]["mining_split"],
                         pair["identity"], pair["identity"], pair["similarity"], *blank, "", "", pair["image_a"], pair["image_b"],
                         pair["camera_a"], pair["camera_b"]])
    return _csv(header, rows)


def failures_csv(result: dict) -> str:
    header = ["model", "id", "observed_category", "query_image", "query_identity", "query_camera", "matched_identity", "matched_image",
              "outcome", "top1_score", "threshold", "score_minus_threshold", "margin", "min_margin", "true_identity_rank",
              "true_identity_score", "quality_flags", "clothing_colour_similarity", "possible_causes_UNPROVEN_hypotheses"]
    rows = []
    for name, block in result["failures"].items():
        for item in block["listed"]:
            o = item["observed"]
            rows.append([name, item["id"], item["category"], item["query"]["ref"], item["query"]["identity"], item["query"]["camera"],
                         item["matched"]["identity"], item["matched"]["ref"], o["outcome"], o["top1_score"], o["threshold"],
                         o["score_minus_threshold"], o["margin"], o["min_margin"], o["true_identity_rank"], o["true_identity_score"],
                         ";".join(o["quality_flags"]), o["clothing_colour_similarity"],
                         " | ".join(f"{c['cause']}: {c['evidence']}" for c in item["possible_causes"])])
    return _csv(header, rows)


def summary_csv(result: dict) -> str:
    meta, challenge = result["metadata"], result["challenge_set"]
    header = ["section", "model", "metric", "value", "note"]
    rows: list[list] = [
        ["experiment", "", "experiment_id", meta["experiment_id"], ""],
        ["experiment", "", "dataset", meta["dataset"]["name"], f"{meta['dataset']['kind']}; benchmark={meta['is_benchmark']}"],
        ["experiment", "", "mining_split", meta["request"]["mining_split"], "which people were searched for look-alikes"],
        ["experiment", "", "seed", meta["request"]["seed"], "same data + seed + settings reproduce the numbers"],
        ["experiment", "", "operating_target", meta["operating_target"], "chosen on the calibration people only"],
        ["challenge_set", "", "identity_pairs", challenge["counts"]["identity_pairs"], ""],
        ["challenge_set", "", "impostor_comparisons", challenge["counts"]["impostor_comparisons"], "different people, chosen because they are alike"],
        ["challenge_set", "", "genuine_comparisons", challenge["counts"]["genuine_comparisons"], "same person, different cameras"],
        ["challenge_set", "", "all_pairs_compared", challenge["counts"]["all_pairs_compared"], "denominator of the all-pairs reference FAR"],
    ]
    for name, model in result["models"].items():
        if model.get("status") != "ok":
            rows.append(["model", name, "status", model["status"], model.get("reason", "")])
            continue
        test, ch = model["test_query_level"], model["challenge"]
        rows += [
            ["model", name, "fingerprint", (model.get("model") or {}).get("fingerprint", ""), ""],
            ["calibration", name, "threshold", model["rule"]["threshold"], "chosen on calibration people"],
            ["calibration", name, "min_margin", model["rule"]["min_margin"], ""],
            ["calibration", name, "target_achieved", model["calibration"]["target_achieved"], ""],
            ["test_query_level", name, "far", test["far"], f"{test['counts']['unknown_accepted']} of {test['counts']['unknown_queries']} strangers accepted"],
            ["test_query_level", name, "far_upper_bound_95", test.get("far_upper_bound_95"), "one-sided 95% bound"],
            ["test_query_level", name, "recall_dir1", test["dir_at_rank"]["1"], "accepted AND correct / enrolled queries"],
            ["challenge_set", name, "far_on_challenge_set", ch["far_on_challenge_set"], f"{ch['false_accepts']} of {ch['impostor_pairs']} hard pairs accepted"],
            ["challenge_set", name, "far_all_pairs_reference", ch["far_all_pairs_reference"], "over ALL different-person pairs"],
            ["challenge_set", name, "tar", ch["tar"], f"{ch['true_accepts']} of {ch['genuine_pairs']} same-person pairs accepted"],
            ["latency", name, "single_crop_ms_p50", ((model.get("latency") or {}).get("single_crop_ms") or {}).get("p50"), "measured on this machine"],
        ]
    return _csv(header, rows)


def recorded_refs(result: dict) -> set[str]:
    """Every dataset-relative image path this experiment mentions - and therefore the only ones it may serve."""
    refs: set[str] = set()
    for pair in result["challenge_set"]["identity_pairs"]:
        refs.update((pair["image_a"], pair["image_b"]))
    for model in result["models"].values():
        for pair in (model.get("challenge") or {}).get("hardest_genuine_pairs", []):
            refs.update((pair["image_a"], pair["image_b"]))
    for block in result["failures"].values():
        for item in block["listed"]:
            refs.add(item["query"]["ref"])
            if item["matched"]["ref"]:
                refs.add(item["matched"]["ref"])
    return refs


def _pct(value, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def render_markdown(result: dict) -> str:
    meta, challenge = result["metadata"], result["challenge_set"]
    definition = challenge["definition"]
    lines = [
        f"# Lookalike Failure Lab - experiment {meta['experiment_id'][:8]}",
        "",
        "*OpenID Vision - Know when to match. Know when to reject.* Independent technical prototype responding to the Zed Digital PS-1 "
        "assignment; not an official Zed Digital product. A similarity score is not a probability and a match is not proof of identity.",
        "",
        f"* Dataset: **{meta['dataset']['name']}** ({meta['dataset']['kind'].replace('_', ' ')}; benchmark: {'yes' if meta['is_benchmark'] else 'NO'})",
        f"* Searched for look-alikes in the **{meta['request']['mining_split']}** people, seed {meta['request']['seed']}",
        f"* Operating target (chosen on calibration people only): {meta['operating_target']}",
        f"* Started {meta['started_at']}, took {meta['duration_seconds']} s",
        "",
    ]
    if result["warnings"]:
        lines += ["## Warnings", "", *[f"* {w}" for w in result["warnings"]], ""]
    lines += [
        "## The challenge set", "",
        f"* {definition['impostor_comparisons']}", f"* {definition['genuine_comparisons']}",
        f"* {definition['inclusion_criteria']}", f"* {definition['model_vs_clothing']}", "",
        f"Counts: {challenge['counts']['identity_pairs']} identity pairs, {challenge['counts']['impostor_comparisons']} impostor "
        f"comparisons, {challenge['counts']['genuine_comparisons']} genuine comparisons "
        f"({challenge['counts']['all_pairs_compared']} different-person pairs compared for the reference rate).", "",
        "## Results at each model's own calibrated threshold", "",
        "| Model | Threshold | Test FAR (strangers accepted) | Test recall | Challenge FAR | All-pairs FAR | Challenge recall |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, model in result["models"].items():
        if model.get("status") != "ok":
            lines.append(f"| {name} | - | not available: {model.get('reason', '')} | | | | |")
            continue
        test, ch = model["test_query_level"], model["challenge"]
        lines.append(f"| {model['label']} | {model['rule']['threshold']:.4f} | {_pct(test['far'])} | {_pct(test['dir_at_rank']['1'])} | "
                     f"{_pct(ch['far_on_challenge_set'])} | {_pct(ch['far_all_pairs_reference'], 4)} | {_pct(ch['tar'])} |")
    lines += ["", "The challenge-set false-accept rate is measured on pairs chosen because they are hard; compare it with the "
              "all-pairs rate, not with a target FAR.", "", "## Most alike pairs of different people", "",
              "| # | Person A | Person B | Similarity | Clothing colour similarity | Decision (baseline) |", "|---|---|---|---|---|---|"]
    for pair in challenge["identity_pairs"][:15]:
        lines.append(f"| {pair['rank']} | {pair['identity_a']} | {pair['identity_b']} | {pair['similarity']:.3f} | "
                     f"{pair['clothing_colour_similarity']:.2f}{' (alike)' if pair['similar_clothing_proxy'] else ''} | {pair['by_model']['baseline']['decision']} |")
    lines += ["", "## Mistakes on the test people (baseline)", ""]
    counts = result["failures"]["baseline"]["counts"]
    lines += [f"* Strangers accepted as an enrolled person: **{counts['incorrect_acceptance']}**",
              f"* Enrolled people accepted as a different enrolled person: **{counts['wrong_identity_accepted']}**",
              f"* Enrolled people not accepted: **{counts['genuine_rejected']}** (of which {counts['genuine_sent_to_review']} sent to review)", "",
              result["failures"]["baseline"]["note"], "", "## Limitations", "", *[f"* {text}" for text in result["limitations"]], "",
              "## Reproducibility", "", meta["reproducibility"], ""]
    return "\n".join(lines)
