"""Offline testbed build of both boot files: sha256 of each (a pure refactor must not change them).

Usage: .venv\\Scripts\\python.exe tools\\bhash.py  (from ai-mod; builds from backup/, writes nothing)"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot  # noqa: E402

for name in ('hlboot.dat', 'hlbootdx.dat'):
    out, _ = boot.apply(Path(__file__).resolve().parents[1] / 'backup' / name, ['admin-always-on', 'ai-log'])
    print(name, hashlib.sha256(out).hexdigest(), len(out))
