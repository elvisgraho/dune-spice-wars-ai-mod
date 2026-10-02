"""Offline lint of the appended (testbed) functions: register-kind mismatches and trap leaks.

Usage: .venv\\Scripts\\python.exe tools\\bcheck.py  (from ai-mod; ~1 min, builds hlboot.dat in memory from backup/)

- kinds: Mov / arithmetic / compares / call args and results / Ret / Field / SetField / constants with registers of
  different kinds (int, float, bool, pointer). A float result stored in a pointer register (a Python variable reused
  for two values) runs but reads garbage. Known harmless: Bool / Mov between bool and Null<Bool> (far-annex,
  harvester run: in-game fine).
- traps: a Ret or jump leaving a try_() block without its EndTrap leaves the trap installed (REVERSING "Traps").
Not a load test: the JIT can still reject what this passes; only a Steam launch proves a build loads."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot  # noqa: E402

JUMPS = {'JTrue', 'JFalse', 'JNull', 'JNotNull', 'JSLt', 'JSGte', 'JSGt', 'JSLte', 'JULt', 'JUGte', 'JNotLt',
         'JNotGte', 'JEq', 'JNotEq', 'JAlways'}


def main():
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
    print('\n'.join(issues))
    print(f'{len(code.functions) - n0} appended functions, {len(issues)} issues')


if __name__ == '__main__':
    main()
