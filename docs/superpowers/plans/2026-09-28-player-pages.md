# Player Pages and Play Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every IMG Academy alum an evergreen page and permanent week pages with an explorer of every recorded play drawn on a simple field, plus a field strip on each homepage card.

**Architecture:** Editions gain an additive `plays` list and snap/usage denominators (schema 2). A pure `src/field.py` decides which plays get a diagram and renders inline SVG. A pure `src/players.py` builds slugs, game logs and season lines from published editions. `src/site.py` renders `/players/`, `/players/<slug>/` and `/players/<slug>/<edition-id>/`; `static/explorer.js` only adds selection and filtering.

**Tech Stack:** Python 3.12, Jinja2 (autoescape, StrictUndefined), stdlib `unittest`, vanilla JavaScript, headless Edge/Chrome for one browser check. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-28-player-pages-design.md` (read it with this plan).

## Global Constraints

- Run everything from the repository root with `.venv/Scripts/python` on Windows (`python` in CI). Local pip needs `PIP_CERT=/c/ProgramData/Norton/Antivirus/wscert.pem`.
- Test command: `.venv/Scripts/python -m unittest discover -s tests` (must stay silent on stdout).
- Public copy says "IMG Academy" in full, never "IMG" alone; never "not affiliated"; coverage is "charted in coverage", never "allowed"; receiver EPA is "team expected points when targeted".
- Missing values are `null`/`None`, never zero. A blank is never a zero anywhere in data, season lines or diagrams.
- Diagram eligibility order (spec §5): text only for `no_play`, kickoff, punt, field_goal, extra_point, or when `penalty`, `fumble`, `interception`, `lateral_reception`, `lateral_rush`, `qb_kneel`, `qb_spike`, `two_point_attempt` is 1, `yardline_100` outside 1–99, `yards_gained` missing, `ydstogo` missing or outside 1–99; else sack → run → completed pass → incomplete pass; else text only.
- Offense always drawn left to right; `x = 100 - yardline_100`; display domain −10…110.
- Season shares are Σ player / Σ team; CPOE is `100 × Σ(complete_pass − cp) / count` over passer rows with non-null `cp`.
- Rate thresholds: QB 50 dropbacks (CPOE: 50 rows with `cp`); RB 30 carries; WR/TE 15 targets; defense impact plays per 100 snaps from 100 defensive snaps; coverage, pressure, tackling and OL stay counts.
- Filters: "All plays", "Impact plays", "Positive plays for the <nickname>", "Negative plays for the <nickname>"; note "Expected points describe the whole play, not the player named on it."
- `key_plays` in `edition.json` stays exactly as today (list of play dicts). `plays` is additive.
- Every commit is SSH-signed (`git commit -S`), ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; `main` changes only through squash-merged PRs the owner approves. Push with `git -c credential.helper= -c "credential.helper=!gh auth git-credential" push`.
- Team snap denominators: the most snaps any player on that team played in that phase of that game (from the game's snap table). This replaces spec §7.1's division by `*_pct`, which cannot recover whole numbers from two-decimal percentages; Task 4 updates the spec text.

## Review Focus

1. **A player traded mid-season:** the evergreen header shows his latest team, the game log shows each week's team, and season lines sum across both teams. Pinned in Task 7.
2. **A registry player missing from older editions (added mid-season):** his pages build with only the weeks he appears in; nothing crashes. Pinned in Task 8.
3. **A played lineman with zero recorded plays:** the week page shows snaps and the lineman caveat, an empty "Recorded plays (0)", no strip and no empty diagram. Pinned in Tasks 8 and 10.
4. **A play without EPA:** listed under "All plays" only, no outcome line, never counted as positive or negative. Pinned in Tasks 8 and 9.
5. **Schema-1 editions (published before this work):** evergreen and week pages render from `key_plays` alone, with "Recorded plays" showing the key moments and a note that the full list was not saved for that week. Pinned in Task 8.

---

## PR 1: Data contract (Tasks 1–4)

Branch: `feat/player-data`. After Task 4, open the PR "Player pages, part 1: edition data for player pages". Nothing on the site changes.

### Task 1: Permanent player addresses (slugs)

**Files:**
- Create: `src/players.py`
- Modify: `src/edition.py:52-57` (`load_registry`)
- Modify: `data/alumni.json`, `tests/fixtures/week02/alumni.json` (add `slug`)
- Test: `tests/test_players.py` (new)

**Interfaces:**
- Produces: `players.slugify(name: str) -> str`; `players.assign_slugs(registry: list[dict]) -> list[dict]` (returns copies with `slug` set where missing, collision-safe); `SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")`. `edition.load_registry` raises `DataError` for a missing, malformed or duplicate slug.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_players.py
import json
import tempfile
import unittest
from pathlib import Path

from src import players
from src.edition import load_registry
from src.errors import DataError


class SlugTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(players.slugify("Grant Delpit"), "grant-delpit")
        self.assertEqual(players.slugify("J.J. McCarthy"), "jj-mccarthy")
        self.assertEqual(players.slugify("DJ Turner II"), "dj-turner-ii")
        self.assertEqual(players.slugify("Hjalte Frøholdt"), "hjalte-frholdt")

    def test_assign_slugs_resolves_collisions_with_the_gsis_suffix(self):
        registry = [{"name": "Chris Smith", "gsis_id": "00-0031111"}, {"name": "Chris Smith", "gsis_id": "00-0042222"}]
        self.assertEqual([a["slug"] for a in players.assign_slugs(registry)], ["chris-smith", "chris-smith-2222"])

    def test_existing_slugs_are_kept(self):
        registry = [{"name": "Grant Delpit", "gsis_id": "00-0036282", "slug": "grant-delpit"}]
        self.assertEqual(players.assign_slugs(registry)[0]["slug"], "grant-delpit")

    def test_registry_requires_valid_unique_slugs(self):
        good = {"name": "A B", "gsis_id": "00-0000001", "slug": "a-b", "source_url": "https://x"}
        for bad in ({**good, "slug": ""}, {**good, "slug": "A B"}):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "alumni.json"
                path.write_text(json.dumps([bad]), encoding="utf-8")
                with self.assertRaises(DataError):
                    load_registry(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "alumni.json"
            path.write_text(json.dumps([good, {**good, "gsis_id": "00-0000002"}]), encoding="utf-8")
            with self.assertRaises(DataError):
                load_registry(path)

    def test_the_real_registries_have_slugs(self):
        for path in (Path("data/alumni.json"), Path("tests/fixtures/week02/alumni.json")):
            registry = load_registry(path)
            self.assertTrue(all(a["slug"] == players.slugify(a["name"]) or a["slug"].startswith(players.slugify(a["name"]) + "-") for a in registry))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m unittest discover -s tests -p test_players.py`
Expected: ERROR `No module named 'src.players'` (or `cannot import name 'players'`).

- [ ] **Step 3: Implement `src/players.py` and registry validation**

```python
# src/players.py
"""Player pages: addresses, game logs and season lines. Pure functions over loaded editions."""
from __future__ import annotations

import re
import unicodedata

SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def slugify(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.replace(".", "").lower()).strip("-")


def assign_slugs(registry):
    """Copies of registry entries with `slug` set; a repeated slug gets the last four digits of the GSIS id."""
    taken, out = set(), []
    for alum in registry:
        slug = alum.get("slug") or slugify(alum["name"])
        if slug in taken:
            slug = f"{slug}-{alum['gsis_id'][-4:]}"
        taken.add(slug)
        out.append(dict(alum, slug=slug))
    return out
```

In `src/edition.py` `load_registry`, after the id check add:

```python
    slugs = [a.get("slug", "") for a in registry]
    if not all(SLUG.fullmatch(s or "") for s in slugs) or len(slugs) != len(set(slugs)):
        raise DataError("Every alumni entry needs a unique lowercase slug")
```

and at the top of `src/edition.py`: `from .players import SLUG`.

- [ ] **Step 4: Add slugs to both registries**

Run (writes `slug` right after `name`, keeping 2-space JSON and LF):

```bash
.venv/Scripts/python - <<'EOF'
import json
from pathlib import Path
from src.players import assign_slugs
for path in (Path("data/alumni.json"), Path("tests/fixtures/week02/alumni.json")):
    registry = json.loads(path.read_text(encoding="utf-8"))
    ordered = [{"name": a["name"], "slug": a["slug"], **{k: v for k, v in a.items() if k not in ("name", "slug")}} for a in assign_slugs(registry)]
    path.write_bytes((json.dumps(ordered, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
EOF
git diff --stat data/alumni.json tests/fixtures/week02/alumni.json
```

Expected: one added line per entry in each file.

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m unittest discover -s tests`
Expected: OK (the golden edition test is unaffected: slugs are not in `edition.json`).

- [ ] **Step 6: Commit**

```bash
git add src/players.py src/edition.py data/alumni.json tests/fixtures/week02/alumni.json tests/test_players.py
git commit -S -m "Give every alum a permanent page address" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: Columns the pages need, validated at download, plus edge-case plays

**Files:**
- Modify: `src/data.py` (`specifications`: pbp, stats, snaps required columns)
- Modify: `scripts/make_fixtures.py` (`PBP_BASE`)
- Modify: `tests/fixtures/week02/pbp.csv` (new columns joined from the real file)
- Create: `scripts/make_edge_cases.py`, `tests/fixtures/pbp_edge_cases.csv`
- Test: `tests/test_data.py`, `tests/test_fixtures.py`

**Interfaces:**
- Produces: `data.PLAY_COLUMNS` (tuple of the pbp columns player pages consume, below); `tests/fixtures/pbp_edge_cases.csv` with a `case` column naming each row: `interception`, `lost_fumble`, `lateral`, `penalty`, `goal_line_td`, `sack`, `completion`, `incompletion`, `run_loss`, `kneel`, `two_point`, `punt`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_data.py (add)
from src.data import PLAY_COLUMNS

class PlayColumnTests(unittest.TestCase):
    def test_pbp_requires_every_column_player_pages_read(self):
        self.assertTrue(set(PLAY_COLUMNS) <= specifications(2026)["pbp"][2])

    def test_stats_and_snaps_require_usage_and_snap_columns(self):
        self.assertTrue({"targets", "target_share", "receiving_air_yards", "air_yards_share"} <= specifications(2026)["stats"][2])
        self.assertTrue({"team", "offense_snaps", "defense_snaps", "st_snaps"} <= specifications(2026)["snaps"][2])
```

```python
# tests/test_fixtures.py (add)
import csv
from src.data import PLAY_COLUMNS

class EdgeCaseFixtureTests(unittest.TestCase):
    def test_pbp_fixture_has_every_play_column(self):
        with open(fixture_data.FIXTURES / "pbp.csv", encoding="utf-8") as handle:
            self.assertTrue(set(PLAY_COLUMNS) <= set(csv.DictReader(handle).fieldnames))

    def test_edge_case_file_has_one_real_row_per_case(self):
        with open(fixture_data.FIXTURES.parent / "pbp_edge_cases.csv", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(sorted(r["case"] for r in rows), sorted([
            "interception", "lost_fumble", "lateral", "penalty", "goal_line_td", "sack",
            "completion", "incompletion", "run_loss", "kneel", "two_point", "punt"]))
        self.assertTrue(all(set(PLAY_COLUMNS) <= set(r) for r in rows))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_[df]*.py"`
Expected: ImportError `cannot import name 'PLAY_COLUMNS'`.

- [ ] **Step 3: Add `PLAY_COLUMNS` and required columns in `src/data.py`**

```python
PLAY_COLUMNS = (
    "posteam", "defteam", "down", "ydstogo", "goal_to_go", "yardline_100", "yards_gained", "air_yards",
    "yards_after_catch", "pass_attempt", "rush_attempt", "complete_pass", "sack", "interception", "fumble",
    "lateral_reception", "lateral_rush", "penalty", "qb_kneel", "qb_spike", "two_point_attempt", "cp",
    "qb_dropback", "qb_epa", "play_deleted", "aborted_play",
)
```

In `specifications`: pbp required set becomes `{"game_id", "play_id", "week", "desc", "epa", "wpa", *PLAY_COLUMNS}`; stats adds `"targets", "target_share", "receiving_air_yards", "air_yards_share"`; snaps adds `"team"`.

- [ ] **Step 4: Extend the fixture pbp and `make_fixtures.py`**

Append the `PLAY_COLUMNS` entries not already present to `PBP_BASE` in `scripts/make_fixtures.py`. Then join the new columns into the existing fixture rows (network; keeps every existing cell):

```bash
.venv/Scripts/python - <<'EOF'
import csv
from pathlib import Path
from src.data import PLAY_COLUMNS, load_sources
data, _, _ = load_sources(2026, ".cache", historical=True, only={"pbp"}, week=2)
full = {(r["game_id"], str(int(float(r["play_id"])))): r for r in data["pbp"]}
path = Path("tests/fixtures/week02/pbp.csv")
rows = list(csv.DictReader(path.open(encoding="utf-8")))
cols = list(rows[0])
new = [c for c in PLAY_COLUMNS if c not in cols]
base_end = cols.index("interception") + 1
out = cols[:base_end] + new + cols[base_end:]
for r in rows:
    src = full[(r["game_id"], str(int(float(r["play_id"]))))]
    assert all(src[c] == r[c] for c in ("epa", "desc")), r["play_id"]
    r.update({c: src[c] for c in new})
with path.open("w", encoding="utf-8", newline="") as h:
    w = csv.DictWriter(h, fieldnames=out, lineterminator="\n"); w.writeheader(); w.writerows(rows)
print("added", new)
EOF
```

- [ ] **Step 5: Create the edge-case fixture**

```python
# scripts/make_edge_cases.py
"""Write tests/fixtures/pbp_edge_cases.csv: one real 2026 play per diagram edge case (network)."""
import csv
from pathlib import Path

from src.data import PLAY_COLUMNS, load_sources

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "interception": lambda r: r["interception"] == "1",
    "lost_fumble": lambda r: r["fumble_lost"] == "1",
    "lateral": lambda r: "1" in (r["lateral_reception"], r["lateral_rush"]),
    "penalty": lambda r: r["penalty"] == "1" and r["play_type"] != "no_play",
    "goal_line_td": lambda r: r["touchdown"] == "1" and r["rush_attempt"] == "1" and r["yardline_100"] in ("1", "2", "3"),
    "sack": lambda r: r["sack"] == "1",
    "completion": lambda r: r["complete_pass"] == "1" and r["air_yards"] not in ("", "NA") and r["fumble"] == "0",
    "incompletion": lambda r: r["pass_attempt"] == "1" and r["complete_pass"] == "0" and r["interception"] == "0" and r["sack"] == "0",
    "run_loss": lambda r: r["rush_attempt"] == "1" and r["yards_gained"].startswith("-") and r["fumble"] == "0",
    "kneel": lambda r: r["qb_kneel"] == "1",
    "two_point": lambda r: r["two_point_attempt"] == "1",
    "punt": lambda r: r["play_type"] == "punt",
}


def main():
    data, _, _ = load_sources(2026, ROOT / ".cache", historical=True, only={"pbp"})
    rows = []
    for case, test in CASES.items():
        match = next((r for r in data["pbp"] if test(r)), None)
        if match is None:
            raise SystemExit(f"No 2026 play found for {case}")
        rows.append({"case": case, **match})
    columns = ["case", "game_id", "play_id", "week", "desc", "epa", "play_type", "touchdown", "fumble_lost", *PLAY_COLUMNS]
    with (ROOT / "tests" / "fixtures" / "pbp_edge_cases.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} edge cases")


if __name__ == "__main__":
    main()
```

Run: `.venv/Scripts/python scripts/make_edge_cases.py` → `Wrote 12 edge cases`.

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python -m unittest discover -s tests`
Expected: OK. If the golden test changes, stop: new columns must not change `edition.json` yet.

- [ ] **Step 7: Commit**

```bash
git add src/data.py scripts/make_fixtures.py scripts/make_edge_cases.py tests/fixtures/week02/pbp.csv tests/fixtures/pbp_edge_cases.csv tests/test_data.py tests/test_fixtures.py
git commit -S -m "Validate the play columns player pages read; add real edge-case plays" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: Every recorded play in the edition (schema 2)

**Files:**
- Modify: `src/evidence.py` (role allowlist, shared side/impact)
- Modify: `src/edition.py` (`SCHEMA_VERSION = 2`, `play_record`, `player_record` adds `plays`)
- Modify: `tests/fixtures/week02/expected_edition.json` (regenerate)
- Test: `tests/test_evidence.py`, `tests/test_edition.py`

**Interfaces:**
- Produces:
  - `ev.RECORDED_ROLES`: tuple of role names without `_player_id` (spec §4 list; `assist_tackle_1..4` expanded).
  - `ev.recorded_roles(play: dict, pid: str) -> list[str]`: matched role names in `RECORDED_ROLES` order.
  - `ev.side_and_impact(play: dict, pid: str, team: str) -> tuple[str, str | None]`: `("defense", "Sack")`, `("offense", "Touchdown")`, `("offense", None)`; `key_plays` uses it (behavior unchanged).
  - `edition.play_record(play: dict, pid: str, team: str, team_name) -> dict`: keys `play_id, quarter, clock, offense, defense, offense_name, defense_name, play_type, down, ydstogo, goal_to_go, yardline_100, yards_gained, air_yards, yards_after_catch, pass_attempt, rush_attempt, complete_pass, sack, interception, fumble, lateral, penalty, qb_kneel, qb_spike, two_point_attempt, cp, qb_dropback, qb_epa, epa, side, impact, roles, description`. Numbers are `int`/`float` or `None`; flags are `0`/`1` or `None`; `lateral` is 1 when either lateral flag is 1.
  - Each player dict in `edition.json` gains `plays: list[dict]` in play-id order (empty for players with no recorded plays).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_evidence.py (add)
class RecordedRoleTests(unittest.TestCase):
    def test_only_allowlisted_roles_count(self):
        play = {"solo_tackle_1_player_id": ME, "penalty_player_id": ME, "fantasy_player_id": ME, "lateral_receiver_player_id": ME}
        self.assertEqual(ev.recorded_roles(play, ME), ["solo_tackle_1"])

    def test_every_matched_role_is_kept_in_order(self):
        play = {"sack_player_id": ME, "forced_fumble_player_1_player_id": ME, "qb_hit_1_player_id": ME}
        self.assertEqual(ev.recorded_roles(play, ME), ["sack", "qb_hit_1", "forced_fumble_player_1"])

    def test_side_and_impact_match_key_plays(self):
        self.assertEqual(ev.side_and_impact(play(1, -1.8, sack_player_id=True), ME, "CLE"), ("defense", "Sack"))
        self.assertEqual(ev.side_and_impact(play(2, 3.1, posteam="CLE", defteam="TB", td_player_id=True), ME, "CLE"), ("offense", "Touchdown"))
```

```python
# tests/test_edition.py (add)
class PlaysTests(unittest.TestCase):
    def test_every_recorded_play_is_saved_with_field_details(self):
        tate = player(build(), "Carnell Tate")
        self.assertEqual(len(tate["plays"]), 5)
        first = tate["plays"][0]
        for key in ("down", "ydstogo", "yardline_100", "yards_gained", "air_yards", "complete_pass", "roles", "side", "offense_name"):
            self.assertIn(key, first)
        self.assertEqual(first["roles"], ["receiver"])
        self.assertEqual([p["play_id"] for p in tate["plays"]], sorted((p["play_id"] for p in tate["plays"]), key=float))

    def test_key_plays_are_among_plays_and_unchanged(self):
        edition = build()
        for p in edition["players"]:
            ids = {q["play_id"] for q in p["plays"]}
            self.assertTrue({k["play_id"] for k in p["key_plays"]} <= ids, p["name"])

    def test_blank_cells_stay_null(self):
        record = ed.play_record({"play_id": "7", "epa": "NA", "air_yards": "", "posteam": "CLE", "defteam": "TB", "desc": "x", "qtr": "1", "time": "15:00", "solo_tackle_1_player_id": "00-1"}, "00-1", "TB", lambda t: t)
        self.assertIsNone(record["epa"])
        self.assertIsNone(record["air_yards"])
        self.assertIsNone(record["sack"])

    def test_schema_version_is_two(self):
        self.assertEqual(build()["schema_version"], 2)

    def test_a_player_without_recorded_plays_has_an_empty_list(self):
        self.assertEqual(player(build(), "Tyler Booker")["plays"], [])
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_e[dv]*.py"`
Expected: failures/errors for the new tests only.

- [ ] **Step 3: Implement in `src/evidence.py`**

Add after `TACKLE_ROLES`:

```python
RECORDED_ROLES = (
    "passer", "rusher", "receiver", "td_player", "interception", "sack", "half_sack_1", "half_sack_2",
    "qb_hit_1", "qb_hit_2", "tackle_for_loss_1", "tackle_for_loss_2", "forced_fumble_player_1",
    "forced_fumble_player_2", "fumble_recovery_1", "fumble_recovery_2", "fumbled_1", "fumbled_2",
    "pass_defense_1", "pass_defense_2", "solo_tackle_1", "solo_tackle_2", "assist_tackle_1", "assist_tackle_2",
    "assist_tackle_3", "assist_tackle_4", "tackle_with_assist_1", "tackle_with_assist_2", "safety",
    "punt_returner", "kickoff_returner", "punter", "kicker", "blocked",
)


def recorded_roles(play, pid):
    """Roles in which the play-by-play names this player (player pages' 'recorded plays')."""
    return [role for role in RECORDED_ROLES if play.get(f"{role}_player_id") == pid]


def side_and_impact(play, pid, team):
    if play.get("defteam") == team:
        return "defense", _defensive_impact(play, pid)[1]
    return "offense", "Touchdown" if play.get("td_player_id") == pid else None
```

In `key_plays`, replace the two branches' impact computation with `side, impact = side_and_impact(play, pid, team)`; keep the tier logic (`rank_` from `_defensive_impact` for defense). The golden file must not change in this step.

- [ ] **Step 4: Implement in `src/edition.py`**

```python
SCHEMA_VERSION = 2
_INTS = ("down", "ydstogo", "yardline_100", "yards_gained", "air_yards", "yards_after_catch")
_FLAGS = ("goal_to_go", "pass_attempt", "rush_attempt", "complete_pass", "sack", "interception", "fumble",
          "penalty", "qb_kneel", "qb_spike", "two_point_attempt", "qb_dropback")


def _int_or_none(value):
    number = ev.num(value)
    return int(number) if number is not None else None


def _flag_or_none(value):
    number = ev.num(value)
    return None if number is None else int(number == 1)


def _round_or_none(value, digits):
    number = ev.num(value)
    return round(number, digits) if number is not None else None


def play_record(play, pid, team, team_name):
    """One recorded play for player pages. Blank or NA cells stay None; flags are 0/1/None."""
    side, impact = ev.side_and_impact(play, pid, team)
    laterals = [_flag_or_none(play.get(k)) for k in ("lateral_reception", "lateral_rush")]
    return {
        "play_id": play_key(play["play_id"]),
        "quarter": ev.quarter_label(play.get("qtr")),
        "clock": play.get("time", ""),
        "offense": play.get("posteam", ""),
        "defense": play.get("defteam", ""),
        "offense_name": team_name(play.get("posteam", "")),
        "defense_name": team_name(play.get("defteam", "")),
        "play_type": play.get("play_type", ""),
        **{k: _int_or_none(play.get(k)) for k in _INTS},
        **{k: _flag_or_none(play.get(k)) for k in _FLAGS},
        "lateral": 1 if 1 in laterals else (0 if 0 in laterals else None),
        "cp": _round_or_none(play.get("cp"), 3),
        "qb_epa": _round_or_none(play.get("qb_epa"), 3),
        "epa": _round_or_none(play.get("epa"), 2),
        "side": side,
        "impact": impact,
        "roles": ev.recorded_roles(play, pid),
        "description": play.get("desc", ""),
    }
```

In `player_record`, after `involvement` is computed:

```python
    recorded = [
        p for p in plays
        if p.get("play_type") not in {"", "no_play"} and p.get("play_deleted") != "1" and p.get("aborted_play") != "1"
        and ev.recorded_roles(p, pid)
    ]
    recorded.sort(key=lambda p: float(p["play_id"]))
```

and add to the returned dict (after `"key_plays"`): `"plays": [play_record(p, pid, team, wk.team_name) for p in recorded],`.

- [ ] **Step 5: Regenerate the golden file and review it**

```bash
UPDATE_GOLDEN=1 .venv/Scripts/python -m unittest discover -s tests -p test_edition.py
git diff --stat tests/fixtures/week02/expected_edition.json
.venv/Scripts/python -c "import json;e=json.load(open('tests/fixtures/week02/expected_edition.json',encoding='utf-8'));print(e['schema_version'],[(p['name'],len(p['plays'])) for p in e['players'] if p['plays']])"
```

Expected: schema 2; `key_plays` blocks unchanged in the diff; every played non-lineman has plays; Booker, Ruiz, Hainsey etc. have `[]`.

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python -m unittest discover -s tests`
Expected: OK. `test_site` still passes (site ignores `plays`).

- [ ] **Step 7: Commit**

```bash
git add src/evidence.py src/edition.py tests/test_evidence.py tests/test_edition.py tests/fixtures/week02/expected_edition.json
git commit -S -m "Save every recorded play in the edition (schema 2)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: Snap and usage denominators

**Files:**
- Modify: `src/edition.py` (`player_record` `snaps`, new `usage`)
- Modify: `docs/superpowers/specs/2026-09-28-player-pages-design.md` §7.1 (snap denominators wording)
- Modify: `tests/fixtures/week02/expected_edition.json`
- Test: `tests/test_edition.py`

**Interfaces:**
- Produces: player `snaps` gains `team_offense`, `team_defense`, `team_st` (int or None); new player key `usage`: `{"targets", "team_targets", "air_yards", "team_air_yards"}` (int or None). `edition.team_snaps(rows: list[dict], team: str) -> dict` and `edition.usage(stat: dict) -> dict` are pure helpers.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_edition.py (add)
class DenominatorTests(unittest.TestCase):
    def test_team_snaps_are_the_most_any_teammate_played(self):
        rows = [{"team": "CLE", "offense_snaps": "60", "defense_snaps": "0", "st_snaps": "3"},
                {"team": "CLE", "offense_snaps": "0", "defense_snaps": "65", "st_snaps": "22"},
                {"team": "TB", "offense_snaps": "70", "defense_snaps": "0", "st_snaps": "1"}]
        self.assertEqual(ed.team_snaps(rows, "CLE"), {"team_offense": 60, "team_defense": 65, "team_st": 22})
        self.assertEqual(ed.team_snaps([], "CLE"), {"team_offense": None, "team_defense": None, "team_st": None})

    def test_usage_recovers_team_totals_or_stays_null(self):
        self.assertEqual(ed.usage({"targets": "5", "target_share": "0.29411765", "receiving_air_yards": "50", "air_yards_share": "0.4385965"}),
                         {"targets": 5, "team_targets": 17, "air_yards": 50, "team_air_yards": 114})
        self.assertEqual(ed.usage({"targets": "5", "target_share": "0.3", "receiving_air_yards": "", "air_yards_share": "0"}),
                         {"targets": 5, "team_targets": None, "air_yards": None, "team_air_yards": None})
        self.assertEqual(ed.usage({}), {"targets": None, "team_targets": None, "air_yards": None, "team_air_yards": None})

    def test_edition_players_carry_denominators(self):
        delpit = player(build(), "Grant Delpit")
        self.assertEqual(delpit["snaps"]["defense"], 65)
        self.assertGreaterEqual(delpit["snaps"]["team_defense"], 65)
        self.assertIn("usage", delpit)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m unittest discover -s tests -p test_edition.py`
Expected: AttributeError `team_snaps`.

- [ ] **Step 3: Implement**

```python
def team_snaps(rows, team):
    """Team snaps per phase: the most any player on the team played in that phase of the game."""
    out = {}
    for phase, column in (("team_offense", "offense_snaps"), ("team_defense", "defense_snaps"), ("team_st", "st_snaps")):
        values = [ev.num(r.get(column)) for r in rows if r.get("team") == team]
        values = [v for v in values if v is not None]
        out[phase] = int(max(values)) if values and max(values) > 0 else None
    return out


def _whole(value, tolerance=0.05):
    return int(round(value)) if value is not None and abs(value - round(value)) <= tolerance else None


def usage(stat):
    targets, share = ev.num(stat.get("targets")), ev.num(stat.get("target_share"))
    air, air_share = ev.num(stat.get("receiving_air_yards")), ev.num(stat.get("air_yards_share"))
    return {
        "targets": int(targets) if targets is not None else None,
        "team_targets": _whole(targets / share) if targets is not None and share else None,
        "air_yards": int(air) if air is not None else None,
        "team_air_yards": _whole(air / air_share) if air is not None and air_share else None,
    }
```

In `player_record`: `"snaps": {...existing..., **team_snaps(wk.snaps_by_team.get((game.get("game_id"), team), []), team)},` and add `"usage": usage(stat),`.

- [ ] **Step 4: Update spec §7.1 wording**

Replace the `snaps` bullet in `docs/superpowers/specs/2026-09-28-player-pages-design.md` §7.1 with: "`snaps`: gains team denominators `team_offense`, `team_defense`, `team_st`: the most snaps any player on the team played in that phase of the game, from the game's snap table (dividing by two-decimal `*_pct` values cannot recover whole numbers). `null` when the team has no rows." and change the `usage` bullet's whole-number check to "within 0.05 of a whole number".

- [ ] **Step 5: Regenerate the golden file, run the suite, commit**

```bash
UPDATE_GOLDEN=1 .venv/Scripts/python -m unittest discover -s tests -p test_edition.py
.venv/Scripts/python -m unittest discover -s tests
git add src/edition.py tests/test_edition.py tests/fixtures/week02/expected_edition.json docs/superpowers/specs/2026-09-28-player-pages-design.md
git commit -S -m "Store team snap and target denominators for season shares" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Then push `feat/player-data`, run `src.site build --check`, and open PR 1.

## PR 2: Field diagram (Tasks 5–6)

Branch: `feat/field-diagram` from `main` after PR 1 merges. Open "Player pages, part 2: field diagrams" after Task 6.

### Task 5: Diagram eligibility and geometry

**Files:**
- Create: `src/field.py`
- Test: `tests/test_field.py` (new)

**Interfaces:**
- Consumes: play dicts shaped like `edition.play_record` (Task 3).
- Produces:
  - `field.kind(play: dict) -> str | None`: `"sack" | "run" | "complete" | "incomplete"` or `None` (text only).
  - `field.geometry(play: dict) -> dict | None`: `{"kind", "x0", "marker", "air_end" (None for runs/sacks), "end", "lo", "hi"}` in field yards (`x = 100 - yardline_100`), window `lo..hi` within −10..110.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_field.py
import csv
import unittest
from pathlib import Path

from src import field
from src.edition import play_record

EDGE = Path(__file__).parent / "fixtures" / "pbp_edge_cases.csv"


def base(**overrides):
    play = {"play_type": "run", "down": 1, "ydstogo": 10, "goal_to_go": 0, "yardline_100": 65, "yards_gained": 4,
            "air_yards": None, "yards_after_catch": None, "pass_attempt": 0, "rush_attempt": 1, "complete_pass": 0,
            "sack": 0, "interception": 0, "fumble": 0, "lateral": 0, "penalty": 0, "qb_kneel": 0, "qb_spike": 0,
            "two_point_attempt": 0}
    play.update(overrides)
    return play


def edge_cases():
    with EDGE.open(encoding="utf-8") as handle:
        # A dummy id that matches no cell: these rows only exercise the diagram rules.
        return {r["case"]: play_record(r, "00-0000000", r["defteam"], lambda t: t) for r in csv.DictReader(handle)}


class KindTests(unittest.TestCase):
    def test_text_only_reasons(self):
        for overrides in ({"play_type": "no_play"}, {"play_type": "punt"}, {"play_type": "kickoff"}, {"play_type": "field_goal"},
                          {"play_type": "extra_point"}, {"penalty": 1}, {"fumble": 1}, {"interception": 1}, {"lateral": 1},
                          {"qb_kneel": 1}, {"qb_spike": 1}, {"two_point_attempt": 1}, {"yardline_100": 0}, {"yardline_100": 100},
                          {"yardline_100": None}, {"yards_gained": None}, {"ydstogo": None}, {"ydstogo": 0}):
            with self.subTest(overrides=overrides):
                self.assertIsNone(field.kind(base(**overrides)))

    def test_precedence_sack_run_complete_incomplete(self):
        self.assertEqual(field.kind(base(play_type="pass", sack=1, rush_attempt=0, pass_attempt=1, yards_gained=-5)), "sack")
        self.assertEqual(field.kind(base()), "run")
        self.assertEqual(field.kind(base(play_type="pass", rush_attempt=0, pass_attempt=1, complete_pass=1, air_yards=8, yards_after_catch=6, yards_gained=14)), "complete")
        self.assertEqual(field.kind(base(play_type="pass", rush_attempt=0, pass_attempt=1, air_yards=12, yards_gained=0)), "incomplete")
        self.assertIsNone(field.kind(base(play_type="pass", rush_attempt=0, pass_attempt=1, air_yards=None, yards_gained=0)))

    def test_real_edge_cases(self):
        cases = edge_cases()
        for text_only in ("interception", "lost_fumble", "lateral", "penalty", "kneel", "two_point", "punt"):
            with self.subTest(case=text_only):
                self.assertIsNone(field.kind(cases[text_only]))
        self.assertEqual(field.kind(cases["sack"]), "sack")
        self.assertEqual(field.kind(cases["completion"]), "complete")
        self.assertEqual(field.kind(cases["incompletion"]), "incomplete")
        self.assertEqual(field.kind(cases["run_loss"]), "run")
        self.assertEqual(field.kind(cases["goal_line_td"]), "run")


class GeometryTests(unittest.TestCase):
    def test_run(self):
        g = field.geometry(base(yardline_100=65, ydstogo=10, yards_gained=4))
        self.assertEqual((g["x0"], g["marker"], g["end"], g["air_end"]), (35, 45, 39, None))

    def test_loss_and_sack_go_backward(self):
        self.assertEqual(field.geometry(base(yards_gained=-3))["end"], 32)
        self.assertEqual(field.geometry(base(play_type="pass", sack=1, rush_attempt=0, pass_attempt=1, yards_gained=-7))["end"], 28)

    def test_completion_has_air_and_after_catch(self):
        g = field.geometry(base(play_type="pass", rush_attempt=0, pass_attempt=1, complete_pass=1, yardline_100=50, air_yards=8, yards_after_catch=6, yards_gained=14))
        self.assertEqual((g["x0"], g["air_end"], g["end"]), (50, 58, 64))

    def test_incompletion_ends_at_the_target(self):
        g = field.geometry(base(play_type="pass", rush_attempt=0, pass_attempt=1, yardline_100=40, air_yards=15, yards_gained=0))
        self.assertEqual((g["air_end"], g["end"]), (75, 60))

    def test_goal_to_go_marker_is_the_goal_line_and_touchdown_ends_on_it(self):
        g = field.geometry(base(yardline_100=3, ydstogo=3, goal_to_go=1, yards_gained=3))
        self.assertEqual((g["marker"], g["end"]), (100, 100))

    def test_loss_into_own_end_zone(self):
        self.assertEqual(field.geometry(base(yardline_100=98, yards_gained=-4))["end"], -2)

    def test_window_is_at_least_thirty_yards_and_inside_the_domain(self):
        g = field.geometry(base(yardline_100=98, ydstogo=10, yards_gained=-4))
        self.assertGreaterEqual(g["hi"] - g["lo"], 30)
        self.assertGreaterEqual(g["lo"], -10)
        self.assertLessEqual(g["hi"], 110)

    def test_text_only_plays_have_no_geometry(self):
        self.assertIsNone(field.geometry(base(penalty=1)))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m unittest discover -s tests -p test_field.py`
Expected: ImportError `cannot import name 'field'`.

- [ ] **Step 3: Implement `src/field.py` geometry**

```python
"""Field diagrams for recorded plays: which plays get one, where the marks go, and the SVG.

Pure functions. The offense always moves left to right; x = 100 - yardline_100 (0 = the offense's goal line).
Only where a play started and ended is drawn; nothing about player movement is invented.
"""
from __future__ import annotations

SPECIAL_TEAMS = {"kickoff", "punt", "field_goal", "extra_point"}
TEXT_ONLY_FLAGS = ("penalty", "fumble", "interception", "lateral", "qb_kneel", "qb_spike", "two_point_attempt")
DOMAIN = (-10, 110)
MIN_WIDTH = 30


def kind(play):
    """'sack' | 'run' | 'complete' | 'incomplete', or None when the play is shown as text only."""
    if play.get("play_type") in SPECIAL_TEAMS | {"no_play", "", None}:
        return None
    if any(play.get(flag) == 1 for flag in TEXT_ONLY_FLAGS):
        return None
    spot, gained, to_go = play.get("yardline_100"), play.get("yards_gained"), play.get("ydstogo")
    if spot is None or not 1 <= spot <= 99 or gained is None or to_go is None or not 1 <= to_go <= 99:
        return None
    if play.get("sack") == 1:
        return "sack"
    if play.get("rush_attempt") == 1:
        return "run"
    if play.get("pass_attempt") == 1 and play.get("air_yards") is not None:
        return "complete" if play.get("complete_pass") == 1 else "incomplete"
    return None


def geometry(play):
    """Marks in field yards, or None for text-only plays."""
    shape = kind(play)
    if shape is None:
        return None
    x0 = 100 - play["yardline_100"]
    marker = 100 if play.get("goal_to_go") == 1 else min(x0 + play["ydstogo"], 100)
    end = x0 + play["yards_gained"]
    air_end = x0 + play["air_yards"] if shape in ("complete", "incomplete") else None
    points = [x0, marker, end] + ([air_end] if air_end is not None else [])
    lo, hi = min(points) - 10, max(points) + 10
    if hi - lo < MIN_WIDTH:
        pad = (MIN_WIDTH - (hi - lo)) / 2
        lo, hi = lo - pad, hi + pad
    lo, hi = max(lo, DOMAIN[0]), min(hi, DOMAIN[1])
    if hi - lo < MIN_WIDTH:
        lo, hi = (DOMAIN[0], DOMAIN[0] + MIN_WIDTH) if lo == DOMAIN[0] else (DOMAIN[1] - MIN_WIDTH, DOMAIN[1])
    return {"kind": shape, "x0": x0, "marker": marker, "air_end": air_end, "end": end, "lo": lo, "hi": hi}
```

- [ ] **Step 4: Run tests, then commit**

```bash
.venv/Scripts/python -m unittest discover -s tests -p test_field.py
.venv/Scripts/python -m unittest discover -s tests
git add src/field.py tests/test_field.py
git commit -S -m "Decide which plays get a field diagram and where the marks go" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 6: Diagram text lines and SVG

**Files:**
- Modify: `src/field.py`
- Test: `tests/test_field.py`

**Interfaces:**
- Consumes: `kind`, `geometry` (Task 5).
- Produces:
  - `field.spot_line(play) -> str`: "3rd & 7 at the TB 35", "1st & goal at the TB 4", "2nd & 10 at the CLE 20", "… at midfield"; `""` when down or spot is missing.
  - `field.result_line(play) -> str | None`: "Sacked for a loss of 5", "Sacked for no gain", "Run for 3 yards", "Run for 1 yard", "Run for a loss of 2", "Run for no gain", "Complete for 14 yards", "Incomplete"; `None` for text-only plays.
  - `field.svg(play, size, team_color="#0057b8") -> str | None`: SVG markup with `role="img"` and `aria-label` = spot line + result line; sizes `"strip"` (320×56), `"medium"` (480×90), `"large"` (960×160); `None` when `geometry` is None.
  - `field.CAPTION = "Where the play started and ended; not a tracking diagram."`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_field.py (add)
class TextLineTests(unittest.TestCase):
    def test_spot_line(self):
        self.assertEqual(field.spot_line(base(down=3, ydstogo=7, yardline_100=35, offense="CLE", defense="TB")), "3rd & 7 at the TB 35")
        self.assertEqual(field.spot_line(base(down=2, ydstogo=10, yardline_100=80, offense="CLE", defense="TB")), "2nd & 10 at the CLE 20")
        self.assertEqual(field.spot_line(base(down=1, ydstogo=4, goal_to_go=1, yardline_100=4, offense="CLE", defense="TB")), "1st & goal at the TB 4")
        self.assertEqual(field.spot_line(base(down=1, ydstogo=10, yardline_100=50, offense="CLE", defense="TB")), "1st & 10 at midfield")
        self.assertEqual(field.spot_line(base(down=None, offense="CLE", defense="TB")), "")

    def test_result_line(self):
        sack = dict(play_type="pass", sack=1, rush_attempt=0, pass_attempt=1)
        self.assertEqual(field.result_line(base(**sack, yards_gained=-5)), "Sacked for a loss of 5")
        self.assertEqual(field.result_line(base(**sack, yards_gained=0)), "Sacked for no gain")
        self.assertEqual(field.result_line(base(yards_gained=1)), "Run for 1 yard")
        self.assertEqual(field.result_line(base(yards_gained=-2)), "Run for a loss of 2")
        self.assertEqual(field.result_line(base(yards_gained=0)), "Run for no gain")
        self.assertEqual(field.result_line(base(play_type="pass", rush_attempt=0, pass_attempt=1, complete_pass=1, air_yards=8, yards_gained=14)), "Complete for 14 yards")
        self.assertEqual(field.result_line(base(play_type="pass", rush_attempt=0, pass_attempt=1, air_yards=8, yards_gained=0)), "Incomplete")
        self.assertIsNone(field.result_line(base(penalty=1)))


class SvgTests(unittest.TestCase):
    def test_svg_is_labeled_and_sized(self):
        markup = field.svg(base(down=1, offense="CLE", defense="TB"), "medium")
        self.assertTrue(markup.startswith('<svg class="field field-medium" viewBox="0 0 480 90"'))
        self.assertIn('role="img"', markup)
        self.assertIn('aria-label="1st &amp; 10 at the CLE 35. Run for 4 yards"', markup)
        self.assertEqual(markup.count("<svg"), 1)

    def test_svg_draws_both_end_zones_near_a_goal_line(self):
        markup = field.svg(base(down=1, ydstogo=3, goal_to_go=1, yardline_100=3, yards_gained=3, offense="CLE", defense="TB"), "large")
        self.assertIn('class="endzone"', markup)
        self.assertIn(">TB<", markup)

    def test_text_is_escaped(self):
        markup = field.svg(base(down=1, offense='<b>', defense="TB"), "strip")
        self.assertNotIn("<b>", markup)

    def test_no_svg_for_text_only_plays(self):
        self.assertIsNone(field.svg(base(penalty=1), "strip"))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m unittest discover -s tests -p test_field.py`
Expected: AttributeError for `spot_line`.

- [ ] **Step 3: Implement text lines and SVG in `src/field.py`**

```python
from html import escape

CAPTION = "Where the play started and ended; not a tracking diagram."
SIZES = {"strip": (320, 56), "medium": (480, 90), "large": (960, 160)}
ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}


def spot_line(play):
    down, spot = play.get("down"), play.get("yardline_100")
    if down not in ORDINALS or spot is None:
        return ""
    distance = "goal" if play.get("goal_to_go") == 1 else play.get("ydstogo")
    if spot == 50:
        where = "midfield"
    elif spot < 50:
        where = f"the {play.get('defense', '')} {spot}"
    else:
        where = f"the {play.get('offense', '')} {100 - spot}"
    return f"{ORDINALS[down]} & {distance} at {where}"


def _yards(n):
    return f"{n} yard" if n == 1 else f"{n} yards"


def result_line(play):
    shape, gained = kind(play), play.get("yards_gained")
    if shape == "sack":
        return "Sacked for no gain" if gained == 0 else f"Sacked for a loss of {abs(gained)}"
    if shape == "run":
        return "Run for no gain" if gained == 0 else (f"Run for a loss of {abs(gained)}" if gained < 0 else f"Run for {_yards(gained)}")
    if shape == "complete":
        return f"Complete for {_yards(gained)}"
    if shape == "incomplete":
        return "Incomplete"
    return None


def svg(play, size, team_color="#0057b8"):
    g = geometry(play)
    if g is None:
        return None
    width, height = SIZES[size]
    scale = width / (g["hi"] - g["lo"])
    x = lambda yards: round((yards - g["lo"]) * scale, 1)
    mid = height / 2
    label = escape(". ".join(t for t in (spot_line(play), result_line(play)) if t), quote=True)
    parts = [f'<svg class="field field-{size}" viewBox="0 0 {width} {height}" role="img" aria-label="{label}" xmlns="http://www.w3.org/2000/svg">',
             f'<rect class="turf" x="0" y="0" width="{width}" height="{height}"/>']
    for goal, lo, hi, team in ((0, g["lo"], 0, play.get("offense", "")), (100, 100, g["hi"], play.get("defense", ""))):
        if g["lo"] < goal < g["hi"] or (goal == 0 and g["lo"] < 0) or (goal == 100 and g["hi"] > 100):
            left, right = x(max(lo, g["lo"])), x(min(hi, g["hi"]))
            if right > left:
                parts.append(f'<rect class="endzone" x="{left}" y="0" width="{round(right - left, 1)}" height="{height}"/>')
                if size != "strip":
                    parts.append(f'<text class="endzone-label" x="{round((left + right) / 2, 1)}" y="{mid + 4}" text-anchor="middle">{escape(team)}</text>')
    for yard in range(0, 101, 5):
        if g["lo"] <= yard <= g["hi"]:
            parts.append(f'<line class="{"yard-major" if yard % 10 == 0 else "yard-minor"}" x1="{x(yard)}" y1="0" x2="{x(yard)}" y2="{height}"/>')
    parts.append(f'<line class="los" x1="{x(g["x0"])}" y1="0" x2="{x(g["x0"])}" y2="{height}"/>')
    parts.append(f'<line class="marker" x1="{x(g["marker"])}" y1="0" x2="{x(g["marker"])}" y2="{height}"/>')
    if g["air_end"] is not None:
        top = max(6, mid - height * 0.35)
        parts.append(f'<path class="air" d="M{x(g["x0"])} {mid} Q{round((x(g["x0"]) + x(g["air_end"])) / 2, 1)} {top} {x(g["air_end"])} {mid}"/>')
        if g["kind"] == "complete":
            parts.append(f'<line class="run" x1="{x(g["air_end"])}" y1="{mid}" x2="{x(g["end"])}" y2="{mid}" style="stroke:{escape(team_color)}"/>')
        else:
            parts.append(f'<circle class="target" cx="{x(g["air_end"])}" cy="{mid}" r="4"/>')
    else:
        parts.append(f'<line class="run" x1="{x(g["x0"])}" y1="{mid}" x2="{x(g["end"])}" y2="{mid}" style="stroke:{escape(team_color)}"/>')
    if g["kind"] != "incomplete":
        parts.append(f'<circle class="ball" cx="{x(g["end"])}" cy="{mid}" r="4"/>')
    parts.append("</svg>")
    return "".join(parts)
```

- [ ] **Step 4: Add diagram styles to `static/styles.css`** (IMG Academy palette only; team color comes inline)

```css
.field{display:block;width:100%;height:auto;margin:6px 0}
.field .turf{fill:#f5f5f5}.field .endzone{fill:#dde3eb}.field .endzone-label{font:700 12px var(--display);fill:#002d54}
.field .yard-minor{stroke:#dde3eb;stroke-width:1}.field .yard-major{stroke:#cecac8;stroke-width:1.5}
.field .los{stroke:#002d54;stroke-width:2}.field .marker{stroke:#e4c200;stroke-width:2}
.field .air{fill:none;stroke:#587089;stroke-width:2;stroke-dasharray:4 4}.field .run{stroke-width:4;stroke-linecap:round}
.field .ball{fill:#002d54}.field .target{fill:#fff;stroke:#587089;stroke-width:2}
```

- [ ] **Step 5: Run the suite and a visual check, then commit**

```bash
.venv/Scripts/python -m unittest discover -s tests
.venv/Scripts/python - <<'EOF'
from pathlib import Path
from tests.test_field import base, edge_cases
from src import field
cases = edge_cases()
html = "<link rel=stylesheet href='static/styles.css'>" + "".join(f"<h4>{k}</h4>" + (field.svg(v, 'large') or 'text only') for k, v in cases.items())
html += field.svg(base(down=1, offense="CLE", defense="TB"), "strip")
Path("_field_preview.html").write_text(html, encoding="utf-8")
EOF
```

Open `_field_preview.html` (headless Edge screenshot as in `scripts/make_share_card.py`) and confirm: sack arrow goes left; completion shows a dashed arc then a solid line; goal-line touchdown ends at the end zone; text-only cases say "text only". Delete `_field_preview.html`.

```bash
git add src/field.py static/styles.css tests/test_field.py
git commit -S -m "Draw recorded plays as small field diagrams with plain text lines" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Push `feat/field-diagram`; open PR 2 (no page uses the diagrams yet).

## PR 3: Player pages (Tasks 7–9)

Branch: `feat/player-pages` from `main` after PR 2 merges. Open "Player pages, part 3: player and week pages with the play explorer" after Task 9.

### Task 7: Game logs, season lines and position groups

**Files:**
- Modify: `src/players.py`
- Test: `tests/test_players.py`

**Interfaces:**
- Consumes: edition dicts (schema 1 or 2) as loaded by `site.load_editions` (`Edition.data`).
- Produces:
  - `players.GROUPS`: ordered `(title, positions)` pairs: Quarterbacks {QB}, Running backs {RB, FB}, Receivers {WR, TE}, Offensive line {OT, OG, G, T, C, OL}, Defensive line {DT, DE, NT, DL, EDGE}, Linebackers {LB, ILB, OLB, MLB}, Defensive backs {CB, S, SAF, FS, SS, DB}.
  - `players.group_of(position: str) -> str` (title; "Other" when unknown).
  - `players.appearances(editions, pid) -> list[tuple[edition_data, player_dict]]` in (season, week) order.
  - `players.game_log(appearances) -> list[dict]` rows `{"edition_id", "week", "team", "opponent", "result", "status", "snaps", "snap_share", "contribution"}` (`snap_share` float 0–1 or None, from the player's main phase).
  - `players.season_lines(appearances, position) -> list[dict]` items `{"label", "text"}`; each `text` is a finished sentence following spec §6.
- Also exported for templates: `players.nickname(team_name) -> str` ("Cleveland Browns" → "Browns").

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_players.py (add)
import copy
import fixture_data


def edition_with(week, **player_changes):
    e = copy.deepcopy(fixture_data.golden_edition())
    e["id"], e["week"] = f"2026-week-{week:02d}", week
    for p in e["players"]:
        p.update(player_changes.get(p["name"], {}))
    return e


class GroupTests(unittest.TestCase):
    def test_groups(self):
        self.assertEqual(players.group_of("SAF"), "Defensive backs")
        self.assertEqual(players.group_of("G"), "Offensive line")
        self.assertEqual(players.group_of("XX"), "Other")
        self.assertEqual(players.nickname("Cleveland Browns"), "Browns")


class GameLogTests(unittest.TestCase):
    def test_rows_follow_week_order_and_show_each_weeks_team(self):
        week2 = edition_with(2)
        week3 = edition_with(3, **{"Grant Delpit": {"team": "NYJ", "team_name": "New York Jets"}})
        rows = players.game_log(players.appearances([week3, week2], "00-0036282"))
        self.assertEqual([r["week"] for r in rows], [2, 3])
        self.assertEqual([r["team"] for r in rows], ["CLE", "NYJ"])
        self.assertEqual(rows[0]["status"], "Played")
        delpit = next(p for p in week2["players"] if p["name"] == "Grant Delpit")
        self.assertAlmostEqual(rows[0]["snap_share"], 65 / delpit["snaps"]["team_defense"], places=3)

    def test_player_missing_from_an_edition_is_skipped(self):
        week2 = edition_with(2)
        week2["players"] = [p for p in week2["players"] if p["name"] != "Grant Delpit"]
        self.assertEqual(players.appearances([week2], "00-0036282"), [])


class SeasonLineTests(unittest.TestCase):
    def test_defense_counts_below_threshold(self):
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([edition_with(2)], "00-0036282"), "SAF")}
        self.assertIn("1 sack", lines["Impact plays"])
        self.assertIn("65 defensive snaps", lines["Snaps"])
        self.assertNotIn("per 100", lines["Impact plays"])
        self.assertIn("Charted in coverage", lines["Coverage"])
        self.assertNotIn("allowed", " ".join(lines.values()))

    def test_rates_appear_at_the_threshold(self):
        weeks = [edition_with(w) for w in range(2, 4)]
        for e in weeks:
            for p in e["players"]:
                if p["name"] == "Grant Delpit":
                    p["snaps"]["defense"] = 60
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances(weeks, "00-0036282"), "SAF")}
        self.assertIn("per 100 defensive snaps", lines["Impact plays"])

    def test_shares_are_ratios_of_sums(self):
        a = edition_with(2, **{"Carnell Tate": {"usage": {"targets": 5, "team_targets": 17, "air_yards": 50, "team_air_yards": 114}}})
        b = edition_with(3, **{"Carnell Tate": {"usage": {"targets": 10, "team_targets": 40, "air_yards": 100, "team_air_yards": 300}}})
        tate = next(p for p in a["players"] if p["name"] == "Carnell Tate")["id"]
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([a, b], tate), "WR")}
        self.assertIn("15 targets", lines["Targets"])
        self.assertIn("26% of team targets", lines["Targets"])  # 15/57, not the mean of 29% and 25%

    def test_cpoe_uses_only_rows_with_cp(self):
        plays = [{"roles": ["passer"], "qb_dropback": 1, "qb_kneel": 0, "qb_spike": 0, "qb_epa": 0.2, "epa": 0.2, "complete_pass": 1, "cp": 0.6}] * 30
        plays += [{"roles": ["passer"], "qb_dropback": 1, "qb_kneel": 0, "qb_spike": 0, "qb_epa": -0.1, "epa": -0.1, "complete_pass": 0, "cp": 0.5}] * 20
        plays += [{"roles": ["passer"], "qb_dropback": 1, "qb_kneel": 0, "qb_spike": 0, "qb_epa": 1.0, "epa": 1.0, "complete_pass": 1, "cp": None}] * 5
        e = edition_with(2, **{"J.J. McCarthy": {"plays": plays, "availability": {"label": "Played", "evidence": "x"}}})
        qb = next(p for p in e["players"] if p["name"] == "J.J. McCarthy")["id"]
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([e], qb), "QB")}
        # 100 * ((30*0.4) + (20*-0.5)) / 50 = +4.0
        self.assertIn("+4.0 percentage points", lines["Completion over expected"])

    def test_lineman_lines_have_no_penalties(self):
        lines = players.season_lines(players.appearances([edition_with(2)], next(p["id"] for p in edition_with(2)["players"] if p["name"] == "Tyler Booker")), "G")
        self.assertFalse(any("penalt" in l["text"].lower() for l in lines))

    def test_traded_player_sums_across_teams(self):
        week3 = edition_with(3, **{"Grant Delpit": {"team": "NYJ", "team_name": "New York Jets"}})
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([edition_with(2), week3], "00-0036282"), "SAF")}
        self.assertIn("130 defensive snaps", lines["Snaps"])
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m unittest discover -s tests -p test_players.py`
Expected: AttributeError for `group_of`.

- [ ] **Step 3: Implement in `src/players.py`**

```python
from . import evidence as ev

GROUPS = (
    ("Quarterbacks", {"QB"}), ("Running backs", {"RB", "FB"}), ("Receivers", {"WR", "TE"}),
    ("Offensive line", {"OT", "OG", "G", "T", "C", "OL"}), ("Defensive line", {"DT", "DE", "NT", "DL", "EDGE"}),
    ("Linebackers", {"LB", "ILB", "OLB", "MLB"}), ("Defensive backs", {"CB", "S", "SAF", "FS", "SS", "DB"}),
)
PHASES = (("offense", "team_offense", "offensive"), ("defense", "team_defense", "defensive"), ("st", "team_st", "special-teams"))
IMPACT_WORDS = {"Sack": ("sack", "sacks"), "Tackle for loss": ("tackle for loss", "tackles for loss"),
                "Interception": ("interception", "interceptions"), "Pass defended": ("pass defended", "passes defended"),
                "Forced fumble": ("forced fumble", "forced fumbles"), "Fumble recovery": ("fumble recovery", "fumble recoveries"),
                "QB hit": ("QB hit", "QB hits"), "3rd-down stop": ("3rd-down stop", "3rd-down stops"),
                "4th-down stop": ("4th-down stop", "4th-down stops"), "Safety": ("safety", "safeties")}


def group_of(position):
    return next((title for title, members in GROUPS if position in members), "Other")


def nickname(team_name):
    return team_name.split()[-1] if team_name else ""


def appearances(editions, pid):
    ordered = sorted(editions, key=lambda e: (e["season"], e["week"]))
    return [(e, p) for e in ordered for p in e["players"] if p["id"] == pid]


def _main_phase(player):
    snaps = player.get("snaps") or {}
    return max(PHASES, key=lambda ph: snaps.get(ph[0]) or 0)


def game_log(apps):
    rows = []
    for e, p in apps:
        phase, team_key, _ = _main_phase(p)
        snaps, team = (p.get("snaps") or {}).get(phase), (p.get("snaps") or {}).get(team_key)
        game = p.get("game") or {}
        rows.append({
            "edition_id": e["id"], "week": e["week"], "team": p["team"], "opponent": game.get("opponent", ""),
            "result": f"{game['result']} {game['team_score']}–{game['opp_score']}" if game else "",
            "status": p["availability"]["label"], "snaps": snaps,
            "snap_share": snaps / team if snaps and team else None,
            "contribution": "",
        })
    return rows


def _n(count, one, many):
    return f"{count} {one if count == 1 else many}"


def _sum(values):
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def _pct(part, whole):
    return f"{round(100 * part / whole)}%" if part is not None and whole else None


def season_lines(apps, position):
    played = [(e, p) for e, p in apps if p["availability"]["label"] == ev.PLAYED]
    lines = [{"label": "Games", "text": f"Played in {_n(len(played), 'game', 'games')} of {len(apps)}."}]
    snap_parts = []
    for phase, team_key, word in PHASES:
        mine = _sum((p.get("snaps") or {}).get(phase) for _, p in apps)
        team = _sum((p.get("snaps") or {}).get(team_key) for _, p in apps if (p.get("snaps") or {}).get(phase))
        if mine:
            share = _pct(mine, team)
            snap_parts.append(f"{mine} {word} snaps" + (f", {share} of the team's" if share else ""))
    if snap_parts:
        lines.append({"label": "Snaps", "text": "; ".join(snap_parts) + "."})
    group = group_of(position)
    plays = [q for _, p in played for q in p.get("plays", [])]
    if group == "Quarterbacks":
        lines += _qb_lines(plays)
    elif group == "Running backs":
        lines += _rush_lines(plays)
    elif group == "Receivers":
        lines += _receiver_lines(played, plays)
    elif group in ("Defensive line", "Linebackers", "Defensive backs"):
        lines += _defense_lines(played, plays)
    return lines


def _efficiency(rows, key, noun, threshold):
    values = [r[key] for r in rows if r.get(key) is not None]
    if len(rows) < threshold or not values:
        return None
    success = sum(1 for v in values if v > 0)
    return f"Expected points per {noun} {sum(values) / len(values):+.2f}; success rate {round(100 * success / len(values))}%."


def _qb_lines(plays):
    drops = [q for q in plays if "passer" in q.get("roles", []) and q.get("qb_dropback") == 1 and q.get("qb_kneel") != 1 and q.get("qb_spike") != 1]
    lines = [{"label": "Dropbacks", "text": f"{_n(len(drops), 'dropback', 'dropbacks')}." + (" " + _efficiency(drops, "qb_epa", "dropback", 50) if _efficiency(drops, "qb_epa", "dropback", 50) else "")}]
    with_cp = [q for q in drops if q.get("cp") is not None and q.get("complete_pass") is not None]
    if len(with_cp) >= 50:
        cpoe = 100 * sum(q["complete_pass"] - q["cp"] for q in with_cp) / len(with_cp)
        lines.append({"label": "Completion over expected", "text": f"{cpoe:+.1f} percentage points on {len(with_cp)} throws."})
    return lines


def _rush_lines(plays):
    carries = [q for q in plays if "rusher" in q.get("roles", []) and q.get("rush_attempt") == 1]
    targets = [q for q in plays if "receiver" in q.get("roles", [])]
    catches = sum(1 for q in targets if q.get("complete_pass") == 1)
    rate = _efficiency(carries, "epa", "carry", 30)
    return [{"label": "Carries", "text": f"{_n(len(carries), 'carry', 'carries')}." + (f" {rate}" if rate else "")},
            {"label": "Receiving", "text": f"{_n(len(targets), 'target', 'targets')}, {_n(catches, 'catch', 'catches')}."}]


def _receiver_lines(played, plays):
    usage = [p.get("usage") or {} for _, p in played]
    targets, team_targets = _sum(u.get("targets") for u in usage), _sum(u.get("team_targets") for u in usage if u.get("team_targets"))
    air, team_air = _sum(u.get("air_yards") for u in usage), _sum(u.get("team_air_yards") for u in usage if u.get("team_air_yards"))
    text = f"{_n(targets or 0, 'target', 'targets')}"
    if targets and team_targets:
        text += f", {_pct(targets, team_targets)} of team targets"
    if air is not None and team_air:
        text += f"; {_pct(air, team_air)} of team air yards"
    lines = [{"label": "Targets", "text": text + "."}]
    charted = [(p.get("charting") or {}).get("targets") for _, p in played]
    charted = [c for c in charted if c]
    if charted:
        lines.append({"label": "Charted targets", "text": f"{sum(c['catchable'] for c in charted)} of {sum(c['charted'] for c in charted)} catchable, {_n(sum(c['drops'] for c in charted), 'drop', 'drops')}."})
    targeted = [q for q in plays if "receiver" in q.get("roles", [])]
    if len(targeted) >= 15:
        values = [q["epa"] for q in targeted if q.get("epa") is not None]
        if values:
            lines.append({"label": "When targeted", "text": f"Team expected points when targeted {sum(values) / len(values):+.2f} per target."})
    return lines


def _defense_lines(played, plays):
    counts = {}
    for q in plays:
        if q.get("side") == "defense" and q.get("impact"):
            counts[q["impact"]] = counts.get(q["impact"], 0) + 1
    total = sum(counts.values())
    parts = [_n(n, *IMPACT_WORDS.get(kind, (kind.lower(), kind.lower()))) for kind, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    snaps = _sum((p.get("snaps") or {}).get("defense") for _, p in played) or 0
    text = f"{_n(total, 'impact play', 'impact plays')}" + (f" ({', '.join(parts)})" if parts else "")
    if snaps >= 100:
        text += f"; {100 * total / snaps:.1f} per 100 defensive snaps"
    lines = [{"label": "Impact plays", "text": text + "."}]
    charting = [p.get("charting") or {} for _, p in played]
    cover = [c["coverage"] for c in charting if c.get("coverage")]
    if cover:
        lines.append({"label": "Coverage", "text": f"Charted in coverage: {_n(sum(c['targets'] for c in cover), 'target', 'targets')}, {_n(sum(c['completions'] for c in cover), 'completion', 'completions')}, {_n(sum(c['yards'] for c in cover), 'yard', 'yards')}."})
    rush = [c["pass_rush"] for c in charting if c.get("pass_rush")]
    if rush:
        lines.append({"label": "Pass rush", "text": f"{_n(sum(r['pressures'] for r in rush), 'pressure', 'pressures')}."})
    tackling = [c["tackling"] for c in charting if c.get("tackling")]
    if tackling:
        lines.append({"label": "Tackling", "text": f"{sum(t['missed'] for t in tackling)} missed in {_n(sum(t['attempts'] for t in tackling), 'attempt', 'attempts')}."})
    return lines
```

Set `"contribution"` in `game_log` rows to `site.contribution(p)` inside `site.py` (Task 8) rather than here, keeping `players.py` free of site imports: leave `""` here and fill it in Task 8.

- [ ] **Step 4: Run the tests and fix only real failures**

Run: `.venv/Scripts/python -m unittest discover -s tests -p test_players.py`
Expected: PASS. If `test_defense_counts_below_threshold` fails on a label, check the fixture player's plays in `expected_edition.json` rather than editing the assertion to match.

- [ ] **Step 5: Commit**

```bash
git add src/players.py tests/test_players.py
git commit -S -m "Build game logs and season lines from published editions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 8: Player, week and index pages

**Files:**
- Modify: `src/site.py` (`build_site`, sitemap, `check_site` unchanged)
- Create: `templates/players.html`, `templates/player.html`, `templates/player_week.html`, `templates/_play.html`, `templates/_player_head.html`
- Modify: `templates/base.html` (nav: add Players)
- Test: `tests/test_site.py`

**Interfaces:**
- Consumes: `players.appearances`, `game_log`, `season_lines`, `group_of`, `nickname`, `GROUPS` (Task 7); `field.svg`, `spot_line`, `result_line`, `CAPTION` (Task 6); `edition.load_registry`; `site.player_view`, `play_outcome`, `contribution`.
- Produces: `site.next_line(player: dict) -> str` ("CLE at PIT · Sun, Oct 4 · 1:00 p.m. ET", "Bye in Week 5, then CLE at PIT · …", "Next game unconfirmed", or "" when there is no `next_game`); `site.play_view(play: dict, player: dict) -> dict` adding `outcome`, `spot`, `result`, `svg_medium`, `svg_large`, `positive` (True/False/None), `key` (bool); `build_site(out, editions_root, config, registry=None)` writes `players/index.html`, `players/<slug>/index.html`, `players/<slug>/<edition-id>/index.html` and adds them to the sitemap.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_site.py (add)
class PlayerPageTests(SiteTestCase):
    def test_every_registry_player_gets_pages(self):
        out = self.render()
        registry = load_registry(fixture_data.FIXTURES / "alumni.json")
        for alum in registry:
            self.assertTrue((out / "players" / alum["slug"] / "index.html").exists(), alum["name"])
            self.assertTrue((out / "players" / alum["slug"] / "2026-week-02" / "index.html").exists(), alum["name"])
        index = self.read(out / "players" / "index.html")
        self.assertIn("Defensive backs", index)
        self.assertIn('href="grant-delpit/"', index)

    def test_week_page_lists_every_recorded_play_with_diagrams(self):
        page = self.read(self.render() / "players" / "carnell-tate" / "2026-week-02" / "index.html")
        self.assertIn("Recorded plays (5)", page)
        self.assertEqual(page.count('class="play '), 5)
        self.assertIn('class="field field-medium"', page)
        self.assertIn("Expected points describe the whole play, not the player named on it.", page)
        self.assertIn("Positive plays for the Titans", page)
        self.assertIn("not a tracking diagram", page)

    def test_lineman_with_no_recorded_plays(self):
        page = self.read(self.render() / "players" / "tyler-booker" / "2026-week-02" / "index.html")
        self.assertIn("Recorded plays (0)", page)
        self.assertIn("Offensive linemen are rarely named in play-by-play", page)
        self.assertNotIn('class="field ', page)

    def test_play_without_epa_has_no_outcome_and_no_side(self):
        edition = fixture_data.golden_edition()
        tate = next(p for p in edition["players"] if p["name"] == "Carnell Tate")
        tate["plays"][0]["epa"] = None
        page = self.read(self.render(edition) / "players" / "carnell-tate" / "2026-week-02" / "index.html")
        first = page.split('class="play ')[1].split("</li>")[0]
        self.assertIn('data-positive=""', first)
        self.assertNotIn("expected point", first)

    def test_schema_one_edition_renders_from_key_moments(self):
        edition = fixture_data.golden_edition()
        edition["schema_version"] = 1
        for p in edition["players"]:
            p.pop("plays", None)
        page = self.read(self.render(edition) / "players" / "grant-delpit" / "2026-week-02" / "index.html")
        self.assertIn("The full play list was not saved for this week", page)
        self.assertIn("Sack", page)

    def test_player_added_later_has_only_his_weeks(self):
        edition = fixture_data.golden_edition()
        edition["players"] = [p for p in edition["players"] if p["name"] != "Grant Delpit"]
        out = self.render(edition)
        self.assertTrue((out / "players" / "grant-delpit" / "index.html").exists())
        self.assertFalse((out / "players" / "grant-delpit" / "2026-week-02").exists())

    def test_evergreen_page_has_season_and_game_log(self):
        page = self.read(self.render() / "players" / "grant-delpit" / "index.html")
        for text in ("Grant Delpit", "CLE / S", "Season", "Impact plays", "Game log", 'href="2026-week-02/"', "See all", "Data as of"):
            self.assertIn(text, page)

    def test_up_next_appears_only_when_the_edition_has_it(self):
        edition = fixture_data.golden_edition()
        delpit = next(p for p in edition["players"] if p["name"] == "Grant Delpit")
        self.assertIsNone(delpit["next_game"])  # the fixture is a historical replay
        self.assertNotIn("Up next", self.read(self.render(edition) / "players" / "grant-delpit" / "index.html"))
        delpit["next_game"] = {"kind": "game", "date": "2026-10-04", "kickoff_et": "13:00", "home_away": "away", "opponent": "PIT", "venue": "Acrisure Stadium", "team": "CLE", "team_name": "Cleveland Browns", "team_color": "#311D00", "week": 3}
        page = self.read(self.render(edition) / "players" / "grant-delpit" / "index.html")
        self.assertIn("Up next", page)
        self.assertIn("CLE at PIT · Sun, Oct 4 · 1:00 p.m. ET", page)

    def test_nav_links_players_and_the_site_passes_its_checks(self):
        out = self.render()
        self.assertIn(">Players</a>", self.read(out / "index.html"))
        self.assertEqual(site.check_site(out, site.load_editions(self.editions)), [])
        self.assertIn("players/grant-delpit/", self.read(out / "sitemap.xml"))
```

Add `from src.edition import load_registry` to the test imports, and make `SiteTestCase.render` pass `registry=load_registry(fixture_data.FIXTURES / "alumni.json")` to `build_site`.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m unittest discover -s tests -p test_site.py`
Expected: failures for the new tests (no `players/` output).

- [ ] **Step 3: Add `play_view` and page building to `src/site.py`**

```python
from markupsafe import Markup

from . import field, players as pl
from .edition import load_registry
from .upnext import kickoff_label, matchup_label  # already imported at the top of site.py; shown for clarity


def next_line(player):
    info = player.get("next_game")
    if not info:
        return ""
    if info.get("kind") == "game":
        return f"{matchup_label(info, info['team'])} · {kickoff_label(info)}"
    if info.get("kind") == "bye":
        return f"Bye in Week {info['bye_week']}, then {matchup_label(info, info['team'])} · {kickoff_label(info)}"
    return "Next game unconfirmed" if info.get("kind") == "unconfirmed" else "Season complete"


def play_view(play, player, key_ids=()):
    epa = play.get("epa")
    positive = None if epa is None else (epa > 0 if play.get("side", "offense") == "offense" else epa < 0)
    medium, large = field.svg(play, "medium", player.get("team_color", "#0057b8")), field.svg(play, "large", player.get("team_color", "#0057b8"))
    return dict(
        play,
        outcome=play_outcome(play, player) if epa is not None else "",
        spot=field.spot_line(play), result=field.result_line(play) or "",
        svg_medium=Markup(medium) if medium else None, svg_large=Markup(large) if large else None,
        positive=positive, key=play.get("play_id") in key_ids,
    )


def week_plays(player):
    """Recorded plays for a week page: key moments first, then game order. Schema-1 editions have only key moments."""
    key_ids = [k["play_id"] for k in player.get("key_plays", [])]
    plays = player.get("plays")
    saved = plays is not None
    source = plays if saved else player.get("key_plays", [])
    ordered = sorted(source, key=lambda q: (q["play_id"] not in key_ids, key_ids.index(q["play_id"]) if q["play_id"] in key_ids else 0, float(q["play_id"])))
    return saved, [play_view(q, player, set(key_ids)) for q in ordered]
```

In `build_site(out, editions_root=..., config=None, registry=None)`: `registry = registry or load_registry()`; after the edition loop, add:

```python
    datas = [e.data for e in editions]
    listing = []
    for alum in registry:
        apps = pl.appearances(datas, alum["gsis_id"])
        latest = apps[-1][1] if apps else None
        base_url = f"players/{alum['slug']}/"
        for e_data, p in apps:
            view = player_view(p)
            saved, plays = week_plays(p)
            page("player_week.html", f"{base_url}{e_data['id']}/index.html", canonical=site_url + f"{base_url}{e_data['id']}/", root="../../../",
                 player=view, edition=e_data, plays=plays, plays_saved=saved, lineman=pl.group_of(p["position"]) == "Offensive line",
                 nickname=pl.nickname(p["team_name"]), caption=field.CAPTION, data_as_of=eastern_label(e_data["generated_at"]),
                 next_text=next_line(p))
            urls.append(f"{site_url}{base_url}{e_data['id']}/")
        log = pl.game_log(apps)
        for row, (_, p) in zip(log, apps):
            row["contribution"] = contribution(p)
        top = week_plays(latest)[1][:1] if latest else []
        page("player.html", base_url + "index.html", canonical=site_url + base_url, root="../../", alum=alum,
             player=player_view(latest) if latest else None, latest_edition=apps[-1][0] if apps else None,
             season=pl.season_lines(apps, latest["position"]) if latest else [], log=log, top_play=top[0] if top else None,
             recorded=len((latest or {}).get("plays", []) or []), next_text=next_line(latest) if latest else "",
             data_as_of=eastern_label(apps[-1][0]["generated_at"]) if apps else "")
        urls.append(site_url + base_url)
        listing.append({"alum": alum, "player": latest, "group": pl.group_of(latest["position"]) if latest else "Other"})
    page("players.html", "players/index.html", canonical=site_url + "players/", root="../",
         groups=[(title, [x for x in listing if x["group"] == title]) for title, _ in pl.GROUPS + (("Other", set()),)])
    urls.append(site_url + "players/")
```

Move the `urls = [...]` line above this block and the sitemap `page(...)` call below it, so the sitemap includes player pages.

- [ ] **Step 4: Write the templates**

`templates/_player_head.html` (shared header):

```html
<header class="player-head" style="--team: {{ player.team_color }}">
  <p class="eyebrow">{{ player.team }} / {{ player.position }}{% if eyebrow_suffix %} · {{ eyebrow_suffix }}{% endif %}</p>
  <h1>{{ player.name }}</h1>
  <p class="score">{{ player.score_line }}</p>
  {% if player.participation %}<p class="evidence">{{ player.participation }}</p>{% endif %}
  <div class="metrics">{% for m in player.metrics %}<div><strong>{{ m.value | num }}</strong><span>{{ m.label }}</span></div>{% endfor %}</div>
  {% if player.charting_lines %}<ul class="ngs charted">{% for line in player.charting_lines %}<li>{{ line }}</li>{% endfor %}</ul>{% endif %}
  <p class="caption">{{ player.context }}{% if player.source_url %} · <a href="{{ player.source_url }}" rel="noopener">IMG Academy affiliation source</a>{% endif %}</p>
</header>
```

`templates/_play.html` (one explorer item):

```html
<li class="play {% if p.key %}key {% endif %}{% if p.impact %}impact{% endif %}" id="play-{{ p.play_id }}" data-positive="{{ '1' if p.positive else ('0' if p.positive == False else '') }}">
  <button type="button" class="play-pick" aria-controls="play-stage">
    <span class="play-meta">{{ p.quarter }} · {{ p.clock }}{% if p.spot %} · {{ p.spot }}{% endif %}{% if p.impact %} · {{ p.impact }}{% endif %}</span>
    {{ p.description }}
  </button>
  {% if p.svg_medium %}{{ p.svg_medium }}{% endif %}
  {% if p.result %}<span class="play-result">{{ p.result }}</span>{% endif %}
  {% if p.outcome %}<span class="play-outcome">{{ p.outcome }}</span>{% endif %}
  {% if p.svg_large %}<template class="play-large">{{ p.svg_large }}</template>{% endif %}
</li>
```

`templates/player_week.html`:

```html
{% extends "base.html" %}
{% block title %}{{ player.name }}, Week {{ edition.week }} · {{ site.title }}{% endblock %}
{% block description %}{{ player.name }}'s Week {{ edition.week }}: every recorded play, drawn on the field.{% endblock %}
{% block content %}
<p class="crumbs"><a href="{{ root }}editions/{{ edition.id }}/">← Week {{ edition.week }} edition</a> · <a href="../">{{ player.name }}'s season</a></p>
{% set eyebrow_suffix = edition.season ~ " Season · Week " ~ edition.week %}
{% include "_player_head.html" %}
<p class="as-of">Data as of {{ data_as_of }}. The NFL can correct statistics later in the week.</p>
<section class="section explorer" aria-labelledby="plays-head">
  <div class="section-head"><h2 id="plays-head">Recorded plays ({{ plays | length }})</h2></div>
  <p class="section-note">The play-by-play names a player only when he throws, runs, is targeted, makes a tackle or a charted defensive play. Most snaps never appear here; see his snaps above.{% if lineman %} Offensive linemen are rarely named in play-by-play; their snaps and team results tell more.{% endif %}</p>
  {% if not plays_saved %}<p class="section-note">The full play list was not saved for this week; these are its key moments.</p>{% endif %}
  {% if plays %}
  <div class="explorer-filters" hidden>
    <button type="button" data-filter="all" aria-pressed="true">All plays</button>
    <button type="button" data-filter="impact" aria-pressed="false">Impact plays</button>
    <button type="button" data-filter="positive" aria-pressed="false">Positive plays for the {{ nickname }}</button>
    <button type="button" data-filter="negative" aria-pressed="false">Negative plays for the {{ nickname }}</button>
  </div>
  <p class="section-note">Expected points describe the whole play, not the player named on it. {{ caption }}</p>
  <div id="play-stage" class="play-stage" aria-live="polite" hidden></div>
  <ol class="plays explorer-list">{% for p in plays %}{% include "_play.html" %}{% endfor %}</ol>
  {% endif %}
</section>
{% if next_text %}<section class="section"><h2>Up next, as of Week {{ edition.week }}</h2><p>{{ next_text }}</p></section>{% endif %}
<script src="{{ root }}static/explorer.js?v={{ explorer_version }}" defer></script>
{% endblock %}
```

`templates/player.html`:

```html
{% extends "base.html" %}
{% block title %}{{ alum.name }} · {{ site.title }}{% endblock %}
{% block description %}{{ alum.name }}'s season: game log, season lines and every recorded play.{% endblock %}
{% block content %}
{% if player %}
{% set eyebrow_suffix = "Latest: Week " ~ latest_edition.week %}
{% include "_player_head.html" %}
{% if top_play and top_play.svg_medium %}<figure class="top-play">{{ top_play.svg_medium }}<figcaption>{{ top_play.result }} {{ top_play.outcome }}</figcaption></figure>{% endif %}
<p><a href="{{ latest_edition.id }}/">See all {{ recorded }} recorded plays from Week {{ latest_edition.week }} →</a></p>
{% if next_text %}<section class="section"><h2>Up next</h2><p>{{ next_text }}</p></section>{% endif %}
<section class="section"><h2>Season</h2><dl class="season">{% for line in season %}<dt>{{ line.label }}</dt><dd>{{ line.text }}</dd>{% endfor %}</dl></section>
<section class="section"><h2>Game log</h2>
<div class="table-wrap"><table><thead><tr><th scope="col">Week</th><th scope="col">Team</th><th scope="col">Opp.</th><th scope="col">Result</th><th scope="col">Status</th><th scope="col">Snaps</th><th scope="col">Contribution</th></tr></thead>
<tbody>{% for r in log %}<tr><td><a href="{{ r.edition_id }}/">{{ r.week }}</a></td><td>{{ r.team }}</td><td>{{ r.opponent }}</td><td>{{ r.result }}</td><td>{{ r.status }}</td><td>{{ r.snaps if r.snaps is not none else "—" }}{% if r.snap_share %} ({{ (r.snap_share * 100) | round | int }}%){% endif %}</td><td>{{ r.contribution }}</td></tr>{% endfor %}</tbody></table></div>
</section>
<p class="as-of">Data as of {{ data_as_of }}. The NFL can correct statistics later in the week.</p>
{% else %}
<h1>{{ alum.name }}</h1><p>No published edition includes {{ alum.name }} yet.</p>
{% endif %}
{% endblock %}
```

`templates/players.html`:

```html
{% extends "base.html" %}
{% block title %}Players · {{ site.title }}{% endblock %}
{% block content %}
<h1>Players</h1>
{% for title, members in groups if members %}
<section class="section"><h2>{{ title }}</h2><ul class="player-list">
{% for m in members %}<li><a href="{{ m.alum.slug }}/">{{ m.alum.name }}</a>{% if m.player %} · {{ m.player.team }} · {{ m.player.availability.label }}{% endif %}</li>{% endfor %}
</ul></section>
{% endfor %}
{% endblock %}
```

In `templates/base.html` nav, between This Week and Archive: `<a href="{{ root }}players/">Players</a>`. In `environment()`, add `env.globals["explorer_version"] = asset_version(ROOT / "static" / "explorer.js")` and create an empty `static/explorer.js` placeholder containing `// Filled in by Task 9.` so the file exists.

- [ ] **Step 5: Run the suite, fix real failures, commit**

```bash
.venv/Scripts/python -m unittest discover -s tests
.venv/Scripts/python -m src.site build --out _site --check
git add src/site.py templates static/explorer.js tests/test_site.py
git commit -S -m "Build player, week and index pages from published editions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 9: Explorer interaction

**Files:**
- Modify: `static/explorer.js`, `static/styles.css`
- Create: `scripts/check_explorer.py`
- Test: `tests/test_site.py` (markup contract)

**Interfaces:**
- Consumes: the markup from Task 8 (`.explorer-filters[hidden]`, `button[data-filter]`, `li.play[data-positive]`, `.play-pick`, `template.play-large`, `#play-stage[hidden]`).
- Produces: with JavaScript, filters are visible, the stage shows the selected play's large diagram, clicking a play selects it (`aria-current="true"`), and `#play-<id>` selects on load.

- [ ] **Step 1: Write the markup-contract test**

```python
# tests/test_site.py (add to PlayerPageTests)
    def test_explorer_markup_contract(self):
        page = self.read(self.render() / "players" / "grant-delpit" / "2026-week-02" / "index.html")
        for needle in ('class="explorer-filters" hidden', 'data-filter="impact"', 'id="play-stage"', '<template class="play-large">', 'static/explorer.js?v='):
            self.assertIn(needle, page)
```

- [ ] **Step 2: Implement `static/explorer.js`**

```javascript
(function () {
  var list = document.querySelector(".explorer-list");
  if (!list) return;
  var stage = document.getElementById("play-stage");
  var items = Array.prototype.slice.call(list.querySelectorAll("li.play"));
  var filters = document.querySelector(".explorer-filters");
  document.documentElement.classList.add("js-explorer");
  filters.hidden = false;
  stage.hidden = false;

  function select(item, updateHash) {
    items.forEach(function (i) { i.removeAttribute("aria-current"); });
    item.setAttribute("aria-current", "true");
    var large = item.querySelector("template.play-large");
    stage.innerHTML = large ? large.innerHTML : "";
    var text = item.querySelector(".play-result, .play-outcome");
    if (!large && text) stage.textContent = text.textContent;
    if (updateHash) history.replaceState(null, "", "#" + item.id);
  }

  function matches(item, filter) {
    if (filter === "impact") return item.classList.contains("impact");
    if (filter === "positive") return item.getAttribute("data-positive") === "1";
    if (filter === "negative") return item.getAttribute("data-positive") === "0";
    return true;
  }

  filters.addEventListener("click", function (event) {
    var button = event.target.closest("button[data-filter]");
    if (!button) return;
    filters.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", String(b === button)); });
    items.forEach(function (i) { i.hidden = !matches(i, button.getAttribute("data-filter")); });
  });

  list.addEventListener("click", function (event) {
    var pick = event.target.closest(".play-pick");
    if (pick) select(pick.closest("li.play"), true);
  });

  var initial = (location.hash && document.getElementById(location.hash.slice(1))) || items[0];
  if (initial) select(initial, false);
})();
```

Styles: `.js-explorer .explorer-list .field{display:none}` (the stage shows the large one), `.play[aria-current="true"]{background:var(--wash);border-left:3px solid var(--brand)}`, `.explorer-filters button[aria-pressed="true"]{background:var(--brand);color:#fff}`, `.play-pick{all:unset;cursor:pointer;display:block}`, `.play-result{display:block;font-size:12px}`.

- [ ] **Step 3: Write `scripts/check_explorer.py` (headless browser check)**

```python
"""Build the site, open a week page in headless Edge/Chrome and check the explorer. Run: python scripts/check_explorer.py"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.make_share_card import browser  # noqa: E402
from src import site  # noqa: E402


def dump(url):
    result = subprocess.run([browser(), "--headless=new", "--disable-gpu", f"--user-data-dir={tempfile.mkdtemp()}",
                             "--virtual-time-budget=5000", "--dump-dom", url], capture_output=True, text=True, timeout=120)
    return result.stdout


def main():
    out = Path(tempfile.mkdtemp()) / "site"
    site.build_site(out)
    page = next(out.glob("players/*/*/index.html"))
    first = page.read_text(encoding="utf-8").split('id="play-')[2].split('"')[0]
    dom = dump(page.as_uri() + f"#play-{first}")
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
```

Run: `.venv/Scripts/python scripts/check_explorer.py` → three `ok` lines. (On Windows the launcher can return early; if the DOM dump is empty, rerun once.)

- [ ] **Step 4: Run the suite and a phone-width check, then commit**

```bash
.venv/Scripts/python -m unittest discover -s tests
.venv/Scripts/python -m src.site build --out _site --check
```

Check one week page at 375 px (browser pane or headless screenshot) for horizontal overflow: `document.documentElement.scrollWidth === 375`.

```bash
git add static/explorer.js static/styles.css scripts/check_explorer.py tests/test_site.py
git commit -S -m "Add the play explorer: selection, filters and linkable plays" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Push `feat/player-pages`; run a Codex review of the branch diff; fix findings with regression tests; open PR 3.

## PR 4: Homepage and docs (Tasks 10–11)

Branch: `feat/player-links` from `main` after PR 3 merges.

### Task 10: Card strips and player links

**Files:**
- Modify: `src/site.py` (`player_view` adds `slug`, `strip`, `strip_play_id`), `src/site.py` `edition_context` (slug map), `templates/_card.html`
- Test: `tests/test_site.py`

**Interfaces:**
- Consumes: `field.svg(play, "strip", team_color)`; registry slugs.
- Produces: each played card with a drawable top key moment shows `<a class="strip" href="…players/<slug>/<edition-id>/#play-<id>">` containing the strip SVG and its outcome line; the card's name links to the week page; "See every play →" link on every played card.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_site.py (add)
class CardStripTests(SiteTestCase):
    def test_card_strip_links_to_the_play(self):
        home = self.read(self.render() / "index.html")
        delpit = home.split('id="player-00-0036282"')[1].split("</article>")[0]
        self.assertIn('class="field field-strip"', delpit)
        self.assertIn('href="players/grant-delpit/2026-week-02/#play-', delpit)
        self.assertIn("See every play", delpit)

    def test_cards_without_drawable_plays_have_no_strip(self):
        home = self.read(self.render() / "index.html")
        cards = home.split('<article class="card"')[1:]
        booker = next(c.split("</article>")[0] for c in cards if "Tyler Booker" in c)
        self.assertNotIn("field-strip", booker)
        self.assertIn("See every play", booker)
```

- [ ] **Step 2: Implement**

In `edition_context(edition, *, root, data_path, slugs)`: pass `slugs = {alum["gsis_id"]: alum["slug"] for alum in registry}` from `build_site`, and for each player view set `view["page"] = f"{root}players/{slugs[p['id']]}/{edition.id}/"` when the id has a slug. Top drawable play: the first key moment whose `play_id` is in `plays` and has a geometry; `view["strip"] = Markup(field.svg(play, "strip", p["team_color"]))`, `view["strip_play_id"]`, `view["strip_outcome"]`.

In `templates/_card.html`: wrap `<h3>` content in `<a href="{{ p.page }}">` when `p.page`; after the metrics block add:

```html
  {% if p.strip %}<a class="strip" href="{{ p.page }}#play-{{ p.strip_play_id }}">{{ p.strip }}<span class="play-outcome">{{ p.strip_outcome }}</span></a>{% endif %}
  {% if p.page %}<p class="see-plays"><a href="{{ p.page }}">See every play →</a></p>{% endif %}
```

- [ ] **Step 3: Run the suite, check phone width, commit**

```bash
.venv/Scripts/python -m unittest discover -s tests
.venv/Scripts/python -m src.site build --out _site --check
git add src/site.py templates/_card.html tests/test_site.py
git commit -S -m "Add a field strip and player links to each homepage card" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 11: Methodology and operations notes

**Files:**
- Modify: `templates/methodology.html`, `docs/OPERATIONS.md`, `CLAUDE.md` (Map: `players.py`, `field.py`)
- Test: `tests/test_site.py`

- [ ] **Step 1: Failing test**

```python
    def test_methodology_explains_player_pages(self):
        page = self.read(self.render() / "methodology" / "index.html")
        self.assertIn('id="player-pages"', page)
        self.assertIn("not a tracking diagram", page)
        self.assertIn("rarely named in play-by-play", page)
```

- [ ] **Step 2: Add the methodology section** (before "Up next"):

```html
  <h2 id="player-pages">Player pages and the play explorer</h2>
  <p>Every alum has a season page and a permanent page for each week. A week page lists every play on which the play-by-play names him: as passer, runner, target, tackler, or on a charted defensive play such as a sack or pass defended. Most snaps never appear there, and offensive linemen are rarely named in play-by-play at all, so snaps and team results come first.</p>
  <p>Field diagrams show where a play started and ended: the line of scrimmage, the first-down marker and the ball's path. They are not a tracking diagram, and no player movement is drawn. Interceptions, fumbles, laterals, penalties and special-teams plays are shown as text only for now. The offense always moves left to right.</p>
  <p>Season lines add up every published week. Shares are season totals divided by team totals, and rates appear only after a meaningful sample: 50 dropbacks, 30 carries, 15 targets or 100 defensive snaps.</p>
```

- [ ] **Step 3: Docs** — `docs/OPERATIONS.md` "When something goes wrong" gains: "To rebuild a published edition with new code: `.venv/Scripts/python -m src.edition --season 2026 --week N --historical`, keep the published `current` roster notes, review the diff, open a PR." `CLAUDE.md` Map gains `players.py` (slugs, game logs, season lines) and `field.py` (diagram eligibility and SVG).

- [ ] **Step 4: Run, commit, push, open PR 4**

```bash
.venv/Scripts/python -m unittest discover -s tests
git add templates/methodology.html docs/OPERATIONS.md CLAUDE.md tests/test_site.py
git commit -S -m "Explain player pages and field diagrams" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

## PR 5: Backfill (Task 12)

### Task 12: Canary, then rebuild Weeks 1–3

**Files:**
- Modify: `editions/2026-week-01/{edition.json,sources.json}`, `editions/2026-week-02/…`, `editions/2026-week-03/…`

- [ ] **Step 1: Canary Week 2 on branch `chore/backfill-plays`**

```bash
.venv/Scripts/python -m src.edition --season 2026 --week 2 --historical
.venv/Scripts/python - <<'EOF'
import json, subprocess
from src.edition import dump_json
path = "editions/2026-week-02/edition.json"
old = json.loads(subprocess.run(["git", "show", "HEAD:" + path], capture_output=True, text=True, encoding="utf-8").stdout)
new = json.load(open(path, encoding="utf-8"))
before = {p["id"]: p["current"] for p in old["players"]}
for p in new["players"]:
    p["current"] = before[p["id"]]
open(path, "wb").write(dump_json(new))
changed = [(n["name"], [k for k in n if k not in ("plays", "usage") and n.get(k) != o.get(k)]) for n, o in zip(new["players"], old["players"])]
print([c for c in changed if c[1]])
EOF
```

Expected: only `plays`, `usage`, `snaps` (denominators) and `schema_version`/`generated_at` differ. Any other change (a stat correction) goes into the PR description.

- [ ] **Step 2: Build and eyeball**

```bash
.venv/Scripts/python -m src.editorial check --all
.venv/Scripts/python -m src.site build --out _site --check
.venv/Scripts/python scripts/check_explorer.py
```

- [ ] **Step 3: Rebuild Week 1 (and Week 3 once it is published) the same way, commit each week separately**

```bash
git add editions/2026-week-02 && git commit -S -m "Rebuild Week 2 with every recorded play" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git add editions/2026-week-01 && git commit -S -m "Rebuild Week 1 with every recorded play" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Push; open PR 5 with the canary diff summary; after merge, verify live: `/players/`, one evergreen page, one week page (explorer works, phone width), a homepage strip.
