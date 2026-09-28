"""Load the committed Week 2 fixture slice (regenerate with scripts/make_fixtures.py)."""
import csv
import json
from datetime import date
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "week02"
DATASETS = (
    "schedule", "rosters", "current_rosters", "players", "stats", "pbp", "snaps", "injuries",
    "teams", "ngs_passing", "ngs_receiving", "ngs_rushing", "ftn", "pfr_def", "pfr_rec", "pfr_rush",
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


def roster_samples():
    with (FIXTURES / "roster_samples.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def golden_edition():
    return json.loads((FIXTURES / "expected_edition.json").read_text(encoding="utf-8"))


def write_edition_dir(root, edition, copy=None, sources=None):
    """Write editions/<id>/ with edition.json, sources.json and editorial.toml for tests."""
    from src import editorial

    target = Path(root) / edition["id"]
    target.mkdir(parents=True, exist_ok=True)
    (target / "edition.json").write_text(json.dumps(edition), encoding="utf-8")
    (target / "sources.json").write_text(json.dumps(sources or {}), encoding="utf-8")
    (target / "editorial.toml").write_text(editorial.dumps(copy or editorial.fallback(edition)), encoding="utf-8")
    return target
