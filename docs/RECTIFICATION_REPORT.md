# Rectification report - OpenID Vision (Task 1: open-set person re-identification)

*Prepared after the review feedback that the person-matching model "barely works on real data". This report says what was wrong, what was changed, what is now measured and what is still not good enough. Nothing here is estimated or hand-typed: every number is read from files in `docs/results/` and can be regenerated with the commands in section 6.*

## 1. What was wrong

| Problem | Evidence |
|---|---|
| **The embedding model did not work.** The OSNet-AIN weight file that shipped with the project reached only **Rank-1 20 % / mAP 13 %** on real cross-camera pictures (100 Market-1501 people, chance = 1 %). | Same 20 % inside Torchreid's own reference code, so the network code was right and the *weight file* was unfit; a verified OSNet checkpoint scored **81 % / 69 %** under the identical protocol. [MODEL_VERIFICATION.md](MODEL_VERIFICATION.md) |
| **No test could have caught it.** Tests checked shape, unit length and determinism - never whether the vectors separate people. | `scripts/verify_embedding.py` now measures discrimination; a unit test pins the registry's verified/failed flags. |
| **There was no benchmark evidence for the headline objective** (false accepts at a fixed recall); the documents said "not run yet". | Now run: [EXPERIMENT_RESULTS.md](EXPERIMENT_RESULTS.md). |
| **Earlier quoted numbers came from the broken weights** (clothing-only "48 of 60 strangers accepted / 8 of 20 recognised"). | Re-measured with the verified model: **51 of 60 / 5 of 20**; face + body unchanged at 0 of 60 strangers accepted and 20 of 20 recognised. |

## 2. What was changed

* Default embedding model replaced by **OSNet x1.0 with the official Torchreid multi-source weights** (MSMT17 + DukeMTMC-reID + CUHK03; Market-1501 is *not* in its training data). The checkpoint is downloaded, **SHA-256 checked, converted once** to a tensors-only file and pinned by a **tensor content digest**; the application loads only that file with the safe loader. The failed OSNet-AIN files stay in the registry flagged *failed verification*.
* New ablation: **identity score = average over a person's photos** (instead of the best photo). Evaluation Lab updated.
* Real **Market-1501 evaluation** (identity-disjoint dev / calibration / test, thresholds chosen on calibration people only): 5 recall targets × 3 seeds, 7 variants, **leakage-guarded metric-learning fine-tune** (batch-hard triplet loss) evaluated on held-out people.
* Every stale claim ("Market-1501 not run", old scores) corrected in README, guides, generators and reference outputs; the 13-photo example and all 11 demo scenarios re-run (**11 of 11 behave as intended**).
* New documents: [REQUIREMENT_AUDIT](REQUIREMENT_AUDIT.md), [IMPLEMENTATION_PLAN](IMPLEMENTATION_PLAN.md), [ALGORITHM_EXPLANATION](ALGORITHM_EXPLANATION.md), [EVALUATION_PROTOCOL](EVALUATION_PROTOCOL.md), [EXPERIMENT_RESULTS](EXPERIMENT_RESULTS.md), [API_REFERENCE](API_REFERENCE.md) (generated from the code), [LIMITATIONS](LIMITATIONS.md).

## 3. What is now measured (Market-1501, body appearance only)

| Measure | Result (mean ± std, 3 seeds, held-out test people) |
|---|---|
| Closed-set Rank-1 / mAP | **83.6 % ± 1.8 / 77.8 % ± 1.4** (was 20 % / 13 % with the old weights) |
| ROC-AUC, enrolled vs stranger | **0.850 ± 0.027** |
| **False-accept rate at 50 % recall** (DIR@1) | **6.4 % ± 3.7** |
| ... at 60 % recall | **12.9 % ± 4.9** |
| ... at 70 % recall | **28.6 % ± 8.0** |
| ... at 80 % recall | **79.7 % ± 19.9** (target reached on calibration for 2 of 3 seeds) |
| ... at 90 % recall | **unreachable** (the best possible DIR@1 is the Rank-1, 83.6 %) |
| Top-1/top-2 margin rule, calibrated confidence, flip augmentation | **no improvement** (e.g. FAR at 70 % recall: 25.0 %, 25.5 %, 28.8 %) |
| Average over a person's photos | FAR **21.4 % ± 7.9** at 70 % and **59.5 % ± 11.2** at 80 % recall - promising, noisy |
| Triplet fine-tune (seed 0, single run) | Rank-1 **83.1 → 89.7 %**, mAP **76.3 → 87.3 %**, FAR at 70 % recall **22.2 → 11.4 %**, 80 % target **unreachable → reachable (58.5 %)**; mixed at the lowest recall (50 %: 3.4 → 6.0 %) |
| Speed (CPU, 2 cores, idle) | embedding **196 ms** per crop (p50), 235 ms (p95), 5.3 crops/s in batches; **not real-time video** |

**Honest reading.** The embedding now works and the benchmark exists. The open-set problem is *hard*: with body appearance alone a stranger only has to resemble one enrolled person to be accepted, so the FAR rises quickly with recall and a 90 % recall target cannot be met. The product's answer is to let the **face decide when it is usable** - on 13 public-domain portraits that gave 13 of 13 right with 0 of 3 same-clothes strangers accepted (clothes only: 4 of 13, 3 of 3 accepted) and on the LFW end-to-end check 20 of 20 recognised with 0 of 60 strangers accepted (clothes only: 5 of 20 and 51 of 60 accepted). **Those are small, easy-data demonstrations; face + body has not been benchmarked on pedestrian cameras** because Market-1501 images contain no usable faces.

## 4. What is still not good enough (stated, not hidden)

* Body-only FAR at high recall is high (table above); the margin rule did not help; the fine-tune gain rests on **one** training run and one seed.
* The benchmark copy has **no official query set**, so results are **not comparable** with published Market-1501 numbers; the same-clothing subset is a colour-histogram **proxy**.
* Face + body is unbenchmarked on pedestrian data; no fairness measurement; no liveness check; no GPU path tested; no Docker packaging; the PDFs (30-page manual, jury deck, HR script) are regenerated from the sources but the **manual's screenshots still show scores from before the model fix**.
* The original PS-1 problem statement is not stored in the repository, so the requirement audit could not be checked against its exact wording.

## 5. Quality evidence

Backend **431 tests passed** (6 min 14 s, 2026-11-03); frontend suites for the touched screens 82 passed; 11 of 11 demo scenarios; identity-disjointness and fine-tune leakage guard covered by tests; the embedding discrimination check is a script, not just a one-off.

## 6. Reproduce

```powershell
python scripts\download_weights.py                      # model: download, verify, convert, verify
python scripts\verify_embedding.py --dataset market1501 # Rank-1 / mAP sanity (add --model osnet_ain_x1_0 to see the failed file)
python scripts\run_evaluation.py --dataset market1501 --mode fixed_recall --target-recall 0.70 --recall-metric dir1 `
       --seeds 0 1 2 --max-identities 120 --max-images 8 --gallery-shots 3 --bootstrap 1000 --out-dir docs\results\market1501
python scripts\build_experiment_results.py              # regenerates EXPERIMENT_RESULTS.md from the saved runs
cd backend; .\.venv\Scripts\python.exe -m pytest        # 431 tests
```
