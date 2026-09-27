"""Build _site from the Week 2 test fixture so the design can be checked in a browser."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import editorial  # noqa: E402
from src.site import build_site  # noqa: E402


def main():
    fixture = ROOT / "tests" / "fixtures" / "week02"
    edition = json.loads((fixture / "expected_edition.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / edition["id"]
        target.mkdir()
        (target / "edition.json").write_text(json.dumps(edition), encoding="utf-8")
        (target / "sources.json").write_text((fixture / "manifest.json").read_text(encoding="utf-8"), encoding="utf-8")
        (target / "editorial.toml").write_text(editorial.dumps(editorial.fallback(edition)), encoding="utf-8")
        written = build_site(ROOT / "_site", Path(tmp))
    print(f"Preview: {len(written)} pages in _site")


if __name__ == "__main__":
    main()
