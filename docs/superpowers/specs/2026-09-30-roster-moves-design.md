# Roster moves with sourced notes: design

Date: 2026-09-30. Status: approved in conversation; awaiting written-spec review.

## Why

The Week 3 data knew J.J. McCarthy had moved from the Vikings to the Giants (`team_changed: true`, and his next game was listed with the Giants), but the site only said so in the Up next list: "J.J. McCarthy (now with NYG)". His card and player page still showed the Vikings. Readers should see a team change where they look for the player, and the site should say *why* ("traded") only when the owner backs it with a reputable link.

## Decisions

- Only **team changes** count as roster moves: a player on a different NFL team than before. Status changes on the same team (practice squad, reserve list, released) are out of scope, because a reserve-list move invites an injury reading the site must never imply.
- A move appears on the **player's card** and **player page**, and the edition PR lists it. No separate edition section; the headline draft never sees moves.
- The owner adds an optional **sourced note** in that week's `editorial.toml`. The site writes the verifiable part of the sentence from the data; the owner writes only an optional `details` clause attributed to the source.
- Allowed sources are official and major free outlets: nfl.com, operations.nfl.com, espn.com, apnews.com and the 32 team sites. Paywalled outlets are excluded (The Athletic); ESPN+ stories cannot be told apart by URL, so the PR reminds the owner to avoid them.
- Automation never states a move reason on its own, and nothing is scraped.

## 1. Detection (`src/edition.py`)

Each player in `edition.json` gains `move`: `null`, or

```json
{"kind": "moved_after_game", "from": "MIN", "to": "NYG",
 "from_name": "Minnesota Vikings", "to_name": "New York Giants", "last_week_with_old_team": 3}
```

Pure functions, tested on their own:

| Kind | Trigger | Neutral line |
|---|---|---|
| `moved_after_game` | The current roster team differs from this week's game team (today's `team_changed` rule) | "Now on the Giants' roster (was Vikings in Week 3)." |
| `first_week` | This week's team differs from the player's team in the **previous published edition** | "First week with the Giants (was Vikings in Week 3)." |

- If both triggers apply (moved into a team for this week and out again afterwards), `moved_after_game` wins, with `from` = this week's team; the earlier change is visible on the previous edition.
- "First week", not "first game": the player may be inactive for the new team.
- No previous edition for the player (Week 1 or a new registry entry): no `first_week` move.
- No current team (released, retired, not found): not a move.
- Two moves in one week: compare only this week's team with the previous edition's team (the net change).
- `last_week_with_old_team` is this week for `moved_after_game`, and the previous edition's week for `first_week` (a bye in between does not count as a week with the old team).
- `team_changed` stays for compatibility; `move` is the field the site reads.
- The builder reads the previous edition from `editions/` on the checked-out branch (`main` in automation). The previous edition is the highest-numbered week lower than this one in the same season.
- Rebuilding a published edition keeps its published `move` (as #30 kept roster notes).

Schema: `edition.json` `schema_version` becomes 3 (additive field). Editions without `move` render as if it were `null`.

## 2. The sourced note (`src/editorial.py`)

`editorial.toml` accepts zero or more entries:

```toml
[[roster_moves]]
player_id = "00-0039923"
kind = "trade"                               # trade | waiver claim | signing
date = 2026-09-28
details = "for a 2027 fourth-round pick"     # optional, the owner's words from the source
source = "https://www.giants.com/news/..."
```

Rendered: **"Traded to the Giants on Sep 28 for a 2027 fourth-round pick. Source: Giants.com"**. Without `details`: "Traded to the Giants on Sep 28." Verbs: `trade` → "Traded to", `waiver claim` → "Claimed off waivers by", `signing` → "Signed by". The team name comes from the move's `to_name` nickname, never from the owner's text.

### Checks (errors: block CI and the merge)

| Field | Rule |
|---|---|
| `player_id` | A player whose `move` is not null in the same edition; at most one entry per player |
| `kind` | One of the three values |
| `date` | A TOML date; on or before the edition's `generated_at` date (Eastern); on or after the date of the player's game in the week named by `last_week_with_old_team` (skipped when that week has no game for him) |
| `source` | `https://`, host equal to or a subdomain of an allowed domain (one list in the code: `ALLOWED_SOURCES`) |
| `details` | Optional; at most 100 characters; no control characters, line breaks or URLs; passes `BLOCKED_TERMS` and the `IMG_ALONE` rule; must not contain the new team's name, nickname or abbreviation, or a month name (the site writes team and date) |

Warnings (shown in CI and the PR, never blocking): a detected move with no note; a note present, with the reminder "Avoid paywalled stories (for example ESPN+)."

### Source labels

A small map from domain to label (`nfl.com` → "NFL.com", `operations.nfl.com` → "NFL Football Operations", `espn.com` → "ESPN", `apnews.com` → "AP", each team site → "<Nickname>.com" as written on that site, e.g. "Giants.com"). Unknown subdomains of an allowed domain fall back to the domain.

### Where a note applies

A note is keyed to the move: (player id, from team, to team). Any edition's card or player page that shows the same move uses the sourced sentence if any published edition carries a matching note. If several do, the earliest edition's note is used. So a note added in the Week 3 PR also shows on Week 4's "First week with the Giants" card.

### Round trip and automation

- `editorial.dumps` writes `roster_moves` entries back unchanged, so owner notes survive a refresh (the pipeline already keeps an owner-edited `editorial.toml`).
- When the bot drafts `editorial.toml`, it appends one commented-out `[[roster_moves]]` block per detected move, pre-filled with `player_id`, empty `kind`, `date`, `details` and `source` lines, and a comment naming the player and both teams. Being commented out, the stub adds no entry until the owner uncomments it.
- The edition PR body gains a **Roster moves** checklist: one line per move ("J.J. McCarthy: Vikings → Giants (moved after the game). Add a sourced note or leave the neutral line."). No moves: the section is omitted.
- The Claude headline draft and its fact sheet do not include moves or notes.

## 3. On the site (`src/site.py`, templates, `static/styles.css`)

- **Card:** one line under the score in the body font (no all-caps label), with a 3px left border in the new team's color. Sourced sentences end with "Source: <label>" linking to the source.
- **Player page:** the same line near the top, under the latest game. The evergreen page shows the latest edition's move; a player moved in Week 3 reads "Now on the Giants' roster…" (Week 3), then "First week with the Giants…" (Week 4), then nothing (Week 5).
- **Links:** source links open the page directly (no `target="_blank"`), with `rel="external noopener"`; the visible label names the outlet so screen readers announce it.
- Unchanged: the "(now with NYG)" label in Up next and the Availability desk.
- Team colors stay a border here; the wider team-color treatment is a separate design pass.

## Testing

- **Detection:** both kinds; both at once; no previous edition; no current team; two moves in one week; historical rebuild keeps the published move.
- **Checks:** one test per rule above (off-list host, look-alike host such as `giants.com.evil.test`, `http://`, future date, date before the game in `last_week_with_old_team`, player without a move, duplicate player, team name or month in `details`, injury term, "IMG" alone, 101 characters, URL in `details`).
- **Rendering:** neutral line for each kind; sourced sentence with and without `details`; a Week 3 note carried to a Week 4 card; source label fallback; escaping.
- **Golden:** a fixture built from the real McCarthy move (2026 Week 3, MIN → NYG).
- **Automation:** PR checklist present or omitted; commented stubs in a drafted `editorial.toml` parse as TOML with no entries; `roster_moves` survives `dumps`/`loads` and a refresh.

## Rollout

1. Build and merge the feature. Week 4 then shows McCarthy's "First week with the Giants" automatically.
2. One small PR rebuilds Week 3 to add `move`, keeping everything else as published (the #30 procedure), and adds the owner's McCarthy note to Week 3's `editorial.toml`. The owner picks the source link.
3. `docs/OPERATIONS.md` gains a short "Roster moves" section: what the checklist means, the allowed sites, and an example entry. `CLAUDE.md` gains one rule: "A move's reason (traded, claimed, signed) appears only from an owner note with an allowed source."

## Out of scope

- Status changes on the same team, and releases.
- Automated news feeds, APIs or scraping.
- Trade terms in structured form (picks, other players).
- The team-color and card design pass (separate, bounded design).
