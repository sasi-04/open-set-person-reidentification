"""
Create your local ``.env`` file.

In plain words: this script copies ``.env.example`` to ``.env`` and replaces the
placeholder access keys with random ones. Access keys are OFF by default
(``REID_AUTH_REQUIRED=false``), so you never need them on your own machine; they
are generated now only so that switching them on later is a one-line change. The
real ``.env`` is git-ignored, so the keys never leave your computer, and they are
not printed. It will not overwrite an existing ``.env`` unless you pass ``--force``.

    python scripts/init_env.py
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDERS = ("replace-me-viewer", "replace-me-operator", "replace-me-admin")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="overwrite an existing .env")
    args = parser.parse_args()

    source, target = REPO_ROOT / ".env.example", REPO_ROOT / ".env"
    if target.exists() and not args.force:
        print(f"{target} already exists - leaving it alone (use --force to regenerate it).")
        return 0

    text = source.read_text(encoding="utf-8")
    for placeholder in PLACEHOLDERS:
        text = text.replace(placeholder, secrets.token_urlsafe(24))
    target.write_text(text, encoding="utf-8")

    print(f"Wrote {target}")
    print("Access keys are OFF (REID_AUTH_REQUIRED=false): no key is needed to open the app.")
    print("To require keys, set REID_AUTH_REQUIRED=true in .env; the keys it would use are already in that file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
