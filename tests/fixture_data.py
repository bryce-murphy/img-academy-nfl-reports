"""Load the committed Week 2 fixture slice (regenerate with scripts/make_fixtures.py)."""
import csv
import json
from datetime import date
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "week02"
DATASETS = (
    "schedule", "rosters", "current_rosters", "players", "stats", "pbp", "snaps", "injuries",
    "teams", "ngs_passing", "ngs_receiving", "ngs_rushing",
)
GENERATED_AT = "2026-09-23T12:00:00+00:00"
TODAY = date(2026, 9, 23)


def load():
    data = {}
    for name in DATASETS:
        with (FIXTURES / f"{name}.csv").open(encoding="utf-8", newline="") as handle:
            data[name] = list(csv.DictReader(handle))
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    registry = json.loads((FIXTURES / "alumni.json").read_text(encoding="utf-8"))
    return data, manifest, registry


def week_games(data, week=2, season=2026):
    return [
        g for g in data["schedule"]
        if int(g["season"]) == season and int(g["week"]) == week and g["game_type"] == "REG"
    ]
