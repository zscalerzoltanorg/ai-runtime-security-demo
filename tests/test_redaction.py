"""Tests for AI Guard entity redaction (API/DAS mode).

Offsets in these fixtures mirror a real AI Guard response: the PERSON span for
"James\tSmith" in "sort this by name\n\n..." starts at 19 and ends at 30.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import guardrails as ai_guard


def entity(content, sub, typ, repl):
    start = content.index(sub)
    return {
        "type": typ,
        "start": start,
        "end": start + len(sub),
        "subcategory": None,
        "anonymizedEntityText": repl,
    }


def guard_body(content, items, *, masked=None):
    ents = [entity(content, sub, typ, repl) for sub, typ, repl in items]
    body = {
        "action": "ALLOW",
        "severity": "LOW",
        "detectorResponses": {
            "pii": {
                "statusCode": 200,
                "triggered": bool(ents),
                "action": "ALLOW",
                "details": {"detectedEntities": ents},
            }
        },
    }
    if masked is not None:
        body["maskedContent"] = masked
    return body


PROMPT = "sort this by name\n\nJames\tSmith\t1/2/1981\tJamesSmith@gmail.com"
ITEMS = [
    ("James\tSmith", "PERSON", "PERSON-1"),
    ("1/2/1981", "DATETIME", "DATETIME-1"),
    ("JamesSmith@gmail.com", "EMAIL", "EMAIL-1"),
]


class EntityOffsetTests(unittest.TestCase):
    def test_offsets_match_real_api_response(self):
        body = guard_body(PROMPT, ITEMS)
        spans = ai_guard._detected_entity_spans(body)  # noqa: SLF001
        person = [s for s in spans if s["type"] == "PERSON"][0]
        self.assertEqual((person["start"], person["end"]), (19, 30))

    def test_only_detected_entities_are_replaced(self):
        text, info = ai_guard.redact_content(PROMPT, guard_body(PROMPT, ITEMS))
        self.assertEqual(
            text, "sort this by name\n\nPERSON-1\tDATETIME-1\tEMAIL-1"
        )
        self.assertEqual(info["method"], "entity_offsets")
        self.assertEqual(info["entity_count"], 3)
        # Surrounding instruction text is preserved verbatim.
        self.assertTrue(text.startswith("sort this by name\n\n"))

    def test_clean_prompt_is_untouched(self):
        text, info = ai_guard.redact_content("what is 2+2", guard_body("what is 2+2", []))
        self.assertEqual(text, "what is 2+2")
        self.assertEqual(info["method"], "none")

    def test_widest_span_wins_so_no_fragment_survives(self):
        content = "James Smith is here"
        body = {
            "detectorResponses": {
                "pii": {
                    "details": {
                        "detectedEntities": [
                            {"type": "NAME", "start": 0, "end": 5, "anonymizedEntityText": "NAME-1"},
                            {"type": "PERSON", "start": 0, "end": 11, "anonymizedEntityText": "PERSON-1"},
                        ]
                    }
                }
            }
        }
        text, info = ai_guard.redact_content(content, body)
        self.assertEqual(text, "PERSON-1 is here")
        self.assertNotIn("Smith", text)
        self.assertEqual(info["entity_count"], 1)

    def test_malformed_offsets_do_not_crash_or_corrupt(self):
        body = {
            "detectorResponses": {
                "pii": {
                    "details": {
                        "detectedEntities": [
                            {"type": "X", "start": -5, "end": 3, "anonymizedEntityText": "A"},
                            {"type": "X", "start": 5, "end": 5, "anonymizedEntityText": "B"},
                            {"type": "X", "start": "abc", "end": None, "anonymizedEntityText": "D"},
                            {"type": "X", "start": 2, "end": 99999, "anonymizedEntityText": "C"},
                        ]
                    }
                }
            }
        }
        text, _info = ai_guard.redact_content("abcdefgh", body)
        self.assertEqual(text, "abcdefgh")

    def test_missing_anonymized_text_falls_back_to_type_label(self):
        body = {
            "detectorResponses": {
                "pii": {"details": {"detectedEntities": [{"type": "SSN", "start": 0, "end": 4}]}}
            }
        }
        text, _info = ai_guard.redact_content("abcd efgh", body)
        self.assertEqual(text, "[SSN] efgh")

    def test_none_body_is_safe(self):
        text, info = ai_guard.redact_content("hello", None)
        self.assertEqual(text, "hello")
        self.assertEqual(info["method"], "none")


class MaskedContentFallbackTests(unittest.TestCase):
    def test_masked_content_used_when_no_offsets(self):
        body = {"detectorResponses": {"pii": {"details": {}}}, "maskedContent": "hello PERSON-1"}
        text, info = ai_guard.redact_content("hello Bob", body, submitted_length=len("hello Bob"))
        self.assertEqual(text, "hello PERSON-1")
        self.assertEqual(info["method"], "masked_content")

    def test_masked_content_refused_when_submission_included_attachments(self):
        """maskedContent covers prompt+attachment text, so it must not be spliced
        into a prompt that was only part of the inspected string."""
        prompt = "hello Bob"
        submitted = prompt + "\n\n[Text attachment: x.txt]\nsecret"
        body = {
            "detectorResponses": {"pii": {"details": {}}},
            "maskedContent": "MASKED BLOB OF PROMPT AND ATTACHMENT",
        }
        text, info = ai_guard.redact_content(
            prompt, body, max_offset=len(prompt), submitted_length=len(submitted)
        )
        self.assertEqual(text, prompt)
        self.assertEqual(info["method"], "none")
        self.assertNotIn("MASKED BLOB", text)


class BoundedApplicationTests(unittest.TestCase):
    def test_spans_past_the_prompt_are_deferred_not_misapplied(self):
        prompt = "summarize James Smith's record"
        submitted = prompt + "\n\n[Text attachment: r.txt]\nMary Wright mary@x.com"
        items = [
            ("James Smith", "PERSON", "PERSON-1"),
            ("Mary Wright", "PERSON", "PERSON-2"),
            ("mary@x.com", "EMAIL", "EMAIL-1"),
        ]
        body = guard_body(submitted, items)
        text, info = ai_guard.redact_content(
            prompt, body, max_offset=len(prompt), submitted_length=len(submitted)
        )
        self.assertEqual(text, "summarize PERSON-1's record")
        self.assertEqual(info["entity_count"], 1)
        self.assertEqual(len(info["deferred"]), 2)


class TraceStepTests(unittest.TestCase):
    def test_trace_step_never_contains_the_matched_text(self):
        import json

        body = guard_body(PROMPT, ITEMS)
        text, info = ai_guard.redact_content(PROMPT, body)
        step = ai_guard.redaction_trace_step(
            "IN", info, before_length=len(PROMPT), after_length=len(text)
        )
        blob = json.dumps(step)
        for secret in ("James", "Smith", "JamesSmith@gmail.com", "1/2/1981"):
            self.assertNotIn(secret, blob)

    def test_step_name_classifies_correctly_in_the_ui(self):
        step = ai_guard.redaction_trace_step(
            "IN", {"method": "none", "applied": [], "deferred": []},
            before_length=1, after_length=1,
        )
        name = step["name"]
        # Must not be mistaken for the provider step...
        self.assertTrue(name.startswith("Zscaler"))
        # ...nor counted as an AI Guard policy check.
        self.assertFalse(name.startswith("Zscaler AI Guard"))


class ToggleTests(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("ZS_GUARDRAILS_APPLY_MASKED_CONTENT")
        os.environ.pop("ZS_GUARDRAILS_APPLY_MASKED_CONTENT", None)

    def tearDown(self):
        os.environ.pop("ZS_GUARDRAILS_APPLY_MASKED_CONTENT", None)
        if self._saved is not None:
            os.environ["ZS_GUARDRAILS_APPLY_MASKED_CONTENT"] = self._saved

    def test_defaults_on(self):
        self.assertTrue(ai_guard.redaction_enabled(None))

    def test_request_override_wins_over_env(self):
        os.environ["ZS_GUARDRAILS_APPLY_MASKED_CONTENT"] = "true"
        self.assertFalse(ai_guard.redaction_enabled(False))
        os.environ["ZS_GUARDRAILS_APPLY_MASKED_CONTENT"] = "false"
        self.assertTrue(ai_guard.redaction_enabled(True))

    def test_env_disables_by_default(self):
        os.environ["ZS_GUARDRAILS_APPLY_MASKED_CONTENT"] = "false"
        self.assertFalse(ai_guard.redaction_enabled(None))


class GuardedChatTests(unittest.TestCase):
    """The provider must receive the redacted prompt, not the original."""

    def setUp(self):
        os.environ["ZS_GUARDRAILS_API_KEY"] = "test-key"
        self._orig_post = ai_guard._post_json  # noqa: SLF001

        def fake_post(url, payload, headers, timeout):
            content = payload["content"]
            if payload["direction"] == "IN":
                return 200, guard_body(content, ITEMS, masked="BLOB")
            return 200, guard_body(content, [])

        ai_guard._post_json = fake_post  # noqa: SLF001

    def tearDown(self):
        ai_guard._post_json = self._orig_post  # noqa: SLF001
        os.environ.pop("ZS_GUARDRAILS_API_KEY", None)

    def _run(self, apply_redaction):
        seen = {}

        def llm(p):
            seen["prompt"] = p
            return "ok", {"trace_step": {"name": "Ollama (Local)", "response": {"status": 200}}}

        payload, status = ai_guard.guarded_chat(
            prompt=PROMPT,
            llm_call=llm,
            redact_target=PROMPT,
            apply_redaction=apply_redaction,
        )
        return seen["prompt"], payload, status

    def test_provider_receives_redacted_prompt(self):
        sent, payload, status = self._run(True)
        self.assertEqual(status, 200)
        self.assertNotIn("James", sent)
        self.assertNotIn("JamesSmith@gmail.com", sent)
        self.assertEqual(sent, "sort this by name\n\nPERSON-1\tDATETIME-1\tEMAIL-1")
        self.assertEqual(payload["guardrails"]["redaction"]["enabled"], True)
        self.assertIn("IN", payload["guardrails"]["redaction"]["applied"])

    def test_redaction_step_appears_in_trace(self):
        _sent, payload, _status = self._run(True)
        names = [s.get("name") for s in payload["trace"]["steps"]]
        self.assertIn("Zscaler Redaction (IN)", names)
        self.assertLess(
            names.index("Zscaler AI Guard (IN)"), names.index("Zscaler Redaction (IN)")
        )
        self.assertLess(
            names.index("Zscaler Redaction (IN)"), names.index("Ollama (Local)")
        )

    def test_toggle_off_preserves_previous_behaviour(self):
        sent, payload, _status = self._run(False)
        self.assertEqual(sent, PROMPT)
        names = [s.get("name") for s in payload["trace"]["steps"]]
        self.assertNotIn("Zscaler Redaction (IN)", names)
        self.assertEqual(payload["guardrails"]["redaction"]["enabled"], False)

    def test_blocked_prompt_never_reaches_the_provider(self):
        def blocking_post(url, payload, headers, timeout):
            return 200, {"action": "BLOCK", "policyName": "p", "detectorResponses": {}}

        ai_guard._post_json = blocking_post  # noqa: SLF001
        called = []

        def llm(p):
            called.append(p)
            return "ok", {"trace_step": {"name": "Ollama (Local)"}}

        payload, status = ai_guard.guarded_chat(
            prompt=PROMPT, llm_call=llm, redact_target=PROMPT, apply_redaction=True
        )
        self.assertEqual(status, 200)
        self.assertEqual(called, [])
        self.assertTrue(payload["guardrails"]["blocked"])


if __name__ == "__main__":
    unittest.main()
