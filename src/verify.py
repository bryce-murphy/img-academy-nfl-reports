"""Confirm the deployed site serves the expected edition. Used by .github/workflows/pages.yml."""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .github import GitHub

ALLOWED_HOSTS = {"bryce-murphy.github.io"}
META = re.compile(r'<meta name="edition-id" content="([^"]+)">')


def _check_host(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"Refusing to verify {url}")


def fetch(url):
    _check_host(url)
    request = Request(url, headers={"User-Agent": "img-academy-nfl-reports", "Cache-Control": "no-cache"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def served_edition(html):
    match = META.search(html)
    return match.group(1) if match else None


def wait_for(url, expected, *, fetch_fn=fetch, sleep=time.sleep, attempts=15, delay=20):
    _check_host(url)
    detail = "no response"
    for attempt in range(attempts):
        try:
            served = served_edition(fetch_fn(f"{url}?verify={attempt}"))
        except OSError as exc:
            detail = f"{type(exc).__name__}: {exc}"
        else:
            if served == expected:
                return True, f"serving {served}"
            detail = f"serving {served or 'no edition id'}"
        if attempt < attempts - 1:
            sleep(delay)
    return False, detail


def main(argv=None, *, github_factory=GitHub):
    parser = argparse.ArgumentParser(prog="python -m src.verify")
    parser.add_argument("--url", required=True)
    parser.add_argument("--edition", required=True)
    args = parser.parse_args(argv)
    ok, detail = wait_for(args.url, args.edition)
    print(f"{'Verified' if ok else 'Not verified'}: {args.url} ({detail})")
    token = os.environ.get("GITHUB_TOKEN")
    if ok:
        if token:
            gh = github_factory(token, os.environ["GITHUB_REPOSITORY"])
            issue = gh.find_issue("Site deployment not verified", "edition-blocked")
            if issue:
                gh.close_issue(issue["number"], f"Resolved: the site now serves {args.edition}.")
        return 0
    if token:
        body = f"Expected edition `{args.edition}` at {args.url}; last check: {detail}.\n\nRun: {os.environ.get('RUN_URL', '')}"
        github_factory(token, os.environ["GITHUB_REPOSITORY"]).upsert_issue("Site deployment not verified", body, "edition-blocked")
    return 1


if __name__ == "__main__":
    sys.exit(main())
