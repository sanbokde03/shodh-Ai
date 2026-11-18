"""Restored assessment comparisons must detect changed Markdown behavior."""

import copy
import unittest

from reviewer.contracts import ROOT, load_json
from reviewer.markdown import load_markdown
from scripts.verify import compare_translation


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.original = load_json(ROOT / 'evaluation/inputs/valid_base.json')
        self.translated = load_markdown(ROOT / 'inputs/valid_base.md')

    def test_supported_paraphrases_preserve_meaning(self):
        self.assertEqual(compare_translation(self.original, self.translated), 0)

    def test_changed_meaning_or_branch_is_rejected(self):
        changed = copy.deepcopy(self.translated)
        changed['requirements'][2]['text'] = 'Escalate tickets waiting more than 30 minutes.'
        with self.assertRaisesRegex(ValueError, 'meaning'):
            compare_translation(self.original, changed)
        changed = copy.deepcopy(self.translated)
        changed['workflow']['nodes'][2]['true'] = 'out_normal'
        with self.assertRaisesRegex(ValueError, 'structure'):
            compare_translation(self.original, changed)

    def test_unresolved_wording_cannot_replace_a_supported_rule(self):
        changed = copy.deepcopy(self.translated)
        changed['requirements'][2]['text'] = 'Escalate tickets waiting too long.'
        with self.assertRaisesRegex(ValueError, 'meaning'):
            compare_translation(self.original, changed)
