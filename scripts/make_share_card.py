"""Render scripts/share_card.html to static/share-card.png (1200x630) with a local headless Edge or Chrome.

Run from the repository root: .venv/Scripts/python scripts/make_share_card.py [source.html] [target.png]
The wordmark comes from templates/_brand.svg so the card always matches the masthead.
The PNG is committed; the site build only copies it.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "share_card.html"
TARGET = ROOT / "static" / "share-card.png"
BRAND = ROOT / "templates" / "_brand.svg"
PLACEHOLDER = "<!-- brand: templates/_brand.svg -->"
CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "msedge",
    "google-chrome",
    "chromium",
)


def browser():
    for candidate in CANDIDATES:
        found = candidate if Path(candidate).exists() else shutil.which(candidate)
        if found:
            return found
    sys.exit("No Edge or Chrome found; install one or add it to PATH.")


def main(source=SOURCE, target=TARGET):
    source, target = Path(source).resolve(), Path(target).resolve()
    html = source.read_text(encoding="utf-8")
    if PLACEHOLDER not in html:
        sys.exit(f"{source.name} is missing the {PLACEHOLDER} placeholder.")
    target.unlink(missing_ok=True)
    # A throwaway profile keeps the browser from handing the job to an already-open window.
    profile = tempfile.mkdtemp(prefix="share-card-")
    page = Path(profile) / "card.html"
    page.write_text(html.replace(PLACEHOLDER, BRAND.read_text(encoding="utf-8")), encoding="utf-8")
    subprocess.run(
        [
            browser(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
            f"--user-data-dir={profile}", "--no-first-run",
            "--window-size=1200,630", "--virtual-time-budget=10000",
            f"--screenshot={target}", page.as_uri(),
        ],
        check=True,
        timeout=120,
    )
    # On Windows the launcher can return before the headless process writes the file.
    deadline = time.monotonic() + 60
    while not (target.exists() and target.stat().st_size) and time.monotonic() < deadline:
        time.sleep(1)
    time.sleep(1)
    shutil.rmtree(profile, ignore_errors=True)
    if not target.exists():
        sys.exit("The browser did not write the screenshot within 60 seconds.")
    with open(target, "rb") as handle:
        header = handle.read(24)
    size = (int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big"))
    if size != (1200, 630):
        sys.exit(f"Expected 1200x630, got {size[0]}x{size[1]}")
    print(f"Wrote {target} (1200x630)")


if __name__ == "__main__":
    main(*sys.argv[1:3])
