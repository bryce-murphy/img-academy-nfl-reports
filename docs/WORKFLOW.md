# Reliable delivery from source to reader

## Recommended first production architecture

Use GitHub Actions for Python collection/validation, versioned GitHub Release assets for the public edition archive, Quarto plus small JavaScript interactions for pages, GitHub Pages for hosting, and separate OAuth publishers for LinkedIn and X. Readers load a prebuilt site; they do not query nflverse or a database on page view. No Supabase, Vercel account, or Netlify account is needed for this design.

| Stage | Durable output | Failure behavior |
| --- | --- | --- |
| Collect | Selected source snapshot, retrieval/update times, source hashes | Retry transient reads with a limit; stop on stale mandatory feeds |
| Validate | Per-game and per-athlete evidence, validation results | Withhold misleading claims; block publication on conflicts |
| Archive | Versioned release bundle for season/week/edition | Never overwrite a published snapshot; use a correction version |
| Render | Complete static weekly archive and player pages | Build in staging; keep the previous deployed site intact |
| Deploy | GitHub Pages deployment with commit and edition IDs | Require successful deployment and URL/content checks before social posting |
| Distribute | Platform, period, content hash, state, remote post ID | Resume only failed platforms; reconcile uncertain API outcomes before retry |

### Where data lives

The Actions runner is scratch space, not storage. Raw downloads can be cached or attached as short-lived diagnostic artifacts. Code, templates, the small sourced alumni registry, configuration and data schemas live in Git. Generated multi-megabyte datasets do not belong in normal Git history.

Each published edition gets a release asset bundle: `report.json`, selected `plays.json.gz`, source/validation manifest, rendered pages, and original social graphics. Include the exact data necessary to reproduce the displayed claims; do not archive an entire third-party database by default. Record source attribution and modifications. GitHub supports downloadable release assets; see [release storage](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#storage-and-bandwidth-quotas).

Each site build loads the existing edition index and released bundles so it includes all prior weeks. Corrections create a new edition, preserve the old evidence, and update a clearly marked canonical report. A scheduled job must not erase the archive by deploying only files from its fresh runner. Periodically export bundles to a second owner-controlled backup destination once one is chosen.

### Where the site lives

[GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages) serves the prebuilt HTML/CSS/JavaScript and small display JSON. It fits a public portfolio and keeps this project on one service. It can host interactive static charts; React is not required for interactivity. A custom domain can be added later without changing the pipeline.

Vercel or Netlify become more useful if preview-deployment collaboration, server-side rendering, a live API, or dynamic application features become necessary. Supabase becomes useful for authentication, private data, saved preferences, or live queries. None is needed for a weekly read-only publication. Supabase Free can pause low-activity projects after seven days, which is another dependency to manage for seasonal reporting. [Supabase pausing](https://supabase.com/docs/guides/platform/free-project-pausing). Vercel Hobby is limited to personal/noncommercial use. [Vercel Hobby](https://vercel.com/docs/plans/hobby).

### Delivery timing and recovery

Collect and validate before the desired Wednesday 9 a.m. Eastern publication time, leaving time for feed delays and a retry. The present disabled cron starts the prototype build at 9 a.m.; production needs an earlier collection stage and a separate publication stage. Use schedule-aware season/week selection including postseason, byes, reschedules, and Monday games. GitHub cron is best-effort and can be delayed or dropped; do not promise second-exact delivery. Confirm the schedule is active before each season because public-repo inactivity can disable it. [GitHub schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

The Wednesday edition combines the completed week with the next scheduled matchup. Resolve the preview against the player's current team, while preserving the previous game's team in the recap. Include opponent, kickoff with a named timezone, venue, and one sourced matchup angle. Separate past-game participation from preliminary next-game availability; never carry a prior week's injury designation forward as current. Show each source's effective date and retrieval time. See [edition design](EDITION_DESIGN.md) for byes, trades, unknown schedules, and historical replay behavior.

Use three separately permissioned jobs: build (read-only), deploy/archive (narrow write permissions), and social publish (scoped secrets in a protected main-only environment). Record durable publication intent before sending a post, then its remote receipt. Serialize publication per edition/platform. GitHub's concurrency alone prevents overlap but does not provide durable deduplication. Use a small protected publication-state branch or another transactional state store; on uncertain outcomes, stop for reconciliation rather than automatically retry.

On failure, keep the last good website available and visibly dated. Do not promote an old edition as new. Notify the owner with a failed step and actionable reason. Do not expose tokens or raw auth responses. A Thursday correction run should compare published facts, version meaningful changes, and avoid re-sending the original social posts.

### Manual-first launch

Current implementation supports collection, core validation, recap generation, and draft artifacts. Matchup previews, durable release archiving, redesigned player pages, public Pages deployment, platform image generation and social publishing are planned, not yet active. Validate those with manual runs before enabling scheduled generation and posting. Profile URLs alone do not connect the social APIs.
