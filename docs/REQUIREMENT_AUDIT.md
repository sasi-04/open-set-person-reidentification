# Requirement audit (code-verified, 2026-11-03)

**Limitation, stated first:** the original Zed Digital PS-1 problem statement is **not stored in this repository**. The requirement list below is the one recorded in [REQUIREMENTS_TRACEABILITY.md](REQUIREMENTS_TRACEABILITY.md) §A, which paraphrases it; every row is therefore **NOT_VERIFIED against the original wording** until the exact text is supplied. Statuses: `VERIFIED` (implemented and shown to work by an executed test or measurement) · `PARTIALLY_IMPLEMENTED` · `MISSING` · `NOT_VERIFIED` · `NOT_APPLICABLE`.

**What was executed for this audit:** backend suite **431 passed** (6 min 14 s, 2026-11-03); frontend suites for the changed screens 82 passed (the full 157-test run dates from 2026-10-13); real-model evaluation on Market-1501 (5 recall targets × 3 seeds, plus a leakage-guarded fine-tuning run); a closed-set embedding check ([MODEL_VERIFICATION.md](MODEL_VERIFICATION.md)); the home-page example on the live server.

## 1. Headline finding of the audit

The previous submission *looked* complete but its central component did not work: the shipped OSNet-AIN weights reached **Rank-1 20 %** on real cross-camera data, which no test noticed because the tests checked shape, norm and determinism, never discrimination. This is fixed (verified model: Rank-1 83.6 %, mAP 77.8 %, 3 seeds) and the benchmark that was previously "pending" has now been run. The remaining gap is *performance*, not plumbing: body appearance alone gives a high false-accept rate at high recall (table in [EXPERIMENT_RESULTS.md](EXPERIMENT_RESULTS.md)).

## 2. Matrix

| # | Requirement | Where | How verified | Status | Gap / correction | Evidence |
|---|---|---|---|---|---|---|
| 1 | Re-identify against an **open set** with near-identical identities | `cv/open_set/` (decision engine, multicue) | unit tests (24 + 54) and the 13-photo example | **VERIFIED** (mechanism) | measured on a benchmark only for the **body** path | `test_decision_engine.py`, `test_face_matching.py`, `docs/results/open_set_example.json` |
| 2 | **Minimise FAR at a fixed recall** | `evaluation/calibration.py`, `scripts/run_evaluation.py` | executed on Market-1501 at 50/60/70/80/90 % | **VERIFIED** (pipeline and measurement) | **performance is modest**: FAR 6.4 / 12.9 / 28.6 / ~80 % at 50 / 60 / 70 / 80 % recall; 90 % unreachable | `docs/results/market1501/`, EXPERIMENT_RESULTS §2 |
| 3 | Person **detection** (Faster R-CNN MobileNetV3) | `cv/detection/detector.py` | API/unit tests; real photo end to end | **VERIFIED** (function) / **NOT_VERIFIED** (detection accuracy) | detector accuracy never benchmarked; not needed for the Market-1501 evaluation (crops) | `test_api_reid.py`, README §3 |
| 4 | **Embeddings**: genuine pretrained, 512-d, finite, normalised, repeatable | `cv/embedding/` | real-model tests + discrimination check | **VERIFIED** (after the fix) | before the fix: shape-only checks hid a 20 % Rank-1 model | `test_training_and_model.py` (real-model tests), `scripts/verify_embedding.py`, MODEL_VERIFICATION |
| 5 | Similarity and matching (cosine on unit vectors, identity aggregation, empty gallery, invalid vectors) | `cv/retrieval/` | unit tests incl. new average-aggregation | **VERIFIED** | default aggregation = best photo; average tested as an ablation | `test_ranking_and_index.py` |
| 6 | **MATCH / UNKNOWN / REVIEW** with defined conditions; never auto-accept the nearest | `cv/open_set/*` | unit tests, written rules | **VERIFIED** | thresholds still **unvalidated** for any camera other than Market-1501 | ALGORITHM_EXPLANATION §6 |
| 7 | Open-set rejection validated on data | evaluation lab | executed | **VERIFIED** for body path; **PARTIALLY_IMPLEMENTED** overall | face + body not benchmarked (faces too small in Market-1501) | EXPERIMENT_RESULTS, LIMITATIONS §1-2 |
| 8 | **Calibration**: identity-disjoint splits, thresholds from validation not test, report if unreachable, sample-size honesty | `evaluation/protocol.py`, `calibration.py` | unit tests (leakage, disjointness) + executed | **VERIFIED** | FAR here is query-level open-set, documented and kept apart from pairwise FAR | `test_splits_are_identity_disjoint`, EVALUATION_PROTOCOL |
| 9 | **Metrics**: TP/FP/FN, recall, precision, FAR, ROC, AUC, FAR-at-recall, latency, throughput | `evaluation/metrics.py`, `performance.py` | hand-computed unit tests; executed | **VERIFIED** | - | `test_metrics.py`, METRICS.md |
| 10 | **Dataset experiment** on a public benchmark | `datasets/market1501` (git-ignored) | executed, provenance recorded | **PARTIALLY_IMPLEMENTED** | third-party copy **without the official `query/` folder**; own protocol, CPU-sized subset (5,067 images); not comparable with leaderboards | EVALUATION_PROTOCOL §2 |
| 11 | **Same-clothing / low inter-class variance subset** | `evaluation/hard_subset.py` | executed (proxy) | **PARTIALLY_IMPLEMENTED** | colour-histogram proxy only - no clothing labels exist for Market-1501 | EXPERIMENT_RESULTS, LIMITATIONS §4 |
| 12 | **Ablations** isolating each component | `evaluation/ablation.py` | executed: baseline, threshold, margin, confidence, flip, **average aggregation**, fine-tuning | **VERIFIED** | margin/confidence/flip: **no gain** (reported); fine-tuning: seed 0 only | EXPERIMENT_RESULTS §2-3 |
| 13 | **Metric learning** (triplet, hard negatives, validation, checkpoint, seed) | `training/`, `scripts/finetune_triplet.py` | unit tests + one real training run | **VERIFIED** (one seed) | trained on dev people only (leakage guard), last stage only; seeds 1-2 and full-backbone are `NOT_RUN` | EXPERIMENT_RESULTS §3 |
| 14 | **Real-time** inference | measured | executed | **PARTIALLY_IMPLEMENTED** | 0.2 s per crop on 2 CPU cores; interactive, **not video-rate**; no claim made | `docs/results/performance_idle.json`, PERFORMANCE.md |
| 15 | One compact backbone; no fixed identity count | registry, gallery | tests | **VERIFIED** | 2.2 M parameters, no classifier head | `test_api_gallery.py` |
| 16 | Frontend workflows (upload, boxes, enroll, match, explain, evaluate, ROC, compare, export, status) | `frontend/src` | UI tests against a pretend server + screenshots of the real app | **VERIFIED** (workflows) | tests use a fake server by design; real-server flows were checked by script/screenshot | 157 UI tests (2026-10-13), manual |
| 17 | Backend quality (validation, limits, cleanup, model reuse, concurrency, auth, CORS) | `backend/app` | 431 tests | **VERIFIED** | auth is off by default (single-user local use) | `test_api_*.py` |
| 18 | Privacy: authorised data only, consent, deletion | enroll flow, docs | tests + docs | **VERIFIED** (mechanisms) | legal compliance is **NOT_APPLICABLE** to a prototype; face data is biometric | SECURITY_AND_PRIVACY.md |
| 19 | Documentation set (audit, architecture, plan, algorithm, protocol, results, API, limitations) | `docs/` | reviewed | **VERIFIED** | numbers in older PDFs (jury deck, manual) pre-date the model fix where noted | this folder |
| 20 | Docker / deployment configuration | - | none in repository | **MISSING** | the project runs through `scripts/start.ps1`; no container files exist | - |

## 3. Highest-priority blockers (and what was done)

1. **Non-discriminative embedding weights** - fixed and verified (blocker removed).
2. **No benchmark evidence for the headline metric** - measured (blocker removed); the *result* is modest.
3. **High FAR at high recall (body only)** - addressed in part: average aggregation and fine-tuning help in these runs; not solved. The architectural answer is the face channel, which cannot be benchmarked on this data.
4. **Original problem statement absent** - open: supply it and the matrix will be re-checked line by line.
