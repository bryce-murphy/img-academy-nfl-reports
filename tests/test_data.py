import gzip
import hashlib
import json
import tempfile
import unittest
from unittest import mock

from src import data
from src.data import PLAY_COLUMNS, DataError, load_sources, parse_csv, specifications, week_filter
from src.errors import NotReady
from src.evidence import RECORDED_ROLES


class ParseCsvTests(unittest.TestCase):
    def test_schema_drift_fails_closed(self):
        with self.assertRaises(DataError):
            parse_csv(b"name\na\n", "test.csv", {"gsis_id"})

    def test_keep_filter_retains_only_matching_rows(self):
        rows = parse_csv(b"week,game_id\n1,a\n2,b\n2,c\n", "pbp.csv", {"week"}, week_filter(2))
        self.assertEqual([r["game_id"] for r in rows], ["b", "c"])

    def test_filter_matching_nothing_is_not_an_empty_source(self):
        self.assertEqual(parse_csv(b"week\n1\n", "pbp.csv", {"week"}, week_filter(5)), [])

    def test_file_without_rows_is_an_empty_source(self):
        with self.assertRaises(DataError):
            parse_csv(b"week\n", "pbp.csv", {"week"})

    def test_gzip_payload_is_filtered(self):
        payload = gzip.compress(b"week,x\n3,a\n4,b\n")
        self.assertEqual(len(parse_csv(payload, "p.csv.gz", {"week"}, week_filter(3))), 1)

    def test_pbp_specification_requires_week_column(self):
        self.assertIn("week", specifications(2026)["pbp"][2])


SCHEDULE_V1_CSV = b"game_id,season,game_type,gameday,home_score,away_score\n2026_02_PHI_TEN,2026,REG,2026-09-20,20,24\n"
SCHEDULE_V2_CSV = SCHEDULE_V1_CSV + b"2026_02_CLE_TB,2026,REG,2026-09-20,19,23\n"
# nflverse publishes the schedule only as games.csv.gz (the plain games.csv was dropped)
SCHEDULE_V1 = gzip.compress(SCHEDULE_V1_CSV, mtime=0)
SCHEDULE_V2 = gzip.compress(SCHEDULE_V2_CSV, mtime=0)


def release(payload):
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    return json.dumps({"assets": [{"name": "games.csv.gz", "updated_at": "2026-09-27T21:46:18Z", "digest": digest}]}).encode()


class LoadSourcesTests(unittest.TestCase):
    """nflverse replaces assets in place; the listed digest can lead the download by a few seconds."""

    def load(self, responses):
        calls = []

        def fake_get(url):
            calls.append(url)
            return responses.pop(0)

        with tempfile.TemporaryDirectory() as cache, mock.patch.object(data, "get_bytes", fake_get), mock.patch.object(data, "pause") as pause:
            datasets, manifest, _ = load_sources(2026, cache, historical=True, only={"schedule"})
        return datasets, manifest, calls, pause

    def test_checksum_mismatch_during_a_replacement_is_retried(self):
        responses = [release(SCHEDULE_V2), SCHEDULE_V1, release(SCHEDULE_V2), SCHEDULE_V2]
        datasets, manifest, calls, pause = self.load(responses)
        self.assertEqual(len(datasets["schedule"]), 2)
        self.assertEqual(manifest["schedule"]["sha256"], hashlib.sha256(SCHEDULE_V2).hexdigest())
        self.assertEqual(len(calls), 4)
        pause.assert_called_once_with(data.RETRY_SECONDS)

    def test_schedule_is_read_from_the_gzipped_asset(self):
        self.assertEqual(specifications(2026)["schedule"][1], "games.csv.gz")
        datasets, manifest, calls, _ = self.load([release(SCHEDULE_V1), SCHEDULE_V1])
        self.assertEqual(len(datasets["schedule"]), 1)
        self.assertTrue(manifest["schedule"]["url"].endswith("/schedules/games.csv.gz"))

    def test_persistent_checksum_mismatch_fails_closed(self):
        responses = [release(SCHEDULE_V2), SCHEDULE_V1] * data.DOWNLOAD_ATTEMPTS
        with self.assertRaisesRegex(DataError, "Cannot verify schedule: Upstream checksum mismatch: schedule"):
            self.load(responses)


class PlayColumnTests(unittest.TestCase):
    def test_pbp_requires_the_three_player_name_columns(self):
        self.assertTrue({"passer_player_name", "rusher_player_name", "receiver_player_name"} <= specifications(2026)["pbp"][2])

    def test_pbp_requires_every_column_player_pages_read(self):
        self.assertTrue(set(PLAY_COLUMNS) <= specifications(2026)["pbp"][2])

    def test_stats_and_snaps_require_usage_and_snap_columns(self):
        self.assertTrue({"targets", "target_share", "receiving_air_yards", "air_yards_share"} <= specifications(2026)["stats"][2])
        self.assertTrue({"team", "offense_snaps", "defense_snaps", "st_snaps"} <= specifications(2026)["snaps"][2])

    def test_pbp_requires_the_columns_recorded_plays_and_charting_consume(self):
        required = specifications(2026)["pbp"][2]
        self.assertTrue({"qtr", "time", "play_type", "fumble_lost", "third_down_failed", "fourth_down_failed"} <= required)
        self.assertTrue({f"{role}_player_id" for role in RECORDED_ROLES} <= required)


class ErrorTests(unittest.TestCase):
    def test_not_ready_is_a_data_error_and_carries_the_week(self):
        error = NotReady("waiting", week=3)
        self.assertIsInstance(error, DataError)
        self.assertEqual(error.week, 3)


if __name__ == "__main__":
    unittest.main()
