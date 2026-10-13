# Metrics - what every number means

Implemented in [`backend/app/evaluation/metrics.py`](../backend/app/evaluation/metrics.py) as plain arithmetic on arrays and verified against a
hand-computed example in [`backend/tests/test_metrics.py`](../backend/tests/test_metrics.py). The worked example below is the same one used by those tests,
so you can check the code against pencil and paper.

## 1. Two kinds of query - and why "FAR" here is not the usual FAR

An evaluation consists of **queries**. Each is one photo of one person:

- a **known** query: the person *is* enrolled (their *other* photos are in the gallery). The right answer is "accept, and name them".
- an **unknown** (stranger) query: the person is *not* enrolled. The right answer is "do not accept".

For each query the system produces the best enrolled candidate and its scores, and the decision rule says accept or not
(`accept` ⇔ similarity ≥ threshold **and** margin ≥ minimum margin, when a margin rule is set).

> **FAR is query-level.** An unknown query is *falsely accepted* whenever the decision engine accepts **any** enrolled identity for it.
> This is different from the pairwise verification error ("are these two photos the same person?"); pairwise numbers are not mixed in anywhere.

## 2. Definitions and denominators

| Metric | Formula | Denominator |
|---|---|---|
| **FAR** - False Accept Rate | unknown queries accepted ÷ unknown queries | **all unknown queries** |
| **TAR** - True Accept Rate | known queries accepted (any identity) ÷ known queries | **all known queries** |
| **FRR** - False Reject Rate | 1 − TAR | all known queries |
| **DIR@k** - Detection & Identification Rate at rank k | known queries that are **accepted** and whose true identity is among the top-k candidates ÷ known queries | **all known queries** |
| **DIR@1** | accepted **and the top candidate is the right person** | all known queries - *the honest "recall" of the system* |
| **Precision** | TP ÷ (TP + FP) | all accepted queries |
| **Recall** | TP ÷ (TP + FN) = DIR@1 | all known queries |
| **F1** | 2·P·R ÷ (P + R) | - |
| **Rank-k** (CMC) | known queries whose true identity ranks ≤ k ÷ known queries | known queries; **thresholds ignored** |
| **mAP** | mean over known queries of the average precision over the ranked gallery *images* | known queries that have a relevant image left |
| **OSCR / AUOSCR** | the curve DIR@1 vs FAR as the threshold sweeps; AUOSCR = area under it (Dhamija et al., 2018) | - |
| **AUROC (detection)** | area under TAR vs FAR: how well the top-1 score separates known from unknown, ignoring identity | - |

For the "name the right person" task: **TP** = known, accepted, correct identity · **FP** = accepted but wrong (a stranger, or an enrolled person given the wrong name) ·
**FN** = a known query not correctly accepted. Queries sent to **review** are counted as *not accepted* in these automatic-decision metrics (the conservative choice), and the review rate is reported separately in the live history.

*Why DIR@1 and TAR are both reported:* TAR counts an enrolled person as "accepted" even when the system names the **wrong** enrolled person, so it can flatter the system. DIR@1 cannot.
The Evaluation Lab lets you choose which one defines "recall" (default DIR@1) and plots both.

## 3. A worked example (the same as the unit tests)

| Query | Kind | Top-1 similarity | Margin | Top-1 correct? | True rank |
|---|---|---|---|---|---|
| K1 | known | 0.90 | 0.30 | yes | 1 |
| K2 | known | 0.80 | 0.20 | yes | 1 |
| K3 | known | 0.70 | 0.05 | **no** | 2 |
| K4 | known | 0.60 | 0.10 | yes | 1 |
| K5 | known | 0.40 | 0.02 | **no** | 3 |
| U1 | unknown | 0.75 | 0.10 | - | - |
| U2 | unknown | 0.50 | 0.05 | - | - |
| U3 | unknown | 0.30 | 0.01 | - | - |
| U4 | unknown | 0.65 | 0.08 | - | - |

**Rule: threshold 0.65, no margin.** Accepted: K1, K2, K3, U1, U4.

- FAR = 2 of 4 unknown (U1, U4) = **0.50** · TAR = 3 of 5 known (K1, K2, K3) = **0.60** · FRR = 0.40
- DIR@1 = K1, K2 = 2 of 5 = **0.40** (K3 was accepted but *named the wrong person*) · DIR@5 = K1, K2, K3 = 3 of 5 = **0.60**
- Precision = 2 correct ÷ 5 accepted = 0.40 · Recall = 0.40 · F1 = 0.40

**Add a margin rule ≥ 0.10.** K3 (margin 0.05) and U4 (0.08) are no longer accepted: FAR = 1 of 4 = **0.25**, TAR = 2 of 5 = 0.40, precision = 2 ÷ 3 = 0.67. *The margin removed one false accept without costing any correct accept - which is exactly what it is for.*

**Curves.** Sweeping the threshold over every observed score gives the ROC points; area under TAR vs FAR = **0.70** (= the chance a random known query outscores a random stranger: 14 of 20 pairs), and under DIR@1 vs FAR (AUOSCR) = **0.50**.
CMC: Rank-1 = 0.6, Rank-2 = 0.8, Rank-3 = 1.0.

## 4. Choosing the operating point (and being honest about it)

**Fixed recall → minimise false accepts** (the PS-1 objective, default): among rules reaching DIR@1 ≥ R on the *calibration* people, take the one with the lowest FAR.
**Fixed FAR → maximise recall:** among rules with FAR ≤ F, take the highest DIR@1.

Both are step functions of the observed scores - **no interpolation** - and the chosen threshold is an actual observed score ("accept if similarity ≥ it"). Ties prefer the simpler rule (no margin / smaller margin).
If no rule reaches the target the result is `target_achieved = false`, a best-effort fallback is shown *clearly labelled as such*, and it cannot be applied as "calibrated".

**Sample size.** A rate cannot be resolved more finely than the sample allows. Reports therefore show, next to every calibration FAR, the number of stranger queries and a one-sided 95 % **Wilson upper bound**
(with zero false accepts among 100 strangers the bound is still ≈ 2.6 %). The "rule of three" flag warns when fewer than ≈ 3 ÷ FAR strangers exist to demonstrate a target (e.g. 300 strangers for FAR 1 %).
**A threshold selected on one sample is a measurement, not a guarantee.**

## 5. Uncertainty

Intervals are **percentile bootstrap over people** (`cluster_bootstrap_ci`): whole identities are resampled with replacement, because photos of one person are not independent - resampling single photos would give intervals that are far too narrow.
All reported rates at a frozen rule are re-computed on each resample; with several seeds the table shows mean ± standard deviation across seeds instead (each seed re-draws who is enrolled).

## 6. Closed-set retrieval metrics and the cross-camera rule

Rank-k and mAP ignore thresholds and ask "can the system retrieve at all?". Following the Market-1501 protocol, when a known query comes from camera *c*, gallery photos of the **same person from camera *c*** are ignored
(matching two frames from one camera is too easy). Only the true person's same-camera photos are hidden; strangers are never handicapped. A known query whose person has no gallery photo from another camera cannot be scored fairly and is
**dropped and counted** in the report (`dropped_same_camera_only`).

## 7. Confidence calibration quality

The optional *calibrated confidence* is a logistic model fitted on the calibration split: `P(top-1 is the correct enrolled identity | similarity, margin)`. Its quality on the **test** split is reported with
**Expected Calibration Error** (average gap between predicted and observed correctness over 10 bins; lower is better) and the **Brier score**. It depends on the known:unknown mix of the calibration data, and only applies to the model it was fitted on.

## 7b. Pair-level numbers in the Lookalike Failure Lab

The lab also reports numbers about *pairs of photos* rather than queries; they are defined separately and never mixed with the query-level FAR above.

| Number | Definition | Denominator |
|---|---|---|
| **Pair similarity** | cosine similarity of two photos' embeddings (not a probability). For a pair of *people* the listed value is that of their single most similar pair of photos | - |
| **Challenge false-accept rate** | different-person pairs with similarity ≥ the model's calibrated threshold | the hard different-person pairs chosen for the challenge set - **high by construction** |
| **All-pairs false-accept rate** | the same count over *every* different-person photo pair in the searched group | all such pairs (the realistic rate) |
| **Challenge recall (TAR)** | same-person pairs from different cameras with similarity ≥ the threshold | all those pairs (or a seeded sample of at most `max_genuine_pairs`) |
| **Clothing-colour similarity** | mean Bhattacharyya similarity of torso and leg colour histograms (label-free proxy) | - |

A pair is judged on the similarity threshold only; the margin rule needs a whole gallery and applies to the query-level numbers.

## 8. Latency and memory

Measured with `time.perf_counter()` after a warm-up, reported as mean / p50 / p95 / p99. Model load and warm-up are reported separately because they happen once. Peak memory is the process peak working set. Throughput = batch size ÷ batch time.
Nothing is quoted that was not measured on the machine named in the report ([PERFORMANCE.md](PERFORMANCE.md)).
