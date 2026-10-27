"""Execute bounded sections of emitted campaign bytecode with explicit engine fixtures."""
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boot
from inject import FB
from rules import common


class Obj(dict):
    __hash__ = object.__hash__
    __eq__ = object.__eq__
    __ne__ = object.__ne__


class Probe:
    def __init__(self):
        self.frames = {}
        wanted = {'_emit_numbers', '_emit_phase', '_emit_member', '_emit_muster', '_emit_go', '_emit_raze',
                  'build_bk_campaign', 'build_forecast', 'build_worm_release'}

        def capture(frame, event, arg):
            if event == 'return' and frame.f_code.co_name in wanted:
                self.frames[frame.f_code.co_name] = dict(frame.f_locals)

        self.code = boot.load(Path(__file__).resolve().parents[1] / 'backup' /
                              os.environ.get('AIMOD_TEST_BOOT', 'hlboot.dat'))
        sys.setprofile(capture)
        try:
            boot._ai_log(self.code)
        finally:
            sys.setprofile(None)
        self.names = {f.findex.value: boot._name(self.code, f) for f in self.code.functions}
        self.maps = {i: {} for code, i in common.GLOBALS.values() if code is self.code}
        self.map_ids = {n: i for n, (code, i) in common.GLOBALS.items() if code is self.code}
        self.calls = []
        self.handlers = {}

    def setup(self, section, **values):
        self.frame = self.frames[section]
        self.fb = self.frame['fb']
        self.regs = {}
        for name, value in values.items():
            self.regs[self.frame[name]] = value
        self.calls = []
        return self

    def field_name(self, reg, index):
        return self.code.types[self.fb.regs[reg]].definition.resolve_fields(self.code)[index].name.resolve(self.code)

    def call(self, fid, args):
        name = self.names.get(fid, str(fid))
        self.calls.append((name, args))
        if fid in self.handlers:
            return self.handlers[fid](*args)
        if name.endswith('ObjectMap.get'):
            return args[0].get(args[1])
        if name.endswith('ObjectMap.set'):
            args[0][args[1]] = args[2]
            return None
        if name.endswith('ObjectMap.remove'):
            return args[0].pop(args[1], None) is not None
        if name.endswith('ObjectMap.clear'):
            return args[0].clear()
        if name.endswith('ArrayObj.getDyn'):
            return args[0][args[1]]
        if name.endswith('ArrayObj.contains'):
            return args[1] in args[0]
        if name.endswith('ArrayObj.push'):
            return args[0].append(args[1])
        if name.endswith('getDistTo'):
            return math.hypot(args[0].get('posx', 0)-args[1].get('posx', 0),
                              args[0].get('posy', 0)-args[1].get('posy', 0))
        if name.endswith('isDead') or name.endswith('isTransported') or name.endswith('isFighting'):
            return args[0].get(name.split('.')[-1], False)
        if name.endswith('get_lifeRatio'):
            return args[0].get('life', 1)
        if name.endswith('get_maxSupply'):
            return args[0].get('maxSupply', 100)
        if name.endswith('get_supply'):
            return args[0].get('supply', 100)
        if name.endswith('get_owner'):
            return args[0].get('owner')
        if name.endswith('isFlying'):
            return args[0].get('flying', False)
        if name.endswith('get_zone'):
            return args[0].get('zone')
        if name.endswith('getOccupierFaction'):
            return args[0].get('occupier')
        if name.endswith('isDeepDesert'):
            return args[0].get('desert', False)
        if name.endswith('isVisibleForFaction'):
            return args[0].get('visible', True)
        if name.endswith('areAtWar'):
            return frozenset(args[1:]) in self.wars
        for key in ('pw', 'free'):
            if fid == self.frame.get(key):
                return args[0].get('power', 100000) if key == 'pw' else args[0].get('free', True)
        if fid == self.frame.get('helpers', {}).get('claim'):
            return args[0].get('claim_ok', True)
        if name.endswith('sqrt'):
            return math.sqrt(args[0])
        raise AssertionError(f'unsupported call {name} {args}')

    def run(self, start, stops, limit=10000, before_op=None):
        pc = self.fb.labels[start] if isinstance(start, str) else start
        stop_at = {self.fb.labels[s] if isinstance(s, str) else s: s for s in stops}
        for _ in range(limit):
            if pc in stop_at:
                return stop_at[pc]
            op = self.fb.ops[pc]
            if op.op == before_op:
                return before_op
            d = {k: v.value for k, v in op.df.items()}
            name = op.op
            jump = False
            r = self.regs
            if name in ('Label', 'EndTrap'):
                pass
            elif name in ('Mov', 'SafeCast', 'UnsafeCast', 'ToDyn', 'ToSFloat', 'ToVirtual'):
                r[d['dst']] = r[d['src']]
            elif name == 'Int':
                r[d['dst']] = self.code.ints[d['ptr']].value
            elif name == 'Bool':
                r[d['dst']] = d['value']
            elif name == 'Null':
                r[d['dst']] = None
            elif name == 'GetGlobal':
                r[d['dst']] = self.maps[d['global']]
            elif name == 'SetGlobal':
                self.maps[d['global']] = r[d['src']]
            elif name == 'Field':
                obj = r[d['obj']]
                field = self.field_name(d['obj'], d['field'])
                r[d['dst']] = len(obj) if field == 'length' else obj.get(field)
            elif name == 'DynGet':
                r[d['dst']] = r[d['obj']].get(self.code.strings.value[d['field']])
            elif name == 'Incr':
                r[d['dst']] += 1
            elif name in ('Add', 'Sub', 'Mul', 'SDiv'):
                a, b = r[d['a']], r[d['b']]
                r[d['dst']] = {'Add': lambda: a+b, 'Sub': lambda: a-b,
                               'Mul': lambda: a*b, 'SDiv': lambda: a/b}[name]()
            elif name in ('JNull', 'JNotNull'):
                jump = (r[d['reg']] is None) == (name == 'JNull')
            elif name in ('JTrue', 'JFalse'):
                jump = bool(r[d['cond']]) == (name == 'JTrue')
            elif name in ('JEq', 'JNotEq', 'JSLt', 'JSLte', 'JSGt', 'JSGte'):
                a, b = r[d['a']], r[d['b']]
                jump = {'JEq': lambda: a == b, 'JNotEq': lambda: a != b, 'JSLt': lambda: a < b,
                        'JSLte': lambda: a <= b, 'JSGt': lambda: a > b, 'JSGte': lambda: a >= b}[name]()
            elif name == 'JAlways':
                jump = True
            elif name.startswith('Call'):
                argv = [x.value for x in d['args']] if name == 'CallN' else [d[f'arg{i}'] for i in range(int(name[4:]))]
                r[d['dst']] = self.call(d['fun'], [r[i] for i in argv])
            else:
                raise AssertionError(f'unsupported opcode {name} at {pc}')
            pc += 1 + d['offset'] if jump else 1
        raise AssertionError('probe exceeded step limit')


if __name__ == '__main__':
    p = Probe()
    for section, frame in p.frames.items():
        print(section, sorted(k for k, v in frame.items() if isinstance(v, int)))
