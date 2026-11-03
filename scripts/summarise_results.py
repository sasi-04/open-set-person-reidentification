"""Tabulate saved evaluation runs (docs/results/<dataset>/*.json) into one Markdown table. each run
answers "if we insist on recognising at least X % of enrolled people, how many strangers get in?".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def cell(summary: dict, key: str, percent: bool = True, digits: int = 1) -> str:
    stat = summary.get(key) or {}
    mean, std = stat.get("mean"), stat.get("std")
    if mean is None:
        return "n/a"
    scale = 100 if percent else 1
    unit = " %" if percent else ""
    return f"{mean * scale:.{digits}f}{unit} ± {(std or 0) * scale:.{digits}f}"


def main() -> int:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/results/market1501")
    runs = []
    for path in sorted(folder.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = data["metadata"]
        target = (meta.get("request") or {}).get("target") or {}
        runs.append((target.get("target_recall", 0), path, data))
    runs.sort(key=lambda r: r[0])

    print("| Target DIR@1 (calibration) | Variant | Target reached on calibration | Test DIR@1 (recall) | Test FAR | ROC-AUC | Rank-1 | mAP | Threshold |")
    print("|---|---|---|---|---|---|---|---|---|")
    for target, path, data in runs:
        for key in ("nn_baseline", "thr", "thr_margin", "thr_confidence", "thr_mean", "thr_margin_flip", "thr_margin_finetuned"):
            variant = data["variants"].get(key)
            if not variant or not variant.get("summary"):
                continue
            s = variant["summary"]
            reached = f"{s.get('targets_achieved', 0)} of {s.get('n_seeds_total', 0)} seeds"
            print(f"| {target:.0%} | {variant['label']} | {reached} | {cell(s, 'dir1')} | {cell(s, 'far')} | {cell(s, 'auroc', False, 3)} | "
                  f"{cell(s, 'rank1')} | {cell(s, 'mAP')} | {cell(s, 'threshold', False, 3)} |")
    meta = runs[-1][2]["metadata"]
    print()
    print("metadata of the last run:", json.dumps({k: meta[k] for k in ("seeds", "protocol", "model") if k in meta}, default=str)[:900])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
