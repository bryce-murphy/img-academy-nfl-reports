# Wednesday Edition v1: automated recap + up-next

Status: draft for owner review · 2026-09-26 · Owner: Bryce Murphy

## 1. Outcome

A public, automated weekly edition of **IMG Academy → NFL** on GitHub Pages, first live for the Week 3 recap on **Wednesday, September 30, 2026**, improved every week after.

The pipeline runs without the owner except for one weekly action: **approving (and optionally editing) the headline pull request.** Everything else—data collection, validation, drafting, PR creation, deployment, verification, failure reporting—is automated.

### Success criteria for September 30

1. The Week 3 edition is live at `https://bryce-murphy.github.io/img-academy-nfl-reports/` and listed in the archive.
2. Every displayed claim traces to validated data in the committed `edition.json`.
3. No player is shown as "Participation unverified" when roster status or a complete snap table answers the question.
4. The homepage follows the approved mockup (`docs/design/homepage.png`, moved from the ignored `build/design-samples/`) on desktop and at 375 px, with monograms and no photographs.
5. The owner's only action for the edition was reviewing and merging its PR; social drafts in the PR link to the live page. (Posting to LinkedIn and X stays manual in v1.)

### Non-goals for v1

Player pages; matchup angle; automated social posting and social graphics; Thursday correction pass; release-asset archive; registry expansion; postseason round labels; IMG or NFL logos.

## 2. Decisions (settled)

| Topic | Decision |
|---|---|
| Architecture | Editions committed to Git; one Python + Jinja2 renderer; Quarto retired; GitHub Pages deploy on merge |
| Drafting | Claude API called from GitHub Actions; deterministic template fallback; owner approves |
| PR identity | Owner-created GitHub App (installed on this repository only) |
| Missed approval | Wait for the owner; 9 a.m. reminder; never auto-publish |
| Go-live | On merge (usually Tuesday evening); Wednesday 9 a.m. ET is the social posting time |
| Availability | Rules in §5, approved as written |
| Brand | Text wordmark "IMG Academy → NFL" plus an original academy-to-league path graphic; no IMG/NFL marks; independence label adjacent to the wordmark |
| Stat mismatch | Withhold that player's stat line with a note; the edition still publishes |
| Registry | 23 sourced alumni unchanged for v1 |
| Social | Owner posts manually from generated drafts in v1 |

## 3. Weekly lifecycle

All times America/New_York. GitHub cron supports IANA time zones (since March 2026) but can start 15 minutes to 2+ hours late; the schedule leaves slack.

Feed timing (nflverse data schedule): play-by-play and player stats update nightly after game days; rosters and injuries daily at 07:00 UTC; snap counts at 00/06/12/18 UTC; schedules every 5 minutes; Next Gen Stats 3–5 a.m. ET. Monday-night data is expected to be complete after the 18:00 UTC (2 p.m. ET) snap-count update on Tuesday.

| When (ET) | Actor | Action |
|---|---|---|
| Tue 14:30 | `edition.yml` attempt 1 | Readiness check → build → draft → open PR, or exit "waiting" |
| Tue 20:30 | attempt 2 | Same; no-op if the PR already exists |
| Wed 06:30 | attempt 3 (final) | Same; if mandatory data is still missing, open a blocking issue. Missing snap counts alone do not block (players stay "unverified" with a warning) |
| Tue evening | Owner | Reviews the PR; optionally edits `editorial.toml` in the browser; squash-merges |
| On merge | `pages.yml` | Render full site → deploy → verify live URL |
| Wed 09:00 | `edition.yml` reminder | If the edition PR is still open, the App comments and mentions the owner |
| Wed 09:00+ | Owner | Posts to LinkedIn and X from the drafts (manual in v1) |

`github.event.schedule` identifies which cron fired, so the pipeline knows the attempt number without inputs. `workflow_dispatch` accepts `season`, `week`, `final` (bool), `refresh` (bool) and `historical` (bool) for manual runs and replays.

## 4. Architecture

```
nflverse releases ──► data.py ──► evidence.py ──► edition.py ──► editions/<id>/edition.json
                                                     │
                                  editorial.py ◄─────┘──► editions/<id>/editorial.toml
                                  (Claude API + validator + fallback)
                                                     │
                                  publish.py ──► PR `edition/<id>` (App token) ──► owner merges
                                                                                   │
                                  site.py + templates/ + static/ ◄── pages.yml ◄───┘ ──► GitHub Pages
```

### Units

| Module | Responsibility | Depends on |
|---|---|---|
| `src/data.py` | Fetch nflverse assets with host allowlist, size limits, checksums, schema checks. **Change:** filter play-by-play rows to the reporting week's `game_id`s while parsing | stdlib |
| `src/evidence.py` | Pure rules: participation, availability labels, snap-table completeness, score/yardage validation, featured-performance ranking | nothing |
| `src/edition.py` | Readiness check; builds the `edition.json` model including up-next; writes `editions/<id>/` | data, evidence |
| `src/editorial.py` | Fact sheet from `edition.json`; Claude call; validator; template fallback; `check` CLI used by CI | edition model, stdlib HTTP |
| `src/site.py` | Renders every committed edition, homepage, archive, methodology, sitemap, 404 into an output directory | Jinja2, edition model |
| `src/publish.py` | GitHub API: commit files to the edition branch, open PR, comment, open/update/close issues | stdlib HTTP |
| `src/pipeline.py` | CLI orchestrating one attempt: kill switch → readiness → build → draft → publish; maps outcomes to exit states | all of the above |
| `templates/`, `static/` | Jinja2 templates (autoescape on), CSS, brand SVG | — |

`src/report.py` is dissolved into `evidence.py`, `edition.py` and `site.py`. Existing tests move with their functions and keep passing.

### Repository layout changes

```
editions/2026-week-03/edition.json      # validated model (committed, reviewed)
editions/2026-week-03/editorial.toml    # headline/dek/lead/featured (drafted, owner-approved)
editions/2026-week-03/social-drafts.json
editions/2026-week-03/sources.json      # source manifest: URLs, upstream timestamps, SHA-256, row counts
templates/  static/                     # renderer inputs (static/styles.css moves from site/styles.css)
docs/design/                            # approved mockups (homepage, player page, mobile)
requirements.lock                       # hash-pinned Jinja2 + MarkupSafe
```

Removed: `site/` (Quarto project), `.github/workflows/report.yml` (replaced by `edition.yml`; its roster-review option becomes a `pipeline.py` flag). `.gitignore` keeps `build/`, `.cache/` and adds `_site/`.

## 5. Evidence and availability rules

Evaluated in order; first match wins.

| # | Evidence | Label | Evidence text |
|---|---|---|---|
| 1 | Positive offense/defense/special-teams snaps | Played | Positive snap count |
| 2 | Play involvement or positive box-score activity **and** an explicit all-zero snap row | Conflicting evidence | Blocks social drafts |
| 3 | Player ID in a recorded play role (excluding penalty-only) | Played | Recorded play involvement |
| 4 | Positive box-score activity | Played | Positive recorded game statistic |
| 5 | No weekly roster record for the season/week | Not on an NFL roster | Current roster shown separately |
| 6 | Weekly roster status `INA` | Inactive for the game | Weekly roster status |
| 7 | Weekly roster status `DEV` | Practice squad | Weekly roster status |
| 8 | Weekly roster status `RES` | Reserve list | No reason is inferred |
| 9 | Weekly roster status `CUT` | Released | Weekly roster status |
| 10 | Team has no game this week | Bye week | Schedule |
| 11 | Explicit all-zero snap row, or absent from a complete team snap table | No snaps recorded | Reason not established |
| 12 | Anything else | Participation unverified | Missing evidence is not evidence of a DNP |

Unrecognized roster statuses fall through to rows 10–12.

**Snap-table completeness:** the team has snap rows for at least 22 distinct players in that game, including at least one offensive and one defensive player. This threshold is a named constant with tests.

**Must verify before use (blocking task):** the nflverse data dictionary meanings of weekly-roster `INA`, `DEV`, `RES`, and the status an elevated practice-squad player carries. Encode the confirmed meanings as tests using fixture rows. If `INA` does not mean game-day inactive, its label becomes "Inactive roster designation" and the rule is revisited with the owner.

Unchanged accuracy rules: stable GSIS/PFR IDs only; schedule scores must match the END GAME play; duplicate play IDs, ambiguous identities and stale mandatory feeds block the edition. **Changed:** a player's passing/rushing/receiving yardage disagreeing with play-by-play withholds that player's stat line ("Stats withheld: sources disagree") and adds a warning, instead of failing the edition.

Injury designations remain labeled as that week's pregame report, never proof of absence.

## 6. Edition model (`edition.json`)

```
schema_version: 1
id: "2026-week-03"; season; week; season_type
generated_at (UTC ISO); label: "Verified source snapshot" | "Historical replay"
games[]: game_id, away/home team, scores, gameday
players[]:
  id, name, position, team (game-week team), team_name, team_color
  availability: {label, evidence}
  game: {game_id, opponent, home_away, team_score, opp_score, result W/L/T} | null
  metrics[] {key, label, value|null}  # position-specific; null renders "—"
  stats_withheld: bool
  snaps {offense, defense, st}
  key_plays[] {play_id, quarter_label ("Q1".."Q4","OT"), clock, description, epa}
  next_gen[] {label, value, unit}
  injury_report {designation, primary_injury} | null
  current {team, roster_status}
  next_game: {kind: "game"|"bye"|"unconfirmed"|"season_complete",
              week, opponent, home_away, date, kickoff_et|null, venue|null, after_bye_game|null}
  alumni_source
featured_ranking[]: player ids ordered by the deterministic performance score
warnings[]; validation {checks[], passed}
publication_ready: bool   # false when conflicting evidence exists; gates social drafts
```

Up-next is omitted (`next_game: null`) for historical replays unless an appropriately dated schedule snapshot exists.

### Deterministic performance score

Used for card order and the fallback headline. Points: touchdown 6, interception 5, sack 4, forced fumble 3, fumble recovery 3, 100+ rushing or receiving yards 5, 300+ passing yards 5, pass defended 1, tackle 0.5, yards/25. Ties break by name. Offensive linemen rank by offensive snaps after all scored players. The table is a named constant with tests.

## 7. Up-next rules

Source: the schedule feed. For each player, find the first game after the reporting week for their **current** roster team.

- Kickoff: schedule `gameday` + `gametime` (Eastern per nflverse; verify during implementation), rendered like "Sun, Oct 4 · 1:00 p.m. ET". Missing time → "Kickoff TBD".
- Venue: schedule `stadium`; missing → "Venue TBD". Never guessed.
- Bye: the team has no game in the next week → "Bye in Week N", then the following game.
- Team changed since the recap game: the recap keeps the game-week team; up-next uses the new team with "Now with <team>".
- Postseason opponent undetermined → "Next matchup unconfirmed". After the team's final game → "Season complete".
- The homepage strip groups players by team. Next-game availability is not shown in v1.

## 8. Editorial drafting

### `editorial.toml`

```toml
schema = 1
source = "claude"            # "claude" | "fallback"; the owner may change content freely
model = "<model id>"
featured_player_id = "00-0036282"
headline = "Two sacks. Two winning sides."
dek = "Grant Delpit and Nolan Smith each recorded a sack as Cleveland and Philadelphia won."
lead = """…up to 80 words…"""
alternates = ["…", "…"]
```

### Drafting step

1. Build a fact sheet from `edition.json` only: played players with metrics, results, key-play descriptions, availability counts, next games. Play descriptions are treated as quoted data in the prompt, never as instructions.
2. Call the Messages API (`api.anthropic.com` added to a separate host allowlist) with a structured-output request for the TOML fields. The model ID lives in `config.json` (`editorial_model`, `claude-opus-5-5`) called at explicit `medium` effort, with the fact sheet wrapped in `<edition_facts>` tags in the user message. Timeout 60 s; two retries on 429/5xx.
3. Validate (below). On success, write `source = "claude"`. On API failure or a failed hard check, write the template fallback (`source = "fallback"`) and include the rejected draft and reasons in the PR description so the owner can still use it.

### Validator

Hard checks (reject the draft in the pipeline; fail CI):
- Schema and required fields present; `featured_player_id` exists and is labeled Played.
- Length: headline ≤ 70 characters, dek ≤ 160, lead ≤ 80 words, exactly two alternates.

Content checks (reject the draft in the pipeline; **warn only** in CI so owner edits are never blocked by a false positive):
- Every numeral and spelled number (one–twenty) matches a value in the fact sheet.
- Every registry player named is labeled Played.
- Capitalized names not found in the fact sheet or an allowlist (team names, cities, "IMG", "Academy", "NFL") are flagged.
- Terms such as injured, injury, benched, DNP, "did not play", scratch, illness, suspended are rejected unless the same term appears in that player's facts.

### Template fallback

`"{Name}: {top two metrics} in {Team}'s {win|loss|tie} vs. {Opponent}"` for the top-ranked performer; dek summarizes participant count and team record for the week; lead lists the top three performers from the fact sheet.

## 9. Automation, idempotency, failure handling

### Attempt outcomes

| Outcome | Exit | Side effects |
|---|---|---|
| Kill switch off (`vars.EDITION_AUTOMATION != 'on'` or `config.scheduled_reports_enabled` false) | success, "disabled" | none |
| Outside season window / no completed week / registry not reviewed for season | success, "skipped" | none (registry mismatch during season opens an issue) |
| `editions/<id>/` already on `main` | success, "published" | none |
| PR `edition/<id>` already open and `refresh` not set | success, "pending approval" | none |
| Data not ready and not final attempt | success, "waiting" | job summary lists missing items |
| Data not ready on final attempt | failure | issue opened/updated |
| Validation failure (score disagreement, ambiguity, schema drift) | failure | issue opened/updated immediately |
| Built and drafted | success, "PR opened" | branch commit, PR, review request; any open blocking issue for this edition is closed |

**Readiness (mandatory):** every game of the week has final scores; play-by-play contains an END GAME for every game; weekly player stats contain the week; weekly rosters updated after the last game date. **Readiness (optional):** snap tables complete for every game; injury and Next Gen Stats present. Optional gaps wait on attempts 1–2 and proceed with warnings on attempt 3.

**Never clobber:** once the PR exists, scheduled runs do not modify it. `refresh: true` (manual dispatch) rebuilds data files but keeps `editorial.toml` if any branch commit was not authored by the App.

**Commits:** created through the GraphQL `createCommitOnBranch` mutation with the App installation token, so they are GitHub-verified. Merged edition directories are immutable to automation.

**Issues:** one per edition, title `Edition <id> blocked`, label `edition-blocked`; body states the failed step, reason, run link and next retry. Updated rather than duplicated; closed by the next successful attempt.

**Concurrency:** `edition-<season>` group, no cancel-in-progress.

## 10. Site and design

Pages: `/` (latest edition), `/editions/<id>/` (permanent), `/archive/` (sorted by season, then week, numerically), `/methodology/`, `404.html`, `sitemap.xml`, `robots.txt`. Each edition page links its `edition.json` and `sources.json`.

Homepage sections, following the mockup: masthead (wordmark, path graphic, "Independent coverage by Bryce Murphy · Not an official IMG Academy or NFL publication" (revised 2026-09-27: the author works at IMG Academy)) → edition eyebrow → headline, dek, lead and featured card (monogram, score) → "Alumni in action" cards for Played players in ranking order → weekly box score table → availability section grouped by label → "Up next" strip grouped by team → sources table, warnings, disclaimer, data license.

Rules: Jinja2 autoescape on; team colors validated as `#RRGGBB`; no third-party images; Open Graph and Twitter meta from headline/dek; `<meta name="edition-id">` on every edition page for deploy verification. Brand graphic: original SVG path motif (Bradenton → league) using site colors; concepts are reviewed by the owner in the implementation PR. Existing fonts (Barlow Condensed, Inter via Google Fonts) and palette carry over. Layout verified at 375 px and 1280 px.

Methodology page is rewritten from the rules in §5, with Wednesday timing and the independence statement.

## 11. Workflows and security

| Workflow | Trigger | Permissions | Secrets |
|---|---|---|---|
| `ci.yml` (Quality) | PR, push to main | `contents: read` | none |
| `codeql.yml` | unchanged | unchanged | none |
| `edition.yml` | schedule ×4, dispatch; `main` only | `contents: read` for `GITHUB_TOKEN`; writes via App token | `edition` environment |
| `pages.yml` | push to `main` (paths: `editions/**`, `templates/**`, `static/**`, `src/**`), dispatch | build: `contents: read`; deploy: `pages: write`, `id-token: write`; verify: `issues: write` | none |

- `ci.yml` job name stays `tests` (required check). It installs `requirements.lock` with `--require-hashes`, runs unit tests, renders the full site into a temp directory, and runs `editorial check` on changed editions.
- `edition` environment: deployment branch `main` only; secrets `ANTHROPIC_API_KEY`, `EDITION_APP_PRIVATE_KEY`; variable `EDITION_APP_ID`. The Anthropic key is exposed only to the drafting step.
- GitHub App permissions: Contents RW, Pull requests RW, Issues RW, Metadata R. Installed on this repository only. "Allow GitHub Actions to create and approve pull requests" stays off.
- All actions are GitHub-owned and pinned by full SHA (`actions/checkout`, `actions/setup-python`, `actions/create-github-app-token`, `actions/configure-pages`, `actions/upload-pages-artifact`, `actions/deploy-pages`).
- Post-deploy verification fetches the live homepage (retrying up to 5 minutes) and checks `edition-id`; failure opens an issue.
- Dependabot: add `groups` so GitHub Actions and pip updates arrive as one PR each. Resolve the five open Dependabot PRs first (CodeQL `init` and `analyze` must move together).

## 12. Testing

- **Fixtures:** small CSV slices of the Week 2 feeds (a handful of games and the registry players, not full datasets) under `tests/fixtures/`.
- **Golden test:** fixtures → `edition.json` compared with a committed expected file.
- **Unit tests:** every row of the §5 table; snap-table completeness; performance score; quarter labels (5 → OT); up-next (next game, bye, trade, TBD time, season complete); validator (each hard and content check); fallback headline; stat-mismatch withholding; idempotency decisions in `pipeline.py` (fake GitHub client); readiness classification.
- **Render tests:** every template renders from the golden edition; output contains no unescaped fixture text; archive order handles Week 10+; `edition-id` meta present.
- **Existing tests** keep passing after the module split.
- **End-to-end dry run (Monday):** `workflow_dispatch` of `edition.yml` for Week 2 → real PR → merge → deploy → live verification.

## 13. Documentation

Update README (current stage, weekly flow), `docs/WORKFLOW.md` (edition data in Git, automated flow), `SECURITY.md` (App, environment, secrets, Anthropic host), `docs/LAUNCH_PLAN.md` (decisions superseded here), `docs/MEDIA_RIGHTS.md` (wordmark note). Add `CLAUDE.md` with accuracy rules, the branch/PR/signing workflow and the weekly flow. Add `docs/OPERATIONS.md`: owner setup, kill switch, rerunning an attempt, handling a blocked issue.

## 14. Delivery tiers and fallback

Tier 1 (must ship for Sept 30): evidence/availability, edition model, renderer and homepage, `pages.yml`, CI changes. With Tier 1 alone, the same edition PR can be produced from a Claude Code session and published.

Tier 2 (target for Sept 30): `editorial.py`, `publish.py`, `pipeline.py`, `edition.yml`, GitHub App flow.

If Tier 2 is incomplete on Tuesday afternoon, the Week 3 PR is produced by running `pipeline.py` locally in a session (identical files), and Tier 2 completes before Week 4.

The launch PR sets `config.json` `scheduled_reports_enabled: true` only after the Monday dry run succeeds; until then scheduled attempts exit "disabled".

Schedule: Sat–Sun build; Mon dry run on Week 2 (first public deploy); Tue Week 3 automated run; Wed owner posts.

## 15. Owner setup (outside the repository)

1. Pages source = GitHub Actions; confirm the `github-pages` environment is limited to `main`.
2. Repository-local commit email = noreply address.
3. SSH commit signing through the Windows ssh-agent.
4. Create and install the GitHub App; store its ID and private key in the `edition` environment.
5. Anthropic Console: credits, a monthly spend limit, an API key stored in the `edition` environment.
6. Repository variable `EDITION_AUTOMATION = on`.

## 16. Verification items (resolved during implementation, each with a test or recorded evidence)

1. Weekly-roster status semantics (§5).
2. Snap-table completeness threshold against Week 2 and Week 3 data.
3. Full-season play-by-play size against `MAX_BYTES` once week-filtering is in place.
4. `actions/upload-pages-artifact` nested action references satisfy the full-SHA pinning policy (confirmed by the Monday dry run).
5. Schedule `gametime` time zone and `stadium` field.
6. Anthropic model ID and request format.
7. `createCommitOnBranch` commits by the App show as Verified.

## 17. Open question for review

Should the Week 2 edition (built Monday as the dry run, labeled "Historical replay", no up-next) remain in the public archive as the first edition? Default: yes.

## 18. Implementation notes (2026-09-26)

Adjustments made while planning, within the approved design:

- The hash-locked dependency file is `requirements.txt` (generated from `requirements.in` with uv), so Dependabot can read it.
- `social-drafts.json` is produced by the renderer at deploy time, so it always matches the approved headline. The PR description carries the same drafts for review.
- Capitalized names in a Claude draft that aren't in the data become review notes rather than rejections, which avoids false positives from title-cased prose. Blocked terms (injury, benched, …) count as supported only when they appear in the named player's own facts.
- `Deploy site` skips its deploy job until the first edition exists.
- The Claude call uses the official `anthropic` SDK with model `claude-opus-5-5` at explicit `medium` effort (owner-directed, following Anthropic's "Prompting Claude Opus 5.5" guide), server-side refusal fallbacks (`fallbacks: "default"`), and the edition facts wrapped in `<edition_facts>` tags that the system prompt marks as data, never instructions.
- nflverse schedules label playoff games `WC`, `DIV`, `CON`, `SB` (never `POST`); `config.json` `season_types` uses those values and stats/Next Gen Stats matching maps them to `POST`.
- Up-next distinguishes "Next matchup unconfirmed" (a team still alive whose next opponent isn't scheduled) from "Season complete", and treats `NA` schedule values as unknown.
- The site palette follows the official IMG Academy Brand Guidelines (v1.2, May 2024) supplied by the owner — IMG Blue `#0057B8`, navy `#002D54`, light `#DDE3EB`, text `#424242` — with team colors used only as bars and borders; no IMG Academy logo, crest or typefaces. Public copy always says "IMG Academy", never "IMG" alone, per the guidelines' editorial rule.
- The GitHub App is referenced by its Client ID (`EDITION_APP_CLIENT_ID`), as `actions/create-github-app-token` v3 expects. GitHub API calls live in `src/github.py` (the spec's `publish.py`), which refuses redirects and non-GitHub hosts; the PR body is built in `src/pipeline.py`, and live-site verification is `src/verify.py`.
- The Claude request timeout is 120 seconds with two SDK retries.
