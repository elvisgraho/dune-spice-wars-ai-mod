"""Worm: an army a sandworm has targeted steps onto rock (reaction, no worm-risk model).

Vanilla reacts only for ent.Harvester (`checkHarvesters` recalls one when `Unit.isWormTarget()`); armies (Fremen
harvesters are armies too) keep fighting on the sand until eaten: 2 Smugglers S_Troopers at full health shooting a
deployed F_Harvester near Haththah (zone worm activity 3) vanished together. `Sandworm.targetEntity` sets
`Unit.targettedByWorm`; `updateTargeting` re-checks its target every update and drops one that is no longer
`canBeWormTarget` (off sand, near a sietch), so reaching rock is the escape.

Every WORM_T s per faction: each of our armies with `isWormTarget()` and `isOnSand()`, outside a protected zone (at most every WFLEE_T s per
army), unless it makes it on its own (moving, not fighting, and its path ends >= WORM_ESC_D farther from the worm
than it is now while the worm is >= WORM_LET_D away, or off the sand within WORM_SAFE_REACH: the worm aggroes within 30-60, strikes <= 40 away after a
5-10 s wind-up; logged `wlet` a, d worm distance, pe path left, once per army per 10 s): the AI order holding it is stopped (Cancel: a hunt / raid / siege would walk it back onto the sand), and it and
the order's other armies on sand within WORM_NEAR of the worm each get `doAction("Move", {actionTarget:
EWorldPosition})` to the nearest safe point: rock (`World.isSandAt`) or sand in a zone the worm can't strike (_no_worm_zone: worm activity
0 or Zone_NoSandworm, e.g. next to a Decoy Thumper) (rings of WORM_STEP up to WORM_R, WORM_DIRS directions: the nearest ring with land; an army with a destination (siege target, else its path end, kept per army WORM_DEST_T in
map `wdest`) while the worm is >= WORM_LET_D away looks WORM_DETOUR further and takes the land point with the least
escape + onward walk (user: the map's rocky middle on the way); others the first found;
none found: WORM_R straight away from the worm). Moved armies go into map `wfled`: aimod_free refuses them for
WORM_HOLD s (no hunt / raid relaunch onto the same sand; a moved harvester's zone is stamped in the faction memory so vanilla's team re-route picks another
field), and aimod_wormheld keeps them out of vanilla's Resupply and
mission picks while a worm is within WORM_NEAR (at most WORM_HOLD s): vanilla re-issued the Atreides Resupply 0.5 s
after every stop, back over the same sand, and the worm re-targeted them: stop / go every 3-4 s for 70 s, 20 moved.
Our sieges (Military order on a structure), and any other Military order (hunt) with armies besides the target, are never stopped, in any phase (user: a capture is never on sand, only a
stray army on the way is): before Action the targeted army alone steps onto rock and stays in the order, held there while the
worm is near (aimod_wormonly: vanilla's Regroup / Engage march call and our gather / stage / desert-step / spos skip it,
strike.py strike_skip / common._skip_striking); in Action it leaves the order by removeUnit
(its last army stays). Other orders (a lone-army Military order, raid walk, Resupply, Discovery, ...) are stopped and their armies on
sand moved. Logs `wflee` per moved army (a, rock found, d to the point, w worm distance, ok). In a trap."""
import math

from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def _move_to(fb, b, cx, army, px, py, fac):
    """army.doAction("Move", {actionTarget: EWorldPosition({x: px, y: py})}, fac) (vanilla checkHarvestingTeams'
    call shape, with a point). Returns the bool result register."""
    da = cx.fn('ent.Entity.doAction')
    da_args = [a.value for a in cx.code.types[da.type.value].definition.args]
    t_arg = da_args[2]
    t_tgt = cx.code.types[t_arg].definition.fields[0].type.value
    cons = cx.code.types[t_tgt].definition.constructs
    wp = [c.name.resolve(cx.code) for c in cons].index('EWorldPosition')
    t_pt = cons[wp].params[0].value
    pt_fields = [f.name.resolve(cx.code) for f in cx.code.types[t_pt].definition.fields]
    pt = fb.reg(t_pt)
    fb.op('New', dst=pt)
    fb.op('SetField', obj=pt, field=pt_fields.index('x'), src=px)
    fb.op('SetField', obj=pt, field=pt_fields.index('y'), src=py)
    tg = fb.reg(t_tgt)
    fb.op('MakeEnum', dst=tg, construct=wp, args=[pt])
    arg = fb.reg(t_arg)
    fb.op('New', dst=arg)
    fb.op('SetField', obj=arg, field=0, src=tg)
    who = fb.reg(da_args[0])
    fb.op('Mov', dst=who, src=army)
    res = fb.reg(cx.code.types[da.type.value].definition.ret.value)
    fb.op('Call4', dst=res, fun=da.findex.value, arg0=who, arg1=fb.string('Move'), arg2=arg, arg3=fac)
    return res


def _do_on(fb, b, cx, unit, action, target, fac):
    """unit.doAction(action, {actionTarget: EEntity(target)}, fac) (vanilla checkHarvestingTeams' MoveAndDeploy
    shape). Returns the bool result register."""
    da = cx.fn('ent.Entity.doAction')
    da_args = [a.value for a in cx.code.types[da.type.value].definition.args]
    t_arg = da_args[2]
    t_tgt = cx.code.types[t_arg].definition.fields[0].type.value
    cons = cx.code.types[t_tgt].definition.constructs
    ee = [c.name.resolve(cx.code) for c in cons].index('EEntity')
    te = fb.reg(cons[ee].params[0].value)
    fb.op('Mov', dst=te, src=target)
    tg = fb.reg(t_tgt)
    fb.op('MakeEnum', dst=tg, construct=ee, args=[te])
    arg = fb.reg(t_arg)
    fb.op('New', dst=arg)
    fb.op('SetField', obj=arg, field=0, src=tg)
    who = fb.reg(da_args[0])
    fb.op('Mov', dst=who, src=unit)
    res = fb.reg(cx.code.types[da.type.value].definition.ret.value)
    fb.op('Call4', dst=res, fun=da.findex.value, arg0=who, arg1=fb.string(action), arg2=arg, arg3=fac)
    return res


def _no_worm_zone(fb, b, cx, z, yes):
    """Jump to `yes` when a sandworm can't strike in zone z (vanilla canBeWormTarget's environment test):
    getCurrentWormActivity <= 0 (a main-base zone) or attribute Zone_NoSandworm (ZONE_NO_WORM: the regions next to
    a Decoy Thumper operation). Falls through otherwise (z null: falls through)."""
    no = _uid('nwz')
    fb.op('JNull', reg=z, offset=no)
    fb.op('JSLte', a=b.call('ent.Zone.getCurrentWormActivity', z), b=b.const('f64', 0), offset=yes)
    has = cx.fn('ent.Object.hasAttribute')
    hat = [a.value for a in cx.code.types[has.type.value].definition.args]
    zo, n2, n3 = fb.reg(hat[0]), fb.reg(hat[2]), fb.reg(hat[3])
    fb.op('Mov', dst=zo, src=z)
    fb.op('Null', dst=n2)
    fb.op('Null', dst=n3)
    hr = fb.reg(cx.t('bool'))
    fb.op('Call4', dst=hr, fun=has.findex.value, arg0=zo, arg1=b.const('i32', ZONE_NO_WORM), arg2=n2, arg3=n3)
    fb.op('JTrue', cond=hr, offset=yes)
    fb.label(no)


def build_worm_flee(cx, helpers):
    """aimod_wormflee(mil, dt) (see module doc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = b.field(_state(fb, b, cx), 'time')
    _tick(fb, b, cx, t, WORM_T, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    gs = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gs, **{'global': cx.global_of('$Game')})
    world = b.field(b.field(gs, 'inst'), 'world')
    fb.op('JNull', reg=world, offset='end')
    my_armies, mlen = _my_armies(fb, b, fac, 'end')
    zi, one = b.const('i32', 0), b.const('i32', 1)
    i, j, k = (fb.reg(cx.t('i32')) for _ in range(3))
    wfled = _global_map(fb, b, cx, 'wfled')
    from rules.memory import _faction_mem
    fmem = _faction_mem(fb, b, cx, fac, True, None)  # harvester moved: its zone counts as danger (team re-route)
    reason = cx.code.types[cx.fn('logic.ai.AIOrder.stop').type.value].definition.args[1].value
    cancel = fb.reg(reason)
    fb.op('MakeEnum', dst=cancel, construct=CANCEL, args=[])
    # doAction("Move", {actionTarget: EWorldPosition({x, y})}, owner): vanilla checkHarvestingTeams' call shape
    da = cx.fn('ent.Entity.doAction')
    da_args = [a.value for a in cx.code.types[da.type.value].definition.args]
    t_arg = da_args[2]  # virtual {actionTarget}
    t_tgt = cx.code.types[t_arg].definition.fields[0].type.value  # ent.EActionTarget
    cons = cx.code.types[t_tgt].definition.constructs
    wp = [c.name.resolve(cx.code) for c in cons].index('EWorldPosition')
    t_pt = cons[wp].params[0].value  # virtual {x, y}
    pt_fields = [f.name.resolve(cx.code) for f in cx.code.types[t_pt].definition.fields]
    move = fb.string('Move')
    # direction table (unrolled), ring loop over the radius
    dirs = [(_ratio(fb, b, math.cos(2 * math.pi * n / WORM_DIRS)), _ratio(fb, b, math.sin(2 * math.pi * n / WORM_DIRS)))
            for n in range(WORM_DIRS)]
    ax, ay, px, py, r, q, d, wd = (fb.reg(cx.t('f64')) for _ in range(8))
    step, rmax = b.const('f64', WORM_STEP), b.const('f64', WORM_R)
    rock, ok = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    mv = fb.reg(cx.t('ent.Army'))  # the army being moved
    # siege army: on the nearest ring with land, the land point nearest its target (the village is land: it steps
    # towards its group, not to the far side); others take the first land point found
    hast, fnd = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    tx, ty, bx, by, bd = (fb.reg(cx.t('f64')) for _ in range(5))
    big = b.const('f64', 1 << 30)
    grp = fb.reg(cx.t('hl.types.ArrayObj'))  # the stopped order's armies (null: none)
    def moved_now(x, skip):
        """Jump to skip if x was already moved in this pass (as another army's order member, or itself)."""
        mn = b.call('haxe.ds.ObjectMap.get', wfled, fb.dyn(x))
        lbl = _uid('mn')
        fb.op('JNull', reg=mn, offset=lbl)
        fb.op('SafeCast', dst=q, src=mn)
        fb.op('JEq', a=q, b=t, offset=skip)
        fb.label(lbl)

    a = _army_loop(fb, b, my_armies, mlen, i, 'army', 'end')
    fb.op('JFalse', cond=b.call('ent.Unit.isWormTarget', a), offset='army')
    fb.op('JFalse', cond=b.call('ent.Entity.isOnSand', a), offset='army')
    _no_worm_zone(fb, b, cx, b.call('ent.Entity.get_zone', a), 'army')  # protected: vanilla drops the target
    moved_now(a, 'army')
    # let it run: a moving army not stuck in a fight that walks away from the worm, or reaches safe ground within
    # WORM_SAFE_REACH, makes it on its own (re-judged every WORM_T: once it stops or turns back, it flees)
    wv = b.field(a, 'targettedByWorm')
    fb.op('JNull', reg=wv, offset='flee')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', a), offset='flee')
    pe = b.call('ent.MobileEntity.getCurrentPathEnd', a)
    fb.op('JNull', reg=pe, offset='flee')
    pex, pey, lq, lr = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('Mov', dst=pex, src=b.field(pe, 'x'))
    fb.op('Mov', dst=pey, src=b.field(pe, 'y'))
    def dist2(dst, x1, y1, x2, y2):
        fb.op('Sub', dst=lq, a=x1, b=x2)
        fb.op('Mul', dst=lq, a=lq, b=lq)
        fb.op('Sub', dst=lr, a=y1, b=y2)
        fb.op('Mul', dst=lr, a=lr, b=lr)
        fb.op('Add', dst=dst, a=lq, b=lr)
        fb.op('Mov', dst=dst, src=b.call('hxd.$Math.sqrt', dst))
    dpa, dpw, daw = (fb.reg(cx.t('f64')) for _ in range(3))
    dist2(dpa, pex, pey, b.field(a, 'posx'), b.field(a, 'posy'))
    fb.op('JSLte', a=dpa, b=b.const('f64', 2), offset='flee')  # standing (path done)
    dist2(dpw, pex, pey, b.field(wv, 'posx'), b.field(wv, 'posy'))
    dist2(daw, b.field(a, 'posx'), b.field(a, 'posy'), b.field(wv, 'posx'), b.field(wv, 'posy'))
    fb.op('JSLt', a=daw, b=b.const('f64', WORM_LET_D), offset='reach')  # already on it: no outrunning it
    fb.op('Sub', dst=lq, a=dpw, b=daw)
    fb.op('JSGte', a=lq, b=b.const('f64', WORM_ESC_D), offset='letrun')
    fb.label('reach')
    fb.op('JSGt', a=dpa, b=b.const('f64', WORM_SAFE_REACH), offset='flee')
    fb.op('JTrue', cond=b.call('world.WorldBase.isSandAt', world, pex, pey), offset='flee')
    fb.label('letrun')
    _throttle(fb, b, cx, 'wlet', a, 10, 'army')
    _log_ev(fb, b, cx, helpers, 'wlet', [('f', fb.get(fac, 'kind')), ('a', a), ('d', daw), ('pe', dpa)])
    fb.op('JAlways', offset='army')
    fb.label('flee')
    _throttle(fb, b, cx, 'wflee', a, WFLEE_T, 'army')
    worm = b.field(a, 'targettedByWorm')
    fb.op('Mov', dst=wd, src=b.const('f64', 0))
    fb.op('JNull', reg=worm, offset='nw')
    fb.op('Mov', dst=wd, src=b.call('ent.Entity.getDistTo', a, worm))
    fb.label('nw')
    # where it was going (user: solid ground on the way, e.g. the map's rocky middle, beats the nearest rock behind
    # it): the end of its current path, before the order stop below clears it; a siege target replaces it
    hasd = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=hasd, value=False)
    # remembered from this army's last flee within WORM_DEST_T (map `wdest` army -> {x, y, t}): after one flee its
    # path ends at our flee point, the real destination is gone (a Fremen trooper fled 11 times in 80 s, rock to rock
    # 20 apart, on its way to Tabr)
    wdm = _global_map(fb, b, cx, 'wdest')
    wdr = fb.reg(cx.t('dyn'))
    fb.op('Mov', dst=wdr, src=b.call('haxe.ds.ObjectMap.get', wdm, fb.dyn(a)))
    fb.op('JNull', reg=wdr, offset='wd_new')
    wdt = fb.reg(cx.t('f64'))
    fb.op('DynGet', dst=wdt, obj=wdr, field=cx.s('t'))
    fb.op('Sub', dst=wdt, a=t, b=wdt)
    fb.op('JSGt', a=wdt, b=b.const('f64', WORM_DEST_T), offset='wd_new')
    fb.op('DynGet', dst=tx, obj=wdr, field=cx.s('x'))
    fb.op('DynGet', dst=ty, obj=wdr, field=cx.s('y'))
    fb.op('Bool', dst=hasd, value=True)
    fb.op('JAlways', offset='nodest')
    fb.label('wd_new')
    pe2 = b.call('ent.MobileEntity.getCurrentPathEnd', a)
    fb.op('JNull', reg=pe2, offset='nodest')
    fb.op('Mov', dst=tx, src=b.field(pe2, 'x'))
    fb.op('Mov', dst=ty, src=b.field(pe2, 'y'))
    fb.op('Sub', dst=q, a=tx, b=b.field(a, 'posx'))
    fb.op('Mul', dst=q, a=q, b=q)
    fb.op('Sub', dst=d, a=ty, b=b.field(a, 'posy'))
    fb.op('Mul', dst=d, a=d, b=d)
    fb.op('Add', dst=q, a=q, b=d)
    fb.op('JSLt', a=q, b=b.const('f64', WORM_DEST_MIN * WORM_DEST_MIN), offset='nodest')
    fb.op('Bool', dst=hasd, value=True)
    wdo = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=wdo)
    b.put(wdo, 'x', tx)
    b.put(wdo, 'y', ty)
    b.put(wdo, 't', t)
    b.call('haxe.ds.ObjectMap.set', wdm, fb.dyn(a), fb.dyn(wdo))
    fb.label('nodest')
    # stop the order holding it (backwards scan, first match)
    fb.op('Null', dst=grp)
    fb.op('Bool', dst=hast, value=False)
    fb.op('Mov', dst=j, src=b.field(orders, 'length'))
    b.loop_head('ord')
    fb.op('JSLte', a=j, b=zi, offset='odone')
    fb.op('Sub', dst=j, a=j, b=one)
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, j), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset='ord')
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='ord')
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', units, fb.dyn(a)), offset='ord')
    # our siege in Action (Annex / Pillage / Liberate / strike under way, user): never stopped; the worm's target
    # leaves it alone (removeUnit cancels nothing in Action while others stay), the last army stays and captures
    widx = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=widx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=widx, b=b.const('i32', MILITARY), offset='wstop')
    wtt = b.field(o, 'targetType')
    fb.op('JNull', reg=wtt, offset='wstop')
    fb.op('EnumIndex', dst=widx, value=wtt)
    fb.op('JEq', a=widx, b=b.const('i32', T_STRUCT), offset='wkeep')
    # ... and any other Military order with armies besides it (hunts): Atreides' 7-army hunt on the renegades at
    # Fongah was stopped at live balance 7.1 (41:23) for one A_Soldier targeted 150 behind on sand; the rest fell into
    # Resupply and were picked off by the renegades in two smaller relaunches
    fb.op('JSLte', a=b.field(units, 'length'), b=one, offset='wstop')
    fb.label('wkeep')
    # ... nor before Action (user: a capture is never on sand, only a stray army on the way is): the targeted army
    # alone steps onto rock and stays in the order (grp null: nobody else moves). Stopping it cancelled Harkonnen's
    # 10-army Annex of Qalmara in Engage at 06:29 for one worm 30 away
    stg = b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'ent.Entity')
    fb.op('JNull', reg=stg, offset='nostg')
    fb.op('Mov', dst=tx, src=b.field(stg, 'posx'))
    fb.op('Mov', dst=ty, src=b.field(stg, 'posy'))
    fb.op('Bool', dst=hast, value=True)
    fb.label('nostg')
    fb.op('JNotEq', a=b.field(o, 'phase'), b=b.const('i32', ACTION), offset='odone')
    fb.op('JSLte', a=b.field(units, 'length'), b=one, offset='army')
    b.call('logic.ai.AIOrder.removeUnit', o, a)
    fb.op('JAlways', offset='odone')
    fb.label('wstop')
    fb.op('Mov', dst=grp, src=b.call('hl.types.ArrayObj.copy', units))
    b.call('logic.ai.AIOrder.stop', o, cancel)
    fb.label('odone')
    fb.op('JFalse', cond=hast, offset='hd_k')
    fb.op('Bool', dst=hasd, value=True)  # the siege target is the destination
    fb.label('hd_k')
    # rings beyond the nearest one with land count while within WORM_DETOUR of it and the worm is still >= WORM_LET_D
    # away (closer it has aggroed: the nearest rock only)
    rlim = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=rlim, src=b.const('f64', 0))
    fb.op('JFalse', cond=hasd, offset='rl_d')
    fb.op('JSLt', a=wd, b=b.const('f64', WORM_LET_D), offset='rl_d')
    fb.op('Mov', dst=rlim, src=b.const('f64', WORM_DETOUR))
    fb.label('rl_d')
    r0 = fb.reg(cx.t('f64'))
    # move a, then the order's other armies on sand
    fb.op('Mov', dst=k, src=zi)
    fb.op('Mov', dst=mv, src=a)
    b.loop_head('mv')
    fb.op('Mov', dst=ax, src=b.field(mv, 'posx'))
    fb.op('Mov', dst=ay, src=b.field(mv, 'posy'))
    fb.op('Bool', dst=rock, value=True)
    fb.op('Mov', dst=r, src=step)
    fb.op('Bool', dst=fnd, value=False)
    fb.op('Mov', dst=bd, src=big)
    fb.op('Mov', dst=r0, src=big)
    b.loop_head('ring')
    fb.op('JSGt', a=r, b=rmax, offset='rend')
    fb.op('JSGt', a=r, b=r0, offset='rend')  # past the nearest land ring + the detour allowance
    for c, s in dirs:
        cand, nxt = _uid('wc'), _uid('wn')
        fb.op('Mul', dst=q, a=r, b=c)
        fb.op('Add', dst=px, a=ax, b=q)
        fb.op('Mul', dst=q, a=r, b=s)
        fb.op('Add', dst=py, a=ay, b=q)
        fb.op('JFalse', cond=b.call('world.WorldBase.isSandAt', world, px, py), offset=cand)
        _no_worm_zone(fb, b, cx, b.call('world.World.getZoneAt', world, px, py), cand)  # thumper-protected sand
        fb.op('JAlways', offset=nxt)
        fb.label(cand)
        fb.op('JFalse', cond=hasd, offset='go')  # nowhere to go: the first land point
        # the first land ring found sets how far we look (r0 = it + the allowance)
        fb.op('JTrue', cond=fnd, offset=cand + 'f')
        fb.op('Add', dst=r0, a=r, b=rlim)
        fb.label(cand + 'f')
        # cost: the escape walk (r) + the way on from there to the destination
        fb.op('Sub', dst=q, a=px, b=tx)
        fb.op('Mul', dst=q, a=q, b=q)
        fb.op('Sub', dst=d, a=py, b=ty)
        fb.op('Mul', dst=d, a=d, b=d)
        fb.op('Add', dst=q, a=q, b=d)
        fb.op('Mov', dst=q, src=b.call('hxd.$Math.sqrt', q))
        fb.op('Add', dst=q, a=q, b=r)
        fb.op('JSGte', a=q, b=bd, offset=nxt)
        fb.op('Mov', dst=bd, src=q)
        fb.op('Mov', dst=bx, src=px)
        fb.op('Mov', dst=by, src=py)
        fb.op('Bool', dst=fnd, value=True)
        fb.label(nxt)
    fb.op('Add', dst=r, a=r, b=step)
    fb.op('JAlways', offset='ring')
    fb.label('rend')
    fb.op('JFalse', cond=fnd, offset='away')
    fb.op('Mov', dst=px, src=bx)
    fb.op('Mov', dst=py, src=by)
    fb.op('JAlways', offset='go')
    # no rock in reach: straight away from the worm (or stay if it is unknown)
    fb.label('away')
    fb.op('Bool', dst=rock, value=False)
    fb.op('JNull', reg=worm, offset='next')
    fb.op('Sub', dst=px, a=ax, b=b.field(worm, 'posx'))
    fb.op('Sub', dst=py, a=ay, b=b.field(worm, 'posy'))
    fb.op('Mul', dst=q, a=px, b=px)
    fb.op('Mul', dst=d, a=py, b=py)
    fb.op('Add', dst=q, a=q, b=d)
    fb.op('JSLte', a=q, b=b.const('f64', 1), offset='next')
    fb.op('Mov', dst=q, src=b.call('hxd.$Math.sqrt', q))
    fb.op('Mul', dst=px, a=px, b=rmax)
    fb.op('SDiv', dst=px, a=px, b=q)
    fb.op('Add', dst=px, a=ax, b=px)
    fb.op('Mul', dst=py, a=py, b=rmax)
    fb.op('SDiv', dst=py, a=py, b=q)
    fb.op('Add', dst=py, a=ay, b=py)
    fb.label('go')
    pt = fb.reg(t_pt)
    fb.op('New', dst=pt)
    fb.op('SetField', obj=pt, field=pt_fields.index('x'), src=px)
    fb.op('SetField', obj=pt, field=pt_fields.index('y'), src=py)
    tg = fb.reg(t_tgt)
    fb.op('MakeEnum', dst=tg, construct=wp, args=[pt])
    arg = fb.reg(t_arg)
    fb.op('New', dst=arg)
    fb.op('SetField', obj=arg, field=0, src=tg)
    who = fb.reg(da_args[0])
    fb.op('Mov', dst=who, src=mv)
    res = fb.reg(cx.code.types[da.type.value].definition.ret.value)
    fb.op('Call4', dst=res, fun=da.findex.value, arg0=who, arg1=move, arg2=arg, arg3=fac)
    b.call('haxe.ds.ObjectMap.set', wfled, fb.dyn(mv), fb.dyn(t))
    fb.op('JNull', reg=b.field(mv, 'harvestComponent'), offset='nohv')
    hz = b.call('ent.Entity.get_zone', mv)
    fb.op('JNull', reg=hz, offset='nohv')
    b.call('haxe.ds.ObjectMap.set', fmem, fb.dyn(hz), fb.dyn(t))
    fb.label('nohv')
    fb.op('Sub', dst=px, a=px, b=ax)
    fb.op('Sub', dst=py, a=py, b=ay)
    fb.op('Mul', dst=px, a=px, b=px)
    fb.op('Mul', dst=py, a=py, b=py)
    fb.op('Add', dst=d, a=px, b=py)
    fb.op('Mov', dst=d, src=b.call('hxd.$Math.sqrt', d))
    _log_ev(fb, b, cx, helpers, 'wflee', [('f', fb.get(fac, 'kind')), ('a', mv), ('rock', rock), ('d', d),
                                          ('w', wd), ('ok', res)])
    # next army of the stopped order still on sand (not a itself)
    fb.label('next')
    fb.op('JNull', reg=grp, offset='army')
    b.loop_head('gn')
    fb.op('JSGte', a=k, b=b.field(grp, 'length'), offset='army')
    fb.op('Mov', dst=mv, src=b.cast(b.call('hl.types.ArrayObj.getDyn', grp, k), 'ent.Army'))
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=mv, offset='gn')
    fb.op('JEq', a=mv, b=a, offset='gn')
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', mv), offset='gn')
    fb.op('JFalse', cond=b.call('ent.Entity.isOnSand', mv), offset='gn')
    moved_now(mv, 'gn')
    fb.op('JNull', reg=worm, offset='mv')  # worm unknown: every army on sand
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', mv, worm), b=b.const('f64', WORM_NEAR), offset='gn')
    fb.op('JAlways', offset='mv')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


def build_wormheld(cx, rally=True):
    """aimod_wormheld(army) -> true while worm-flee moved it less than WORM_HOLD s ago (map `wfled`) and a sandworm
    (State.worms) is within WORM_NEAR of it: it waits on the rock instead of being re-ordered over the sand; also
    while it walks to a rally point (map `rallied` within RALLY_HOLD, rules/rally.py). Never in a zone the worm can't
    strike (_no_worm_zone). rally=False (aimod_wormonly): the worm part only, for the march skips (strike.py
    strike_skip, common._skip_striking): a rally's armies join a contest hunt right at its commit, and skipping their
    march there could leave them standing in Regroup."""
    fb = FB(cx, [cx.t('ent.Entity')], cx.t('bool'))
    b = B(fb)
    ok = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=ok, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    st = _state(fb, b, cx)
    q = fb.reg(cx.t('f64'))
    # walking to a rally point (rules/rally.py): held too
    if not rally:
        fb.op('JAlways', offset='norly')
    rv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rallied'), fb.dyn(0))
    fb.op('JNull', reg=rv, offset='norly')
    fb.op('SafeCast', dst=q, src=rv)
    fb.op('Sub', dst=q, a=b.field(st, 'time'), b=q)
    fb.op('JSGt', a=q, b=b.const('f64', RALLY_HOLD), offset='norly')
    fb.op('Bool', dst=ok, value=True)
    fb.op('JAlways', offset='end')
    fb.label('norly')
    # in a zone the worm can't strike (thumper-protected neighbour, main-base zone): nothing to wait for (Fremen
    # stood 60+ s at the edge of Aeg-wahad's Decoy Thumper region, out of Resupply / Defense)
    _no_worm_zone(fb, b, cx, b.call('ent.Entity.get_zone', 0), 'end')
    wv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'wfled'), fb.dyn(0))
    fb.op('JNull', reg=wv, offset='end')
    fb.op('SafeCast', dst=q, src=wv)
    fb.op('Sub', dst=q, a=b.field(st, 'time'), b=q)
    fb.op('JSGt', a=q, b=b.const('f64', WORM_HOLD), offset='end')
    worms = b.field(st, 'worms')
    fb.op('JNull', reg=worms, offset='end')
    k = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    we = fb.reg(cx.t('ent.Entity'))
    b.loop_head('w')
    fb.op('JSGte', a=k, b=b.field(worms, 'length'), offset='end')
    fb.op('Mov', dst=we, src=b.cast(b.call('hl.types.ArrayObj.getDyn', worms, k), 'ent.Sandworm'))
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=we, offset='w')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', 0, we), b=b.const('f64', WORM_NEAR), offset='w')
    fb.op('Bool', dst=ok, value=True)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=ok)
    return fb.build()


def log_worm_kill(cx, helpers, new_ids):
    """Every army a sandworm eats is logged (`weaten`: o owner, a army, fled = s since worm-flee moved it, -1 never):
    the single Army.playDeathWorm call in Sandworm.tryAttack is wrapped (log in a trap, then the original)."""
    fn = cx.fn('ent.Sandworm.tryAttack')
    pdw = cx.fn('ent.Army.playDeathWorm')
    sites = [op for op in fn.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == pdw.findex.value]
    if len(sites) != 1:
        raise ValueError(f'worm-kill log: expected 1 Army.playDeathWorm call in tryAttack, found {len(sites)}')
    ft = cx.code.types[pdw.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=pdw.type.value)
    b = B(fb)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fl = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=fl, src=b.const('f64', -1))
    wf = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'wfled'), fb.dyn(0))
    fb.op('JNull', reg=wf, offset='nf')
    fb.op('SafeCast', dst=fl, src=wf)
    fb.op('Sub', dst=fl, a=b.field(_state(fb, b, cx), 'time'), b=fl)
    fb.label('nf')
    own = b.call('ent.Entity.get_owner', 0)
    _log_ev(fb, b, cx, helpers, 'weaten', [('o', fb.get(own, 'kind')), ('a', 0), ('fled', fl)])
    fb.label('end')
    fb.end_try(guard)
    res = fb.reg(ft.ret.value)
    fb.op(f'Call{len(ft.args)}', dst=res, fun=pdw.findex.value, **{f'arg{i}': i for i in range(len(ft.args))})
    fb.op('Ret', ret=res)
    w = fb.build()
    sites[0].df['fun'].value = w
    new_ids.add(w)
    return {'worm:kill-log': 1}
