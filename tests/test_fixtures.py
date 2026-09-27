import unittest
from collections import defaultdict

import fixture_data
from src import evidence as ev


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.manifest, cls.registry = fixture_data.load()
        cls.ids = {a["name"]: a["gsis_id"] for a in cls.registry}

    def status(self, name, week="2"):
        rows = [r for r in self.data["rosters"] if r["gsis_id"] == self.ids[name] and r["week"] == week]
        return rows[0]["status"] if rows else None

    def test_thirteen_players_and_sixteen_games(self):
        self.assertEqual(len(self.registry), 13)
        self.assertEqual(len(fixture_data.week_games(self.data)), 16)

    def test_every_week_two_game_has_an_end_marker(self):
        ended = {p["game_id"] for p in self.data["pbp"] if p["desc"].strip().upper() == "END GAME"}
        self.assertTrue({g["game_id"] for g in fixture_data.week_games(self.data)} <= ended)

    def test_weekly_roster_statuses(self):
        self.assertEqual(self.status("Warren Brinson"), "INA")
        self.assertEqual(self.status("DeMonte Capehart"), "INA")
        self.assertEqual(self.status("Evan Neal"), "DEV")
        self.assertIsNone(self.status("Xavier Thomas"))
        self.assertEqual(self.status("J.J. McCarthy"), "ACT")

    def test_snap_tables_are_complete_for_every_team(self):
        by_team = defaultdict(list)
        for row in self.data["snaps"]:
            by_team[(row["game_id"], row["team"])].append(row)
        self.assertEqual(len(by_team), 32)
        self.assertTrue(all(ev.snap_table_complete(rows) for rows in by_team.values()))

    def test_reserve_rows_carry_reserve_codes(self):
        reserved = [r for r in fixture_data.roster_samples() if r["status"] == "RES"]
        self.assertTrue(reserved)
        self.assertTrue(all(r["status_description_abbr"].startswith("R") for r in reserved))

    def test_elevated_practice_squad_players_appear_active(self):
        elevated = [r for r in fixture_data.roster_samples() if r["status"] == "ACT"]
        self.assertTrue(elevated)
        by_pfr_id = defaultdict(list)
        for row in self.data["snaps"]:
            by_pfr_id[row["pfr_player_id"]].append(row)
        found = False
        for player in elevated:
            for snap in by_pfr_id.get(player["pfr_id"], []):
                counts = [ev.num(snap.get(key)) for key in ev.SNAP_KEYS]
                if any(value is not None and value > 0 for value in counts):
                    label = ev.availability(snap, [], {}, {"status": "ACT"}, True, False)[0]
                    self.assertEqual(label, ev.PLAYED)
                    found = True
                    break
            if found:
                break
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
