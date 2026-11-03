"""Write docs/EXPERIMENT_RESULTS.md: the saved evaluation runs, tabulated by code, around hand-written
interpretation.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import summarise_results  # noqa: E402


def table(folder: str, keep: tuple[str, ...]) -> str:
    sys.argv = ["summarise_results.py", str(REPO_ROOT / folder)]
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        summarise_results.main()
    lines = [line for line in buffer.getvalue().splitlines() if line.startswith("|")]
    header, rule, rows = lines[0], lines[1], lines[2:]
    rows = [row for row in rows if any(f"| {name} |" in row for name in keep)]
    return "\n".join([header, rule, *rows])


def run_facts(folder: str) -> dict:
    files = sorted((REPO_ROOT / folder).glob("*.json"))
    data = json.loads(files[0].read_text(encoding="utf-8"))
    meta = data["metadata"]
    return {"software": meta["software"], "performance": data["performance"], "protocol": meta["protocol"]["0"], "model": meta["model"]}


MAIN_KEEP = ("Nearest neighbour (no rejection)", "+ Calibrated threshold", "+ Top-1/top-2 margin rule", "+ Calibrated confidence (instead of margin)",
             "+ Average over a person's photos (instead of the best photo)", "+ Flip test-time augmentation")
FT_KEEP = ("+ Calibrated threshold", "+ Top-1/top-2 margin rule", "+ Triplet fine-tuned backbone")


def main() -> int:
    facts = run_facts("docs/results/market1501")
    idle = json.loads((REPO_ROOT / "docs" / "results" / "performance_idle.json").read_text(encoding="utf-8-sig"))  # measured with nothing else running
    perf, soft = idle["performance"], idle["hardware"]
    text = f"""# Experiment results - Market-1501, body appearance only

*Measured 2026-10-25 / 2026-11-03 on the development laptop. Protocol: [EVALUATION_PROTOCOL.md](EVALUATION_PROTOCOL.md). Raw runs: `docs/results/market1501/` and `docs/results/market1501_finetuned/`. Regenerate this page with `python scripts/build_experiment_results.py`.*

**Read this first.** These are body-appearance numbers on a public benchmark, with the project's own identity-disjoint protocol on a CPU-sized subset (no official `query/` folder was available, so they are *not* comparable with published Market-1501 results).
Face + body cannot be benchmarked on Market-1501 (the images are too small for faces). Known limits: [LIMITATIONS.md](LIMITATIONS.md).

## 1. Setup in one table

| | |
|---|---|
| Dataset | Market-1501, 26,051 labelled images / 1,501 identities / 6 cameras (pool of train + test folders) |
| Per split (seed 0) | 60 enrolled + 60 stranger people; 3 gallery photos per enrolled person; {facts['protocol']['calibration']['known_queries']} / {facts['protocol']['test']['known_queries']} known queries and {facts['protocol']['calibration']['unknown_queries']} / {facts['protocol']['test']['unknown_queries']} stranger queries (calibration / test) |
| Seeds | 0, 1, 2 (each re-draws who is enrolled and who is a stranger); the fine-tuning experiment uses seed 0 only |
| Model | {facts['model'].get('architecture')} - {facts['model'].get('weights')} (verified: [MODEL_VERIFICATION.md](MODEL_VERIFICATION.md)) |
| Hardware / software | Intel Core i5-7300U (2 cores / 4 threads), {soft['total_memory_gb']} GB RAM, no GPU; Python {soft['python']}, torch {soft['torch']}, numpy {soft['numpy']} |
| Speed (measured) | embedding one crop: p50 {perf['embedding']['single_crop_ms']['p50']:.0f} ms, p95 {perf['embedding']['single_crop_ms']['p95']:.0f} ms; batch of 16: {perf['embedding']['batch']['throughput_crops_per_second']:.1f} crops/s; retrieval per query (180-image gallery): {perf['retrieval_ms_per_query']:.3f} ms; model load {perf['model_load_seconds']:.2f} s; peak memory {perf['peak_memory_mb']:.0f} MB. **Not real-time video** |

## 2. FAR at a fixed recall - the PS-1 objective (3 seeds, TEST people)

For each target recall (DIR@1 = enrolled people accepted **and** correctly named) the threshold is chosen on the **calibration** people to give the lowest FAR that still reaches the target, frozen, and scored once on the disjoint **test** people.
FAR = strangers for whom *any* enrolled person was named. Entries are mean ± standard deviation over the seeds.

{table('docs/results/market1501', MAIN_KEEP)}

**What the table says**

* **Embedding quality is good:** closed-set Rank-1 83.6 % ± 1.8, mAP 77.8 % ± 1.4 (best photo per person), ROC-AUC 0.850 ± 0.027 for telling enrolled people from strangers.
* **The open-set price is high.** With the plain threshold rule the test FAR is **6.4 %** at 50 % recall, **12.9 %** at 60 %, **28.6 %** at 70 %, and about **80 %** at 80 % recall (the 80 % target was reached on calibration for only 2 of 3 seeds). **A 90 % recall target is unreachable** - the best possible DIR@1 is the Rank-1 of 83.6 % - and the best-effort threshold accepts 99.6 % of strangers. Body appearance alone cannot give a low FAR at high recall; this is the "low inter-class variance" problem, measured.
* **Negative result - the top-1/top-2 margin rule did not help:** at 70 % recall FAR 25.0 % ± 4.7 vs 28.6 % ± 8.0 for the plain threshold (inside the noise) and it lowered recall and ROC-AUC. **Calibrated confidence** was equivalent (25.5 % ± 4.8). **Flip augmentation** gave nothing (28.8 % ± 4.6).
* **Averaging a person's photos** (instead of taking the best photo) was the best *free* change: FAR 21.4 % ± 7.9 at 70 % recall and 59.5 % ± 11.2 at 80 % (reached on all 3 seeds), Rank-1 87.8 % ± 3.8 - but the standard deviations are large and the recall actually reached differs between variants (70.5 % vs 72.7 %), so treat it as *promising, not proven*.
* **Threshold-only rejection has a structural weakness:** a stranger only has to resemble *one* of 60 enrolled people (180 photos) to be accepted, so FAR grows quickly as the gallery grows. This is why the product uses the face first.

## 3. Does metric-learning fine-tuning help? (seed 0 only, TEST people)

The last stage of the network was fine-tuned for 3 epochs × 30 batches (16 people × 4 photos) with **batch-hard triplet loss** (cosine distance, margin 0.3, hard-negative mining inside each batch) on the **590 development people only** (8,759 images, 2,650 s on this CPU).
The evaluation refuses a checkpoint if any person it was trained on appears in the calibration or test split (a leakage guard with its own test); none did. Checkpoint: `backend/weights/finetuned/market_seed0_head.pt` (git-ignored). Training seed: 0; **one seed, one training run - no confidence statement is possible beyond "this run"**.

{table('docs/results/market1501_finetuned', FT_KEEP)}

(The `+ Calibrated threshold` and `+ Top-1/top-2 margin rule` rows are the **pretrained** model on the same seed-0 people; `+ Triplet fine-tuned backbone` is the fine-tuned one.)

* Closed-set quality rose from **Rank-1 83.1 % → 89.7 %** and **mAP 76.3 % → 87.3 %**.
* At **70 % recall** the false-accept rate fell from **22.2 % to 11.4 %**; at **80 %** the target went from **unreachable (FAR 100 %) to reachable with FAR 58.5 %**.
* At the **lowest recalls the result is mixed** (50 %: FAR 3.4 % → 6.0 %, i.e. not better; 60 %: 9.7 % → 6.0 %). With 60 stranger people the FAR resolution is coarse, and this is a single seed.
* The fine-tuned checkpoint is **not** the product default: it is trained on Market-1501 people and would need re-validation on any other camera. Use it via `REID_EMBEDDING_CHECKPOINT`.

## 4. What was not run

`NOT_RUN`: fine-tuning for seeds 1 and 2 (about 45 minutes each on this CPU); full-backbone fine-tuning (`--trainable all`); any experiment on a second dataset or on same-clothing ground truth; face + body on pedestrian data.
"""
    target = REPO_ROOT / "docs" / "EXPERIMENT_RESULTS.md"
    target.write_text(text, encoding="utf-8", newline="\n")
    print("wrote", target.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
