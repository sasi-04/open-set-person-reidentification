# The algorithms actually used

*Everything on this page describes code that exists and runs. Where an idea was considered but is not in the product it is listed in section 8.*

## 1. The pipeline

```
Input image
  → quality check (size, sharpness, aspect)              backend/app/cv/quality.py
  → person detection (Faster R-CNN MobileNetV3, COCO)    backend/app/cv/detection/detector.py
  → person crop (padded, never stretched)                backend/app/cv/geometry.py
  → body embedding: OSNet x1.0, 512-d, L2-normalised     backend/app/cv/embedding/extractor.py  (+ osnet.py)
  → face analysis: YuNet detector + SFace 128-d          backend/app/cv/face/engine.py
  → gallery comparison (cosine similarity, best photo per person)
                                                         backend/app/cv/retrieval/{gallery_index,ranking}.py
  → candidate selection (top-k people, face and body scores)
  → rejection checks (thresholds, review band, margin, quality flags)
                                                         backend/app/cv/open_set/{multicue,decision_engine}.py
  → final decision: MATCH | UNKNOWN | REVIEW  (+ a processing-error state)
```

The decision functions are **pure** (scores in, decision out; no database, no images), so they are unit-tested against hand-worked cases.
**A nearest neighbour is never accepted automatically**: every accepted match must pass an explicit rule, and an unknown person is rejected *even
though* some enrolled person is, by construction, always "closest".

## 2. Person detection

`torchvision` Faster R-CNN with a MobileNetV3-Large FPN backbone, COCO weights (SHA-pinned, BSD). Only the `person` class is kept, boxes are
clipped to the image, detector confidence is shown **separately** from identity confidence, and an image with nobody in it is a clear error, not a silent
nearest-neighbour. Input can also be declared "already a person crop" (portraits and benchmark crops) to skip detection.

## 3. Body embedding

OSNet x1.0 (Zhou et al., ICCV 2019), 2.2 M parameters, input 256×128 RGB, ImageNet normalisation, global pooling + one fully-connected layer = a **512-d**
vector, L2-normalised so that **cosine similarity = dot product**. Pretrained weights: Torchreid's official multi-source checkpoint (MSMT17 + DukeMTMC-reID + CUHK03);
**Market-1501 was not in its training data**. Its discriminative power was *measured* (Rank-1 81 % / mAP 69 % on a 100-person cross-camera check, then
Rank-1 83.6 % / mAP 77.8 % under the full protocol) - a 512-d vector is not automatically discriminative, and an earlier weight file that looked fine
(correct shape, finite, unit length) scored only 20 %: see [MODEL_VERIFICATION.md](MODEL_VERIFICATION.md).

## 4. Face embedding (used when a usable face is visible)

YuNet finds faces; a face is **usable** only if it is large enough, sharp enough and not turned away; SFace gives a 128-d vector. The face threshold
**0.465** was fixed by a rule decided in advance - strangers may reach it at most once in 100,000 comparisons - measured on 4.5 million LFW stranger pairs
([FACE_AND_BODY_MATCHING.md](FACE_AND_BODY_MATCHING.md)). Face accuracy was measured on LFW only (98.93 % ± 0.35 over 6,000 pairs); Market-1501 images are too small for faces, so the
benchmark evaluation of this project is **body-only**.

## 5. Gallery and similarity

* Each enrolled person has one or more photos; each photo is one embedding row. **Person score = the best photo's similarity** (default); the evaluation also tests the
  average over photos (a measured ablation, [EXPERIMENT_RESULTS.md](EXPERIMENT_RESULTS.md)).
* Similarity is cosine on unit vectors (a dot product). Distances are never mixed with similarities; all thresholds are on similarity ("higher is more alike").
* An empty gallery gives UNKNOWN, not an error; non-finite or wrongly sized embeddings are rejected before they reach the index.

## 6. The decision - exact conditions

**Situation A - a usable face is visible and at least one enrolled person has a face on file: the FACE decides.**

| Condition (best face similarity *f*, face threshold *T*, review band *b* = 0.10) | Decision |
|---|---|
| *f* ≥ *T* (and the optional margin rule passes) | **MATCH** that person |
| *T* − *b* ≤ *f* < *T* | **REVIEW** - too close to call automatically |
| *f* < *T* − *b* | **UNKNOWN** - unless an enrolled person *without* a face on file passes the body threshold, then **REVIEW** (nothing to verify the face against) |

Clothing similarity can **never** turn a failed face into a MATCH; that is the point of the design.

**Situation B - no usable face (back view, far away, blurred) or nobody enrolled has a face: the BODY decides** with the original rules, in this order:
quality flags (blurry, cut off ...) → **REVIEW**; best body similarity < body threshold → **UNKNOWN**; top-1/top-2 margin below the configured minimum → **REVIEW** (or UNKNOWN by policy);
otherwise the body evidence passes - and because clothing alone is weak evidence, a body-only pass is sent to **REVIEW** instead of MATCH (policy `body_only_action = review`; `accept` is selectable).

**REVIEW is therefore never a fallback for lack of calibration:** each REVIEW has a named cause (near the face threshold, ambiguous margin, poor quality, no face on file, body-only evidence) that is printed with the decision.

## 7. Calibration (how thresholds are chosen)

[METRICS.md](METRICS.md) and [EVALUATION_PROTOCOL.md](EVALUATION_PROTOCOL.md) give the full definitions. In short: people are split **identity-disjointly** into development / calibration / test;
for a target recall *R* (DIR@1, "accepted *and* correctly named"), every observed score is tried as a threshold on the **calibration** people, those reaching *R* are kept, the one with the **lowest FAR** wins,
and that frozen rule is then scored once on the **test** people. If no threshold reaches *R* the run says so (`target_achieved = false`), shows a clearly labelled best-effort fallback and refuses to call it calibrated.
**FAR is query-level** (a stranger is falsely accepted whenever *any* enrolled person is named for them) - this is an open-set false-positive-identification rate, not the pairwise verification FAR.
A raw similarity is **not** a probability; the optional "calibrated confidence" is a separately fitted logistic model with its own reported error (ECE, Brier).

## 8. Considered, not in the product

* Training a new backbone from scratch (impossible on this CPU in useful time; fine-tuning only the last stage is implemented and was run once, seed 0 - see EXPERIMENT_RESULTS.md section 3).
* Liveness / anti-spoofing, depth sensing, multi-camera tracking: absent. Video is judged frame by frame, never tracked.
* Re-ranking (k-reciprocal), pose or part-based models, clothing-change-specific training: not implemented.
