"""Strand: idle armies left on hostile land walk home (AI-POLICY §5a goal 1: armies never starve outside our land).

Vanilla has a gap: `checkPatrols` takes only idle armies at 100% life AND supply, and `checkUnits` sends Resupply only
below 90%. An idle army at 90-99% supply in a neutral or enemy zone gets no order and stands there draining supply
(3 full-health Fremen stood ~55 s next to Harkonnen's Dal-Al'tar after auto-fighting a raider, while a Harkonnen hunt
on them gathered).

Every START s per faction, after hunt and raid (they claim armies first): each of our armies in no order at all
(strand variant of aimod_free: any life / supply, a Patrol order counts as busy, never a harvester), not fighting,
with `Army.isInHostileZone` gets a vanilla-style Patrol (prio 0, "Move") to the nearest structure on our land, keyed
like safe-heal: aimod_unsafe level 1 (contested) costs DETOUR, level 2 (overwhelming) is skipped. Not when the army is
within AT_HOME_R of it (the Patrol would end at once: re-issue loop). Patrol armies stay free
for hunts, raids and sieges; once home the army is off hostile land, so it is never re-issued (no loop).
Logs `strand` (a army, s target, d distance). Fails safe: in a trap, nothing issued on error."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def build_strand(cx, helpers, idle, unsafe):
    """aimod_strand(mil, dt) (see module doc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = b.field(_state(fb, b, cx), 'time')
    _tick(fb, b, cx, t, START, 'end')
    orders_obj = b.field(ctrl, 'aiOrders')
    orders = b.field(orders_obj, 'orders')
    fb.op('JNull', reg=orders, offset='end')
    structs = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=structs, offset='end')
    sn = b.field(structs, 'length')
    my_armies, mlen = _my_armies(fb, b, fac, 'end')
    zi = b.const('i32', 0)
    detour2, big = b.const('f64', DETOUR * DETOUR), b.const('f64', 1 << 30)
    t_false = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_false, value=False)
    i, k, lvl = fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    ok = fb.reg(cx.t('bool'))
    key, bk, d, bd = (fb.reg(cx.t('f64')) for _ in range(4))
    best = fb.reg(cx.t('ent.Structure'))
    add = cx.fn('logic.ai.AIOrders.addOrder')
    at = [a.value for a in cx.code.types[add.type.value].definition.args]

    a = _army_loop(fb, b, my_armies, mlen, i, 'army', 'end')
    fb.op('Call2', dst=ok, fun=idle, arg0=a, arg1=orders)
    fb.op('JFalse', cond=ok, offset='army')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', a), offset='army')
    fb.op('JFalse', cond=b.call('ent.Army.isInHostileZone', a), offset='army')
    # nearest structure on our land, safe-heal penalties
    fb.op('Null', dst=best)
    fb.op('Mov', dst=bk, src=big)
    fb.op('Mov', dst=k, src=zi)
    b.loop_head('st')
    fb.op('JSGte', a=k, b=sn, offset='stdone')
    s = b.cast(b.call('hl.types.ArrayObj.getDyn', structs, k), 'ent.Structure')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=s, offset='st')
    z = b.call('ent.Entity.get_zone', s)
    fb.op('JNull', reg=z, offset='st')
    fb.op('JNotEq', a=b.field(z, 'owner'), b=fac, offset='st')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', a, s))
    fb.op('Mul', dst=key, a=d, b=d)
    nf = fb.reg(cx.t('ent.Faction'))
    fb.op('Null', dst=nf)  # ownerless structure: judged for the army's owner
    fb.op('Call4', dst=lvl, fun=unsafe, arg0=s, arg1=a, arg2=t_false, arg3=nf)
    fb.op('JSGt', a=lvl, b=b.const('i32', 1), offset='st')  # overwhelming: never walk into it
    fb.op('JSLte', a=lvl, b=zi, offset='safe')
    fb.op('Add', dst=key, a=key, b=detour2)
    fb.label('safe')
    fb.op('JSGte', a=key, b=bk, offset='st')
    fb.op('Mov', dst=bk, src=key)
    fb.op('Mov', dst=bd, src=d)
    fb.op('Mov', dst=best, src=s)
    fb.op('JAlways', offset='st')
    fb.label('stdone')
    fb.op('JNull', reg=best, offset='army')
    # already next to it (a zone border runs close to our village): a Patrol there ends at once and was re-issued
    # every scan; the structure's supply radius covers it anyway
    fb.op('JSLte', a=bd, b=b.const('f64', AT_HOME_R), offset='army')
    # vanilla checkPatrols order: Patrol(village), prio 0, "Move", no missions
    arr = _new_array(fb, b, cx)
    b.call('hl.types.ArrayObj.push', arr, fb.dyn(a))
    kind = fb.reg(cx.t('logic.ai.AIOrderType'))
    fb.op('MakeEnum', dst=kind, construct=PATROL, args=[best])
    tgt = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=tgt, src=best)
    nulls = []
    for n in (6, 7, 8, 9, 10):  # sa, mm, om, data, onComplete
        r = fb.reg(at[n])
        fb.op('Null', dst=r)
        nulls.append(r)
    res = fb.reg(cx.t('logic.ai.AIOrder'))
    fb.op('CallN', dst=res, fun=helpers.get('addOrder', add.findex.value),
          args=[orders_obj, kind, zi, arr, tgt, fb.string('Move')] + nulls)
    fb.op('Bool', dst=ok, value=False)
    fb.op('JNull', reg=res, offset='lg')
    fb.op('Bool', dst=ok, value=True)
    fb.label('lg')
    _log_ev(fb, b, cx, helpers, 'strand', [('f', fb.get(fac, 'kind')), ('a', a), ('s', tgt), ('d', bd), ('ok', ok)])
    fb.op('JAlways', offset='army')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
