import json
import tempfile
import unittest
from pathlib import Path

from src import players
from src.edition import load_registry
from src.errors import DataError


class SlugTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(players.slugify("Grant Delpit"), "grant-delpit")
        self.assertEqual(players.slugify("J.J. McCarthy"), "jj-mccarthy")
        self.assertEqual(players.slugify("DJ Turner II"), "dj-turner-ii")
        self.assertEqual(players.slugify("Hjalte Frøholdt"), "hjalte-frholdt")

    def test_assign_slugs_resolves_collisions_with_the_gsis_suffix(self):
        registry = [{"name": "Chris Smith", "gsis_id": "00-0031111"}, {"name": "Chris Smith", "gsis_id": "00-0042222"}]
        self.assertEqual([a["slug"] for a in players.assign_slugs(registry)], ["chris-smith", "chris-smith-2222"])

    def test_existing_slugs_are_kept(self):
        registry = [{"name": "Grant Delpit", "gsis_id": "00-0036282", "slug": "grant-delpit"}]
        self.assertEqual(players.assign_slugs(registry)[0]["slug"], "grant-delpit")

    def test_registry_requires_valid_unique_slugs(self):
        good = {"name": "A B", "gsis_id": "00-0000001", "slug": "a-b", "source_url": "https://x"}
        for bad in ({**good, "slug": ""}, {**good, "slug": "A B"}):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "alumni.json"
                path.write_text(json.dumps([bad]), encoding="utf-8")
                with self.assertRaises(DataError):
                    load_registry(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "alumni.json"
            path.write_text(json.dumps([good, {**good, "gsis_id": "00-0000002"}]), encoding="utf-8")
            with self.assertRaises(DataError):
                load_registry(path)

    def test_the_real_registries_have_slugs(self):
        for path in (Path("data/alumni.json"), Path("tests/fixtures/week02/alumni.json")):
            registry = load_registry(path)
            self.assertTrue(all(a["slug"] == players.slugify(a["name"]) or a["slug"].startswith(players.slugify(a["name"]) + "-") for a in registry))
