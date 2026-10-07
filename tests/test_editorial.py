import contextlib
import io
import json
import tempfile
import unittest
from unittest import mock
from datetime import date, datetime
from pathlib import Path

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


    def test_card_order_survives_a_round_trip_and_is_omitted_when_unset(self):
        base = {"featured_player_id": "00-0036282", "headline": "H", "dek": "D", "lead": "L", "alternates": ["A", "B"]}
        self.assertNotIn("card_order", editorial.loads(editorial.dumps(base)))
        loaded = editorial.loads(editorial.dumps(dict(base, card_order=["00-0036282", "00-0041438"])))
        self.assertEqual(loaded["card_order"], ["00-0036282", "00-0041438"])


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

    def test_fallback_dek_tells_the_second_storyline_without_a_count(self):
        edition = fixture_data.golden_edition()
        players = {p["id"]: p for p in edition["players"]}
        first, second = (players[pid]["name"] for pid in edition["featured_ranking"][:2])
        dek = editorial.fallback(edition)["dek"]
        self.assertIn(second, dek)
        self.assertNotIn(first, dek)
        self.assertNotIn("alumni", dek)
        self.assertLessEqual(len(dek), editorial.LIMITS["dek"])

    def test_fallback_lead_carries_the_alumni_count(self):
        edition = fixture_data.golden_edition()
        lead = editorial.fallback(edition)["lead"]
        self.assertIn(f"{edition['counts']['played']} of the {edition['counts']['followed']} IMG Academy alumni", lead)

    def test_fallback_with_one_player_passes_review(self):
        edition = fixture_data.golden_edition()
        edition["featured_ranking"] = edition["featured_ranking"][:1]
        copy = editorial.fallback(edition)
        result = editorial.review(copy, edition)
        self.assertEqual(result.errors, [])
        self.assertTrue(copy["dek"])

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

    def test_card_order_accepts_players_who_played(self):
        played = self.edition["featured_ranking"][:2]
        self.assertEqual(self.review(card_order=played).errors, [])
        self.assertEqual(self.review(card_order=[]).errors, [])

    def test_card_order_rejects_bad_entries(self):
        played = self.edition["featured_ranking"]
        absent = next(p["id"] for p in self.edition["players"] if p["availability"]["label"] != ev.PLAYED)
        for value, expected in (("00-1", "list of player IDs"), ([1], "list of player IDs"), (["00-9999999"], "not a player in this edition"),
                                ([absent], "did not play"), ([played[0], played[0]], "more than once")):
            with self.subTest(value=value):
                self.assertIn(expected, " ".join(self.review(card_order=value).errors))

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

    def test_team_snap_totals_are_not_allowed_numbers(self):
        player = next(p for p in self.edition["players"] if p["availability"]["label"] == ev.PLAYED)
        player["snaps"] = {"offense": 0, "defense": 47, "st": 2, "team_offense": 61, "team_defense": 973, "team_st": 29}
        facts = editorial.fact_sheet(self.edition)
        entry = next(e for e in facts["players"] if e["id"] == player["id"])
        self.assertEqual(entry["snaps"], {"offense": 0, "defense": 47, "st": 2})
        self.assertNotIn(973.0, editorial.allowed_numbers(facts))

    def test_naming_a_player_who_did_not_play_is_a_problem(self):
        problems = self.review(lead="Warren Brinson watched the win from the sideline.").problems
        self.assertTrue(any("Warren Brinson" in p for p in problems))

    def test_blocked_terms_need_support(self):
        self.assertTrue(any("bench" in p for p in self.review(dek="Delpit was benched late.").problems))

    def test_blocked_terms_are_scoped_to_the_named_player(self):
        problems = self.review(headline="Grant Delpit injured on the final play").problems
        self.assertTrue(any("injur" in p for p in problems))

    def test_blocked_terms_without_a_named_player_need_support(self):
        problems = self.review(dek="An injury-filled week for the alumni.").problems
        self.assertTrue(any("injur" in p for p in problems))

    def test_img_alone_is_an_error_but_img_academy_is_fine(self):
        # Week 1's first Claude draft said "IMG alumni"; public copy always says "IMG Academy".
        self.assertTrue(any("IMG Academy" in e for e in self.review(dek="IMG alumni kept meeting across the line.").errors))
        self.assertTrue(any("IMG Academy" in e for e in self.review(alternates=["IMG's best week", "Week 2"]).errors))
        self.assertEqual(self.review(dek="IMG Academy alumni kept meeting across the line.").errors, [])

    def test_unknown_names_are_notes_not_problems(self):
        result = self.review(lead="Grant Delpit chased Justin Jefferson all day.")
        self.assertEqual(result.problems, [])
        self.assertIn("name not found in the data: Justin Jefferson", result.notes)

    def test_name_check_ignores_sentence_breaks_and_descriptors(self):
        # Week 2's real false alarms: runs joined across a full stop, and a description before a name.
        lead = ("Grant Delpit had a sack at Tampa Bay. On the other side, Fellow Brown Grant Delpit kept going. "
                "Cleveland won. Fifteen IMG Academy alumni played in Week 2.")
        self.assertEqual(self.review(lead=lead).notes, [])

    def test_unknown_name_in_front_of_a_known_name_is_still_flagged(self):
        result = self.review(lead="Justin Jefferson Grant Delpit met after the game. Fellow Brown Grant Delpit smiled.")
        self.assertIn("name not found in the data: Justin Jefferson", result.notes)
        self.assertFalse(any("Fellow" in note for note in result.notes))

    def test_name_check_keeps_initials_and_still_flags_unknown_names(self):
        result = self.review(lead="Coach Kevin Stefanski praised Grant Delpit. J.J. Watt watched.")
        self.assertTrue(any("Kevin Stefanski" in note for note in result.notes))
        self.assertIn("name not found in the data: J.J. Watt", result.notes)


class CheckCommandTests(unittest.TestCase):
    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            edition = fixture_data.golden_edition()
            directory = fixture_data.write_edition_dir(tmp, edition)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(editorial.main(["check", str(directory)]), 0)
                (directory / "editorial.toml").write_text(editorial.dumps(dict(editorial.fallback(edition), headline="x" * 90)), encoding="utf-8")
                self.assertEqual(editorial.main(["check", str(directory)]), 1)
            self.assertIn("::error file=", output.getvalue())
            self.assertIn("headline is 90 characters; the limit is 70", output.getvalue())

    def test_check_all_without_editions_passes(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(editorial.main(["check", "--all", "--editions", tmp]), 0)
        self.assertIn("Checked 0 edition(s).", output.getvalue())


MOVE = {"kind": "moved_after_game", "from": "MIN", "to": "NYG", "from_name": "Minnesota Vikings", "to_name": "New York Giants",
        "from_color": "#4F2683", "to_color": "#0B2265", "status": None, "last_week_with_old_team": 2, "last_game_date": "2026-09-20"}


def moved_edition():
    e = fixture_data.golden_edition()
    e["players"][0]["move"] = dict(MOVE)
    return e


def note(**changes):
    base = {"player_id": fixture_data.golden_edition()["players"][0]["id"], "kind": "trade", "date": date(2026, 9, 21),
            "details": "for a 2027 fourth-round pick", "source": "https://www.giants.com/news/x"}
    base.update(changes)
    return base


class RosterNoteTests(unittest.TestCase):
    def errors(self, *notes, edition=None):
        return editorial.check_roster_notes(list(notes), edition or moved_edition())

    def test_valid_note(self):
        self.assertEqual(self.errors(note()), [])
        self.assertEqual(self.errors(note(details="")), [])
        self.assertEqual(self.errors({k: v for k, v in note().items() if k != "details"}), [])

    def test_each_rule(self):
        cases = {
            "has no roster move": note(player_id="nobody"),
            "kind must be one of": note(kind="swap"),
            "does not fit": note(kind="release"),
            "after this edition's data": note(date=date(2026, 9, 24)),
            "before his game": note(date=date(2026, 9, 19)),
            "allowed site": note(source="https://theathletic.com/x"),
            "the limit is 100": note(details="x" * 101),
            "one line": note(details="for a\npick"),
            "link": note(details="see www.giants.com"),
            '"IMG" alone': note(details="an IMG alum"),
            "uses 'injur'": note(details="after an injury"),
            "uses 'physical'": note(details="after a failed physical"),
            "uses 'reserve'": note(details="from the reserve/non-football list"),
            "repeats the team": note(details="to the Giants for a pick"),
            "repeats the date": note(details="on Sep 28 for a pick"),
            "unknown fields": note(team="NYG"),
        }
        for expected, bad in cases.items():
            with self.subTest(expected):
                self.assertTrue(any(expected in e for e in self.errors(bad)), self.errors(bad))

    def test_unhashable_kind_is_a_kind_error(self):
        self.assertTrue(any("kind must be one of" in m for m in self.errors(note(kind=["trade"]))))

    def test_departure_kinds_need_a_departure(self):
        e = moved_edition()
        e["players"][0]["move"] = dict(MOVE, kind="left_after_game", to=None, to_name=None, to_color=None, status="CUT")
        self.assertEqual(self.errors(note(kind="release", details=""), edition=e), [])
        self.assertTrue(any("does not fit" in m for m in self.errors(note(kind="trade"), edition=e)))

    def test_duplicate_player(self):
        self.assertTrue(any("already has a note" in m for m in self.errors(note(), note())))

    def test_date_must_be_a_plain_date(self):
        self.assertTrue(any("date must be a date" in m for m in self.errors(note(date=datetime(2026, 9, 21, 10, 0)))))
        self.assertTrue(any("date must be a date" in m for m in self.errors(note(date="2026-09-21"))))

    def test_review_reports_note_errors(self):
        e = moved_edition()
        copy_ = dict(editorial.fallback(e), roster_moves=[note(source="https://example.com/x")])
        self.assertTrue(any("allowed site" in m for m in editorial.review(copy_, e).errors))

    def test_warnings(self):
        e = moved_edition()
        name = e["players"][0]["name"]
        self.assertEqual(editorial.roster_note_warnings(editorial.fallback(e), e),
                         [f"{name} has a roster move with no sourced note; the site shows the neutral line"])
        self.assertEqual(editorial.roster_note_warnings(dict(editorial.fallback(e), roster_moves=[note()]), e),
                         ["Roster move notes: avoid paywalled stories (for example ESPN+)"])

    def test_dumps_round_trips_notes_and_writes_commented_stubs(self):
        e = moved_edition()
        text = editorial.dumps(dict(editorial.fallback(e), roster_moves=[note()]))
        self.assertEqual(editorial.loads(text)["roster_moves"], [note()])
        stub_text = editorial.dumps(editorial.fallback(e), stubs=[e["players"][0]])
        self.assertIn("# [[roster_moves]]", stub_text)
        self.assertIn(f'# player_id = "{e["players"][0]["id"]}"', stub_text)
        self.assertIn("Vikings → Giants (moved after the game)", stub_text)
        self.assertNotIn("roster_moves", editorial.loads(stub_text))
        noted = editorial.dumps(dict(editorial.fallback(e), roster_moves=[note()]), stubs=[e["players"][0]])
        self.assertNotIn("# [[roster_moves]]", noted)

    def test_headline_fact_sheet_never_sees_moves(self):
        e = moved_edition()
        e["players"][0]["move"]["to_name"] = "Marker Team Zebras"
        self.assertNotIn("Zebras", json.dumps(editorial.fact_sheet(e)))

    def draft(self, toml_text):
        e = moved_edition()
        with tempfile.TemporaryDirectory() as tmp:
            directory = fixture_data.write_edition_dir(Path(tmp), e)
            if toml_text is not None:
                (directory / "editorial.toml").write_text(toml_text, encoding="utf-8")
            with mock.patch.object(editorial, "produce", return_value=(editorial.fallback(e), {})), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(editorial.main(["draft", str(directory)]), 0)
            return editorial.loads((directory / "editorial.toml").read_text(encoding="utf-8")), (directory / "editorial.toml").read_text(encoding="utf-8"), e

    def test_draft_keeps_owner_notes_and_adds_stubs(self):
        e = moved_edition()
        kept = editorial.dumps(dict(editorial.fallback(e), roster_moves=[note()]))
        parsed, text, _ = self.draft(kept)
        self.assertEqual(parsed["roster_moves"], [note()])
        self.assertNotIn("# [[roster_moves]]", text)
        _, text, _ = self.draft(None)
        self.assertIn("# [[roster_moves]]", text)
        _, text, _ = self.draft("not = [valid")
        self.assertIn("# [[roster_moves]]", text)

    def test_invalid_toml_is_a_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = fixture_data.write_edition_dir(Path(tmp), fixture_data.golden_edition())
            (directory / "editorial.toml").write_text(editorial.dumps(editorial.fallback(fixture_data.golden_edition())) + "[[roster_moves]]\ndate = YYYY-MM-DD\n", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = editorial.check([directory])
        self.assertEqual(status, 1)
        self.assertIn("::error file=", output.getvalue())
        self.assertIn("not valid TOML", output.getvalue())


if __name__ == "__main__":
    unittest.main()
