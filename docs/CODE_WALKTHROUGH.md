# Code walkthrough - a guided tour in plain language

This page is for a reviewer who wants to *understand the code*, not just run it. Allow about 30 minutes.
Every source file starts with a short "In plain words" paragraph saying what it is for and why it exists, so
you can also just open any file and read its header.

## The idea in 60 seconds

```
photo ──► find the people ──► cut each one out ──► find the FACE ──► make fingerprints: face (128 numbers) + body (512) ──► compare
                                                  (is it usable?)      (an "embedding")                                       with enrolled people
                                                                                                                                       │
                                                                                              ▼
                                    answer  ◄── decide: accept / unknown / review ◄── ranked list with similarity scores
```

Three kinds of network do the heavy lifting (a **detector** to find people, a **body embedder** and a **face recogniser** to fingerprint them). Everything else is
ordinary, readable code: checking the upload is safe, comparing fingerprints with a dot product, and - the part that makes
this project different - **deciding whether the best match is actually good enough**.

## Repository map

```
backend/app/
  main.py                 builds the web application: start-up, middleware, uniform error handling
  core/                   settings (config.py), error types, logging with request IDs, access roles, device choice
  api/routes/             THIN web routes: check the role, call a service, return the result. No logic lives here.
  schemas/                the exact shape of every request and response (Pydantic)
  services/               the workflows: reid_service (a query), gallery_service, evaluation_service (background jobs: evaluation,
                          calibration, look-alike experiments, video), video_service (sampling a clip), policy_service
                          (versioned thresholds), maintenance_service (retention), overview_service
  cv/                     computer vision, one folder per stage
    imaging.py              safe image decoding   |  geometry.py   boxes and cropping   |  quality.py   crop quality checks
    detection/detector.py   find people           |  embedding/    the body network and how it is loaded safely
    face/                   find + judge a face, face fingerprint, hair/skin/clothing colour cues (display only)
    retrieval/              similarity + ranking  |  open_set/     the decision engine, policy, calibrated confidence
  evaluation/             everything scientific: metrics, protocol, calibration, ablations, hard subset, reports,
                          lookalike.py (the Lookalike Failure Lab), sandbox.py (the threshold sandbox), lookalike_export.py
  training/               batch-hard triplet loss + the fine-tuning loop
  db/                     SQLite tables (SQLAlchemy)
backend/tests/            393 tests          frontend/src/       the web interface (130 tests)
scripts/                  command-line tools (setup, weights, datasets, evaluation, calibration, fine-tuning, benchmark)
docs/                     you are here
```

A rule that keeps the code easy to follow: **routes know about HTTP, services know about workflows, `cv/` and `evaluation/` know about
mathematics - and none of them know about each other's job.** The decision engine, for example, has no database, no web framework and no images;
it takes scores and a policy and returns a decision, which is why it can be tested exhaustively.

## Follow one request: "is this person enrolled?"

A person drops a photo on the **Match Studio** screen and presses *Run re-identification*.

### 1. The browser sends it
[`frontend/src/pages/ReidPage.tsx`](../frontend/src/pages/ReidPage.tsx) only *arranges* components; the behaviour is in the hook
[`useReid.ts`](../frontend/src/features/reid/useReid.ts), which holds the state ("which image, who was detected, which person is selected, what came back") and picks the
mode. It calls [`api.predict`](../frontend/src/services/api.ts), which goes through the single network function
[`request()`](../frontend/src/services/http.ts): it adds the access key in a header (only if keys are switched on and one was entered), applies a timeout, and turns any error into one readable `ApiError`.

### 2. The route is deliberately boring
[`backend/app/api/routes/reid.py`](../backend/app/api/routes/reid.py) → `predict()`. It checks the caller has at least the *viewer* role
(a dependency, see [`core/security.py`](../backend/app/core/security.py); with access keys off - the default - every caller passes), reads the upload with a size cap, and hands over to the service.

### 3. The upload is treated as hostile - [`cv/imaging.py`](../backend/app/cv/imaging.py) → `decode_image()`
It never trusts the file name or MIME type. It checks the *real bytes* with Pillow, rejects oversized files and absurd dimensions **before** decoding everything
(decompression-bomb protection), applies the camera's rotation, and converts to plain RGB pixels.

### 4. Finding the people - [`services/reid_service.py`](../backend/app/services/reid_service.py) → `_find_people()`
Three modes: *crop* (the image already is one person), *box* (the person you selected), *all* (run the detector).
[`cv/detection/detector.py`](../backend/app/cv/detection/detector.py) keeps only the COCO "person" class above a confidence floor. That confidence is the **detector's** certainty
that a box holds a person - it is stored and shown separately and is never mixed into the identity score.

### 5. Cutting out and checking each person - [`cv/geometry.py`](../backend/app/cv/geometry.py), [`cv/quality.py`](../backend/app/cv/quality.py)
`crop_person` adds a small margin and pads (never stretches) crops that are far from a standing person's proportions. `assess_crop` records simple, explainable facts:
tiny (*blocking*: not embedded at all), low resolution, blurry, cut off by the frame, unusual shape (*soft*: sent to human review).

### 6. One batch through the network - [`cv/embedding/extractor.py`](../backend/app/cv/embedding/extractor.py) → `embed()`
The network ([`osnet_ain.py`](../backend/app/cv/embedding/osnet_ain.py)) was loaded **once** at start-up, in eval mode, with gradients off. For each batch it resizes and
normalises the crops, runs the network, L2-normalises (so a dot product *is* the cosine similarity) and then **refuses to return anything not finite or not unit length**.
The weights file was checksum-verified and loaded with `weights_only=True` ([`weights.py`](../backend/app/cv/embedding/weights.py)).

### 7. Ranking the enrolled people - [`cv/retrieval/`](../backend/app/cv/retrieval/ranking.py)
The gallery lives in RAM as one matrix ([`gallery_index.py`](../backend/app/cv/retrieval/gallery_index.py)); a query is one matrix multiplication. Each person has several reference
images, and their score is the best-matching image (`best_score_per_identity`). `rank_identities` uses a *stable* sort so ties never reorder between runs. This **same file** is
used by the evaluation code, so what we measure is what we serve.

### 7b. The face - [`cv/face/engine.py`](../backend/app/cv/face/engine.py), [`services/face_service.py`](../backend/app/services/face_service.py)
If the active policy uses faces, each person's region of the photo goes through a small face detector (YuNet). A face only counts if it is **usable**: at least 40 px wide, a confident detection, not turned away, sharp enough - otherwise the reason is reported (`face_small`, `face_blurry`, ...) and the body is used instead. A usable face becomes 128 numbers (SFace). Enrolled reference photos get the same treatment once, at enrolment, and their face fingerprints sit in their own search index next to the body one. [`services/matching.py`](../backend/app/services/matching.py) then asks the body index and the face index about **every** enrolled person and hands both answers to the decision engine.

### 8. The decision - [`cv/open_set/decision_engine.py`](../backend/app/cv/open_set/decision_engine.py) → `decide()` and [`multicue.py`](../backend/app/cv/open_set/multicue.py) → `decide_multicue()`
This is the heart of the project, and it is short enough to read in two minutes. The first rule that applies wins:

| # | Rule | Outcome |
|---|---|---|
| 1 | nobody is enrolled | `UNKNOWN` (reason: empty gallery) |
| 2 | the crop has quality flags and the policy says so | `REVIEW_REQUIRED` |
| 3 | best similarity **below the threshold** | `UNKNOWN` - *the nearest neighbour is not accepted* |
| 4 | a margin rule is set and *(best − second best)* is below it | `REVIEW_REQUIRED` (or `UNKNOWN`, by policy) |
| 5 | otherwise | `ACCEPTED` |

**With face matching on** the rules in `multicue.py` apply instead: a usable face that reaches the face threshold → MATCH; a face just below it → REVIEW; a clear mismatch → UNKNOWN *even if the clothes match perfectly*; no usable face → the body rules above, except that a strong body match is sent to REVIEW rather than accepted (clothing alone is weak evidence). The full rule and where each number comes from: [FACE_AND_BODY_MATCHING.md](FACE_AND_BODY_MATCHING.md).

The returned `Decision` carries the actual scores, the threshold, the margin, the policy version and a sentence assembled **from those numbers** - so the explanation can never disagree
with the data. Four different numbers are kept apart on purpose: similarity (retrieval score), margin (ambiguity signal), calibrated confidence (a fitted probability, only when one exists) and the detector score.

### 9. Where the thresholds come from - [`services/policy_service.py`](../backend/app/services/policy_service.py)
The threshold is a database row, one of a numbered series. Changing it never edits a row: it adds version *n+1* and flips the "active" flag. Every request reads the active row, so a change takes effect
on the very next request - it is not cached in the browser or the server - and every decision records the version it was made under. Status is honest: `unvalidated` → `experimental` → `calibrated`.

### 10. Saving and answering - `reid_service.predict()` (end)
It writes a history row (scores, no raw images, no embeddings) and optionally keeps the crop for the retention window, then returns timings measured with `time.perf_counter()`
around each stage, so the interface shows real numbers.

## How a threshold is chosen (the evaluation, in one page)

[`evaluation/runner.py`](../backend/app/evaluation/runner.py) → `run_evaluation()` is a readable recipe:

1. **Split the people** ([`protocol.py`](../backend/app/evaluation/protocol.py)) into *development / calibration / test* groups that never overlap; inside calibration and test, half are *enrolled* (a few photos become the gallery, the rest are
   "known" queries) and half are *strangers* (all their photos are "unknown" queries). One seed controls everything, and `assert_disjoint()` re-checks the guarantees.
2. **Embed each image once** and cache it ([`embedding_store.py`](../backend/app/evaluation/embedding_store.py)).
3. **Score every query** ([`scoring.py`](../backend/app/evaluation/scoring.py)) with the *same* ranking functions as the live system, hiding same-camera photos of the true person (Market-1501 convention).
4. **For each ablation variant** ([`ablation.py`](../backend/app/evaluation/ablation.py)): choose the rule on the *calibration* people ([`calibration.py`](../backend/app/evaluation/calibration.py)), **freeze it**, and
   apply it to the *test* people ([`metrics.py`](../backend/app/evaluation/metrics.py): FAR, TAR, DIR@k, ROC, OSCR, Rank-k, mAP, bootstrap intervals that resample *people*, not queries).
5. **Pick the final configuration using calibration numbers only**, and write JSON / Markdown / HTML reports ([`report.py`](../backend/app/evaluation/report.py)).

If the requested target (say "90 % recall") cannot be met, `select_operating_point` returns `target_achieved = False`, and every later step carries that fact: the policy cannot be applied as *calibrated*.

## Two newer paths, in one paragraph each

**A video** ([`services/video_service.py`](../backend/app/services/video_service.py)): the upload is checked by its real bytes and probed with OpenCV, then a background job reads the file, keeps one frame every N seconds, and for each kept frame runs the *same* detect → crop → embed → rank → `decide()` steps as a single photo
(there is no second matcher). Frames are independent: no identity is carried from one to the next, and the result says so. The original file is deleted when the job ends.

**A look-alike experiment** ([`evaluation/lookalike.py`](../backend/app/evaluation/lookalike.py)): it builds the usual identity-disjoint protocol, chooses each model's threshold on the *calibration* people, then scans every pair of photos of different people (in blocks, so memory stays small)
to rank the most alike pairs of people, turns the top ones plus same-person pairs from different cameras into a challenge set, measures each model on it, and lists the real mistakes with measured facts and hypotheses kept in separate fields.
The **threshold sandbox** ([`evaluation/sandbox.py`](../backend/app/evaluation/sandbox.py)) re-counts a run's stored per-query table under any trial rule, using the same decision rule as the live engine and never writing to the policy. Full explanation: [LOOKALIKE_LAB.md](LOOKALIKE_LAB.md).

## Reading the frontend

`src/pages/*` = one file per screen (they arrange): Command Center, Gallery, Match Studio, Video Explorer, Lookalike Failure Lab, Evaluation Lab, Settings. `src/features/*` = the pieces of each screen (reid, gallery, evaluation, lookalike, video, model, settings, history). `src/components/ui/*` = the small design-system kit (button, dialog, tabs, form fields,
toast...). `src/services/*` = the typed API layer. `src/lib/*` = formatting and presentation helpers (one place decides that a missing number shows as "—", never "0"). Colours, radii and fonts exist only as
CSS variables in [`styles/index.css`](../frontend/src/styles/index.css); components never contain raw colour values.

## Conventions you will see

- **Plain-words headers** on every file; function docstrings explain *why*, not just *what*.
- **Errors are values, not surprises:** `AppError` subclasses ([`core/errors.py`](../backend/app/core/errors.py)) carry a stable code and a human message; one handler in `main.py` renders them all identically.
- **Nothing silently swallowed:** the few broad `except Exception` blocks log or re-raise with context (for example one bad file in a batch is reported without losing the others).
- **Parameterised data access only** (SQLAlchemy ORM); no string-built SQL anywhere.
- **Tests read like specifications** (`test_top_candidate_is_not_automatically_accepted`, `test_calibration_run_never_embeds_a_test_image`).

## Where to extend it

| I want to… | Touch |
|---|---|
| use a different backbone | add a spec in [`embedding/registry.py`](../backend/app/cv/embedding/registry.py) (and a class satisfying [`base.py`](../backend/app/cv/embedding/base.py) if it is not an OSNet); nothing else changes |
| add an ablation variant | add a `VariantSpec` in [`ablation.py`](../backend/app/evaluation/ablation.py) |
| add a metric | a pure function in [`metrics.py`](../backend/app/evaluation/metrics.py) + a hand-computed test in `tests/test_metrics.py` |
| change the decision rules | [`decision_engine.py`](../backend/app/cv/open_set/decision_engine.py) + [`policy.py`](../backend/app/cv/open_set/policy.py), then extend `tests/test_decision_engine.py` |
| add a screen | a page in `src/pages`, a route in `App.tsx`, a nav item in `components/layout/navigation.tsx` |
| add a failure category to the Lookalike Failure Lab | a hypothesis rule in `explain_failure()` ([`lookalike.py`](../backend/app/evaluation/lookalike.py)) + a test in `tests/test_lookalike.py`; keep it labelled as a hypothesis |
| allow another video container | `sniff_container()` in [`video_service.py`](../backend/app/services/video_service.py) and the allow-list; add a test with a real file |

## Questions a reviewer is likely to ask

| Question | Answer / where |
|---|---|
| "How do you stop a look-alike stranger being accepted?" | You cannot *guarantee* it - you can measure and trade it off. The threshold/margin are chosen on held-out people for a stated FAR/recall target, the report shows the FAR with a 95 % bound, and the look-alike subset shows the FAR specifically for look-alikes. |
| "Is the test set ever used to tune anything?" | No. `tests/test_evaluation_pipeline.py::test_calibration_run_never_embeds_a_test_image` proves the calibration path never even reads a test image; the variant is selected on calibration numbers. |
| "What if a fine-tuned model saw the test people?" | `_finetuned_problem()` in `runner.py` refuses it, naming the overlapping people (tested). |
| "Are any results simulated?" | No. Embeddings come from the real network; tests use fakes only to test plumbing and say so. |
| "What happens when something is missing?" | The interface says "Not evaluated" / "No dataset installed" / "Model not loaded" - see `tests/test_api_basics.py` and `src/pages/pages.test.tsx`. |
