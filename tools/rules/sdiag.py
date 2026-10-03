"""Siege diagnostics (no decision): what our siege armies look like when the militia fight starts.

Why: Fremen lost 70-100% of 3-army Annexes on neutral villages against militia only (Ubdah 09:57 3 armies wiped in
2 min, Bir-kus 30:23 -69% at an engage ratio of 4.1, Kul-po 47:47 -93% at 2.2: an F_Demo + Discovery_FremenTrooper
pick from 684 away), while other militia fights at 2-4x lost < 25%. The order rows don't say which armies went in,
at what health and supply, so no fix can be chosen yet (AI-POLICY §1.1).

aimod_sact(mil, dt), in the tick chain every SACT_CHECK s: each of our Military orders on a structure in Action logs
`sact` once per target per SACT_T s: tgt, sa (siege action), H = aimod_militia(target), M = sum aimod_pw, and
armies = [{k kind, hp %, sup / ms supply, regen (hasSafeRegen)}]. Fails safe: in a trap."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

SACT_CHECK = 3   # s: scan period (Action lasts ~60-200 s)
SACT_T = 300     # s: one row per target per this (a siege of the same village again later logs again)


def build_sact(cx, helpers, pw, militia):
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    _tick(fb, b, cx, t, SACT_CHECK, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    k, ix, j = fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k, src=b.field(orders, 'length'))
    h, m, p, x = (fb.reg(cx.t('f64')) for _ in range(4))
    tgt = fb.reg(cx.t('ent.Entity'))
    b.loop_head('o')
    fb.op('JSLte', a=k, b=b.const('i32', 0), offset='end')
    fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, k), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset='o')
    fb.op('EnumIndex', dst=ix, value=b.field(o, 'type'))
    fb.op('JNotEq', a=ix, b=b.const('i32', MILITARY), offset='o')
    fb.op('JNotEq', a=b.field(o, 'phase'), b=b.const('i32', ACTION), offset='o')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='o')
    fb.op('EnumIndex', dst=ix, value=tt)
    fb.op('JNotEq', a=ix, b=b.const('i32', T_STRUCT), offset='o')
    fb.op('Mov', dst=tgt, src=b.call('logic.ai.AIOrder.getTarget', o))
    fb.op('JNull', reg=tgt, offset='o')
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='o')
    _throttle(fb, b, cx, 'sact', tgt, SACT_T, 'o')
    s = b.cast(fb.dyn(tgt), 'ent.Structure')
    fb.op('Mov', dst=h, src=b.const('f64', 0))
    fb.op('JNull', reg=s, offset='noh')
    fb.op('Call1', dst=h, fun=militia, arg0=s)
    fb.label('noh')
    fb.op('Mov', dst=m, src=b.const('f64', 0))
    arr = _new_array(fb, b, cx)
    un = b.field(units, 'length')
    fb.op('Mov', dst=j, src=b.const('i32', 0))
    b.loop_head('u')
    fb.op('JSGte', a=j, b=un, offset='udone')
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', units, j), 'ent.Army')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=a, offset='u')
    fb.op('Call1', dst=p, fun=pw, arg0=a)
    fb.op('Add', dst=m, a=m, b=p)
    e = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=e)
    b.put(e, 'k', fb.get(a, 'kind'))
    fb.op('Mul', dst=x, a=b.call('ent.Entity.get_lifeRatio', a), b=b.const('f64', 100))
    b.put(e, 'hp', b.to_int(x))
    b.put(e, 'sup', b.to_int(b.call('ent.Army.get_supply', a)))
    b.put(e, 'ms', b.to_int(b.call('ent.Army.get_maxSupply', a)))
    b.put(e, 'regen', b.call('ent.Unit.hasSafeRegen', a))
    b.put(e, 'pw', b.to_int(p))
    b.call('hl.types.ArrayObj.push', arr, fb.dyn(e))
    fb.op('JAlways', offset='u')
    fb.label('udone')
    _log_ev(fb, b, cx, helpers, 'sact', [('f', fb.get(fac, 'kind')), ('tgt', tgt),
                                         ('sa', b.cast(fb.get(o, 'siegeAction'), 'String')), ('H', h), ('M', m),
                                         ('armies', arr)])
    fb.op('JAlways', offset='o')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


SREACH_T = 300   # s: special-reach pass per faction


def build_sreach(cx, helpers):
    """aimod_sreach(mil, dt), in the tick chain every SREACH_T s (diagnostic, no decision): every village in a special
    region (zone kind in ANNEX_SPECIALS / ANNEX_SPECIALS_EARLY) that isn't ours logs `sreach` (f, s, rk = region id,
    hops = Zone.getDistanceToPlayerTerritory(us, true): vanilla's siege-scan reach, rec = Structure.isReconnedFaction:
    a village we never surveyed is never offered by any scan). Why: Smugglers never scored the special village Tadno
    (no log row at all in 18 min) although it lay near their land past a deep desert. Fails safe: in a trap."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    st = _state(fb, b, cx)
    _tick(fb, b, cx, b.field(st, 'time'), SREACH_T, 'end')
    vl = b.field(st, 'villages')
    fb.op('JNull', reg=vl, offset='end')
    i, hops = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    rk = fb.reg(cx.t('String'))
    t_true = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_true, value=True)
    gdt = cx.fn('ent.Zone.getDistanceToPlayerTerritory')
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('v')
    fb.op('JSGte', a=i, b=b.field(vl, 'length'), offset='end')
    v = b.cast(b.call('hl.types.ArrayObj.getDyn', vl, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=v, offset='v')
    ve = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ve, src=v)
    fb.op('JEq', a=b.call('ent.Entity.get_owner', ve), b=fac, offset='v')
    z = b.call('ent.Entity.get_zone', ve)
    fb.op('JNull', reg=z, offset='v')
    kd = b.field(z, 'kind')
    fb.op('JNull', reg=kd, offset='v')
    ids = sorted(set(ANNEX_SPECIALS) | set(ANNEX_SPECIALS_EARLY))
    for n_, rid in enumerate(ids):
        fb.op('JEq', a=b.call('String.__compare', kd, fb.dyn(fb.string(rid))), b=b.const('i32', 0), offset=f'sp{n_}')
    fb.op('JAlways', offset='v')
    for n_, rid in enumerate(ids):
        fb.label(f'sp{n_}')
        fb.op('JAlways', offset='hit')
    fb.label('hit')
    fb.op('Mov', dst=rk, src=kd)
    fb.op('Call3', dst=hops, fun=gdt.findex.value, arg0=z, arg1=fac, arg2=fb.dyn(t_true))
    hf = fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=hf, src=hops)
    _log_ev(fb, b, cx, helpers, 'sreach', [('f', fb.get(fac, 'kind')), ('s', ve), ('rk', rk), ('hops', hf),
                                           ('rec', b.call('ent.Structure.isReconnedFaction', v, fac))])
    fb.op('JAlways', offset='v')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
