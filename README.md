# OpenID Vision - Intelligent Identity Verification Lab

> *Know when to match. Know when to reject.*

**Open-set person re-identification under low inter-class variance** - an independent technical prototype built in response to the
Zed Digital *PS-1* assignment. It is **not** an official Zed Digital product and is not endorsed by Zed Digital.

> **In one paragraph.** A camera sees a person leave and later return. Standard "re-ID" assumes the person is
> always one of the people already known, and returns the nearest match. The real world is harsher: the
> returning person may be a *stranger* who simply dresses like someone enrolled (same uniform, similar build),
> and wrongly accepting them is the failure that matters. This system finds the most likely enrolled person
> **and** decides, with an explicit, versioned and measurable rule, whether the evidence is strong enough to
> accept that match - otherwise it says *unknown* or asks a human to *review*. **It looks at the face first and the whole
> body (clothing, build) second**: when a usable face is visible the face decides, so similar clothing can no longer get a
> stranger accepted. A built-in evaluation lab measures how many strangers get in versus how many enrolled people are correctly accepted.

| | |
|---|---|
| **What you can do** | **open the home page and press *Run the example*** - a built-in open-set analysis on 13 public-domain photos (known people, strangers, strangers in the *same clothes*) that shows face + body against clothes-only, with no setup; enroll authorised people; run a photo (**Match Studio**) or a prerecorded clip (**Video Explorer**) through detection → embedding → decision and see *why* the system said MATCH, UNKNOWN or REVIEW; hunt for the failures that matter in the **Lookalike Failure Lab**; calibrate the threshold on held-out people and try other thresholds safely in the **threshold sandbox**; export everything as JSON / CSV |
| **What it is not** | a surveillance product, an identity-verification service, a multi-object tracker or a live-camera system (see [Known limitations](#20-known-limitations)) |
| **Status** | all code, **427 backend and 157 interface tests**, real-model end-to-end checks (real photos, a real video, a real look-alike experiment, real face photos) and documentation are done. **Measured so far:** the face stage on the standard LFW benchmark (98.9 % accuracy; [report](docs/results/face_lfw.json)) and an end-to-end face-versus-clothing comparison ([report](docs/results/face_vs_body_lfw.json)). **Not run yet:** the pedestrian re-identification benchmark - Market-1501 must be supplied by you (it is research-licensed), so there are no pedestrian-ReID accuracy numbers. |
| **Using it (start here)** | double-click **`Start OpenID Vision.bat`**: the **home page** shows the three essentials (enroll · match · open-set analysis) and the example. For a step-by-step guide follow the **[User manual (PDF, 30 pages, with pictures of every screen)](OpenID-Vision-User-Manual.pdf)** - it needs no technical knowledge |
| **Explaining it** | [10-minute presentation script for HR (PDF)](OpenID-Vision-HR-Presentation-10min.pdf) · [docs/OPEN_SET_EXAMPLE.md](docs/OPEN_SET_EXAMPLE.md) (the home-page example: what it shows and what it does not prove) · [docs/JURY_GUIDE.md](docs/JURY_GUIDE.md) (what to say, a 10-minute demo script, 32 questions with honest answers) · the in-app **How it works** page (top bar) · [docs/FACE_AND_BODY_MATCHING.md](docs/FACE_AND_BODY_MATCHING.md) (exact rule, measurements, limits) |

---

## Contents

1. [Project overview](#1-project-overview) · 2. [Problem statement](#2-problem-statement) · 3. [Architecture](#3-system-architecture) ·
4. [Technology stack](#4-technology-stack) · 5. [Install on Windows](#5-installation-on-windows-11) · 6. [Python setup](#6-python-virtual-environment) ·
7. [Frontend setup](#7-frontend-installation) · 8. [Model weights & licence](#8-model-weights-and-licensing) · 9. [Dataset acquisition](#9-dataset-acquisition) ·
10. [Dataset layout](#10-dataset-directory-structure) · 11. [Start backend](#11-start-the-backend) · 12. [Start frontend](#12-start-the-frontend) ·
13. [API](#13-api-documentation) · 14. [Enroll](#14-enroll-a-reference-identity) · 15. [Re-identify](#15-perform-re-identification) ·
16. [Evaluate](#16-run-an-evaluation) · 17. [Calibrate](#17-calibrate-thresholds) · 18. [Interpreting metrics](#18-how-to-interpret-the-metrics) ·
19. [Tests](#19-run-the-automated-tests) · 20. [Limitations](#20-known-limitations) · 21. [Privacy](#21-privacy-and-data-retention) ·
22. [Troubleshooting](#22-troubleshooting) · 23. [Future work](#23-future-improvements)

**New to the code?** Read [docs/CODE_WALKTHROUGH.md](docs/CODE_WALKTHROUGH.md) first - it follows one request from the
browser to the database in plain language. Presenting it? Start with [docs/JURY_GUIDE.md](docs/JURY_GUIDE.md) and the ready-made **demo pack** in [demo/](demo/README.md): a PDF guide with real outputs, a 15-slide deck, public-domain sample pictures with known right answers, and `python demo\run_demo.py` which runs every scenario and prints PASS / FAIL (shorter running order: [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md)).

---

## 1. Project overview

Five ideas run through the whole system:

1. **Retrieval is not identification.** Ranking the enrolled people by similarity always produces a "best" name -
   even for a stranger. A separate *decision engine* ([backend/app/cv/open_set/](backend/app/cv/open_set/decision_engine.py)) accepts that name
   only if it passes an explicit rule. A nearest neighbour is never accepted automatically.
2. **Three decisions, plus an error state, never mixed up:** **MATCH** · **UNKNOWN** (no supported match) · **REVIEW** (ambiguous or poor-quality evidence) ·
   and PROCESSING ERROR when the input could not be handled at all. (The API's stable codes are `accepted`, `unknown`, `review_required`, `processing_error`;
   the interface shows MATCH / UNKNOWN / REVIEW.) "Unknown" is a verdict on the *evidence*, not a single identity: unknown people are never grouped or auto-enrolled.
3. **Every number is measured, nothing is simulated.** Embeddings come from a real pretrained network, speeds are timed on the machine,
   and metrics have written definitions with their denominators ([docs/METRICS.md](docs/METRICS.md)). Where data is missing, screens say
   "Not evaluated" instead of showing a plausible-looking number.
4. **Thresholds are chosen on data they will not be scored on.** People are split into *development / calibration / test* groups that never overlap.
   Rules are fitted on calibration people and frozen before the test people are scored.
5. **The face decides when it can be trusted; clothing only supports it.** A whole-body model mostly sees clothing colour and build, so a different person
   in similar clothes can look alike to it. With face matching on (the default), a usable face decides: a face that does not match can never be overruled by
   similar clothing. With no usable face (back view, far away, blurred) the system falls back to the body *and asks a person* instead of auto-matching.
   The face threshold (0.465) was chosen by a fixed rule on 4.5 million stranger pairs - see [docs/FACE_AND_BODY_MATCHING.md](docs/FACE_AND_BODY_MATCHING.md).
   Face fingerprints are **biometric data**; consent and deletion rules are in [docs/SECURITY_AND_PRIVACY.md](docs/SECURITY_AND_PRIVACY.md) §4a.

### What is implemented versus what has been validated

This table is deliberately blunt. "Implemented" means the code exists and is unit-tested; "validated" means it has been measured on real held-out data.

| Component | Implemented & tested | Validated on a public benchmark |
|---|---|---|
| Person detection (torchvision Faster R-CNN, COCO), quality checks | yes (real photo checked end to end) | n/a |
| Pretrained OSNet-AIN embeddings (single compact backbone, 512-d) | yes (real weights, SHA-256 verified) | **not yet** - needs Market-1501 |
| **Face matching** (YuNet detector + SFace recogniser, usable-face checks, face-first decision rule, hair/skin/clothing colour cues for a human reader) | yes (54 backend + 16 interface tests; real photos end to end) | **face stage: yes, on LFW** (98.93 % ± 0.35 over 6,000 pairs; 1 stranger pair in 100,000 reaches the default threshold). **Not** on pedestrian data, other cameras, or across demographic groups |
| Open-set decision engine (threshold, margin, review, unknown) | yes | **not yet** |
| Calibration workflow (fixed-recall / fixed-FAR, sample-size honesty) | yes | **not yet** (workflow demonstrated on a synthetic set only) |
| Calibrated confidence model (Platt, from similarity + margin) | yes | **not yet** |
| Evaluation: ROC, FAR/TAR, DIR@k, Rank-k, mAP, OSCR, bootstrap CIs, ablations | yes (metrics checked against hand-computed examples) | **not yet** |
| Same-clothing hard subset (colour-histogram proxy + manual-annotation hook) | yes | **not yet** |
| Triplet fine-tuning with batch-hard mining + leakage guard | yes (code and tests) | **no checkpoint has been trained**; no improvement is claimed |
| **Lookalike Failure Lab**: look-alike pair mining, reproducible challenge set, failure inspection with unproven hypotheses, baseline-vs-improved comparison, exports | yes (unit + API tests; run end to end with the real model on the smoke-test set) | **not yet** - needs Market-1501; no improved model has been trained, so none is compared |
| **Threshold sandbox** (try any threshold on a run's fixed per-query scores; never changes the policy) | yes (checked against the live decision engine on 3,200 random cases) | n/a |
| **Video Explorer** (frame-by-frame decisions on prerecorded clips; not tracking) | yes (real video files in tests; run end to end with the real detector and model) | n/a - accuracy on video has not been measured |
| **Built-in open-set example** on the home page (13 public-domain photos in a private, temporary gallery; face + body versus clothes-only; plots; a what-if slider) | yes (34 backend + 27 interface tests; run end to end with the real models: [report](docs/results/open_set_example.json)) | **no - it is a 13-photo demonstration, not a benchmark** ([what it does and does not prove](docs/OPEN_SET_EXAMPLE.md)) |
| Gallery management, history, retention, audit trail, optional access keys | yes | n/a |
| Web interface (7 screens plus a "How it works" tour, graphite look with light option, responsive) | yes (157 UI tests; layouts audited at 5 widths, with face data on screen) | n/a |

### The seven screens (plus a plain-language "How it works" tour, linked from the top bar)

| | Screen | What it is for |
|---|---|---|
| A | **Command Center** (the home page) | **the essentials first**: *1 Enroll people · 2 Match photos · 3 See the open-set analysis* (ticks itself from real data), then the **open-set example** you can run with one click and read at a glance (comparison table, two score plots, a face-line slider, all 13 photos with both matchers' answers), then the live system state (models, device, gallery, MATCH / UNKNOWN / REVIEW counts, threshold status, recent experiments) |
| B | **Identity Gallery** | enroll authorised test identities, add reference photos, see which people have a usable face on file, search, view, delete (with confirmation), rebuild embeddings, analyse faces of older photos |
| C | **Match Studio** | query photo → detected people → pick one → ranked candidates (each with its face and body score), the **Evidence** card (face vs body, the two faces side by side, hair/skin/clothing colour cues), the decision with its reason, exports of the decision record |
| D | **Video Explorer** | sample a prerecorded video every N seconds; see every frame's people and decisions, timings, progress, cancel; **frame-by-frame, not tracking** |
| E | **Lookalike Failure Lab** | *the signature feature*: find the different people the model confuses, build a reproducible challenge set, inspect the real mistakes, compare a baseline with an improved model if one exists |
| F | **Evaluation Lab** | ROC / FAR-vs-recall, fixed-recall operating point, ablations, **threshold sandbox**, latency, dataset metadata, experiment history, downloadable reports |
| G | **Model & System Settings** | models with weight provenance, the versioned decision policy (validated vs experimental), live system health and loading errors, privacy, audit trail |

---

## 2. Problem statement

The challenge text (PS-1 · *Open-Set Person Re-Identification under Low Inter-Class Variance*), and where each requirement lives:

| Requirement | Where it is addressed |
|---|---|
| Real deployments re-identify a person against an **open set** of unknown identities, where many people look almost identical | [decision engine](backend/app/cv/open_set/decision_engine.py), [hard-subset evaluation](backend/app/evaluation/hard_subset.py) |
| The hard failure is the **false accept**; *minimise FAR at a fixed recall* | [calibration](backend/app/evaluation/calibration.py) mode `fixed_recall` (the default); the alternative `fixed_far` is also available |
| **Metric learning**, margin / decision boundary, **hard-negative mining**, **calibration of scores into confidences** | [triplet loss + batch-hard mining](backend/app/training/triplet.py), [margin rule](backend/app/cv/open_set/policy.py), [Platt confidence model](backend/app/cv/open_set/confidence.py) |
| **Real-time**, one **compact backbone**, **no fixed identity count** | OSNet-AIN (2.2 M parameters); no classifier head - the gallery is a plain index of embeddings, so enrolling or deleting people needs no retraining. Measured speed: [docs/PERFORMANCE.md](docs/PERFORMANCE.md) |
| **ROC / FAR-vs-TAR analysis** on a **public benchmark** and a **curated low-variance subset**, with **ablations** | [Evaluation Lab](docs/EVALUATION.md) - pipeline complete, benchmark run pending the dataset |

Full requirement-by-requirement mapping with test names: [docs/REQUIREMENTS_TRACEABILITY.md](docs/REQUIREMENTS_TRACEABILITY.md).

---

## 3. System architecture

```
 Browser (React + TypeScript)                 Backend (FastAPI + PyTorch)                      Local storage
┌───────────────────────────┐   HTTP/JSON    ┌───────────────────────────────────────┐   ┌────────────────────────┐
│ 7 screens                 │ ─────────────► │ api/    thin routes (+ optional keys)  │   │ SQLite  (metadata,     │
│ Command Center · Gallery ·│                │ services/ the workflows                │──►│   policy versions,     │
│ Match Studio · Video ·    │ ◄───────────── │   reid · gallery · video · jobs        │   │   history, runs, audit)│
│ Lookalike Failure Lab ·   │                │ cv/     the computer vision            │   │ references/ (JPEG crops)│
│ Evaluation Lab · Settings │                │   detection → quality → embedding →    │   │ queries/ video_frames/ │
└───────────────────────────┘                │   retrieval → open_set decision        │   │ cache/  (embeddings)   │
                                             │ evaluation/ metrics · protocol · runner│   │ reports/ (JSON/MD/HTML)│
                                             │ training/   triplet fine-tuning        │   └────────────────────────┘
                                             └───────────────────────────────────────┘
                                                      loads once at startup:  OSNet-AIN embedder · Faster R-CNN detector · YuNet + SFace (faces)
```

One query, in order: **upload → decode safely → detect people → crop & quality-check → find and judge the face → embed body (one batch) and face → rank enrolled
people by face and by body → decide under the active policy (face first) → save scores → answer**. Details and design decisions: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Gallery strategy (a documented, consistent decision).** Each enrolled person keeps their *individual image embeddings*; a person's score for a
query is the score of their *best-matching image*. The same function ([ranking.py](backend/app/cv/retrieval/ranking.py)) is used by the live API
and by the evaluation code, so what is measured is what is served.

---

## 4. Technology stack

| Layer | Choice (exact version used) | Why |
|---|---|---|
| Embedding backbone | **OSNet-AIN x1.0** (ported from Torchreid, MIT) on PyTorch **2.14.1** (CPU build) | compact (2.17 M parameters), designed for person ReID, strong across cameras |
| Person detector | torchvision **Faster R-CNN MobileNetV3-Large FPN**, COCO weights (BSD) | lightweight, person class filter, no AGPL dependency |
| Backend | Python **3.14**, FastAPI **0.136**, Pydantic **2.14**, SQLAlchemy **2.0.54** (SQLite, PostgreSQL-ready), Uvicorn **0.47** | typed schemas, auto-generated OpenAPI docs |
| Image / maths / video | NumPy **2.5**, Pillow **12.3**, OpenCV-headless **5.0** (also decodes the videos; FFmpeg is built in) | |
| Frontend | React **19.3**, TypeScript **7.0**, Vite **8.3**, Tailwind CSS **4.3**, TanStack Query **5**, Radix Dialog, Recharts **3.10**, Lucide icons | accessible primitives, typed API layer |
| Tests | pytest **9.1** (+ httpx2), Vitest **5.0** + Testing Library | 427 backend + 157 frontend tests |
| Node.js | **24.21 LTS** (set up locally by `scripts/setup.ps1` if missing) | |

Pinned ranges: [backend/requirements.txt](backend/requirements.txt), [frontend/package.json](frontend/package.json) (with a lock file).

---

## 5. Installation on Windows 11

Developed and tested on **Windows 10 (build 19045)** with a 2-core / 4-thread laptop CPU, 8 GB RAM and no GPU. Windows 11 uses the same
steps but was not separately tested. Python 3.11 or newer is required (3.14 was used). Node.js is installed for you if missing.

**Fastest path** (one command, ~5 minutes, downloads ≈ 400 MB):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

Then open **http://127.0.0.1:8000**. There is nothing to sign in to: access keys are **off by default** (see §20 and `docs/SECURITY_AND_PRIVACY.md` to switch them on).

`setup.ps1` creates the virtual environment, installs CPU PyTorch and the backend packages, writes `.env`, downloads and
**verifies** the model weights, installs a portable Node.js if you have none (checksum-verified), and builds the interface. Everything cached or
temporary stays inside the project's `.tools/` folder - useful if your `C:` drive is nearly full. Use `-DryRun` to preview it, `-SkipNode` for backend only.

The sections below are the same steps done by hand.

## 6. Python virtual environment

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
cd ..
backend\.venv\Scripts\python.exe scripts\init_env.py          # writes .env with random keys (does not overwrite an existing one)
```

For an NVIDIA GPU, install the matching CUDA build of PyTorch instead of the CPU one and set `REID_DEVICE=auto` (the default): the system uses the
GPU when PyTorch can see one and otherwise falls back to the CPU. Asking for `REID_DEVICE=cuda` without a GPU is a clear error, not a silent slowdown.
*The GPU path is implemented but has not been tested here (no GPU available).*

## 7. Frontend installation

```powershell
cd frontend
npm install
npm run build        # production build, served by the backend itself on port 8000
```

## 8. Model weights and licensing

The application **never downloads anything while running**. Weights come from one explicit, verifying step:

```powershell
backend\.venv\Scripts\python.exe scripts\download_weights.py
```

| File | Source | Size | Licence | Integrity check |
|---|---|---|---|---|
| `osnet_ain_x1_0.pt` (embedder) | [Hugging Face `LibreYOLO/LibreReID-osnet`](https://huggingface.co/LibreYOLO/LibreReID-osnet) - a byte-identical mirror of the [Torchreid](https://github.com/KaiyangZhou/deep-person-reid) model zoo | 8.5 MB | MIT | SHA-256 pinned in [registry.py](backend/app/cv/embedding/registry.py) (cross-checked against the Hugging Face API) |
| `fasterrcnn_mobilenet_v3_large_fpn-fb6a3cc7.pth` (detector) | [torchvision](https://download.pytorch.org/models/fasterrcnn_mobilenet_v3_large_fpn-fb6a3cc7.pth) | 74 MB | BSD-3-Clause | SHA-256 prefix = the 8 hex characters in the official file name |
| `face_detection_yunet_2023mar.onnx` (face detector) | [OpenCV model zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) | 0.2 MB | MIT | SHA-256 equals the value in the zoo's own Git-LFS pointer file (checked in [registry.py](backend/app/cv/face/registry.py)) |
| `face_recognition_sface_2021dec.onnx` (face recogniser) | [OpenCV model zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) | 37 MB | Apache-2.0 | same method |

Face models are optional: `--skip-face` leaves them out, `REID_FACE_MATCHING=false` switches them off, and without the files the system matches on the body only and says so.

Weights are loaded with `torch.load(weights_only=True)` (cannot execute pickled code), must match the architecture exactly, and a file that fails
its check is deleted, never used. A corrupt or missing file leaves the server running with a clear "model not loaded" status instead of crashing.

**Training-data caveat (please read).** The OSNet-AIN weights are the multi-source *domain-generalisation* release, trained on **MSMT17, DukeMTMC-reID
and CUHK03** - *not* on Market-1501, which makes Market-1501 an unseen target domain (a fairer test). Those are research datasets with their own terms,
and DukeMTMC-reID was withdrawn by its authors in 2019 for privacy reasons. Treat this prototype as research-only; do not deploy it commercially without
reviewing those terms. The face models were trained by their authors on public face datasets whose terms this project has not audited (see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).

## 9. Dataset acquisition

**You supply the benchmark.** Market-1501 (Zheng et al., ICCV 2015) is licensed for **non-commercial research** and may not be redistributed, so it is
not bundled and the application never downloads it.

1. Download *Market-1501-v15.09.15* from its authors (see the dataset's [project page](https://zheng-lab-anu.github.io/Project/project_reid.html) and the paper
   *"Scalable Person Re-identification: A Benchmark"*), and read its terms. Cite the paper if you publish results.
2. Unpack it safely and check it:

```powershell
backend\.venv\Scripts\python.exe scripts\prepare_dataset.py unpack C:\Downloads\Market-1501-v15.09.15.zip --name market1501
backend\.venv\Scripts\python.exe scripts\prepare_dataset.py inspect market1501
```

`unpack` refuses archive entries that try to escape the folder, will not write into a non-empty folder, and `inspect` tells you in plain words whether the
evaluation can use the data (people, images, cameras, readability, missing folders). Your own **authorised** images work too: put them in
`datasets/<name>/<person_id>/<image>.jpg` (a camera can be encoded as `c3` in the file name).

A **synthetic smoke-test** set (cartoon mannequins) can be generated for checking that the pipeline runs: `python scripts/make_smoke_dataset.py`.
It is stamped `kind: smoke_test`; every screen and report labels results on it *"not a benchmark"* and the dashboard ignores it.

## 10. Dataset directory structure

```
datasets/                              (git-ignored; never committed)
├── market1501/                        official layout; a nested "Market-1501-v15.09.15/" folder is found automatically
│   ├── bounding_box_train/  0002_c1s1_000451_03.jpg   (person 0002, camera 1, ...)
│   ├── bounding_box_test/   ...        junk (-1) and distractor (0000) files are ignored
│   ├── query/               ...
│   └── hard_subset.json     optional - manual "same clothing" annotation (see docs/EVALUATION.md)
└── my_own_data/                       folder layout: one folder per person
    ├── subject-001/  c1_000.jpg  c2_001.jpg ...
    └── dataset.json                   optional: {"name": "...", "kind": "benchmark" | "smoke_test", "license": "..."}
```

## 11. Start the backend

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1            # http://127.0.0.1:8000
```

or by hand: `cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`. Port **8000** is the default;
`start.ps1` refuses to start if the port is busy (use `-Port 8020` to move) and never touches another program's process. The built interface is served from the same port.

## 12. Start the frontend

Only needed while *editing* the interface (hot reload):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Dev       # also opens http://localhost:5173
# or:  cd frontend; npm run dev
```

## 13. API documentation

Interactive documentation (generated from the code, so it cannot drift): **http://127.0.0.1:8000/api/docs**. By default no key is needed. If you switch keys on (`REID_AUTH_REQUIRED=true`), every route except `/api/health` and `/api/readiness` needs an `X-API-Key` header. Errors always look like `{"error": {"code", "message", "request_id", "details"}}`.

| Area | Routes (role needed) |
|---|---|
| Health | `GET /api/health` · `GET /api/readiness` (public, 503 if the model is not loaded) · `GET /api/auth/me` · `GET /api/overview` |
| Re-ID | `POST /api/reid/detect` · `POST /api/reid/predict` (viewer) · `GET /api/reid/history` · `GET /api/reid/history/{request_id}` · `GET /api/reid/history/{request_id}/export?format=json\|csv` (the decision record) |
| Video | `GET /api/video/limits` · `POST /api/video/analyze` (multipart: `video`, `every_seconds`, `max_frames`) · `GET /api/video/jobs` · `GET /api/video/jobs/{id}` · `POST …/{id}/cancel` (viewer) · `GET …/{id}/frames/{n}` · `GET …/{id}/export?format=json\|frames_csv` · `DELETE …/{id}` (operator) |
| Lookalike lab | `POST /api/lookalike/run` (admin) · `GET /api/lookalike/runs` · `GET …/runs/{id}` · `GET …/runs/{id}/export?format=json\|md\|pairs_csv\|failures_csv\|summary_csv` · `GET …/runs/{id}/image?ref=…` (viewer; only images the experiment recorded) |
| Threshold sandbox | `GET /api/evaluation/runs/{id}/sandbox` · `POST /api/evaluation/runs/{id}/sandbox` (viewer: read-only, never writes the policy) |
| Built-in example | `GET /api/demo` · `POST /api/demo/prepare` · `POST /api/demo/cases/{id}` · `DELETE /api/demo/sandbox` · `GET /api/demo/files/{path}` (viewer; read-only: a private in-memory gallery, nothing saved, your gallery untouched) |
| Gallery | `GET /api/gallery` · `GET /api/gallery/{ref}` (viewer) · `POST /api/gallery/enroll` · `POST /api/gallery/{ref}/images` · `DELETE /api/gallery/{ref}?confirm={ref}` · `POST /api/gallery/rebuild` (operator) · `POST /api/gallery/reset` (admin) |
| Evaluation | `GET /api/evaluation/datasets` · `…/checkpoints` · `…/runs` · `…/runs/{id}` · `…/runs/{id}/report?format=json\|md\|html` (viewer) · `POST …/run` · `POST …/calibrate` · `POST …/runs/{id}/cancel` (admin) |
| Policy | `GET /api/config` · `GET /api/model/status` · `GET /api/config/history` (viewer) · `POST /api/config/thresholds` · `POST /api/maintenance/cleanup` · `GET /api/audit` (admin) |

The role in brackets only matters when keys are switched on: **viewer** (run queries, read) · **operator** (+ manage the gallery) · **admin** (+ thresholds, evaluations, reset, cleanup). With keys off, every caller is an admin.

## 14. Enroll a reference identity

*In the interface:* **Identity Gallery → Enroll identity** → choose a pseudonymous *reference ID* (e.g. `subject-017`, not a real name), add one or more images,
and confirm the person is authorised. Photos containing several people are refused so the wrong person can never be enrolled by accident.

*From the command line* (PowerShell; use `curl.exe`, not the `curl` alias):

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/gallery/enroll `
  -F reference_id=subject-017 -F consent_confirmed=true -F images_are_crops=false `
  -F "images=@C:\authorised\subject-017_a.jpg" -F "images=@C:\authorised\subject-017_b.jpg"
```

Only our own re-encoded JPEG *crop* of the person is stored (never the raw upload), together with a body fingerprint and - if a usable face is found - a face fingerprint.
**Include at least one clear, front-facing photo of the face**: a person enrolled without one can only be matched by clothing and build, and the screen warns you. Add more images later
with *Add images*; delete needs the reference ID typed back and removes the face data too. Galleries enrolled before face matching existed are upgraded automatically at start-up (or press **Analyse faces**).

## 15. Perform re-identification

*In the interface:* **Match Studio** → drop an image → **Detect people** (optional; select who to match) → **Run re-identification**. You get the outcome, the
actual similarity, the threshold, the margin to the runner-up, the model, the measured time, a plain-language reason, and *all* ranked candidates.
Tick **"Image is already a person crop"** for tight crops (skips the detector). With face matching on you also get the **Evidence** card: the face and body scores against their own thresholds,
the two faces side by side, and hair / skin / clothing colour cues (shown for a human reader; they never change the decision).

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/reid/predict -F "image=@C:\authorised\query.jpg" -F mode=all -F top_k=5
```

(With keys switched on, add `-H "X-API-Key: <your key>"` to either command.)

`mode` is `all` (detect and match everyone), `box` (one person, with `box=x1,y1,x2,y2`) or `crop` (the image already is one person).

### 15a. Video Explorer

*In the interface:* **Video Explorer** → drop a clip (`.mp4 .mov .avi .mkv .webm`, up to 100 MB / 180 s by default) → choose how often to take a frame → **Analyse video**.
Each sampled frame goes through the same detector, model, gallery and decision rules as a photo, and **each frame is judged on its own**: a person is never followed between frames,
so this is frame-by-frame re-identification, **not multi-object tracking** (the screen says so). You get a timeline (M = match, U = unknown, R = review, – = nobody found), the frame with its
people drawn on it, the reason and numbers for each person, per-frame timings, and JSON / CSV exports. The uploaded video is deleted as soon as processing ends; frame previews are kept
for `REID_QUERY_RETENTION_HOURS` (24 h) and can be deleted earlier. Limits are in `.env` (`REID_MAX_VIDEO_MB`, `REID_MAX_VIDEO_SECONDS`, `REID_MAX_VIDEO_FRAMES`).

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/video/analyze -F "video=@C:\authorised\clip.mp4" -F every_seconds=1 -F max_frames=30
curl.exe http://127.0.0.1:8000/api/video/jobs/<run_id>          # progress, then every frame's decisions
```

### 15b. Lookalike Failure Lab

The failure that matters most is **two different people who look alike**. The lab goes looking for it on a labelled dataset (install one first, §9):

1. **Mine** - list the pairs of different people whose photos the model finds most alike (searching the *test*, *calibration* or *development* people).
2. **Challenge** - turn those pairs, plus ordinary same-person pairs from different cameras, into a fixed, reproducible *challenge set* and measure the matcher on it at its **own calibrated threshold**
   (chosen on calibration people only, never on the people being searched). The challenge false-accept rate is shown **next to** the all-pairs rate, because the first is high by construction.
3. **Compare** - score the *same* pairs with a fine-tuned checkpoint, if you select one. A checkpoint trained on any evaluated person is refused automatically. With none selected the lab says so; it never invents a comparison.
4. **Inspect** - open each real mistake (stranger accepted / enrolled person given the wrong name / enrolled person not accepted) with both photos, the **observed** numbers, and **possible causes labelled "hypothesis - not proven"**.

Embedding similarity and clothing similarity are kept separate: each pair also carries a label-free clothing-*colour* similarity, because look-alike embeddings do not prove identical clothing.
Exports: full JSON record, pairs CSV, mistakes CSV, summary CSV, Markdown report. Details and definitions: [docs/LOOKALIKE_LAB.md](docs/LOOKALIKE_LAB.md).

```powershell
python scripts\make_smoke_dataset.py        # only to check the lab runs; its results are labelled "not a benchmark"
# then, in the interface:  Lookalike Failure Lab → Run look-alike experiment
```

### 15c. Threshold sandbox

Every finished evaluation or look-alike experiment keeps a fixed table of its per-query results. The sandbox (a tab in both labs) lets you try **any** threshold and margin rule on that table and shows, with real
counts, how many strangers would get in, how many enrolled people would be turned away, and which individual decisions change - next to the run's own calibrated rule. The counting uses the same rule as the live
decision engine (tested for equality on random cases). **It never changes the active policy** (there is deliberately no "apply" button), and on the *test* split it warns that picking a threshold because it looks good
there would be tuning on the test set. Real thresholds are chosen by a calibration run and applied in **Model & System Settings**.

## 16. Run an evaluation

*In the interface:* **Evaluation Lab** → choose a dataset, the operating point and seeds → **Run evaluation**. It runs in the background with real progress and can be cancelled.
It produces the ablation table, ROC (FAR vs recall), score distributions, CMC/mAP, the same-clothing subset analysis, speed/memory, metadata, and downloadable reports.

*From the command line:*

```powershell
# PS-1 objective: keep 90% of enrolled people accepted AND correct, minimise false accepts. Three seeds.
backend\.venv\Scripts\python.exe scripts\run_evaluation.py --dataset market1501 --mode fixed_recall --target-recall 0.90 --seeds 0 1 2 --max-identities 150
# Alternative: never let more than 1% of strangers in, keep as many enrolled people as possible.
backend\.venv\Scripts\python.exe scripts\run_evaluation.py --dataset market1501 --mode fixed_far --target-far 0.01
```

CPU time: embedding costs about 0.12-0.2 s per *new* image on the development laptop and is cached, so repeat runs are fast. Use `--max-identities` for a
first run; the full Market-1501 (≈32 000 images) is roughly an hour of embedding on a small CPU. Reports land in `backend/data/reports/`.

*Optional metric-learning fine-tuning* (implemented, **no checkpoint trained yet**, no improvement claimed):

```powershell
backend\.venv\Scripts\python.exe scripts\finetune_triplet.py --dataset market1501 --seed 0 --epochs 3 --out backend\weights\finetuned\market_seed0.pt
backend\.venv\Scripts\python.exe scripts\run_evaluation.py --dataset market1501 --seeds 0 --finetuned-checkpoint backend\weights\finetuned\market_seed0.pt --variants thr thr_margin thr_margin_finetuned
```

The checkpoint records exactly which people it trained on; the evaluation **refuses it automatically** if any of them is in its calibration or test split.

## 17. Calibrate thresholds

The shipped threshold (`0.70`) is an **unvalidated starting value** and is labelled so everywhere. To replace it with something defensible:

*Interface:* **Evaluation Lab → Calibrate threshold** (uses only the calibration split; the test split is never read), then **Model & Thresholds → Apply this calibration**.
*Command line:* `backend\.venv\Scripts\python.exe scripts\calibrate_threshold.py --dataset market1501 --mode fixed_recall --target-recall 0.90`.

What you get: a threshold (and optionally a margin rule), the FAR measured on calibration people **with its 95 % upper confidence bound and sample size**, and a
fitted *calibrated confidence* model. **If the target cannot be met the result says so and cannot be applied as "calibrated".** A calibration is also refused
if it was computed for a different model than the one running. Policy changes are versioned and audited; every decision records the version that made it.

Policy status: `unvalidated` (starting value) · `experimental` (typed in by a person) · `calibrated` (selected on a held-out calibration split by this workflow).

## 18. How to interpret the metrics

Short version - full definitions with denominators and a worked example are in **[docs/METRICS.md](docs/METRICS.md)**.

| Metric | Plain meaning | Denominator |
|---|---|---|
| **FAR** (False Accept Rate) | how often a *stranger* is wrongly named as an enrolled person | all stranger queries |
| **TAR** | how often an enrolled person is accepted (any identity) | all enrolled-person queries |
| **DIR@k** | enrolled person accepted **and** correctly in the top-k (DIR@1 = "accepted and correct") | all enrolled-person queries |
| **ROC / OSCR curve** | recall plotted against FAR as the threshold moves; the OSCR curve is DIR@1 vs FAR and AUOSCR its area | - |
| **Rank-1 / Rank-k, mAP** | closed-set retrieval quality, thresholds ignored | enrolled-person queries / ranked gallery images |
| **Precision / recall / F1** | for "name the right person": TP = accepted & correct; FP = accepted but wrong or a stranger | accepted / enrolled-person queries |

FAR is **query-level**: an unknown query counts as falsely accepted whenever the engine accepts *any* enrolled identity for it. It is not a pairwise verification error.

## 19. Run the automated tests

```powershell
cd backend ; .\.venv\Scripts\python.exe -m pytest              # 427 tests, about 3 min (fakes for the networks, real video files, plus real-model tests)
cd ..\frontend ; npm test                                        # 157 tests, about 2 min
cd ..\frontend ; npm run typecheck                               # strict TypeScript
```

Backend tests use deterministic fakes in place of the neural networks (so they check routes, rules, storage and security, **not accuracy**) plus a few real-model tests that run
automatically when the weights are present. Metric tests compare against hand-computed answers. Results of the last run are in [docs/REQUIREMENTS_TRACEABILITY.md](docs/REQUIREMENTS_TRACEABILITY.md#test-results).
Responsive layout: [docs/DESIGN.md](docs/DESIGN.md#responsive-testing) explains the five-width audit and ships the script.

## 20. Known limitations

- **No pedestrian-benchmark numbers yet.** The pipeline is complete and verified, but Market-1501 has to be supplied by you (§9). Until then the Evaluation Lab shows an honest empty state.
  The Evaluation Lab and the Lookalike Failure Lab measure the **body** model (their datasets have no readable faces).
- **Face matching is 2-D photo matching, not a phone's Face ID.** No depth sensing, no liveness check (a photo of a person can be matched like the person), look-alikes and twins can still score high,
  and masks, sunglasses, strong angles, low light and tiny faces make a face unusable (reported, never silently trusted). Face accuracy was measured only on LFW (easy, frontal, mostly well-lit public figures);
  other cameras and demographic groups were **not** measured, and face recognition is known to vary across groups. The default face threshold is evidence-based but **unvalidated for your cameras**.
  Details and numbers: [docs/FACE_AND_BODY_MATCHING.md](docs/FACE_AND_BODY_MATCHING.md).
- **The cartoon smoke-test set is not meaningful for accuracy.** A real-photo model separates cartoon mannequins poorly (the system correctly reported that the 90 % recall target was unreachable on it).
- **Speed is interactive, not real-time video.** Measured on a 2-core laptop CPU: about **0.5 s** for a one-person photo when the machine is idle and up to **≈ 1.2 s** when other programs are busy
  (detector ≈ 0.4-1.0 s, embedding ≈ 0.1-0.29 s). Video Explorer analyses sampled frames of prerecorded clips one at a time (0.7-3.4 s per frame measured here, depending on how busy the machine was); it is not a tracker, and there is no live-camera or cross-camera tracking. A GPU path exists but is untested here. See [docs/PERFORMANCE.md](docs/PERFORMANCE.md).
- **A threshold chosen on one calibration sample is not a guarantee of the same FAR on new people.** Reports show sample sizes and a 95 % upper bound; small calibration sets are flagged.
- **The look-alike challenge set is selected by the baseline model**, so its false-accept rate is high by construction and is not comparable with a normal FAR (the lab prints the realistic all-pairs rate beside it). A model compared on the same pairs is a fair stress test, not a random sample.
- **No improved model exists yet.** The comparison machinery is built and tested, but no fine-tuned checkpoint has been trained or evaluated, so no improvement is claimed.
- **Possible causes of a mistake are hypotheses** worded from recorded numbers; none has been tested by changing the input.
- **Video accuracy has not been measured**; the end-to-end check used frames cut from one photo, which proves the pipeline and decisions, not accuracy.
- **"Same clothing" is a proxy**: Market-1501 has no clothing labels, so look-alikes are found with colour histograms (or a manual `hard_subset.json`).
- **Calibrated confidence depends on the known:unknown mix of the calibration data** and is valid only for the model it was fitted on.
- **Single-tenant, local trust boundary, and no login by default.** Access keys are off (everyone is an admin) and the server listens on `127.0.0.1` only; that network isolation is the only protection. Optional keys (three shared roles) exist but there are no user accounts and no TLS. Switch the keys on, or better put it behind real authentication and HTTPS, before exposing it beyond localhost.
- **No claim of demographic fairness, privacy compliance or production readiness** is made or implied. The pretrained weights were trained on research datasets (see §8).
- SQLite with `create_all` plus an automatic "add missing optional columns" step (no full migration tool yet); one background job at a time; evaluation embeds on the CPU.

## 21. Privacy and data retention

Full policy: [docs/SECURITY_AND_PRIVACY.md](docs/SECURITY_AND_PRIVACY.md). In short:

- Use **authorised, controlled test images only.** Never point this at public cameras, scrape photos, or try to identify real-world individuals. Enrolling requires an explicit authorisation tick, and identities are pseudonymous labels.
- **Raw uploads are never stored.** We keep our own re-encoded JPEG of the person *crop*: reference crops until the identity is deleted; query crops for `REID_QUERY_RETENTION_HOURS` (default **24 h**, `0` = never).
  History rows (scores and decisions only - no images, no embeddings) are removed after `REID_HISTORY_RETENTION_DAYS` (default **30**). Cleanup runs at startup and on demand (Settings → Run cleanup now).
- **Video:** the upload is deleted the moment processing ends (success, failure or cancel); small frame previews follow the same retention as query crops and can be deleted at once; limits on size, length and frames apply; the real container type is checked from the file's bytes, never its name.
- Logs contain routes, status codes and timings - never images, embeddings or keys. Sensitive actions are written to an audit trail (admin-only).
- Stored files use server-generated random names; user-supplied names/paths never touch the file system. Uploads are checked by content (not extension), size- and dimension-limited, and re-encoded.
- A rejected query is described neutrally ("no supported match"); it is never presented as evidence of wrongdoing, and rejected people are never auto-enrolled or grouped.
- **Face data is biometric data.** A face fingerprint (128 numbers) is stored only for enrolled, consenting people, on this computer only, until they are deleted (deleting removes it). A query face is compared and discarded: only scores and decisions are kept in the history.
  Enrolment says so. Biometric data is specially regulated (GDPR, India's DPDP Act, Illinois BIPA); this prototype claims no compliance. See [docs/SECURITY_AND_PRIVACY.md](docs/SECURITY_AND_PRIVACY.md) §4a.

## 22. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ENOSPC: no space left on device` from `npm`/`pip` | The system drive `C:` is full (caches default there). `scripts\setup.ps1` already redirects caches to `.tools\`; for manual commands set `npm_config_cache`, `PIP_CACHE_DIR` and `TEMP` to a folder on another drive. |
| `Port 8000 is already in use` | Something else owns it. Use `start.ps1 -Port 8020`. (The script never stops other programs.) |
| Top bar says **Backend offline** | The backend is not running, or the dev proxy points to the wrong port (`REID_BACKEND_URL`). |
| Top bar says **Model not loaded** / `model_unavailable` (503) | Weights missing or corrupt: run `scripts\download_weights.py`. The reason is shown on **Model & System → Runtime & system**. |
| Results say "face models are not loaded - only the body is compared" | The two face files are missing or failed their checksum: run `scripts\download_weights.py` (without `--skip-face`) and restart. Matching works on the body meanwhile, and says so. |
| A person's card says **No face on file** | Their reference photos contain no usable face (back view, tiny, blurred, turned). Add a clear front-facing photo, or press **Analyse faces** if the photos were enrolled before face matching existed. |
| **Detector missing** | Only the detector weights are absent. Crop mode ("Image is already a person crop") still works; Video Explorer needs the detector and will say it is not runnable. |
| Video upload refused | The file is not really an MP4/MOV/AVI/MKV/WebM (checked from its bytes), is over the size / length limit, or cannot be decoded. The message says which. |
| Lookalike Failure Lab says **Not runnable** | No labelled dataset is installed (§9) or the embedding model is not loaded. The message names the fix. |
| "The baseline model could not reach the requested operating point" | The calibration people cannot be separated well enough for the recall you asked for (typical on the cartoon smoke-test set). The threshold shown is a fallback, not calibrated. |
| A **Connect** screen asks for a key | Keys have been switched on (`REID_AUTH_REQUIRED=true` in `.env`). Enter one of the three keys from `.env`, or set it back to `false` and restart the backend. |
| `403 forbidden` (keys on only) | Your key's role is too low (e.g. viewer trying to enroll). The button tooltip names the needed role. |
| Evaluation Lab says **No dataset is installed** | See §9. `prepare_dataset.py inspect <name>` explains what is missing. |
| "Calibration was computed for a different model" | The model/flip setting changed since. Re-run calibration. After switching models also press **Rebuild embeddings** in the gallery. |
| An evaluation is slow | First runs embed every new image on the CPU (cached afterwards). Lower **Max people per split**. |
| Screens look unstyled after editing the frontend | Run `npm run build` again (the backend serves `frontend/dist`) or use `start.ps1 -Dev`. |
| Corrupt text (`â€“`) after editing files in PowerShell | Windows PowerShell 5.1 re-encodes UTF-8 files. Edit with an editor, not `Get-Content | Set-Content`. |

## 23. Future improvements

1. Run the benchmark: Market-1501 (and MSMT17 for a harder, multi-camera set), multiple seeds, publish the report; then train and *evaluate* a triplet fine-tuned checkpoint.
2. Real clothing annotation (the manual-subset hook is in place) and clothing-change datasets for a ground-truth low-variance subset.
3. Learned score fusion (e.g. attributes + embedding) with the same calibration discipline; margin/ArcFace-style objectives; re-ranking.
4. Tracklet aggregation on top of Video Explorer (many frames of one person → one robust embedding), only on authorised footage; full multi-object tracking would be a separate project (PS-2).
5. Production hardening: OIDC/SSO, TLS, PostgreSQL + Alembic migrations, per-tenant galleries, rate limiting, GPU/ONNX inference, observability.
6. Fairness and robustness studies across demographics, lighting and camera types before any real deployment.

---

*Credits: OSNet - Zhou et al., ICCV 2019 / TPAMI 2021 (Torchreid, MIT). Batch-hard triplet loss - Hermans et al., 2017. Market-1501 - Zheng et al., ICCV 2015. Open-set classification rate - Dhamija et al., NeurIPS 2018.
The OpenID Vision name, logo and graphite-and-crimson look are original to this project; no Zed Digital assets are used.*
