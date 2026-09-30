"""Roster moves: detection against earlier editions, allowed sources and the sentences. Pure functions."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from . import evidence as ev
from .upnext import MONTHS

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


TEAM_SITES = {
    "azcardinals.com": "AZCardinals.com", "atlantafalcons.com": "AtlantaFalcons.com", "baltimoreravens.com": "BaltimoreRavens.com",
    "buffalobills.com": "BuffaloBills.com", "panthers.com": "Panthers.com", "chicagobears.com": "ChicagoBears.com",
    "bengals.com": "Bengals.com", "clevelandbrowns.com": "ClevelandBrowns.com", "dallascowboys.com": "DallasCowboys.com",
    "denverbroncos.com": "DenverBroncos.com", "detroitlions.com": "DetroitLions.com", "packers.com": "Packers.com",
    "houstontexans.com": "HoustonTexans.com", "colts.com": "Colts.com", "jaguars.com": "Jaguars.com",
    "chiefs.com": "Chiefs.com", "raiders.com": "Raiders.com", "chargers.com": "Chargers.com", "therams.com": "TheRams.com",
    "miamidolphins.com": "MiamiDolphins.com", "vikings.com": "Vikings.com", "patriots.com": "Patriots.com",
    "neworleanssaints.com": "NewOrleansSaints.com", "giants.com": "Giants.com", "newyorkjets.com": "NewYorkJets.com",
    "philadelphiaeagles.com": "PhiladelphiaEagles.com", "steelers.com": "Steelers.com", "49ers.com": "49ers.com",
    "seahawks.com": "Seahawks.com", "buccaneers.com": "Buccaneers.com", "tennesseetitans.com": "TennesseeTitans.com",
    "commanders.com": "Commanders.com",
}
ALLOWED_SOURCES = {"operations.nfl.com": "NFL Football Operations", "nfl.com": "NFL.com", "espn.com": "ESPN", "apnews.com": "AP", **TEAM_SITES}
ARRIVALS = ("trade", "waiver claim", "signing")
DEPARTURES = ("release", "waived")
VERBS = {"trade": "Traded to", "waiver claim": "Claimed off waivers by", "signing": "Signed by", "release": "Released by", "waived": "Waived by"}
KIND_TEXT = {"moved_after_game": "moved after the game", "first_week": "first week with the new team",
             "left_after_game": "left after the game", "left_before_week": "left before this week"}


def source_label(url):
    """The outlet label for an allowed https link, or None. Hosts match exactly or as a subdomain."""
    if not isinstance(url, str):
        return None
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or parts.username or parts.password or parts.port or not parts.hostname:
        return None
    host = parts.hostname.lower()
    for domain in sorted(ALLOWED_SOURCES, key=len, reverse=True):
        if host == domain or host.endswith("." + domain):
            return ALLOWED_SOURCES[domain]
    return None


def nickname(team_name):
    return team_name.split()[-1] if team_name else ""


def neutral(move):
    old, week = nickname(move["from_name"]), move["last_week_with_old_team"]
    if move["to"]:
        new = nickname(move["to_name"])
        if move["kind"] == "first_week":
            return f"First week with the {new} (was {old} in Week {week})."
        return f"Now on the {new}' roster (was {old} in Week {week})."
    if move["status"] == "CUT":
        return f"Released by the {old} (on their roster in Week {week})."
    if move["status"] == "RET":
        return f"Listed as retired (on the {old}' roster in Week {week})."
    return f"No longer on the {old}' roster (last listed in Week {week})."


def describe(move):
    if move["to"]:
        return f"{nickname(move['from_name'])} → {nickname(move['to_name'])} ({KIND_TEXT[move['kind']]})"
    return f"left the {nickname(move['from_name'])} ({KIND_TEXT[move['kind']]})"


def sourced(move, note):
    team = nickname(move["to_name"] if note["kind"] in ARRIVALS else move["from_name"])
    day = note["date"]
    details = (note.get("details") or "").strip().rstrip(".").strip()
    return f"{VERBS[note['kind']]} the {team} on {MONTHS[day.month - 1]} {day.day}{' ' + details if details else ''}."


def note_index(editions):
    """(player id, from, to) -> the earliest edition's note for that move. `editions` is oldest first."""
    index = {}
    for data, copy in editions:
        players = {p["id"]: p for p in data.get("players", [])}
        for note in (copy or {}).get("roster_moves", []) or []:
            move = (players.get(note.get("player_id")) or {}).get("move")
            if move:
                index.setdefault((note["player_id"], move["from"], move["to"]), note)
    return index


def view(player, index):
    move = player.get("move")
    if not move:
        return None
    note = index.get((player["id"], move["from"], move["to"]))
    color = move.get("to_color") or move.get("from_color")
    if note:
        return {"text": sourced(move, note), "source_url": note["source"], "source_label": source_label(note["source"]), "color": color}
    return {"text": neutral(move), "source_url": None, "source_label": None, "color": color}
