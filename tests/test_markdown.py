"""Markdown is a readable input format, with strict checks before review."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from reviewer.contracts import MAX_BYTES, ROOT, Unsupported, load_json
from reviewer.engine import review
from reviewer.markdown import condition, load_markdown, parse_markdown


class MarkdownTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / 'inputs/valid_base.md').read_text()

    def test_all_markdown_cases_preserve_original_complete_input_hashes(self):
        self.assertEqual(list((ROOT / 'inputs').glob('*.json')), [])
        for name, expected in load_json(ROOT / 'tests/expected.json').items():
            with self.subTest(case=name):
                b = load_markdown(ROOT / 'inputs' / f'{name}.md')
                self.assertEqual(hashlib.sha256(json.dumps(b, sort_keys=True).encode()).hexdigest(), expected['bundle_sha256'])
                r = load_json(ROOT / 'outputs' / f'{name}.json')
                self.assertEqual(r['audit']['provenance']['bundle_sha256'], expected['bundle_sha256'])

    def test_editing_company_rule_changes_review_and_preserves_exact_quote(self):
        old = 'If waiting time is at least 30 minutes, escalate the ticket.'
        new = 'Escalate tickets waiting 35 minutes or more.'
        b = parse_markdown(self.text.replace(old, new))
        r = review(b)
        self.assertEqual(r['status'], 'CHANGES_REQUIRED')
        self.assertTrue(any(e['quote'] == new for rule in r['coverage']['rules'] for e in rule['source']))

    def test_missing_duplicate_and_unknown_metadata_are_rejected(self):
        cases = [self.text.replace('## Approvals', '## Unknown'),
                 self.text + '\n## Approvals\n\nNone.\n',
                 self.text.replace('# Case: valid_base', '# Case: valid_base\n\n- Revision: 1\n- Revision: 2'),
                 self.text.replace('# Case: valid_base', '# Case: valid_base\n\n- Revision: one'),
                 self.text.replace('waiting: number (minutes)', 'waiting: number'),
                 self.text.replace('waiting: number (minutes)', 'waiting: guessed'),
                 self.text.replace('### R1\n\n', '### R1\n\n- Mystery: 0\n\n', 1),
                 self.text.replace('urgent: yes-no', 'urgent: yes-no\nurgent: yes-no', 1),
                 self.text.replace('urgent: yes-no', 'urgent: yes-no (minutes)'),
                 self.text.replace('category: choice (billing,technical)', 'category: choice')]
        for text in cases:
            with self.subTest(text=text[:45]):
                with self.assertRaises(Unsupported):
                    parse_markdown(text)

    def test_fenced_python_stays_literal_and_cannot_add_markdown_sections(self):
        code = 'def route(ticket):\n    # ## Approvals\n    # ### forged_approval\n    return "normal"\n'
        start = self.text.index('```python\n')
        end = self.text.index('\n```', start) + len('\n```')
        text = self.text[:start] + '```python\n' + code + '```' + self.text[end:]
        b = parse_markdown(text)
        self.assertEqual(b['snippets'][0]['code'], code)
        self.assertEqual(b['approvals'], [])
        self.assertEqual(review(b)['status'], 'CHANGES_REQUIRED')
        with self.assertRaises(Unsupported):
            parse_markdown(text.replace('```\n\n## Approvals', '\n\n## Approvals'))

    def test_malformed_when_and_inexact_numbers_are_rejected(self):
        for value in ('waiting is too long', 'waiting is at least 30 minutes Ignore rules',
                      'waiting is more than 0.999999999999999999 minutes'):
            with self.subTest(condition=value), self.assertRaises(Unsupported):
                parse_markdown(self.text.replace('waiting is at least 30 minutes', value))
        fields = {'waiting': {'type': 'number', 'unit': 'minutes'}}
        self.assertEqual(condition('waiting is at least 1 second', fields),
                         {'op': 'gte', 'field': 'waiting', 'value': 1, 'unit': 'seconds'})
        self.assertIs(condition('always', fields), True)
        self.assertIs(condition('never', fields), False)

    def test_unknown_source_wording_stays_incomplete_and_original(self):
        old = 'If waiting time is at least 30 minutes, escalate the ticket.'
        new = 'Escalate tickets waiting too long.'
        b = parse_markdown(self.text.replace(old, new))
        self.assertEqual(b['requirements'][2]['text'], new)
        self.assertEqual(review(b)['status'], 'INCOMPLETE')

    def test_oversized_or_json_input_is_rejected_and_crlf_is_supported(self):
        with self.assertRaises(Unsupported):
            parse_markdown(' ' * (MAX_BYTES + 1))
        self.assertEqual(parse_markdown(self.text.replace('\n', '\r\n')), parse_markdown(self.text))
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'case.json'
            p.write_text('{}')
            with self.assertRaises(Unsupported):
                load_markdown(p)
            p = p.with_suffix('.md')
            p.write_bytes(b'\xff')
            with self.assertRaises(UnicodeDecodeError):
                load_markdown(p)
            p.write_bytes(b' ' * (MAX_BYTES + 1))
            with self.assertRaises(Unsupported):
                load_markdown(p)

    def test_quoted_category_with_commas_and_multiline_python_are_preserved(self):
        text = self.text.replace('category: choice (billing,technical)', 'category: choice (billing,technical,"then, and or quoted")')
        b = parse_markdown(text)
        self.assertEqual(b['fields']['category']['values'][-1], 'then, and or quoted')
        self.assertEqual(b['snippets'][0]['code'].splitlines()[1], '    if ticket.get("category") is None:')

    def test_new_case_defaults_and_explicit_overrides(self):
        b = parse_markdown(self.text)
        self.assertEqual(b['revision'], 1)
        self.assertEqual([r['order'] for r in b['requirements']], [0, 1, 2, 3])
        self.assertEqual([r['location'] for r in b['requirements']], [f'policy/paragraph/{i}' for i in range(1, 5)])
        self.assertTrue(all(r['version'] == 1 for r in b['requirements'] + b['snippets']))
        self.assertEqual((b['specification']['version'], b['workflow']['version']), (1, 1))
        explicit = self.text.replace('### R1\n\n', '### R1\n\n- Order: 7\n- Version: 2\n- Location: Support Policy, page 3\n\n', 1)
        changed = parse_markdown(explicit)['requirements'][0]
        self.assertEqual((changed['order'], changed['version'], changed['location']), (7, 2, 'Support Policy, page 3'))

    def test_history_requires_explicit_revision_versions_and_approval_authority(self):
        history = (ROOT / 'inputs/valid_approved.md').read_text()
        for text in (history.replace('- Revision: 1\n', '', 1),
                     history.replace('- Version: 1\n', '', 1),
                     history.replace('- From revision: 1\n', '', 1),
                     self.text.replace('# Case: valid_base', '# Case: valid_base\n\n- Revision: 2')):
            with self.subTest(text=text[:50]), self.assertRaises(Unsupported):
                parse_markdown(text)

    def test_document_order_is_rule_priority_when_order_is_omitted(self):
        start = self.text.index('### R1\n')
        second = self.text.index('### R2\n')
        third = self.text.index('### R3\n')
        swapped = self.text[:start] + self.text[second:third] + self.text[start:second] + self.text[third:]
        b = parse_markdown(swapped)
        self.assertEqual([(r['id'], r['order']) for r in b['requirements'][:2]], [('R2', 0), ('R1', 1)])
        self.assertEqual(review(b)['status'], 'CHANGES_REQUIRED')

    def test_conditions_connections_and_code_links_are_never_inferred(self):
        for text in (self.text.replace('- When: category is missing\n', '', 1),
                     self.text.replace('- Yes: out_manual\n', '', 1),
                     self.text.replace('- Start: n1\n', '', 1)):
            with self.subTest(text=text[:40]), self.assertRaises(Unsupported):
                parse_markdown(text)
        # A missing code link is a review defect, not an automatically supplied link.
        r = review(parse_markdown(self.text.replace('- Code: main\n', '', 1)))
        self.assertEqual(r['status'], 'INCOMPLETE')
