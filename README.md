# IMG Academy NFL Reports

Independent, evidence-led weekly coverage of football players who attended IMG Academy, by [Bryce Murphy](https://www.linkedin.com/in/bryce-murphy/). Public portfolio project; not endorsed by IMG Academy or the NFL.

## Current stage

The secure repository foundation and manual Python report builder are implemented. The first 2026 Week 2 build follows 23 sourced alumni and confirms 15 participants. Layout is a working prototype. The next design is a weekly editorial overview with compact box scores, team results, an availability strip, and detailed individual player pages.

**Scheduling is disabled. Social publishing is not connected or implemented yet. GitHub Pages is not deployed yet.** The workflow currently produces downloadable reports and social text drafts. These are deliberate rollout boundaries, not claims of production readiness.

## Run by hand

Open **Actions → Build report → Run workflow**. Leave season/week blank for the latest eligible week, or enter an explicit season/week. The generated artifact contains HTML, Quarto source, structured data, social drafts, and a source manifest. No social post is sent.

Locally, with Python 3.11 or newer:

```sh
python -m unittest discover -s tests -v
python -m src.report --season 2026 --week 2
# Optional: render the report archive with Quarto
quarto render site
```

The report builder uses Python's standard library and public nflverse release files directly. No Python packages or credentials are needed. [nflreadpy](https://nflreadpy.nflverse.com/) is the official Python loader for the same ecosystem and is a good extension point for larger Polars analyses. Direct release reads make source version, freshness, and checksum capture explicit here. Available Next Gen Stats summaries are included when the athlete/week match is present.

Generated files are under `site/reports/SEASON-week-WW/` and are ignored by Git. The standalone report has inline styling; optional web fonts need an internet connection and fall back to local fonts. Third-party images are disabled pending permission. The Quarto site provides the eventual searchable archive. The current workflow keeps artifacts for 30 days; durable archival is a launch requirement. See the [complete delivery architecture](docs/WORKFLOW.md).

## Accuracy rules

- Stable GSIS/PFR IDs, not fuzzy names. Weekly team and game identity must agree.
- Completed reporting window only. Schedule scores must match an END GAME play-by-play record.
- Passing, rushing, and receiving yards reconcile with play-by-play. These are consistency checks within nflverse, not independent gamebook verification.
- Positive offensive, defensive, or special-teams snaps establish participation. Actual play involvement or positive game statistics can also establish participation.
- A missing row is unknown. Zero snaps do not reveal a reason. Injury reports are pregame designations, not proof that a player missed the game. No illness or benching claim is guessed.
- Optional missing feeds are labeled; mandatory stale/missing data, duplicate plays, ambiguous identities, and score disagreements fail the build.
- No raw tracking trajectories or invented blocking grades. Play EPA is an offensive team outcome, not an individual player score.

## Planned publishing cadence

Tuesday at **9 a.m. America/New_York**, after Monday Night Football, regular season and postseason. The workflow has a September–February calendar filter and a completed-game-window check. January and February belong to the preceding NFL season. `scheduled_reports_enabled` starts false. GitHub schedules can be delayed; 9 a.m. is a target, not a delivery SLA. Public-repository schedules can be disabled after 60 days of inactivity; preseason checks must re-enable them when necessary.

Manual runs come first. A new alumni review is required each season before enabling scheduled reports. `--refresh-roster` generates a review snapshot; weekly builds already refresh roster membership. This does not discover every new alumnus automatically. Sourced new names and stable IDs must be added and reviewed, including transfers, rookies and undrafted players.

## Distribution targets

- LinkedIn: https://www.linkedin.com/in/bryce-murphy/
- X: https://x.com/BryceVMurphy

See [launch plan](docs/LAUNCH_PLAN.md) for OAuth connections, costs, durable publishing state, correction handling, security settings, and design decisions. Never paste access tokens into an issue or report.

## Security and licenses

See [SECURITY.md](SECURITY.md). GitHub settings are verified separately from policy files. Core report code is MIT; nflverse data is generally CC BY 4.0, with different terms for FTN data. Third-party logos and headshots are disabled; original monograms and team-color accents are the default. Portfolio use alone does not establish image reuse rights. See the [media policy](docs/MEDIA_RIGHTS.md). No IMG Academy logo is included.
