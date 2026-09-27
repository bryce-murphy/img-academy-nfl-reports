"""Resolve each team's next scheduled game from the nflverse schedule. Pure functions."""
from __future__ import annotations

from datetime import date

REGULAR_SEASON_WEEKS = 18
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def next_game(schedule, season, after_week, team, allowed=("REG", "POST")):
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
        # Postseason pairings appear in the schedule once set; with none left, the season is over.
        return {"kind": "season_complete" if after_week >= REGULAR_SEASON_WEEKS else "unconfirmed"}
    game = future[0]
    home = game["home_team"] == team
    info = {
        "kind": "game",
        "week": int(game["week"]),
        "opponent": game["away_team"] if home else game["home_team"],
        "home_away": "neutral" if game.get("location") == "Neutral" else ("home" if home else "away"),
        "date": game["gameday"],
        "kickoff_et": game.get("gametime") or None,
        "venue": game.get("stadium") or None,
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
