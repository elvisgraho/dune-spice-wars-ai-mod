"""Resupply guard (`rsguard`, user): a resupply walk that leads away from its heal target is turned around.

Why: Atreides' A_Elite on a vanilla Resupply(1,1) to its own Aish-fir (match 2026-10-04 09:28, 50:33) walked ~950 the
other way through neutral and Harkonnen land, supply 88 -> 0 of 135, life 100 -> 10%, and died at Tuotar next to
Smugglers' Tuek at 54:33, still on that order; no rule of ours moved it (none logged it) and nothing watched a
Resupply walk.

aimod_rsguard(mil, dt), tick chain every RSG_CHECK s per faction: for each army of our Resupply orders (AIOrderType 4)
with a target: map `rsgd` army -> best (smallest) distance to the target seen, `rsgt` army -> when. A new best
updates both. When the army is in a hostile zone (Army.isInHostileZone: it loses supply), its best is RSG_T s old
and it now stands >= RSG_GROW farther than that best: the order is stopped (Cancel) and the army walks (Move) to
our nearest structure; both maps forget it. Logs `rsg` (a, tgt, d, best, s = where it is sent, ds).
Fails safe: in a trap."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.worm import _move_to

RSG_CHECK = 2
RSG_T = 20        # s: no closer than its best for this long
RSG_GROW = 40     # ... and this much farther than its best


def build_rsguard(cx, helpers):
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    _tick(fb, b, cx, t, RSG_CHECK, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    mpd = _global_map(fb, b, cx, 'rsgd')
    mpt = _global_map(fb, b, cx, 'rsgt')
    k, ix, j = (fb.reg(cx.t('i32')) for _ in range(3))
    d, bd, q = (fb.reg(cx.t('f64')) for _ in range(3))
    o = fb.reg(cx.t('logic.ai.AIOrder'))
    tgt = fb.reg(cx.t('ent.Entity'))
    ae = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=k, src=b.field(orders, 'length'))
    b.loop_head('o')
    fb.op('JSLte', a=k, b=b.const('i32', 0), offset='end')
    fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
    fb.op('Mov', dst=o, src=b.cast(b.call('hl.types.ArrayObj.getDyn', orders, k), 'logic.ai.AIOrder'))
    fb.op('JNull', reg=o, offset='o')
    fb.op('EnumIndex', dst=ix, value=b.field(o, 'type'))
    fb.op('JNotEq', a=ix, b=b.const('i32', RESUPPLY), offset='o')
    fb.op('JNull', reg=b.field(o, 'targetType'), offset='o')
    fb.op('Mov', dst=tgt, src=b.call('logic.ai.AIOrder.getTarget', o))
    fb.op('JNull', reg=tgt, offset='o')
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='o')
    a = _army_loop(fb, b, units, b.field(units, 'length'), j, 'u', 'o')
    fb.op('Mov', dst=ae, src=a)
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', ae, tgt))
    bv = b.call('haxe.ds.ObjectMap.get', mpd, fb.dyn(a))
    fb.op('JNull', reg=bv, offset='best')
    fb.op('SafeCast', dst=bd, src=bv)
    fb.op('JSLt', a=d, b=bd, offset='best')
    # not closer than its best: judged once it has been so for RSG_T, in a hostile zone, RSG_GROW farther
    fb.op('JFalse', cond=b.call('ent.Army.isInHostileZone', a), offset='u')
    tv = b.call('haxe.ds.ObjectMap.get', mpt, fb.dyn(a))
    fb.op('JNull', reg=tv, offset='u')
    fb.op('SafeCast', dst=q, src=tv)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSLt', a=q, b=b.const('f64', RSG_T), offset='u')
    fb.op('Sub', dst=q, a=d, b=bd)
    fb.op('JSLt', a=q, b=b.const('f64', RSG_GROW), offset='u')
    # turn it around: our nearest structure
    ss = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=ss, offset='u')
    near = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=near)
    nd, sd = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=nd, src=b.const('f64', 1 << 30))
    si = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=si, src=b.const('i32', 0))
    b.loop_head('s')
    fb.op('JSGte', a=si, b=b.field(ss, 'length'), offset='sd')
    se = b.cast(b.call('hl.types.ArrayObj.getDyn', ss, si), 'ent.Entity')
    fb.op('Incr', dst=si)
    fb.op('JNull', reg=se, offset='s')
    fb.op('Mov', dst=sd, src=b.call('ent.Entity.getDistTo', ae, se))
    fb.op('JSGte', a=sd, b=nd, offset='s')
    fb.op('Mov', dst=nd, src=sd)
    fb.op('Mov', dst=near, src=se)
    fb.op('JAlways', offset='s')
    fb.label('sd')
    fb.op('JNull', reg=near, offset='u')
    _log_ev(fb, b, cx, helpers, 'rsg', [('f', fb.get(fac, 'kind')), ('a', ae), ('tgt', tgt), ('d', d), ('best', bd),
                                        ('s', near), ('ds', nd)])
    b.call('haxe.ds.ObjectMap.remove', mpd, fb.dyn(a))
    b.call('haxe.ds.ObjectMap.remove', mpt, fb.dyn(a))
    reason = cx.code.types[cx.fn('logic.ai.AIOrder.stop').type.value].definition.args[1].value
    cancel = fb.reg(reason)
    fb.op('MakeEnum', dst=cancel, construct=CANCEL, args=[])
    b.call('logic.ai.AIOrder.stop', o, cancel)
    _move_to(fb, b, cx, ae, b.field(near, 'posx'), b.field(near, 'posy'), fac)
    fb.op('JAlways', offset='end')  # one per tick: the order list changed
    fb.label('best')
    b.call('haxe.ds.ObjectMap.set', mpd, fb.dyn(a), fb.dyn(d))
    b.call('haxe.ds.ObjectMap.set', mpt, fb.dyn(a), fb.dyn(t))
    fb.op('JAlways', offset='u')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
