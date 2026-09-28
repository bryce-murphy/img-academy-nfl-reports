"""Build the validated edition model (edition.json) from nflverse datasets."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import evidence as ev
from . import readiness
from .data import load_sources, utcnow
from .errors import DataError, NotReady
from .upnext import next_game

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
DEFAULT_COLOR = "#123d35"
RECEIVING = [("receiving_yards", "receiving yards"), ("receptions", "catches"), ("targets", "targets"), ("receiving_tds", "TD")]
POSITIONS = {
    "QB": [("passing_yards", "pass yards"), ("passing_tds", "pass TD"), ("passing_interceptions", "INT"), ("rushing_yards", "rush yards")],
    "WR": RECEIVING,
    "TE": RECEIVING,
    "RB": [("rushing_yards", "rush yards"), ("carries", "carries"), ("rushing_tds", "rush TD"), ("receiving_yards", "receiving yards")],
    "K": [("fg_made", "field goals"), ("fg_att", "FG attempts"), ("pat_made", "extra points"), ("fg_long", "long FG")],
    "P": [("pt_att", "punts"), ("pt_yards", "punt yards"), ("pt_inside_20", "inside the 20"), ("pt_long", "long punt")],
}
DEFENSE = [("def_tackles_solo", "solo tackles"), ("def_tackle_assists", "assists"), ("def_sacks", "sacks"), ("def_pass_defended", "passes defended")]
SNAP_METRICS = {
    "OL": [("offense_snaps", "offensive snaps"), ("st_snaps", "special-teams snaps")],
    "LS": [("st_snaps", "special-teams snaps")],
}
OFFENSIVE_LINE = {"OL", "OT", "OG", "C", "G", "T"}
ROSTER_LABELS = {"ACT": "Active roster", "INA": "Inactive", "RES": "Reserve list", "DEV": "Practice squad", "CUT": "Released", "RET": "Retired", "EXE": "Exempt list"}
NEXT_GEN = {
    "ngs_passing": [("avg_time_to_throw", "Time to throw", "s"), ("completion_percentage_above_expectation", "Completion above expectation", "percentage points")],
    "ngs_receiving": [("avg_separation", "Average separation", "yards"), ("avg_yac_above_expectation", "YAC above expectation per catch", "yards")],
    "ngs_rushing": [("rush_yards_over_expected", "Rushing yards over expected", "yards"), ("rush_yards_over_expected_per_att", "RYOE per carry", "yards")],
}
YARDAGE_KEYS = ("passing_yards", "rushing_yards", "receiving_yards")


def edition_id(season, week):
    return f"{season}-week-{week:02d}"


def load_config(path=ROOT / "config.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_registry(path=ROOT / "data" / "alumni.json"):
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = [a["gsis_id"] for a in registry]
    if len(ids) != len(set(ids)) or not all(re.fullmatch(r"00-\d{7}", i) for i in ids):
        raise DataError("Invalid or duplicate alumni IDs")
    return registry


def safe_color(value):
    return value if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else DEFAULT_COLOR


def stat_season_type(game_type):
    """nflverse schedule game_type is REG/WC/DIV/CON/SB; stats and NGS season_type is REG/POST."""
    return "REG" if game_type == "REG" else "POST"


def metrics_for(position, stats, snap):
    group = "OL" if position in OFFENSIVE_LINE else position
    if group in SNAP_METRICS:
        return [{"key": k, "label": label, "value": ev.clean(snap.get(k))} for k, label in SNAP_METRICS[group]]
    return [{"key": k, "label": label, "value": ev.clean(stats.get(k))} for k, label in POSITIONS.get(group, DEFENSE)]


def game_summary(game, team):
    if not game:
        return None
    home = game["home_team"] == team
    team_score = ev.clean(game["home_score"] if home else game["away_score"])
    opp_score = ev.clean(game["away_score"] if home else game["home_score"])
    result = "W" if team_score > opp_score else "L" if team_score < opp_score else "T"
    return {
        "game_id": game["game_id"],
        "opponent": game["away_team"] if home else game["home_team"],
        "home_away": "home" if home else "away",
        "team_score": team_score,
        "opp_score": opp_score,
        "result": result,
    }


class _Week:
    """Indexes shared by every player record in one edition."""

    def __init__(self, data, games, season, week, historical, by_game):
        self.data = data
        self.games = games
        self.season = season
        self.week = week
        self.historical = historical
        self.by_game = by_game
        self.stat_season_types = {stat_season_type(g["game_type"]) for g in games}
        self.people = {p["gsis_id"]: p for p in data["players"] if p.get("gsis_id")}
        self.teams = {t["team_abbr"]: t for t in data["teams"]}
        self.snaps_by_team = defaultdict(list)
        for row in data.get("snaps", []):
            self.snaps_by_team[(row["game_id"], row["team"])].append(row)
        self.ftn = {(r["nflverse_game_id"], play_key(r["nflverse_play_id"])): r for r in data.get("ftn", []) if int(r["week"]) == week}
        self.ftn_games = {game_id for game_id, _ in self.ftn}
        self.pfr = {
            name: {(r["game_id"], r["pfr_player_id"]): r for r in data.get(name, []) if int(r["week"]) == week}
            for name in ("pfr_def", "pfr_rec", "pfr_rush")
        }

    def team_name(self, team):
        return self.teams.get(team, {}).get("team_name", team)

    def team_color(self, team):
        return safe_color(self.teams.get(team, {}).get("team_color"))

    def this_week(self, rows, id_key, pid):
        return [r for r in rows if r[id_key] == pid and int(r["season"]) == self.season and int(r["week"]) == self.week]


def play_key(value):
    """'40', '40.0' -> '40': play ids differ in format between play-by-play and FTN."""
    return str(int(float(value)))


def _yes(value):
    return str(value).strip().upper() in ("TRUE", "1")


def _count(row, key):
    return int(ev.num(row.get(key)) or 0)


def charting(wk, pid, pfr, game, plays, name, warnings):
    """Hand-charted extras (FTN Data; Pro Football Reference), as counts. None when nothing was charted."""
    if not game:
        return None
    game_id = game["game_id"]
    found = {"targets": None, "coverage": None, "pass_rush": None, "tackling": None, "rushing": None, "broken_tackles": None}
    if game_id in wk.ftn_games:
        targets = [p for p in plays if p.get("receiver_player_id") == pid and p.get("play_type") == "pass"]
        rows = [(p, wk.ftn.get((game_id, play_key(p["play_id"])))) for p in targets]
        rows = [(p, r) for p, r in rows if r]
        if rows:
            found["targets"] = {
                "charted": len(rows),
                "catchable": sum(_yes(r["is_catchable_ball"]) for _, r in rows),
                "contested": sum(_yes(r["is_contested_ball"]) for _, r in rows),
                "contested_catches": sum(_yes(r["is_contested_ball"]) and p.get("complete_pass") == "1" for p, r in rows),
                "drops": sum(_yes(r["is_drop"]) for _, r in rows),
            }
    defense = wk.pfr["pfr_def"].get((game_id, pfr)) if pfr else None
    if defense:
        cover = {k: _count(defense, c) for k, c in (("targets", "def_targets"), ("completions", "def_completions_allowed"), ("yards", "def_yards_allowed"), ("touchdowns", "def_receiving_td_allowed"), ("interceptions", "def_ints"))}
        problem = ev.coverage_problem(**cover)
        if problem:
            warnings.append(f"{name}: charted coverage withheld ({problem})")
        elif cover["targets"]:
            found["coverage"] = cover
        rush = {k: _count(defense, c) for k, c in (("pressures", "def_pressures"), ("hurries", "def_times_hurried"), ("qb_hits", "def_times_hitqb"), ("sacks", "def_sacks"), ("blitzes", "def_times_blitzed"))}
        if any(rush.values()):
            found["pass_rush"] = rush
        missed = _count(defense, "def_missed_tackles")
        attempts = missed + _count(defense, "def_tackles_combined")
        if attempts:
            found["tackling"] = {"missed": missed, "attempts": attempts}
    carries = wk.pfr["pfr_rush"].get((game_id, pfr)) if pfr else None
    if carries and _count(carries, "carries"):
        found["rushing"] = {
            "carries": _count(carries, "carries"),
            "before_contact": _count(carries, "rushing_yards_before_contact"),
            "after_contact": _count(carries, "rushing_yards_after_contact"),
            "broken_tackles": _count(carries, "rushing_broken_tackles"),
        }
    catches = wk.pfr["pfr_rec"].get((game_id, pfr)) if pfr else None
    if catches and _count(catches, "receiving_broken_tackles"):
        found["broken_tackles"] = _count(catches, "receiving_broken_tackles")
    return found if any(v is not None for v in found.values()) else None


def next_gen(wk, pid, team, game):
    values = []
    if not game:
        return values
    for source, fields in NEXT_GEN.items():
        rows = [
            r for r in wk.data.get(source, [])
            if r["player_gsis_id"] == pid and int(r["season"]) == wk.season and int(r["week"]) == wk.week
            and r["team_abbr"] == team and r.get("season_type") == stat_season_type(game.get("game_type", ""))
        ]
        row = ev.unique(rows, "Next Gen Stats")
        for key, label, unit in fields:
            value = ev.num(row.get(key))
            if value is not None:
                values.append({"label": label, "value": round(value, 2), "unit": unit, "source": source})
    return values


def player_record(alum, wk, warnings):
    pid, name = alum["gsis_id"], alum["name"]
    data = wk.data
    person = wk.people.get(pid, {})
    roster = ev.unique(wk.this_week(data["rosters"], "gsis_id", pid), name + " weekly roster")
    current = ev.unique([r for r in data["current_rosters"] if r["gsis_id"] == pid], name + " current roster")
    stat = ev.unique([r for r in wk.this_week(data["stats"], "player_id", pid) if r["season_type"] in wk.stat_season_types], name + " statistics")
    team = stat.get("team") or roster.get("team", "")
    game = ev.unique([g for g in wk.games if team and team in (g["home_team"], g["away_team"])], name + " team schedule")
    if stat and (not game or stat["game_id"] != game["game_id"]):
        raise DataError(f"Game/team identity mismatch for {name}")
    plays = wk.by_game.get(game.get("game_id"), [])
    # Actual participation roles only: penalty-only and fantasy attributions do not count.
    roles = [k for k in (plays[0] if plays else {}) if k.endswith("_player_id") and not k.startswith(("penalty", "fantasy"))]
    involvement = [p for p in plays if p.get("play_type") not in {"", "no_play"} and any(p.get(k) == pid for k in roles)]
    pfr = alum.get("pfr_id") or person.get("pfr_id") or roster.get("pfr_id")
    snap = ev.unique([s for s in data.get("snaps", []) if pfr and s["pfr_player_id"] == pfr and s["game_id"] == game.get("game_id")], name + " snap count")
    if snap and snap["team"] != team:
        raise DataError(f"Snap count team does not match the game roster for {name}")
    injury = ev.unique([r for r in wk.this_week(data.get("injuries", []), "gsis_id", pid) if r["team"] == team], name + " injury report")
    complete = ev.snap_table_complete(wk.snaps_by_team.get((game.get("game_id"), team), []))
    label, evidence_text = ev.availability(snap, involvement, stat, roster or None, bool(game), complete)
    mismatches = ev.yardage_mismatches(stat, plays, pid)
    if mismatches:
        warnings.append(f"{name}: stats withheld because {', '.join(mismatches)} disagree with play-by-play")
    position = person.get("position") or roster.get("position") or current.get("position", "")
    metrics = metrics_for(position, stat, snap)
    if mismatches:
        metrics = [dict(m, value=None) for m in metrics]
    next_team = current.get("team") or team
    upcoming = None
    if not wk.historical and current.get("status") not in ("CUT", "RET"):
        upcoming = next_game(data["schedule"], wk.season, wk.week, next_team)
        upcoming.update(team=next_team, team_name=wk.team_name(next_team), team_color=wk.team_color(next_team))
    draft = f"{person['draft_year']} draft, round {person.get('draft_round', '')}" if person.get("draft_year") else ""
    return {
        "id": pid,
        "name": name,
        "position": position,
        "team": team,
        "team_name": wk.team_name(team),
        "team_color": wk.team_color(team),
        "context": " · ".join(x for x in (person.get("college_name", ""), draft) if x),
        "availability": {"label": label, "evidence": evidence_text},
        "game": game_summary(game, team),
        "metrics": metrics,
        "stats_withheld": bool(mismatches),
        "snaps": {"offense": ev.clean(snap.get("offense_snaps")), "defense": ev.clean(snap.get("defense_snaps")), "st": ev.clean(snap.get("st_snaps"))},
        "key_plays": [
            dict(k, offense_name=wk.team_name(k["offense"]), defense_name=wk.team_name(k["defense"]))
            for k in ev.key_plays(involvement, pid, team)
        ],
        "next_gen": next_gen(wk, pid, team, game),
        "charting": charting(wk, pid, pfr, game, plays, name, warnings),
        "injury_report": {"designation": injury.get("report_status", ""), "primary_injury": injury.get("report_primary_injury", "")}
        if injury.get("report_status") or injury.get("report_primary_injury") else None,
        "current": {
            "team": current.get("team", ""),
            "roster_status": current.get("status", ""),
            "roster_label": ROSTER_LABELS.get(current.get("status", ""), current.get("status", "") or "Not found"),
        },
        "team_changed": bool(team and current.get("team") and current["team"] != team),
        "next_game": upcoming,
        "score": ev.performance_score(stat) if label == ev.PLAYED and not mismatches else 0.0,
        "alumni_source": alum["source_url"],
    }


def build_edition(data, registry, games, season, week, *, generated_at, historical=False, warnings=()):
    warnings = list(warnings)
    wk = _Week(data, games, season, week, historical, ev.validate_games(games, data["pbp"]))
    players = [player_record(alum, wk, warnings) for alum in registry]
    ranking = ev.rank(players)
    order = {pid: i for i, pid in enumerate(ranking)}
    players.sort(key=lambda p: (order.get(p["id"], len(order)), ev.LABEL_ORDER.index(p["availability"]["label"]), p["name"]))
    conflicts = [p["name"] for p in players if p["availability"]["label"] == ev.CONFLICT]
    if conflicts:
        warnings.append("Conflicting participation evidence for " + ", ".join(conflicts) + "; social drafts are withheld")
    labels = Counter(p["availability"]["label"] for p in players)
    reconciled = sum(
        1 for p in players
        if not p["stats_withheld"] and any(m["key"] in YARDAGE_KEYS and m["value"] is not None for m in p["metrics"])
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "id": edition_id(season, week),
        "season": season,
        "week": week,
        "season_type": games[0]["game_type"] if games else "REG",
        "generated_at": generated_at,
        "label": "Historical replay" if historical else "Verified source snapshot",
        "historical": historical,
        "games": [
            {"game_id": g["game_id"], "gameday": g["gameday"], "away_team": g["away_team"], "away_score": ev.clean(g["away_score"]),
             "home_team": g["home_team"], "home_score": ev.clean(g["home_score"])}
            for g in sorted(games, key=lambda g: (g["gameday"], g["game_id"]))
        ],
        "players": players,
        "featured_ranking": ranking,
        "counts": {"followed": len(players), "played": labels[ev.PLAYED], "by_label": dict(sorted(labels.items()))},
        "warnings": warnings,
        "validation": {
            "passed": True,
            "checks": [
                f"Final scores match the play-by-play end-of-game record for all {len(games)} games.",
                "Players are matched by GSIS and PFR IDs, never by name.",
                f"Passing, rushing and receiving yards reconcile with play-by-play for {reconciled} players.",
                "Missing statistics are never treated as a DNP; absences come from weekly roster statuses and complete snap tables.",
            ],
        },
        "publication_ready": not conflicts,
    }


def dump_json(value, *, sort_keys=False):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n").encode("utf-8")


def write_edition(edition, sources, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "edition.json").write_bytes(dump_json(edition))
    (directory / "sources.json").write_bytes(dump_json(sources, sort_keys=True))


def fetch(season, *, week=None, only=None, historical=False):
    config = load_config()
    return load_sources(season, ROOT / ".cache", config["max_source_age_hours"], historical, only=only, week=week)


def due_week(season, week, *, today, historical, scheduled, season_types, sources=fetch):
    schedule = sources(season, only={"schedule"}, historical=historical)[0]["schedule"]
    return ev.choose_week(schedule, season, today, season_types, week, scheduled)


def build_week(season, week, games, *, historical, final, registry, sources=fetch):
    data, manifest, warnings = sources(season, week=week, historical=historical)
    ids = {alum["gsis_id"] for alum in registry}
    followed_teams = {
        row["team"] for row in data["rosters"]
        if row["gsis_id"] in ids and int(row["season"]) == season and int(row["week"]) == week
    }
    report = readiness.assess(data, manifest, games, season, week, followed_teams=followed_teams)
    if not report.ready(final):
        raise NotReady("Waiting for: " + "; ".join(report.missing()), week=week)
    warnings = list(warnings) + [f"{item} not yet available; related claims withheld" for item in report.missing_optional]
    edition = build_edition(
        data, registry, games, season, week,
        generated_at=utcnow().isoformat(timespec="seconds"), historical=historical, warnings=warnings,
    )
    return edition, manifest, report


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m src.edition", description="Build editions/<id>/ from nflverse data (manual path).")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--historical", action="store_true", help="Relax source freshness and omit up-next")
    parser.add_argument("--out", type=Path, default=ROOT / "editions")
    args = parser.parse_args(argv)
    config = load_config()
    week, games = due_week(args.season, args.week, today=utcnow().date(), historical=args.historical, scheduled=False, season_types=config["season_types"])
    edition, manifest, report = build_week(args.season, week, games, historical=args.historical, final=True, registry=load_registry())
    directory = args.out / edition["id"]
    write_edition(edition, manifest, directory)
    from . import editorial  # local import: editorial reads edition dicts; edition never needs editorial otherwise

    headline_file = directory / "editorial.toml"
    if not headline_file.exists():
        headline_file.write_bytes(editorial.dumps(editorial.fallback(edition)).encode("utf-8"))
    print(f"Built {directory}: {edition['counts']['played']} of {edition['counts']['followed']} alumni played; "
          f"missing optional data: {', '.join(report.missing_optional) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
