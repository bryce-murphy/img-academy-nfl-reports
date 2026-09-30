# Roster Moves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect when an alum changes or leaves an NFL team, show it on his card (or Availability desk entry) and player page, and let the owner back the reason with a sourced note in `editorial.toml`.

**Architecture:** A new pure module `src/moves.py` owns detection (comparing this week's team, today's roster and earlier published editions), the allowed-source list and the sentences. `src/edition.py` attaches a `move` to every player (schema 3) and gains a `--rebuild` mode that keeps published roster facts. `src/editorial.py` validates and writes `[[roster_moves]]` notes. `src/pipeline.py` lists moves in the edition PR and drafts commented stubs. `src/site.py` renders one shared `_move.html` line.

**Tech Stack:** Python 3.12 stdlib (`tomllib`, `urllib.parse`, `datetime`), Jinja2 templates, stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-30-roster-moves-design.md`

## Global Constraints

- Missing values are `None`/null, never zero. A blank is never a zero.
- Public copy says "IMG Academy" in full, never "IMG" alone; never "not affiliated".
- Never claim injury, illness or benching; move notes pass `editorial.BLOCKED_TERMS`.
- A move's reason (traded, claimed, signed, waived) appears only from an owner note with an allowed source; only the data's own statuses (released, retired) appear without one.
- Automation never rewrites a merged `editions/<id>/` directory. `--rebuild` is a manual, owner-reviewed path.
- Allowed source domains: `nfl.com`, `operations.nfl.com`, `espn.com`, `apnews.com` and the 32 team sites listed in Task 3. No paywalled outlets.
- `details`: at most 100 characters.
- Add a regression test with every accuracy fix. Test output stays silent.
- The `move` object carries three fields beyond the spec's example for rendering and checks: `from_color`, `to_color` (team colors, `None` when there is no team) and `last_game_date` (`"YYYY-MM-DD"` of the player's game in `last_week_with_old_team`, or `None`).
- Commits: signed, `git commit -S`, trailer `Co-Authored-By: <model> <noreply@anthropic.com>`.

## Review Focus

1. **An uncommented but unedited stub** (`date = YYYY-MM-DD`) makes `editorial.toml` invalid TOML: `src.editorial check` must print an `::error` naming the file, not a traceback (Task 4, `test_invalid_toml_is_a_clean_error`).
2. **Look-alike and unusual links**: `https://giants.com.evil.test/`, `https://giants.com@evil.test/`, `https://GIANTS.com/x` (uppercase), `https://www.giants.com:8443/x` (port): only the uppercase one is allowed (Task 3, `test_look_alike_and_odd_hosts`).
3. **A TOML datetime instead of a date** (`date = 2026-09-28T10:00:00`) is an error, not a crash (Task 4, `test_date_must_be_a_plain_date`).
4. **Older editions**: schema 2 editions have no `move`, and a note in one must not crash the site (Task 6, `test_schema_2_editions_and_orphan_notes_render`).
5. **`details` ending in a period** must not produce ".." (Task 3, `test_details_trailing_period_is_not_doubled`).

---

### Task 1: Detect moves (`src/moves.py`)

**Files:**
- Create: `src/moves.py`
- Test: `tests/test_moves.py`

**Interfaces:**
- Produces:
  - `moves.week_team(player: dict) -> str | None`: this week's NFL team, `None` when the availability label is "Not on an NFL roster" or "Released".
  - `moves.now_team(player: dict) -> str | None`: today's team from `player["current"]`, `None` when the status is `CUT` or `RET` or the team is blank.
  - `moves.departure_status(player: dict) -> str`: `"RET"`, `"CUT"` or `"none"`.
  - `moves.detect(player: dict, week: int, games: list[dict], history: list[dict], team_name: Callable[[str], str], team_color: Callable[[str], str]) -> dict | None`. `games` are this edition's games (each with `game_id`, `gameday`). `history` holds earlier edition dicts of the same season, sorted by week ascending.
  - `moves.load_history(root: Path, season: int, week: int) -> list[dict]`
  - `moves.moved_players(edition: dict) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_moves.py`:

```python
import unittest

from src import moves

NAMES = {"MIN": "Minnesota Vikings", "NYG": "New York Giants", "CLE": "Cleveland Browns"}
COLORS = {"MIN": "#4F2683", "NYG": "#0B2265", "CLE": "#311D00"}


def player(team="MIN", label="Played", now="MIN", status="ACT", game_id="g", pid="p1"):
    return {
        "id": pid, "name": "J.J. McCarthy", "team": team,
        "availability": {"label": label, "evidence": ""},
        "current": {"team": now, "roster_status": status, "roster_label": ""},
        "game": {"game_id": game_id} if game_id else None,
    }


def edition(week, *players, gameday="2026-09-20"):
    return {"season": 2026, "week": week, "games": [{"game_id": "g", "gameday": gameday}], "players": list(players)}


def detect(p, week=3, history=(), gameday="2026-09-27"):
    return moves.detect(p, week, [{"game_id": "g", "gameday": gameday}], list(history), NAMES.get, COLORS.get)


class DetectTests(unittest.TestCase):
    def test_no_move(self):
        self.assertIsNone(detect(player(), history=[edition(2, player())]))

    def test_moved_after_game(self):
        move = detect(player(now="NYG"))
        self.assertEqual(move, {
            "kind": "moved_after_game", "from": "MIN", "to": "NYG",
            "from_name": "Minnesota Vikings", "to_name": "New York Giants",
            "from_color": "#4F2683", "to_color": "#0B2265",
            "status": None, "last_week_with_old_team": 3, "last_game_date": "2026-09-27",
        })

    def test_first_week_with_new_team(self):
        before = edition(3, player(now="NYG"), gameday="2026-09-27")
        move = detect(player(team="NYG", now="NYG"), week=4, history=[before])
        self.assertEqual((move["kind"], move["from"], move["to"], move["last_week_with_old_team"], move["last_game_date"]),
                         ("first_week", "MIN", "NYG", 3, "2026-09-27"))

    def test_first_week_even_when_inactive_for_new_team(self):
        before = edition(3, player())
        move = detect(player(team="NYG", label="Inactive for the game", now="NYG"), week=4, history=[before])
        self.assertEqual(move["kind"], "first_week")

    def test_left_after_game_released(self):
        move = detect(player(now="MIN", status="CUT"))
        self.assertEqual((move["kind"], move["to"], move["to_name"], move["to_color"], move["status"]),
                         ("left_after_game", None, None, None, "CUT"))

    def test_left_after_game_retired_and_missing(self):
        self.assertEqual(detect(player(now="MIN", status="RET"))["status"], "RET")
        self.assertEqual(detect(player(now="", status=""))["status"], "none")

    def test_left_before_week(self):
        before = edition(3, player())
        gone = player(team="", label="Not on an NFL roster", now="", status="", game_id=None)
        move = detect(gone, week=4, history=[before])
        self.assertEqual((move["kind"], move["from"], move["status"], move["last_week_with_old_team"]),
                         ("left_before_week", "MIN", "none", 3))

    def test_released_label_this_week_is_off_the_team(self):
        before = edition(3, player())
        cut = player(team="MIN", label="Released", now="MIN", status="CUT", game_id="g")
        move = detect(cut, week=4, history=[before])
        self.assertEqual((move["kind"], move["status"]), ("left_before_week", "CUT"))

    def test_off_every_roster_for_a_second_week_is_not_a_move(self):
        gone = player(team="", label="Not on an NFL roster", now="", status="", game_id=None)
        history = [edition(3, player()), edition(4, gone)]
        self.assertIsNone(detect(gone, week=5, history=history))

    def test_re_signing_after_release_is_a_first_week_from_the_last_team(self):
        gone = player(team="", label="Not on an NFL roster", now="", status="", game_id=None)
        history = [edition(3, player(), gameday="2026-09-27"), edition(4, gone)]
        move = detect(player(team="CLE", now="CLE"), week=5, history=history)
        self.assertEqual((move["kind"], move["from"], move["to"], move["last_week_with_old_team"]), ("first_week", "MIN", "CLE", 3))

    def test_re_signing_with_the_same_team_is_not_a_move(self):
        gone = player(team="", label="Not on an NFL roster", now="", status="", game_id=None)
        history = [edition(3, player()), edition(4, gone)]
        self.assertIsNone(detect(player(), week=5, history=history))

    def test_later_change_wins_over_arrival(self):
        before = edition(3, player())
        move = detect(player(team="NYG", now="CLE"), week=4, history=[before])
        self.assertEqual((move["kind"], move["from"], move["to"], move["last_week_with_old_team"]), ("moved_after_game", "NYG", "CLE", 4))

    def test_no_previous_edition_means_no_arrival_or_departure(self):
        self.assertIsNone(detect(player(team="NYG", now="NYG"), week=1))
        gone = player(team="", label="Not on an NFL roster", now="", status="", game_id=None)
        self.assertIsNone(detect(gone, week=1))

    def test_new_registry_player_has_no_arrival(self):
        other = player(pid="someone-else")
        self.assertIsNone(detect(player(team="NYG", now="NYG"), week=4, history=[edition(3, other)]))

    def test_two_moves_in_one_week_show_the_net_change(self):
        before = edition(3, player())
        move = detect(player(team="CLE", now="CLE"), week=4, history=[before])
        self.assertEqual((move["from"], move["to"]), ("MIN", "CLE"))

    def test_no_game_date_when_old_team_had_no_game(self):
        self.assertIsNone(detect(player(now="NYG", game_id=None))["last_game_date"])


class HistoryTests(unittest.TestCase):
    def test_load_history_reads_earlier_weeks_of_the_season_in_order(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for eid, week in (("2026-week-02", 2), ("2026-week-01", 1), ("2026-week-03", 3), ("2025-week-17", 17)):
                (root / eid).mkdir()
                (root / eid / "edition.json").write_text(json.dumps({"season": int(eid[:4]), "week": week, "players": []}), encoding="utf-8")
            self.assertEqual([e["week"] for e in moves.load_history(root, 2026, 3)], [1, 2])
            self.assertEqual(moves.load_history(root / "missing", 2026, 3), [])

    def test_moved_players(self):
        e = {"players": [{"id": "a", "move": None}, {"id": "b", "move": {"kind": "first_week"}}, {"id": "c"}]}
        self.assertEqual([p["id"] for p in moves.moved_players(e)], ["b"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_moves.py"`
Expected: FAIL with `ImportError: cannot import name 'moves'`.

- [ ] **Step 3: Implement**

Create `src/moves.py`:

```python
"""Roster moves: detection against earlier editions, allowed sources and the sentences. Pure functions."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import evidence as ev

OFF_STATUSES = {"CUT", "RET"}
OFF_LABELS = {ev.NOT_ON_ROSTER, "Released"}
EDITION_DIR = re.compile(r"(\d{4})-week-(\d{2})")


def week_team(player):
    if player["availability"]["label"] in OFF_LABELS:
        return None
    return player.get("team") or None


def now_team(player):
    current = player.get("current") or {}
    if current.get("roster_status") in OFF_STATUSES:
        return None
    return current.get("team") or None


def departure_status(player):
    status = (player.get("current") or {}).get("roster_status")
    if status == "RET":
        return "RET"
    if status == "CUT" or player["availability"]["label"] == "Released":
        return "CUT"
    return "none"


def _game_date(games, player):
    game_id = (player.get("game") or {}).get("game_id")
    return next((g["gameday"] for g in games if g["game_id"] == game_id), None) if game_id else None


def detect(player, week, games, history, team_name, team_color):
    """Return the player's roster move for this edition, or None. See the spec's §1 tables."""
    def move(kind, old, new, last_week, last_date):
        return {
            "kind": kind, "from": old, "to": new,
            "from_name": team_name(old), "to_name": team_name(new) if new else None,
            "from_color": team_color(old), "to_color": team_color(new) if new else None,
            "status": None if new else departure_status(player),
            "last_week_with_old_team": last_week, "last_game_date": last_date,
        }

    this, now = week_team(player), now_team(player)
    if this and now != this:
        return move("moved_after_game" if now else "left_after_game", this, now, week, _game_date(games, player))
    earlier = [(e, q) for e in history for q in e["players"] if q["id"] == player["id"]]
    previous = history[-1] if history else None
    before_player = next((q for e, q in earlier if e is previous), None)
    before = week_team(before_player) if before_player else None
    if before and this != before:
        kind = "first_week" if this else "left_before_week"
        return move(kind, before, this, previous["week"], _game_date(previous["games"], before_player))
    if this and before is None:
        last = next(((e, q) for e, q in reversed(earlier) if week_team(q)), None)
        if last and week_team(last[1]) != this:
            return move("first_week", week_team(last[1]), this, last[0]["week"], _game_date(last[0]["games"], last[1]))
    return None


def load_history(root, season, week):
    """Earlier published editions of the same season, oldest first."""
    found = []
    root = Path(root)
    if not root.is_dir():
        return found
    for directory in root.iterdir():
        match = EDITION_DIR.fullmatch(directory.name)
        if match and int(match[1]) == season and int(match[2]) < week and (directory / "edition.json").is_file():
            found.append(json.loads((directory / "edition.json").read_text(encoding="utf-8")))
    return sorted(found, key=lambda e: e["week"])


def moved_players(edition):
    return [p for p in edition["players"] if p.get("move")]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_moves.py"`
Expected: PASS (17 tests), no other output.

- [ ] **Step 5: Commit**

```bash
git add src/moves.py tests/test_moves.py
git commit -S -m "Detect roster moves against earlier editions" -m "Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 2: Attach moves to editions (schema 3) and the `--rebuild` mode

**Files:**
- Modify: `src/edition.py` (`SCHEMA_VERSION`, `build_edition`, `build_week`, `main`)
- Modify: `tests/fixtures/week02/expected_edition.json` (regenerated golden)
- Modify: `tests/test_pipeline.py` (isolate history)
- Test: `tests/test_edition.py`, `tests/test_moves.py`

**Interfaces:**
- Consumes: `moves.detect`, `moves.load_history` (Task 1).
- Produces:
  - `edition.EDITIONS_ROOT = ROOT / "editions"`
  - `build_edition(..., history=(), keep=None)`: `keep` maps player id → published player dict.
  - `build_week(..., editions_root=None, keep=None)`
  - `python -m src.edition --season S --week W [--historical] --rebuild`
  - `edition.KEEP_FIELDS = ("current", "position", "team_changed")`
  - Every player dict has a `move` key (`None` or a move dict). `SCHEMA_VERSION = 3`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_edition.py` (the `fixture_data` import is already there; add `from src import edition as edition_module` and `from src import moves` if missing):

```python
class MoveAttachTests(unittest.TestCase):
    def build(self, **kwargs):
        data, _, registry = fixture_data.load()
        games = fixture_data.week_games(data)
        return edition_module.build_edition(data, registry, games, 2026, 2, generated_at=fixture_data.GENERATED_AT, **kwargs)

    def test_schema_3_every_player_has_a_move_key(self):
        e = self.build()
        self.assertEqual(e["schema_version"], 3)
        self.assertTrue(all("move" in p for p in e["players"]))

    def test_history_produces_first_week_moves(self):
        e = self.build()
        target = next(p for p in e["players"] if moves.week_team(p) and moves.now_team(p) == moves.week_team(p))
        earlier = {"season": 2026, "week": 1, "games": [], "players": [dict(target, team="ZZZ", availability={"label": "Played", "evidence": ""}, game=None)]}
        again = self.build(history=[earlier])
        moved = next(p for p in again["players"] if p["id"] == target["id"])
        self.assertEqual((moved["move"]["kind"], moved["move"]["from"], moved["move"]["to"]), ("first_week", "ZZZ", target["team"]))

    def test_keep_restores_published_roster_facts_and_move(self):
        e = self.build()
        target = e["players"][0]
        published = dict(target, current={"team": "OLD", "roster_status": "ACT", "roster_label": "Active roster"},
                         position="XX", team_changed=True, move={"kind": "moved_after_game", "from": "A", "to": "B"})
        again = self.build(keep={target["id"]: published})
        kept = next(p for p in again["players"] if p["id"] == target["id"])
        self.assertEqual((kept["current"]["team"], kept["position"], kept["team_changed"], kept["move"]["to"]), ("OLD", "XX", True, "B"))

    def test_keep_without_a_published_move_recomputes_from_published_roster(self):
        e = self.build()
        target = next(p for p in e["players"] if p["availability"]["label"] == "Played")
        published = {k: v for k, v in target.items() if k != "move"}
        published["current"] = dict(target["current"], team="ZZZ", roster_status="ACT")
        again = self.build(keep={target["id"]: published})
        kept = next(p for p in again["players"] if p["id"] == target["id"])
        self.assertEqual((kept["move"]["kind"], kept["move"]["to"]), ("moved_after_game", "ZZZ"))
```

Add to `tests/test_moves.py` (real published data; editions are never rewritten by automation):

```python
class RealDataTests(unittest.TestCase):
    def test_mccarthy_week_3_is_a_move_after_the_game(self):
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "editions"
        week3 = json.loads((root / "2026-week-03" / "edition.json").read_text(encoding="utf-8"))
        mccarthy = next(p for p in week3["players"] if p["name"] == "J.J. McCarthy")
        gameday = next(g["gameday"] for g in week3["games"] if g["game_id"] == mccarthy["game"]["game_id"])
        move = moves.detect(mccarthy, 3, week3["games"], moves.load_history(root, 2026, 3), NAMES.get, COLORS.get)
        self.assertEqual((move["kind"], move["from"], move["to"], move["last_week_with_old_team"], move["last_game_date"]),
                         ("moved_after_game", "MIN", "NYG", 3, gameday))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_edition.py"`
Expected: FAIL (`schema_version` is 2; `build_edition() got an unexpected keyword argument 'history'`). `RealDataTests` already passes (it uses Task 1 only).

- [ ] **Step 3: Implement**

In `src/edition.py`:

```python
from . import moves  # with the other relative imports

SCHEMA_VERSION = 3
EDITIONS_ROOT = ROOT / "editions"
KEEP_FIELDS = ("current", "position", "team_changed")
```

In `build_edition`, change the signature and add the move pass right after `players = [...]`:

```python
def build_edition(data, registry, games, season, week, *, generated_at, historical=False, warnings=(), history=(), keep=None):
    warnings = list(warnings)
    wk = _Week(data, games, season, week, historical, ev.validate_games(games, data["pbp"]))
    players = [player_record(alum, wk, warnings) for alum in registry]
    keep = keep or {}
    for p in players:
        published = keep.get(p["id"])
        if published:
            p.update({k: published[k] for k in KEEP_FIELDS if k in published})
        if published and "move" in published:
            p["move"] = published["move"]
        else:
            p["move"] = moves.detect(p, week, games, list(history), wk.team_name, wk.team_color)
```

In `build_week`:

```python
def build_week(season, week, games, *, historical, final, registry, sources=fetch, editions_root=None, keep=None):
    ...
    edition = build_edition(
        data, registry, games, season, week,
        generated_at=utcnow().isoformat(timespec="seconds"), historical=historical, warnings=warnings,
        history=moves.load_history(editions_root or EDITIONS_ROOT, season, week), keep=keep,
    )
```

In `main`, add the flag and pass `keep`:

```python
    parser.add_argument("--rebuild", action="store_true",
                        help="Rebuild a published edition, keeping its roster notes, positions, team-change flags and moves")
    ...
    week, games = due_week(...)
    keep = None
    if args.rebuild:
        published = args.out / edition_id(args.season, week) / "edition.json"
        if not published.is_file():
            parser.error(f"--rebuild needs a published {published}")
        keep = {p["id"]: p for p in json.loads(published.read_text(encoding="utf-8"))["players"]}
    edition, manifest, report = build_week(args.season, week, games, historical=args.historical, final=True,
                                           registry=load_registry(), editions_root=args.out, keep=keep)
```

Then regenerate the golden file and confirm the only differences are `schema_version` 2 → 3 and `"move": null` on every player:

```bash
UPDATE_GOLDEN=1 .venv/Scripts/python -m unittest discover -s tests -p "test_edition.py"
git diff --stat tests/fixtures/week02/expected_edition.json
git diff tests/fixtures/week02/expected_edition.json | grep '^[+-] ' | sort | uniq -c
```

Expected: `+ "move": null,` once per player, and the `schema_version` line.

In `tests/test_pipeline.py`, isolate the pipeline from the repository's real editions. `PipelineTests.setUp` becomes:

```python
    def setUp(self):
        self.data, self.manifest, self.registry = fixture_data.load()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = unittest.mock.patch.object(edition_module, "EDITIONS_ROOT", Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
```

with `import tempfile`, `import unittest.mock`, `from pathlib import Path` and `from src import edition as edition_module` at the top. Any other class in the file that calls `pipeline.run_attempt` gets the same four patch lines in its `setUp`.

- [ ] **Step 4: Run all tests**

Run: `.venv/Scripts/python -m unittest discover -s tests`
Expected: PASS, no output beyond the summary.

- [ ] **Step 5: Commit**

```bash
git add src/edition.py tests/test_edition.py tests/test_moves.py tests/test_pipeline.py tests/fixtures/week02/expected_edition.json
git commit -S -m "Attach roster moves to editions (schema 3); add --rebuild that keeps published roster facts" -m "Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 3: Allowed sources and sentences (`src/moves.py`)

**Files:**
- Modify: `src/moves.py`
- Test: `tests/test_moves.py`

**Interfaces:**
- Consumes: move dicts (Task 1).
- Produces:
  - `moves.ALLOWED_SOURCES: dict[str, str]` (domain → label)
  - `moves.source_label(url: str) -> str | None` (`None` = not allowed)
  - `moves.ARRIVALS = ("trade", "waiver claim", "signing")`, `moves.DEPARTURES = ("release", "waived")`, `moves.VERBS: dict[str, str]`
  - `moves.nickname(team_name: str) -> str`
  - `moves.neutral(move: dict) -> str`
  - `moves.describe(move: dict) -> str` (for the PR: "Vikings → Giants (moved after the game)")
  - `moves.sourced(move: dict, note: dict) -> str` (`note["date"]` is a `datetime.date`)
  - `moves.note_index(editions: list[tuple[dict, dict]]) -> dict` (a list of `(edition_data, editorial_copy)`, oldest first; key `(player_id, from, to)`)
  - `moves.view(player: dict, index: dict) -> dict | None` → `{"text", "source_url", "source_label", "color"}`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_moves.py`:

```python
from datetime import date

ARRIVAL = {"kind": "moved_after_game", "from": "MIN", "to": "NYG", "from_name": "Minnesota Vikings", "to_name": "New York Giants",
           "from_color": "#4F2683", "to_color": "#0B2265", "status": None, "last_week_with_old_team": 3, "last_game_date": "2026-09-27"}
DEPARTURE = dict(ARRIVAL, kind="left_after_game", to=None, to_name=None, to_color=None, status="CUT")
NOTE = {"player_id": "p1", "kind": "trade", "date": date(2026, 9, 28), "details": "for a 2027 fourth-round pick",
        "source": "https://www.giants.com/news/trade"}


class SourceTests(unittest.TestCase):
    def test_allowed_sites_and_labels(self):
        self.assertEqual(moves.source_label("https://www.giants.com/news/x"), "Giants.com")
        self.assertEqual(moves.source_label("https://operations.nfl.com/updates/x"), "NFL Football Operations")
        self.assertEqual(moves.source_label("https://www.nfl.com/news/x"), "NFL.com")
        self.assertEqual(moves.source_label("https://apnews.com/article/x"), "AP")
        self.assertEqual(moves.source_label("https://www.espn.com/nfl/story/x"), "ESPN")
        self.assertEqual(len([d for d in moves.ALLOWED_SOURCES if d not in {"nfl.com", "operations.nfl.com", "espn.com", "apnews.com"}]), 32)

    def test_rejected_links(self):
        for url in ("http://www.giants.com/x", "https://theathletic.com/x", "https://example.com/x", "giants.com/x", "", "https://nfl.com.evil.test/x"):
            self.assertIsNone(moves.source_label(url), url)

    def test_look_alike_and_odd_hosts(self):
        self.assertIsNone(moves.source_label("https://giants.com.evil.test/x"))
        self.assertIsNone(moves.source_label("https://giants.com@evil.test/x"))
        self.assertIsNone(moves.source_label("https://www.giants.com:8443/x"))
        self.assertEqual(moves.source_label("https://GIANTS.com/x"), "Giants.com")


class SentenceTests(unittest.TestCase):
    def test_neutral_lines(self):
        self.assertEqual(moves.neutral(ARRIVAL), "Now on the Giants' roster (was Vikings in Week 3).")
        self.assertEqual(moves.neutral(dict(ARRIVAL, kind="first_week")), "First week with the Giants (was Vikings in Week 3).")
        self.assertEqual(moves.neutral(DEPARTURE), "Released by the Vikings (on their roster in Week 3).")
        self.assertEqual(moves.neutral(dict(DEPARTURE, status="RET")), "Listed as retired (on the Vikings' roster in Week 3).")
        self.assertEqual(moves.neutral(dict(DEPARTURE, status="none", kind="left_before_week")), "No longer on the Vikings' roster (last listed in Week 3).")

    def test_describe_for_the_pr(self):
        self.assertEqual(moves.describe(ARRIVAL), "Vikings → Giants (moved after the game)")
        self.assertEqual(moves.describe(dict(DEPARTURE, kind="left_before_week")), "left the Vikings (left before this week)")

    def test_sourced_sentences(self):
        self.assertEqual(moves.sourced(ARRIVAL, NOTE), "Traded to the Giants on Sep 28 for a 2027 fourth-round pick.")
        self.assertEqual(moves.sourced(ARRIVAL, dict(NOTE, details="")), "Traded to the Giants on Sep 28.")
        self.assertEqual(moves.sourced(ARRIVAL, dict(NOTE, kind="waiver claim")), "Claimed off waivers by the Giants on Sep 28 for a 2027 fourth-round pick.")
        self.assertEqual(moves.sourced(DEPARTURE, dict(NOTE, kind="waived", details="")), "Waived by the Vikings on Sep 28.")
        self.assertEqual(moves.sourced(DEPARTURE, dict(NOTE, kind="release", details="")), "Released by the Vikings on Sep 28.")

    def test_details_trailing_period_is_not_doubled(self):
        self.assertEqual(moves.sourced(ARRIVAL, dict(NOTE, details="for a 2027 fourth-round pick.")),
                         "Traded to the Giants on Sep 28 for a 2027 fourth-round pick.")

    def test_view_prefers_a_matching_note_from_any_edition(self):
        week3 = {"week": 3, "players": [{"id": "p1", "move": ARRIVAL}]}
        week4_player = {"id": "p1", "move": dict(ARRIVAL, kind="first_week")}
        index = moves.note_index([(week3, {"roster_moves": [NOTE]}), ({"week": 4, "players": [week4_player]}, {})])
        shown = moves.view(week4_player, index)
        self.assertEqual(shown, {"text": "Traded to the Giants on Sep 28 for a 2027 fourth-round pick.",
                                 "source_url": NOTE["source"], "source_label": "Giants.com", "color": "#0B2265"})

    def test_earliest_note_wins_and_neutral_without_note(self):
        week3 = {"week": 3, "players": [{"id": "p1", "move": ARRIVAL}]}
        week4 = {"week": 4, "players": [{"id": "p1", "move": dict(ARRIVAL, kind="first_week")}]}
        later = dict(NOTE, details="later text")
        index = moves.note_index([(week3, {"roster_moves": [NOTE]}), (week4, {"roster_moves": [later]})])
        self.assertIn("fourth-round", moves.view(week4["players"][0], index)["text"])
        self.assertEqual(moves.view({"id": "p1", "move": DEPARTURE}, {}),
                         {"text": "Released by the Vikings (on their roster in Week 3).", "source_url": None, "source_label": None, "color": "#4F2683"})
        self.assertIsNone(moves.view({"id": "p1", "move": None}, index))
        self.assertIsNone(moves.view({"id": "p1"}, index))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_moves.py"`
Expected: FAIL with `AttributeError: module 'src.moves' has no attribute 'source_label'`.

- [ ] **Step 3: Implement**

Append to `src/moves.py` (add `from urllib.parse import urlsplit` and `from .upnext import MONTHS` to the imports):

```python
TEAM_SITES = {
    "azcardinals.com": "AZCardinals.com", "atlantafalcons.com": "AtlantaFalcons.com", "baltimoreravens.com": "BaltimoreRavens.com",
    "buffalobills.com": "BuffaloBills.com", "panthers.com": "Panthers.com", "chicagobears.com": "ChicagoBears.com",
    "bengals.com": "Bengals.com", "clevelandbrowns.com": "ClevelandBrowns.com", "dallascowboys.com": "DallasCowboys.com",
    "denverbroncos.com": "DenverBroncos.com", "detroitlions.com": "DetroitLions.com", "packers.com": "Packers.com",
    "houstontexans.com": "HoustonTexans.com", "colts.com": "Colts.com", "jaguars.com": "Jaguars.com",
    "chiefs.com": "Chiefs.com", "raiders.com": "Raiders.com", "chargers.com": "Chargers.com", "therams.com": "TheRams.com",
    "miamidolphins.com": "MiamiDolphins.com", "vikings.com": "Vikings.com", "patriots.com": "Patriots.com",
    "neworleanssaints.com": "NewOrleansSaints.com", "giants.com": "Giants.com", "newyorkjets.com": "NewYorkJets.com",
    "philadelphiaeagles.com": "PhiladelphiaEagles.com", "steelers.com": "Steelers.com", "49ers.com": "49ers.com",
    "seahawks.com": "Seahawks.com", "buccaneers.com": "Buccaneers.com", "tennesseetitans.com": "TennesseeTitans.com",
    "commanders.com": "Commanders.com",
}
ALLOWED_SOURCES = {"operations.nfl.com": "NFL Football Operations", "nfl.com": "NFL.com", "espn.com": "ESPN", "apnews.com": "AP", **TEAM_SITES}
ARRIVALS = ("trade", "waiver claim", "signing")
DEPARTURES = ("release", "waived")
VERBS = {"trade": "Traded to", "waiver claim": "Claimed off waivers by", "signing": "Signed by", "release": "Released by", "waived": "Waived by"}
KIND_TEXT = {"moved_after_game": "moved after the game", "first_week": "first week with the new team",
             "left_after_game": "left after the game", "left_before_week": "left before this week"}


def source_label(url):
    """The outlet label for an allowed https link, or None. Hosts match exactly or as a subdomain."""
    if not isinstance(url, str):
        return None
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or parts.username or parts.password or parts.port or not parts.hostname:
        return None
    host = parts.hostname.lower()
    for domain in sorted(ALLOWED_SOURCES, key=len, reverse=True):
        if host == domain or host.endswith("." + domain):
            return ALLOWED_SOURCES[domain]
    return None


def nickname(team_name):
    return team_name.split()[-1] if team_name else ""


def neutral(move):
    old, week = nickname(move["from_name"]), move["last_week_with_old_team"]
    if move["to"]:
        new = nickname(move["to_name"])
        if move["kind"] == "first_week":
            return f"First week with the {new} (was {old} in Week {week})."
        return f"Now on the {new}' roster (was {old} in Week {week})."
    if move["status"] == "CUT":
        return f"Released by the {old} (on their roster in Week {week})."
    if move["status"] == "RET":
        return f"Listed as retired (on the {old}' roster in Week {week})."
    return f"No longer on the {old}' roster (last listed in Week {week})."


def describe(move):
    if move["to"]:
        return f"{nickname(move['from_name'])} → {nickname(move['to_name'])} ({KIND_TEXT[move['kind']]})"
    return f"left the {nickname(move['from_name'])} ({KIND_TEXT[move['kind']]})"


def sourced(move, note):
    team = nickname(move["to_name"] if note["kind"] in ARRIVALS else move["from_name"])
    day = note["date"]
    details = (note.get("details") or "").strip().rstrip(".").strip()
    return f"{VERBS[note['kind']]} the {team} on {MONTHS[day.month - 1]} {day.day}{' ' + details if details else ''}."


def note_index(editions):
    """(player id, from, to) -> the earliest edition's note for that move. `editions` is oldest first."""
    index = {}
    for data, copy in editions:
        players = {p["id"]: p for p in data.get("players", [])}
        for note in (copy or {}).get("roster_moves", []) or []:
            move = (players.get(note.get("player_id")) or {}).get("move")
            if move:
                index.setdefault((note["player_id"], move["from"], move["to"]), note)
    return index


def view(player, index):
    move = player.get("move")
    if not move:
        return None
    note = index.get((player["id"], move["from"], move["to"]))
    color = move.get("to_color") or move.get("from_color")
    if note:
        return {"text": sourced(move, note), "source_url": note["source"], "source_label": source_label(note["source"]), "color": color}
    return {"text": neutral(move), "source_url": None, "source_label": None, "color": color}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_moves.py"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/moves.py tests/test_moves.py
git commit -S -m "Roster move sentences, allowed sources and note lookup" -m "Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 4: Validate and write `[[roster_moves]]` notes (`src/editorial.py`)

**Files:**
- Modify: `src/editorial.py` (`dumps`, `review`, `check`; new `check_roster_notes`, `roster_note_warnings`)
- Test: `tests/test_editorial.py`

**Interfaces:**
- Consumes: `moves.source_label`, `moves.ARRIVALS`, `moves.VERBS`, `moves.nickname`, `moves.describe`, `moves.moved_players` (Tasks 1 and 3).
- Produces:
  - `editorial.dumps(copy: dict, stubs: list[dict] = ()) -> str`. It writes `copy["roster_moves"]` entries, then one commented stub per player in `stubs` who has no note yet.
  - `editorial.check_roster_notes(notes, edition) -> list[str]`: errors, added to `review(...).errors`.
  - `editorial.roster_note_warnings(copy, edition) -> list[str]`, printed as warnings by `check`.
  - `DETAILS_LIMIT = 100`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_editorial.py` (add `import copy as copy_module`, `import tempfile`, `from datetime import date, datetime` and `from pathlib import Path` if missing):

```python
MOVE = {"kind": "moved_after_game", "from": "MIN", "to": "NYG", "from_name": "Minnesota Vikings", "to_name": "New York Giants",
        "from_color": "#4F2683", "to_color": "#0B2265", "status": None, "last_week_with_old_team": 2, "last_game_date": "2026-09-20"}


def moved_edition():
    e = fixture_data.golden_edition()
    e["players"][0]["move"] = dict(MOVE)
    return e


def note(**changes):
    base = {"player_id": fixture_data.golden_edition()["players"][0]["id"], "kind": "trade", "date": date(2026, 9, 21),
            "details": "for a 2027 fourth-round pick", "source": "https://www.giants.com/news/x"}
    base.update(changes)
    return base


class RosterNoteTests(unittest.TestCase):
    def errors(self, *notes, edition=None):
        return editorial.check_roster_notes(list(notes), edition or moved_edition())

    def test_valid_note(self):
        self.assertEqual(self.errors(note()), [])
        self.assertEqual(self.errors(note(details="")), [])
        self.assertEqual(self.errors({k: v for k, v in note().items() if k != "details"}), [])

    def test_each_rule(self):
        cases = {
            "has no roster move": note(player_id="nobody"),
            "kind must be one of": note(kind="swap"),
            "does not fit": note(kind="release"),
            "after this edition's data": note(date=date(2026, 9, 24)),
            "before his game": note(date=date(2026, 9, 19)),
            "allowed site": note(source="https://theathletic.com/x"),
            "the limit is 100": note(details="x" * 101),
            "one line": note(details="for a\npick"),
            "link": note(details="see www.giants.com"),
            '"IMG" alone': note(details="an IMG alum"),
            "uses 'injur'": note(details="after an injury"),
            "repeats the team": note(details="to the Giants for a pick"),
            "repeats the date": note(details="on Sep 28 for a pick"),
            "unknown fields": note(team="NYG"),
        }
        for expected, bad in cases.items():
            with self.subTest(expected):
                self.assertTrue(any(expected in e for e in self.errors(bad)), self.errors(bad))

    def test_departure_kinds_need_a_departure(self):
        e = moved_edition()
        e["players"][0]["move"] = dict(MOVE, kind="left_after_game", to=None, to_name=None, to_color=None, status="CUT")
        self.assertEqual(self.errors(note(kind="release", details=""), edition=e), [])
        self.assertTrue(any("does not fit" in m for m in self.errors(note(kind="trade"), edition=e)))

    def test_duplicate_player(self):
        self.assertTrue(any("already has a note" in m for m in self.errors(note(), note())))

    def test_date_must_be_a_plain_date(self):
        self.assertTrue(any("date must be a date" in m for m in self.errors(note(date=datetime(2026, 9, 21, 10, 0)))))
        self.assertTrue(any("date must be a date" in m for m in self.errors(note(date="2026-09-21"))))

    def test_review_reports_note_errors(self):
        e = moved_edition()
        copy_ = dict(editorial.fallback(e), roster_moves=[note(source="https://example.com/x")])
        self.assertTrue(any("allowed site" in m for m in editorial.review(copy_, e).errors))

    def test_warnings(self):
        e = moved_edition()
        name = e["players"][0]["name"]
        self.assertEqual(editorial.roster_note_warnings(editorial.fallback(e), e),
                         [f"{name} has a roster move with no sourced note; the site shows the neutral line"])
        self.assertEqual(editorial.roster_note_warnings(dict(editorial.fallback(e), roster_moves=[note()]), e),
                         ["Roster move notes: avoid paywalled stories (for example ESPN+)"])

    def test_dumps_round_trips_notes_and_writes_commented_stubs(self):
        e = moved_edition()
        text = editorial.dumps(dict(editorial.fallback(e), roster_moves=[note()]))
        self.assertEqual(editorial.loads(text)["roster_moves"], [note()])
        stub_text = editorial.dumps(editorial.fallback(e), stubs=[e["players"][0]])
        self.assertIn("# [[roster_moves]]", stub_text)
        self.assertIn(f'# player_id = "{e["players"][0]["id"]}"', stub_text)
        self.assertIn("Vikings → Giants (moved after the game)", stub_text)
        self.assertNotIn("roster_moves", editorial.loads(stub_text))
        noted = editorial.dumps(dict(editorial.fallback(e), roster_moves=[note()]), stubs=[e["players"][0]])
        self.assertNotIn("# [[roster_moves]]", noted)

    def test_headline_fact_sheet_never_sees_moves(self):
        e = moved_edition()
        e["players"][0]["move"]["to_name"] = "Marker Team Zebras"
        self.assertNotIn("Zebras", json.dumps(editorial.fact_sheet(e)))

    def test_invalid_toml_is_a_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = fixture_data.write_edition_dir(Path(tmp), fixture_data.golden_edition())
            (directory / "editorial.toml").write_text(editorial.dumps(editorial.fallback(fixture_data.golden_edition())) + "[[roster_moves]]\ndate = YYYY-MM-DD\n", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = editorial.check([directory])
        self.assertEqual(status, 1)
        self.assertIn("::error file=", output.getvalue())
        self.assertIn("not valid TOML", output.getvalue())
```

(Add `import contextlib` and `import io` at the top of the file if missing.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_editorial.py"`
Expected: FAIL with `AttributeError: module 'src.editorial' has no attribute 'check_roster_notes'`.

- [ ] **Step 3: Implement**

In `src/editorial.py`:

```python
from datetime import date, datetime  # with the other imports
from . import moves

DETAILS_LIMIT = 100
NOTE_FIELDS = {"player_id", "kind", "date", "details", "source"}
LINKISH = re.compile(r"https?://|www\.", re.I)
MONTH_WORD = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
                        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\b")
```

Extend `dumps`:

```python
def _note_lines(note):
    lines = ["", "[[roster_moves]]", f"player_id = {_toml_string(note.get('player_id', ''))}", f"kind = {_toml_string(note.get('kind', ''))}"]
    day = note.get("date")
    lines.append(f"date = {day.isoformat()}" if isinstance(day, date) and not isinstance(day, datetime) else f"date = {_toml_string(day or '')}")
    if note.get("details"):
        lines.append(f"details = {_toml_string(note['details'])}")
    lines.append(f"source = {_toml_string(note.get('source', ''))}")
    return lines


def _stub_lines(player):
    kinds = " | ".join(moves.ARRIVALS if player["move"]["to"] else moves.DEPARTURES)
    return [
        "",
        f"# Roster move: {player['name']}, {moves.describe(player['move'])}.",
        "# To say why, uncomment the lines below and fill them in with a link from an allowed site (docs/OPERATIONS.md).",
        "# [[roster_moves]]",
        f"# player_id = {_toml_string(player['id'])}",
        f'# kind = ""                 # {kinds}',
        "# date = YYYY-MM-DD",
        '# details = ""              # optional, your words from the source',
        '# source = "https://"',
    ]


def dumps(copy, stubs=()):
    lines = [
        f"schema = {SCHEMA}",
        f"source = {_toml_string(copy.get('source', 'owner'))}",
        f"model = {_toml_string(copy.get('model', ''))}",
        f"featured_player_id = {_toml_string(copy.get('featured_player_id', ''))}",
        f"headline = {_toml_string(copy['headline'])}",
        f"dek = {_toml_string(copy['dek'])}",
        f"lead = {_toml_string(copy['lead'])}",
        "alternates = [" + ", ".join(_toml_string(a) for a in copy.get("alternates", [])) + "]",
    ]
    notes = copy.get("roster_moves") or []
    for entry in notes:
        lines += _note_lines(entry)
    noted = {entry.get("player_id") for entry in notes}
    for player in stubs:
        if player.get("move") and player["id"] not in noted:
            lines += _stub_lines(player)
    return "\n".join(lines) + "\n"
```

Add the checks:

```python
def _details_problems(details, move):
    if not details:
        return []
    if not isinstance(details, str):
        return ["details must be text"]
    problems = []
    if len(details) > DETAILS_LIMIT:
        problems.append(f"details is {len(details)} characters; the limit is {DETAILS_LIMIT}")
    if CONTROL.search(details):
        problems.append("details must be one line")
    if LINKISH.search(details):
        problems.append("details must not contain a link; put it in source")
    if IMG_ALONE.search(details):
        problems.append('details says "IMG" alone; write "IMG Academy" in full')
    lower = details.lower()
    problems += [f"details uses '{term}'" for term in BLOCKED_TERMS if term in lower]
    code, name = (move["to"], move["to_name"]) if move["to"] else (move["from"], move["from_name"])
    if name.lower() in lower or moves.nickname(name).lower() in lower or re.search(rf"\b{re.escape(code)}\b", details):
        problems.append("details repeats the team; the sentence already names it")
    if MONTH_WORD.search(details):
        problems.append("details repeats the date; the sentence already gives it")
    return problems


def check_roster_notes(notes, edition):
    """Errors for [[roster_moves]] entries. See the spec's §2 checks table."""
    if not isinstance(notes, list):
        return ["roster_moves must be written as [[roster_moves]] tables"]
    from .site import to_eastern  # local import: site imports editorial

    latest = to_eastern(datetime.fromisoformat(edition["generated_at"].replace("Z", "+00:00"))).date()
    players = {p["id"]: p for p in edition["players"]}
    errors, seen = [], set()
    for number, entry in enumerate(notes, 1):
        if not isinstance(entry, dict):
            errors.append(f"roster_moves entry {number} must be a table")
            continue
        player = players.get(entry.get("player_id"))
        if not player or not player.get("move"):
            errors.append(f"roster_moves entry {number}: player_id {entry.get('player_id')!r} has no roster move in this edition")
            continue
        where = f"roster move note for {player['name']}"
        if player["id"] in seen:
            errors.append(f"{where}: he already has a note")
            continue
        seen.add(player["id"])
        move = player["move"]
        unknown = sorted(set(entry) - NOTE_FIELDS)
        if unknown:
            errors.append(f"{where}: unknown fields {', '.join(unknown)}")
        kind = entry.get("kind")
        if kind not in moves.VERBS:
            errors.append(f"{where}: kind must be one of {', '.join(moves.VERBS)}")
        elif (kind in moves.ARRIVALS) != bool(move["to"]):
            errors.append(f"{where}: kind '{kind}' does not fit {moves.describe(move)}")
        day = entry.get("date")
        if not isinstance(day, date) or isinstance(day, datetime):
            errors.append(f"{where}: date must be a date like 2026-09-28")
        else:
            if day > latest:
                errors.append(f"{where}: date {day.isoformat()} is after this edition's data ({latest.isoformat()})")
            if move.get("last_game_date") and day < date.fromisoformat(move["last_game_date"]):
                errors.append(f"{where}: date {day.isoformat()} is before his game on {move['last_game_date']}")
        if moves.source_label(entry.get("source")) is None:
            errors.append(f"{where}: source must be an https:// link on an allowed site (see docs/OPERATIONS.md)")
        errors += [f"{where}: {problem}" for problem in _details_problems(entry.get("details", ""), move)]
    return errors


def roster_note_warnings(copy, edition):
    noted = {entry.get("player_id") for entry in copy.get("roster_moves") or [] if isinstance(entry, dict)}
    warnings = [f"{p['name']} has a roster move with no sourced note; the site shows the neutral line"
                for p in moves.moved_players(edition) if p["id"] not in noted]
    if noted:
        warnings.append("Roster move notes: avoid paywalled stories (for example ESPN+)")
    return warnings
```

In `review`, just before `return result`:

```python
    result.errors.extend(check_roster_notes(copy.get("roster_moves", []), edition))
```

Change `check` so that a TOML error is reported cleanly and the warnings print:

```python
def check(directories):
    status = 0
    for directory in directories:
        edition = json.loads((directory / "edition.json").read_text(encoding="utf-8"))
        target = (directory / "editorial.toml").as_posix()
        try:
            copy = load(directory / "editorial.toml")
        except tomllib.TOMLDecodeError as exc:
            print(f"::error file={target}::editorial.toml is not valid TOML ({exc}); check any roster_moves lines you uncommented")
            status = 1
            continue
        result = review(copy, edition)
        for message in result.errors:
            print(f"::error file={target}::{message}")
            status = 1
        for message in result.problems + result.notes + roster_note_warnings(copy, edition):
            print(f"::warning file={target}::{message}")
    print(f"Checked {len(directories)} edition(s).")
    return status
```

- [ ] **Step 4: Run all tests**

Run: `.venv/Scripts/python -m unittest discover -s tests`
Expected: PASS. Then `.venv/Scripts/python -m src.editorial check --all` must still pass on the real editions (they have no moves yet).

- [ ] **Step 5: Commit**

```bash
git add src/editorial.py tests/test_editorial.py
git commit -S -m "Validate and write sourced roster move notes in editorial.toml" -m "Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 5: Roster moves in the edition PR and drafted stubs (`src/pipeline.py`, `src/edition.py`)

**Files:**
- Modify: `src/pipeline.py` (`run_attempt` drafting line, `pr_body`)
- Modify: `src/edition.py` (`main`: the fallback headline file)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `moves.moved_players`, `moves.describe`, `moves.neutral`, `editorial.dumps(copy, stubs=...)`.
- Produces: a PR body section headed `**Roster moves**`, and stubs in the bot-drafted `editorial.toml`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py`, next to `test_pr_body_lists_pending_charting`. Reuse the objects that test builds (`edition`, `copy`, `report`, `drafts`), exactly as that test constructs them:

```python
    def test_pr_body_lists_roster_moves(self):
        edition = fixture_data.golden_edition()
        copy = editorial.fallback(edition)
        report = {"used": "fallback", "reasons": [], "rejected": None, "notes": []}
        drafts = {"state": "withheld", "reason": "test"}
        self.assertNotIn("Roster moves", pipeline.pr_body(edition, copy, report, Readiness(), drafts, "run"))
        edition["players"][0]["move"] = dict(PIPELINE_MOVE)
        body = pipeline.pr_body(edition, copy, report, Readiness(), drafts, "run")
        name = edition["players"][0]["name"]
        self.assertIn("**Roster moves**", body)
        self.assertIn(f'- [ ] {name}: Vikings → Giants (moved after the game). Site shows: "Now on the Giants\' roster (was Vikings in Week 2)."', body)
        self.assertIn("ESPN+", body)
```

Add to `PipelineTests` (it builds the Week 2 fixture through `self.attempt`; `pipeline.build_week` is the name `run_attempt` calls):

```python
    def test_drafted_editorial_has_stubs_for_moves(self):
        original = pipeline.build_week

        def with_move(*args, **kwargs):
            edition, manifest, report = original(*args, **kwargs)
            edition["players"][0]["move"] = dict(PIPELINE_MOVE)
            return edition, manifest, report

        gh = FakeGitHub()
        with unittest.mock.patch.object(pipeline, "build_week", with_move):
            self.assertEqual(self.attempt(gh).state, "opened")
        text = gh.commits[0][2]["editions/2026-week-02/editorial.toml"].decode("utf-8")
        self.assertIn("# [[roster_moves]]", text)
        self.assertNotIn("roster_moves", editorial.loads(text))
        self.assertIn("**Roster moves**", gh.opened[0][2])
```

and at module level:

```python
PIPELINE_MOVE = {"kind": "moved_after_game", "from": "MIN", "to": "NYG", "from_name": "Minnesota Vikings", "to_name": "New York Giants",
                 "from_color": "#4F2683", "to_color": "#0B2265", "status": None, "last_week_with_old_team": 2, "last_game_date": "2026-09-20"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_pipeline.py"`
Expected: FAIL (no "Roster moves" in the body; no stub in the committed file).

- [ ] **Step 3: Implement**

In `src/pipeline.py` (add `from . import moves`):

```python
        copy, draft_report = (drafter or default_drafter(cfg))(edition)
        files[f"editions/{eid}/editorial.toml"] = editorial.dumps(copy, stubs=moves.moved_players(edition)).encode("utf-8")
```

In `pr_body`, after the `**Availability:**` lines:

```python
    moved = moves.moved_players(edition)
    if moved:
        lines += ["**Roster moves** (the site shows the neutral line unless you uncomment and fill in the entry in `editorial.toml`; "
                  "links must be on an allowed site, and avoid paywalled stories such as ESPN+):"]
        lines += [f"- [ ] {p['name']}: {moves.describe(p['move'])}. Site shows: \"{moves.neutral(p['move'])}\"" for p in moved] + [""]
```

In `src/edition.py` `main`, the fallback headline file:

```python
        headline_file.write_bytes(editorial.dumps(editorial.fallback(edition), stubs=moves.moved_players(edition)).encode("utf-8"))
```

- [ ] **Step 4: Run all tests**

Run: `.venv/Scripts/python -m unittest discover -s tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline.py src/edition.py tests/test_pipeline.py
git commit -S -m "List roster moves in the edition PR and draft commented note stubs" -m "Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 6: Show moves on cards, the Availability desk and player pages

**Files:**
- Create: `templates/_move.html`
- Modify: `templates/_card.html`, `templates/_player_head.html`, `templates/edition.html` (Availability desk), `static/styles.css`
- Modify: `src/site.py` (`build_site`, `edition_context`)
- Test: `tests/test_site.py`

**Interfaces:**
- Consumes: `moves.note_index`, `moves.view` (Task 3).
- Produces: `edition_context(edition, *, root, data_path, slugs, notes=None)`. Each player view gains `move` (the `moves.view` dict or `None`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_site.py`:

```python
MOVE = {"kind": "moved_after_game", "from": "MIN", "to": "NYG", "from_name": "Minnesota Vikings", "to_name": "New York Giants",
        "from_color": "#4F2683", "to_color": "#0B2265", "status": None, "last_week_with_old_team": 2, "last_game_date": "2026-09-20"}


class MoveRenderTests(SiteTestCase):
    def edition_with_moves(self):
        e = fixture_data.golden_edition()
        played = next(p for p in e["players"] if p["availability"]["label"] == ev.PLAYED)
        absent = next(p for p in e["players"] if p["availability"]["label"] != ev.PLAYED)
        played["move"] = dict(MOVE)
        absent["move"] = dict(MOVE, kind="left_after_game", to=None, to_name=None, to_color=None, status="CUT")
        return e, played, absent

    def test_neutral_lines_on_card_desk_and_player_page(self):
        e, played, absent = self.edition_with_moves()
        out = self.render(e)
        home = self.read(out / "index.html")
        card = next(c for c in home.split('<article class="card"')[1:] if played["name"] in c)
        self.assertIn("Now on the Giants&#39; roster (was Vikings in Week 2).", card)
        self.assertIn("--move: #0B2265", card)
        self.assertIn(f"{absent['name']}: Released by the Vikings (on their roster in Week 2).", home)
        slug = next(a["slug"] for a in load_registry(fixture_data.FIXTURES / "alumni.json") if a["gsis_id"] == played["id"])
        self.assertIn("Now on the Giants&#39; roster", self.read(out / "players" / slug / "index.html"))

    def test_sourced_note_renders_with_link(self):
        from datetime import date
        e, played, _ = self.edition_with_moves()
        copy_ = dict(editorial.fallback(e), roster_moves=[{"player_id": played["id"], "kind": "trade", "date": date(2026, 9, 21),
                                                           "details": "for a 2027 fourth-round pick", "source": "https://www.giants.com/news/x"}])
        home = self.read(self.render(e, copy_) / "index.html")
        self.assertIn("Traded to the Giants on Sep 21 for a 2027 fourth-round pick.", home)
        self.assertIn('Source: <a href="https://www.giants.com/news/x" rel="external noopener">Giants.com</a>', home)

    def test_schema_2_editions_and_orphan_notes_render(self):
        from datetime import date
        e = fixture_data.golden_edition()
        for p in e["players"]:
            p.pop("move", None)
        e["schema_version"] = 2
        copy_ = dict(editorial.fallback(e), roster_moves=[{"player_id": e["players"][0]["id"], "kind": "trade", "date": date(2026, 9, 21),
                                                           "source": "https://www.giants.com/news/x"}])
        home = self.read(self.render(e, copy_) / "index.html")
        self.assertNotIn('class="move"', home)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_site.py"`
Expected: FAIL (`Now on the Giants` not found).

- [ ] **Step 3: Implement**

Create `templates/_move.html`:

```html
<p class="move" style="--move: {{ move.color }}">{{ move.text }}{% if move.source_url %} Source: <a href="{{ move.source_url }}" rel="external noopener">{{ move.source_label }}</a>{% endif %}</p>
```

In `templates/_card.html`, directly after `<p class="score">{{ p.score_line }}</p>`:

```html
  {% if p.move %}{% set move = p.move %}{% include "_move.html" %}{% endif %}
```

In `templates/_player_head.html`, directly after `<p class="score">{{ player.score_line }}</p>`:

```html
  {% if player.move %}{% set move = player.move %}{% include "_move.html" %}{% endif %}
```

In `templates/edition.html`, in the Availability desk, add this line after the names `<dd>` (written inline so the player's name leads the sentence):

```html
      {% for p in group.players if p.move %}<dd class="desk-move" style="--move: {{ p.move.color }}">{{ p.name }}: {{ p.move.text }}{% if p.move.source_url %} Source: <a href="{{ p.move.source_url }}" rel="external noopener">{{ p.move.source_label }}</a>{% endif %}</dd>{% endfor %}
```

In `static/styles.css`, append:

```css
.move,.desk-move{margin:4px 0 0;padding-left:10px;border-left:3px solid var(--move,var(--brand));font-size:14px;color:var(--ink)}
```

In `src/site.py` (add `from . import moves`):

```python
def edition_context(edition, *, root, data_path, slugs, notes=None):
    players = [player_view(p) for p in edition.data["players"]]
    for raw, view in zip(edition.data["players"], players):
        view["move"] = moves.view(raw, notes or {})
        ...  # the existing loop body, unchanged
```

In `build_site`, after `editions = load_editions(editions_root)`:

```python
    notes = moves.note_index([(e.data, e.editorial) for e in editions])
```

Pass `notes=notes` to both `edition_context(...)` calls. In the player-page loop, set the move on each view before rendering:

```python
        for e_data, p in apps:
            view = player_view(p)
            view["move"] = moves.view(p, notes)
            ...
        latest_view = player_view(latest) if latest else None
        if latest_view:
            latest_view["move"] = moves.view(latest, notes)
        page("player.html", ..., player=latest_view, ...)
```

(`player=player_view(latest) if latest else None` becomes `player=latest_view`.)

- [ ] **Step 4: Run all tests and the build check**

Run:
```bash
.venv/Scripts/python -m unittest discover -s tests
.venv/Scripts/python -m src.site build --out _site --check
```
Expected: PASS; the build check prints its page count with no errors.

- [ ] **Step 5: Commit**

```bash
git add templates/_move.html templates/_card.html templates/_player_head.html templates/edition.html static/styles.css src/site.py tests/test_site.py
git commit -S -m "Show roster moves on cards, the Availability desk and player pages" -m "Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 7: Owner docs and the project rule

**Files:**
- Modify: `docs/OPERATIONS.md`, `CLAUDE.md`, `templates/methodology.html`

- [ ] **Step 1: Add the owner section to `docs/OPERATIONS.md`** (after the "To rebuild a published edition" bullet):

```markdown
### Roster moves

When an alum changes or leaves an NFL team, the edition PR lists it under **Roster moves** and the site shows a neutral line ("Now on the Giants' roster (was Vikings in Week 3)."). To say why, open `editorial.toml` in the PR, uncomment the entry and fill it in:

    [[roster_moves]]
    player_id = "00-0039923"
    kind = "trade"                            # trade | waiver claim | signing | release | waived
    date = 2026-09-28
    details = "for a 2027 fourth-round pick"  # optional, your words from the source
    source = "https://www.giants.com/news/..."

The site writes "Traded to the Giants on Sep 28 for a 2027 fourth-round pick. Source: Giants.com". Allowed sites: nfl.com, operations.nfl.com, espn.com, apnews.com and the 32 team sites. Avoid paywalled stories (for example ESPN+). `details` is at most 100 characters and must not repeat the team or the date.

- **Rebuild a published edition:** `.venv/Scripts/python -m src.edition --season 2026 --week N --rebuild` (add `--historical` for Weeks 1–2). It keeps each player's published roster notes, position, team-change flag and move.
```

Replace the existing "To rebuild a published edition with new code" bullet's command with the `--rebuild` form so the two agree.

- [ ] **Step 2: Add the rule to `CLAUDE.md`** under "Rules that must not bend":

```markdown
- A move's reason (traded, claimed, signed, waived) appears only from an owner note with an allowed source; only the data's own statuses (released, retired) appear without one.
```

and to the Map: `` - `moves.py`: roster moves (detection against earlier editions), allowed sources and move sentences. ``

- [ ] **Step 3: Add one paragraph to `templates/methodology.html`** in the player-pages section:

```html
<p>When an alum changes or leaves an NFL team, his card and player page say so, based on the weekly and current NFL rosters. The reason (a trade, a waiver claim, a signing) appears only with a link to the NFL, a team site, ESPN or the AP.</p>
```

- [ ] **Step 4: Run all tests and the build check**

```bash
.venv/Scripts/python -m unittest discover -s tests
.venv/Scripts/python -m src.site build --out _site --check
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/OPERATIONS.md CLAUDE.md templates/methodology.html
git commit -S -m "Document roster moves for the owner and readers" -m "Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

## After merge (owner-approved, not part of the implementation branch)

1. On a branch `chore/week3-move`: `.venv/Scripts/python -m src.edition --season 2026 --week 3 --rebuild`. Confirm the only diff in `edition.json` is `schema_version` and `move` (McCarthy: `moved_after_game`, MIN → NYG; everyone else `null`). Revert any other change and record it in the PR.
2. The owner supplies the McCarthy source link. Add the `[[roster_moves]]` entry to `editions/2026-week-03/editorial.toml`, then run `src.editorial check --all` and the site build check, and open the PR.
3. After Week 4 publishes, confirm McCarthy's card shows the sourced sentence (carried over from Week 3).
