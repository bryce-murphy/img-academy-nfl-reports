"""Minimal GitHub REST and GraphQL client for the edition pipeline. Standard library only."""
from __future__ import annotations

import base64
import json
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

API = "https://api.github.com"


class GitHubError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(f"GitHub API returned {status}: {message}")
        self.status = status


class _RefuseRedirects(HTTPRedirectHandler):
    """Never follow redirects: a 3xx would resend the Authorization header to the new location."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = build_opener(_RefuseRedirects)


def urllib_transport(method, url, headers, body):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise GitHubError(0, f"refusing a non-GitHub URL {url}")
    request = Request(url, data=body, method=method, headers=headers)
    try:
        with _OPENER.open(request, timeout=60) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


class GitHub:
    def __init__(self, token, repo, transport=urllib_transport):
        self.token = token
        self.repo = repo
        self.owner = repo.split("/")[0]
        self.transport = transport

    def call(self, method, path, payload=None, *, missing_ok=False):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "img-academy-nfl-reports",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        status, raw = self.transport(method, API + path, headers, body)
        if status == 404 and missing_ok:
            return None
        if status >= 300:
            raise GitHubError(status, raw[:300].decode("utf-8", "replace"))
        return json.loads(raw) if raw else {}

    def _repo(self, suffix):
        return f"/repos/{self.repo}{suffix}"

    def ref_sha(self, branch):
        data = self.call("GET", self._repo(f"/git/ref/heads/{quote(branch)}"), missing_ok=True)
        return data["object"]["sha"] if data else None

    def create_branch(self, branch, sha):
        self.call("POST", self._repo("/git/refs"), {"ref": f"refs/heads/{branch}", "sha": sha})

    def file_exists(self, path, ref):
        return self.call("GET", self._repo(f"/contents/{quote(path)}?ref={quote(ref, safe='')}"), missing_ok=True) is not None

    def read_file(self, path, ref):
        data = self.call("GET", self._repo(f"/contents/{quote(path)}?ref={quote(ref, safe='')}"), missing_ok=True)
        return None if data is None else base64.b64decode(data["content"]).decode("utf-8")

    def graphql(self, query, variables):
        result = self.call("POST", "/graphql", {"query": query, "variables": variables})
        if result.get("errors"):
            raise GitHubError(200, json.dumps(result["errors"])[:300])
        return result["data"]

    def commit_files(self, branch, expected_head, files, headline, body=""):
        """Commit through createCommitOnBranch so GitHub signs the commit (shown as Verified)."""
        query = "mutation($input: CreateCommitOnBranchInput!) { createCommitOnBranch(input: $input) { commit { oid } } }"
        additions = [{"path": path, "contents": base64.b64encode(content).decode("ascii")} for path, content in sorted(files.items())]
        variables = {"input": {
            "branch": {"repositoryNameWithOwner": self.repo, "branchName": branch},
            "message": {"headline": headline, "body": body},
            "expectedHeadOid": expected_head,
            "fileChanges": {"additions": additions},
        }}
        return self.graphql(query, variables)["createCommitOnBranch"]["commit"]["oid"]

    def find_pr(self, branch):
        prs = self.call("GET", self._repo(f"/pulls?{urlencode({'state': 'open', 'head': f'{self.owner}:{branch}'})}"))
        return prs[0] if prs else None

    def open_prs(self):
        return self.call("GET", self._repo("/pulls?state=open&per_page=100"))

    def open_pr(self, branch, title, body, base="main"):
        return self.call("POST", self._repo("/pulls"), {"title": title, "head": branch, "base": base, "body": body})

    def update_pr(self, number, body, title=None):
        self.call("PATCH", self._repo(f"/pulls/{number}"), {"body": body, **({"title": title} if title else {})})

    def request_review(self, number, reviewers):
        self.call("POST", self._repo(f"/pulls/{number}/requested_reviewers"), {"reviewers": list(reviewers)})

    def comment(self, number, body):
        self.call("POST", self._repo(f"/issues/{number}/comments"), {"body": body})

    def branch_authors(self, branch, base="main"):
        data = self.call("GET", self._repo(f"/compare/{quote(base)}...{quote(branch)}"))
        authors = set()
        for commit in data.get("commits", []):
            author = commit.get("author") or {}
            authors.add(author.get("login") or commit["commit"]["author"].get("email", "unknown"))
        return authors

    def ensure_label(self, name, color="b60205"):
        if self.call("GET", self._repo(f"/labels/{quote(name)}"), missing_ok=True) is None:
            self.call("POST", self._repo("/labels"), {"name": name, "color": color})

    def find_issue(self, title, label):
        items = self.call("GET", self._repo(f"/issues?{urlencode({'state': 'open', 'labels': label, 'per_page': 100})}"))
        return next((item for item in items if item["title"] == title and "pull_request" not in item), None)

    def upsert_issue(self, title, body, label):
        existing = self.find_issue(title, label)
        if existing:
            self.call("PATCH", self._repo(f"/issues/{existing['number']}"), {"body": body})
            return existing["number"]
        self.ensure_label(label)
        return self.call("POST", self._repo("/issues"), {"title": title, "body": body, "labels": [label]})["number"]

    def close_issue(self, number, comment):
        self.comment(number, comment)
        self.call("PATCH", self._repo(f"/issues/{number}"), {"state": "closed"})
