# Roster moves with sourced notes: design

Date: 2026-09-30. Status: approved in conversation; awaiting written-spec review.

## Why

The Week 3 data knew J.J. McCarthy had moved from the Vikings to the Giants (`team_changed: true`, and his next game was listed with the Giants), but the site only said so in the Up next list: "J.J. McCarthy (now with NYG)". His Availability desk entry and player page still showed the Vikings. Readers should see a team change where they look for the player, and the site should say *why* ("traded") only when the owner backs it with a reputable link.

## Decisions

- Roster moves are **team changes**: joining a different NFL team, or **leaving a team** (released, retired, or no longer on any roster). Status changes on the same team (practice squad, reserve list) are out of scope, because a reserve-list move invites an injury reading the site must never imply.
- A move appears on the **player's card** (or, for a player without a card, under his name in the **Availability desk**) and on his **player page**, and the edition PR lists it. No separate edition section; the headline draft never sees moves.
- The owner adds an optional **sourced note** in that week's `editorial.toml`. The site writes the verifiable part of the sentence from the data; the owner writes only an optional `details` clause attributed to the source.
- Allowed sources are official and major free outlets: nfl.com, operations.nfl.com, espn.com, apnews.com and the 32 team sites. Paywalled outlets are excluded (The Athletic); ESPN+ stories cannot be told apart by URL, so the PR reminds the owner to avoid them.
- Automation never states a move reason on its own, and nothing is scraped.

## 1. Detection (`src/edition.py`)

Each player in `edition.json` gains `move`: `null`, or

```json
{"kind": "moved_after_game", "from": "MIN", "to": "NYG",
 "from_name": "Minnesota Vikings", "to_name": "New York Giants",
 "status": null, "last_week_with_old_team": 3}
```

For a departure, `to` and `to_name` are null and `status` is `"CUT"` (released), `"RET"` (retired) or `"none"` (on no roster in the data).

Pure functions, tested on their own. "Before" is the player's team in the **previous published edition**; "this week" is the team in this week's game (or roster, if he had no game); "now" is the current roster at build time.

| Kind | Trigger |
|---|---|
| `moved_after_game` | This week's team is set, and now he is on a different NFL team (today's `team_changed` rule) |
| `first_week` | Before he was on one team; this week he is on a different NFL team |
| `left_after_game` | This week's team is set, and now he is on no NFL team |
| `left_before_week` | Before he was on a team; this week he is on no NFL team |

Neutral lines (no owner note):

| Kind | Line |
|---|---|
| `moved_after_game` | "Now on the Giants' roster (was Vikings in Week 3)." |
| `first_week` | "First week with the Giants (was Vikings in Week 3)." |
| Departure, status `CUT` | "Released by the Vikings (on their roster in Week 3)." |
| Departure, status `RET` | "Listed as retired (on the Vikings' roster in Week 3)." |
| Departure, status `none` | "No longer on the Vikings' roster (last listed in Week 3)." |

"Released" and "retired" are official roster statuses in the data, so they need no note; a player who is simply missing gets only the softer "No longer on…" line.

- At most one move per player per edition. If an arrival (`first_week`) and a later change (`moved_after_game` or `left_after_game`) both apply, the later change wins, with `from` = this week's team; the arrival is visible on the previous edition.
- "First week", not "first game": the player may be inactive for the new team.
- No previous edition for the player (Week 1 or a new registry entry): no `first_week` or `left_before_week` move.
- Once a player is off every roster, later weeks are not moves (before and this week both have no team). If he signs again, that is a `first_week` move with `from` = his last team.
- Two moves in one week: compare only this week with before (the net change).
- `last_week_with_old_team` is this week for `moved_after_game` and `left_after_game`, and the previous edition's week for `first_week` and `left_before_week` (a bye in between does not count as a week with the old team).
- `team_changed` stays for compatibility; `move` is the field the site reads.
- The builder reads the previous edition from `editions/` on the checked-out branch (`main` in automation). The previous edition is the highest-numbered week lower than this one in the same season.
- Rebuilding a published edition keeps its published `move` (as #30 kept roster notes).

Schema: `edition.json` `schema_version` becomes 3 (additive field). Editions without `move` render as if it were `null`.

## 2. The sourced note (`src/editorial.py`)

`editorial.toml` accepts zero or more entries:

```toml
[[roster_moves]]
player_id = "00-0039923"
kind = "trade"                               # trade | waiver claim | signing | release | waived
date = 2026-09-28
details = "for a 2027 fourth-round pick"     # optional, the owner's words from the source
source = "https://www.giants.com/news/..."
```

Rendered: **"Traded to the Giants on Sep 28 for a 2027 fourth-round pick. Source: Giants.com"**. Without `details`: "Traded to the Giants on Sep 28." Arrival kinds name the new team: `trade` → "Traded to", `waiver claim` → "Claimed off waivers by", `signing` → "Signed by". Departure kinds name the old team: `release` → "Released by", `waived` → "Waived by" ("Waived by the Vikings on Sep 28."). The team name comes from the move's `to_name` or `from_name` nickname, never from the owner's text.

### Checks (errors: block CI and the merge)

| Field | Rule |
|---|---|
| `player_id` | A player whose `move` is not null in the same edition; at most one entry per player |
| `kind` | One of the five values, and it must fit the move: `trade`, `waiver claim` and `signing` need an arrival (`moved_after_game`, `first_week`); `release` and `waived` need a departure (`left_after_game`, `left_before_week`) |
| `date` | A TOML date; on or before the edition's `generated_at` date (Eastern); on or after the date of the player's game in the week named by `last_week_with_old_team` (skipped when that week has no game for him) |
| `source` | `https://`, host equal to or a subdomain of an allowed domain (one list in the code: `ALLOWED_SOURCES`) |
| `details` | Optional; at most 100 characters; no control characters, line breaks or URLs; passes `BLOCKED_TERMS` and the `IMG_ALONE` rule; must not contain the named team's name, nickname or abbreviation, or a month name (the site writes team and date) |

Warnings (shown in CI and the PR, never blocking): a detected move with no note; a note present, with the reminder "Avoid paywalled stories (for example ESPN+)."

### Source labels

A small map from domain to label (`nfl.com` → "NFL.com", `operations.nfl.com` → "NFL Football Operations", `espn.com` → "ESPN", `apnews.com` → "AP", each team site → "<Nickname>.com" as written on that site, e.g. "Giants.com"). Unknown subdomains of an allowed domain fall back to the domain.

### Where a note applies

A note is keyed to the move: (player id, from team, to team, with `to` null for a departure). Any edition's card or player page that shows the same move uses the sourced sentence if any published edition carries a matching note. If several do, the earliest edition's note is used. So a note added in the Week 3 PR also shows on Week 4's "First week with the Giants" card.

### Round trip and automation

- `editorial.dumps` writes `roster_moves` entries back unchanged, so owner notes survive a refresh (the pipeline already keeps an owner-edited `editorial.toml`).
- When the bot drafts `editorial.toml`, it appends one commented-out `[[roster_moves]]` block per detected move, pre-filled with `player_id`, empty `kind`, `date`, `details` and `source` lines, and a comment naming the player and both teams. Being commented out, the stub adds no entry until the owner uncomments it.
- The edition PR body gains a **Roster moves** checklist: one line per move ("J.J. McCarthy: Vikings → Giants (moved after the game). Add a sourced note or leave the neutral line."). No moves: the section is omitted.
- The Claude headline draft and its fact sheet do not include moves or notes.

## 3. On the site (`src/site.py`, templates, `static/styles.css`)

- **Card:** one line under the score in the body font (no all-caps label), with a 3px left border in the new team's color (the old team's color for a departure). Sourced sentences end with "Source: <label>" linking to the source.
- **Availability desk:** a player without a card (inactive, practice squad, not on a roster) gets the same line under his name in his desk group.
- **Player page:** the same line near the top, under the latest game. The evergreen page shows the latest edition's move; a player moved in Week 3 reads "Now on the Giants' roster…" (Week 3), then "First week with the Giants…" (Week 4), then nothing (Week 5). A departure shows until a later edition shows no move.
- **Links:** source links open the page directly (no `target="_blank"`), with `rel="external noopener"`; the visible label names the outlet so screen readers announce it.
- Unchanged: the "(now with NYG)" label in Up next, and the Availability desk's groups and evidence lines.
- Team colors stay a border here; the wider team-color treatment is a separate design pass.

## Testing

- **Detection:** all four kinds; departure status `CUT`, `RET` and `none`; an arrival and a later change in one week; no previous edition; off every roster for a second week (no move); re-signing after a release; two moves in one week; historical rebuild keeps the published move.
- **Checks:** one test per rule above (off-list host, look-alike host such as `giants.com.evil.test`, `http://`, future date, date before the game in `last_week_with_old_team`, player without a move, duplicate player, `kind` that does not fit the move (`release` on an arrival, `trade` on a departure), team name or month in `details`, injury term, "IMG" alone, 101 characters, URL in `details`).
- **Rendering:** neutral line for each kind and departure status; a desk entry for a player without a card; sourced sentence with and without `details`; a Week 3 note carried to a Week 4 card; source label fallback; escaping.
- **Golden:** a fixture built from the real McCarthy move (2026 Week 3, MIN → NYG).
- **Automation:** PR checklist present or omitted; commented stubs in a drafted `editorial.toml` parse as TOML with no entries; `roster_moves` survives `dumps`/`loads` and a refresh.

## Rollout

1. Build and merge the feature. Week 4 then shows McCarthy's "First week with the Giants" automatically.
2. One small PR rebuilds Week 3 to add `move`, keeping everything else as published (the #30 procedure), and adds the owner's McCarthy note to Week 3's `editorial.toml`. The owner picks the source link.
3. `docs/OPERATIONS.md` gains a short "Roster moves" section: what the checklist means, the allowed sites, and an example entry. `CLAUDE.md` gains one rule: "A move's reason (traded, claimed, signed, waived) appears only from an owner note with an allowed source; only the data's own statuses (released, retired) appear without one."

## Out of scope

- Status changes on the same team (practice squad, reserve list, exempt list).
- Automated news feeds, APIs or scraping.
- Trade terms in structured form (picks, other players).
- The team-color and card design pass (separate, bounded design).
