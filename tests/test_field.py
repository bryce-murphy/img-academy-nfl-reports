import csv
import re
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

    def test_pass_with_unknown_completion_is_text_only(self):
        self.assertIsNone(field.kind(base(play_type="pass", rush_attempt=0, pass_attempt=1, air_yards=8, complete_pass=None, yards_gained=8)))

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

    def test_touchdown_endpoint_does_not_pass_the_goal_line(self):
        g = field.geometry(base(yardline_100=5, yards_gained=8))
        self.assertEqual(g["end"], 100)


class TextLineTests(unittest.TestCase):
    def test_spot_line(self):
        self.assertEqual(field.spot_line(base(down=3, ydstogo=7, yardline_100=35, offense="CLE", defense="TB")), "3rd & 7 at the TB 35")
        self.assertEqual(field.spot_line(base(down=2, ydstogo=10, yardline_100=80, offense="CLE", defense="TB")), "2nd & 10 at the CLE 20")
        self.assertEqual(field.spot_line(base(down=1, ydstogo=4, goal_to_go=1, yardline_100=4, offense="CLE", defense="TB")), "1st & goal at the TB 4")
        self.assertEqual(field.spot_line(base(down=1, ydstogo=10, yardline_100=50, offense="CLE", defense="TB")), "1st & 10 at midfield")
        self.assertEqual(field.spot_line(base(down=None, offense="CLE", defense="TB")), "")

    def test_spot_line_missing_distance_is_blank(self):
        self.assertEqual(field.spot_line(base(down=1, ydstogo=None, goal_to_go=0, yardline_100=35, offense="CLE", defense="TB")), "")

    def test_result_line(self):
        sack = dict(play_type="pass", sack=1, rush_attempt=0, pass_attempt=1)
        self.assertEqual(field.result_line(base(**sack, yards_gained=-5)), "Sacked for a loss of 5")
        self.assertEqual(field.result_line(base(**sack, yards_gained=0)), "Sacked for no gain")
        self.assertEqual(field.result_line(base(yards_gained=1)), "Run for 1 yard")
        self.assertEqual(field.result_line(base(yards_gained=-2)), "Run for a loss of 2")
        self.assertEqual(field.result_line(base(yards_gained=0)), "Run for no gain")
        self.assertEqual(field.result_line(base(play_type="pass", rush_attempt=0, pass_attempt=1, complete_pass=1, air_yards=8, yards_gained=14)), "Complete for 14 yards")
        self.assertEqual(field.result_line(base(play_type="pass", rush_attempt=0, pass_attempt=1, air_yards=8, yards_gained=0)), "Incomplete")
        self.assertIsNone(field.result_line(base(penalty=1)))

    def test_result_line_sign_aware_wording(self):
        self.assertEqual(field.result_line(base(play_type="pass", rush_attempt=0, pass_attempt=1, complete_pass=1, air_yards=5, yards_gained=-3)), "Complete for a loss of 3")
        self.assertEqual(field.result_line(base(play_type="pass", rush_attempt=0, pass_attempt=1, complete_pass=1, air_yards=5, yards_gained=0)), "Complete for no gain")
        sack = dict(play_type="pass", sack=1, rush_attempt=0, pass_attempt=1)
        self.assertEqual(field.result_line(base(**sack, yards_gained=2)), "Sacked for no gain")


class SvgTests(unittest.TestCase):
    def test_svg_is_labeled_and_sized(self):
        markup = field.svg(base(down=1, offense="CLE", defense="TB"), "medium")
        self.assertTrue(markup.startswith('<svg class="field field-medium" viewBox="0 0 480 90"'))
        self.assertIn('role="img"', markup)
        self.assertIn('aria-label="1st &amp; 10 at the CLE 35. Run for 4 yards"', markup)
        self.assertEqual(markup.count("<svg"), 1)

    def test_svg_draws_both_end_zones_near_a_goal_line(self):
        markup = field.svg(base(down=1, ydstogo=3, goal_to_go=1, yardline_100=3, yards_gained=3, offense="CLE", defense="TB"), "large")
        self.assertIn('class="endzone"', markup)
        self.assertIn(">TB<", markup)

    def test_text_is_escaped(self):
        markup = field.svg(base(down=1, offense='<b>', defense="TB"), "strip")
        self.assertNotIn("<b>", markup)

    def test_no_svg_for_text_only_plays(self):
        self.assertIsNone(field.svg(base(penalty=1), "strip"))

    def test_coordinates_are_clamped_to_the_viewbox(self):
        play = base(play_type="pass", sack=1, rush_attempt=0, pass_attempt=1, yardline_100=98, yards_gained=-20)
        width, _ = field.SIZES["medium"]
        markup = field.svg(play, "medium")
        coords = [float(v) for v in re.findall(r'(?:x1|x2|cx)="(-?[\d.]+)"', markup)]
        self.assertTrue(coords, "expected at least one drawn coordinate")
        self.assertTrue(all(0 <= v <= width for v in coords))

    def test_svg_includes_outcome_in_label(self):
        markup = field.svg(base(down=1, offense="CLE", defense="TB"), "medium", outcome="4th down stop")
        self.assertIn('aria-label="1st &amp; 10 at the CLE 35. Run for 4 yards. 4th down stop"', markup)

    def test_team_color_marks_only_the_players_side_end_label(self):
        own_side = field.svg(base(yardline_100=95, ydstogo=10, yards_gained=-8, offense="CLE", defense="TB"), "large", team_color="#aa0000")
        self.assertRegex(own_side, r'<text class="endzone-label"[^>]*style="fill:#aa0000"[^>]*>CLE<')
        self.assertNotIn("stroke:#aa0000", own_side)
        opp_side = field.svg(base(down=1, ydstogo=3, goal_to_go=1, yardline_100=3, yards_gained=3, offense="CLE", defense="TB", side="defense"), "large", team_color="#aa0000")
        self.assertRegex(opp_side, r'<text class="endzone-label"[^>]*style="fill:#aa0000"[^>]*>TB<')
        self.assertNotIn("stroke:#aa0000", opp_side)
