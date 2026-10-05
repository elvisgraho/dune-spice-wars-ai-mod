"""Bunker split: silence the bunker partner of a village we capture (user, AI-POLICY "Bunker split").

Two villages close together cover each other: a village under siege has silent turrets, but its partner's battery
keeps firing into the occupation. Harkonnen annexed Atreides' Hay-Al'dak (9 armies, 18:46) while Tad-ras, 55 away,
shot into the whole occupation range (spos had nowhere to step to); 8 of 9 armies died. User: "it should have
liberated it too".

aimod_bunker(mil, dt), tick chain every BSPLIT_CHECK s: our Military Annex / Liberate / Pillage orders on a structure A in
Engage (walking in under the guns: Harkonnen's Aegtah, user) or Action with 2+ armies, once per order (map `bspl`): the
nearest village B of an at-war faction (not a main base, not under any siege) within COVER_R of A whose turrets cover
A (aimod_cover1 > 0). The order's ground armies nearest B go to a new Military order ArmySiege on B (Liberate when
available, else Pillage) of priority BSPLIT_PRIO, above the capture's: addOrder moves them itself (it refuses armies
of an order with priority >= its own, and takes only one army per order: each leaves through
AIOrders.removeUnitFromOrders first; before Action the removal runs through take-keep). Nearest first until
BSPLIT_K x B's militia (aimod_militia), at least one army, at most half the order in Action, 1 / BSPLIT_KEEP_SHARE of an
order of BSPLIT_KEEP_MIN+ in Engage (take-keep's limit; more would cancel the capture). Short of the militia: no split
(log why weak; in Engage tried again in Action). Hostile armies at A or able to reach it (aimod_threat within
REACT_R): no split yet (log why relief, re-checked every pass: a split in front of a relief lost both halves). The split order goes into map `bspo` (split -> capture): raid's abort
pass leaves it alone (it read the defenders fighting the capture next door as the split's enemy and aborted it `weak`
0.27 s after the split). Logs `bsplit` (tgt, b, n, of, sa, M, mil, ok). Fails safe: in a trap."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.strat import _has_action

BSPLIT_KINDS = ('Annex', 'Liberate', 'Pillage')


def build_bunker(cx, helpers, pw, militia):
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    state = _state(fb, b, cx)
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(state, 'time'))
    _tick(fb, b, cx, t, BSPLIT_CHECK, 'end')
    orders_obj = b.field(ctrl, 'aiOrders')
    orders = b.field(orders_obj, 'orders')
    fb.op('JNull', reg=orders, offset='end')
    villages = b.field(state, 'villages')
    fb.op('JNull', reg=villages, offset='end')
    bspl = _global_map(fb, b, cx, 'bspl')
    k, ix, vi, j, un, half, cnt = (fb.reg(cx.t('i32')) for _ in range(7))
    d, bd, p, need, got, c1 = (fb.reg(cx.t('f64')) for _ in range(6))
    ae, be, ve, ue, near = (fb.reg(cx.t('ent.Entity')) for _ in range(5))
    bst = fb.reg(cx.t('ent.Structure'))
    no_arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=no_arr)
    kinds = [fb.dyn(fb.string(kd)) for kd in BSPLIT_KINDS]
    fb.op('Mov', dst=k, src=b.field(orders, 'length'))
    b.loop_head('o')
    fb.op('JSLte', a=k, b=b.const('i32', 0), offset='end')
    fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, k), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset='o')
    fb.op('EnumIndex', dst=ix, value=b.field(o, 'type'))
    fb.op('JNotEq', a=ix, b=b.const('i32', MILITARY), offset='o')
    ph = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=ph, src=b.field(o, 'phase'))
    fb.op('JEq', a=ph, b=b.const('i32', ACTION), offset='phok')
    fb.op('JNotEq', a=ph, b=b.const('i32', REGROUP + 1), offset='o')  # Engage: walking in under the guns already
    fb.label('phok')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='o')
    fb.op('EnumIndex', dst=ix, value=tt)
    fb.op('JNotEq', a=ix, b=b.const('i32', T_STRUCT), offset='o')
    fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', bspl, fb.dyn(o)), offset='o')  # once per order
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='o')
    fb.op('Mov', dst=un, src=b.field(units, 'length'))
    fb.op('JSLt', a=un, b=b.const('i32', 2), offset='o')
    sa = b.cast(fb.get(o, 'siegeAction'), 'String')
    fb.op('JNull', reg=sa, offset='o')
    for kd in kinds:
        nxt = _uid('kd')
        fb.op('JNotEq', a=b.call('String.__compare', sa, kd), b=b.const('i32', 0), offset=nxt)
        fb.op('JAlways', offset='kok')
        fb.label(nxt)
    fb.op('JAlways', offset='o')
    fb.label('kok')
    a_s = b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'ent.Structure')
    fb.op('JNull', reg=a_s, offset='o')
    fb.op('Mov', dst=ae, src=a_s)
    # B: the nearest at-war village within COVER_R of A, not besieged, whose guns cover A
    fb.op('Null', dst=be)
    fb.op('Mov', dst=bd, src=b.const('f64', COVER_R))
    fb.op('Mov', dst=vi, src=b.const('i32', 0))
    b.loop_head('v')
    fb.op('JSGte', a=vi, b=b.field(villages, 'length'), offset='vdone')
    v = b.cast(b.call('hl.types.ArrayObj.getDyn', villages, vi), 'ent.Structure')
    fb.op('Incr', dst=vi)
    fb.op('JNull', reg=v, offset='v')
    fb.op('Mov', dst=ve, src=v)
    fb.op('JEq', a=ve, b=ae, offset='v')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', v), offset='v')
    vo = b.call('ent.Entity.get_owner', ve)
    fb.op('JNull', reg=vo, offset='v')
    fb.op('JEq', a=vo, b=fac, offset='v')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, vo), offset='v')
    vsg = b.field(v, 'siege')
    fb.op('JNull', reg=vsg, offset='v')
    fb.op('JNotNull', reg=b.field(vsg, 'besiegingFaction'), offset='v')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', ve, ae))
    fb.op('JSGte', a=d, b=bd, offset='v')
    fb.op('Call3', dst=c1, fun=helpers['cover1'], arg0=ae, arg1=v, arg2=no_arr)
    fb.op('JSLte', a=c1, b=b.const('f64', 0), offset='v')
    fb.op('Mov', dst=bd, src=d)
    fb.op('Mov', dst=be, src=ve)
    fb.op('JAlways', offset='v')
    fb.label('vdone')
    fb.op('JNull', reg=be, offset='o')
    fb.op('Mov', dst=bst, src=b.cast(be, 'ent.Structure'))
    # siege action on B: Liberate when available, else Pillage, else none
    act = fb.reg(cx.t('String'))
    fb.op('Mov', dst=act, src=fb.string('Liberate'))
    _has_action(fb, b, cx, bst, fac, 'Liberate', 'actok', 'trypil')
    fb.label('trypil')
    fb.op('Mov', dst=act, src=fb.string('Pillage'))
    _has_action(fb, b, cx, bst, fac, 'Pillage', 'actok', 'o')
    fb.label('actok')
    # armies: nearest ground ones to B until BSPLIT_K x its militia, >= 1, <= half the order
    fb.op('Call1', dst=need, fun=militia, arg0=bst)
    fb.op('Mul', dst=need, a=need, b=_ratio(fb, b, BSPLIT_K))
    fb.op('SDiv', dst=half, a=un, b=b.const('i32', 2))
    # Engage: addOrder takes them from the capture through take-keep (rules/orders.py), which allows at most 1 /
    # KEEP_SHARE of an order of KEEP_MIN+ armies before Action (more would cancel the capture)
    fb.op('JEq', a=ph, b=b.const('i32', ACTION), offset='capok')
    fb.op('JSLt', a=un, b=b.const('i32', BSPLIT_KEEP_MIN), offset='o')
    fb.op('SDiv', dst=half, a=un, b=b.const('i32', BSPLIT_KEEP_SHARE))
    fb.label('capok')
    arr = _new_array(fb, b, cx)
    fb.op('Mov', dst=got, src=b.const('f64', 0))
    fb.op('Mov', dst=cnt, src=b.const('i32', 0))
    b.loop_head('pick')
    fb.op('JSGte', a=cnt, b=half, offset='picked')
    fb.op('JSGt', a=cnt, b=b.const('i32', 0), offset='pneed')
    fb.op('JAlways', offset='pfind')
    fb.label('pneed')
    fb.op('JSGte', a=got, b=need, offset='picked')
    fb.label('pfind')
    fb.op('Null', dst=near)
    fb.op('Mov', dst=bd, src=b.const('f64', 1 << 30))
    u = _army_loop(fb, b, units, b.field(units, 'length'), j, 'u', 'udone')
    fb.op('JTrue', cond=b.call('ent.Unit.isFlying', u), offset='u')
    fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', arr, fb.dyn(u)), offset='u')
    fb.op('Mov', dst=ue, src=u)
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', ue, be))
    # only armies already at the fight: a straggler 308 from B (Fremen's F_Hero_1 walking in to Hul-ram) got a split
    # vanilla cancelled in Waiting at once (supply / path)
    fb.op('JSGt', a=d, b=b.const('f64', BSPLIT_R), offset='u')
    fb.op('JSGte', a=d, b=bd, offset='u')
    fb.op('Mov', dst=bd, src=d)
    fb.op('Mov', dst=near, src=ue)
    fb.op('JAlways', offset='u')
    fb.label('udone')
    fb.op('JNull', reg=near, offset='picked')
    b.call('hl.types.ArrayObj.push', arr, fb.dyn(near))
    fb.op('Incr', dst=cnt)
    fb.op('Call1', dst=p, fun=pw, arg0=b.cast(near, 'ent.Army'))
    fb.op('Add', dst=got, a=got, b=p)
    fb.op('JAlways', offset='pick')
    fb.label('picked')
    fb.op('JSLte', a=cnt, b=b.const('i32', 0), offset='o')
    # half the order can't beat B's militia: no split (one 39k army sent at a 100k militia would just die)
    fb.op('JSGte', a=got, b=need, offset='strong')
    _log_ev(fb, b, cx, helpers, 'bsplit', [('f', fb.get(fac, 'kind')), ('tgt', ae), ('b', be), ('n', fb.dyn(cnt)),
                                           ('of', fb.dyn(un)), ('M', got), ('mil', need), ('why', 'weak')])
    fb.op('JNotEq', a=ph, b=b.const('i32', ACTION), offset='o')  # Engage: try again in Action (half the order)
    b.call('haxe.ds.ObjectMap.set', bspl, fb.dyn(o), fb.dyn(t))
    fb.op('JAlways', offset='o')
    fb.label('strong')
    # relief: a hostile army at A or able to reach it (aimod_threat within REACT_R, release's danger radius): keep the
    # force together, re-checked next pass (Atreides' Sandwan raid, 8 armies in Action at 6.8:1, split 3 to Ullab at
    # 69:50; Fremen's relief arrived, Sandwan 0.31 and Ullab 131k vs 154k: both lost, match 2026-10-04 20:27)
    rel = fb.reg(cx.t('f64'))
    fb.op('Call3', dst=rel, fun=helpers['threat'], arg0=fac, arg1=ae, arg2=b.const('f64', REACT_R))
    fb.op('JSLte', a=rel, b=b.const('f64', 0), offset='norel')
    _throttle(fb, b, cx, 'bsrel', o, 30, 'o')
    _log_ev(fb, b, cx, helpers, 'bsplit', [('f', fb.get(fac, 'kind')), ('tgt', ae), ('b', be), ('n', fb.dyn(cnt)),
                                           ('of', fb.dyn(un)), ('M', got), ('H', rel), ('why', 'relief')])
    fb.op('JAlways', offset='o')
    fb.label('norel')
    # addOrder takes the armies from the capture itself when the split's priority is higher (Annex 3; it refused
    # armies of an order with priority >= its own: all 5 first splits returned null); before Action through take-keep
    b.call('haxe.ds.ObjectMap.set', bspl, fb.dyn(o), fb.dyn(t))
    # ... but addOrder takes only the first of them from each order (its scan breaks after one unit): the second
    # stayed in both and vanilla cancelled Harkonnen's 11-army Pillage of Nunval 0.15 s later. Each leaves through
    # removeUnitFromOrders first (take-keep guards it before Action)
    rfo = cx.fn('logic.ai.AIOrders.removeUnitFromOrders')
    rfu = fb.reg(cx.code.types[rfo.type.value].definition.args[1].value)
    jr = fb.reg(cx.t('i32'))
    ra = _army_loop(fb, b, arr, b.field(arr, 'length'), jr, 'rm', 'rmdone')
    fb.op('Mov', dst=rfu, src=ra)
    fb.op('Call2', dst=void, fun=rfo.findex.value, arg0=orders_obj, arg1=rfu)
    fb.op('JAlways', offset='rm')
    fb.label('rmdone')
    add = cx.fn('logic.ai.AIOrders.addOrder')
    at = [a_.value for a_ in cx.code.types[add.type.value].definition.args]
    kind = fb.reg(cx.t('logic.ai.AIOrderType'))
    fb.op('MakeEnum', dst=kind, construct=MILITARY, args=[])
    mm, om = _new_array(fb, b, cx), _new_array(fb, b, cx)
    nulls = []
    for n in (9, 10):  # data, onComplete
        rr = fb.reg(at[n])
        fb.op('Null', dst=rr)
        nulls.append(rr)
    res = fb.reg(cx.t('logic.ai.AIOrder'))
    fb.op('CallN', dst=res, fun=helpers.get('addOrder', add.findex.value),
          args=[orders_obj, kind, b.const('i32', BSPLIT_PRIO), arr, be, fb.string('ArmySiege'), act, mm, om] + nulls)
    ok = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=ok, value=False)
    fb.op('JNull', reg=res, offset='lg')
    fb.op('Bool', dst=ok, value=True)
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'bspo'), fb.dyn(res), fb.dyn(o))  # raid's abort skips it
    fb.label('lg')
    _log_ev(fb, b, cx, helpers, 'bsplit', [('f', fb.get(fac, 'kind')), ('tgt', ae), ('b', be), ('n', fb.dyn(cnt)),
                                           ('of', fb.dyn(un)), ('sa', act), ('M', got), ('mil', need), ('ok', ok)])
    fb.op('JAlways', offset='o')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
