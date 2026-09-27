import unittest
from copy import deepcopy

import fixture_data
from src import editorial, pipeline
from src.pipeline import Settings

CFG = {
    "scheduled_reports_enabled": True,
    "season_types": ["REG", "WC", "DIV", "CON", "SB"],
    "registry_reviewed_season": 2026,
    "owner_github": "bryce-murphy",
    "site_url": "https://bryce-murphy.github.io/img-academy-nfl-reports/",
    "editorial_model": "claude-opus-5-5",
}
FIRST = "30 14 * 9-12,1-2 2"
FINAL = "30 6 * 9-12,1-2 3"
BOT = "edition-bot[bot]"


class FakeGitHub:
    def __init__(self, *, on_main=False, pr=None, authors=(), issue=None, open_prs=(), branch_file=None):
        self.on_main, self.pr, self.authors, self.issue = on_main, pr, set(authors), issue
        self._open_prs, self.branch_file = list(open_prs), branch_file
        self.refs = {"main": "main-sha"}
        self.commits, self.opened, self.updated, self.reviews = [], [], [], []
        self.upserts, self.closed, self.comments = [], [], []

    def file_exists(self, path, ref):
        return self.on_main

    def find_pr(self, branch):
        return self.pr

    def branch_authors(self, branch, base="main"):
        return self.authors

    def read_file(self, path, ref):
        return self.branch_file

    def ref_sha(self, branch):
        return self.refs.get(branch)

    def create_branch(self, branch, sha):
        self.refs[branch] = sha

    def commit_files(self, branch, head, files, headline, body=""):
        self.commits.append((branch, head, dict(files)))
        return "new-sha"

    def open_pr(self, branch, title, body, base="main"):
        self.opened.append((branch, title, body))
        return {"number": 42}

    def update_pr(self, number, body):
        self.updated.append((number, body))

    def request_review(self, number, reviewers):
        self.reviews.append((number, list(reviewers)))

    def find_issue(self, title, label):
        return self.issue if self.issue and self.issue["title"] == title else None

    def upsert_issue(self, title, body, label):
        self.upserts.append((title, body, label))
        return 7

    def close_issue(self, number, comment):
        self.closed.append((number, comment))

    def open_prs(self):
        return self._open_prs

    def comment(self, number, body):
        self.comments.append((number, body))


def sources_from(data, manifest):
    def sources(season, *, week=None, only=None, historical=False):
        if only:
            return {key: data[key] for key in only}, {}, []
        return data, manifest, []
    return sources


def template_drafter(edition):
    return editorial.fallback(edition), {"used": "fallback", "reasons": ["test drafter"], "rejected": None, "notes": []}


def without_end_of_game(data):
    data = deepcopy(data)
    data["pbp"] = [p for p in data["pbp"] if p["desc"].strip().upper() != "END GAME"]
    return data


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.data, self.manifest, self.registry = fixture_data.load()

    def attempt(self, gh, settings=None, data=None, cfg=None):
        settings = settings or Settings(event="schedule", schedule=FIRST, automation="on", run_url="https://run", bot_login=BOT)
        return pipeline.run_attempt(
            settings, gh=gh, cfg=cfg or CFG, registry=self.registry, today=fixture_data.TODAY,
            sources=sources_from(data or self.data, self.manifest), drafter=template_drafter,
        )

    def test_kill_switch(self):
        self.assertEqual(self.attempt(FakeGitHub(), Settings(event="schedule", schedule=FIRST, automation="off")).state, "disabled")

    def test_scheduled_runs_need_the_config_flag(self):
        self.assertEqual(self.attempt(FakeGitHub(), cfg=dict(CFG, scheduled_reports_enabled=False)).state, "disabled")

    def test_opens_a_pr_with_three_files_and_requests_review(self):
        gh = FakeGitHub()
        outcome = self.attempt(gh)
        self.assertEqual((outcome.state, outcome.number), ("opened", 42))
        branch, head, files = gh.commits[0]
        self.assertEqual((branch, head), ("edition/2026-week-02", "main-sha"))
        self.assertEqual(sorted(files), [
            "editions/2026-week-02/edition.json", "editions/2026-week-02/editorial.toml", "editions/2026-week-02/sources.json",
        ])
        self.assertEqual(gh.reviews, [(42, ["bryce-murphy"])])
        title, body = gh.opened[0][1], gh.opened[0][2]
        self.assertTrue(title.startswith("Edition 2026 Week 2: "))
        self.assertIn("How to approve", body)
        self.assertIn("test drafter", body)

    def test_published_edition_is_not_rebuilt(self):
        gh = FakeGitHub(on_main=True)
        self.assertEqual(self.attempt(gh).state, "published")
        self.assertEqual(gh.commits, [])

    def test_existing_pr_is_left_alone(self):
        gh = FakeGitHub(pr={"number": 9})
        outcome = self.attempt(gh)
        self.assertEqual((outcome.state, outcome.number), ("pending", 9))
        self.assertEqual(gh.commits, [])

    def test_refresh_keeps_owner_headline(self):
        owner_copy = editorial.dumps(dict(editorial.fallback(fixture_data.golden_edition()), headline="Owner headline", source="owner"))
        gh = FakeGitHub(pr={"number": 9}, authors={BOT, "bryce-murphy"}, branch_file=owner_copy)
        gh.refs["edition/2026-week-02"] = "branch-sha"
        settings = Settings(event="workflow_dispatch", refresh=True, week=2, automation="on", bot_login=BOT)
        self.assertEqual(self.attempt(gh, settings).state, "opened")
        branch, head, files = gh.commits[0]
        self.assertEqual(head, "branch-sha")
        self.assertNotIn("editions/2026-week-02/editorial.toml", files)
        self.assertIn("Owner headline", gh.updated[0][1])

    def test_missing_data_waits_on_early_attempts(self):
        gh = FakeGitHub()
        outcome = self.attempt(gh, data=without_end_of_game(self.data))
        self.assertEqual(outcome.state, "waiting")
        self.assertFalse(outcome.failed)
        self.assertEqual(gh.upserts, [])

    def test_final_attempt_with_missing_data_opens_blocking_issue(self):
        gh = FakeGitHub()
        settings = Settings(event="schedule", schedule=FINAL, automation="on", run_url="https://run")
        outcome = self.attempt(gh, settings, data=without_end_of_game(self.data))
        self.assertTrue(outcome.failed)
        self.assertEqual(gh.upserts[0][0], "Edition 2026-week-02 blocked")
        self.assertEqual(gh.upserts[0][2], "edition-blocked")
        self.assertIn("https://run", gh.upserts[0][1])
        self.assertEqual(gh.commits, [])

    def test_unscored_game_on_final_attempt_blocks_that_week(self):
        data = deepcopy(self.data)
        for game in data["schedule"]:
            if game["week"] == "2" and game["home_team"] == "CHI":
                game["home_score"] = ""
        gh = FakeGitHub()
        self.attempt(gh, Settings(event="schedule", schedule=FINAL, automation="on"), data=data)
        self.assertEqual(gh.upserts[0][0], "Edition 2026-week-02 blocked")

    def test_validation_failure_blocks(self):
        data = deepcopy(self.data)
        next(p for p in data["pbp"] if p["desc"].strip().upper() == "END GAME")["total_home_score"] = "99"
        gh = FakeGitHub()
        outcome = self.attempt(gh, data=data)
        self.assertTrue(outcome.failed)
        self.assertIn("Final score disagreement", gh.upserts[0][1])

    def test_success_closes_a_blocking_issue(self):
        gh = FakeGitHub(issue={"number": 5, "title": "Edition 2026-week-02 blocked"})
        self.attempt(gh)
        self.assertEqual(gh.closed[0][0], 5)

    def test_reminder_mentions_the_owner_on_edition_prs_only(self):
        gh = FakeGitHub(open_prs=[{"number": 42, "head": {"ref": "edition/2026-week-02"}}, {"number": 3, "head": {"ref": "feat/other"}}])
        self.assertEqual(pipeline.remind(gh, "bryce-murphy").state, "reminded")
        self.assertEqual([number for number, _ in gh.comments], [42])
        self.assertIn("@bryce-murphy", gh.comments[0][1])

    def test_settings_from_env(self):
        settings = pipeline.settings_from_env({"EVENT_NAME": "schedule", "SCHEDULE": FINAL, "EDITION_AUTOMATION": "on", "APP_SLUG": "edition-bot", "INPUT_WEEK": ""})
        self.assertEqual((settings.attempt, settings.week, settings.bot_login), (3, None, BOT))
        with self.assertRaises(SystemExit):
            pipeline.settings_from_env({"INPUT_WEEK": "3; rm -rf /"})


if __name__ == "__main__":
    unittest.main()
