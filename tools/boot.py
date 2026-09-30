"""HashLink bytecode (hlboot*.dat) inspection and patching via crashlink.

Patches locate code by function name + expected instruction pattern (never raw offsets),
then re-serialize, re-parse and confirm only the intended bytes changed.
"""
from crashlink import Bytecode


def load(path):
    return Bytecode.from_path(str(path))


def func_by_name(code, name):
    hits = [f for f in code.functions if _name(code, f) == name]
    if len(hits) != 1:
        raise ValueError(f'expected one function {name}, found {len(hits)}')
    return hits[0]


def _name(code, f):
    try:
        return code.full_func_name(f)
    except Exception:
        return '<none>'


def field_name(code, func, reg, index):
    t = code.types[func.regs[reg].value]
    return t.definition.fields[index].name.resolve(code)


def _admin_always_on(code):
    """Main.initPrefs forces `prefs.isAdmin = false` after loading prefs. Make it `true`.

    Admin unlocks the dev console command set and the hotkey macros (Menu/Game.adminKeys).
    """
    f = func_by_name(code, '$Main.initPrefs')
    load_fn = func_by_name(code, 'hxd.$Save.load').findex.value
    ops = f.ops
    start = next(i for i, op in enumerate(ops) if op.df.get('fun') is not None and op.df['fun'].value == load_fn)
    for i in range(start, len(ops) - 1):
        a, b = ops[i], ops[i + 1]
        if (a.op == 'Bool' and b.op == 'SetField' and b.df['src'].value == a.df['dst'].value
                and field_name(code, f, b.df['obj'].value, b.df['field'].value) == 'isAdmin'):
            state = a.df['value'].value
            return a.df['value'], state
    raise ValueError('isAdmin reset not found in Main.initPrefs')


# Value flips: id -> (locator returning (slot, current), original value, patched value)
FLIPS = {
    'admin-always-on': (_admin_always_on, False, True),
}


def _ai_log(code):
    import json
    from pathlib import Path
    import inject
    cfg = json.loads((Path(__file__).resolve().parents[1] / 'testbed' / 'ailog.json').read_text())
    return inject.apply(code, cfg.get('trace', []), cfg.get('trace_per_caller', []))


# Structural patches: id -> fn(code) -> report dict (must raise if anything isn't found)
STRUCTURAL = {
    'ai-log': _ai_log,
}


def apply(raw_path, patch_ids):
    """Return (patched bytes, report). Raises unless every patch finds its expected original state."""
    code = load(raw_path)
    n_funcs = len(code.functions)
    report = {}
    for pid in patch_ids:
        if pid in FLIPS:
            locate, before, after = FLIPS[pid]
            slot, current = locate(code)
            if current != before:
                raise ValueError(f'{pid}: expected original value {before}, found {current}')
            slot.value = after
            report[pid] = 'flipped'
        else:
            report[pid] = STRUCTURAL[pid](code)
    out = code.serialise()
    check = Bytecode.from_bytes(out)  # must re-parse
    for pid in patch_ids:
        if pid in FLIPS and FLIPS[pid][0](check)[1] != FLIPS[pid][2]:
            raise ValueError(f'{pid}: not present after re-parse')
    if 'ai-log' in patch_ids and len(check.functions) <= n_funcs:
        raise ValueError('ai-log: no functions added')
    if not [p for p in patch_ids if p not in FLIPS]:
        original = open(raw_path, 'rb').read()
        changed = sum(x != y for x, y in zip(original, out)) + abs(len(original) - len(out))
        if changed != len(patch_ids):
            raise ValueError(f'unexpected diff size: {changed} bytes')
    return out, report


def decompile(code, findex):
    from crashlink import decomp
    from crashlink.pseudo import pseudo
    f = next((f for f in code.functions if f.findex.value == findex), None)
    if f is None:
        raise ValueError(f'no function f@{findex}')
    return pseudo(decomp.IRFunction(code, f))


def disasm(code, findex):
    from crashlink.disasm import func as dfunc
    f = next(f for f in code.functions if f.findex.value == findex)
    return dfunc(code, f)
