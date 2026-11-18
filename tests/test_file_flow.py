"""Scenario files are reviewed without menus, labels or stored predictions."""

import contextlib
import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reviewer.__main__ import main, save_report, simplify_report
from reviewer.contracts import ROOT, load_json, validate
from reviewer.markdown import load_markdown
from reviewer.engine import review
from reviewer.model import FakeClient


class FileFlowTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'reviewer', *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True, timeout=15)

    def test_simple_findings_keep_evidence_locations_and_counterexamples(self):
        bundle = load_markdown(ROOT / 'inputs/defect_boundary.md')
        full = review(bundle)
        before = copy.deepcopy(full)
        simple = simplify_report(full, 'offline')
        validate(simple, load_json(ROOT / 'schemas/report.schema.json'))
        self.assertEqual(full, before)
        self.assertEqual(simple['status'], full['status'])
        self.assertNotIn('model', simple)
        self.assertNotIn('provenance', simple)
        self.assertEqual(simple['audit']['model'], full['model'])
        self.assertEqual(simple['audit']['provenance'], full['provenance'])
        self.assertEqual(simple['resources'], full['resources'])
        for item, original in zip(simple['findings'], full['findings']):
            self.assertEqual(item['location'], original['location_description'])
            self.assertEqual(item['reference'], original['location'])
            self.assertEqual(item['counterexample'], original['counterexample'])
            self.assertEqual(item['correction'], original['correction'])
            self.assertTrue(item['evidence'])
            self.assertTrue(all(e in original['evidence'] for e in item['evidence']))
            self.assertTrue(any(e['artifact'] == 'source' for e in item['evidence']))
        self.assertLess(len(json.dumps(simple)), len(json.dumps(full)))
        self.assertTrue(all('This ticket should go to escalation' in f['problem'] for f in simple['findings']))

    def test_simple_results_disclose_incomplete_scope_and_model_failures(self):
        for name in ('valid_base', 'defect_code'):
            with self.subTest(case=name):
                full = review(load_markdown(ROOT / 'inputs' / f'{name}.md'), FakeClient('timeout'))
                simple = simplify_report(full, 'offline')
                self.assertEqual(simple['status'], full['status'])
                self.assertNotEqual(simple['status'], 'PASS')
                self.assertIn('could not be completed', simple['summary'])
                self.assertEqual(simple['coverage']['unreviewed'], full['coverage']['unreviewed'])
                self.assertEqual(simple['resources']['model_calls'], 2)
                self.assertEqual(simple['audit']['model']['attempts'], full['model']['attempts'])

    def test_simple_pass_omits_empty_ticket_results_and_repeated_rule_quotes(self):
        full = review(load_markdown(ROOT / 'inputs/valid_base.md'))
        simple = simplify_report(full, 'offline')
        self.assertEqual(simple['findings'], [])
        self.assertNotIn('ticket_results', simple)
        self.assertEqual(simple['coverage']['rules'], {'R1': 'reviewed', 'R2': 'reviewed', 'R3': 'reviewed', 'R4': 'reviewed'})
        self.assertTrue(all(set(check) == {'check', 'status'} for check in simple['check_results']))
        full['check_results'] = [{'check': 'code_syntax:my_code', 'status': 'PASS'}]
        self.assertEqual(simplify_report(full, 'offline')['check_results'][0]['check'], 'code syntax:my_code')

        bundle = load_markdown(ROOT / 'inputs/valid_base.md')
        bundle['snippets'][0]['code'] = 'def route(ticket):\n    if :\n'
        syntax = simplify_report(review(bundle), 'offline')
        validate(syntax, load_json(ROOT / 'schemas/report.schema.json'))
        self.assertEqual(syntax['status'], 'CHANGES_REQUIRED')
        self.assertTrue(all(f['evidence'] for f in syntax['findings']))

    def test_all_24_preserved_cases_match_regression_expectations(self):
        expected = load_json(ROOT / 'tests/expected.json')
        self.assertEqual({p.stem for p in (ROOT / 'inputs').glob('*.md')}, set(expected))
        self.assertEqual(len(expected), 24)
        for name, case in expected.items():
            with self.subTest(case=name):
                b = load_markdown(ROOT / 'inputs' / f'{name}.md')
                self.assertEqual(hashlib.sha256(json.dumps(b, sort_keys=True).encode()).hexdigest(), case['bundle_sha256'])
                r = review(b, FakeClient(case['model_mode']))
                self.assertEqual(r['status'], case['status'])
                self.assertTrue(all(not rule['text'].startswith(('IF ', 'WHEN ', 'OTHERWISE ')) for rule in b['requirements']))

    def test_offline_batch_creates_matching_complete_json_files(self):
        with tempfile.TemporaryDirectory() as directory:
            p = self.run_cli('--offline', '--output-dir', directory)
            self.assertEqual(p.returncode, 2)  # The batch includes incomplete cases.
            self.assertEqual(p.stdout, '')
            self.assertEqual({f.name for f in Path(directory).glob('*.json')}, {f.with_suffix('.json').name for f in (ROOT / 'inputs').glob('*.md')})
            schema = load_json(ROOT / 'schemas/report.schema.json')
            for path in Path(directory).glob('*.json'):
                r = load_json(path)
                validate(r, schema)
                b = load_markdown(ROOT / 'inputs' / path.with_suffix('.md').name)
                self.assertEqual(r['audit']['provenance']['bundle_sha256'], hashlib.sha256(json.dumps(b, sort_keys=True).encode()).hexdigest())
                self.assertEqual(r['mode'], 'offline')
                if r['resources']['model_calls']:
                    self.assertIn('fake', r['audit']['model']['client'])
                else:
                    self.assertEqual(r['audit']['model'], {})

    def test_one_custom_file_writes_one_result(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'my_case.md'
            text = (ROOT / 'inputs/valid_base.md').read_text().replace('# Case: valid_base', '# Case: my_case')
            source.write_text(text)
            target = Path(directory) / 'results'
            p = self.run_cli(source, '--offline', '--output-dir', target)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(p.stdout, '')
            self.assertEqual(load_json(target / source.with_suffix('.json').name)['status'], 'PASS')
            self.assertEqual(len(list(target.iterdir())), 1)

    def test_bad_input_creates_incomplete_json_and_batch_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'inputs', Path(directory) / 'outputs'
            source.mkdir()
            (source / 'bad.md').write_text('Missing Markdown sections')
            (source / 'good.md').write_bytes((ROOT / 'inputs/valid_base.md').read_bytes())
            p = self.run_cli(source, '--offline', '--output-dir', target)
            self.assertEqual(p.returncode, 2)
            self.assertEqual(load_json(target / 'bad.json')['status'], 'INCOMPLETE')
            self.assertEqual(load_json(target / 'good.json')['status'], 'PASS')
            self.assertEqual(p.stdout, '')

    def test_output_cannot_overwrite_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'case.md'
            original = (ROOT / 'inputs/valid_base.md').read_bytes()
            source.write_bytes(original)
            p = self.run_cli(source, '--offline', '--output-dir', directory)
            self.assertEqual(p.returncode, 2)
            self.assertIn('separate from input', p.stderr)
            self.assertEqual(source.read_bytes(), original)

    def test_failed_save_keeps_previous_result_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'result.json'
            target.write_text('{"previous": true}')
            with patch('reviewer.__main__.os.replace', side_effect=OSError('Disk error')):
                with self.assertRaises(OSError):
                    save_report(target, {'status': 'PASS'})
            self.assertEqual(target.read_text(), '{"previous": true}')
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_real_ai_is_default_and_failure_never_uses_synthetic_responses(self):
        class Unavailable:
            provenance = 'live-local-ollama'

            def complete(self, request, config):
                self.config = config
                raise OSError('AI service unavailable')

        client = Unavailable()
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(sys, 'argv', ['reviewer', str(ROOT / 'inputs/valid_base.md'), '--output-dir', directory]), \
                patch('reviewer.__main__.OllamaClient', return_value=client), \
                patch('reviewer.__main__.FakeClient') as fake, \
                contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(), 2)
            fake.assert_not_called()
            self.assertEqual(stdout.getvalue(), '')
            r = load_json(Path(directory) / 'valid_base.json')
            self.assertEqual(r['status'], 'INCOMPLETE')
            self.assertEqual(r['resources']['model_calls'], 2)
            self.assertEqual(client.config.model, 'qwen3.5:9b')
            self.assertIs(client.config.thinking, False)
