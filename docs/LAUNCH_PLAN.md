# Launch plan and verified source findings

> The decisions of 2026-09-26 in [the v1 design spec](superpowers/specs/2026-09-26-wednesday-edition-v1-design.md) supersede this plan where they differ: the brand, full automation with headline approval, Git as the archive, and Quarto retired in favor of Jinja2.

Data research checked September 25, 2026; cadence and repository controls updated September 26. This is a build plan, not an assertion that every feature is already enabled.

## Accepted decisions

- Public repository: `bryce-murphy/img-academy-nfl-reports`.
- Alumni: played football at IMG Academy; exclude camps/training-only attendance.
- Audience: fans and alumni with optional analytical depth.
- Editorial approach: balanced, candid, and contextual about positive and negative outcomes.
- Visual direction: sports editorial, strong photography, bold headlines and clean charts.
- Publishing target: Wednesdays at 9 a.m. Eastern, regular season and postseason. Recap the completed NFL week and preview the next matchup.
- Preview: opponent, kickoff, venue, and one evidence-based matchup angle. Next-game availability is preliminary at publication.
- Solo maintainer: pull requests and passing checks are required; another person's approval is not required.
- Personal LinkedIn and X accounts. Free data first; label unverified information.
- Independent portfolio branding. Team logos and headshots requested; no IMG Academy brand assets until arranged.

## Recommended experience

The weekly homepage should tell the story in a minute: one evidence-backed headline, a lead player/story, team results, and compact position-specific box scores for confirmed participants. Selecting a player opens a stable weekly player page. Put nonparticipants and unresolved participation in a compact availability section; distinguish verified absence from unknown participation. Never label unknown evidence “benched” or “out of the rotation.”

Individual pages should provide an original monogram (or a cleared athlete portrait), game result, role/workload, key statistics, season context, an interactive key-play explorer, and a next-matchup preview. Favor a few useful charts over a dashboard full of gauges. Show good and bad play outcomes with attribution caveats. No universal player grade: a receiver's target-play EPA, a defender's recorded involvement, and a lineman's snap count are different kinds of evidence. The [edition design](EDITION_DESIGN.md) specifies the recap/preview boundary and evidence rules.

Potential visuals: target depth and direction, field position before/after a play, play EPA/WPA timeline, workload by offense/defense/special teams, season trends, and available Next Gen Stats summaries. Field diagrams are schematic unless actual coordinates are licensed; never label them tracking replays. Chart units, denominators, sample sizes and missingness remain visible.

Social package: one weekly roundup with a strong native image, an optional small carousel on LinkedIn, and an X post or short thread. Every item links to the corresponding web report or player page. Generate graphics and copy from the same validated records. Avoid generating a noisy post for every alumnus by default.

## Stack decision

Python + Quarto + GitHub Pages is the practical default. Python supplies validated data; Quarto renders an accessible static archive. Add small JavaScript interactions for filtering and play exploration. React becomes worthwhile if complex linked interactive views dominate the project, but it is not necessary for this initial reading experience. A single HTML file is useful for downloading one report, but a website provides stable links, navigation, indexing and an archive. This recommendation remains adjustable while the UI is being planned.

## Verified feeds

Actual 2026 play-by-play, weekly player statistics, rosters, snap counts and injury files were downloaded. Updated release assets were observed on September 25. Next Gen Stats supplies aggregate passing, rushing and receiving measures. Upstream update time does not prove every expected player/game row is present, so each build validates coverage.

References: [Python loader](https://nflreadpy.nflverse.com/), [nflverse releases](https://github.com/nflverse/nflverse-data/releases), [availability schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html), [data dictionaries](https://nflreadr.nflverse.com/articles/).

The detailed participation feed from 2023 onward is delivered after the season. Public Next Gen Stats summaries do not establish access to live player-by-player x/y tracking. Historical Big Data Bowl data may support a separate research feature under its own terms. A Thursday reconciliation pass is recommended for NFL stat corrections after Wednesday publication.

Use official IMG/NFL/team sources to maintain alumni affiliations, then intersect with live roster IDs. The registry currently combines [2025 NFL kickoff alumni](https://playfootball.nfl.com/news-events/news-and-features/texas-and-south-florida-high-schools-dominate-nfl-kickoff-weekend-rosters/), [2026 draft reporting](https://playfootball.nfl.com/news-events/news-and-features/11-schools-have-multiple-former-high-school-football-players-taken-in-2026-nfl-draft/), and a historical affiliation for K.J. Osborn. Reconcile against the current kickoff list and account for transfers/undrafted signings. Do not rely on direct PFR scraping: [Sports Reference's data-use policy](https://www.sports-reference.com/data_use.html) restricts automated reuse. Its rate limit is not a reuse license.

## Remaining launch work

1. Agree the homepage/player-page design using realistic interactive samples; implement responsive views and position-aware narratives.
2. Expand validation beyond offensive yards: independent official gamebook/box-score checks where feasible, defense and special-teams reconciliation, and explicit game-day inactive evidence. Unknown reasons can remain unknown under the free-data approach.
3. Test full reports across bye weeks, postseason, trades, practice-squad elevations, rescheduled games, feed outages and stat corrections. Keep small regression fixtures, not entire raw datasets, in Git.
4. Implement a durable archive of published editions and checksums. Fresh runners cannot rely on a previous run's filesystem. A 30-day Actions artifact is not permanent storage. Separate immutable publication evidence from the current corrected view.
5. Generate platform-ready PNGs and LinkedIn carousel pages, with image provenance and reuse review. Include alternatives and a fallback when a headshot is missing. No fabricated athlete portrait.
6. Deploy and verify public report/player URLs before putting links in posts. Quarto is prepared locally, but Pages is not currently deployed.
7. Connect accounts through OAuth. LinkedIn requires member posting permission; access tokens normally last 60 days and programmatic refresh is restricted to eligible partners. A profile URL alone cannot authorize posting. [LinkedIn sharing](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin), [token refresh](https://learn.microsoft.com/en-us/linkedin/shared/authentication/programmatic-refresh-tokens).
8. X currently uses prepaid pay-per-use API credits. Listed rates include $0.015 for creating a plain post and $0.200 for a post containing a URL; confirm in the developer console before connecting. No credit purchase is authorized by a preference for free data. [X pricing](https://docs.x.com/x-api/getting-started/pricing).
9. Implement separate per-platform publishers, a persistent idempotency ledger, receipts, bounded retries, token-expiry alerts and a kill switch. An ambiguous timeout must be reconciled before retrying. A successful LinkedIn post must not be repeated when only X failed.
10. Run a manual preview, then a manual publish to each connected account. Only then enable Wednesday scheduling. Use `America/New_York` for DST; skip empty/offseason windows. Plan notification delivery and confirm alert ownership. [GitHub schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Repository safety checklist

Secret scanning and push protection, Dependabot alerts and fixes, private vulnerability reporting, CodeQL, read-only default workflow tokens, restricted allowed actions, immutable action pins, and main-branch protection are enabled. Main requires pull requests, up-to-date passing `tests` and `analyze` checks, signed commits, linear history, and resolved conversations; administrators are included. Force pushes and deletion are disabled. The solo-maintainer policy requires zero external approvals. Keep social credentials in a main-only publishing environment when that feature is implemented; no secrets in forked PR runs. Confirm account 2FA/passkeys and recovery information without collecting those secrets. See [SECURITY.md](../SECURITY.md) for verified controls and remaining account responsibilities.
