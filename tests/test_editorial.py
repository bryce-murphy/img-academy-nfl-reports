import tempfile
import unittest

import fixture_data
from src import editorial
from src import evidence as ev


def no_one_played():
    edition = fixture_data.golden_edition()
    for p in edition["players"]:
        p["availability"] = {"label": ev.BYE, "evidence": "No game on this week's schedule"}
    edition["featured_ranking"] = []
    edition["counts"]["played"] = 0
    return edition


class TomlTests(unittest.TestCase):
    def test_round_trip_keeps_quotes_unicode_and_collapses_newlines(self):
        original = {
            "source": "owner", "model": "", "featured_player_id": "00-0036282",
            "headline": 'Delpit\'s “two-sack” day \\o/ <b>🏈',
            "dek": "line one\nline two\ttabbed",
            "lead": 'He said "yes".',
            "alternates": ["A", "B"],
        }
        loaded = editorial.loads(editorial.dumps(original))
        self.assertEqual(loaded["headline"], original["headline"])
        self.assertEqual(loaded["dek"], "line one line two tabbed")
        self.assertEqual(loaded["lead"], 'He said "yes".')
        self.assertEqual(loaded["alternates"], ["A", "B"])
        self.assertEqual(loaded["schema"], 1)


class FallbackTests(unittest.TestCase):
    def test_fallback_passes_its_own_review(self):
        edition = fixture_data.golden_edition()
        result = editorial.review(editorial.fallback(edition), edition)
        self.assertEqual((result.errors, result.problems), ([], []))

    def test_fallback_features_the_top_ranked_player(self):
        edition = fixture_data.golden_edition()
        self.assertEqual(editorial.fallback(edition)["featured_player_id"], edition["featured_ranking"][0])

    def test_fallback_without_played_players_passes_review(self):
        edition = no_one_played()
        copy = editorial.fallback(edition)
        self.assertEqual(copy["featured_player_id"], "")
        result = editorial.review(copy, edition)
        self.assertEqual((result.errors, result.problems), ([], []))

    def test_metric_phrases_use_the_singular_for_one(self):
        self.assertEqual(editorial.metric_phrase(1, "sacks"), "1 sack")
        self.assertEqual(editorial.metric_phrase(5, "solo tackles"), "5 solo tackles")


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.edition = fixture_data.golden_edition()
        self.copy = editorial.fallback(self.edition)
        self.ids = {p["name"]: p["id"] for p in self.edition["players"]}

    def review(self, **changes):
        return editorial.review(dict(self.copy, **changes), self.edition)

    def test_featured_player_must_have_played(self):
        self.assertIn("did not play", " ".join(self.review(featured_player_id=self.ids["J.J. McCarthy"]).errors))

    def test_featured_player_must_exist(self):
        self.assertTrue(self.review(featured_player_id="00-9999999").errors)

    def test_length_limits(self):
        self.assertTrue(self.review(headline="x" * 71).errors)
        self.assertTrue(self.review(dek="x" * 161).errors)
        self.assertTrue(self.review(lead="word " * 81).errors)

    def test_exactly_two_alternates(self):
        self.assertTrue(self.review(alternates=["only one"]).errors)

    def test_numbers_must_come_from_the_data(self):
        self.assertTrue(any("314" in p for p in self.review(headline="Delpit posts 314 tackles").problems))

    def test_spelled_totals_are_allowed(self):
        self.assertEqual(self.review(headline="Two sacks. Two winning sides.").problems, [])

    def test_naming_a_player_who_did_not_play_is_a_problem(self):
        problems = self.review(lead="Warren Brinson watched the win from the sideline.").problems
        self.assertTrue(any("Warren Brinson" in p for p in problems))

    def test_blocked_terms_need_support(self):
        self.assertTrue(any("bench" in p for p in self.review(dek="Delpit was benched late.").problems))

    def test_unknown_names_are_notes_not_problems(self):
        result = self.review(lead="Grant Delpit chased Justin Jefferson all day.")
        self.assertEqual(result.problems, [])
        self.assertIn("name not found in the data: Justin Jefferson", result.notes)


class CheckCommandTests(unittest.TestCase):
    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            edition = fixture_data.golden_edition()
            directory = fixture_data.write_edition_dir(tmp, edition)
            self.assertEqual(editorial.main(["check", str(directory)]), 0)
            (directory / "editorial.toml").write_text(editorial.dumps(dict(editorial.fallback(edition), headline="x" * 90)), encoding="utf-8")
            self.assertEqual(editorial.main(["check", str(directory)]), 1)

    def test_check_all_without_editions_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(editorial.main(["check", "--all", "--editions", tmp]), 0)


if __name__ == "__main__":
    unittest.main()
