import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

import fixture_data
from src import editorial, site
from src import evidence as ev
from src.edition import load_registry

CONFIG = {
    "title": "IMG Academy → NFL",
    "author": "Bryce Murphy",
    "linkedin_profile": "https://www.linkedin.com/in/bryce-murphy/",
    "site_url": "https://bryce-murphy.github.io/img-academy-nfl-reports/",
}


class SiteTestCase(unittest.TestCase):
    def render(self, edition=None, copy_=None, extra=()):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.editions = root / "editions"
        fixture_data.write_edition_dir(self.editions, edition or fixture_data.golden_edition(), copy_)
        for other in extra:
            fixture_data.write_edition_dir(self.editions, other)
        out = root / "out"
        site.build_site(out, self.editions, CONFIG, registry=load_registry(fixture_data.FIXTURES / "alumni.json"))
        return out

    @staticmethod
    def read(path):
        return path.read_text(encoding="utf-8")


class RenderTests(SiteTestCase):
    def test_homepage_is_the_latest_edition(self):
        html = self.read(self.render() / "index.html")
        self.assertIn('<meta name="edition-id" content="2026-week-02">', html)
        self.assertIn("IMG Academy → NFL", html)
        self.assertIn("Not an official IMG Academy or NFL publication", html)

    def test_headline_markup_is_escaped(self):
        edition = fixture_data.golden_edition()
        headline = dict(editorial.fallback(edition), headline='<script>alert("x")</script> & “quotes”')
        html = self.read(self.render(edition, headline) / "index.html")
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    def test_availability_desk_groups_absences(self):
        html = self.read(self.render() / "editions" / "2026-week-02" / "index.html")
        for text in ("Inactive for the game", "Warren Brinson", "Practice squad", "No snaps recorded", "Not on an NFL roster"):
            self.assertIn(text, html)

    def test_up_next_uses_eastern_kickoffs(self):
        html = self.read(self.render() / "index.html")
        self.assertIn("ATL at GB", html)
        self.assertIn("Thu, Sep 24 · 8:15 p.m. ET", html)

    def test_page_renders_without_featured_player(self):
        edition = fixture_data.golden_edition()
        for p in edition["players"]:
            p["availability"] = {"label": ev.BYE, "evidence": "No game on this week's schedule"}
        edition["featured_ranking"] = []
        edition["counts"]["played"] = 0
        html = self.read(self.render(edition) / "index.html")
        self.assertNotIn('<aside class="featured"', html)
        self.assertIn("Bye week", html)

    def test_social_drafts_link_to_the_edition(self):
        drafts = json.loads(self.read(self.render() / "editions" / "2026-week-02" / "social-drafts.json"))
        self.assertEqual(drafts["state"], "draft")
        self.assertEqual(drafts["url"], CONFIG["site_url"] + "editions/2026-week-02/")
        self.assertIn(drafts["url"], drafts["linkedin"])
        self.assertLessEqual(len(drafts["x"]), 280)

    def test_social_drafts_are_withheld_on_conflict(self):
        edition = fixture_data.golden_edition()
        edition["publication_ready"] = False
        drafts = json.loads(self.read(self.render(edition) / "editions" / "2026-week-02" / "social-drafts.json"))
        self.assertEqual(drafts["state"], "withheld")

    def test_archive_lists_week_ten_before_week_two(self):
        week2 = fixture_data.golden_edition()
        week10 = dict(copy.deepcopy(week2), id="2026-week-10", week=10)
        out = self.render(week2, extra=[week10])
        archive = self.read(out / "archive" / "index.html")
        self.assertLess(archive.index("editions/2026-week-10/"), archive.index("editions/2026-week-02/"))
        self.assertIn('content="2026-week-10"', self.read(out / "index.html"))

    def test_empty_site_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            site.build_site(out, Path(tmp) / "no-editions", CONFIG)
            self.assertIn("The first edition is on its way", self.read(out / "index.html"))
            self.assertTrue((out / "methodology" / "index.html").exists())

    def test_build_writes_every_published_artifact(self):
        out = self.render()
        self.assertTrue((out / "static" / "styles.css").exists())
        self.assertTrue((out / ".nojekyll").exists())
        not_found = self.read(out / "404.html")
        self.assertIn('href="https://bryce-murphy.github.io/img-academy-nfl-reports/archive/"', not_found)
        sitemap = self.read(out / "sitemap.xml")
        self.assertIn(
            "<loc>https://bryce-murphy.github.io/img-academy-nfl-reports/editions/2026-week-02/</loc>", sitemap
        )
        with open(out / "robots.txt", encoding="utf-8", newline="") as handle:
            robots = handle.read()
        self.assertEqual(
            robots,
            "User-agent: *\nAllow: /\nSitemap: https://bryce-murphy.github.io/img-academy-nfl-reports/sitemap.xml\n",
        )
        edition_json = json.loads(self.read(out / "editions" / "2026-week-02" / "edition.json"))
        self.assertEqual(edition_json, fixture_data.golden_edition())
        sources_json = json.loads(self.read(out / "editions" / "2026-week-02" / "sources.json"))
        self.assertEqual(sources_json, {})

    def test_every_page_has_a_large_share_image_and_favicon(self):
        out = self.render()
        image = CONFIG["site_url"] + "static/share-card.png"
        for page in out.rglob("*.html"):
            html = self.read(page)
            self.assertIn(f'<meta property="og:image" content="{image}">', html, page)
            self.assertIn('<meta name="twitter:card" content="summary_large_image">', html, page)
            self.assertIn('<meta property="og:image:alt"', html, page)
            self.assertIn('static/favicon.svg" type="image/svg+xml">', html, page)
        with open(out / "static" / "share-card.png", "rb") as handle:
            header = handle.read(24)
        self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual((int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")), (1200, 630))
        self.assertTrue((out / "static" / "favicon.svg").exists())

    def test_play_outcome_is_told_from_each_side(self):
        browns = {"position": "SAF", "team": "CLE", "team_name": "Cleveland Browns", "game": {"opponent": "TB"}}
        titans = {"position": "WR", "team": "TEN", "team_name": "Tennessee Titans", "game": {"opponent": "PHI"}}
        names = {"offense": "TB", "defense": "CLE", "offense_name": "Tampa Bay Buccaneers", "defense_name": "Cleveland Browns"}
        outcome = site.play_outcome
        self.assertEqual(outcome(dict(names, side="defense", epa=-0.6), browns), "Good for the Browns defense: the Buccaneers lost 0.6 expected points")
        self.assertEqual(outcome(dict(names, side="defense", epa=0.82), browns), "The Buccaneers gained 0.8 expected points")
        mine = {"offense": "TEN", "defense": "PHI", "offense_name": "Tennessee Titans", "defense_name": "Philadelphia Eagles"}
        self.assertEqual(outcome(dict(mine, side="offense", epa=-1.38), titans), "The Titans lost 1.4 expected points")
        self.assertEqual(outcome(dict(mine, side="offense", epa=1.0), titans), "The Titans gained 1 expected point")
        # Editions published before key plays carried a side (Week 2) fall back to the player's position.
        self.assertEqual(outcome({"epa": 2.03}, browns), "TB gained 2.0 expected points")
        self.assertEqual(outcome({"epa": -1.24}, titans), "The Titans lost 1.2 expected points")

    def test_editions_published_before_play_sides_still_render(self):
        edition = fixture_data.golden_edition()
        new_fields = ("side", "impact", "offense", "defense", "offense_name", "defense_name")
        for p in edition["players"]:
            p["key_plays"] = [{k: v for k, v in play.items() if k not in new_fields} for play in p["key_plays"]]
        html = self.read(self.render(edition) / "index.html")
        self.assertIn("Good for the Browns defense", html)

    def test_key_moments_show_impact_and_outcome(self):
        html = self.read(self.render() / "index.html")
        self.assertIn("Sack", html)
        self.assertIn("Good for the Browns defense", html)
        self.assertNotIn("EPA -", html)

    def test_charting_lines_are_counts_in_plain_words(self):
        lines = site.charting_lines
        self.assertEqual(lines({"charting": None}), [])
        self.assertEqual(lines({"charting": {"targets": {"charted": 5, "catchable": 3, "contested": 1, "contested_catches": 1, "drops": 0}}}),
                         ["Targets: 3 of 5 catchable, 0 drops, 1 of 1 contested caught"])
        self.assertEqual(lines({"charting": {"coverage": {"targets": 4, "completions": 2, "yards": 17, "touchdowns": 1, "interceptions": 0}}}),
                         ["Charted in coverage: 4 targets, 2 completions, 17 yards, 1 touchdown"])
        self.assertEqual(lines({"charting": {"pass_rush": {"pressures": 1, "hurries": 0, "qb_hits": 0, "sacks": 1, "blitzes": 2}}}),
                         ["Pass rush: 1 pressure (1 sack), blitzed 2 times"])
        self.assertEqual(lines({"charting": {"pass_rush": {"pressures": 0, "hurries": 0, "qb_hits": 0, "sacks": 0, "blitzes": 1}}}),
                         ["Pass rush: 0 pressures, blitzed 1 time"])
        self.assertEqual(lines({"charting": {"tackling": {"missed": 1, "attempts": 6}}}), ["Tackling: 1 missed in 6 attempts"])
        self.assertEqual(lines({"charting": {"rushing": {"carries": 5, "before_contact": 16, "after_contact": 8, "broken_tackles": 0}}}),
                         ["Rushing: 8 of 24 yards after contact, 0 broken tackles"])
        self.assertEqual(lines({"charting": {"broken_tackles": 2}}), ["Broken tackles after the catch: 2"])

    def test_cards_show_charting_and_pages_credit_the_charting_sources(self):
        out = self.render()
        html = self.read(out / "index.html")
        self.assertIn("Charted in coverage: 4 targets, 2 completions, 17 yards", html)
        self.assertIn("Targets: 3 of 5 catchable, 0 drops", html)
        self.assertNotIn(" allowed", html.split('<footer class="site-footer">')[0].split("<main")[1])
        for page in (html, self.read(out / "methodology" / "index.html")):
            self.assertIn("FTN Data via nflverse", page)
            self.assertIn("https://creativecommons.org/licenses/by-sa/4.0/", page)
            self.assertIn("Pro Football Reference", page)

    def test_key_moments_are_explained_once_not_on_every_card(self):
        out = self.render()
        home = self.read(out / "index.html")
        self.assertNotIn('<p class="caption">Defenders', home)
        self.assertEqual(home.count("describe the play, not a grade"), 1)
        self.assertIn('href="methodology/#key-plays"', home)
        method = self.read(out / "methodology" / "index.html")
        self.assertIn('id="key-plays"', method)
        self.assertIn("sacks, tackles for loss", method)
        self.assertNotIn("largest expected points added", method)

    def test_eastern_time_label_follows_daylight_saving(self):
        label = site.eastern_label
        self.assertEqual(label("2026-09-28T13:52:10+00:00"), "Mon, Sep 28, 9:52 a.m. ET")
        self.assertEqual(label("2026-11-01T05:59:00+00:00"), "Sun, Nov 1, 1:59 a.m. ET")  # still daylight time
        self.assertEqual(label("2026-11-01T06:00:00+00:00"), "Sun, Nov 1, 1:00 a.m. ET")  # standard time from here
        self.assertEqual(label("2026-12-15T17:00:00+00:00"), "Tue, Dec 15, 12:00 p.m. ET")
        self.assertEqual(label("2027-03-14T07:00:00+00:00"), "Sun, Mar 14, 3:00 a.m. ET")  # daylight time begins
        self.assertEqual(label("2026-09-23T12:00:00+00:00"), "Wed, Sep 23, 8:00 a.m. ET")

    def test_edition_page_shows_when_its_data_was_pulled(self):
        html = self.read(self.render() / "index.html")
        self.assertIn("Data as of Wed, Sep 23, 8:00 a.m. ET", html)
        self.assertIn("The NFL can correct statistics later in the week.", html)

    def test_stylesheet_url_changes_with_its_content(self):
        out = self.render()
        version = site.asset_version(site.ROOT / "static" / "styles.css")
        self.assertRegex(version, r"^[0-9a-f]{10}$")
        for page in out.rglob("*.html"):
            self.assertIn(f'static/styles.css?v={version}"', self.read(page), page)
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.css", Path(tmp) / "b.css"
            a.write_text("body{color:red}", encoding="utf-8")
            b.write_text("body{color:blue}", encoding="utf-8")
            self.assertNotEqual(site.asset_version(a), site.asset_version(b))

    def test_nav_methodology_heading_and_safety_label(self):
        out = self.render()
        home = self.read(out / "index.html")
        self.assertIn(">This Week</a>", home)
        self.assertIn("CLE / S</p>", home)
        self.assertNotIn("/ SAF", home)
        self.assertIn("<h1>Methodology</h1>", self.read(out / "methodology" / "index.html"))
        delpit = next(p for p in fixture_data.golden_edition()["players"] if p["name"] == "Grant Delpit")
        self.assertEqual(delpit["position"], "SAF")  # the data keeps the feed's code; only the display changes

    def test_eyebrows_match_the_share_card_style(self):
        edition = dict(fixture_data.golden_edition(), historical=True)
        out = self.render(edition)
        home = self.read(out / "index.html")
        self.assertIn("2026 Season · Week 2 Recap", home)
        self.assertIn("· Historical Replay", home)
        self.assertNotIn("Wednesday edition", home)
        self.assertIn("2026 Season · Week 2 Recap · Historical Replay", self.read(out / "archive" / "index.html"))

    def test_no_page_or_draft_claims_to_be_unaffiliated(self):
        # The author works at IMG Academy: the accurate claim is "not an official publication".
        out = self.render()
        for page in [*out.rglob("*.html"), *out.rglob("social-drafts.json")]:
            text = self.read(page).lower()
            self.assertNotIn("not affiliated", text, page)
            self.assertNotIn("works at img academy", text, page)
        footer = self.read(out / "index.html").split('<footer class="site-footer">')[1]
        self.assertIn("personal project", footer)
        self.assertIn("not an official IMG Academy publication", footer)
        card = (Path(site.ROOT) / "scripts" / "share_card.html").read_text(encoding="utf-8")
        self.assertIn("Not an official IMG Academy or NFL publication", card)
        self.assertIn("2026 Season · Weekly Recap", card)

    def test_cards_say_how_much_a_player_played_in_words(self):
        html = self.read(self.render() / "index.html")
        delpit = next(p for p in fixture_data.golden_edition()["players"] if p["name"] == "Grant Delpit")
        self.assertNotIn("Positive snap count", html)
        self.assertIn(f"Played {delpit['snaps']['defense']:g} defensive snaps", html)

    def test_participation_line(self):
        def player(snaps, metrics=(), label=ev.PLAYED, evidence="Positive snap count"):
            return {"snaps": snaps, "metrics": [{"label": m, "value": 1} for m in metrics], "availability": {"label": label, "evidence": evidence}}

        line = site.participation_line
        self.assertEqual(line(player({"defense": 47, "st": 2}, ["solo tackles"])), "Played 47 defensive snaps and 2 on special teams.")
        self.assertEqual(line(player({"offense": 40}, ["receiving yards"])), "Played 40 offensive snaps.")
        self.assertEqual(line(player({"offense": 3, "defense": 1, "st": 12}, ["solo tackles"])), "Played 3 offensive snaps, 1 defensive snap and 12 on special teams.")
        self.assertEqual(line(player({"st": 12}, ["solo tackles"])), "Played 12 special-teams snaps.")
        self.assertEqual(line(player({"offense": 68, "st": 4}, ["offensive snaps", "special-teams snaps"])), "")
        self.assertEqual(
            line(player({}, ["receiving yards"], evidence="Recorded play involvement")),
            "Recorded play involvement; snap counts not available.",
        )
        self.assertEqual(line(dict(player({"offense": 68}, ["offensive snaps"]), stats_withheld=True)), "Played 68 offensive snaps.")

    def test_linkedin_draft_is_first_person_and_states_independence(self):
        drafts = json.loads(self.read(self.render() / "editions" / "2026-week-02" / "social-drafts.json"))
        self.assertIn("Every week I track", drafts["linkedin"])
        self.assertIn("A personal project, not an official IMG Academy or NFL publication.", drafts["linkedin"])
        self.assertNotIn("participation evidence", drafts["linkedin"])

    def test_helpers(self):
        delpit = next(p for p in fixture_data.golden_edition()["players"] if p["name"] == "Grant Delpit")
        self.assertEqual(site.result_line(delpit), "W 23–19 vs. TB")
        self.assertEqual(site.initials("J.J. McCarthy"), "JM")
        self.assertIn("1 sack", site.contribution(delpit))

    def test_stylesheet_uses_img_academy_palette_and_team_colors_only_as_bars(self):
        css = (site.ROOT / "static" / "styles.css").read_text(encoding="utf-8")
        for token in ("--brand:#0057b8", "--navy:#002d54", "--ink:#424242", "--wash:#f5f5f5"):
            self.assertIn(token, css)
        self.assertNotIn("#f2f4ef", css)  # old off-white background
        self.assertNotIn("#cbdb2a", css.lower())  # green reserved for IMG Academy Youth Sport Camps
        team_uses = re.findall(r"([\w-]+):[^;{}]*var\(--team", css)
        self.assertTrue(team_uses)
        for prop in team_uses:
            self.assertTrue(prop.startswith("border"), f"team color used for {prop}")

    def test_pages_never_shorten_img_academy_to_img(self):
        out = self.render()
        for page in out.rglob("*.html"):
            text = re.sub(r"<[^>]+>", " ", page.read_text(encoding="utf-8"))
            self.assertIsNone(re.search(r"\bIMG\b(?!\s+Academy)", text, re.IGNORECASE), page.name)


import contextlib
import io


class PlayerPageTests(SiteTestCase):
    def test_every_registry_player_gets_pages(self):
        out = self.render()
        registry = load_registry(fixture_data.FIXTURES / "alumni.json")
        for alum in registry:
            self.assertTrue((out / "players" / alum["slug"] / "index.html").exists(), alum["name"])
            self.assertTrue((out / "players" / alum["slug"] / "2026-week-02" / "index.html").exists(), alum["name"])
        index = self.read(out / "players" / "index.html")
        self.assertIn("Defensive backs", index)
        self.assertIn('href="grant-delpit/"', index)

    def test_week_page_lists_every_recorded_play_with_diagrams(self):
        page = self.read(self.render() / "players" / "carnell-tate" / "2026-week-02" / "index.html")
        self.assertIn("Recorded plays (5)", page)
        self.assertEqual(page.count('class="play '), 5)
        self.assertIn('class="field field-medium"', page)
        self.assertIn("Expected points describe the whole play, not the player named on it.", page)
        self.assertIn("Positive plays for the Titans", page)
        self.assertIn("not a tracking diagram", page)

    def test_lineman_with_no_recorded_plays(self):
        page = self.read(self.render() / "players" / "tyler-booker" / "2026-week-02" / "index.html")
        self.assertIn("Recorded plays (0)", page)
        self.assertIn("Offensive linemen are rarely named in play-by-play", page)
        self.assertNotIn('class="field ', page)

    def test_play_without_epa_has_no_outcome_and_no_side(self):
        edition = fixture_data.golden_edition()
        tate = next(p for p in edition["players"] if p["name"] == "Carnell Tate")
        first_key = tate["key_plays"][0]["play_id"]  # key moments are listed first
        next(q for q in tate["plays"] if q["play_id"] == first_key)["epa"] = None
        page = self.read(self.render(edition) / "players" / "carnell-tate" / "2026-week-02" / "index.html")
        first = page.split('class="play ')[1].split("</li>")[0]
        self.assertIn('data-positive=""', first)
        self.assertNotIn("expected point", first)

    def test_schema_one_edition_renders_from_key_moments(self):
        edition = fixture_data.golden_edition()
        edition["schema_version"] = 1
        for p in edition["players"]:
            p.pop("plays", None)
        page = self.read(self.render(edition) / "players" / "grant-delpit" / "2026-week-02" / "index.html")
        self.assertIn("The full play list was not saved for this week", page)
        self.assertIn("Sack", page)

    def test_player_added_later_has_only_his_weeks(self):
        edition = fixture_data.golden_edition()
        delpit = next(p for p in edition["players"] if p["name"] == "Grant Delpit")
        edition["players"].remove(delpit)
        edition["featured_ranking"] = [pid for pid in edition["featured_ranking"] if pid != delpit["id"]]
        out = self.render(edition)
        self.assertTrue((out / "players" / "grant-delpit" / "index.html").exists())
        self.assertFalse((out / "players" / "grant-delpit" / "2026-week-02").exists())

    def test_evergreen_page_has_season_and_game_log(self):
        page = self.read(self.render() / "players" / "grant-delpit" / "index.html")
        for text in ("Grant Delpit", "CLE / S", "Season", "Impact plays", "Game log", 'href="2026-week-02/"', "See all", "Data as of"):
            self.assertIn(text, page)

    def test_up_next_appears_only_when_the_edition_has_it(self):
        edition = fixture_data.golden_edition()
        delpit = next(p for p in edition["players"] if p["name"] == "Grant Delpit")
        delpit["next_game"] = None
        self.assertNotIn("Up next", self.read(self.render(edition) / "players" / "grant-delpit" / "index.html"))
        delpit["next_game"] = {"kind": "game", "date": "2026-10-04", "kickoff_et": "13:00", "home_away": "away", "opponent": "PIT", "venue": "Acrisure Stadium", "team": "CLE", "team_name": "Cleveland Browns", "team_color": "#311D00", "week": 3}
        page = self.read(self.render(edition) / "players" / "grant-delpit" / "index.html")
        self.assertIn("Up next", page)
        self.assertIn("CLE at PIT · Sun, Oct 4 · 1:00 p.m. ET", page)
        edition["historical"] = True
        page = self.read(self.render(edition) / "players" / "grant-delpit" / "index.html")
        self.assertNotIn("Up next", page)  # a historical replay's next game is long past

    def test_evergreen_count_matches_week_page_on_schema_one(self):
        edition = fixture_data.golden_edition()
        edition["schema_version"] = 1
        for p in edition["players"]:
            p.pop("plays", None)
        out = self.render(edition)
        week = self.read(out / "players" / "grant-delpit" / "2026-week-02" / "index.html")
        count = re.search(r"Recorded plays \((\d+)\)", week)[1]
        self.assertNotEqual(count, "0")
        self.assertIn(f"See all {count} recorded plays", self.read(out / "players" / "grant-delpit" / "index.html"))

    def test_evergreen_header_has_monogram_and_college_line(self):
        page = self.read(self.render() / "players" / "grant-delpit" / "index.html")
        self.assertIn('<div class="monogram" aria-hidden="true">GD</div>', page)
        self.assertIn("LSU · 2020 draft, round 2", page)

    def test_week_page_for_a_week_not_played_shows_status_not_explorer(self):
        page = self.read(self.render() / "players" / "warren-brinson" / "2026-week-02" / "index.html")
        self.assertNotIn("Recorded plays", page)
        self.assertNotIn("explorer", page)
        self.assertIn("Inactive for the game", page)
        self.assertIn("Weekly roster status: inactive", page)

    def test_evergreen_latest_week_not_played_shows_status(self):
        page = self.read(self.render() / "players" / "jj-mccarthy" / "index.html")
        self.assertNotIn("See all", page)
        self.assertNotIn('class="top-play"', page)
        self.assertIn("No snaps recorded", page)
        self.assertIn("Reason not established by snap counts", page)

    def test_play_description_is_escaped_but_diagram_is_markup(self):
        edition = fixture_data.golden_edition()
        tate = next(p for p in edition["players"] if p["name"] == "Carnell Tate")
        tate["plays"][1]["description"] = '<script>alert("x")</script>'
        page = self.read(self.render(edition) / "players" / "carnell-tate" / "2026-week-02" / "index.html")
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn('<svg class="field field-medium"', page)
        self.assertNotIn("&lt;svg", page)

    def test_nav_links_players_and_the_site_passes_its_checks(self):
        out = self.render()
        self.assertIn(">Players</a>", self.read(out / "index.html"))
        self.assertEqual(site.check_site(out, site.load_editions(self.editions)), [])
        self.assertIn("players/grant-delpit/", self.read(out / "sitemap.xml"))


class CheckTests(SiteTestCase):
    def test_rendered_site_passes_its_checks(self):
        out = self.render()
        self.assertEqual(site.check_site(out, site.load_editions(self.editions)), [])

    def test_broken_link_is_reported(self):
        out = self.render()
        page = out / "archive" / "index.html"
        page.write_text(page.read_text(encoding="utf-8") + '<a href="../missing/">x</a>', encoding="utf-8")
        self.assertTrue(any("missing" in p for p in site.check_site(out, site.load_editions(self.editions))))

    def test_missing_edition_id_is_reported(self):
        out = self.render()
        (out / "index.html").write_text("<html></html>", encoding="utf-8")
        self.assertIn("index.html does not show the latest edition", site.check_site(out, site.load_editions(self.editions)))

    def test_cli_build_check_and_latest_id(self):
        out = self.render()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(site.main(["build", "--out", str(out), "--editions", str(self.editions), "--check"]), 0)
        self.assertIn("Rendered ", output.getvalue())
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            site.main(["latest-id", "--editions", str(self.editions)])
        self.assertEqual(buffer.getvalue().strip(), "2026-week-02")


if __name__ == "__main__":
    unittest.main()
