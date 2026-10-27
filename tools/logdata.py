"""Validate telemetry at the reader boundary and give exports source/session identities.

Validation never discards raw evidence. Invalid records remain exportable with
errors, but cannot contribute to behavioral conclusions. IDs are match-local.
"""
from collections import Counter
import math


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def identity(value):
    return finite(value) and value > 0 and int(value) == value


# These contracts cover the events used by the feedback analyzer. Other event
# kinds remain visible and are inventoried as unchecked, rather than called valid.
CONTRACTS = {
    'dact': {'a': dict, 'k': str},
    'micro': {'army': dict, 'to': str},
    'order': {'type': str},
    'end': {'type': str, 'why': (str, type(None))},
    'stop': {'type': str, 'why': (str, type(None))},
    'phase': {'to': 'number'},
    'rfail': {'r': str, 'at': 'number'},
    'trap': {'src': str},
    'bcamp': {'act': str, 'tgt': dict},
    'snap': {'armies': 'number', 'structs': 'number'},
    'aw': {'a': list, 'n': 'number'},
    'opcast': {'op': str},
    'opfail': {'op': str},
    'odead': {},
    'hunt': {'act': str},
    'call': {'fn': str},
}


def validate(event):
    if event.get('_parse') == 'failed':
        return []  # parser failures already have their own diagnostic
    errors = []
    if event.get('f') is not None and (not isinstance(event['f'], str) or not event['f'].strip()):
        errors.append('f must be a faction string')
    if not any(finite(event.get(field)) for field in ('g', 't')):
        errors.append('missing usable clock')
    for field in ('g', 't'):
        if event.get(field) is not None and not finite(event[field]):
            errors.append(f'{field} must be finite')
    for field, expected in CONTRACTS.get(event.get('e'), {}).items():
        value = event.get(field)
        good = finite(value) if expected == 'number' else isinstance(value, expected)
        if field not in event or not good or expected is str and not value.strip():
            errors.append(f'{field} missing or invalid')
    if event.get('e') in ('dact', 'micro', 'order', 'end', 'stop', 'snap', 'bcamp', 'aw', 'opcast', 'opfail', 'odead', 'hunt'):
        if not isinstance(event.get('f'), str):
            errors.append('f missing or invalid')
    if event.get('oid') is not None and not identity(event['oid']):
        errors.append('oid must be a positive integer')
    for key in ('at',) if event.get('e') == 'rfail' else ('to',) if event.get('e') == 'phase' else ():
        if finite(event.get(key)) and (event[key] < 0 or int(event[key]) != event[key]):
            errors.append(f'{key} must be a non-negative integer')
    if event.get('e') == 'opfail' and event.get('r') is not None and not finite(event['r']):
        errors.append('r must be a numeric reason code')
    if event.get('e') == 'call' and str(event.get('fn', '')).endswith('set_isAI'):
        if not isinstance(event.get('f'), str) or not any(isinstance(event.get(k), bool) for k in ('a1', 'r')):
            errors.append('AI-control event needs a faction and boolean state')
    if event.get('e') == 'bcamp' and event.get('hp') is not None:
        if not finite(event['hp']) or not 0 <= event['hp'] <= 100:
            errors.append('hp outside 0..100')
    for field in ('a', 'army', 'tgt', 's', 'near', 'pt', 'nt'):
        entity = event.get(field)
        if not isinstance(entity, dict):
            continue
        if entity.get('id') is not None and not identity(entity['id']):
            errors.append(f'{field}.id must be a positive integer')
        for name in ('k', 'o', 'p'):
            if entity.get(name) is not None and not isinstance(entity[name], str):
                errors.append(f'{field}.{name} must be text')
        for name in ('x', 'y'):
            if entity.get(name) is not None and not finite(entity[name]):
                errors.append(f'{field}.{name} must be finite')
    pending = [('', event)]
    while pending and len(errors) < 12:
        path, value = pending.pop()
        if isinstance(value, float) and not math.isfinite(value):
            errors.append(f'{path} contains a non-finite number')
        elif isinstance(value, dict):
            pending.extend((f'{path}.{k}'.lstrip('.'), v) for k, v in value.items() if not k.startswith('_'))
        elif isinstance(value, list):
            pending.extend((f'{path}[{i}]', v) for i, v in enumerate(value))
    return list(dict.fromkeys(errors))


def prepare(events):
    """Copies with file-order session labels; clock resets never merge reused IDs."""
    result, session = [], 1
    previous = {}
    for event in events:
        reset = any(finite(event.get(key)) and key in previous and previous[key] - event[key] > 1
                    for key in ('t', 'g'))
        if reset:
            session += 1
            previous.clear()
        previous.update({key: event[key] for key in ('t', 'g') if finite(event.get(key))})
        result.append(dict(event, _session=session, _validation_errors=validate(event)))
    return result


def sessions(events):
    return sorted({e['_session'] for e in events})


def matches(event, faction=None, kinds=None, entity=None, order=None, session=None):
    if faction and event.get('f') != faction or kinds and event.get('e') not in kinds:
        return False
    if session is not None and event['_session'] != session:
        return False
    if order is not None and event.get('oid') != order:
        return False
    if entity is not None:
        pending = [event]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                if value.get('id') == entity:
                    break
                pending.extend(v for k, v in value.items() if not k.startswith('_'))
            elif isinstance(value, list):
                pending.extend(value)
        else:
            return False
    return True


def audit(events):
    invalid = [e for e in events if e['_validation_errors']]
    checked = sum(e.get('e') in CONTRACTS for e in events)
    return {'checked_events': checked, 'invalid_events': len(invalid),
            'usable_events': sum(not e['_validation_errors'] and e.get('_parse', 'full') == 'full' for e in events),
            'unchecked_event_kinds': dict(Counter(e.get('e') for e in events if e.get('e') not in CONTRACTS)),
            'sessions': [{'id': sid, 'events': sum(e['_session'] == sid for e in events)} for sid in sessions(events)]}


def _json_value(value, field=None):
    if isinstance(value, dict):
        return {k: _json_value(v, k) for k, v in value.items() if not k.startswith('_')}
    if isinstance(value, list):
        return [_json_value(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None  # invalid data is explicit in validation_errors and the source line remains addressable
    if field in ('id', 'oid') and identity(value):
        return int(value)
    return value


def export_record(event, source_sha256):
    line = event.get('_line')
    record = {'schema_version': 1, 'source_sha256': source_sha256,
              'record_id': f'{source_sha256}:{line}', 'session': event['_session'], 'line': line,
              'parse_status': event.get('_parse', 'full'), 'validation_errors': event['_validation_errors'],
              'event': _json_value(event)}
    if event.get('_raw'):
        record['raw_excerpt'] = event['_raw']
    return record
