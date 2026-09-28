import base64
import json
import unittest

from src.github import GitHub, GitHubError, urllib_transport, _RefuseRedirects


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, method, url, headers, body):
        self.requests.append({"method": method, "url": url, "headers": headers, "json": json.loads(body) if body else None})
        status, payload = self.responses.pop(0)
        return status, b"" if payload is None else json.dumps(payload).encode()


def client(*responses):
    transport = FakeTransport(*responses)
    return GitHub("token-123", "bryce-murphy/img-academy-nfl-reports", transport), transport


class GitHubTests(unittest.TestCase):
    def test_missing_branch_returns_none(self):
        gh, transport = client((404, {"message": "Not Found"}))
        self.assertIsNone(gh.ref_sha("edition/2026-week-03"))
        self.assertTrue(transport.requests[0]["url"].endswith("/repos/bryce-murphy/img-academy-nfl-reports/git/ref/heads/edition/2026-week-03"))
        self.assertEqual(transport.requests[0]["headers"]["Authorization"], "Bearer token-123")

    def test_create_branch_payload(self):
        gh, transport = client((201, {}))
        gh.create_branch("edition/2026-week-03", "abc")
        self.assertEqual(transport.requests[0]["json"], {"ref": "refs/heads/edition/2026-week-03", "sha": "abc"})

    def test_commit_files_uses_verified_graphql_commit(self):
        gh, transport = client((200, {"data": {"createCommitOnBranch": {"commit": {"oid": "new"}}}}))
        oid = gh.commit_files("edition/x", "head", {"editions/x/a.json": b"{}"}, "Edition x")
        self.assertEqual(oid, "new")
        variables = transport.requests[0]["json"]["variables"]["input"]
        self.assertEqual(variables["expectedHeadOid"], "head")
        self.assertEqual(variables["branch"]["branchName"], "edition/x")
        self.assertEqual(base64.b64decode(variables["fileChanges"]["additions"][0]["contents"]), b"{}")

    def test_graphql_errors_raise(self):
        gh, _ = client((200, {"errors": [{"message": "stale head"}]}))
        with self.assertRaises(GitHubError):
            gh.graphql("query", {})

    def test_find_pr_filters_by_head(self):
        gh, transport = client((200, [{"number": 5}]))
        self.assertEqual(gh.find_pr("edition/2026-week-03")["number"], 5)
        self.assertIn("head=bryce-murphy%3Aedition%2F2026-week-03", transport.requests[0]["url"])

    def test_upsert_issue_creates_label_and_issue(self):
        gh, transport = client((200, []), (404, None), (201, {}), (201, {"number": 12}))
        self.assertEqual(gh.upsert_issue("Edition x blocked", "body", "edition-blocked"), 12)
        self.assertEqual([r["method"] for r in transport.requests], ["GET", "GET", "POST", "POST"])
        self.assertEqual(transport.requests[3]["json"]["labels"], ["edition-blocked"])

    def test_upsert_issue_updates_existing(self):
        gh, transport = client((200, [{"number": 3, "title": "Edition x blocked"}]), (200, {}))
        self.assertEqual(gh.upsert_issue("Edition x blocked", "new body", "edition-blocked"), 3)
        self.assertEqual((transport.requests[1]["method"], transport.requests[1]["json"]), ("PATCH", {"body": "new body"}))

    def test_update_pr_sends_title_and_body(self):
        gh, transport = client((200, {}))
        gh.update_pr(9, "new body", title="Edition 2026 Week 2: New headline")
        self.assertEqual((transport.requests[0]["method"], transport.requests[0]["json"]), ("PATCH", {"body": "new body", "title": "Edition 2026 Week 2: New headline"}))

    def test_branch_authors(self):
        gh, _ = client((200, {"commits": [{"author": {"login": "edition-bot[bot]"}}, {"author": None, "commit": {"author": {"email": "x@example.org"}}}]}))
        self.assertEqual(gh.branch_authors("edition/x"), {"edition-bot[bot]", "x@example.org"})

    def test_read_file_decodes_content(self):
        gh, _ = client((200, {"content": base64.b64encode(b"headline").decode()}))
        self.assertEqual(gh.read_file("editions/x/editorial.toml", "edition/x"), "headline")

    def test_server_errors_raise(self):
        gh, _ = client((500, {"message": "boom"}))
        with self.assertRaises(GitHubError) as ctx:
            gh.open_prs()
        self.assertEqual(ctx.exception.status, 500)

    def test_transport_refuses_other_hosts(self):
        with self.assertRaises(GitHubError):
            urllib_transport("GET", "https://example.org/repos", {}, None)

    def test_redirects_are_never_followed(self):
        self.assertIsNone(_RefuseRedirects().redirect_request(None, None, 302, "Found", {}, "https://evil.example/"))

    def test_transport_refuses_plain_http(self):
        with self.assertRaises(GitHubError):
            urllib_transport("GET", "http://api.github.com/repos", {}, None)

    def test_redirect_status_is_an_error(self):
        gh, _ = client((302, {"message": "Moved"}))
        with self.assertRaises(GitHubError) as ctx:
            gh.open_prs()
        self.assertEqual(ctx.exception.status, 302)


if __name__ == "__main__":
    unittest.main()
