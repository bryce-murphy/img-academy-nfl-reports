import unittest

from src.upnext import kickoff_label, matchup_label, next_game


def game(week, away, home, day, time="13:00", stadium="Field", location="Home", game_type="REG"):
    return {
        "season": "2026", "game_type": game_type, "week": str(week), "away_team": away, "home_team": home,
        "gameday": day, "gametime": time, "stadium": stadium, "location": location,
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
        self.assertEqual(next_game(SCHEDULE, 2026, 18, "PHI"), {"kind": "season_complete"})
        self.assertEqual(next_game(SCHEDULE, 2026, 5, "PHI"), {"kind": "unconfirmed"})

    def test_postseason_games_are_found(self):
        schedule = [game(19, "PHI", "CHI", "2027-01-16", game_type="POST")]
        self.assertEqual(next_game(schedule, 2026, 18, "PHI")["week"], 19)


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
