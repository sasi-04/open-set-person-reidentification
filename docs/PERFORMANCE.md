# Performance - measured, not assumed

Every figure here was produced by [`scripts/benchmark_latency.py`](../scripts/benchmark_latency.py) or by timing real requests on the machine below. **No latency or throughput target is claimed.**
Re-run the script on your hardware; numbers from other machines will differ.

**Measurement machine:** Intel Core (family 6 model 142, laptop class), **2 physical cores / 4 threads**, 7.9 GB RAM, Windows 10 (19045), **no GPU**; Python 3.14.4, PyTorch 2.14.1 (CPU), 2 torch threads. A browser and the backend
were running at the same time (a realistic, slightly noisy desktop).

## The headline

One person in a ~1 MP portrait photo, through the real HTTP API. Two measured conditions on the same laptop - the difference is entirely how busy the CPU was:

| Stage | **Idle machine** (nothing else running) | **Busy machine** (browser + test suites running) |
|---|---|---|
| Detection (Faster R-CNN MobileNetV3, short side 480 px) | 0.39 - 0.48 s | 0.9 - 1.05 s |
| Cropping and quality checks | 2.5 ms | 6 - 13 ms |
| Embedding (OSNet-AIN x1.0, one crop) | 0.10 - 0.11 s | 0.26 - 0.29 s |
| Gallery search + decision | 0.3 - 2.3 ms | 0.3 - 3.8 ms |
| **Total per request** | **≈ 0.50 - 0.57 s** | **≈ 1.2 s** |
| Photo with 4 people | ≈ 1.3 s | ≈ 2.4 s |

So **expect roughly 0.5 s - 1.2 s per query on a 2-core laptop CPU**, depending on load. That is **interactive, not real-time video**. For an image that is *already a tight person crop* (no detector) the request takes roughly 0.1 - 0.3 s. The bottleneck is the detector, not the ReID backbone.
(The idle numbers come from the final verification run; the busy numbers from the first real-model run. Scores were bit-for-bit identical in both - only the timing changed.)

## The face stage (added with face matching)

Measured on the same machine, CPU only, with a browser and the server running. Single runs from the reference demo (`demo/expected_output/scenario*.decision.json`) and the LFW evaluation (`docs/results/face_lfw.json`):

| What | Measured |
|---|---|
| Face detection + fingerprint on a small head-and-shoulders picture (LFW, 250 px) | **about 57 ms** per picture (mean over 7,701 pictures) |
| The same on a 960 x 1,200 portrait inside a Match Studio request (`face_ms` in the decision record) | **84 - 260 ms** (the detector works on the picture at up to 1,280 px; larger pictures cost more) |
| Face stage when no face is found (back view, blurred head) | **8 - 28 ms** (the detector finds nothing quickly) |
| Seven people in one street photo | 33 ms for all seven faces (the faces are small and mostly unusable); the request took about 1.5 s in total, dominated by the person detector (0.8 s) and the body embedding (0.6 s) |
| Whole request for a ready-made crop with a face | **0.27 - 0.40 s** (body embedding about 0.1 - 0.15 s) |

So face matching adds roughly **0.06 - 0.25 s per person** on this CPU; the person detector is still the slowest part of a full-photo request. Searching the face index (128 numbers per face) is a matrix product like the body search and takes well under a millisecond for a small gallery. These are single measurements on a busy laptop, not a benchmark.

## Video and experiments (single real runs - illustrative, not a benchmark)

Measured once each on the same laptop while a browser and an editor were open, with the real detector and the real model. They show the order of magnitude and that nothing is faked; they are **not** a statistical benchmark.

| What | Measured |
|---|---|
| **Video Explorer**, a 3-second 480×640 clip (frames cut from real street photos), sampled every second → 3 frames | per-frame detect + embed + match: **0.74 s** (1 person), **1.68 s** (5 people), **0.97 s** (1 person); whole job incl. decoding and thumbnails **4.1 s** wall. The same clip re-run later on a *busier* machine (right after a build and the test suites) took **1.5 s / 3.4 s / 2.7 s** per frame - the same spread between an idle and a busy CPU as for photos. Each frame is processed on its own: the detector dominates, exactly as for photos. The job result stores decode / detect / embed / match times per frame, so you can read them for any clip. |
| **Lookalike Failure Lab**, smoke-test set (800 synthetic images; capped to 30 people per split, 8 photos each) | **73 s** end to end on the first run, of which ~58 s embedding new images at ≈ 0.2 s each; embeddings are cached on disk, so a rerun re-does only the (fast) matrix maths. Pair mining itself is block-wise matrix products: scanning every pair of photos of different people took **1.6 s for 7,200 photos of 600 people (25.9 million pairs, 512-d embeddings, random vectors - timing only)** and picking the top 40 pairs 36 ms, so the scan is not the bottleneck at Market-1501 scale; embedding the images is. |

**This is not real time.** At roughly one second per processed frame on this CPU, Video Explorer is meant for sampling a clip (for example every second), not for processing 25-30 frames per second. A GPU would change this materially but has not been tested here.

## Methodology note (and a correction we made)

CPU timings on a laptop drift (thermal throttling, background load, turbo clocks). Measuring setting A and then setting B therefore says more about *when* each ran than about A versus B.
All comparisons below use **interleaved** measurements (A, B, A, B … alternating who goes first) and report **paired** statistics. Our first attempt used sequential timing and produced a misleading "folded batch-norm is 8-18 % faster" result
and, in another run, "folded is slower"; the interleaved test is the one to trust.

## Embedding backbone - OSNet-AIN x1.0, 256×128 input (official weights)

| Setting | Load (one-off) | Warm-up (one-off) | 1 crop p50 | p95 | p99 | Batch of 16 |
|---|---|---|---|---|---|---|
| plain network | 0.55 s | 0.13 s | **126 ms** | 181 ms | 276 ms | 152 ms/crop (6.6 crops/s) |
| batch-norm folded into convolutions | 0.34 s | 0.13 s | 117 ms | 167 ms | 208 ms | 166 ms/crop (6.0 crops/s) |

*Paired comparison, 60 interleaved runs: the folded model was faster in 35 of 60 pairs; median time ratio folded/plain = 0.96.* So the effect is about **4 % for a single crop, and none (slightly worse) in batches** - within the noise of this machine.
Profiling had shown convolutions at ~62 % of the time and batch-norm at ~13 %, which suggested a larger gain; the measurement did not confirm it. We therefore **kept the optimisation but turned it off by default**
(`REID_FOLD_BATCH_NORM=false`): it computes the same function (verified to 6e-6 on the raw output, cosine ≥ 0.99999 - `test_folded_real_model_matches_the_unfolded_one`) and may help more on other CPUs.

**Model loading and warm-up are one-off costs** (≈ 0.5 s and 0.13 s) paid at start-up; they are never part of a request's latency.

### Narrower widths (timing only - random weights, accuracy NOT measured)

| Width | Parameters | 1 crop p50 | p95 |
|---|---|---|---|
| x1.0 (default) | 2.17 M | 119 ms | 138 ms |
| x0.75 | 1.29 M | 123 ms | 151 ms |
| x0.5 | 0.63 M | 77 ms | 104 ms |
| x0.25 | 0.20 M | 54 ms | 77 ms |

(x1.0 and x0.75 are indistinguishable here - noise.) Smaller widths are about 1.5-2× faster but their *accuracy has not been evaluated in this project*; switch with `REID_EMBEDDING_MODEL` and re-calibrate.

## Person detector (1280×720 test image, interleaved sizes)

| Input short side | p50 | p95 | Trade-off |
|---|---|---|---|
| 320 px | 219 ms | 333 ms | fastest; may miss small or distant people |
| **480 px (default)** | 390 ms | 596 ms | balanced |
| 640 px | 718 ms | 1046 ms | best for small people |

The benchmark uses a noise image with no people; real photos are slower (the box-refinement stage has real work to do), which is why the end-to-end figure above (0.9-1.05 s for a portrait photo) is higher. Change with `REID_DETECTOR_MIN_SIZE`.

## Gallery search (one query, 5 reference images per person)

| Enrolled people | Reference images | p50 | p95 |
|---|---|---|---|
| 100 | 500 | 0.30 ms | 0.70 ms |
| 1 000 | 5 000 | 1.33 ms | 2.35 ms |
| 10 000 | 50 000 | 11.4 ms | 13.7 ms |

Search is one matrix multiplication over an in-memory array and scales linearly; even 10 000 people cost far less than a single embedding. The index is rebuilt atomically on every gallery change and carries a version number (cache invalidation).

## Memory

The server process with both models loaded and a small gallery uses roughly **0.7-0.9 GB** (peak working set measured 749 MB during an evaluation run and 919 MB in the benchmark with three detectors loaded at once).

## What was done to be efficient

- Models load **once** per process, in eval mode, with gradients disabled (`torch.inference_mode`); one forward pass per batch of crops, and one batch for all people in a photo.
- The gallery is a single matrix; evaluation reuses a disk cache of embeddings keyed by dataset, file, size and model fingerprint.
- Evaluation runs in a background thread with real progress; it cannot block the web server.
- `start.ps1` runs uvicorn with `--limit-concurrency 32` so a busy small CPU answers 503 rather than queueing without bound.

## Improving speed (ideas, none claimed)

1. A GPU (the code selects CUDA automatically; untested here). 2. A smaller detector input or `ssdlite320_mobilenet_v3_large`. 3. Detect once per video track and re-use the box. 4. ONNX Runtime / OpenVINO for the CPU. 5. A narrower OSNet after measuring its accuracy.
