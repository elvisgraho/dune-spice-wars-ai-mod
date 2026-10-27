"""Reader-boundary and evidence-integrity regressions, including reused match IDs."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import aireport
import logarchive
import logdata
import logfeedback
import mod
from test_logfeedback import event, folder


class ValidationTests(unittest.TestCase):
    def test_parse_success_does_not_mean_a_command_record_is_complete(self):
        rows = aireport.parse_lines(['AIMOD {e : dact, f : Fremen, k : Move, g : 1}'])
        self.assertEqual(rows[0]['_parse'], 'full')
        report = logfeedback.analyze(rows)
        self.assertEqual(report['coverage']['validation']['invalid_events'], 1)
        self.assertEqual(report['event_counts']['dact'], 1)
        self.assertFalse(report['command_sources'])
        self.assertTrue(logfeedback.failed_validation(report))

    def test_nonfinite_numbers_are_flagged_and_strict_json_remains_valid(self):
        rows = logdata.prepare([event('dact', float('inf'), a={'id': 77.0}, k='Move', _line=4)])
        record = logdata.export_record(rows[0], 'a' * 64)
        encoded = json.dumps(record, allow_nan=False)
        self.assertIsNone(json.loads(encoded)['event']['g'])
        self.assertIsInstance(record['event']['a']['id'], int)
        self.assertTrue(record['validation_errors'])
        self.assertEqual(record['record_id'], 'a' * 64 + ':4')

    def test_invalid_identity_cannot_create_a_false_command_conflict(self):
        rows = [event('dact', t, a={'id': 0}, k=kind) for t, kind in
                ((0, 'Move'), (0.1, 'ArmyFight'), (0.2, 'Move'), (0.3, 'ArmyFight'))]
        report = logfeedback.analyze(rows)
        self.assertEqual(report['coverage']['validation']['invalid_events'], 4)
        self.assertFalse(any(f['kind'] == 'command_conflict' for f in report['findings']))

    def test_identity_coverage_is_not_inferred_from_one_good_record(self):
        rows = [event('dact', 0, a={'id': 77}, k='Move'), event('dact', 1, a={'k': 'F_Elite'}, k='Move'),
                event('end', 2, oid=5, type='Military', why='Success'),
                event('end', 3, type='Military', why='Success')]
        c = logfeedback.analyze(rows)['coverage']
        self.assertEqual(c['actor_ids'], {'available': 1, 'total': 2})
        self.assertFalse(c['stable_actor_ids'])
        self.assertEqual(c['order_correlation'], 'mixed ids/legacy heuristic')

    def test_nullable_end_reason_is_legitimate_not_missing_data(self):
        self.assertFalse(logdata.validate(event('end', type='Military', why=None)))
        self.assertTrue(logdata.validate(event('end', type='Military')))

    def test_app_time_is_never_used_as_game_time_for_behavioral_metrics(self):
        rows = [{'e': 'dact', 't': 500, 'f': 'Fremen', 'a': {'id': 77}, 'k': 'Move'}]
        report = logfeedback.analyze(rows)
        self.assertEqual(report['coverage']['missing_game_clocks'], 1)
        self.assertIsNone(report['coverage']['first_game_s'])
        self.assertFalse(report['command_sources'])
        self.assertTrue(logfeedback.failed_validation(report))

    def test_unusual_end_reasons_remain_visible(self):
        report = logfeedback.analyze([event('end', oid=1, type='Military', why=None)])
        self.assertEqual(report['factions'][0]['end_reasons'], {'None': 1})
        self.assertIn('0/0/0/1', logfeedback.format_feedback(report))


class SessionTests(unittest.TestCase):
    def test_reused_order_ids_in_concatenated_matches_are_kept_separate(self):
        rows = [event('order', 5, oid=1, type='Military'), event('end', 20, oid=1, type='Military', why='Success'),
                event('order', 0, oid=1, type='Military'), event('end', 10, oid=1, type='Military', why='Cancel')]
        report = logfeedback.analyze(rows)
        self.assertTrue(report['multiple_sessions'])
        self.assertEqual(len(report['sessions']), 2)
        self.assertEqual(report['sessions'][0]['factions'][0]['end_Success'], 1)
        self.assertEqual(report['sessions'][1]['factions'][0]['end_Cancel'], 1)
        self.assertIn('analyzed separately', logfeedback.format_feedback(report))
        self.assertEqual(logfeedback.analyze(rows, session=2)['session'], 2)

    def test_tiny_clock_reordering_is_not_a_new_session_but_app_restart_is(self):
        rows = logdata.prepare([event('x', 20, t=10), event('x', 19.9, t=10.1), event('x', 20, t=0)])
        self.assertEqual([e['_session'] for e in rows], [1, 1, 2])

    def test_recursive_entity_filter_and_order_filter_have_distinct_meanings(self):
        e = logdata.prepare([event('aw', a=[{'id': 77}], n=1, oid=88)])[0]
        self.assertTrue(logdata.matches(e, entity=77))
        self.assertFalse(logdata.matches(e, entity=88))
        self.assertTrue(logdata.matches(e, order=88))


class IntegrityTests(unittest.TestCase):
    def test_raw_bytes_are_preserved_and_tampering_with_log_invalidates_map(self):
        with folder() as path:
            raw = b'header\r\nAIMOD {e : x, g : 1}\r\n\xff'
            log = logarchive.archive(raw, path, {'crumbs': ['old.py:7'], 'source_map_matches_build': True})
            self.assertEqual(log.read_bytes(), raw)
            self.assertEqual(logarchive.inspect_archive(log)['status'], 'verified')
            log.write_bytes(raw + b'changed')
            self.assertEqual(logarchive.inspect_archive(log)['status'], 'mismatch')
            self.assertIsNone(logarchive.source_map(log))

    def test_changed_or_swapped_sidecar_is_not_used(self):
        with folder() as path:
            log = logarchive.archive('one', path, {'crumbs': ['a:1'], 'source_map_matches_build': True})
            other = logarchive.archive('two', path, {'crumbs': ['b:2'], 'source_map_matches_build': True})
            log.with_suffix('.meta.json').write_bytes(other.with_suffix('.meta.json').read_bytes())
            self.assertIsNone(logarchive.source_map(log))
            data = json.loads(other.with_suffix('.meta.json').read_text())
            data['crumbs'] = ['wrong:99']
            other.with_suffix('.meta.json').write_text(json.dumps(data))
            self.assertIsNone(logarchive.source_map(other))

    def test_invalid_and_legacy_metadata_are_distinguished(self):
        with folder() as path:
            log = path / 'old.log'
            log.write_bytes(b'old')
            meta = log.with_suffix('.meta.json')
            meta.write_text('[]')
            self.assertEqual(logarchive.inspect_archive(log)['status'], 'invalid')
            meta.write_text('{"format": 2, "crumbs": ["unbound.py:1"]}')
            self.assertEqual(logarchive.inspect_archive(log)['status'], 'legacy_unbound')
            self.assertIsNone(logarchive.source_map(log))

    def test_interrupted_archive_is_not_reused_as_a_verified_archive(self):
        with folder() as path:
            write = logarchive._atomic_write

            def interrupted(target, data):
                if target.name.endswith('.meta.json'):
                    raise OSError('simulated interruption')
                write(target, data)

            with patch.object(logarchive, '_atomic_write', side_effect=interrupted):
                with self.assertRaises(OSError):
                    logarchive.archive('data', path, {})
            orphan = next(path.glob('*.log'))
            self.assertEqual(logarchive.inspect_archive(orphan)['status'], 'missing')
            recovered = logarchive.archive('data', path, {})
            self.assertNotEqual(recovered, orphan)
            self.assertEqual(logarchive.inspect_archive(recovered)['status'], 'verified')
            self.assertEqual(orphan.read_text(), 'data')


class ExportCliTests(unittest.TestCase):
    def run_cli(self, log, *args):
        return subprocess.run([sys.executable, str(Path(mod.__file__)), 'log', str(log), *args],
                              text=True, capture_output=True, env=dict(os.environ, PYTHONIOENCODING='utf-8'))

    def test_jsonl_has_source_session_line_and_integer_ids(self):
        with folder() as path:
            log = path / 'combined.log'
            raw = (b'AIMOD {e : order, f : Fremen, oid : 1, type : Military, tgt : {id : 77}, g : 5}\n'
                   b'AIMOD {e : order, f : Fremen, oid : 1, type : Military, tgt : {id : 77}, g : 0}\n')
            log.write_bytes(raw)
            result = self.run_cli(log, '--events-jsonl', '--entity', '77')
            self.assertEqual(result.returncode, 0, result.stderr)
            records = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual([r['session'] for r in records], [1, 2])
            self.assertEqual([r['line'] for r in records], [1, 2])
            self.assertEqual(records[0]['source_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertNotEqual(records[0]['record_id'], records[1]['record_id'])
            self.assertIsInstance(records[0]['event']['oid'], int)
            selected = self.run_cli(log, '--events-jsonl', '--order', '1', '--session', '2')
            self.assertEqual(len(selected.stdout.splitlines()), 1)
            self.assertNotEqual(self.run_cli(log, '--around', '00:01').returncode, 0)

    def test_strict_rejects_incomplete_data_after_printing_valid_json(self):
        with folder() as path:
            log = path / 'bad.log'
            log.write_text('AIMOD {e : dact, f : Fremen, k : Move, g : 1}\n')
            result = self.run_cli(log, '--json', '--strict')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['coverage']['validation']['invalid_events'], 1)


if __name__ == '__main__':
    unittest.main()
