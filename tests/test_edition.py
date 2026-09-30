import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fixture_data
from src import edition as ed
from src import editorial
from src import evidence as ev
from src import moves
from src.errors import DataError, NotReady
from src.readiness import Readiness

EXPECTED_LABELS = {
    "Grant Delpit": "Played",
    "DeMonte Capehart": "Inactive for the game",
    "Carnell Tate": "Played",
    "Nolan Smith": "Played",
    "Warren Brinson": "Inactive for the game",
    "Andre Cisco": "Played",
    "J.J. McCarthy": "No snaps recorded",
    "Evan Neal": "Practice squad",
    "Xavier Thomas": "Not on an NFL roster",
    "Cesar Ruiz": "Played",
    "Kaytron Allen": "Played",
    "Tyler Booker": "Played",
    "Daylen Everette": "Played",
}


def build(data=None, **kwargs):
    fixture, _, registry = fixture_data.load()
    data = data or fixture
    return ed.build_edition(data, registry, fixture_data.week_games(data), 2026, 2, generated_at=fixture_data.GENERATED_AT, **kwargs)


def player(edition, name):
    return next(p for p in edition["players"] if p["name"] == name)


def alum(name):
    return next(a for a in fixture_data.load()[2] if a["name"] == name)


class GoldenTests(unittest.TestCase):
    def test_matches_golden_file(self):
        edition = build()
        path = fixture_data.FIXTURES / "expected_edition.json"
        if os.environ.get("UPDATE_GOLDEN"):
            path.write_bytes(ed.dump_json(edition))
        self.assertEqual(edition, json.loads(path.read_text(encoding="utf-8")))


class ChartingTests(unittest.TestCase):
    """FTN and PFR charting are optional extras shown as counts; bad rows are withheld, never guessed."""

    def test_receiver_targets_from_ftn(self):
        self.assertEqual(player(build(), "Carnell Tate")["charting"]["targets"], {"charted": 5, "catchable": 3, "contested": 0, "contested_catches": 0, "drops": 0})

    def test_defender_coverage_pass_rush_and_tackling_from_pfr(self):
        delpit = player(build(), "Grant Delpit")["charting"]
        self.assertEqual(delpit["coverage"], {"targets": 4, "completions": 2, "yards": 17, "touchdowns": 0, "interceptions": 0})
        self.assertEqual(delpit["pass_rush"], {"pressures": 1, "hurries": 0, "qb_hits": 0, "sacks": 1, "blitzes": 2})
        self.assertEqual(delpit["tackling"], {"missed": 0, "attempts": 5})

    def test_inconsistent_coverage_row_is_withheld_with_a_warning(self):
        edition = build()
        cisco = player(edition, "Andre Cisco")["charting"]
        self.assertIsNone(cisco["coverage"])
        self.assertEqual(cisco["tackling"], {"missed": 1, "attempts": 6})
        self.assertTrue(any("Andre Cisco" in w and "coverage" in w for w in edition["warnings"]))

    def test_rusher_contact_yards_from_pfr(self):
        allen = player(build(), "Kaytron Allen")["charting"]
        self.assertEqual(allen["rushing"], {"carries": 5, "before_contact": 16, "after_contact": 8, "broken_tackles": 0})

    def mutate(self, name, key, match, **changes):
        data, _, _ = fixture_data.load()
        for row in data[name]:
            if row[key] == match:
                row.update(changes)
        return data

    def test_malformed_optional_rows_do_not_abort_the_edition(self):
        data, _, _ = fixture_data.load()
        data["ftn"].append(dict(data["ftn"][0], nflverse_play_id="NA"))
        data["ftn"].append(dict(data["ftn"][0], week=""))
        self.assertEqual(player(build(data), "Carnell Tate")["charting"]["targets"]["charted"], 5)

    def test_blank_pfr_fields_withhold_the_line_instead_of_reading_zero(self):
        edition = build(self.mutate("pfr_def", "pfr_player_name", "Grant Delpit", def_missed_tackles="NA", def_completions_allowed=""))
        delpit = player(edition, "Grant Delpit")["charting"]
        self.assertIsNone(delpit["coverage"])
        self.assertIsNone(delpit["tackling"])
        self.assertEqual(delpit["pass_rush"]["sacks"], 1)

    def test_unknown_ftn_flags_are_not_counted_as_no(self):
        data, _, _ = fixture_data.load()
        tate_plays = {(p["game_id"], p["play_id"]) for p in data["pbp"] if p.get("receiver_player_id") == alum("Carnell Tate")["gsis_id"]}
        first = next(r for r in data["ftn"] if (r["nflverse_game_id"], r["nflverse_play_id"]) in tate_plays)
        first["is_drop"] = "NA"
        self.assertEqual(player(build(data), "Carnell Tate")["charting"]["targets"]["charted"], 4)

    def test_pfr_row_for_another_team_is_withheld(self):
        edition = build(self.mutate("pfr_def", "pfr_player_name", "Grant Delpit", team="TB"))
        self.assertIsNone(player(edition, "Grant Delpit")["charting"])  # his only PFR row, so nothing is charted
        self.assertTrue(any("Grant Delpit" in w and "team" in w for w in edition["warnings"]))

    def test_contact_yards_that_disagree_with_the_box_score_are_withheld(self):
        edition = build(self.mutate("pfr_rush", "pfr_player_name", "Kaytron Allen", rushing_yards_after_contact="20"))
        self.assertIsNone(player(edition, "Kaytron Allen")["charting"])
        self.assertTrue(any("Kaytron Allen" in w and "contact" in w for w in edition["warnings"]))

    def test_duplicate_charting_rows_are_ambiguous_and_withheld(self):
        data, _, _ = fixture_data.load()
        delpit = next(r for r in data["pfr_def"] if r["pfr_player_name"] == "Grant Delpit")
        data["pfr_def"].append(dict(delpit, def_targets="9"))
        edition = build(data)
        charting = player(edition, "Grant Delpit")["charting"]
        self.assertTrue(charting is None or charting["coverage"] is None)
        self.assertTrue(any("Grant Delpit" in w and "duplicate" in w for w in edition["warnings"]))

    def test_missing_charting_sources_leave_charting_empty(self):
        data, _, _ = fixture_data.load()
        for name in ("ftn", "pfr_def", "pfr_rec", "pfr_rush"):
            data[name] = []
        tate = player(build(data), "Carnell Tate")
        self.assertIsNone(tate["charting"])


class EditionTests(unittest.TestCase):
    def test_availability_labels(self):
        self.assertEqual({p["name"]: p["availability"]["label"] for p in build()["players"]}, EXPECTED_LABELS)

    def test_identity_and_counts(self):
        edition = build()
        self.assertEqual(edition["id"], "2026-week-02")
        self.assertEqual((edition["counts"]["followed"], edition["counts"]["played"]), (13, 8))
        self.assertTrue(edition["publication_ready"])

    def test_ranking_holds_only_players_who_played(self):
        edition = build()
        played = {p["id"] for p in edition["players"] if p["availability"]["label"] == ev.PLAYED}
        ranking = edition["featured_ranking"]
        self.assertEqual(set(ranking), played)
        self.assertLess(ranking.index(alum("Carnell Tate")["gsis_id"]), ranking.index(alum("Cesar Ruiz")["gsis_id"]))

    def test_up_next_for_week_three(self):
        info = player(build(), "Warren Brinson")["next_game"]
        self.assertEqual(
            (info["kind"], info["opponent"], info["home_away"], info["kickoff_et"], info["venue"], info["team"]),
            ("game", "ATL", "home", "20:15", "Lambeau Field", "GB"),
        )

    def test_historical_replay_has_no_up_next(self):
        edition = build(historical=True)
        self.assertTrue(all(p["next_game"] is None for p in edition["players"]))
        self.assertEqual(edition["label"], "Historical replay")

    def test_traded_player_up_next_uses_current_team(self):
        data, _, _ = fixture_data.load()
        for row in data["current_rosters"]:
            if row["gsis_id"] == alum("Carnell Tate")["gsis_id"]:
                row["team"] = "CLE"
        tate = player(build(data), "Carnell Tate")
        self.assertEqual(tate["team"], "TEN")
        self.assertTrue(tate["team_changed"])
        self.assertEqual((tate["next_game"]["team"], tate["next_game"]["opponent"]), ("CLE", "CAR"))

    def test_cut_player_has_no_up_next(self):
        data, _, _ = fixture_data.load()
        for row in data["current_rosters"]:
            if row["gsis_id"] == alum("Carnell Tate")["gsis_id"]:
                row["status"] = "CUT"
        tate = player(build(data), "Carnell Tate")
        self.assertIsNone(tate["next_game"])

    def test_retired_player_has_no_up_next(self):
        data, _, _ = fixture_data.load()
        for row in data["current_rosters"]:
            if row["gsis_id"] == alum("Carnell Tate")["gsis_id"]:
                row["status"] = "RET"
        tate = player(build(data), "Carnell Tate")
        self.assertIsNone(tate["next_game"])

    def test_yardage_mismatch_withholds_only_that_player(self):
        data, _, _ = fixture_data.load()
        for row in data["stats"]:
            if row["player_id"] == alum("Carnell Tate")["gsis_id"]:
                row["receiving_yards"] = str(int(float(row["receiving_yards"])) + 3)
        edition = build(data)
        tate = player(edition, "Carnell Tate")
        self.assertTrue(tate["stats_withheld"])
        self.assertTrue(all(m["value"] is None for m in tate["metrics"]))
        self.assertTrue(any("Carnell Tate" in w for w in edition["warnings"]))
        self.assertEqual(player(edition, "Grant Delpit")["availability"]["label"], ev.PLAYED)

    def test_conflicting_evidence_blocks_social_drafts(self):
        data, _, _ = fixture_data.load()
        for row in data["snaps"]:
            if row["pfr_player_id"] == alum("Carnell Tate")["pfr_id"]:
                row.update(offense_snaps="0", defense_snaps="0", st_snaps="0")
        edition = build(data)
        self.assertEqual(player(edition, "Carnell Tate")["availability"]["label"], ev.CONFLICT)
        self.assertFalse(edition["publication_ready"])

    def test_display_fields_are_safe(self):
        edition = build()
        quarters = {k["quarter"] for p in edition["players"] for k in p["key_plays"]}
        self.assertTrue(quarters <= {"Q1", "Q2", "Q3", "Q4", "OT"})
        self.assertTrue(all(re.fullmatch(r"#[0-9a-fA-F]{6}", p["team_color"]) for p in edition["players"]))

    def test_write_edition_uses_lf_line_endings(self):
        with tempfile.TemporaryDirectory() as tmp:
            ed.write_edition(build(), {"schedule": {"rows": 1}}, Path(tmp) / "2026-week-02")
            raw = (Path(tmp) / "2026-week-02" / "edition.json").read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertEqual(json.loads(raw)["id"], "2026-week-02")

    def test_registry_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "alumni.json"
            entry = {"gsis_id": "00-0000001", "name": "A", "source_url": "https://example.org"}
            path.write_text(json.dumps([entry, entry]), encoding="utf-8")
            with self.assertRaises(DataError):
                ed.load_registry(path)

    def test_build_week_waits_for_missing_end_of_game(self):
        data, manifest, registry = fixture_data.load()
        data["pbp"] = [p for p in data["pbp"] if p["desc"].strip().upper() != "END GAME"]

        def sources(season, *, week=None, only=None, historical=False):
            return data, manifest, []

        with self.assertRaises(NotReady):
            ed.build_week(2026, 2, fixture_data.week_games(data), historical=False, final=True, registry=registry, sources=sources)

    def test_build_week_from_fixture(self):
        data, manifest, registry = fixture_data.load()

        def sources(season, *, week=None, only=None, historical=False):
            return data, manifest, []

        edition, sources_out, report = ed.build_week(2026, 2, fixture_data.week_games(data), historical=False, final=False, registry=registry, sources=sources)
        self.assertEqual((edition["id"], report.missing()), ("2026-week-02", []))
        self.assertIs(sources_out, manifest)

    def test_postseason_game_types_map_to_post_stats(self):
        self.assertEqual(ed.stat_season_type("REG"), "REG")
        self.assertEqual(ed.stat_season_type("WC"), "POST")
        self.assertEqual(ed.stat_season_type("SB"), "POST")


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

    def test_schema_version_is_three(self):
        self.assertEqual(build()["schema_version"], 3)

    def test_a_player_without_recorded_plays_has_an_empty_list(self):
        self.assertEqual(player(build(), "Tyler Booker")["plays"], [])

    def test_lateral_is_one_if_either_flag_is_one_zero_only_if_both_are_explicitly_zero(self):
        def lateral(reception, rush):
            row = {"play_id": "7", "posteam": "CLE", "defteam": "TB", "desc": "x", "qtr": "1", "time": "15:00"}
            if reception is not None:
                row["lateral_reception"] = reception
            if rush is not None:
                row["lateral_rush"] = rush
            return ed.play_record(row, "00-1", "TB", lambda t: t)["lateral"]

        self.assertEqual(lateral("1", None), 1)
        self.assertEqual(lateral(None, "1"), 1)
        self.assertEqual(lateral("0", "0"), 0)
        self.assertIsNone(lateral("0", None))
        self.assertIsNone(lateral(None, "0"))
        self.assertIsNone(lateral(None, None))


class MainHeadlineTests(unittest.TestCase):
    def test_writes_fallback_headline_without_overwriting_an_existing_one(self):
        data = fixture_data.load()[0]
        fixture_manifest = fixture_data.load()[1]
        games = fixture_data.week_games(data)
        golden_edition = fixture_data.golden_edition()

        def run():
            with mock.patch.object(ed, "due_week", return_value=(2, games)), \
                 mock.patch.object(ed, "build_week", return_value=(golden_edition, fixture_manifest, Readiness())):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    code = ed.main(["--season", "2026", "--week", "2", "--out", tmp])
                self.assertIn("Built ", output.getvalue())
                return code

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run(), 0)
            headline_path = Path(tmp) / "2026-week-02" / "editorial.toml"
            raw = headline_path.read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertEqual(editorial.load(headline_path)["source"], "fallback")

            owner_copy = dict(editorial.fallback(golden_edition), headline="Owner headline")
            headline_path.write_bytes(editorial.dumps(owner_copy).encode("utf-8"))

            self.assertEqual(run(), 0)
            self.assertIn("Owner headline", headline_path.read_text(encoding="utf-8"))


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


class MoveAttachTests(unittest.TestCase):
    def build(self, **kwargs):
        return build(**kwargs)

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


if __name__ == "__main__":
    unittest.main()
