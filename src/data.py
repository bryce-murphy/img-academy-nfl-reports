"""Read public nflverse releases with an auditable source manifest. No scraped PFR pages."""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .errors import DataError, NotReady  # noqa: F401  (re-exported)

RELEASES = "https://api.github.com/repos/nflverse/nflverse-data/releases/tags/"
DOWNLOADS = "https://github.com/nflverse/nflverse-data/releases/download/"
HOSTS = {"api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
MAX_BYTES = 180_000_000
DOWNLOAD_ATTEMPTS = 3
RETRY_SECONDS = 20


def pause(seconds):
    time.sleep(seconds)


def utcnow():
    return datetime.now(timezone.utc)


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def get_bytes(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS:
        raise DataError("Source URL is outside the approved nflverse download hosts")
    request = Request(url, headers={"User-Agent": "img-academy-nfl-reports/0.1"})
    with urlopen(request, timeout=90) as response:
        if urlparse(response.url).hostname not in HOSTS:
            raise DataError("Unexpected download destination")
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise DataError("Source exceeds the download size limit")
    return payload


def specifications(season):
    return {
        "schedule": ("schedules", "games.csv", {"game_id", "season", "game_type", "gameday", "home_score", "away_score"}),
        "rosters": ("weekly_rosters", f"roster_weekly_{season}.csv", {"gsis_id", "team", "week", "status"}),
        "current_rosters": ("rosters", f"roster_{season}.csv", {"gsis_id", "team", "status"}),
        "players": ("players", "players.csv", {"gsis_id", "display_name", "pfr_id"}),
        "stats": ("stats_player", f"stats_player_week_{season}.csv", {"player_id", "week", "season", "game_id", "team"}),
        "pbp": ("pbp", f"play_by_play_{season}.csv.gz", {"game_id", "play_id", "week", "desc", "epa", "wpa"}),
        "snaps": ("snap_counts", f"snap_counts_{season}.csv", {"game_id", "pfr_player_id", "offense_snaps", "defense_snaps", "st_snaps"}),
        "injuries": ("injuries", f"injuries_{season}.csv", {"gsis_id", "week", "report_status", "report_primary_injury"}),
        "teams": ("teams", "teams_colors_logos.csv", {"team_abbr", "team_name", "team_logo_espn"}),
        "ngs_passing": ("nextgen_stats", "ngs_passing.csv.gz", {"season", "week", "player_gsis_id", "team_abbr"}),
        "ngs_receiving": ("nextgen_stats", "ngs_receiving.csv.gz", {"season", "week", "player_gsis_id", "team_abbr"}),
        "ngs_rushing": ("nextgen_stats", "ngs_rushing.csv.gz", {"season", "week", "player_gsis_id", "team_abbr"}),
    }


def parse_csv(payload, filename, required, keep=None):
    if filename.endswith(".gz"):
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
            payload = stream.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise DataError("Expanded source exceeds size limit")
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    if not required.issubset(set(reader.fieldnames or [])):
        raise DataError(f"Required columns changed in {filename}")
    rows, seen = [], 0
    for row in reader:
        seen += 1
        if keep is None or keep(row):
            rows.append(row)
    if not seen:
        raise DataError(f"Empty source: {filename}")
    return rows


def week_filter(week):
    wanted = str(week)
    return lambda row: row.get("week") == wanted


def fetch_verified(name, tag, filename, historical, max_age_hours):
    # nflverse replaces assets in place, so the listed digest can briefly lead the
    # download. Re-read both after a pause; never accept bytes that don't match.
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        release = json.loads(get_bytes(RELEASES + tag))
        assets = [a for a in release["assets"] if a["name"] == filename]
        if len(assets) != 1:
            raise DataError(f"Expected one asset named {filename}")
        asset = assets[0]
        fetched = utcnow()
        updated = stamp(asset["updated_at"])
        if updated > fetched:
            raise DataError(f"Source timestamp is in the future: {name}")
        if not historical and name not in {"players", "teams"}:
            if (fetched - updated).total_seconds() > max_age_hours * 3600:
                raise DataError(f"Stale source: {name}")
        url = DOWNLOADS + tag + "/" + filename
        payload = get_bytes(url)
        digest = hashlib.sha256(payload).hexdigest()
        if not asset.get("digest", "").startswith("sha256:") or asset["digest"] == "sha256:" + digest:
            return asset, fetched, url, payload, digest
        if attempt < DOWNLOAD_ATTEMPTS:
            pause(RETRY_SECONDS)
    raise DataError(f"Upstream checksum mismatch: {name}")


def load_sources(season, cache, max_age_hours=48, historical=False, only=None, week=None):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    datasets, manifest, warnings = {}, {}, []
    optional = {"snaps", "injuries", "ngs_passing", "ngs_receiving", "ngs_rushing"}
    for name, (tag, filename, required) in specifications(season).items():
        if only is not None and name not in only:
            continue
        try:
            asset, fetched, url, payload, digest = fetch_verified(name, tag, filename, historical, max_age_hours)
            keep = week_filter(week) if week is not None and name == "pbp" else None
            datasets[name] = parse_csv(payload, filename, required, keep)
            (cache / filename).write_bytes(payload)
            manifest[name] = {"url": url, "updated_at": asset["updated_at"], "fetched_at": fetched.isoformat(), "sha256": digest, "rows": len(datasets[name])}
        except Exception as exc:
            if name not in optional:
                raise DataError(f"Cannot verify {name}: {exc}") from exc
            datasets[name] = []
            warnings.append(f"{name} unavailable; related claims withheld ({type(exc).__name__})")
    (cache / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return datasets, manifest, warnings
