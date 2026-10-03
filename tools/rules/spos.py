"""Siege position: capture from the side of the village away from enemy turrets, and don't chase into them.

Vanilla walks a siege army to the nearest point of the occupation range and micro chases whatever attacks it:
Fremen took Atreides' Sadnin (113 from Arrakeen) with 10 armies standing on its north side, 90-110 from the main
base guns, and lost 6 of them while the order's own balance read 2-13 (winning); one F_Trooper chased a defender to
38 from Arrakeen. F_Special_2, 46 south of Sadnin (159 from Arrakeen), stayed at 100 hp the whole fight.

Every SPOS_T_CHECK s per faction: our Military orders with a Structure target in Action (any army within SPOS_R of
the target) or Engage (armies within SPOS_IN: never pulls a walker forward): an army covered by at-war turrets other
than the target's (aimod_cover, own false, target excluded) is moved (doAction Move, at most every SPOS_T s per army)
to P = target + SPOS_OFF away from the nearest at-war structure E whose guns cover it (aimod_cover1 > 0; not the
target): still in the occupation range,
farther from E's guns. Not if P is no farther from E than the army already is. Map `sposm` army -> time (desert-step
leaves such an army alone for SPOS_T x 2). Logs `spos` (a, tgt, es, d to P) once per army per 15 s. In a trap.

Unstick (same pass, Action): an army stuck in the village footprint (see `_unstick`) is walked out to the target's
safe position; vanilla only re-sends ArmySiege to it, which never takes hold (Fremen F_Sneak at Tabwan, 2.5 min)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.worm import _move_to


def _unstick(fb, b, cx, helpers, fac, t, ph, a, ae, tgt, maps, sp_args, go, nxt):
    """Unstick (Action only): army ae within STUCK_R of the target, the target neither besieged nor occupied, and ae
    moved less than STUCK_MOVE for STUCK_T s (maps stkx / stky / stkt: last spot and since when) -> Move to
    tgt.getSafePosition() (collision-free, radius + 5 out; vanilla sends it only to armies outside the occupation
    range), clock restarted, then `nxt`. Else fall through to `go`. Logs `unstick` (a, tgt, ok)."""
    stkx, stky, stkt = maps
    px, py, q, w = (fb.reg(cx.t('f64')) for _ in range(4))
    sset, sclr = _uid('sset'), _uid('sclr')
    fb.op('JNotEq', a=ph, b=b.const('i32', ACTION), offset=go)
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ae, tgt), b=b.const('f64', STUCK_R), offset=go)
    fb.op('JFalse', cond=b.call('ent.Unit.canAutoUndeploy', a), offset=go)  # installed turret: can't walk anyway
    st = b.cast(tgt, 'ent.Structure')
    fb.op('JNull', reg=st, offset=go)
    sg = b.field(st, 'siege')
    fb.op('JNull', reg=sg, offset=go)
    fb.op('JTrue', cond=b.field(sg, 'isUnderSiege'), offset=sclr)
    fb.op('JNotNull', reg=b.field(sg, 'occupier'), offset=sclr)
    vx = b.call('haxe.ds.ObjectMap.get', stkx, fb.dyn(a))
    fb.op('JNull', reg=vx, offset=sset)
    vy = b.call('haxe.ds.ObjectMap.get', stky, fb.dyn(a))
    fb.op('JNull', reg=vy, offset=sset)
    vt = b.call('haxe.ds.ObjectMap.get', stkt, fb.dyn(a))
    fb.op('JNull', reg=vt, offset=sset)
    fb.op('SafeCast', dst=px, src=vx)
    fb.op('SafeCast', dst=py, src=vy)
    fb.op('Sub', dst=px, a=b.field(ae, 'posx'), b=px)
    fb.op('Sub', dst=py, a=b.field(ae, 'posy'), b=py)
    fb.op('Mul', dst=px, a=px, b=px)
    fb.op('Mul', dst=py, a=py, b=py)
    fb.op('Add', dst=px, a=px, b=py)
    fb.op('JSGt', a=px, b=b.const('f64', STUCK_MOVE * STUCK_MOVE), offset=sset)
    fb.op('SafeCast', dst=q, src=vt)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSLt', a=q, b=b.const('f64', STUCK_T), offset=go)
    pt = b.call('ent.Entity.getSafePosition', tgt, *sp_args)
    fb.op('JNull', reg=pt, offset=go)
    fb.op('Mov', dst=px, src=b.field(pt, 'x'))
    fb.op('Mov', dst=py, src=b.field(pt, 'y'))
    ok = _move_to(fb, b, cx, a, px, py, fac)
    b.call('haxe.ds.ObjectMap.set', stkt, fb.dyn(a), fb.dyn(t))
    fb.op('Mov', dst=w, src=q)
    _log_ev(fb, b, cx, helpers, 'unstick', [('f', fb.get(fac, 'kind')), ('a', a), ('tgt', tgt), ('st', w),
                                            ('ok', ok)])
    fb.op('JAlways', offset=nxt)
    fb.label(sclr)  # the siege runs: no stuck clock
    b.call('haxe.ds.ObjectMap.remove', stkt, fb.dyn(a))
    fb.op('JAlways', offset=go)
    fb.label(sset)  # moved (or first seen): new spot, clock from now
    fb.op('Mov', dst=px, src=b.field(ae, 'posx'))
    fb.op('Mov', dst=py, src=b.field(ae, 'posy'))
    b.call('haxe.ds.ObjectMap.set', stkx, fb.dyn(a), fb.dyn(px))
    b.call('haxe.ds.ObjectMap.set', stky, fb.dyn(a), fb.dyn(py))
    b.call('haxe.ds.ObjectMap.set', stkt, fb.dyn(a), fb.dyn(t))
    fb.op('JAlways', offset=go)


def build_spos(cx, helpers, cover):
    """aimod_spos(mil, dt) (see module doc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    _tick(fb, b, cx, t, SPOS_CHECK, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    state = _state(fb, b, cx)
    facs = b.cast(fb.get(state, 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=facs, offset='end')
    sposm = _global_map(fb, b, cx, 'sposm')
    zi = b.const('i32', 0)
    i, j, k, l, idx, ph = (fb.reg(cx.t('i32')) for _ in range(6))
    d, lim, cv, bd, dx, dy, q, px, py = (fb.reg(cx.t('f64')) for _ in range(9))
    tgt, ee, ae = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    f_false, no_arr = fb.reg(cx.t('bool')), fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Bool', dst=f_false, value=False)
    fb.op('Null', dst=no_arr)
    maps = [_global_map(fb, b, cx, nm) for nm in ('stkx', 'stky', 'stkt')]
    gsp = cx.fn('ent.Entity.getSafePosition')
    sp_args = [fb.reg(a.value) for a in cx.code.types[gsp.type.value].definition.args[1:]]
    for r in sp_args:
        fb.op('Null', dst=r)
    fb.op('Mov', dst=i, src=b.field(orders, 'length'))
    b.loop_head('o')
    fb.op('JSLte', a=i, b=zi, offset='end')
    fb.op('Sub', dst=i, a=i, b=b.const('i32', 1))
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, i), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset='o')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='o')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='o')
    fb.op('EnumIndex', dst=idx, value=tt)
    fb.op('JNotEq', a=idx, b=b.const('i32', T_STRUCT), offset='o')
    fb.op('Mov', dst=ph, src=b.field(o, 'phase'))
    fb.op('Mov', dst=lim, src=b.const('f64', SPOS_R))
    fb.op('JEq', a=ph, b=b.const('i32', ACTION), offset='plim')
    fb.op('JNotEq', a=ph, b=b.const('i32', REGROUP + 1), offset='o')
    fb.op('Mov', dst=lim, src=b.const('f64', SPOS_IN))
    fb.label('plim')
    fb.op('Mov', dst=tgt, src=b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'ent.Entity'))
    fb.op('JNull', reg=tgt, offset='o')
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='o')
    un = b.field(units, 'length')
    a = _army_loop(fb, b, units, un, j, 'a', 'o')
    fb.op('Mov', dst=ae, src=a)
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ae, tgt), b=lim, offset='a')
    _unstick(fb, b, cx, helpers, fac, t, ph, a, ae, tgt, maps, sp_args, 'cov', 'a')
    fb.label('cov')
    fb.op('CallN', dst=cv, fun=cover, args=[fac, ae, tgt, f_false, no_arr])
    fb.op('JSLte', a=cv, b=b.const('f64', 0), offset='a')
    # nearest at-war structure (not the target) covering the army: the guns to step away from
    c1 = fb.reg(cx.t('f64'))
    fb.op('Null', dst=ee)
    fb.op('Mov', dst=bd, src=b.const('f64', 1 << 30))
    fb.op('Mov', dst=k, src=zi)
    b.loop_head('f')
    fb.op('JSGte', a=k, b=b.field(facs, 'length'), offset='fdone')
    of = b.cast(b.call('hl.types.ArrayObj.getDyn', facs, k), 'ent.Faction')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=of, offset='f')
    fb.op('JEq', a=of, b=fac, offset='f')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, of), offset='f')
    ss = b.cast(fb.get(of, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=ss, offset='f')
    fb.op('Mov', dst=l, src=zi)
    b.loop_head('g')
    fb.op('JSGte', a=l, b=b.field(ss, 'length'), offset='f')
    se = b.cast(b.call('hl.types.ArrayObj.getDyn', ss, l), 'ent.Entity')
    fb.op('Incr', dst=l)
    fb.op('JNull', reg=se, offset='g')
    fb.op('JEq', a=se, b=tgt, offset='g')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', ae, se))
    fb.op('JSGte', a=d, b=bd, offset='g')
    # only a structure whose guns reach the army: Fremen at Atreides' Arkwaz stepped away from a gunless Smugglers
    # InfiltrationCell 50 off (towards Arrakeen's guns, the real cover) 76 times in 3 min
    sst = b.cast(fb.dyn(se), 'ent.Structure')
    fb.op('JNull', reg=sst, offset='g')
    fb.op('Call3', dst=c1, fun=helpers['cover1'], arg0=ae, arg1=sst, arg2=no_arr)
    fb.op('JSLte', a=c1, b=b.const('f64', 0), offset='g')
    fb.op('Mov', dst=bd, src=d)
    fb.op('Mov', dst=ee, src=se)
    fb.op('JAlways', offset='g')
    fb.label('fdone')
    fb.op('JNull', reg=ee, offset='a')
    # P = target + SPOS_OFF along (target - E)
    fb.op('Sub', dst=dx, a=b.field(tgt, 'posx'), b=b.field(ee, 'posx'))
    fb.op('Sub', dst=dy, a=b.field(tgt, 'posy'), b=b.field(ee, 'posy'))
    fb.op('Mul', dst=q, a=dx, b=dx)
    fb.op('Mul', dst=d, a=dy, b=dy)
    fb.op('Add', dst=q, a=q, b=d)
    fb.op('JSLte', a=q, b=b.const('f64', 1), offset='a')
    fb.op('Mov', dst=q, src=b.call('hxd.$Math.sqrt', q))
    off = b.const('f64', SPOS_OFF)
    fb.op('Mul', dst=px, a=dx, b=off)
    fb.op('SDiv', dst=px, a=px, b=q)
    fb.op('Add', dst=px, a=px, b=b.field(tgt, 'posx'))
    fb.op('Mul', dst=py, a=dy, b=off)
    fb.op('SDiv', dst=py, a=py, b=q)
    fb.op('Add', dst=py, a=py, b=b.field(tgt, 'posy'))
    # only if P is farther from E than the army is now (else nothing to gain)
    fb.op('Sub', dst=dx, a=px, b=b.field(ee, 'posx'))
    fb.op('Sub', dst=dy, a=py, b=b.field(ee, 'posy'))
    fb.op('Mul', dst=dx, a=dx, b=dx)
    fb.op('Mul', dst=dy, a=dy, b=dy)
    fb.op('Add', dst=dx, a=dx, b=dy)
    fb.op('Mov', dst=dx, src=b.call('hxd.$Math.sqrt', dx))
    fb.op('Sub', dst=dx, a=dx, b=b.const('f64', 10))
    fb.op('JSLte', a=dx, b=bd, offset='a')
    _skip_striking(fb, b, cx, helpers, a, 'a')  # en-route strike: it fights first
    _throttle(fb, b, cx, 'spos', a, SPOS_T, 'a')
    b.call('haxe.ds.ObjectMap.set', sposm, fb.dyn(a), fb.dyn(t))
    ok = _move_to(fb, b, cx, a, px, py, fac)
    _throttle(fb, b, cx, 'sposlog', a, 15, 'a')
    _log_ev(fb, b, cx, helpers, 'spos', [('f', fb.get(fac, 'kind')), ('a', a), ('tgt', tgt), ('es', ee),
                                         ('cv', cv), ('ok', ok)])
    fb.op('JAlways', offset='a')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


def build_keep_capture(cx, helpers, new_ids):
    """Keep capture: vanilla micro (unitMicroManagement) gives the first army of a fight group, whatever its life or
    distance, the role 'defend our nearest vulnerable structure' (ours with any besiegingFaction or occupier) and
    Repositions it there with findRelocationPos(army, null, structure). Fremen pulled a F_Sneak out of the Tabwan
    capture to Altar, 130 away, 07:10-07:38 (122 re-issues), then walked it back: the capture lost its occupier.
    All 5 findRelocationPos calls -> this wrapper: for our own structure (the defender role; occupy / siege roles
    target others) and an army within KEEP_R of a village our faction is besieging or occupying (the capture it
    holds; Army.aiOrder is often null on AI besiegers), return null (no Reposition: it keeps its current micro).
    Real defense still comes by orders (vanilla Defense, contest hunt, rally). Logs `keepcap` (a, s, v) per army
    every 15 s."""
    orig = cx.fn('logic.ai.AIUnits.findRelocationPos')
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    kp = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=kp, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=1, offset='orig')
    fb.op('JNull', reg=3, offset='orig')
    ae, se, ve = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ae, src=1)
    fb.op('Mov', dst=se, src=3)
    fac = b.call('ent.Entity.get_owner', ae)
    fb.op('JNull', reg=fac, offset='orig')
    fb.op('JNotEq', a=b.call('ent.Entity.get_owner', se), b=fac, offset='orig')  # not the defender role
    villages = b.field(_state(fb, b, cx), 'villages')
    fb.op('JNull', reg=villages, offset='orig')
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('v')
    fb.op('JSGte', a=i, b=b.field(villages, 'length'), offset='orig')
    v = b.cast(b.call('hl.types.ArrayObj.getDyn', villages, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=v, offset='v')
    fb.op('Mov', dst=ve, src=v)
    fb.op('JEq', a=ve, b=se, offset='v')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ae, ve), b=b.const('f64', KEEP_R), offset='v')
    sg = b.field(v, 'siege')
    fb.op('JNull', reg=sg, offset='v')
    fb.op('JEq', a=b.field(sg, 'besiegingFaction'), b=fac, offset='keep')
    fb.op('JNotEq', a=b.call('ent.comp.SiegeComponent.getOccupierFaction', sg), b=fac, offset='v')
    fb.label('keep')
    _throttle(fb, b, cx, 'keepcap', ae, 15, 'null')
    _log_ev(fb, b, cx, helpers, 'keepcap', [('f', fb.get(fac, 'kind')), ('a', ae), ('s', se), ('v', ve)])
    fb.label('null')
    fb.op('Bool', dst=kp, value=True)
    fb.label('orig')
    fb.end_try(guard)
    fb.op('JFalse', cond=kp, offset='call')
    fb.op('Null', dst=res)
    fb.op('Ret', ret=res)
    fb.label('call')
    fb.op('Call4', dst=res, fun=orig.findex.value, arg0=0, arg1=1, arg2=2, arg3=3)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    f = cx.fn('logic.ai.AIUnits.unitMicroManagement')
    sites = [op for op in f.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == orig.findex.value]
    if len(sites) != 5:
        raise ValueError(f'keep-capture: expected 5 findRelocationPos calls in unitMicroManagement, found {len(sites)}')
    for op in sites:
        op.df['fun'].value = w
    return {'keep-capture': len(sites)}
