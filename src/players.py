"""Player pages: addresses, game logs and season lines. Pure functions over loaded editions."""
from __future__ import annotations

import re
import unicodedata

SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def slugify(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.replace(".", "").lower()).strip("-")


def assign_slugs(registry):
    """Copies of registry entries with `slug` set; a repeated slug gets the last four digits of the GSIS id."""
    taken, out = set(), []
    for alum in registry:
        slug = alum.get("slug") or slugify(alum["name"])
        if slug in taken:
            slug = f"{slug}-{alum['gsis_id'][-4:]}"
        taken.add(slug)
        out.append(dict(alum, slug=slug))
    return out
