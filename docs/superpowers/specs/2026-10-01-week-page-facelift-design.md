# Player week page facelift: design

Date: 2026-10-01. Status: approved in conversation; awaiting written-spec review.

## Why

The landing page's team-color design works; the player week page (`/players/<slug>/<edition-id>/`) does not. Its field is a flat gray box with no yard numbers, hash marks or arrowheads, so a 10-yard sack draws like a 10-yard gain pointed the other way, and on a defender's page nothing says whether a play helped the alum's team. The words come straight from the play-by-play ("(8:54) (Shotgun) 16-J.Goff sacked at DET 48 for -10 yards (8-A.Cisco).") or read robotically ("Good for the Jets defense: the Lions lost 2.5 expected points"). Filters are unstyled browser buttons and two disclaimers stack under them.

## Goal and audience

Plain language up front for fans, family and IMG Academy staff, with the numbers one tap away (owner choice C). Success: opening Andre Cisco's Week 3 page, a reader can tell within seconds which plays he made and whether each helped the Jets, and the page reads like a sportswriter wrote it. Accuracy is unchanged: presentation and wording only.

## Decisions

- Broadcast orientation: the offense always moves left to right; direction is shown by an arrowhead and a +/− yardage label, outcome by color and by a text tag (owner choice A).
- Play lines are written from the saved play data with sentence templates; no Claude-written text on this page (owner choice A).
- Colors follow the landing page: team bars (`site.team_bar`) and the IMG Academy palette; team colors stay bars, borders, the ball path and tags; the yellow first-down marker stays (football convention).
- The raw play-by-play, expected points and air yards / yards after the catch move into a collapsed "More" layer; nothing is deleted.

## 1. Page layout

- Top: the existing team-bar header and stat tiles, then a **game summary line** built from counts: "Six plays with his name on them: a sack, four tackles and a 3rd-down stop."
- Plays section:
  - Desktop (≥ 900px): two columns, play list left, large field right that stays in view while scrolling (`position: sticky`) and shows the selected play.
  - Phones: one column; each play card shows its own field; tapping a play opens its details and scrolls the big field into view when one is shown.
  - Filters: one row of buttons styled like the landing page, the active one in the team bar color: **All**, **Impact plays** (sacks, takeaways, tackles for loss, stops: today's `impact` set), **Helped the <nickname>**, **Hurt the <nickname>**.
- Each play is a compact card:
  ```
  Q1 · 8:54                               [ Big play ]
  Cisco sacked Goff for a 10-yard loss.
  3rd & 7 at the DET 42
  [ small field drawing ]
  ▸ More
  ```
  - "More" (a `<details>` element) holds the play-by-play text, the expected-points sentence ("The Lions lost 2.5 expected points on the play.") and air yards / yards after the catch when present.
- One "About these drawings" note at the end of the section replaces the two stacked disclaimers: drawings show where the play started and ended, not player tracking; expected points describe the whole play, not one player.
- Players who did not play keep today's status section; editions without full play lists keep showing their key moments in the same card format.

## 2. Outcome tags and colors

- `helped` is today's three-way `positive` from `site.play_view`: True, False, or None when EPA is missing or rounds to 0.0. Unchanged rule.
- Tag: **"Big play"** when helped and the absolute EPA is ≥ 2.0; **"Helped the <nickname>"** when helped otherwise; **"Hurt the <nickname>"** when not helped; no tag when None.
- Tag styles: "Big play" filled with the team bar color and bar text color; "Helped" outlined in the team color; "Hurt" outlined in the site slate (`--muted`).
- Active filter button, the selected card's left border and "Big play" use the team bar color. Everything else uses the IMG Academy palette (navy headings, white cards with hairline borders, the `--wash` gray).

## 3. The field drawing (`src/field.py`)

- Turf in `--wash`; navy yard lines every 5 yards (heavier at 10s); yard numbers at each 10 (10, 20, 30, 40, 50, 40, 30, 20, 10) along the bottom edge; short hash marks at each yard along both sides, sized to the drawing.
- End zones filled with each team's bar color (`site.team_bar` for that team), labeled with the team abbreviation in that bar's text color. Offense's end zone left, defense's right, as today.
- Line of scrimmage: solid navy. First-down marker: yellow (`--first-down`), unchanged.
- Ball path with an arrowhead (an SVG marker) at the end, and a bold yardage label beside the arrowhead: "+13", "−10", "0":
  - runs, sacks and yards after the catch: solid line;
  - passes: a dashed arc from the line of scrimmage to the catch point (air yards), then the solid yards-after-catch line;
  - incompletions: a dashed arc ending in an open circle, labeled "Incomplete".
- Path color: the alum's team color (as its bar color, for contrast on the turf) when helped; `--muted` slate when hurt; navy when None.
- Sizes: large 960×240 (was 960×160); card size 480×120; the landing-page strip keeps its 320×56 size and the new style, omits yard numbers and hash marks, and keeps the arrowhead and yardage label.
- Which plays get a drawing, the yard window and clamping are unchanged (text-only: penalties, fumbles, interceptions, laterals, kneels, spikes, two-point tries, special teams, missing or out-of-range spots).
- `field.svg(play, size, team_color, outcome="", helped=None, teams=None)`: `helped` picks the path color; `teams` maps team abbreviation to `(bar, ink)` for the end zones. The accessible label adds the yardage and the outcome tag.

## 4. Plain-language lines (`src/playtext.py`, new)

### Names

- Each saved play gains `passer_name`, `rusher_name`, `receiver_name` from the play-by-play's `passer_player_name`, `rusher_player_name`, `receiver_player_name` (e.g. "J.Goff"). They are added to the required download columns; a blank stays null.
- Displayed as the last name: everything after the leading initial and its period ("J.Goff" → "Goff", "A.St. Brown" → "St. Brown"). A name without that shape is shown as written. The alum is his registry last name ("Cisco"). Teams use their nickname ("the Lions").
- Weeks 1–3 are rebuilt with `src.edition --rebuild` to add the names; every published fact stays.

### Templates

Chosen from the alum's roles on the play (`roles`) and the play's result:

| His role | Line |
|---|---|
| sack | "Cisco sacked Goff for a 10-yard loss." / "…for no gain." |
| pass defense (incomplete) | "Newsome broke up Ward's pass to Robinson." |
| tackle after a catch | "Cisco brought down Gibbs after a 13-yard catch." |
| tackle on a run | "Cisco stopped Montgomery after a 2-yard run." / "…for a 3-yard loss." / "…for no gain." |
| assisted tackle | "Cisco helped bring down Gibbs after a 13-yard catch." |
| interception / forced fumble | "Cisco intercepted Goff." / "Cisco forced a fumble." |
| rusher | "Allen ran for 6 yards." / "…lost 2 yards." / "…was stopped for no gain." |
| receiver (catch) | "Tate caught a 12-yard pass from Ward." |
| receiver (incomplete) | "Ward's pass to Tate fell incomplete." |
| passer | "McCarthy completed a 15-yard pass to Jefferson." / "McCarthy's pass to Jefferson fell incomplete." / "McCarthy was sacked for a 7-yard loss." |

- Add-ons: "…for a touchdown" when the alum is the `td` role on the play; ", stopping the <nickname> on 3rd down" (or 4th) when the play's impact tag is a down stop.
- Each row has two phrasings, picked by play number parity, so a page does not repeat itself.
- Fallback: when no template fits or a needed name is missing, the line is the play-by-play text with the clock, formation tags ("(Shotgun)", "(No Huddle, Shotgun)") and jersey numbers removed. Never invented.

### Game summary line

"<Count word> plays with his name on them: <list>." The list counts impact tags and roles in a fixed order (sacks, interceptions, forced fumbles, passes defended, tackles for loss, tackles, down stops; catches, carries, completions for offense), written in words up to ten ("a sack, four tackles and a 3rd-down stop"). One play: "One play with his name on it: …". No plays: no summary line.

### Rules (tested)

- Every number in a line comes from that play's fields (`yards_gained`, `air_yards`, `yards_after_catch`, `down`).
- A missing value makes a simpler sentence, never a zero ("Cisco brought down Gibbs.").
- No injury, illness or benching words (`editorial.BLOCKED_TERMS`).
- "IMG Academy" in full wherever it appears.

## 5. Explorer script (`static/explorer.js`)

Same behavior as today: filters, selecting a play, `#play-<id>` links select a play on load, a filter that hides the selected play selects the first visible one. Changes: filter values map to `impact`, `helped`, `hurt`; on narrow screens selecting a play scrolls the big field into view only when it is displayed. Without JavaScript every card keeps its own drawing and its "More" details.

## Testing

- `playtext`: one test per template row and phrasing, add-ons, the fallback (cleaned text), missing-name and missing-value cases, the summary line (one, several, none), blocked terms.
- Tags: EPA just under and at 2.0, a value rounding to 0.0, missing EPA, offense and defense sides.
- `field`: arrowhead direction and the +/− label for gain, loss and no gain; path color by `helped`; yard numbers and hash marks only inside the window; end-zone text contrast ≥ 4.5 for every team color; text-only plays unchanged; the accessible label includes yardage and tag.
- Data: the three name columns required at download; blanks stay null; golden edition updated additively.
- Real data: Cisco's and Newsome's Week 3 lines after the rebuild.
- Site: the two-column layout markup, the tags, the "More" layer, the single note; desktop and phone screenshots for the owner before the PR.

## Rollout

1. One feature PR (code, templates, CSS, tests, `CLAUDE.md` map line for `playtext.py`).
2. A follow-up PR rebuilds Weeks 1–3 with `--rebuild` to add the names, reviewed like #30.
3. Week 4 gets everything from the automated run.

## Out of scope

- The landing page and its cards (the card strips pick up the new drawing style automatically).
- The evergreen season page beyond its top-play drawing.
- Claude-written text on player pages.
- Player tracking data or any third-party imagery.
