"""World model queries every rule reads (AI-POLICY §3): power, threat (at-war armies + neutral raiders targeting
us), neutral raiders, terrain, own power, free armies, our land, supply budget, turret cover, siege state,
defensive posture. Each builder appends one function and returns its findex."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.intel import _ghost, _seen_map, _known_rec, _rec_get


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


def _approaching(fb, b, cx, x, p, d, skip, r=None):
    """Fall through if mover x heads towards entity p (its path ends nearer to p than x is now, or no path is
    known); jump to `skip` if it is moving elsewhere (e.g. milling around its own base). With r (a register): its
    path must also end within r of p, i.e. it arrives: Atreides' Patrol / Resupply shuffles at Gun-dah ended
    ~90-100 from Smugglers' Annarekh, read as an attack within FLEE_R, and the rally pulled Smugglers' hunters home
    (22:02-22:28). Rally only: elsewhere a mover bound for a regroup point just outside r is still coming."""
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
    if r is not None:
        fb.op('Mul', dst=dy, a=r, b=r)
        fb.op('JSGt', a=dx, b=dy, offset=skip)
    fb.label(ok)


def build_threat(cx, pw, horizon_s=HORIZON, stats=False, reach=None, prey=False, discount=True, arrive=False):
    """aimod_threat(fac, p, r) -> power of the armies hostile to fac within r of p, or heading there and able to
    arrive within horizon_s (a mover whose path ends farther from p than it is now doesn't count; arrive=True: nor one
    whose path ends outside r, for the rally, see _approaching). Hostile = owned
    by a faction at war with fac, or a neutral raider (Army.raid: rebels, Fremen raids, marauders, ...) whose raid
    targets fac.
    stats=True: aimod_threat_stats(fac, p, r, skip, res, zone), same armies minus those owned by `skip`, each also
    pushed into res as unitSimulatedCombatStats(army, zone) (for vanilla power reports).
    reach=R: aimod_react(fac, p, r), also the armies within R that are free to answer: not fighting, idle or heading
    towards p; one occupying or contesting a structure counts OCC_W (it can break off: Fremen left Ars-ha to hunt the
    Atreides at their harvester).
    prey=True: aimod_hthreat(fac, p, r, pf, dn), the hunt measure around prey faction pf (null: plain threat): pf's
    armies as above; a third party at war with pf is skipped (it fights the prey too); one allied / at peace with pf
    counts within max(r, dn + ALLY_WIN), dn = our nearest army's distance (it arrives before we finish the kill).
    discount=False (heal / retreat / strand safety: where an army rests, it is still there when the capture ends or
    the stack walks in): no BUSY_W / OCC_W / OUT_W, every army at full power (Atreides retreated at 0 supply to
    Ars-sud 92 from 4 Fremen armies annexing Sindalus, counted at 25%, and lost 180k there)."""
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
    # fog of war (rules/intel.py): unseen armies count from fac's sightings only
    mp = _seen_map(fb, b, cx, 0)
    now = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=now, src=b.field(state, 'time'))
    qx, qy = b.field(1, 'posx'), b.field(1, 'posy')

    gr = 2
    if reach is not None:  # aimod_react: a remembered army within the answer radius counts too (busy: BUSY_W)
        gr = fb.reg(cx.t('f64'))
        fb.op('Mov', dst=gr, src=2)
        rch = b.const('f64', reach)
        fb.op('JSGte', a=gr, b=rch, offset='grok')
        fb.op('Mov', dst=gr, src=rch)
        fb.label('grok')

    def ghost(live):
        gp = _ghost(fb, b, cx, 0, mp, now, x, live, 'loop', qx, qy, gr, busy=discount)
        fb.op('Add', dst=tot, a=tot, b=gp)
        if stats:
            fb.op('JNull', reg=4, offset='loop')
            fb.op('JNull', reg=5, offset='loop')
            b.call('hl.types.ArrayObj.push', 4, fb.dyn(b.call('$HCombatStats.unitSimulatedCombatStats', x, 5)))
        fb.op('JAlways', offset='loop')

    x = _army_loop(fb, b, armies, alen, i, 'loop', 'done')
    xo = b.call('ent.Entity.get_owner', x)
    fb.op('JNotNull', reg=xo, offset='owned')
    _raider_vs(fb, b, x, 0, 'rvis', 'loop')
    fb.label('rvis')
    ghost('near')
    fb.label('owned')
    fb.op('JEq', a=xo, b=0, offset='loop')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, 0, xo), offset='loop')
    if stats:
        fb.op('JEq', a=xo, b=3, offset='loop')
    ghost('olive')
    fb.label('olive')
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
        # p belongs to the army's own faction: its Defense (prio 5) pulls it out of a capture (Annex prio 3) at once
        fb.op('JNull', reg=xo, offset='rnx')
        fb.op('JNull', reg=fb.get(1, 'siege'), offset='rnx')  # p a structure (a hunted army gets no Defense)
        fb.op('JEq', a=b.call('ent.Entity.get_owner', 1), b=xo, offset='rown')
        fb.label('rnx')
        fb.op('JNotNull', reg=b.field(x, 'occupiedStructure'), offset='busy')
        fb.op('JNotNull', reg=b.field(x, 'contestingStructure'), offset='busy')
        fb.label('rown')
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
    _approaching(fb, b, cx, x, 1, d, 'loop', r=2 if arrive else None)
    if reach is not None:  # busy capturing within reach: it can break off (counts OCC_W)
        fb.op('JAlways', offset='count')
        fb.label('busy')
        fb.op('Call1', dst=p, fun=pw, arg0=x)
        fb.op('Mul', dst=p, a=p, b=_ratio(fb, b, OCC_W))
        fb.op('Add', dst=tot, a=tot, b=p)
        fb.op('JAlways', offset='loop')
    fb.label('count')
    if not discount:
        fb.op('Call1', dst=p, fun=pw, arg0=x)
        fb.op('Add', dst=tot, a=tot, b=p)
        fb.op('JAlways', offset='loop')
    # busy capturing a structure away from p (> BUSY_R): counts BUSY_W, not pushed as stats; at its own capture
    # (a contest, a hunt on it) full (Atreides held every defender in `rally` at Qal-nit for 12 Fremen armies
    # occupying Halnah 133-157 away, and let neutral attackers hit Qal-nit)
    full = _uid('full')
    occ = b.field(x, 'occupiedStructure')
    fb.op('JNull', reg=occ, offset=full)
    oe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=oe, src=occ)
    fb.op('JEq', a=b.call('ent.Entity.get_owner', oe), b=b.call('ent.Entity.get_owner', x), offset=full)  # resting home
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', oe, 1), b=b.const('f64', BUSY_R), offset=full)
    # p is a structure of the army's own faction (we attack its village): its Defense outranks the capture, it
    # comes at full strength (Smugglers raided Aidval next to Fremen's Annex of Gur-Al'lulah, counted at OCC_W)
    xow = b.call('ent.Entity.get_owner', x)
    fb.op('JNull', reg=xow, offset=full + 'o')
    fb.op('JNull', reg=fb.get(1, 'siege'), offset=full + 'o')  # p a structure (a hunted army gets no Defense)
    fb.op('JEq', a=b.call('ent.Entity.get_owner', 1), b=xow, offset=full)
    fb.label(full + 'o')
    fb.op('Call1', dst=p, fun=pw, arg0=x)
    # defending (p on our land): BUSY_W; an offensive (p off our land: hunt / raid / press target): OCC_W, the
    # break-off weight, so a busy stack next door still deters attacks on it
    bw = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=bw, src=_ratio(fb, b, OCC_W))
    bz = b.call('ent.Entity.get_zone', 1)
    fb.op('JNull', reg=bz, offset=full + 'w')
    fb.op('JNotEq', a=b.field(bz, 'owner'), b=0, offset=full + 'w')
    fb.op('Mov', dst=bw, src=_ratio(fb, b, BUSY_W))
    fb.label(full + 'w')
    fb.op('Mul', dst=p, a=p, b=bw)
    fb.op('Add', dst=tot, a=tot, b=p)
    fb.op('JAlways', offset='loop')
    fb.label(full)
    fb.op('Call1', dst=p, fun=pw, arg0=x)
    # p on our land, the army off it and not moving: OUT_W (it has to walk in first; Atreides should defend inside
    # their land while Fremen stand liberating outside it)
    inl = _uid('inl')
    qz = b.call('ent.Entity.get_zone', 1)
    fb.op('JNull', reg=qz, offset=inl)
    fb.op('JNotEq', a=b.field(qz, 'owner'), b=0, offset=inl)
    xz = b.call('ent.Entity.get_zone', x)
    fb.op('JNull', reg=xz, offset=inl)
    fb.op('JEq', a=b.field(xz, 'owner'), b=0, offset=inl)
    fb.op('JTrue', cond=b.call('ent.Unit.isMoving', x), offset=inl)
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', x, 1), b=b.const('f64', OUT_R), offset=inl)  # at the border
    fb.op('Mul', dst=p, a=p, b=_ratio(fb, b, OUT_W))
    fb.label(inl)
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
    mp = _seen_map(fb, b, cx, 0)
    now = b.field(_state(fb, b, cx), 'time')
    qx, qy = b.field(1, 'posx'), b.field(1, 'posy')
    x = _army_loop(fb, b, armies, alen, i, 'loop', 'end')
    fb.op('JNotNull', reg=b.call('ent.Entity.get_owner', x), offset='loop')
    fb.op('JNull', reg=b.field(x, 'raid'), offset='loop')
    _raider_vs(fb, b, x, 0, 'loop', 'other')
    fb.label('other')
    gp = _ghost(fb, b, cx, 0, mp, now, x, 'nlive', 'loop', qx, qy, 2)  # fog: unseen raiders from memory
    fb.op('Add', dst=tot, a=tot, b=gp)
    fb.op('JAlways', offset='loop')
    fb.label('nlive')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', x, 1), b=2, offset='loop')
    fb.op('Call1', dst=p, fun=pw, arg0=x)
    fb.op('Add', dst=tot, a=tot, b=p)
    fb.op('JAlways', offset='loop')
    fb.label('end')
    fb.op('Ret', ret=tot)
    return fb.build()


def build_terrain(cx):
    """aimod_terrain(fac, zone) -> OWN_T on our zone, ENEMY_T on the zone of a faction at war with us, else 1;
    off our zone also x max(DECAY_FLOOR, 1 - rate x DECAY_DAYS) in a region that drains ground life (DECAY_ZONES by
    Zone.kind: Acid Lakes, The Desolation; on our zone we heal at our structures). Multiplies a power ratio (ours /
    theirs) before comparing it with ENTER / ABORT / RETREAT."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Zone')], cx.t('f64'))
    b = B(fb)
    res = b.const('f64', 1)
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    o = b.field(1, 'owner')
    fb.op('JNull', reg=o, offset='decay')
    fb.op('JNotEq', a=o, b=0, offset='other')
    fb.op('Mov', dst=res, src=_ratio(fb, b, OWN_T))
    fb.op('JAlways', offset='end')
    fb.label('other')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', _state(fb, b, cx), 0, o), offset='decay')
    fb.op('Mov', dst=res, src=_ratio(fb, b, ENEMY_T))
    fb.label('decay')
    kd = b.field(1, 'kind')
    fb.op('JNull', reg=kd, offset='end')
    for i, (name, rate) in enumerate(sorted(DECAY_ZONES.items())):
        fb.op('JNotEq', a=b.call('String.__compare', kd, fb.dyn(fb.string(name))), b=b.const('i32', 0),
              offset=f'dz{i}')
        fb.op('Mul', dst=res, a=res, b=_ratio(fb, b, max(DECAY_FLOOR, 1 - rate * DECAY_DAYS)))
        fb.op('JAlways', offset='end')
        fb.label(f'dz{i}')
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
    Patrol). Busy = in any non-Patrol order of `orders` (scanned: Unit.aiOrder is never maintained),
    so Resupply/Discovery/hunts/sieges keep their armies (healing comes first, policy §5).
    Variant (raid): other life / supply floors, and a Resupply order doesn't count as busy (a raid that refills
    supply beats walking home, when the supply budget allows it: aimod_raidsup).
    Variant patrol_ok=False (strand): a Patrol order counts as busy too (idle = in no order at all).
    Hunts pass min_supply 0: a share of max supply says nothing about the walk (a max-supply rise left Atreides' 6
    armies at Sandkus at 82/125 while Harkonnen took Sandsud); every hunt army passes the absolute trip budget
    (aimod_supok) instead."""
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
    # busy = in an order of `orders` (never Unit.aiOrder: written only on controller start / save load, so null all
    # match and stale after a load, where it kept every army of a saved order busy for good); null orders = the
    # caller's own order units (hunt objective check): no order test
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
    of ours d away, these reach our land first (same speed). A total below HOME_MIN_H is 0. A home guard (where it will stand: position, or a mover's
    path end, on its own faction's zone and > OUT_R from our land) counts OUT_W.
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
        # home-guard test of movers (below): the world for the path end's zone, our structures for its distance
        world = fb.reg(cx.t('world.World'))
        fb.op('Null', dst=world)
        gs = fb.reg(cx.t('$Game'))
        fb.op('GetGlobal', dst=gs, **{'global': cx.global_of('$Game')})
        fb.op('JNull', reg=gs, offset='nowd')
        gi = b.field(gs, 'inst')
        fb.op('JNull', reg=gi, offset='nowd')
        fb.op('Mov', dst=world, src=b.field(gi, 'world'))
        fb.label('nowd')
        ours = b.cast(fb.get(0, 'structures', 'array'), 'hl.types.ArrayObj')
        on, j = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
        fb.op('Mov', dst=on, src=b.const('i32', 0))
        fb.op('JNull', reg=ours, offset='noours')
        fb.op('Mov', dst=on, src=b.field(ours, 'length'))
        fb.label('noours')
        qx, qy = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
        out2 = b.const('f64', OUT_R * OUT_R)
        mp = _seen_map(fb, b, cx, 0)
        now = b.field(state, 'time')
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
        # fog: an unseen army by its sighting (land distance then, minus its possible walk since); last seen busy: out
        gd = fb.reg(cx.t('f64'))
        gp = _ghost(fb, b, cx, 0, mp, now, x, 'hlive', 'loop', dist=gd, busy='skip')
        fb.op('JSGt', a=gd, b=1, offset='loop')
        fb.op('Add', dst=tot, a=tot, b=gp)
        fb.op('JAlways', offset='loop')
        fb.label('hlive')
        fb.op('JTrue', cond=b.call('ent.Entity.isFighting', x), offset='loop')
        fb.op('JNotNull', reg=b.field(x, 'occupiedStructure'), offset='loop')
        fb.op('JNotNull', reg=b.field(x, 'contestingStructure'), offset='loop')
    xe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=xe, src=x)
    fb.op('Call2', dst=d, fun=land, arg0=0, arg1=xe)
    fb.op('JSGt', a=d, b=1, offset='loop')
    fb.op('Call1', dst=p, fun=pw, arg0=x)
    if not own:
        # a home guard counts OUT_W, as in aimod_threat for a point on our land: it has to walk in first. At full
        # weight two neighbours' guards held each other: Smugglers and Atreides each read need > their whole army from
        # the other's stack at Gun-dah / Annarekh (`hold` 67-69%). Judged where the army will stand: a stander at its
        # position, a mover at its path end (as the rally's standoff test). Guard = that point on its own faction's
        # zone and > OUT_R from every structure on our land. A vanilla Patrol inside Atreides land (3 of 8 armies
        # moving) read full and cancelled Fremen's Yelat pillage at 0% (`home` H 237k vs M 126k); they never came.
        # A mover heading for our border (path end within OUT_R) or off its land, or with no path end, stays full.
        hg, mv, half = _uid('hg'), _uid('hgm'), _uid('hgh')
        fb.op('JNull', reg=xo, offset=hg)  # a raider (no owner) is no home guard
        fb.op('JTrue', cond=b.call('ent.Unit.isMoving', x), offset=mv)
        xz = b.call('ent.Entity.get_zone', x)
        fb.op('JNull', reg=xz, offset=hg)
        fb.op('JNotEq', a=b.field(xz, 'owner'), b=xo, offset=hg)
        fb.op('JSLte', a=d, b=b.const('f64', OUT_R), offset=hg)  # right at our structures: full, as in aimod_threat
        fb.op('JAlways', offset=half)
        fb.label(mv)
        fb.op('JNull', reg=world, offset=hg)
        pe = b.call('ent.MobileEntity.getCurrentPathEnd', x)
        fb.op('JNull', reg=pe, offset=hg)
        ex, ey = b.field(pe, 'x'), b.field(pe, 'y')
        ez = b.call('world.World.getZoneAt', world, ex, ey)
        fb.op('JNull', reg=ez, offset=hg)
        fb.op('JNotEq', a=b.field(ez, 'owner'), b=xo, offset=hg)
        # the path end within OUT_R of a structure on our land: walking up to our border, full
        fb.op('JNull', reg=ours, offset=half)
        fb.op('Mov', dst=j, src=b.const('i32', 0))
        ol = _uid('hgo')
        b.loop_head(ol)
        fb.op('JSGte', a=j, b=on, offset=half)
        s = b.cast(b.call('hl.types.ArrayObj.getDyn', ours, j), 'ent.Entity')
        fb.op('Incr', dst=j)
        fb.op('JNull', reg=s, offset=ol)
        sz = b.call('ent.Entity.get_zone', s)
        fb.op('JNull', reg=sz, offset=ol)
        fb.op('JNotEq', a=b.field(sz, 'owner'), b=0, offset=ol)  # our land only (not UWHeadquarters in others' zones)
        fb.op('Sub', dst=qx, a=ex, b=b.field(s, 'posx'))
        fb.op('Sub', dst=qy, a=ey, b=b.field(s, 'posy'))
        fb.op('Mul', dst=qx, a=qx, b=qx)
        fb.op('Mul', dst=qy, a=qy, b=qy)
        fb.op('Add', dst=qx, a=qx, b=qy)
        fb.op('JSLte', a=qx, b=out2, offset=hg)
        fb.op('JAlways', offset=ol)
        fb.label(half)
        fb.op('Mul', dst=p, a=p, b=_ratio(fb, b, OUT_W))
        fb.label(hg)
    fb.op('Add', dst=tot, a=tot, b=p)
    fb.op('JAlways', offset='loop')
    fb.label('end')
    if not own:
        # below HOME_MIN_H no strike: a 20k raider band near Grimwan with no army of ours home (m 0) aborted Fremen's
        # pillage at 10% (`home` h20k m0k, 17:21), Smugglers' Fondah / Grimwan likewise (18:24, 23:06)
        fb.op('JSGte', a=tot, b=b.const('f64', HOME_MIN_H), offset='ret')
        fb.op('Mov', dst=tot, src=b.const('f64', 0))
        fb.label('ret')
    fb.op('Ret', ret=tot)
    return fb.build()


def build_supok(cx):
    """aimod_supok(a, d, k) -> supply >= k * (SUP_U * d + SUP_RESERVE): enough to walk d back to our land
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
    fb.op('Mov', dst=r, src=_ratio(fb, b, SUP_RESERVE))
    fb.op('Add', dst=need, a=need, b=r)
    fb.op('Mul', dst=need, a=need, b=2)
    fb.op('JSGte', a=b.call('ent.Army.get_supply', 0), b=need, offset='end')
    fb.op('Bool', dst=res, value=False)
    fb.label('end')
    fb.op('Ret', ret=res)
    return fb.build()


def build_raidsup(cx):
    """aimod_raidsup(a, d_to, d_home) -> a can raid a village d_to away that lies d_home from our land (a free Supply
    Drop, rules/sdrop.py: non-mech armies need only SUP_RESERVE on arrival and get SD_REFILL more): it arrives
    with >= RAID_ARRIVE supply (supply - SUP_U x d_to; fighting the militia drains too), occupying doesn't
    drain (Army.isInHostileZone is false in occupation range), a finished pillage refills OCC_REFILL x max
    (data Army_Supply_Resupply_OccupationRatio), and then it still has the budget home (SUP_U x d_home +
    SUP_RESERVE). True for armies without supply."""
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
    fb.op('Mov', dst=q, src=_ratio(fb, b, RAID_ARRIVE))
    # a free Supply Drop (rules/sdrop.py map `sdfree`, seen within SD_FRESH s) covers the militia fight of a non-mech
    # army: it only needs the reserve on arrival; sdrop then locks the drop to this raid
    sdok = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=sdok, value=False)
    fb.op('JTrue', cond=b.call('ent.Unit.isMechanical', 0), offset='sdno')
    ae = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ae, src=0)
    own = b.call('ent.Entity.get_owner', ae)
    fb.op('JNull', reg=own, offset='sdno')
    seen = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'sdfree'), fb.dyn(own))
    fb.op('JNull', reg=seen, offset='sdno')
    ts = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=ts, src=seen)
    fb.op('Sub', dst=ts, a=b.field(_state(fb, b, cx), 'time'), b=ts)
    fb.op('JSGt', a=ts, b=b.const('f64', SD_FRESH), offset='sdno')
    fb.op('Mov', dst=q, src=_ratio(fb, b, SUP_RESERVE))
    fb.op('Bool', dst=sdok, value=True)
    fb.label('sdno')
    fb.op('JSLt', a=arrive, b=q, offset='end')
    fb.op('Mul', dst=q, a=ms, b=_ratio(fb, b, OCC_REFILL))
    fb.op('Add', dst=arrive, a=arrive, b=q)
    fb.op('JFalse', cond=sdok, offset='sdnr')
    fb.op('Add', dst=arrive, a=arrive, b=b.const('f64', SD_REFILL))  # the drop refills during the pillage
    fb.label('sdnr')
    fb.op('JSLte', a=arrive, b=ms, offset='capped')
    fb.op('Mov', dst=arrive, src=ms)
    fb.label('capped')
    fb.op('Mul', dst=q, a=2, b=su)
    need = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=need, src=_ratio(fb, b, SUP_RESERVE))
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


def _build_cover1(cx):
    """aimod_cover1(e, s, res) -> turret cover of structure s at entity e (aimod_cover's per-structure body), -1 when
    reading s threw (own trap: one bad structure no longer kills the caller's whole run; hunt / strat died here every
    10-30 s for Smugglers, Harkonnen and Fremen, `rfail` at hunt.py:133 / strat.py:127 / strat.py:206)."""
    fb = FB(cx, [cx.t('ent.Entity'), cx.t('ent.Structure'), cx.t('hl.types.ArrayObj')], cx.t('f64'))
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=res, src=b.const('f64', -1))  # stays -1 if the trap fires
    n0 = fb.reg(cx.t('i32'))  # report length before this structure (rolled back to it on a throw)
    fb.op('Mov', dst=n0, src=b.const('i32', 0))
    fb.op('JNull', reg=2, offset='n0d')
    fb.op('Mov', dst=n0, src=b.field(2, 'length'))
    fb.label('n0d')
    guard = fb.try_()
    tot = b.const('f64', 0)
    zero = b.const('f64', 0)
    th = b.const('f64', TURRET_H)
    cover = b.const('f64', COVER_R)
    op_ = fb.reg(cx.t('f64'))
    k = fb.reg(cx.t('i32'))
    s = 1
    sde = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=sde, src=s)
    sd = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=sd, src=b.call('ent.Entity.getDistTo', 0, sde))
    # every turret building (main base districts too) from where it stands: past this nothing reaches e
    fb.op('JSGt', a=sd, b=b.const('f64', COVER_R + TURRET_SPREAD), offset='done')
    fb.op('JFalse', cond=b.call('ent.Structure.get_isMainBase', s), offset='village')
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', s), offset='done')
    # main base guns: from its centre, COVER_R (Sadnin, 113 from Arrakeen, lost 6 of 10 armies to them)
    fb.op('JSGt', a=sd, b=cover, offset='stats')
    mst = b.call('$HCombatStats.mainBaseCombatStats', s)
    fb.op('JNull', reg=mst, offset='stats')
    fb.op('Mov', dst=op_, src=b.call('$HPowerScore.offensivePotential', fb.dyn(mst), zero))
    fb.op('Mul', dst=op_, a=op_, b=th)
    fb.op('Mul', dst=op_, a=op_, b=b.const('f64', MB_GUN_W))  # main-base guns hit far above their power score
    fb.op('Add', dst=tot, a=tot, b=op_)
    fb.op('JNull', reg=2, offset='stats')
    for _ in range(MB_GUN_W):  # ... in vanilla's report too: the same stats again
        b.call('hl.types.ArrayObj.push', 2, fb.dyn(mst))
    fb.op('JAlways', offset='stats')  # a main base is never silenced by a siege
    fb.label('village')
    sg = b.field(s, 'siege')
    fb.op('JNull', reg=sg, offset='stats')
    fb.op('JNotNull', reg=b.field(sg, 'besiegingFaction'), offset='done')  # being annexed / pillaged: silent
    # turrets: each powered, built building from where it stands, by its own attack range (+ TURRET_SPREAD fade); a
    # powered building without an attack (range 0) or still in construction never covers
    fb.label('stats')
    bp = b.field(s, 'buildings')
    fb.op('JNull', reg=bp, offset='done')
    arr = b.cast(b.field(bp, 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=arr, offset='done')
    an = b.field(arr, 'length')
    spread = b.const('f64', TURRET_SPREAD)
    one = b.const('f64', 1)
    w = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head('kl')
    fb.op('JSGte', a=k, b=an, offset='done')
    bd = b.cast(b.call('hl.types.ArrayObj.getDyn', arr, k), 'ent.BaseBuilding')  # main-base districts / HQ parts are plain BaseBuildings ($BaseBuilding.create): a cast to Building threw
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=bd, offset='kl')
    fb.op('JSLte', a=b.call('ent.Entity.get_power', bd), b=zero, offset='kl')
    fb.op('JTrue', cond=b.call('ent.BaseBuilding.get_inConstruction', bd), offset='kl')  # status 3: not built yet
    # w = (range + SPREAD - d) / SPREAD, capped at 1: full within range, 0 at range + SPREAD
    fb.op('Mov', dst=w, src=b.call('ent.Entity.get_attackRange', bd))
    fb.op('JSLte', a=w, b=zero, offset='kl')
    fb.op('Add', dst=w, a=w, b=spread)
    fb.op('Sub', dst=w, a=w, b=b.call('ent.Entity.getDistTo', 0, bd))
    fb.op('JSLte', a=w, b=zero, offset='kl')
    fb.op('SDiv', dst=w, a=w, b=spread)
    fb.op('JSLte', a=w, b=one, offset='wok')
    fb.op('Mov', dst=w, src=one)
    fb.label('wok')
    st = b.call('$HCombatStats.buildingCombatStats', bd)
    fb.op('JNull', reg=st, offset='kl')
    fb.op('Mov', dst=op_, src=b.call('$HPowerScore.offensivePotential', fb.dyn(st), zero))
    fb.op('Mul', dst=op_, a=op_, b=th)
    fb.op('Mul', dst=op_, a=op_, b=w)
    fb.op('Add', dst=tot, a=tot, b=op_)
    fb.op('JNull', reg=2, offset='kl')
    fb.op('JSLt', a=w, b=_ratio(fb, b, 0.5), offset='kl')  # vanilla report: only turrets mostly in reach
    b.call('hl.types.ArrayObj.push', 2, fb.dyn(st))
    fb.op('JAlways', offset='kl')
    fb.label('done')
    fb.op('Mov', dst=res, src=tot)
    fb.end_try(guard)
    # threw part-way: its stats already pushed would stay in vanilla's report (a Smugglers HQ's building stats with
    # health read 43M enemy power at Atreides' Uliel Annex, order balance 0.007): drop them
    fb.op('JSGte', a=res, b=b.const('f64', 0), offset='ret')
    fb.op('JNull', reg=2, offset='ret')
    nx = fb.reg(cx.t('i32'))
    fb.op('Sub', dst=nx, a=b.field(2, 'length'), b=n0)
    fb.op('JSLte', a=nx, b=b.const('i32', 0), offset='ret')
    g2 = fb.try_()
    b.call('hl.types.ArrayObj.splice', 2, n0, nx)
    fb.end_try(g2)
    fb.label('ret')
    fb.op('Ret', ret=res)
    return fb.build()


def build_cover(cx, helpers):
    """aimod_cover(fac, e, exclude, own, res) -> turret cover at e: for every structure within COVER_R of e (not
    `exclude`) owned by fac (own) or by a faction at war with fac (not own), each of its combat stats without health
    (turrets = buildings with power, main base guns; militia have health and are skipped) adds offensivePotential x
    TURRET_H to the result (an active main base's guns x MB_GUN_W), and is pushed into `res` when res is not null
    (for vanilla power reports; a main base's MB_GUN_W times). Silent: a besieged village (its turrets stop while it
    is annexed / pillaged) and dead main bases. Guest structures (zone owner != their owner: Smugglers' Underworld
    HQs) are skipped. Each structure is read by aimod_cover1 in its own trap: one that throws adds nothing (its
    pushes into res are rolled back) and is logged `cvbad` (f = asking faction, s = the structure, own; once per structure per 60 s)."""
    one_s = _build_cover1(cx)
    helpers['cover1'] = one_s  # behave adds it to new_ids (no call-site redirects inside)
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Entity'), cx.t('ent.Entity'), cx.t('bool'),
                 cx.t('hl.types.ArrayObj')], cx.t('f64'))
    b = B(fb)
    tot = b.const('f64', 0)
    zero = b.const('f64', 0)
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    state = _state(fb, b, cx)
    facs = b.cast(fb.get(state, 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=facs, offset='end')
    n = b.field(facs, 'length')
    i, j = (fb.reg(cx.t('i32')) for _ in range(2))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    op_ = fb.reg(cx.t('f64'))
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
    # fog: an enemy structure we never surveyed has unknown turrets (Structure.isReconnedFaction)
    fb.op('JTrue', cond=3, offset='rcn')
    fb.op('JFalse', cond=b.call('ent.Structure.isReconnedFaction', s, 0), offset='sl')
    fb.label('rcn')
    # far structures first (most of the map): no call / trap per structure past turret reach
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', 1, se), b=b.const('f64', COVER_R + TURRET_SPREAD), offset='sl')
    gz = b.call('ent.Entity.get_zone', se)
    fb.op('JNull', reg=gz, offset='gok')
    fb.op('JNotEq', a=b.field(gz, 'owner'), b=f, offset='sl')  # a guest (Underworld HQ): no turrets, not counted
    fb.label('gok')
    fb.op('Call3', dst=op_, fun=one_s, arg0=1, arg1=s, arg2=4)
    fb.op('JSLt', a=op_, b=zero, offset='bad')
    fb.op('Add', dst=tot, a=tot, b=op_)
    fb.op('JAlways', offset='sl')
    fb.label('bad')
    _throttle(fb, b, cx, 'cvbad', se, 60, 'sl')
    _log_ev(fb, b, cx, helpers, 'cvbad', [('f', fb.get(0, 'kind')), ('s', se), ('own', 3)])
    fb.op('JAlways', offset='sl')
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


def _renegades_at(fb, b, cx, s, yes):
    """Jump to `yes` when a renegade drop army (owner null, raid kind Renegade_Drop: vanilla Raids.regularUpdate
    spawnRaid("Renegade_Drop", null, village)) is within RENEGADE_R of s: its Takeover (siege action InstallHub)
    turns the village into a RenegadeBase for good, unlike a raider's pillage."""
    armies = b.field(_state(fb, b, cx), 'armies')
    k = fb.reg(cx.t('i32'))
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=s)
    no = _uid('rgn')
    fb.op('JNull', reg=armies, offset=no)
    x = _army_loop(fb, b, armies, b.field(armies, 'length'), k, no + 'l', no)
    fb.op('JNotNull', reg=b.call('ent.Entity.get_owner', x), offset=no + 'l')
    rd = b.field(x, 'raid')
    fb.op('JNull', reg=rd, offset=no + 'l')
    rk = b.field(rd, 'kind')
    fb.op('JNull', reg=rk, offset=no + 'l')
    fb.op('JNotEq', a=b.call('String.__compare', fb.dyn(rk), fb.dyn(fb.string('Renegade_Drop'))), b=b.const('i32', 0),
          offset=no + 'l')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', x, se), b=b.const('f64', RENEGADE_R), offset=no + 'l')
    fb.op('JAlways', offset=yes)
    fb.label(no)


def build_defend(cx, sieged, helpers, threat, neutral, own, cover, terrain):
    """aimod_defend(fac) -> one of fac's villages or main bases besieged by an at-war faction, else a neutral village
    within HOME_RING_R of one of fac's active main bases besieged / occupied by one (our home ring: a player groups
    up to stop it; Harkonnen annexed Gurlab while Smugglers annexed Zadak 177 from Carthag), else null. Renegades
    taking a village over count like a faction (_renegades_at); other raider sieges are the contest hunt's.
    Hopeless ones are skipped (never while an order of ours defending it / aimed within GATHER_R of it has an army in
    transit, e.g. a worm ride: those read 0): our armies within GATHER_R (+ our cover) x terrain below DEF_HOPE_IN x (threat +
    other raiders + enemy cover) there, left at DEF_HOPE_OUT (map `dhl` structure -> when last hopeless, 30 s, log `dhope`): a lost
    cause must not freeze every offensive (Atreides at Adnih / Tuonah vs 600-900k Fremen sat 4.5 min doing nothing).
    Several: the highest stake wins (a capture over a pillage, then the nearest to our active main base).
    Non-null = defensive posture: no new offensives (vanilla siege actions, chases) until it is resolved."""
    st_t = cx.t('ent.Structure')
    fb = FB(cx, [cx.t('ent.Faction')], st_t)
    b = B(fb)
    res = fb.reg(st_t)
    fb.op('Null', dst=res)
    fb.op('JNull', reg=0, offset='end')
    he, hn = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    hh, hm, hq, hl = (fb.reg(cx.t('f64')) for _ in range(4))
    hx = fb.reg(cx.t('ent.Army'))
    fb.op('Null', dst=hx)
    fb.op('Null', dst=hn)
    hf, ht, harr = fb.reg(cx.t('bool')), fb.reg(cx.t('bool')), fb.reg(cx.t('hl.types.ArrayObj'))
    hop = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=hf, value=False)
    fb.op('Bool', dst=ht, value=True)
    fb.op('Null', dst=harr)
    dhl = _global_map(fb, b, cx, 'dhl')

    def hopeless(s, skip):
        """Jump to `skip` when the defense of s is hopeless (hysteresis in map `dhl`) or the rally conceded it (map
        `rlygu` within RALLY_COOL); a main base never. The power sums run in a trap (callers like the spacing
        wrapper run inside vanilla calls): on error s counts as defended."""
        fb.op('Mov', dst=he, src=s)
        mbk, gok, lin, lout, lend = (_uid(n) for n in ('hmb', 'hgu', 'hpi', 'hpo', 'hpe'))
        fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', b.cast(fb.dyn(he), 'ent.Structure')), offset=mbk)
        gu = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rlygu'), fb.dyn(he))
        fb.op('JNull', reg=gu, offset=gok)
        fb.op('SafeCast', dst=hq, src=gu)
        fb.op('Sub', dst=hq, a=b.field(_state(fb, b, cx), 'time'), b=hq)
        fb.op('JSLt', a=hq, b=b.const('f64', RALLY_COOL), offset=skip)
        fb.label(gok)
        fb.op('Bool', dst=hop, value=False)
        g = fb.try_()
        # reinforcements in transit (worm ride, shuttle: _army_loop skips them, they read 0 power): an order of ours
        # defending s, or aimed within GATHER_R of it, with an army in transit -> not hopeless while they ride (Fremen
        # at Sandmur: 4 armies on a worm to its Defense, judged hopeless at 107k vs 277k, the Defense stopped mid-ride
        # by dstop, and an Annex of Burtar took the 2 armies left that would have followed)
        tro = b.field(b.field(b.field(0, 'aiController'), 'aiOrders'), 'orders')
        tdone, tol, tul = _uid('htd'), _uid('hto'), _uid('htu')
        fb.op('JNull', reg=tro, offset=tdone)
        tk, tj, tix = fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
        tte = fb.reg(cx.t('ent.Entity'))
        fb.op('Mov', dst=tk, src=b.field(tro, 'length'))
        b.loop_head(tol)
        fb.op('JSLte', a=tk, b=b.const('i32', 0), offset=tdone)
        fb.op('Sub', dst=tk, a=tk, b=b.const('i32', 1))
        to_ = b.cast(b.call('hl.types.ArrayObj.getDyn', tro, tk), 'logic.ai.AIOrder')
        fb.op('JNull', reg=to_, offset=tol)
        tun = b.field(to_, 'units')
        fb.op('JNull', reg=tun, offset=tol)
        tot = b.field(to_, 'type')
        fb.op('EnumIndex', dst=tix, value=tot)
        tnd, tchk = _uid('htn'), _uid('htc')
        fb.op('JNotEq', a=tix, b=b.const('i32', DEFENSE), offset=tnd)
        fb.op('EnumField', dst=tte, value=tot, construct=DEFENSE, field=0)
        fb.op('JEq', a=tte, b=he, offset=tchk)
        fb.label(tnd)
        fb.op('Mov', dst=tte, src=b.call('logic.ai.AIOrder.getTarget', to_))
        fb.op('JNull', reg=tte, offset=tol)
        fb.op('JSGt', a=b.call('ent.Entity.getDistTo', tte, he), b=b.const('f64', GATHER_R), offset=tol)
        fb.label(tchk)
        fb.op('Mov', dst=tj, src=b.const('i32', 0))
        b.loop_head(tul)
        fb.op('JSGte', a=tj, b=b.field(tun, 'length'), offset=tol)
        tu = b.cast(b.call('hl.types.ArrayObj.getDyn', tun, tj), 'ent.Army')
        fb.op('Incr', dst=tj)
        fb.op('JNull', reg=tu, offset=tul)
        fb.op('JTrue', cond=b.call('ent.Entity.isTransported', tu), offset=lout)
        fb.op('JAlways', offset=tul)
        fb.label(tdone)
        loc = b.const('f64', LOCAL)
        fb.op('Call3', dst=hh, fun=threat, arg0=0, arg1=he, arg2=loc)
        fb.op('Call3', dst=hq, fun=neutral, arg0=0, arg1=he, arg2=loc)
        fb.op('Add', dst=hh, a=hh, b=hq)
        fb.op('CallN', dst=hq, fun=cover, args=[0, he, he, hf, harr])
        fb.op('Add', dst=hh, a=hh, b=hq)
        fb.op('CallN', dst=hm, fun=own, args=[0, he, b.const('f64', GATHER_R), hx])
        fb.op('CallN', dst=hq, fun=cover, args=[0, he, he, ht, harr])
        fb.op('Add', dst=hm, a=hm, b=hq)
        fb.op('Call2', dst=hq, fun=terrain, arg0=0, arg1=b.call('ent.Entity.get_zone', he))
        fb.op('Mul', dst=hm, a=hm, b=hq)
        fb.op('Mov', dst=hl, src=_ratio(fb, b, DEF_HOPE_IN))
        # committed by the rally within RALLY_COOL: hold the plan down to DEF_HOPE_COMMIT (policy §1.5)
        cmv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rlyc'), fb.dyn(he))
        cmn = _uid('cmn')
        fb.op('JNull', reg=cmv, offset=cmn)
        fb.op('SafeCast', dst=hq, src=cmv)
        fb.op('Sub', dst=hq, a=b.field(_state(fb, b, cx), 'time'), b=hq)
        fb.op('JSGt', a=hq, b=b.const('f64', RALLY_COOL), offset=cmn)
        fb.op('Mov', dst=hl, src=_ratio(fb, b, DEF_HOPE_COMMIT))
        fb.label(cmn)
        dv = b.call('haxe.ds.ObjectMap.get', dhl, fb.dyn(he))  # hopeless at this time, kept while re-judged
        fb.op('JNull', reg=dv, offset=lin)
        fb.op('SafeCast', dst=hq, src=dv)
        fb.op('Sub', dst=hq, a=b.field(_state(fb, b, cx), 'time'), b=hq)
        fb.op('JSGt', a=hq, b=b.const('f64', 30), offset=lin)  # stale (an old siege): fresh judgment
        fb.op('Mov', dst=hl, src=_ratio(fb, b, DEF_HOPE_OUT))
        fb.label(lin)
        fb.op('Mul', dst=hl, a=hl, b=hh)
        fb.op('JSGte', a=hm, b=hl, offset=lout)
        fb.op('Bool', dst=hop, value=True)
        b.call('haxe.ds.ObjectMap.set', dhl, fb.dyn(he), fb.dyn(b.field(_state(fb, b, cx), 'time')))
        fb.op('JAlways', offset=lend)
        fb.label(lout)
        b.call('haxe.ds.ObjectMap.remove', dhl, fb.dyn(he))
        fb.label(lend)
        fb.end_try(g)
        fb.op('JFalse', cond=hop, offset=mbk)
        _throttle(fb, b, cx, 'dhope', he, 10, skip)
        _log_ev(fb, b, cx, helpers, 'dhope', [('f', fb.get(0, 'kind')), ('s', he), ('H', hh), ('M', hm)])
        fb.op('JAlways', offset=skip)
        fb.label(mbk)
    ok = fb.reg(cx.t('bool'))
    i = fb.reg(cx.t('i32'))
    villages = b.field(_state(fb, b, cx), 'villages')
    bases = b.field(0, 'mainBases')
    kq, kb, kd, kbest = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('Mov', dst=kbest, src=b.const('f64', -(1 << 30)))
    kj = fb.reg(cx.t('i32'))
    ke, kme = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
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
        # a raider-only siege (no faction) is the contest hunt's, not a reason for a defensive posture, unless
        # renegades are taking the village over (a permanent loss, like a capture)
        sgd = b.field(s, 'siege')
        fb.op('JNotNull', reg=b.field(sgd, 'besiegingFaction'), offset=f'{name}f')
        fb.op('JNotNull', reg=b.call('ent.comp.SiegeComponent.getOccupierFaction', sgd), offset=f'{name}f')
        _renegades_at(fb, b, cx, s, f'{name}f')
        fb.op('JAlways', offset=name)
        fb.label(f'{name}f')
        hopeless(s, name)
        # stake: a capture (Annex / Liberate / Takeover, or a siege whose occupation hasn't started) over a pillage,
        # then the nearest to our active main base (user: Atreides defended Sharas' pillage while Fremen annexed
        # Grim-in next to Arrakeen)
        fb.op('Mov', dst=kq, src=b.const('f64', 1 << 20))
        _pillaging(fb, b, cx, s, f'{name}p')
        fb.op('Mov', dst=kq, src=b.const('f64', 1 << 21))
        fb.label(f'{name}p')
        fb.op('Mov', dst=ke, src=s)
        fb.op('Mov', dst=kb, src=b.const('f64', 1 << 19))
        fb.op('JNull', reg=bases, offset=f'{name}bd')
        fb.op('Mov', dst=kj, src=b.const('i32', 0))
        b.loop_head(f'{name}bl')
        fb.op('JSGte', a=kj, b=b.field(bases, 'length'), offset=f'{name}bd')
        kmb = b.cast(b.call('hl.types.ArrayObj.getDyn', bases, kj), 'ent.Structure')
        fb.op('Incr', dst=kj)
        fb.op('JNull', reg=kmb, offset=f'{name}bl')
        fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', kmb), offset=f'{name}bl')
        fb.op('Mov', dst=kme, src=kmb)
        fb.op('Mov', dst=kd, src=b.call('ent.Entity.getDistTo', ke, kme))
        fb.op('JSGte', a=kd, b=kb, offset=f'{name}bl')
        fb.op('Mov', dst=kb, src=kd)
        fb.op('JAlways', offset=f'{name}bl')
        fb.label(f'{name}bd')
        fb.op('Sub', dst=kq, a=kq, b=kb)
        fb.op('JSLte', a=kq, b=kbest, offset=name)
        fb.op('Mov', dst=kbest, src=kq)
        fb.op('Mov', dst=res, src=s)
        fb.op('JAlways', offset=name)
        fb.label(done)
    fb.op('JNotNull', reg=res, offset='end')
    # home ring: a neutral village next to one of our active main bases under an at-war faction's siege
    fb.op('JNull', reg=villages, offset='hdone')
    fb.op('JNull', reg=bases, offset='hdone')
    j = fb.reg(cx.t('i32'))
    se, me = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('h')
    fb.op('JSGte', a=i, b=b.field(villages, 'length'), offset='hdone')
    s = b.cast(b.call('hl.types.ArrayObj.getDyn', villages, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=s, offset='h')
    fb.op('JNotNull', reg=b.call('ent.Entity.get_owner', s), offset='h')
    fb.op('Call2', dst=ok, fun=sieged, arg0=0, arg1=s)
    fb.op('JFalse', cond=ok, offset='h')
    sgd = b.field(s, 'siege')
    fb.op('JNotNull', reg=b.field(sgd, 'besiegingFaction'), offset='hf')
    fb.op('JNotNull', reg=b.call('ent.comp.SiegeComponent.getOccupierFaction', sgd), offset='hf')
    _renegades_at(fb, b, cx, s, 'hf')  # renegade Takeover: ours to stop (Haykus 244 from Tabr)
    fb.op('JAlways', offset='h')  # other raiders: hunt's
    fb.label('hf')
    fb.op('Mov', dst=se, src=s)
    fb.op('Mov', dst=j, src=b.const('i32', 0))
    b.loop_head('hb')
    fb.op('JSGte', a=j, b=b.field(bases, 'length'), offset='h')
    mb = b.cast(b.call('hl.types.ArrayObj.getDyn', bases, j), 'ent.Structure')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=mb, offset='hb')
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', mb), offset='hb')
    fb.op('Mov', dst=me, src=mb)
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', se, me), b=b.const('f64', HOME_RING_R), offset='hb')
    hopeless(se, 'h')
    fb.op('Mov', dst=res, src=s)
    fb.op('JAlways', offset='end')
    fb.label('hdone')
    fb.label('end')
    fb.op('Ret', ret=res)
    return fb.build()


def build_sieged(cx):
    """aimod_sieged(fac, s) -> s is besieged or occupied by a faction at war with fac (or by neutral raiders: no
    faction set), and s is neutral, ours, or belongs to a faction not at war with us (a capture we want to stop);
    raiders count only on a neutral village or ours. Reads the structure's own siege state
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
    fb.op('JNotNull', reg=bf, offset='have')
    # no faction: a neutral raider besieging / occupying it (liberating, pillaging) blocks every faction's Annex /
    # Pillage / Liberate there until it dies (Raider_Ranged liberating Qal-nit)
    # ... only on a neutral village or ours: raiders on a third faction's village hurt only that faction (Fremen
    # cancelled a chase `objective` for a raider siege of Harkonnen's O-ram, 830 away, and no contest followed)
    fb.op('JTrue', cond=b.field(sg, 'isUnderSiege'), offset='rown')
    fb.op('JNull', reg=b.field(sg, 'occupier'), offset='end')
    fb.label('rown')
    ro = b.call('ent.Entity.get_owner', 1)
    fb.op('JNull', reg=ro, offset='yes')
    fb.op('JEq', a=ro, b=0, offset='yes')
    fb.op('JAlways', offset='end')
    fb.label('have')
    fb.op('JEq', a=bf, b=0, offset='end')
    state = _state(fb, b, cx)
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, 0, bf), offset='end')
    fb.label('own')
    state = _state(fb, b, cx)
    o = b.call('ent.Entity.get_owner', 1)
    fb.op('JNull', reg=o, offset='yes')
    fb.op('JEq', a=o, b=0, offset='yes')
    fb.op('JTrue', cond=b.call('logic.state.State.areAtWar', state, 0, o), offset='end')
    fb.label('yes')
    # fog: another faction's / a neutral village's siege state only while we see its cell (ours: the game alerts us)
    fb.op('JEq', a=b.call('ent.Entity.get_owner', 1), b=0, offset='vok')
    fb.op('JFalse', cond=b.call('ent.Faction.isInVisibleCell', 0, 1), offset='end')
    fb.label('vok')
    fb.op('Bool', dst=res, value=True)
    fb.label('end')
    fb.op('Ret', ret=res)
    return fb.build()
