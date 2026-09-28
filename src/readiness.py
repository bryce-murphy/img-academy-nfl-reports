"""Decide whether the reporting week's data has landed. Pure functions over loaded datasets."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from .evidence import num, snap_table_complete


@dataclass
class Readiness:
    missing_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)
    # Charting (Next Gen Stats, FTN, PFR) often lands after Tuesday: listed for the editor, never waited for.
    pending: list[str] = field(default_factory=list)

    def ready(self, final):
        return not self.missing_required and (final or not self.missing_optional)

    def missing(self):
        return self.missing_required + self.missing_optional


def _updated_on(timestamp):
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date()


def assess(data, manifest, games, season, week, followed_teams=None):
    report = Readiness()
    last_day = max(date.fromisoformat(g["gameday"]) for g in games)
    ended = {p["game_id"] for p in data["pbp"] if p.get("desc", "").strip().upper() == "END GAME"}
    stats_by_game = defaultdict(list)
    for row in data["stats"]:
        if int(row["season"]) == season and int(row["week"]) == week:
            stats_by_game[row["game_id"]].append(row)
    for game in games:
        if num(game["home_score"]) is None or num(game["away_score"]) is None:
            report.missing_required.append(f"final score for {game['game_id']}")
        if game["game_id"] not in ended:
            report.missing_required.append(f"play-by-play end of game for {game['game_id']}")
        if followed_teams is None or {game["away_team"], game["home_team"]} & followed_teams:
            if not stats_by_game.get(game["game_id"]):
                report.missing_required.append(f"player statistics for {game['game_id']}")
    rosters_updated = manifest.get("rosters", {}).get("updated_at")
    if not rosters_updated or _updated_on(rosters_updated) <= last_day:
        report.missing_required.append("weekly rosters updated after the last game")
    by_team = defaultdict(list)
    for row in data.get("snaps", []):
        by_team[(row["game_id"], row["team"])].append(row)
    for game in games:
        for team in (game["away_team"], game["home_team"]):
            if not snap_table_complete(by_team.get((game["game_id"], team), [])):
                report.missing_optional.append(f"snap counts for {team} in {game['game_id']}")
    if not any(int(i["season"]) == season and int(i["week"]) == week for i in data.get("injuries", [])):
        report.missing_optional.append("injury report")
    report.pending = charting_gaps(data, games, season, week, followed_teams)
    return report


def _this_week(rows, season, week):
    return [r for r in rows if num(r.get("season")) == season and num(r.get("week")) == week]


def charting_gaps(data, games, season, week, followed_teams=None):
    gaps = []
    for kind in ("passing", "receiving", "rushing"):
        if not _this_week(data.get(f"ngs_{kind}", []), season, week):
            gaps.append(f"Next Gen Stats ({kind}) for Week {week}")
    ftn_games = {r.get("nflverse_game_id") for r in _this_week(data.get("ftn", []), season, week)}
    pfr_games = {r.get("game_id") for name in ("pfr_def", "pfr_rec", "pfr_rush") for r in _this_week(data.get(name, []), season, week)}
    for game in games:
        if followed_teams is not None and not {game["away_team"], game["home_team"]} & followed_teams:
            continue
        if game["game_id"] not in ftn_games:
            gaps.append(f"FTN charting for {game['game_id']}")
        if game["game_id"] not in pfr_games:
            gaps.append(f"PFR charting for {game['game_id']}")
    return gaps
