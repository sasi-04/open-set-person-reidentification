# Evaluation protocol - exactly what was measured

*The PS-1 objective: **minimise the false-accept rate at a fixed genuine-match recall.** This page states the protocol that produced every number in
[EXPERIMENT_RESULTS.md](EXPERIMENT_RESULTS.md). Metric formulas and a worked example are in [METRICS.md](METRICS.md); the code is `backend/app/evaluation/`.*

## 1. Two metrics that must not be confused

| Name | Question it answers | Used here? |
|---|---|---|
| **Open-set identification** (query level) | "A photo arrives. Does the system accept it and name the right enrolled person - or wrongly accept a stranger?" | **Yes - every headline number.** FAR = strangers for whom *any* enrolled person is named ÷ all stranger queries. Recall = **DIR@1** = known queries accepted **and** correctly named ÷ all known queries. |
| **Pairwise verification** | "Are these two photos the same person?" | Only inside the Lookalike Failure Lab, labelled as pair-level and never mixed with the above. |

Closed-set numbers (**Rank-1, Rank-5, mAP**) are reported *next to* them to show retrieval quality; they ignore thresholds and say nothing about rejecting strangers.

## 2. Data

| | |
|---|---|
| Dataset | **Market-1501** (Zheng et al., ICCV 2015): 1,501 identities, 6 cameras. Copy used: `bounding_box_train` + `bounding_box_test` pooled = **26,051 labelled images** after dropping junk (`0000`) and distractor (`-1`) files (loader: `evaluation/datasets.py`). |
| Source and licence | Third-party mirror `huggingface.co/datasets/aveocr/Market-1501-v15.09.15.zip` (archive SHA-256 `416BB77B...FE96`). **Non-commercial research use only**; kept in `datasets/` which git ignores - never committed or redistributed. |
| What is missing | That copy has **no official `query/` folder**, so the official Market-1501 query/gallery protocol is **not reproduced** and results here are **not comparable** to leaderboard numbers. |
| Clothing labels | None exist. The "same-clothing" subset is a label-free **proxy** (top quartile of torso/leg colour-histogram similarity to another enrolled person) - not ground truth. |
| Images actually processed | Reported per run (embedding cache: 5,067 distinct images for the main experiment). |

## 3. Splits (identity-disjoint, prevents leakage)

For each seed, identities are shuffled and divided into **development** (40 %, used only for optional fine-tuning), **calibration** (20 %) and **test** (the rest, capped). Nobody appears in more than one split.
Inside calibration and test, half of the people are **enrolled** (3 gallery photos each, `gallery_shots=3`) and half are **strangers** (never enrolled; also never enrolled in the *other* split).
Known queries are the enrolled people's remaining photos; stranger queries are the strangers' photos. At most 8 photos per person and 120 people per split are used (a CPU-sized subset; flags `--max-images 8 --max-identities 120`).
**Cross-camera rule:** a known query from camera *c* ignores that person's gallery photos from camera *c* (a person whose gallery has no other camera is dropped and counted).

| Split of seed 0 | Enrolled | Strangers | Gallery images | Known queries | Stranger queries |
|---|---|---|---|---|---|
| Calibration | 60 | 60 | 180 | 290 | 458 |
| Test | 60 | 60 | 180 | 290 | 465 |

## 4. Choosing the operating point - on calibration people only

1. For the target recall *R* (DIR@1), every observed score is tried as an "accept if similarity ≥ threshold" rule **on the calibration split**.
2. Rules reaching DIR@1 ≥ *R* are eligible; the one with the **lowest calibration FAR** is selected (ties prefer the simpler rule).
3. If no rule is eligible the result says `target_achieved = false`, shows a best-effort fallback labelled as such, and it cannot be applied as "calibrated".
4. The selected rule is **frozen** and scored once on the **test** split. The test split is never used to choose a threshold, margin or confidence model; curve-based figures that sweep thresholds on test data are labelled "not a pre-registered operating point".
5. Uncertainty: mean ± standard deviation over seeds (each seed re-draws who is enrolled and who is a stranger); within a seed a 95 % percentile bootstrap over **people** (not photos); calibration reports a Wilson upper bound and a "rule of three" sample-size warning.

## 5. Variants (ablation) - each differs from its parent by one ingredient

`nn_baseline` (no rejection) → `thr` (+ calibrated threshold) → `thr_margin` (+ top-1/top-2 margin) · `thr_confidence` (calibrated confidence instead of margin) · `thr_mean` (average over a person's photos instead of the best photo) · `thr_margin_flip` (+ flip augmentation) · `thr_margin_finetuned` (+ triplet fine-tuned backbone; refused automatically if it was trained on any evaluated person).

## 6. Reproduce it

```powershell
# one-time: the model and the data (see datasets/README.md for the dataset)
python scripts\download_weights.py
python scripts\verify_embedding.py --dataset market1501                    # sanity: does the embedding separate people at all?

python scripts\run_evaluation.py --dataset market1501 --mode fixed_recall --target-recall 0.70 --recall-metric dir1 `
       --seeds 0 1 2 --max-identities 120 --max-images 8 --gallery-shots 3 --bootstrap 1000 --out-dir docs\results\market1501
python scripts\summarise_results.py docs\results\market1501                 # the table in EXPERIMENT_RESULTS.md
```

Seeds, protocol fractions, model fingerprint, package versions and hardware are written into every result file (`metadata`). Cached embeddings make a re-run of the scoring take seconds; the first run takes about 50 minutes on the 2-core development laptop.

## 7. What these results can and cannot show

They show how well **body appearance alone** separates enrolled people from strangers on a public benchmark, under a stated protocol. They do **not** show face + body performance (Market-1501 images are too small to contain usable faces),
accuracy on other cameras, fairness across demographic groups, or production readiness.
