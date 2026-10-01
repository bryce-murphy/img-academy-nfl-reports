import re
import unittest

from src import editorial, playtext

CISCO = {"name": "Andre Cisco", "team_name": "New York Jets"}
NEWSOME = {"name": "Greg Newsome II", "team_name": "New York Giants"}
ALLEN = {"name": "Kaytron Allen", "team_name": "Washington Commanders"}
TATE = {"name": "Carnell Tate", "team_name": "Tennessee Titans"}
MCCARTHY = {"name": "J.J. McCarthy", "team_name": "Minnesota Vikings"}


def play(**overrides):
    p = {"play_id": "100", "offense_name": "Detroit Lions", "defense_name": "New York Jets", "roles": [], "impact": None,
         "play_type": "pass", "yards_gained": 0, "pass_attempt": 0, "rush_attempt": 0, "complete_pass": 0, "sack": 0,
         "interception": 0, "fumble": 0, "penalty": 0, "lateral": 0, "two_point_attempt": 0,
         "passer_name": "J.Goff", "rusher_name": None, "receiver_name": None, "description": "", "epa": None}
    p.update(overrides)
    return p


def run(**overrides):
    fields = dict(play_type="run", rush_attempt=1, passer_name=None, rusher_name="D.Montgomery")
    fields.update(overrides)
    return play(**fields)


def catch(**overrides):
    fields = dict(pass_attempt=1, complete_pass=1, receiver_name="J.Gibbs")
    fields.update(overrides)
    return play(**fields)


class NameTests(unittest.TestCase):
    def test_last_names(self):
        for given, expected in (("J.Goff", "Goff"), ("A.St. Brown", "St. Brown"), ("Ja.Chase", "Chase"),
                                ("J.Smith-Njigba", "Smith-Njigba"), ("Goff", "Goff"), (None, None), ("", None)):
            with self.subTest(given=given):
                self.assertEqual(playtext.last_name(given), expected)

    def test_alum_names_drop_suffixes(self):
        self.assertEqual(playtext.alum_name("Greg Newsome II"), "Newsome")
        self.assertEqual(playtext.alum_name("J.J. McCarthy"), "McCarthy")


class DefenseLineTests(unittest.TestCase):
    def test_sack(self):
        sack = dict(roles=["sack", "solo_tackle_1"], sack=1, pass_attempt=1)
        self.assertEqual(playtext.play_line(play(yards_gained=-10, **sack), CISCO), "Cisco sacked Goff for a 10-yard loss.")
        self.assertEqual(playtext.play_line(play(play_id="101", yards_gained=-10, **sack), CISCO), "Cisco brought down Goff for a 10-yard sack.")
        self.assertEqual(playtext.play_line(play(yards_gained=0, **sack), CISCO), "Cisco sacked Goff for no gain.")
        self.assertEqual(playtext.play_line(play(yards_gained=None, **sack), CISCO), "Cisco sacked Goff.")
        half = play(roles=["half_sack_1"], sack=1, pass_attempt=1, yards_gained=-6)
        self.assertEqual(playtext.play_line(half, CISCO), "Cisco shared a sack of Goff for a 6-yard loss.")

    def test_pass_breakup(self):
        breakup = dict(roles=["pass_defense_1"], pass_attempt=1, passer_name="C.Ward", receiver_name="W.Robinson", offense_name="Tennessee Titans")
        self.assertEqual(playtext.play_line(play(**breakup), NEWSOME), "Newsome broke up Ward's pass to Robinson.")
        self.assertEqual(playtext.play_line(play(play_id="101", **breakup), NEWSOME), "Newsome got a hand on Ward's pass to Robinson.")
        self.assertEqual(playtext.play_line(play(**dict(breakup, receiver_name=None)), NEWSOME), "Newsome broke up Ward's pass.")

    def test_tackle_after_a_catch(self):
        self.assertEqual(playtext.play_line(catch(roles=["solo_tackle_1"], yards_gained=13), CISCO), "Cisco brought down Gibbs after a 13-yard catch.")
        self.assertEqual(playtext.play_line(catch(play_id="101", roles=["solo_tackle_1"], yards_gained=13), CISCO), "Gibbs caught a 13-yard pass before Cisco made the tackle.")
        self.assertEqual(playtext.play_line(catch(roles=["assist_tackle_1"], yards_gained=13), CISCO), "Cisco helped bring down Gibbs after a 13-yard catch.")
        self.assertEqual(playtext.play_line(catch(roles=["solo_tackle_1"], yards_gained=None), CISCO), "Cisco brought down Gibbs.")

    def test_tackle_on_a_run(self):
        self.assertEqual(playtext.play_line(run(roles=["solo_tackle_1"], yards_gained=2), CISCO), "Cisco stopped Montgomery after a 2-yard run.")
        self.assertEqual(playtext.play_line(run(play_id="101", roles=["solo_tackle_1"], yards_gained=2), CISCO), "Montgomery ran for 2 yards before Cisco made the tackle.")
        self.assertEqual(playtext.play_line(run(roles=["tackle_for_loss_1", "solo_tackle_1"], yards_gained=-3), CISCO), "Cisco stopped Montgomery for a 3-yard loss.")
        self.assertEqual(playtext.play_line(run(roles=["solo_tackle_1"], yards_gained=0), CISCO), "Cisco stopped Montgomery for no gain.")
        self.assertEqual(playtext.play_line(run(roles=["assist_tackle_2"], yards_gained=0), CISCO), "Cisco helped stop Montgomery for no gain.")

    def test_takeaways(self):
        pick = dict(roles=["interception"], interception=1, pass_attempt=1)
        self.assertEqual(playtext.play_line(play(**pick), CISCO), "Cisco intercepted Goff.")
        self.assertEqual(playtext.play_line(play(play_id="101", **pick), CISCO), "Cisco picked off Goff.")
        forced = run(roles=["forced_fumble_player_1", "solo_tackle_1"], fumble=1, yards_gained=3)
        self.assertEqual(playtext.play_line(forced, CISCO), "Cisco forced a fumble.")
        self.assertEqual(playtext.play_line(dict(forced, play_id="101"), CISCO), "Cisco knocked the ball loose.")


class OffenseLineTests(unittest.TestCase):
    def test_rusher(self):
        carry = dict(roles=["rusher"], rusher_name="K.Allen")
        self.assertEqual(playtext.play_line(run(yards_gained=6, **carry), ALLEN), "Allen ran for 6 yards.")
        self.assertEqual(playtext.play_line(run(play_id="101", yards_gained=6, **carry), ALLEN), "Allen picked up 6 yards on the ground.")
        self.assertEqual(playtext.play_line(run(yards_gained=1, **carry), ALLEN), "Allen ran for 1 yard.")
        self.assertEqual(playtext.play_line(run(yards_gained=-2, **carry), ALLEN), "Allen lost 2 yards.")
        self.assertEqual(playtext.play_line(run(yards_gained=0, **carry), ALLEN), "Allen was stopped for no gain.")

    def test_receiver(self):
        target = dict(roles=["receiver"], pass_attempt=1, passer_name="C.Ward", receiver_name="C.Tate", offense_name="Tennessee Titans")
        self.assertEqual(playtext.play_line(play(complete_pass=1, yards_gained=12, **target), TATE), "Tate caught a 12-yard pass from Ward.")
        self.assertEqual(playtext.play_line(play(play_id="101", complete_pass=1, yards_gained=12, **target), TATE), "Ward hit Tate for 12 yards.")
        self.assertEqual(playtext.play_line(play(complete_pass=0, **target), TATE), "Ward's pass to Tate fell incomplete.")

    def test_passer(self):
        throw = dict(roles=["passer"], pass_attempt=1, passer_name="J.McCarthy", receiver_name="J.Jefferson", offense_name="Minnesota Vikings")
        self.assertEqual(playtext.play_line(play(complete_pass=1, yards_gained=15, **throw), MCCARTHY), "McCarthy completed a 15-yard pass to Jefferson.")
        self.assertEqual(playtext.play_line(play(play_id="101", complete_pass=1, yards_gained=15, **throw), MCCARTHY), "McCarthy found Jefferson for 15 yards.")
        self.assertEqual(playtext.play_line(play(complete_pass=0, **throw), MCCARTHY), "McCarthy's pass to Jefferson fell incomplete.")
        self.assertEqual(playtext.play_line(play(sack=1, yards_gained=-7, **throw), MCCARTHY), "McCarthy was sacked for a 7-yard loss.")


class AddOnAndFallbackTests(unittest.TestCase):
    def test_touchdown_and_down_stop_add_ons(self):
        score = play(roles=["receiver", "td"], pass_attempt=1, complete_pass=1, yards_gained=12, passer_name="C.Ward", receiver_name="C.Tate")
        self.assertEqual(playtext.play_line(score, TATE), "Tate caught a 12-yard pass from Ward for a touchdown.")
        stop = run(roles=["solo_tackle_1"], yards_gained=1, impact="3rd-down stop")
        self.assertEqual(playtext.play_line(stop, CISCO), "Cisco stopped Montgomery after a 1-yard run, stopping the Lions on 3rd down.")

    def test_precedence_picks_one_sentence(self):
        both = play(roles=["sack", "forced_fumble_player_1", "solo_tackle_1"], sack=1, fumble=1, pass_attempt=1, yards_gained=-8)
        self.assertEqual(playtext.play_line(both, CISCO), "Cisco sacked Goff for an 8-yard loss.")

    def test_fallback_is_the_cleaned_play_by_play(self):
        text = "(1:47) (No Huddle, Shotgun) 16-J.Goff pass short left to 18-I.TeSlaa to NYJ 4 for 5 yards (8-A.Cisco)."
        self.assertEqual(playtext.play_line(play(roles=["kicker"], description=text), CISCO),
                         "J.Goff pass short left to I.TeSlaa to NYJ 4 for 5 yards (A.Cisco).")
        self.assertEqual(playtext.clean_description("(8:54) (Shotgun) 16-J.Goff sacked at DET 48 for -10 yards (8-A.Cisco)."),
                         "J.Goff sacked at DET 48 for -10 yards (A.Cisco).")

    def test_missing_names_fall_back(self):
        self.assertEqual(playtext.play_line(catch(roles=["solo_tackle_1"], receiver_name=None, yards_gained=13, description="(2:00) X"), CISCO), "X")

    def test_flagged_plays_fall_back(self):
        picked = play(roles=["receiver"], pass_attempt=1, interception=1, passer_name="C.Ward", receiver_name="C.Tate", description="(3:00) INT")
        self.assertEqual(playtext.play_line(picked, TATE), "INT")
        flagged = run(roles=["solo_tackle_1"], penalty=1, yards_gained=4, description="(4:00) PEN")
        self.assertEqual(playtext.play_line(flagged, CISCO), "PEN")
        lateral = run(roles=["rusher"], lateral=1, rusher_name="K.Allen", yards_gained=4, description="(5:00) LAT")
        self.assertEqual(playtext.play_line(lateral, ALLEN), "LAT")

    def test_lines_never_use_blocked_terms_or_zero_yards(self):
        samples = [play(yards_gained=-10, roles=["sack"], sack=1, pass_attempt=1), catch(roles=["solo_tackle_1"], yards_gained=None),
                   run(roles=["solo_tackle_1"], yards_gained=None), run(roles=["rusher"], rusher_name="K.Allen", yards_gained=None)]
        for sample in samples:
            line = playtext.play_line(sample, CISCO).lower()
            with self.subTest(line=line):
                self.assertFalse(any(term in line for term in editorial.BLOCKED_TERMS))
                self.assertIsNone(re.search(r"(?<!\d)0-yard", line))
                self.assertNotIn(" 0 yard", line)


class FixRoundTests(unittest.TestCase):
    def test_deflected_but_caught_pass_is_not_a_breakup(self):
        only = catch(roles=["pass_defense_1"], yards_gained=9, description="(2:00) 16-J.Goff pass short to 18-J.Gibbs for 9 yards.")
        self.assertEqual(playtext.play_line(only, CISCO), "J.Goff pass short to J.Gibbs for 9 yards.")
        both = catch(roles=["pass_defense_1", "solo_tackle_1"], yards_gained=9)
        self.assertEqual(playtext.play_line(both, CISCO), "Cisco brought down Gibbs after a 9-yard catch.")

    def test_shared_tackle_for_loss_is_not_solo(self):
        shared = run(roles=["tackle_for_loss_1", "assist_tackle_1"], yards_gained=-2)
        self.assertEqual(playtext.play_line(shared, CISCO), "Cisco helped stop Montgomery for a 2-yard loss.")
        alone = run(roles=["tackle_for_loss_1"], yards_gained=-3)
        self.assertEqual(playtext.play_line(alone, CISCO), "Cisco stopped Montgomery for a 3-yard loss.")

    def test_fallback_drops_blocked_sentences(self):
        text = "(2:00) 16-J.Goff pass short left to 18-I.TeSlaa for 5 yards (8-A.Cisco). 18-I.TeSlaa was injured during the play."
        self.assertEqual(playtext.safe_description(text), "J.Goff pass short left to I.TeSlaa for 5 yards (A.Cisco).")
        self.assertEqual(playtext.play_line(play(roles=["kicker"], description=text), CISCO),
                         "J.Goff pass short left to I.TeSlaa for 5 yards (A.Cisco).")
        self.assertEqual(playtext.safe_description("(1:00) 18-I.TeSlaa was injured during the play."), "")

    def test_no_touchdown_add_on_for_a_flat_carry(self):
        line = playtext.play_line(run(roles=["rusher", "td"], rusher_name="K.Allen", yards_gained=0), ALLEN)
        self.assertEqual(line, "Allen was stopped for no gain.")


class TagTests(unittest.TestCase):
    def test_helped_follows_the_expected_points_rule(self):
        self.assertTrue(playtext.helped({"epa": 0.5}, "offense"))
        self.assertTrue(playtext.helped({"epa": -2.46}, "defense"))
        self.assertFalse(playtext.helped({"epa": 0.8}, "defense"))
        self.assertIsNone(playtext.helped({"epa": 0.04}, "defense"))
        self.assertIsNone(playtext.helped({"epa": None}, "offense"))

    def test_tags(self):
        self.assertEqual(playtext.tag({"epa": -2.46}, "defense", "Jets"), {"key": "big", "text": "Big play"})
        self.assertEqual(playtext.tag({"epa": -2.0}, "defense", "Jets"), {"key": "big", "text": "Big play"})
        self.assertEqual(playtext.tag({"epa": -1.94}, "defense", "Jets"), {"key": "helped", "text": "Helped the Jets"})
        self.assertEqual(playtext.tag({"epa": 0.8}, "defense", "Jets"), {"key": "hurt", "text": "Hurt the Jets"})
        self.assertEqual(playtext.tag({"epa": 2.0}, "offense", "Titans"), {"key": "big", "text": "Big play"})
        self.assertIsNone(playtext.tag({"epa": 0.03}, "offense", "Titans"))
        self.assertIsNone(playtext.tag({"epa": None}, "offense", "Titans"))


    def test_big_play_uses_the_rounded_value_the_sentence_shows(self):
        self.assertEqual(playtext.tag({"epa": -1.96}, "defense", "Jets"), {"key": "big", "text": "Big play"})
        self.assertEqual(playtext.tag({"epa": -1.94}, "defense", "Jets"), {"key": "helped", "text": "Helped the Jets"})


class ClockAndSummaryFixTests(unittest.TestCase):
    def test_last_minute_clock_is_stripped(self):
        self.assertEqual(playtext.clean_description("(:02) K.Johnson left guard to NYJ 2 for 3 yards."), "K.Johnson left guard to NYJ 2 for 3 yards.")

    def test_caught_deflection_is_not_a_pass_breakup(self):
        plays = [{"impact": "Pass defended", "roles": ["pass_defense_1", "solo_tackle_1"], "complete_pass": 1}]
        self.assertEqual(playtext.summary(plays), "One play with his name on it: a tackle.")


class DetailTests(unittest.TestCase):
    def test_expected_points_sentence(self):
        self.assertEqual(playtext.epa_sentence({"epa": -2.46, "offense_name": "Detroit Lions"}), "The Lions lost 2.5 expected points on the play.")
        self.assertEqual(playtext.epa_sentence({"epa": 1.0, "offense_name": "Detroit Lions"}), "The Lions gained 1 expected point on the play.")
        self.assertEqual(playtext.epa_sentence({"epa": 0.04, "offense_name": "Detroit Lions"}), "The Lions' expected points barely moved on the play.")
        self.assertEqual(playtext.epa_sentence({"epa": None, "offense_name": "Detroit Lions"}), "")

    def test_air_sentence(self):
        self.assertEqual(playtext.air_sentence({"pass_attempt": 1, "complete_pass": 1, "air_yards": 8, "yards_after_catch": 6}), "Thrown 8 yards past the line; 6 yards after the catch.")
        self.assertEqual(playtext.air_sentence({"pass_attempt": 1, "complete_pass": 1, "air_yards": -2, "yards_after_catch": 15}), "Thrown 2 yards behind the line; 15 yards after the catch.")
        self.assertEqual(playtext.air_sentence({"pass_attempt": 1, "complete_pass": 0, "air_yards": 12, "yards_after_catch": None}), "Thrown 12 yards past the line.")
        self.assertEqual(playtext.air_sentence({"pass_attempt": 0, "air_yards": None}), "")


class SummaryTests(unittest.TestCase):
    def test_counts_one_category_per_play(self):
        plays = [{"impact": "Sack", "roles": ["sack", "solo_tackle_1"]}] + [{"impact": None, "roles": ["solo_tackle_1"]}] * 4 + [{"impact": "3rd-down stop", "roles": ["solo_tackle_1"]}]
        self.assertEqual(playtext.summary(plays), "Six plays with his name on them: a sack, four tackles and a 3rd-down stop.")

    def test_one_play_and_none(self):
        self.assertEqual(playtext.summary([{"impact": "Pass defended", "roles": ["pass_defense_1"]}]), "One play with his name on it: a pass breakup.")
        self.assertEqual(playtext.summary([{"impact": "Interception", "roles": ["interception"]}]), "One play with his name on it: an interception.")
        self.assertEqual(playtext.summary([]), "")

    def test_offense_and_large_counts(self):
        plays = [{"impact": None, "roles": ["receiver"], "complete_pass": 1}] * 11
        self.assertEqual(playtext.summary(plays), "11 plays with his name on them: 11 catches.")
        mixed = [{"impact": None, "roles": ["rusher"]}, {"impact": None, "roles": ["receiver"], "complete_pass": 0}, {"impact": "Blocked kick", "roles": ["blocked"]}]
        self.assertEqual(playtext.summary(mixed), "Three plays with his name on them: a carry, a target and one other play.")
