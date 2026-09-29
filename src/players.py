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
TACKLE_ROLES = ("solo_tackle_1", "solo_tackle_2", "assist_tackle_1", "assist_tackle_2",
                 "assist_tackle_3", "assist_tackle_4", "tackle_with_assist_1", "tackle_with_assist_2")


def group_of(position):
    return next((title for title, members in GROUPS if position in members), "Other")


def nickname(team_name):
    return team_name.split()[-1] if team_name else ""


def appearances(editions, pid):
    ordered = sorted(editions, key=lambda e: (e["season"], e["week"]))
    return [(e, p) for e in ordered for p in e["players"] if p["id"] == pid]


PHASE_ABBREVIATIONS = {"offense": "OFF", "defense": "DEF", "st": "ST"}


def snap_phases(player):
    """Every phase the player took a snap in, labeled like the card's snap line, with its share where the team total exists."""
    snaps = player.get("snaps") or {}
    phases = []
    for phase, team_key, _ in PHASES:
        count, team = snaps.get(phase), snaps.get(team_key)
        if count:
            phases.append({"abbr": PHASE_ABBREVIATIONS[phase], "count": count, "share": count / team if team else None})
    return phases


def snaps_text(phases):
    """'8 DEF (15%) · 11 ST (48%)'; a phase without a team total shows no share; '—' when none."""
    parts = [f"{ev.fmt(s['count'])} {s['abbr']}" + (f" ({round(100 * s['share'])}%)" if s["share"] is not None else "") for s in phases]
    return " · ".join(parts) if parts else "—"


def game_log(apps):
    rows = []
    for e, p in apps:
        phases = snap_phases(p)
        game = p.get("game") or {}
        rows.append({
            "edition_id": e["id"], "week": e["week"], "team": p["team"], "opponent": game.get("opponent", ""),
            "result": f"{game['result']} {game['team_score']}–{game['opp_score']}" if game else "",
            "status": p["availability"]["label"], "snaps": phases, "snaps_text": snaps_text(phases),
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


def _share_note(n, m):
    """Spec §6: a ratio-of-sums line notes when its own numerator/denominator pairing is only partly matched."""
    return f" (share based on {n} of {m} weeks)" if 0 < n < m else ""


def season_lines(apps, position):
    played = [(e, p) for e, p in apps if p["availability"]["label"] == ev.PLAYED]
    lines = [{"label": "Games", "text": f"Played in {_n(len(played), 'game', 'games')} of {len(apps)}."}]
    snap_parts = []
    for phase, team_key, word in PHASES:
        rows = [((p.get("snaps") or {}).get(phase), (p.get("snaps") or {}).get(team_key)) for _, p in apps]
        weeks_with_mine = [(m, t) for m, t in rows if m is not None]
        mine = _sum(m for m, _ in rows)
        if not mine:
            continue
        text = f"{mine} {word} snaps"
        matched = [(m, t) for m, t in weeks_with_mine if t is not None]
        if matched:
            share = _pct(sum(m for m, _ in matched), sum(t for _, t in matched))
            if share:
                text += f", {share} of the team's" + _share_note(len(matched), len(weeks_with_mine))
        snap_parts.append(text)
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
    """The rate's population is rows with a non-null `key`, not all rows: a missing EPA is not a zero."""
    values = [r[key] for r in rows if r.get(key) is not None]
    if len(values) < threshold:
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
    known = [q for q in targets if q.get("complete_pass") is not None]
    catches = sum(1 for q in known if q["complete_pass"] == 1)
    catch_note = f" (catches known for {len(known)} of {len(targets)} targets)" if 0 < len(known) < len(targets) else ""
    rate = _efficiency(carries, "epa", "carry", 30)
    return [{"label": "Carries", "text": f"{_n(len(carries), 'carry', 'carries')}{note}." + (f" {rate}" if rate else "")},
            {"label": "Receiving", "text": f"{_n(len(targets), 'target', 'targets')}, {_n(catches, 'catch', 'catches')}{catch_note}{note}."}]


def _receiver_lines(played, plays, plays_weeks, note):
    lines = []
    usage_weeks = [(e, p) for e, p in played if (p.get("usage") or {}).get("targets") is not None]
    if usage_weeks:
        usage = [p.get("usage") or {} for _, p in usage_weeks]
        targets = _sum(u.get("targets") for u in usage)
        text = f"{_n(targets, 'target', 'targets')}" + _based_on_note(len(usage_weeks), len(played))

        target_matched = [u for u in usage if u.get("team_targets") is not None]
        if target_matched:
            share = _pct(sum(u["targets"] for u in target_matched), sum(u["team_targets"] for u in target_matched))
            if share:
                text += f", {share} of team targets" + _share_note(len(target_matched), len(usage_weeks))

        air_weeks = [u for u in usage if u.get("air_yards") is not None]
        air_matched = [u for u in air_weeks if u.get("team_air_yards") is not None]
        if air_matched:
            share = _pct(sum(u["air_yards"] for u in air_matched), sum(u["team_air_yards"] for u in air_matched))
            if share:
                text += f"; {share} of team air yards" + _share_note(len(air_matched), len(air_weeks))

        lines.append({"label": "Targets", "text": text + "."})
    charted = [(p.get("charting") or {}).get("targets") for _, p in played]
    charted = [c for c in charted if c]
    if charted:
        text = f"{sum(c['catchable'] for c in charted)} of {sum(c['charted'] for c in charted)} catchable, {_n(sum(c['drops'] for c in charted), 'drop', 'drops')}"
        lines.append({"label": "Charted targets", "text": text + _based_on_note(len(charted), len(played)) + "."})
    if plays_weeks:
        targeted = [q for q in plays if "receiver" in q.get("roles", [])]
        values = [q["epa"] for q in targeted if q.get("epa") is not None]
        if len(values) >= 15:
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
        snaps = _sum((p.get("snaps") or {}).get("defense") for _, p in plays_weeks) or 0
        text = f"{_n(total, 'impact play', 'impact plays')}" + (f" ({', '.join(parts)})" if parts else "")
        if snaps >= 100:
            text += f"; {100 * total / snaps:.1f} per 100 defensive snaps"
        lines.append({"label": "Impact plays", "text": text + note + "."})
        tackles = sum(1 for q in plays if any(role in q.get("roles", []) for role in TACKLE_ROLES))
        lines.append({"label": "Tackles", "text": f"{_n(tackles, 'tackle', 'tackles')}{note}."})
    charting = [p.get("charting") or {} for _, p in played]
    cover = [c["coverage"] for c in charting if c.get("coverage")]
    if cover:
        text = f"Charted in coverage: {_n(sum(c['targets'] for c in cover), 'target', 'targets')}, {_n(sum(c['completions'] for c in cover), 'completion', 'completions')}, {_n(sum(c['yards'] for c in cover), 'yard', 'yards')}"
        lines.append({"label": "Coverage", "text": text + _based_on_note(len(cover), len(played)) + "."})
    rush = [c["pass_rush"] for c in charting if c.get("pass_rush")]
    if rush:
        text = f"{_n(sum(r['pressures'] for r in rush), 'pressure', 'pressures')}"
        lines.append({"label": "Pass rush", "text": text + _based_on_note(len(rush), len(played)) + "."})
    tackling = [c["tackling"] for c in charting if c.get("tackling")]
    if tackling:
        text = f"{sum(t['missed'] for t in tackling)} missed in {_n(sum(t['attempts'] for t in tackling), 'attempt', 'attempts')}"
        lines.append({"label": "Tackling", "text": text + _based_on_note(len(tackling), len(played)) + "."})
    return lines
