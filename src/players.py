"""Player pages: addresses, game logs and season lines. Pure functions over loaded editions."""
from __future__ import annotations

import re
import unicodedata

from . import evidence as ev

SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def slugify(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.replace(".", "").lower()).strip("-")


def assign_slugs(registry):
    """Copies of registry entries with `slug` set; a repeated slug gets the last four digits of the GSIS id."""
    taken, out = set(), []
    for alum in registry:
        slug = alum.get("slug") or slugify(alum["name"])
        if slug in taken:
            slug = f"{slug}-{alum['gsis_id'][-4:]}"
        taken.add(slug)
        out.append(dict(alum, slug=slug))
    return out


GROUPS = (
    ("Quarterbacks", {"QB"}), ("Running backs", {"RB", "FB"}), ("Receivers", {"WR", "TE"}),
    ("Offensive line", {"OT", "OG", "G", "T", "C", "OL"}), ("Defensive line", {"DT", "DE", "NT", "DL", "EDGE"}),
    ("Linebackers", {"LB", "ILB", "OLB", "MLB"}), ("Defensive backs", {"CB", "S", "SAF", "FS", "SS", "DB"}),
)
PHASES = (("offense", "team_offense", "offensive"), ("defense", "team_defense", "defensive"), ("st", "team_st", "special-teams"))
IMPACT_WORDS = {"Sack": ("sack", "sacks"), "Tackle for loss": ("tackle for loss", "tackles for loss"),
                "Interception": ("interception", "interceptions"), "Pass defended": ("pass defended", "passes defended"),
                "Forced fumble": ("forced fumble", "forced fumbles"), "Fumble recovery": ("fumble recovery", "fumble recoveries"),
                "QB hit": ("QB hit", "QB hits"), "3rd-down stop": ("3rd-down stop", "3rd-down stops"),
                "4th-down stop": ("4th-down stop", "4th-down stops"), "Safety": ("safety", "safeties")}


def group_of(position):
    return next((title for title, members in GROUPS if position in members), "Other")


def nickname(team_name):
    return team_name.split()[-1] if team_name else ""


def appearances(editions, pid):
    ordered = sorted(editions, key=lambda e: (e["season"], e["week"]))
    return [(e, p) for e in ordered for p in e["players"] if p["id"] == pid]


def _main_phase(player):
    snaps = player.get("snaps") or {}
    return max(PHASES, key=lambda ph: snaps.get(ph[0]) or 0)


def game_log(apps):
    rows = []
    for e, p in apps:
        phase, team_key, _ = _main_phase(p)
        snaps, team = (p.get("snaps") or {}).get(phase), (p.get("snaps") or {}).get(team_key)
        game = p.get("game") or {}
        rows.append({
            "edition_id": e["id"], "week": e["week"], "team": p["team"], "opponent": game.get("opponent", ""),
            "result": f"{game['result']} {game['team_score']}–{game['opp_score']}" if game else "",
            "status": p["availability"]["label"], "snaps": snaps,
            "snap_share": snaps / team if snaps and team else None,
            "contribution": "",
        })
    return rows


def _n(count, one, many):
    return f"{count} {one if count == 1 else many}"


def _sum(values):
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def _pct(part, whole):
    return f"{round(100 * part / whole)}%" if part is not None and whole else None


def _based_on_note(n, m):
    """Spec §9: note when a play- or usage-derived line only covers some of the played weeks."""
    return f" (based on {n} of {m} weeks)" if 0 < n < m else ""


def season_lines(apps, position):
    played = [(e, p) for e, p in apps if p["availability"]["label"] == ev.PLAYED]
    lines = [{"label": "Games", "text": f"Played in {_n(len(played), 'game', 'games')} of {len(apps)}."}]
    snap_parts = []
    for phase, team_key, word in PHASES:
        mine = _sum((p.get("snaps") or {}).get(phase) for _, p in apps)
        team = _sum((p.get("snaps") or {}).get(team_key) for _, p in apps if (p.get("snaps") or {}).get(phase))
        if mine:
            share = _pct(mine, team)
            snap_parts.append(f"{mine} {word} snaps" + (f", {share} of the team's" if share else ""))
    if snap_parts:
        lines.append({"label": "Snaps", "text": "; ".join(snap_parts) + "."})
    group = group_of(position)
    plays_weeks = [(e, p) for e, p in played if "plays" in p]
    plays = [q for _, p in plays_weeks for q in p.get("plays", [])]
    note = _based_on_note(len(plays_weeks), len(played))
    if group == "Quarterbacks":
        if plays_weeks:
            lines += _qb_lines(plays, note)
    elif group == "Running backs":
        if plays_weeks:
            lines += _rush_lines(plays, note)
    elif group == "Receivers":
        lines += _receiver_lines(played, plays, plays_weeks, note)
    elif group in ("Defensive line", "Linebackers", "Defensive backs"):
        lines += _defense_lines(played, plays, plays_weeks, note)
    return lines


def _efficiency(rows, key, noun, threshold):
    values = [r[key] for r in rows if r.get(key) is not None]
    if len(rows) < threshold or not values:
        return None
    success = sum(1 for v in values if v > 0)
    return f"Expected points per {noun} {sum(values) / len(values):+.2f}; success rate {round(100 * success / len(values))}%."


def _qb_lines(plays, note):
    drops = [q for q in plays if "passer" in q.get("roles", []) and q.get("qb_dropback") == 1 and q.get("qb_kneel") != 1 and q.get("qb_spike") != 1]
    eff = _efficiency(drops, "qb_epa", "dropback", 50)
    lines = [{"label": "Dropbacks", "text": f"{_n(len(drops), 'dropback', 'dropbacks')}{note}." + (f" {eff}" if eff else "")}]
    with_cp = [q for q in drops if q.get("cp") is not None and q.get("complete_pass") is not None]
    if len(with_cp) >= 50:
        cpoe = 100 * sum(q["complete_pass"] - q["cp"] for q in with_cp) / len(with_cp)
        lines.append({"label": "Completion over expected", "text": f"{cpoe:+.1f} percentage points on {len(with_cp)} throws{note}."})
    return lines


def _rush_lines(plays, note):
    carries = [q for q in plays if "rusher" in q.get("roles", []) and q.get("rush_attempt") == 1]
    targets = [q for q in plays if "receiver" in q.get("roles", [])]
    catches = sum(1 for q in targets if q.get("complete_pass") == 1)
    rate = _efficiency(carries, "epa", "carry", 30)
    return [{"label": "Carries", "text": f"{_n(len(carries), 'carry', 'carries')}{note}." + (f" {rate}" if rate else "")},
            {"label": "Receiving", "text": f"{_n(len(targets), 'target', 'targets')}, {_n(catches, 'catch', 'catches')}{note}."}]


def _receiver_lines(played, plays, plays_weeks, note):
    lines = []
    usage_weeks = [(e, p) for e, p in played if (p.get("usage") or {}).get("targets") is not None]
    if usage_weeks:
        usage = [p.get("usage") or {} for _, p in usage_weeks]
        targets = _sum(u.get("targets") for u in usage)
        team_targets = _sum(u.get("team_targets") for u in usage if u.get("team_targets"))
        air = _sum(u.get("air_yards") for u in usage)
        team_air = _sum(u.get("team_air_yards") for u in usage if u.get("team_air_yards"))
        usage_note = _based_on_note(len(usage_weeks), len(played))
        text = f"{_n(targets, 'target', 'targets')}"
        if targets and team_targets:
            text += f", {_pct(targets, team_targets)} of team targets"
        if air is not None and team_air:
            text += f"; {_pct(air, team_air)} of team air yards"
        lines.append({"label": "Targets", "text": text + usage_note + "."})
    charted = [(p.get("charting") or {}).get("targets") for _, p in played]
    charted = [c for c in charted if c]
    if charted:
        lines.append({"label": "Charted targets", "text": f"{sum(c['catchable'] for c in charted)} of {sum(c['charted'] for c in charted)} catchable, {_n(sum(c['drops'] for c in charted), 'drop', 'drops')}."})
    if plays_weeks:
        targeted = [q for q in plays if "receiver" in q.get("roles", [])]
        if len(targeted) >= 15:
            values = [q["epa"] for q in targeted if q.get("epa") is not None]
            if values:
                lines.append({"label": "When targeted", "text": f"Team expected points when targeted {sum(values) / len(values):+.2f} per target{note}."})
    return lines


def _defense_lines(played, plays, plays_weeks, note):
    lines = []
    if plays_weeks:
        counts = {}
        for q in plays:
            if q.get("side") == "defense" and q.get("impact"):
                counts[q["impact"]] = counts.get(q["impact"], 0) + 1
        total = sum(counts.values())
        parts = [_n(n, *IMPACT_WORDS.get(kind, (kind.lower(), kind.lower()))) for kind, n in sorted(counts.items(), key=lambda kv: -kv[1])]
        snaps = _sum((p.get("snaps") or {}).get("defense") for _, p in played) or 0
        text = f"{_n(total, 'impact play', 'impact plays')}" + (f" ({', '.join(parts)})" if parts else "")
        if snaps >= 100:
            text += f"; {100 * total / snaps:.1f} per 100 defensive snaps"
        lines.append({"label": "Impact plays", "text": text + note + "."})
    charting = [p.get("charting") or {} for _, p in played]
    cover = [c["coverage"] for c in charting if c.get("coverage")]
    if cover:
        lines.append({"label": "Coverage", "text": f"Charted in coverage: {_n(sum(c['targets'] for c in cover), 'target', 'targets')}, {_n(sum(c['completions'] for c in cover), 'completion', 'completions')}, {_n(sum(c['yards'] for c in cover), 'yard', 'yards')}."})
    rush = [c["pass_rush"] for c in charting if c.get("pass_rush")]
    if rush:
        lines.append({"label": "Pass rush", "text": f"{_n(sum(r['pressures'] for r in rush), 'pressure', 'pressures')}."})
    tackling = [c["tackling"] for c in charting if c.get("tackling")]
    if tackling:
        lines.append({"label": "Tackling", "text": f"{sum(t['missed'] for t in tackling)} missed in {_n(sum(t['attempts'] for t in tackling), 'attempt', 'attempts')}."})
    return lines
