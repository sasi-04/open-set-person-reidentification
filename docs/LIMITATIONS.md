# Limitations - what is not proven, not done, or not possible here

*Written to be read before anything else is believed. Every item is something this repository does **not** claim.*

## What the measurements do not show

1. **Body-only open-set performance on Market-1501 is modest, and that is the honest result.** At a required recall (DIR@1) of 70 % the test false-accept rate was **28.6 % ± 8.0**; at 50 % recall it was 6.4 %; a 90 % recall target is **unreachable** with this model (its best Rank-1 is 83.6 %). Body appearance alone does not separate enrolled people from strangers well enough for a low FAR at high recall. See [EXPERIMENT_RESULTS.md](EXPERIMENT_RESULTS.md).
2. **Face + body was not benchmarked.** Market-1501 crops are about 64×128 pixels - too small for a usable face - so the benchmark exercises the body path only. The face path (YuNet + SFace) was measured on LFW (98.93 % ± 0.35, 6,000 pairs) and on 13 public-domain portraits ([OPEN_SET_EXAMPLE.md](OPEN_SET_EXAMPLE.md)); both are easy data. No face + body result exists for pedestrian cameras.
3. **It is not the official Market-1501 protocol.** The dataset copy has no `query/` folder; the project's own identity-disjoint protocol (60 enrolled + 60 stranger people per split, 3 gallery photos each, ≤ 8 photos per person, 3 seeds) was used, on a CPU-sized subset (5,067 images embedded). Numbers are not comparable with published Market-1501 results.
4. **The "same-clothing" subset is a proxy** (colour histograms), not ground truth: Market-1501 has no clothing labels. No dataset with same-clothing labels was available offline.
5. **No cross-dataset or own-camera evaluation.** Thresholds are calibrated on Market-1501 calibration people; they are *not* validated for any other camera.
6. **Fairness is not measured** (age, skin tone, gender); face systems can perform differently across groups.
7. **Example demo = 13 photos.** It illustrates the mechanism; it is not an error rate.

## What was found wrong, and what is still open

| Finding | Status |
|---|---|
| The OSNet-AIN weight file shipped in version 1 reached only **Rank-1 20 %** (a verified OSNet checkpoint: 81 %) | **Fixed** - replaced and hash-pinned; the cause of the weak file is **not established** ([MODEL_VERIFICATION.md](MODEL_VERIFICATION.md)) |
| Earlier documents called the embedding "validated" on the strength of shape / norm / determinism tests | Corrected: those tests never measured discriminative power |
| Thresholds set for the old file (body 0.70) | Re-measured on Market-1501 calibration people; the live default remains an **unvalidated starting value** until applied through a calibration run |
| The smaller `osnet_ain_x*` files | **Unverified**, flagged in the registry; not used |

## Not implemented

* **Liveness / anti-spoofing** (a photograph can fool the face matcher); **depth sensing**.
* **Tracking across frames**: video is judged frame by frame.
* **Real-time video rate**: measured 0.18 s per crop on 2 CPU cores (about 6 crops/s in batches); interactive, not video-rate.
* **GPU path** is coded but untested (no GPU available).
* **Training a backbone from scratch**; **re-ranking**; **clothing-change-specific learning**.

## Data and legal

* Face fingerprints are **biometric data**: use only consenting people; a real deployment needs a legal basis and an impact assessment (GDPR, DPDP Act, BIPA).
* Market-1501 is **non-commercial research** data, fetched from a third-party mirror with no declared licence and kept out of git. The embedding checkpoint was trained on MSMT17 + DukeMTMC-reID + CUHK03 (DukeMTMC-reID was withdrawn by its authors in 2019): research use only.
