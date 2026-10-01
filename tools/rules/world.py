"""World model queries every rule reads (AI-POLICY §3): power, threat (at-war armies + neutral raiders targeting
us), neutral raiders, terrain, own power, free armies, our land, supply budget, turret cover, siege state,
defensive posture. Each builder appends one function and returns its findex."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def build_pw(cx):
    fb = FB(cx, [cx.t('ent.Unit')], cx.t('f64'))
    b = B(fb)
    r = b.call('$HPowerScore.singlePowerScore', b.call('$HCombatStats.unitCombatStats', 0))
    fb.op('Ret', ret=r)
    return fb.build()


def _raider_vs(fb, b, x, fac, yes, no):
    """Jump to `yes` if army x (owner null) is a neutral raider whose raid targets fac (Raid.targetFaction; the
    raid's own hostility test, Raid.isHostileWith), to `no` otherwise (not a raider, or raiding someone else)."""
    rd = b.field(x, 'raid')
    fb.op('JNull', reg=rd, offset=no)
    fb.op('JEq', a=b.field(rd, 'targetFaction'), b=fac, offset=yes)
    fb.op('JAlways', offset=no)


def _approaching(fb, b, cx, x, p, d, skip):
    """Fall through if mover x heads towards entity p (its path ends nearer to p than x is now, or no path is
    known); jump to `skip` if it is moving elsewhere (e.g. milling around its own base)."""
    pe = b.call('ent.MobileEntity.getCurrentPathEnd', x)
    ok = f'appr{len(fb.ops)}'
    fb.op('JNull', reg=pe, offset=ok)
    dx, dy = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Sub', dst=dx, a=b.field(pe, 'x'), b=b.field(p, 'posx'))
    fb.op('Sub', dst=dy, a=b.field(pe, 'y'), b=b.field(p, 'posy'))
    fb.op('Mul', dst=dx, a=dx, b=dx)
    fb.op('Mul', dst=dy, a=dy, b=dy)
    fb.op('Add', dst=dx, a=dx, b=dy)
    fb.op('Mul', dst=dy, a=d, b=d)
    fb.op('JSGte', a=dx, b=dy, offset=skip)
    fb.label(ok)


def build_threat(cx, pw, horizon_s=HORIZON, stats=False, reach=None, prey=False):
    """aimod_threat(fac, p, r) -> power of the armies hostile to fac within r of p, or heading there and able to
    arrive within horizon_s (a mover whose path ends farther from p than it is now doesn't count). Hostile = owned
    by a faction at war with fac, or a neutral raider (Army.raid: rebels, Fremen raids, marauders, ...) whose raid
    targets fac.
    stats=True: aimod_threat_stats(fac, p, r, skip, res, zone), same armies minus those owned by `skip`, each also
    pushed into res as unitSimulatedCombatStats(army, zone) (for vanilla power reports).
    reach=R: aimod_react(fac, p, r), also the armies within R that are free to answer: not fighting, idle or heading
    towards p; one occupying or contesting a structure counts OCC_W (it can break off: Fremen left Ars-ha to hunt the
    Atreides at their harvester).
    prey=True: aimod_hthreat(fac, p, r, pf, dn), the hunt measure around prey faction pf (null: plain threat): pf's
    armies as above; a third party at war with pf is skipped (it fights the prey too); one allied / at peace with pf
    counts within max(r, dn + ALLY_WIN), dn = our nearest army's distance (it arrives before we finish the kill)."""
    extra = [cx.t('ent.Faction'), cx.t('hl.types.ArrayObj'), cx.t('ent.Zone')] if stats else []
    if prey:
        extra = [cx.t('ent.Faction'), cx.t('f64')]
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Entity'), cx.t('f64')] + extra, cx.t('f64'))
    b = B(fb)
    tot = b.const('f64', 0)
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    state = _state(fb, b, cx)
    armies = b.field(state, 'armies')
    alen = b.field(armies, 'length')
    horizon, zero = b.const('f64', horizon_s), b.const('f64', 0)
    i = fb.reg(cx.t('i32'))
    d, eta, p = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    ref_t = cx.code.types[cx.fn('ent.Unit.getSpeed').type.value].definition.args[1].value
    noref = fb.reg(ref_t)
    fb.op('Null', dst=noref)
    x = _army_loop(fb, b, armies, alen, i, 'loop', 'done')
    xo = b.call('ent.Entity.get_owner', x)
    fb.op('JNotNull', reg=xo, offset='owned')
    _raider_vs(fb, b, x, 0, 'near', 'loop')
    fb.label('owned')
    fb.op('JEq', a=xo, b=0, offset='loop')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, 0, xo), offset='loop')
    if stats:
        fb.op('JEq', a=xo, b=3, offset='loop')
    if prey:
        fb.op('JNull', reg=3, offset='near')
        fb.op('JEq', a=xo, b=3, offset='near')  # the prey's own armies
        fb.op('JTrue', cond=b.call('logic.state.State.areAtWar', state, 3, xo), offset='loop')  # the prey's rival
        win = fb.reg(cx.t('f64'))
        fb.op('Add', dst=win, a=4, b=b.const('f64', ALLY_WIN))
        fb.op('JSGte', a=win, b=2, offset='winok')
        fb.op('Mov', dst=win, src=2)
        fb.label('winok')
        fb.op('JSLte', a=b.call('ent.Entity.getDistTo', x, 1), b=win, offset='count')
        fb.op('JAlways', offset='loop')
    fb.label('near')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', x, 1))
    fb.op('JSLte', a=d, b=2, offset='count')
    if reach is not None:
        fb.op('JSGt', a=d, b=b.const('f64', reach), offset='mv')
        fb.op('JTrue', cond=b.call('ent.Entity.isFighting', x), offset='mv')
        fb.op('JNotNull', reg=b.field(x, 'occupiedStructure'), offset='busy')
        fb.op('JNotNull', reg=b.field(x, 'contestingStructure'), offset='busy')
        fb.op('JFalse', cond=b.call('ent.Unit.isMoving', x), offset='count')
        _approaching(fb, b, cx, x, 1, d, 'loop')
        fb.op('JAlways', offset='count')
        fb.label('mv')
    fb.op('JFalse', cond=b.call('ent.Unit.isMoving', x), offset='loop')
    spd = b.call('ent.Unit.getSpeed', x, noref)
    fb.op('JSLte', a=spd, b=zero, offset='loop')
    fb.op('Sub', dst=eta, a=d, b=2)
    fb.op('SDiv', dst=eta, a=eta, b=spd)
    fb.op('JSGt', a=eta, b=horizon, offset='loop')
    _approaching(fb, b, cx, x, 1, d, 'loop')
    if reach is not None:  # busy capturing within reach: it can break off (counts OCC_W)
        fb.op('JAlways', offset='count')
        fb.label('busy')
        fb.op('Call1', dst=p, fun=pw, arg0=x)
        fb.op('Mul', dst=p, a=p, b=_ratio(fb, b, OCC_W))
        fb.op('Add', dst=tot, a=tot, b=p)
        fb.op('JAlways', offset='loop')
    fb.label('count')
    fb.op('Call1', dst=p, fun=pw, arg0=x)
    fb.op('Add', dst=tot, a=tot, b=p)
    if stats:
        fb.op('JNull', reg=4, offset='loop')
        fb.op('JNull', reg=5, offset='loop')
        st = b.call('$HCombatStats.unitSimulatedCombatStats', x, 5)
        b.call('hl.types.ArrayObj.push', 4, fb.dyn(st))
    fb.op('JAlways', offset='loop')
    fb.label('done')
    fb.label('end')
    fb.op('Ret', ret=tot)
    return fb.build()


def build_neutral(cx, pw):
    """aimod_neutral(fac, p, r) -> power of the neutral raiders within r of p that aimod_threat doesn't count
    (raiding someone else: they ignore us, but fight back when we hunt them)."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Entity'), cx.t('f64')], cx.t('f64'))
    b = B(fb)
    tot = b.const('f64', 0)
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    armies = b.field(_state(fb, b, cx), 'armies')
    alen = b.field(armies, 'length')
    i = fb.reg(cx.t('i32'))
    p = fb.reg(cx.t('f64'))
    x = _army_loop(fb, b, armies, alen, i, 'loop', 'end')
    fb.op('JNotNull', reg=b.call('ent.Entity.get_owner', x), offset='loop')
    fb.op('JNull', reg=b.field(x, 'raid'), offset='loop')
    _raider_vs(fb, b, x, 0, 'loop', 'other')
    fb.label('other')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', x, 1), b=2, offset='loop')
    fb.op('Call1', dst=p, fun=pw, arg0=x)
    fb.op('Add', dst=tot, a=tot, b=p)
    fb.op('JAlways', offset='loop')
    fb.label('end')
    fb.op('Ret', ret=tot)
    return fb.build()


def build_terrain(cx):
    """aimod_terrain(fac, zone) -> OWN_T on our zone, ENEMY_T on the zone of a faction at war with us, else 1.
    Multiplies a power ratio (ours / theirs) before comparing it with ENTER / ABORT / RETREAT."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Zone')], cx.t('f64'))
    b = B(fb)
    res = b.const('f64', 1)
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    o = b.field(1, 'owner')
    fb.op('JNull', reg=o, offset='end')
    fb.op('JNotEq', a=o, b=0, offset='other')
    fb.op('Mov', dst=res, src=_ratio(fb, b, OWN_T))
    fb.op('JAlways', offset='end')
    fb.label('other')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', _state(fb, b, cx), 0, o), offset='end')
    fb.op('Mov', dst=res, src=_ratio(fb, b, ENEMY_T))
    fb.label('end')
    fb.op('Ret', ret=res)
    return fb.build()


def build_own(cx, pw):
    """aimod_own(fac, p, r, exclude) -> own non-militia army power within r of p, excluding `exclude`."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Entity'), cx.t('f64'), cx.t('ent.Army')], cx.t('f64'))
    b = B(fb)
    tot = b.const('f64', 0)
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    arr, alen = _my_armies(fb, b, 0, 'end')
    i = fb.reg(cx.t('i32'))
    p = fb.reg(cx.t('f64'))
    x = _army_loop(fb, b, arr, alen, i, 'loop', 'end')
    fb.op('JEq', a=x, b=3, offset='loop')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', x, 1), b=2, offset='loop')
    fb.op('Call1', dst=p, fun=pw, arg0=x)
    fb.op('Add', dst=tot, a=tot, b=p)
    fb.op('JAlways', offset='loop')
    fb.label('end')
    fb.op('Ret', ret=tot)
    return fb.build()


def build_free(cx, pw, min_life=MIN_LIFE, min_supply=MIN_SUPPLY, resupply_ok=False, patrol_ok=True):
    """aimod_free(a, orders): may join a hunt (alive, controllable, combat army (not a harvester: Fremen harvesters
    are armies with power, moved by direct commands, not orders), life and supply >= 90%, and in no order except
    Patrol). Busy = in any non-Patrol order of `orders` (Army.aiOrder is not set for hunt orders),
    so Resupply/Discovery/hunts/sieges keep their armies (healing comes first, policy §5).
    Variant (raid): other life / supply floors, and a Resupply order doesn't count as busy (a raid that refills
    supply beats walking home, when the supply budget allows it: aimod_raidsup).
    Variant patrol_ok=False (strand): a Patrol order counts as busy too (idle = in no order at all)."""
    fb = FB(cx, [cx.t('ent.Army'), cx.t('hl.types.ArrayObj')], cx.t('bool'))
    b = B(fb)
    no, yes = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('Bool', dst=no, value=False)
    fb.op('Bool', dst=yes, value=True)
    fb.op('JNull', reg=0, offset='no')
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', 0), offset='no')
    fb.op('JFalse', cond=b.call('ent.Unit.hasControl', 0), offset='no')
    fb.op('JTrue', cond=b.field(0, 'isMilitia'), offset='no')
    fb.op('JTrue', cond=b.call('ent.Entity.isTransported', 0), offset='no')
    fb.op('JNotNull', reg=b.field(0, 'harvestComponent'), offset='no')  # harvesters (Fremen: armies, pw > 0)
    # sent off the sand by worm-flee within WORM_HOLD s
    wf = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'wfled'), fb.dyn(0))
    fb.op('JNull', reg=wf, offset='wf_ok')
    wft = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=wft, src=wf)
    fb.op('Sub', dst=wft, a=b.field(_state(fb, b, cx), 'time'), b=wft)
    fb.op('JSLt', a=wft, b=b.const('f64', WORM_HOLD), offset='no')
    fb.label('wf_ok')
    fb.op('JSLt', a=b.call('ent.Entity.get_lifeRatio', 0), b=_ratio(fb, b, min_life), offset='no')
    ms = b.call('ent.Army.get_maxSupply', 0)
    zero = b.const('f64', 0)
    fb.op('JSLte', a=ms, b=zero, offset='sup_ok')
    sr = fb.reg(cx.t('f64'))
    fb.op('SDiv', dst=sr, a=b.call('ent.Army.get_supply', 0), b=ms)
    fb.op('JSLt', a=sr, b=_ratio(fb, b, min_supply), offset='no')
    fb.label('sup_ok')
    p = fb.reg(cx.t('f64'))
    fb.op('Call1', dst=p, fun=pw, arg0=0)
    fb.op('JSLte', a=p, b=zero, offset='no')
    idx = fb.reg(cx.t('i32'))
    patrol = b.const('i32', PATROL)
    resupply = b.const('i32', RESUPPLY) if resupply_ok else None
    o = b.field(0, 'aiOrder')
    fb.op('JNull', reg=o, offset='orders')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    if resupply_ok:
        fb.op('JEq', a=idx, b=resupply, offset='orders')
    if patrol_ok:
        fb.op('JNotEq', a=idx, b=patrol, offset='no')
    else:
        fb.op('JAlways', offset='no')
    fb.label('orders')
    fb.op('JNull', reg=1, offset='yes')
    n = b.field(1, 'length')
    i = b.const('i32', 0)
    me = fb.dyn(0)
    b.loop_head('ord')
    fb.op('JSGte', a=i, b=n, offset='yes')
    oo = b.cast(b.call('hl.types.ArrayObj.getDyn', 1, i), 'logic.ai.AIOrder')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=oo, offset='ord')
    fb.op('EnumIndex', dst=idx, value=b.field(oo, 'type'))
    if patrol_ok:
        fb.op('JEq', a=idx, b=patrol, offset='ord')
    if resupply_ok:
        fb.op('JEq', a=idx, b=resupply, offset='ord')
    units = b.field(oo, 'units')
    fb.op('JNull', reg=units, offset='ord')
    fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', units, me), offset='no')
    fb.op('JAlways', offset='ord')
    fb.label('no')
    fb.op('Ret', ret=no)
    fb.label('yes')
    fb.op('Ret', ret=yes)
    return fb.build()


def build_land(cx):
    """aimod_land(fac, e) -> distance from e to fac's nearest structure standing on a zone fac owns (2^30 if none).
    'Our land': excludes structures inside other factions' zones (Smugglers' UWHeadquarters sit in enemy villages)."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Entity')], cx.t('f64'))
    b = B(fb)
    best = b.const('f64', 1 << 30)
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    structs = b.cast(fb.get(0, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=structs, offset='end')
    n = b.field(structs, 'length')
    i = b.const('i32', 0)
    b.loop_head('loop')
    fb.op('JSGte', a=i, b=n, offset='end')
    s = b.cast(b.call('hl.types.ArrayObj.getDyn', structs, i), 'ent.Entity')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=s, offset='loop')
    z = b.call('ent.Entity.get_zone', s)
    fb.op('JNull', reg=z, offset='loop')
    fb.op('JNotEq', a=b.field(z, 'owner'), b=0, offset='loop')
    d = b.call('ent.Entity.getDistTo', 1, s)
    fb.op('JSGte', a=d, b=best, offset='loop')
    fb.op('Mov', dst=best, src=d)
    fb.op('JAlways', offset='loop')
    fb.label('end')
    fb.op('Ret', ret=best)
    return fb.build()


def build_home(cx, pw, land, own=False):
    """aimod_home(fac, d) -> power of the hostile armies (at war with fac, or raiders targeting it) within d of our
    land (aimod_land) that are free to strike it: not fighting, not occupying or contesting a structure. With armies
    of ours d away, these reach our land first (same speed).
    own=True: aimod_homeown(fac, d, exclude) -> power of our combat armies (no harvesters) within d of our land that
    are not in `exclude` (an order's units): who is home before them."""
    extra = [cx.t('hl.types.ArrayObj')] if own else []
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('f64')] + extra, cx.t('f64'))
    b = B(fb)
    tot = b.const('f64', 0)
    fb.op('JNull', reg=0, offset='end')
    i = fb.reg(cx.t('i32'))
    p, d = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    if own:
        arr, alen = _my_armies(fb, b, 0, 'end')
    else:
        state = _state(fb, b, cx)
        arr = b.field(state, 'armies')
        alen = b.field(arr, 'length')
    x = _army_loop(fb, b, arr, alen, i, 'loop', 'end')
    if own:
        fb.op('JNotNull', reg=b.field(x, 'harvestComponent'), offset='loop')
        fb.op('JNull', reg=2, offset='mine')
        fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', 2, fb.dyn(x)), offset='loop')
        fb.label('mine')
    else:
        xo = b.call('ent.Entity.get_owner', x)
        fb.op('JNotNull', reg=xo, offset='owned')
        _raider_vs(fb, b, x, 0, 'hostile', 'loop')
        fb.label('owned')
        fb.op('JEq', a=xo, b=0, offset='loop')
        fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, 0, xo), offset='loop')
        fb.label('hostile')
        fb.op('JTrue', cond=b.call('ent.Entity.isFighting', x), offset='loop')
        fb.op('JNotNull', reg=b.field(x, 'occupiedStructure'), offset='loop')
        fb.op('JNotNull', reg=b.field(x, 'contestingStructure'), offset='loop')
    xe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=xe, src=x)
    fb.op('Call2', dst=d, fun=land, arg0=0, arg1=xe)
    fb.op('JSGt', a=d, b=1, offset='loop')
    fb.op('Call1', dst=p, fun=pw, arg0=x)
    fb.op('Add', dst=tot, a=tot, b=p)
    fb.op('JAlways', offset='loop')
    fb.label('end')
    fb.op('Ret', ret=tot)
    return fb.build()


def build_supok(cx):
    """aimod_supok(a, d, k) -> supply >= k * (SUP_U * d + SUP_RES * maxSupply): enough to walk d back to our land
    (true for armies without supply)."""
    fb = FB(cx, [cx.t('ent.Army'), cx.t('f64'), cx.t('f64')], cx.t('bool'))
    b = B(fb)
    res = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=res, value=True)
    fb.op('JNull', reg=0, offset='end')
    ms = b.call('ent.Army.get_maxSupply', 0)
    fb.op('JSLte', a=ms, b=b.const('f64', 0), offset='end')
    need, r = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mul', dst=need, a=1, b=_ratio(fb, b, SUP_U))
    fb.op('Mul', dst=r, a=ms, b=_ratio(fb, b, SUP_RES))
    fb.op('Add', dst=need, a=need, b=r)
    fb.op('Mul', dst=need, a=need, b=2)
    fb.op('JSGte', a=b.call('ent.Army.get_supply', 0), b=need, offset='end')
    fb.op('Bool', dst=res, value=False)
    fb.label('end')
    fb.op('Ret', ret=res)
    return fb.build()


def build_raidsup(cx):
    """aimod_raidsup(a, d_to, d_home) -> a can raid a village d_to away that lies d_home from our land: it arrives
    with >= RAID_ARRIVE x max supply (supply - SUP_U x d_to; fighting the militia drains too), occupying doesn't
    drain (Army.isInHostileZone is false in occupation range), a finished pillage refills OCC_REFILL x max
    (data Army_Supply_Resupply_OccupationRatio), and then it still has the budget home (SUP_U x d_home + SUP_RES x
    max). True for armies without supply."""
    fb = FB(cx, [cx.t('ent.Army'), cx.t('f64'), cx.t('f64')], cx.t('bool'))
    b = B(fb)
    res = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=res, value=True)
    fb.op('JNull', reg=0, offset='end')
    ms = b.call('ent.Army.get_maxSupply', 0)
    fb.op('JSLte', a=ms, b=b.const('f64', 0), offset='end')
    fb.op('Bool', dst=res, value=False)
    su = _ratio(fb, b, SUP_U)
    arrive, q = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mul', dst=q, a=1, b=su)
    fb.op('Sub', dst=arrive, a=b.call('ent.Army.get_supply', 0), b=q)
    fb.op('Mul', dst=q, a=ms, b=_ratio(fb, b, RAID_ARRIVE))
    fb.op('JSLt', a=arrive, b=q, offset='end')
    fb.op('Mul', dst=q, a=ms, b=_ratio(fb, b, OCC_REFILL))
    fb.op('Add', dst=arrive, a=arrive, b=q)
    fb.op('JSLte', a=arrive, b=ms, offset='capped')
    fb.op('Mov', dst=arrive, src=ms)
    fb.label('capped')
    fb.op('Mul', dst=q, a=2, b=su)
    need = fb.reg(cx.t('f64'))
    fb.op('Mul', dst=need, a=ms, b=_ratio(fb, b, SUP_RES))
    fb.op('Add', dst=need, a=need, b=q)
    fb.op('JSLt', a=arrive, b=need, offset='end')
    fb.op('Bool', dst=res, value=True)
    fb.label('end')
    fb.op('Ret', ret=res)
    return fb.build()


def build_militia(cx):
    """aimod_militia(s) -> power of s's own defenders that have health (village militia; turrets are health-less
    and counted by aimod_cover instead), on the aimod_pw scale."""
    fb = FB(cx, [cx.t('ent.Structure')], cx.t('f64'))
    b = B(fb)
    tot = b.const('f64', 0)
    zero = b.const('f64', 0)
    fb.op('JNull', reg=0, offset='end')
    arr = b.call('$HCombatStats.structureCombatStats', 0)
    fb.op('JNull', reg=arr, offset='end')
    n = b.field(arr, 'length')
    i = b.const('i32', 0)
    p = fb.reg(cx.t('f64'))
    b.loop_head('l')
    fb.op('JSGte', a=i, b=n, offset='end')
    st = b.call('hl.types.ArrayObj.getDyn', arr, i)
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=st, offset='l')
    fb.op('Mov', dst=p, src=b.call('$HPowerScore.singlePowerScore', st))
    fb.op('JSLte', a=p, b=zero, offset='l')
    fb.op('Add', dst=tot, a=tot, b=p)
    fb.op('JAlways', offset='l')
    fb.label('end')
    fb.op('Ret', ret=tot)
    return fb.build()


def build_short(cx, land, supok):
    """aimod_short(fac, a) -> a is losing supply and has less than the budget back to fac's land (supok, k = 1)."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Army')], cx.t('bool'))
    b = B(fb)
    res = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=res, value=False)
    fb.op('JNull', reg=1, offset='end')
    fb.op('JFalse', cond=b.call('ent.Army.isLosingSupply', 1), offset='end')
    e = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=e, src=1)
    d, ok = fb.reg(cx.t('f64')), fb.reg(cx.t('bool'))
    fb.op('Call2', dst=d, fun=land, arg0=0, arg1=e)
    fb.op('Call3', dst=ok, fun=supok, arg0=1, arg1=d, arg2=b.const('f64', 1))
    fb.op('JTrue', cond=ok, offset='end')
    fb.op('Bool', dst=res, value=True)
    fb.label('end')
    fb.op('Ret', ret=res)
    return fb.build()


def build_cover(cx):
    """aimod_cover(fac, e, exclude, own, res) -> turret cover at e: for every structure within COVER_R of e (not
    `exclude`) owned by fac (own) or by a faction at war with fac (not own), each of its combat stats without health
    (turrets = buildings with power, main base guns; militia have health and are skipped) adds offensivePotential x
    TURRET_H to the result (an active main base's guns x MB_GUN_W), and is pushed into `res` when res is not null
    (for vanilla power reports; a main base's MB_GUN_W times). Silent: a
    besieged village (its turrets stop while it is annexed / pillaged) and dead main bases."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Entity'), cx.t('ent.Entity'), cx.t('bool'),
                 cx.t('hl.types.ArrayObj')], cx.t('f64'))
    b = B(fb)
    tot = b.const('f64', 0)
    zero = b.const('f64', 0)
    th = b.const('f64', TURRET_H)
    cover = b.const('f64', COVER_R)
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    state = _state(fb, b, cx)
    facs = b.cast(fb.get(state, 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=facs, offset='end')
    n = b.field(facs, 'length')
    i, j, k = (fb.reg(cx.t('i32')) for _ in range(3))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    sps, op_ = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    se = fb.reg(cx.t('ent.Entity'))
    b.loop_head('fl')
    fb.op('JSGte', a=i, b=n, offset='end')
    f = b.cast(b.call('hl.types.ArrayObj.getDyn', facs, i), 'ent.Faction')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=f, offset='fl')
    fb.op('JFalse', cond=3, offset='enemy')
    fb.op('JNotEq', a=f, b=0, offset='fl')
    fb.op('JAlways', offset='fok')
    fb.label('enemy')
    fb.op('JEq', a=f, b=0, offset='fl')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, 0, f), offset='fl')
    fb.label('fok')
    sts = b.cast(fb.get(f, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=sts, offset='fl')
    sn = b.field(sts, 'length')
    fb.op('Mov', dst=j, src=b.const('i32', 0))
    b.loop_head('sl')
    fb.op('JSGte', a=j, b=sn, offset='fl')
    s = b.cast(b.call('hl.types.ArrayObj.getDyn', sts, j), 'ent.Structure')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=s, offset='sl')
    fb.op('Mov', dst=se, src=s)
    fb.op('JEq', a=se, b=2, offset='sl')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', 1, se), b=cover, offset='sl')
    ismb = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=ismb, value=False)
    fb.op('JFalse', cond=b.call('ent.Structure.get_isMainBase', s), offset='village')
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', s), offset='sl')
    fb.op('Bool', dst=ismb, value=True)
    fb.op('JAlways', offset='stats')
    fb.label('village')
    sg = b.field(s, 'siege')
    fb.op('JNull', reg=sg, offset='stats')
    fb.op('JNotNull', reg=b.field(sg, 'besiegingFaction'), offset='sl')  # being annexed / pillaged: silent
    fb.label('stats')
    arr = b.call('$HCombatStats.structureCombatStats', s)
    fb.op('JNull', reg=arr, offset='sl')
    an = b.field(arr, 'length')
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head('kl')
    fb.op('JSGte', a=k, b=an, offset='sl')
    st = b.call('hl.types.ArrayObj.getDyn', arr, k)
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=st, offset='kl')
    fb.op('Mov', dst=sps, src=b.call('$HPowerScore.singlePowerScore', st))
    fb.op('JSGt', a=sps, b=zero, offset='kl')  # has health: militia, not a turret
    fb.op('Mov', dst=op_, src=b.call('$HPowerScore.offensivePotential', st, zero))
    fb.op('Mul', dst=op_, a=op_, b=th)
    fb.op('JFalse', cond=ismb, offset='nmb1')
    fb.op('Mul', dst=op_, a=op_, b=b.const('f64', MB_GUN_W))  # main-base guns hit far above their power score
    fb.label('nmb1')
    fb.op('Add', dst=tot, a=tot, b=op_)
    fb.op('JNull', reg=4, offset='kl')
    b.call('hl.types.ArrayObj.push', 4, st)
    fb.op('JFalse', cond=ismb, offset='kl')
    for _ in range(MB_GUN_W - 1):  # ... in vanilla's report too: the same stats again
        b.call('hl.types.ArrayObj.push', 4, st)
    fb.op('JAlways', offset='kl')
    fb.label('end')
    fb.op('Ret', ret=tot)
    return fb.build()


def build_silence(cx):
    """aimod_silence(res, s, c): remove the health-less stats (turrets) among res[0..c) = s's own structure stats,
    unless s is a main base: a village's turrets stop while it is annexed / pillaged."""
    fb = FB(cx, [cx.t('hl.types.ArrayObj'), cx.t('ent.Structure'), cx.t('i32')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    zero = b.const('f64', 0)
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', 1), offset='end')
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=2)
    n = b.field(0, 'length')
    fb.op('JSLte', a=i, b=n, offset='ok')
    fb.op('Mov', dst=i, src=n)
    fb.label('ok')
    one = b.const('i32', 1)
    zi = b.const('i32', 0)
    b.loop_head('l')
    fb.op('JSLte', a=i, b=zi, offset='end')
    fb.op('Sub', dst=i, a=i, b=one)
    st = b.call('hl.types.ArrayObj.getDyn', 0, i)
    fb.op('JNull', reg=st, offset='l')
    fb.op('JSGt', a=b.call('$HPowerScore.singlePowerScore', st), b=zero, offset='l')
    b.call('hl.types.ArrayObj.splice', 0, i, one)
    fb.op('JAlways', offset='l')
    fb.label('end')
    fb.op('Ret', ret=void)
    return fb.build()


def build_defend(cx, sieged):
    """aimod_defend(fac) -> one of fac's villages or main bases besieged by an at-war faction, else null.
    Non-null = defensive posture: no new offensives (vanilla siege actions, chases) until it is resolved."""
    st_t = cx.t('ent.Structure')
    fb = FB(cx, [cx.t('ent.Faction')], st_t)
    b = B(fb)
    res = fb.reg(st_t)
    fb.op('Null', dst=res)
    fb.op('JNull', reg=0, offset='end')
    ok = fb.reg(cx.t('bool'))
    i = fb.reg(cx.t('i32'))
    villages = b.field(_state(fb, b, cx), 'villages')
    bases = b.field(0, 'mainBases')
    for name, arr in (('v', villages), ('b', bases)):
        done = f'{name}done'
        fb.op('JNull', reg=arr, offset=done)
        n = b.field(arr, 'length')
        fb.op('Mov', dst=i, src=b.const('i32', 0))
        b.loop_head(name)
        fb.op('JSGte', a=i, b=n, offset=done)
        s = b.cast(b.call('hl.types.ArrayObj.getDyn', arr, i), 'ent.Structure')
        fb.op('Incr', dst=i)
        fb.op('JNull', reg=s, offset=name)
        fb.op('JNotEq', a=b.call('ent.Entity.get_owner', s), b=0, offset=name)
        fb.op('Call2', dst=ok, fun=sieged, arg0=0, arg1=s)
        fb.op('JFalse', cond=ok, offset=name)
        fb.op('Mov', dst=res, src=s)
        fb.op('JAlways', offset='end')
        fb.label(done)
    fb.label('end')
    fb.op('Ret', ret=res)
    return fb.build()


def build_sieged(cx):
    """aimod_sieged(fac, s) -> s is besieged or occupied by a faction at war with fac, and s is neutral, ours, or
    belongs to a faction not at war with us (a capture we want to stop). Reads the structure's own siege state
    (as vanilla micro does), so it sees human and AI sieges alike (Army.aiOrder is often null on besiegers)."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Structure')], cx.t('bool'))
    b = B(fb)
    res = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=res, value=False)
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    sg = b.field(1, 'siege')
    fb.op('JNull', reg=sg, offset='end')
    bf = fb.reg(cx.t('ent.Faction'))
    fb.op('Mov', dst=bf, src=b.field(sg, 'besiegingFaction'))
    fb.op('JNotNull', reg=bf, offset='have')
    fb.op('Mov', dst=bf, src=b.call('ent.comp.SiegeComponent.getOccupierFaction', sg))
    fb.op('JNull', reg=bf, offset='end')
    fb.label('have')
    fb.op('JEq', a=bf, b=0, offset='end')
    state = _state(fb, b, cx)
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, 0, bf), offset='end')
    o = b.call('ent.Entity.get_owner', 1)
    fb.op('JNull', reg=o, offset='yes')
    fb.op('JEq', a=o, b=0, offset='yes')
    fb.op('JTrue', cond=b.call('logic.state.State.areAtWar', state, 0, o), offset='end')
    fb.label('yes')
    fb.op('Bool', dst=res, value=True)
    fb.label('end')
    fb.op('Ret', ret=res)
    return fb.build()
