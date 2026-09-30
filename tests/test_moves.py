import unittest

from src import moves

NAMES = {"MIN": "Minnesota Vikings", "NYG": "New York Giants", "CLE": "Cleveland Browns"}
COLORS = {"MIN": "#4F2683", "NYG": "#0B2265", "CLE": "#311D00"}


def player(team="MIN", label="Played", now="MIN", status="ACT", game_id="g", pid="p1"):
    return {
        "id": pid, "name": "J.J. McCarthy", "team": team,
        "availability": {"label": label, "evidence": ""},
        "current": {"team": now, "roster_status": status, "roster_label": ""},
        "game": {"game_id": game_id} if game_id else None,
    }


def edition(week, *players, gameday="2026-09-20"):
    return {"season": 2026, "week": week, "games": [{"game_id": "g", "gameday": gameday}], "players": list(players)}


def detect(p, week=3, history=(), gameday="2026-09-27"):
    return moves.detect(p, week, [{"game_id": "g", "gameday": gameday}], list(history), NAMES.get, COLORS.get)


class DetectTests(unittest.TestCase):
    def test_no_move(self):
        self.assertIsNone(detect(player(), history=[edition(2, player())]))

    def test_moved_after_game(self):
        move = detect(player(now="NYG"))
        self.assertEqual(move, {
            "kind": "moved_after_game", "from": "MIN", "to": "NYG",
            "from_name": "Minnesota Vikings", "to_name": "New York Giants",
            "from_color": "#4F2683", "to_color": "#0B2265",
            "status": None, "last_week_with_old_team": 3, "last_game_date": "2026-09-27",
        })

    def test_first_week_with_new_team(self):
        before = edition(3, player(now="NYG"), gameday="2026-09-27")
        move = detect(player(team="NYG", now="NYG"), week=4, history=[before])
        self.assertEqual((move["kind"], move["from"], move["to"], move["last_week_with_old_team"], move["last_game_date"]),
                         ("first_week", "MIN", "NYG", 3, "2026-09-27"))

    def test_first_week_even_when_inactive_for_new_team(self):
        before = edition(3, player())
        move = detect(player(team="NYG", label="Inactive for the game", now="NYG"), week=4, history=[before])
        self.assertEqual(move["kind"], "first_week")

    def test_left_after_game_released(self):
        move = detect(player(now="MIN", status="CUT"))
        self.assertEqual((move["kind"], move["to"], move["to_name"], move["to_color"], move["status"]),
                         ("left_after_game", None, None, None, "CUT"))

    def test_left_after_game_retired_and_missing(self):
        self.assertEqual(detect(player(now="MIN", status="RET"))["status"], "RET")
        self.assertEqual(detect(player(now="", status=""))["status"], "none")

    def test_left_before_week(self):
        before = edition(3, player())
        gone = player(team="", label="Not on an NFL roster", now="", status="", game_id=None)
        move = detect(gone, week=4, history=[before])
        self.assertEqual((move["kind"], move["from"], move["status"], move["last_week_with_old_team"]),
                         ("left_before_week", "MIN", "none", 3))

    def test_released_label_this_week_is_off_the_team(self):
        before = edition(3, player())
        cut = player(team="MIN", label="Released", now="MIN", status="CUT", game_id="g")
        move = detect(cut, week=4, history=[before])
        self.assertEqual((move["kind"], move["status"]), ("left_before_week", "CUT"))

    def test_off_every_roster_for_a_second_week_is_not_a_move(self):
        gone = player(team="", label="Not on an NFL roster", now="", status="", game_id=None)
        history = [edition(3, player()), edition(4, gone)]
        self.assertIsNone(detect(gone, week=5, history=history))

    def test_re_signing_after_release_is_a_first_week_from_the_last_team(self):
        gone = player(team="", label="Not on an NFL roster", now="", status="", game_id=None)
        history = [edition(3, player(), gameday="2026-09-27"), edition(4, gone)]
        move = detect(player(team="CLE", now="CLE"), week=5, history=history)
        self.assertEqual((move["kind"], move["from"], move["to"], move["last_week_with_old_team"]), ("first_week", "MIN", "CLE", 3))

    def test_re_signing_with_the_same_team_is_not_a_move(self):
        gone = player(team="", label="Not on an NFL roster", now="", status="", game_id=None)
        history = [edition(3, player()), edition(4, gone)]
        self.assertIsNone(detect(player(), week=5, history=history))

    def test_later_change_wins_over_arrival(self):
        before = edition(3, player())
        move = detect(player(team="NYG", now="CLE"), week=4, history=[before])
        self.assertEqual((move["kind"], move["from"], move["to"], move["last_week_with_old_team"]), ("moved_after_game", "NYG", "CLE", 4))

    def test_no_previous_edition_means_no_arrival_or_departure(self):
        self.assertIsNone(detect(player(team="NYG", now="NYG"), week=1))
        gone = player(team="", label="Not on an NFL roster", now="", status="", game_id=None)
        self.assertIsNone(detect(gone, week=1))

    def test_new_registry_player_has_no_arrival(self):
        other = player(pid="someone-else")
        self.assertIsNone(detect(player(team="NYG", now="NYG"), week=4, history=[edition(3, other)]))

    def test_two_moves_in_one_week_show_the_net_change(self):
        before = edition(3, player())
        move = detect(player(team="CLE", now="CLE"), week=4, history=[before])
        self.assertEqual((move["from"], move["to"]), ("MIN", "CLE"))

    def test_no_game_date_when_old_team_had_no_game(self):
        self.assertIsNone(detect(player(now="NYG", game_id=None))["last_game_date"])


class HistoryTests(unittest.TestCase):
    def test_load_history_reads_earlier_weeks_of_the_season_in_order(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for eid, week in (("2026-week-02", 2), ("2026-week-01", 1), ("2026-week-03", 3), ("2025-week-17", 17)):
                (root / eid).mkdir()
                (root / eid / "edition.json").write_text(json.dumps({"season": int(eid[:4]), "week": week, "players": []}), encoding="utf-8")
            self.assertEqual([e["week"] for e in moves.load_history(root, 2026, 3)], [1, 2])
            self.assertEqual(moves.load_history(root / "missing", 2026, 3), [])

    def test_moved_players(self):
        e = {"players": [{"id": "a", "move": None}, {"id": "b", "move": {"kind": "first_week"}}, {"id": "c"}]}
        self.assertEqual([p["id"] for p in moves.moved_players(e)], ["b"])
