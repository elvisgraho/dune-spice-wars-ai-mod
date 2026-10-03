"""Enemy army awareness (core), injected with the `ai-log` patch. Observation only: no AI behaviour change yet.

aimod_aware(mil: AIMilitary, dt): every PERIOD game seconds per AI faction (stateless throttle:
floor(t/P) != floor((t-dt)/P)), scan Game.inst.state.armies and log event `aw`:
  f, n (hostile armies listed), en (their summed power), mine (own non-militia army power),
  a = [{o owner, k kind, x, y, pw power (HPowerScore.singlePowerScore(HCombatStats.unitCombatStats) = what the
        AI itself uses; includes trait/operation buffs and HP), hp life %, sup/ms supply/max, ls losing supply,
        hz in hostile zone, zo zone owner, sand on sand, worm zone worm activity, vis visible to f, mv moving, spd Unit.getSpeed,
        d distance to f's nearest structure (near), da distance to f's nearest own army (na kind, nsa/nty/ntgt
        its AI order = what our army is busy with), sa/ty/tgt its AI order (enemy intent, AI factions only),
        oc/ct occupied/contested structure}, ...]
Listed: at-war (State.areAtWar), non-militia, not transported, and (within RANGE of one of f's structures OR
within RANGE of one of f's armies OR visible to f anywhere, e.g. spotted by an ornithopter). Neutral raiders (owner
null, Army.raid) only within RANGE, with rk raid kind and rt = their raid targets f (only those count in en).
Hooked by redirecting AIMilitary.regularUpdate's direct call to updateBlockers(dt) (runs only for live AI).
"""
from inject import FB

PERIOD = 10   # game seconds between scans (per AI faction)
RANGE = 600   # list hostile armies within this distance of one of our structures (world units; Halha-Tabr ~180)


class B:
    """Typed-op helpers on top of FB."""

    def __init__(self, fb):
        self.fb, self.cx, self.code = fb, fb.cx, fb.code

    def const(self, t, v):
        r = self.fb.reg(self.cx.t('i32'))
        self.fb.op('Int', dst=r, ptr=self.code.add_i32(v).value)
        if t == 'i32':
            return r
        f = self.fb.reg(self.cx.t('f64'))
        self.fb.op('ToSFloat', dst=f, src=r)
        return f

    def call(self, name, *args):
        f = self.cx.fn(name)
        ft = self.code.types[f.type.value].definition
        dst = self.fb.reg(ft.ret.value)
        conv = []
        for a, want in zip(args, ft.args):
            if self.fb.regs[a] != want.value and self.code.types[want.value].kind.value == 15:  # virtual
                v = self.fb.reg(want.value)
                self.fb.op('ToVirtual', dst=v, src=a)
                a = v
            conv.append(a)
        n = len(conv)
        if n <= 4:
            self.fb.op(f'Call{n}', dst=dst, fun=f.findex.value, **{f'arg{i}': a for i, a in enumerate(conv)})
        else:
            self.fb.op('CallN', dst=dst, fun=f.findex.value, args=conv)
        return dst

    def field(self, obj, name):
        t = self.fb.regs[obj]
        dst = self.fb.reg(self.cx.field_type(t, name))
        self.fb.op('Field', dst=dst, obj=obj, field=self.cx.field(t, name))
        return dst

    def cast(self, src, t):
        dst = self.fb.reg(self.cx.t(t))
        self.fb.op('SafeCast', dst=dst, src=src)
        return dst

    def to_int(self, f):
        dst = self.fb.reg(self.cx.t('i32'))
        self.fb.op('ToInt', dst=dst, src=f)
        return dst

    def put(self, d, key, reg):
        self.fb.op('DynSet', obj=d, field=self.cx.s(key), src=self.fb.dyn(reg))

    def loop_head(self, name):
        self.fb.label(name)
        self.fb.op('Label')  # HL requires a Label op at backward-jump targets

    def name_of(self, ent):
        """Dyn: placeName, else kind (null-safe)."""
        out = self.fb.reg(self.cx.t('dyn'))
        self.fb.op('Mov', dst=out, src=self.fb.get(ent, 'placeName'))
        skip = f'_nm{len(self.fb.ops)}'
        self.fb.op('JNotNull', reg=out, offset=skip)
        self.fb.op('Mov', dst=out, src=self.fb.get(ent, 'kind'))
        self.fb.label(skip)
        return out


def build_aware(cx, helpers):
    mil_t = cx.t('logic.ai.AIMilitary')
    fb = FB(cx, [mil_t, cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()

    # throttle
    gs = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gs, **{'global': cx.global_of('$Game')})
    state = b.field(b.field(gs, 'inst'), 'state')
    t = b.field(state, 'time')
    p = b.const('f64', PERIOD)
    q1, t2, q2 = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('SDiv', dst=q1, a=t, b=p)
    fb.op('Sub', dst=t2, a=t, b=1)  # reg 1 = dt
    fb.op('SDiv', dst=q2, a=t2, b=p)
    fb.op('JEq', a=b.to_int(q1), b=b.to_int(q2), offset='end')

    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    armies = b.field(state, 'armies')
    alen = b.field(armies, 'length')
    structs = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    slen = b.field(structs, 'length')
    rng = b.const('f64', RANGE)
    big = b.const('f64', 1 << 30)
    one = b.const('i32', 1)
    i, j, n = b.const('i32', 0), fb.reg(cx.t('i32')), b.const('i32', 0)
    en, mine = b.const('f64', 0), b.const('f64', 0)
    my_armies = b.cast(fb.get(fac, 'armies', 'array'), 'hl.types.ArrayObj')
    mlen = b.field(my_armies, 'length')
    rdr, rtg = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    best, best_a = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    near = fb.reg(cx.t('ent.Entity'))
    near_a = fb.reg(cx.t('ent.Army'))
    text = fb.string('')
    comma = fb.string(',')
    add = '$String.__add__'

    b.loop_head('armies')
    fb.op('JSGte', a=i, b=alen, offset='done')
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', armies, i), 'ent.Army')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=a, offset='armies')
    fb.op('JTrue', cond=b.field(a, 'isMilitia'), offset='armies')
    fb.op('JTrue', cond=b.call('ent.Entity.isTransported', a), offset='armies')
    owner = b.call('ent.Entity.get_owner', a)
    pw = b.call('$HPowerScore.singlePowerScore', b.call('$HCombatStats.unitCombatStats', a))
    # neutral raiders (owner null, Army.raid: rebels, renegades, Fremen raids, ...): listed near us with their raid
    # kind (rk) and whether the raid targets us (rt); only those add to en
    fb.op('Bool', dst=rdr, value=False)
    fb.op('Bool', dst=rtg, value=False)
    fb.op('JNotNull', reg=owner, offset='owned')
    rd = b.field(a, 'raid')
    fb.op('JNull', reg=rd, offset='armies')
    fb.op('Bool', dst=rdr, value=True)
    fb.op('JNotEq', a=b.field(rd, 'targetFaction'), b=fac, offset='hostile')
    fb.op('Bool', dst=rtg, value=True)
    fb.op('JAlways', offset='hostile')
    fb.label('owned')
    fb.op('JNotEq', a=owner, b=fac, offset='foreign')
    fb.op('Add', dst=mine, a=mine, b=pw)
    fb.op('JAlways', offset='armies')
    fb.label('foreign')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, owner), offset='armies')
    fb.label('hostile')

    # nearest own structure
    fb.op('Mov', dst=best, src=big)
    fb.op('Null', dst=near)
    fb.op('Int', dst=j, ptr=cx.code.add_i32(0).value)
    b.loop_head('structs')
    fb.op('JSGte', a=j, b=slen, offset='sdone')
    s = b.cast(b.call('hl.types.ArrayObj.getDyn', structs, j), 'ent.Entity')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=s, offset='structs')
    dd = b.call('ent.Entity.getDistTo', a, s)
    fb.op('JSGte', a=dd, b=best, offset='structs')
    fb.op('Mov', dst=best, src=dd)
    fb.op('Mov', dst=near, src=s)
    fb.op('JAlways', offset='structs')
    fb.label('sdone')

    # nearest own army (non-militia, not transported)
    fb.op('Mov', dst=best_a, src=big)
    fb.op('Null', dst=near_a)
    fb.op('Int', dst=j, ptr=cx.code.add_i32(0).value)
    b.loop_head('mine')
    fb.op('JSGte', a=j, b=mlen, offset='mdone')
    m = b.cast(b.call('hl.types.ArrayObj.getDyn', my_armies, j), 'ent.Army')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=m, offset='mine')
    fb.op('JTrue', cond=b.field(m, 'isMilitia'), offset='mine')
    fb.op('JTrue', cond=b.call('ent.Entity.isTransported', m), offset='mine')
    dd = b.call('ent.Entity.getDistTo', a, m)
    fb.op('JSGte', a=dd, b=best_a, offset='mine')
    fb.op('Mov', dst=best_a, src=dd)
    fb.op('Mov', dst=near_a, src=m)
    fb.op('JAlways', offset='mine')
    fb.label('mdone')

    # listed if near one of our structures or armies, or visible to us anywhere (e.g. spotted by an ornithopter)
    vis = b.call('ent.Entity.isVisibleForFaction', a, fac)
    fb.op('JSLte', a=best, b=rng, offset='keep')
    fb.op('JSLte', a=best_a, b=rng, offset='keep')
    fb.op('JTrue', cond=rdr, offset='armies')  # raiders only near us
    fb.op('JFalse', cond=vis, offset='armies')
    fb.label('keep')

    e = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=e)
    b.put(e, 'o', fb.get(owner, 'kind'))
    b.put(e, 'k', fb.get(a, 'kind'))
    b.put(e, 'x', b.to_int(b.field(a, 'posx')))
    b.put(e, 'y', b.to_int(b.field(a, 'posy')))
    b.put(e, 'pw', b.to_int(pw))
    hp = fb.reg(cx.t('f64'))
    fb.op('Mul', dst=hp, a=b.call('ent.Entity.get_lifeRatio', a), b=b.const('f64', 100))
    b.put(e, 'hp', b.to_int(hp))
    b.put(e, 'sup', b.to_int(b.call('ent.Army.get_supply', a)))
    b.put(e, 'ms', b.to_int(b.call('ent.Army.get_maxSupply', a)))
    b.put(e, 'ls', b.call('ent.Army.isLosingSupply', a))
    b.put(e, 'hz', b.call('ent.Army.isInHostileZone', a))
    b.put(e, 'sand', b.call('ent.Entity.isOnSand', a))
    b.put(e, 'vis', vis)
    b.put(e, 'mv', b.call('ent.Unit.isMoving', a))
    noref = fb.reg(cx.code.types[cx.fn('ent.Unit.getSpeed').type.value].definition.args[1].value)
    fb.op('Null', dst=noref)
    b.put(e, 'spd', b.call('ent.Unit.getSpeed', a, noref))  # world units/s? calibrates behave.HORIZON
    b.put(e, 'd', b.to_int(best))
    b.put(e, 'near', b.name_of(near))
    b.put(e, 'da', b.to_int(best_a))
    fb.op('JNull', reg=near_a, offset='nomine')
    b.put(e, 'na', fb.get(near_a, 'kind'))
    from rules.common import _order_of  # local: rules.common imports this module
    my_order = fb.reg(cx.t('logic.ai.AIOrder'))
    _order_of(fb, b, cx, fac, near_a, my_order, 'nomine')  # Unit.aiOrder is never maintained
    b.put(e, 'nsa', fb.get(my_order, 'siegeAction'))
    b.put(e, 'nty', fb.get(my_order, 'type'))
    fb.op('JNull', reg=fb.get(my_order, 'targetType'), offset='nomine')
    b.put(e, 'ntgt', b.name_of(b.call('logic.ai.AIOrder.getTarget', my_order)))
    fb.label('nomine')
    z = b.call('ent.Entity.get_zone', a)
    fb.op('JNull', reg=z, offset='nozone')
    b.put(e, 'zo', fb.get(z, 'owner', 'kind'))
    b.put(e, 'worm', b.call('ent.Zone.getCurrentWormActivity', z))
    b.put(e, 'wt', b.call('ent.Unit.isWormTarget', a))  # a worm has targeted it
    fb.label('nozone')
    order = fb.reg(cx.t('logic.ai.AIOrder'))
    _order_of(fb, b, cx, owner, a, order, 'noorder')
    b.put(e, 'sa', fb.get(order, 'siegeAction'))
    b.put(e, 'ty', fb.get(order, 'type'))
    fb.op('JNull', reg=fb.get(order, 'targetType'), offset='noorder')
    b.put(e, 'tgt', b.name_of(b.call('logic.ai.AIOrder.getTarget', order)))
    fb.label('noorder')
    fb.op('JFalse', cond=rdr, offset='noraid')
    b.put(e, 'rk', fb.get(a, 'raid', 'kind'))
    b.put(e, 'rt', rtg)
    fb.label('noraid')
    b.put(e, 'oc', fb.get(a, 'occupiedStructure', 'placeName'))
    b.put(e, 'ct', fb.get(a, 'contestingStructure', 'placeName'))

    zero = b.const('i32', 0)
    fb.op('JEq', a=n, b=zero, offset='first')
    fb.op('Mov', dst=text, src=b.call(add, text, comma))
    fb.label('first')
    fb.op('Mov', dst=text, src=b.call(add, text, b.call('$Std.string', fb.dyn(e))))
    fb.op('Add', dst=n, a=n, b=one)
    fb.op('JFalse', cond=rdr, offset='enadd')
    fb.op('JFalse', cond=rtg, offset='armies')
    fb.label('enadd')
    fb.op('Add', dst=en, a=en, b=pw)
    fb.op('JAlways', offset='armies')

    fb.label('done')
    d = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=d)
    b.put(d, 'e', fb.string('aw'))
    b.put(d, 'f', fb.get(fac, 'kind'))
    b.put(d, 'n', n)
    b.put(d, 'en', b.to_int(en))
    b.put(d, 'mine', b.to_int(mine))
    lst = b.call(add, b.call(add, fb.string('['), text), fb.string(']'))
    b.put(d, 'a', lst)
    fb.op('Call1', dst=void, fun=helpers['log'], arg0=fb.dyn(d))
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


def install(cx, helpers, new_ids, hunt=None):
    """Redirect AIMilitary.regularUpdate -> updateBlockers(dt) to a wrapper that also runs aimod_aware (+ hunt)."""
    aware = build_aware(cx, helpers)
    target = cx.fn('logic.ai.AIMilitary.updateBlockers')
    caller = cx.fn('logic.ai.AIMilitary.regularUpdate')
    refs = [op.df['fun'] for op in caller.ops
            if op.op == 'Call2' and op.df['fun'].value == target.findex.value]
    if len(refs) != 1:
        raise ValueError(f'aware: expected 1 updateBlockers call in regularUpdate, found {len(refs)}')
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'), fun_type=target.type.value)
    v = fb.reg(cx.t('void'))
    fb.op('Call2', dst=v, fun=target.findex.value, arg0=0, arg1=1)  # original, outside any trap
    guard = fb.try_()
    fb.op('Call2', dst=v, fun=aware, arg0=0, arg1=1)
    fb.end_try(guard)
    if hunt is not None:  # behave.hunt(mil, dt): own throttles and trap
        guard = fb.try_()
        fb.op('Call2', dst=v, fun=hunt, arg0=0, arg1=1)
        fb.end_try(guard)
    fb.op('Ret', ret=v)
    w = fb.build()
    refs[0].value = w
    new_ids.update({aware, w})
    return {'aw:updateBlockers': 1}
