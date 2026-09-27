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


class MainHeadlineTests(unittest.TestCase):
    def test_writes_fallback_headline_without_overwriting_an_existing_one(self):
        data = fixture_data.load()[0]
        fixture_manifest = fixture_data.load()[1]
        games = fixture_data.week_games(data)
        golden_edition = fixture_data.golden_edition()

        def run():
            with mock.patch.object(ed, "due_week", return_value=(2, games)), \
                 mock.patch.object(ed, "build_week", return_value=(golden_edition, fixture_manifest, Readiness())):
                return ed.main(["--season", "2026", "--week", "2", "--out", tmp])

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


if __name__ == "__main__":
    unittest.main()
