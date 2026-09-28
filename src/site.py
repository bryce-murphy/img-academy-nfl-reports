"""Render the static site from committed editions with Jinja2 templates."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
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
# Display labels where the feed's code differs from the usual shorthand; the data keeps the feed's code.
POSITION_LABELS = {"SAF": "S"}
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
        f"Every week I track the IMG Academy football alumni in the NFL: results, how much each one played "
        f"and what's next. Every number is checked against the data. Here's Week {week}:\n\n{url}\n\n"
        "A personal project, not an official IMG Academy or NFL publication."
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


LINK = re.compile(r'(?:href|src)="([^"#?]*)[^"]*"')


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
