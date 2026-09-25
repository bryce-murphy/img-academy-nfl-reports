"""Conservative player-level reporting and HTML/Quarto rendering."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

from .data import DataError, load_sources, utcnow

ROOT = Path(__file__).resolve().parents[1]
IMAGE_HOSTS = {"a.espncdn.com", "static.www.nfl.com", "static.clubs.nfl.com", "static.nfl.com"}
ROSTER_LABELS = {"ACT": "Active roster", "INA": "Inactive roster designation", "RES": "Reserve list", "DEV": "Practice squad", "CUT": "Released"}
POSITIONS = {
    "QB": [("passing_yards", "pass yards"), ("passing_tds", "pass TD"), ("passing_interceptions", "INT"), ("rushing_yards", "rush yards")],
    "WR": [("receiving_yards", "receiving yards"), ("receptions", "catches"), ("targets", "targets"), ("receiving_tds", "TD")],
    "TE": [("receiving_yards", "receiving yards"), ("receptions", "catches"), ("targets", "targets"), ("receiving_tds", "TD")],
    "RB": [("rushing_yards", "rush yards"), ("carries", "carries"), ("rushing_tds", "rush TD"), ("receiving_yards", "receiving yards")],
}
DEFENSE = [("def_tackles_solo", "solo tackles"), ("def_tackle_assists", "assists"), ("def_sacks", "sacks"), ("def_pass_defended", "passes defended")]
OL = {"OL", "OT", "OG", "C", "G", "T"}


def num(value):
    if value in (None, "", "NA", "NaN"):
        return None
    parsed = float(value)
    if not math.isfinite(parsed):
        raise DataError("Non-finite statistic")
    return parsed


def fmt(value):
    value = num(value)
    return "—" if value is None else f"{value:g}"


def unique(rows, label):
    if len(rows) > 1:
        raise DataError(f"Ambiguous {label}; review the identity/game mapping")
    return rows[0] if rows else {}


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
        raise DataError("This NFL week still has scheduled games")
    if scheduled and not (0 < (asof - last_day).days <= 7):
        return None, []
    if any(num(g["home_score"]) is None or num(g["away_score"]) is None for g in games):
        raise DataError("Scores are missing; do not reuse the preceding week's report")
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
            raise DataError(f"No end-of-game evidence for {game['game_id']}")
        end = ends[-1]
        for side in ("home", "away"):
            if num(end.get(f"total_{side}_score")) != num(game[f"{side}_score"]):
                raise DataError(f"Final score disagreement for {game['game_id']}")
    return by_game


def participation(snap, plays, stats):
    counts = [num(snap.get(k)) for k in ("offense_snaps", "defense_snaps", "st_snaps")]
    if any(v is not None and v < 0 for v in counts):
        raise DataError("Negative snap count")
    # Positive snaps include special teams. A zero-stat row is not proof of a DNP.
    if any(v is not None and v > 0 for v in counts):
        return "Played", "Positive snap count"
    if plays:
        if snap and all(v == 0 for v in counts):
            return "Conflicting evidence", "Recorded play involvement conflicts with zero snaps"
        return "Played", "Player ID appears in a recorded football play"
    activity = ("attempts", "carries", "receptions", "def_tackles_solo", "def_tackle_assists", "def_sacks", "def_interceptions", "fg_att", "pat_att", "pt_att", "kickoff_returns", "punt_returns")
    if any((num(stats.get(k)) or 0) > 0 for k in activity):
        if snap and all(v == 0 for v in counts):
            return "Conflicting evidence", "Box-score activity conflicts with zero snaps"
        return "Played", "Positive recorded game statistic"
    if snap and all(v == 0 for v in counts):
        return "No snaps recorded", "Reason not established by snap counts"
    return "Participation unverified", "Missing evidence is not evidence of a DNP"


def validate_offense(stats, plays, gsis_id):
    checks = [("passing_yards", "passer_player_id"), ("rushing_yards", "rusher_player_id"), ("receiving_yards", "receiver_player_id")]
    for metric, role in checks:
        expected = num(stats.get(metric))
        if expected is None:
            continue
        observed = sum(num(p.get(metric)) or 0 for p in plays if p.get(role) == gsis_id and p.get("play_type") != "no_play")
        if abs(expected - observed) > .01:
            raise DataError(f"Player stats disagree with play-by-play: {gsis_id}, {metric}")


def build_records(data, registry, games, season, week):
    by_game = validate_games(games, data["pbp"])
    people = {p["gsis_id"]: p for p in data["players"] if p["gsis_id"]}
    teams = {t["team_abbr"]: t for t in data["teams"]}
    records = []
    for alum in registry:
        pid = alum["gsis_id"]
        person = people.get(pid, {})
        roster = unique([r for r in data["rosters"] if r["gsis_id"] == pid and int(r["season"]) == season and int(r["week"]) == week], alum["name"] + " weekly roster")
        current = unique([r for r in data["current_rosters"] if r["gsis_id"] == pid], alum["name"] + " current roster")
        stat_rows = [r for r in data["stats"] if r["player_id"] == pid and int(r["season"]) == season and int(r["week"]) == week and r["season_type"] in {g["game_type"] for g in games}]
        stat = unique(stat_rows, alum["name"] + " statistics")
        team = stat.get("team") or roster.get("team", "")
        game = unique([g for g in games if team in {g["home_team"], g["away_team"]}], "team schedule")
        if stat and (not game or stat["game_id"] != game["game_id"]):
            raise DataError(f"Game/team identity mismatch for {alum['name']}")
        plays = by_game.get(game.get("game_id"), [])
        # Only actual participation roles, excluding penalty-only mentions and names in descriptions.
        role_fields = [k for k in (plays[0] if plays else {}) if k.endswith("_player_id") and not k.startswith(("penalty", "fantasy", "name"))]
        involvement = [p for p in plays if p.get("play_type") not in {"", "no_play"} and any(p.get(k) == pid for k in role_fields)]
        pfr = alum.get("pfr_id") or person.get("pfr_id") or roster.get("pfr_id")
        snap = unique([s for s in data["snaps"] if pfr and s["pfr_player_id"] == pfr and s["game_id"] == game.get("game_id")], "snap count")
        if snap and snap["team"] != team:
            raise DataError("Snap count team does not match the game roster")
        injury = unique([r for r in data["injuries"] if r["gsis_id"] == pid and int(r["season"]) == season and int(r["week"]) == week and r["team"] == team], "injury report")
        status, evidence = participation(snap, involvement, stat)
        if not game:
            status, evidence = ("Bye / no game this week", "No game on this week's schedule") if roster else ("No weekly roster record", "Current roster is shown separately")
        validate_offense(stat, plays, pid)
        pos = person.get("position") or roster.get("position") or current.get("position", "")
        if pos in OL or roster.get("position") == "OL":
            metrics = [("offense_snaps", "offensive snaps"), ("st_snaps", "special-teams snaps")]
            metrics = [{"label": label, "value": fmt(snap.get(key))} for key, label in metrics]
        else:
            metrics = [{"label": label, "value": fmt(stat.get(key))} for key, label in POSITIONS.get(pos, DEFENSE)]
        highlights = sorted([p for p in involvement if num(p.get("epa")) is not None], key=lambda p: abs(num(p["epa"])), reverse=True)[:3]
        record = {"id": pid, "name": alum["name"], "position": pos, "team": team, "team_name": teams.get(team, {}).get("team_name", team),
                  "team_color": teams.get(team, {}).get("team_color", "#123d35"),
                  "logo": teams.get(team, {}).get("team_logo_espn", ""), "headshot": roster.get("headshot_url") or person.get("headshot", ""),
                  "college": person.get("college_name", ""), "draft_year": person.get("draft_year", ""), "draft_round": person.get("draft_round", ""),
                  "status": status, "evidence": evidence, "weekly_roster_status": roster.get("status", ""), "current_team": current.get("team", ""), "current_status": current.get("status", ""),
                  "injury_designation": injury.get("report_status", ""), "reported_injury": injury.get("report_primary_injury", ""),
                  "practice_status": injury.get("practice_status", ""), "metrics": metrics, "snap_counts": {k: snap.get(k, "") for k in ("offense_snaps", "defense_snaps", "st_snaps")},
                  "game": game, "stats": stat, "alumni_source": alum["source_url"],
                  "plays": [{"description": p["desc"], "epa": fmt(p["epa"]), "wpa": fmt(p.get("wpa")), "play_id": p["play_id"], "quarter": p.get("qtr", ""), "clock": p.get("time", "")} for p in highlights]}
        record["next_gen"] = []
        ngs_fields = {"ngs_passing": [("avg_time_to_throw", "Time to throw", "s"), ("completion_percentage_above_expectation", "Completion above expectation", "percentage points")],
                      "ngs_receiving": [("avg_separation", "Average separation", "yards"), ("avg_yac_above_expectation", "YAC above expectation per catch", "yards")],
                      "ngs_rushing": [("rush_yards_over_expected", "Rushing yards over expected", "yards"), ("rush_yards_over_expected_per_att", "RYOE per carry", "yards")]}
        for source, fields in ngs_fields.items():
            ngs = unique([r for r in data.get(source, []) if r["player_gsis_id"] == pid and int(r["season"]) == season and int(r["week"]) == week and r["team_abbr"] == team and r.get("season_type") == game.get("game_type")], "Next Gen Stats")
            for key, label, unit in fields:
                value = num(ngs.get(key))
                if value is not None:
                    record["next_gen"].append({"label": label, "value": round(value, 2), "unit": unit, "source": source})
        records.append(record)
    return records


def safe_image(url, alt, css):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in IMAGE_HOSTS:
        return ""
    return f'<img class="{css}" src="{html.escape(url, quote=True)}" alt="{html.escape(alt, quote=True)}" loading="lazy" referrerpolicy="no-referrer">'


def score_line(record):
    g = record["game"]
    if not g:
        return "No game in this reporting window"
    return f"{g['away_team']} {fmt(g['away_score'])} · {g['home_team']} {fmt(g['home_score'])} — Final"


def card(record):
    e = html.escape
    metrics = "".join(f'<div><strong>{e(m["value"])}</strong><span>{e(m["label"])}</span></div>' for m in record["metrics"])
    injury = ""
    if record["injury_designation"] or record["reported_injury"]:
        designation = record["injury_designation"] or "No game designation supplied"
        injury = f'<p class="availability">Week-specific injury report: {e(designation)} · {e(record["reported_injury"] or "reason not supplied")}. This is a pregame report, not a diagnosis or proof of absence.</p>'
    plays = "".join(f'<li><span class="play-meta">Q{e(p["quarter"])} · {e(p["clock"])} · Play {e(p["play_id"])} · EPA {e(p["epa"])}</span>{e(p["description"])}</li>' for p in record["plays"])
    play_section = f'<details><summary>Key moments · {len(record["plays"])}</summary><ol class="plays">{plays}</ol><p class="caption">Selected by absolute play EPA. EPA belongs to the offensive team on the play; it is not an individual player grade. Negative EPA can favor a defender.</p></details>' if plays else '<p class="caption">No attributable play highlights available. Offensive-line coverage uses snaps; no blocking grade is inferred.</p>'
    badge = "played" if record["status"] == "Played" else "pending"
    context = " · ".join(x for x in [record["college"], f'{record["draft_year"]} draft, round {record["draft_round"]}' if record["draft_year"] else ""] if x)
    advanced = ''.join(f'<li>{e(m["label"])}: <strong>{m["value"]} {e(m["unit"])}</strong></li>' for m in record.get('next_gen', []))
    advanced = f'<div class="advanced"><p class="eyebrow">NEXT GEN STATS</p><ul>{advanced}</ul></div>' if advanced else ''
    color = record.get('team_color', '#123d35')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        color = '#123d35'
    initials = ''.join(part[0] for part in record['name'].split()[:2])
    portrait = f'<div class="player-monogram" style="border-color:{color}" aria-label="{e(record["name"])} player monogram">{e(initials)}</div>'
    logo = ''
    if record.get('display_third_party_images', False):
        portrait = safe_image(record['headshot'], record['name'], 'headshot') or portrait
        logo = safe_image(record['logo'], record['team_name'] + ' logo', 'team-logo')
    return f'''<article class="player-card" id="player-{e(record['id'])}">
<div class="player-top"><div>{logo}<span class="eyebrow">{e(record['team'] or 'Roster watch')} / {e(record['position'])}</span><h2>{e(record['name'])}</h2><p class="context">{e(context)}</p></div>{portrait}</div>
<p class="score">{e(score_line(record))}</p><span class="badge {badge}">{e(record['status'])}</span><span class="evidence">{e(record['evidence'])}</span>
<div class="metrics">{metrics}</div><p class="caption">Snaps: offense {fmt(record['snap_counts']['offense_snaps'])} / defense {fmt(record['snap_counts']['defense_snaps'])} / special teams {fmt(record['snap_counts']['st_snaps'])}. — means unavailable.</p>
{injury}{advanced}{play_section}<footer>Current roster: {e(record['current_team'] or 'Not found')} · {e(ROSTER_LABELS.get(record['current_status'], record['current_status'] or 'Unverified'))}. <a href="{e(record['alumni_source'], quote=True)}">IMG affiliation source</a></footer></article>'''


def content(report):
    e = html.escape
    records = report["players"]
    played = sum(p["status"] == "Played" for p in records)
    uncertain = sum(p["status"] in {"Participation unverified", "Conflicting evidence"} for p in records)
    stars = sorted(records, key=lambda p: (-(num(p["stats"].get("passing_yards")) or num(p["stats"].get("receiving_yards")) or num(p["stats"].get("rushing_yards")) or 0), p["name"]))
    sources = "".join(f'<tr><td><a href="{e(v["url"])}">{e(k)}</a></td><td>{e(v["updated_at"])}</td><td>{v["rows"]:,}</td></tr>' for k, v in report["sources"].items())
    warnings = "".join(f'<li>{e(w)}</li>' for w in report["warnings"])
    return f'''<header class="masthead"><a href="../../index.html">IMG TO THE NFL</a><span>Independent coverage by Bryce Murphy</span></header>
<section class="lead"><p class="eyebrow">THE ALUMNI REPORT / {report['season']} / WEEK {report['week']:02d}</p><h1>From Bradenton.<br>To the big stage.</h1><p class="dek">IMG football alumni, their contributions, and a closer look at the week that was.</p><div class="edition"><span>{played} confirmed participants</span><span>{len(records)} players followed</span><span>{uncertain} awaiting participation evidence</span></div></section>
<aside class="report-note">{e(report['label'])} · Retrieved {e(report['generated_at'])}. Stats can be corrected after publication. Players on practice squads or reserve lists remain visible in roster watch.</aside>
<div class="player-grid">{''.join(card(p) for p in stars)}</div>
<section class="method"><h2>Trust the story. Check the evidence.</h2><p>Final scores agree between schedule and play-by-play. Passing, rushing, and receiving yards are reconciled with recorded plays. These are consistency checks within nflverse, not an independent official-box-score audit. Snap counts provide a separate participation signal when available. No injury, illness, or benching reason is inferred from missing statistics.</p><p>Registry: verified IMG football affiliations from the NFL's 2025 kickoff list, 2026 draft reporting and historical alumni. Transfers, reserve statuses, and practice squads are retained. The registry requires a new review each season and can receive sourced corrections throughout the year.</p><ul>{warnings}</ul><table><thead><tr><th>Source</th><th>Upstream update (UTC)</th><th>Rows</th></tr></thead><tbody>{sources}</tbody></table><p><a href="report.json">Report data and source checksums</a> · <a href="social-drafts.json">Social drafts</a></p><p class="caption">Data: nflverse, CC BY 4.0; snap counts originate with PFR. Third-party logos and headshots are disabled pending rights clearance. Original monograms and team-color accents identify players. This independent portfolio project is not endorsed by IMG Academy, the NFL, its teams, or its players.</p></section>'''


def write_report(report, directory):
    directory.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    report["content_sha256"] = hashlib.sha256(serialized.encode()).hexdigest()
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    body = content(report)
    css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
    (directory / "index.html").write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="IMG Academy alumni in the NFL: weekly performance, participation evidence, and key plays."><title>IMG to the NFL · {report["season"]} Week {report["week"]}</title><style>{css}</style></head><body><main>{body}</main></body></html>', encoding="utf-8")
    # Raw HTML remains escaped before insertion into either HTML or Quarto.
    (directory / "index.qmd").write_text(f'---\ntitle: "{report["season"]} · Week {report["week"]}"\nformat: html\n---\n\n```{{=html}}\n{body}\n```\n', encoding="utf-8")
    cfg = json.loads((ROOT / "config.json").read_text())
    url = cfg["site_url"] + f'reports/{report["season"]}-week-{report["week"]:02d}/'
    leaders = [p for p in report["players"] if p["status"] == "Played" and p["position"] in POSITIONS]
    lines = [f'{p["name"]}: ' + ', '.join(m["value"] + ' ' + m["label"] for m in p["metrics"][:3]) for p in leaders]
    drafts = {"state": "draft", "period": f'{report["season"]}-{report["week"]}', "report_hash": report["content_sha256"], "url": url,
              "linkedin": f'From Bradenton to the NFL: Week {report["week"]}.\n\n' + '\n'.join(lines) + '\n\nThe full IMG football alumni report includes participation evidence, team results and key plays. Missing information is labeled, not guessed.\n\n' + url,
              "x": f'IMG to the NFL | Week {report["week"]}\nPerformance, participation and the plays that mattered for IMG football alumni. Explore the full report: {url}',
              "requires": ["Confirm the public report URL is live", "Connect personal accounts through OAuth", "Review image reuse and credits", "Approve initial report quality before enabling cron"]}
    (directory / "social-drafts.json").write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int)
    parser.add_argument("--week", type=int)
    parser.add_argument("--scheduled", action="store_true")
    parser.add_argument("--historical", action="store_true", help="Disable freshness cutoff; still verify game and identity checks")
    parser.add_argument("--refresh-roster", action="store_true")
    args = parser.parse_args()
    cfg = json.loads((ROOT / "config.json").read_text())
    if args.scheduled and not cfg["scheduled_reports_enabled"]:
        print("Scheduled reports are disabled. Manual runs are available.")
        return
    today = utcnow().date()
    season = args.season or (today.year if today.month >= 3 else today.year - 1)
    if not 1999 <= season <= today.year:
        raise DataError("Invalid season")
    if args.scheduled and cfg["registry_reviewed_season"] != season:
        raise DataError("Annual alumni review is required before scheduled reports")
    registry = json.loads((ROOT / "data" / "alumni.json").read_text())
    ids = [a["gsis_id"] for a in registry]
    if len(ids) != len(set(ids)) or not all(re.fullmatch(r"00-\d{7}", i) for i in ids):
        raise DataError("Invalid or duplicate alumni IDs")
    data, manifest, warnings = load_sources(season, ROOT / ".cache", cfg["max_source_age_hours"], args.historical, only={"current_rosters"} if args.refresh_roster else None)
    if args.refresh_roster:
        snapshot = [{"name": a["name"], "gsis_id": a["gsis_id"], "roster": [r for r in data["current_rosters"] if r["gsis_id"] == a["gsis_id"]]} for a in registry]
        target = ROOT / "build"
        target.mkdir(exist_ok=True)
        (target / "roster-review.json").write_text(json.dumps({"season": season, "fetched_at": utcnow().isoformat(), "players": snapshot}, indent=2), encoding="utf-8")
        print("Roster review saved; new alumni require sourced registry entries.")
        return
    week, games = choose_week(data["schedule"], season, today, cfg["season_types"], args.week, args.scheduled)
    if week is None:
        print("Outside a completed NFL reporting week; skipped.")
        return
    records = build_records(data, registry, games, season, week)
    for record in records:
        record['display_third_party_images'] = cfg['display_third_party_images']
    if any(r["status"] == "Conflicting evidence" for r in records):
        warnings.append("Conflicting participation evidence: social publication must be withheld")
    report = {"season": season, "week": week, "generated_at": utcnow().isoformat(), "label": "Historical replay" if args.historical else "Verified source snapshot",
              "players": records, "sources": manifest, "warnings": warnings, "publication_ready": not warnings and all(r["status"] != "Conflicting evidence" for r in records)}
    directory = ROOT / "site" / "reports" / f"{season}-week-{week:02d}"
    write_report(report, directory)
    (ROOT / "site" / "latest.json").write_text(json.dumps({"season": season, "week": week, "path": str(directory.relative_to(ROOT / 'site')).replace('\\', '/')}), encoding="utf-8")
    print(f"Built {season} week {week}: {len(records)} alumni; {sum(p['status'] == 'Played' for p in records)} confirmed participants. Social drafts only.")


if __name__ == "__main__":
    main()
