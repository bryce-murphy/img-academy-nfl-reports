"""Build the site, open a week page in headless Edge/Chrome and check the explorer.

Run: python scripts/check_explorer.py [--fixture]

The committed real editions are schema 1 (key moments only, no full play-by-play diagrams). If the
real build has no week page with recorded plays, this falls back to building from the Week 2 test
fixture (schema 2, with diagrams) so the check actually exercises the explorer. Pass --fixture to
force the fixture build (schema 2, real <svg> diagrams) even when a real edition would qualify.
"""
import re
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


def first_play_id(text):
    ids = [m for m in re.findall(r'id="play-([^"]+)"', text) if m != "stage"]
    return ids[0] if ids else None


def first_play_has_svg(text):
    play_id = first_play_id(text)
    if play_id is None:
        return False
    block = re.search(r'<li class="play[^"]*" id="play-' + re.escape(play_id) + r'".*?</li>', text, re.S)
    return bool(block) and 'template class="play-large"' in block.group(0)


def best_page(pages):
    """Prefer a page whose first play has a large diagram, so the default selection exercises
    the template.play-large branch; fall back to any page with plays."""
    with_svg, any_plays = None, None
    for page in pages:
        text = page.read_text(encoding="utf-8")
        if 'id="play-' not in text:
            continue
        any_plays = any_plays or page
        if with_svg is None and first_play_has_svg(text):
            with_svg = page
    return with_svg or any_plays


def build_real():
    out = Path(tempfile.mkdtemp()) / "site"
    site.build_site(out)
    return best_page(sorted(out.glob("players/*/*/index.html")))


def build_from_fixture():
    import fixture_data

    tmp = Path(tempfile.mkdtemp())
    editions_root = tmp / "editions"
    fixture_data.write_edition_dir(editions_root, fixture_data.golden_edition())
    out = tmp / "site"
    site.build_site(out, editions_root, registry=load_registry(fixture_data.FIXTURES / "alumni.json"))
    page = best_page(sorted(out.glob("players/*/*/index.html")))
    if page is None:
        sys.exit("No player week page with plays found in the fixture build either.")
    return page


def dump_with_retry(url):
    dom = dump(url)
    if not dom.strip():
        dom = dump(url)  # Windows launcher can return before output is ready
    return dom


def selected_tag(dom, play_id):
    marker = f'id="play-{play_id}"'
    return dom.split(marker)[1].split(">")[0] if marker in dom else ""


def main():
    use_fixture = "--fixture" in sys.argv[1:]
    if use_fixture:
        page = build_from_fixture()
        source = "Week 2 test fixture (--fixture)"
    else:
        page = build_real()
        source = "real editions"
        if page is None:
            page = build_from_fixture()
            source = "Week 2 test fixture (no real edition had plays)"
    print(f"Using {source}: {page}")
    text = page.read_text(encoding="utf-8")
    ids = [m for m in re.findall(r'id="play-([^"]+)"', text) if m != "stage"]
    first = ids[0]

    dom = dump_with_retry(page.as_uri() + f"#play-{first}")
    filters = dom.split('class="explorer-filters"')[1].split(">")[0] if 'class="explorer-filters"' in dom else "hidden"
    stage = dom.split('id="play-stage"')[1].split("</div>")[0] if 'id="play-stage"' in dom else ""
    selected = selected_tag(dom, first)
    checks = {
        "filters shown": "hidden" not in filters,
        "stage filled": "<svg" in stage or bool(stage.split(">", 1)[-1].strip()),
        "fragment selected": 'aria-current="true"' in selected,
    }

    if len(ids) > 1:
        second = ids[1]
        dom2 = dump_with_retry(page.as_uri() + f"#play-{second}")
        selected_first_in_dom2 = selected_tag(dom2, first)
        selected_second_in_dom2 = selected_tag(dom2, second)
        checks["non-first fragment selected"] = 'aria-current="true"' in selected_second_in_dom2
        checks["non-first fragment deselects the first"] = 'aria-current="true"' not in selected_first_in_dom2
    else:
        print("(only one play on this page; skipping the non-first fragment check)")

    for name, ok in checks.items():
        print(("ok   " if ok else "FAIL ") + name)
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
