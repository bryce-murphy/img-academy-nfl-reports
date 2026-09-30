# Operations runbook

## The weekly rhythm (Eastern time)

| When | What happens | What you do |
|---|---|---|
| Tue 2:30 p.m. | Attempt 1 opens the edition PR, or waits for late data | Nothing |
| Tue 8:30 p.m. | Attempt 2, only if still waiting | Nothing |
| Tue evening | — | Review and merge the PR |
| Wed 6:30 a.m. | Final attempt: publishes without optional feeds, or opens a blocked issue | Nothing |
| Wed 9:00 a.m. | Reminder comment if the PR is still open | Merge if you haven't; post to LinkedIn and X |

GitHub can start scheduled runs 15 minutes to 2 hours late.

## Approving an edition

1. Open the PR titled "Edition 2026 Week N: …". GitHub Mobile works.
2. Read the headline, dek, lead and alternates. If Claude's draft was rejected, its text and the reasons sit in a collapsed section.
3. To change the text: **Files changed** → `editions/<id>/editorial.toml` → **⋯ → Edit file**. Change only the text inside the quotes. To use an alternate, paste it into `headline`. To feature someone else, set `featured_player_id` to another ID from the "This week" table; only players who played are accepted.
4. Commit to the same branch and wait for `tests` to pass. A structural mistake, such as a headline over 70 characters, fails the check with a message saying what to fix.
5. Click **Squash and merge**. **Deploy site** runs automatically; the edition is live when it finishes, usually within 3 minutes.
6. Post from the social drafts in the PR. The same text is on the site at `/editions/<id>/social-drafts.json`.

## When something goes wrong

- **"Edition <id> blocked" issue.** Read the step and the reason.
  - *Data readiness:* usually a late feed. When the data lands, run **Actions → Weekly edition → Run workflow** with `final` checked.
  - *Validation:* the sources genuinely disagree. Don't work around it; open a Claude Code session and ask for the issue to be investigated.
- **Pause all automation:** Settings → Secrets and variables → Actions → Variables → set `EDITION_AUTOMATION` to `off`.
- **Rebuild an open edition PR with fresher data:** run the workflow with `refresh` checked. Your headline edits are kept.
- **Manual fallback, if automation is broken:** in a Claude Code session, run `.venv/Scripts/python -m src.edition --season 2026 --week N`. Optionally run `.venv/Scripts/python -m src.editorial draft editions/2026-week-NN` (needs `ANTHROPIC_API_KEY` locally). Then commit on a branch named `edition/2026-week-NN`, push, open a PR and merge it as usual.
- **"Site deployment not verified" issue:** re-run **Deploy site** from the Actions tab. If it keeps failing, check Settings → Pages.
- **To rebuild a published edition with new code:** run `.venv/Scripts/python -m src.edition --season 2026 --week N --rebuild` (add `--historical` for Weeks 1–2). It keeps each player's published roster notes, position, team-change flag and move. Review the diff and open a PR.

### Roster moves

When an alum changes or leaves an NFL team, the edition PR lists it under **Roster moves** and the site shows a neutral line ("Now on the Giants' roster (was Vikings in Week 3)."). To say why, open `editorial.toml` in the PR, uncomment the entry and fill it in:

    [[roster_moves]]
    player_id = "00-0039923"
    kind = "trade"                            # trade | waiver claim | signing | release | waived
    date = 2026-09-28
    details = "for a 2027 fourth-round pick"  # optional, your words from the source
    source = "https://www.giants.com/news/..."

The site writes "Traded to the Giants on Sep 28 for a 2027 fourth-round pick. Source: Giants.com". Allowed sites: nfl.com, operations.nfl.com, espn.com, apnews.com and the 32 team sites. Avoid paywalled stories (for example ESPN+). `details` is at most 100 characters and must not repeat the team or the date.

## One-time owner setup

- **Pages:** Source is **GitHub Actions**; the `github-pages` environment is limited to `main`.
- **`edition` environment:** deployment branch `main` only. Secrets `EDITION_APP_PRIVATE_KEY` and `ANTHROPIC_API_KEY`; variable `EDITION_APP_CLIENT_ID` (the App's **Client ID**).
- **Repository variable:** `EDITION_AUTOMATION` = `on`.
- **GitHub App:** repository permissions Contents, Pull requests and Issues set to read and write; installed only on this repository; webhook off.
- **Commit signing:** SSH signing key held by the Windows ssh-agent; commit email is the GitHub noreply address.

## Keys and rotation

- **Anthropic key:** Console → API keys. Keep a monthly spend limit. To rotate: create a new key, update the `edition` secret, delete the old key.
- **GitHub App private key:** App settings → Private keys → Generate. Update the secret, then delete the old key.
- **If a key leaks:** revoke it first, then rotate. Removing it from Git history does not revoke it.

## Each season

- Review `data/alumni.json` (rookies, transfers, undrafted signings), with a source for every entry. Give each new entry a permanent lowercase `slug` (e.g. `grant-delpit`); it is the player's page address, so never change it, and the build refuses entries without one. Then set `registry_reviewed_season` in `config.json`. Scheduled editions refuse to run until the two match.
- Update the season on the share card (`scripts/share_card.html`, "2026 Season · Weekly Recap"), then run `scripts/make_share_card.py`.
- Public repositories lose scheduled workflows after 60 days without activity. In late August, open Actions and re-enable **Weekly edition** if needed.
