"""Regenerate tests/fixtures/week02 from live nflverse releases (network required).

Keeps a small, representative slice of 2026 Week 2 so tests exercise every availability
rule without committing full datasets. Run: .venv/Scripts/python scripts/make_fixtures.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data import load_sources, specifications  # noqa: E402

SEASON, WEEK = 2026, 2
OUT = ROOT / "tests" / "fixtures" / "week02"
NAMES = [
    "Grant Delpit", "DeMonte Capehart", "Carnell Tate", "Nolan Smith", "Warren Brinson",
    "Andre Cisco", "J.J. McCarthy", "Evan Neal", "Xavier Thomas", "Cesar Ruiz",
    "Kaytron Allen", "Tyler Booker", "Daylen Everette",
]
SCHEDULE_COLUMNS = [
    "game_id", "season", "game_type", "week", "gameday", "weekday", "gametime", "away_team",
    "away_score", "home_team", "home_score", "location", "stadium",
]
PBP_BASE = [
    "game_id", "play_id", "week", "season_type", "desc", "epa", "wpa", "qtr", "time", "play_type",
    "total_home_score", "total_away_score", "passing_yards", "rushing_yards", "receiving_yards",
]
PLAYER_COLUMNS = ["gsis_id", "display_name", "pfr_id", "position", "college_name", "draft_year", "draft_round"]
TEAM_COLUMNS = ["team_abbr", "team_name", "team_color", "team_logo_espn"]


def write(name, rows, columns):
    with (OUT / f"{name}.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def columns_of(rows, name):
    return list(rows[0].keys()) if rows else sorted(specifications(SEASON)[name][2])


def main():
    alumni = json.loads((ROOT / "data" / "alumni.json").read_text(encoding="utf-8"))
    registry = [a for a in alumni if a["name"] in NAMES]
    if len(registry) != len(NAMES):
        raise SystemExit("A fixture player is missing from data/alumni.json")
    ids = {a["gsis_id"] for a in registry}
    data, manifest, warnings = load_sources(SEASON, ROOT / ".cache", historical=True, week=WEEK)
    for warning in warnings:
        print("warning:", warning)
    OUT.mkdir(parents=True, exist_ok=True)
    week, next_week = str(WEEK), str(WEEK + 1)
    schedule = [g for g in data["schedule"] if g["season"] == str(SEASON)]
    week_games = {g["game_id"] for g in schedule if g["week"] == week}
    write("schedule", schedule, SCHEDULE_COLUMNS)
    rosters = [r for r in data["rosters"] if r["gsis_id"] in ids and r["week"] in (week, next_week)]
    write("rosters", rosters, columns_of(rosters, "rosters"))
    current = [r for r in data["current_rosters"] if r["gsis_id"] in ids]
    write("current_rosters", current, columns_of(current, "current_rosters"))
    write("players", [p for p in data["players"] if p["gsis_id"] in ids], PLAYER_COLUMNS)
    stats = [r for r in data["stats"] if r["player_id"] in ids and r["week"] == week]
    write("stats", stats, columns_of(data["stats"], "stats"))
    roles = [c for c in data["pbp"][0] if c.endswith("_player_id")]
    plays = [
        p for p in data["pbp"]
        if p["game_id"] in week_games
        and (p["desc"].strip().upper() == "END GAME" or any(p.get(c) in ids for c in roles))
    ]
    write("pbp", plays, PBP_BASE + roles)
    write("snaps", [s for s in data["snaps"] if s["game_id"] in week_games], columns_of(data["snaps"], "snaps"))
    injuries = [r for r in data["injuries"] if r["week"] == week and r["gsis_id"] in ids]
    write("injuries", injuries, columns_of(data["injuries"], "injuries"))
    write("teams", data["teams"], TEAM_COLUMNS)
    for name in ("ngs_passing", "ngs_receiving", "ngs_rushing"):
        rows = [r for r in data[name] if r["season"] == str(SEASON) and r["week"] == week and r["player_gsis_id"] in ids]
        write(name, rows, columns_of(data[name], name))
    (OUT / "alumni.json").write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8", newline="\n")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote fixtures for {len(registry)} players and {len(week_games)} games to {OUT}")


if __name__ == "__main__":
    main()
