"""Render the static site from committed editions with Jinja2 templates."""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup, escape

from . import editorial, field, moves, playtext
from . import evidence as ev
from . import players as pl
from .edition import load_config, load_registry
from .upnext import DAYS, MONTHS, kickoff_label, matchup_label

ROOT = Path(__file__).resolve().parents[1]
BRAND = "#0057b8"
HEX = re.compile(r"#[0-9a-fA-F]{6}")
SCORE = re.compile(r"\b\d+-\d+\b")
EDITION_DIR = re.compile(r"(\d{4})-week-(\d{2})")
SNAP_ABBREVIATIONS = (("offense", "OFF"), ("defense", "DEF"), ("st", "ST"))
# Display labels where the feed's code differs from the usual shorthand; the data keeps the feed's code.
POSITION_LABELS = {"SAF": "S"}
DEFENSIVE_POSITIONS = {"CB", "S", "SAF", "FS", "SS", "DB", "LB", "ILB", "OLB", "MLB", "DE", "DT", "NT", "DL", "EDGE"}
AVAILABILITY_NOTES = {
    ev.CONFLICT: "Sources disagree. Social posts wait until the owner reviews this.",
    "Inactive for the game": "From the weekly roster. The reason is not inferred.",
    "Practice squad": "Practice-squad players are not on the game-day roster unless elevated.",
    "Reserve list": "Reserve designations are shown without an inferred reason.",
    "Released": "Released during the reporting week.",
    ev.BYE: "The team did not play this week.",
    ev.NO_SNAPS: "Active, but absent from a complete snap-count table. The reason is not established.",
    ev.UNVERIFIED: "Evidence is incomplete. Missing data is never treated as a DNP.",
    ev.NOT_ON_ROSTER: "Not on an NFL weekly roster this week.",
}


@dataclass
class Edition:
    id: str
    season: int
    week: int
    data: dict
    editorial: dict
    sources: dict


def load_editions(root):
    editions = []
    for directory in Path(root).glob("*-week-*"):
        match = EDITION_DIR.fullmatch(directory.name)
        if not match or not directory.is_dir():
            continue
        editions.append(Edition(
            directory.name, int(match[1]), int(match[2]),
            json.loads((directory / "edition.json").read_text(encoding="utf-8")),
            editorial.load(directory / "editorial.toml"),
            json.loads((directory / "sources.json").read_text(encoding="utf-8")),
        ))
    return sorted(editions, key=lambda e: (e.season, e.week))


def initials(name):
    return "".join(part[0] for part in name.split()[:2]).upper()


def score_line(player):
    game = player.get("game")
    if not game:
        return "No game this week"
    return f"{player['team']} {ev.fmt(game['team_score'])} · {game['opponent']} {ev.fmt(game['opp_score'])}"


def result_line(player):
    game = player.get("game")
    if not game:
        return "—"
    return f"{game['result']} {ev.fmt(game['team_score'])}–{ev.fmt(game['opp_score'])} vs. {game['opponent']}"


def contribution(player):
    if player.get("stats_withheld"):
        return "Stats withheld: sources disagree"
    phrases = editorial.top_phrases(player, 4)
    return " · ".join(phrases) if phrases else "No recorded statistics"


def snap_line(player):
    parts = [f"{ev.fmt(player['snaps'][key])} {abbr}" for key, abbr in SNAP_ABBREVIATIONS if player["snaps"].get(key)]
    return " · ".join(parts) if parts else "—"


def participation_line(player):
    """How much a player played, in words; the card's metric tiles already carry lineman snap counts."""
    availability = player["availability"]
    if availability["label"] != ev.PLAYED:
        return f"{availability['evidence']} · Snaps {snap_line(player)}"
    metrics = player["metrics"]
    if metrics and not player.get("stats_withheld") and all(m["label"].endswith("snaps") for m in metrics):
        return ""
    snaps = player["snaps"]
    parts = [f"{ev.fmt(snaps[key])} {name} snap{'' if snaps[key] == 1 else 's'}" for key, name in (("offense", "offensive"), ("defense", "defensive")) if snaps.get(key)]
    if snaps.get("st"):
        count = ev.fmt(snaps["st"])
        parts.append(f"{count} on special teams" if parts else f"{count} special-teams snap{'' if snaps['st'] == 1 else 's'}")
    if not parts:
        return f"{availability['evidence']}; snap counts not available."
    return "Played " + (parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]) + "."


def _the(team_name):
    """'Cleveland Browns' -> 'the Browns'; a bare abbreviation stays as it is."""
    return f"the {team_name.split()[-1]}" if " " in team_name else team_name


def play_outcome(key_play, player):
    """What a key play meant, told from the offense's expected points (EPA) in words.

    Editions published before key plays carried a side fall back to the player's position.
    """
    side = key_play.get("side") or ("defense" if player["position"] in DEFENSIVE_POSITIONS else "offense")
    if key_play.get("offense_name"):
        offense, defense = _the(key_play["offense_name"]), _the(key_play["defense_name"])
    else:
        mine, other = player["team_name"], (player.get("game") or {}).get("opponent", "")
        offense, defense = (_the(mine), other) if side == "offense" else (other, _the(mine))
    value = round(abs(key_play["epa"]), 1)
    points = "1 expected point" if value == 1 else f"{value:.1f} expected points"
    if side == "defense" and key_play["epa"] < 0:
        return f"Good for {defense} defense: {offense} lost {points}"
    text = f"{offense} {'lost' if key_play['epa'] < 0 else 'gained'} {points}"
    return text[0].upper() + text[1:]


def _n(count, word, plural=None):
    return f"{count} {word if count == 1 else plural or word + 's'}"


def charting_lines(player):
    """Charted extras as plain counts. Coverage is 'charted in coverage', never 'allowed'."""
    c = player.get("charting") or {}
    lines = []
    if c.get("targets"):
        t = c["targets"]
        text = f"Targets: {t['catchable']} of {t['charted']} catchable, {_n(t['drops'], 'drop')}"
        if t["contested"]:
            text += f", {t['contested_catches']} of {t['contested']} contested caught"
        lines.append(text)
    if c.get("coverage"):
        v = c["coverage"]
        parts = [_n(v["targets"], "target"), _n(v["completions"], "completion"), _n(v["yards"], "yard")]
        parts += [_n(v["touchdowns"], "touchdown")] if v["touchdowns"] else []
        parts += [_n(v["interceptions"], "interception")] if v["interceptions"] else []
        lines.append("Charted in coverage: " + ", ".join(parts))
    if c.get("pass_rush"):
        r = c["pass_rush"]
        detail = ", ".join(_n(r[k], *w) for k, w in (("sacks", ("sack",)), ("qb_hits", ("QB hit",)), ("hurries", ("hurry", "hurries"))) if r[k])
        text = f"Pass rush: {_n(r['pressures'], 'pressure')}" + (f" ({detail})" if detail else "")
        if r["blitzes"]:
            text += f", blitzed {_n(r['blitzes'], 'time')}"
        lines.append(text)
    if c.get("tackling"):
        lines.append(f"Tackling: {c['tackling']['missed']} missed in {_n(c['tackling']['attempts'], 'attempt')}")
    if c.get("rushing"):
        u = c["rushing"]
        lines.append(f"Rushing: {u['after_contact']} of {_n(u['before_contact'] + u['after_contact'], 'yard')} after contact, {_n(u['broken_tackles'], 'broken tackle')}")
    if c.get("broken_tackles"):
        lines.append(f"Broken tackles after the catch: {c['broken_tackles']}")
    return lines


def _sunday_on_or_after(day):
    return day + timedelta(days=(6 - day.weekday()) % 7)


def to_eastern(moment):
    """US Eastern time without a tz database: daylight time runs from 2 a.m. on the second Sunday of
    March to 2 a.m. on the first Sunday of November."""
    moment = moment.astimezone(timezone.utc)
    starts = datetime.combine(_sunday_on_or_after(date(moment.year, 3, 8)), datetime.min.time(), timezone.utc) + timedelta(hours=7)
    ends = datetime.combine(_sunday_on_or_after(date(moment.year, 11, 1)), datetime.min.time(), timezone.utc) + timedelta(hours=6)
    return moment + timedelta(hours=-4 if starts <= moment < ends else -5)


def eastern_label(timestamp):
    """'2026-09-28T13:52:10+00:00' -> 'Mon, Sep 28, 9:52 a.m. ET'."""
    local = to_eastern(datetime.fromisoformat(timestamp.replace("Z", "+00:00")))
    suffix = "a.m." if local.hour < 12 else "p.m."
    return f"{DAYS[local.weekday()]}, {MONTHS[local.month - 1]} {local.day}, {local.hour % 12 or 12}:{local.minute:02d} {suffix} ET"


def _luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG contrast ratio between two #rrggbb colors."""
    light, dark = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _shade(color, keep):
    return "#" + "".join(f"{round(int(color[i:i + 2], 16) * keep):02x}" for i in (1, 3, 5))


def team_bar(color):
    """(background, text, outline) for a team-color bar at WCAG AA (4.5:1). White text when it passes. A light
    color (like Saints gold) becomes trim: its own text and outline on a near-black shade of itself. Any other
    color is deepened step by step until white text passes."""
    color = color if isinstance(color, str) and HEX.fullmatch(color) else BRAND
    if contrast(color, "#ffffff") >= 4.5:
        return color, "#ffffff", None
    if contrast(color, "#ffffff") < 3:
        return _shade(color, 0.12), color, color
    shade, step = color, 0
    while contrast(shade, "#ffffff") < 4.5:
        step += 1
        shade = _shade(color, 1 - step / 20)
    return shade, "#ffffff", None


def keep_scores(text):
    """Escape the text, then keep scores like 12-7 on one line."""
    return Markup(SCORE.sub(lambda m: f'<span class="nowrap">{m.group(0)}</span>', str(escape(text))))


def asset_version(path):
    """A short content fingerprint for cache-busting URLs: a changed file gets a new URL."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:10]


def player_view(player):
    view = dict(player)
    view.update(
        initials=initials(player["name"]),
        position=POSITION_LABELS.get(player["position"], player["position"]),
        score_line=score_line(player),
        result_line=result_line(player),
        contribution=contribution(player),
        snap_line=snap_line(player),
        participation=participation_line(player),
        charting_lines=charting_lines(player),
        key_plays=[dict(k, impact=k.get("impact"), outcome=play_outcome(k, player)) for k in player.get("key_plays", [])],
        source_url=player["alumni_source"] if player["alumni_source"].startswith("https://") else "",
    )
    view["bar"], view["ink"], view["edge"] = team_bar(player.get("team_color"))
    return view


def next_line(player):
    info = player.get("next_game")
    if not info:
        return ""
    if info.get("kind") == "game":
        return f"{matchup_label(info, info['team'])} · {kickoff_label(info)}"
    if info.get("kind") == "bye":
        return f"Bye in Week {info['bye_week']}, then {matchup_label(info, info['team'])} · {kickoff_label(info)}"
    return "Next game unconfirmed" if info.get("kind") == "unconfirmed" else "Season complete"


def team_colors(edition_data):
    """abbr -> team color for every team in the edition; older editions fall back to the alumni's own teams."""
    colors = {p["team"]: p["team_color"] for p in edition_data.get("players", []) if p.get("team") and p.get("team_color")}
    colors.update({abbr: t["color"] for abbr, t in (edition_data.get("teams") or {}).items()})
    return colors


def _drawings(play, player, tag, good, teams):
    colors = dict(teams or {})
    colors.setdefault(player.get("team"), player.get("team_color"))
    zones = {side: team_bar(colors.get(play.get(side)))[:2] for side in ("offense", "defense")}
    path = team_bar(player.get("team_color"))[0]
    return lambda size: field.svg(play, size, outcome=tag["text"] if tag else "", helped=good, path_color=path, zones=zones)


def play_view(play, player, key_ids=(), teams=None):
    """`positive` is three-way: True, False, or None (unknown epa, or neutral: it rounds to 0.0 as shown)."""
    epa = play.get("epa")
    side = play.get("side") or ("defense" if player["position"] in DEFENSIVE_POSITIONS else "offense")
    good = playtext.helped(play, side)
    tag = playtext.tag(play, side, pl.nickname(player["team_name"]))
    draw = _drawings(play, player, tag, good, teams)
    medium, large = draw("medium"), draw("large")
    return dict(
        play,
        outcome=play_outcome(play, player) if epa is not None else "",
        spot=field.spot_line(play), result=field.result_line(play) or "",
        svg_medium=Markup(medium) if medium else None, svg_large=Markup(large) if large else None,
        positive=good, key=play.get("play_id") in key_ids,
        line=playtext.play_line(play, player), tag=tag,
        epa_text=playtext.epa_sentence(play), air_text=playtext.air_sentence(play),
        pbp_text=playtext.safe_description(play.get("description", "")),
    )


def week_plays(player, teams=None):
    """Recorded plays for a week page: key moments first, then game order. Schema-1 editions have only key moments.

    A key moment can be missing from `plays` (credited through a role outside the recorded-play roles, or on a
    deleted play); it is appended so the explorer lists every key moment the card shows."""
    key_plays = player.get("key_plays", [])
    key_ids = [k["play_id"] for k in key_plays]
    plays = player.get("plays")
    saved = plays is not None
    if saved:
        present = {q["play_id"] for q in plays}
        source = list(plays) + [k for k in key_plays if k["play_id"] not in present]
    else:
        source = key_plays
    ordered = sorted(source, key=lambda q: (q["play_id"] not in key_ids, key_ids.index(q["play_id"]) if q["play_id"] in key_ids else 0, float(q["play_id"])))
    return saved, [play_view(q, player, set(key_ids), teams) for q in ordered]


def up_next_groups(players):
    groups = {}
    for player in players:
        info = player.get("next_game")
        if not info or not info.get("team"):
            continue
        team = info["team"]
        group = groups.setdefault(team, {"team": team, "team_name": info["team_name"], "team_color": info["team_color"], "info": info, "players": []})
        group["players"].append(player["name"] + (f" (now with {team})" if player.get("team_changed") else ""))
    rendered = []
    for group in groups.values():
        info = group["info"]
        if info["kind"] == "game":
            group.update(heading=matchup_label(info, group["team"]), when=kickoff_label(info), venue=info.get("venue") or "Venue TBD")
        elif info["kind"] == "bye":
            group.update(heading=f"Bye in Week {info['bye_week']}", when=f"Then {matchup_label(info, group['team'])} · {kickoff_label(info)}", venue=info.get("venue") or "Venue TBD")
        elif info["kind"] == "season_complete":
            group.update(heading="Season complete", when="", venue="")
        else:
            group.update(heading="Next matchup unconfirmed", when="", venue="")
        rendered.append(group)
    return sorted(rendered, key=lambda g: (g["info"].get("date", "9999-12-31"), g["team"]))


def top_drawable_play(player):
    """The first key moment, in key-moment order, that is present in the player's recorded plays (schema 2)
    and has a field diagram. Schema-1 editions have no `plays`, so they never yield a drawable play."""
    plays_by_id = {q["play_id"]: q for q in player.get("plays") or []}
    for k in player.get("key_plays", []):
        play = plays_by_id.get(k["play_id"])
        if play is not None and field.geometry(play) is not None:
            return play
    return None


def edition_context(edition, *, root, data_path, slugs, notes=None):
    players = [player_view(p) for p in edition.data["players"]]
    teams = team_colors(edition.data)
    for raw, view in zip(edition.data["players"], players):
        view["move"] = moves.view(raw, notes or {}, edition.data["season"])
        slug = slugs.get(raw["id"])
        view["page"] = f"{root}players/{slug}/{edition.id}/" if slug else None
        top = top_drawable_play(raw)
        view["strip"] = None
        if top is not None:
            outcome = play_outcome(top, raw) if top.get("epa") is not None else ""
            side = top.get("side") or ("defense" if raw["position"] in DEFENSIVE_POSITIONS else "offense")
            good = playtext.helped(top, side)
            tag = playtext.tag(top, side, pl.nickname(raw["team_name"]))
            view["strip"] = Markup(_drawings(top, raw, tag, good, teams)("strip"))
            view["strip_play_id"] = top["play_id"]
            view["strip_outcome"] = outcome
    by_id = {p["id"]: p for p in players}
    featured = by_id.get(edition.editorial.get("featured_player_id", ""))
    if featured and featured["availability"]["label"] != ev.PLAYED:
        featured = None
    availability = []
    for label in ev.LABEL_ORDER:
        members = [p for p in players if p["availability"]["label"] == label]
        if label != ev.PLAYED and members:
            availability.append({"label": label, "note": AVAILABILITY_NOTES.get(label, ""), "players": members})
    return {
        "edition": edition.data,
        "editorial": edition.editorial,
        "featured": featured,
        "played": [by_id[pid] for pid in edition.data["featured_ranking"] if pid in by_id],
        "availability": availability,
        "up_next": up_next_groups(players),
        "sources": sorted(edition.sources.items()),
        "root": root,
        "data_as_of": eastern_label(edition.data["generated_at"]),
        "data_path": data_path,
    }


def social_drafts(edition, copy, url):
    if not edition["publication_ready"]:
        return {"state": "withheld", "edition": edition["id"], "url": url, "reason": "Conflicting participation evidence needs review before posting."}
    week = edition["week"]
    linkedin = (
        f"{copy['headline']}\n\n{copy['dek']}\n\n"
        f"Every week I track the IMG Academy football alumni in the NFL: results, how much each one played "
        f"and what's next. Every number is checked against the data. Here's Week {week}:\n\n{url}\n\n"
        "A personal project, not an official IMG Academy or NFL publication."
    )
    x = f"{copy['headline']}\n\nIMG Academy → NFL, Week {week}: {url}"
    return {"state": "draft", "edition": edition["id"], "url": url, "linkedin": linkedin, "x": x}


@functools.cache
def environment():
    """One shared Jinja environment per process; templates and asset fingerprints do not change during a build."""
    env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["num"] = ev.fmt
    env.filters["scores"] = keep_scores
    env.filters["safe_description"] = playtext.safe_description
    env.globals["asset_version"] = asset_version(ROOT / "static" / "styles.css")
    env.globals["explorer_version"] = asset_version(ROOT / "static" / "explorer.js")
    return env


def _write_json(path, value, **options):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, **options) + "\n", encoding="utf-8", newline="\n")


def build_site(out, editions_root=ROOT / "editions", config=None, registry=None):
    config = config or load_config()
    if registry is None:
        registry = load_registry()
    env = environment()
    editions = load_editions(editions_root)
    notes = moves.note_index([(e.data, e.editorial) for e in editions])
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    (out / "static").mkdir(parents=True)
    for asset in (ROOT / "static").iterdir():
        shutil.copy2(asset, out / "static" / asset.name)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    site_url = config["site_url"]
    slugs = {alum["gsis_id"]: alum["slug"] for alum in registry}
    written = []

    def page(template, path, **context):
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(env.get_template(template).render(site=config, **context), encoding="utf-8", newline="\n")
        written.append(target)

    urls = [site_url, site_url + "archive/", site_url + "methodology/"] + [f"{site_url}editions/{e.id}/" for e in editions]
    for e in editions:
        folder = f"editions/{e.id}/"
        page("edition.html", folder + "index.html", canonical=site_url + folder, **edition_context(e, root="../../", data_path="", slugs=slugs, notes=notes))
        _write_json(out / folder / "edition.json", e.data)
        _write_json(out / folder / "sources.json", e.sources, sort_keys=True)
        _write_json(out / folder / "social-drafts.json", social_drafts(e.data, e.editorial, site_url + folder))
    if editions:
        latest = editions[-1]
        page("edition.html", "index.html", canonical=f"{site_url}editions/{latest.id}/",
             **edition_context(latest, root="", data_path=f"editions/{latest.id}/", slugs=slugs, notes=notes))
    else:
        page("empty.html", "index.html", canonical=site_url, root="")
    page("archive.html", "archive/index.html", canonical=site_url + "archive/", root="../", editions=list(reversed(editions)))
    page("methodology.html", "methodology/index.html", canonical=site_url + "methodology/", root="../")
    page("404.html", "404.html", canonical=site_url, root=site_url)
    datas = [e.data for e in editions]
    listing = []
    for alum in registry:
        apps = pl.appearances(datas, alum["gsis_id"])
        latest = apps[-1][1] if apps else None
        base_url = f"players/{alum['slug']}/"
        for e_data, p in apps:
            view = player_view(p)
            view["move"] = moves.view(p, notes, e_data["season"])
            teams = team_colors(e_data)
            saved, plays = week_plays(p, teams)
            page("player_week.html", f"{base_url}{e_data['id']}/index.html", canonical=site_url + f"{base_url}{e_data['id']}/", root="../../../",
                 player=view, edition=e_data, plays=plays, plays_saved=saved, played=p["availability"]["label"] == ev.PLAYED, lineman=pl.group_of(p["position"]) == "Offensive line",
                 nickname=pl.nickname(p["team_name"]), caption=field.CAPTION, data_as_of=eastern_label(e_data["generated_at"]),
                 next_text=next_line(p), summary=playtext.summary(plays) if saved and p["availability"]["label"] == ev.PLAYED else "")
            urls.append(f"{site_url}{base_url}{e_data['id']}/")
        log = pl.game_log(apps)
        for row, (_, p) in zip(log, apps):
            row["contribution"] = contribution(p)
        latest_edition = apps[-1][0] if apps else None
        latest_saved, latest_plays = week_plays(latest, team_colors(latest_edition)) if latest else (False, [])
        top = top_drawable_play(latest) if latest else None
        latest_view = player_view(latest) if latest else None
        if latest_view:
            latest_view["move"] = moves.view(latest, notes, latest_edition["season"])
        page("player.html", base_url + "index.html", canonical=site_url + base_url, root="../../", alum=alum,
             player=latest_view, latest_edition=latest_edition,
             played=bool(latest) and latest["availability"]["label"] == ev.PLAYED,
             season=pl.season_lines(apps, latest["position"]) if latest else [], log=log,
             top_play=play_view(top, latest, teams=team_colors(latest_edition)) if top else None, recorded=len(latest_plays), plays_saved=latest_saved,
             next_text=next_line(latest) if latest and not latest_edition.get("historical") else "",
             data_as_of=eastern_label(latest_edition["generated_at"]) if apps else "")
        urls.append(site_url + base_url)
        listing.append({"alum": alum, "player": latest, "group": pl.group_of(latest["position"]) if latest else "Other"})
    page("players.html", "players/index.html", canonical=site_url + "players/", root="../",
         groups=[(title, [x for x in listing if x["group"] == title]) for title, _ in pl.GROUPS + (("Other", set()),)])
    urls.append(site_url + "players/")
    page("sitemap.xml", "sitemap.xml", canonical=site_url, root="", urls=urls)
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {site_url}sitemap.xml\n", encoding="utf-8", newline="\n")
    return written


LINK = re.compile(r'(?:href|src)="([^"#?]*)[^"]*"')
PLAY_FRAGMENT = re.compile(r'href="([^"#?]*)(?:\?[^"#]*)?#(play-[^"]+)"')


def check_site(out, editions):
    out = Path(out)
    problems = []
    for e in editions:
        page = out / "editions" / e.id / "index.html"
        if f'<meta name="edition-id" content="{e.id}">' not in page.read_text(encoding="utf-8"):
            problems.append(f"editions/{e.id}/index.html is missing its edition-id")
    if editions and f'<meta name="edition-id" content="{editions[-1].id}">' not in (out / "index.html").read_text(encoding="utf-8"):
        problems.append("index.html does not show the latest edition")
    for page in sorted(out.rglob("*.html")):
        text = page.read_text(encoding="utf-8")
        name = page.relative_to(out).as_posix()
        if "{{" in text or "{%" in text:
            problems.append(f"{name} contains unrendered template syntax")
        for target in LINK.findall(text):
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (page.parent / target).resolve()
            if target.endswith("/") or resolved.is_dir():
                resolved = resolved / "index.html"
            if not resolved.exists():
                problems.append(f"{name} links to missing {target}")
        for target, fragment in PLAY_FRAGMENT.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = page if not target else (page.parent / target).resolve()
            if target.endswith("/") or resolved.is_dir():
                resolved = resolved / "index.html"
            if resolved.exists() and f'id="{fragment}"' not in resolved.read_text(encoding="utf-8"):
                problems.append(f"{name} links to missing {target}#{fragment}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m src.site")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Render the site")
    build.add_argument("--out", type=Path, default=ROOT / "_site")
    build.add_argument("--editions", type=Path, default=ROOT / "editions")
    build.add_argument("--check", action="store_true", help="Exit 1 if links or edition ids are wrong")
    latest = sub.add_parser("latest-id", help="Print the newest edition id, or 'none'")
    latest.add_argument("--editions", type=Path, default=ROOT / "editions")
    args = parser.parse_args(argv)
    if args.command == "latest-id":
        editions = load_editions(args.editions)
        print(editions[-1].id if editions else "none")
        return 0
    written = build_site(args.out, args.editions)
    print(f"Rendered {len(written)} pages into {args.out}")
    if args.check:
        problems = check_site(args.out, load_editions(args.editions))
        for problem in problems:
            print(f"::error::{problem}")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
