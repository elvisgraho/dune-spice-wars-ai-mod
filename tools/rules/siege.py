"""Vanilla siege and order inputs: turret/third-party-aware power reports, bunker target score, siege launch gate
(defend / bunker / annex-spacing), discovery gate, busy-siege null fix."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.intel import _seen_map, _rec_get, _rec_of



OWNER_F = (1, 0.5, 0.25, 0.1, 0, 0)   # an owner's army by zones away (data AI_PowerScore_EnemyAdditionalArmy_Factor
# 1 / .75 / .5 / .25 / .1 / 0: user, an army zones away gets seen coming and the capture retreats if it returns; Fremen
# never started on Zayur with Harkonnen's stack 360 away, match 2026-10-04 21:4x); main bases keep vanilla's table
OWNER_MB_F = (1, 0.8, 0.65, 0.5, 0.2)    # ... _MainBase_Factor (the target is a main base)


def _owner_armies(fb, b, cx, pw, ai, s, res, fac=None, acc=None):
    """Vanilla getEnemyCombatStats' owner-army part with fog of war: each combat army of s's owner by what the asking
    faction knows: seen now -> its zone (busy fighting / capturing: x BUSY_W); seen within SEEN_T -> the zone of its
    sighting (busy then and less than BUSY_SEEN_T ago: x BUSY_W); seen now in a Military order of its owner on another
    structure (on a mission elsewhere): x MISSION_W; unknown -> the owner's main base (a player assumes
    the unseen army is home). Weight = vanilla's factor by zones from s; pushed into res as
    unitSimulatedCombatStats(army, s's zone) with that externalFactor, as vanilla does. With `acc` (f64 reg) and
    `fac` (the asking faction): power x weight summed into acc instead (aimod_owner_pw)."""
    if fac is None:
        fac = b.field(b.field(ai, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='oa_end')
    so = b.call('ent.Entity.get_owner', s)
    fb.op('JNull', reg=so, offset='oa_end')
    sz = b.call('ent.Entity.get_zone', s)
    fb.op('JNull', reg=sz, offset='oa_end')
    dists = b.call('ent.Zone.calcDistanceFrom', sz)
    fb.op('JNull', reg=dists, offset='oa_end')
    nd = b.field(dists, 'length')
    gs = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gs, **{'global': cx.global_of('$Game')})
    world = b.field(b.field(gs, 'inst'), 'world')
    fb.op('JNull', reg=world, offset='oa_end')
    mbz = fb.reg(cx.t('ent.Zone'))
    fb.op('Null', dst=mbz)
    mb = b.call('ent.Faction.get_mainBase', so)
    fb.op('JNull', reg=mb, offset='oa_nomb')
    mbe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=mbe, src=mb)
    fb.op('Mov', dst=mbz, src=b.call('ent.Entity.get_zone', mbe))
    fb.label('oa_nomb')
    ismb = b.call('ent.Structure.get_isMainBase', s)
    mp = _seen_map(fb, b, cx, fac)
    now = b.field(_state(fb, b, cx), 'time')
    arr, alen = _my_armies(fb, b, so, 'oa_end')
    i, dz, zid = fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    z = fb.reg(cx.t('ent.Zone'))
    f, p, age = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    bz, bm = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    x = _army_loop(fb, b, arr, alen, i, 'oa_l', 'oa_end')
    fb.op('JNotNull', reg=b.field(x, 'harvestComponent'), offset='oa_l')
    fb.op('Call1', dst=p, fun=pw, arg0=x)
    fb.op('JSLte', a=p, b=b.const('f64', 0), offset='oa_l')
    fb.op('Bool', dst=bz, value=False)
    fb.op('Bool', dst=bm, value=False)
    fb.op('JTrue', cond=b.call('ent.Entity.isVisibleForFaction', x, fac), offset='oa_vis')
    rec = _rec_of(fb, b, cx, mp, x, 'oa_unk')
    fb.op('Sub', dst=age, a=now, b=_rec_get(fb, b, cx, rec, 't'))
    fb.op('JSGt', a=age, b=b.const('f64', SEEN_T), offset='oa_unk')
    fb.op('Mov', dst=z, src=b.call('world.World.getZoneAt', world, _rec_get(fb, b, cx, rec, 'x'),
                                   _rec_get(fb, b, cx, rec, 'y')))
    fb.op('JSGt', a=age, b=b.const('f64', BUSY_SEEN_T), offset='oa_zone')
    fb.op('JSLt', a=_rec_get(fb, b, cx, rec, 'b'), b=b.const('f64', 1), offset='oa_zone')
    fb.op('Bool', dst=bz, value=True)
    fb.op('JAlways', offset='oa_zone')
    fb.label('oa_unk')
    fb.op('Mov', dst=z, src=mbz)
    fb.op('JAlways', offset='oa_zone')
    fb.label('oa_vis')
    fb.op('Mov', dst=z, src=b.call('ent.Entity.get_zone', x))
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', x), offset='oa_vb')
    fb.op('JNotNull', reg=b.field(x, 'occupiedStructure'), offset='oa_vb')
    fb.op('JNotNull', reg=b.field(x, 'contestingStructure'), offset='oa_vb')
    # on a mission elsewhere: a Military order of its owner on another structure (walking to a capture / liberation)
    # counts x MISSION_W (user: Harkonnen's stack 360 away was out liberating, Fremen's Liberate of Zayur needed
    # 13-16 of 19 armies at 2x and never went, match 2026-10-04 21:4x)
    xo = fb.reg(cx.t('logic.ai.AIOrder'))
    _order_of(fb, b, cx, so, x, xo, 'oa_zone')
    xix = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=xix, value=b.field(xo, 'type'))
    fb.op('JNotEq', a=xix, b=b.const('i32', MILITARY), offset='oa_zone')
    xtt = b.field(xo, 'targetType')
    fb.op('JNull', reg=xtt, offset='oa_zone')
    fb.op('EnumIndex', dst=xix, value=xtt)
    fb.op('JNotEq', a=xix, b=b.const('i32', T_STRUCT), offset='oa_zone')
    xts = b.cast(b.call('logic.ai.AIOrder.getTarget', xo), 'ent.Entity')
    fb.op('JNull', reg=xts, offset='oa_zone')
    fb.op('JEq', a=xts, b=s, offset='oa_zone')
    fb.op('Bool', dst=bm, value=True)
    fb.op('JAlways', offset='oa_zone')
    fb.label('oa_vb')
    fb.op('Bool', dst=bz, value=True)
    fb.label('oa_zone')
    fb.op('JNull', reg=z, offset='oa_l')
    fb.op('Mov', dst=zid, src=b.field(z, 'id'))
    fb.op('Mov', dst=dz, src=b.const('i32', 0))
    fb.op('JSGte', a=zid, b=nd, offset='oa_dz')  # vanilla: an id past the table reads 0
    fb.op('JSLt', a=zid, b=b.const('i32', 0), offset='oa_dz')
    fb.op('SafeCast', dst=dz, src=b.call('hl.types.ArrayBytes_Int.getDyn', dists, zid))
    fb.label('oa_dz')
    fb.op('JTrue', cond=ismb, offset='oa_mf')
    for tbl, lab in ((OWNER_F, 'oa_vf'), (OWNER_MB_F, 'oa_mf')):
        fb.label(lab)
        for k, v in enumerate(tbl):
            nxt = f'{lab}{k}'
            if k < len(tbl) - 1:
                fb.op('JNotEq', a=dz, b=b.const('i32', k), offset=nxt)
            fb.op('Mov', dst=f, src=_ratio(fb, b, v))
            fb.op('JAlways', offset='oa_f')
            if k < len(tbl) - 1:
                fb.label(nxt)
    fb.label('oa_f')
    fb.op('JSLte', a=f, b=b.const('f64', 0), offset='oa_l')
    fb.op('JFalse', cond=bz, offset='oa_nb')
    fb.op('Mul', dst=f, a=f, b=_ratio(fb, b, BUSY_W))
    fb.label('oa_nb')
    fb.op('JFalse', cond=bm, offset='oa_nm')
    fb.op('Mul', dst=f, a=f, b=_ratio(fb, b, MISSION_W))
    fb.label('oa_nm')
    if acc is not None:
        fb.op('Mul', dst=p, a=p, b=f)
        fb.op('Add', dst=acc, a=acc, b=p)
        fb.op('JAlways', offset='oa_l')
    else:
        st = b.call('$HCombatStats.unitSimulatedCombatStats', x, sz)
        fb.op('JNull', reg=st, offset='oa_l')
        fb.op('DynSet', obj=st, field=cx.s('externalFactor'), src=f)
        b.call('hl.types.ArrayObj.push', res, fb.dyn(st))
        fb.op('JAlways', offset='oa_l')
    fb.label('oa_end')


def build_owner_pw(cx, pw):
    """aimod_owner_pw(fac, s) -> f64: the owner of structure s's combat armies as faction fac knows them (seen -> its
    zone, remembered -> the zone of its sighting, unknown -> the owner's main base; busy x BUSY_W), each power x
    vanilla's owner factor by zones from s (OWNER_F / OWNER_MB_F). 0 for an unowned s or on any error. Raids on an
    at-war village read their side as at least this (Atreides raided Smugglers' Tab-Al'nin at 274k vs a seen 287k
    twice and lost everything to 166-245M of order power: the defenders were out of sight)."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Structure')], cx.t('f64'))
    b = B(fb)
    acc = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=acc, src=b.const('f64', 0))
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='oa_end')
    fb.op('JNull', reg=1, offset='oa_end')
    _owner_armies(fb, b, cx, pw, None, 1, None, fac=0, acc=acc)
    fb.end_try(guard)
    fb.op('Ret', ret=acc)
    return fb.build()


def build_turret_stats(cx, cover, silence, threat_stats, new_ids, pw):
    """Turret- and third-party-aware vanilla power reports (pickUnits = attack/defense sizing, getOrderPowerBalance =
    live balance):
    - getEnemyCombatStats(s, ...) for a structure not ours: drop s's own turrets (silent while we annex / pillage
      it; not for main bases) and add the turrets / main base guns of every other at-war structure within COVER_R
      (vanilla adds only the owner's main base in range: a bunker neighbour's turrets were ignored), and the
      at-war armies of every faction but s's owner within LOCAL of s (aimod_threat measure; vanilla counts only
      the owner's armies, so a neutral village next to a rival's army blob looked like a 3:1 win). The live
      balance (tryUseOrderAbilities, Action phase) only decides emergency order abilities; it cancels nothing.
    - structureCombatStats(allyStructure) (our defended structure): drop its turrets while it is besieged, add our
      other structures' turrets within COVER_R.
    Health-less stats add offense, which vanilla multiplies by the army HP: fear grows with the armies it supports.
    Original result on any error."""
    report = {}
    callers = ['logic.ai.AIUnits.pickUnits', 'logic.ai.AIUnits.getOrderPowerBalance']
    arr_t = cx.t('hl.types.ArrayObj')
    # enemy side
    orig = cx.fn('logic.ai.AIUnits.getEnemyCombatStats')
    args = [a.value for a in cx.code.types[orig.type.value].definition.args]
    fb = FB(cx, args, arr_t, fun_type=orig.type.value)
    b = B(fb)
    void = fb.reg(cx.t('void'))
    res = fb.reg(arr_t)
    # fog of war: the owner's armies (vanilla: every one, zone-weighted) are added below from what we know of them
    own_add = fb.reg(cx.t('bool'))
    ign = fb.reg(args[3])
    fb.op('Bool', dst=own_add, value=False)
    fb.op('Mov', dst=ign, src=3)
    g0 = fb.try_()
    fb.op('JNull', reg=1, offset='oa_no')
    so0 = b.call('ent.Entity.get_owner', 1)
    fb.op('JNull', reg=so0, offset='oa_no')
    fb.op('JEq', a=so0, b=b.field(b.field(0, 'controller'), 'owner'), offset='oa_no')
    fb.op('JNull', reg=3, offset='oa_yes')
    fl0 = fb.reg(cx.t('bool'))
    fb.op('SafeCast', dst=fl0, src=3)
    fb.op('JTrue', cond=fl0, offset='oa_no')
    fb.label('oa_yes')
    fb.op('Bool', dst=own_add, value=True)
    tb = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=tb, value=True)
    fb.op('Mov', dst=ign, src=fb.dyn(tb))
    fb.label('oa_no')
    fb.end_try(g0)
    fb.op('Call4', dst=res, fun=orig.findex.value, arg0=0, arg1=1, arg2=2, arg3=ign)
    fb.op('JFalse', cond=own_add, offset='oa_done')
    fb.op('JNull', reg=res, offset='oa_done')
    g1 = fb.try_()
    _owner_armies(fb, b, cx, pw, 0, 1, res)
    fb.end_try(g1)
    fb.label('oa_done')
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    fb.op('JNull', reg=1, offset='end')
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    fb.op('JEq', a=b.call('ent.Entity.get_owner', 1), b=fac, offset='end')
    own = b.call('$HCombatStats.structureCombatStats', 1)
    fb.op('JNull', reg=own, offset='cov')
    fb.op('Call3', dst=void, fun=silence, arg0=res, arg1=1, arg2=b.field(own, 'length'))
    fb.label('cov')
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=1)
    no, t = fb.reg(cx.t('bool')), fb.reg(cx.t('f64'))
    fb.op('Bool', dst=no, value=False)
    fb.op('CallN', dst=t, fun=cover, args=[fac, se, se, no, res])
    # third-party armies: at-war armies around the target that vanilla ignores (all of them for a neutral village,
    # other factions' for an owned one; the owner's own are counted by vanilla, zone-weighted). Not when the caller
    # asks to ignore armies, nor for an army target (`units`: vanilla adds that army's team itself)
    fb.op('JNull', reg=3, offset='third')
    flag = fb.reg(cx.t('bool'))
    fb.op('SafeCast', dst=flag, src=3)
    fb.op('JTrue', cond=flag, offset='end')
    fb.label('third')
    fb.op('JNull', reg=2, offset='units')
    fb.op('JSGt', a=b.field(2, 'length'), b=b.const('i32', 0), offset='end')
    fb.label('units')
    z = b.call('ent.Entity.get_zone', se)
    fb.op('JNull', reg=z, offset='end')
    so = b.call('ent.Entity.get_owner', se)
    fb.op('CallN', dst=t, fun=threat_stats, args=[fac, se, b.const('f64', LOCAL), so, res, z])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    report['turret:getEnemyCombatStats'] = _redirect(cx, 'logic.ai.AIUnits.getEnemyCombatStats', callers, w)
    # our side
    orig = cx.fn('$HCombatStats.structureCombatStats')
    fb = FB(cx, [cx.t('ent.Structure')], arr_t, fun_type=orig.type.value)
    b = B(fb)
    void = fb.reg(cx.t('void'))
    res = fb.reg(arr_t)
    fb.op('Call1', dst=res, fun=orig.findex.value, arg0=0)
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    fb.op('JNull', reg=0, offset='end')
    o = b.call('ent.Entity.get_owner', 0)
    fb.op('JNull', reg=o, offset='end')
    sg = b.field(0, 'siege')
    fb.op('JNull', reg=sg, offset='cov')
    fb.op('JNull', reg=b.field(sg, 'besiegingFaction'), offset='cov')
    fb.op('Call3', dst=void, fun=silence, arg0=res, arg1=0, arg2=b.field(res, 'length'))
    fb.label('cov')
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=0)
    yes, t = fb.reg(cx.t('bool')), fb.reg(cx.t('f64'))
    fb.op('Bool', dst=yes, value=True)
    fb.op('CallN', dst=t, fun=cover, args=[o, se, se, yes, res])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    report['turret:allyStructure'] = _redirect(cx, '$HCombatStats.structureCombatStats', callers, w)
    return report


def build_ddclean(cx, strict=False, threat=None):
    """aimod_ddclean(fac, zone) -> true when fac can gain deep deserts by surrounding them (attribute DD_ATB, or kind
    Fremen before it) and the zone borders an unowned deep desert that is an uncontested ring in progress: one of its
    neighbours is already ours, no other faction's main-base zone borders it, and every neighbour with a village
    still missing (the zone itself excluded) is neutral and farther than DD_BASE_R from other factions' main bases,
    within supply reach (common._unreach) and without an at-war stack at it (aimod_threat within LOCAL, when built
    with threat): an unfavourable ring is dropped, not pursued at all costs (user).
    Used by raid / the pillage press (never pillage such a village: Devastated, cost doubled).
    strict=True: aimod_ddhold, the Annex hold's test: the attribute itself (before it a ring yields nothing) and at
    most DD_HOLD_MISS villages missing besides the zone (a far-off ring doesn't freeze every other Annex)."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Zone')], cx.t('bool'))
    b = B(fb)
    ok = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=ok, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    zi = b.const('i32', 0)
    gobj = fb.reg(cx.code.types[cx.fn('ent.Object.hasAttribute').type.value].definition.args[0].value)
    fb.op('Mov', dst=gobj, src=0)
    has = cx.fn('ent.Object.hasAttribute')
    hat = [a.value for a in cx.code.types[has.type.value].definition.args]
    href, hfac = fb.reg(hat[2]), fb.reg(hat[3])
    fb.op('Null', dst=href)
    fb.op('Null', dst=hfac)
    hres = fb.reg(cx.t('bool'))
    fb.op('Call4', dst=hres, fun=has.findex.value, arg0=gobj, arg1=b.const('i32', DD_ATB), arg2=href, arg3=hfac)
    fb.op('JTrue', cond=hres, offset='cap')
    if strict:
        fb.op('JAlways', offset='end')
    kd = b.field(0, 'kind')
    fb.op('JNull', reg=kd, offset='end')
    fb.op('JNotEq', a=b.call('String.__compare', kd, fb.dyn(fb.string('Fremen'))), b=zi, offset='end')
    fb.label('cap')
    hmb = cx.fn('ent.Zone.hasMainBase')
    hnull = fb.reg(cx.code.types[hmb.type.value].definition.args[1].value)
    fb.op('Null', dst=hnull)
    hm, ours = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    facs = b.cast(fb.get(_state(fb, b, cx), 'factions', 'array'), 'hl.types.ArrayObj')
    br = b.const('f64', DD_BASE_R)
    k1, k2, k3, k4 = (fb.reg(cx.t('i32')) for _ in range(4))
    zn = b.field(1, 'neighbors')
    fb.op('JNull', reg=zn, offset='end')
    fb.op('Mov', dst=k1, src=zi)
    b.loop_head('d')
    fb.op('JSGte', a=k1, b=b.field(zn, 'length'), offset='end')
    dz = b.cast(b.call('hl.types.ArrayObj.getDyn', zn, k1), 'ent.Zone')
    fb.op('Incr', dst=k1)
    fb.op('JNull', reg=dz, offset='d')
    fb.op('JFalse', cond=b.call('ent.Zone.isDeepDesert', dz), offset='d')
    fb.op('JEq', a=b.field(dz, 'owner'), b=0, offset='d')
    fb.op('Bool', dst=ours, value=False)
    nmiss = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=nmiss, src=zi)
    dn = b.field(dz, 'neighbors')
    fb.op('JNull', reg=dn, offset='d')
    fb.op('Mov', dst=k2, src=zi)
    b.loop_head('e')
    fb.op('JSGte', a=k2, b=b.field(dn, 'length'), offset='ed')
    mz = b.cast(b.call('hl.types.ArrayObj.getDyn', dn, k2), 'ent.Zone')
    fb.op('Incr', dst=k2)
    fb.op('JNull', reg=mz, offset='e')
    fb.op('JEq', a=mz, b=1, offset='e')  # the zone itself
    mo = b.field(mz, 'owner')
    fb.op('JNotEq', a=mo, b=0, offset='nm')
    fb.op('Bool', dst=ours, value=True)
    fb.op('JAlways', offset='e')
    fb.label('nm')
    fb.op('Call2', dst=hm, fun=hmb.findex.value, arg0=mz, arg1=hnull)
    fb.op('JTrue', cond=hm, offset='d')  # another faction's main base borders it: never ours
    mv = b.call('ent.Zone.getVillage', mz)
    fb.op('JNull', reg=mv, offset='e')  # no village: not counted by updateOwner
    fb.op('JNotNull', reg=mo, offset='d')  # another faction holds a missing neighbour: contested
    # not favourable: a missing neighbour out of supply reach (our last order on it died in Waiting) or with an at-war
    # stack at / heading to it -> no ring in progress there (the hold releases, raids may take it)
    mvu = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=mvu, src=mv)
    _unreach(fb, b, cx, mvu, b.field(_state(fb, b, cx), 'time'), 'd', 0)
    if threat is not None:
        thq = fb.reg(cx.t('f64'))
        fb.op('Call3', dst=thq, fun=threat, arg0=0, arg1=mvu, arg2=b.const('f64', LOCAL))
        fb.op('JSGt', a=thq, b=b.const('f64', 0), offset='d')
    fb.op('JNull', reg=facs, offset='miss')
    mve = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=mve, src=mv)
    fb.op('Mov', dst=k3, src=zi)
    b.loop_head('f')
    fb.op('JSGte', a=k3, b=b.field(facs, 'length'), offset='miss')
    of = b.cast(b.call('hl.types.ArrayObj.getDyn', facs, k3), 'ent.Faction')
    fb.op('Incr', dst=k3)
    fb.op('JNull', reg=of, offset='f')
    fb.op('JEq', a=of, b=0, offset='f')
    mbs = b.field(of, 'mainBases')
    fb.op('JNull', reg=mbs, offset='f')
    fb.op('Mov', dst=k4, src=zi)
    b.loop_head('g')
    fb.op('JSGte', a=k4, b=b.field(mbs, 'length'), offset='f')
    mb = b.cast(b.call('hl.types.ArrayObj.getDyn', mbs, k4), 'ent.Entity')
    fb.op('Incr', dst=k4)
    fb.op('JNull', reg=mb, offset='g')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', mve, mb), b=br, offset='d')  # near an enemy base: contested
    fb.op('JAlways', offset='g')
    fb.label('miss')  # a neutral missing village, clear of enemy bases
    fb.op('Incr', dst=nmiss)
    fb.op('JAlways', offset='e')
    fb.label('ed')
    fb.op('JFalse', cond=ours, offset='d')  # ring not started from our land
    if strict:
        fb.op('JSGt', a=nmiss, b=b.const('i32', DD_HOLD_MISS), offset='d')
    fb.op('Bool', dst=ok, value=True)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=ok)
    return fb.build()


def build_spacing(cx, helpers, defend, land, home, homeown):
    """Wrapper for the single tryAction -> tryArmyAction(k, s, data) call (every vanilla siege launch: Annex,
    Pillage, Raze, ...), strategic order of checks:
    1. defend: one of our structures is besieged (aimod_defend) -> no new offensive: refuse (log `space`, why defend,
       near = our besieged structure).
    2. bunker: an Annex goes first to a village within BUNKER_R of our active main base that an at-war faction took
       (lost) and no Military order of ours targets yet: s is replaced (log `bunker`). Bypasses vanilla's target
       score and aggressiveness gate on purpose. Neutral ones aren't redirected (it beat deep-desert ring villages
       and everything else): the Annex value scores them x BUNKER_MB.
    1b. trip cost of a Liberate / Raze / PillageSietch / Dismantle (d = its target's distance to our land; not the
    director's pressed village,
       map `spv`): (a) beyond LOCAL while our Annex is pending (Annexation gauge >= RAID_GAUGE, full for less than
       RAID_GAUGE_T: raid's map `rgauge`, read only) -> refuse, why annex (the armies are about to have better work
       at home); (b) the at-war armies free to reach our land before we are back (aimod_home(d)) x ENTER above
       LIB_KEEP x our armies within d of our land (aimod_homeown) x OWN_T -> refuse, why exposed (the farther, the
       more of them count). Judged at launch only: a running order is never re-judged (no flip-flop). Pillage is
       raid's; Annex has its own value per cost.
    1c. scout: Fremen opening hold (aimod_fopen, rules/fopen.py) -> refuse an Annex, why scout.
    3. annex-spacing: one of our Military orders already targets another structure within ADJ_R of s (two thin
       sieges side by side split the force) -> refuse (log `space`, why space).
    Refusal = onActionEnd(gauge(k), Dismiss, data): gauge un-paused, no decay, no onFailure blocks; `exposed` lasts
    minutes (the Liberation gauge re-fired every 0.5 s for 12 min, 1801 fires), so it ends with Skip instead (x0.85,
    still no onFailure blocks): the gauge refills and re-asks in ~30 s. `space` logged
    once per faction per 10 s (the gauge retries often). Otherwise (or on any error) the original with s (or the
    bunker village); when that call created an order on the target (not NoAvailableArmy / NotEnoughArmies) its time is
    recorded (map 'alaunch'; the bunker skips a village launched less than RETRY s ago, the scoring wrapper drops it)."""
    orig = cx.fn('logic.ai.AIMilitary.tryArmyAction')
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    fb = FB(cx, args, cx.t('void'), fun_type=orig.type.value)
    b = B(fb)
    void = fb.reg(cx.t('void'))
    st_t = cx.t('ent.Structure')
    blocked = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=blocked, value=False)
    decay = fb.reg(cx.t('bool'))  # a lasting refusal: the gauge decays instead of re-firing every 0.5 s
    fb.op('Bool', dst=decay, value=False)
    near = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=near)
    why = fb.reg(cx.t('String'))
    fb.op('Mov', dst=why, src=fb.string('space'))
    tgt = fb.reg(st_t)  # the target we launch (s, or the bunker village)
    fb.op('Mov', dst=tgt, src=2)
    guard = fb.try_()
    fb.op('JNull', reg=2, offset='done')
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='done')
    orders = b.field(b.field(b.field(0, 'controller'), 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='done')
    n = b.field(orders, 'length')
    i, j, idx = fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    zi = b.const('i32', 0)
    s_e = fb.reg(cx.t('ent.Entity'))

    # 1. defensive posture
    dfs = fb.reg(st_t)
    fb.op('Call1', dst=dfs, fun=defend, arg0=fac)
    fb.op('JNull', reg=dfs, offset='rallyg')
    fb.op('Mov', dst=near, src=dfs)
    fb.op('Mov', dst=why, src=fb.string('defend'))
    fb.op('Bool', dst=blocked, value=True)
    fb.op('JAlways', offset='done')
    # 1a. a rally running (map `rly`, rules/rally.py: the enemy is at or heading to D, not yet besieging): the armies
    # gather there, no siege takes them away (Fremen's Annex of Sabbat took 3 armies from the rally point while
    # Atreides walked to Grim-po)
    fb.label('rallyg')
    rlv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rly'), fb.dyn(fac))
    fb.op('JNull', reg=rlv, offset='bunker')
    rls = b.cast(rlv, 'ent.Structure')
    fb.op('JNull', reg=rls, offset='bunker')
    fb.op('Mov', dst=near, src=rls)
    fb.op('Mov', dst=why, src=fb.string('rally'))
    fb.op('Bool', dst=blocked, value=True)
    fb.op('JAlways', offset='done')

    # 1b. trip cost of a Liberate / Raze (Harkonnen sent 9 of 11 armies to liberate Atreides' Marwan 694 from its
    # land while its Annex waited on Authority; affordable 2 min later, it failed NotEnoughArmies / NoAvailableArmy)
    fb.label('bunker')
    # Sietch and renegade-base strikes too (PillageSietch / Dismantle, prio 2, owner-less: vanilla sizes them by the
    # defenders alone): Smugglers sent all 15 armies to Ub-Al'khelon's sietch for 5 min while the director held
    # (no spare force, 640k hostile near home)
    for kind in ('Liberate', 'PillageSietch', 'Dismantle'):
        fb.op('JEq', a=b.call('String.__compare', 1, fb.dyn(fb.string(kind))), b=zi, offset='farchk')
    fb.op('JNotEq', a=b.call('String.__compare', 1, fb.dyn(fb.string('Raze'))), b=zi, offset='bunker2')
    fb.label('farchk')
    fb.op('JEq', a=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'spv'), fb.dyn(fac)), b=fb.dyn(2),
          offset='bunker2')  # the pressed village
    fdis, fq, fh = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=s_e, src=2)
    fb.op('Call2', dst=fdis, fun=land, arg0=fac, arg1=s_e)
    # (a) our Annex is pending: work at home first
    fb.op('JSLte', a=fdis, b=b.const('f64', LOCAL), offset='fexp')
    gauges = b.cast(fb.get(0, 'gauges'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=gauges, offset='fexp')
    gk = fb.reg(cx.t('String'))
    gi = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=gi, src=zi)
    b.loop_head('fgl')
    fb.op('JSGte', a=gi, b=b.field(gauges, 'length'), offset='fexp')
    gg = b.call('hl.types.ArrayObj.getDyn', gauges, gi)
    fb.op('Incr', dst=gi)
    fb.op('JNull', reg=gg, offset='fgl')
    fb.op('DynGet', dst=gk, obj=gg, field=cx.s('kind'))
    fb.op('JNull', reg=gk, offset='fgl')
    fb.op('JNotEq', a=b.call('String.__compare', gk, fb.dyn(fb.string('Annexation'))), b=zi, offset='fgl')
    fb.op('DynGet', dst=fq, obj=gg, field=cx.s('value'))
    fb.op('JSLt', a=fq, b=b.const('f64', RAID_GAUGE), offset='fexp')
    rgv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rgauge'), fb.dyn(fac))
    fb.op('JNull', reg=rgv, offset='fann')  # full, not yet timed: pending
    fb.op('SafeCast', dst=fq, src=rgv)
    fb.op('Sub', dst=fq, a=b.field(_state(fb, b, cx), 'time'), b=fq)
    fb.op('JSGte', a=fq, b=b.const('f64', RAID_GAUGE_T), offset='fexp')  # stuck full: its Annex isn't coming
    fb.label('fann')
    fb.op('Mov', dst=why, src=fb.string('annex'))
    fb.op('Bool', dst=blocked, value=True)
    fb.op('JAlways', offset='done')
    # (b) home exposure over the trip
    fb.label('fexp')
    fnul = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=fnul)
    fb.op('Call2', dst=fh, fun=home, arg0=fac, arg1=fdis)
    fb.op('JSLte', a=fh, b=b.const('f64', 0), offset='bunker2')
    fb.op('Call3', dst=fq, fun=homeown, arg0=fac, arg1=fdis, arg2=fnul)
    fb.op('Mul', dst=fq, a=fq, b=_ratio(fb, b, LIB_KEEP * OWN_T))
    fb.op('Mul', dst=fh, a=fh, b=_ratio(fb, b, ENTER))
    fb.op('JSLte', a=fh, b=fq, offset='bunker2')
    fb.op('Mov', dst=why, src=fb.string('exposed'))
    fb.op('Bool', dst=blocked, value=True)
    fb.op('Bool', dst=decay, value=True)
    fb.op('JAlways', offset='done')

    # 2. bunker: Annex only
    fb.label('bunker2')
    cmp = b.call('String.__compare', 1, fb.dyn(fb.string('Annex')))
    fb.op('JNotEq', a=cmp, b=zi, offset='spacing')
    # 1c. Fremen opening scout hold (rules/fopen.py): no first Annex before a ring village or FOPEN_N choices are known
    hold = fb.reg(cx.t('bool'))
    fb.op('Call1', dst=hold, fun=helpers['fopen'], arg0=fac)
    fb.op('JFalse', cond=hold, offset='fopen_no')
    fb.op('Mov', dst=why, src=fb.string('scout'))
    fb.op('Bool', dst=blocked, value=True)
    fb.op('JAlways', offset='done')
    fb.label('fopen_no')
    state = _state(fb, b, cx)
    villages = b.field(state, 'villages')
    fb.op('JNull', reg=villages, offset='spacing')
    vn = b.field(villages, 'length')
    bases = b.field(fac, 'mainBases')
    fb.op('JNull', reg=bases, offset='spacing')
    bn = b.field(bases, 'length')
    br = b.const('f64', BUNKER_R)
    mbe, ve = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    k = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=zi)
    b.loop_head('mb')
    fb.op('JSGte', a=i, b=bn, offset='spacing')
    mb = b.cast(b.call('hl.types.ArrayObj.getDyn', bases, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=mb, offset='mb')
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', mb), offset='mb')
    fb.op('Mov', dst=mbe, src=mb)
    fb.op('Mov', dst=j, src=zi)
    b.loop_head('bv')
    fb.op('JSGte', a=j, b=vn, offset='mb')
    v = b.cast(b.call('hl.types.ArrayObj.getDyn', villages, j), 'ent.Structure')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=v, offset='bv')
    fb.op('Mov', dst=ve, src=v)
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ve, mbe), b=br, offset='bv')
    vo = b.call('ent.Entity.get_owner', ve)
    fb.op('JNull', reg=vo, offset='bv')  # neutral: no redirect, its Annex score x BUNKER_MB instead
    fb.op('JEq', a=vo, b=fac, offset='bv')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, vo), offset='bv')
    fb.label('bfree')
    fb.op('Mov', dst=s_e, src=tgt)
    fb.op('JEq', a=ve, b=s_e, offset='spacing')  # vanilla picked it already
    _recent_launch(fb, b, cx, ve, b.field(state, 'time'), 'bv', fac=fac, helpers=helpers)  # its last launch ended at once
    # skip it if one of our Military orders already targets it
    fb.op('Mov', dst=k, src=zi)
    b.loop_head('bo')
    fb.op('JSGte', a=k, b=n, offset='bswap')
    bo = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, k), 'logic.ai.AIOrder')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=bo, offset='bo')
    fb.op('EnumIndex', dst=idx, value=b.field(bo, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='bo')
    btt = b.field(bo, 'targetType')
    fb.op('JNull', reg=btt, offset='bo')
    fb.op('EnumIndex', dst=idx, value=btt)
    fb.op('JNotEq', a=idx, b=b.const('i32', T_STRUCT), offset='bo')
    fb.op('JEq', a=b.call('logic.ai.AIOrder.getTarget', bo), b=ve, offset='bv')
    fb.op('JAlways', offset='bo')
    fb.label('bswap')
    guard_l = fb.try_()
    _throttle(fb, b, cx, 'bunkx', fac, 10, 'bnolog')  # vanilla re-fires the gauge every few s: once per 10 s
    _log_ev(fb, b, cx, helpers, 'bunker', [('f', fb.get(fac, 'kind')), ('k', 1), ('tgt', ve), ('was', 2),
                                           ('mb', mbe)])
    fb.label('bnolog')
    fb.end_try(guard_l)
    fb.op('Mov', dst=tgt, src=v)

    # 2b. Authority reserve (Annex only): vanilla checks the price against the stock alone, and the cost is paid only
    # when the capture starts (militia dead). Fremen launched Qalnih (136) at 181 Authority while Urno's capture was
    # paying ~126 and then raised the price (+1 village): 5 armies stood idle at Qalnih for minutes. Each Annex of ours
    # not yet capturing owes its cost + ANNEX_RISE, a capture under way ANNEX_RISE (paid; its gain raises our price);
    # stock < our cost + that -> refuse (why auth, near = last pending target; log `ares` au / need / n)
    fb.label('spacing')
    fb.op('JNotEq', a=b.call('String.__compare', 1, fb.dyn(fb.string('Annex'))), b=zi, offset='ares_ok')
    ocf = cx.fn('ent.comp.SiegeComponent.getOccupationActionCost')
    ocd = cx.code.types[ocf.type.value].definition
    ocn = fb.reg(ocd.args[2].value)
    fb.op('Null', dst=ocn)
    rq = fb.reg(cx.t('f64'))
    rneed, rau = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    rn, rown = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))  # pending Annexes / of them still owing their price
    fb.op('Mov', dst=rn, src=zi)
    fb.op('Mov', dst=rown, src=zi)

    def annex_cost(st, dst):
        """dst += sum of qty of st's Annex costs for us."""
        lbl = _uid('rc')
        sg = b.field(st, 'siege')
        fb.op('JNull', reg=sg, offset=lbl)
        arr = fb.reg(ocd.ret.value)
        fb.op('Call4', dst=arr, fun=ocf.findex.value, arg0=sg, arg1=1, arg2=ocn, arg3=fac)
        fb.op('JNull', reg=arr, offset=lbl)
        ck = fb.reg(cx.t('i32'))
        fb.op('Mov', dst=ck, src=zi)
        head = _uid('rcl')
        b.loop_head(head)
        fb.op('JSGte', a=ck, b=b.field(arr, 'length'), offset=lbl)
        qd = fb.get(b.call('hl.types.ArrayObj.getDyn', arr, ck), 'qty')
        fb.op('Incr', dst=ck)
        fb.op('JNull', reg=qd, offset=head)
        fb.op('SafeCast', dst=rq, src=qd)
        fb.op('Add', dst=dst, a=dst, b=rq)
        fb.op('JAlways', offset=head)
        fb.label(lbl)

    fb.op('Mov', dst=rneed, src=b.const('f64', 0))
    annex_cost(tgt, rneed)
    fb.op('Mov', dst=s_e, src=tgt)
    fb.op('Mov', dst=i, src=zi)
    b.loop_head('ro')
    fb.op('JSGte', a=i, b=n, offset='rjudge')
    ro = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, i), 'logic.ai.AIOrder')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=ro, offset='ro')
    fb.op('EnumIndex', dst=idx, value=b.field(ro, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='ro')
    rsa = b.cast(fb.get(ro, 'siegeAction'), 'String')
    fb.op('JNull', reg=rsa, offset='ro')
    fb.op('JNotEq', a=b.call('String.__compare', rsa, fb.dyn(fb.string('Annex'))), b=zi, offset='ro')
    rt = b.call('logic.ai.AIOrder.getTarget', ro)
    fb.op('JNull', reg=rt, offset='ro')
    fb.op('JEq', a=rt, b=s_e, offset='ro')
    rs = b.cast(fb.dyn(rt), 'ent.Structure')
    fb.op('JNull', reg=rs, offset='ro')
    fb.op('Mov', dst=near, src=rt)
    fb.op('Incr', dst=rn)
    fb.op('Add', dst=rneed, a=rneed, b=b.const('f64', ANNEX_RISE))
    rsg = b.field(rs, 'siege')
    fb.op('JNull', reg=rsg, offset='rowe')
    fb.op('JNotEq', a=b.field(rsg, 'besiegingFaction'), b=fac, offset='rowe')
    fb.op('JSGt', a=b.call('ent.comp.SiegeComponent.getOccupationActionProgress', rsg), b=b.const('f64', 0),
          offset='ro')  # capturing: paid
    fb.label('rowe')
    fb.op('Incr', dst=rown)
    annex_cost(rs, rneed)
    fb.op('JAlways', offset='ro')
    fb.label('rjudge')
    fb.op('JSLte', a=rn, b=zi, offset='ares_ok')
    fb.op('Call2', dst=rau, fun=cx.fn('ent.Faction.getResource').findex.value, arg0=fac,
          arg1=b.const('i32', RES_AUTHORITY))
    # never more than the stock can hold (Faction.getMaxResStock): Fremen sat at the 500 cap vs need 522 for 6 min
    # (68:03-73:32) and no Annex could ever launch
    # ... but only while no other Annex of ours still owes its price (rown 0): with one pending the cap let Fremen
    # launch Yekhelon (500) on top of Adriyah (177) at 497 Authority, then Odnin; Authority fell to 1 and the captures
    # stood waiting for it (user: only go for a capture with the Authority)
    fb.op('JSGt', a=rown, b=zi, offset='ares_cap')
    rmx = b.call('ent.Faction.getMaxResStock', fac, fb.string('Authority'))
    fb.op('JNull', reg=rmx, offset='ares_cap')
    rmf = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=rmf, src=rmx)
    fb.op('JSLte', a=rmf, b=b.const('f64', 0), offset='ares_cap')  # no cap known
    fb.op('JSLte', a=rneed, b=rmf, offset='ares_cap')
    fb.op('Mov', dst=rneed, src=rmf)
    fb.label('ares_cap')
    fb.op('JSGte', a=rau, b=rneed, offset='ares_ok')
    _throttle(fb, b, cx, 'ares', fac, 10, 'ares_nl')
    _log_ev(fb, b, cx, helpers, 'ares', [('f', fb.get(fac, 'kind')), ('tgt', s_e), ('au', rau), ('need', rneed),
                                         ('n', rn), ('owe', fb.dyn(rown)), ('near', near)])
    fb.label('ares_nl')
    fb.op('Mov', dst=why, src=fb.string('auth'))
    fb.op('Bool', dst=blocked, value=True)
    fb.op('JAlways', offset='done')
    fb.label('ares_ok')
    fb.op('Null', dst=near)

    # 3. annex-spacing
    fb.op('Mov', dst=s_e, src=tgt)
    fb.op('Mov', dst=i, src=zi)
    adj = b.const('f64', ADJ_R)
    b.loop_head('o')
    fb.op('JSGte', a=i, b=n, offset='done')
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, i), 'logic.ai.AIOrder')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=o, offset='o')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='o')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='o')
    fb.op('EnumIndex', dst=idx, value=tt)
    fb.op('JNotEq', a=idx, b=b.const('i32', T_STRUCT), offset='o')
    t = b.call('logic.ai.AIOrder.getTarget', o)
    fb.op('JNull', reg=t, offset='o')
    fb.op('JEq', a=t, b=s_e, offset='o')
    fb.op('JSGte', a=b.call('ent.Entity.getDistTo', t, s_e), b=adj, offset='o')
    fb.op('Mov', dst=near, src=t)
    fb.op('Bool', dst=blocked, value=True)
    fb.label('done')
    fb.end_try(guard)
    fb.op('JTrue', cond=blocked, offset='block')
    fb.op('Call4', dst=void, fun=orig.findex.value, arg0=0, arg1=1, arg2=tgt, arg3=3)
    # 4. peaceful annex fallback (Atreides' PeacefullyAnnex ability): an Annex whose army launch above created no order
    # on the target (NoAvailableArmy / NotEnoughArmies / ArmyNotStrongEnough: Atreides' affordable Annexes ended
    # NoAvailableArmy x25 / stuck x21 while its armies held the Nundad standoff) is done by the ability when it can be
    # used on the target and `_pannex_ok` passes (>= PANNEX_MIN_VILLAGES villages, Influence >= PANNEX_INF, target
    # >= PANNEX_HOPS zones from our main base). Armies first: they
    # annex for free, and peaceful-first spent the opening's scarce Influence while armies idled. Vanilla's own
    # peaceful check (ResourceManager) rarely fires. Log `pannex`. The gauge gets Success after vanilla's failure
    # result (Annex has no onFailure blocks); the Ret comes after the trap (a jump out of it leaves it installed).
    pdone = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=pdone, value=False)
    gpa = fb.try_()
    fb.op('JNotEq', a=b.call('String.__compare', 1, fb.dyn(fb.string('Annex'))), b=b.const('i32', 0), offset='pa_no')
    pfac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=pfac, offset='pa_no')
    pse = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=pse, src=tgt)
    _pannex_ok(fb, b, cx, pfac, pse, 'pa_no')  # villages, Influence, not next to our main base
    pinf = fb.reg(cx.t('f64'))
    fb.op('Call2', dst=pinf, fun=cx.fn('ent.Faction.getResource').findex.value, arg0=pfac, arg1=b.const('i32', RES_INFLUENCE))
    pords = b.field(b.field(b.field(0, 'controller'), 'aiOrders'), 'orders')
    fb.op('JNull', reg=pords, offset='pa_no')
    pk, pix = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=pk, src=b.field(pords, 'length'))
    b.loop_head('pa_o')
    fb.op('JSLte', a=pk, b=b.const('i32', 0), offset='pa_free')
    fb.op('Sub', dst=pk, a=pk, b=b.const('i32', 1))
    po = b.cast(b.call('hl.types.ArrayObj.getDyn', pords, pk), 'logic.ai.AIOrder')
    fb.op('JNull', reg=po, offset='pa_o')
    ptt = b.field(po, 'targetType')
    fb.op('JNull', reg=ptt, offset='pa_o')
    fb.op('EnumIndex', dst=pix, value=ptt)
    fb.op('JNotEq', a=pix, b=b.const('i32', T_STRUCT), offset='pa_o')
    fb.op('JEq', a=b.call('logic.ai.AIOrder.getTarget', po), b=pse, offset='pa_no')  # the armies went
    fb.op('JAlways', offset='pa_o')
    fb.label('pa_free')
    pabm = b.call('ent.Faction.get_abilities', pfac)
    fb.op('JNull', reg=pabm, offset='pa_no')
    cua = cx.fn('logic.faction.AbilityManager.canUseAbilityOn')
    cua_args = [a.value for a in cx.code.types[cua.type.value].definition.args]
    dt_t = cx.t('DisplayTarget')
    dt_names = [c.name.resolve(cx.code) for c in cx.code.types[dt_t].definition.constructs]
    pdt = fb.reg(dt_t)
    fb.op('MakeEnum', dst=pdt, construct=dt_names.index('Structure'), args=[tgt])
    pdo = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=pdo)
    fb.op('DynSet', obj=pdo, field=cx.s('src'), src=fb.dyn(pdt))
    fb.op('DynSet', obj=pdo, field=cx.s('struct'), src=fb.dyn(tgt))
    pva = fb.reg(cua_args[2])
    fb.op('ToVirtual', dst=pva, src=pdo)
    pn3, pn4 = fb.reg(cua_args[3]), fb.reg(cua_args[4])
    fb.op('Null', dst=pn3)
    fb.op('Null', dst=pn4)
    pab = fb.string('PeacefullyAnnex')
    pok = fb.reg(cx.t('bool'))
    fb.op('CallN', dst=pok, fun=cua.findex.value, args=[pabm, pab, pva, pn3, pn4])
    fb.op('JFalse', cond=pok, offset='pa_no')
    uao = cx.fn('logic.faction.AbilityManager.useAbilityOn')
    pres = fb.reg(cx.code.types[uao.type.value].definition.ret.value)
    fb.op('CallN', dst=pres, fun=uao.findex.value, args=[pabm, pab, pva, pn3, pn4])
    _log_ev(fb, b, cx, helpers, 'pannex', [('f', fb.get(pfac, 'kind')), ('tgt', pse), ('inf', pinf), ('r', fb.dyn(pres))])
    pend = cx.fn('logic.ai.AIMilitary.onActionEnd')
    prt = cx.code.types[pend.type.value].definition.args[2].value
    prn = [c.name.resolve(cx.code) for c in cx.code.types[prt].definition.constructs]
    preason = fb.reg(prt)
    fb.op('MakeEnum', dst=preason, construct=prn.index('Success'), args=[])  # the gauge is satisfied (x0)
    pgk = b.call('logic.ai.AIMilitary.getMilitaryGaugeKindFromSiegeActionKind', 0, 1)
    fb.op('Call4', dst=void, fun=pend.findex.value, arg0=0, arg1=pgk, arg2=preason, arg3=3)
    fb.op('Bool', dst=pdone, value=True)
    fb.label('pa_no')
    fb.end_try(gpa)
    fb.op('JFalse', cond=pdone, offset='pa_skip')
    fb.op('Ret', ret=void)  # done peacefully: no launch record, no stuck count
    fb.label('pa_skip')
    # remember the launch (retry, in the scoring wrapper) only when it created an order on the target: a pick that
    # ended NoAvailableArmy / NotEnoughArmies blocked every Atreides candidate for RETRY s and the gauge spun on
    # Invalid every ~1.5 s (00:17-00:46, 02:45-03:19)
    guard3 = fb.try_()
    s_e3 = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=s_e3, src=tgt)
    ords = b.field(b.field(b.field(0, 'controller'), 'aiOrders'), 'orders')
    fb.op('JNull', reg=ords, offset='rec_done')
    k3, ix3 = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k3, src=b.field(ords, 'length'))
    b.loop_head('rec')
    fb.op('JSLte', a=k3, b=b.const('i32', 0), offset='rec_none')
    fb.op('Sub', dst=k3, a=k3, b=b.const('i32', 1))
    o3 = b.cast(b.call('hl.types.ArrayObj.getDyn', ords, k3), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o3, offset='rec')
    tt3 = b.field(o3, 'targetType')
    fb.op('JNull', reg=tt3, offset='rec')
    fb.op('EnumIndex', dst=ix3, value=tt3)
    fb.op('JNotEq', a=ix3, b=b.const('i32', T_STRUCT), offset='rec')
    fb.op('JNotEq', a=b.call('logic.ai.AIOrder.getTarget', o3), b=s_e3, offset='rec')
    # block for the next relaunch: doubled (up to RETRY_MAX) when this launch came within block + RETRY of the last
    # one (it ended at once again: Smugglers' Liberation on Dam-Al'riyah, InsufficientSupply every 30-60 s for 10
    # min), else RETRY
    amap, bmap = _global_map(fb, b, cx, 'alaunch'), _global_map(fb, b, cx, 'ablk')
    now3, pl, pb = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=now3, src=b.field(_state(fb, b, cx), 'time'))
    fb.op('Mov', dst=pb, src=b.const('f64', RETRY))
    pbv = b.call('haxe.ds.ObjectMap.get', bmap, fb.dyn(s_e3))
    fb.op('JNull', reg=pbv, offset='blk0')
    fb.op('SafeCast', dst=pb, src=pbv)
    fb.label('blk0')
    # the last order on this target (map `aord`): ended before Regroup (cancelled in Waiting: InsufficientSupply)
    # -> double, however long ago; reached Regroup or later -> it lasted: RETRY. The gap alone reset the block
    # while every launch still died at once (Fremen Liberate of Hal-nit 31:38-37:37 x6, 550-850 away, block back to
    # RETRY after a 101 s gap; each launch also cancelled its armies' Resupply / Patrol)
    omap = _global_map(fb, b, cx, 'aord')
    pov = b.call('haxe.ds.ObjectMap.get', omap, fb.dyn(s_e3))
    fb.op('JNull', reg=pov, offset='blkgap')
    po = b.cast(pov, 'logic.ai.AIOrder')
    fb.op('JNull', reg=po, offset='blkgap')
    fb.op('JSLt', a=b.field(po, 'phase'), b=b.const('i32', REGROUP), offset='blkdbl')
    fb.op('JAlways', offset='blkr')
    fb.label('blkgap')
    plv = b.call('haxe.ds.ObjectMap.get', amap, fb.dyn(s_e3))
    fb.op('JNull', reg=plv, offset='blkr')
    fb.op('SafeCast', dst=pl, src=plv)
    fb.op('Sub', dst=pl, a=now3, b=pl)
    fb.op('Sub', dst=pl, a=pl, b=pb)
    fb.op('JSGte', a=pl, b=b.const('f64', RETRY), offset='blkr')
    fb.label('blkdbl')
    fb.op('Add', dst=pb, a=pb, b=pb)
    fb.op('JSLte', a=pb, b=b.const('f64', RETRY_MAX), offset='blks')
    fb.op('Mov', dst=pb, src=b.const('f64', RETRY_MAX))
    fb.op('JAlways', offset='blks')
    fb.label('blkr')
    fb.op('Mov', dst=pb, src=b.const('f64', RETRY))
    fb.label('blks')
    b.call('haxe.ds.ObjectMap.set', bmap, fb.dyn(s_e3), fb.dyn(pb))
    b.call('haxe.ds.ObjectMap.set', amap, fb.dyn(s_e3), fb.dyn(now3))
    b.call('haxe.ds.ObjectMap.set', omap, fb.dyn(s_e3), fb.dyn(o3))
    # the armies it set out with (map `aunits`: common._recent_launch's lost-siege memory counts the dead once it ends)
    ou3 = b.field(o3, 'units')
    fb.op('JNull', reg=ou3, offset='au_no')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'aunits'), fb.dyn(s_e3),
           fb.dyn(b.call('hl.types.ArrayObj.copy', ou3)))
    fb.label('au_no')
    # launched while a free Supply Drop was held (map `sdfree` within SD_FRESH: vanilla's supply check already ran
    # with sdrop-trip's lift): map `asd` target -> 1, so common._unreach doesn't waive the next block for the drop
    # (Fremen's 10-army Liberate of Tab-ras, 1018 away, died InsufficientSupply 5 times in 8 min with a drop held)
    asd = _global_map(fb, b, cx, 'asd')
    b.call('haxe.ds.ObjectMap.remove', asd, fb.dyn(s_e3))
    sdv3 = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'sdfree'),
                  fb.dyn(b.field(b.field(0, 'controller'), 'owner')))
    fb.op('JNull', reg=sdv3, offset='asd_w')
    sdq3 = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=sdq3, src=sdv3)
    fb.op('Sub', dst=sdq3, a=now3, b=sdq3)
    fb.op('JSLte', a=sdq3, b=b.const('f64', SD_FRESH), offset='asd_set')
    # ... or with a worm ride available (rules/ride.py map `wfree`): the same, for the ride's waiver
    fb.label('asd_w')
    _ride_free(fb, b, cx, b.field(b.field(0, 'controller'), 'owner'), now3, 'asd_no')
    fb.label('asd_set')
    b.call('haxe.ds.ObjectMap.set', asd, fb.dyn(s_e3), fb.dyn(now3))
    fb.label('asd_no')
    # an Annex on an uncontested ring village: count it (the ring hold ends after DD_TRIES: resistance)
    fb.op('JNotEq', a=b.call('String.__compare', 1, fb.dyn(fb.string('Annex'))), b=b.const('i32', 0), offset='rec_done')
    rz = b.call('ent.Entity.get_zone', s_e3)
    fb.op('JNull', reg=rz, offset='rec_done')
    rcl = fb.reg(cx.t('bool'))
    fb.op('Call2', dst=rcl, fun=helpers['ddhold'], arg0=b.field(b.field(0, 'controller'), 'owner'), arg1=rz)
    fb.op('JFalse', cond=rcl, offset='rec_done')
    tmap = _global_map(fb, b, cx, 'dtries')
    tq = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=tq, src=b.const('f64', 0))
    tv = b.call('haxe.ds.ObjectMap.get', tmap, fb.dyn(s_e3))
    fb.op('JNull', reg=tv, offset='rec_t0')
    fb.op('SafeCast', dst=tq, src=tv)
    fb.label('rec_t0')
    fb.op('Add', dst=tq, a=tq, b=b.const('f64', 1))
    b.call('haxe.ds.ObjectMap.set', tmap, fb.dyn(s_e3), fb.dyn(tq))
    fb.op('JAlways', offset='rec_done')
    # no order (NotEnoughArmies, ArmyNotStrongEnough, ...) with an army free: a tension partner we can't take loses
    # interest, x TEN_FAIL for every village of ours rubbing it (the gate lift would otherwise keep the gauge on it; it rebuilds by contact)
    fb.label('rec_none')
    # stuck: FAIL_N orderless launches on one target within FAIL_WIN (ArmyNotStrongEnough, NotEnoughArmies, ...) ->
    # dropped from the target scores for FAIL_BLOCK s, doubled up to FAIL_MAX when it comes back to the same loop
    # (Fremen's 10 armies sat at Ars-bu while the gauges re-picked Harkonnen's Aliftah every ~25 s, 183 picks on
    # Ars-bu before that: no order, so the retry block never applied)
    # ... counted only when we had an army to send (non-harvester, in no Military order): wiped or all busy is
    # NoAvailableArmy, not this target's fault (new spawns must find every target open; no tension drop either)
    ffac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=ffac, offset='rec_done')
    # ... nor when vanilla's idle list for this launch was empty (map `sidle`, set by the pick-life getUnits wrapper:
    # NoAvailableArmy): every faction's first target was blocked 120 s at 00:14, the opening Annexes waited to 02:14
    # ... nor when that list held only a few of our free armies (NotEnoughArmies with 1 idle while the rest spawned /
    # walked out at match start: Atreides Aeg-mur, Harkonnen Marron, Smugglers Lar-nit, each blocked 120 s from 00:23,
    # first Annexes at 02:18-02:37 vs Fremen's 00:15). The target is at fault only when vanilla could offer at least
    # STUCK_IDLE x our free armies and still found too few; fsn -1 = list size unknown (old rule: any free army)
    fsv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'sidle'), fb.dyn(ffac))
    fsn = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=fsn, src=b.const('i32', -1))
    fb.op('JNull', reg=fsv, offset='fsidl')
    fb.op('SafeCast', dst=fsn, src=fsv)
    fb.op('JSLte', a=fsn, b=b.const('i32', 0), offset='rec_done')
    fb.label('fsidl')
    fnf = fb.reg(cx.t('i32'))  # our free armies (non-harvester, in no Military order)
    fb.op('Mov', dst=fnf, src=b.const('i32', 0))
    farr, falen = _my_armies(fb, b, ffac, 'rec_done')
    fi, fk, fix = fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fa = _army_loop(fb, b, farr, falen, fi, 'fav', 'fcnt_d')
    fb.op('JNotNull', reg=b.field(fa, 'harvestComponent'), offset='fav')
    fb.op('Mov', dst=fk, src=b.field(ords, 'length'))
    b.loop_head('fao')
    fb.op('JSLte', a=fk, b=b.const('i32', 0), offset='fhave_one')  # free: count it
    fb.op('Sub', dst=fk, a=fk, b=b.const('i32', 1))
    fo = b.cast(b.call('hl.types.ArrayObj.getDyn', ords, fk), 'logic.ai.AIOrder')
    fb.op('JNull', reg=fo, offset='fao')
    fb.op('EnumIndex', dst=fix, value=b.field(fo, 'type'))
    fb.op('JNotEq', a=fix, b=b.const('i32', MILITARY), offset='fao')
    fou = b.field(fo, 'units')
    fb.op('JNull', reg=fou, offset='fao')
    fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', fou, fb.dyn(fa)), offset='fav')  # busy
    fb.op('JAlways', offset='fao')
    fb.label('fhave_one')
    fb.op('Incr', dst=fnf)
    fb.op('JAlways', offset='fav')
    fb.label('fcnt_d')
    fb.op('JSLte', a=fnf, b=b.const('i32', 0), offset='rec_done')  # none free: wiped or all busy
    fb.op('JSLt', a=fsn, b=b.const('i32', 0), offset='fhave')  # list size unknown
    fsh, fnh = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=fsh, src=fsn)
    fb.op('ToSFloat', dst=fnh, src=fnf)
    fb.op('Mul', dst=fnh, a=fnh, b=_ratio(fb, b, STUCK_IDLE))
    fb.op('JSLt', a=fsh, b=fnh, offset='rec_done')  # vanilla saw too few of them: not this target's fault
    fb.label('fhave')
    # ... nor when we can't pay for it now (MissingResources: vanilla reserves and waits; Smugglers' Fafir got stuck
    # blocks for 2-8 min while Authority came in)
    ocf = cx.fn('ent.comp.SiegeComponent.getOccupationActionCost')
    ocat = [a.value for a in cx.code.types[ocf.type.value].definition.args]
    ocn = fb.reg(ocat[2])
    fb.op('Null', dst=ocn)
    fsg = b.field(b.cast(fb.dyn(s_e3), 'ent.Structure'), 'siege')
    fb.op('JNull', reg=fsg, offset='faff')
    fcost = fb.reg(cx.code.types[ocf.type.value].definition.ret.value)
    fb.op('Call4', dst=fcost, fun=ocf.findex.value, arg0=fsg, arg1=1, arg2=ocn, arg3=ffac)
    fb.op('JNull', reg=fcost, offset='faff')
    fctl = b.field(ffac, 'aiController')
    fb.op('JNull', reg=fctl, offset='faff')
    fmiss = b.call('logic.ai.AIController.getMissingResources', fctl, fcost, fb.dyn(b.const('i32', 3)))
    fb.op('JNull', reg=fmiss, offset='faff')
    fb.op('JSGt', a=b.field(fmiss, 'length'), b=b.const('i32', 0), offset='rec_done')
    fb.label('faff')
    fcm, ftm, fum, fbm = (_global_map(fb, b, cx, n) for n in ('afc', 'aft', 'afu', 'afb'))
    fnow, fq, fc, fbk = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('Mov', dst=fnow, src=b.field(_state(fb, b, cx), 'time'))
    fb.op('Mov', dst=fc, src=b.const('f64', 1))
    ftv = b.call('haxe.ds.ObjectMap.get', ftm, fb.dyn(s_e3))
    fb.op('JNull', reg=ftv, offset='fnew')
    fb.op('SafeCast', dst=fq, src=ftv)
    fb.op('Sub', dst=fq, a=fnow, b=fq)
    fb.op('JSGt', a=fq, b=b.const('f64', FAIL_WIN), offset='fnew')
    fb.op('SafeCast', dst=fc, src=b.call('haxe.ds.ObjectMap.get', fcm, fb.dyn(s_e3)))
    fb.op('Add', dst=fc, a=fc, b=b.const('f64', 1))
    fb.op('JAlways', offset='fcnt')
    fb.label('fnew')
    b.call('haxe.ds.ObjectMap.set', ftm, fb.dyn(s_e3), fb.dyn(fnow))
    fb.label('fcnt')
    b.call('haxe.ds.ObjectMap.set', fcm, fb.dyn(s_e3), fb.dyn(fc))
    fb.op('JSLt', a=fc, b=b.const('f64', FAIL_N), offset='fdone')
    # block: FAIL_BLOCK, doubled when the last block ended less than FAIL_WIN ago
    fb.op('Mov', dst=fbk, src=b.const('f64', FAIL_BLOCK))
    fuv = b.call('haxe.ds.ObjectMap.get', fum, fb.dyn(s_e3))
    fb.op('JNull', reg=fuv, offset='fset')
    fb.op('SafeCast', dst=fq, src=fuv)
    fb.op('Sub', dst=fq, a=fnow, b=fq)
    fb.op('JSGt', a=fq, b=b.const('f64', FAIL_WIN), offset='fset')
    fb.op('SafeCast', dst=fbk, src=b.call('haxe.ds.ObjectMap.get', fbm, fb.dyn(s_e3)))
    fb.op('Add', dst=fbk, a=fbk, b=fbk)
    fb.op('JSLte', a=fbk, b=b.const('f64', FAIL_MAX), offset='fset')
    fb.op('Mov', dst=fbk, src=b.const('f64', FAIL_MAX))
    fb.label('fset')
    b.call('haxe.ds.ObjectMap.set', fbm, fb.dyn(s_e3), fb.dyn(fbk))
    fb.op('Add', dst=fq, a=fnow, b=fbk)
    b.call('haxe.ds.ObjectMap.set', fum, fb.dyn(s_e3), fb.dyn(fq))
    b.call('haxe.ds.ObjectMap.remove', ftm, fb.dyn(s_e3))
    b.call('haxe.ds.ObjectMap.remove', fcm, fb.dyn(s_e3))
    fb.label('fdone')
    tfac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=tfac, offset='rec_done')
    tmine = b.cast(fb.get(tfac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=tmine, offset='rec_done')
    tenw3, tenv3 = _global_map(fb, b, cx, 'tenw'), _global_map(fb, b, cx, 'tenv')
    ti3 = fb.reg(cx.t('i32'))
    tq3 = fb.reg(cx.t('f64'))
    tve = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ti3, src=b.const('i32', 0))
    b.loop_head('rtn')
    fb.op('JSGte', a=ti3, b=b.field(tmine, 'length'), offset='rec_done')
    tsv = b.call('hl.types.ArrayObj.getDyn', tmine, ti3)
    fb.op('Incr', dst=ti3)
    fb.op('JNull', reg=tsv, offset='rtn')
    fb.op('JNotEq', a=b.call('haxe.ds.ObjectMap.get', tenw3, tsv), b=fb.dyn(s_e3), offset='rtn')
    ttv = b.call('haxe.ds.ObjectMap.get', tenv3, tsv)
    fb.op('JNull', reg=ttv, offset='rtn')
    fb.op('SafeCast', dst=tq3, src=ttv)
    fb.op('Mul', dst=tq3, a=tq3, b=_ratio(fb, b, TEN_FAIL))
    b.call('haxe.ds.ObjectMap.set', tenv3, tsv, fb.dyn(tq3))
    fb.op('Mov', dst=tve, src=b.cast(tsv, 'ent.Entity'))
    _log_ev(fb, b, cx, helpers, 'tdrop', [('f', fb.get(tfac, 'kind')), ('k', 1), ('v', tve), ('w', s_e3),
                                          ('T%', tq3)])
    fb.op('JAlways', offset='rtn')
    fb.label('rec_done')
    fb.end_try(guard3)
    fb.op('Ret', ret=void)
    fb.label('block')
    guard2 = fb.try_()
    owner = b.field(b.field(0, 'controller'), 'owner')
    _throttle(fb, b, cx, 'space', owner, 10, 'nolog')  # the gauge retries often while refused
    fb.op('Mov', dst=s_e, src=tgt)
    _log_ev(fb, b, cx, helpers, 'space', [('f', fb.get(owner, 'kind')), ('k', 1), ('why', why), ('tgt', s_e),
                                          ('near', near)])  # k = reg 1, the siege action kind (String)
    fb.label('nolog')
    fb.end_try(guard2)
    gk = b.call('logic.ai.AIMilitary.getMilitaryGaugeKindFromSiegeActionKind', 0, 1)
    end = cx.fn('logic.ai.AIMilitary.onActionEnd')
    rt = cx.code.types[end.type.value].definition.args[2].value
    names = [c.name.resolve(cx.code) for c in cx.code.types[rt].definition.constructs]
    reason = fb.reg(rt)
    fb.op('MakeEnum', dst=reason, construct=names.index('Dismiss'), args=[])  # impactNeeds: no gauge decay
    fb.op('JFalse', cond=decay, offset='endact')
    fb.op('MakeEnum', dst=reason, construct=names.index('Skip'), args=[])  # x0.85, no onFailure blocks
    fb.label('endact')
    fb.op('Call4', dst=void, fun=end.findex.value, arg0=0, arg1=gk, arg2=reason, arg3=3)
    fb.op('Ret', ret=void)
    w = fb.build()
    caller = cx.fn('logic.ai.AIMilitary.tryAction')
    sites = [op for op in caller.ops if op.df.get('fun') is not None and op.df['fun'].value == orig.findex.value]
    if len(sites) != 1:
        raise ValueError(f'annex-spacing: expected 1 tryArmyAction call in tryAction, found {len(sites)}')
    sites[0].df['fun'].value = w
    return w


def fix_busy_siege(cx):
    """Vanilla null access hit by hunts (it aborts the faction's checkUnits every tick, freezing its armies).
    getUnits' busy filter (closure (ctx, AIOrder) -> Bool, f40983 in hlboot) reads target-as-Structure .siege.isUnderSiege
    for every Military order in phase 5 (Action); a Group target gives null. In place, same size: `NullCheck s` ->
    `JNull s -> <the type check's skip target>`, so non-structure Military orders fall through to the priority check."""
    from crashlink.core import Opcode
    from crashlink.opcodes import opcodes
    f = cx.fn('logic.ai.AIUnits.getUnits')
    order_t, struct_t = cx.t('logic.ai.AIOrder'), cx.t('ent.Structure')
    hits = []
    for op in f.ops:
        if op.op not in ('InstanceClosure', 'Closure'):
            continue
        tgt = next(g for g in cx.code.functions if g.findex.value == op.df['fun'].value)
        ft = cx.code.types[tgt.type.value].definition
        if [a.value for a in ft.args][1:] == [order_t] and ft.ret.value == cx.t('bool'):
            hits.append(tgt)
    if len({t.findex.value for t in hits}) != 1:
        raise ValueError(f'busy-siege: expected one (ctx, AIOrder) -> Bool closure in getUnits, found {len(hits)}')
    g = hits[0]
    ops = g.ops
    for i in range(1, len(ops) - 1):
        a, n, p = ops[i], ops[i + 1], ops[i - 1]
        if (a.op == 'NullCheck' and n.op == 'Field' and n.df['obj'].value == a.df['reg'].value
                and g.regs[a.df['reg'].value].value == struct_t
                and field_name_t(cx, struct_t, n.df['field'].value) == 'siege'
                and p.op == 'JNotEq'):
            skip = i - 1 + 1 + p.df['offset'].value  # where the `type == Military` test jumps when false
            j = Opcode('JNull', {})
            for fld, typ in opcodes['JNull'].items():
                j.df[fld] = Opcode.TYPE_MAP[typ]()
            j.df['reg'].value = a.df['reg'].value
            j.df['offset'].value = skip - (i + 1)
            ops[i] = j
            return {'busy-siege': f'f{g.findex.value} op{i} NullCheck -> JNull +{skip - i - 1}'}
    raise ValueError('busy-siege: NullCheck s; Field s.siege after the Military test not found')


def build_wind_fallback(cx, helpers, new_ids):
    """Wind filter off: vanilla getSiegeableVillages (considerWater, once one of our zones has a SpiceArea, our Water
    goal unmet (ResourceManager.compareGoals < 0) and we own > 1 structure) keeps only candidates whose zone
    windForce >= valueCache[1185] AI_WindTrap_MinimumWind 4 (NoStructuresWithSufficientWind when none is left). It
    deadlocked Fremen on low-wind maps (no Annex 6:00-11:11) and, while windy villages existed, hid the rest from
    our Annex value (user: our scoring picks the good candidates): Fremen annexed windy Eyur 42:50 while neutral,
    unguarded Alifdad, closing their deep-desert ring, never was a candidate. Every call site (vanilla and ours, one
    measure) goes through this wrapper: considerWater is cleared for the call and restored after (the original call
    outside any trap). Logs `wind` (f, k) once per faction per 60 s when the filter was asked for."""
    orig = cx.fn('logic.ai.$AIMilitary.getSiegeableVillages')
    oid = orig.findex.value
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    ret_t = ft.ret.value
    vfields = [f.name.resolve(cx.code) for f in cx.code.types[args[3]].definition.fields]
    if 'considerWater' not in vfields:
        raise ValueError('wind-fallback: args.considerWater not found')
    wfi = vfields.index('considerWater')
    fb = FB(cx, args, ret_t, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(ret_t)
    old = fb.reg(cx.t('bool'))
    fb.op('JNull', reg=3, offset='plain')
    fb.op('Field', dst=old, obj=3, field=wfi)
    fb.op('JFalse', cond=old, offset='plain')
    off = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=off, value=False)
    fb.op('SetField', obj=3, field=wfi, src=off)
    fb.op('Call4', dst=res, fun=oid, arg0=0, arg1=1, arg2=2, arg3=3)
    fb.op('SetField', obj=3, field=wfi, src=old)
    g = fb.try_()
    fb.op('JNull', reg=2, offset='wl')
    _throttle(fb, b, cx, 'wind', 2, 60, 'wl')
    _log_ev(fb, b, cx, helpers, 'wind', [('f', fb.get(2, 'kind')), ('k', 1)])
    fb.label('wl')
    fb.end_try(g)
    fb.op('Ret', ret=res)
    fb.label('plain')
    fb.op('Call4', dst=res, fun=oid, arg0=0, arg1=1, arg2=2, arg3=3)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    n = 0
    for f in cx.code.functions:
        if f.findex.value == w:
            continue
        for op in f.ops:
            if op.op.startswith('Call') and op.df.get('fun') is not None and op.df['fun'].value == oid:
                op.df['fun'].value = w
                n += 1
    if n < 1:
        raise ValueError('wind-fallback: no getSiegeableVillages call site')
    return {'wind-fallback': n}
