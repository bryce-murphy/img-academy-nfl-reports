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
        self.assertTrue(markup.startswith('<svg class="field field-medium" viewBox="0 0 480 120"'))
        self.assertIn('role="img"', markup)
        self.assertIn('aria-label="1st &amp; 10 at the CLE 35. Run for 4 yards"', markup)
        self.assertEqual(markup.count("<svg"), 1)

    def test_svg_draws_both_end_zones_near_a_goal_line(self):
        markup = field.svg(base(down=1, ydstogo=3, goal_to_go=1, yardline_100=3, yards_gained=3, offense="CLE", defense="TB"), "large")
        self.assertIn('class="endzone"', markup)
        self.assertIn(">TB<", markup)

    def test_text_is_escaped(self):
        markup = field.svg(base(down=1, offense='<b>', defense="TB"), "card")
        self.assertNotIn("<b>", markup)

    def test_no_svg_for_text_only_plays(self):
        self.assertIsNone(field.svg(base(penalty=1), "card"))

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


ARROW = re.compile(r'<polygon class="arrow" points="([\d.]+),[\d.]+ ([\d.]+),')


def pass_play(**overrides):
    return base(play_type="pass", rush_attempt=0, pass_attempt=1, **overrides)


class FaceliftTests(unittest.TestCase):
    def test_sizes(self):
        self.assertIn('viewBox="0 0 720 300"', field.svg(base(), "large"))
        self.assertIn('viewBox="0 0 480 120"', field.svg(base(), "medium"))
        self.assertIn('viewBox="0 0 240 90"', field.svg(base(), "card"))

    def test_gain_points_right_with_a_plus_label(self):
        markup = field.svg(base(yards_gained=4), "medium")
        tip, back = map(float, ARROW.search(markup).groups())
        self.assertGreater(tip, back)
        self.assertIn(">+4</text>", markup)

    def test_loss_points_left_with_a_minus_label(self):
        markup = field.svg(pass_play(sack=1, yards_gained=-10), "medium")
        tip, back = map(float, ARROW.search(markup).groups())
        self.assertLess(tip, back)
        self.assertIn(">−10</text>", markup)

    def test_no_gain_has_a_ball_and_a_zero_label(self):
        markup = field.svg(base(yards_gained=0), "medium")
        self.assertNotIn('class="arrow"', markup)
        self.assertIn('class="ball"', markup)
        self.assertIn(">0</text>", markup)

    def test_incomplete_has_a_target_and_label(self):
        markup = field.svg(pass_play(air_yards=12, yards_gained=0, complete_pass=0), "medium")
        self.assertNotIn('class="arrow"', markup)
        self.assertIn('class="target"', markup)
        self.assertIn(">Incomplete</text>", markup)

    def test_path_color_follows_the_outcome(self):
        self.assertIn('<g class="path path-helped" style="color:#0B2265">', field.svg(base(), "medium", helped=True, path_color="#0B2265"))
        self.assertIn('<g class="path path-hurt">', field.svg(base(), "medium", helped=False, path_color="#0B2265"))
        self.assertIn('<g class="path path-neutral">', field.svg(base(), "medium"))

    def test_numbers_and_hashes_inside_the_window(self):
        markup = field.svg(base(), "large")
        g = field.geometry(base())
        numbers = re.findall(r'class="yard-number" x="([\d.]+)" y="[\d.]+" text-anchor="middle">(\d+)<', markup)
        for x, yard in numbers:
            self.assertTrue(int(yard) % 10 == 0)
            self.assertTrue(0 < float(x) < 720)
        self.assertIn('class="hash"', markup)
        self.assertGreaterEqual(markup.count('class="yard-number"'), 2)
        card = field.svg(base(), "card")
        self.assertIn('class="yard-number"', card)
        self.assertIn('class="hash"', card)
        self.assertLess(g["lo"], g["hi"])

    def test_end_zones_use_the_given_team_colors(self):
        goal_line = base(yardline_100=4, ydstogo=4, goal_to_go=1, yards_gained=4)
        markup = field.svg(goal_line, "medium", zones={"offense": ("#0B2265", "#ffffff"), "defense": ("#191711", "#D3BC8D")})
        self.assertIn('class="endzone" x=', markup)
        self.assertIn("fill:#191711", markup)
        self.assertIn("fill:#D3BC8D", markup)

    def test_yardage_label_stays_inside(self):
        long_gain = base(yardline_100=40, ydstogo=10, yards_gained=38)
        markup = field.svg(long_gain, "medium")
        x = float(re.search(r'<text class="yardage" x="([\d.]+)"', markup).group(1))
        self.assertTrue(24 <= x <= 480 - 24)

    def test_touchdown_label_sits_on_the_field_not_the_end_zone(self):
        markup = field.svg(base(yardline_100=12, ydstogo=10, goal_to_go=0, yards_gained=12), "medium")
        label = re.search(r'<text class="yardage" x="([\d.]+)" y="[\d.]+" text-anchor="(\w+)"', markup)
        goal_x = float(re.findall(r'class="endzone" x="([\d.]+)"', markup)[0])
        self.assertEqual(label.group(2), "end")
        self.assertLess(float(label.group(1)), goal_x)

    def test_safety_depth_loss_label_sits_on_the_field(self):
        markup = field.svg(pass_play(sack=1, yardline_100=95, ydstogo=10, goal_to_go=0, yards_gained=-8), "medium")
        label = re.search(r'<text class="yardage" x="([\d.]+)" y="[\d.]+" text-anchor="(\w+)"', markup)
        zone = re.search(r'class="endzone" x="([\d.]+)" y="0" width="([\d.]+)"', markup)
        self.assertEqual(label.group(2), "start")
        self.assertGreater(float(label.group(1)), float(zone.group(1)) + float(zone.group(2)))

    def test_short_play_labels_clear_the_line_of_scrimmage(self):
        # Rendered label sizes from styles.css; a glyph is at most about 0.6 em wide.
        fonts = {"card": 16, "medium": 17, "large": 26}
        plays = {"loss of 2": pass_play(sack=1, yards_gained=-2), "gain of 1": base(yards_gained=1), "gain of 2": base(yards_gained=2),
                 "no gain": base(yards_gained=0), "short incompletion": pass_play(air_yards=2, yards_gained=0, complete_pass=0),
                 "incompletion behind the line": pass_play(air_yards=-2, yards_gained=0, complete_pass=0)}
        for size, font in fonts.items():
            for name, play in plays.items():
                with self.subTest(size=size, play=name):
                    markup = field.svg(play, size)
                    los = float(re.search(r'class="los" x1="([\d.]+)"', markup).group(1))
                    x, anchor, text = re.search(r'<text class="yardage" x="([\d.]+)" y="[\d.]+" text-anchor="(\w+)">([^<]+)<', markup).groups()
                    x, width = float(x), len(text) * font * 0.6
                    left = {"start": x, "middle": x - width / 2, "end": x - width}[anchor]
                    self.assertFalse(left <= los <= left + width, f"{text!r} spans {left:.0f}-{left + width:.0f}, LOS at {los}")

    def test_short_loss_label_sits_on_the_play_line_past_the_arrowhead(self):
        # Jihaad Campbell, 2026 Week 3: a 2-yard loss at the PHI 7 whose centered label sat on the 10-yard line.
        play = pass_play(sack=1, down=1, ydstogo=7, goal_to_go=1, yardline_100=7, yards_gained=-2)
        markup = field.svg(play, "card")
        tip, _ = map(float, ARROW.search(markup).groups())
        x, y, anchor = re.search(r'<text class="yardage" x="([\d.]+)" y="([\d.]+)" text-anchor="(\w+)"', markup).groups()
        self.assertEqual(anchor, "end")
        self.assertLess(float(x), tip)
        self.assertAlmostEqual(float(y), field.SIZES["card"][1] * 0.45 + field.LABEL_FONT["card"] * 0.35, delta=0.1)
        # The wider week-page fields leave room to keep it centered over the tip.
        self.assertIn('text-anchor="middle">−2<', field.svg(play, "medium"))

    def test_long_play_label_stays_centered_over_the_tip(self):
        markup = field.svg(base(yards_gained=9), "medium")
        self.assertIn('text-anchor="middle">+9<', markup)

    def test_aria_label_carries_the_tag(self):
        self.assertIn("Big play", field.svg(base(), "medium", outcome="Big play"))

    def test_text_only_plays_still_have_no_drawing(self):
        self.assertIsNone(field.svg(base(penalty=1), "medium"))
        self.assertIsNone(field.yardage_label(base(penalty=1)))

    def catch(self, air, gained):
        return pass_play(complete_pass=1, air_yards=air, yards_gained=gained)

    def test_completion_arrow_shows_the_net_result_not_the_catch_point(self):
        markup = field.svg(self.catch(12, 10), "medium")
        tip, back = map(float, ARROW.search(markup).groups())
        self.assertGreater(tip, back)
        self.assertIn(">+10</text>", markup)

    def test_completion_behind_the_line_for_a_loss_points_left(self):
        markup = field.svg(self.catch(-3, -2), "medium")
        tip, back = map(float, ARROW.search(markup).groups())
        self.assertLess(tip, back)
        self.assertIn(">−2</text>", markup)

    def test_completion_for_no_gain_has_a_ball_and_no_arrow(self):
        markup = field.svg(self.catch(5, 0), "medium")
        self.assertNotIn('class="arrow"', markup)
        self.assertIn('class="ball"', markup)
        self.assertIn(">0</text>", markup)

    def test_completion_label_sits_below_the_arc_and_catch_marker(self):
        markup = field.svg(self.catch(4, 15), "medium")
        y = float(re.search(r'<text class="yardage" x="[\d.]+" y="([\d.]+)"', markup).group(1))
        self.assertGreater(y, 54.0)

    def test_large_drawing_uses_a_bigger_arrowhead(self):
        def head(size):
            tip, back = map(float, ARROW.search(field.svg(base(yards_gained=10), size)).groups())
            return tip - back
        self.assertEqual(head("large"), 12)
        self.assertEqual(head("medium"), 9)

    def test_completion_marks_the_catch_point(self):
        markup = field.svg(self.catch(4, 15), "medium")
        self.assertIn('class="catch"', markup)
        tip, back = map(float, ARROW.search(markup).groups())
        self.assertGreater(tip, back)
