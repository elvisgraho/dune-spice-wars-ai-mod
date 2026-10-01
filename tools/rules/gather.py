"""Gather: our armies of one attack arrive together (AI-POLICY §1.6 concentrate).

Vanilla Regroup is not a gathering: checkRegroupOrder counts an army as arrived at the second-to-last step of its own
path, so armies coming from different sides leave Regroup 60-120 apart; Engage then sends each straight in and the
nearest fights alone (Harkonnen hunt at Annaha: the H_Elite fought the A_Demo ~15 s alone, hp 100 -> 68, before the
H_Demo and H_Soldier arrived; Harkonnen Annex of Tuo-lon: one H_Trooper fought the militia ~20 s alone, hp 100 -> 40).

Every GATHER_T s per faction: our Military orders in Engage (phase 4); target = getTarget() (village, or hunt
group). Armies of the order within GATHER_ORD_R of the target count (farther ones are stragglers: not waited for);
dmax = the farthest of them. An army more than GATHER_GAP closer than dmax, not fighting and more than GATHER_MIN
from the target (out of contact: never stopped next to the prey or the militia) and not draining in the deep desert
(desert-step moves that one onto the village's side), on a hunt whose moving prey isn't heading towards it (a
fleeing prey isn't waited for), is held: doAction("Move") to its own
position, map `ghold` army -> time refreshed every pass. The checkEngageOrder getActionDesc call is wrapped: a held
army (refreshed within 2 x GATHER_T) reads as busy (a remembered non-null action desc) so vanilla doesn't re-send it;
once released vanilla re-issues the order's action at once. An order holds for at most GATHER_MAX s in all (map
`gstart`): a far laggard can't stall the attack. Logs `gather` (a, d, dmax, n) when an army is first held."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.worm import _move_to
from rules.world import _approaching


def build_gather(cx, helpers):
    """aimod_gather(mil, dt) (see module doc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = b.field(_state(fb, b, cx), 'time')
    _tick(fb, b, cx, t, GATHER_T, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    hold, gstart = _global_map(fb, b, cx, 'ghold'), _global_map(fb, b, cx, 'gstart')
    zi = b.const('i32', 0)
    i, j, idx, cnt = (fb.reg(cx.t('i32')) for _ in range(4))
    d, dmax, q, gs = (fb.reg(cx.t('f64')) for _ in range(4))
    gr, gmin, gap = b.const('f64', GATHER_ORD_R), b.const('f64', GATHER_MIN), b.const('f64', GATHER_GAP)
    tgt = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=i, src=b.field(orders, 'length'))
    b.loop_head('o')
    fb.op('JSLte', a=i, b=zi, offset='end')
    fb.op('Sub', dst=i, a=i, b=b.const('i32', 1))
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, i), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset='o')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='o')
    fb.op('JNotEq', a=b.field(o, 'phase'), b=b.const('i32', REGROUP + 1), offset='o')
    fb.op('Mov', dst=tgt, src=b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'ent.Entity'))
    fb.op('JNull', reg=tgt, offset='o')
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='o')
    un = b.field(units, 'length')
    fb.op('JSLte', a=un, b=b.const('i32', 1), offset='o')
    # hunt on a moving prey: hold only while it comes towards us (waiting lets a fleeing prey escape)
    prey = fb.reg(cx.t('ent.Army'))
    fb.op('Null', dst=prey)
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='np')
    fb.op('EnumIndex', dst=idx, value=tt)
    fb.op('JNotEq', a=idx, b=b.const('i32', T_GROUP), offset='np')
    gents = b.cast(fb.get(tgt, 'entities'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=gents, offset='np')
    fb.op('JSLte', a=b.field(gents, 'length'), b=zi, offset='np')
    fb.op('Mov', dst=prey, src=b.cast(b.call('hl.types.ArrayObj.getDyn', gents, zi), 'ent.Army'))
    fb.op('JNull', reg=prey, offset='np')
    fb.op('JTrue', cond=b.call('ent.Unit.isMoving', prey), offset='np')
    fb.op('Null', dst=prey)  # standing still: no check
    fb.label('np')
    # hold budget per order
    st = b.call('haxe.ds.ObjectMap.get', gstart, fb.dyn(o))
    fb.op('JNull', reg=st, offset='fresh')
    fb.op('SafeCast', dst=gs, src=st)
    fb.op('Sub', dst=q, a=t, b=gs)
    fb.op('JSGt', a=q, b=b.const('f64', GATHER_MAX), offset='o')
    fb.label('fresh')
    # farthest counted army
    fb.op('Mov', dst=dmax, src=b.const('f64', 0))
    fb.op('Mov', dst=cnt, src=zi)
    a = _army_loop(fb, b, units, un, j, 'm', 'mdone')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', a, tgt))
    fb.op('JSGt', a=d, b=gr, offset='m')
    fb.op('Incr', dst=cnt)
    fb.op('JSLte', a=d, b=dmax, offset='m')
    fb.op('Mov', dst=dmax, src=d)
    fb.op('JAlways', offset='m')
    fb.label('mdone')
    fb.op('JSLte', a=cnt, b=b.const('i32', 1), offset='o')
    # hold the leaders
    a2 = _army_loop(fb, b, units, un, j, 'h', 'o')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', a2, tgt))
    fb.op('JSGt', a=d, b=gr, offset='h')
    fb.op('JSLte', a=d, b=gmin, offset='h')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', a2), offset='h')
    fb.op('JFalse', cond=b.call('ent.Army.isInHostileZone', a2), offset='gdz')
    gz = b.call('ent.Entity.get_zone', a2)
    fb.op('JNull', reg=gz, offset='gdz')
    fb.op('JTrue', cond=b.call('ent.Zone.isDeepDesert', gz), offset='h')  # draining x deep desert: desert-step's
    fb.label('gdz')
    fb.op('Add', dst=q, a=d, b=gap)
    fb.op('JSGte', a=q, b=dmax, offset='h')
    fb.op('JNull', reg=prey, offset='pok')
    pd = b.call('ent.Entity.getDistTo', prey, a2)
    _approaching(fb, b, cx, prey, a2, pd, 'h')  # the prey moves away from this leader: no wait
    fb.label('pok')
    # first hold of this order starts its budget
    fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', gstart, fb.dyn(o)), offset='budget')
    b.call('haxe.ds.ObjectMap.set', gstart, fb.dyn(o), fb.dyn(t))
    fb.label('budget')
    was = b.call('haxe.ds.ObjectMap.get', hold, fb.dyn(a2))
    b.call('haxe.ds.ObjectMap.set', hold, fb.dyn(a2), fb.dyn(t))
    fb.op('JNull', reg=was, offset='stop')
    fb.op('SafeCast', dst=q, src=was)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSLte', a=q, b=b.const('f64', 2 * GATHER_T), offset='h')  # still held: nothing to re-issue
    fb.label('stop')
    _move_to(fb, b, cx, a2, b.field(a2, 'posx'), b.field(a2, 'posy'), fac)
    _log_ev(fb, b, cx, helpers, 'gather', [('f', fb.get(fac, 'kind')), ('a', a2), ('tgt', tgt), ('d', d),
                                           ('dmax', dmax), ('n', cnt)])
    fb.op('JAlways', offset='h')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


def gather_busy(cx, new_ids):
    """The single getActionDesc call in checkEngageOrder -> wrapper: a non-null desc is remembered (map `gdesc`, key
    0); a null one for an army held by aimod_gather (map `ghold` refreshed within 2 x GATHER_T) returns the remembered
    desc, so vanilla doesn't re-send the army to the target. Original otherwise / on error."""
    fn = cx.fn('logic.ai.AIOrders.checkEngageOrder')
    gad = cx.fn('ent.Entity.getActionDesc')
    sites = [op for op in fn.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == gad.findex.value]
    if len(sites) != 1:
        raise ValueError(f'gather: expected 1 getActionDesc call in checkEngageOrder, found {len(sites)}')
    ft = cx.code.types[gad.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=gad.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('Call1', dst=res, fun=gad.findex.value, arg0=0)
    guard = fb.try_()
    dm = _global_map(fb, b, cx, 'gdesc')
    key = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=key, src=0)
    fb.op('JNull', reg=res, offset='isnull')
    b.call('haxe.ds.ObjectMap.set', dm, fb.dyn(_state(fb, b, cx)), fb.dyn(res))
    fb.op('JAlways', offset='end')
    fb.label('isnull')
    hv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'ghold'), fb.dyn(key))
    fb.op('JNull', reg=hv, offset='end')
    q = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=q, src=hv)
    fb.op('Sub', dst=q, a=b.field(_state(fb, b, cx), 'time'), b=q)
    fb.op('JSGt', a=q, b=b.const('f64', 2 * GATHER_T), offset='end')
    keep = b.call('haxe.ds.ObjectMap.get', dm, fb.dyn(_state(fb, b, cx)))
    fb.op('JNull', reg=keep, offset='end')
    fb.op('SafeCast', dst=res, src=keep)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    sites[0].df['fun'].value = w
    new_ids.add(w)
    return {'gather-busy': 1}
