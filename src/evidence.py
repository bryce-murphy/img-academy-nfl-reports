"""Pure evidence rules. No I/O: every function takes rows and returns facts or raises."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

from .errors import DataError, NotReady

PLAYED = "Played"
CONFLICT = "Conflicting evidence"
NOT_ON_ROSTER = "Not on an NFL roster"
BYE = "Bye week"
NO_SNAPS = "No snaps recorded"
UNVERIFIED = "Participation unverified"
ROSTER_STATUS = {
    "INA": ("Inactive for the game", "Weekly roster status: inactive"),
    "DEV": ("Practice squad", "Weekly roster status: practice squad"),
    "RES": ("Reserve list", "Reserve list; no reason is inferred"),
    "CUT": ("Released", "Weekly roster status: released"),
}
LABEL_ORDER = [
    PLAYED, CONFLICT, "Inactive for the game", "Practice squad", "Reserve list", "Released",
    BYE, NO_SNAPS, UNVERIFIED, NOT_ON_ROSTER,
]
SNAP_KEYS = ("offense_snaps", "defense_snaps", "st_snaps")
ACTIVITY_KEYS = (
    "attempts", "carries", "receptions", "targets", "def_tackles_solo", "def_tackle_assists",
    "def_sacks", "def_interceptions", "def_pass_defended", "fg_att", "pat_att", "pt_att",
    "kickoff_returns", "punt_returns",
)
COMPLETE_SNAP_TABLE_MIN_PLAYERS = 22
YARDAGE_CHECKS = (
    ("passing_yards", "passer_player_id"),
    ("rushing_yards", "rusher_player_id"),
    ("receiving_yards", "receiver_player_id"),
)


def num(value):
    if value in (None, "", "NA", "NaN"):
        return None
    parsed = float(value)
    if not math.isfinite(parsed):
        raise DataError("Non-finite statistic")
    return parsed


def clean(value):
    parsed = num(value)
    if parsed is None:
        return None
    return int(parsed) if parsed.is_integer() else round(parsed, 2)


def fmt(value):
    parsed = num(value)
    return "—" if parsed is None else f"{parsed:g}"


def unique(rows, label):
    if len(rows) > 1:
        raise DataError(f"Ambiguous {label}; review the identity/game mapping")
    return rows[0] if rows else {}


def quarter_label(qtr):
    quarter = int(num(qtr) or 0)
    if 1 <= quarter <= 4:
        return f"Q{quarter}"
    if quarter == 5:
        return "OT"
    if quarter > 5:
        return f"{quarter - 4}OT"
    return ""


def snap_table_complete(team_rows):
    players = {row.get("pfr_player_id") for row in team_rows if row.get("pfr_player_id")}
    offense = any((num(row.get("offense_snaps")) or 0) > 0 for row in team_rows)
    defense = any((num(row.get("defense_snaps")) or 0) > 0 for row in team_rows)
    return len(players) >= COMPLETE_SNAP_TABLE_MIN_PLAYERS and offense and defense


def availability(snap, plays, stats, roster, has_game, team_snaps_complete):
    """Return (label, evidence). The first matching rule wins; see the spec's §5 table."""
    counts = [num(snap.get(key)) for key in SNAP_KEYS]
    if any(value is not None and value < 0 for value in counts):
        raise DataError("Negative snap count")
    explicit_zero = bool(snap) and all(value == 0 for value in counts)
    activity = any((num(stats.get(key)) or 0) > 0 for key in ACTIVITY_KEYS)
    if any(value is not None and value > 0 for value in counts):
        return PLAYED, "Positive snap count"
    if (plays or activity) and explicit_zero:
        return CONFLICT, "Recorded plays or statistics conflict with zero snaps"
    if plays:
        return PLAYED, "Recorded play involvement"
    if activity:
        return PLAYED, "Positive recorded game statistic"
    if roster is None:
        return NOT_ON_ROSTER, "No weekly roster record; current roster shown separately"
    if roster.get("status") in ROSTER_STATUS:
        return ROSTER_STATUS[roster["status"]]
    if not has_game:
        return BYE, "No game on this week's schedule"
    if explicit_zero or team_snaps_complete:
        return NO_SNAPS, "Reason not established by snap counts"
    return UNVERIFIED, "Missing evidence is not evidence of a DNP"


def choose_week(schedule, season, asof, allowed, week=None, scheduled=False):
    groups = defaultdict(list)
    for game in schedule:
        if int(game["season"]) == season and game["game_type"] in allowed:
            groups[int(game["week"])].append(game)
    eligible = [w for w, games in groups.items() if max(date.fromisoformat(g["gameday"]) for g in games) < asof]
    if week is not None:
        if week not in groups:
            raise DataError("Requested week is not a regular-season or postseason week")
        chosen = week
    elif eligible:
        chosen = max(eligible)
    else:
        raise DataError("No completed reporting window")
    games = groups[chosen]
    last_day = max(date.fromisoformat(g["gameday"]) for g in games)
    if last_day >= asof:
        raise NotReady("This NFL week still has scheduled games", week=chosen)
    if scheduled and not (0 < (asof - last_day).days <= 7):
        return None, []
    if any(num(g["home_score"]) is None or num(g["away_score"]) is None for g in games):
        raise NotReady("Scores are missing; do not reuse the preceding week's report", week=chosen)
    return chosen, games


def validate_games(games, pbp):
    by_game = defaultdict(list)
    seen = set()
    for play in pbp:
        key = (play["game_id"], play["play_id"])
        if key in seen:
            raise DataError("Duplicate play IDs")
        seen.add(key)
        by_game[play["game_id"]].append(play)
    for game in games:
        plays = by_game[game["game_id"]]
        ends = [p for p in plays if p.get("desc", "").strip().upper() == "END GAME"]
        if not ends:
            raise NotReady(f"No end-of-game evidence for {game['game_id']}")
        end = ends[-1]
        for side in ("home", "away"):
            if num(end.get(f"total_{side}_score")) != num(game[f"{side}_score"]):
                raise DataError(f"Final score disagreement for {game['game_id']}")
    return by_game


def yardage_mismatches(stats, plays, gsis_id):
    mismatches = []
    for metric, role in YARDAGE_CHECKS:
        expected = num(stats.get(metric))
        if expected is None:
            continue
        observed = sum(num(p.get(metric)) or 0 for p in plays if p.get(role) == gsis_id and p.get("play_type") != "no_play")
        if abs(expected - observed) > 0.01:
            mismatches.append(metric)
    return mismatches


def performance_score(stats):
    def stat(key):
        return num(stats.get(key)) or 0

    touchdowns = sum(stat(k) for k in ("passing_tds", "rushing_tds", "receiving_tds", "def_tds", "special_teams_tds"))
    score = 6 * touchdowns + 5 * stat("def_interceptions") + 4 * stat("def_sacks")
    score += 3 * stat("def_fumbles_forced") + 3 * stat("fumble_recovery_opp")
    score += 5 * (stat("rushing_yards") >= 100) + 5 * (stat("receiving_yards") >= 100) + 5 * (stat("passing_yards") >= 300)
    score += stat("def_pass_defended") + 0.5 * (stat("def_tackles_solo") + stat("def_tackle_assists"))
    score += (stat("passing_yards") + stat("rushing_yards") + stat("receiving_yards")) / 25
    return round(score, 2)


def rank(players):
    played = [p for p in players if p["availability"]["label"] == PLAYED]

    def key(player):
        snaps = sum(value or 0 for value in player["snaps"].values())
        return (-player["score"], -snaps, player["name"])

    return [p["id"] for p in sorted(played, key=key)]


# A defender's key moments start with what the defense did, not the tackles that end the offense's
# biggest gains: highest-ranked impact first, then the play that cost the offense the most.
DEFENSIVE_IMPACT = (
    ("Interception", ("interception_player_id", "lateral_interception_player_id")),
    ("Fumble recovery", ("fumble_recovery_1_player_id", "fumble_recovery_2_player_id")),
    ("Forced fumble", ("forced_fumble_player_1_player_id", "forced_fumble_player_2_player_id")),
    ("Safety", ("safety_player_id",)),
    ("Sack", ("sack_player_id", "half_sack_1_player_id", "half_sack_2_player_id")),
    ("Tackle for loss", ("tackle_for_loss_1_player_id", "tackle_for_loss_2_player_id")),
    ("Pass defended", ("pass_defense_1_player_id", "pass_defense_2_player_id")),
    ("QB hit", ("qb_hit_1_player_id", "qb_hit_2_player_id")),
)
TACKLE_ROLES = (
    "solo_tackle_1_player_id", "solo_tackle_2_player_id", "assist_tackle_1_player_id", "assist_tackle_2_player_id",
    "assist_tackle_3_player_id", "assist_tackle_4_player_id", "tackle_with_assist_1_player_id", "tackle_with_assist_2_player_id",
)


def _defensive_impact(play, pid):
    for rank_, (label, roles) in enumerate(DEFENSIVE_IMPACT):
        if any(play.get(role) == pid for role in roles):
            if label == "Fumble recovery" and play.get("fumble_lost") != "1":
                continue
            return rank_, label
    stopped = play.get("third_down_failed") == "1" or play.get("fourth_down_failed") == "1"
    if stopped and any(play.get(role) == pid for role in TACKLE_ROLES):
        return len(DEFENSIVE_IMPACT), "Stop"
    return None, None


def key_plays(plays, pid, team, limit=3):
    """Up to `limit` plays for one player, each tagged with the side of the ball and what happened.

    Defense: impact plays first (takeaways, sacks, tackles for loss, passes defended, QB hits, stops),
    then plays the defense won, then other tackles, each ordered by the offense's EPA (lowest first).
    Offense: the largest EPA swings, good or bad, as before.
    """
    chosen = []
    for play in plays:
        epa = num(play.get("epa"))
        if epa is None:
            continue
        if play.get("defteam") == team:
            rank_, impact = _defensive_impact(play, pid)
            tier = rank_ if rank_ is not None else len(DEFENSIVE_IMPACT) + (1 if epa < 0 else 2)
            chosen.append(((tier, epa), play, "defense", impact))
        else:
            impact = "Touchdown" if play.get("td_player_id") == pid else None
            chosen.append(((0, -abs(epa)), play, "offense", impact))
    chosen.sort(key=lambda item: item[0])
    return [
        {"play_id": play["play_id"], "quarter": quarter_label(play.get("qtr")), "clock": play.get("time", ""),
         "description": play["desc"], "epa": round(num(play["epa"]), 2), "side": side, "impact": impact,
         "offense": play.get("posteam", ""), "defense": play.get("defteam", "")}
        for _, play, side, impact in chosen[:limit]
    ]
