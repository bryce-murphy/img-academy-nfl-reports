import unittest
from datetime import date

from src.data import DataError, parse_csv
from src.report import choose_week, participation, safe_image, unique, validate_games, validate_offense


class AccuracyTests(unittest.TestCase):
    def test_missing_stats_never_mean_dnp(self):
        self.assertEqual(participation({}, [], {})[0], 'Participation unverified')

    def test_zero_stat_row_does_not_establish_absence(self):
        self.assertEqual(participation({}, [], {'attempts': '0'})[0], 'Participation unverified')

    def test_special_teams_only_counts_as_played(self):
        snap = {'offense_snaps': '0', 'defense_snaps': '0', 'st_snaps': '8'}
        self.assertEqual(participation(snap, [], {})[0], 'Played')

    def test_zero_snaps_never_infer_benching(self):
        snap = {'offense_snaps': '0', 'defense_snaps': '0', 'st_snaps': '0'}
        self.assertEqual(participation(snap, [], {})[0], 'No snaps recorded')

    def test_partial_snap_coverage_remains_unknown(self):
        self.assertEqual(participation({'offense_snaps': '0'}, [], {})[0], 'Participation unverified')

    def test_conflicting_participation_is_flagged(self):
        snap = {'offense_snaps': '0', 'defense_snaps': '0', 'st_snaps': '0'}
        self.assertEqual(participation(snap, [{}], {})[0], 'Conflicting evidence')

    def test_ambiguous_roster_is_rejected(self):
        with self.assertRaises(DataError):
            unique([{}, {}], 'roster')

    def test_schema_drift_fails_closed(self):
        with self.assertRaises(DataError):
            parse_csv(b'name\na\n', 'test.csv', {'gsis_id'})

    def test_offseason_skips_scheduled_reports(self):
        game = {'season': '2025', 'week': '22', 'game_type': 'POST', 'gameday': '2026-02-08', 'home_score': '20', 'away_score': '10'}
        self.assertEqual(choose_week([game], 2025, date(2026, 2, 24), ['REG', 'POST'], scheduled=True), (None, []))

    def test_monday_game_is_not_skipped(self):
        game = {'season': '2026', 'week': '2', 'game_type': 'REG', 'gameday': '2026-09-21', 'home_score': '', 'away_score': ''}
        with self.assertRaises(DataError):
            choose_week([game], 2026, date(2026, 9, 22), ['REG'])

    def test_future_week_cannot_be_rendered(self):
        game = {'season': '2026', 'week': '3', 'game_type': 'REG', 'gameday': '2026-09-28', 'home_score': '', 'away_score': ''}
        with self.assertRaises(DataError):
            choose_week([game], 2026, date(2026, 9, 25), ['REG'], week=3)

    def test_final_score_mismatch_blocks_report(self):
        game = {'game_id': 'g', 'home_score': '24', 'away_score': '7'}
        play = {'game_id': 'g', 'play_id': '1', 'desc': 'END GAME', 'total_home_score': '21', 'total_away_score': '7'}
        with self.assertRaises(DataError):
            validate_games([game], [play])

    def test_score_without_end_marker_is_not_final(self):
        with self.assertRaises(DataError):
            validate_games([{'game_id': 'g'}], [])

    def test_duplicate_play_ids_block_report(self):
        with self.assertRaises(DataError):
            validate_games([], [{'game_id': 'g', 'play_id': '1'}] * 2)

    def test_stat_correction_mismatch_blocks_report(self):
        with self.assertRaises(DataError):
            validate_offense({'passing_yards': '250'}, [{'passer_player_id': 'p', 'passing_yards': '249'}], 'p')

    def test_image_urls_are_restricted_and_escaped(self):
        self.assertEqual(safe_image('javascript:alert(1)', 'a', 'image'), '')
        self.assertEqual(safe_image('https://evil.example/test', 'a', 'image'), '')
        self.assertIn('&quot;', safe_image('https://a.espncdn.com/a', 'a"b', 'image'))


if __name__ == '__main__':
    unittest.main()
