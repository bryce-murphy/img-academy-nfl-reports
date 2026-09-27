import unittest

from src.upnext import kickoff_label, matchup_label, next_game


def game(week, away, home, day, time="13:00", stadium="Field", location="Home", game_type="REG", away_score="", home_score=""):
    return {
        "season": "2026", "game_type": game_type, "week": str(week), "away_team": away, "home_team": home,
        "gameday": day, "gametime": time, "stadium": stadium, "location": location,
        "away_score": away_score, "home_score": home_score,
    }


SCHEDULE = [
    game(3, "PHI", "CHI", "2026-09-28", "20:15", "Soldier Field"),
    game(3, "ATL", "GB", "2026-09-24", "20:15", "Lambeau Field"),
    game(5, "GB", "DAL", "2026-10-11", "", ""),
    game(4, "BAL", "DAL", "2026-10-04", "09:30", "Maracana Stadium", "Neutral"),
]


class NextGameTests(unittest.TestCase):
    def test_away_game(self):
        info = next_game(SCHEDULE, 2026, 2, "PHI")
        self.assertEqual((info["kind"], info["week"], info["opponent"], info["home_away"]), ("game", 3, "CHI", "away"))
        self.assertEqual((info["kickoff_et"], info["venue"], info["date"]), ("20:15", "Soldier Field", "2026-09-28"))

    def test_home_game(self):
        info = next_game(SCHEDULE, 2026, 2, "GB")
        self.assertEqual((info["opponent"], info["home_away"]), ("ATL", "home"))

    def test_bye_week_is_explicit(self):
        info = next_game(SCHEDULE, 2026, 3, "GB")
        self.assertEqual((info["kind"], info["bye_week"], info["week"], info["opponent"]), ("bye", 4, 5, "DAL"))

    def test_missing_time_and_venue_stay_unknown(self):
        info = next_game(SCHEDULE, 2026, 3, "GB")
        self.assertIsNone(info["kickoff_et"])
        self.assertIsNone(info["venue"])

    def test_neutral_site(self):
        self.assertEqual(next_game(SCHEDULE, 2026, 3, "DAL")["home_away"], "neutral")

    def test_no_team_is_unconfirmed(self):
        self.assertEqual(next_game(SCHEDULE, 2026, 2, ""), {"kind": "unconfirmed"})

    def test_no_future_game(self):
        # No future game after week 5: since no postseason games exist for PHI, unconfirmed
        self.assertEqual(next_game(SCHEDULE, 2026, 5, "PHI"), {"kind": "unconfirmed"})
        # Week 18 regular season with no bracket game: still unconfirmed (not yet known who advances)
        reg_only = [game(18, "PHI", "CHI", "2026-12-27", "13:00", home_score="28", away_score="24")]
        self.assertEqual(next_game(reg_only, 2026, 18, "PHI"), {"kind": "unconfirmed"})
        # After week 19 (one playoff week), team with no game: season_complete
        self.assertEqual(next_game(reg_only, 2026, 19, "PHI"), {"kind": "season_complete"})

    def test_postseason_games_are_found(self):
        schedule = [game(19, "PHI", "CHI", "2027-01-16", game_type="WC")]
        info = next_game(schedule, 2026, 18, "PHI")
        self.assertEqual((info["kind"], info["week"]), ("game", 19))

    def test_wildcard_loss_is_season_complete(self):
        schedule = [game(19, "PHI", "CHI", "2027-01-16", game_type="WC", away_score="17", home_score="21")]
        self.assertEqual(next_game(schedule, 2026, 19, "PHI"), {"kind": "season_complete"})

    def test_wildcard_win_with_no_later_game_is_unconfirmed(self):
        schedule = [game(19, "PHI", "CHI", "2027-01-16", game_type="WC", away_score="28", home_score="24")]
        self.assertEqual(next_game(schedule, 2026, 19, "PHI"), {"kind": "unconfirmed"})

    def test_superbowl_is_always_season_complete(self):
        schedule = [game(22, "PHI", "KC", "2027-02-07", game_type="SB", away_score="31", home_score="34")]
        self.assertEqual(next_game(schedule, 2026, 22, "PHI"), {"kind": "season_complete"})

    def test_na_values_become_none(self):
        na_schedule = [game(3, "PHI", "CHI", "2026-09-28", time="NA", stadium="NA")]
        info = next_game(na_schedule, 2026, 2, "PHI")
        self.assertIsNone(info["kickoff_et"])
        self.assertIsNone(info["venue"])

    def test_midnight_kickoff_label(self):
        self.assertEqual(kickoff_label({"date": "2026-10-11", "kickoff_et": "00:05"}), "Sun, Oct 11 · 12:05 a.m. ET")


class LabelTests(unittest.TestCase):
    def test_kickoff_labels(self):
        self.assertEqual(kickoff_label({"date": "2026-09-28", "kickoff_et": "20:15"}), "Mon, Sep 28 · 8:15 p.m. ET")
        self.assertEqual(kickoff_label({"date": "2026-10-04", "kickoff_et": "09:30"}), "Sun, Oct 4 · 9:30 a.m. ET")
        self.assertEqual(kickoff_label({"date": "2026-09-27", "kickoff_et": "12:00"}), "Sun, Sep 27 · 12:00 p.m. ET")
        self.assertEqual(kickoff_label({"date": "2026-10-11", "kickoff_et": None}), "Sun, Oct 11 · Kickoff TBD")

    def test_matchup_labels(self):
        self.assertEqual(matchup_label({"home_away": "away", "opponent": "CHI"}, "PHI"), "PHI at CHI")
        self.assertEqual(matchup_label({"home_away": "home", "opponent": "ATL"}, "GB"), "ATL at GB")
        self.assertEqual(matchup_label({"home_away": "neutral", "opponent": "BAL"}, "DAL"), "DAL vs. BAL")


if __name__ == "__main__":
    unittest.main()
