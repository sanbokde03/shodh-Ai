"""Real failures stay failures; explicit grammar and ticket data are validated."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from reviewer.contracts import ROOT, Unsupported
from reviewer.engine import review
from reviewer.markdown import load_markdown, parse_markdown
from reviewer.model import FakeClient


class UsabilityFixTests(unittest.TestCase):
    def test_contradictory_ambiguity_is_retried_with_feedback(self):
        class CorrectingClient(FakeClient):
            def complete(self, request, config):
                if self.calls:
                    self.feedback = request.get('validation_feedback')
                return super().complete(request, config)
        client = CorrectingClient('ambiguous,ok')
        r = review(load_markdown(ROOT / 'inputs/valid_unusual_units.md'), client)
        self.assertEqual(r['status'], 'PASS')
        self.assertIn('complete declared-language interpretation', client.feedback)
        self.assertEqual(r['resources']['model_retries'], 1)
        attempts = r['model']['attempts']
        self.assertEqual([a['result'] for a in attempts], ['rejected', 'validated'])
        self.assertNotEqual(attempts[0]['request_sha256'], attempts[1]['request_sha256'])
        self.assertEqual(attempts[1]['validation_feedback'], client.feedback)

    def test_repeated_contradictions_and_real_ambiguity_never_become_pass(self):
        b = load_markdown(ROOT / 'inputs/valid_unusual_units.md')
        r = review(b, FakeClient('ambiguous'))
        self.assertEqual(r['status'], 'INCOMPLETE')
        self.assertEqual(r['resources']['model_calls'], 2)
        r = review(load_markdown(ROOT / 'inputs/incomplete_ambiguous.md'), FakeClient('ambiguous'))
        self.assertEqual(r['status'], 'INCOMPLETE')
        self.assertEqual(r['resources']['model_calls'], 1)
        self.assertTrue(any(u['scope'] == 'model_ambiguity' for u in r['coverage']['unreviewed']))

    def test_markdown_tickets_reach_company_spec_workflow_and_code(self):
        b = load_markdown(ROOT / 'examples/ticket_demo.md')
        self.assertEqual(b['example_tickets'], [{'category':'billing','urgent':False,'waiting':30}, {'urgent':True,'waiting':5}])
        r = review(b)
        self.assertEqual(r['status'], 'PASS')
        self.assertEqual([row['expected_route'] for row in r['ticket_results']], ['escalation','manual'])
        for row in r['ticket_results']:
            self.assertEqual(set(row['artifacts']), {'specification','workflow','code'})
            self.assertTrue(all(route == row['expected_route'] for route in row['artifacts'].values()))

    def test_one_ticket_and_units_and_missing_are_preserved(self):
        text = (ROOT / 'inputs/valid_base.md').read_text()
        b = parse_markdown(text + '\n## Example tickets\n\ncategory: null\nurgent: no\nwaiting: 1800 seconds\n')
        self.assertEqual(b['example_tickets'], [{'category':None,'urgent':False,'waiting':30}])
        self.assertEqual(review(b)['ticket_results'][0]['expected_route'], 'manual')
        b = parse_markdown(text + '\n## Example tickets\n\ncategory:\nwaiting: missing\n')
        self.assertEqual(b['example_tickets'], [{}])

    def test_invalid_ticket_values_do_not_get_ignored(self):
        text = (ROOT / 'inputs/valid_base.md').read_text() + '\n## Example tickets\n\n'
        for ticket in ('urgent: perhaps', 'unknown: yes', 'waiting: 0.5 minutes', 'waiting: 30 seconds',
                       'waiting: 30 days', 'category: unlisted', 'urgent: missing\nurgent: no', ''):
            with self.subTest(ticket=ticket), self.assertRaises(Unsupported):
                parse_markdown(text + ticket)
        with self.assertRaises(Unsupported):
            parse_markdown(text + '\n'.join(f'### ticket_{i}\nwaiting: {i}\n' for i in range(129)))

    def test_cli_writes_ticket_results_in_json(self):
        with tempfile.TemporaryDirectory() as directory:
            p = subprocess.run([sys.executable,'-m','reviewer','examples/ticket_demo.md','--offline','--output-dir',directory],
                               capture_output=True,text=True,cwd=ROOT,timeout=15)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(p.stdout, '')
            r = json.loads((Path(directory)/'ticket_demo.json').read_text())
            self.assertEqual(len(r['ticket_results']), 2)
            self.assertEqual(r['ticket_results'][0]['artifacts']['workflow'], 'escalation')
