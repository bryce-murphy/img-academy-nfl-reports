# Player pages and play explorer: design

Status: approved in conversation 2026-09-28, pending review of this written spec.
Owner: Bryce Murphy. Builds on `2026-09-26-wednesday-edition-v1-design.md`.

## 1. Goal

Give every IMG Academy alum a page that families, coaches and fans can share and follow all season, and let readers see every play a player was credited on, drawn on a simple field, without inventing anything the data does not show. A front-office reader should find the numbers defensible; a fan should understand every line without a glossary.

Target: live with the Week 4 edition (Wednesday 2026-10-07). Week 3 publishes without player pages.

## 2. Decisions

| Topic | Decision |
|---|---|
| Page structure | Evergreen page per player plus a permanent page per player per week (option C). |
| Explorer contents | Every credited play, key moments pre-selected, with filters (option B). |
| Homepage cards | A small static field diagram of the card's top key moment (option A); no JavaScript on the homepage. |
| Season section | Game log plus position-specific season lines with visible samples; no league percentiles yet (option A). |
| Build approach | Static pages built from edition data; a small script only adds explorer interaction (approach A). |
| Old editions | Weeks 1 and 2, and Week 3 after it publishes, are rebuilt once with full play data when this ships. |
| Not in scope | Drive context around a play, league percentiles, player photos, animation, per-player share images. |

## 3. Pages

### 3.1 Evergreen player page: `/players/<slug>/`

1. **Header.** Name, "TEAM / POS" (display labels, e.g. `S` for the feed's `SAF`), college and draft, the IMG Academy affiliation source link, and a monogram with a team-color bar. No photos or logos.
2. **Latest week.** The newest published edition (every edition covers every registry player): result, participation line ("Played 65 defensive snaps and 5 on special teams"), stat tiles, charted lines, his top key moment on a medium field diagram, and "See all N plays from Week W →" linking to the week page. When he did not play, his status that week and its evidence instead.
3. **Season lines.** Section 6. Samples are always shown; rates only above the thresholds.
4. **Game log.** One row per published edition: week, opponent, result, status (Played / Inactive / Practice squad / Reserve / Not on a roster / Bye / No snaps recorded / Participation unverified), snaps with snap share, and the card's contribution line. Each row links to that week page.
5. **Up next.** From the latest edition's up-next data; omitted when the latest edition is a historical replay.
6. **Footer note.** Data as of the latest edition's timestamp; "Not an official IMG Academy or NFL publication" through the shared base template.

Every registry player gets a page, including players who have not played this season.

### 3.2 Week page: `/players/<slug>/<edition-id>/`

A permanent record of one week. It never changes after publication except through a deliberate edition rebuild.

1. **Links.** "← Week W edition" and "Grant Delpit's season".
2. **Header.** "TEAM / POS · 2026 Season · Week W", result, participation line, stat tiles, charted lines, and the data-as-of line.
3. **Play explorer.** Section 4.
4. **Up next as it was that week**, only when that edition had it.

Players who did not play in a week still get a week page with their status and evidence and no explorer.

### 3.3 Players index: `/players/`

Every alum grouped by position group (Quarterbacks, Running backs, Receivers, Offensive line, Defensive line, Linebackers, Defensive backs), each with team and latest status, linking to the evergreen page. The top navigation gains **Players** between This Week and Archive.

### 3.4 Homepage and edition cards

- A slim field strip of the card's top key moment with its outcome line under it.
- The player's name and the strip link to his week page with that play selected (`…/<edition-id>/#play-<play_id>`).
- A "See every play →" link.
- Cards without credited plays (for example offensive linemen and untargeted cornerbacks) show no strip.

## 4. Play explorer

- **Contents.** Every play the player is credited on (the involvement rule already used for availability: any `*_player_id` role except penalty-only and fantasy credits; `no_play` and deleted/aborted plays excluded).
- **Order.** Key moments first, in their selection order; then the remaining plays in game order.
- **Each play shows.** Quarter and clock, down and distance and spot ("3rd & 7 at the TB 35"), the impact tag when there is one, the official play description, the plain-English outcome line from the player's side, and its field diagram.
- **Filters.** "All plays" (default, key moments at the top), "Impact plays" (plays with an impact tag), "Good for the <team nickname>", "Good for the opponent". "Good for" is decided from the player's side: for his offense EPA > 0; for his defense EPA < 0. Plays without EPA appear only under "All plays".
- **Without JavaScript.** All plays are listed, each with its own medium diagram, and the filter controls are hidden. Nothing is lost.
- **With JavaScript.** One large diagram at the top follows the selected play; clicking a play selects it; filters show and hide list items; the URL fragment `#play-<id>` selects a play on load and updates on selection. About 50 lines of vanilla JavaScript in `static/explorer.js`, loaded with `defer` on week pages only, versioned like the stylesheet.
- **Accessibility.** Plays are buttons in a list; the selected play has `aria-current`; each diagram has a text alternative equal to its spot, result and outcome lines.

## 5. Field diagram

Rendered at build time as inline SVG by a pure Python function (`src/field.py`), so it works without JavaScript and is unit-testable.

- **Orientation.** The offense always moves left to right. Field coordinate: `x = 100 - yardline_100` (0 = the offense's own goal line, 100 = the opponent's goal line).
- **Window.** From `min(start, end, first-down marker) - 10` to `max(...) + 10`, at least 30 yards wide, clamped to the field; end zones are drawn when the window reaches a goal line and labeled with the defending team's abbreviation.
- **Marks.**
  - Line of scrimmage: solid line at `x0 = 100 - yardline_100`.
  - First-down marker: yellow line at `x0 + ydstogo`, or the goal line when `goal_to_go` is 1.
  - Runs, sacks and other scrimmage plays: arrow from `x0` to `x0 + yards_gained` (backward for losses).
  - Passes: dashed arc from `x0` to `x0 + air_yards`; for completions a solid line from there to `x0 + yards_gained` (yards after catch); incompletions end in an open circle at the target spot.
  - The player's team color marks his side's end label; everything else uses the site palette.
- **Text under the diagram.** Spot line ("3rd & 7 at the TB 35"), result line ("Sacked for a loss of 5", "Complete for 14 yards", "Run for 3 yards", "Incomplete"), and the outcome line.
- **Caption (once per explorer).** "Where the play started and ended; not a tracking diagram."
- **No diagram, text only,** when any needed field is missing, for penalties, kneels, spikes, two-point tries, and for special-teams plays in this release (kickoffs and punts need return geometry that we will add later).
- **Sizes.** Strip (card, about 320×56), medium (inline list, about 480×90), large (explorer, full width). One function with a size argument.

## 6. Season lines

Computed at site build from all published editions for the player; never stored. Season values are ratios of summed numerators and denominators. Below the threshold a line shows counts only; at or above it the rate is added. Wording is identical for good and poor results.

| Group | Lines (counts always) | Rate shown from |
|---|---|---|
| All players | Games played; snaps and snap share by phase ("412 defensive snaps, 78% of the team's") | — |
| QB | Dropbacks; expected points per dropback (`qb_epa`); success rate (EPA > 0); completion percentage over expected in percentage points (`100 × (completions − Σcp) / attempts with cp`) | 50 dropbacks |
| RB | Carries; expected points per carry; success rate; targets and catches | 30 carries |
| WR / TE | Targets and share of team targets; share of team air yards; catchable targets and drops (FTN); team expected points when targeted | 15 targets |
| Defense (DL, LB, DB) | Impact plays with components (sacks, tackles for loss, interceptions, passes defended, forced fumbles, QB hits, 3rd/4th-down stops); tackles; charted coverage targets, completions and yards; pressures; missed tackles in attempts | 100 defensive snaps for "per 100 snaps" rates |
| OL | Games, snaps, snap share; accepted penalties and penalty yards from the weekly stats | 300 offensive snaps for "per 100 snaps" |

Rules carried over from the metrics red team: coverage is "charted in coverage", never "allowed"; receiver EPA is "team expected points when targeted"; no cross-position ranking; a missing source is shown as pending, never zero.

## 7. Data

### 7.1 Edition schema version 2

`edition.json` `schema` becomes 2. Per player:

- `plays`: every credited play, each with `play_id`, `quarter`, `clock`, `offense`, `defense`, `offense_name`, `defense_name`, `play_type`, `down`, `ydstogo`, `goal_to_go`, `yardline_100`, `yards_gained`, `air_yards`, `yards_after_catch`, `complete_pass`, `cp`, `qb_dropback`, `qb_epa`, `epa`, `side`, `impact`, `role` (passer / rusher / receiver / defender / returner / kicker / other), and `description`. Missing values are `null`, never zero.
- `key_plays`: becomes a list of `play_id`s referring into `plays`. The site and the headline fact sheet resolve them; schema-1 editions (list of play dicts) are still read.
- `snap_share`: `{"offense": 0.78, "defense": null, "st": 0.12}` from the snap counts' `*_pct` columns.
- `usage`: from the weekly stats: `targets`, `target_share`, `receiving_air_yards`, `air_yards_share`, `penalties`, `penalty_yards` (nulls when absent).

All fields come from files already downloaded (play-by-play, weekly stats, snap counts). The play-by-play fixture and `scripts/make_fixtures.py` gain `goal_to_go`, `air_yards`, `yards_after_catch`, `complete_pass`, `cp`, `qb_dropback`, `qb_epa`, `play_deleted` and `aborted_play`.

### 7.2 Player addresses

`data/alumni.json` gains `slug` for every entry: lowercase name, letters and digits joined by hyphens ("J.J. McCarthy" → "jj-mccarthy", "DJ Turner II" → "dj-turner-ii"). If two entries would share a slug, the later one gets `-<last 4 of gsis_id>`. A test enforces presence, format and uniqueness; once published a slug never changes.

### 7.3 Size

Week 2 has about 40 credited plays across the followed players; `plays` adds roughly 30 KB to its `edition.json`. No concern at this scale.

## 8. Code layout

- `src/evidence.py`: unchanged rules; `key_plays` also returns ids.
- `src/edition.py`: builds `plays`, `snap_share`, `usage`; schema 2.
- `src/field.py` (new): pure SVG geometry and rendering.
- `src/players.py` (new): slug helpers, season aggregation, game log rows, position grouping; pure functions over loaded editions.
- `src/site.py`: renders `players/index.html`, evergreen pages, week pages; adds the card strip.
- `templates/`: `players.html` (index), `player.html` (evergreen), `player_week.html`, `_play.html` (one explorer item); `_card.html` gains the strip. Diagrams are SVG strings returned by `src/field.py`, built only from numbers and escaped text, and inserted with Jinja's `Markup`.
- `static/explorer.js` (new), `static/styles.css` additions.
- `docs/`: methodology section "Player pages and the play explorer"; OPERATIONS note on rebuilding an edition.

## 9. Error handling

- A play missing any field its diagram needs renders as text only.
- An unknown slug for a registry player fails the build with a clear message (the registry test prevents it).
- An edition that cannot be read fails the build as today; a schema-1 edition renders with key moments only.
- Season lines skip an edition whose player row lacks a field instead of treating it as zero, and note "based on N of M weeks" when that happens.

## 10. Testing

- **Data:** `plays` for the Week 2 fixture matches the player's credited plays and their field values; text-only plays for missing geometry; schema-1 editions still render.
- **Diagram geometry:** start, marker and end positions for runs, losses, sacks, completions (air yards + YAC), incompletions, goal-to-go, plays near both goal lines, and left-to-right orientation for either team.
- **Pages:** every registry player has an evergreen page and a week page per edition; game-log links resolve; thresholds switch counts to rates; non-players get correct pages; slugs match the registry; the players index groups correctly.
- **Explorer:** without JavaScript every play has a diagram; a headless-browser test (Edge, as used for the share card) checks filtering, selection and `#play-` fragments.
- **Existing gates:** link check on every page, phone-width overflow check, `src.editorial check`, and a Codex review before each PR merges.

## 11. Rollout

Four PRs, each merged by the owner and checked live after deploy:

1. **Data:** schema 2, registry slugs, fixture columns; rebuild Weeks 1 and 2 with full plays (headline files untouched; current-roster notes kept as published).
2. **Pages:** evergreen pages, week pages with the explorer, the players index, `src/field.py`, `static/explorer.js`.
3. **Homepage:** card strips, "Players" in the navigation.
4. **Docs:** methodology and operations notes.

After PR 1 merges, Week 3 (published Wednesday) is rebuilt the same way. The weekly pipeline needs no change: pages are built from whatever editions are published.

## 12. Risks

- Some credited plays lack air yards or spots (laterals, penalties with enforcement): these fall back to text, never guessed.
- Players credited only on special teams get few diagrams in this release.
- Season lines early in the season are mostly counts; that is intended.
