import copy
import json
import tempfile
import unittest
from pathlib import Path

import fixture_data
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
        self.assertAlmostEqual(rows[0]["snaps"][0]["share"], 65 / delpit["snaps"]["team_defense"], places=3)

    def test_snaps_show_every_phase_labeled_with_its_share(self):
        week2 = edition_with(2)
        everette = next(p for p in week2["players"] if p["name"] == "Daylen Everette")
        row = players.game_log(players.appearances([week2], everette["id"]))[0]
        self.assertEqual([(s["abbr"], s["count"]) for s in row["snaps"]], [("DEF", 8), ("ST", 11)])
        self.assertEqual(row["snaps_text"], "8 DEF (15%) · 11 ST (48%)")
        everette["snaps"]["team_st"] = None
        row = players.game_log(players.appearances([week2], everette["id"]))[0]
        self.assertEqual(row["snaps_text"], "8 DEF (15%) · 11 ST")
        capehart = next(p for p in week2["players"] if p["name"] == "DeMonte Capehart")
        self.assertEqual(players.game_log(players.appearances([week2], capehart["id"]))[0]["snaps_text"], "—")

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
        self.assertIn("Thrown at 4 times in coverage. 2 were completed, for 17 yards", lines["Coverage"])
        self.assertEqual(lines["Pass rush"], "Pressured the quarterback once.")
        self.assertEqual(lines["Tackling"], "Made 5 tackles and missed none.")
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

    def test_receiver_with_no_recorded_targets_has_no_targets_line(self):
        e = edition_with(2, **{"Carnell Tate": {"usage": {"targets": None, "team_targets": None, "air_yards": None, "team_air_yards": None}}})
        tate = next(p for p in e["players"] if p["name"] == "Carnell Tate")["id"]
        lines = players.season_lines(players.appearances([e], tate), "WR")
        self.assertNotIn("Targets", [l["label"] for l in lines])
        self.assertNotIn("0 targets", " ".join(l["text"] for l in lines))

    def test_rb_lines_note_partial_play_data(self):
        week2, week3 = edition_with(2), edition_with(3)
        for p in week3["players"]:
            if p["name"] == "Kaytron Allen":
                p.pop("plays", None)
        allen = next(p for p in week2["players"] if p["name"] == "Kaytron Allen")["id"]
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([week2, week3], allen), "RB")}
        self.assertIn("(based on 1 of 2 weeks)", lines["Carries"])

    def test_defense_lines_note_partial_play_data(self):
        week2 = edition_with(2)
        week3 = edition_with(3, **{"Grant Delpit": {"team": "NYJ", "team_name": "New York Jets"}})
        for p in week3["players"]:
            if p["name"] == "Grant Delpit":
                p.pop("plays", None)
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([week2, week3], "00-0036282"), "SAF")}
        self.assertIn("(based on 1 of 2 weeks)", lines["Impact plays"])

    def test_rb_lines_absent_without_any_play_data(self):
        week2 = edition_with(2)
        for p in week2["players"]:
            if p["name"] == "Kaytron Allen":
                p.pop("plays", None)
        allen = next(p for p in week2["players"] if p["name"] == "Kaytron Allen")["id"]
        lines = players.season_lines(players.appearances([week2], allen), "RB")
        self.assertNotIn("Carries", [l["label"] for l in lines])
        self.assertNotIn("Receiving", [l["label"] for l in lines])
        self.assertNotIn("0 carries", " ".join(l["text"] for l in lines))

    def test_snap_share_uses_matched_pairs_not_mismatched_totals(self):
        week2 = edition_with(2, **{"Grant Delpit": {"snaps": {"offense": 0, "defense": 50, "st": 0, "team_offense": 0, "team_defense": None, "team_st": 0}}})
        week3 = edition_with(3, **{"Grant Delpit": {"snaps": {"offense": 0, "defense": 10, "st": 0, "team_offense": 0, "team_defense": 20, "team_st": 0}}})
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([week2, week3], "00-0036282"), "SAF")}
        self.assertIn("60 defensive snaps", lines["Snaps"])
        self.assertIn("50% of the team's", lines["Snaps"])
        self.assertNotIn("300%", lines["Snaps"])
        self.assertIn("(share based on 1 of 2 weeks)", lines["Snaps"])

    def test_defensive_impact_rate_uses_snaps_from_plays_weeks_only(self):
        week2 = edition_with(2)
        week3 = edition_with(3, **{"Grant Delpit": {
            "team": "NYJ", "team_name": "New York Jets",
            "snaps": {"offense": 0, "defense": 200, "st": 0, "team_offense": 0, "team_defense": 200, "team_st": 0},
        }})
        for p in week3["players"]:
            if p["name"] == "Grant Delpit":
                p.pop("plays", None)
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([week2, week3], "00-0036282"), "SAF")}
        # Only week 2's 65 defensive snaps count (its `plays` supplied the 1 sack); week 3's 200 snaps
        # have no matching play data and must not pad the denominator past the 100-snap threshold.
        self.assertNotIn("per 100", lines["Impact plays"])

    def test_qb_efficiency_threshold_counts_only_rows_with_epa(self):
        plays = [{"roles": ["passer"], "qb_dropback": 1, "qb_kneel": 0, "qb_spike": 0, "qb_epa": 0.1, "epa": 0.1, "complete_pass": 1, "cp": 0.6}] * 40
        plays += [{"roles": ["passer"], "qb_dropback": 1, "qb_kneel": 0, "qb_spike": 0, "qb_epa": None, "epa": None, "complete_pass": None, "cp": None}] * 20
        e = edition_with(2, **{"J.J. McCarthy": {"plays": plays, "availability": {"label": "Played", "evidence": "x"}}})
        qb = next(p for p in e["players"] if p["name"] == "J.J. McCarthy")["id"]
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([e], qb), "QB")}
        self.assertIn("60 dropbacks", lines["Dropbacks"])
        self.assertNotIn("Expected points per dropback", lines["Dropbacks"])

    def test_rb_efficiency_threshold_counts_only_rows_with_epa(self):
        carries = [{"roles": ["rusher"], "rush_attempt": 1, "epa": 0.1}] * 20
        carries += [{"roles": ["rusher"], "rush_attempt": 1, "epa": None}] * 15
        e = edition_with(2, **{"Kaytron Allen": {"plays": carries}})
        allen = next(p for p in e["players"] if p["name"] == "Kaytron Allen")["id"]
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([e], allen), "RB")}
        self.assertIn("35 carries", lines["Carries"])
        self.assertNotIn("Expected points per carry", lines["Carries"])

    def test_wr_when_targeted_threshold_counts_only_rows_with_epa(self):
        targets = [{"roles": ["receiver"], "epa": 0.2}] * 10
        targets += [{"roles": ["receiver"], "epa": None}] * 10
        e = edition_with(2, **{"Carnell Tate": {"plays": targets}})
        tate = next(p for p in e["players"] if p["name"] == "Carnell Tate")["id"]
        lines = players.season_lines(players.appearances([e], tate), "WR")
        self.assertNotIn("When targeted", [l["label"] for l in lines])

    def test_rb_catches_known_only_over_targets_with_known_completion(self):
        targets = [{"roles": ["receiver"], "complete_pass": 1}] * 3
        targets += [{"roles": ["receiver"], "complete_pass": 0}] * 2
        targets += [{"roles": ["receiver"], "complete_pass": None}] * 5
        e = edition_with(2, **{"Kaytron Allen": {"plays": targets}})
        allen = next(p for p in e["players"] if p["name"] == "Kaytron Allen")["id"]
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([e], allen), "RB")}
        self.assertIn("10 targets, 3 catches", lines["Receiving"])
        self.assertIn("(catches known for 5 of 10 targets)", lines["Receiving"])

    def test_receiver_shares_use_matched_pairs_with_their_own_notes(self):
        a = edition_with(2, **{"Carnell Tate": {"usage": {"targets": 5, "team_targets": None, "air_yards": 50, "team_air_yards": 100}}})
        b = edition_with(3, **{"Carnell Tate": {"usage": {"targets": 10, "team_targets": 40, "air_yards": 100, "team_air_yards": 300}}})
        tate = next(p for p in a["players"] if p["name"] == "Carnell Tate")["id"]
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([a, b], tate), "WR")}
        self.assertIn("15 targets", lines["Targets"])
        self.assertIn("25% of team targets", lines["Targets"])  # 10/40 only: the week without team_targets is excluded
        self.assertIn("38% of team air yards", lines["Targets"])  # (50+100)/(100+300), both weeks matched
        self.assertEqual(lines["Targets"].count("(share based on 1 of 2 weeks)"), 1)

    def test_defense_charting_lines_note_partial_weeks(self):
        week2 = edition_with(2, **{"Grant Delpit": {"charting": {
            "targets": None,
            "coverage": {"targets": 4, "completions": 2, "yards": 17, "touchdowns": 0, "interceptions": 0},
            "pass_rush": {"pressures": 1, "hurries": 0, "qb_hits": 0, "sacks": 1, "blitzes": 2},
            "tackling": None, "rushing": None, "broken_tackles": None,
        }}})
        week3 = edition_with(3, **{"Grant Delpit": {"charting": {
            "targets": None, "coverage": None,
            "pass_rush": {"pressures": 2, "hurries": 1, "qb_hits": 0, "sacks": 0, "blitzes": 1},
            "tackling": {"missed": 1, "attempts": 4}, "rushing": None, "broken_tackles": None,
        }}})
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([week2, week3], "00-0036282"), "SAF")}
        self.assertEqual(lines["Coverage"], "Thrown at 4 times in coverage. 2 were completed, for 17 yards (based on 1 of 2 weeks).")
        self.assertEqual(lines["Tackling"], "Made 3 tackles and missed 1 (based on 1 of 2 weeks).")
        self.assertEqual(lines["Pass rush"], "Pressured the quarterback 3 times.")

    def test_season_pass_rush_never_claims_zero_pressures(self):
        # An all-zero PFR pass-rush week is not stored, so a season total of 0 can't be told from missing data.
        week2 = edition_with(2, **{"Grant Delpit": {"charting": {
            "targets": None, "coverage": None, "pass_rush": {"pressures": 0, "hurries": 0, "qb_hits": 0, "sacks": 0, "blitzes": 2},
            "tackling": None, "rushing": None, "broken_tackles": None}}})
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([week2], "00-0036282"), "SAF")}
        self.assertNotIn("Pass rush", lines)

    def test_receiver_charted_targets_note_partial_weeks(self):
        a = edition_with(2, **{"Carnell Tate": {"charting": {
            "targets": {"charted": 5, "catchable": 3, "contested": 0, "contested_catches": 0, "drops": 0},
            "coverage": None, "pass_rush": None, "tackling": None, "rushing": None, "broken_tackles": None,
        }}})
        b = edition_with(3, **{"Carnell Tate": {"charting": {
            "targets": None, "coverage": None, "pass_rush": None, "tackling": None, "rushing": None, "broken_tackles": None,
        }}})
        tate = next(p for p in a["players"] if p["name"] == "Carnell Tate")["id"]
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([a, b], tate), "WR")}
        self.assertEqual(lines["Pass catching"], "3 of his 5 charted targets were catchable. No drops (based on 1 of 2 weeks).")

    def test_defense_tackles_line(self):
        plays = [{"roles": ["solo_tackle_1"], "side": "defense", "impact": None}] * 3
        plays += [{"roles": ["assist_tackle_1", "qb_hit_1"], "side": "defense", "impact": "QB hit"}] * 1
        plays += [{"roles": ["passer"], "side": "offense", "impact": None}] * 1
        e = edition_with(2, **{"Grant Delpit": {"plays": plays}})
        lines = {l["label"]: l["text"] for l in players.season_lines(players.appearances([e], "00-0036282"), "SAF")}
        self.assertIn("Tackles", lines)
        self.assertIn("4 tackles", lines["Tackles"])
