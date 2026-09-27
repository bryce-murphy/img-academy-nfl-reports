import unittest

from src import verify

URL = "https://bryce-murphy.github.io/img-academy-nfl-reports/"


def page(edition_id):
    return f'<html><head><meta name="edition-id" content="{edition_id}"></head></html>'


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


if __name__ == "__main__":
    unittest.main()
