"""Resolve each team's next scheduled game from the nflverse schedule. Pure functions."""
from __future__ import annotations

from datetime import date

REGULAR_SEASON_WEEKS = 18
POSTSEASON = ("WC", "DIV", "CON", "SB")
MISSING = (None, "", "NA", "NaN")
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _present(value):
    """Return None if value is in MISSING, otherwise the value."""
    return None if value in MISSING else value


def _won(game, team):
    """Determine if team won the game; treat unknown results as the team still alive."""
    home = game["home_team"] == team
    own, other = (game.get("home_score"), game.get("away_score")) if home else (game.get("away_score"), game.get("home_score"))
    if _present(own) is None or _present(other) is None:
        return True  # result unknown: treat the team as still alive, so the matchup stays unconfirmed
    return float(own) > float(other)


def _season_state(schedule, season, after_week, team, allowed):
    """No future game is scheduled for this team: decide between 'unconfirmed' and 'season_complete'."""
    if after_week < REGULAR_SEASON_WEEKS:
        return "unconfirmed"
    played = [
        g for g in schedule
        if int(g["season"]) == season and g["game_type"] in allowed
        and int(g["week"]) <= after_week and team in (g["home_team"], g["away_team"])
    ]
    if not played:
        return "unconfirmed"
    last = max(played, key=lambda g: int(g["week"]))
    if last["game_type"] == "SB":
        return "season_complete"
    if last["game_type"] in POSTSEASON:
        return "unconfirmed" if _won(last, team) else "season_complete"
    # Regular season over and no bracket game: after Wild Card weekend the team is out. The Wednesday
    # after Week 18 a top seed on a bye looks the same, so that edition stays unconfirmed.
    return "season_complete" if after_week > REGULAR_SEASON_WEEKS else "unconfirmed"


def next_game(schedule, season, after_week, team, allowed=("REG",) + POSTSEASON):
    if not team:
        return {"kind": "unconfirmed"}
    future = sorted(
        (
            g for g in schedule
            if int(g["season"]) == season and g["game_type"] in allowed
            and int(g["week"]) > after_week and team in (g["home_team"], g["away_team"])
        ),
        key=lambda g: (int(g["week"]), g["gameday"]),
    )
    if not future:
        return {"kind": _season_state(schedule, season, after_week, team, allowed)}
    game = future[0]
    home = game["home_team"] == team
    info = {
        "kind": "game",
        "week": int(game["week"]),
        "opponent": game["away_team"] if home else game["home_team"],
        "home_away": "neutral" if game.get("location") == "Neutral" else ("home" if home else "away"),
        "date": game["gameday"],
        "kickoff_et": _present(game.get("gametime")),
        "venue": _present(game.get("stadium")),
    }
    if info["week"] > after_week + 1:
        info["kind"] = "bye"
        info["bye_week"] = after_week + 1
    return info


def kickoff_label(info):
    day = date.fromisoformat(info["date"])
    text = f"{DAYS[day.weekday()]}, {MONTHS[day.month - 1]} {day.day}"
    if not info.get("kickoff_et"):
        return f"{text} · Kickoff TBD"
    hour, minute = (int(part) for part in info["kickoff_et"].split(":")[:2])
    suffix = "a.m." if hour < 12 else "p.m."
    return f"{text} · {hour % 12 or 12}:{minute:02d} {suffix} ET"


def matchup_label(info, team):
    if info["home_away"] == "neutral":
        return f"{team} vs. {info['opponent']}"
    if info["home_away"] == "home":
        return f"{info['opponent']} at {team}"
    return f"{team} at {info['opponent']}"
