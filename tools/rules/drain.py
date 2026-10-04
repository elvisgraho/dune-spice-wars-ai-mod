"""Siege drain (`drain`): a siege in Action whose armies wear down without a fight we see is called off.

Why: Fremen's 16-army Annex of Harkonnen's Zay-nit (match 2026-10-03 23:08, 38:44-41:59) sat in Action 3 min
while turret fire and unseen armies took every army from 100% to 4-30% life, then 13 of them died within 12 s.
The fight retreat check never fired: the warzone balance read 1.0 (no enemy army power found), so nothing judged
the siege lost.

aimod_drain(mil, dt), in the tick chain every DRAIN_CHECK s: each of our Military orders on a structure in Action:
avg = summed life ratio of its armies / the army count when Action began (a dead army counts 0); the first avg
seen in Action and that count are kept (maps `drain0` / `drain0n`, per order). When avg <
DRAIN_HP and avg <= start - DRAIN_DROP and the capture progress there < DRAIN_PR and its militia still stands (aimod_militia > 0): the order is cancelled (its
armies go home to heal through vanilla) and the target goes into lost-siege memory (`slost`, no second assault
the same way for LOST_T). Logs `drain` (f, s, hp% avg now, hp0% start, pr% progress, n armies)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

DRAIN_CHECK = 2


def build_drain(cx, helpers, militia):
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    _tick(fb, b, cx, t, DRAIN_CHECK, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    k, ix, j, n = (fb.reg(cx.t('i32')) for _ in range(4))
    avg, h0, pr, q, nf = (fb.reg(cx.t('f64')) for _ in range(5))
    zero = b.const('f64', 0)
    mp = _global_map(fb, b, cx, 'drain0')
    o = fb.reg(cx.t('logic.ai.AIOrder'))
    tgt = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=k, src=b.field(orders, 'length'))
    b.loop_head('o')
    fb.op('JSLte', a=k, b=b.const('i32', 0), offset='end')
    fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
    fb.op('Mov', dst=o, src=b.cast(b.call('hl.types.ArrayObj.getDyn', orders, k), 'logic.ai.AIOrder'))
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
    s = b.cast(fb.dyn(tgt), 'ent.Structure')
    fb.op('JNull', reg=s, offset='o')
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='o')
    # mean life of the order's armies
    fb.op('Mov', dst=avg, src=zero)
    fb.op('Mov', dst=n, src=b.const('i32', 0))
    fb.op('Mov', dst=j, src=b.const('i32', 0))
    b.loop_head('u')
    fb.op('JSGte', a=j, b=b.field(units, 'length'), offset='ud')
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', units, j), 'ent.Army')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=a, offset='u')
    fb.op('Add', dst=avg, a=avg, b=b.call('ent.Entity.get_lifeRatio', a))
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset='u')
    fb.label('ud')
    fb.op('JSLte', a=n, b=b.const('i32', 0), offset='o')
    fb.op('ToSFloat', dst=nf, src=n)
    # start value per order: mean life and army count when Action began
    mpn = _global_map(fb, b, cx, 'drain0n')
    sv = b.call('haxe.ds.ObjectMap.get', mp, fb.dyn(o))
    fb.op('JNotNull', reg=sv, offset='has')
    sa = fb.reg(cx.t('f64'))
    fb.op('SDiv', dst=sa, a=avg, b=nf)
    b.call('haxe.ds.ObjectMap.set', mp, fb.dyn(o), fb.dyn(sa))
    b.call('haxe.ds.ObjectMap.set', mpn, fb.dyn(o), fb.dyn(nf))
    fb.op('JAlways', offset='o')
    fb.label('has')
    fb.op('SafeCast', dst=h0, src=sv)
    # an army that died counts as 0 life (dead ones leave the order: Atreides' Liberate of Adron 70:00 lost 3 of 12
    # and most of the rest's life while the survivors' mean stayed up)
    n0v = b.call('haxe.ds.ObjectMap.get', mpn, fb.dyn(o))
    fb.op('JNull', reg=n0v, offset='n0d')
    fb.op('SafeCast', dst=q, src=n0v)
    fb.op('JSLte', a=q, b=nf, offset='n0d')
    fb.op('Mov', dst=nf, src=q)
    fb.label('n0d')
    fb.op('SDiv', dst=avg, a=avg, b=nf)
    fb.op('JSGte', a=avg, b=_ratio(fb, b, DRAIN_HP), offset='o')
    fb.op('Sub', dst=q, a=h0, b=avg)
    fb.op('JSLt', a=q, b=_ratio(fb, b, DRAIN_DROP), offset='o')
    fb.op('Mov', dst=pr, src=zero)
    sg = b.field(s, 'siege')
    fb.op('JNull', reg=sg, offset='np')
    fb.op('Mov', dst=pr, src=b.call('ent.comp.SiegeComponent.getOccupationActionProgress', sg))
    fb.label('np')
    fb.op('JSGte', a=pr, b=_ratio(fb, b, DRAIN_PR), offset='o')
    # militia dead = the fight is won (armies `release` freed then look like dead ones: Smugglers' Ubtar 03:12 and
    # Atreides' Qadlulah 05:06 were cancelled at 7-12% capture with no defender left)
    fb.op('Call1', dst=q, fun=militia, arg0=s)
    fb.op('JSLte', a=q, b=zero, offset='o')
    _log_ev(fb, b, cx, helpers, 'drain', [('f', fb.get(fac, 'kind')), ('s', tgt), ('hp%', avg), ('hp0%', h0),
                                          ('pr%', pr), ('n', fb.dyn(n))])
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'slost'), fb.dyn(tgt), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'slostf'), fb.dyn(tgt), fb.dyn(fac))
    b.call('haxe.ds.ObjectMap.remove', mp, fb.dyn(o))
    b.call('haxe.ds.ObjectMap.remove', mpn, fb.dyn(o))
    reason = cx.code.types[cx.fn('logic.ai.AIOrder.stop').type.value].definition.args[1].value
    cancel = fb.reg(reason)
    fb.op('MakeEnum', dst=cancel, construct=CANCEL, args=[])
    b.call('logic.ai.AIOrder.stop', o, cancel)
    fb.op('JAlways', offset='end')  # one per tick: the order list changed
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
