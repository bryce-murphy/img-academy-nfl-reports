import unittest
from datetime import date

from src import evidence as ev
from src.errors import DataError, NotReady

ACTIVE = {"status": "ACT"}


def label(snap=None, plays=(), stats=None, roster=ACTIVE, has_game=True, complete=False):
    return ev.availability(snap or {}, list(plays), stats or {}, roster, has_game, complete)[0]


class AvailabilityTests(unittest.TestCase):
    def test_missing_stats_never_mean_dnp(self):
        self.assertEqual(label(), ev.UNVERIFIED)

    def test_zero_stat_row_does_not_establish_absence(self):
        self.assertEqual(label(stats={"attempts": "0"}), ev.UNVERIFIED)

    def test_special_teams_only_counts_as_played(self):
        self.assertEqual(label(snap={"offense_snaps": "0", "defense_snaps": "0", "st_snaps": "8"}), ev.PLAYED)

    def test_zero_snap_row_never_infers_benching(self):
        self.assertEqual(label(snap={"offense_snaps": "0", "defense_snaps": "0", "st_snaps": "0"}), ev.NO_SNAPS)

    def test_partial_snap_coverage_remains_unknown(self):
        self.assertEqual(label(snap={"offense_snaps": "0"}), ev.UNVERIFIED)

    def test_involvement_with_zero_snaps_is_conflicting(self):
        zero = {"offense_snaps": "0", "defense_snaps": "0", "st_snaps": "0"}
        self.assertEqual(label(snap=zero, plays=[{}]), ev.CONFLICT)
        self.assertEqual(label(snap=zero, stats={"carries": "2"}), ev.CONFLICT)

    def test_involvement_without_snaps_counts_as_played(self):
        self.assertEqual(label(plays=[{}]), ev.PLAYED)
        self.assertEqual(label(stats={"targets": "1"}), ev.PLAYED)

    def test_roster_statuses_become_labels(self):
        self.assertEqual(label(roster={"status": "INA"}), "Inactive for the game")
        self.assertEqual(label(roster={"status": "DEV"}), "Practice squad")
        self.assertEqual(label(roster={"status": "RES"}), "Reserve list")
        self.assertEqual(label(roster={"status": "CUT"}), "Released")

    def test_positive_snaps_outrank_roster_status(self):
        self.assertEqual(label(snap={"defense_snaps": "3"}, roster={"status": "INA"}), ev.PLAYED)

    def test_no_weekly_roster_record(self):
        self.assertEqual(label(roster=None, has_game=False), ev.NOT_ON_ROSTER)

    def test_bye_week(self):
        self.assertEqual(label(has_game=False), ev.BYE)

    def test_absent_from_complete_snap_table(self):
        self.assertEqual(label(complete=True), ev.NO_SNAPS)

    def test_unknown_roster_status_falls_through(self):
        self.assertEqual(label(roster={"status": "EXE"}), ev.UNVERIFIED)

    def test_negative_snaps_are_rejected(self):
        with self.assertRaises(DataError):
            label(snap={"offense_snaps": "-1"})


class SnapTableTests(unittest.TestCase):
    def rows(self, count, offense=True, defense=True):
        rows = [{"pfr_player_id": f"P{i}", "offense_snaps": "0", "defense_snaps": "0"} for i in range(count)]
        if offense:
            rows[0]["offense_snaps"] = "60"
        if defense:
            rows[1]["defense_snaps"] = "55"
        return rows

    def test_twenty_two_players_with_both_units_is_complete(self):
        self.assertTrue(ev.snap_table_complete(self.rows(22)))

    def test_twenty_one_players_is_incomplete(self):
        self.assertFalse(ev.snap_table_complete(self.rows(21)))

    def test_missing_a_unit_is_incomplete(self):
        self.assertFalse(ev.snap_table_complete(self.rows(30, defense=False)))


class FormattingTests(unittest.TestCase):
    def test_quarter_labels(self):
        self.assertEqual([ev.quarter_label(q) for q in ("1", "4", "5", "6", "")], ["Q1", "Q4", "OT", "2OT", ""])

    def test_clean_numbers(self):
        self.assertEqual(ev.clean("5"), 5)
        self.assertEqual(ev.clean("0.843"), 0.84)
        self.assertIsNone(ev.clean(""))

    def test_ambiguous_rows_are_rejected(self):
        with self.assertRaises(DataError):
            ev.unique([{}, {}], "roster")


class WeekTests(unittest.TestCase):
    def test_offseason_skips_scheduled_reports(self):
        game = {"season": "2025", "week": "22", "game_type": "POST", "gameday": "2026-02-08", "home_score": "20", "away_score": "10"}
        self.assertEqual(ev.choose_week([game], 2025, date(2026, 2, 24), ["REG", "POST"], scheduled=True), (None, []))

    def test_monday_game_without_score_is_not_ready(self):
        game = {"season": "2026", "week": "2", "game_type": "REG", "gameday": "2026-09-21", "home_score": "", "away_score": ""}
        with self.assertRaises(NotReady) as ctx:
            ev.choose_week([game], 2026, date(2026, 9, 22), ["REG"])
        self.assertEqual(ctx.exception.week, 2)

    def test_future_week_cannot_be_rendered(self):
        game = {"season": "2026", "week": "3", "game_type": "REG", "gameday": "2026-09-28", "home_score": "", "away_score": ""}
        with self.assertRaises(NotReady):
            ev.choose_week([game], 2026, date(2026, 9, 25), ["REG"], week=3)


class GameValidationTests(unittest.TestCase):
    def test_final_score_mismatch_blocks_report(self):
        game = {"game_id": "g", "home_score": "24", "away_score": "7"}
        play = {"game_id": "g", "play_id": "1", "desc": "END GAME", "total_home_score": "21", "total_away_score": "7"}
        with self.assertRaises(DataError) as ctx:
            ev.validate_games([game], [play])
        self.assertNotIsInstance(ctx.exception, NotReady)

    def test_missing_end_marker_is_not_ready(self):
        with self.assertRaises(NotReady):
            ev.validate_games([{"game_id": "g"}], [])

    def test_duplicate_play_ids_block_report(self):
        with self.assertRaises(DataError):
            ev.validate_games([], [{"game_id": "g", "play_id": "1"}] * 2)

    def test_yardage_mismatch_is_reported_not_raised(self):
        mismatches = ev.yardage_mismatches({"passing_yards": "250"}, [{"passer_player_id": "p", "passing_yards": "249"}], "p")
        self.assertEqual(mismatches, ["passing_yards"])

    def test_matching_yardage_passes(self):
        plays = [{"rusher_player_id": "p", "rushing_yards": "20"}, {"rusher_player_id": "p", "rushing_yards": "4", "play_type": "run"}]
        self.assertEqual(ev.yardage_mismatches({"rushing_yards": "24"}, plays, "p"), [])


class RankingTests(unittest.TestCase):
    def test_defensive_score(self):
        self.assertEqual(ev.performance_score({"def_sacks": "1", "def_tackles_solo": "5"}), 6.5)

    def test_offensive_bonuses(self):
        stats = {"receiving_yards": "100", "receiving_tds": "1", "receptions": "7"}
        self.assertEqual(ev.performance_score(stats), 6 + 5 + 4.0)

    def player(self, pid, name, score, offense=0, label=ev.PLAYED):
        return {"id": pid, "name": name, "score": score, "snaps": {"offense": offense, "defense": 0, "st": 0}, "availability": {"label": label}}

    def test_rank_orders_score_then_snaps_then_name(self):
        players = [
            self.player("ol", "Olin Line", 0, offense=70),
            self.player("b", "Bea Back", 2.0),
            self.player("a", "Al Ace", 2.0),
            self.player("x", "Xavier Out", 9.0, label="Inactive for the game"),
        ]
        self.assertEqual(ev.rank(players), ["a", "b", "ol"])


if __name__ == "__main__":
    unittest.main()
