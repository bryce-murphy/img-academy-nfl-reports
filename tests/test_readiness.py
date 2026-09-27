import unittest

import fixture_data
from src.readiness import assess

GAME = {"game_id": "g1", "gameday": "2026-09-28", "away_team": "PHI", "home_team": "CHI", "away_score": "24", "home_score": "20"}
MANIFEST = {"rosters": {"updated_at": "2026-09-29T07:00:00Z"}}


def snap_rows(team, count=22):
    rows = [{"game_id": "g1", "team": team, "pfr_player_id": f"{team}{i}", "offense_snaps": "0", "defense_snaps": "0"} for i in range(count)]
    rows[0]["offense_snaps"] = "60"
    rows[1]["defense_snaps"] = "55"
    return rows


def ready_data():
    return {
        "pbp": [{"game_id": "g1", "desc": "END GAME"}],
        "stats": [{"season": "2026", "week": "3"}],
        "snaps": snap_rows("PHI") + snap_rows("CHI"),
        "injuries": [{"season": "2026", "week": "3"}],
    }


class ReadinessTests(unittest.TestCase):
    def check(self, data=None, manifest=MANIFEST, game=GAME):
        return assess(data or ready_data(), manifest, [game], 2026, 3)

    def test_complete_week_is_ready(self):
        report = self.check()
        self.assertEqual(report.missing(), [])
        self.assertTrue(report.ready(final=False))

    def test_missing_final_score_is_required(self):
        report = self.check(game=dict(GAME, home_score=""))
        self.assertIn("final score for g1", report.missing_required)

    def test_missing_end_of_game_is_required(self):
        data = ready_data()
        data["pbp"] = []
        self.assertIn("play-by-play end of game for g1", self.check(data).missing_required)

    def test_missing_weekly_stats_is_required(self):
        data = ready_data()
        data["stats"] = [{"season": "2026", "week": "2"}]
        self.assertIn("weekly player statistics", self.check(data).missing_required)

    def test_rosters_must_update_after_the_last_game(self):
        report = self.check(manifest={"rosters": {"updated_at": "2026-09-28T07:00:00Z"}})
        self.assertIn("weekly rosters updated after the last game", report.missing_required)

    def test_incomplete_snaps_only_wait_until_the_final_attempt(self):
        data = ready_data()
        data["snaps"] = snap_rows("PHI")
        report = self.check(data)
        self.assertEqual(report.missing_optional, ["snap counts for CHI in g1"])
        self.assertFalse(report.ready(final=False))
        self.assertTrue(report.ready(final=True))

    def test_missing_injury_report_is_optional(self):
        data = ready_data()
        data["injuries"] = []
        self.assertEqual(self.check(data).missing_optional, ["injury report"])

    def test_week_two_fixture_is_ready(self):
        data, manifest, _ = fixture_data.load()
        report = assess(data, manifest, fixture_data.week_games(data), 2026, 2)
        self.assertEqual(report.missing(), [])


if __name__ == "__main__":
    unittest.main()
