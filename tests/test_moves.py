import unittest
from datetime import date

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

    def test_release_by_another_team_is_not_a_release_by_the_old_team(self):
        self.assertEqual(detect(player(now="NYG", status="CUT"))["status"], "none")
        before = edition(3, player())
        other = player(team="NYG", label="Released", now="NYG", status="CUT")
        self.assertEqual(detect(other, week=4, history=[before])["status"], "none")

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

    def test_first_week_after_a_bye_names_the_last_week_with_the_old_team(self):
        bye = player(label="Bye week", game_id=None)
        history = [edition(3, player(), gameday="2026-09-27"), edition(4, bye)]
        move = detect(player(team="NYG", now="NYG"), week=5, history=history)
        self.assertEqual((move["kind"], move["from"], move["last_week_with_old_team"], move["last_game_date"]),
                         ("first_week", "MIN", 3, "2026-09-27"))

    def test_moved_after_game_during_a_bye_names_the_last_week_with_the_old_team(self):
        bye = player(label="Bye week", game_id=None, now="NYG")
        move = detect(bye, week=4, history=[edition(3, player(), gameday="2026-09-27")])
        self.assertEqual((move["kind"], move["from"], move["to"], move["last_week_with_old_team"], move["last_game_date"]),
                         ("moved_after_game", "MIN", "NYG", 3, "2026-09-27"))

    def test_left_before_week_after_a_bye_names_the_last_week_with_the_old_team(self):
        gone = player(team="", label="Not on an NFL roster", now="", status="", game_id=None)
        history = [edition(3, player(), gameday="2026-09-27"), edition(4, player(label="Bye week", game_id=None))]
        move = detect(gone, week=5, history=history)
        self.assertEqual((move["kind"], move["from"], move["last_week_with_old_team"], move["last_game_date"]),
                         ("left_before_week", "MIN", 3, "2026-09-27"))

    def test_only_a_bye_with_the_old_team_keeps_the_candidate_week(self):
        history = [edition(4, player(label="Bye week", game_id=None))]
        move = detect(player(team="NYG", now="NYG"), week=5, history=history)
        self.assertEqual((move["kind"], move["from"], move["last_week_with_old_team"], move["last_game_date"]), ("first_week", "MIN", 4, None))
        bye = player(label="Bye week", game_id=None, now="NYG")
        move = detect(bye, week=4)
        self.assertEqual((move["kind"], move["last_week_with_old_team"], move["last_game_date"]), ("moved_after_game", 4, None))

    def test_bye_walk_back_stops_at_an_older_stint(self):
        history = [edition(1, player(), gameday="2026-09-13"), edition(2, player(team="NYG", now="NYG")),
                   edition(3, player(label="Bye week", game_id=None))]
        move = detect(player(team="NYG", now="NYG"), week=4, history=history)
        self.assertEqual((move["kind"], move["from"], move["last_week_with_old_team"], move["last_game_date"]), ("first_week", "MIN", 3, None))

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


class RealDataTests(unittest.TestCase):
    def test_mccarthy_week_3_is_a_move_after_the_game(self):
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "editions"
        week3 = json.loads((root / "2026-week-03" / "edition.json").read_text(encoding="utf-8"))
        mccarthy = next(p for p in week3["players"] if p["name"] == "J.J. McCarthy")
        gameday = next(g["gameday"] for g in week3["games"] if g["game_id"] == mccarthy["game"]["game_id"])
        move = moves.detect(mccarthy, 3, week3["games"], moves.load_history(root, 2026, 3), NAMES.get, COLORS.get)
        self.assertEqual((move["kind"], move["from"], move["to"], move["last_week_with_old_team"], move["last_game_date"]),
                         ("moved_after_game", "MIN", "NYG", 3, gameday))


ARRIVAL = {"kind": "moved_after_game", "from": "MIN", "to": "NYG", "from_name": "Minnesota Vikings", "to_name": "New York Giants",
           "from_color": "#4F2683", "to_color": "#0B2265", "status": None, "last_week_with_old_team": 3, "last_game_date": "2026-09-27"}
DEPARTURE = dict(ARRIVAL, kind="left_after_game", to=None, to_name=None, to_color=None, status="CUT")
NOTE = {"player_id": "p1", "kind": "trade", "date": date(2026, 9, 28), "details": "for a 2027 fourth-round pick",
        "source": "https://www.giants.com/news/trade"}


class SourceTests(unittest.TestCase):
    def test_allowed_sites_and_labels(self):
        self.assertEqual(moves.source_label("https://www.giants.com/news/x"), "Giants.com")
        self.assertEqual(moves.source_label("https://operations.nfl.com/updates/x"), "NFL Football Operations")
        self.assertEqual(moves.source_label("https://www.nfl.com/news/x"), "NFL.com")
        self.assertEqual(moves.source_label("https://apnews.com/article/x"), "AP")
        self.assertEqual(moves.source_label("https://www.espn.com/nfl/story/x"), "ESPN")
        self.assertEqual(len([d for d in moves.ALLOWED_SOURCES if d not in {"nfl.com", "operations.nfl.com", "espn.com", "apnews.com"}]), 32)

    def test_rejected_links(self):
        for url in ("http://www.giants.com/x", "https://theathletic.com/x", "https://example.com/x", "giants.com/x", "", "https://nfl.com.evil.test/x",
                    "https://giants.com:abc/x", "https://giants.com:99999/x", "https://[x/"):
            self.assertIsNone(moves.source_label(url), url)

    def test_look_alike_and_odd_hosts(self):
        self.assertIsNone(moves.source_label("https://giants.com.evil.test/x"))
        self.assertIsNone(moves.source_label("https://giants.com@evil.test/x"))
        self.assertIsNone(moves.source_label("https://www.giants.com:8443/x"))
        self.assertEqual(moves.source_label("https://GIANTS.com/x"), "Giants.com")


class SentenceTests(unittest.TestCase):
    def test_neutral_lines(self):
        self.assertEqual(moves.neutral(ARRIVAL), "Now on the Giants' roster (was Vikings in Week 3).")
        self.assertEqual(moves.neutral(dict(ARRIVAL, kind="first_week")), "First week with the Giants (was Vikings in Week 3).")
        self.assertEqual(moves.neutral(DEPARTURE), "Released by the Vikings (on their roster in Week 3).")
        self.assertEqual(moves.neutral(dict(DEPARTURE, status="RET")), "Listed as retired (on the Vikings' roster in Week 3).")
        self.assertEqual(moves.neutral(dict(DEPARTURE, status="none", kind="left_before_week")), "No longer on the Vikings' roster (last listed in Week 3).")

    def test_describe_for_the_pr(self):
        self.assertEqual(moves.describe(ARRIVAL), "Vikings → Giants (moved after the game)")
        self.assertEqual(moves.describe(dict(DEPARTURE, kind="left_before_week")), "left the Vikings (left before this week)")

    def test_sourced_sentences(self):
        self.assertEqual(moves.sourced(ARRIVAL, NOTE), "Traded to the Giants on Sep 28 for a 2027 fourth-round pick.")
        self.assertEqual(moves.sourced(ARRIVAL, dict(NOTE, details="")), "Traded to the Giants on Sep 28.")
        self.assertEqual(moves.sourced(ARRIVAL, dict(NOTE, kind="waiver claim")), "Claimed off waivers by the Giants on Sep 28 for a 2027 fourth-round pick.")
        self.assertEqual(moves.sourced(DEPARTURE, dict(NOTE, kind="waived", details="")), "Waived by the Vikings on Sep 28.")
        self.assertEqual(moves.sourced(DEPARTURE, dict(NOTE, kind="release", details="")), "Released by the Vikings on Sep 28.")

    def test_details_trailing_period_is_not_doubled(self):
        self.assertEqual(moves.sourced(ARRIVAL, dict(NOTE, details="for a 2027 fourth-round pick.")),
                         "Traded to the Giants on Sep 28 for a 2027 fourth-round pick.")

    def test_view_prefers_a_matching_note_from_any_edition(self):
        week3 = {"season": 2026, "week": 3, "players": [{"id": "p1", "move": ARRIVAL}]}
        week4_player = {"id": "p1", "move": dict(ARRIVAL, kind="first_week")}
        index = moves.note_index([(week3, {"roster_moves": [NOTE]}), ({"season": 2026, "week": 4, "players": [week4_player]}, {})])
        shown = moves.view(week4_player, index, 2026)
        self.assertEqual(shown, {"text": "Traded to the Giants on Sep 28 for a 2027 fourth-round pick.",
                                 "source_url": NOTE["source"], "source_label": "Giants.com", "color": "#0B2265"})

    def test_same_move_twice_keeps_each_note_to_its_own_occurrence(self):
        first = {"id": "p1", "move": dict(DEPARTURE, last_week_with_old_team=3)}
        second = {"id": "p1", "move": dict(DEPARTURE, last_week_with_old_team=9)}
        note3 = dict(NOTE, kind="release", date=date(2026, 9, 28), details="")
        note9 = dict(NOTE, kind="release", date=date(2026, 11, 20), details="")
        index = moves.note_index([({"season": 2026, "week": 4, "players": [first]}, {"roster_moves": [note3]}),
                                  ({"season": 2026, "week": 10, "players": [second]}, {"roster_moves": [note9]})])
        self.assertEqual(moves.view(first, index, 2026)["text"], "Released by the Vikings on Sep 28.")
        self.assertEqual(moves.view(second, index, 2026)["text"], "Released by the Vikings on Nov 20.")
        self.assertEqual(moves.view(second, index, 2025)["text"], moves.neutral(second["move"]))

    def test_earliest_note_wins_and_neutral_without_note(self):
        week3 = {"season": 2026, "week": 3, "players": [{"id": "p1", "move": ARRIVAL}]}
        week4 = {"season": 2026, "week": 4, "players": [{"id": "p1", "move": dict(ARRIVAL, kind="first_week")}]}
        later = dict(NOTE, details="later text")
        index = moves.note_index([(week3, {"roster_moves": [NOTE]}), (week4, {"roster_moves": [later]})])
        self.assertIn("fourth-round", moves.view(week4["players"][0], index, 2026)["text"])
        self.assertEqual(moves.view({"id": "p1", "move": DEPARTURE}, {}, 2026),
                         {"text": "Released by the Vikings (on their roster in Week 3).", "source_url": None, "source_label": None, "color": "#4F2683"})
        self.assertIsNone(moves.view({"id": "p1", "move": None}, index, 2026))
        self.assertIsNone(moves.view({"id": "p1"}, index, 2026))

    def test_view_fallback_to_neutral_for_disallowed_source(self):
        week3 = {"season": 2026, "week": 3, "players": [{"id": "p1", "move": ARRIVAL}]}
        bad_source = dict(NOTE, source="https://theathletic.com/x")
        index = moves.note_index([(week3, {"roster_moves": [bad_source]})])
        result = moves.view(week3["players"][0], index, 2026)
        self.assertEqual(result["text"], moves.neutral(ARRIVAL))
        self.assertIsNone(result["source_url"])
        self.assertIsNone(result["source_label"])

    def test_view_fallback_for_invalid_kind(self):
        week3 = {"season": 2026, "week": 3, "players": [{"id": "p1", "move": ARRIVAL}]}
        bad_kind = dict(NOTE, kind="javascript:alert(1)")
        index = moves.note_index([(week3, {"roster_moves": [bad_kind]})])
        result = moves.view(week3["players"][0], index, 2026)
        self.assertEqual(result["text"], moves.neutral(ARRIVAL))
        self.assertIsNone(result["source_url"])

    def test_view_fallback_for_wrong_direction_arrival_kind_on_departure(self):
        week3 = {"season": 2026, "week": 3, "players": [{"id": "p1", "move": DEPARTURE}]}
        wrong_kind = dict(NOTE, kind="trade")
        index = moves.note_index([(week3, {"roster_moves": [wrong_kind]})])
        result = moves.view(week3["players"][0], index, 2026)
        self.assertEqual(result["text"], moves.neutral(DEPARTURE))
        self.assertIsNone(result["source_url"])

    def test_view_fallback_for_wrong_direction_departure_kind_on_arrival(self):
        week3 = {"season": 2026, "week": 3, "players": [{"id": "p1", "move": ARRIVAL}]}
        wrong_kind = dict(NOTE, kind="release")
        index = moves.note_index([(week3, {"roster_moves": [wrong_kind]})])
        result = moves.view(week3["players"][0], index, 2026)
        self.assertEqual(result["text"], moves.neutral(ARRIVAL))
        self.assertIsNone(result["source_url"])

    def test_view_fallback_for_invalid_date(self):
        week3 = {"season": 2026, "week": 3, "players": [{"id": "p1", "move": ARRIVAL}]}
        bad_date = dict(NOTE, date="2026-09-28")
        index = moves.note_index([(week3, {"roster_moves": [bad_date]})])
        result = moves.view(week3["players"][0], index, 2026)
        self.assertEqual(result["text"], moves.neutral(ARRIVAL))
        self.assertIsNone(result["source_url"])
