# OpenID Vision - demo pack

*Know when to match. Know when to reject.*

Everything needed to **run** the system, **see** what it does and **explain** it to people who did not build it - with pictures that have
known right answers and the real outputs of a reference run.

## Start here

| If you want to... | Open |
|---|---|
| learn to USE the website, step by step | **`..\OpenID-Vision-User-Manual.pdf`** (30 pages, every screen photographed with numbered boxes, including the home-page example; rebuilt by `scripts\make_manual_images.mjs` + `scripts\build_user_manual.mjs`) |
| see the point in 10 seconds, with no setup | open the website's **home page** and press **Run the example** (or `python demo\run_open_set_example.py`): 13 public-domain photos, face + body against clothes-only - [what it shows and does not prove](../docs/OPEN_SET_EXAMPLE.md) |
| understand the project in 10 minutes | **`DEMO_GUIDE.pdf`** (how to run it, how to read every screen, every scenario with its real output) |
| present it | **`JURY_DECK.pdf`** (15 slides) and **`JURY_GUIDE.pdf`** (what to say, a click-by-click demo, the numbers you may and may not quote, 32 likely questions with honest answers) |
| understand the exact rule and the measurements | **`FACE_AND_BODY_MATCHING.pdf`** |
| run it yourself | the three commands below |

## Three commands (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1        # once: Python environment, interface, models (checksum-verified)
powershell -ExecutionPolicy Bypass -File scripts\start.ps1        # leave open; the system is at http://127.0.0.1:8000
python demo\run_demo.py --compare                                 # runs every scenario and prints what it decided and why
```

`run_demo.py` enrols three example people, shows the system the pictures and clips in `samples/`, and for every scenario prints the answer it
**should** give, the answer it **gave**, the face and body scores and the system's own explanation. It saves the decision records (JSON and CSV)
to `output_latest/`; compare them with `expected_output/` (a reference run). `--compare` also re-runs the face photos under the old
clothing-only policy so you can see the difference (it puts the policy back afterwards); `--lab` adds the Lookalike Failure Lab;
`--cleanup` removes the example people.

## The stories the pack shows

1. **Face + body (the main show).** The same person in different clothes and years is recognised; strangers are rejected - even when
   clothing alone would have let them in. Clothing-only matching got **3 of 8** of these photos right; face + body got **8 of 8**.
2. **No usable face (the safe fallback).** Street photos with the heads blurred: the system will not accept on clothing alone; it asks a person (REVIEW).
3. **Strangers in the same clothes (the home-page example).** Three people who were never enrolled, photographed in the same orange flight suit as enrolled people: clothing alone accepted **3 of 3**, face + body **0 of 3** (and 5 of 5 known people recognised instead of 0 of 5). 13 photos - a demonstration, not a benchmark.

## Try it with your own volunteers

```powershell
python demo\face_check.py my_photos --i-have-consent          # layout of my_photos\ is explained at the top of face_check.py
python demo\face_check.py demo\samples\faces --i-have-consent # the public-domain set
```

## What is in this folder

| Path | What it is |
|---|---|
| `DEMO_GUIDE.pdf`, `JURY_DECK.pdf`, `JURY_GUIDE.pdf`, `FACE_AND_BODY_MATCHING.pdf` | the printable documents (rebuilt by `scripts\build_demo_documents.mjs`) |
| `samples/` | the pictures and clips (`SOURCES.md` lists author and licence of every file; all public domain or CC0, heads blurred in the street photos) |
| `expected_output/` | the real results of a reference run: one decision record per scenario, the video results, the clothing-vs-face comparison, the lab exports |
| `screenshots/` | real screenshots of the interface, taken by `scripts\make_demo_screenshots.mjs` |
| `run_demo.py` | runs every scenario against the running server (standard library only) |
| `run_open_set_example.py` | runs the home-page example from the command line (read-only for your data) and saves `docs/results/open_set_example.json`; `samples/demo_manifest.json` lists its people, photos and right answers |
| `face_check.py` | the same idea for your own folder of consenting volunteers' photos |
| `make_samples.py`, `prepare_scenes.py`, `prepare_faces.py`, `write_sources.py`, `annotate_screenshot.py` | rebuild the samples, their sources file and the annotated screenshot (reproducible; licences are checked and non-public-domain files are refused) |

## Honest limits (please read before presenting)

* **Not a phone's Face ID**: 2-D photo matching, no depth sensor, no liveness check.
* Face accuracy was measured on the standard **LFW** benchmark (easy) - **98.9 %** - plus a small end-to-end test; other cameras, lighting, ages and demographic groups were **not** measured.
* The **pedestrian re-identification benchmark (Market-1501) has not been run** (it must be supplied under its research licence).
* Thresholds are evidence-based defaults, **unvalidated** for any specific camera; the screens say so.
* The example people are public figures photographed at work; they are used only to show recognition across photographs. Use only consenting volunteers for your own tests.
