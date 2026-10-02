"""AI decision logging injected into hlboot*.dat (patch id `ai-log`).

Technique: append new functions; redirect existing `Call` ops to them by changing only the
function index. No existing op is inserted/removed, so jump offsets never change.

Output: one line per event appended to game.log via lib.Log.fileLog:
    AIMOD {e : pick, f : Smugglers, t : 812.3, ...}
Parse with `mod log`. All ids are resolved by name, so this works on both boot files.
"""
from crashlink.core import (DebugInfo, Enum, Function, Obj, Opcode, Reg, VarInt, fileRef, fIndex, tIndex)
from crashlink.opcodes import opcodes

KIND = {'void': 0, 'i32': 3, 'f64': 6, 'bool': 7, 'bytes': 8, 'dyn': 9, 'dynobj': 16}


class Ctx:
    """Name -> id lookups for one Bytecode image."""

    def __init__(self, code):
        self.code = code
        self.funcs = {}
        for f in code.functions:
            try:
                self.funcs.setdefault(code.full_func_name(f), f)
            except Exception:
                pass
        self.objs = {}  # enums first so classes win on a name clash (an enum is also called 'String')
        for cls in (Enum, Obj):
            self.objs.update({t.definition.name.resolve(code): i for i, t in enumerate(code.types)
                              if isinstance(t.definition, cls)})
        self.kinds = {}
        for i, t in enumerate(code.types):
            self.kinds.setdefault(t.kind.value, i)

    def global_of(self, type_name):
        """Global index holding the static object of a class (found from existing GetGlobal ops)."""
        t = self.t(type_name)
        for f in self.code.functions:
            for op in f.ops:
                if op.op == 'GetGlobal' and f.regs[op.df['dst'].value].value == t:
                    return op.df['global'].value
        raise ValueError(f'no global of type {type_name}')

    def field_type(self, obj_type, name):
        return self.code.types[obj_type].definition.resolve_fields(self.code)[self.field(obj_type, name)].type.value

    def fn(self, name):
        if name not in self.funcs:
            raise ValueError(f'function not found: {name}')
        return self.funcs[name]

    def t(self, name):
        return self.kinds[KIND[name]] if name in KIND else self.objs[name]

    def field(self, obj_type, name):
        fields = self.code.types[obj_type].definition.resolve_fields(self.code)
        hits = [i for i, f in enumerate(fields) if f.name.resolve(self.code) == name]
        if len(hits) != 1:
            raise ValueError(f'field {name} not found on t@{obj_type}')
        return hits[0]

    def s(self, text):
        """String-table index (for DynGet/DynSet field names and String ops)."""
        vals = self.code.strings.value
        if text in vals:
            return vals.index(text)
        return self.code.add_string(text).value


class FB:
    """Tiny function builder. Jumps use labels resolved at build()."""

    def __init__(self, cx, arg_types, ret_type, fun_type=None):
        self.cx, self.code = cx, cx.code
        self.regs = list(arg_types)
        self.ret = ret_type
        self.fun_type = fun_type
        self.ops, self.fix, self.labels = [], [], {}
        self._nargs = len(arg_types)

    def reg(self, t):
        self.regs.append(t)
        return len(self.regs) - 1

    def op(self, name, **kw):
        o = Opcode(name, {})
        for field, typ in opcodes[name].items():
            v = Opcode.TYPE_MAP[typ]()
            if typ == 'Regs':
                v.value = [Reg(x) for x in kw[field]]
            elif typ == 'JumpOffset':
                v.value = 0
                self.fix.append((len(self.ops), field, kw[field]))
            else:
                v.value = kw[field]
            o.df[field] = v
        self.ops.append(o)

    def label(self, name):
        if name in self.labels:  # a reused name would silently retarget every jump to it
            raise ValueError(f'duplicate label {name!r}')
        self.labels[name] = len(self.ops)

    def string(self, text):
        b, n, r = self.reg(self.cx.t('bytes')), self.reg(self.cx.t('i32')), self.reg(self.cx.t('String'))
        self.op('String', dst=b, ptr=self.cx.s(text))
        self.op('Int', dst=n, ptr=self.code.add_i32(len(text.encode('utf-16-le')) // 2).value)
        self.op('Call2', dst=r, fun=self.cx.fn('$String.__alloc__').findex.value, arg0=b, arg1=n)
        return r

    def dyn(self, r):
        """Register as Dyn, the way the Haxe compiler does it: ToDyn boxes primitives only;
        pointer types (obj, virtual, dynobj, enum, Null<T>, String...) are Mov'd as-is.
        (ToDyn on a pointer wraps it in a new box: DynGet/DynSet then hit the box, not the object.)"""
        if self.regs[r] == self.cx.t('dyn'):
            return r
        d = self.reg(self.cx.t('dyn'))
        kind = self.code.types[self.regs[r]].kind.value
        self.op('ToDyn' if kind in (1, 2, 3, 4, 5, 6, 7, 8, 13, 17) else 'Mov', dst=d, src=r)
        return d

    def get(self, obj, *path):
        """Null-safe field path -> Dyn register (null if any link is null or the field is missing).
        Uses Reflect.field (returns null for unknown fields); DynGet would throw 'Invalid field access'."""
        cur = self.dyn(obj)
        for i, name in enumerate(path):
            nxt = self.reg(self.cx.t('dyn'))
            end = f'_g{len(self.ops)}_{i}'
            self.op('Null', dst=nxt)
            self.op('JNull', reg=cur, offset=end)
            self.op('Call2', dst=nxt, fun=self.cx.fn('$Reflect.field').findex.value, arg0=cur, arg1=self.string(name))
            self.label(end)
            cur = nxt
        return cur

    def try_(self):
        """Start an exception trap; returns a token for end_try. Anything thrown inside is swallowed."""
        exc, label = self.reg(self.cx.t('dyn')), f'_trap{len(self.ops)}'
        self.op('Trap', exc=exc, offset=label)
        return exc, label

    def end_try(self, token):
        exc, label = token
        self.op('EndTrap', exc=exc)
        self.label(label)  # handler = continue after the guarded block

    def build(self):
        for idx, field, name in self.fix:
            self.ops[idx].df[field].value = self.labels[name] - (idx + 1)
        f = Function()
        f.findex = fIndex(self.code.next_free_findex().value)
        f.regs = [tIndex(t) for t in self.regs]
        f.ops = self.ops
        f.type = tIndex(self.fun_type if self.fun_type is not None else _fun_type(self.code, self.regs[:self._nargs], self.ret))
        f.version = self.code.version.value
        f.has_debug = bool(self.code.has_debug_info)
        if f.has_debug:
            f.debuginfo = DebugInfo()
            f.debuginfo.value = [fileRef(0, 0) for _ in f.ops]
            f.nassigns, f.assigns = VarInt(0), []
        self.code.functions.append(f)
        self.code.invalidate_findex_cache()
        return f.findex.value


def _fun_type(code, args, ret):
    from crashlink.asm import AsmFile
    return AsmFile._intern_fun_type(None, code, [tIndex(a) for a in args], tIndex(ret)).value


# ------------------------------------------------------------------ helpers

def build_log(cx):
    """aimod_log(d: Dyn): d.t = appTime; fileLog.writeString('AIMOD ' + Std.string(d) + '\\n'); flush."""
    fb = FB(cx, [cx.t('dyn')], cx.t('void'))
    dolog = cx.fn('lib.$Log.doLog')
    log_t = cx.t('lib.$Log')
    g = next(op.df['global'].value for op in dolog.ops
             if op.op == 'GetGlobal' and dolog.regs[op.df['dst'].value].value == log_t)
    lg, fl, v = fb.reg(log_t), fb.reg(cx.t('sys.io.FileOutput')), fb.reg(cx.t('void'))
    guard = fb.try_()
    fb.op('GetGlobal', dst=lg, **{'global': g})
    fb.op('Field', dst=fl, obj=lg, field=cx.field(log_t, 'fileLog'))
    fb.op('JNull', reg=fl, offset='end')
    tm = fb.reg(cx.t('f64'))
    fb.op('Call0', dst=tm, fun=cx.fn('$Const.get_appTime').findex.value)
    fb.op('DynSet', obj=0, field=cx.s('t'), src=tm)
    game_t = cx.t('$Game')  # g = Game.inst.state.time (game seconds; independent of speed)
    gs = fb.reg(game_t)
    gi = fb.reg(cx.field_type(game_t, 'inst'))
    fb.op('GetGlobal', dst=gs, **{'global': cx.global_of('$Game')})
    fb.op('Field', dst=gi, obj=gs, field=cx.field(game_t, 'inst'))
    fb.op('DynSet', obj=0, field=cx.s('g'), src=fb.get(gi, 'state', 'time'))
    body = fb.reg(cx.t('String'))
    fb.op('Call1', dst=body, fun=cx.fn('$Std.string').findex.value, arg0=0)
    add = cx.fn('$String.__add__').findex.value
    line = fb.reg(cx.t('String'))
    fb.op('Call2', dst=line, fun=add, arg0=fb.string('AIMOD '), arg1=body)
    fb.op('Call2', dst=line, fun=add, arg0=line, arg1=fb.string('\n'))
    enc = fb.reg(cx.t('haxe.io.Encoding'))
    fb.op('Null', dst=enc)
    fb.op('Call3', dst=v, fun=cx.fn('haxe.io.Output.writeString').findex.value, arg0=fl, arg1=line, arg2=enc)
    fb.op('Call1', dst=v, fun=cx.fn('sys.io.FileOutput.flush').findex.value, arg0=fl)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=v)
    return fb.build()


def build_ent(cx):
    """aimod_ent(e: Dyn) -> Dyn: {k: kind, o: owner.kind, p: placeName, x, y} or null."""
    fb = FB(cx, [cx.t('dyn')], cx.t('dyn'))
    out = fb.reg(cx.t('dyn'))
    fb.op('Null', dst=out)
    fb.op('JNull', reg=0, offset='end')
    obj = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=obj)
    for key, path in (('k', ('kind',)), ('o', ('_owner', 'kind')), ('p', ('placeName',)), ('x', ('posx',)), ('y', ('posy',))):
        fb.op('DynSet', obj=obj, field=cx.s(key), src=fb.get(0, *path))
    fb.op('Mov', dst=out, src=obj)
    fb.label('end')
    fb.op('Ret', ret=out)
    return fb.build()


def build_str(cx, limit=240):
    """aimod_str(x: Dyn) -> Dyn: Std.string(x), truncated to `limit` chars (null stays null)."""
    code = cx.code
    fb = FB(cx, [cx.t('dyn')], cx.t('dyn'))
    out = fb.reg(cx.t('dyn'))
    fb.op('Null', dst=out)
    fb.op('JNull', reg=0, offset='end')
    s = fb.reg(cx.t('String'))
    fb.op('Call1', dst=s, fun=cx.fn('$Std.string').findex.value, arg0=0)
    substr = cx.fn('String.substr')
    null_t = substr.type.resolve(code).definition.args[2].value
    n, lim, zero, nlim = fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(null_t)
    fb.op('Field', dst=n, obj=s, field=cx.field(cx.t('String'), 'length'))
    fb.op('Int', dst=lim, ptr=code.add_i32(limit).value)
    fb.op('JSLte', a=n, b=lim, offset='keep')
    fb.op('Int', dst=zero, ptr=code.add_i32(0).value)
    fb.op('ToDyn', dst=nlim, src=lim)
    fb.op('Call3', dst=s, fun=substr.findex.value, arg0=s, arg1=zero, arg2=nlim)
    fb.label('keep')
    fb.op('Mov', dst=out, src=s)
    fb.label('end')
    fb.op('Ret', ret=out)
    return fb.build()


def build_fac(cx):
    """aimod_fac(x: Dyn) -> Dyn: faction kind of an AI module/controller/order/entity/faction."""
    fb = FB(cx, [cx.t('dyn')], cx.t('dyn'))
    out = fb.reg(cx.t('dyn'))
    for path in (('controller', 'owner', 'kind'), ('orders', 'controller', 'owner', 'kind'),
                 ('owner', 'kind'), ('_owner', 'kind')):
        fb.op('Mov', dst=out, src=fb.get(0, *path))
        skip = f'_f{len(fb.ops)}'
        fb.op('JNull', reg=out, offset=skip)
        fb.op('Ret', ret=out)
        fb.label(skip)
    fb.op('JNull', reg=fb.get(0, 'isAI'), offset='none')  # x is itself a faction
    fb.op('Mov', dst=out, src=fb.get(0, 'kind'))
    fb.op('Ret', ret=out)
    fb.label('none')
    fb.op('Null', dst=out)
    fb.op('Ret', ret=out)
    return fb.build()


def _is_sub(cx, t, base):
    code = cx.code
    while t is not None and t >= 0:
        d = code.types[t].definition
        if not isinstance(d, Obj):
            return False
        if d.name.resolve(code) == base:
            return True
        t = d.super.value if d.super.value >= 0 else None
    return False


def describe(fb, reg, ctx):
    """Dyn register describing any value compactly, chosen by its static type (None = skip)."""
    cx, t = fb.cx, fb.regs[reg]
    typ = cx.code.types[t]
    kind = typ.kind.value
    if kind in (1, 2, 3, 4, 5, 6, 7, 18, 19):  # numbers, bool, enum (prints its name), Null<T>
        return fb.dyn(reg)
    if kind == 11:
        name = typ.definition.name.resolve(cx.code)
        if name == 'String':
            return fb.dyn(reg)
        if name.startswith('hl.types.Array'):
            return length(fb, reg)
        if name.startswith('hxbit.ArrayProxy'):
            return fb.get(reg, 'array', 'length')
        if _is_sub(cx, t, 'ent.Entity'):
            out = fb.reg(cx.t('dyn'))
            fb.op('Call1', dst=out, fun=ctx['ent'], arg0=fb.dyn(reg))
            return out
        if name == 'logic.ai.AIOrder':
            sub = fb.reg(cx.t('dynobj'))
            fb.op('New', dst=sub)
            _order_fields(fb, sub, reg, ctx)
            return fb.dyn(sub)
    if kind in (9, 11, 15, 16):  # dyn / other class / virtual / anon: truncated text
        out = fb.reg(cx.t('dyn'))
        fb.op('Call1', dst=out, fun=ctx['str'], arg0=fb.dyn(reg))
        return out
    return None  # functions, refs, native arrays


def trace_wrapper(cx, target, label, helpers, src=None):
    """Generic event 'call': fn=label, f=faction(arg0), a<i>=args, r=result, src=caller (optional)."""
    code = cx.code
    fun = target.type.resolve(code).definition
    args = [a.value for a in fun.args]
    fb = FB(cx, args, fun.ret.value, fun_type=target.type.value)
    res = fb.reg(fun.ret.value)
    d = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=d)
    fb.op('DynSet', obj=d, field=cx.s('e'), src=fb.string('call'))
    fb.op('DynSet', obj=d, field=cx.s('fn'), src=fb.string(label))
    if src:
        fb.op('DynSet', obj=d, field=cx.s('src'), src=fb.string(src))
    ctx = dict(helpers, args=list(range(len(args))), res=res)
    guard = fb.try_()
    if args:
        fac = fb.reg(cx.t('dyn'))
        fb.op('Call1', dst=fac, fun=helpers['fac'], arg0=fb.dyn(0))
        put(fb, d, 'f', fac)
    this_is_ai = bool(args) and code.types[args[0]].kind.value == 11 and \
        code.types[args[0]].definition.name.resolve(code).startswith('logic.ai.')
    for i in range(1 if this_is_ai else 0, len(args)):
        v = describe(fb, i, ctx)
        if v is not None:
            put(fb, d, f'a{i}', v)
    fb.end_try(guard)
    call = {0: 'Call0', 1: 'Call1', 2: 'Call2', 3: 'Call3', 4: 'Call4'}.get(len(args), 'CallN')
    kw = {'dst': res, 'fun': target.findex.value}
    kw.update({'args': list(range(len(args)))} if call == 'CallN' else {f'arg{i}': i for i in range(len(args))})
    fb.op(call, **kw)  # original call, outside any trap
    guard = fb.try_()
    if code.types[fun.ret.value].kind.value != 0:
        v = describe(fb, res, ctx)
        if v is not None:
            put(fb, d, 'r', v)
    v = fb.reg(cx.t('void'))
    fb.op('Call1', dst=v, fun=helpers['log'], arg0=fb.dyn(d))
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    return fb.build()


# ------------------------------------------------------------------ wrappers

def wrapper(cx, target, event, before, after, helpers, src=None):
    """New function with target's exact signature: logs, calls target, returns its result.

    before/after: callbacks (fb, d, args, res) adding DynSet fields to the event object d.
    """
    code = cx.code
    fun = target.type.resolve(code).definition
    args = [a.value for a in fun.args]
    fb = FB(cx, args, fun.ret.value, fun_type=target.type.value)
    res = fb.reg(fun.ret.value)
    d = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=d)
    fb.op('DynSet', obj=d, field=cx.s('e'), src=fb.string(event))
    if src:
        fb.op('DynSet', obj=d, field=cx.s('src'), src=fb.string(src))
    ctx = dict(helpers, args=list(range(len(args))), res=res)
    if before:
        guard = fb.try_()
        before(fb, d, ctx)
        fb.end_try(guard)
    call = {0: 'Call0', 1: 'Call1', 2: 'Call2', 3: 'Call3', 4: 'Call4'}.get(len(args), 'CallN')
    kw = {'dst': res, 'fun': target.findex.value}
    if call == 'CallN':
        kw['args'] = list(range(len(args)))
    else:
        kw.update({f'arg{i}': i for i in range(len(args))})
    fb.op(call, **kw)  # the original call: never inside a trap, so game behaviour is unchanged
    guard = fb.try_()
    if after:
        after(fb, d, ctx)
    v = fb.reg(cx.t('void'))
    fb.op('Call1', dst=v, fun=helpers['log'], arg0=fb.dyn(d))
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    return fb.build()


def put(fb, d, key, reg):
    fb.op('DynSet', obj=d, field=fb.cx.s(key), src=reg)


def put_ent(fb, d, key, reg, ctx):
    out = fb.reg(fb.cx.t('dyn'))
    fb.op('Call1', dst=out, fun=ctx['ent'], arg0=fb.dyn(reg))
    put(fb, d, key, out)


def faction_of_module(fb, reg):
    return fb.get(reg, 'controller', 'owner', 'kind')


def faction_of_order(fb, reg):
    return fb.get(reg, 'orders', 'controller', 'owner', 'kind')


def length(fb, reg):
    return fb.get(reg, 'length')


# event specs: (event, target function, caller filter or None, before, after)
def _pick_after(fb, d, c):
    a = c['args']
    put(fb, d, 'f', faction_of_module(fb, a[0]))
    put_ent(fb, d, 'tgt', fb.get(a[1], 'enemyStructure'), c)
    put(fb, d, 'tf', fb.get(a[1], 'targetFaction', 'kind'))
    put(fb, d, 'req', fb.get(a[1], 'requiredPowerBalance'))
    put(fb, d, 'allIn', fb.get(a[1], 'allIn'))
    put(fb, d, 'ign3rd', fb.get(a[1], 'ignoreOtherFactionArmies'))
    put(fb, d, 'sim', fb.get(a[1], 'simulatePendingArmies'))
    put(fb, d, 'cand', length(fb, fb.get(a[1], 'consideredUnits')))
    put(fb, d, 'eu', length(fb, fb.get(a[1], 'enemyUnits')))
    put(fb, d, 'sel', length(fb, c['res']))
    _first_pos(fb, d, c['res'])


def _first_pos(fb, d, arr_reg):
    """ax/ay = position of element 0 of an ArrayObj of entities (order armies / selected units)."""
    cx = fb.cx
    idx, first = fb.reg(cx.t('i32')), fb.reg(cx.t('dyn'))
    fb.op('Int', dst=idx, ptr=cx.code.add_i32(0).value)
    fb.op('Call2', dst=first, fun=cx.fn('hl.types.ArrayObj.getDyn').findex.value, arg0=arr_reg, arg1=idx)
    put(fb, d, 'ax', fb.get(first, 'posx'))
    put(fb, d, 'ay', fb.get(first, 'posy'))


def _snap_before(fb, d, c):
    a = c['args'][0]  # AIController, once per game day per AI faction
    put(fb, d, 'f', fb.get(a, 'owner', 'kind'))
    put(fb, d, 'aggr', fb.get(a, 'aiMilitary', '_aggressiveness'))
    s = fb.reg(fb.cx.t('dyn'))
    fb.op('Call1', dst=s, fun=c['str'], arg0=fb.get(a, 'aiMilitary', 'gauges'))
    put(fb, d, 'gauges', s)
    put(fb, d, 'armies', fb.get(a, 'owner', 'armies', 'array', 'length'))
    put(fb, d, 'structs', fb.get(a, 'owner', 'structures', 'array', 'length'))
    # stocks (resource sheet indices: 6 Authority, 10 Influence, 1 Solari) and the net Authority rate: explains an
    # Annex gauge that fires with no pick (vanilla reserves for an unaffordable target and waits)
    cx = fb.cx
    fr = fb.reg(cx.t('ent.Faction'))
    fb.op('SafeCast', dst=fr, src=fb.get(a, 'owner'))
    skip = f'_snapres{len(fb.ops)}'
    fb.op('JNull', reg=fr, offset=skip)
    for key, k in (('au', 6), ('inf', 10), ('sol', 1)):
        ki, v = fb.reg(cx.t('i32')), fb.reg(cx.t('f64'))
        fb.op('Int', dst=ki, ptr=cx.code.add_i32(k).value)
        fb.op('Call2', dst=v, fun=cx.fn('ent.Faction.getResource').findex.value, arg0=fr, arg1=ki)
        put(fb, d, key, fb.dyn(v))
    gp = cx.fn('ent.Faction.getResourceProduction')
    gpa = [t.value for t in cx.code.types[gp.type.value].definition.args]
    ki, v = fb.reg(cx.t('i32')), fb.reg(cx.t('f64'))
    fb.op('Int', dst=ki, ptr=cx.code.add_i32(6).value)
    nulls = []
    for t in gpa[2:]:
        r = fb.reg(t)
        fb.op('Null', dst=r)
        nulls.append(r)
    fb.op('CallN', dst=v, fun=gp.findex.value, args=[fr, ki] + nulls)
    put(fb, d, 'aup', fb.dyn(v))
    fb.label(skip)


def _fight_after(fb, d, c):
    a = c['args']  # AIUnits, Warzone -> Bool
    put(fb, d, 'f', faction_of_module(fb, a[0]))
    put(fb, d, 'wx', fb.get(a[1], '_centroid', 'x'))
    put(fb, d, 'wy', fb.get(a[1], '_centroid', 'y'))
    put(fb, d, 'ents', fb.get(a[1], 'entities', 'array', 'length'))
    put(fb, d, 'ok', fb.dyn(c['res']))


def _micro_before(fb, d, c):
    a = c['args']  # AIUnits, fight, army, AIMicroBehavior
    put(fb, d, 'f', faction_of_module(fb, a[0]))
    put_ent(fb, d, 'army', a[2], c)
    put(fb, d, 'from', fb.get(a[1], 'micro'))
    put(fb, d, 'to', fb.dyn(a[3]))
    put(fb, d, 'n', length(fb, fb.get(a[1], 'armies')))


def _stop_before(fb, d, c):
    _order_fields(fb, d, c['args'][0], c)
    put(fb, d, 'why', fb.dyn(c['args'][1]))


def _pw_after(fb, d, c):
    r = c['args'][0]
    put(fb, d, 'b', fb.get(r, 'balance'))
    put(fb, d, 'my', fb.get(r, 'my', 'powerScore'))
    put(fb, d, 'en', fb.get(r, 'enemy', 'powerScore'))


def _order_after(fb, d, c):
    a = c['args']  # this, type, prio, units, target, action, siegeAction, ...
    put(fb, d, 'f', faction_of_module(fb, a[0]))
    put(fb, d, 'type', fb.dyn(a[1]))
    put(fb, d, 'prio', fb.dyn(a[2]))
    put(fb, d, 'n', length(fb, a[3]))
    put_ent(fb, d, 'tgt', a[4], c)
    put(fb, d, 'act', fb.dyn(a[5]))
    put(fb, d, 'sa', fb.dyn(a[6]))
    _first_pos(fb, d, a[3])


def _order_fields(fb, d, o, ctx):
    put(fb, d, 'f', faction_of_order(fb, o))
    # target lives in enum targetType; call AIOrder.getTarget() only when targetType != null
    tt, tgt = fb.get(o, 'targetType'), fb.reg(fb.cx.t('ent.Entity'))
    skip = f'_tt{len(fb.ops)}'
    fb.op('Null', dst=tgt)
    fb.op('JNull', reg=tt, offset=skip)
    fb.op('Call1', dst=tgt, fun=fb.cx.fn('logic.ai.AIOrder.getTarget').findex.value, arg0=o)
    fb.label(skip)
    put_ent(fb, d, 'tgt', tgt, ctx)
    put(fb, d, 'type', fb.get(o, 'type'))
    put(fb, d, 'act', fb.get(o, 'action'))
    put(fb, d, 'sa', fb.get(o, 'siegeAction'))
    put(fb, d, 'tf', fb.get(o, 'targetFaction', 'kind'))
    put(fb, d, 'n', length(fb, fb.get(o, 'units')))
    put(fb, d, 'ph', fb.get(o, 'phase'))


def _end_before(fb, d, c):
    a = c['args']  # this(AIOrders), order, reason
    _order_fields(fb, d, a[1], c)
    put(fb, d, 'why', fb.dyn(a[2]))


def _phase_before(fb, d, c):
    _order_fields(fb, d, c['args'][0], c)  # ph = phase before


def _phase_to(fb, d, c):
    put(fb, d, 'to', fb.dyn(c['args'][1]))


def _next_after(fb, d, c):
    put(fb, d, 'to', fb.get(c['args'][0], 'phase'))


def _balance_after(fb, d, c):
    _order_fields(fb, d, c['args'][1], c)
    put(fb, d, 'b', fb.dyn(c['res']))


def _info_closure(cx):
    """The unnamed closure behind console command `info` (registered in initUser; calls Const.getVersion)."""
    init = cx.fn('ui.BaseConsole.initUser')
    version = cx.fn('$Const.getVersion').findex.value
    by_id = {f.findex.value: f for f in cx.code.functions}
    hits = [by_id[op.df['fun'].value] for op in init.ops if op.op == 'InstanceClosure'
            and any(o.df.get('fun') is not None and o.df['fun'].value == version for o in by_id[op.df['fun'].value].ops)]
    if len(hits) != 1:
        raise ValueError(f'info closure: expected 1 match, found {len(hits)}')
    return hits[0]


PER_CALLER = object()  # caller spec: one wrapper per calling function, logged as `src`

EVENTS = [
    ('pick', 'logic.ai.AIUnits.pickUnits', None, None, _pick_after),
    ('pw', '$HPowerScore.compute', 'logic.ai.AIUnits.pickUnits', None, _pw_after),
    ('order', 'logic.ai.AIOrders.addOrder', None, None, _order_after),
    ('end', 'logic.ai.AIOrders.removeOrder', None, _end_before, None),
    ('phase', 'logic.ai.AIOrder.changePhase', None, _phase_before, _phase_to),
    ('phase', 'logic.ai.AIOrder.nextPhase', None, _phase_before, _next_after),
    ('fightb', 'logic.ai.AIUnits.getOrderPowerBalance', None, None, _balance_after),
    ('fpw', '$HPowerScore.compute', 'logic.ai.AIUnits.getOrderPowerBalance', None, _pw_after),
    ('mark', _info_closure, 'ui.BaseConsole.initUser', None, None),  # console `info` = marker (macro L)
    ('snap', 'logic.ai.AIController.dailyUpdate', None, _snap_before, None),
    ('fight', 'logic.ai.AIUnits.initFight', None, None, _fight_after),
    ('micro', 'logic.ai.AIUnits.changeArmyMicro', None, _micro_before, None),
    ('stop', 'logic.ai.AIOrder.stop', PER_CALLER, _stop_before, None),  # src = which code cancelled it
]


def _sites(code, target_id, skip, caller=None):
    """Direct call / closure-creation ops referencing target_id, grouped by caller name."""
    out = {}
    for f in code.functions:
        if f.findex.value in skip:
            continue
        name = code.full_func_name(f)
        if caller and name != caller:
            continue
        for op in f.ops:
            fn = op.df.get('fun')
            direct = op.op.startswith('Call') and op.op not in ('CallClosure', 'CallMethod', 'CallThis')
            if (direct or op.op in ('InstanceClosure', 'StaticClosure')) and fn is not None and fn.value == target_id:
                out.setdefault(name, []).append(fn)
    return out


def _short(name):
    return '.'.join(name.replace('logic.ai.', '').replace('$', '').split('.')[-2:])


def apply(code, trace=(), trace_per_caller=()):
    """Inject EVENTS plus generic traces (function names). Returns {event: redirected call sites}."""
    cx = Ctx(code)
    helpers = {'log': build_log(cx), 'ent': build_ent(cx), 'str': build_str(cx), 'fac': build_fac(cx)}
    report = {}
    new_ids = set(helpers.values())
    jobs = [(ev, tgt, caller, before, after, 'event') for ev, tgt, caller, before, after in EVENTS]
    jobs += [('call', name, None, None, None, 'trace') for name in trace]
    jobs += [('call', name, PER_CALLER, None, None, 'trace') for name in trace_per_caller]
    for event, target_name, caller, before, after, mode in jobs:
        target = target_name(cx) if callable(target_name) else cx.fn(target_name)
        label = target_name if isinstance(target_name, str) else target_name.__name__
        groups = _sites(code, target.findex.value, new_ids, None if caller is PER_CALLER else caller)
        if not groups:
            if mode == 'trace':
                report[f'call:{_short(label)}'] = 'NO DIRECT CALL SITES (virtual/closure only) - not traced'
                continue
            raise ValueError(f'{event}: no call sites for {label}')
        if caller is PER_CALLER:
            wrappers = {g: (wrapper(cx, target, event, before, after, helpers, src=_short(g)) if mode == 'event'
                            else trace_wrapper(cx, target, _short(label), helpers, src=_short(g))) for g in groups}
        else:
            w = (wrapper(cx, target, event, before, after, helpers) if mode == 'event'
                 else trace_wrapper(cx, target, _short(label), helpers))
            wrappers = {g: w for g in groups}
        new_ids.update(wrappers.values())
        n = 0
        for g, refs in groups.items():
            for ref in refs:
                ref.value = wrappers[g]
                n += 1
        report[f'{event}:{_short(label)}'] = n
        if event == 'order':
            helpers['addOrder'] = w  # logging wrapper of AIOrders.addOrder, reused by behave.hunt
        if event == 'phase' and label.endswith('nextPhase'):
            helpers['nextPhase'] = w  # logging wrapper of AIOrder.nextPhase, reused by behave.hunt (engage)
    import aware  # enemy army awareness scan (event `aw`)
    import behave  # behaviour on top of it: safe-heal + hunt (event `hunt`)
    rep, hunt = behave.install(cx, helpers, new_ids)
    report.update(rep)
    report.update(aware.install(cx, helpers, new_ids, hunt))
    return report
