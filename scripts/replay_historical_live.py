"""Replay old observations with their archived implementation, never relabel them."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ['SHODH_IMPLEMENTATION_ROOT'])

from reviewer.contracts import load_json
from reviewer.engine import review
from reviewer.markdown import load_markdown
from reviewer.model import Config


class RecordedClient:
    provenance = 'historical response replay; no network or new inference'

    def __init__(self, response):
        self.response = response

    def complete(self, request, config):
        return self.response


def replay(bundle, saved):
    if not saved['resources']['model_calls']:
        assert review(bundle)['status'] == saved['status']
        return False
    attempt = saved['model']['attempts'][-1]
    assert attempt['result'] == 'validated'
    r = review(bundle, RecordedClient(attempt['response']), Config(**saved['model']['configuration']))
    for key in ('request_sha256', 'response_schema_sha256'):
        assert r['model'][key] == saved['model'][key], key
    assert r['status'] == saved['status']
    assert r['model']['attempts'][-1]['result'] == 'validated'
    return True


def main():
    live = load_json(ROOT/'reports/live_current.json')
    assert len(live['cases']) == 5
    for row in live['cases']:
        replay(load_json(ROOT/'evaluation/inputs'/f"{row['id']}.json"), row['report'])
        assert row['actual'] == row['expected']
    public = load_json(ROOT/'reports/pre_usability_outputs.json')
    count = sum(replay(load_markdown(ROOT/'inputs'/f'{name}.md'), report) for name, report in public.items())
    assert len(public) == 24
    assert public['valid_unusual_units']['status'] == 'INCOMPLETE'
    result = {'scope':'Historical observations replayed with pre-usability-fixes.zip and their original prompt/schema. No new inference and no claim about current-model accuracy.',
              'original_live_development': {'scope':live['scope'],'configuration':live['configuration'],'metrics':live['metrics']},
              'pre_fix_public_outputs':len(public),'pre_fix_validated_responses_replayed':count,
              'preserved_failure':'valid_unusual_units unnecessarily returned INCOMPLETE before the fix'}
    (ROOT/'reports/historical_live_replay.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Historical replay: 5 original cases and {len(public)} pre-fix outputs; {count} validated pre-fix responses.')


if __name__ == '__main__':
    main()
