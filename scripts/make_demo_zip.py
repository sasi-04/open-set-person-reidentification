"""
Zip the demo pack so it can be e-mailed or copied to a USB stick.

In plain words: collects the printable documents, the sample pictures with their licence record, the reference outputs, the screenshots
and the demo scripts into ONE file, ``OpenID-Vision-Demo-Pack.zip`` (next to the project folder's README), with a short START_HERE.txt.
Generated scratch (``demo/output_latest``, ``demo/_build``, caches) is left out.

    python scripts/make_demo_zip.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "OpenID-Vision-Demo-Pack.zip"
SKIP = {"output_latest", "_build", "__pycache__"}
EXTRA_DOCS = ["JURY_GUIDE.md", "FACE_AND_BODY_MATCHING.md", "OPEN_SET_EXAMPLE.md", "SECURITY_AND_PRIVACY.md"]

START_HERE = """OpenID Vision - demo pack
=========================

Know when to match. Know when to reject.

Open these first (in this order):
  0. OpenID-Vision-User-Manual.pdf   HOW TO USE THE WEBSITE, step by step, with pictures (start here if you will operate it)
  1. demo/DEMO_GUIDE.pdf   how to run the system, how to read each screen, every scenario with its real output
  2. demo/JURY_DECK.pdf    15 slides for a presentation
  3. demo/JURY_GUIDE.pdf   what to say, a click-by-click demo, numbers you may and may not quote, 32 questions with honest answers

What is in the pack:
  demo/samples/            pictures and clips with known right answers (public domain / CC0; SOURCES.md has every author and licence)
  demo/expected_output/    the real results of a reference run
  demo/screenshots/        real screenshots of the interface
  demo/*.py                run_demo.py runs every scenario against a running server; run_open_set_example.py runs the home-page example; face_check.py tests your own volunteers' photos
  docs/results/            the raw measurements behind every number (LFW face benchmark; face + body comparison; the home-page example)
  docs/                    the written explanations (face and body matching, the home-page example, privacy)

To RUN the system you also need the full project folder (the code and the models); see demo/README.md.
To just READ and PRESENT, the three PDFs are enough.

Important honesty notes
  * Not a phone's Face ID: 2-D photo matching, no depth sensor, no liveness check.
  * Face accuracy was measured on the standard LFW benchmark (98.9 %) - an easy test - plus a small end-to-end check.
  * The pedestrian re-identification benchmark (Market-1501) has NOT been run.
  * Thresholds are evidence-based defaults, unvalidated for any specific camera.
  * Face fingerprints are biometric data: use only consenting volunteers.
"""


def main() -> int:
    count = 0
    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        bundle.writestr("START_HERE.txt", START_HERE.replace("\n", "\r\n"))
        for name in ("OpenID-Vision-User-Manual.pdf", "Start OpenID Vision.bat"):
            if (ROOT / name).is_file():
                bundle.write(ROOT / name, name)
                count += 1
        for path in sorted((ROOT / "demo").rglob("*")):
            if path.is_file() and not (set(path.relative_to(ROOT).parts) & SKIP) and path.suffix != ".pyc":
                bundle.write(path, path.relative_to(ROOT).as_posix())
                count += 1
        for path in sorted((ROOT / "docs" / "results").glob("*.json")):
            bundle.write(path, path.relative_to(ROOT).as_posix())
            count += 1
        for name in EXTRA_DOCS:
            bundle.write(ROOT / "docs" / name, f"docs/{name}")
            count += 1
    print(f"wrote {TARGET.name}: {count} files, {TARGET.stat().st_size / 2**20:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
