"""Build the site, open a week page in headless Edge/Chrome and check the explorer. Run: python scripts/check_explorer.py

The committed real editions are schema 1 (key moments only, no full play-by-play diagrams). If the
real build has no week page with recorded plays, this falls back to building from the Week 2 test
fixture (schema 2, with diagrams) so the check actually exercises the explorer.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from scripts.make_share_card import browser  # noqa: E402
from src import site  # noqa: E402
from src.edition import load_registry  # noqa: E402


def dump(url):
    result = subprocess.run([browser(), "--headless=new", "--disable-gpu", f"--user-data-dir={tempfile.mkdtemp()}",
                             "--virtual-time-budget=5000", "--dump-dom", url], capture_output=True,
                             encoding="utf-8", errors="replace", timeout=120)
    return result.stdout


def build_real():
    out = Path(tempfile.mkdtemp()) / "site"
    site.build_site(out)
    for page in out.glob("players/*/*/index.html"):
        if 'id="play-' in page.read_text(encoding="utf-8"):
            return page
    return None


def build_from_fixture():
    import fixture_data

    tmp = Path(tempfile.mkdtemp())
    editions_root = tmp / "editions"
    fixture_data.write_edition_dir(editions_root, fixture_data.golden_edition())
    out = tmp / "site"
    site.build_site(out, editions_root, registry=load_registry(fixture_data.FIXTURES / "alumni.json"))
    for page in out.glob("players/*/*/index.html"):
        if 'id="play-' in page.read_text(encoding="utf-8"):
            return page
    sys.exit("No player week page with plays found in the fixture build either.")


def main():
    page = build_real()
    source = "real editions"
    if page is None:
        page = build_from_fixture()
        source = "Week 2 test fixture"
    print(f"Using {source}: {page}")
    text = page.read_text(encoding="utf-8")
    first = text.split('id="play-')[2].split('"')[0]
    dom = dump(page.as_uri() + f"#play-{first}")
    if not dom.strip():
        dom = dump(page.as_uri() + f"#play-{first}")  # Windows launcher can return before output is ready
    filters = dom.split('class="explorer-filters"')[1].split(">")[0] if 'class="explorer-filters"' in dom else "hidden"
    stage = dom.split('id="play-stage"')[1].split("</div>")[0] if 'id="play-stage"' in dom else ""
    selected = dom.split(f'id="play-{first}"')[1].split(">")[0] if f'id="play-{first}"' in dom else ""
    checks = {
        "filters shown": "hidden" not in filters,
        "stage filled": "<svg" in stage or bool(stage.split(">", 1)[-1].strip()),
        "fragment selected": 'aria-current="true"' in selected,
    }
    for name, ok in checks.items():
        print(("ok   " if ok else "FAIL ") + name)
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
