"""Evaluate frozen new cases; expected routes never come from reviewer predictions."""

import argparse
import hashlib
import json
import operator
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from fractions import Fraction

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'evaluation/reserved_20261118'
SCALES={'seconds':1,'minutes':60,'hours':3600,'count':1}


def expected_route(ticket, params):
    manual,priority,escalation,normal=params['routes']
    topic=ticket.get(params['topic'])
    attempts=ticket.get(params['tries'])
    age=ticket.get(params['age'])
    if topic is None:
        return manual
    if ticket.get(params['urgent']) is True and (topic=='security' or (attempts is not None and attempts>=params['priority_minimum'])):
        return priority
    if age is not None and age>=params['threshold_seconds'] and attempts is not None and attempts>=params['minimum']:
        return escalation
    return normal


def predicate(e,ticket,fields):
    if type(e) is bool:
        return e
    op=e['op']
    if op=='and':return all(predicate(a,ticket,fields) for a in e['args'])
    if op=='or':return any(predicate(a,ticket,fields) for a in e['args'])
    if op=='not':return not predicate(e['arg'],ticket,fields)
    actual=ticket.get(e['field'])
    if op=='missing':return actual is None
    if actual is None:return op=='ne'
    expected=e['value']
    if 'unit' in e:
        expected=Fraction(str(expected))*SCALES[e['unit']]/SCALES[fields[e['field']]['unit']]
    return {'eq':operator.eq,'ne':operator.ne,'lt':operator.lt,'lte':operator.le,'gt':operator.gt,'gte':operator.ge}[op](actual,expected)


def actual_route(bundle,artifact,ticket):
    if artifact=='specification':
        return next((r['route'] for r in sorted(bundle['specification']['rules'],key=lambda r:r['order']) if predicate(r['when'],ticket,bundle['fields'])),None)
    if artifact=='workflow':
        nodes={n['id']:n for n in bundle['workflow']['nodes']}
        current=bundle['workflow']['entry'];seen=set()
        while current in nodes and current not in seen:
            seen.add(current);node=nodes[current]
            if node['kind']=='route':return node['route']
            current=node['true'] if predicate(node['when'],ticket,bundle['fields']) else node['false']
        return 'ERROR:cycle' if current in seen else 'ERROR:missing_branch'
    if artifact=='code':
        namespace={}
        # Only hash-verified generated fixtures reach this evaluation-only execution.
        exec(compile(bundle['snippets'][0]['code'],'<frozen generated holdout>','exec'),{'__builtins__':{}},namespace)
        try:return namespace['route'](ticket)
        except (KeyError,TypeError) as exc:return f'ERROR:{type(exc).__name__}'
    raise ValueError(artifact)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--live',action='store_true')
    mode.add_argument('--replay-live',action='store_true')
    args=parser.parse_args()
    manifest=json.loads((FOLDER/'manifest.json').read_text())
    for name,sha in manifest['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha,f'Frozen content changed: {name}'
    target=ROOT/'reports'/('additional_live_first.json' if args.live else 'additional_live_replay.json' if args.replay_live else 'additional_offline_first.json')
    if args.live and target.exists():raise SystemExit('First live results already exist; use --replay-live, do not overwrite them')
    if not args.live and not args.replay_live and target.exists():target=ROOT/'reports/additional_offline_replay.json'
    recorded=json.loads((ROOT/'reports/additional_live_first.json').read_text()) if args.replay_live else None
    with tempfile.TemporaryDirectory(prefix='shodh-new-reserved-') as directory:
        with zipfile.ZipFile(ROOT/'checkpoints/reserved_20261118.zip') as archive:archive.extractall(directory)
        sys.path.insert(0,directory)
        from reviewer.contracts import load_json,validate
        from reviewer.markdown import load_markdown
        from reviewer.engine import review,inventory
        from reviewer.model import Config,FakeClient,OllamaClient
        schema=load_json(Path(directory)/'schemas/report.schema.json')
        config=Config(model='qwen3.5:9b',timeout_seconds=90,thinking=False) if args.live or args.replay_live else Config()
        rows=[];counts=Counter();quality=Counter();elapsed=0.0
        result={'scope':'First evaluation of eight new procedural holdouts frozen after usability fixes; families and generator known to the AI author, not a blinded or human-audited benchmark. All concrete cases become exposed after this run.',
                'mode':'real-local-model' if args.live else 'recorded-live-response-replay' if args.replay_live else 'synthetic-offline',
                'new_inference':args.live,'seed':manifest['seed'],'manifest_sha256':hashlib.sha256((FOLDER/'manifest.json').read_bytes()).hexdigest(),
                'configuration':config.__dict__,'metrics':{},'cases':rows}
        for name in manifest['cases']:
            bundle=load_markdown(FOLDER/'inputs'/f'{name}.md')
            label=load_json(FOLDER/'labels'/f'{name}.json')
            saved=next(row['report'] for row in recorded['cases'] if row['id']==name) if recorded else None
            if saved and saved['resources']['model_calls']:
                class RecordedClient:
                    provenance='recorded response validation; no new inference'
                    def complete(self,request,config):return saved['model']['attempts'][-1]['response']
                client=RecordedClient()
            else:client=OllamaClient() if args.live else FakeClient()
            report=review(bundle,client,config)
            validate(report,schema)
            if saved:
                assert report['status']==saved['status']
                if saved['resources']['model_calls']:
                    assert report['model']['request_sha256']==saved['model']['request_sha256']
                    assert report['model']['response_schema_sha256']==saved['model']['response_schema_sha256']
            counts['total']+=1;counts['correct']+=report['status']==label['status']
            counts[f"{label['kind']}_total"]+=1
            counts[f"{label['kind']}_incomplete"]+=report['status']=='INCOMPLETE'
            counts['false_passes']+=label['kind']=='defective' and report['status']=='PASS'
            counts['false_blocks']+=label['kind']=='valid' and report['status']=='CHANGES_REQUIRED'
            counts['calls']+=report['resources']['model_calls'];counts['retries']+=report['resources']['model_retries'];elapsed+=report['resources']['seconds']
            allowed=inventory(bundle)
            for f in report['findings']:
                supported=all(e in allowed for e in f['evidence'])
                if 'counterexample' in f:
                    witness=f['counterexample']
                    agrees=expected_route(witness['ticket'],label['oracle'])==witness['expected_route'] and actual_route(bundle,f['artifact'],witness['ticket'])==witness['actual_route'] and witness['expected_route']!=witness['actual_route']
                    quality['counterexamples']+=1;quality['counterexamples_correct']+=agrees;supported &= agrees
                quality['unsupported_findings']+=not supported
            target_found=None
            if label['target']:
                target_found=any(all(f.get(k)==v for k,v in label['target'].items()) for f in report['findings'])
                quality['target_total']+=1;quality['target_found']+=target_found
            if label['kind']!='incomplete':
                for row in report['ticket_results']:
                    assert expected_route(row['ticket'],label['oracle'])==row['expected_route']
                    for artifact,route in row['artifacts'].items():assert actual_route(bundle,artifact,row['ticket'])==route
            rows.append({'id':name,'kind':label['kind'],'expected':label['status'],'actual':report['status'],'correct':report['status']==label['status'],'target_found':target_found,'report':report})
            result['metrics']={**dict(counts),'finding_quality':dict(quality),'runtime_seconds':elapsed}
            target.write_text(json.dumps(result,indent=2)+'\n')
            print(f"{name}: expected {label['status']}, actual {report['status']}",flush=True)
        print(json.dumps(result['metrics'],indent=2),flush=True)
        return 0 if counts['correct']==counts['total']==8 and not quality['unsupported_findings'] and quality['counterexamples']==quality['counterexamples_correct'] and quality['target_found']==quality['target_total'] else 1


if __name__=='__main__':sys.exit(main())
