import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

import fixture_data
from src import editorial, site
from src import evidence as ev

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
        site.build_site(out, self.editions, CONFIG)
        return out

    @staticmethod
    def read(path):
        return path.read_text(encoding="utf-8")


class RenderTests(SiteTestCase):
    def test_homepage_is_the_latest_edition(self):
        html = self.read(self.render() / "index.html")
        self.assertIn('<meta name="edition-id" content="2026-week-02">', html)
        self.assertIn("IMG Academy → NFL", html)
        self.assertIn("Not affiliated with IMG Academy or the NFL", html)

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

    def test_helpers(self):
        delpit = next(p for p in fixture_data.golden_edition()["players"] if p["name"] == "Grant Delpit")
        self.assertEqual(site.result_line(delpit), "W 23–19 vs. TB")
        self.assertEqual(site.initials("J.J. McCarthy"), "JM")
        self.assertIn("1 sack", site.contribution(delpit))

    def test_stylesheet_uses_img_palette_and_team_colors_only_as_bars(self):
        css = (site.ROOT / "static" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("--brand:#0057b8", css)
        self.assertIn("--navy:#003057", css)
        self.assertNotIn("#f2f4ef", css)
        team_uses = re.findall(r"([\w-]+):[^;{}]*var\(--team", css)
        self.assertTrue(team_uses)
        for prop in team_uses:
            self.assertTrue(prop.startswith("border"), f"team color used for {prop}")

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
        self.assertEqual(site.main(["build", "--out", str(out), "--editions", str(self.editions), "--check"]), 0)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            site.main(["latest-id", "--editions", str(self.editions)])
        self.assertEqual(buffer.getvalue().strip(), "2026-week-02")


if __name__ == "__main__":
    unittest.main()
