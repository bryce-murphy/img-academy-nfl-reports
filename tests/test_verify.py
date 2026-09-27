import os
import unittest
from unittest import mock

from src import verify

URL = "https://bryce-murphy.github.io/img-academy-nfl-reports/"


def page(edition_id):
    return f'<html><head><meta name="edition-id" content="{edition_id}"></head></html>'


class FakeGitHub:
    def __init__(self, token, repo, issue=None):
        self.token, self.repo, self.issue = token, repo, issue
        self.closed = []

    def find_issue(self, title, label):
        return self.issue if self.issue and self.issue["title"] == title and label == "edition-blocked" else None

    def close_issue(self, number, comment):
        self.closed.append((number, comment))

    def upsert_issue(self, title, body, label):
        pass


class VerifyTests(unittest.TestCase):
    def test_served_edition(self):
        self.assertEqual(verify.served_edition(page("2026-week-03")), "2026-week-03")
        self.assertIsNone(verify.served_edition("<html></html>"))

    def test_waits_until_the_new_edition_appears(self):
        pages = iter([page("2026-week-02"), page("2026-week-03")])
        sleeps, urls = [], []

        def fetch(url):
            urls.append(url)
            return next(pages)

        ok, detail = verify.wait_for(URL, "2026-week-03", fetch_fn=fetch, sleep=sleeps.append, attempts=3, delay=5)
        self.assertTrue(ok)
        self.assertEqual(sleeps, [5])
        self.assertEqual(urls[0], URL + "?verify=0")

    def test_gives_up_with_the_last_observation(self):
        ok, detail = verify.wait_for(URL, "2026-week-03", fetch_fn=lambda url: page("2026-week-02"), sleep=lambda s: None, attempts=2, delay=0)
        self.assertFalse(ok)
        self.assertIn("2026-week-02", detail)

    def test_network_errors_are_retried(self):
        calls = []

        def flaky(url):
            calls.append(url)
            if len(calls) == 1:
                raise OSError("connection reset")
            return page("2026-week-03")

        ok, _ = verify.wait_for(URL, "2026-week-03", fetch_fn=flaky, sleep=lambda s: None, attempts=3, delay=0)
        self.assertTrue(ok)

    def test_other_hosts_are_refused(self):
        with self.assertRaises(ValueError):
            verify.wait_for("https://evil.example/", "x", fetch_fn=lambda url: "", sleep=lambda s: None)


class MainClosesBlockingIssueTests(unittest.TestCase):
    def run_main(self, gh, fetch_fn):
        factory = lambda token, repo: gh
        env = {"GITHUB_TOKEN": "tok", "GITHUB_REPOSITORY": "bryce-murphy/img-academy-nfl-reports"}
        with mock.patch.object(verify, "wait_for", lambda url, expected, **kw: (fetch_fn(),  "detail")):
            with mock.patch.dict(os.environ, env, clear=False):
                return verify.main(["--url", URL, "--edition", "2026-week-03"], github_factory=factory)

    def test_successful_verification_closes_an_open_blocking_issue(self):
        gh = FakeGitHub("tok", "repo", issue={"number": 9, "title": "Site deployment not verified"})
        code = self.run_main(gh, lambda: True)
        self.assertEqual(code, 0)
        self.assertEqual(gh.closed, [(9, "Resolved: the site now serves 2026-week-03.")])

    def test_successful_verification_without_a_blocking_issue_does_nothing(self):
        gh = FakeGitHub("tok", "repo", issue=None)
        code = self.run_main(gh, lambda: True)
        self.assertEqual(code, 0)
        self.assertEqual(gh.closed, [])

    def test_failed_verification_does_not_close_anything(self):
        gh = FakeGitHub("tok", "repo", issue={"number": 9, "title": "Site deployment not verified"})
        code = self.run_main(gh, lambda: False)
        self.assertEqual(code, 1)
        self.assertEqual(gh.closed, [])


if __name__ == "__main__":
    unittest.main()
