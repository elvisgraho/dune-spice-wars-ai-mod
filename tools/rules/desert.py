"""Desert step: an army of ours at a siege target that stands in the deep desert steps onto the village's land and
fights there (no retreat; AI-POLICY §4 supply).

Army.getSupplyChanges multiplies the drain by Army_DeepDesertDailySupplyDrain_MRatio (attribute 455) in a DeepDesert
zone and then by the combat ratio while fighting (both apply), and an army fighting the militia is not occupying, so
it drains (Army.isInHostileZone is false only in occupation range). A village on the edge of a deep desert: 5
Fremen armies went to cap it, 2 stood on the desert side of the militia fight the whole time, losing supply
several times faster than one step closer.

Every CHECK s per faction: our Military orders with a Structure target (sieges, raids) in Engage or Action (not
Regroup: a lone army would step ahead of the pack; not Retreat: never pushed back to the village); each of
their armies that drain (`Army.isInHostileZone`: not occupying in range; fighting or waiting) while standing in a
deep desert zone, with the target in a zone that isn't deep desert, more than DSTEP_IN and at most DSTEP_R away: `doAction("Move", EWorldPosition)` to the point DSTEP_IN from the target on the line towards the
army (in the village's zone, still in the fight), at most every DSTEP_T s per army. Micro re-engages from there.
Logs `dstep` (a, tgt, d). In a trap."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.worm import _move_to


def build_desert_step(cx, helpers):
    """aimod_dstep(mil, dt) (see module doc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = b.field(_state(fb, b, cx), 'time')
    _tick(fb, b, cx, t, CHECK, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    zi = b.const('i32', 0)
    i, j, idx = (fb.reg(cx.t('i32')) for _ in range(3))
    d, px, py, q = (fb.reg(cx.t('f64')) for _ in range(4))
    tgt = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=i, src=b.field(orders, 'length'))
    b.loop_head('o')
    fb.op('JSLte', a=i, b=zi, offset='end')
    fb.op('Sub', dst=i, a=i, b=b.const('i32', 1))
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, i), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset='o')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='o')
    ph = b.field(o, 'phase')
    fb.op('JSLte', a=ph, b=b.const('i32', REGROUP), offset='o')  # Regroup: the pack forms first (no lone step ahead)
    fb.op('JSGt', a=ph, b=b.const('i32', ACTION), offset='o')  # Retreat: never pushed back to the village
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='o')
    fb.op('EnumIndex', dst=idx, value=tt)
    fb.op('JNotEq', a=idx, b=b.const('i32', T_STRUCT), offset='o')
    fb.op('Mov', dst=tgt, src=b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'ent.Entity'))
    fb.op('JNull', reg=tgt, offset='o')
    tz = b.call('ent.Entity.get_zone', tgt)
    fb.op('JNull', reg=tz, offset='o')
    fb.op('JTrue', cond=b.call('ent.Zone.isDeepDesert', tz), offset='o')
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='o')
    a = _army_loop(fb, b, units, b.field(units, 'length'), j, 'u', 'o')
    # siege-position just moved it off enemy guns (rules/spos.py): that wins
    sp = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'sposm'), fb.dyn(a))
    fb.op('JNull', reg=sp, offset='nosp')
    spq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=spq, src=sp)
    fb.op('Sub', dst=spq, a=b.field(_state(fb, b, cx), 'time'), b=spq)
    fb.op('JSLt', a=spq, b=b.const('f64', 2 * SPOS_T), offset='u')
    fb.label('nosp')
    fb.op('JFalse', cond=b.call('ent.Army.isInHostileZone', a), offset='u')  # occupying in range: no drain
    az = b.call('ent.Entity.get_zone', a)
    fb.op('JNull', reg=az, offset='u')
    fb.op('JFalse', cond=b.call('ent.Zone.isDeepDesert', az), offset='u')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', a, tgt))
    fb.op('JSGt', a=d, b=b.const('f64', DSTEP_R), offset='u')
    fb.op('JSLte', a=d, b=b.const('f64', DSTEP_IN), offset='u')
    _skip_striking(fb, b, cx, helpers, a, 'u')  # en-route strike: it fights first
    _throttle(fb, b, cx, 'dstep', a, DSTEP_T, 'u')
    # point DSTEP_IN from the target towards the army
    tx, ty = b.field(tgt, 'posx'), b.field(tgt, 'posy')
    fb.op('Sub', dst=px, a=b.field(a, 'posx'), b=tx)
    fb.op('Sub', dst=py, a=b.field(a, 'posy'), b=ty)
    fb.op('Mov', dst=q, src=b.const('f64', DSTEP_IN))
    fb.op('SDiv', dst=q, a=q, b=d)
    fb.op('Mul', dst=px, a=px, b=q)
    fb.op('Mul', dst=py, a=py, b=q)
    fb.op('Add', dst=px, a=px, b=tx)
    fb.op('Add', dst=py, a=py, b=ty)
    ok = _move_to(fb, b, cx, a, px, py, fac)
    _log_ev(fb, b, cx, helpers, 'dstep', [('f', fb.get(fac, 'kind')), ('a', a), ('tgt', tgt), ('d', d),
                                          ('ok', ok)])
    fb.op('JAlways', offset='u')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
