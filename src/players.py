"""Player pages: addresses, game logs and season lines. Pure functions over loaded editions."""
from __future__ import annotations

import re
import unicodedata

from . import evidence as ev
from . import statlines

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


MINIMUM = {"dropbacks": 50, "throws": 50, "carries": 30, "targets": 15, "snaps": 100}
DEFINITIONS = {
    "snap_share": "His snaps divided by the team's in that phase, in weeks where both are known.",
    "epa_dropback": "Average change in the offense's expected points on his dropbacks (passes, sacks and scrambles). It describes the whole play, not one player.",
    "success_dropback": "Share of his dropbacks with positive expected points added: plays that left the offense better placed to score.",
    "cpoe": "His completion rate minus the rate nflverse's completion-probability model expected for the same throws.",
    "epa_carry": "Average change in the offense's expected points on his carries. It describes the whole play, not one player.",
    "success_carry": "Share of his carries with positive expected points added.",
    "target_share": "His targets divided by the team's, in weeks where both are known.",
    "air_share": "His air yards (how far passes to him traveled past the line of scrimmage) divided by the team's.",
    "epa_target": "Average change in the offense's expected points on throws to him, caught or not. It describes the whole play, not one player.",
    "impact_rate": "Impact plays (sacks, takeaways, passes defended, tackles for loss, QB hits, safeties and 3rd- or 4th-down stops) for every 100 defensive snaps.",
}


def _row(label, value, sample, definition):
    return {"label": label, "value": value, "sample": sample, "definition": DEFINITIONS[definition]}


def _short(label, count, unit, definition):
    """A rate below its minimum sample: shown as a dash with the count it has, never as a noisy number."""
    return _row(label, "—", f"{count} {unit} (shown from {MINIMUM[unit]})", definition)


def _signed(value, digits=2):
    return f"{round(value, digits) + 0.0:+.{digits}f}".replace("-", "−")


def _thrown_to(count):
    return "Thrown to once" if count == 1 else f"Thrown to {count} times"


def season_lines(apps, position):
    """Plain-language season sentences."""
    return season(apps, position)[0]


def season_numbers(apps, position):
    """The same season's rates in their analytics terms, for the "By the numbers" table."""
    return season(apps, position)[1]


def season(apps, position):
    """(lines, rows): the sentences and the table come from one computation, so they cannot disagree."""
    played = [(e, p) for e, p in apps if p["availability"]["label"] == ev.PLAYED]
    if played:
        games = f"Played in {_n(len(played), 'game', 'games')} of {len(apps)}."
    else:
        games = f"No games played yet ({_n(len(apps), 'week', 'weeks')})."
    lines, rows = [{"label": "Games", "text": games}], []
    snap_parts = []
    for phase, team_key, word in PHASES:
        pairs = [((p.get("snaps") or {}).get(phase), (p.get("snaps") or {}).get(team_key)) for _, p in apps]
        weeks_with_mine = [(m, t) for m, t in pairs if m is not None]
        mine = _sum(m for m, _ in pairs)
        if not mine:
            continue
        text = f"{mine} {word} snaps"
        matched = [(m, t) for m, t in weeks_with_mine if t is not None]
        if matched:
            mine_matched, team_matched = sum(m for m, _ in matched), sum(t for _, t in matched)
            share = _pct(mine_matched, team_matched)
            if share:
                text += f", {share} of the team's" + _share_note(len(matched), len(weeks_with_mine))
                rows.append(_row(f"{word.capitalize()} snap share", share, f"{mine_matched} of {team_matched} snaps", "snap_share"))
        snap_parts.append(text)
    if snap_parts:
        lines.append({"label": "Snaps", "text": "; ".join(snap_parts) + "."})
    group = group_of(position)
    plays_weeks = [(e, p) for e, p in played if "plays" in p]
    plays = [q for _, p in plays_weeks for q in p.get("plays", [])]
    note = _based_on_note(len(plays_weeks), len(played))
    more = ([], [])
    if group == "Quarterbacks":
        if plays_weeks:
            more = _qb_lines(plays, note)
    elif group == "Running backs":
        if plays_weeks:
            more = _rush_lines(plays, note)
    elif group == "Receivers":
        more = _receiver_lines(played, plays, plays_weeks, note)
    elif group in ("Defensive line", "Linebackers", "Defensive backs"):
        more = _defense_lines(played, plays, plays_weeks, note)
    return lines + more[0], rows + more[1]


def _efficiency(rows, key):
    """(count, mean, success %) over rows with a non-null `key`: a missing EPA is not a zero."""
    values = [r[key] for r in rows if r.get(key) is not None]
    if not values:
        return 0, None, None
    return len(values), sum(values) / len(values), 100 * sum(1 for v in values if v > 0) / len(values)


def _epa_words(mean, success):
    change = round(mean, 2)
    each = f"On average each {'added' if change > 0 else 'cost'} {abs(change):.2f} expected points" if change else "On average each left expected points about even"
    return f"{each}, and {round(success)}% left the offense better placed to score"


def _efficiency_rows(n, mean, success, unit, epa_label, kind):
    if n < MINIMUM[unit]:
        return [_short(epa_label, n, unit, f"epa_{kind}"), _short("Success rate", n, unit, f"success_{kind}")]
    return [_row(epa_label, _signed(mean), f"{n} {unit}", f"epa_{kind}"), _row("Success rate", f"{round(success)}%", f"{n} {unit}", f"success_{kind}")]


def _qb_lines(plays, note):
    drops = [q for q in plays if "passer" in q.get("roles", []) and q.get("qb_dropback") == 1 and q.get("qb_kneel") != 1 and q.get("qb_spike") != 1]
    n, mean, success = _efficiency(drops, "qb_epa")
    text = f"{_n(len(drops), 'dropback', 'dropbacks')}{note}." + (f" {_epa_words(mean, success)}." if n >= MINIMUM["dropbacks"] else "")
    lines = [{"label": "Dropbacks", "text": text}]
    rows = _efficiency_rows(n, mean, success, "dropbacks", "EPA per dropback", "dropback")
    with_cp = [q for q in drops if q.get("cp") is not None and q.get("complete_pass") is not None]
    if len(with_cp) >= MINIMUM["throws"]:
        cpoe = round(100 * sum(q["complete_pass"] - q["cp"] for q in with_cp) / len(with_cp), 1) + 0.0
        words = f"Completed passes at a rate {abs(cpoe):.1f} percentage points {'above' if cpoe > 0 else 'below'} expected" if cpoe else "Completed passes at the expected rate"
        lines.append({"label": "Completion over expected", "text": f"{words}, on {len(with_cp)} throws{note}."})
        rows.append(_row("Completion % over expected", f"{_signed(cpoe, 1)} pts", f"{len(with_cp)} throws", "cpoe"))
    else:
        rows.append(_short("Completion % over expected", len(with_cp), "throws", "cpoe"))
    return lines, rows


def _rush_lines(plays, note):
    carries = [q for q in plays if "rusher" in q.get("roles", []) and q.get("rush_attempt") == 1]
    n, mean, success = _efficiency(carries, "epa")
    text = f"{_n(len(carries), 'carry', 'carries')}{note}." + (f" {_epa_words(mean, success)}." if n >= MINIMUM["carries"] else "")
    targets = [q for q in plays if "receiver" in q.get("roles", [])]
    known = [q for q in targets if q.get("complete_pass") is not None]
    catches = sum(1 for q in known if q["complete_pass"] == 1)
    if not targets:
        receiving = "No passes thrown his way"
    elif len(known) < len(targets):
        receiving = f"{_thrown_to(len(targets))}; caught {catches} of the {len(known)} with a known result"
    elif len(targets) == 1:
        receiving = f"{'Caught' if catches else 'Did not catch'} the 1 pass thrown his way"
    else:
        receiving = f"Caught {catches} of the {len(targets)} passes thrown his way"
    lines = [{"label": "Carries", "text": text}, {"label": "Receiving", "text": receiving + note + "."}]
    return lines, _efficiency_rows(n, mean, success, "carries", "EPA per carry", "carry")


def _receiver_lines(played, plays, plays_weeks, note):
    lines, rows = [], []
    usage_weeks = [(e, p) for e, p in played if (p.get("usage") or {}).get("targets") is not None]
    if usage_weeks:
        usage = [p.get("usage") or {} for _, p in usage_weeks]
        targets = _sum(u.get("targets") for u in usage)
        text = _thrown_to(targets) + _based_on_note(len(usage_weeks), len(played))
        target_matched = [u for u in usage if u.get("team_targets") is not None]
        if target_matched:
            mine, team = sum(u["targets"] for u in target_matched), sum(u["team_targets"] for u in target_matched)
            share = _pct(mine, team)
            if share:
                text += f", {share} of the team's targets" + _share_note(len(target_matched), len(usage_weeks))
                rows.append(_row("Target share", share, f"{mine} of {team} targets", "target_share"))
        text += "."
        air_weeks = [u for u in usage if u.get("air_yards") is not None]
        air_matched = [u for u in air_weeks if u.get("team_air_yards") is not None]
        if air_matched:
            mine, team = sum(u["air_yards"] for u in air_matched), sum(u["team_air_yards"] for u in air_matched)
            share = _pct(mine, team)
            if share:
                text += f" Those passes covered {share} of the distance the team threw downfield" + _share_note(len(air_matched), len(air_weeks)) + "."
                rows.append(_row("Air-yards share", share, f"{ev.fmt(mine)} of {ev.fmt(team)} air yards", "air_share"))
        lines.append({"label": "Targets", "text": text})
    charted = [(p.get("charting") or {}).get("targets") for _, p in played]
    charted = [c for c in charted if c]
    if charted:
        total = {key: sum(c[key] for c in charted) for key in ("charted", "catchable", "drops")}
        lines.append({"label": "Pass catching", "text": statlines.sentence(statlines.targets(total), _based_on_note(len(charted), len(played)))})
    if plays_weeks:
        targeted = [q for q in plays if "receiver" in q.get("roles", [])]
        values = [q["epa"] for q in targeted if q.get("epa") is not None]
        if len(values) >= MINIMUM["targets"]:
            mean = round(sum(values) / len(values), 2) + 0.0
            words = f"Throws his way {'added' if mean > 0 else 'cost'} {abs(mean):.2f} expected points each, on average" if mean else "Throws his way left expected points about even, on average"
            lines.append({"label": "When targeted", "text": words + note + "."})
            rows.append(_row("EPA per target (team)", _signed(mean), f"{len(values)} targets", "epa_target"))
        else:
            rows.append(_short("EPA per target (team)", len(values), "targets", "epa_target"))
    return lines, rows


def _defense_lines(played, plays, plays_weeks, note):
    lines, rows = [], []
    if plays_weeks:
        counts = {}
        for q in plays:
            if q.get("side") == "defense" and q.get("impact"):
                counts[q["impact"]] = counts.get(q["impact"], 0) + 1
        total = sum(counts.values())
        parts = [_n(n, *IMPACT_WORDS.get(kind, (kind.lower(), kind.lower()))) for kind, n in sorted(counts.items(), key=lambda kv: -kv[1])]
        snaps = _sum((p.get("snaps") or {}).get("defense") for _, p in plays_weeks) or 0
        text = f"{_n(total, 'impact play', 'impact plays')}" + (f" ({', '.join(parts)})" if parts else "")
        if snaps >= MINIMUM["snaps"]:
            rate = 100 * total / snaps
            text += f", about {rate:.1f} for every 100 defensive snaps"
            rows.append(_row("Impact plays per 100 snaps", f"{rate:.1f}", f"{total} in {snaps} defensive snaps", "impact_rate"))
        else:
            rows.append(_short("Impact plays per 100 snaps", snaps, "snaps", "impact_rate"))
        lines.append({"label": "Impact plays", "text": text + note + "."})
        tackles = sum(1 for q in plays if any(role in q.get("roles", []) for role in TACKLE_ROLES))
        lines.append({"label": "Tackles", "text": f"{_n(tackles, 'tackle', 'tackles')}{note}."})
    charting = [p.get("charting") or {} for _, p in played]
    cover = [c["coverage"] for c in charting if c.get("coverage")]
    if cover:
        total = {key: sum(c.get(key, 0) for c in cover) for key in ("targets", "completions", "yards", "touchdowns", "interceptions")}
        lines.append({"label": "Coverage", "text": statlines.sentence(statlines.coverage(total), _based_on_note(len(cover), len(played)))})
    rush = [c["pass_rush"] for c in charting if c.get("pass_rush")]
    pressured = statlines.pressures(sum(r["pressures"] for r in rush))
    if pressured:
        lines.append({"label": "Pass rush", "text": statlines.sentence(pressured, _based_on_note(len(rush), len(played)))})
    tackling = [c["tackling"] for c in charting if c.get("tackling")]
    if tackling:
        parts = statlines.tackling(sum(t["missed"] for t in tackling), sum(t["attempts"] for t in tackling))
        lines.append({"label": "Tackling", "text": statlines.sentence(parts, _based_on_note(len(tackling), len(played)))})
    return lines, rows
