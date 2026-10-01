# Week Page Facelift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the player week page plain-language play lines, outcome tags, a broadcast-style field drawing and the landing page's colors, with the numbers one tap away.

**Architecture:** A new pure module `src/playtext.py` writes each play's sentence, its outcome tag, the expected-points and air-yards sentences, and the game summary. `src/field.py` redraws the field (yard numbers, hash marks, team-color end zones, arrowheads, +/− labels, outcome-colored paths). The edition saves passer/rusher/receiver names per play and a team color map (schema 4). `src/site.py` wires it together; templates, CSS and `static/explorer.js` give the two-column layout and play cards.

**Tech Stack:** Python 3.12 stdlib, Jinja2, inline SVG, vanilla JS, stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-01-week-page-facelift-design.md`

## Global Constraints

- Presentation and wording only: no claim changes. Missing values are None, never zero; a missing value makes a simpler sentence ("Cisco brought down Gibbs."), never "0-yard".
- No injury, illness or benching words (`editorial.BLOCKED_TERMS`). "IMG Academy" in full, never "IMG" alone.
- Broadcast orientation: the offense always moves left to right.
- Outcome rule is today's: helped = EPA > 0 for the offense / EPA < 0 for the defense; None when EPA is missing or rounds to 0.0. "Big play" = helped and |EPA| ≥ 2.0.
- Colors: team bars from `site.team_bar` and the IMG Academy palette; team colors only as bars, borders, the ball path and tags; the first-down marker stays yellow.
- Sizes: large 960×240, medium 480×120, strip 320×56 (strip: no yard numbers or hash marks).
- Test output stays silent. Every commit signed (`git commit -S`) with `Co-Authored-By: <model> <noreply@anthropic.com>`.

## Review Focus

1. **A play where the alum has several roles** (a sack that also forced a fumble; a tackle that was a 3rd-down stop) must produce exactly one sentence, by the fixed precedence (interception > sack > forced fumble > pass breakup > tackle > passer > rusher > receiver), plus at most the touchdown and down-stop add-ons (Task 2, `test_precedence_picks_one_sentence`).
2. **Unusual play-by-play names** ("A.St. Brown", "Ja.Chase", "J.Smith-Njigba", a name with no initial) must give a sensible last name, never an empty string (Task 2, `test_last_names`).
3. **Labels near the window edge**: a long gain that ends at the right edge must keep its "+38" label inside the drawing (Task 4, `test_yardage_label_stays_inside`).
4. **Published editions without the new data** (Weeks 1–3 before their rebuild: no names, no `teams`) must render: fallback lines, default end-zone colors, no crash (Task 5, `test_schema_3_editions_still_render`).
5. **Plays that are flagged but not the alum's takeaway** (an interception thrown at the alum as receiver, a penalty, a lateral) must fall back to the cleaned play-by-play text, never "fell incomplete" (Task 2, `test_flagged_plays_fall_back`).

---

### Task 1: Save names and team colors in editions (schema 4)

**Files:**
- Modify: `src/data.py` (pbp required columns)
- Modify: `src/edition.py` (`SCHEMA_VERSION`, `play_record`, `build_edition`)
- Modify: `tests/fixtures/week02/expected_edition.json` (regenerated golden)
- Test: `tests/test_data.py`, `tests/test_edition.py`

**Interfaces:**
- Produces: every play record gains `passer_name`, `rusher_name`, `receiver_name` (str or None, the play-by-play's "J.Goff" form). Every edition gains top-level `teams: {abbr: {"name": str, "color": "#rrggbb"}}` for every team in that week's games. `SCHEMA_VERSION = 4`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_data.py`, add to the class that holds the existing "pbp required columns" tests (around line 77):

```python
    def test_pbp_requires_the_three_player_name_columns(self):
        self.assertTrue({"passer_player_name", "rusher_player_name", "receiver_player_name"} <= specifications(2026)["pbp"][2])
```

In `tests/test_edition.py` (it imports `from src import edition as ed`; `build()` is the module helper), add:

```python
class PlayNamesAndTeamsTests(unittest.TestCase):
    def test_play_records_keep_passer_rusher_and_receiver_names(self):
        data, _, _ = fixture_data.load()
        row = dict(data["pbp"][0], passer_player_name="J.Goff", rusher_player_name="", receiver_player_name="A.St. Brown")
        record = ed.play_record(row, "00-0000000", row["defteam"], lambda t: t)
        self.assertEqual((record["passer_name"], record["rusher_name"], record["receiver_name"]), ("J.Goff", None, "A.St. Brown"))

    def test_edition_has_a_color_for_every_team_this_week(self):
        edition = build()
        teams = {g["home_team"] for g in edition["games"]} | {g["away_team"] for g in edition["games"]}
        self.assertEqual(set(edition["teams"]), teams)
        for abbr, team in edition["teams"].items():
            with self.subTest(abbr=abbr):
                self.assertRegex(team["color"], r"^#[0-9a-fA-F]{6}$")
                self.assertTrue(team["name"])
```

Rename the existing `test_schema_version_is_three` to `test_schema_version_is_four` and make it assert `4`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_edition.py"` and `-p "test_data.py"`
Expected: FAIL (`KeyError: 'passer_name'`, `KeyError: 'teams'`, schema 3 ≠ 4, missing columns).

- [ ] **Step 3: Implement**

`src/data.py`, in `specifications()` the `"pbp"` set, after `"qtr", "time", "play_type", "fumble_lost", "third_down_failed", "fourth_down_failed",`:

```python
            "passer_player_name", "rusher_player_name", "receiver_player_name",
```

`src/edition.py`:

```python
SCHEMA_VERSION = 4
```

In `play_record`, after `"description": play.get("desc", ""),`:

```python
        "passer_name": play.get("passer_player_name") or None,
        "rusher_name": play.get("rusher_player_name") or None,
        "receiver_name": play.get("receiver_player_name") or None,
```

In `build_edition`'s returned dict, after `"games": [...]`:

```python
        "teams": {
            abbr: {"name": wk.team_name(abbr), "color": wk.team_color(abbr)}
            for abbr in sorted({g["home_team"] for g in games} | {g["away_team"] for g in games})
        },
```

Regenerate the golden and confirm the diff is only `schema_version` 3 → 4, the new `teams` block, and three `null` name fields per play (the Week 2 fixture's pbp slice has no name columns):

```bash
UPDATE_GOLDEN=1 .venv/Scripts/python -m unittest discover -s tests -p "test_edition.py"
git diff --stat tests/fixtures/week02/expected_edition.json
```

- [ ] **Step 4: Run all tests**

Run: `.venv/Scripts/python -m unittest discover -s tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data.py src/edition.py tests/test_data.py tests/test_edition.py tests/fixtures/week02/expected_edition.json
git commit -S -m "Save passer, rusher and receiver names and a team color map in editions (schema 4)" -m "Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 2: Plain-language play lines (`src/playtext.py`)

**Files:**
- Create: `src/playtext.py`
- Test: `tests/test_playtext.py`

**Interfaces:**
- Consumes: play records (Task 1 names; existing `roles`, `impact`, flags, `yards_gained`, `offense_name`, `description`, `play_id`); `editorial.NAME_SUFFIXES`, `editorial.BLOCKED_TERMS`; `players.nickname(team_name)`.
- Produces:
  - `playtext.last_name(pbp_name: str | None) -> str | None`
  - `playtext.alum_name(full_name: str) -> str`
  - `playtext.clean_description(text: str) -> str`
  - `playtext.play_line(play: dict, player: dict) -> str` (`player` needs `name`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_playtext.py`:

```python
import unittest

from src import editorial, playtext

CISCO = {"name": "Andre Cisco", "team_name": "New York Jets"}
NEWSOME = {"name": "Greg Newsome II", "team_name": "New York Giants"}
ALLEN = {"name": "Kaytron Allen", "team_name": "Washington Commanders"}
TATE = {"name": "Carnell Tate", "team_name": "Tennessee Titans"}
MCCARTHY = {"name": "J.J. McCarthy", "team_name": "Minnesota Vikings"}


def play(**overrides):
    p = {"play_id": "100", "offense_name": "Detroit Lions", "defense_name": "New York Jets", "roles": [], "impact": None,
         "play_type": "pass", "yards_gained": 0, "pass_attempt": 0, "rush_attempt": 0, "complete_pass": 0, "sack": 0,
         "interception": 0, "fumble": 0, "penalty": 0, "lateral": 0, "two_point_attempt": 0,
         "passer_name": "J.Goff", "rusher_name": None, "receiver_name": None, "description": "", "epa": None}
    p.update(overrides)
    return p


def run(**overrides):
    fields = dict(play_type="run", rush_attempt=1, passer_name=None, rusher_name="D.Montgomery")
    fields.update(overrides)
    return play(**fields)


def catch(**overrides):
    fields = dict(pass_attempt=1, complete_pass=1, receiver_name="J.Gibbs")
    fields.update(overrides)
    return play(**fields)


class NameTests(unittest.TestCase):
    def test_last_names(self):
        for given, expected in (("J.Goff", "Goff"), ("A.St. Brown", "St. Brown"), ("Ja.Chase", "Chase"),
                                ("J.Smith-Njigba", "Smith-Njigba"), ("Goff", "Goff"), (None, None), ("", None)):
            with self.subTest(given=given):
                self.assertEqual(playtext.last_name(given), expected)

    def test_alum_names_drop_suffixes(self):
        self.assertEqual(playtext.alum_name("Greg Newsome II"), "Newsome")
        self.assertEqual(playtext.alum_name("J.J. McCarthy"), "McCarthy")


class DefenseLineTests(unittest.TestCase):
    def test_sack(self):
        sack = dict(roles=["sack", "solo_tackle_1"], sack=1, pass_attempt=1)
        self.assertEqual(playtext.play_line(play(yards_gained=-10, **sack), CISCO), "Cisco sacked Goff for a 10-yard loss.")
        self.assertEqual(playtext.play_line(play(play_id="101", yards_gained=-10, **sack), CISCO), "Cisco brought down Goff for a 10-yard sack.")
        self.assertEqual(playtext.play_line(play(yards_gained=0, **sack), CISCO), "Cisco sacked Goff for no gain.")
        self.assertEqual(playtext.play_line(play(yards_gained=None, **sack), CISCO), "Cisco sacked Goff.")
        half = play(roles=["half_sack_1"], sack=1, pass_attempt=1, yards_gained=-6)
        self.assertEqual(playtext.play_line(half, CISCO), "Cisco shared a sack of Goff for a 6-yard loss.")

    def test_pass_breakup(self):
        breakup = dict(roles=["pass_defense_1"], pass_attempt=1, passer_name="C.Ward", receiver_name="W.Robinson", offense_name="Tennessee Titans")
        self.assertEqual(playtext.play_line(play(**breakup), NEWSOME), "Newsome broke up Ward's pass to Robinson.")
        self.assertEqual(playtext.play_line(play(play_id="101", **breakup), NEWSOME), "Newsome got a hand on Ward's pass to Robinson.")
        self.assertEqual(playtext.play_line(play(**dict(breakup, receiver_name=None)), NEWSOME), "Newsome broke up Ward's pass.")

    def test_tackle_after_a_catch(self):
        self.assertEqual(playtext.play_line(catch(roles=["solo_tackle_1"], yards_gained=13), CISCO), "Cisco brought down Gibbs after a 13-yard catch.")
        self.assertEqual(playtext.play_line(catch(play_id="101", roles=["solo_tackle_1"], yards_gained=13), CISCO), "Gibbs caught a 13-yard pass before Cisco made the tackle.")
        self.assertEqual(playtext.play_line(catch(roles=["assist_tackle_1"], yards_gained=13), CISCO), "Cisco helped bring down Gibbs after a 13-yard catch.")
        self.assertEqual(playtext.play_line(catch(roles=["solo_tackle_1"], yards_gained=None), CISCO), "Cisco brought down Gibbs.")

    def test_tackle_on_a_run(self):
        self.assertEqual(playtext.play_line(run(roles=["solo_tackle_1"], yards_gained=2), CISCO), "Cisco stopped Montgomery after a 2-yard run.")
        self.assertEqual(playtext.play_line(run(play_id="101", roles=["solo_tackle_1"], yards_gained=2), CISCO), "Montgomery ran for 2 yards before Cisco made the tackle.")
        self.assertEqual(playtext.play_line(run(roles=["tackle_for_loss_1", "solo_tackle_1"], yards_gained=-3), CISCO), "Cisco stopped Montgomery for a 3-yard loss.")
        self.assertEqual(playtext.play_line(run(roles=["solo_tackle_1"], yards_gained=0), CISCO), "Cisco stopped Montgomery for no gain.")
        self.assertEqual(playtext.play_line(run(roles=["assist_tackle_2"], yards_gained=0), CISCO), "Cisco helped stop Montgomery for no gain.")

    def test_takeaways(self):
        pick = dict(roles=["interception"], interception=1, pass_attempt=1)
        self.assertEqual(playtext.play_line(play(**pick), CISCO), "Cisco intercepted Goff.")
        self.assertEqual(playtext.play_line(play(play_id="101", **pick), CISCO), "Cisco picked off Goff.")
        forced = run(roles=["forced_fumble_player_1", "solo_tackle_1"], fumble=1, yards_gained=3)
        self.assertEqual(playtext.play_line(forced, CISCO), "Cisco forced a fumble.")
        self.assertEqual(playtext.play_line(dict(forced, play_id="101"), CISCO), "Cisco knocked the ball loose.")


class OffenseLineTests(unittest.TestCase):
    def test_rusher(self):
        carry = dict(roles=["rusher"], rusher_name="K.Allen")
        self.assertEqual(playtext.play_line(run(yards_gained=6, **carry), ALLEN), "Allen ran for 6 yards.")
        self.assertEqual(playtext.play_line(run(play_id="101", yards_gained=6, **carry), ALLEN), "Allen picked up 6 yards on the ground.")
        self.assertEqual(playtext.play_line(run(yards_gained=1, **carry), ALLEN), "Allen ran for 1 yard.")
        self.assertEqual(playtext.play_line(run(yards_gained=-2, **carry), ALLEN), "Allen lost 2 yards.")
        self.assertEqual(playtext.play_line(run(yards_gained=0, **carry), ALLEN), "Allen was stopped for no gain.")

    def test_receiver(self):
        target = dict(roles=["receiver"], pass_attempt=1, passer_name="C.Ward", receiver_name="C.Tate", offense_name="Tennessee Titans")
        self.assertEqual(playtext.play_line(play(complete_pass=1, yards_gained=12, **target), TATE), "Tate caught a 12-yard pass from Ward.")
        self.assertEqual(playtext.play_line(play(play_id="101", complete_pass=1, yards_gained=12, **target), TATE), "Ward hit Tate for 12 yards.")
        self.assertEqual(playtext.play_line(play(complete_pass=0, **target), TATE), "Ward's pass to Tate fell incomplete.")

    def test_passer(self):
        throw = dict(roles=["passer"], pass_attempt=1, passer_name="J.McCarthy", receiver_name="J.Jefferson", offense_name="Minnesota Vikings")
        self.assertEqual(playtext.play_line(play(complete_pass=1, yards_gained=15, **throw), MCCARTHY), "McCarthy completed a 15-yard pass to Jefferson.")
        self.assertEqual(playtext.play_line(play(play_id="101", complete_pass=1, yards_gained=15, **throw), MCCARTHY), "McCarthy found Jefferson for 15 yards.")
        self.assertEqual(playtext.play_line(play(complete_pass=0, **throw), MCCARTHY), "McCarthy's pass to Jefferson fell incomplete.")
        self.assertEqual(playtext.play_line(play(sack=1, yards_gained=-7, **throw), MCCARTHY), "McCarthy was sacked for a 7-yard loss.")


class AddOnAndFallbackTests(unittest.TestCase):
    def test_touchdown_and_down_stop_add_ons(self):
        score = play(roles=["receiver", "td"], pass_attempt=1, complete_pass=1, yards_gained=12, passer_name="C.Ward", receiver_name="C.Tate")
        self.assertEqual(playtext.play_line(score, TATE), "Tate caught a 12-yard pass from Ward for a touchdown.")
        stop = run(roles=["solo_tackle_1"], yards_gained=1, impact="3rd-down stop")
        self.assertEqual(playtext.play_line(stop, CISCO), "Cisco stopped Montgomery after a 1-yard run, stopping the Lions on 3rd down.")

    def test_precedence_picks_one_sentence(self):
        both = play(roles=["sack", "forced_fumble_player_1", "solo_tackle_1"], sack=1, fumble=1, pass_attempt=1, yards_gained=-8)
        self.assertEqual(playtext.play_line(both, CISCO), "Cisco sacked Goff for an 8-yard loss.")

    def test_fallback_is_the_cleaned_play_by_play(self):
        text = "(1:47) (No Huddle, Shotgun) 16-J.Goff pass short left to 18-I.TeSlaa to NYJ 4 for 5 yards (8-A.Cisco)."
        self.assertEqual(playtext.play_line(play(roles=["kicker"], description=text), CISCO),
                         "J.Goff pass short left to I.TeSlaa to NYJ 4 for 5 yards (A.Cisco).")
        self.assertEqual(playtext.clean_description("(8:54) (Shotgun) 16-J.Goff sacked at DET 48 for -10 yards (8-A.Cisco)."),
                         "J.Goff sacked at DET 48 for -10 yards (A.Cisco).")

    def test_missing_names_fall_back(self):
        self.assertEqual(playtext.play_line(catch(roles=["solo_tackle_1"], receiver_name=None, yards_gained=13, description="(2:00) X"), CISCO), "X")

    def test_flagged_plays_fall_back(self):
        picked = play(roles=["receiver"], pass_attempt=1, interception=1, passer_name="C.Ward", receiver_name="C.Tate", description="(3:00) INT")
        self.assertEqual(playtext.play_line(picked, TATE), "INT")
        flagged = run(roles=["solo_tackle_1"], penalty=1, yards_gained=4, description="(4:00) PEN")
        self.assertEqual(playtext.play_line(flagged, CISCO), "PEN")
        lateral = run(roles=["rusher"], lateral=1, rusher_name="K.Allen", yards_gained=4, description="(5:00) LAT")
        self.assertEqual(playtext.play_line(lateral, ALLEN), "LAT")

    def test_lines_never_use_blocked_terms_or_zero_yards(self):
        samples = [play(yards_gained=-10, roles=["sack"], sack=1, pass_attempt=1), catch(roles=["solo_tackle_1"], yards_gained=None),
                   run(roles=["solo_tackle_1"], yards_gained=None), run(roles=["rusher"], rusher_name="K.Allen", yards_gained=None)]
        for sample in samples:
            line = playtext.play_line(sample, CISCO).lower()
            with self.subTest(line=line):
                self.assertFalse(any(term in line for term in editorial.BLOCKED_TERMS))
                self.assertNotIn("0-yard", line)
                self.assertNotIn(" 0 yard", line)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_playtext.py"`
Expected: FAIL with `ImportError: cannot import name 'playtext'`.

- [ ] **Step 3: Implement**

Create `src/playtext.py`:

```python
"""Plain-language lines for player week pages: one sentence per play, outcome tags and a game summary.

Pure functions over saved play records. Every number comes from the play's own fields; a missing value makes a
simpler sentence, never a zero. When no template fits, the play-by-play text is shown, cleaned. Nothing is invented.
"""
from __future__ import annotations

import re

from .editorial import NAME_SUFFIXES
from .players import nickname

CLOCK = re.compile(r"^\(\d{1,2}:\d{2}\)\s*")
FORMATION = re.compile(r"\((?:No Huddle, )?Shotgun\)\s*|\(No Huddle\)\s*")
JERSEY = re.compile(r"\b\d{1,2}-(?=[A-Z])")
PBP_NAME = re.compile(r"[A-Z][a-z]{0,2}\.\s?(.+)")
SACKS = {"sack", "half_sack_1", "half_sack_2"}
FORCED = {"forced_fumble_player_1", "forced_fumble_player_2"}
BREAKUPS = {"pass_defense_1", "pass_defense_2"}
SOLO = {"solo_tackle_1", "solo_tackle_2", "tackle_with_assist_1", "tackle_with_assist_2", "tackle_for_loss_1", "tackle_for_loss_2"}
ASSISTS = {"assist_tackle_1", "assist_tackle_2", "assist_tackle_3", "assist_tackle_4"}
SPECIAL_TEAMS = {"kickoff", "punt", "field_goal", "extra_point"}
STOPS = ("3rd-down stop", "4th-down stop")


def last_name(pbp_name):
    """'J.Goff' -> 'Goff', 'A.St. Brown' -> 'St. Brown'; other shapes as written; blank -> None."""
    if not pbp_name or not pbp_name.strip():
        return None
    match = PBP_NAME.fullmatch(pbp_name.strip())
    return match.group(1) if match else pbp_name.strip()


def alum_name(full_name):
    parts = [part for part in full_name.split() if part not in NAME_SUFFIXES]
    return parts[-1] if parts else full_name


def clean_description(text):
    text = CLOCK.sub("", text or "")
    text = FORMATION.sub("", text)
    text = JERSEY.sub("", text)
    return " ".join(text.split())


def _yards(n):
    return f"{n} yard" if n == 1 else f"{n} yards"


def _a(n):
    """'a 10-yard', 'an 8-yard', 'an 11-yard', 'an 18-yard'."""
    return f"an {n}" if str(n).startswith("8") or n in (11, 18) else f"a {n}"


def _even(play):
    try:
        return int(float(play.get("play_id") or 0)) % 2 == 0
    except ValueError:
        return True


def _blocked(play, roles):
    """Flags whose meaning the templates can't carry; the alum's own takeaway role is the exception."""
    if play.get("play_type") in SPECIAL_TEAMS or play.get("penalty") == 1 or play.get("lateral") == 1 or play.get("two_point_attempt") == 1:
        return True
    if play.get("interception") == 1 and "interception" not in roles:
        return True
    return play.get("fumble") == 1 and not roles & (FORCED | {"fumble_recovery_1", "fumble_recovery_2"})


def _template(play, me, roles):
    if _blocked(play, roles):
        return None
    gained = play.get("yards_gained")
    qb, runner, target = (last_name(play.get(k)) for k in ("passer_name", "rusher_name", "receiver_name"))
    pick = lambda first, second: first if _even(play) else second
    if "interception" in roles:
        return pick(f"{me} intercepted {qb}.", f"{me} picked off {qb}.") if qb else None
    if roles & SACKS:
        if not qb:
            return None
        verb = f"{me} sacked {qb}" if "sack" in roles else f"{me} shared a sack of {qb}"
        if gained is None:
            return f"{verb}."
        if gained == 0:
            return f"{verb} for no gain."
        if gained < 0 and "sack" in roles:
            return pick(f"{verb} for {_a(abs(gained))}-yard loss.", f"{me} brought down {qb} for {_a(abs(gained))}-yard sack.")
        return f"{verb} for {_a(abs(gained))}-yard loss." if gained < 0 else f"{verb}."
    if roles & FORCED:
        return pick(f"{me} forced a fumble.", f"{me} knocked the ball loose.")
    if roles & BREAKUPS:
        if not qb:
            return None
        thrown = f"{qb}'s pass to {target}" if target else f"{qb}'s pass"
        return pick(f"{me} broke up {thrown}.", f"{me} got a hand on {thrown}.")
    if roles & (SOLO | ASSISTS):
        return _tackle(play, me, roles, gained, runner, target, pick)
    if "passer" in roles:
        return _passer(play, me, gained, target, pick)
    if "rusher" in roles:
        if gained is None:
            return f"{me} ran the ball."
        if gained > 0:
            return pick(f"{me} ran for {_yards(gained)}.", f"{me} picked up {_yards(gained)} on the ground.")
        return f"{me} was stopped for no gain." if gained == 0 else f"{me} lost {_yards(abs(gained))}."
    if "receiver" in roles:
        source = f" from {qb}" if qb else ""
        if play.get("complete_pass") == 1:
            if gained is None:
                return f"{me} caught a pass{source}."
            if gained > 0:
                return pick(f"{me} caught {_a(gained)}-yard pass{source}.", f"{qb} hit {me} for {_yards(gained)}." if qb else f"{me} caught {_a(gained)}-yard pass.")
            return f"{me} caught a pass{source} for no gain." if gained == 0 else f"{me} caught a pass{source} but lost {_yards(abs(gained))}."
        if play.get("complete_pass") == 0:
            return f"{qb}'s pass to {me} fell incomplete." if qb else f"A pass to {me} fell incomplete."
    return None


def _tackle(play, me, roles, gained, runner, target, pick):
    solo = bool(roles & SOLO)
    bring, stop = ("brought down", "stopped") if solo else ("helped bring down", "helped stop")
    made = "made the tackle" if solo else "helped make the tackle"
    if play.get("complete_pass") == 1 and target:
        who, after = target, "catch"
    elif play.get("rush_attempt") == 1 and runner:
        who, after = runner, "run"
    else:
        return None
    if gained is None:
        return f"{me} {bring} {who}."
    if gained > 0 and after == "catch":
        return pick(f"{me} {bring} {who} after {_a(gained)}-yard catch.", f"{who} caught {_a(gained)}-yard pass before {me} {made}.")
    if gained > 0:
        return pick(f"{me} {stop} {who} after {_a(gained)}-yard run.", f"{who} ran for {_yards(gained)} before {me} {made}.")
    tail = " after the catch" if after == "catch" else ""
    return f"{me} {stop} {who} for no gain{tail}." if gained == 0 else f"{me} {stop} {who} for {_a(abs(gained))}-yard loss{tail}."


def _passer(play, me, gained, target, pick):
    if play.get("sack") == 1:
        if gained is None:
            return f"{me} was sacked."
        return f"{me} was sacked for no gain." if gained == 0 else f"{me} was sacked for {_a(abs(gained))}-yard loss."
    if not target:
        return f"{me}'s pass fell incomplete." if play.get("complete_pass") == 0 else None
    if play.get("complete_pass") == 1:
        if gained is None:
            return f"{me} completed a pass to {target}."
        if gained > 0:
            return pick(f"{me} completed {_a(gained)}-yard pass to {target}.", f"{me} found {target} for {_yards(gained)}.")
        return f"{me} completed a pass to {target} for no gain." if gained == 0 else f"{me} completed a pass to {target} for {_a(abs(gained))}-yard loss."
    if play.get("complete_pass") == 0:
        return f"{me}'s pass to {target} fell incomplete."
    return None


def play_line(play, player):
    """One plain sentence for the alum's part in the play, or the cleaned play-by-play text."""
    roles = set(play.get("roles") or [])
    line = _template(play, alum_name(player["name"]), roles)
    if line is None:
        return clean_description(play.get("description", ""))
    if "td" in roles:
        line = line[:-1] + " for a touchdown."
    if play.get("impact") in STOPS and play.get("offense_name"):
        line = f"{line[:-1]}, stopping the {nickname(play['offense_name'])} on {play['impact'][:3]} down."
    return line
```

Note the sack test expects "for a 10-yard loss" and "for an 8-yard loss"; `_a()` picks the article from how the number is read aloud.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_playtext.py"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/playtext.py tests/test_playtext.py
git commit -S -m "Write plain-language play lines from saved play data" -m "Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 3: Outcome tags, detail sentences and the game summary (`src/playtext.py`)

**Files:**
- Modify: `src/playtext.py`
- Test: `tests/test_playtext.py`

**Interfaces:**
- Produces:
  - `playtext.BIG_PLAY = 2.0`
  - `playtext.helped(play: dict, side: str) -> bool | None`
  - `playtext.tag(play: dict, side: str, nick: str) -> dict | None` → `{"key": "big" | "helped" | "hurt", "text": str}`
  - `playtext.epa_sentence(play: dict) -> str`
  - `playtext.air_sentence(play: dict) -> str`
  - `playtext.summary(plays: list[dict]) -> str`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_playtext.py`:

```python
class TagTests(unittest.TestCase):
    def test_helped_follows_the_expected_points_rule(self):
        self.assertTrue(playtext.helped({"epa": 0.5}, "offense"))
        self.assertTrue(playtext.helped({"epa": -2.46}, "defense"))
        self.assertFalse(playtext.helped({"epa": 0.8}, "defense"))
        self.assertIsNone(playtext.helped({"epa": 0.04}, "defense"))
        self.assertIsNone(playtext.helped({"epa": None}, "offense"))

    def test_tags(self):
        self.assertEqual(playtext.tag({"epa": -2.46}, "defense", "Jets"), {"key": "big", "text": "Big play"})
        self.assertEqual(playtext.tag({"epa": -2.0}, "defense", "Jets"), {"key": "big", "text": "Big play"})
        self.assertEqual(playtext.tag({"epa": -1.99}, "defense", "Jets"), {"key": "helped", "text": "Helped the Jets"})
        self.assertEqual(playtext.tag({"epa": 0.8}, "defense", "Jets"), {"key": "hurt", "text": "Hurt the Jets"})
        self.assertEqual(playtext.tag({"epa": 2.0}, "offense", "Titans"), {"key": "big", "text": "Big play"})
        self.assertIsNone(playtext.tag({"epa": 0.03}, "offense", "Titans"))
        self.assertIsNone(playtext.tag({"epa": None}, "offense", "Titans"))


class DetailTests(unittest.TestCase):
    def test_expected_points_sentence(self):
        self.assertEqual(playtext.epa_sentence({"epa": -2.46, "offense_name": "Detroit Lions"}), "The Lions lost 2.5 expected points on the play.")
        self.assertEqual(playtext.epa_sentence({"epa": 1.0, "offense_name": "Detroit Lions"}), "The Lions gained 1 expected point on the play.")
        self.assertEqual(playtext.epa_sentence({"epa": 0.04, "offense_name": "Detroit Lions"}), "The Lions' expected points barely moved on the play.")
        self.assertEqual(playtext.epa_sentence({"epa": None, "offense_name": "Detroit Lions"}), "")

    def test_air_sentence(self):
        self.assertEqual(playtext.air_sentence({"pass_attempt": 1, "complete_pass": 1, "air_yards": 8, "yards_after_catch": 6}), "Thrown 8 yards past the line; 6 yards after the catch.")
        self.assertEqual(playtext.air_sentence({"pass_attempt": 1, "complete_pass": 1, "air_yards": -2, "yards_after_catch": 15}), "Thrown 2 yards behind the line; 15 yards after the catch.")
        self.assertEqual(playtext.air_sentence({"pass_attempt": 1, "complete_pass": 0, "air_yards": 12, "yards_after_catch": None}), "Thrown 12 yards past the line.")
        self.assertEqual(playtext.air_sentence({"pass_attempt": 0, "air_yards": None}), "")


class SummaryTests(unittest.TestCase):
    def test_counts_one_category_per_play(self):
        plays = [{"impact": "Sack", "roles": ["sack", "solo_tackle_1"]}] + [{"impact": None, "roles": ["solo_tackle_1"]}] * 4 + [{"impact": "3rd-down stop", "roles": ["solo_tackle_1"]}]
        self.assertEqual(playtext.summary(plays), "Six plays with his name on them: a sack, four tackles and a 3rd-down stop.")

    def test_one_play_and_none(self):
        self.assertEqual(playtext.summary([{"impact": "Pass defended", "roles": ["pass_defense_1"]}]), "One play with his name on it: a pass breakup.")
        self.assertEqual(playtext.summary([{"impact": "Interception", "roles": ["interception"]}]), "One play with his name on it: an interception.")
        self.assertEqual(playtext.summary([]), "")

    def test_offense_and_large_counts(self):
        plays = [{"impact": None, "roles": ["receiver"], "complete_pass": 1}] * 11
        self.assertEqual(playtext.summary(plays), "11 plays with his name on them: 11 catches.")
        mixed = [{"impact": None, "roles": ["rusher"]}, {"impact": None, "roles": ["receiver"], "complete_pass": 0}, {"impact": "Blocked kick", "roles": ["blocked"]}]
        self.assertEqual(playtext.summary(mixed), "Three plays with his name on them: a carry, a target and one other play.")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_playtext.py"`
Expected: FAIL with `AttributeError: module 'src.playtext' has no attribute 'helped'`.

- [ ] **Step 3: Implement**

Add `from collections import Counter` to the imports of `src/playtext.py`, then append:

```python
BIG_PLAY = 2.0
COUNT_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
CATEGORIES = (
    ("Sack", "sack", "sacks"), ("Interception", "interception", "interceptions"), ("Forced fumble", "forced fumble", "forced fumbles"),
    ("Fumble recovery", "fumble recovery", "fumble recoveries"), ("Safety", "safety", "safeties"),
    ("Pass defended", "pass breakup", "pass breakups"), ("Tackle for loss", "tackle for loss", "tackles for loss"),
    ("QB hit", "QB hit", "QB hits"), ("tackle", "tackle", "tackles"),
    ("3rd-down stop", "3rd-down stop", "3rd-down stops"), ("4th-down stop", "4th-down stop", "4th-down stops"),
    ("Touchdown", "touchdown", "touchdowns"), ("catch", "catch", "catches"),
    ("carry", "carry", "carries"), ("pass", "pass", "passes"), ("target", "target", "targets"), ("other", "other play", "other plays"),
)
KNOWN = {key for key, _, _ in CATEGORIES}


def helped(play, side):
    """True when the play helped the alum's team, False when it hurt, None when unknown or neutral (rounds to 0.0)."""
    epa = play.get("epa")
    if epa is None or round(abs(epa), 1) == 0:
        return None
    return epa > 0 if side == "offense" else epa < 0


def tag(play, side, nick):
    good = helped(play, side)
    if good is None:
        return None
    if not good:
        return {"key": "hurt", "text": f"Hurt the {nick}"}
    if abs(play["epa"]) >= BIG_PLAY:
        return {"key": "big", "text": "Big play"}
    return {"key": "helped", "text": f"Helped the {nick}"}


def epa_sentence(play):
    epa, offense = play.get("epa"), play.get("offense_name")
    if epa is None or not offense:
        return ""
    team, value = nickname(offense), round(abs(epa), 1)
    if value == 0:
        return f"The {team}' expected points barely moved on the play."
    points = "1 expected point" if value == 1 else f"{value:.1f} expected points"
    return f"The {team} {'lost' if epa < 0 else 'gained'} {points} on the play."


def air_sentence(play):
    air = play.get("air_yards")
    if play.get("pass_attempt") != 1 or air is None:
        return ""
    where = f"{_yards(air)} past the line" if air > 0 else ("at the line" if air == 0 else f"{_yards(abs(air))} behind the line")
    text = f"Thrown {where}"
    after = play.get("yards_after_catch")
    if play.get("complete_pass") == 1 and after is not None:
        text += f"; {_yards(after)} after the catch" if after >= 0 else f"; lost {_yards(abs(after))} after the catch"
    return text + "."


def _category(play):
    impact = play.get("impact")
    if impact:
        return impact if impact in KNOWN else "other"
    roles = set(play.get("roles") or [])
    if roles & (SOLO | ASSISTS):
        return "tackle"
    if "receiver" in roles:
        return "catch" if play.get("complete_pass") == 1 else "target"
    if "rusher" in roles:
        return "carry"
    if "passer" in roles:
        return "pass"
    return "other"


def _word(n):
    return COUNT_WORDS[n] if n <= 10 else str(n)


def _count(n, one, many):
    if n > 1:
        return f"{_word(n)} {many}"
    if one == "other play":
        return "one other play"
    return f"an {one}" if one[0] in "aeiou" else f"a {one}"


def summary(plays):
    """'Six plays with his name on them: a sack, four tackles and a 3rd-down stop.' One category per play."""
    if not plays:
        return ""
    counts = Counter(_category(p) for p in plays)
    parts = [_count(counts[key], one, many) for key, one, many in CATEGORIES if counts[key]]
    n = len(plays)
    lead = f"{_word(n).capitalize()} play with his name on it" if n == 1 else f"{_word(n).capitalize()} plays with his name on them"
    listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return f"{lead}: {listed}."
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_playtext.py"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/playtext.py tests/test_playtext.py
git commit -S -m "Outcome tags, expected-points and air-yards sentences, and the game summary" -m "Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 4: Redraw the field (`src/field.py`)

**Files:**
- Modify: `src/field.py` (`SIZES`, `CAPTION`, `svg`; new `yardage_label`)
- Modify: `static/styles.css` (the `.field` rules)
- Test: `tests/test_field.py`

**Interfaces:**
- Produces:
  - `field.SIZES = {"strip": (320, 56), "medium": (480, 120), "large": (960, 240)}`
  - `field.CAPTION = "Each drawing shows where the play started and ended, not player tracking."`
  - `field.yardage_label(play: dict) -> str | None` ("+13", "−10" with U+2212, "0", "Incomplete"; None for text-only plays)
  - `field.svg(play, size, outcome="", helped=None, path_color="#0057b8", zones=None) -> str | None`. `zones = {"offense": (fill, ink), "defense": (fill, ink)}`. The old positional `team_color` argument is removed; Task 5 updates every caller.

- [ ] **Step 1: Write the failing tests**

In `tests/test_field.py`, update any existing call `field.svg(play, size, "<color>", ...)` to the new keyword form (`field.svg(play, size, outcome=...)`) and the medium-size assertion to `viewBox="0 0 480 120"`. The existing test that checks the team color on the player's end-zone label tests behavior this task replaces: delete it, because `test_end_zones_use_the_given_team_colors` below covers end-zone colors. Then add:

```python
ARROW = re.compile(r'<polygon class="arrow" points="([\d.]+),[\d.]+ ([\d.]+),')


def pass_play(**overrides):
    return base(play_type="pass", rush_attempt=0, pass_attempt=1, **overrides)


class FaceliftTests(unittest.TestCase):
    def test_sizes(self):
        self.assertIn('viewBox="0 0 960 240"', field.svg(base(), "large"))
        self.assertIn('viewBox="0 0 480 120"', field.svg(base(), "medium"))
        self.assertIn('viewBox="0 0 320 56"', field.svg(base(), "strip"))

    def test_gain_points_right_with_a_plus_label(self):
        markup = field.svg(base(yards_gained=4), "medium")
        tip, back = map(float, ARROW.search(markup).groups())
        self.assertGreater(tip, back)
        self.assertIn(">+4</text>", markup)

    def test_loss_points_left_with_a_minus_label(self):
        markup = field.svg(pass_play(sack=1, yards_gained=-10), "medium")
        tip, back = map(float, ARROW.search(markup).groups())
        self.assertLess(tip, back)
        self.assertIn(">−10</text>", markup)

    def test_no_gain_has_a_ball_and_a_zero_label(self):
        markup = field.svg(base(yards_gained=0), "medium")
        self.assertNotIn('class="arrow"', markup)
        self.assertIn('class="ball"', markup)
        self.assertIn(">0</text>", markup)

    def test_incomplete_has_a_target_and_label(self):
        markup = field.svg(pass_play(air_yards=12, yards_gained=0, complete_pass=0), "medium")
        self.assertNotIn('class="arrow"', markup)
        self.assertIn('class="target"', markup)
        self.assertIn(">Incomplete</text>", markup)

    def test_path_color_follows_the_outcome(self):
        self.assertIn('<g class="path path-helped" style="color:#0B2265">', field.svg(base(), "medium", helped=True, path_color="#0B2265"))
        self.assertIn('<g class="path path-hurt">', field.svg(base(), "medium", helped=False, path_color="#0B2265"))
        self.assertIn('<g class="path path-neutral">', field.svg(base(), "medium"))

    def test_numbers_and_hashes_only_on_detailed_sizes_and_inside_the_window(self):
        markup = field.svg(base(), "large")
        g = field.geometry(base())
        for yard in re.findall(r'class="yard-number" x="[\d.]+" y="[\d.]+" text-anchor="middle">(\d+)<', markup):
            self.assertTrue(int(yard) % 10 == 0)
        self.assertIn('class="hash"', markup)
        self.assertGreaterEqual(markup.count('class="yard-number"'), 2)
        strip = field.svg(base(), "strip")
        self.assertNotIn('class="yard-number"', strip)
        self.assertNotIn('class="hash"', strip)
        self.assertLess(g["lo"], g["hi"])

    def test_end_zones_use_the_given_team_colors(self):
        goal_line = base(yardline_100=4, ydstogo=4, goal_to_go=1, yards_gained=4)
        markup = field.svg(goal_line, "medium", zones={"offense": ("#0B2265", "#ffffff"), "defense": ("#191711", "#D3BC8D")})
        self.assertIn('class="endzone" x=', markup)
        self.assertIn("fill:#191711", markup)
        self.assertIn("fill:#D3BC8D", markup)

    def test_yardage_label_stays_inside(self):
        long_gain = base(yardline_100=40, ydstogo=10, yards_gained=38)
        markup = field.svg(long_gain, "medium")
        x = float(re.search(r'<text class="yardage" x="([\d.]+)"', markup).group(1))
        self.assertTrue(24 <= x <= 480 - 24)

    def test_aria_label_carries_the_tag(self):
        self.assertIn("Big play", field.svg(base(), "medium", outcome="Big play"))

    def test_text_only_plays_still_have_no_drawing(self):
        self.assertIsNone(field.svg(base(penalty=1), "medium"))
        self.assertIsNone(field.yardage_label(base(penalty=1)))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_field.py"`
Expected: FAIL (old sizes; no arrow, labels, path groups or zones).

- [ ] **Step 3: Implement**

In `src/field.py`:

```python
CAPTION = "Each drawing shows where the play started and ended, not player tracking."
SIZES = {"strip": (320, 56), "medium": (480, 120), "large": (960, 240)}
MINUS = "−"


def yardage_label(play):
    shape, gained = kind(play), play.get("yards_gained")
    if shape is None:
        return None
    if shape == "incomplete":
        return "Incomplete"
    return f"+{gained}" if gained > 0 else ("0" if gained == 0 else f"{MINUS}{abs(gained)}")
```

Replace `svg` with:

```python
def svg(play, size, outcome="", helped=None, path_color="#0057b8", zones=None):
    """Broadcast view: the offense moves left to right. `helped` colors the ball's path (the alum's team bar color when
    True, slate when False, navy when unknown); `zones` gives each end zone its team bar (fill, ink)."""
    g = geometry(play)
    if g is None:
        return None
    width, height = SIZES[size]
    detailed = size != "strip"
    scale = width / (g["hi"] - g["lo"])
    clamp = lambda yards: max(g["lo"], min(g["hi"], yards))
    x = lambda yards: round((clamp(yards) - g["lo"]) * scale, 1)
    mid = round(height * 0.45, 1) if detailed else height / 2
    label = escape(". ".join(t for t in (spot_line(play), result_line(play), outcome) if t), quote=True)
    parts = [f'<svg class="field field-{size}" viewBox="0 0 {width} {height}" role="img" aria-label="{label}" xmlns="http://www.w3.org/2000/svg">',
             f'<rect class="turf" x="0" y="0" width="{width}" height="{height}"/>']
    zones = zones or {}
    for zone_side, goal, lo, hi, team in (("offense", 0, g["lo"], 0, play.get("offense", "")), ("defense", 100, 100, g["hi"], play.get("defense", ""))):
        if g["lo"] < goal < g["hi"] or (goal == 0 and g["lo"] < 0) or (goal == 100 and g["hi"] > 100):
            left, right = x(max(lo, g["lo"])), x(min(hi, g["hi"]))
            if right > left:
                fill, ink = zones.get(zone_side, (None, None))
                fill_style = f' style="fill:{escape(fill)}"' if fill else ""
                parts.append(f'<rect class="endzone" x="{left}" y="0" width="{round(right - left, 1)}" height="{height}"{fill_style}/>')
                if detailed:
                    ink_style = f' style="fill:{escape(ink)}"' if ink else ""
                    parts.append(f'<text class="endzone-label" x="{round((left + right) / 2, 1)}" y="{mid + 5}" text-anchor="middle"{ink_style}>{escape(team)}</text>')
    for yard in range(0, 101, 5):
        if g["lo"] <= yard <= g["hi"]:
            parts.append(f'<line class="{"yard-major" if yard % 10 == 0 else "yard-minor"}" x1="{x(yard)}" y1="0" x2="{x(yard)}" y2="{height}"/>')
    if detailed:
        for yard in range(1, 100):
            if yard % 5 and g["lo"] < yard < g["hi"]:
                for top in (round(height * 0.25, 1), round(height * 0.62, 1)):
                    parts.append(f'<line class="hash" x1="{x(yard)}" y1="{top}" x2="{x(yard)}" y2="{round(top + 6, 1)}"/>')
        for yard in range(10, 100, 10):
            if g["lo"] + 2 <= yard <= g["hi"] - 2:
                parts.append(f'<text class="yard-number" x="{x(yard)}" y="{height - 8}" text-anchor="middle">{yard if yard <= 50 else 100 - yard}</text>')
    parts.append(f'<line class="los" x1="{x(g["x0"])}" y1="0" x2="{x(g["x0"])}" y2="{height}"/>')
    parts.append(f'<line class="marker" x1="{x(g["marker"])}" y1="0" x2="{x(g["marker"])}" y2="{height}"/>')
    state = "helped" if helped else ("hurt" if helped is False else "neutral")
    color = f' style="color:{escape(path_color)}"' if helped else ""
    parts.append(f'<g class="path path-{state}"{color}>')
    head = 9 if detailed else 6
    if g["air_end"] is not None:
        top = max(6, mid - height * 0.32)
        parts.append(f'<path class="air" d="M{x(g["x0"])} {mid} Q{round((x(g["x0"]) + x(g["air_end"])) / 2, 1)} {round(top, 1)} {x(g["air_end"])} {mid}"/>')
        start = x(g["air_end"])
    else:
        start = x(g["x0"])
    end = x(g["end"])
    if g["kind"] == "incomplete":
        parts.append(f'<circle class="target" cx="{x(g["air_end"])}" cy="{mid}" r="{5 if detailed else 4}"/>')
        tip = x(g["air_end"])
    elif end == start == x(g["x0"]):
        parts.append(f'<circle class="ball" cx="{end}" cy="{mid}" r="{5 if detailed else 4}"/>')
        tip = end
    else:
        direction = 1 if end >= start else -1
        if abs(end - start) > head:
            parts.append(f'<line class="run" x1="{start}" y1="{mid}" x2="{round(end - direction * head, 1)}" y2="{mid}"/>')
        back = round(end - direction * head, 1)
        parts.append(f'<polygon class="arrow" points="{end},{mid} {back},{round(mid - head * 0.65, 1)} {back},{round(mid + head * 0.65, 1)}"/>')
        tip = end
    parts.append("</g>")
    text = yardage_label(play)
    if text:
        lx = round(min(max(tip, 24), width - 24), 1)
        parts.append(f'<text class="yardage" x="{lx}" y="{round(mid - head - 6, 1)}" text-anchor="middle">{escape(text)}</text>')
    parts.append("</svg>")
    return "".join(parts)
```

In `static/styles.css`, replace the existing `.field …` block (the lines that start with `.field`) with:

```css
.field{display:block;width:100%;height:auto;margin:6px 0}
.field .turf{fill:var(--wash)}.field .endzone{fill:var(--light)}
.field .endzone-label{font:800 16px var(--display);fill:var(--navy);letter-spacing:1px}
.field .yard-minor{stroke:var(--navy);stroke-opacity:.15;stroke-width:1}.field .yard-major{stroke:var(--navy);stroke-opacity:.3;stroke-width:1.5}
.field .hash{stroke:var(--navy);stroke-opacity:.25;stroke-width:1.5}
.field .yard-number{font:700 15px var(--display);fill:var(--navy);fill-opacity:.45}
.field .los{stroke:var(--navy);stroke-width:2.5}.field .marker{stroke:var(--first-down);stroke-width:2.5}
.field .path{color:var(--navy)}.field .path-hurt{color:var(--muted)}
.field .run{stroke:currentColor;stroke-width:4;stroke-linecap:round}.field .air{fill:none;stroke:currentColor;stroke-width:2.5;stroke-dasharray:6 5}
.field .arrow,.field .ball{fill:currentColor}.field .target{fill:#fff;stroke:currentColor;stroke-width:2.5}
.field .yardage{font:800 17px var(--display);fill:var(--navy)}
.field-strip .yardage{font-size:13px}
```

- [ ] **Step 4: Run all tests**

Run: `.venv/Scripts/python -m unittest discover -s tests`
Expected: `test_field.py` passes. `test_site.py` failures from the removed `team_color` argument belong to Task 5. Note them in the report; don't fix them here.

- [ ] **Step 5: Commit**

```bash
git add src/field.py static/styles.css tests/test_field.py
git commit -S -m "Redraw the field: yard numbers, hash marks, team end zones, arrowheads and outcome colors" -m "Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 5: Wire play text and the new field into the site (`src/site.py`)

**Files:**
- Modify: `src/site.py` (`play_view`, `week_plays`, `edition_context` strip, `build_site` player loops; new `team_colors`)
- Test: `tests/test_site.py`

**Interfaces:**
- Consumes: `playtext.play_line`, `tag`, `helped`, `epa_sentence`, `air_sentence`, `summary` (Tasks 2–3); `field.svg(..., outcome, helped, path_color, zones)` (Task 4); edition `teams` (Task 1); `site.team_bar` (existing).
- Produces:
  - `site.team_colors(edition_data: dict) -> dict[str, str]`
  - `site.play_view(play, player, key_ids=(), teams=None)`, which adds the keys `line`, `tag`, `epa_text` and `air_text`. `positive` now equals `playtext.helped(...)`.
  - `site.week_plays(player, teams=None)`
  - The player week page gets a template variable `summary`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_site.py`:

```python
class PlayViewFaceliftTests(SiteTestCase):
    def defender_play(self):
        edition = fixture_data.golden_edition()
        player = next(p for p in edition["players"] if any(q.get("side") == "defense" and q.get("epa") for q in p.get("plays") or []))
        play = next(q for q in player["plays"] if q.get("side") == "defense" and q.get("epa"))
        return edition, player, play

    def test_play_view_has_line_tag_and_details(self):
        edition, player, play = self.defender_play()
        view = site.play_view(play, player, teams=site.team_colors(edition))
        self.assertTrue(view["line"])
        self.assertEqual(view["tag"], playtext.tag(play, "defense", players_mod.nickname(player["team_name"])))
        self.assertEqual(view["epa_text"], playtext.epa_sentence(play))
        if view["svg_medium"]:
            self.assertIn('class="path path-', str(view["svg_medium"]))

    def test_team_colors_come_from_the_edition_with_player_fallback(self):
        edition = fixture_data.golden_edition()
        colors = site.team_colors(edition)
        self.assertEqual(set(colors), set(edition["teams"]))
        self.assertEqual(site.team_colors({"players": [{"team": "NYG", "team_color": "#0B2265"}]}), {"NYG": "#0B2265"})

    def test_week_page_has_summary_and_plain_lines(self):
        edition, player, _ = self.defender_play()
        slug = next(a["slug"] for a in load_registry(fixture_data.FIXTURES / "alumni.json") if a["gsis_id"] == player["id"])
        page = self.read(self.render(edition) / "players" / slug / edition["id"] / "index.html")
        self.assertIn('class="game-summary"', page)
        self.assertIn(playtext.summary(site.week_plays(player)[1]), page)

    def test_schema_3_editions_still_render(self):
        edition = fixture_data.golden_edition()
        edition.pop("teams")
        edition["schema_version"] = 3
        for p in edition["players"]:
            for q in p.get("plays") or []:
                for key in ("passer_name", "rusher_name", "receiver_name"):
                    q.pop(key, None)
        out = self.render(edition)
        self.assertTrue((out / "index.html").exists())
```

At the top of `tests/test_site.py` add `from src import playtext` and `from src import players as players_mod`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_site.py"`
Expected: FAIL (`team_colors` missing, no `line`/`tag` keys, old `field.svg` call errors).

- [ ] **Step 3: Implement**

In `src/site.py` add `from . import playtext` beside the other relative imports, then:

```python
def team_colors(edition_data):
    """abbr -> team color for every team in the edition; older editions fall back to the alumni's own teams."""
    colors = {p["team"]: p["team_color"] for p in edition_data.get("players", []) if p.get("team") and p.get("team_color")}
    colors.update({abbr: t["color"] for abbr, t in (edition_data.get("teams") or {}).items()})
    return colors


def _drawings(play, player, tag, good, teams):
    colors = dict(teams or {})
    colors.setdefault(player.get("team"), player.get("team_color"))
    zones = {side: team_bar(colors.get(play.get(side)))[:2] for side in ("offense", "defense")}
    path = team_bar(player.get("team_color"))[0]
    draw = lambda size: field.svg(play, size, outcome=tag["text"] if tag else "", helped=good, path_color=path, zones=zones)
    return draw
```

Replace `play_view` with:

```python
def play_view(play, player, key_ids=(), teams=None):
    """`positive` is three-way: True, False, or None (unknown epa, or neutral: it rounds to 0.0 as shown)."""
    epa = play.get("epa")
    side = play.get("side") or ("defense" if player["position"] in DEFENSIVE_POSITIONS else "offense")
    good = playtext.helped(play, side)
    tag = playtext.tag(play, side, pl.nickname(player["team_name"]))
    draw = _drawings(play, player, tag, good, teams)
    medium, large = draw("medium"), draw("large")
    return dict(
        play,
        outcome=play_outcome(play, player) if epa is not None else "",
        spot=field.spot_line(play), result=field.result_line(play) or "",
        svg_medium=Markup(medium) if medium else None, svg_large=Markup(large) if large else None,
        positive=good, key=play.get("play_id") in key_ids,
        line=playtext.play_line(play, player), tag=tag,
        epa_text=playtext.epa_sentence(play), air_text=playtext.air_sentence(play),
    )
```

Change `week_plays(player)` to `week_plays(player, teams=None)` and its last line to `return saved, [play_view(q, player, set(key_ids), teams) for q in ordered]`.

In `edition_context`, replace the strip drawing with the new style (keep `strip_outcome` as today):

```python
        teams = team_colors(edition.data)
        ...
        if top is not None:
            outcome = play_outcome(top, raw) if top.get("epa") is not None else ""
            side = top.get("side") or ("defense" if raw["position"] in DEFENSIVE_POSITIONS else "offense")
            good = playtext.helped(top, side)
            tag = playtext.tag(top, side, pl.nickname(raw["team_name"]))
            view["strip"] = Markup(_drawings(top, raw, tag, good, teams)("strip"))
            view["strip_play_id"] = top["play_id"]
            view["strip_outcome"] = outcome
```

(compute `teams` once before the `for raw, view in zip(...)` loop).

In `build_site`'s player loop, compute `teams = team_colors(e_data)` per edition, call `week_plays(p, teams)`, and pass `summary=playtext.summary(plays)` to the `player_week.html` page call. For the evergreen page, use `team_colors(latest_edition)` in `week_plays(latest, ...)` and `play_view(top, latest, teams=...)`.

Fix the existing `test_site.py` assertions that Task 4 or this task broke. They're the ones that name the old `field.svg` signature or old sizes. The filter-label assertions belong to Task 6, so leave those failing and note them.

- [ ] **Step 4: Run all tests**

Run: `.venv/Scripts/python -m unittest discover -s tests`
Expected: all pass except the old filter-label assertions ("Positive plays for the …"), which Task 6 updates. List them in the report.

- [ ] **Step 5: Commit**

```bash
git add src/site.py tests/test_site.py
git commit -S -m "Wire plain-language lines, tags and the new field into week pages and card strips" -m "Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

### Task 6: Week page layout, cards, filters and copy

**Files:**
- Modify: `templates/player_week.html`, `templates/_play.html`, `static/styles.css`, `static/explorer.js`, `templates/methodology.html`
- Modify: `scripts/check_explorer.py` (only if its selectors change)
- Test: `tests/test_site.py`

**Interfaces:**
- Consumes: the `play_view` keys `line`, `tag`, `epa_text` and `air_text`, the existing `spot`, `description`, `svg_medium`, `svg_large`, `quarter` and `clock`, and the page's `summary` (Task 5).
- Produces:
  - markup classes `game-summary`, `explorer-body`, `explorer-list`, `play-line`, `play-spot`, `tag tag-<key>`, `play-more` and `about-drawings`;
  - filter values `all`, `impact`, `helped` and `hurt`;
  - `data-tag` on each play `<li>`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_site.py` (update the existing tests that assert "Positive plays for the Titans", `data-filter="positive"`, `data-positive` or the old caption string to the new markup):

```python
class WeekPageLayoutTests(SiteTestCase):
    def week_page(self):
        edition = fixture_data.golden_edition()
        player = next(p for p in edition["players"] if p.get("plays"))
        slug = next(a["slug"] for a in load_registry(fixture_data.FIXTURES / "alumni.json") if a["gsis_id"] == player["id"])
        return player, self.read(self.render(edition) / "players" / slug / edition["id"] / "index.html")

    def test_layout_filters_and_cards(self):
        player, page = self.week_page()
        nick = players_mod.nickname(player["team_name"])
        for needle in ('class="game-summary"', 'class="explorer-body"', 'data-filter="impact"', 'data-filter="helped"',
                       'data-filter="hurt"', f">Helped the {nick}<", f">Hurt the {nick}<", 'class="play-line"', '<details class="play-more">'):
            self.assertIn(needle, page)
        self.assertNotIn("Positive plays for the", page)
        self.assertEqual(page.count('class="about-drawings"'), 1)
        self.assertNotIn("Expected points describe the whole play, not the player named on it.", page)

    def test_more_holds_the_play_by_play_and_numbers(self):
        _, page = self.week_page()
        more = page.split('<details class="play-more">')[1].split("</details>")[0]
        self.assertIn("<summary>More</summary>", more)

    def test_explorer_script_uses_the_new_filters(self):
        script = (site.ROOT / "static" / "explorer.js").read_text(encoding="utf-8")
        for needle in ('"helped"', '"hurt"', "data-tag", ".play-line"):
            self.assertIn(needle, script)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m unittest discover -s tests -p "test_site.py"`
Expected: FAIL (old markup).

- [ ] **Step 3: Implement**

`templates/_play.html`, the whole file:

```html
<li class="play{% if p.key %} key{% endif %}{% if p.impact %} impact{% endif %}" id="play-{{ p.play_id }}" data-tag="{{ p.tag.key if p.tag else '' }}">
  <button type="button" class="play-pick" aria-controls="play-stage">
    <span class="play-meta">{{ p.quarter }} · {{ p.clock }}</span>
    {% if p.tag %}<span class="tag tag-{{ p.tag.key }}">{{ p.tag.text }}</span>{% endif %}
    <span class="play-line">{{ p.line }}</span>
    {% if p.spot %}<span class="play-spot">{{ p.spot }}</span>{% endif %}
  </button>
  {% if p.svg_medium %}{{ p.svg_medium }}{% endif %}
  <details class="play-more"><summary>More</summary>
    {% if p.description %}<p>{{ p.description }}</p>{% endif %}
    {% if p.epa_text %}<p>{{ p.epa_text }}</p>{% endif %}
    {% if p.air_text %}<p>{{ p.air_text }}</p>{% endif %}
  </details>
  {% if p.svg_large %}<template class="play-large">{{ p.svg_large }}</template>{% endif %}
</li>
```

`templates/player_week.html`: replace the `{% if played %}<section class="section explorer" …>…</section>` block with:

```html
<section class="section explorer" aria-labelledby="plays-head" style="--team: {{ player.team_color }}; --bar: {{ player.bar }}; --bar-ink: {{ player.ink }}">
  <div class="section-head"><h2 id="plays-head">{{ "Recorded plays" if plays_saved else "Key moments" }} ({{ plays | length }})</h2></div>
  {% if summary %}<p class="game-summary">{{ summary }}</p>{% endif %}
  <p class="section-note">The play-by-play names a player only when he throws, runs, is targeted, makes a tackle or a charted defensive play. Most snaps never appear here; see his snaps above.{% if lineman %} Offensive linemen are rarely named in play-by-play; their snaps and team results tell more.{% endif %}</p>
  {% if not plays_saved %}<p class="section-note">The full play list was not saved for this week; these are its key moments.</p>{% endif %}
  {% if plays %}
  <div class="explorer-filters" hidden>
    <button type="button" data-filter="all" aria-pressed="true">All</button>
    <button type="button" data-filter="impact" aria-pressed="false">Impact plays</button>
    <button type="button" data-filter="helped" aria-pressed="false">Helped the {{ nickname }}</button>
    <button type="button" data-filter="hurt" aria-pressed="false">Hurt the {{ nickname }}</button>
  </div>
  <div class="explorer-body">
    <ol class="explorer-list">{% for p in plays %}{% include "_play.html" %}{% endfor %}</ol>
    <div id="play-stage" class="play-stage" aria-live="polite" hidden></div>
  </div>
  <p class="about-drawings"><strong>About these drawings.</strong> {{ caption }} Expected points describe the whole play, not one player.</p>
  {% endif %}
</section>
```

`static/explorer.js`: change `matches` and the no-drawing fallback:

```js
  function matches(item, filter) {
    var tag = item.getAttribute("data-tag");
    if (filter === "impact") return item.classList.contains("impact");
    if (filter === "helped") return tag === "big" || tag === "helped";
    if (filter === "hurt") return tag === "hurt";
    return true;
  }
```

and in `select`: `var text = item.querySelector(".play-line");`.

`static/styles.css`: remove the old `.js-explorer .explorer-list .field{display:none}`, `.play[aria-current="true"]{…}`, `.explorer-filters button[aria-pressed="true"]{…}`, `.play-pick{…}` and `.play-result{…}` rules. Append:

```css
.game-summary{margin:0 0 10px;font-size:18px;font-weight:600;color:var(--navy)}
.explorer-filters{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 18px}
.explorer-filters button{font:600 14px Inter,Arial,sans-serif;padding:7px 14px;border:1px solid var(--line);background:var(--card);color:var(--navy);cursor:pointer}
.explorer-filters button[aria-pressed="true"]{background:var(--bar,var(--brand));color:var(--bar-ink,#fff);border-color:var(--bar,var(--brand))}
.explorer-list{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.explorer-list .play{background:var(--card);border:1px solid var(--line);border-left:4px solid transparent;padding:12px 14px;margin:0}
.explorer-list .play[aria-current="true"]{border-left-color:var(--bar,var(--brand))}
.play-pick{all:unset;cursor:pointer;display:grid;grid-template-columns:1fr auto;gap:2px 12px;width:100%}
.play-pick:focus-visible{outline:3px solid var(--brand);outline-offset:3px}
.play-pick .play-meta{grid-column:1;grid-row:1}
.tag{grid-column:2;grid-row:1;justify-self:end;align-self:start;font-size:12px;font-weight:700;padding:2px 8px;border:1.5px solid var(--line);color:var(--navy);white-space:nowrap}
.tag-big{background:var(--bar,var(--brand));border-color:var(--bar,var(--brand));color:var(--bar-ink,#fff)}
.tag-helped{border-color:var(--team,var(--brand))}
.tag-hurt{border-color:var(--muted);color:var(--muted)}
.play-line{grid-column:1/-1;font-size:16px;font-weight:600;line-height:1.4;color:var(--navy)}
.play-spot{grid-column:1/-1;font-size:13px;color:var(--muted)}
.play-more{margin-top:6px;font-size:13px}.play-more summary{font-weight:600;color:var(--brand)}.play-more p{margin:4px 0}
.about-drawings{margin:18px 0 0;font-size:12px;color:var(--muted)}
.play-stage .field{margin:0}
@media (min-width:900px){.explorer-body{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr);gap:24px;align-items:start}.play-stage{position:sticky;top:16px}.js-explorer .explorer-list .field{display:none}}
@media (max-width:899px){.play-stage{display:none !important}}
```

`templates/methodology.html`: in the "Player pages and the play explorer" section, replace the sentence "The offense always moves left to right." with:

```html
The offense always moves left to right, like a TV broadcast. The arrow and its +/− label show which way the ball went; the path is drawn in the alum's team color when the play helped his team and in gray when it hurt. Each play also says it in words: "Big play" (it helped by 2 or more expected points), "Helped" or "Hurt".
```

If `scripts/check_explorer.py` reads selectors that changed (`plays explorer-list` → `explorer-list`), update it to match.

- [ ] **Step 4: Run all tests and the build check**

```bash
.venv/Scripts/python -m unittest discover -s tests
.venv/Scripts/python -m src.site build --out _site --check
```
Expected: PASS; build renders every page.

- [ ] **Step 5: Commit**

```bash
git add templates static scripts tests
git commit -S -m "Week page facelift: two-column explorer, play cards with tags and details, styled filters, one drawings note" -m "Co-Authored-By: <model> <noreply@anthropic.com>"
```

The controller adds `` - `playtext.py`: plain-language play lines, outcome tags and the game summary for week pages. `` to the `CLAUDE.md` Map, because subagents can't write `CLAUDE.md`.

---

## After merge (owner-approved, separate PR)

1. On `chore/rebuild-names`, run `.venv/Scripts/python -m src.edition --season 2026 --week N --rebuild` for weeks 1 and 2 (add `--historical`) and 3 (without it). Confirm the only changes are `schema_version`, `teams`, the three name fields per play and `generated_at`.
2. Add a real-data test: the lines for Cisco's and Newsome's Week 3 plays read as plain sentences, for example "Cisco sacked Goff for a 10-yard loss." and "Newsome broke up Ward's pass to Robinson."
3. Take desktop and phone screenshots of Cisco's Week 3 page for the owner, then open the PR.
