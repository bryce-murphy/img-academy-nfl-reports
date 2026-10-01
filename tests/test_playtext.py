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
