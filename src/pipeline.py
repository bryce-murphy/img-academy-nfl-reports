"""One automated attempt at this week's edition. Called by .github/workflows/edition.yml."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from . import editorial
from .data import utcnow
from .edition import build_week, due_week, dump_json, edition_id, fetch, load_config, load_registry
from .errors import DataError, NotReady
from .github import GitHub
from .site import contribution, result_line, social_drafts

ATTEMPTS = {"30 14 * 9-12,1-2 2": 1, "30 20 * 9-12,1-2 2": 2, "30 6 * 9-12,1-2 3": 3}
FINAL_ATTEMPT = 3
REMINDER = "0 9 * 9-12,1-2 3"
BLOCKED_LABEL = "edition-blocked"
SEASON_MONTHS = {9, 10, 11, 12, 1, 2}
FENCE = "`" * 3
FENCE4 = "`" * 4


@dataclass
class Settings:
    event: str = "workflow_dispatch"
    schedule: str = ""
    season: int | None = None
    week: int | None = None
    final: bool = False
    refresh: bool = False
    historical: bool = False
    automation: str = ""
    run_url: str = ""
    bot_login: str = ""

    @property
    def attempt(self):
        return ATTEMPTS.get(self.schedule, 0)


@dataclass
class Outcome:
    state: str
    message: str
    failed: bool = False
    number: int | None = None


def _optional_int(env, key):
    value = env.get(key, "").strip()
    if not value:
        return None
    if not value.isdigit():
        raise SystemExit(f"{key} must contain digits only")
    return int(value)


def settings_from_env(env):
    return Settings(
        event=env.get("EVENT_NAME", ""),
        schedule=env.get("SCHEDULE", ""),
        season=_optional_int(env, "INPUT_SEASON"),
        week=_optional_int(env, "INPUT_WEEK"),
        final=env.get("INPUT_FINAL") == "true",
        refresh=env.get("INPUT_REFRESH") == "true",
        historical=env.get("INPUT_HISTORICAL") == "true",
        automation=env.get("EDITION_AUTOMATION", ""),
        run_url=env.get("RUN_URL", ""),
        bot_login=f"{env.get('APP_SLUG', '')}[bot]",
    )


def block(gh, eid, step, reason, settings):
    body = "\n".join([
        f"**Step:** {step}", "", f"**Reason:** {reason}", "", f"**Run:** {settings.run_url}", "",
        "Next: fix the cause, then run **Actions → Weekly edition → Run workflow**, or wait for the next scheduled attempt.",
        "The site keeps showing the last published edition until this one is approved.",
    ])
    gh.upsert_issue(f"Edition {eid} blocked", body, BLOCKED_LABEL)
    return Outcome("blocked", reason, failed=True)


def not_ready(gh, eid, reason, final, settings):
    if not final:
        return Outcome("waiting", reason)
    return block(gh, eid, "Data readiness", f"Still not ready on the final attempt. {reason}", settings)


def default_drafter(cfg):
    return lambda edition: editorial.produce(edition, model=cfg["editorial_model"])


def run_attempt(settings, *, gh, cfg, registry, today, sources=fetch, drafter=None):
    s = settings
    if s.automation != "on":
        return Outcome("disabled", "Repository variable EDITION_AUTOMATION is not 'on'.")
    scheduled = s.event == "schedule"
    if scheduled and not cfg["scheduled_reports_enabled"]:
        return Outcome("disabled", "config.json scheduled_reports_enabled is false.")
    if scheduled and today.month not in SEASON_MONTHS:
        return Outcome("skipped", "Outside the September–February season window.")
    season = s.season or (today.year if today.month >= 3 else today.year - 1)
    final = s.final or s.attempt >= FINAL_ATTEMPT
    try:
        week, games = due_week(season, s.week, today=today, historical=s.historical, scheduled=scheduled, season_types=cfg["season_types"], sources=sources)
    except NotReady as exc:
        return not_ready(gh, edition_id(season, exc.week) if exc.week else str(season), str(exc), final, s)
    except DataError as exc:
        if scheduled and str(exc) == "No completed reporting window":
            return Outcome("skipped", str(exc))
        return not_ready(gh, str(season), str(exc), final, s)
    if week is None:
        return Outcome("skipped", "No NFL week finished in the last seven days.")
    eid = edition_id(season, week)
    stale = None if s.historical else gh.find_issue(f"Edition {season} blocked", BLOCKED_LABEL)
    if stale:  # opened by an earlier live schedule failure, before any week was known; replays can't vouch for it
        gh.close_issue(stale["number"], f"Resolved: the schedule loaded and edition {eid} is due.")
    if gh.file_exists(f"editions/{eid}/edition.json", "main"):
        issue = gh.find_issue(f"Edition {eid} blocked", BLOCKED_LABEL)
        if issue:
            gh.close_issue(issue["number"], f"Resolved: edition {eid} is published on main.")
        return Outcome("published", f"Edition {eid} is already on main.")
    branch = f"edition/{eid}"
    pr = gh.find_pr(branch)
    if pr and not s.refresh:
        return Outcome("pending", f"Edition {eid} is waiting for approval in #{pr['number']}.", number=pr["number"])
    if scheduled and cfg["registry_reviewed_season"] != season:
        return block(gh, eid, "Registry review", f"data/alumni.json was last reviewed for {cfg['registry_reviewed_season']}; review it for {season} and update config.json.", s)
    try:
        edition, manifest, report = build_week(season, week, games, historical=s.historical, final=final, registry=registry, sources=sources)
    except NotReady as exc:
        return not_ready(gh, eid, str(exc), final, s)
    except DataError as exc:
        step = "Data sources" if str(exc).startswith(("Cannot verify", "Stale source")) else "Validation"
        return block(gh, eid, step, str(exc), s)
    files = {f"editions/{eid}/edition.json": dump_json(edition), f"editions/{eid}/sources.json": dump_json(manifest, sort_keys=True)}
    head = gh.ref_sha(branch)
    if (pr or head is not None) and gh.branch_authors(branch) - {s.bot_login}:
        copy = editorial.loads(gh.read_file(f"editions/{eid}/editorial.toml", branch))
        draft_report = {"used": "owner edits kept", "reasons": [], "rejected": None, "notes": []}
    else:
        copy, draft_report = (drafter or default_drafter(cfg))(edition)
        files[f"editions/{eid}/editorial.toml"] = editorial.dumps(copy).encode("utf-8")
    if head is None:
        head = gh.ref_sha("main")
        gh.create_branch(branch, head)
    gh.commit_files(branch, head, files, f"Edition {season} Week {week}: data and headline draft")
    drafts = social_drafts(edition, copy, f"{cfg['site_url']}editions/{eid}/")
    body = pr_body(edition, copy, draft_report, report, drafts, s.run_url)
    title = f"Edition {season} Week {week}: {copy['headline']}"
    if pr:
        number = pr["number"]
        gh.update_pr(number, body, title=title)
    else:
        number = gh.open_pr(branch, title, body)["number"]
        gh.request_review(number, [cfg["owner_github"]])
    issue = gh.find_issue(f"Edition {eid} blocked", BLOCKED_LABEL)
    if issue:
        gh.close_issue(issue["number"], f"Resolved: the edition is ready for approval in #{number}.")
    return Outcome("opened", f"Edition {eid} is ready for approval in #{number}.", number=number)


def remind(gh, owner):
    pending = [pr for pr in gh.open_prs() if pr["head"]["ref"].startswith("edition/")]
    for pr in pending:
        gh.comment(pr["number"], f"@{owner} Reminder: this edition is waiting for your approval. The site keeps last week's edition until you merge.")
    return Outcome("reminded" if pending else "nothing pending", f"{len(pending)} edition PR(s) waiting.")


def pr_body(edition, copy, draft_report, readiness_report, drafts, run_url):
    players = {p["id"]: p for p in edition["players"]}
    featured = players.get(copy.get("featured_player_id"), {}).get("name", "none")
    played = [players[pid] for pid in edition["featured_ranking"]]
    lines = [f"## {copy['headline']}", "", f"_{copy['dek']}_", "", copy["lead"], "", "**Alternate headlines**"]
    lines += [f"- {alternate}" for alternate in copy["alternates"]]
    lines += ["", f"**Featured player:** {featured} · **Headline source:** {draft_report['used']}", ""]
    if draft_report.get("rejected"):
        lines += ["<details><summary>Claude's draft was not used. Reasons and text:</summary>", ""]
        lines += [f"- {reason}" for reason in draft_report["reasons"]]
        lines += ["", FENCE4 + "toml", editorial.dumps(dict(draft_report["rejected"], source="claude")).rstrip(), FENCE4, "</details>", ""]
    elif draft_report.get("reasons"):
        lines += [f"> {reason}" for reason in draft_report["reasons"]] + [""]
    if draft_report.get("notes"):
        lines += ["**Check before approving:**"] + [f"- {note}" for note in draft_report["notes"]] + [""]
    lines += ["### This week", "", "| Player | Result | Contribution |", "|---|---|---|"]
    lines += [f"| {p['name']} ({p['team']}) | {result_line(p)} | {contribution(p)} |" for p in played] or ["| No alumni played | | |"]
    by_label = ", ".join(f"{label}: {count}" for label, count in edition["counts"]["by_label"].items())
    lines += ["", f"**Availability:** {by_label}", ""]
    if readiness_report.missing_optional:
        lines += ["**Published without:**"] + [f"- {item}" for item in readiness_report.missing_optional] + [""]
    if readiness_report.pending:
        lines += ["**Charting not yet available (those card lines are left off; a refresh adds them):**"]
        lines += [f"- {item}" for item in readiness_report.pending] + [""]
    if edition["warnings"]:
        lines += ["**Warnings**"] + [f"- {warning}" for warning in edition["warnings"]] + [""]
    lines += ["**Checks**"] + [f"- {check}" for check in edition["validation"]["checks"]] + [""]
    if drafts["state"] == "draft":
        lines += ["### Social drafts (post after the site updates)", "", "**LinkedIn**", FENCE, drafts["linkedin"], FENCE, "**X**", FENCE, drafts["x"], FENCE, ""]
    else:
        lines += ["### Social drafts", "", f"Withheld: {drafts['reason']}", ""]
    lines += [
        "### How to approve",
        "1. Read the headline, dek and lead above.",
        "2. To change them: **Files changed** → `editorial.toml` → **⋯ → Edit file**. Edit only the text inside the quotes, then **Commit changes** to this branch. The `tests` check runs again.",
        "3. Click **Squash and merge**. The site deploys and verifies itself within a few minutes.",
        "",
        f"Built by [this workflow run]({run_url}).",
    ]
    return "\n".join(lines)


def main():
    settings = settings_from_env(os.environ)
    cfg = load_config()
    gh = GitHub(os.environ["GH_APP_TOKEN"], os.environ["GITHUB_REPOSITORY"])
    if settings.automation != "on":
        outcome = Outcome("disabled", "Repository variable EDITION_AUTOMATION is not 'on'.")
    elif settings.schedule == REMINDER:
        outcome = remind(gh, cfg["owner_github"])
    else:
        outcome = run_attempt(settings, gh=gh, cfg=cfg, registry=load_registry(), today=utcnow().date())
    line = f"{outcome.state}: {outcome.message}"
    print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"### Weekly edition\n\n{line}\n")
    return 1 if outcome.failed else 0


if __name__ == "__main__":
    sys.exit(main())
