"""New-case labels and the production checkpoint were frozen before evaluation."""

import hashlib
import json
import unittest
import zipfile
from pathlib import Path

from scripts.evaluate_additional_cases import expected_route

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'evaluation/reserved_20261118'


class ReservedProtocolTests(unittest.TestCase):
    def test_frozen_content_and_first_result_are_preserved(self):
        raw=(FOLDER/'manifest.json').read_bytes()
        manifest=json.loads(raw)
        self.assertEqual(len(manifest['cases']),8)
        with zipfile.ZipFile(ROOT/'checkpoints/reserved_20261118.zip') as checkpoint:
            for name,expected in manifest['files'].items():
                data = checkpoint.read(name) if name.startswith(('reviewer/', 'schemas/')) else (ROOT/name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),expected,name)
        first=json.loads((ROOT/'reports/additional_offline_first.json').read_text())
        self.assertEqual(first['manifest_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(first['metrics']['total'],8)
        self.assertEqual(first['metrics']['correct'],8)

    def test_independent_oracle_boundaries_and_overlapping_exception(self):
        p=json.loads((FOLDER/'labels/new_reserved_a.json').read_text())['oracle']
        manual,priority,escalation,normal=p['routes']
        boundary={p['topic']:'billing',p['urgent']:False,p['age']:p['threshold_seconds'],p['tries']:p['minimum']}
        self.assertEqual(expected_route(boundary,p),escalation)
        self.assertEqual(expected_route({**boundary,p['age']:p['threshold_seconds']-1},p),normal)
        overlapping={**boundary,p['urgent']:True,p['tries']:p['priority_minimum']}
        self.assertEqual(expected_route(overlapping,p),priority)
        del overlapping[p['topic']]
        self.assertEqual(expected_route(overlapping,p),manual)
