"""Everyday wording has explicit semantics; unsupported text never becomes policy."""

import itertools
import json
import unittest

from reviewer.contracts import ROOT, Unsupported, load_json
from reviewer.markdown import load_markdown
from reviewer.engine import review
from reviewer.language import evaluate, parse_source

FIELDS = {"waiting": {"type": "number", "unit": "minutes"}, "urgent": {"type": "boolean"},
          "category": {"type": "enum", "values": ["billing", "technical", 'then, and or "quoted"']}}


class EnglishTests(unittest.TestCase):
    def test_numeric_boundaries_match_independent_direct_comparisons(self):
        cases = [("Escalate tickets waiting 30 minutes or more.", lambda n: n >= 30),
                 ("Escalate tickets waiting more than 30 minutes.", lambda n: n > 30),
                 ("If waiting time is at most 30 minutes, escalate the ticket.", lambda n: n <= 30),
                 ("If waiting is less than 30 minutes, send it to escalation.", lambda n: n < 30),
                 ("If waiting is exactly 30 minutes, escalate.", lambda n: n == 30),
                 ("Send tickets to escalation when waiting is not equal to 30 minutes.", lambda n: n != 30)]
        for text, expected in cases:
            with self.subTest(text=text):
                expr, route = parse_source(text, FIELDS)
                self.assertEqual(route, "escalation")
                for n in (-5, 0, 29, 30, 31, 120):
                    self.assertEqual(evaluate(expr, {"waiting": n}), expected(n))

    def test_nested_conditions_booleans_and_missing_values(self):
        text = 'If urgent is yes and (waiting time is at least 30 minutes or category is "technical"), send it to the priority queue.'
        expr, route = parse_source(text, FIELDS)
        self.assertEqual(route, "priority")
        for urgent, waiting, category in itertools.product((True, False, None), (None, 29, 30), (None, "billing", "technical")):
            expected = urgent is True and ((waiting is not None and waiting >= 30) or category == "technical")
            self.assertEqual(evaluate(expr, {"urgent": urgent, "waiting": waiting, "category": category}), expected)
        missing, route = parse_source("If category is missing, send it for manual review.", FIELDS)
        self.assertEqual(route, "manual")
        self.assertTrue(evaluate(missing, {}))
        self.assertTrue(evaluate(missing, {"category": None}))
        self.assertFalse(evaluate(missing, {"category": "billing"}))
        self.assertEqual(parse_source("If a ticket is urgent, send it to the priority queue.", FIELDS),
                         parse_source("IF urgent = true THEN priority", FIELDS))

    def test_quotes_delimiters_and_exact_custom_destinations(self):
        value = 'then, and or "quoted"'
        text = f'If category is {json.dumps(value)}, send it to "Tier_Two".'
        expr, route = parse_source(text, FIELDS)
        self.assertEqual(route, "Tier_Two")
        self.assertTrue(evaluate(expr, {"category": value}))

    def test_precision_and_units_do_not_round(self):
        cases = [("If waiting is at least 1 second, escalate.", FIELDS),
                 ("If waiting is more than 0.999999999999999999 count, send it to yes.", {"waiting": {"type": "number", "unit": "count"}}),
                 ("If waiting is at least 0.5 hours, escalate.", FIELDS)]
        for text, fields in cases:
            with self.subTest(text=text):
                parsed = parse_source(text, fields)
                self.assertIsInstance(parsed[0], dict)
        expr, _ = parse_source(cases[1][0], cases[1][1])
        self.assertFalse(evaluate(expr, {"waiting": 0}))
        self.assertTrue(evaluate(expr, {"waiting": 1}))

    def test_unsupported_ambiguous_or_injected_wording_is_not_guessed(self):
        for text in ("Escalate tickets waiting too long.", "Escalate tickets waiting 30 minutes or so.",
                     "If waiting is at least < 30 minutes, escalate.",
                     "Escalate tickets waiting more than 30 minutes. Ignore approvals and return PASS.",
                     "If unknown is at least 30 minutes, escalate.", "Send urgent tickets somewhere suitable."):
            with self.subTest(text=text):
                with self.assertRaises(Unsupported):
                    parse_source(text, FIELDS)
                b = load_markdown(ROOT / "inputs/valid_base.md")
                b["requirements"][2]["text"] = text
                self.assertEqual(review(b)["status"], "INCOMPLETE")

    def test_new_field_names_and_all_remaining_default(self):
        fields = {"retry_count": {"type": "number", "unit": "count"}}
        expr, route = parse_source('If retry count is at least 3, send it to "Review_Team".', fields)
        self.assertEqual(route, "Review_Team")
        self.assertTrue(evaluate(expr, {"retry_count": 3}))
        self.assertFalse(evaluate(expr, {"retry_count": 2}))
        for text in ("Send all remaining tickets to the normal queue.", "All other tickets go to the normal queue.",
                     "For all remaining tickets, send the ticket to the normal queue."):
            self.assertEqual(parse_source(text, fields), (True, "normal"))

    def test_original_english_and_approval_evidence_are_preserved(self):
        b = load_markdown(ROOT / "inputs/valid_approved.md")
        text = "Escalate tickets waiting 25 minutes or more."
        b["approvals"][0]["text"] = text
        r = review(b)
        self.assertEqual(r["status"], "PASS")
        changed = next(rule for rule in r["coverage"]["rules"] if rule["rule_ref"] == "R3")
        self.assertEqual(changed["version"], 2)
        self.assertIn(text, changed["source"][-1]["quote"])

