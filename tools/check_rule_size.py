"""Fail when an AI rule module exceeds the repository's 1,300-line limit.

Run from ai-mod: .venv\\Scripts\\python.exe tools\\check_rule_size.py
"""
from pathlib import Path

MAX_LINES = 1300
RULES = Path(__file__).resolve().parent / 'rules'


def main():
    sizes = sorted(
        ((len(path.read_text(encoding='utf-8').splitlines()), path) for path in RULES.rglob('*.py')),
        reverse=True,
    )
    oversized = [(count, path) for count, path in sizes if count > MAX_LINES]
    for count, path in oversized:
        print(f'FAIL: {path.relative_to(RULES)} has {count} lines; limit {MAX_LINES}')
    if oversized:
        return 1
    count, path = sizes[0]
    print(f'PASS: {len(sizes)} rule modules within {MAX_LINES} lines; '
          f'largest {path.relative_to(RULES)} ({count})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
