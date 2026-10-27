r"""Manifest safety checks. Run: .venv\Scripts\python.exe -m unittest discover -s tools -p test_bhash.py"""
import contextlib
import io
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import bhash


@contextlib.contextmanager
def manifest_file():
    # mkdir's default permissions work with Windows restricted process tokens.
    folder = Path(tempfile.gettempdir()) / f'bhash-{uuid.uuid4().hex}'
    folder.mkdir()
    manifest = folder / 'before.json'
    try:
        yield manifest
    finally:
        manifest.unlink(missing_ok=True)
        folder.rmdir()


class HashManifestTests(unittest.TestCase):
    def run_command(self, *args):
        with patch('sys.argv', ['bhash.py', *map(str, args)]), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return bhash.main()

    def test_round_trip_and_change_in_either_boot(self):
        with manifest_file() as manifest:
            with patch.object(bhash.boot, 'apply', side_effect=lambda path, _: (path.name.encode(), {})):
                self.assertEqual(self.run_command('--save', manifest), 0)
                baseline = json.loads(manifest.read_text(encoding='utf-8'))
                self.assertEqual(set(baseline), set(bhash.BOOT_NAMES))
                self.assertEqual(self.run_command('--check', manifest), 0)
            for changed in bhash.BOOT_NAMES:
                with self.subTest(boot=changed), patch.object(
                    bhash.boot, 'apply', side_effect=lambda path, _: (
                        path.name.encode() + (b'changed' if path.name == changed else b''), {}
                    )
                ):
                    self.assertEqual(self.run_command('--check', manifest), 1)
                    self.assertEqual(json.loads(manifest.read_text(encoding='utf-8')), baseline)

    def test_existing_baseline_is_never_overwritten(self):
        with manifest_file() as manifest:
            manifest.write_text('keep me', encoding='utf-8')
            with patch.object(bhash.boot, 'apply') as build:
                with self.assertRaises(SystemExit) as error:
                    self.run_command('--save', manifest)
                self.assertEqual(error.exception.code, 2)
                build.assert_not_called()
            self.assertEqual(manifest.read_text(encoding='utf-8'), 'keep me')

    def test_incomplete_baseline_is_rejected_before_building(self):
        with manifest_file() as manifest:
            manifest.write_text('{}', encoding='utf-8')
            with patch.object(bhash.boot, 'apply') as build:
                with self.assertRaises(SystemExit) as error:
                    self.run_command('--check', manifest)
                self.assertEqual(error.exception.code, 2)
                build.assert_not_called()


if __name__ == '__main__':
    unittest.main()
