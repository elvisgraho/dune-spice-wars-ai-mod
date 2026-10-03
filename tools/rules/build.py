"""Turret steering (AI-POLICY §5a goal 2, standoff): a village that at-war armies keep standing next to, or a front
village, gets a MissileBattery first.

Front village: our village (on our land, not a main base) whose zone borders >= TURRET_EXPOSED zones held by
factions at war with us, or that lies >= TURRET_REMOTE zones from our main base (Zone.getDistanceToPlayerBase: too
far for a relief to come in time), or that borders our main base's zone and >= TURRET_BASE_GATE zones of any other faction
(at war or not: the way into our base), or that lies >= REMOTE_D from our nearest active main base in a straight line (big zones: Harkonnen's Odlab, 386
from Carthag, 2 hops), or that is the map's centre zone or borders it (zone at the mean village
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
(below its defense minimum) is lifted; NaN (invalid pair) is kept. Every other MissileBattery pair scores NaN (dropped):
a battery only where a rule above calls for one (user: vanilla's map-exposure score put one on Harkonnen's Yedah, a
Manpower village no rule saw as a front); logs `tveto` (s, sc vanilla score > 0, n, hops) once per village per 60 s. A standing record not refreshed for 2 x STAND_T
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
        # far in a straight line from our main base (big zones: Harkonnen's Odlab, 386 from Carthag, 2 hops)
        bdist = _base_dist(fb, b, s, 1)
        fb.op('JSGte', a=bdist, b=b.const('f64', 1 << 29), offset=u + 'nb')  # no main base of ours
        fb.op('JSGte', a=bdist, b=b.const('f64', REMOTE_D), offset=u + 'y')
        fb.label(u + 'nb')
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
    fb.op('JAlways', offset='nobat')
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
    fb.op('JAlways', offset='nobat')
    fb.label('seen')
    fb.op('SafeCast', dst=el, src=first)
    fb.op('Sub', dst=el, a=now, b=el)
    fb.op('JSLt', a=el, b=b.const('f64', STAND_T), offset='nobat')
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
    fb.op('JSGte', a=c, b=hx, offset='nobat')
    # only a battery that can be built now or once paid for: a full village (VillageUpgradesLimitReached) would be
    # picked over and over, and in combat / occupied vanilla only queues it (the same check checkBuildings runs
    # before doAddBuilding); demolishing for a slot is the exposed case's only
    fb.op('JEq', a=ri, b=b.const('i32', rnames.index('Success')), offset='boost')
    fb.op('JNotEq', a=ri, b=b.const('i32', rnames.index('MissingResources')), offset='nobat')
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
    fb.op('JAlways', offset='end')
    # no rule of ours calls for a battery here: dropped (NaN), whatever vanilla's map-exposure score says (user:
    # Harkonnen built one at Yedah, a Manpower village no rule of ours saw as a front)
    fb.label('nobat')
    vs = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=vs, src=res)
    fz = b.const('f64', 0)
    fb.op('SDiv', dst=res, a=fz, b=fz)
    fb.op('JSLte', a=vs, b=fz, offset='end')
    _throttle(fb, b, cx, 'tveto', s, 60, 'end')
    _log_ev(fb, b, cx, helpers, 'tveto', [('f', fb.get(1, 'kind')), ('s', s), ('sc', vs), ('n', fb.dyn(ne_n)),
                                          ('hops', fb.dyn(hops))])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    # only the pick's scoring closure (scoring_logic_ai_AIStructureBuilding): checkBuildings re-scores the pick and
    # the village's existing buildings for VillageUpgradesLimitReached and demolishes any scoring below the pick, so
    # a bonus there would tear down a standoff village's economy for a turret
    skip = set(new_ids) | {w, inner, cx.fn('logic.ai.BuildingManager.checkBuildings').findex.value}  # our wrappers (chained)
    sites = [op for g in cx.code.functions if g.findex.value not in skip for op in g.ops
             if op.op.startswith('Call') and op.df.get('fun') is not None and op.df['fun'].value == oid]
    if len(sites) != 1:
        raise ValueError(f'turret-steer: expected 1 scoring-closure call of getBuildingStructureScore, found {len(sites)}')
    sites[0].df['fun'].value = w
    return {'turret-steer': 1}


def build_spice_first(cx, helpers, new_ids, inner):
    """Spice first (user: the first building on a spice village is its harvester): score wrapper for
    getBuildingStructureScore (pair {s, k}, f, context, noStocks) called by turret-steer instead of `inner`. For a
    village s of ours on our land whose zone has spice (Zone.hasSpice) and holds no Refinery yet (Upgrades.getKind),
    while a Refinery can go up there now or once paid (checkAddUpgrade Success / MissingResources): the Refinery pair
    scores max(score, 0) + SPICE_FIRST_W, every other pair on that village NaN (dropped), so vanilla's weighted pick
    (Insane: best 2) can't put a Marketplace or a battery first and the village saves for its harvester. Vanilla gave
    the Refinery base + aiWeight 10, below village-bonus buildings (upgrade factor x 10) and under-produced resources.
    Refinery not buildable (notForFactions Fremen / Vernius, full, occupied): untouched. A remote village that wants
    an Airfield (airfield-steer's test) builds that first: untouched until its Airfield stands or goes up (log `rfaf`
    s). Log `rfirst` (s, sc vanilla) once per village per 60 s. Fails safe: inner's score on error."""
    orig = cx.fn('logic.ai.$HScoring.getBuildingStructureScore')
    ft = cx.code.types[orig.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Call4', dst=res, fun=inner, arg0=0, arg1=1, arg2=2, arg3=3)  # outside the trap
    guard = fb.try_()
    fb.op('JSGte', a=res, b=b.const('f64', -(1 << 30)), offset='real')  # NaN = not buildable: keep it
    fb.op('JAlways', offset='end')
    fb.label('real')
    fb.op('JNull', reg=1, offset='end')
    so = fb.get(0, 's')
    fb.op('JNull', reg=so, offset='end')
    s = b.cast(so, 'ent.Structure')
    fb.op('JNull', reg=s, offset='end')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', s), offset='end')
    z = b.call('ent.Entity.get_zone', s)
    fb.op('JNull', reg=z, offset='end')
    fb.op('JNotEq', a=b.field(z, 'owner'), b=1, offset='end')  # our land (not an Underworld HQ in theirs)
    fb.op('JFalse', cond=b.call('ent.Zone.hasSpice', z), offset='end')
    # SPICE_ANY (Fremen, Vernius: Refinery notForFactions) never get one: no per-pair checks, no `rnot` noise
    fkd = b.field(1, 'kind')
    fb.op('JNull', reg=fkd, offset='end')
    for nm in SPICE_ANY:
        fb.op('JEq', a=b.call('String.__compare', fkd, fb.dyn(fb.string(nm))), b=b.const('i32', 0), offset='end')
    up = b.field(s, 'upgrades')
    fb.op('JNull', reg=up, offset='end')
    refinery = fb.string('Refinery')
    gk = cx.fn('logic.Upgrades.getKind')
    gkt = [a.value for a in cx.code.types[gk.type.value].definition.args]
    gkn = []
    for t_ in gkt[2:]:
        r_ = fb.reg(t_)
        fb.op('Null', dst=r_)
        gkn.append(r_)
    ku = fb.reg(cx.code.types[gk.type.value].definition.ret.value)
    fb.op('CallN', dst=ku, fun=gk.findex.value, args=[up, refinery] + gkn)
    fb.op('JNotNull', reg=ku, offset='end')  # has its harvester building (built or going up)
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
    fb.op('CallN', dst=rr, fun=ca.findex.value, args=[up, refinery, dref] + cnul)
    ri = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ri, value=rr)
    _write_names(rnames)
    fb.op('JEq', a=ri, b=b.const('i32', rnames.index('Success')), offset='can')
    fb.op('JEq', a=ri, b=b.const('i32', rnames.index('MissingResources')), offset='can')
    # a spice village of ours where no Refinery can go up (full of an earlier owner's buildings after a capture,
    # occupied, ...): untouched, logged `rnot` (r = checkAddUpgrade result, named in mod log via work/eresult.json)
    # once per village per 300 s: the evidence for a demolition path (as turret-steer's) if full villages show up
    # transient (a building going up, a fight at the village): the next scoring after it lifts it; not logged
    for nm in ('ConstructionInProgress', 'IsInCombat', 'UpgradeInProgress'):
        fb.op('JEq', a=ri, b=b.const('i32', rnames.index(nm)), offset='end')
    rse = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=rse, src=s)
    _throttle(fb, b, cx, 'rnot', rse, 300, 'end')
    rif = fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=rif, src=ri)
    _log_ev(fb, b, cx, helpers, 'rnot', [('f', fb.get(1, 'kind')), ('s', rse), ('r', rif)])
    fb.op('JAlways', offset='end')
    fb.label('can')
    # a remote village that wants an Airfield (airfield-steer's measure: remote, not behind our base, none of ours
    # within AF_SPACING, one can go up): the Airfield first, then the Refinery (user: Atreides' Marmah, 594 from
    # Arrakeen, saved for its Refinery while armies walked the whole way)
    sfe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=sfe, src=s)
    airfield = fb.string('Airfield')
    _af_remote(fb, b, cx, s, z, 1, 'afrem', 'afno', 'afno')
    fb.label('afrem')
    fb.op('CallN', dst=ku, fun=gk.findex.value, args=[up, airfield] + gkn)
    fb.op('JNotNull', reg=ku, offset='afno')  # its Airfield stands or goes up: the Refinery's turn
    fb.op('JTrue', cond=_af_behind(fb, b, cx, sfe, 1, 'afno'), offset='afno')
    fb.op('JTrue', cond=_af_spaced(fb, b, cx, s, sfe, 1, airfield, gk, gkn, ku), offset='afno')
    fb.op('CallN', dst=rr, fun=ca.findex.value, args=[up, airfield, dref] + cnul)
    fb.op('EnumIndex', dst=ri, value=rr)
    fb.op('JEq', a=ri, b=b.const('i32', rnames.index('Success')), offset='afyes')
    fb.op('JNotEq', a=ri, b=b.const('i32', rnames.index('MissingResources')), offset='afno')
    fb.label('afyes')
    _throttle(fb, b, cx, 'rfaf', sfe, 60, 'end')
    _log_ev(fb, b, cx, helpers, 'rfaf', [('f', fb.get(1, 'kind')), ('s', sfe)])
    fb.op('JAlways', offset='end')
    fb.label('afno')
    k = fb.get(0, 'k')
    fb.op('JNull', reg=k, offset='end')
    ks = b.cast(k, 'String')
    fb.op('JEq', a=b.call('String.__compare', ks, fb.dyn(refinery)), b=b.const('i32', 0), offset='isref')
    fb.op('Mov', dst=res, src=_nan_f(fb, b, cx))  # anything else waits for the harvester building
    fb.op('JAlways', offset='end')
    fb.label('isref')
    v0 = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=v0, src=res)
    fb.op('JSGte', a=res, b=b.const('f64', 0), offset='pos')
    fb.op('Mov', dst=res, src=b.const('f64', 0))
    fb.label('pos')
    fb.op('Add', dst=res, a=res, b=b.const('f64', SPICE_FIRST_W))
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=s)
    _throttle(fb, b, cx, 'rfirst', se, 60, 'end')
    _log_ev(fb, b, cx, helpers, 'rfirst', [('f', fb.get(1, 'kind')), ('s', se), ('sc', v0)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    return w


def build_wonder(cx, helpers, new_ids, inner):
    """Wonder steering (user: the Spacing Guild Branch went up in easily contested villages near the map's middle).
    Score wrapper for getBuildingStructureScore (pair {s, k}, f, context, noStocks), called by the next wrapper up
    instead of `inner`. For k a wonder (WONDER_COST: cdb props.isWonder, one per faction) on a village s of ours on our
    land (not a main base):
    - never in the map's centre zone (zone at the mean village position) or a zone bordering it, nor in a front village
      (zone bordering >= TURRET_EXPOSED zones of at-war factions): NaN (dropped; log `wveto` why centre / front);
    - else score = max(score, 0) x (0.5 + near) x (0.5 + edge) x (1 + WONDER_DISC_W x disc) x boost, near = 1 - d(our
      nearest active main base) / WONDER_BASE_R (>= 0), edge = d(map centre) / farthest village's d(centre), disc = 1 -
      real cost at s (Upgrades.getCost: village traits Handymen -40% / Megalopolis -10%) / WONDER_COST (>= 0), boost =
      WONDER_BOOST_W where s's zone kind starts with WONDER_BOOST[k] (Space Wreck), else 1. Logs `wsteer` (s, k, sc
      vanilla, m multiplier x100, disc x100) once per village per 60 s.
    Every other pair: unchanged. Fails safe: inner's score on error."""
    orig = cx.fn('logic.ai.$HScoring.getBuildingStructureScore')
    ft = cx.code.types[orig.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Call4', dst=res, fun=inner, arg0=0, arg1=1, arg2=2, arg3=3)  # outside the trap
    guard = fb.try_()
    fb.op('JSGte', a=res, b=b.const('f64', -(1 << 30)), offset='real')  # NaN = not buildable: keep it
    fb.op('JAlways', offset='end')
    fb.label('real')
    fb.op('JNull', reg=1, offset='end')
    k = fb.get(0, 'k')
    fb.op('JNull', reg=k, offset='end')
    ks = b.cast(k, 'String')
    zi = b.const('i32', 0)
    base, boost = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    bpre = fb.reg(cx.t('String'))
    names = sorted(WONDER_COST)
    for n_, wid in enumerate(names):
        fb.op('JEq', a=b.call('String.__compare', ks, fb.dyn(fb.string(wid))), b=zi, offset=f'w{n_}')
    fb.op('JAlways', offset='end')
    for n_, wid in enumerate(names):
        fb.label(f'w{n_}')
        fb.op('Mov', dst=base, src=b.const('f64', WONDER_COST[wid]))
        if wid in WONDER_BOOST:
            fb.op('Mov', dst=bpre, src=fb.string(WONDER_BOOST[wid]))
        else:
            fb.op('Null', dst=bpre)
        fb.op('JAlways', offset='isw')
    fb.label('isw')
    so = fb.get(0, 's')
    fb.op('JNull', reg=so, offset='end')
    s = b.cast(so, 'ent.Structure')
    fb.op('JNull', reg=s, offset='end')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', s), offset='end')
    z = b.call('ent.Entity.get_zone', s)
    fb.op('JNull', reg=z, offset='end')
    fb.op('JNotEq', a=b.field(z, 'owner'), b=1, offset='end')  # our land
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=s)
    why = fb.reg(cx.t('String'))
    st = _state(fb, b, cx)
    # front: >= TURRET_EXPOSED at-war neighbour zones
    nb = b.field(z, 'neighbors')
    ne, i = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=ne, src=zi)
    fb.op('JNull', reg=nb, offset='nbd')
    fb.op('Mov', dst=i, src=zi)
    b.loop_head('nb')
    fb.op('JSGte', a=i, b=b.field(nb, 'length'), offset='nbd')
    nz = b.cast(b.call('hl.types.ArrayObj.getDyn', nb, i), 'ent.Zone')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=nz, offset='nb')
    no_ = b.field(nz, 'owner')
    fb.op('JNull', reg=no_, offset='nb')
    fb.op('JEq', a=no_, b=1, offset='nb')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', st, 1, no_), offset='nb')
    fb.op('Incr', dst=ne)
    fb.op('JAlways', offset='nb')
    fb.label('nbd')
    fb.op('Mov', dst=why, src=fb.string('front'))
    fb.op('JSGte', a=ne, b=b.const('i32', TURRET_EXPOSED), offset='veto')
    # map centre = mean village position; farthest village's distance to it
    vl = b.field(st, 'villages')
    fb.op('JNull', reg=vl, offset='end')
    vn = b.field(vl, 'length')
    fb.op('JSLte', a=vn, b=zi, offset='end')
    cxs, cys, dx, dy, dmx, q = (fb.reg(cx.t('f64')) for _ in range(6))
    fb.op('Mov', dst=cxs, src=b.const('f64', 0))
    fb.op('Mov', dst=cys, src=b.const('f64', 0))
    fb.op('Mov', dst=i, src=zi)
    b.loop_head('vc')
    fb.op('JSGte', a=i, b=vn, offset='vcd')
    vv = b.cast(b.call('hl.types.ArrayObj.getDyn', vl, i), 'ent.Entity')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=vv, offset='vc')
    fb.op('Add', dst=cxs, a=cxs, b=b.field(vv, 'posx'))
    fb.op('Add', dst=cys, a=cys, b=b.field(vv, 'posy'))
    fb.op('JAlways', offset='vc')
    fb.label('vcd')
    vnf = fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=vnf, src=vn)
    fb.op('SDiv', dst=cxs, a=cxs, b=vnf)
    fb.op('SDiv', dst=cys, a=cys, b=vnf)

    def dcen(dst, e):
        fb.op('Sub', dst=dx, a=b.field(e, 'posx'), b=cxs)
        fb.op('Sub', dst=dy, a=b.field(e, 'posy'), b=cys)
        fb.op('Mul', dst=dx, a=dx, b=dx)
        fb.op('Mul', dst=dy, a=dy, b=dy)
        fb.op('Add', dst=dst, a=dx, b=dy)
        fb.op('Mov', dst=dst, src=b.call('hxd.$Math.sqrt', dst))
    fb.op('Mov', dst=dmx, src=b.const('f64', 1))
    fb.op('Mov', dst=i, src=zi)
    b.loop_head('vm')
    fb.op('JSGte', a=i, b=vn, offset='vmd')
    vv2 = b.cast(b.call('hl.types.ArrayObj.getDyn', vl, i), 'ent.Entity')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=vv2, offset='vm')
    dcen(q, vv2)
    fb.op('JSLte', a=q, b=dmx, offset='vm')
    fb.op('Mov', dst=dmx, src=q)
    fb.op('JAlways', offset='vm')
    fb.label('vmd')
    # centre zone or bordering it
    gm = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gm, **{'global': cx.global_of('$Game')})
    wd = b.field(b.field(gm, 'inst'), 'world')
    fb.op('JNull', reg=wd, offset='end')
    cz = b.call('world.World.getZoneAt', wd, cxs, cys)
    fb.op('JNull', reg=cz, offset='nocen')
    fb.op('Mov', dst=why, src=fb.string('centre'))
    fb.op('JEq', a=cz, b=z, offset='veto')
    fb.op('JNull', reg=nb, offset='nocen')
    fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', nb, fb.dyn(cz)), offset='veto')
    fb.label('nocen')
    m, t2 = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    one = b.const('f64', 1)
    half = _ratio(fb, b, 0.5)
    # near our base
    fb.op('SDiv', dst=t2, a=_base_dist(fb, b, s, 1), b=b.const('f64', WONDER_BASE_R))
    fb.op('Sub', dst=t2, a=one, b=t2)
    fb.op('JSGte', a=t2, b=b.const('f64', 0), offset='nr')
    fb.op('Mov', dst=t2, src=b.const('f64', 0))
    fb.label('nr')
    fb.op('Add', dst=m, a=t2, b=half)
    # far from the centre
    dcen(q, se)
    fb.op('SDiv', dst=t2, a=q, b=dmx)
    fb.op('Add', dst=t2, a=t2, b=half)
    fb.op('Mul', dst=m, a=m, b=t2)
    # building discount at this village (real cost / base)
    disc = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=disc, src=b.const('f64', 0))
    up = b.field(s, 'upgrades')
    fb.op('JNull', reg=up, offset='dd')
    gc = cx.fn('logic.Upgrades.getCost')
    gct = [a.value for a in cx.code.types[gc.type.value].definition.args]
    gcn = []
    for t_ in gct[2:]:
        r_ = fb.reg(t_)
        fb.op('Null', dst=r_)
        gcn.append(r_)
    cost = fb.reg(cx.code.types[gc.type.value].definition.ret.value)
    fb.op('CallN', dst=cost, fun=gc.findex.value, args=[up, ks] + gcn)
    fb.op('JNull', reg=cost, offset='dd')
    tot, qv = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=tot, src=b.const('f64', 0))
    fb.op('Mov', dst=i, src=zi)
    b.loop_head('cs')
    fb.op('JSGte', a=i, b=b.field(cost, 'length'), offset='csd')
    qd = fb.get(b.call('hl.types.ArrayObj.getDyn', cost, i), 'qty')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=qd, offset='cs')
    fb.op('SafeCast', dst=qv, src=qd)
    fb.op('Add', dst=tot, a=tot, b=qv)
    fb.op('JAlways', offset='cs')
    fb.label('csd')
    fb.op('JSLte', a=tot, b=b.const('f64', 0), offset='dd')
    fb.op('SDiv', dst=disc, a=tot, b=base)
    fb.op('Sub', dst=disc, a=one, b=disc)
    fb.op('JSGte', a=disc, b=b.const('f64', 0), offset='dd')
    fb.op('Mov', dst=disc, src=b.const('f64', 0))
    fb.label('dd')
    fb.op('Mul', dst=t2, a=disc, b=_ratio(fb, b, WONDER_DISC_W))
    fb.op('Add', dst=t2, a=t2, b=one)
    fb.op('Mul', dst=m, a=m, b=t2)
    # production boost (Space Wreck for the Guild Branch / Recycling Plant)
    fb.op('JNull', reg=bpre, offset='nob')
    kd = b.field(z, 'kind')
    fb.op('JNull', reg=kd, offset='nob')
    fb.op('JFalse', cond=b.call('$StringTools.startsWith', kd, bpre), offset='nob')
    fb.op('Mul', dst=m, a=m, b=_ratio(fb, b, WONDER_BOOST_W))
    fb.label('nob')
    v0 = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=v0, src=res)
    fb.op('JSGte', a=res, b=b.const('f64', 0), offset='pos')
    fb.op('Mov', dst=res, src=b.const('f64', 0))
    fb.label('pos')
    fb.op('Mul', dst=res, a=res, b=m)
    _throttle(fb, b, cx, 'wsteer', se, 60, 'end')
    _log_ev(fb, b, cx, helpers, 'wsteer', [('f', fb.get(1, 'kind')), ('s', se), ('k', ks), ('sc', v0), ('m%', m),
                                           ('disc%', disc)])
    fb.op('JAlways', offset='end')
    fb.label('veto')
    fb.op('Mov', dst=v0, src=res)
    fb.op('Mov', dst=res, src=_nan_f(fb, b, cx))
    _throttle(fb, b, cx, 'wveto', se, 60, 'end')
    _log_ev(fb, b, cx, helpers, 'wveto', [('f', fb.get(1, 'kind')), ('s', se), ('k', ks), ('why', why), ('sc', v0)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    return w


def _af_can(fb, b, cx, up, airfield):
    """Bool register: Upgrades.checkAddUpgrade(up, Airfield) is Success or MissingResources (can go up now or once
    paid; not full, occupied, in combat, ...)."""
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
    fb.op('CallN', dst=rr, fun=ca.findex.value, args=[up, airfield, dref] + cnul)
    ri = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ri, value=rr)
    ok = fb.reg(cx.t('bool'))
    u = _uid('afc')
    fb.op('Bool', dst=ok, value=True)
    fb.op('JEq', a=ri, b=b.const('i32', rnames.index('Success')), offset=u)
    fb.op('JEq', a=ri, b=b.const('i32', rnames.index('MissingResources')), offset=u)
    fb.op('Bool', dst=ok, value=False)
    fb.label(u)
    return ok


def build_airfield(cx, helpers, threat, new_ids, inner):
    """Airfield steering (user: remote villages get an Airfield to aid travel, then their battery; airfields spaced;
    none in a corner behind our base). Score wrapper for getBuildingStructureScore (pair {s, k}, f, context,
    noStocks), called by turret-steer instead of `inner`. For a village s of ours on our land (not a main base):
    - remote: >= TURRET_REMOTE zones from our main base (Zone.getDistanceToPlayerBase) or >= REMOTE_D in a straight
      line from our nearest active main base B;
    - behind: for every other faction's active main base M, d(s, M) >= d(B, M) (s lies between us and the map border:
      Harkonnen's Harur, 309 west of Carthag at the map's edge, got a vanilla Airfield no army ever used);
    - spaced: another Airfield of ours (Upgrades.getKind: built or going up) within AF_SPACING of s.
    want = remote, not behind, not spaced, no Airfield at s, and an Airfield can go up there now or once paid
    (checkAddUpgrade Success / MissingResources; Fremen: notForFactions, never).
    k = Airfield: want -> max(score, 0) + AF_BONUS (log `afield` s, sc, d, hops once per village per 60 s); behind or
    spaced -> NaN, vanilla's own airfield pick dropped (log `afveto` s, why, d once per village per 60 s); else vanilla.
    k = MissileBattery while want: NaN (the Airfield first; turret-steer's boost / demolition wait for the next
    scoring), unless at-war power >= STAND_MIN_H stands within STAND_R (a standoff: the battery goes first) or
    turret-steer freed a slot there for the battery within TRES_T (map `tres`: that slot is the battery's). A full
    village (no Airfield possible) builds its battery first.
    Every other pair: unchanged. Fails safe: inner's score on error."""
    orig = cx.fn('logic.ai.$HScoring.getBuildingStructureScore')
    ft = cx.code.types[orig.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Call4', dst=res, fun=inner, arg0=0, arg1=1, arg2=2, arg3=3)  # outside the trap
    guard = fb.try_()
    fb.op('JSGte', a=res, b=b.const('f64', -(1 << 30)), offset='real')  # NaN = not buildable: keep it
    fb.op('JAlways', offset='end')
    fb.label('real')
    fb.op('JNull', reg=1, offset='end')
    k = fb.get(0, 'k')
    fb.op('JNull', reg=k, offset='end')
    ks = b.cast(k, 'String')
    zi = b.const('i32', 0)
    airfield, battery = fb.string('Airfield'), fb.string('MissileBattery')
    isaf = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=isaf, value=True)
    fb.op('JEq', a=b.call('String.__compare', ks, fb.dyn(airfield)), b=zi, offset='kind')
    fb.op('Bool', dst=isaf, value=False)
    fb.op('JNotEq', a=b.call('String.__compare', ks, fb.dyn(battery)), b=zi, offset='end')
    fb.label('kind')
    so = fb.get(0, 's')
    fb.op('JNull', reg=so, offset='end')
    s = b.cast(so, 'ent.Structure')
    fb.op('JNull', reg=s, offset='end')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', s), offset='end')
    z = b.call('ent.Entity.get_zone', s)
    fb.op('JNull', reg=z, offset='end')
    fb.op('JNotEq', a=b.field(z, 'owner'), b=1, offset='end')  # our land (not an Underworld HQ in theirs)
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=s)
    up = b.field(s, 'upgrades')
    fb.op('JNull', reg=up, offset='end')
    gk = cx.fn('logic.Upgrades.getKind')
    gkt = [a.value for a in cx.code.types[gk.type.value].definition.args]
    gkn = []
    for t_ in gkt[2:]:
        r_ = fb.reg(t_)
        fb.op('Null', dst=r_)
        gkn.append(r_)
    ku = fb.reg(cx.code.types[gk.type.value].definition.ret.value)
    why = fb.reg(cx.t('String'))
    # remote?
    db, hops = _af_remote(fb, b, cx, s, z, 1, 'remote', 'near', 'end')
    fb.label('near')
    # not remote: an Airfield pick stands only where it isn't behind us / next to another (checks below), a battery
    # is turret-steer's
    fb.op('JFalse', cond=isaf, offset='end')
    fb.label('remote')
    behind = _af_behind(fb, b, cx, se, 1, 'end')
    spaced = _af_spaced(fb, b, cx, s, se, 1, airfield, gk, gkn, ku)
    fb.op('JFalse', cond=isaf, offset='bat')
    # --- Airfield pair
    fb.op('JTrue', cond=behind, offset='veto_b')
    fb.op('JTrue', cond=spaced, offset='veto_s')
    fb.op('JSGte', a=db, b=b.const('f64', REMOTE_D), offset='boost')
    fb.op('JSGte', a=hops, b=b.const('i32', 99), offset='end')
    fb.op('JSGte', a=hops, b=b.const('i32', TURRET_REMOTE), offset='boost')
    fb.op('JAlways', offset='end')  # not remote: vanilla's own pick, spaced and not behind
    fb.label('veto_b')
    fb.op('Mov', dst=why, src=fb.string('behind'))
    fb.op('JAlways', offset='veto')
    fb.label('veto_s')
    fb.op('Mov', dst=why, src=fb.string('spaced'))
    fb.label('veto')
    vs = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=vs, src=res)
    fb.op('Mov', dst=res, src=_nan_f(fb, b, cx))
    _throttle(fb, b, cx, 'afveto', se, 60, 'end')
    _log_ev(fb, b, cx, helpers, 'afveto', [('f', fb.get(1, 'kind')), ('s', se), ('why', why), ('sc', vs), ('d', db)])
    fb.op('JAlways', offset='end')
    fb.label('boost')
    # only while s has no Airfield (built or going up) and one can go up now or once paid: the boost ran on with the
    # Airfield standing (Atreides' Zadak: `afield` rows 17:00-66:00, Airfield picked at 17:00)
    fb.op('CallN', dst=ku, fun=gk.findex.value, args=[up, airfield] + gkn)
    fb.op('JNotNull', reg=ku, offset='end')
    fb.op('JFalse', cond=_af_can(fb, b, cx, up, airfield), offset='end')
    v0 = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=v0, src=res)
    fb.op('JSGte', a=res, b=b.const('f64', 0), offset='pos')
    fb.op('Mov', dst=res, src=b.const('f64', 0))
    fb.label('pos')
    fb.op('Add', dst=res, a=res, b=b.const('f64', AF_BONUS))
    _throttle(fb, b, cx, 'afield', se, 60, 'end')
    hf = fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=hf, src=hops)
    _log_ev(fb, b, cx, helpers, 'afield', [('f', fb.get(1, 'kind')), ('s', se), ('sc', v0), ('d', db), ('hops', hf)])
    fb.op('JAlways', offset='end')
    # --- MissileBattery pair on a remote village: the Airfield first while one is wanted and can go up
    fb.label('bat')
    fb.op('JTrue', cond=behind, offset='end')
    fb.op('JTrue', cond=spaced, offset='end')
    # a slot turret-steer freed for the battery (map `tres`, within TRES_T) is the battery's: deferring it would leave
    # the slot empty (turret-steer drops every other pair there meanwhile) and then hand it to the Airfield
    trv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'tres'), fb.dyn(s))
    fb.op('JNull', reg=trv, offset='notres')
    tq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=tq, src=trv)
    fb.op('Sub', dst=tq, a=b.field(_state(fb, b, cx), 'time'), b=tq)
    fb.op('JSLte', a=tq, b=b.const('f64', TRES_T), offset='end')
    fb.label('notres')
    fb.op('CallN', dst=ku, fun=gk.findex.value, args=[up, airfield] + gkn)
    fb.op('JNotNull', reg=ku, offset='end')  # has its Airfield (built or going up): the battery's turn
    fb.op('JFalse', cond=_af_can(fb, b, cx, up, airfield), offset='end')  # no Airfield possible: battery
    h = fb.reg(cx.t('f64'))
    fb.op('Call3', dst=h, fun=threat, arg0=1, arg1=se, arg2=b.const('f64', STAND_R))
    fb.op('JSGte', a=h, b=b.const('f64', STAND_MIN_H), offset='end')  # a standoff: the battery goes first
    fb.op('Mov', dst=res, src=_nan_f(fb, b, cx))
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    return w


def _write_names(names):
    """work/eresult.json: checkAddUpgrade result index -> name, for mod log. Both boot files build it in parallel
    processes (same content): private temp file, then swapped in; a swap blocked by the other writer is fine."""
    import json
    import os
    from pathlib import Path as _P
    out = _P(__file__).resolve().parents[2] / 'work' / 'eresult.json'
    tmp = out.with_name(f'eresult.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(names), encoding='utf-8')
    try:
        os.replace(tmp, out)
    except OSError:
        tmp.unlink(missing_ok=True)


def _nan_f(fb, b, cx):
    r = fb.reg(cx.t('f64'))
    z = b.const('f64', 0)
    fb.op('SDiv', dst=r, a=z, b=z)
    return r


def build_bpick(cx, helpers, new_ids):
    """Diagnostics: which building pair vanilla actually picks. In `BuildingManager.checkBuildings`, the first
    getBuildingStructureScore call after `pickMapWeight` scores the picked pair (`selectedBestScore`); it goes through
    this wrapper (vanilla result unchanged) that logs `bpick` (f, s, k, sc) once per village per 30 s: why remote
    villages kept `afield` +100 rows for minutes without an Airfield (Atreides Marmah / Sharas)."""
    orig = cx.fn('logic.ai.$HScoring.getBuildingStructureScore')
    cb = cx.fn('logic.ai.BuildingManager.checkBuildings')
    pmw = {f.findex.value for nm, f in cx.funcs.items() if 'pickMapWeight' in nm}
    ops = cb.ops
    k0 = next((i for i, op in enumerate(ops) if op.op.startswith('Call') and op.df.get('fun') is not None
               and op.df['fun'].value in pmw), None)
    if k0 is None:
        raise ValueError('bpick: no pickMapWeight call in checkBuildings')
    site = next((op for op in ops[k0:] if op.op.startswith('Call') and op.df.get('fun') is not None
                 and op.df['fun'].value == orig.findex.value), None)
    if site is None:
        raise ValueError('bpick: no getBuildingStructureScore call after pickMapWeight in checkBuildings')
    ft = cx.code.types[orig.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Call4', dst=res, fun=orig.findex.value, arg0=0, arg1=1, arg2=2, arg3=3)  # vanilla, outside the trap
    guard = fb.try_()
    fb.op('JNull', reg=1, offset='end')
    so = fb.get(0, 's')
    fb.op('JNull', reg=so, offset='end')
    s = b.cast(so, 'ent.Structure')
    fb.op('JNull', reg=s, offset='end')
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=s)
    _throttle(fb, b, cx, 'bpick', se, 30, 'end')
    _log_ev(fb, b, cx, helpers, 'bpick', [('f', fb.get(1, 'kind')), ('s', se), ('k', fb.get(0, 'k')), ('sc', res)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    site.df['fun'].value = w
    return {'bpick': 1}
