"""Read the documented Markdown case format without executing embedded code."""

import csv
import json
import re
from fractions import Fraction
from pathlib import Path

from .contracts import MAX_BYTES, ROOT, Unsupported, load_json, validate, validate_bundle
from .english import EnglishCondition
from .language import UNITS, normalize


def headings(text, prefix):
    before, records, current, fence = [], [], None, None
    for line in text.splitlines(keepends=True):
        marker = re.fullmatch(r'(`{3,})([^`]*)\n?', line)
        if fence:
            if line.strip() == fence:
                fence = None
        elif marker:
            fence = marker[1]
        elif line.startswith(prefix):
            current = []
            records.append((line[len(prefix):].strip(), current))
            continue
        (before if current is None else current).append(line)
    if fence:
        raise Unsupported('Close the Python code block with matching backticks')
    names = [name for name, _ in records]
    if len(names) != len(set(names)):
        raise Unsupported('Duplicate Markdown section or record heading')
    return ''.join(before).strip(), [(name, ''.join(lines).strip()) for name, lines in records]


def properties(text, allowed, *, body=False):
    header, separator, prose = text.partition('\n\n') if body else (text, '', '')
    if body:
        first = header.splitlines()[0] if header else ''
        if first and not first.startswith('- ') and first.partition(':')[0] not in allowed:
            return {'text': text}
    values = {}
    for line in header.splitlines():
        if not line.strip():
            continue
        line = line.removeprefix('- ')
        key, colon, value = line.partition(':')
        if not colon or key not in allowed or allowed[key] in values:
            raise Unsupported(f'Unknown or repeated Markdown property: {line}')
        value = value.strip()
        if not value:
            raise Unsupported(f'Give a value for {key}')
        if key in ('Version', 'Order', 'Revision', 'Sequence', 'Base version', 'From revision', 'To revision'):
            if not re.fullmatch(r'-?\d+', value):
                raise Unsupported(f'{key} must be a whole number')
            value = int(value)
        values[allowed[key]] = value
    if body:
        if not separator or not prose:
            raise Unsupported('Separate the metadata and rule text/code with a blank line')
        values['text'] = prose
    return values


def json_numbers(value):
    if isinstance(value, Fraction):
        try:
            number = int(value) if value.denominator == 1 else float(value)
        except OverflowError as exc:
            raise Unsupported('This cutoff is too large to store exactly') from exc
        if Fraction(str(number)) != value:
            raise Unsupported('This cutoff cannot be stored exactly; use a smaller native unit')
        return number
    if isinstance(value, dict):
        return {key: json_numbers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [json_numbers(child) for child in value]
    return value


def condition(text, fields):
    if text in ('always', 'never'):
        return text == 'always'
    parser = EnglishCondition(text, fields)
    expr = parser.expression()
    if parser.i != len(parser.tokens):
        raise Unsupported('The whole When condition must use the documented rule language')
    normalize(expr, fields)
    return json_numbers(expr)


def example_tickets(text, fields):
    preface, records = headings(text, '### ')
    if preface == 'None.' and not records:
        return []
    if preface and records:
        raise Unsupported('Put each example ticket under its own ### heading')
    records = records or [('ticket', preface)]
    if len(records) > 128:
        raise Unsupported('Provide at most 128 example tickets')
    tickets = []
    for _, content in records:
        ticket, seen = {}, set()
        if not content:
            raise Unsupported('Supply ticket details, or use None. for no example tickets')
        for line in content.splitlines():
            if not line.strip():
                continue
            name, colon, value = line.strip().partition(':')
            if not colon or name not in fields or name in seen:
                raise Unsupported('Example tickets must use unique declared field names')
            seen.add(name)
            value = value.strip()
            if not value or value.casefold() == 'missing':
                continue
            field = fields[name]
            if value.casefold() == 'null':
                parsed = None
            elif field['type'] == 'boolean':
                if value.casefold() not in ('yes', 'no', 'true', 'false'):
                    raise Unsupported(f'{name}: use yes or no')
                parsed = value.casefold() in ('yes', 'true')
            elif field['type'] == 'number':
                match = re.fullmatch(r'(-?\d+)(?:\s+(seconds?|minutes?|hours?|count))?', value)
                if not match:
                    raise Unsupported(f'{name}: give a whole number, optionally followed by its time unit')
                unit = match[2] or field['unit']
                unit = unit + 's' if unit in ('second', 'minute', 'hour') else unit
                if (unit == 'count') != (field['unit'] == 'count'):
                    raise Unsupported(f'{name}: incompatible ticket units')
                quantity = Fraction(int(match[1]) * UNITS[unit], UNITS[field['unit']])
                if quantity.denominator != 1:
                    raise Unsupported(f'{name}: the ticket value must be a whole number in {field["unit"]}')
                parsed = int(quantity)
            else:
                parsed = json.loads(value) if value.startswith('"') else value
                if parsed not in field['values']:
                    raise Unsupported(f'{name}: choose a declared category')
            ticket[name] = parsed
        tickets.append(ticket)
    return tickets


def parse_markdown(text):
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise Unsupported(f'Input exceeds {MAX_BYTES} bytes; nothing was truncated')
    text = text.replace('\r\n', '\n')
    title, sections = headings(text, '## ')
    first, newline, metadata = title.partition('\n')
    if not first.startswith('# Case: '):
        raise Unsupported('Start with # Case: your_case_name')
    bundle = {'schema_version': '1.0', 'id': first[len('# Case: '):].strip(),
              **properties(metadata, {'Revision': 'revision'})}
    sections = dict(sections)
    expected = {'Ticket details', 'Company rules', 'Specification', 'Workflow', 'Python', 'Approvals'}
    if set(sections) - {'Example tickets'} != expected:
        raise Unsupported(f'Use these Markdown sections: {", ".join(sorted(expected))}; Example tickets is optional')
    has_approvals = sections['Approvals'].strip() != 'None.'
    if has_approvals and 'revision' not in bundle:
        raise Unsupported('Give an explicit Revision when approval records are supplied')
    bundle.setdefault('revision', 1)
    new_case = bundle['revision'] == 1 and not has_approvals

    def version(record):
        if 'version' not in record:
            if not new_case:
                raise Unsupported('Give explicit artifact and rule versions for existing revisions or approval histories')
            record['version'] = 1
    fields = {}
    for line in sections['Ticket details'].splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]{0,79}):\s*(number|yes-no|choice)(?:\s+\((.*)\))?', line.strip())
        if not match or match[1] in fields:
            raise Unsupported('Use one unique ticket detail per line, such as waiting: number (minutes)')
        name, kind, detail = match.groups()
        field = {'type': {'yes-no': 'boolean', 'choice': 'enum'}.get(kind, kind)}
        if kind == 'number':
            field['unit'] = detail
        elif kind == 'choice':
            try:
                field['values'] = next(csv.reader([detail or ''], skipinitialspace=True, strict=True))
            except csv.Error as exc:
                raise Unsupported(f'Invalid comma-separated Choices: {exc}') from exc
        elif detail is not None:
            raise Unsupported('A yes-no ticket detail does not take units or choices')
        fields[name] = field
    bundle['fields'] = fields
    schema = load_json(ROOT / 'schemas/bundle.schema.json')
    validate(fields, schema['properties']['fields'], schema)
    maps = {
        'Company rules': {'Version': 'version', 'Order': 'order', 'Location': 'location'},
        'Specification': {'Order': 'order', 'Company rule': 'rule_ref', 'When': 'when', 'Route': 'route'},
        'Workflow': {'Company rule': 'rule_ref', 'Code': 'snippet_id', 'When': 'when', 'Yes': 'true', 'No': 'false', 'Route': 'route'},
        'Python': {'Version': 'version'},
        'Approvals': {'Company rule': 'rule_ref', 'Status': 'status', 'Base version': 'base_version', 'Version': 'version',
                      'Sequence': 'sequence', 'From revision': 'from_revision', 'To revision': 'to_revision'},
    }
    for section, mapping in maps.items():
        preface, records = headings(sections[section], '### ')
        metadata = properties(preface, {'Version': 'version', **({'Start': 'entry'} if section == 'Workflow' else {})}) if section in ('Specification', 'Workflow') else {}
        if section in ('Specification', 'Workflow'):
            version(metadata)
        if section not in ('Specification', 'Workflow') and preface != ('None.' if not records else ''):
            raise Unsupported(f'{section}: use ### records, or None. for an empty section')
        items = []
        for position, (name, content) in enumerate(records):
            item = {'id': name, **properties(content, mapping, body=section in ('Company rules', 'Python', 'Approvals'))}
            if section in ('Company rules', 'Specification'):
                item.setdefault('order', position)
            if section in ('Company rules', 'Python'):
                version(item)
            if section == 'Company rules':
                item.setdefault('location', f"policy/paragraph/{item['order'] + 1}")
            if 'when' in item:
                item['when'] = condition(item['when'], fields)
            if section == 'Workflow':
                item['kind'] = 'decision' if 'when' in item else 'route'
            if section == 'Python':
                match = re.fullmatch(r'(`{3,})python\n(.*)\n\1', item.pop('text'), re.S)
                if not match:
                    raise Unsupported('Put literal Python in a fenced ```python code block')
                item['code'] = match[2] + '\n'
            items.append(item)
        key = {'Company rules': 'requirements', 'Specification': 'specification', 'Workflow': 'workflow', 'Python': 'snippets', 'Approvals': 'approvals'}[section]
        bundle[key] = {**metadata, 'rules' if section == 'Specification' else 'nodes': items} if section in ('Specification', 'Workflow') else items
    if 'Example tickets' in sections:
        bundle['example_tickets'] = example_tickets(sections['Example tickets'], fields)
    validate_bundle(bundle)
    return bundle


def load_markdown(path):
    path = Path(path)
    if path.suffix.lower() != '.md':
        raise Unsupported('Scenario inputs must be .md Markdown files')
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise Unsupported(f'Input exceeds {MAX_BYTES} bytes; nothing was truncated')
    return parse_markdown(raw.decode('utf-8'))
