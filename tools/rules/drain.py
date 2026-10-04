"""Siege drain (`drain`): a siege in Action whose armies wear down without a fight we see is called off.

Why: Fremen's 16-army Annex of Harkonnen's Zay-nit (match 2026-10-03 23:08, 38:44-41:59) sat in Action 3 min
while turret fire and unseen armies took every army from 100% to 4-30% life, then 13 of them died within 12 s.
The fight retreat check never fired: the warzone balance read 1.0 (no enemy army power found), so nothing judged
the siege lost.

aimod_drain(mil, dt), in the tick chain every DRAIN_CHECK s: each of our Military orders on a structure in Action
whose capture progress there < DRAIN_PR and whose militia still stands (aimod_militia > 0) or at-war guns other than
its own cover it (aimod_cover > 0: the wear is the guns; Fremen at Arkkhelon under Arrakeen) is judged per army (user):
an army is worn when its life < DRAIN_HP and at least DRAIN_DROP below its life when first seen in this order's Action
(maps `drain0a` army -> life, `drain0o` army -> order). Worn armies leave the order (removeUnit; never the last one;
they heal through vanilla) while the rest keep capturing (log `drain` act split, n of). Every army left worn: the order
is cancelled and the target goes into lost-siege memory (`slost`, no second assault the same way for LOST_T; a neutral
village gets `nbump` instead). Logs `drain` act cancel (f, s, hp% mean now, hp0% mean start, pr% progress, n armies)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

DRAIN_CHECK = 2


def build_drain(cx, helpers, militia, cover):
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
    # gates: the capture isn't under way (a capture progressing: the fight was won) and something is wearing them
    fb.op('Mov', dst=pr, src=zero)
    sg = b.field(s, 'siege')
    fb.op('JNull', reg=sg, offset='np')
    fb.op('Mov', dst=pr, src=b.call('ent.comp.SiegeComponent.getOccupationActionProgress', sg))
    fb.label('np')
    fb.op('JSGte', a=pr, b=_ratio(fb, b, DRAIN_PR), offset='o')
    # militia dead = the fight is won (armies `release` freed then look like dead ones: Smugglers' Ubtar 03:12 and
    # Atreides' Qadlulah 05:06 were cancelled at 7-12% capture with no defender left)
    fb.op('Call1', dst=q, fun=militia, arg0=s)
    fb.op('JSGt', a=q, b=zero, offset='dr_go')
    # ... unless enemy guns cover the target (not its own turrets): the wear is the guns, the militia is long dead
    # (Fremen's Annex of Arkkhelon under Arrakeen's guns: vanilla's balance read 4-23 while 15 armies lost 86%, 5 dead)
    cvn, cvf = fb.reg(cx.t('hl.types.ArrayObj')), fb.reg(cx.t('bool'))
    fb.op('Null', dst=cvn)
    fb.op('Bool', dst=cvf, value=False)
    fb.op('CallN', dst=q, fun=cover, args=[fac, tgt, tgt, cvf, cvn])
    fb.op('JSLte', a=q, b=zero, offset='o')
    fb.label('dr_go')
    # per army (user: judge each army, not everybody at once): an army is worn when its life is below DRAIN_HP and
    # at least DRAIN_DROP below where it stood when first seen in this order's Action (maps `drain0a` army -> life,
    # `drain0o` army -> order). Worn armies leave the order (they heal through vanilla) while the others keep
    # capturing; the order is cancelled only when every army left is worn (Fremen's 8 armies at Atreides' Sad-po,
    # mean life 76% -> 44%, were all called off while some still stood)
    m0a, m0o = _global_map(fb, b, cx, 'drain0a'), _global_map(fb, b, cx, 'drain0o')
    nw, nh = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    lr, st = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=nw, src=b.const('i32', 0))
    fb.op('Mov', dst=nh, src=b.const('i32', 0))
    fb.op('Mov', dst=avg, src=zero)
    fb.op('Mov', dst=h0, src=zero)
    fb.op('Mov', dst=n, src=b.const('i32', 0))
    fb.op('Mov', dst=j, src=b.const('i32', 0))
    b.loop_head('u')
    fb.op('JSGte', a=j, b=b.field(units, 'length'), offset='ud')
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', units, j), 'ent.Army')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=a, offset='u')
    fb.op('Incr', dst=n)
    fb.op('Mov', dst=lr, src=b.call('ent.Entity.get_lifeRatio', a))
    fb.op('Add', dst=avg, a=avg, b=lr)
    ov = b.call('haxe.ds.ObjectMap.get', m0o, fb.dyn(a))
    fb.op('JNotEq', a=ov, b=fb.dyn(o), offset='u_new')
    sv = b.call('haxe.ds.ObjectMap.get', m0a, fb.dyn(a))
    fb.op('JNull', reg=sv, offset='u_new')
    fb.op('SafeCast', dst=st, src=sv)
    fb.op('JAlways', offset='u_has')
    fb.label('u_new')
    b.call('haxe.ds.ObjectMap.set', m0o, fb.dyn(a), fb.dyn(o))
    b.call('haxe.ds.ObjectMap.set', m0a, fb.dyn(a), fb.dyn(lr))
    fb.op('Mov', dst=st, src=lr)
    fb.label('u_has')
    fb.op('Add', dst=h0, a=h0, b=st)
    fb.op('JSGte', a=lr, b=_ratio(fb, b, DRAIN_HP), offset='u_ok')
    fb.op('Sub', dst=q, a=st, b=lr)
    fb.op('JSLt', a=q, b=_ratio(fb, b, DRAIN_DROP), offset='u_ok')
    fb.op('Incr', dst=nw)
    fb.op('JAlways', offset='u')
    fb.label('u_ok')
    fb.op('Incr', dst=nh)
    fb.op('JAlways', offset='u')
    fb.label('ud')
    fb.op('JSLte', a=n, b=b.const('i32', 0), offset='o')
    fb.op('ToSFloat', dst=nf, src=n)
    fb.op('SDiv', dst=avg, a=avg, b=nf)
    fb.op('SDiv', dst=h0, a=h0, b=nf)
    fb.op('JSLte', a=nw, b=b.const('i32', 0), offset='o')
    fb.op('JSLte', a=nh, b=b.const('i32', 0), offset='dr_all')
    # split: the worn ones leave, backwards (removeUnit shrinks the list), never the last army
    ns = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=ns, src=b.const('i32', 0))
    fb.op('Mov', dst=j, src=b.field(units, 'length'))
    b.loop_head('sp')
    fb.op('JSLte', a=j, b=b.const('i32', 0), offset='spd')
    fb.op('Sub', dst=j, a=j, b=b.const('i32', 1))
    x = b.cast(b.call('hl.types.ArrayObj.getDyn', units, j), 'ent.Army')
    fb.op('JNull', reg=x, offset='sp')
    fb.op('JSLte', a=b.field(units, 'length'), b=b.const('i32', 1), offset='spd')
    fb.op('Mov', dst=lr, src=b.call('ent.Entity.get_lifeRatio', x))
    fb.op('JSGte', a=lr, b=_ratio(fb, b, DRAIN_HP), offset='sp')
    sv2 = b.call('haxe.ds.ObjectMap.get', m0a, fb.dyn(x))
    fb.op('JNull', reg=sv2, offset='sp')
    fb.op('SafeCast', dst=st, src=sv2)
    fb.op('Sub', dst=q, a=st, b=lr)
    fb.op('JSLt', a=q, b=_ratio(fb, b, DRAIN_DROP), offset='sp')
    b.call('logic.ai.AIOrder.removeUnit', o, x)
    b.call('haxe.ds.ObjectMap.remove', m0o, fb.dyn(x))
    b.call('haxe.ds.ObjectMap.remove', m0a, fb.dyn(x))
    fb.op('Incr', dst=ns)
    fb.op('JAlways', offset='sp')
    fb.label('spd')
    fb.op('JSLte', a=ns, b=b.const('i32', 0), offset='o')
    _log_ev(fb, b, cx, helpers, 'drain', [('f', fb.get(fac, 'kind')), ('act', 'split'), ('s', tgt), ('hp%', avg),
                                          ('hp0%', h0), ('pr%', pr), ('n', fb.dyn(ns)), ('of', fb.dyn(n))])
    fb.op('JAlways', offset='o')
    fb.label('dr_all')
    nb = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=nb, value=False)
    # a neutral village (militia only): no fear memory, a little more next time (user; `nbump`, common._nbump):
    # Harkonnen's first Annex (Kar-nun) drained at 1:04 kept its only Annex candidate out for 15 min
    _neutral_village(fb, b, cx, tgt, 'dr_lost')
    _nbump_mark(fb, b, cx, fac, tgt, t)
    fb.op('Bool', dst=nb, value=True)
    fb.op('JAlways', offset='dr_log')
    fb.label('dr_lost')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'slost'), fb.dyn(tgt), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'slostf'), fb.dyn(tgt), fb.dyn(fac))
    fb.label('dr_log')
    _log_ev(fb, b, cx, helpers, 'drain', [('f', fb.get(fac, 'kind')), ('s', tgt), ('hp%', avg), ('hp0%', h0),
                                          ('pr%', pr), ('n', fb.dyn(n)), ('bump', nb), ('act', 'cancel')])
    reason = cx.code.types[cx.fn('logic.ai.AIOrder.stop').type.value].definition.args[1].value
    cancel = fb.reg(reason)
    fb.op('MakeEnum', dst=cancel, construct=CANCEL, args=[])
    b.call('logic.ai.AIOrder.stop', o, cancel)
    fb.op('JAlways', offset='end')  # one per tick: the order list changed
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
