"""Offline lint of the appended (testbed) functions: register-kind mismatches and trap leaks.

Usage: .venv\\Scripts\\python.exe tools\\bcheck.py  (from ai-mod; ~1 min, builds hlboot.dat in memory from backup/)

- kinds: Mov / arithmetic / compares / call args and results / Ret / Field / SetField / constants with registers of
  different kinds (int, float, bool, pointer). A float result stored in a pointer register (a Python variable reused
  for two values) runs but reads garbage. Known harmless: Bool / Mov between bool and Null<Bool> (far-annex,
  harvester run: in-game fine).
- traps: a Ret or jump leaving a try_() block without its EndTrap leaves the trap installed (REVERSING "Traps").
- unassigned: a register read on some path before any write (definite assignment over the control-flow graph; a
  trap handler starts from the state at its Trap). The builder pitfall: a forward jump over the code that loads a
  value leaves the register null (pointer: the rule's trap swallows the exception, the rule silently does nothing)
  or 0 (number). Reviewed findings are accepted in tools/bcheck_baseline.txt; a new one is an issue. After
  reviewing new ones: `bcheck.py --update-baseline`.
Not a load test: the JIT can still reject what this passes; only a Steam launch proves a build loads."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot  # noqa: E402
from crashlink.opcodes import opcodes  # noqa: E402
from inject import FB  # noqa: E402

BASELINE = Path(__file__).resolve().parent / 'bcheck_baseline.txt'
JUMPS = {'JTrue', 'JFalse', 'JNull', 'JNotNull', 'JSLt', 'JSGte', 'JSGt', 'JSLte', 'JULt', 'JUGte', 'JNotLt',
         'JNotGte', 'JEq', 'JNotEq', 'JAlways'}


def _flow(f, nargs, T, cls):
    """Definite-assignment check of one function: [(op index, op name, reg, kind)] for reads of registers that
    some path reaches unwritten."""
    ops = f.ops
    n = len(ops)
    R = [r.value for r in f.regs]

    def succ(i):
        op = ops[i]
        o = op.op
        d = op.df
        out = []
        if o in ('Ret', 'Throw', 'Rethrow'):
            return out
        if o in JUMPS:
            out.append(i + 1 + d['offset'].value)
            if o != 'JAlways':
                out.append(i + 1)
            return out
        if o == 'Switch':
            out.extend(i + 1 + x for x in [v.value for v in d['offsets'].value])
            out.append(i + 1)
            return out
        out.append(i + 1)
        return out

    def regs_of(op):
        spec = opcodes.get(op.op, {})
        reads, writes = [], []
        for k, kind in spec.items():
            if k not in op.df:
                continue
            v = op.df[k]
            if kind == 'Reg':
                (writes if k == 'dst' or (op.op == 'Trap' and k == 'exc') else reads).append(v.value)
                if op.op == 'Incr' and k == 'dst':
                    reads.append(v.value)
            elif kind == 'Regs':
                reads.extend(x.value for x in v.value)
        return reads, writes

    full = (1 << len(R)) - 1
    entry = (1 << nargs) - 1
    state = [None] * n
    state[0] = entry
    work = [0]
    while work:
        i = work.pop()
        if i >= n:
            continue
        cur = state[i]
        reads, writes = regs_of(ops[i])
        out = cur
        for w in writes:
            out |= 1 << w
        targets = succ(i)
        if ops[i].op == 'Trap':  # the handler: what was assigned at the Trap, plus the exception
            h = i + 1 + ops[i].df['offset'].value
            hs = cur | (1 << ops[i].df['exc'].value)
            targets = [i + 1]
            if h < n and (state[h] is None or state[h] & hs != state[h]):
                state[h] = hs if state[h] is None else state[h] & hs
                work.append(h)
        for t in targets:
            if t >= n:
                continue
            if state[t] is None:
                state[t] = out
                work.append(t)
            elif state[t] & out != state[t]:
                state[t] &= out
                work.append(t)
    bad = []
    for i, op in enumerate(ops):
        if state[i] is None:
            continue
        reads, _ = regs_of(op)
        for r in reads:
            if not state[i] >> r & 1 and cls(R[r]) != 'void':
                bad.append((i, op.op, r, cls(R[r])))
    return bad


def main():
    FB.TRACK_SRC = True
    code = boot.load(Path(__file__).resolve().parents[1] / 'backup' / 'hlboot.dat')
    n0 = len(code.functions)
    boot._ai_log(code)
    T = code.types

    def cls(t):
        k = T[t].kind.value
        if k in (1, 2, 3, 4):
            return f'i{k}'
        if k in (5, 6):
            return f'f{k}'
        return {7: 'bool', 0: 'void'}.get(k, 'ptr')

    funs = {f.findex.value: f for f in code.functions}
    funs.update({n.findex.value: n for n in code.natives})
    issues = []
    for f in code.functions[n0:]:
        R = [r.value for r in f.regs]
        rc = lambda r: cls(R[r])  # noqa: E731
        fret = cls(T[f.type.value].definition.ret.value)
        for i, op in enumerate(f.ops):
            d = {k: v.value for k, v in op.df.items()}
            o, msg = op.op, None
            if o == 'Mov' and rc(d['dst']) != rc(d['src']):
                msg = (rc(d['dst']), rc(d['src']))
            elif o in ('Add', 'Sub', 'Mul', 'SDiv', 'UDiv', 'SMod') and len({rc(d['dst']), rc(d['a']), rc(d['b'])}) > 1:
                msg = (rc(d['dst']), rc(d['a']), rc(d['b']))
            elif o in JUMPS and 'a' in d and rc(d['a']) != rc(d['b']):
                msg = (rc(d['a']), rc(d['b']))
            elif o in ('JNull', 'JNotNull') and rc(d['reg']) != 'ptr':
                msg = rc(d['reg'])
            elif o in ('JTrue', 'JFalse') and rc(d['cond']) != 'bool':
                msg = rc(d['cond'])
            elif o == 'ToSFloat' and not (rc(d['src'])[0] == 'i' and rc(d['dst'])[0] == 'f'):
                msg = (rc(d['dst']), rc(d['src']))
            elif o == 'ToInt' and not (rc(d['src'])[0] == 'f' and rc(d['dst'])[0] == 'i'):
                msg = (rc(d['dst']), rc(d['src']))
            elif o in ('Incr', 'Int', 'EnumIndex') and rc(d['dst'])[0] != 'i':
                msg = rc(d['dst'])
            elif o == 'Bool' and rc(d['dst']) != 'bool':
                msg = rc(d['dst'])
            elif o == 'Null' and rc(d['dst']) != 'ptr':
                msg = rc(d['dst'])
            elif o in ('Field', 'SetField'):
                fs = T[R[d['obj']]].definition.resolve_fields(code)
                want, have = cls(fs[d['field']].type.value), rc(d['dst'] if o == 'Field' else d['src'])
                if want != have:
                    msg = (have, want)
            elif o.startswith('Call') and o not in ('CallMethod', 'CallThis', 'CallClosure') and 'fun' in d:
                ft = T[funs[d['fun']].type.value].definition
                args = [x.value for x in d['args']] if 'args' in d else [d[f'arg{j}'] for j in range(int(o[4:]))]
                want = [a.value for a in ft.args]
                if len(args) != len(want):
                    msg = ('argc', len(args), len(want))
                elif any(rc(a) != cls(w) for a, w in zip(args, want)):
                    msg = ('args', [(j, rc(a), cls(w)) for j, (a, w) in enumerate(zip(args, want)) if rc(a) != cls(w)])
                elif rc(d['dst']) not in ('void', cls(ft.ret.value)):
                    msg = ('ret', rc(d['dst']), cls(ft.ret.value))
            elif o == 'Ret' and fret != 'void' and rc(d['ret']) != fret:
                msg = (rc(d['ret']), fret)
            elif o == 'Trap':
                h = i + 1 + d['offset']
                e = h - 1  # EndTrap, or EndTrap + JAlways over a logging handler (inject.FB.trap_hook)
                if f.ops[e].op == 'JAlways' and f.ops[e - 1].op == 'EndTrap':
                    e -= 1
                if f.ops[e].op != 'EndTrap':
                    msg = 'no EndTrap before handler'
                else:
                    for j in range(i + 1, e):
                        q = f.ops[j]
                        t = j + 1 + q.df['offset'].value if q.op in JUMPS else None
                        if q.op == 'Ret' or (t is not None and not i + 1 <= t <= e):
                            issues.append(f'f@{f.findex.value} op{j} {q.op} leaves trap@{i}')
            if msg:
                issues.append(f'f@{f.findex.value} op{i} {o} {msg}')
        nargs = len(T[f.type.value].definition.args)
        src, labels, srcs = FB.BUILT.get(f.findex.value, ('?', {}, []))
        for i, o, r, k in _flow(f, nargs, T, cls):
            at = srcs[i] if i < len(srcs) else '?'
            issues.append(f'f@{f.findex.value} {src} op{i} [{at}] {o} reads r{r} ({k}) unassigned on some path')
    # unassigned reads: many are guarded by a separate flag set together with the register (the builder's usual
    # `ok` / `apok` pattern), which a flow check can't see. Reviewed ones are accepted in BASELINE (key = rule, source
    # line, op, kind); only new ones count. `--update-baseline` rewrites it after a review.
    src_cache = {}

    # module name (as inject._src_mod reports it: file stem, a package's __init__ by its package name) -> file
    tools_dir = Path(__file__).resolve().parent
    mod_files = {}
    for p_ in sorted(tools_dir.glob('*.py')) + sorted((tools_dir / 'rules').rglob('*.py')):
        mod_files.setdefault(p_.parent.name if p_.stem == '__init__' else p_.stem, p_)

    def line_text(ref):  # 'mod:line' -> that line's code (line numbers shift with every edit; the code doesn't)
        mod, _, ln = ref.partition(':')
        p = mod_files.get(mod)
        if p is None:
            return ref
        lines = src_cache.setdefault(p, p.read_text(encoding='utf-8').splitlines())
        return lines[int(ln) - 1].strip() if ln.isdigit() and int(ln) <= len(lines) else ref

    def key(x):
        m = re.search(r'\[([^\]]*)\]', x)
        chain = ' <- '.join(line_text(r) for r in m.group(1).split(' <- ')) if m else ''
        return re.sub(r'f@\d+ | op\d+| reads r\d+|\[[^\]]*\]', '', x) + ' | ' + chain
    flow = [x for x in issues if 'unassigned' in x]
    other = [x for x in issues if 'unassigned' not in x]
    if '--update-baseline' in sys.argv:
        BASELINE.write_text('\n'.join(sorted({key(x) for x in flow})) + '\n', encoding='utf-8')
        print(f'baseline: {len({key(x) for x in flow})} accepted unassigned reads written to {BASELINE.name}')
    known = set(BASELINE.read_text(encoding='utf-8').splitlines()) if BASELINE.exists() else set()
    new = [x for x in flow if key(x) not in known]
    issues = other + new
    print('\n'.join(issues))
    print(f'{len(code.functions) - n0} appended functions, {len(issues)} issues ({len(flow) - len(new)} accepted '
          f'unassigned reads in {BASELINE.name})')


if __name__ == '__main__':
    main()
