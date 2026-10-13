# The Lookalike Failure Lab

> **Scope note (face matching).** The Evaluation Lab, the calibration workflow and the Lookalike Failure Lab measure the **body** model: their datasets (Market-1501 and the smoke-test set) are full-body crops without readable faces, so face matching cannot take part in them and they are always run under the body-only rules. The face stage has its own measurements - the standard LFW benchmark and an end-to-end face-versus-clothing check - described in [FACE_AND_BODY_MATCHING.md](FACE_AND_BODY_MATCHING.md) and reproducible with `scripts/evaluate_face_lfw.py` and `scripts/verify_face_vs_body.py`.

*A diagnostic tool, not a new learning algorithm. It proves nothing by itself; it makes a specific kind of failure visible, measurable and exportable.*

## 1. The problem it looks at

A re-identification system compares a query photo with enrolled people and reports the closest one. The costly mistake is a **false accept**: a stranger who *looks like* an enrolled person
(same uniform, similar build) scores high enough to be accepted. Such strangers are rare in a random sample but common in the real situations the PS-1 brief describes ("low inter-class variance"),
so an ordinary average over all strangers hides them. The lab goes looking for exactly these people.

## 2. What it does, in four steps

| Step | Question | What is produced |
|---|---|---|
| **1 Mine** | Which pairs of *different* people does the model find most alike? | a ranked list of identity pairs, each with the most similar pair of photos and the matcher's decision on it |
| **2 Challenge** | How does the matcher do on exactly those pairs? | a fixed, reproducible *challenge set* (hard different-person pairs + same-person pairs from different cameras) and each model's rates on it |
| **3 Compare** | Does an improved (fine-tuned) model do better on the **same** pairs? | a side-by-side table, or an explicit "no comparison, because..." |
| **4 Inspect** | What do the actual mistakes look like, and what might explain them? | mistake cards: both photos, the measured numbers, and hypotheses clearly marked "not proven" |

## 3. Plain-language definitions

* **Different-identity (impostor) comparison** - two photos of two different people. If the matcher would accept such a pair as "the same person", that is a **false accept**.
* **Genuine comparison** - two photos of the *same* person, from different cameras (like recognising someone in a new place). If the matcher would reject it, that is a **false reject**.
* **Pair similarity** - the cosine similarity of the two photos' embeddings (a score from -1 to 1; **not a probability**). A pair is "accepted" when its similarity reaches the model's calibrated threshold.
  For a pair of people, the listed similarity is that of their single most similar pair of photos - the strongest evidence that they could be confused.
* **Challenge false-accept rate** - the share of the *hard* different-person pairs the matcher would accept. **High by construction**, because those pairs were chosen for being hard.
* **All-pairs false-accept rate** - the same question asked of *every* different-person pair in the searched group: the realistic rate. The lab always prints it next to the challenge rate.
* **Clothing-colour similarity** - a label-free proxy (torso and leg colour histograms, Bhattacharyya similarity), computed independently of the model. A pair is flagged "similar clothing colours" when it falls in the top quarter of a seeded sample of all different-person pairs.
  The datasets carry **no clothing labels**, so this is a proxy, and the lab never assumes that look-alike *embeddings* mean look-alike *clothing*; both numbers are shown and kept apart.

## 4. The honesty rules built into the code

These are enforced by [`evaluation/lookalike.py`](../backend/app/evaluation/lookalike.py) and checked by [`tests/test_lookalike.py`](../backend/tests/test_lookalike.py):

1. **The threshold is chosen on calibration people only** - for a stated target (for example "keep 90 % of enrolled people accepted and correct"). Searching the test people for look-alikes happens *afterwards* and cannot change it
   (`test_the_threshold_is_chosen_on_calibration_people_so_the_mined_split_cannot_change_it`).
2. **Pair mining is exact.** The block-wise scan is compared with a brute-force double loop (`test_pair_scan_equals_a_brute_force_double_loop`).
3. **A second model is compared only if it is clean.** A checkpoint trained on any person in the calibration or test group is refused with the reason; on the *development* group (its own training people) no comparison is offered at all.
   With no checkpoint the result says "unavailable" and why - there is no placeholder number. Both models are scored on identical pairs, each at its own calibrated threshold.
4. **Observed and hypothesised are separate fields.** A mistake record has `observed` (measured numbers) and `possible_causes` (each tagged `hypothesis - not proven`, each tied to a recorded number; "no simple cause is visible" is a valid answer).
5. **Unreachable targets are reported, not hidden.** If the calibration people cannot meet the target, the run says so, and the threshold is labelled a fallback.
6. **Smoke-test datasets are never presented as benchmarks** (a warning on the result, in the exports, and on screen).
7. **Reproducible.** The same dataset files, seed and settings give the same splits, pairs and numbers (`test_same_seed_gives_the_same_experiment`). The experiment ID, model fingerprints, request and software versions are in every export.

## 5. What you can read on the screen

| Tab | Shows |
|---|---|
| Look-alike pairs | the most alike pairs of different people as photo pairs with the matcher's decision, the similarity against the threshold, and the clothing-colour similarity; filters for false accepts and similar-clothing pairs |
| Challenge set | counts, both stranger rates side by side, each model's recall on same-person pairs, the curve of same-person pairs accepted against hard strangers accepted, a threshold-effects slider, the least-alike same-person pairs, and how the set was built |
| Mistakes | counts of all mistakes by category and a list of the most instructive ones (categories: *stranger accepted*, *enrolled person given the wrong name*, *enrolled person not accepted*) |
| Baseline vs improved | the two models on the same examples - or the reason there is no comparison |
| Threshold sandbox | any threshold / margin rule recounted on the run's fixed query results (see [EVALUATION.md](EVALUATION.md#9-threshold-sandbox)); never changes the policy |
| Method & limits | limitations and the reproducibility record |

## 6. Exports

`GET /api/lookalike/runs/{id}/export?format=...` (or the buttons on the screen): `json` (the complete record, including the sandbox table), `pairs_csv`, `failures_csv` (observed values, then the unproven hypotheses),
`summary_csv` (one row per metric and model), `md` (a report that reads top to bottom). Text cells that start with `= + - @` are neutralised so a spreadsheet cannot treat a dataset label as a formula.
Photos are served by `GET /api/lookalike/runs/{id}/image?ref=...` as re-encoded JPEG, and only for paths the experiment itself recorded (traversal attempts return 404).

## 7. Running it

* **With Market-1501** (research use; see the README, "Dataset acquisition"): *Lookalike Failure Lab → Run look-alike experiment*. Embedding is cached, so a rerun is fast.
* **To check the lab itself:** `python scripts\make_smoke_dataset.py` creates a synthetic set. On it the real model cannot separate the cartoon people, so the lab reports "target not reached" and an all-pairs false-accept rate of about 38 % -
  which is the *correct* behaviour for unseparable data and says nothing about real performance.
* **With an improved model:** train one with `scripts\finetune_triplet.py`, then pick it in the form. Remember the checkpoint is only valid for the held-out people it was trained against.

## 8. What it does not claim

* It does not claim any model is accurate: with no benchmark run there are no accuracy figures in this repository.
* It does not claim that metric learning, hard-negative mining or margin losses help: the training code exists and is tested, but **no checkpoint has been trained or evaluated**, so the comparison tab is empty by design.
* The challenge set is selected with the baseline model, so it is a stress test, not a random sample.
* The "possible causes" are ideas to check. None has been tested by changing the input, and none should be read as the proven reason.
