# IMG Academy → NFL

Independent, evidence-led weekly coverage of NFL players who played football at IMG Academy, by [Bryce Murphy](https://www.linkedin.com/in/bryce-murphy/). A personal portfolio project, not an official IMG Academy or NFL publication and not endorsed by either.

**Read it:** https://bryce-murphy.github.io/img-academy-nfl-reports/

## How an edition is made

1. On Tuesday at 2:30 p.m. Eastern, a scheduled workflow checks that every game of the week is final and that the nflverse feeds have landed. It tries again at 8:30 p.m. and at 6:30 a.m. Wednesday.
2. It builds `editions/<season>-week-<WW>/edition.json`, applies the accuracy rules below, and drafts the headline with Claude. If the draft fails a check, a plain template headline is used instead.
3. A GitHub App opens a pull request. The editor reads the headline, edits it if needed, and merges.
4. Merging renders the site and deploys it to GitHub Pages, then confirms that the live page shows the new edition.

Problems open an `Edition <id> blocked` issue instead of publishing. The routine is in [operations](docs/OPERATIONS.md).

## Accuracy rules

- Players are identified by stable GSIS/PFR IDs, never by name.
- Only completed weeks are reported. Schedule scores must match the play-by-play end-of-game record.
- Passing, rushing and receiving yards must reconcile with play-by-play. If they don't, that player's stat line is withheld and labeled.
- A player counts as having played only with positive snaps, a recorded role in a play, or a positive statistic. Absences come only from weekly roster statuses (inactive, practice squad, reserve list) or complete snap tables. Anything else is "Participation unverified".
- Injury reports are pregame designations, not proof of absence. No illness or benching claim is guessed.
- No raw tracking data and no invented grades. EPA belongs to the offense on a play.

## Run it locally

```sh
python -m venv .venv
.venv/Scripts/python -m pip install --require-hashes -r requirements.txt
.venv/Scripts/python -m unittest discover -s tests -v
.venv/Scripts/python -m src.edition --season 2026 --week 3
.venv/Scripts/python -m src.site build --out _site --check
```

On macOS or Linux, use `.venv/bin/python`.

## Repository map

- `src/`: data loading (`data.py`), evidence rules (`evidence.py`), readiness (`readiness.py`), the edition model (`edition.py`), up-next (`upnext.py`), headlines (`editorial.py`), the site (`site.py`), deployment checks (`verify.py`), the GitHub client (`github.py`) and the weekly attempt (`pipeline.py`).
- `editions/`: published editions (data plus the approved headline). Automation never rewrites a merged edition.
- `templates/`, `static/`: the site design.
- `data/alumni.json`: the sourced alumni registry.
- `docs/`: the spec and plan, operations, data notes, media policy and delivery architecture.

## Licenses and media

Code is MIT. nflverse data is generally CC BY 4.0; FTN data has different terms. The site uses no team logos, player photographs or IMG Academy marks. See the [media policy](docs/MEDIA_RIGHTS.md) and [security policy](SECURITY.md).
