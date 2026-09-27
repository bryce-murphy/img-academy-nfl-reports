import copy
import json
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

    def test_helpers(self):
        delpit = next(p for p in fixture_data.golden_edition()["players"] if p["name"] == "Grant Delpit")
        self.assertEqual(site.result_line(delpit), "W 23–19 vs. TB")
        self.assertEqual(site.initials("J.J. McCarthy"), "JM")
        self.assertIn("1 sack", site.contribution(delpit))


if __name__ == "__main__":
    unittest.main()
