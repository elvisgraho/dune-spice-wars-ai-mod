"""Evidence-first match feedback from parsed AIMOD events. No game decisions live here.

Default output is bounded; detailed reports and raw events remain in aireport.
JSON uses the same analysis as text. Historical logs without IDs are explicitly
identified, and moving armies are never correlated by their coordinates.
"""
from collections import Counter, defaultdict, deque
import math
import logdata

LOW_DAMAGE_MIN_S = 60  # only judge completed, sustained attack windows
LOW_DAMAGE_MAX_PP = 1  # observed base HP loss, in percentage points

def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def time_of(event):
    # App seconds are not interchangeable with game seconds at x4 speed.
    return event['g'] if number(event.get('g')) else None


def clock(value):
    return '--:--' if value is None else f'{int(value // 60):02d}:{int(value % 60):02d}'


def label(entity):
    if not isinstance(entity, dict):
        return str(entity) if entity is not None else '?'
    return str(entity.get('p') or entity.get('k') or '?')


def target_key(entity):
    """Static targets can use their name/position in old logs; army tracking requires IDs."""
    if not isinstance(entity, dict):
        return str(entity)
    if number(entity.get('id')):
        return ('id', entity['id'])
    return (entity.get('o'), entity.get('k'), entity.get('p'), entity.get('x'), entity.get('y'))


def analyze(events, faction=None, event_kinds=None, crumbs=None, entity=None, order=None, session=None):
    prepared = logdata.prepare(events)
    available = logdata.sessions(prepared)
    if session is not None:
        if session not in available:
            raise ValueError(f'session {session} is not present; available sessions: {available}')
        available = [session]
    reports = []
    for sid in available or [1]:
        rows = [e for e in prepared if e['_session'] == sid]
        report = _single_report(rows, faction, event_kinds, crumbs if len(logdata.sessions(prepared)) <= 1 else None,
                                entity=entity, order=order)
        report['session'] = sid
        reports.append(report)
    if len(reports) == 1:
        return reports[0]
    return {'schema_version': 2, 'multiple_sessions': True, 'sessions': reports,
            'coverage': {'input_events': len(prepared), 'validation': logdata.audit(prepared)},
            'scope': {'faction': faction, 'events': event_kinds, 'entity': entity, 'order': order}}


def _single_report(events, faction=None, event_kinds=None, crumbs=None, entity=None, order=None):
    selected = [e for e in events if (not faction or e.get('f') == faction)
                and (not event_kinds or e.get('e') in event_kinds)
                and logdata.matches(e, entity=entity, order=order)]
    valid_selected = [e for e in selected if not e['_validation_errors'] and e.get('_parse', 'full') == 'full']
    timed = [e for e in valid_selected if time_of(e) is not None]
    timed.sort(key=time_of)
    start, end = (time_of(timed[0]), time_of(timed[-1])) if timed else (None, None)
    quality = Counter(e.get('_parse', 'full') for e in events)
    counts = Counter(e.get('e', '?') for e in selected)
    byte_counts = Counter()
    for e in selected:
        byte_counts[e.get('e', '?')] += e.get('_bytes', 0)
    findings = []

    def finding(kind, severity, rows, message, fac=None):
        times = [time_of(e) for e in rows if time_of(e) is not None]
        entry = {'kind': kind, 'severity': severity, 'faction': fac, 'count': len(rows),
                         'first_game_s': min(times) if times else None,
                         'last_game_s': max(times) if times else None,
                         'source_lines': [e['_line'] for e in rows[:3] if e.get('_line') is not None], 'message': message}
        findings.append(entry)
        return entry

    damaged = [e for e in events if e.get('_parse') in ('failed', 'salvaged')]
    if damaged:
        finding('parse_quality', 'warning', damaged,
                f'{quality["failed"]} unreadable and {quality["salvaged"]} partially recovered events; inspect raw source lines')
    invalid = defaultdict(list)
    for e in events:
        if e['_validation_errors']:
            invalid[(e.get('e'), tuple(e['_validation_errors']))].append(e)
    for (kind, errors), rows in invalid.items():
        finding('invalid_telemetry', 'error' if kind in ('rfail', 'trap') else 'warning', rows,
                f'{kind}: {"; ".join(errors)}; excluded from behavioral metrics')
    missing_game_clock = [e for e in events if e.get('e') in logdata.CONTRACTS and e.get('e') != 'call'
                          and e.get('_parse', 'full') == 'full' and not e['_validation_errors']
                          and time_of(e) is None]
    if missing_game_clock:
        finding('missing_game_clock', 'warning', missing_game_clock,
                'game clock missing; app seconds retained in exports but excluded from game-time metrics')
    failures = defaultdict(list)
    for e in selected:
        if e['_validation_errors']:
            continue
        if e.get('e') in ('rfail', 'trap'):
            key = (e['e'], e.get('f'), e.get('r') or e.get('src'), e.get('at'), str(e.get('err', ''))[:120])
            failures[key].append(e)
    for (kind, fac, rule, at, error), rows in failures.items():
        location = f'step {at}'
        if number(at) and crumbs is not None and 0 <= int(at) < len(crumbs):
            location = crumbs[int(at)]
        finding(kind, 'error', rows, f'{rule}: {error or location}', fac)

    disabled, control_windows = {}, []
    controls = [e for e in timed if e.get('e') == 'call' and str(e.get('fn', '')).endswith('set_isAI')]
    for e in controls:
        on = e.get('r') if isinstance(e.get('r'), bool) else e.get('a1')
        if not isinstance(on, bool):
            continue
        fac = e.get('f')
        if not on and fac not in disabled:
            disabled[fac] = e
        elif on and fac in disabled:
            first = disabled.pop(fac)
            control_windows.append({'faction': fac, 'start_game_s': time_of(first),
                                    'end_game_s': time_of(e), 'source': first.get('src')})
            if time_of(e) - time_of(first) >= 30:
                finding('ai_off', 'warning', [first, e], 'AI was disabled for at least 30 game seconds', fac)
    for fac, first in disabled.items():
        control_windows.append({'faction': fac, 'start_game_s': time_of(first), 'end_game_s': None,
                                'source': first.get('src')})
        finding('ai_off', 'warning', [first], 'AI is still disabled at the end of the observed log', fac)

    # End callbacks can repeat. New logs deduplicate by actual order identity;
    # old logs use target/action/time and explicitly report that limitation.
    per_faction = defaultdict(Counter)
    seen_end = set()
    waiting, fast, operation_failures = defaultdict(list), defaultdict(list), defaultdict(list)
    latest_stop = {}
    for e in timed:
        fac, kind, at = e.get('f'), e.get('e'), time_of(e)
        if fac:
            per_faction[fac]  # include observed factions even before they issue orders
        military = str(e.get('type', '')).startswith('Military')
        if kind == 'order' and military:
            per_faction[fac]['order_attempts'] += 1
        if kind == 'end' and military:
            identity = ('id', e['oid']) if number(e.get('oid')) else (
                'legacy', fac, target_key(e.get('tgt')), e.get('sa'), round(at, 1))
            if identity not in seen_end:
                seen_end.add(identity)
                per_faction[fac]['end_' + str(e.get('why'))] += 1
        if kind == 'odead':
            per_faction[fac]['removal_rows'] += 1  # includes expiring temporary armies; not confirmed kills
        if kind == 'hunt' and e.get('act') == 'start' and e.get('ok') in (True, 'true'):
            per_faction[fac]['hunt_starts'] += 1
        if kind == 'opcast':
            per_faction[fac]['operation_casts'] += 1
        if kind == 'opfail':
            operation_failures[(fac, e.get('op'), e.get('r'))].append(e)
        order_key = (fac, str(e.get('type', '')).split('(')[0], target_key(e.get('tgt')), e.get('sa'))
        if kind == 'stop' and e.get('why') == 'Cancel':
            latest_stop[order_key] = at
            if e.get('ph') == 1:
                waiting[order_key].append(e)
        elif kind == 'order' and order_key in latest_stop:
            if 0 <= at - latest_stop.pop(order_key) <= 2:
                fast[order_key].append(e)
    for key, rows in waiting.items():
        if len(rows) >= 20:
            finding('waiting_cancel', 'warning', rows, f'{key[1]} repeatedly cancelled in Waiting at {label(rows[0].get("tgt"))}', key[0])
    for key, rows in fast.items():
        if len(rows) >= 10:
            finding('order_churn', 'warning', rows, f'{key[1]} cancelled and reissued on the same target within 2 seconds', key[0])
    for (fac, op, reason), rows in operation_failures.items():
        if len(rows) >= 3:
            from aireport import _ereason
            finding('operation_refused', 'warning', rows, f'{op} repeatedly refused, reason {_ereason(reason)}', fac)

    # Command conflict detection is exact only with stable actor IDs. Legacy
    # position snapshots are deliberately not merged into guessed army tracks.
    actors = defaultdict(deque)
    conflicts = defaultdict(list)
    command_sources = Counter()
    for e in timed:
        if e.get('e') != 'dact':
            continue
        command_sources[(e.get('f'), e.get('src') or 'vanilla micro')] += 1
        actor = e.get('a')
        if not isinstance(actor, dict) or not number(actor.get('id')):
            continue
        key, at = (e.get('f'), actor['id']), time_of(e)
        recent = actors[key]
        while recent and at - time_of(recent[0]) > 0.5:
            recent.popleft()
        if any({old.get('k'), e.get('k')} == {'Move', 'ArmyFight'} for old in recent):
            conflicts[key].append(e)
        recent.append(e)
    for (fac, uid), rows in conflicts.items():
        if len(rows) >= 3:
            finding('command_conflict', 'warning', rows, f'army #{int(uid)} receives Move and ArmyFight within 0.5 seconds', fac)

    campaigns = {}
    for e in timed:
        if e.get('e') != 'bcamp' or not isinstance(e.get('tgt'), dict) or not number(e.get('hp')):
            continue
        key, at = target_key(e['tgt']), time_of(e)
        c = campaigns.setdefault(key, {'target': label(e['tgt']), 'owner': e['tgt'].get('o'), 'first_hp': None,
                                       'last_hp': None, 'min_hp': None, 'go_windows': [], 'active': None})
        hp = e.get('hp')
        if number(hp):
            if c['first_hp'] is None:
                c['first_hp'] = hp
            c['last_hp'] = hp
            c['min_hp'] = min(c['min_hp'], hp) if c['min_hp'] is not None else hp
        if e.get('act') == 'phase' and e.get('to') == 2 and c['active'] is None:
            c['active'] = {'start_game_s': at, 'end_game_s': None, 'start_hp': hp, 'min_hp': hp,
                           'start_line': e.get('_line'), 'end_line': None}
            c['go_windows'].append(c['active'])
        if c['active'] is not None:
            if number(hp):
                previous = c['active']['min_hp']
                c['active']['min_hp'] = min(previous, hp) if number(previous) else hp
            if e.get('act') == 'phase' and e.get('to') != 2:
                c['active']['end_game_s'] = at
                c['active']['end_line'] = e.get('_line')
                c['active'] = None
    for c in campaigns.values():
        c.pop('active')
        for window in c['go_windows']:
            window['damage_percentage_points'] = (max(0, window['start_hp'] - window['min_hp'])
                if number(window['start_hp']) and number(window['min_hp']) else None)
            if (window['end_game_s'] is not None
                    and window['end_game_s'] - window['start_game_s'] >= LOW_DAMAGE_MIN_S
                    and number(window['damage_percentage_points'])
                    and window['damage_percentage_points'] <= LOW_DAMAGE_MAX_PP):
                row = {'g': window['end_game_s'], '_line': window['end_line']}
                entry = finding('base_low_damage', 'warning', [row],
                                f'{c["target"]}: sustained attack ended with only '
                                f'{window["damage_percentage_points"]} percentage points of observed base damage')
                entry['first_game_s'] = window['start_game_s']
                entry['source_lines'] = [line for line in (window['start_line'], window['end_line']) if line is not None]
    micro = [e for e in valid_selected if e.get('e') == 'micro']
    actors = [e for e in valid_selected if e.get('e') == 'dact']
    actor_ids = sum(isinstance(e.get('a'), dict) and logdata.identity(e['a'].get('id')) for e in actors)
    order_rows = [e for e in valid_selected if e.get('e') in ('order', 'end', 'phase', 'stop')]
    order_ids = sum(logdata.identity(e.get('oid')) for e in order_rows)
    correlation = ('unavailable' if not order_rows else 'ids' if order_ids == len(order_rows)
                   else 'mixed ids/legacy heuristic' if order_ids else 'legacy target/time heuristic')
    findings.sort(key=lambda f: (f['severity'] != 'error', -f['count']))
    return {'schema_version': 2, 'scope': {'faction': faction, 'events': sorted(event_kinds) if event_kinds else None,
                                         'entity': entity, 'order': order},
            'coverage': {'input_events': len(events), 'selected_events': len(selected), 'first_game_s': start,
                         'last_game_s': end, 'parse': dict(quality),
                         'micro_observation': 'changes' if micro and all(e.get('mode') == 'changes' for e in micro) else 'legacy/all/unknown',
                         'stable_actor_ids': actor_ids == len(actors) and bool(actors),
                         'actor_ids': {'available': actor_ids, 'total': len(actors)},
                         'order_correlation': correlation, 'order_ids': {'available': order_ids, 'total': len(order_rows)},
                         'validation': logdata.audit(events), 'missing_game_clocks': len(missing_game_clock)},
            'event_counts': dict(counts), 'event_bytes': dict(byte_counts),
            'factions': [{'name': f, **dict(c), 'end_reasons': {k[4:]: n for k, n in c.items() if k.startswith('end_')}}
                         for f, c in sorted(per_faction.items(), key=lambda pair: str(pair[0]))],
            'campaigns': list(campaigns.values()), 'findings': findings,
            'ai_control_observed': bool(controls), 'ai_off_windows': control_windows,
            'command_sources': [{'faction': f, 'source': s, 'attempts': n} for (f, s), n in command_sources.most_common()]}


def failed_validation(report):
    if report.get('multiple_sessions'):
        return any(failed_validation(child) for child in report['sessions'])
    c = report['coverage']
    return bool(c['parse'].get('failed', 0) or c['parse'].get('salvaged', 0)
                or c['validation']['invalid_events'] or c['missing_game_clocks']
                or any(f['severity'] == 'error' for f in report['findings']))


def format_feedback(report, limit=8):
    if report.get('multiple_sessions'):
        out = ['# Multiple log sessions detected; match-local IDs are analyzed separately.']
        for child in report['sessions'][:4]:
            out.append(f'\nSession {child["session"]}')
            out.append(format_feedback(child, limit=3))
        if len(report['sessions']) > 4:
            out.append('Further sessions are in --json; use --session N to inspect one.')
        return '\n'.join(out)
    c = report['coverage']
    out = [f'# AI feedback: {c["selected_events"]:,} events, {clock(c["first_game_s"])}-{clock(c["last_game_s"])}',
           f'Coverage: parse {c["parse"]}; core contracts {c["validation"]["checked_events"]}/{c["input_events"]} checked; '
           f'invalid={c["validation"]["invalid_events"]}; micro={c["micro_observation"]}',
           f'Identity: orders {c["order_ids"]["available"]}/{c["order_ids"]["total"]} ({c["order_correlation"]}); '
           f'actors {c["actor_ids"]["available"]}/{c["actor_ids"]["total"]}']
    if any(report['scope'].values()):
        out.append(f'Scope: {report["scope"]}')
    if not c['selected_events']:
        out.append('No matching AIMOD events. Check the testbed and selected filters.')
        return '\n'.join(out)
    findings = report['findings']
    shown = [f for f in findings if f['severity'] == 'error']
    shown += [f for f in findings if f['severity'] != 'error'][:limit]
    out.append('\nFindings:')
    if not findings:
        out.append('  No configured failure patterns detected. This is not a verdict on AI quality.')
    for f in shown:
        where = f'{f["faction"]} ' if f['faction'] else ''
        around = f' | --around {clock(f["first_game_s"])}' if f['first_game_s'] is not None else ''
        out.append(f'  {f["severity"].upper()} {where}{f["message"]} x{f["count"]} '
                   f'[{clock(f["first_game_s"])}-{clock(f["last_game_s"])}; lines {f["source_lines"]}]{around}')
    if len(shown) < len(findings):
        out.append(f'  {len(findings) - len(shown)} more groups in --json.')
    out.append('\nOutcomes: orders=attempts; ends=Success/Cancel/Fail/Other; removals include expired temporaries')
    for f in report['factions']:
        other = sum(n for reason, n in f['end_reasons'].items() if reason not in ('Success', 'Cancel', 'Fail'))
        out.append(f'  {f["name"]}: orders {f.get("order_attempts", 0)}, ends '
                   f'{f.get("end_Success", 0)}/{f.get("end_Cancel", 0)}/{f.get("end_Fail", 0)}/{other}, '
                   f'removals {f.get("removal_rows", 0)}, hunts {f.get("hunt_starts", 0)}, ops {f.get("operation_casts", 0)}')
    for campaign in report['campaigns']:
        out.append(f'\nCampaign {campaign["target"]}: HP {campaign["first_hp"]}->{campaign["last_hp"]}%, '
                   f'min {campaign["min_hp"]}%, {len(campaign["go_windows"])} observed attack windows')
        for window in campaign['go_windows'][-4:]:
            end = clock(window['end_game_s']) if window['end_game_s'] is not None else 'open at log end'
            out.append(f'  {clock(window["start_game_s"])}-{end}: damage {window["damage_percentage_points"]} percentage points')
    out.append('\nCommand attempts by source:')
    for row in report['command_sources'][:6]:
        out.append(f'  {row["faction"]}: {row["source"]} {row["attempts"]}')
    if not c['stable_actor_ids']:
        out.append(f'  Actor IDs {c["actor_ids"]["available"]}/{c["actor_ids"]["total"]}: '
                   'per-army command conflicts cannot be established for unidentified records.')
    top = sorted(report['event_bytes'].items(), key=lambda item: -item[1])[:4]
    out.append('\nLargest log contributors: ' + ', '.join(f'{kind} {size / 1e6:.2f} MB' for kind, size in top))
    out.append('Inspect with --around MM:SS --event KIND, --details, --score or --raw; --json includes every finding.')
    out.append('Pattern findings are not a verdict on AI quality.')
    return '\n'.join(out)
