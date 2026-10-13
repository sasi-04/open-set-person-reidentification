"""
Measure how fast each stage of the pipeline really is on THIS machine.

In plain words: we never quote a speed we have not measured. This script times, after a warm-up
(model loading and warm-up are reported separately because they happen once):

  * the embedding backbone, one crop at a time (p50/p95/p99) and in batches;
  * the effect of the batch-norm folding optimisation;
  * the person detector at several input sizes;
  * gallery search for galleries of different sizes;
  * peak memory of this process.

Run it with the backend venv active:   python scripts/benchmark_latency.py
The result is printed and saved to backend/data/reports/benchmark_latency.md. Numbers from other
computers will differ - quote them only together with the machine description printed at the top.
"""

from __future__ import annotations

import argparse
import platform
import sys
import time
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.device import resolve_device  # noqa: E402
from app.cv.detection.detector import PersonDetector  # noqa: E402
from app.cv.embedding.extractor import OSNetExtractor  # noqa: E402
from app.cv.embedding.osnet_ain import OSNetAIN  # noqa: E402
from app.cv.embedding.registry import EMBEDDING_MODELS, get_spec  # noqa: E402
from app.cv.retrieval.gallery_index import GalleryIndex, IndexEntry  # noqa: E402
from app.evaluation.performance import measure_embedding_latency, peak_memory_mb, percentiles  # noqa: E402


def crops(n: int, seed: int = 0) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    return [rng.integers(0, 255, (200, 90, 3), dtype=np.uint8) for _ in range(n)]


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=40, help="single-crop measurements per setting")
    parser.add_argument("--skip-detector", action="store_true")
    args = parser.parse_args()

    device = resolve_device(settings.device)
    lines: list[str] = []

    def say(text: str = "") -> None:
        print(text, flush=True)
        lines.append(text)

    import psutil

    say("# Latency and memory benchmark")
    say()
    say(f"- Machine: {platform.processor() or platform.machine()}, {psutil.cpu_count(logical=False)} cores / {psutil.cpu_count()} threads, "
        f"{psutil.virtual_memory().total / 2**30:.1f} GB RAM, {platform.platform()}")
    say(f"- Software: Python {platform.python_version()}, torch {torch.__version__}, device **{device}**, torch threads {torch.get_num_threads()}")
    say(f"- Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    say()

    # ------------------------------------------------------------------- embedding backbone
    say("## Embedding backbone (official OSNet-AIN x1.0 weights, 256x128 input)")
    say()
    say("| Setting | Load (one-off) | Warm-up (one-off) | 1 crop p50 | p95 | p99 | Batch of 16 |")
    say("|---|---|---|---|---|---|---|")
    spec = get_spec(settings.embedding_model)
    sample = crops(8)
    extractors = {fold: OSNetExtractor.load(spec, settings.weights_dir, device, fold_bn=fold) for fold in (False, True)}

    # Interleaved measurement: A, B, A, B ... (alternating who goes first) so drift, thermal throttling and
    # background load hit both settings equally. Timing one setting after the other on a laptop is NOT a fair test.
    samples: dict[bool, list[float]] = {False: [], True: []}
    for extractor in extractors.values():
        for crop in sample[:3]:
            extractor.embed([crop])  # warm-up, excluded
    for i in range(args.runs):
        order = (False, True) if i % 2 == 0 else (True, False)
        for fold in order:
            started = time.perf_counter()
            extractors[fold].embed([sample[i % len(sample)]])
            samples[fold].append((time.perf_counter() - started) * 1000)
    batch_ms: dict[bool, list[float]] = {False: [], True: []}
    batch = sample * 2  # 16 crops
    for i in range(6):
        for fold in ((False, True) if i % 2 == 0 else (True, False)):
            started = time.perf_counter()
            extractors[fold].embed(batch)
            batch_ms[fold].append((time.perf_counter() - started) * 1000 / len(batch))
    for fold, extractor in extractors.items():
        stats = percentiles(samples[fold])
        per_crop = float(np.median(batch_ms[fold]))
        say(f"| {spec.display_name}, batch-norm {'folded' if fold else 'not folded'} | {extractor.load_seconds:.2f} s | {extractor.warmup_seconds:.2f} s | "
            f"{stats['p50']:.0f} ms | {stats['p95']:.0f} ms | {stats['p99']:.0f} ms | {per_crop:.0f} ms/crop ({1000 / per_crop:.1f} crops/s) |")
    paired = np.array(samples[True]) / np.array(samples[False])  # ratio < 1 means the folded model was faster in that pair
    say()
    say(f"Paired comparison over {len(paired)} interleaved runs: folded was faster in {int((paired < 1).sum())} of {len(paired)} pairs; "
        f"median time ratio folded/not-folded = **{np.median(paired):.2f}** (below 1.00 = faster).")
    say()

    say("### Smaller widths (timing only - random weights, NOT accuracy)")
    say()
    say("| Width | Parameters | 1 crop p50 | p95 |")
    say("|---|---|---|---|")
    for name, model_spec in EMBEDDING_MODELS.items():
        model = OSNetAIN(model_spec.channels, model_spec.feature_dim).eval()
        x = torch.randn(1, 3, 256, 128)
        timings = []
        with torch.inference_mode():
            for _ in range(3):
                model(x)
            for _ in range(args.runs):
                started = time.perf_counter()
                model(x)
                timings.append((time.perf_counter() - started) * 1000)
        stats = percentiles(timings)
        say(f"| {model_spec.display_name} | {sum(p.numel() for p in model.parameters()) / 1e6:.2f} M | {stats['p50']:.0f} ms | {stats['p95']:.0f} ms |")
    say()

    # --------------------------------------------------------------------------- detector
    if not args.skip_detector:
        say("## Person detector (torchvision Faster R-CNN MobileNetV3, COCO) on a 1280x720 image")
        say()
        say("| Input short side | Load (one-off) | p50 | p95 |")
        say("|---|---|---|---|")
        rng = np.random.default_rng(1)
        image = rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8)
        detectors = {}
        try:
            for min_size in (320, 480, 640):
                detectors[min_size] = PersonDetector.load(settings.detector_model, settings.weights_dir, device, min_size=min_size,
                                                          score_threshold=settings.detector_score_threshold, max_people=settings.detector_max_people)
                detectors[min_size].detect(image)  # warm-up
        except Exception as exc:  # weights may not be downloaded
            say(f"| unavailable: {exc} | | | |")
        timings: dict[int, list[float]] = {size: [] for size in detectors}
        for round_number in range(max(8, args.runs // 4)):  # interleave the sizes for the same fairness reason as above
            for size in (list(detectors) if round_number % 2 == 0 else list(reversed(list(detectors)))):
                started = time.perf_counter()
                detectors[size].detect(image)
                timings[size].append((time.perf_counter() - started) * 1000)
        for size, detector in detectors.items():
            stats = percentiles(timings[size])
            say(f"| {size} px | {detector.load_seconds:.2f} s | {stats['p50']:.0f} ms | {stats['p95']:.0f} ms |")
        say()
        say("(Random-noise images contain no people, so the post-processing stage is idle; real photos are somewhat slower.)")
        say()

    # ----------------------------------------------------------------------------- search
    say("## Gallery search (one query, 5 reference images per person)")
    say()
    say("| Enrolled people | Reference images | p50 | p95 |")
    say("|---|---|---|---|")
    rng = np.random.default_rng(2)
    for people in (100, 1_000, 10_000):
        index = GalleryIndex(dim=512)
        vectors = rng.normal(size=(people * 5, 512)).astype(np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        index.replace(IndexEntry(f"p{i // 5:05d}", f"img{i}", vectors[i]) for i in range(people * 5))
        query = vectors[0]
        index.search(query, 5)
        timings = []
        for _ in range(60):
            started = time.perf_counter()
            index.search(query, 5)
            timings.append((time.perf_counter() - started) * 1000)
        stats = percentiles(timings)
        say(f"| {people:,} | {people * 5:,} | {stats['p50']:.2f} ms | {stats['p95']:.2f} ms |")
    say()
    say(f"Peak memory of this benchmark process: **{peak_memory_mb()} MB**.")

    out = settings.report_dir / "benchmark_latency.md"
    settings.ensure_directories()
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nSaved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
