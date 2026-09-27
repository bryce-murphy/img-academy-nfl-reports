# Verified nflverse feed semantics

Checked 2026-09-26 against 2026 Weeks 1–3; the Week 2 fixture tests pin these facts.

- **Weekly roster `status`.** `INA` (code `A01`) appears for about 6–7 players per team per week and changes week to week (DeMonte Capehart: `INA` in Week 2, `ACT` in Week 3), which matches game-day inactives. `DEV` (`P01`, `P03`, `P06`, `P07`) is the practice squad; elevated practice-squad players appear as `ACT` with a `P` code. `RES` covers reserve lists (`R01`, `R04`, `R48`, …). `CUT` is released; `RET` retired; `EXE` exempt. The nflverse dictionary describes `status` only generally ("Active, Inactive, Injured Reserve, Practice Squad etc").
- **Snap counts.** Each team has 45–48 rows per game, only for players with at least one snap. Absence from a complete table means no snaps. "Complete" = at least 22 distinct players with offensive and defensive snaps (`evidence.COMPLETE_SNAP_TABLE_MIN_PLAYERS`).
- **Schedule times.** `gametime` is Eastern (Thursday night at Green Bay is `20:15`). `stadium` holds the venue name, including international venues.
- **Play-by-play size.** 5,662 rows through early Week 3 decompress to 11.4 MB (about 2 KB per row). A full season is about 100 MB, under `MAX_BYTES` (180 MB). Only the reporting week's rows are kept in memory.
- **Quarters.** `qtr` is `5` for overtime; the site shows `OT`.
- **Pages artifact action.** `actions/upload-pages-artifact` v5.0.0 pins its nested `actions/upload-artifact` by full SHA, so it satisfies the repository's SHA-pinning policy.
- **Feed timing (nflverse data schedule).** Play-by-play and player stats: nightly after game days. Rosters and injuries: 07:00 UTC daily. Snap counts: 00/06/12/18 UTC. Schedules: every 5 minutes. Next Gen Stats: 3–5 a.m. ET.
