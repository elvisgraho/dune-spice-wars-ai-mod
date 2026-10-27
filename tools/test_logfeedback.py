"""Regression cases from real logs: enum points, duplicate callbacks and misleading health."""
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

import aireport
import logarchive
import logfeedback
import mod
import scorecard


@contextlib.contextmanager
def folder():
    path = Path(tempfile.gettempdir()) / f'aimod-log-test-{uuid.uuid4().hex}'
    path.mkdir()
    try:
        yield path
    finally:
        for child in path.iterdir():
            child.unlink()
        path.rmdir()


def event(kind, time=0, **fields):
    if kind == 'snap':
        fields = {'armies': 0, 'structs': 1, **fields}
    return {'e': kind, 'g': time, 'f': 'Fremen', **fields}


class ParserTests(unittest.TestCase):
    def test_nested_enum_points_and_old_fight_map_keep_following_fields(self):
        lines = ['game header', 'AIMOD {e : micro, f : Fremen, from : [ent.Army => Idle, '
                 'ent.Army => Flee({556.4,910},[])], to : Flee({556.4,910},[]), n : 2, g : 78.6}']
        e = aireport.parse_lines(lines)[0]
        self.assertEqual((e['_parse'], e['_line'], e['n'], e['g']), ('full', 2, 2, 78.6))
        self.assertEqual(e['to'], 'Flee({556.4,910},[])')

    def test_damaged_rows_are_visible_and_keep_source_lines(self):
        e = aireport.parse_lines(['AIMOD {e : broken, x : [{'])[0]
        self.assertEqual(e['_parse'], 'failed')
        self.assertEqual(e['_line'], 1)
        self.assertIn('_raw', e)

    def test_invalid_faction_does_not_crash_analysis(self):
        events = aireport.parse_lines(['AIMOD {e : order, f : {bad : x}, g : 1}'])
        self.assertEqual(events[0]['_parse'], 'failed')
        self.assertTrue(logfeedback.analyze(events)['findings'])

    def test_integer_game_clock_is_not_replaced_by_app_time(self):
        self.assertEqual(aireport.when({'g': 0, 't': 100}, 10), 0)

    def test_timeline_hides_parser_metadata_and_handles_empty_filters(self):
        rows = aireport.parse_lines(['AIMOD {e : fpw, f : Fremen, g : 10, b : 2}'])
        text = aireport.around(rows, 10, include_noisy=True)
        self.assertIn('fpw', text)
        self.assertNotIn('_parse', text)
        self.assertNotIn('_bytes', text)
        self.assertIn('No AIMOD', aireport.around([], 10))
        self.assertIn('#77', aireport.short(event('dact', a={'id': 77, 'k': 'F_Elite'})))


class FeedbackTests(unittest.TestCase):
    def test_ai_disabled_windows_are_not_silently_dropped(self):
        rows = [event('call', 0, fn='Faction.set_isAI', r=False), event('snap', 50)]
        report = logfeedback.analyze(rows)
        self.assertEqual(report['findings'][0]['kind'], 'ai_off')
        rows.append(event('call', 51, fn='Faction.set_isAI', r=True))
        self.assertEqual(logfeedback.analyze(rows)['ai_off_windows'][0]['end_game_s'], 51)
    def test_reports_use_order_identity_for_overlapping_orders_on_one_target(self):
        target = {'id': 7, 'p': 'v'}
        rows = [event('order', 1, oid=1, type='Military', sa='Annex', n=4, tgt=target),
                event('order', 2, oid=2, type='Military', sa='Annex', n=3, tgt=target),
                event('end', 3, oid=2, type='Military', sa='Annex', n=3, tgt=target, why='Success'),
                event('end', 4, oid=2, type='Military', sa='Annex', n=3, tgt=target, why='Success'),
                event('end', 5, oid=1, type='Military', sa='Annex', n=4, tgt=target, why='Cancel')]
        text = aireport.summarize(rows)
        first = next(line for line in text.splitlines() if line.startswith('!00:01'))
        second = next(line for line in text.splitlines() if line.startswith(' 00:02'))
        self.assertIn('Cancel+4s', first)
        self.assertIn('Success+1s', second)
        text = scorecard.scorecard([event('snap'), *rows])
        self.assertIn('Annex 2: ok 1 cancel 1', text)

    def test_order_ids_deduplicate_callbacks_without_merging_distinct_orders(self):
        events = [event('end', 10, oid=1, type='Military', why='Success'),
                  event('end', 11, oid=1, type='Military', why='Success'),
                  event('end', 11, oid=2, type='Military', why='Success')]
        self.assertEqual(logfeedback.analyze(events)['factions'][0]['end_Success'], 2)

    def test_parser_warnings_are_not_hidden_by_a_faction_filter(self):
        events = [event('snap'), {'e': 'unparsed', '_parse': 'failed', '_line': 9}]
        report = logfeedback.analyze(events, faction='Fremen')
        self.assertEqual(report['coverage']['selected_events'], 1)
        self.assertEqual(report['findings'][0]['source_lines'], [9])

    def test_rule_failure_uses_only_the_supplied_build_map(self):
        report = logfeedback.analyze([event('rfail', 12, r='hunt', at=0)], crumbs=['running.py:55'])
        self.assertEqual(report['findings'][0]['message'], 'hunt: running.py:55')
        self.assertEqual(report['findings'][0]['severity'], 'error')

    def test_campaign_ignores_field_targets_and_tracks_damage_per_attack(self):
        base = {'id': 1, 'k': 'Arrakeen', 'o': 'Atreides'}
        events = [event('bcamp', 0, act='phase', to=2, hp=100, tgt=base),
                  event('bcamp', 1, act='phase', to=2, hp=98, tgt=base),
                  event('bcamp', 2, act='field', tgt={'id': 9, 'k': 'A_Trooper'}),
                  event('bcamp', 10, act='direct', hp=80, tgt=base),
                  event('bcamp', 20, act='phase', to=3, hp=80, tgt=base)]
        campaigns = logfeedback.analyze(events)['campaigns']
        self.assertEqual(len(campaigns), 1)
        self.assertEqual(len(campaigns[0]['go_windows']), 1)
        self.assertEqual(campaigns[0]['go_windows'][0]['damage_percentage_points'], 20)

    def test_command_conflicts_require_stable_ids(self):
        rows = [event('dact', t, k=k, a={'id': 77}) for t, k in
                ((0, 'Move'), (0.1, 'ArmyFight'), (0.2, 'Move'), (0.3, 'ArmyFight'))]
        self.assertTrue(any(f['kind'] == 'command_conflict' for f in logfeedback.analyze(rows)['findings']))
        for e in rows:
            e['a'] = {'k': 'F_Elite', 'x': 100, 'y': 100}
        self.assertFalse(logfeedback.analyze(rows)['findings'])

    def test_completed_low_damage_attack_is_actionable_but_open_attack_is_not(self):
        base = {'id': 1, 'k': 'Arrakeen'}
        rows = [event('bcamp', 0, act='phase', to=2, hp=100, tgt=base),
                event('bcamp', 100, act='state', hp=100, tgt=base)]
        self.assertFalse(logfeedback.analyze(rows)['findings'])
        rows.append(event('bcamp', 120, act='phase', to=3, hp=100, tgt=base))
        finding = logfeedback.analyze(rows)['findings'][0]
        self.assertEqual(finding['kind'], 'base_low_damage')
        self.assertEqual((finding['first_game_s'], finding['last_game_s']), (0, 120))

    def test_missing_telemetry_is_not_a_claim_that_the_ai_is_good(self):
        text = logfeedback.format_feedback(logfeedback.analyze([event('snap')]))
        self.assertIn('not a verdict on AI quality', text)
        self.assertIn('cannot be established', text)


class ArchiveAndCliTests(unittest.TestCase):
    def test_full_archive_keeps_exceptions_and_freezes_the_first_source_map(self):
        with folder() as path:
            text = '1 [Game] Null access\n hxd/App.hx line 0\nAIMOD {e : rfail, r : hunt, at : 0, g : 1}\n'
            saved = logarchive.archive(text, path, {'crumbs': ['old.py:1'], 'source_map_matches_build': True})
            same = logarchive.archive(text, path, {'crumbs': ['new.py:999'], 'source_map_matches_build': True})
            self.assertEqual(saved, same)
            self.assertEqual(saved.read_text(encoding='utf-8'), text)
            self.assertEqual(logarchive.source_map(saved), ['old.py:1'])
            self.assertIn('INJECTED CODE IS FAILING', mod.health(saved))

    def test_silent_rule_failure_prevents_health_ok(self):
        with folder() as path:
            log = path / 'fixture.log'
            log.write_text('1 [Game] Started\nAIMOD {e : rfail, r : hunt, at : 2, g : 4}\n', encoding='utf-8')
            self.assertTrue(mod.health(log).startswith('HEALTH ERROR'))

    def test_json_and_exact_raw_filters_are_usable_from_the_cli(self):
        with folder() as path:
            log = path / 'fixture.log'
            log.write_text('AIMOD {e : snap, f : Fremen, g : 0}\n'
                           'AIMOD {e : dact, f : Atreides, g : 1, k : Fremen}\n', encoding='utf-8')
            command = [sys.executable, str(Path(mod.__file__)), 'log', str(log)]
            env = dict(os.environ, PYTHONIOENCODING='utf-8')
            report = json.loads(subprocess.check_output(command + ['--json'], text=True, env=env))
            self.assertEqual(report['coverage']['input_events'], 2)
            self.assertIn('unavailable', report['health'])
            filtered = json.loads(subprocess.check_output(command + ['--json', '--event', 'dact'], text=True, env=env))
            self.assertEqual(filtered['coverage']['input_events'], 2)
            self.assertEqual(filtered['coverage']['selected_events'], 1)
            raw = subprocess.check_output(command + ['--raw', '--faction', 'Fremen'], text=True, env=env)
            self.assertIn('e : snap', raw)
            self.assertNotIn('e : dact', raw)


if __name__ == '__main__':
    unittest.main()
