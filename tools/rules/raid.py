"""Raid: opportunistic pillage of an at-war village next to our armies (AI-POLICY §5a goal 5b).

Vanilla pillages only from its Pillage gauge, which barely rises, and only with idle armies at >= 90% supply: a
stack standing next to a weakly held enemy village walked home to resupply instead (Fremen at Od-lulah). A pillage
refills OCC_REFILL of max supply and occupying doesn't drain, so a raid on the way home is often cheaper than the walk.

Every START s per faction, at most one launch per RAID_GAP s, never while defending (aimod_defend):
- candidates: villages owned by a faction at war with us, not besieged, not a main base, "Pillage" among
  SiegeComponent.getAvailableOccupationActions(us) (faction rules, e.g. Atreides can't pillage), and no Military order
  of ours on it;
- force: our armies within RAID_R that are free for a raid (aimod_free variant: life >= RAID_LIFE, any supply, a
  Resupply order doesn't count as busy) and pass the raid supply budget (aimod_raidsup);
- test: their power (+ our turret cover) >= ENTER x (at-war threat within LOCAL + enemy turret cover + the village's
  militia) / terrain: "no real threat" in the policy's own measure;
- pick: the candidate nearest to one of our armies; order = Military prio 1 (Pillage aiPrio) ArmySiege "Pillage",
  all those armies. Vanilla then runs it like its own pillage (phases, fight retreat, cancel on peace).
Logs `raid` (starts). Fails safe: in a trap, nothing launched on error."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def build_raid(cx, helpers, pw, raidable, threat, land, terrain, raidsup, cover, defend, militia):
    """aimod_raid(mil, dt) (see module doc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    state = _state(fb, b, cx)
    t = b.field(state, 'time')
    _tick(fb, b, cx, t, START, 'end')
    # commit gap and defensive posture
    lastmap = _global_map(fb, b, cx, 'raid')
    last = b.call('haxe.ds.ObjectMap.get', lastmap, fb.dyn(fac))
    lastf = fb.reg(cx.t('f64'))
    fb.op('JNull', reg=last, offset='gapok')
    fb.op('SafeCast', dst=lastf, src=last)
    fb.op('Sub', dst=lastf, a=t, b=lastf)
    fb.op('JSLt', a=lastf, b=b.const('f64', RAID_GAP), offset='end')
    fb.label('gapok')
    dfs = fb.reg(cx.t('ent.Structure'))
    fb.op('Call1', dst=dfs, fun=defend, arg0=fac)
    fb.op('JNotNull', reg=dfs, offset='end')
    orders_obj = b.field(ctrl, 'aiOrders')
    orders = b.field(orders_obj, 'orders')
    fb.op('JNull', reg=orders, offset='end')
    on = b.field(orders, 'length')
    villages = b.field(state, 'villages')
    fb.op('JNull', reg=villages, offset='end')
    vn = b.field(villages, 'length')
    my_armies, mlen = _my_armies(fb, b, fac, 'end')

    zi, zero, big = b.const('i32', 0), b.const('f64', 0), b.const('f64', 1 << 30)
    raid_r, local = b.const('f64', RAID_R), b.const('f64', LOCAL)
    enter = _ratio(fb, b, ENTER)
    t_false, t_true = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_false, value=False)
    fb.op('Bool', dst=t_true, value=True)
    no_arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=no_arr)
    pillage = fb.dyn(fb.string('Pillage'))
    i, j, k, idx = (fb.reg(cx.t('i32')) for _ in range(4))
    h, m, p, q, sd, dmin, dy, tf = (fb.reg(cx.t('f64')) for _ in range(8))
    ok = fb.reg(cx.t('bool'))
    ve = fb.reg(cx.t('ent.Entity'))
    best = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=best)
    best_d, best_h, best_m, best_sd = b.const('f64', 1 << 30), b.const('f64', 0), b.const('f64', 0), b.const('f64', 0)

    fb.op('Mov', dst=i, src=zi)
    b.loop_head('v')
    fb.op('JSGte', a=i, b=vn, offset='vdone')
    v = b.cast(b.call('hl.types.ArrayObj.getDyn', villages, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=v, offset='v')
    fb.op('Mov', dst=ve, src=v)
    # an at-war faction's village, not a main base, nobody besieging it
    vo = b.call('ent.Entity.get_owner', ve)
    fb.op('JNull', reg=vo, offset='v')
    fb.op('JEq', a=vo, b=fac, offset='v')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, vo), offset='v')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', v), offset='v')
    sg = b.field(v, 'siege')
    fb.op('JNull', reg=sg, offset='v')
    fb.op('JNotNull', reg=b.field(sg, 'besiegingFaction'), offset='v')
    # the game lets us pillage it (faction rules: Atreides can't)
    acts = b.call('ent.comp.SiegeComponent.getAvailableOccupationActions', sg, fac)
    fb.op('JNull', reg=acts, offset='v')
    an = b.field(acts, 'length')
    fb.op('Mov', dst=j, src=zi)
    b.loop_head('act')
    fb.op('JSGte', a=j, b=an, offset='v')
    a_s = b.cast(b.call('hl.types.ArrayObj.getDyn', acts, j), 'String')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=a_s, offset='act')
    fb.op('JNotEq', a=b.call('String.__compare', a_s, pillage), b=zi, offset='act')
    # not already one of our Military targets
    fb.op('Mov', dst=j, src=zi)
    b.loop_head('o')
    fb.op('JSGte', a=j, b=on, offset='odone')
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, j), 'logic.ai.AIOrder')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=o, offset='o')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='o')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='o')
    fb.op('EnumIndex', dst=idx, value=tt)
    fb.op('JNotEq', a=idx, b=b.const('i32', T_STRUCT), offset='o')
    fb.op('JEq', a=b.call('logic.ai.AIOrder.getTarget', o), b=ve, offset='v')
    fb.op('JAlways', offset='o')
    fb.label('odone')
    # our raid force there (+ our turret cover), with the supply for the raid and the way home
    fb.op('Call2', dst=sd, fun=land, arg0=fac, arg1=ve)
    fb.op('CallN', dst=m, fun=cover, args=[fac, ve, ve, t_true, no_arr])
    fb.op('Mov', dst=dmin, src=big)
    y = _army_loop(fb, b, my_armies, mlen, k, 'y', 'ydone')
    fb.op('Mov', dst=dy, src=b.call('ent.Entity.getDistTo', y, ve))
    fb.op('JSGt', a=dy, b=raid_r, offset='y')
    fb.op('Call2', dst=ok, fun=raidable, arg0=y, arg1=orders)
    fb.op('JFalse', cond=ok, offset='y')
    fb.op('Call3', dst=ok, fun=raidsup, arg0=y, arg1=dy, arg2=sd)
    fb.op('JFalse', cond=ok, offset='y')
    fb.op('Call1', dst=p, fun=pw, arg0=y)
    fb.op('Add', dst=m, a=m, b=p)
    fb.op('JSGte', a=dy, b=dmin, offset='y')
    fb.op('Mov', dst=dmin, src=dy)
    fb.op('JAlways', offset='y')
    fb.label('ydone')
    fb.op('JSGte', a=dmin, b=big, offset='v')
    # their side: armies in reach, turrets covering it, its militia
    fb.op('Call3', dst=h, fun=threat, arg0=fac, arg1=ve, arg2=local)
    fb.op('CallN', dst=q, fun=cover, args=[fac, ve, ve, t_false, no_arr])
    fb.op('Add', dst=h, a=h, b=q)
    fb.op('Call1', dst=q, fun=militia, arg0=v)
    fb.op('Add', dst=h, a=h, b=q)
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', ve))
    fb.op('Mul', dst=q, a=h, b=enter)
    fb.op('SDiv', dst=q, a=q, b=tf)
    fb.op('JSLt', a=m, b=q, offset='v')
    fb.op('JSGte', a=dmin, b=best_d, offset='v')
    for dst, src in ((best, ve), (best_d, dmin), (best_h, h), (best_m, m), (best_sd, sd)):
        fb.op('Mov', dst=dst, src=src)
    fb.op('JAlways', offset='v')
    fb.label('vdone')
    fb.op('JNull', reg=best, offset='end')

    # launch: every raid-ready army in reach of the chosen village
    arr = _new_array(fb, b, cx)
    y = _army_loop(fb, b, my_armies, mlen, k, 'g', 'gdone')
    fb.op('Mov', dst=dy, src=b.call('ent.Entity.getDistTo', y, best))
    fb.op('JSGt', a=dy, b=raid_r, offset='g')
    fb.op('Call2', dst=ok, fun=raidable, arg0=y, arg1=orders)
    fb.op('JFalse', cond=ok, offset='g')
    fb.op('Call3', dst=ok, fun=raidsup, arg0=y, arg1=dy, arg2=best_sd)
    fb.op('JFalse', cond=ok, offset='g')
    b.call('hl.types.ArrayObj.push', arr, fb.dyn(y))
    fb.op('JAlways', offset='g')
    fb.label('gdone')
    fb.op('JSLte', a=b.field(arr, 'length'), b=zi, offset='end')
    add = cx.fn('logic.ai.AIOrders.addOrder')
    at = [a.value for a in cx.code.types[add.type.value].definition.args]
    kind = fb.reg(cx.t('logic.ai.AIOrderType'))
    fb.op('MakeEnum', dst=kind, construct=MILITARY, args=[])
    mm, om = _new_array(fb, b, cx), _new_array(fb, b, cx)  # no missions (vanilla iterates these arrays)
    nulls = []
    for n in (9, 10):  # data, onComplete (null-checked by addOrder's completion closure)
        r = fb.reg(at[n])
        fb.op('Null', dst=r)
        nulls.append(r)
    res = fb.reg(cx.t('logic.ai.AIOrder'))
    fb.op('CallN', dst=res, fun=helpers.get('addOrder', add.findex.value),
          args=[orders_obj, kind, b.const('i32', 1), arr, best, fb.string('ArmySiege'), fb.string('Pillage'),
                mm, om] + nulls)
    fb.op('Bool', dst=ok, value=False)
    fb.op('JNull', reg=res, offset='fail')
    fb.op('Bool', dst=ok, value=True)
    b.call('haxe.ds.ObjectMap.set', lastmap, fb.dyn(fac), fb.dyn(t))
    fb.label('fail')
    _log_ev(fb, b, cx, helpers, 'raid', [('f', fb.get(fac, 'kind')), ('tgt', best), ('H', best_h), ('M', best_m),
                                         ('n', b.field(arr, 'length')), ('dm', best_d), ('sd', best_sd), ('ok', ok)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
