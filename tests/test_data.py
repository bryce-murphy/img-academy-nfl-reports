import gzip
import unittest

from src.data import DataError, parse_csv, specifications, week_filter
from src.errors import NotReady


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


class ErrorTests(unittest.TestCase):
    def test_not_ready_is_a_data_error_and_carries_the_week(self):
        error = NotReady("waiting", week=3)
        self.assertIsInstance(error, DataError)
        self.assertEqual(error.week, 3)


if __name__ == "__main__":
    unittest.main()
