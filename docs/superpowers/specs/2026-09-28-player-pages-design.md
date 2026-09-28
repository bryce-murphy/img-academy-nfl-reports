# Player pages and play explorer: design

Status: approved in conversation 2026-09-28, revised the same day after a Codex review (see §13), pending review of this written spec.
Owner: Bryce Murphy. Builds on `2026-09-26-wednesday-edition-v1-design.md`.

## 1. Goal

Give every IMG Academy alum a page that families, coaches and fans can share and follow all season, and let readers see every play the play-by-play records him on, drawn on a simple field, without inventing anything the data does not show. A front-office reader should find the numbers defensible; a fan should understand every line without a glossary.

Target: live with the Week 4 edition (Wednesday 2026-10-07). Week 3 publishes without player pages.

## 2. Decisions

| Topic | Decision |
|---|---|
| Page structure | Evergreen page per player plus a permanent page per player per week (option C). |
| Explorer contents | Every play on which the play-by-play records the player in an allowlisted role, key moments pre-selected, with filters (option B). |
| Homepage cards | A small static field diagram of the card's top key moment (option A); no JavaScript on the homepage. |
| Season section | Game log plus position-specific season lines with visible samples; no league percentiles yet (option A). |
| Build approach | Static pages built from edition data; a small script only adds explorer interaction (approach A). |
| Old editions | Weeks 1 to 3 are rebuilt once with full play data in the last PR, after a canary build and a diff review. |
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
- Cards without recorded plays (for example offensive linemen and untargeted cornerbacks) show no strip.

## 4. Play explorer

- **Contents.** "Recorded plays": every play on which the play-by-play names the player in one of these roles: `passer`, `rusher`, `receiver`, `td`, `interception`, `sack`, `half_sack_1/2`, `qb_hit_1/2`, `tackle_for_loss_1/2`, `forced_fumble_player_1/2`, `fumble_recovery_1/2`, `fumbled_1/2`, `pass_defense_1/2`, `solo_tackle_1/2`, `assist_tackle_1..4`, `tackle_with_assist_1/2`, `safety`, `punt_returner`, `kickoff_returner`, `punter`, `kicker`, `blocked` (each `<role>_player_id`). Every matched role is stored. Excluded: penalty-only and fantasy fields, lateral bookkeeping roles, `no_play`, `play_deleted`, `aborted_play`. This list is for the explorer only; the availability rule is unchanged.
- **Reader meaning.** The explorer is headed "Recorded plays (N)" and always says: "The play-by-play names a player only when he throws, runs, is targeted, makes a tackle or a charted defensive play. Most snaps never appear here; see his snaps above." Offensive linemen get: "Offensive linemen are rarely named in play-by-play; their snaps and team results tell more." A low count never implies low participation: snaps and charting come first on every page.
- **Order.** Key moments first, in their selection order; then the remaining plays in game order.
- **Each play shows.** Quarter and clock, down and distance and spot ("3rd & 7 at the TB 35"), the impact tag when there is one, the official play description, the plain-English outcome line from the player's side, and its field diagram.
- **Filters.** "All plays" (default, key moments at the top), "Impact plays" (plays with an impact tag), "Positive plays for the <team nickname>", "Negative plays for the <team nickname>". Positive is decided for his team, not him: on offense EPA > 0, on defense EPA < 0. Next to the filters: "Expected points describe the whole play, not the player named on it." Plays without EPA appear only under "All plays".
- **Without JavaScript.** All plays are listed, each with its own medium diagram, and the filter controls are hidden. Nothing is lost.
- **With JavaScript.** One large diagram at the top follows the selected play; clicking a play selects it; filters show and hide list items; the URL fragment `#play-<id>` selects a play on load and updates on selection. About 50 lines of vanilla JavaScript in `static/explorer.js`, loaded with `defer` on week pages only, versioned like the stylesheet.
- **Accessibility.** Plays are buttons in a list; the selected play has `aria-current`; each diagram has a text alternative equal to its spot, result and outcome lines.

## 5. Field diagram

Rendered at build time as inline SVG by a pure Python function (`src/field.py`), so it works without JavaScript and is unit-testable.

- **Orientation.** The offense always moves left to right. Field coordinate: `x = 100 - yardline_100` (0 = the offense's own goal line, 100 = the opponent's goal line).
- **Display domain.** −10 to 110, so both end zones exist: the left end zone is labeled with the offense's abbreviation, the right with the defense's. The window runs from `min(start, end, marker) - 10` to `max(...) + 10`, at least 30 yards wide, clamped to the domain. Marks are clamped for drawing only; the text always states the real result.
- **Eligibility, checked in this order.** Text only when any of: `play_type` is `no_play` or a special-teams type (kickoff, punt, field_goal, extra_point); `penalty`, `fumble`, `interception`, `lateral_reception`, `lateral_rush`, `qb_kneel`, `qb_spike` or `two_point_attempt` is 1; `yardline_100` is outside 1–99; `yards_gained` is missing; `ydstogo` is missing or outside 1–99. Otherwise draw as, in precedence order: **sack** (`sack` = 1; `play_type` is `pass` and there are no air yards), **run** (`rush_attempt` = 1), **completed pass** (`complete_pass` = 1 and `air_yards` present), **incomplete pass** (`pass_attempt` = 1, `complete_pass` = 0, `air_yards` present); anything else is text only.
- **Goal lines.** A touchdown ends exactly on the goal line (x = 100); a safety or a loss into the own end zone ends below 0 and is drawn inside the left end zone.
- **Marks.**
  - Line of scrimmage: solid line at `x0 = 100 - yardline_100`.
  - First-down marker: yellow line at `x0 + ydstogo`, or the goal line when `goal_to_go` is 1.
  - Runs, sacks and other scrimmage plays: arrow from `x0` to `x0 + yards_gained` (backward for losses).
  - Completed passes: dashed arc from `x0` to `x0 + air_yards`, then a solid line to `x0 + yards_gained` (yards after catch).
  - Incomplete passes: dashed arc ending in an open circle at `x0 + air_yards`.
  - Interceptions, fumbles and laterals: text only in this release (their paths need return geometry).
  - The player's team color marks his side's end label; everything else uses the site palette.
- **Text under the diagram.** Spot line ("3rd & 7 at the TB 35"), result line ("Sacked for a loss of 5", "Complete for 14 yards", "Run for 3 yards", "Incomplete"), and the outcome line.
- **Caption (once per explorer).** "Where the play started and ended; not a tracking diagram."
- **No diagram** means the play still appears with all its text; only the drawing is skipped.
- **Sizes.** Strip (card, about 320×56), medium (inline list, about 480×90), large (explorer, full width). One function with a size argument.

## 6. Season lines

Computed at site build from all published editions for the player; never stored. Season values are ratios of summed numerators and denominators. Below the threshold a line shows counts only; at or above it the rate is added. Wording is identical for good and poor results.

| Group | Lines (counts always) | Rate shown from |
|---|---|---|
| All players | Games played; snaps and snap share by phase ("412 defensive snaps, 78% of the team's") | — |
| QB | Dropbacks (`qb_dropback` = 1, excluding kneels and spikes); expected points per dropback (mean `qb_epa` over those rows); success rate (share with EPA > 0); completion percentage over expected in percentage points: over passer rows with non-null `cp`, `100 × Σ(complete_pass − cp) / count` | 50 dropbacks; CPOE from 50 rows with `cp` |
| RB | Carries; expected points per carry; success rate; targets and catches | 30 carries |
| WR / TE | Targets and share of team targets (Σ player targets / Σ team targets); share of team air yards (same, air yards); catchable targets and drops (FTN); team expected points when targeted | 15 targets |
| Defense (DL, LB, DB) | Impact plays with components (sacks, tackles for loss, interceptions, passes defended, forced fumbles, QB hits, 3rd/4th-down stops); tackles; charted coverage targets, completions and yards; pressures; missed tackles in attempts | Impact plays per 100 defensive snaps from 100 snaps. Coverage, pressure and tackling stay counts in this release |
| OL | Games, snaps, snap share | — (no penalty line: linemen usually have no weekly stats row, and absence is not zero) |

Snap shares, target shares and air-yard shares are always Σ player / Σ team over the season, never an average of weekly percentages.

Rules carried over from the metrics red team: coverage is "charted in coverage", never "allowed"; receiver EPA is "team expected points when targeted"; no cross-position ranking; a missing source is shown as pending, never zero.

## 7. Data

### 7.1 Edition schema version 2

`edition.json` `schema` becomes 2. Per player:

- `plays`: every recorded play (§4), each with `play_id`, `quarter`, `clock`, `offense`, `defense`, `offense_name`, `defense_name`, `play_type`, `down`, `ydstogo`, `goal_to_go`, `yardline_100`, `yards_gained`, `air_yards`, `yards_after_catch`, `pass_attempt`, `rush_attempt`, `complete_pass`, `sack`, `interception`, `fumble`, `lateral`, `penalty`, `qb_kneel`, `qb_spike`, `two_point_attempt`, `cp`, `qb_dropback`, `qb_epa`, `epa`, `side`, `impact`, `roles` (the matched role names), and `description`. Missing values are `null`, never zero.
- `key_plays`: unchanged (the same list of play dicts as schema 1), so every current consumer keeps working; the explorer matches them to `plays` by `play_id`.
- `snaps`: gains team denominators `team_offense`, `team_defense`, `team_st`: the most snaps any player on the team played in that phase of the game, from the game's snap table (dividing by two-decimal `*_pct` values cannot recover whole numbers). `null` when the team has no rows.
- `usage`: `targets`, `team_targets`, `air_yards`, `team_air_yards` from the weekly stats (`targets / target_share`, `receiving_air_yards / air_yards_share`, accepted only when within 0.05 of a whole number); `null` when a share is missing or zero.

All fields come from files already downloaded (play-by-play, weekly stats, snap counts), and every consumed column is added to that source's required columns so upstream renames fail loudly. The play-by-play fixture and `scripts/make_fixtures.py` gain the new columns, and the fixture gains real Week 2 rows for edge cases not involving our players: an interception, a lost fumble, a lateral, a penalty, a goal-line touchdown, a safety if one exists, and a sack.

### 7.2 Player addresses

`data/alumni.json` gains `slug` for every entry: lowercase name, letters and digits joined by hyphens ("J.J. McCarthy" → "jj-mccarthy", "DJ Turner II" → "dj-turner-ii"). If two entries would share a slug, the later one gets `-<last 4 of gsis_id>`. A test enforces presence, format and uniqueness; once published a slug never changes.

### 7.3 Size

Week 2 has about 40 recorded plays across the followed players; `plays` adds roughly 30 KB to its `edition.json`. No concern at this scale.

## 8. Code layout

- `src/evidence.py`: existing rules unchanged; adds the recorded-play role allowlist (§4) and diagram eligibility flags as pure functions.
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

- **Data:** `plays` for the Week 2 fixture matches the player's recorded plays (allowlisted roles) and their field values; text-only plays for missing geometry; schema-1 editions still render.
- **Diagram geometry:** the eligibility matrix row by row (every text-only reason, and sack before run before pass); start, marker and end positions for runs, losses, sacks, completions (air yards + YAC), incompletions, goal-to-go, touchdowns at x = 100, losses into the own end zone, and left-to-right orientation for either team; real edge-case fixture rows plus synthetic cases.
- **Aggregation:** CPOE over matched rows; season shares as ratios of sums; denominators rejected when not whole numbers; the OL table has no penalty line.
- **Pages:** every registry player has an evergreen page and a week page per edition; game-log links resolve; thresholds switch counts to rates; non-players get correct pages; slugs match the registry; the players index groups correctly.
- **Explorer:** without JavaScript every play has a diagram; a headless-browser test (Edge, as used for the share card) checks filtering, selection and `#play-` fragments.
- **Existing gates:** link check on every page, phone-width overflow check, `src.editorial check`, and a Codex review before each PR merges.

## 11. Rollout

Five PRs. Each is deployable on its own, merged by the owner, and checked live after deploy:

1. **Data contract.** Schema 2 as additive fields (`plays`, snap and usage denominators; `key_plays` unchanged), registry slugs, required-column validation, edge-case fixtures. The site renders exactly as before.
2. **Field diagram.** `src/field.py` with the eligibility matrix and geometry, fully tested; no page uses it yet.
3. **Player pages.** Evergreen pages, week pages with the explorer (`static/explorer.js`), the players index.
4. **Homepage and docs.** Card strips, "Players" in the navigation, methodology and operations notes.
5. **Backfill.** A canary rebuild of Week 2 is diffed and reviewed first; then Weeks 1 to 3 are rebuilt with full plays (headline files untouched, current-roster notes kept as published). A rebuild reads today's upstream data, which may include NFL corrections since first publication; each page's data-as-of line shows the rebuild time.

If time runs short for the Week 4 edition, PR 4's card strips move to the following week; PRs 1 to 3 carry the core feature.

## 12. Risks

- Rebuilt weeks may differ slightly from what first published because of upstream corrections; the canary diff shows any change before merge.

- Some recorded plays lack air yards or spots (laterals, penalties with enforcement): these fall back to text, never guessed.
- Players recorded only on special teams get few diagrams in this release.
- Season lines early in the season are mostly counts; that is intended.

## 13. Review record

A Codex review on 2026-09-28 found, and this revision fixes: interceptions drawn as incompletions, sacks mis-branched as passes, fumbles and laterals drawn as one path (now text only); a missing eligibility order and end-zone model; an over-broad "any player id" play rule (now an allowlist with honest "recorded plays" wording and lineman/defensive-back caveats); filter names that read like individual grades; a CPOE formula mixing populations; season shares that averaged weekly percentages; an OL penalty line built on missing data; rates on sparse coverage and pressure counts; a schema change that would have broken deployed consumers; and an oversized second PR.
