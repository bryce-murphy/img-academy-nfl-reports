import csv
import unittest
from pathlib import Path

from src import field
from src.edition import play_record

EDGE = Path(__file__).parent / "fixtures" / "pbp_edge_cases.csv"


def base(**overrides):
    play = {"play_type": "run", "down": 1, "ydstogo": 10, "goal_to_go": 0, "yardline_100": 65, "yards_gained": 4,
            "air_yards": None, "yards_after_catch": None, "pass_attempt": 0, "rush_attempt": 1, "complete_pass": 0,
            "sack": 0, "interception": 0, "fumble": 0, "lateral": 0, "penalty": 0, "qb_kneel": 0, "qb_spike": 0,
            "two_point_attempt": 0}
    play.update(overrides)
    return play


def edge_cases():
    with EDGE.open(encoding="utf-8") as handle:
        # A dummy id that matches no cell: these rows only exercise the diagram rules.
        return {r["case"]: play_record(r, "00-0000000", r["defteam"], lambda t: t) for r in csv.DictReader(handle)}


class KindTests(unittest.TestCase):
    def test_text_only_reasons(self):
        for overrides in ({"play_type": "no_play"}, {"play_type": "punt"}, {"play_type": "kickoff"}, {"play_type": "field_goal"},
                          {"play_type": "extra_point"}, {"penalty": 1}, {"fumble": 1}, {"interception": 1}, {"lateral": 1},
                          {"qb_kneel": 1}, {"qb_spike": 1}, {"two_point_attempt": 1}, {"yardline_100": 0}, {"yardline_100": 100},
                          {"yardline_100": None}, {"yards_gained": None}, {"ydstogo": None}, {"ydstogo": 0}):
            with self.subTest(overrides=overrides):
                self.assertIsNone(field.kind(base(**overrides)))

    def test_precedence_sack_run_complete_incomplete(self):
        self.assertEqual(field.kind(base(play_type="pass", sack=1, rush_attempt=0, pass_attempt=1, yards_gained=-5)), "sack")
        self.assertEqual(field.kind(base()), "run")
        self.assertEqual(field.kind(base(play_type="pass", rush_attempt=0, pass_attempt=1, complete_pass=1, air_yards=8, yards_after_catch=6, yards_gained=14)), "complete")
        self.assertEqual(field.kind(base(play_type="pass", rush_attempt=0, pass_attempt=1, air_yards=12, yards_gained=0)), "incomplete")
        self.assertIsNone(field.kind(base(play_type="pass", rush_attempt=0, pass_attempt=1, air_yards=None, yards_gained=0)))

    def test_real_edge_cases(self):
        cases = edge_cases()
        for text_only in ("interception", "lost_fumble", "lateral", "penalty", "kneel", "two_point", "punt"):
            with self.subTest(case=text_only):
                self.assertIsNone(field.kind(cases[text_only]))
        self.assertEqual(field.kind(cases["sack"]), "sack")
        self.assertEqual(field.kind(cases["completion"]), "complete")
        self.assertEqual(field.kind(cases["incompletion"]), "incomplete")
        self.assertEqual(field.kind(cases["run_loss"]), "run")
        self.assertEqual(field.kind(cases["goal_line_td"]), "run")


class GeometryTests(unittest.TestCase):
    def test_run(self):
        g = field.geometry(base(yardline_100=65, ydstogo=10, yards_gained=4))
        self.assertEqual((g["x0"], g["marker"], g["end"], g["air_end"]), (35, 45, 39, None))

    def test_loss_and_sack_go_backward(self):
        self.assertEqual(field.geometry(base(yards_gained=-3))["end"], 32)
        self.assertEqual(field.geometry(base(play_type="pass", sack=1, rush_attempt=0, pass_attempt=1, yards_gained=-7))["end"], 28)

    def test_completion_has_air_and_after_catch(self):
        g = field.geometry(base(play_type="pass", rush_attempt=0, pass_attempt=1, complete_pass=1, yardline_100=50, air_yards=8, yards_after_catch=6, yards_gained=14))
        self.assertEqual((g["x0"], g["air_end"], g["end"]), (50, 58, 64))

    def test_incompletion_ends_at_the_target(self):
        g = field.geometry(base(play_type="pass", rush_attempt=0, pass_attempt=1, yardline_100=40, air_yards=15, yards_gained=0))
        self.assertEqual((g["air_end"], g["end"]), (75, 60))

    def test_goal_to_go_marker_is_the_goal_line_and_touchdown_ends_on_it(self):
        g = field.geometry(base(yardline_100=3, ydstogo=3, goal_to_go=1, yards_gained=3))
        self.assertEqual((g["marker"], g["end"]), (100, 100))

    def test_loss_into_own_end_zone(self):
        self.assertEqual(field.geometry(base(yardline_100=98, yards_gained=-4))["end"], -2)

    def test_window_is_at_least_thirty_yards_and_inside_the_domain(self):
        g = field.geometry(base(yardline_100=98, ydstogo=10, yards_gained=-4))
        self.assertGreaterEqual(g["hi"] - g["lo"], 30)
        self.assertGreaterEqual(g["lo"], -10)
        self.assertLessEqual(g["hi"], 110)

    def test_text_only_plays_have_no_geometry(self):
        self.assertIsNone(field.geometry(base(penalty=1)))
