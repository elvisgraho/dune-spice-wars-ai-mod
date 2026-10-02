"""Turret steering (AI-POLICY §5a goal 2, standoff): a village that at-war armies keep standing next to, or a front
village, gets a MissileBattery first.

Front village: our village (on our land, not a main base) whose zone borders >= TURRET_EXPOSED zones held by
factions at war with us, or that lies >= TURRET_REMOTE zones from our main base (Zone.getDistanceToPlayerBase: too
far for a relief to come in time), or that borders our main base's zone and >= TURRET_BASE_GATE zones of any other faction
(at war or not: the way into our base), or that is the map's centre zone or borders it (zone at the mean village
position, World.getZoneAt: every way across the map passes there), without a battery: MissileBattery scores max(vanilla, 0) + STAND_BONUS when it can be built
now or once paid. Full (VillageUpgradesLimitReached) and the battery affordable now (AIController.getMissingResources
at priority 3 empty): the first of TURRET_DEMOLISH present (Marketplace, MaintenanceCenter, ResearchHub) is removed
(upgrades.removeUpgrade(getKind(k).uid, null), vanilla's own replace call; log `tdem` f, s, k, n = front zones,
hops) and
the battery is boosted once the slot is free (removeUpgrade(uid, null) only starts demolishUpgrade: the slot stays
taken meanwhile; no second demolition and no boost on that village within TRES_T, else the next building would go
too, or a battery picked while full would let checkBuildings' replace path remove the lowest-scored building); for
TRES_T s (map `tres` village -> when) every other building on that village scores NaN (dropped) while it is still a
front village without a battery, so vanilla can't refill the slot. None present:
nothing is demolished. (User: Atreides, weakest, was overrun by Fremen through such villages.)

The failure: vanilla scores MissileBattery on static map exposure only (`structureDefenses`: enemy-owned neighbour
zones), never on armies. Smugglers' Annarekh and Atreides' Gun-dah (115 apart) faced each other's whole army for
most of the match: both directors sat in `hold`, every rally / raid judgment read the other stack, Smugglers' armies
were pulled home from hunts (Walanim 22:28) and their villages were harassed; no turret was ever built there. A
battery covers COVER_R: one at either village of a bunker pair (Annarekh / Tsimrekh 75 apart) covers both.

Wrapper around the scoring closure's call of $HScoring.getBuildingStructureScore (pair {s, k}, f, context,
considerNoStocks; not checkBuildings' re-scorings, whose replace logic demolishes lower-scored buildings): for
k = MissileBattery on a village s of ours on our land (not a main base) where at-war power aimod_threat(f, s,
STAND_R) >= STAND_MIN_H has stood for STAND_T s (map `stnd` village -> first seen, cleared when it drops) and our
turret cover at s (aimod_cover own; a battery of the pair partner counts) is below ENTER x that power, the score becomes
max(vanilla, 0) + STAND_BONUS (vanilla scores are ~10-40 and Insane picks among the best 2 pairs on different
villages). Each battery adds to the cover `strat` subtracts from the home need, so built turrets free armies.
Only when Upgrades.checkAddUpgrade says Success or MissingResources (not full, in combat, occupied). Vanilla's 0
(below its defense minimum) is lifted; NaN (invalid pair) is kept. A standing record not refreshed for 2 x STAND_T
restarts (map `stnl` last seen). Unaffordable: vanilla's
reserve logic saves for it. Logs `turret` (s, h, sc vanilla score) once per village per 30 s. Fails safe: in a
trap, the vanilla score on error."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def build_turret_steer(cx, helpers, threat, cover, new_ids, inner=None):
    """Redirect the getBuildingStructureScore calls to the wrapper (see module doc). `inner`: a score wrapper with
    vanilla's signature to call instead of vanilla (uhq-ext)."""
    orig = cx.fn('logic.ai.$HScoring.getBuildingStructureScore')
    oid = orig.findex.value
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    if args[1] != cx.t('ent.Faction') or ft.ret.value != cx.t('f64'):
        raise ValueError('turret-steer: getBuildingStructureScore(pair, Faction, context, noStocks) -> f64 expected')
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Call4', dst=res, fun=inner or oid, arg0=0, arg1=1, arg2=2, arg3=3)  # vanilla score, outside any trap
    guard = fb.try_()
    # NaN (invalid pair, dropped by vanilla) fails every ordered compare: only a real score falls through
    fb.op('JSGte', a=res, b=b.const('f64', -(1 << 30)), offset='real')
    fb.op('JAlways', offset='end')
    fb.label('real')
    fb.op('JNull', reg=1, offset='end')
    k = fb.get(0, 'k')
    fb.op('JNull', reg=k, offset='end')
    ks = b.cast(k, 'String')
    so = fb.get(0, 's')
    fb.op('JNull', reg=so, offset='end')
    s = b.cast(so, 'ent.Structure')
    fb.op('JNull', reg=s, offset='end')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', s), offset='end')
    z = b.call('ent.Entity.get_zone', s)
    fb.op('JNull', reg=z, offset='end')
    fb.op('JNotEq', a=b.field(z, 'owner'), b=1, offset='end')
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=s)
    now = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=now, src=b.field(_state(fb, b, cx), 'time'))
    up = b.field(s, 'upgrades')
    fb.op('JNull', reg=up, offset='end')
    zi = b.const('i32', 0)
    battery = fb.string('MissileBattery')
    gk = cx.fn('logic.Upgrades.getKind')
    gkt = [a.value for a in cx.code.types[gk.type.value].definition.args]
    gkn = []
    for t_ in gkt[2:]:
        r_ = fb.reg(t_)
        fb.op('Null', dst=r_)
        gkn.append(r_)
    ku = fb.reg(cx.code.types[gk.type.value].definition.ret.value)

    def get_kind(name):
        """ku = our building of kind `name` in s (null if none)."""
        fb.op('CallN', dst=ku, fun=gk.findex.value, args=[up, name] + gkn)
        return ku

    ex = fb.reg(cx.t('bool'))
    ne_n, kk, hops = fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    ne_o = fb.reg(cx.t('i32'))  # neighbour zones held by any other faction (base gate)
    cxs, cys = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    cen = fb.reg(cx.t('bool'))
    fb.op('Mov', dst=hops, src=b.const('i32', 99))
    gdb = cx.fn('ent.Zone.getDistanceToPlayerBase')
    gnull = fb.reg(cx.code.types[gdb.type.value].definition.args[2].value)
    fb.op('Null', dst=gnull)

    def exposed():
        """ex = our village's zone borders >= TURRET_EXPOSED zones held by factions at war with us (a standing
        front), lies >= TURRET_REMOTE zones from our main base (too far for a relief in time), borders our main base
        with >= TURRET_BASE_GATE zones of any other faction next to it (the gate to our base), or is the map's centre
        zone / borders it (cen); ne_n = the at-war neighbour zones, hops = zones from our main base (99: none)."""
        u = _uid('ex')
        fb.op('Bool', dst=ex, value=False)
        fb.op('Bool', dst=cen, value=False)
        fb.op('Mov', dst=ne_n, src=zi)
        fb.op('Mov', dst=ne_o, src=zi)
        nb = b.field(z, 'neighbors')
        fb.op('JNull', reg=nb, offset=u + 'd')
        fb.op('Mov', dst=kk, src=zi)
        b.loop_head(u + 'l')
        fb.op('JSGte', a=kk, b=b.field(nb, 'length'), offset=u + 'c')
        nz = b.cast(b.call('hl.types.ArrayObj.getDyn', nb, kk), 'ent.Zone')
        fb.op('Incr', dst=kk)
        fb.op('JNull', reg=nz, offset=u + 'l')
        no_ = b.field(nz, 'owner')
        fb.op('JNull', reg=no_, offset=u + 'l')
        fb.op('JEq', a=no_, b=1, offset=u + 'l')  # areAtWar(us, us) logs a vanilla warning per call
        fb.op('Incr', dst=ne_o)
        fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', _state(fb, b, cx), 1, no_), offset=u + 'l')
        fb.op('Incr', dst=ne_n)
        fb.op('JAlways', offset=u + 'l')
        fb.label(u + 'c')
        fb.op('JSGte', a=ne_n, b=b.const('i32', TURRET_EXPOSED), offset=u + 'y')
        fb.op('Call3', dst=hops, fun=gdb.findex.value, arg0=z, arg1=1, arg2=gnull)
        fb.op('JSGte', a=hops, b=b.const('i32', 99), offset=u + 'm')  # no main base: no measure
        fb.op('JSGte', a=hops, b=b.const('i32', TURRET_REMOTE), offset=u + 'y')
        # the gate to our main base: borders it and >= TURRET_BASE_GATE zones of any other faction, at war or not (user)
        fb.op('JNotEq', a=hops, b=b.const('i32', 1), offset=u + 'm')
        fb.op('JSGte', a=ne_o, b=b.const('i32', TURRET_BASE_GATE), offset=u + 'y')
        fb.label(u + 'm')
        # the map's centre zone (zone at the mean village position) or one bordering it: every faction's way across
        # the map passes there (Harkonnen's Tuorekh, 195 from the centre)
        vl = b.field(_state(fb, b, cx), 'villages')
        fb.op('JNull', reg=vl, offset=u + 'd')
        vn = b.field(vl, 'length')
        fb.op('JSLte', a=vn, b=zi, offset=u + 'd')
        fb.op('Mov', dst=cxs, src=b.const('f64', 0))
        fb.op('Mov', dst=cys, src=b.const('f64', 0))
        fb.op('Mov', dst=kk, src=zi)
        b.loop_head(u + 'v')
        fb.op('JSGte', a=kk, b=vn, offset=u + 'vd')
        vv = b.cast(b.call('hl.types.ArrayObj.getDyn', vl, kk), 'ent.Entity')
        fb.op('Incr', dst=kk)
        fb.op('JNull', reg=vv, offset=u + 'v')
        fb.op('Add', dst=cxs, a=cxs, b=b.field(vv, 'posx'))
        fb.op('Add', dst=cys, a=cys, b=b.field(vv, 'posy'))
        fb.op('JAlways', offset=u + 'v')
        fb.label(u + 'vd')
        vnf = fb.reg(cx.t('f64'))
        fb.op('ToSFloat', dst=vnf, src=vn)
        fb.op('SDiv', dst=cxs, a=cxs, b=vnf)
        fb.op('SDiv', dst=cys, a=cys, b=vnf)
        gm = fb.reg(cx.t('$Game'))
        fb.op('GetGlobal', dst=gm, **{'global': cx.global_of('$Game')})
        wd = b.field(b.field(gm, 'inst'), 'world')
        fb.op('JNull', reg=wd, offset=u + 'd')
        cz = b.call('world.World.getZoneAt', wd, cxs, cys)
        fb.op('JNull', reg=cz, offset=u + 'd')
        fb.op('JEq', a=cz, b=z, offset=u + 'cy')
        fb.op('JNull', reg=nb, offset=u + 'd')
        fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', nb, fb.dyn(cz)), offset=u + 'd')
        fb.label(u + 'cy')
        fb.op('Bool', dst=cen, value=True)
        fb.label(u + 'y')
        fb.op('Bool', dst=ex, value=True)
        fb.label(u + 'd')

    tres = _global_map(fb, b, cx, 'tres')  # village -> when we demolished a building there for its battery
    fb.op('JEq', a=b.call('String.__compare', ks, fb.dyn(battery)), b=zi, offset='isbat')
    # another building on an exposed village whose slot we freed for its battery: dropped (NaN) until the battery
    # stands or TRES_T passes (vanilla would refill the slot and the next scoring would demolish again)
    trv = b.call('haxe.ds.ObjectMap.get', tres, fb.dyn(s))
    fb.op('JNull', reg=trv, offset='end')
    tq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=tq, src=trv)
    fb.op('Sub', dst=tq, a=now, b=tq)
    fb.op('JSGt', a=tq, b=b.const('f64', TRES_T), offset='end')
    fb.op('JNotNull', reg=get_kind(battery), offset='end')
    exposed()
    fb.op('JFalse', cond=ex, offset='end')  # the front moved on: the village builds freely again
    zf = b.const('f64', 0)
    fb.op('SDiv', dst=res, a=zf, b=zf)  # NaN: vanilla drops the pair
    fb.op('JAlways', offset='end')
    fb.label('isbat')
    # can a battery go up here now (or once paid)? the check checkBuildings runs before doAddBuilding
    ca = cx.fn('logic.Upgrades.checkAddUpgrade')
    cat = [a.value for a in cx.code.types[ca.type.value].definition.args]
    cret = cx.code.types[ca.type.value].definition.ret.value
    rnames = [c_.name.resolve(cx.code) for c_ in cx.code.types[cret].definition.constructs]
    dref = fb.reg(cat[2])
    fb.op('Ref', dst=dref, src=b.const('i32', 0))
    cnul = []
    for t_ in cat[3:]:
        r_ = fb.reg(t_)
        fb.op('Null', dst=r_)
        cnul.append(r_)
    rr = fb.reg(cret)
    fb.op('CallN', dst=rr, fun=ca.findex.value, args=[up, battery, dref] + cnul)
    ri = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ri, value=rr)
    h = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=h, src=b.const('f64', 0))
    # exposed village without a battery: build one; full -> demolish by TURRET_DEMOLISH order when it's affordable
    exposed()
    fb.op('JFalse', cond=ex, offset='stand')
    fb.op('JNotNull', reg=get_kind(battery), offset='stand')
    fb.op('JEq', a=ri, b=b.const('i32', rnames.index('Success')), offset='boost')
    fb.op('JEq', a=ri, b=b.const('i32', rnames.index('MissingResources')), offset='boost')
    fb.op('JNotEq', a=ri, b=b.const('i32', rnames.index('VillageUpgradesLimitReached')), offset='end')
    # a demolition here within TRES_T: removeUpgrade(uid, null) only starts demolishUpgrade, the slot stays taken
    # until it ends; neither demolish the next building nor boost (picked while full, checkBuildings' replace path
    # would remove whatever scores lowest on vanilla's own score)
    tr2 = b.call('haxe.ds.ObjectMap.get', tres, fb.dyn(s))
    fb.op('JNull', reg=tr2, offset='dmok')
    tq2 = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=tq2, src=tr2)
    fb.op('Sub', dst=tq2, a=now, b=tq2)
    fb.op('JSLte', a=tq2, b=b.const('f64', TRES_T), offset='end')
    fb.label('dmok')
    ctl = b.field(1, 'aiController')
    fb.op('JNull', reg=ctl, offset='end')
    gc = cx.fn('logic.Upgrades.getCost')
    gct = [a.value for a in cx.code.types[gc.type.value].definition.args]
    gcn = []
    for t_ in gct[2:]:
        r_ = fb.reg(t_)
        fb.op('Null', dst=r_)
        gcn.append(r_)
    cost = fb.reg(cx.code.types[gc.type.value].definition.ret.value)
    fb.op('CallN', dst=cost, fun=gc.findex.value, args=[up, battery] + gcn)
    fb.op('JNull', reg=cost, offset='end')
    miss = b.call('logic.ai.AIController.getMissingResources', ctl, cost, fb.dyn(b.const('i32', 3)))
    fb.op('JNull', reg=miss, offset='afford')
    fb.op('JSGt', a=b.field(miss, 'length'), b=zi, offset='end')  # not affordable now: keep the building, no gap
    fb.label('afford')
    rm = cx.fn('logic.Upgrades.removeUpgrade')
    rmt = [a.value for a in cx.code.types[rm.type.value].definition.args]
    rmret = cx.code.types[rm.type.value].definition.ret.value
    rmnames = [c_.name.resolve(cx.code) for c_ in cx.code.types[rmret].definition.constructs]
    inst = fb.reg(rmt[2])
    fb.op('Null', dst=inst)
    rr2, ri2 = fb.reg(rmret), fb.reg(cx.t('i32'))
    uid = fb.reg(cx.t('i32'))
    for kind in TURRET_DEMOLISH:
        nxt = _uid('dm')
        u = get_kind(fb.string(kind))
        fb.op('JNull', reg=u, offset=nxt)
        fb.op('SafeCast', dst=uid, src=fb.get(u, 'uid'))
        fb.op('CallN', dst=rr2, fun=rm.findex.value, args=[up, uid, inst])
        fb.op('EnumIndex', dst=ri2, value=rr2)
        fb.op('JNotEq', a=ri2, b=b.const('i32', rmnames.index('Success')), offset='end')
        b.call('haxe.ds.ObjectMap.set', tres, fb.dyn(s), fb.dyn(now))
        _log_ev(fb, b, cx, helpers, 'tdem', [('f', fb.get(1, 'kind')), ('s', s), ('k', fb.string(kind)),
                                             ('n', fb.dyn(ne_n)), ('hops', fb.dyn(hops)),
                                             ('cen', cen)])
        fb.op('JAlways', offset='end')  # boosted once the demolition has freed the slot (Success / MissingResources)
        fb.label(nxt)
    fb.op('JAlways', offset='end')  # full, none of them there: keep the village as it is
    fb.label('stand')
    fb.op('Call3', dst=h, fun=threat, arg0=1, arg1=se, arg2=b.const('f64', STAND_R))
    stnd = _global_map(fb, b, cx, 'stnd')
    fb.op('JSGte', a=h, b=b.const('f64', STAND_MIN_H), offset='standing')
    b.call('haxe.ds.ObjectMap.remove', stnd, fb.dyn(s))
    fb.op('JAlways', offset='end')
    fb.label('standing')
    # scoring runs only now and then: a record not refreshed for 2 x STAND_T is an earlier, ended standoff (a stack
    # that passed, left unseen and came back much later must stand STAND_T again)
    stnl = _global_map(fb, b, cx, 'stnl')
    el = fb.reg(cx.t('f64'))
    last = b.call('haxe.ds.ObjectMap.get', stnl, fb.dyn(s))
    b.call('haxe.ds.ObjectMap.set', stnl, fb.dyn(s), fb.dyn(now))
    fb.op('JNull', reg=last, offset='fresh')
    fb.op('SafeCast', dst=el, src=last)
    fb.op('Sub', dst=el, a=now, b=el)
    fb.op('JSGt', a=el, b=b.const('f64', 2 * STAND_T), offset='fresh')
    first = b.call('haxe.ds.ObjectMap.get', stnd, fb.dyn(s))
    fb.op('JNotNull', reg=first, offset='seen')
    fb.label('fresh')
    b.call('haxe.ds.ObjectMap.set', stnd, fb.dyn(s), fb.dyn(now))
    fb.op('JAlways', offset='end')
    fb.label('seen')
    fb.op('SafeCast', dst=el, src=first)
    fb.op('Sub', dst=el, a=now, b=el)
    fb.op('JSLt', a=el, b=b.const('f64', STAND_T), offset='end')
    ne = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=ne)
    na = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=na)
    t_true = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_true, value=True)
    c = fb.reg(cx.t('f64'))
    fb.op('CallN', dst=c, fun=cover, args=[1, se, ne, t_true, na])
    # enough turrets of ours (the partner's count) already hold it: cover >= ENTER x the standing power
    hx = fb.reg(cx.t('f64'))
    fb.op('Mul', dst=hx, a=h, b=_ratio(fb, b, ENTER))
    fb.op('JSGte', a=c, b=hx, offset='end')
    # only a battery that can be built now or once paid for: a full village (VillageUpgradesLimitReached) would be
    # picked over and over, and in combat / occupied vanilla only queues it (the same check checkBuildings runs
    # before doAddBuilding); demolishing for a slot is the exposed case's only
    fb.op('JEq', a=ri, b=b.const('i32', rnames.index('Success')), offset='boost')
    fb.op('JNotEq', a=ri, b=b.const('i32', rnames.index('MissingResources')), offset='end')
    fb.label('boost')
    v0 = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=v0, src=res)
    zero = b.const('f64', 0)
    fb.op('JSGte', a=res, b=zero, offset='pos')
    fb.op('Mov', dst=res, src=zero)
    fb.label('pos')
    fb.op('Add', dst=res, a=res, b=b.const('f64', STAND_BONUS))
    _throttle(fb, b, cx, 'turret', s, 30, 'end')
    _log_ev(fb, b, cx, helpers, 'turret', [('f', fb.get(1, 'kind')), ('s', s), ('h', h), ('sc', v0), ('n', fb.dyn(ne_n)),
                                          ('hops', fb.dyn(hops)), ('cen', cen)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    # only the pick's scoring closure (scoring_logic_ai_AIStructureBuilding): checkBuildings re-scores the pick and
    # the village's existing buildings for VillageUpgradesLimitReached and demolishes any scoring below the pick, so
    # a bonus there would tear down a standoff village's economy for a turret
    skip = {w, inner, cx.fn('logic.ai.BuildingManager.checkBuildings').findex.value}
    sites = [op for g in cx.code.functions if g.findex.value not in skip for op in g.ops
             if op.op.startswith('Call') and op.df.get('fun') is not None and op.df['fun'].value == oid]
    if len(sites) != 1:
        raise ValueError(f'turret-steer: expected 1 scoring-closure call of getBuildingStructureScore, found {len(sites)}')
    sites[0].df['fun'].value = w
    return {'turret-steer': 1}
