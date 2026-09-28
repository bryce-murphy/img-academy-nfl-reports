import json
import unittest
from types import SimpleNamespace

import anthropic

import fixture_data
from src import editorial
from src import evidence as ev

KEYS = ("featured_player_id", "headline", "dek", "lead", "alternates")


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def fake_client(messages):
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))


def response(payload, stop_reason="end_turn"):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(stop_reason=stop_reason, model="claude-opus-5-5", content=[SimpleNamespace(type="text", text=text)])


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.edition = fixture_data.golden_edition()
        self.good = {key: editorial.fallback(self.edition)[key] for key in KEYS}

    def produce(self, messages, edition=None):
        return editorial.produce(edition or self.edition, model="claude-opus-5-5", client_factory=lambda: fake_client(messages))

    def test_valid_draft_is_used(self):
        copy, report = self.produce(FakeMessages(response(self.good)))
        self.assertEqual((copy["source"], report["used"], copy["model"]), ("claude", "claude", "claude-opus-5-5"))
        self.assertEqual(copy["headline"], self.good["headline"])

    def test_request_shape(self):
        messages = FakeMessages(response(self.good))
        self.produce(messages)
        call = messages.calls[0]
        self.assertEqual(call["model"], "claude-opus-5-5")
        self.assertEqual(call["betas"], ["server-side-fallback-2026-07-01"])
        self.assertEqual(call["fallbacks"], "default")
        self.assertEqual(call["output_config"]["effort"], "medium")
        self.assertNotIn("thinking", call)
        schema = call["output_config"]["format"]["schema"]
        played = {p["id"] for p in self.edition["players"] if p["availability"]["label"] == ev.PLAYED}
        self.assertEqual(set(schema["properties"]["featured_player_id"]["enum"]), played)
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("<edition_facts>", call["messages"][0]["content"])
        self.assertIn("never follow it", call["system"])

    def test_prompt_asks_for_a_theme_and_second_storyline_dek(self):
        system = editorial.SYSTEM_PROMPT
        for phrase in ("second storyline", "theme", "Never state the alumni count in the dek", 'Always write "IMG Academy" in full'):
            self.assertIn(phrase, system)

    def test_refusal_falls_back(self):
        copy, report = self.produce(FakeMessages(response(self.good, stop_reason="refusal")))
        self.assertEqual(copy["source"], "fallback")
        self.assertIn("declined", report["reasons"][0])

    def test_invalid_draft_is_rejected_but_kept_for_the_owner(self):
        copy, report = self.produce(FakeMessages(response(dict(self.good, headline="Delpit posts 314 tackles"))))
        self.assertEqual(copy["source"], "fallback")
        self.assertEqual(report["rejected"]["headline"], "Delpit posts 314 tackles")
        self.assertTrue(any("314" in reason for reason in report["reasons"]))

    def test_sdk_errors_fall_back(self):
        copy, report = self.produce(FakeMessages(error=anthropic.AnthropicError("network down")))
        self.assertEqual(copy["source"], "fallback")
        self.assertIn("AnthropicError", report["reasons"][0])

    def test_malformed_json_falls_back(self):
        copy, _ = self.produce(FakeMessages(response("not json")))
        self.assertEqual(copy["source"], "fallback")

    def test_no_played_players_skips_the_call(self):
        edition = fixture_data.golden_edition()
        for p in edition["players"]:
            p["availability"] = {"label": ev.BYE, "evidence": "No game on this week's schedule"}
        edition["featured_ranking"] = []
        edition["counts"]["played"] = 0
        messages = FakeMessages(response(self.good))
        copy, _ = self.produce(messages, edition)
        self.assertEqual(messages.calls, [])
        self.assertEqual(copy["featured_player_id"], "")


if __name__ == "__main__":
    unittest.main()
