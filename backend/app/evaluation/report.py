"""
Human-readable evaluation reports (Markdown and HTML).

In plain words: the JSON result of a run is complete but not pleasant to read.
This module turns it into a short report. The content is assembled ONCE as a
list of simple sections (text + tables), and two tiny renderers print that same
structure as Markdown or as a standalone HTML page, so the two can never
disagree. Only numbers present in the result are shown; anything missing is
printed as "n/a" - never invented.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field

from .ablation import VARIANT_BY_KEY


@dataclass
class Section:
    title: str
    paragraphs: list[str] = field(default_factory=list)
    header: list[str] | None = None
    rows: list[list[str]] = field(default_factory=list)


# ------------------------------------------------------------------ formatting
def pct(value, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def num(value, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def with_ci(value, interval, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    text = pct(value, digits)
    if interval:
        text += f" [{pct(interval['low'], digits)}, {pct(interval['high'], digits)}]"
    return text


def mean_std(entry: dict | None, as_percent: bool = True, digits: int = 1) -> str:
    if not entry or entry.get("mean") is None:
        return "n/a"
    fmt = pct if as_percent else num
    text = fmt(entry["mean"], digits)
    if entry.get("std") is not None:
        text += f" ± {fmt(entry['std'], digits)}"
    return text


# ---------------------------------------------------------------------- builder
def build_sections(result: dict) -> list[Section]:
    if result.get("kind") == "calibration":
        return _calibration_sections(result)
    return _evaluation_sections(result)


def _evaluation_sections(result: dict) -> list[Section]:
    meta = result["metadata"]
    dataset = meta["dataset"]
    sections: list[Section] = []

    overview = Section("Overview")
    overview.paragraphs.append(
        f"Dataset **{dataset['name']}** ({dataset['kind'].replace('_', ' ')}; {dataset['identities']} identities, "
        f"{dataset['images']} images). Operating target: **{meta['operating_target']}**. "
        f"Seeds: {', '.join(str(s) for s in meta['request']['seeds'])}. "
        f"Model: {meta['model']['architecture']} ({meta['model']['weights']}) on {meta['model']['device']}."
    )
    overview.paragraphs.extend(f"WARNING: {w}" for w in result.get("warnings", []))
    sections.append(overview)

    protocol = next(iter(meta["protocol"].values()))
    sections.append(Section(
        "People and queries per split (first seed)",
        ["Splits are identity-disjoint: nobody appears in more than one of dev / calibration / test, "
         "and enrolled people never appear as strangers."],
        ["Split", "Enrolled people", "Unknown people", "Gallery images", "Known queries", "Unknown queries"],
        [[name.title(), str(s["enrolled_identities"]), str(s["unknown_identities"]), str(s["gallery_images"]),
          str(s["known_queries"]), str(s["unknown_queries"])] for name, s in
         (("calibration", protocol["calibration"]), ("test", protocol["test"]))],
    ))

    ablation = Section(
        "Ablation - held-out TEST split",
        ["Every rule (threshold, margin, confidence model) was chosen on the CALIBRATION split and frozen before "
         "the test split was scored. DIR@1 = enrolled people accepted AND correctly named; FAR = strangers accepted. "
         "Intervals are 95% percentile bootstrap over people (first seed)."],
        ["Variant", "DIR@1 (recall)", "FAR", "TAR", "Rank-1", "mAP", "AUOSCR", "Threshold", "Margin", "Target met on calibration"],
    )
    for key, data in result["variants"].items():
        label = VARIANT_BY_KEY[key].label
        summary = data.get("summary")
        if not summary:
            ablation.rows.append([label, "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a",
                                  data.get("reason") or data["status"]])
            continue
        first = next(r for r in data["per_seed"] if r.get("status") == "ok")
        ci = (first.get("test") or {}).get("confidence_intervals") or {}
        dir1 = with_ci(first["test"]["dir_at_rank"]["1"], ci.get("dir1")) if len(data["per_seed"]) == 1 else mean_std(summary["dir1"])
        far = with_ci(first["test"]["far"], ci.get("far")) if len(data["per_seed"]) == 1 else mean_std(summary["far"])
        threshold = summary["threshold"]["mean"]
        margin = summary["min_margin"]["mean"]
        calibrated = summary["targets_achieved"] == summary["n_seeds_total"]
        ablation.rows.append([
            label, dir1, far, mean_std(summary["tar"]), mean_std(summary["rank1"]), mean_std(summary["mAP"]),
            mean_std(summary["auoscr"], as_percent=False, digits=3),
            "-" if threshold is None else num(threshold) + ("" if calibrated else " (best effort, not calibrated)"),
            "-" if margin is None else num(margin),
            f"{summary['targets_achieved']}/{summary['n_seeds_total']} seeds",
        ])
    sections.append(ablation)

    hard = Section(
        "Low inter-class variance - same-clothing look-alike subset (TEST)",
        ["The SAME frozen rule applied only to the queries that look most like another enrolled person "
         "(top quartile by clothing-colour similarity - a label-free proxy, not ground-truth clothing labels)."],
        ["Variant", "FAR - all queries", "FAR - look-alikes", "DIR@1 - all", "DIR@1 - look-alikes"],
    )
    for key, data in result["variants"].items():
        summary = data.get("summary")
        if summary and VARIANT_BY_KEY[key].rejection != "none":
            hard.rows.append([VARIANT_BY_KEY[key].label, mean_std(summary["far"]), mean_std(summary["hard_far"]),
                              mean_std(summary["dir1"]), mean_std(summary["hard_dir1"])])
    sections.append(hard)

    selected = result.get("selected_variant", {})
    choice = Section("Selected configuration")
    if selected.get("key"):
        choice.paragraphs.append(
            f"**{VARIANT_BY_KEY[selected['key']].label}** - chosen on the {selected['selected_on']} "
            f"({selected['criterion']}). Calibration FAR {pct(selected['calibration_far'])}, "
            f"calibration DIR@1 {pct(selected['calibration_recall'])}.")
    else:
        choice.paragraphs.append(f"No configuration selected. {selected.get('reason', '')}")
    sections.append(choice)

    performance = meta and result.get("performance", {})
    single = (performance.get("embedding") or {}).get("single_crop_ms") or {}
    if single:
        batch = performance["embedding"]["batch"]
        sections.append(Section(
            "Speed and memory (measured on this machine)",
            [performance.get("note", "")],
            ["Measure", "Value"],
            [["Embedding, one crop at a time (p50 / p95 / p99)", f"{single['p50']} / {single['p95']} / {single['p99']} ms"],
             ["Embedding throughput (batch of " + str(batch["batch_size"]) + ")", f"{batch['throughput_crops_per_second']} crops/s"],
             ["Retrieval per query (gallery of " + str(performance["retrieval_gallery_images"]) + " images)", f"{performance['retrieval_ms_per_query']} ms"],
             ["Model load / warm-up (one-off)", f"{performance['model_load_seconds']} s / {performance['warmup_seconds']} s"],
             ["Peak memory", f"{performance['peak_memory_mb']} MB"],
             ["Device", str(performance["device"])]],
        ))

    sections.append(Section(
        "How to read this report",
        ["FAR is query-level: a stranger counts as falsely accepted whenever the system names ANY enrolled person for them.",
         "A threshold selected on one calibration sample does not guarantee the same FAR for new people; "
         "the confidence interval and the calibration sample size show how much to trust it.",
         "Results are for the dataset, split and seeds above. They do not demonstrate demographic fairness, "
         "privacy compliance or production readiness."],
    ))
    return sections


def _calibration_sections(result: dict) -> list[Section]:
    meta, selected = result["metadata"], result["selected"]
    achieved = selected["target_achieved"]
    section = Section(
        "Threshold calibration",
        [f"Dataset **{meta['dataset']['name']}**, calibration split only ({meta['split_used']}). "
         f"Target: **{meta['operating_target']}**.",
         "TARGET ACHIEVED on the calibration data." if achieved else "TARGET NOT ACHIEVED - see notes.",
         *result.get("warnings", []), *selected.get("notes", [])],
        ["Quantity", "Value"],
        [["Accept threshold", num(selected["threshold"])], ["Minimum margin", num(selected["min_margin"])],
         ["Calibration FAR", pct(selected["calibration"]["far"], 2)],
         ["Calibration DIR@1", pct(selected["calibration"]["dir_at_rank"]["1"])],
         ["FAR 95% upper bound", pct(selected["far_upper_bound_95"], 2)],
         ["Unknown / known queries", f"{selected['n_unknown']} / {selected['n_known']}"]],
    )
    return [section]


# -------------------------------------------------------------------- renderers
PRODUCT = "OpenID Vision"
TAGLINE = "Know when to match. Know when to reject."
INDEPENDENCE_NOTE = (
    "Independent technical prototype responding to the Zed Digital PS-1 assignment; not an official Zed Digital product. "
    "A similarity score is not a probability and a match is not proof of identity."
)
# The same original mark as the interface and the favicon: two overlapping rings (a comparison) and a red tick (the verified decision).
LOGO_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' width='40' height='40' role='img' aria-label='OpenID Vision'>"
    "<rect width='32' height='32' rx='8' fill='#14181e'/>"
    "<circle cx='12.4' cy='16' r='6.3' fill='none' stroke='#f3f4f6' stroke-width='2'/>"
    "<circle cx='19.6' cy='16' r='6.3' fill='none' stroke='#f3f4f6' stroke-opacity='.5' stroke-width='2'/>"
    "<path d='M13.9 16.4l1.9 2 3.6-4.3' fill='none' stroke='#E31B23' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'/></svg>"
)


def render_markdown(result: dict) -> str:
    lines = [f"# {PRODUCT} - {'calibration' if result.get('kind') == 'calibration' else 'evaluation'} report", "", f"*{TAGLINE}* {INDEPENDENCE_NOTE}", ""]
    for section in build_sections(result):
        lines += [f"## {section.title}", ""]
        for paragraph in section.paragraphs:
            lines += [paragraph, ""]
        if section.header:
            lines.append("| " + " | ".join(section.header) + " |")
            lines.append("|" + "|".join("---" for _ in section.header) + "|")
            lines += ["| " + " | ".join(row) + " |" for row in section.rows]
            lines.append("")
    return "\n".join(lines)


def _inline(text: str) -> str:
    """Escape, then turn **bold** into <strong>."""
    parts = html.escape(text).split("**")
    return "".join(f"<strong>{p}</strong>" if i % 2 else p for i, p in enumerate(parts))


def render_html(result: dict) -> str:
    body = []
    for section in build_sections(result):
        body.append(f"<h2>{html.escape(section.title)}</h2>")
        body += [f"<p>{_inline(p)}</p>" for p in section.paragraphs]
        if section.header:
            head = "".join(f"<th>{html.escape(h)}</th>" for h in section.header)
            rows = "".join("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>" for row in section.rows)
            body.append(f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>")
    style = (
        "body{font:15px/1.5 system-ui,Segoe UI,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#111317}"
        "h1{font-family:Poppins,system-ui,sans-serif}table{border-collapse:collapse;width:100%;font-size:13px}"
        "th,td{border:1px solid #d9dbdf;padding:6px 8px;text-align:left}th{background:#f3f4f6}.scroll{overflow-x:auto}"
    )
    style += ".brand{display:flex;align-items:center;gap:12px;margin-bottom:1rem}.brand small{display:block;color:#5f6672}footer{margin-top:2rem;color:#5f6672;font-size:12px}"
    kind = "calibration" if result.get("kind") == "calibration" else "evaluation"
    header = f"<div class='brand'>{LOGO_SVG}<div><strong>{PRODUCT}</strong><small>{html.escape(TAGLINE)}</small></div></div>"
    return (f"<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{PRODUCT} - {kind} report</title><style>{style}</style><body>{header}<h1>{kind.capitalize()} report</h1>{''.join(body)}"
            f"<footer>{html.escape(INDEPENDENCE_NOTE)}</footer></body></html>")
