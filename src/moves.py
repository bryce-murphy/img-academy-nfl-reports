"""Roster moves: detection against earlier editions, allowed sources and the sentences. Pure functions."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import evidence as ev

OFF_STATUSES = {"CUT", "RET"}
OFF_LABELS = {ev.NOT_ON_ROSTER, "Released"}
EDITION_DIR = re.compile(r"(\d{4})-week-(\d{2})")


def week_team(player):
    if player["availability"]["label"] in OFF_LABELS:
        return None
    return player.get("team") or None


def now_team(player):
    current = player.get("current") or {}
    if current.get("roster_status") in OFF_STATUSES:
        return None
    return current.get("team") or None


def departure_status(player):
    status = (player.get("current") or {}).get("roster_status")
    if status == "RET":
        return "RET"
    if status == "CUT" or player["availability"]["label"] == "Released":
        return "CUT"
    return "none"


def _game_date(games, player):
    game_id = (player.get("game") or {}).get("game_id")
    return next((g["gameday"] for g in games if g["game_id"] == game_id), None) if game_id else None


def detect(player, week, games, history, team_name, team_color):
    """Return the player's roster move for this edition, or None. See the spec's §1 tables."""
    def move(kind, old, new, last_week, last_date):
        return {
            "kind": kind, "from": old, "to": new,
            "from_name": team_name(old), "to_name": team_name(new) if new else None,
            "from_color": team_color(old), "to_color": team_color(new) if new else None,
            "status": None if new else departure_status(player),
            "last_week_with_old_team": last_week, "last_game_date": last_date,
        }

    this, now = week_team(player), now_team(player)
    if this and now != this:
        return move("moved_after_game" if now else "left_after_game", this, now, week, _game_date(games, player))
    earlier = [(e, q) for e in history for q in e["players"] if q["id"] == player["id"]]
    previous = history[-1] if history else None
    before_player = next((q for e, q in earlier if e is previous), None)
    before = week_team(before_player) if before_player else None
    if before and this != before:
        kind = "first_week" if this else "left_before_week"
        return move(kind, before, this, previous["week"], _game_date(previous["games"], before_player))
    if this and before is None:
        last = next(((e, q) for e, q in reversed(earlier) if week_team(q)), None)
        if last and week_team(last[1]) != this:
            return move("first_week", week_team(last[1]), this, last[0]["week"], _game_date(last[0]["games"], last[1]))
    return None


def load_history(root, season, week):
    """Earlier published editions of the same season, oldest first."""
    found = []
    root = Path(root)
    if not root.is_dir():
        return found
    for directory in root.iterdir():
        match = EDITION_DIR.fullmatch(directory.name)
        if match and int(match[1]) == season and int(match[2]) < week and (directory / "edition.json").is_file():
            found.append(json.loads((directory / "edition.json").read_text(encoding="utf-8")))
    return sorted(found, key=lambda e: e["week"])


def moved_players(edition):
    return [p for p in edition["players"] if p.get("move")]
