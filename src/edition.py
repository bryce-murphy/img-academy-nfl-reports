"""Build the validated edition model (edition.json) from nflverse datasets."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import evidence as ev
from . import moves
from . import readiness
from .data import load_sources, utcnow
from .errors import DataError, NotReady
from .players import SLUG
from .upnext import next_game

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 4
EDITIONS_ROOT = ROOT / "editions"
KEEP_FIELDS = ("current", "position", "team_changed")
_INTS = ("down", "ydstogo", "yardline_100", "yards_gained", "air_yards", "yards_after_catch")
_FLAGS = ("goal_to_go", "pass_attempt", "rush_attempt", "complete_pass", "sack", "interception", "fumble",
          "penalty", "qb_kneel", "qb_spike", "two_point_attempt", "qb_dropback")
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
    slugs = [a.get("slug", "") for a in registry]
    if not all(SLUG.fullmatch(s or "") for s in slugs) or len(slugs) != len(set(slugs)):
        raise DataError("Every alumni entry needs a unique lowercase slug")
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
        # Charting is optional: malformed rows are skipped and duplicate join keys are ambiguous, never guessed.
        self.ftn, self.ftn_ambiguous = _index(
            ((r["nflverse_game_id"], play_key(r.get("nflverse_play_id"))), r) for r in data.get("ftn", []) if ev.num(r.get("week")) == week
        )
        self.ftn_games = {game_id for game_id, _ in self.ftn}
        self.pfr = {
            name: _index(((r["game_id"], r["pfr_player_id"]), r) for r in data.get(name, []) if ev.num(r.get("week")) == week)
            for name in ("pfr_def", "pfr_rec", "pfr_rush")
        }

    def team_name(self, team):
        return self.teams.get(team, {}).get("team_name", team)

    def team_color(self, team):
        return safe_color(self.teams.get(team, {}).get("team_color"))

    def this_week(self, rows, id_key, pid):
        return [r for r in rows if r[id_key] == pid and int(r["season"]) == self.season and int(r["week"]) == self.week]


def play_key(value):
    """'40', '40.0' -> '40': play ids differ in format between play-by-play and FTN. None when not a whole number."""
    number = ev.num(value)
    return str(int(number)) if number is not None and number == int(number) else None


def _int_or_none(value):
    number = ev.num(value)
    return int(number) if number is not None else None


_MISSING_TEXT = ("", "NA", "NaN")


def _text_or_none(value):
    """A play-by-play text cell, or None when it is blank or an NA/NaN placeholder."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text in _MISSING_TEXT else text


def _flag_or_none(value):
    number = ev.num(value)
    return None if number is None else int(number == 1)


def _round_or_none(value, digits):
    number = ev.num(value)
    return round(number, digits) if number is not None else None


def play_record(play, pid, team, team_name):
    """One recorded play for player pages. Blank or NA cells stay None; flags are 0/1/None."""
    side, impact = ev.side_and_impact(play, pid, team)
    laterals = [_flag_or_none(play.get(k)) for k in ("lateral_reception", "lateral_rush")]
    return {
        "play_id": play_key(play["play_id"]),
        "quarter": ev.quarter_label(play.get("qtr")),
        "clock": play.get("time", ""),
        "offense": play.get("posteam", ""),
        "defense": play.get("defteam", ""),
        "offense_name": team_name(play.get("posteam", "")),
        "defense_name": team_name(play.get("defteam", "")),
        "play_type": play.get("play_type", ""),
        **{k: _int_or_none(play.get(k)) for k in _INTS},
        **{k: _flag_or_none(play.get(k)) for k in _FLAGS},
        "lateral": 1 if 1 in laterals else (0 if laterals == [0, 0] else None),
        "cp": _round_or_none(play.get("cp"), 3),
        "qb_epa": _round_or_none(play.get("qb_epa"), 3),
        "epa": _round_or_none(play.get("epa"), 2),
        "side": side,
        "impact": impact,
        "roles": ev.recorded_roles(play, pid),
        "description": play.get("desc", ""),
        "passer_name": _text_or_none(play.get("passer_player_name")),
        "rusher_name": _text_or_none(play.get("rusher_player_name")),
        "receiver_name": _text_or_none(play.get("receiver_player_name")),
    }


def _index(pairs):
    """Map join key -> row, dropping keys that appear more than once (returned separately as ambiguous)."""
    index, ambiguous = {}, set()
    for key, row in pairs:
        if None in key:
            continue
        if key in index:
            ambiguous.add(key)
        index[key] = row
    for key in ambiguous:
        index.pop(key)
    return index, ambiguous


def _flag(value):
    """FTN booleans: True/False only when explicitly charted; anything else is unknown (None)."""
    text = str(value).strip().upper()
    return True if text in ("TRUE", "1") else False if text in ("FALSE", "0") else None


def _counts(row, fields):
    """Counts for a group of fields, or None if any is missing: a blank is never a zero. Whole numbers become ints;
    a fraction (PFR splits a shared sack as 0.5) is kept as it is."""
    values = {key: ev.num(row.get(column)) for key, column in fields}
    return None if any(v is None for v in values.values()) else {k: int(v) if float(v).is_integer() else v for k, v in values.items()}


COVERAGE_FIELDS = (("targets", "def_targets"), ("completions", "def_completions_allowed"), ("yards", "def_yards_allowed"), ("touchdowns", "def_receiving_td_allowed"), ("interceptions", "def_ints"))
PASS_RUSH_FIELDS = (("pressures", "def_pressures"), ("hurries", "def_times_hurried"), ("qb_hits", "def_times_hitqb"), ("sacks", "def_sacks"), ("blitzes", "def_times_blitzed"))
TACKLING_FIELDS = (("missed", "def_missed_tackles"), ("combined", "def_tackles_combined"))
RUSHING_FIELDS = (("carries", "carries"), ("before_contact", "rushing_yards_before_contact"), ("after_contact", "rushing_yards_after_contact"), ("broken_tackles", "rushing_broken_tackles"))


def _pfr_row(wk, source, game_id, pfr, team, name, warnings):
    if not pfr:
        return None
    index, ambiguous = wk.pfr[source]
    if (game_id, pfr) in ambiguous:
        warnings.append(f"{name}: duplicate {source} charting rows withheld")
        return None
    row = index.get((game_id, pfr))
    if row and row.get("team") != team:
        warnings.append(f"{name}: {source} charting withheld (row team {row.get('team')} is not {team})")
        return None
    return row


def _target_counts(wk, pid, game_id, plays):
    charted = []
    for p in plays:
        if p.get("receiver_player_id") != pid or p.get("play_type") != "pass":
            continue
        key = (game_id, play_key(p.get("play_id")))
        row = wk.ftn.get(key)
        flags = {k: _flag(row.get(k)) for k in ("is_catchable_ball", "is_contested_ball", "is_drop")} if row else None
        if flags and None not in flags.values():
            charted.append((p, flags))
    if not charted:
        return None
    return {
        "charted": len(charted),
        "catchable": sum(f["is_catchable_ball"] for _, f in charted),
        "contested": sum(f["is_contested_ball"] for _, f in charted),
        "contested_catches": sum(f["is_contested_ball"] and p.get("complete_pass") == "1" for p, f in charted),
        "drops": sum(f["is_drop"] for _, f in charted),
    }


def charting(wk, pid, pfr, team, game, plays, stat, name, warnings):
    """Hand-charted extras (FTN Data; Pro Football Reference), as counts. None when nothing was charted."""
    if not game:
        return None
    game_id = game["game_id"]
    found = {"targets": None, "coverage": None, "pass_rush": None, "tackling": None, "rushing": None, "broken_tackles": None}
    if game_id in wk.ftn_games:
        found["targets"] = _target_counts(wk, pid, game_id, plays)
    defense = _pfr_row(wk, "pfr_def", game_id, pfr, team, name, warnings)
    if defense:
        cover = _counts(defense, COVERAGE_FIELDS)
        problem = cover and ev.coverage_problem(**cover)
        if problem:
            warnings.append(f"{name}: charted coverage withheld ({problem})")
        elif cover and cover["targets"]:
            found["coverage"] = cover
        rush = _counts(defense, PASS_RUSH_FIELDS)
        if rush and any(rush.values()):
            found["pass_rush"] = rush
        tackles = _counts(defense, TACKLING_FIELDS)
        if tackles and tackles["missed"] + tackles["combined"]:
            found["tackling"] = {"missed": tackles["missed"], "attempts": tackles["missed"] + tackles["combined"]}
    carries = _pfr_row(wk, "pfr_rush", game_id, pfr, team, name, warnings)
    rushing = _counts(carries, RUSHING_FIELDS) if carries else None
    if rushing and rushing["carries"]:
        box_carries, box_yards = ev.num(stat.get("carries")), ev.num(stat.get("rushing_yards"))
        charted_yards = rushing["before_contact"] + rushing["after_contact"]
        if box_carries is None or box_yards is None:
            warnings.append(f"{name}: charted contact yards withheld (no box-score rushing line)")
        elif (box_carries, box_yards) != (rushing["carries"], charted_yards):
            warnings.append(f"{name}: charted contact yards withheld ({charted_yards} yards on {rushing['carries']} carries; box score {box_yards:g} on {box_carries:g})")
        else:
            found["rushing"] = rushing
    catches = _pfr_row(wk, "pfr_rec", game_id, pfr, team, name, warnings)
    broken = ev.num(catches.get("receiving_broken_tackles")) if catches else None
    if broken:
        found["broken_tackles"] = int(broken)
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


def team_snaps(rows, team):
    """Team snaps per phase: the most any player on the team played in that phase of the game."""
    out = {}
    for phase, column in (("team_offense", "offense_snaps"), ("team_defense", "defense_snaps"), ("team_st", "st_snaps")):
        values = [ev.num(r.get(column)) for r in rows if r.get("team") == team]
        values = [v for v in values if v is not None]
        out[phase] = int(max(values)) if values and max(values) > 0 else None
    return out


def _whole(value, tolerance=0.05):
    return int(round(value)) if value is not None and abs(value - round(value)) <= tolerance else None


def usage(stat):
    targets, share = ev.num(stat.get("targets")), ev.num(stat.get("target_share"))
    air, air_share = ev.num(stat.get("receiving_air_yards")), ev.num(stat.get("air_yards_share"))
    return {
        "targets": int(targets) if targets is not None else None,
        "team_targets": _whole(targets / share) if targets is not None and share else None,
        "air_yards": int(air) if air is not None else None,
        "team_air_yards": _whole(air / air_share) if air is not None and air_share else None,
    }


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
    recorded = [
        p for p in plays
        if p.get("play_type") not in {"", "no_play"} and p.get("play_deleted") != "1" and p.get("aborted_play") != "1"
        and ev.recorded_roles(p, pid)
    ]
    recorded.sort(key=lambda p: float(p["play_id"]))
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
        "snaps": {
            "offense": ev.clean(snap.get("offense_snaps")), "defense": ev.clean(snap.get("defense_snaps")), "st": ev.clean(snap.get("st_snaps")),
            **team_snaps(wk.snaps_by_team.get((game.get("game_id"), team), []), team),
        },
        "usage": usage(stat),
        "key_plays": [
            dict(k, offense_name=wk.team_name(k["offense"]), defense_name=wk.team_name(k["defense"]))
            for k in ev.key_plays(involvement, pid, team)
        ],
        "plays": [play_record(p, pid, team, wk.team_name) for p in recorded],
        "next_gen": next_gen(wk, pid, team, game),
        "charting": charting(wk, pid, pfr, team, game, plays, stat, name, warnings),
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


def build_edition(data, registry, games, season, week, *, generated_at, historical=False, warnings=(), history=(), keep=None):
    warnings = list(warnings)
    wk = _Week(data, games, season, week, historical, ev.validate_games(games, data["pbp"]))
    players = [player_record(alum, wk, warnings) for alum in registry]
    keep = keep or {}
    for p in players:
        published = keep.get(p["id"])
        if published:
            p.update({k: published[k] for k in KEEP_FIELDS if k in published})
        if published and "move" in published:
            p["move"] = published["move"]
        else:
            p["move"] = moves.detect(p, week, games, list(history), wk.team_name, wk.team_color)
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
        "teams": {
            abbr: {"name": wk.team_name(abbr), "color": wk.team_color(abbr)}
            for abbr in sorted({g["home_team"] for g in games} | {g["away_team"] for g in games})
        },
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


def build_week(season, week, games, *, historical, final, registry, sources=fetch, editions_root=None, keep=None):
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
        history=moves.load_history(editions_root or EDITIONS_ROOT, season, week), keep=keep,
    )
    return edition, manifest, report


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m src.edition", description="Build editions/<id>/ from nflverse data (manual path).")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--historical", action="store_true", help="Relax source freshness and omit up-next")
    parser.add_argument("--out", type=Path, default=ROOT / "editions")
    parser.add_argument("--rebuild", action="store_true",
                        help="Rebuild a published edition, keeping its roster notes, positions, team-change flags and moves")
    args = parser.parse_args(argv)
    config = load_config()
    week, games = due_week(args.season, args.week, today=utcnow().date(), historical=args.historical, scheduled=False, season_types=config["season_types"])
    keep = None
    if args.rebuild:
        published = args.out / edition_id(args.season, week) / "edition.json"
        if not published.is_file():
            parser.error(f"--rebuild needs a published {published}")
        keep = {p["id"]: p for p in json.loads(published.read_text(encoding="utf-8"))["players"]}
    edition, manifest, report = build_week(args.season, week, games, historical=args.historical, final=True,
                                           registry=load_registry(), editions_root=args.out, keep=keep)
    directory = args.out / edition["id"]
    write_edition(edition, manifest, directory)
    from . import editorial  # local import: editorial reads edition dicts; edition never needs editorial otherwise

    headline_file = directory / "editorial.toml"
    if not headline_file.exists():
        headline_file.write_bytes(editorial.dumps(editorial.fallback(edition), stubs=moves.moved_players(edition)).encode("utf-8"))
    print(f"Built {directory}: {edition['counts']['played']} of {edition['counts']['followed']} alumni played; "
          f"missing optional data: {', '.join(report.missing_optional) or 'none'}; "
          f"charting pending: {', '.join(report.pending) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
