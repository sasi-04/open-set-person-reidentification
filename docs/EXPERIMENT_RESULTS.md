# Experiment results - Market-1501, body appearance only

*Measured 2026-10-25 / 2026-11-03 on the development laptop. Protocol: [EVALUATION_PROTOCOL.md](EVALUATION_PROTOCOL.md). Raw runs: `docs/results/market1501/` and `docs/results/market1501_finetuned/`. Regenerate this page with `python scripts/build_experiment_results.py`.*

**Read this first.** These are body-appearance numbers on a public benchmark, with the project's own identity-disjoint protocol on a CPU-sized subset (no official `query/` folder was available, so they are *not* comparable with published Market-1501 results).
Face + body cannot be benchmarked on Market-1501 (the images are too small for faces). Known limits: [LIMITATIONS.md](LIMITATIONS.md).

## 1. Setup in one table

| | |
|---|---|
| Dataset | Market-1501, 26,051 labelled images / 1,501 identities / 6 cameras (pool of train + test folders) |
| Per split (seed 0) | 60 enrolled + 60 stranger people; 3 gallery photos per enrolled person; 290 / 290 known queries and 458 / 465 stranger queries (calibration / test) |
| Seeds | 0, 1, 2 (each re-draws who is enrolled and who is a stranger); the fine-tuning experiment uses seed 0 only |
| Model | OSNet x1.0 (multi-source) - official osnet_x1_0_ms_d_c.pt (verified: [MODEL_VERIFICATION.md](MODEL_VERIFICATION.md)) |
| Hardware / software | Intel Core i5-7300U (2 cores / 4 threads), 7.9 GB RAM, no GPU; Python 3.14.4, torch 2.14.1+cpu, numpy 2.5.2 |
| Speed (measured) | embedding one crop: p50 196 ms, p95 235 ms; batch of 16: 5.3 crops/s; retrieval per query (180-image gallery): 0.017 ms; model load 0.62 s; peak memory 613 MB. **Not real-time video** |

## 2. FAR at a fixed recall - the PS-1 objective (3 seeds, TEST people)

For each target recall (DIR@1 = enrolled people accepted **and** correctly named) the threshold is chosen on the **calibration** people to give the lowest FAR that still reaches the target, frozen, and scored once on the disjoint **test** people.
FAR = strangers for whom *any* enrolled person was named. Entries are mean ± standard deviation over the seeds.

| Target DIR@1 (calibration) | Variant | Target reached on calibration | Test DIR@1 (recall) | Test FAR | ROC-AUC | Rank-1 | mAP | Threshold |
|---|---|---|---|---|---|---|---|---|
| 50% | Nearest neighbour (no rejection) | 0 of 3 seeds | 83.6 % ± 1.8 | 100.0 % ± 0.0 | n/a | 83.6 % ± 1.8 | 77.8 % ± 1.4 | n/a |
| 50% | + Calibrated threshold | 3 of 3 seeds | 53.3 % ± 3.5 | 6.4 % ± 3.7 | 0.850 ± 0.027 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.775 ± 0.008 |
| 50% | + Top-1/top-2 margin rule | 3 of 3 seeds | 50.5 % ± 2.3 | 6.2 % ± 2.9 | 0.770 ± 0.036 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.749 ± 0.027 |
| 50% | + Calibrated confidence (instead of margin) | 3 of 3 seeds | 54.7 % ± 2.5 | 7.0 % ± 1.4 | 0.847 ± 0.017 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.500 ± 0.043 |
| 50% | + Average over a person's photos (instead of the best photo) | 3 of 3 seeds | 53.7 % ± 9.4 | 5.4 % ± 3.9 | 0.861 ± 0.026 | 87.8 % ± 3.8 | 77.8 % ± 1.4 | 0.725 ± 0.007 |
| 50% | + Flip test-time augmentation | 3 of 3 seeds | 52.5 % ± 0.9 | 7.6 % ± 3.5 | 0.760 ± 0.028 | 83.4 % ± 1.5 | 77.9 % ± 1.3 | 0.733 ± 0.029 |
| 60% | Nearest neighbour (no rejection) | 0 of 3 seeds | 83.6 % ± 1.8 | 100.0 % ± 0.0 | n/a | 83.6 % ± 1.8 | 77.8 % ± 1.4 | n/a |
| 60% | + Calibrated threshold | 3 of 3 seeds | 64.3 % ± 2.2 | 12.9 % ± 4.9 | 0.850 ± 0.027 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.749 ± 0.006 |
| 60% | + Top-1/top-2 margin rule | 3 of 3 seeds | 60.5 % ± 0.2 | 13.8 % ± 4.2 | 0.779 ± 0.020 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.711 ± 0.014 |
| 60% | + Calibrated confidence (instead of margin) | 3 of 3 seeds | 61.7 % ± 3.3 | 11.4 % ± 2.5 | 0.847 ± 0.017 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.352 ± 0.047 |
| 60% | + Average over a person's photos (instead of the best photo) | 3 of 3 seeds | 62.9 % ± 8.7 | 12.2 % ± 8.0 | 0.861 ± 0.026 | 87.8 % ± 3.8 | 77.8 % ± 1.4 | 0.703 ± 0.010 |
| 60% | + Flip test-time augmentation | 3 of 3 seeds | 60.2 % ± 1.1 | 13.9 % ± 4.8 | 0.776 ± 0.020 | 83.4 % ± 1.5 | 77.9 % ± 1.3 | 0.710 ± 0.023 |
| 70% | Nearest neighbour (no rejection) | 0 of 3 seeds | 83.6 % ± 1.8 | 100.0 % ± 0.0 | n/a | 83.6 % ± 1.8 | 77.8 % ± 1.4 | n/a |
| 70% | + Calibrated threshold | 3 of 3 seeds | 72.7 % ± 2.2 | 28.6 % ± 8.0 | 0.850 ± 0.027 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.715 ± 0.008 |
| 70% | + Top-1/top-2 margin rule | 3 of 3 seeds | 71.4 % ± 2.1 | 25.0 % ± 4.7 | 0.827 ± 0.048 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.710 ± 0.011 |
| 70% | + Calibrated confidence (instead of margin) | 3 of 3 seeds | 73.3 % ± 1.0 | 25.5 % ± 4.8 | 0.847 ± 0.017 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.179 ± 0.034 |
| 70% | + Average over a person's photos (instead of the best photo) | 3 of 3 seeds | 70.5 % ± 5.0 | 21.4 % ± 7.9 | 0.861 ± 0.026 | 87.8 % ± 3.8 | 77.8 % ± 1.4 | 0.680 ± 0.009 |
| 70% | + Flip test-time augmentation | 3 of 3 seeds | 73.0 % ± 0.7 | 28.8 % ± 4.6 | 0.814 ± 0.025 | 83.4 % ± 1.5 | 77.9 % ± 1.3 | 0.696 ± 0.009 |
| 80% | Nearest neighbour (no rejection) | 0 of 3 seeds | 83.6 % ± 1.8 | 100.0 % ± 0.0 | n/a | 83.6 % ± 1.8 | 77.8 % ± 1.4 | n/a |
| 80% | + Calibrated threshold | 2 of 3 seeds | 81.5 % ± 1.4 | 79.7 % ± 19.9 | 0.850 ± 0.027 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.615 ± 0.073 |
| 80% | + Top-1/top-2 margin rule | 2 of 3 seeds | 80.9 % ± 2.2 | 76.0 % ± 21.2 | 0.836 ± 0.039 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.599 ± 0.060 |
| 80% | + Calibrated confidence (instead of margin) | 2 of 3 seeds | 81.7 % ± 1.2 | 77.9 % ± 21.3 | 0.847 ± 0.017 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.048 ± 0.036 |
| 80% | + Average over a person's photos (instead of the best photo) | 3 of 3 seeds | 84.1 % ± 1.6 | 59.5 % ± 11.2 | 0.861 ± 0.026 | 87.8 % ± 3.8 | 77.8 % ± 1.4 | 0.620 ± 0.019 |
| 80% | + Flip test-time augmentation | 2 of 3 seeds | 82.0 % ± 1.7 | 80.1 % ± 17.2 | 0.838 ± 0.037 | 83.4 % ± 1.5 | 77.9 % ± 1.3 | 0.584 ± 0.050 |
| 90% | Nearest neighbour (no rejection) | 0 of 3 seeds | 83.6 % ± 1.8 | 100.0 % ± 0.0 | n/a | 83.6 % ± 1.8 | 77.8 % ± 1.4 | n/a |
| 90% | + Calibrated threshold | 0 of 3 seeds | 83.6 % ± 1.8 | 99.6 % ± 0.3 | 0.850 ± 0.027 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.550 ± 0.016 |
| 90% | + Top-1/top-2 margin rule | 0 of 3 seeds | 83.6 % ± 1.8 | 99.6 % ± 0.3 | 0.850 ± 0.027 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.550 ± 0.016 |
| 90% | + Calibrated confidence (instead of margin) | 0 of 3 seeds | 83.6 % ± 1.8 | 99.6 % ± 0.3 | 0.847 ± 0.017 | 83.6 % ± 1.8 | 77.8 % ± 1.4 | 0.013 ± 0.006 |
| 90% | + Average over a person's photos (instead of the best photo) | 0 of 3 seeds | 87.8 % ± 3.8 | 99.7 % ± 0.3 | 0.861 ± 0.026 | 87.8 % ± 3.8 | 77.8 % ± 1.4 | 0.496 ± 0.020 |
| 90% | + Flip test-time augmentation | 0 of 3 seeds | 83.4 % ± 1.5 | 99.5 % ± 0.5 | 0.849 ± 0.027 | 83.4 % ± 1.5 | 77.9 % ± 1.3 | 0.549 ± 0.019 |

**What the table says**

* **Embedding quality is good:** closed-set Rank-1 83.6 % ± 1.8, mAP 77.8 % ± 1.4 (best photo per person), ROC-AUC 0.850 ± 0.027 for telling enrolled people from strangers.
* **The open-set price is high.** With the plain threshold rule the test FAR is **6.4 %** at 50 % recall, **12.9 %** at 60 %, **28.6 %** at 70 %, and about **80 %** at 80 % recall (the 80 % target was reached on calibration for only 2 of 3 seeds). **A 90 % recall target is unreachable** - the best possible DIR@1 is the Rank-1 of 83.6 % - and the best-effort threshold accepts 99.6 % of strangers. Body appearance alone cannot give a low FAR at high recall; this is the "low inter-class variance" problem, measured.
* **Negative result - the top-1/top-2 margin rule did not help:** at 70 % recall FAR 25.0 % ± 4.7 vs 28.6 % ± 8.0 for the plain threshold (inside the noise) and it lowered recall and ROC-AUC. **Calibrated confidence** was equivalent (25.5 % ± 4.8). **Flip augmentation** gave nothing (28.8 % ± 4.6).
* **Averaging a person's photos** (instead of taking the best photo) was the best *free* change: FAR 21.4 % ± 7.9 at 70 % recall and 59.5 % ± 11.2 at 80 % (reached on all 3 seeds), Rank-1 87.8 % ± 3.8 - but the standard deviations are large and the recall actually reached differs between variants (70.5 % vs 72.7 %), so treat it as *promising, not proven*.
* **Threshold-only rejection has a structural weakness:** a stranger only has to resemble *one* of 60 enrolled people (180 photos) to be accepted, so FAR grows quickly as the gallery grows. This is why the product uses the face first.

## 3. Does metric-learning fine-tuning help? (seed 0 only, TEST people)

The last stage of the network was fine-tuned for 3 epochs × 30 batches (16 people × 4 photos) with **batch-hard triplet loss** (cosine distance, margin 0.3, hard-negative mining inside each batch) on the **590 development people only** (8,759 images, 2,650 s on this CPU).
The evaluation refuses a checkpoint if any person it was trained on appears in the calibration or test split (a leakage guard with its own test); none did. Checkpoint: `backend/weights/finetuned/market_seed0_head.pt` (git-ignored). Training seed: 0; **one seed, one training run - no confidence statement is possible beyond "this run"**.

| Target DIR@1 (calibration) | Variant | Target reached on calibration | Test DIR@1 (recall) | Test FAR | ROC-AUC | Rank-1 | mAP | Threshold |
|---|---|---|---|---|---|---|---|---|
| 50% | + Calibrated threshold | 1 of 1 seeds | 55.5 % ± 0.0 | 3.9 % ± 0.0 | 0.881 ± 0.000 | 83.1 % ± 0.0 | 76.3 % ± 0.0 | 0.780 ± 0.000 |
| 50% | + Top-1/top-2 margin rule | 1 of 1 seeds | 53.1 % ± 0.0 | 3.4 % ± 0.0 | 0.797 ± 0.000 | 83.1 % ± 0.0 | 76.3 % ± 0.0 | 0.760 ± 0.000 |
| 50% | + Triplet fine-tuned backbone | 1 of 1 seeds | 60.0 % ± 0.0 | 6.0 % ± 0.0 | 0.811 ± 0.000 | 89.7 % ± 0.0 | 87.3 % ± 0.0 | 0.795 ± 0.000 |
| 60% | + Calibrated threshold | 1 of 1 seeds | 64.8 % ± 0.0 | 8.4 % ± 0.0 | 0.881 ± 0.000 | 83.1 % ± 0.0 | 76.3 % ± 0.0 | 0.752 ± 0.000 |
| 60% | + Top-1/top-2 margin rule | 1 of 1 seeds | 60.7 % ± 0.0 | 9.7 % ± 0.0 | 0.797 ± 0.000 | 83.1 % ± 0.0 | 76.3 % ± 0.0 | 0.712 ± 0.000 |
| 60% | + Triplet fine-tuned backbone | 1 of 1 seeds | 64.1 % ± 0.0 | 6.0 % ± 0.0 | 0.901 ± 0.000 | 89.7 % ± 0.0 | 87.3 % ± 0.0 | 0.806 ± 0.000 |
| 70% | + Calibrated threshold | 1 of 1 seeds | 73.8 % ± 0.0 | 22.2 % ± 0.0 | 0.881 ± 0.000 | 83.1 % ± 0.0 | 76.3 % ± 0.0 | 0.719 ± 0.000 |
| 70% | + Top-1/top-2 margin rule | 1 of 1 seeds | 73.8 % ± 0.0 | 22.2 % ± 0.0 | 0.881 ± 0.000 | 83.1 % ± 0.0 | 76.3 % ± 0.0 | 0.719 ± 0.000 |
| 70% | + Triplet fine-tuned backbone | 1 of 1 seeds | 72.1 % ± 0.0 | 11.4 % ± 0.0 | 0.901 ± 0.000 | 89.7 % ± 0.0 | 87.3 % ± 0.0 | 0.779 ± 0.000 |
| 80% | + Calibrated threshold | 0 of 1 seeds | 83.1 % ± 0.0 | 100.0 % ± 0.0 | 0.881 ± 0.000 | 83.1 % ± 0.0 | 76.3 % ± 0.0 | 0.532 ± 0.000 |
| 80% | + Top-1/top-2 margin rule | 0 of 1 seeds | 83.1 % ± 0.0 | 100.0 % ± 0.0 | 0.881 ± 0.000 | 83.1 % ± 0.0 | 76.3 % ± 0.0 | 0.532 ± 0.000 |
| 80% | + Triplet fine-tuned backbone | 1 of 1 seeds | 87.9 % ± 0.0 | 58.5 % ± 0.0 | 0.901 ± 0.000 | 89.7 % ± 0.0 | 87.3 % ± 0.0 | 0.642 ± 0.000 |

(The `+ Calibrated threshold` and `+ Top-1/top-2 margin rule` rows are the **pretrained** model on the same seed-0 people; `+ Triplet fine-tuned backbone` is the fine-tuned one.)

* Closed-set quality rose from **Rank-1 83.1 % → 89.7 %** and **mAP 76.3 % → 87.3 %**.
* At **70 % recall** the false-accept rate fell from **22.2 % to 11.4 %**; at **80 %** the target went from **unreachable (FAR 100 %) to reachable with FAR 58.5 %**.
* At the **lowest recalls the result is mixed** (50 %: FAR 3.4 % → 6.0 %, i.e. not better; 60 %: 9.7 % → 6.0 %). With 60 stranger people the FAR resolution is coarse, and this is a single seed.
* The fine-tuned checkpoint is **not** the product default: it is trained on Market-1501 people and would need re-validation on any other camera. Use it via `REID_EMBEDDING_CHECKPOINT`.

## 4. What was not run

`NOT_RUN`: fine-tuning for seeds 1 and 2 (about 45 minutes each on this CPU); full-backbone fine-tuning (`--trainable all`); any experiment on a second dataset or on same-clothing ground truth; face + body on pedestrian data.
