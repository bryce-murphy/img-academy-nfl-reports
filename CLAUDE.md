# IMG Academy → NFL: notes for Claude

A weekly, evidence-led web edition about NFL players who played football at IMG Academy. It is a public portfolio project by Bryce Murphy. Spec: `docs/superpowers/specs/2026-09-26-wednesday-edition-v1-design.md`. Owner routine: `docs/OPERATIONS.md`.

## Commands (Windows, Git Bash, from the repository root)

```bash
.venv/Scripts/python -m unittest discover -s tests -v
.venv/Scripts/python -m unittest discover -s tests -p "test_edition.py" -v
.venv/Scripts/python -m src.edition --season 2026 --week 3
.venv/Scripts/python -m src.editorial check --all
.venv/Scripts/python -m src.site build --out _site --check
.venv/Scripts/python scripts/preview_site.py
```

- **Refresh the test fixtures** (network): `.venv/Scripts/python scripts/make_fixtures.py`, then run the golden test with `UPDATE_GOLDEN=1` and review the diff.
- **Regenerate the share image** after editing `scripts/share_card.html`: `.venv/Scripts/python scripts/make_share_card.py` (headless Edge or Chrome; writes `static/share-card.png`).
- **Regenerate the dependency lock:** `uv pip compile requirements.in --universal --generate-hashes --python-version 3.12 --system-certs -o requirements.txt`
- **Local pip installs** on this machine need `PIP_CERT=/c/ProgramData/Norton/Antivirus/wscert.pem` (antivirus TLS interception).

## Map

- `evidence.py`: every rule about who played and why a player didn't; all pure functions.
- `edition.py`: builds `edition.json`.
- `editorial.py`: the headline file and its checks.
- `site.py` with `templates/` and `static/`: the renderer.
- `pipeline.py`: one scheduled attempt.
- `github.py`: API calls.
- `verify.py`: checks the live site.

## Claude API

- Headline drafting: `claude-opus-5-5`, effort `medium`, structured output, template fallback (`src/editorial.py`).

## Rules that must not bend

- Never claim injury, illness or benching from missing rows or zero statistics. Missing evidence is "Participation unverified".
- Match players by GSIS/PFR IDs only. Every registry entry needs an affiliation source.
- No Pro Football Reference scraping. No third-party images. No IMG Academy or NFL logos until permission is recorded in `docs/MEDIA_RIGHTS.md`.
- Add a regression test with every accuracy fix.
- Automation never rewrites a merged `editions/<id>/` directory.
- Pin every GitHub Action to a full SHA. Use only GitHub-owned actions. Never put `${{ }}` expressions inside `run:` scripts; pass values through `env:`.
- Public copy says "IMG Academy" in full, never "IMG" alone (brand guidelines' editorial rule).
- The author works at IMG Academy: never write "not affiliated". The label is "Not an official IMG Academy or NFL publication"; the site does not mention the author's job.
- Site colors come from the official IMG Academy palette in `static/styles.css`; team colors are only bars and borders. Football-diagram conventions are the exception (the first-down marker is yellow, `--first-down`).

## Git

- `main` requires a PR, passing `tests` and `analyze` checks, signed commits and linear history (squash merge only).
- Commits are signed with the SSH key held by the Windows ssh-agent. The author email is `36241992+bryce-murphy@users.noreply.github.com`.
- Never push to `main` and never disable protections. Merge only when the owner says so.
- If `git push` hangs on a credential prompt, push with `git -c credential.helper= -c "credential.helper=!gh auth git-credential" push`.
