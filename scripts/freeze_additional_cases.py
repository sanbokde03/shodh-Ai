"""Freeze new, AI-authored procedural holdouts before reviewer execution."""

import hashlib
import json
import random
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'evaluation/reserved_20261118'
SEED = 2026111801


def prop(name, value):
    return f'- {name}: {value}\n'


def expression(e):
    if type(e) is bool:
        return 'always' if e else 'never'
    op = e['op']
    if op in ('and', 'or'):
        return '(' + f' {op} '.join(expression(a) for a in e['args']) + ')'
    if op == 'missing':
        return f"{e['field']} is missing"
    phrase = {'eq':'', 'gte':'at least', 'gt':'more than'}[op]
    return f"{e['field']} is {phrase} {json.dumps(e['value'])}".replace('  ', ' ') + (f" {e['unit']}" if 'unit' in e else '')


def markdown(b):
    text = f"# Case: {b['id']}\n\n" + prop('Revision', b['revision']) + '\n## Ticket details\n\n'
    for name, f in b['fields'].items():
        value = f"number ({f['unit']})" if f['type'] == 'number' else 'yes-no' if f['type'] == 'boolean' else 'choice (' + ','.join(f['values']) + ')'
        text += f'{name}: {value}  \n'
    text += '\n## Company rules\n\n'
    for r in b['requirements']:
        text += f"### {r['id']}\n\n" + prop('Order', r['order']) + prop('Version', r['version']) + prop('Location', r['location']) + '\n' + r['text'] + '\n\n'
    text += '## Specification\n\n' + prop('Version', b['specification']['version']) + '\n'
    for r in b['specification']['rules']:
        text += f"### {r['id']}\n\n" + prop('Order', r['order']) + prop('Company rule', r['rule_ref']) + prop('When', expression(r['when'])) + prop('Route', r['route']) + '\n'
    text += '## Workflow\n\n' + prop('Version', b['workflow']['version']) + prop('Start', b['workflow']['entry']) + '\n'
    for n in b['workflow']['nodes']:
        text += f"### {n['id']}\n\n"
        for key, label in [('rule_ref','Company rule'), ('snippet_id','Code')]:
            if key in n:
                text += prop(label, n[key])
        if n['kind'] == 'decision':
            text += prop('When', expression(n['when'])) + prop('Yes', n['true']) + prop('No', n['false'])
        else:
            text += prop('Route', n['route'])
        text += '\n'
    text += '## Python\n\n'
    for s in b['snippets']:
        text += f"### {s['id']}\n\n" + prop('Version', s['version']) + '\n```python\n' + s['code'] + '```\n\n'
    text += '## Approvals\n\n'
    if not b['approvals']:
        text += 'None.\n'
    for a in b['approvals']:
        text += f"### {a['id']}\n\n"
        for key,label in [('rule_ref','Company rule'),('status','Status'),('base_version','Base version'),('version','Version'),('sequence','Sequence'),('from_revision','From revision'),('to_revision','To revision')]:
            text += prop(label,a[key])
        text += '\n' + a['text'] + '\n\n'
    text += '\n## Example tickets\n\n'
    for i,ticket in enumerate(b['example_tickets'],1):
        text += f'### Example {i}\n\n'
        for key,value in ticket.items():
            text += f"{key}: {('yes' if value else 'no') if type(value) is bool else value}  \n"
        text += '\n'
    return text


def main():
    if FOLDER.exists():
        raise SystemExit('Reserved freeze already exists; never overwrite or relabel inspected cases')
    FOLDER.mkdir()
    for folder in ('inputs','labels'):
        (FOLDER/folder).mkdir()
    rng = random.Random(SEED)
    manifest = {'created_before_evaluation_utc':datetime.now(timezone.utc).isoformat(), 'seed':SEED,
                'label_method':'Direct policy reasoning and a separate handwritten routing oracle; never reviewer predictions. AI-authored, not human-audited.',
                'reservation':'Eight new concrete variants created after the two usability fixes. Families/generator are known to the author; excluded from tuning. First evaluation must use the frozen production checkpoint. Once evaluated they become exposed historical cases.',
                'files':{}, 'cases':[]}
    for letter in 'abcdefgh':
        token = rng.randrange(10000,99999)
        age, tries, urgent, topic = (f'{name}_{token}' for name in ('age','attempts','urgent','topic'))
        manual, priority, escalation, normal = (f'{name}_{token}' for name in ('Manual','Priority','Escalation','Normal'))
        refs = [f'policy_{token}_{i}' for i in range(4)]
        threshold, minimum, priority_min = rng.randrange(11,35), rng.randrange(2,5), rng.randrange(6,9)
        effective = threshold - 3 if letter == 'b' else threshold
        revision = rng.randrange(20,90)
        priority_expr = {'op':'and','args':[{'op':'eq','field':urgent,'value':True}, {'op':'or','args':[{'op':'eq','field':topic,'value':'security'},{'op':'gte','field':tries,'value':priority_min}]}]}
        escalation_expr = {'op':'and','args':[{'op':'gte','field':age,'value':effective*60,'unit':'seconds'},{'op':'gte','field':tries,'value':minimum}]}
        source_age = f'not ({age} is less than {threshold} minutes or {age} is missing)' if letter == 'a' else f'{age} is at least {threshold} minutes'
        source_texts = [f'If {topic} is missing, send the ticket to "{manual}".',
            f'If {urgent} is yes and ({topic} is "security" or {tries} is at least {priority_min}), send the ticket to "{priority}".',
            f'If {source_age} and {tries} is at least {minimum}, send the ticket to "{escalation}".',
            f'For all remaining tickets, send the ticket to "{normal}".']
        routes = [manual,priority,escalation,normal]
        predicates = [{'op':'missing','field':topic},priority_expr,escalation_expr,True]
        rules = [{'id':refs[i],'order':i,'version':1,'location':f'new_policy/{token}/paragraph/{i+1}','text':source_texts[i]} for i in range(4)]
        nodes = [dict(id='check_topic',kind='decision',rule_ref=refs[0],when=predicates[0],true='out_manual',false='check_priority',snippet_id='router'),
                 dict(id='check_priority',kind='decision',rule_ref=refs[1],when=priority_expr,true='out_priority',false='check_age'),
                 dict(id='check_age',kind='decision',rule_ref=refs[2],when=escalation_expr,true='out_escalation',false='out_normal')]
        nodes += [dict(id='out_'+name,kind='route',route=route) for name,route in zip(('manual','priority','escalation','normal'),routes)]
        code = f'''def route(ticket):
    if ticket.get("{topic}") is None:
        return "{manual}"
    if ticket.get("{urgent}") == True and (ticket.get("{topic}") == "security" or (ticket.get("{tries}") is not None and ticket.get("{tries}") >= {priority_min})):
        return "{priority}"
    if ticket.get("{age}") is not None and ticket.get("{age}") >= {effective*60} and ticket.get("{tries}") is not None and ticket.get("{tries}") >= {minimum}:
        return "{escalation}"
    return "{normal}"
'''
        b = {'schema_version':'1.0','id':f'new_reserved_{letter}','revision':revision,
             'fields':{age:{'type':'number','unit':'seconds'},tries:{'type':'number','unit':'count'},urgent:{'type':'boolean'},topic:{'type':'enum','values':['billing','security','research']}},
             'requirements':rules, 'specification':{'version':rng.randrange(2,8),'rules':[dict(id=f'spec_{token}_{i}',order=i,rule_ref=refs[i],when=json.loads(json.dumps(predicates[i])),route=routes[i]) for i in range(4)]},
             'workflow':{'version':rng.randrange(2,8),'entry':'check_topic','nodes':json.loads(json.dumps(nodes))},
             'snippets':[{'id':'router','version':rng.randrange(2,8),'code':code}], 'approvals':[],
             'example_tickets':[{topic:'billing',urgent:False,age:effective*60,tries:minimum},{urgent:True,tries:priority_min,age:effective*60}]}
        status, kind, target = 'PASS','valid',None
        reason = 'New fields/routes, nested AND/OR, missing guards and native seconds preserve the ordered policy.'
        if letter in ('a','b','h'):
            replacement = f'If {age} is at least {effective if letter=="b" else threshold-2} minutes and {tries} is at least {minimum}, send the ticket to "{escalation}".'
            a = dict(id=f'approval_{token}',rule_ref=refs[2],status='approved' if letter in ('b','h') else 'proposed',base_version=1,version=2,sequence=1,from_revision=revision,to_revision=revision,text=replacement)
            b['approvals']=[a]
        if letter=='a':
            reason = 'NOT(less than cutoff OR missing) is equivalent to a guarded inclusive cutoff; an unapproved proposal has no effect.'
        elif letter=='b':
            reason = 'Applicable approved change lowers the cutoff; specification, workflow and code use the new value.'
        elif letter=='c':
            b['workflow']['nodes'][2]['when']['args'][0]['op']='gt'
            status,kind='CHANGES_REQUIRED','defective'
            target={'artifact':'workflow','rule_ref':refs[2],'location':'/nodes/2'}
            reason='At exactly the cutoff with enough attempts, workflow uses > instead of >= and chooses normal.'
        elif letter=='d':
            b['workflow']['entry']='check_priority'
            b['workflow']['nodes'][1]['false']='check_topic'
            b['workflow']['nodes'][0]['false']='check_age'
            b['workflow']['nodes'][1]['snippet_id']=b['workflow']['nodes'][0].pop('snippet_id')
            status,kind='CHANGES_REQUIRED','defective'
            target={'artifact':'workflow','rule_ref':refs[0],'location':'/nodes/1'}
            reason='Missing category and urgent/enough attempts overlap; policy requires manual but workflow prioritizes first.'
        elif letter=='e':
            b['snippets'][0]['code']=code.replace(f'ticket.get("{urgent}")',f'ticket["{urgent}"]')
            status,kind='CHANGES_REQUIRED','defective'
            target={'artifact':'code','rule_ref':refs[3],'location':'router:4'}
            reason='Categorized ticket without the urgent key should use normal, but Python raises KeyError.'
        elif letter=='f':
            b['workflow']['nodes'][2]['true']='out_normal'
            status,kind='CHANGES_REQUIRED','defective'
            target={'artifact':'workflow','rule_ref':refs[2],'location':'/nodes/2'}
            reason='Correct age/attempt checks point to the wrong destination.'
        elif letter=='g':
            b['requirements'][2]['text']=f'If {age} is too long and {tries} is at least {minimum}, send the ticket to "{escalation}".'
            status,kind='INCOMPLETE','incomplete'
            reason='The source does not define too long; implementation values cannot supply the missing cutoff.'
        elif letter=='h':
            b['approvals'].append({**b['approvals'][0],'id':f'rejected_{token}','status':'rejected'})
            status,kind='INCOMPLETE','incomplete'
            reason='Approved and rejected records target the same rule version and active revision.'
        rng.shuffle(b['requirements'])
        rng.shuffle(b['specification']['rules'])
        label = {'status':status,'kind':kind,'reason':reason,'target':target,
                 'oracle':{'age':age,'tries':tries,'urgent':urgent,'topic':topic,'threshold_seconds':effective*60,'minimum':minimum,'priority_minimum':priority_min,'routes':routes}}
        for subfolder,suffix,data in [('inputs','.md',markdown(b)),('labels','.json',json.dumps(label,indent=2)+'\n')]:
            path=FOLDER/subfolder/(b['id']+suffix);path.write_text(data)
            manifest['files'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
        manifest['cases'].append(b['id'])
    checkpoint=ROOT/'checkpoints/reserved_20261118.zip'
    with zipfile.ZipFile(checkpoint,'w',zipfile.ZIP_DEFLATED) as z:
        for folder in ('reviewer','schemas'):
            for p in sorted((ROOT/folder).rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts:
                    z.write(p,p.relative_to(ROOT));manifest['files'][str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (checkpoint,Path(__file__),ROOT/'scripts/evaluate_additional_cases.py'):
        manifest['files'][str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    (FOLDER/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Frozen eight cases, independent labels, seed, protocol and implementation before evaluation. No reviewer executed.')


if __name__=='__main__':
    main()
