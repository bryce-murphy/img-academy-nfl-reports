"""Render the static site from committed editions with Jinja2 templates."""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from . import editorial
from . import evidence as ev
from .edition import load_config
from .upnext import kickoff_label, matchup_label

ROOT = Path(__file__).resolve().parents[1]
EDITION_DIR = re.compile(r"(\d{4})-week-(\d{2})")
SNAP_ABBREVIATIONS = (("offense", "OFF"), ("defense", "DEF"), ("st", "ST"))
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
    return f"{player['team']} {ev.fmt(game['team_score'])} · {game['opponent']} {ev.fmt(game['opp_score'])} — Final"


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


def player_view(player):
    view = dict(player)
    view.update(
        initials=initials(player["name"]),
        score_line=score_line(player),
        result_line=result_line(player),
        contribution=contribution(player),
        snap_line=snap_line(player),
        source_url=player["alumni_source"] if player["alumni_source"].startswith("https://") else "",
    )
    return view


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


def edition_context(edition, *, root, data_path):
    players = [player_view(p) for p in edition.data["players"]]
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
        "data_path": data_path,
    }


def social_drafts(edition, copy, url):
    if not edition["publication_ready"]:
        return {"state": "withheld", "edition": edition["id"], "url": url, "reason": "Conflicting participation evidence needs review before posting."}
    week = edition["week"]
    linkedin = (
        f"{copy['headline']}\n\n{copy['dek']}\n\n"
        f"The IMG Academy → NFL Week {week} edition has results, participation evidence and what's next "
        f"for every alum we follow. Missing information is labeled, not guessed.\n\n{url}"
    )
    x = f"{copy['headline']}\n\nIMG Academy → NFL, Week {week}: {url}"
    return {"state": "draft", "edition": edition["id"], "url": url, "linkedin": linkedin, "x": x}


def environment():
    env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["num"] = ev.fmt
    return env


def _write_json(path, value, **options):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, **options) + "\n", encoding="utf-8", newline="\n")


def build_site(out, editions_root=ROOT / "editions", config=None):
    config = config or load_config()
    env = environment()
    editions = load_editions(editions_root)
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    (out / "static").mkdir(parents=True)
    for asset in (ROOT / "static").iterdir():
        shutil.copy2(asset, out / "static" / asset.name)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    site_url = config["site_url"]
    written = []

    def page(template, path, **context):
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(env.get_template(template).render(site=config, **context), encoding="utf-8", newline="\n")
        written.append(target)

    for e in editions:
        folder = f"editions/{e.id}/"
        page("edition.html", folder + "index.html", canonical=site_url + folder, **edition_context(e, root="../../", data_path=""))
        _write_json(out / folder / "edition.json", e.data)
        _write_json(out / folder / "sources.json", e.sources, sort_keys=True)
        _write_json(out / folder / "social-drafts.json", social_drafts(e.data, e.editorial, site_url + folder))
    if editions:
        latest = editions[-1]
        page("edition.html", "index.html", canonical=f"{site_url}editions/{latest.id}/",
             **edition_context(latest, root="", data_path=f"editions/{latest.id}/"))
    else:
        page("empty.html", "index.html", canonical=site_url, root="")
    page("archive.html", "archive/index.html", canonical=site_url + "archive/", root="../", editions=list(reversed(editions)))
    page("methodology.html", "methodology/index.html", canonical=site_url + "methodology/", root="../")
    page("404.html", "404.html", canonical=site_url, root=site_url)
    urls = [site_url, site_url + "archive/", site_url + "methodology/"] + [f"{site_url}editions/{e.id}/" for e in editions]
    page("sitemap.xml", "sitemap.xml", canonical=site_url, root="", urls=urls)
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {site_url}sitemap.xml\n", encoding="utf-8", newline="\n")
    return written
