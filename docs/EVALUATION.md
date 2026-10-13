# Evaluation - protocol, ablations, calibration and the low-variance subset

> **Scope note (face matching).** The Evaluation Lab, the calibration workflow and the Lookalike Failure Lab measure the **body** model: their datasets (Market-1501 and the smoke-test set) are full-body crops without readable faces, so face matching cannot take part in them and they are always run under the body-only rules. The face stage has its own measurements - the standard LFW benchmark and an end-to-end face-versus-clothing check - described in [FACE_AND_BODY_MATCHING.md](FACE_AND_BODY_MATCHING.md) and reproducible with `scripts/evaluate_face_lfw.py` and `scripts/verify_face_vs_body.py`.

Code: [`backend/app/evaluation/`](../backend/app/evaluation/). Run it from the **Evaluation Lab** screen or the scripts
[`run_evaluation.py`](../scripts/run_evaluation.py) / [`calibrate_threshold.py`](../scripts/calibrate_threshold.py). Metric definitions: [METRICS.md](METRICS.md).

> **Status.** The whole pipeline is implemented, unit-tested and verified end to end on a *synthetic* smoke-test set. **It has not been run on a public benchmark yet**, because Market-1501 is research-licensed and must be supplied
> by you (README §9). Nothing in this repository claims benchmark performance. Section 7 shows what the pipeline did on the synthetic set - *only* as evidence that it behaves honestly, not as an accuracy result.

## 1. The protocol: who may appear where

People (identities) are split **by person**, never by photo, into three groups that never overlap:

| Group | Used for | Never used for |
|---|---|---|
| **Development** (default 40 %) | optional fine-tuning, hard-negative mining | any scoring |
| **Calibration** (20 %) | choosing thresholds, margins, the confidence model, and which variant is "selected" | the reported results |
| **Test** (the rest) | the final, reported numbers | choosing anything |

Inside **calibration** and **test**, people are split again (default half / half):

- **enrolled** people: a few photos (default 3, spread over as many cameras as possible) form the **gallery**; their remaining photos are **known queries**.
- **unknown** people: they are *never* in the gallery; every photo of theirs is an **unknown query** (a stranger).

Guarantees, all re-checked by `Protocol.assert_disjoint()` and covered by tests: identity-disjoint groups; a gallery photo is never also a query; enrolled people never appear as strangers; one seed makes the split reproducible
(`test_same_seed_gives_identical_protocol_and_other_seeds_differ`). With several seeds, each seed re-draws the partition, which shows how stable the result is. Defaults are CPU-friendly (`max_images_per_identity = 12`); lift the caps for a full run.

Photos come from a **cross-camera** protocol (a query ignores the true person's gallery photos from its own camera - see METRICS §6). The pretrained weights were not trained on Market-1501, so no people in it are "seen" by the network.

## 2. The ablation: what does each ingredient buy?

Each variant adds **one** ingredient to its parent and is measured with the same metrics on the same test people ([`ablation.py`](../backend/app/evaluation/ablation.py)):

| Variant | Parent | What changes |
|---|---|---|
| `nn_baseline` - nearest neighbour | - | closed-set behaviour: always names the closest person. FAR = 100 % by construction (it cannot say "unknown") |
| `thr` - + calibrated threshold | nn_baseline | accept only if top-1 similarity ≥ a threshold chosen on the calibration people |
| `thr_margin` - + top-1/top-2 margin | thr | also require the winner to beat the runner-up by a margin (grid-searched on calibration people) |
| `thr_confidence` - + calibrated confidence | thr | *instead of* the margin: threshold a logistic confidence fitted from similarity and margin |
| `thr_margin_flip` - + flip augmentation | thr_margin | average each embedding with that of the mirrored crop |
| `thr_margin_finetuned` - + triplet fine-tuned backbone | thr_margin | only if a checkpoint exists; otherwise reported as *unavailable* with the reason |

**Selection of the "final configuration"** uses **calibration numbers only** (lowest calibration FAR among variants that reached the recall target; ties go to the simpler variant) - never the test numbers. If no variant reaches the target the report says
"no configuration selected" and shows what each variant achieved anyway. `tests/test_evaluation_pipeline.py::test_impossible_target_yields_no_selected_variant`.

The embedding cache stores *plain* and *mirrored* embeddings separately, so flip augmentation costs no extra model passes; folded and un-folded networks never share a cache.

## 3. Operating point and calibration

The PS-1 goal - *minimise the false-accept rate at a fixed recall* - is the default mode (`fixed_recall`); `fixed_far` is the mirror image. See METRICS §4 for how the rule is selected, why steps are not interpolated, and how sample size is reported.
`run_calibration` embeds **only the calibration people** and never opens a test image (proved by `test_calibration_run_never_embeds_a_test_image`), so a calibration can be done without exposing the test split at all.
Applying a calibration to the live system additionally requires: the run succeeded, the target was achieved, and its model fingerprint equals the running model's.

## 4. The low inter-class variance (same-clothing) subset

Standard benchmarks have **no clothing labels**, so a ground-truth "same clothing" attribute cannot be claimed. Two mechanisms are provided and the report always names which was used:

1. **Proxy (default, label-free, model-independent)** - [`hard_subset.py`](../backend/app/evaluation/hard_subset.py). For each query, torso and leg **colour histograms** (HSV, 8×3×3 bins) are compared with the
   closest *other* enrolled person's; the top quartile (separately for known and unknown queries) form the hard subset. It never looks at the ReID model, the threshold or any test outcome, so it cannot be cherry-picked after seeing results.
2. **Manual annotation (override)** - a human lists, in `datasets/<name>/hard_subset.json`, the queries whose clothing really resembles another enrolled person (`python scripts/prepare_dataset.py template <name>` creates the file). When present it replaces the proxy.

The same frozen rule is applied to all queries and to the hard subset, and a second analysis re-selects the threshold on the *calibration* look-alikes to show the **price of holding the same target against look-alikes** (extra recall lost, or FAR that cannot be held).

## 5. Reproducibility record

Every result stores: the full request (dataset, seeds, target, protocol), per-seed split sizes, the model fingerprint (name + weight hash + options), software versions (Python, torch, numpy), duration, the checkpoint used, and which hard-subset method ran.
Same seed + same cache → identical numbers (`test_runs_are_reproducible_with_fixed_seeds`).

## 6. Running the benchmark (once you have the dataset)

```powershell
backend\.venv\Scripts\python.exe scripts\prepare_dataset.py inspect market1501
backend\.venv\Scripts\python.exe scripts\run_evaluation.py --dataset market1501 --mode fixed_recall --target-recall 0.90 --seeds 0 1 2
backend\.venv\Scripts\python.exe scripts\run_evaluation.py --dataset market1501 --mode fixed_far --target-far 0.01 --seeds 0 1 2
```

The first run embeds the images on the CPU (cached afterwards). For a quick look add `--max-identities 150`. The Markdown report (`backend/data/reports/…md`) is ready to paste into a write-up; the JSON holds every curve and count.

## 7. What the pipeline did on the synthetic smoke-test set (NOT a benchmark)

`scripts/make_smoke_dataset.py` draws cartoon mannequins in look-alike groups of four (same clothing colours). A network trained on real photos separates them poorly - which makes it a useful test of the pipeline's *honesty*:

| Check | What happened |
|---|---|
| Ask for **90 % recall** | The system reported **"target not reached"** for every variant, selected **no configuration**, labelled its fallback threshold *not calibrated*, and refused to apply it. (Closed-set Rank-1 was only 39.6 % ± 9.6 % over two seeds.) |
| Ask for a relaxed **30 % recall** | The calibration found threshold **0.918** with FAR **31.25 %** on 80 strangers (25 accepted), 95 % upper bound **40.3 %**, and displayed that the score distributions of enrolled people and strangers overlap almost completely. |
| Effect of applying it | A green-shirted stranger that the unvalidated default (0.70) had **accepted at 0.823** was **rejected** after calibration - and, as the PS-1 trade-off predicts, the enrolled person (0.813) was rejected too. Raising the bar to keep strangers out costs recall when everyone looks alike. |

These are properties of a synthetic toy set. Do not quote them as accuracy.

## 8. Tests that guard this subsystem

`tests/test_metrics.py` (hand-computed values) · `tests/test_evaluation_pipeline.py` (identity-disjoint splits, leakage detection, cross-camera masking, calibration/test separation, reproducibility, unreachable targets, cache, dataset readers) ·
`tests/test_training_and_model.py` (fine-tune leakage guard) · `tests/test_api_config_and_jobs.py` (background jobs, cancel, failure, apply-calibration rules) ·
`tests/test_sandbox.py` (the sandbox rule equals the live decision engine on 3,200 random cases; the sandbox replays a run's own test numbers exactly) · `tests/test_lookalike.py` (exact pair mining, threshold isolation, leakage refusal, hypotheses always labelled unproven, reproducibility) ·
`tests/test_api_lab_and_video.py` (the lab, exports, image serving and the sandbox through the HTTP API).

## 9. Threshold sandbox

*"What would change if I moved the dial?" - answered with real counts, without changing anything.*

Every finished evaluation run (first seed, plain embeddings) and every look-alike experiment stores a compact **per-query table** for its calibration and test splits: who the query really was, which enrolled person the matcher
picked, the best similarity, the lead over the runner-up, and whether the pick was right ([`evaluation/sandbox.py`](../backend/app/evaluation/sandbox.py)). The sandbox endpoint re-counts *that table* under any trial threshold/margin rule:

* **Same rule as the live system.** `decide_rows` reproduces rules 3-5 of the decision engine (below threshold → UNKNOWN; margin too small → REVIEW or UNKNOWN; otherwise MATCH). `tests/test_sandbox.py` checks it against `decide()` on 3,200 random cases, and replaying a run's own rule reproduces that run's reported FAR and recall exactly.
* **Fixed evaluation set.** Nothing is re-embedded or re-run, so the numbers compare like with like.
* **Output.** The five outcome counts (true accepts, wrong-identity accepts, false accepts, false rejects, true rejects) plus REVIEW counts; FAR with a 95 % upper bound; recall; the same figures for the run's calibrated rule; and the individual queries whose decision changes (strangers who would now get in are listed first).
* **It cannot write.** There is no "apply" in the sandbox and no code path from it to the policy tables (`writes_policy` is always `false`; `test_trying_thresholds_changes_the_counts_but_never_the_active_policy`). The only route to a new production threshold is a calibration run on the calibration split followed by an explicit, audited apply in Model & System Settings.
* **Test-split caution.** Looking at test numbers while moving the slider is fine for understanding the trade-off, but keeping the value that looks best there would be tuning on the test set; the response carries that warning for the test split.

The **Lookalike Failure Lab** ([LOOKALIKE_LAB.md](LOOKALIKE_LAB.md)) builds on the same protocol and scoring code and adds look-alike mining, a reproducible challenge set and failure inspection.
