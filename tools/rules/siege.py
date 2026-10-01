"""Vanilla siege and order inputs: turret/third-party-aware power reports, bunker target score, siege launch gate
(defend / bunker / annex-spacing), discovery gate, busy-siege null fix."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def build_turret_stats(cx, cover, silence, threat_stats, new_ids):
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
    fb.op('Call4', dst=res, fun=orig.findex.value, arg0=0, arg1=1, arg2=2, arg3=3)
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


def _recent_launch(fb, b, cx, s_e, t, recent):
    """Jump to `recent` if vanilla launched a siege on s_e less than RETRY s ago (map 'alaunch', set by the
    tryArmyAction wrapper)."""
    last = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'alaunch'), fb.dyn(s_e))
    old = _uid('old')
    fb.op('JNull', reg=last, offset=old)
    lf = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=lf, src=last)
    fb.op('Sub', dst=lf, a=t, b=lf)
    fb.op('JSLt', a=lf, b=b.const('f64', RETRY), offset=recent)
    fb.label(old)


def build_ddclean(cx, strict=False):
    """aimod_ddclean(fac, zone) -> true when fac can gain deep deserts by surrounding them (attribute DD_ATB, or kind
    Fremen before it) and the zone borders an unowned deep desert that is an uncontested ring in progress: one of its
    neighbours is already ours, no other faction's main-base zone borders it, and every neighbour with a village
    still missing (the zone itself excluded) is neutral and farther than DD_BASE_R from other factions' main bases.
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


def _annex_value(fb, b, cx, helpers, res, mine, mn):
    """Annex only (k = arg 2): value per cost on top of vanilla's score (closure f40995: -10 / zone of distance,
    resource fields in the zone (SpiceArea 40, others 10), region aiWeight (specials 20, Pole 40), main-base
    proximity x Outpost_DistanceCost_MRatio, owned neighbours x 10, +100 for a spice village while we own none; no
    annex cost at all, and tryAction then reserves Authority and waits when the pick is unaffordable). For each
    positive score: + ANNEX_SPECIAL in a special region; SPICE_ANY factions lose vanilla's first-spice +100;
    factions with distance annex costs x the NEAR_W compactness factor (distance to our nearest structure on our
    land); x cmin / cost (real Authority cost: siege.getOccupationActionCost("Annex"), cmin = cheapest candidate:
    a village costing 2 cheap ones counts half); a spice village while we own none x ANNEX_SPICE1 (not SPICE_ANY);
    Fremen deep desert (Zone.updateOwner: a deep desert goes to the single owner of every neighbour with a village
    or main base, if it has DeepDesert_Surounded_GainControl): x (1 + w x min(DD_CAP, sum over unowned deep
    deserts next to the candidate of chance / (1 + neighbours still missing after it))), w = DD_W with the
    attribute, DD_W_PRE for Fremen before it; chance x DD_ENEMY per missing neighbour owned by another faction and
    per one within DD_BASE_R of another faction's main base; 0 when another faction's main base zone borders it;
    x DD_LINK when the candidate borders none of our non-deep-desert zones (reaching it means crossing desert).
    floor ANNEX_FLOOR. Ring hold (same factions): a candidate next to an unowned deep desert is a ring village (map
    'dring' -> now); when a candidate is on an uncontested ring in progress (aimod_ddhold) with fewer than DD_TRIES
    Annex launches (map 'dtries', counted by the launch gate), or one of our armies runs an Annex order on such a
    village, every candidate that isn't a ring village is dropped (Fremen Adur: the spice village was annexed while
    the ring around the uncontested desert was open; dropped, raid pillages it instead). Logs `ascore` (ASCORE_T per
    faction): tgt = our best, s, c (its cost), cmin, vb = vanilla's best (before this), v0 its vanilla score, vs =
    its score now, n candidates, hold = candidates dropped by the ring hold (never the director's pressed village)."""
    fac = 1
    fb.op('JNotEq', a=b.call('String.__compare', 2, fb.dyn(fb.string('Annex'))), b=b.const('i32', 0), offset='end')
    n = b.field(0, 'length')
    zero, big = b.const('f64', 0), b.const('f64', 1 << 30)
    zi = b.const('i32', 0)
    i, j = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    sc, c, cmin, q, d, dm, aw, v0 = (fb.reg(cx.t('f64')) for _ in range(8))
    se, te = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    annex = fb.string('Annex')
    gav = cx.fn('ent.Object.getAtbVal')
    gat = [a.value for a in cx.code.types[gav.type.value].definition.args]
    gref, gfac = fb.reg(gat[2]), fb.reg(gat[3])
    fb.op('Null', dst=gref)
    fb.op('Null', dst=gfac)
    gobj = fb.reg(gat[0])
    fb.op('Mov', dst=gobj, src=fac)
    dcr = fb.reg(cx.t('f64'))
    fb.op('Call4', dst=dcr, fun=gav.findex.value, arg0=gobj, arg1=b.const('i32', 952), arg2=gref, arg3=gfac)
    # SPICE_ANY faction? first spice village owned?
    exempt = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=exempt, value=False)
    kd = b.field(fac, 'kind')
    fb.op('JNull', reg=kd, offset='an_kd')
    for nm in SPICE_ANY:
        lbl = _uid('sx')
        fb.op('JNotEq', a=b.call('String.__compare', kd, fb.dyn(fb.string(nm))), b=zi, offset=lbl)
        fb.op('Bool', dst=exempt, value=True)
        fb.label(lbl)
    fb.label('an_kd')
    nsp = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=nsp, src=b.const('i32', 1))
    nsd = fb.get(fac, 'cacheData', 'numSpiceVillages')
    fb.op('JNull', reg=nsd, offset='an_nsp')
    fb.op('SafeCast', dst=nsp, src=nsd)
    fb.label('an_nsp')
    # Fremen deep desert weight: DD_W with DeepDesert_Surounded_GainControl, DD_W_PRE for Fremen before it
    ddw, dd, con, miss, bdd = (fb.reg(cx.t('f64')) for _ in range(5))
    fb.op('Mov', dst=ddw, src=zero)
    fb.op('Mov', dst=dd, src=zero)
    fb.op('Mov', dst=bdd, src=zero)
    one_f, den = _ratio(fb, b, 1), _ratio(fb, b, DD_ENEMY)
    k1, k2, k3, k4 = (fb.reg(cx.t('i32')) for _ in range(4))
    hm = fb.reg(cx.t('bool'))
    hmb = cx.fn('ent.Zone.hasMainBase')
    hnull = fb.reg(cx.code.types[hmb.type.value].definition.args[1].value)
    fb.op('Null', dst=hnull)
    ddc = helpers['ddhold']
    now = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=now, src=b.field(_state(fb, b, cx), 'time'))
    dring, dtries = _global_map(fb, b, cx, 'dring'), _global_map(fb, b, cx, 'dtries')
    hold, isr, cln = fb.reg(cx.t('bool')), fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('Bool', dst=hold, value=False)
    nh = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=nh, src=b.const('i32', 0))
    brest = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=brest)
    brs, brc, brdd, trq = (fb.reg(cx.t('f64')) for _ in range(4))
    for r in (brs, brc, brdd):
        fb.op('Mov', dst=r, src=b.const('f64', 0))
    has = cx.fn('ent.Object.hasAttribute')
    hat = [a.value for a in cx.code.types[has.type.value].definition.args]
    href, hfac = fb.reg(hat[2]), fb.reg(hat[3])
    fb.op('Null', dst=href)
    fb.op('Null', dst=hfac)
    hres = fb.reg(cx.t('bool'))
    fb.op('Call4', dst=hres, fun=has.findex.value, arg0=gobj, arg1=b.const('i32', DD_ATB), arg2=href, arg3=hfac)
    fb.op('JFalse', cond=hres, offset='an_dpre')
    fb.op('Mov', dst=ddw, src=_ratio(fb, b, DD_W))
    fb.op('JAlways', offset='an_dw')
    fb.label('an_dpre')
    fb.op('JNull', reg=kd, offset='an_dw')
    fb.op('JNotEq', a=b.call('String.__compare', kd, fb.dyn(fb.string('Fremen'))), b=zi, offset='an_dw')
    fb.op('Mov', dst=ddw, src=_ratio(fb, b, DD_W_PRE))
    fb.label('an_dw')
    facs = b.cast(fb.get(_state(fb, b, cx), 'factions', 'array'), 'hl.types.ArrayObj')
    oc = cx.fn('ent.comp.SiegeComponent.getOccupationActionCost')
    oat = [a.value for a in cx.code.types[oc.type.value].definition.args]
    onull = fb.reg(oat[2])
    fb.op('Null', dst=onull)

    def cost_of(st, dst):
        """dst = sum of qty of st's Annex costs for us (0 if unknown)."""
        lbl = _uid('co')
        fb.op('Mov', dst=dst, src=zero)
        sg = b.field(st, 'siege')
        fb.op('JNull', reg=sg, offset=lbl)
        arr = fb.reg(cx.code.types[oc.type.value].definition.ret.value)
        fb.op('Call4', dst=arr, fun=oc.findex.value, arg0=sg, arg1=annex, arg2=onull, arg3=fac)
        fb.op('JNull', reg=arr, offset=lbl)
        k = fb.reg(cx.t('i32'))
        fb.op('Mov', dst=k, src=zi)
        head = _uid('cl')
        b.loop_head(head)
        fb.op('JSGte', a=k, b=b.field(arr, 'length'), offset=lbl)
        qd = fb.get(b.call('hl.types.ArrayObj.getDyn', arr, k), 'qty')
        fb.op('Incr', dst=k)
        fb.op('JNull', reg=qd, offset=head)
        fb.op('SafeCast', dst=q, src=qd)
        fb.op('Add', dst=dst, a=dst, b=q)
        fb.op('JAlways', offset=head)
        fb.label(lbl)

    # pass 1: cheapest candidate cost, vanilla's best
    vb = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=vb)
    fb.op('Mov', dst=v0, src=zero)
    fb.op('Mov', dst=cmin, src=big)
    fb.op('Mov', dst=i, src=zi)
    b.loop_head('an1')
    fb.op('JSGte', a=i, b=n, offset='an1d')
    s = b.cast(b.call('hl.types.ArrayObj.getDyn', 0, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=s, offset='an1')
    fb.op('Mov', dst=se, src=s)
    v = b.call('haxe.ds.ObjectMap.get', res, fb.dyn(se))
    fb.op('JNull', reg=v, offset='an1')
    fb.op('SafeCast', dst=sc, src=v)
    fb.op('JSLte', a=sc, b=zero, offset='an1')
    fb.op('JSLte', a=sc, b=v0, offset='an1c')
    fb.op('Mov', dst=v0, src=sc)
    fb.op('Mov', dst=vb, src=se)
    fb.label('an1c')
    cost_of(s, c)
    fb.op('JSLte', a=c, b=zero, offset='an1')
    fb.op('JSGte', a=c, b=cmin, offset='an1')
    fb.op('Mov', dst=cmin, src=c)
    fb.op('JAlways', offset='an1')
    fb.label('an1d')
    # pass 2: rescore
    best = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=best)
    bs, bc = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=bs, src=zero)
    fb.op('Mov', dst=bc, src=zero)
    hs = fb.reg(cx.t('bool'))
    fb.op('Mov', dst=i, src=zi)
    b.loop_head('an2')
    fb.op('JSGte', a=i, b=n, offset='an2d')
    s2 = b.cast(b.call('hl.types.ArrayObj.getDyn', 0, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=s2, offset='an2')
    fb.op('Mov', dst=se, src=s2)
    v2 = b.call('haxe.ds.ObjectMap.get', res, fb.dyn(se))
    fb.op('JNull', reg=v2, offset='an2')
    fb.op('SafeCast', dst=sc, src=v2)
    fb.op('JSLte', a=sc, b=zero, offset='an2')
    z = b.call('ent.Entity.get_zone', se)
    fb.op('JNull', reg=z, offset='an2')
    # special region
    awd = fb.get(z, 'inf', 'props', 'aiWeight')
    fb.op('JNull', reg=awd, offset='an_nsx')
    fb.op('SafeCast', dst=aw, src=awd)
    fb.op('JSLt', a=aw, b=b.const('f64', 20), offset='an_nsx')
    fb.op('Add', dst=sc, a=sc, b=b.const('f64', ANNEX_SPECIAL))
    fb.label('an_nsx')
    # first spice village: SPICE_ANY factions lose vanilla's +100
    fb.op('Mov', dst=hs, src=b.call('ent.Zone.hasSpice', z))
    fb.op('JFalse', cond=hs, offset='an_nsp1')
    fb.op('JSGte', a=nsp, b=b.const('i32', 1), offset='an_nsp1')
    fb.op('JFalse', cond=exempt, offset='an_nsp1')
    fb.op('Sub', dst=sc, a=sc, b=b.const('f64', 100))
    fb.label('an_nsp1')
    # compactness (factions with distance annex costs)
    fb.op('JSLte', a=dcr, b=zero, offset='an_near')
    fb.op('Mov', dst=dm, src=big)
    fb.op('Mov', dst=j, src=zi)
    b.loop_head('an_m')
    fb.op('JSGte', a=j, b=mn, offset='an_md')
    t = b.cast(b.call('hl.types.ArrayObj.getDyn', mine, j), 'ent.Structure')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=t, offset='an_m')
    fb.op('Mov', dst=te, src=t)
    tz = b.call('ent.Entity.get_zone', te)
    fb.op('JNull', reg=tz, offset='an_m')
    fb.op('JNotEq', a=b.field(tz, 'owner'), b=fac, offset='an_m')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', se, te))
    fb.op('JSGte', a=d, b=dm, offset='an_m')
    fb.op('Mov', dst=dm, src=d)
    fb.op('JAlways', offset='an_m')
    fb.label('an_md')
    fb.op('JSGte', a=dm, b=big, offset='an_near')
    ref = b.const('f64', NEAR_REF)
    fb.op('Sub', dst=q, a=ref, b=dm)
    fb.op('SDiv', dst=q, a=q, b=ref)
    fb.op('Mul', dst=q, a=q, b=_ratio(fb, b, NEAR_W))
    lo, hi = _ratio(fb, b, -NEAR_W), _ratio(fb, b, NEAR_W)
    fb.op('JSGte', a=q, b=lo, offset='an_lo')
    fb.op('Mov', dst=q, src=lo)
    fb.label('an_lo')
    fb.op('JSLte', a=q, b=hi, offset='an_hi')
    fb.op('Mov', dst=q, src=hi)
    fb.label('an_hi')
    fb.op('Add', dst=q, a=q, b=_ratio(fb, b, 1))
    fb.op('Mul', dst=sc, a=sc, b=q)
    fb.label('an_near')
    # value per cost
    fb.op('Mov', dst=c, src=zero)
    fb.op('JSGte', a=cmin, b=big, offset='an_nc')
    cost_of(s2, c)
    fb.op('JSLte', a=c, b=zero, offset='an_nc')
    fb.op('Mul', dst=sc, a=sc, b=cmin)
    fb.op('SDiv', dst=sc, a=sc, b=c)
    fb.label('an_nc')
    # opening: a spice field first
    fb.op('JFalse', cond=hs, offset='an_s1')
    fb.op('JSGte', a=nsp, b=b.const('i32', 1), offset='an_s1')
    fb.op('JTrue', cond=exempt, offset='an_s1')
    fb.op('Mul', dst=sc, a=sc, b=b.const('f64', ANNEX_SPICE1))
    fb.label('an_s1')
    # Fremen deep desert: surround it (all neighbours with a village / main base ours -> Zone.updateOwner gives it)
    fb.op('Bool', dst=isr, value=False)
    fb.op('JSLte', a=ddw, b=zero, offset='an_dd')
    fb.op('Mov', dst=dd, src=zero)
    zn = b.field(z, 'neighbors')
    fb.op('JNull', reg=zn, offset='an_ddx')
    fb.op('Mov', dst=k1, src=zi)
    b.loop_head('an_d')
    fb.op('JSGte', a=k1, b=b.field(zn, 'length'), offset='an_ddx')
    dz = b.cast(b.call('hl.types.ArrayObj.getDyn', zn, k1), 'ent.Zone')
    fb.op('Incr', dst=k1)
    fb.op('JNull', reg=dz, offset='an_d')
    fb.op('JFalse', cond=b.call('ent.Zone.isDeepDesert', dz), offset='an_d')
    fb.op('JEq', a=b.field(dz, 'owner'), b=fac, offset='an_d')
    fb.op('Mov', dst=con, src=_ratio(fb, b, 1))
    fb.op('Mov', dst=miss, src=zero)
    dn = b.field(dz, 'neighbors')
    fb.op('JNull', reg=dn, offset='an_d')
    fb.op('Mov', dst=k2, src=zi)
    b.loop_head('an_e')
    fb.op('JSGte', a=k2, b=b.field(dn, 'length'), offset='an_ed')
    mz = b.cast(b.call('hl.types.ArrayObj.getDyn', dn, k2), 'ent.Zone')
    fb.op('Incr', dst=k2)
    fb.op('JNull', reg=mz, offset='an_e')
    fb.op('JEq', a=mz, b=z, offset='an_e')  # the candidate itself
    mo = b.field(mz, 'owner')
    fb.op('JEq', a=mo, b=fac, offset='an_e')
    fb.op('Call2', dst=hm, fun=hmb.findex.value, arg0=mz, arg1=hnull)
    fb.op('JTrue', cond=hm, offset='an_d')  # another faction's main base borders it: never ours
    mv = b.call('ent.Zone.getVillage', mz)
    fb.op('JNull', reg=mv, offset='an_e')  # no village: not counted by updateOwner
    fb.op('Add', dst=miss, a=miss, b=one_f)
    fb.op('JNull', reg=mo, offset='an_nown')
    fb.op('Mul', dst=con, a=con, b=den)
    fb.label('an_nown')
    # within DD_BASE_R of another faction's main base
    fb.op('JNull', reg=facs, offset='an_e')
    fb.op('Mov', dst=k3, src=zi)
    b.loop_head('an_f')
    fb.op('JSGte', a=k3, b=b.field(facs, 'length'), offset='an_e')
    of = b.cast(b.call('hl.types.ArrayObj.getDyn', facs, k3), 'ent.Faction')
    fb.op('Incr', dst=k3)
    fb.op('JNull', reg=of, offset='an_f')
    fb.op('JEq', a=of, b=fac, offset='an_f')
    mbs = b.field(of, 'mainBases')
    fb.op('JNull', reg=mbs, offset='an_f')
    fb.op('Mov', dst=k4, src=zi)
    b.loop_head('an_g')
    fb.op('JSGte', a=k4, b=b.field(mbs, 'length'), offset='an_f')
    mb = b.cast(b.call('hl.types.ArrayObj.getDyn', mbs, k4), 'ent.Entity')
    fb.op('Incr', dst=k4)
    fb.op('JNull', reg=mb, offset='an_g')
    mve = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=mve, src=mv)
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', mve, mb), b=b.const('f64', DD_BASE_R), offset='an_g')
    fb.op('Mul', dst=con, a=con, b=den)
    fb.op('JAlways', offset='an_e')  # once per missing neighbour
    fb.label('an_ed')
    fb.op('Add', dst=miss, a=miss, b=one_f)
    fb.op('SDiv', dst=con, a=con, b=miss)
    fb.op('Add', dst=dd, a=dd, b=con)
    fb.op('JAlways', offset='an_d')
    fb.label('an_ddx')
    # ring village (map 'dring' = now); uncontested ring in progress with < DD_TRIES launches: hold the others
    fb.op('JSLte', a=dd, b=zero, offset='an_rg')
    fb.op('Bool', dst=isr, value=True)
    b.call('haxe.ds.ObjectMap.set', dring, fb.dyn(se), fb.dyn(now))
    fb.op('JTrue', cond=hold, offset='an_rg')
    fb.op('Call2', dst=cln, fun=ddc, arg0=fac, arg1=z)
    fb.op('JFalse', cond=cln, offset='an_rg')
    trv = b.call('haxe.ds.ObjectMap.get', dtries, fb.dyn(se))
    fb.op('JNull', reg=trv, offset='an_rgh')
    fb.op('SafeCast', dst=trq, src=trv)
    fb.op('JSGte', a=trq, b=b.const('f64', DD_TRIES), offset='an_rg')
    fb.label('an_rgh')
    fb.op('Bool', dst=hold, value=True)
    fb.label('an_rg')
    # reachable over land: the candidate borders one of our zones that isn't deep desert
    fb.op('JSLte', a=dd, b=zero, offset='an_lk')
    fb.op('Mov', dst=k1, src=zi)
    b.loop_head('an_l')
    fb.op('JSGte', a=k1, b=b.field(zn, 'length'), offset='an_unl')
    lz = b.cast(b.call('hl.types.ArrayObj.getDyn', zn, k1), 'ent.Zone')
    fb.op('Incr', dst=k1)
    fb.op('JNull', reg=lz, offset='an_l')
    fb.op('JNotEq', a=b.field(lz, 'owner'), b=fac, offset='an_l')
    fb.op('JTrue', cond=b.call('ent.Zone.isDeepDesert', lz), offset='an_l')
    fb.op('JAlways', offset='an_lk')
    fb.label('an_unl')
    fb.op('Mul', dst=dd, a=dd, b=_ratio(fb, b, DD_LINK))
    fb.label('an_lk')
    fb.op('JSLte', a=dd, b=b.const('f64', DD_CAP), offset='an_ddc')
    fb.op('Mov', dst=dd, src=b.const('f64', DD_CAP))
    fb.label('an_ddc')
    fb.op('Mul', dst=q, a=dd, b=ddw)
    fb.op('Add', dst=q, a=q, b=one_f)
    fb.op('Mul', dst=sc, a=sc, b=q)
    fb.label('an_dd')
    floor = _ratio(fb, b, ANNEX_FLOOR)
    fb.op('JSGte', a=sc, b=floor, offset='an_fl')
    fb.op('Mov', dst=sc, src=floor)
    fb.label('an_fl')
    b.call('haxe.ds.ObjectMap.set', res, fb.dyn(se), fb.dyn(sc))
    fb.op('JFalse', cond=isr, offset='an_br')
    fb.op('JSLte', a=sc, b=brs, offset='an_br')
    fb.op('Mov', dst=brs, src=sc)
    fb.op('Mov', dst=brc, src=c)
    fb.op('Mov', dst=brdd, src=dd)
    fb.op('Mov', dst=brest, src=se)
    fb.label('an_br')
    fb.op('JSLte', a=sc, b=bs, offset='an2')
    fb.op('Mov', dst=bs, src=sc)
    fb.op('Mov', dst=bc, src=c)
    fb.op('Mov', dst=bdd, src=dd)
    fb.op('Mov', dst=best, src=se)
    fb.op('JAlways', offset='an2')
    fb.label('an2d')
    # ring hold: also while one of our armies runs an Annex order on an uncontested ring village (it isn't a
    # candidate then)
    fb.op('JSLte', a=ddw, b=zero, offset='an_h3')
    fb.op('JTrue', cond=hold, offset='an_hold')
    arms, an = _my_armies(fb, b, fac, 'an_h3')
    ar = _army_loop(fb, b, arms, an, j, 'an_o', 'an_h3')
    ao = b.field(ar, 'aiOrder')
    fb.op('JNull', reg=ao, offset='an_o')
    att = b.field(ao, 'targetType')
    fb.op('JNull', reg=att, offset='an_o')
    aix = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=aix, value=att)
    fb.op('JNotEq', a=aix, b=b.const('i32', T_STRUCT), offset='an_o')
    asa = b.cast(fb.get(ao, 'siegeAction'), 'String')
    fb.op('JNull', reg=asa, offset='an_o')
    fb.op('JNotEq', a=b.call('String.__compare', asa, fb.dyn(annex)), b=zi, offset='an_o')
    atg = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=atg, src=b.cast(b.call('logic.ai.AIOrder.getTarget', ao), 'ent.Entity'))
    fb.op('JNull', reg=atg, offset='an_o')
    atz = b.call('ent.Entity.get_zone', atg)
    fb.op('JNull', reg=atz, offset='an_o')
    fb.op('JEq', a=b.field(atz, 'owner'), b=fac, offset='an_o')
    fb.op('Call2', dst=cln, fun=ddc, arg0=fac, arg1=atz)
    fb.op('JFalse', cond=cln, offset='an_o')
    atv = b.call('haxe.ds.ObjectMap.get', dtries, fb.dyn(atg))
    fb.op('JNull', reg=atv, offset='an_hold')
    fb.op('SafeCast', dst=trq, src=atv)
    fb.op('JSGte', a=trq, b=b.const('f64', DD_TRIES), offset='an_o')
    fb.label('an_hold')
    prs = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'spv'), fb.dyn(fac))  # strat's pressed village
    fb.op('Mov', dst=i, src=zi)
    b.loop_head('an3')
    fb.op('JSGte', a=i, b=n, offset='an3d')
    s3 = b.cast(b.call('hl.types.ArrayObj.getDyn', 0, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=s3, offset='an3')
    fb.op('Mov', dst=se, src=s3)
    fb.op('JNull', reg=b.call('haxe.ds.ObjectMap.get', res, fb.dyn(se)), offset='an3')
    fb.op('JEq', a=fb.dyn(se), b=prs, offset='an3')  # pressed in annex mode: the director's call stands
    rv = b.call('haxe.ds.ObjectMap.get', dring, fb.dyn(se))
    fb.op('JNull', reg=rv, offset='an3x')
    fb.op('SafeCast', dst=q, src=rv)
    fb.op('JEq', a=q, b=now, offset='an3')  # a ring village in this call: kept
    fb.label('an3x')
    b.call('haxe.ds.ObjectMap.remove', res, fb.dyn(se))
    fb.op('Incr', dst=nh)
    fb.op('JAlways', offset='an3')
    fb.label('an3d')
    fb.op('Mov', dst=best, src=brest)
    fb.op('Mov', dst=bs, src=brs)
    fb.op('Mov', dst=bc, src=brc)
    fb.op('Mov', dst=bdd, src=brdd)
    fb.label('an_h3')
    fb.op('JNotNull', reg=best, offset='an_lgb')
    fb.op('JSLte', a=nh, b=zi, offset='end')  # held with no ring candidate (its Annex runs): still logged
    fb.label('an_lgb')
    _throttle(fb, b, cx, 'ascore', fac, ASCORE_T, 'end')
    vs = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=vs, src=zero)
    fb.op('JNull', reg=vb, offset='an_lg')
    vv = b.call('haxe.ds.ObjectMap.get', res, fb.dyn(vb))
    fb.op('JNull', reg=vv, offset='an_lg')
    fb.op('SafeCast', dst=vs, src=vv)
    fb.label('an_lg')
    fb.op('JSLt', a=cmin, b=big, offset='an_cm')
    fb.op('Mov', dst=cmin, src=zero)
    fb.label('an_cm')
    _log_ev(fb, b, cx, helpers, 'ascore', [('f', fb.get(fac, 'kind')), ('tgt', best), ('s', bs), ('c', bc),
                                           ('cmin', cmin), ('vb', vb), ('v0', v0), ('vs', vs), ('n', n),
                                           ('dd%', bdd), ('hold', nh)])


def build_scoring(cx, new_ids, helpers):
    """Target scores: the single tryAction -> $HScoring.structures(structures, faction, k, ...) call (target
    scores for Annex / Liberate / Pillage / ...) -> wrapper:
    - retry: a structure vanilla launched a siege on less than RETRY s ago is dropped. While its order runs vanilla
      doesn't re-pick it, so a re-pick means that order ended at once: fillAttackSteps cancels in Waiting with
      InsufficientSupply (the lowest army supply < AIOrders.estimateSupplyCost of the path) and the gauge, still
      full, re-picked the same village every ~2.5 s (Fremen Pelmah x39). Logs `space` why retry (10 s throttle);
    - bunker preference: a positive score x BUNKER_W when the structure is within COVER_R of one of our structures
      on our land (their turrets cover each other) or within BUNKER_R of our main base.
    Original scores on any error."""
    orig = cx.fn('logic.ai.$HScoring.structures')
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('CallN', dst=res, fun=orig.findex.value, args=list(range(len(args))))
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    n = b.field(0, 'length')
    # press (rules/strat.py): the gates are opened for the pressed village's owner only; among its villages only the
    # pressed one stays; its Annex score x PRESS_W in annex mode (vanilla picks at random among the top scores), and
    # it is no Annex target in pillage mode (`raid` takes it)
    pvd = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'spv'), fb.dyn(1))
    fb.op('JNull', reg=pvd, offset='nopress')
    pfp = b.cast(b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'spf'), fb.dyn(1)), 'ent.Faction')
    fb.op('JNull', reg=pfp, offset='nopress')
    pab, isann = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('SafeCast', dst=pab, src=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'spa'), fb.dyn(1)))
    fb.op('Bool', dst=isann, value=True)
    fb.op('JEq', a=b.call('String.__compare', 2, fb.dyn(fb.string('Annex'))), b=b.const('i32', 0), offset='pk')
    fb.op('Bool', dst=isann, value=False)
    fb.label('pk')
    pi = fb.reg(cx.t('i32'))
    psc = fb.reg(cx.t('f64'))
    pse = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=pi, src=b.const('i32', 0))
    b.loop_head('ps')
    fb.op('JSGte', a=pi, b=n, offset='nopress')
    pst = b.cast(b.call('hl.types.ArrayObj.getDyn', 0, pi), 'ent.Structure')
    fb.op('Incr', dst=pi)
    fb.op('JNull', reg=pst, offset='ps')
    fb.op('Mov', dst=pse, src=pst)
    fb.op('JNotEq', a=b.call('ent.Entity.get_owner', pse), b=pfp, offset='ps')
    fb.op('JNotEq', a=fb.dyn(pse), b=pvd, offset='pdrop')
    fb.op('JFalse', cond=isann, offset='ps')  # the pressed village: other actions (Pillage, ...) unchanged
    fb.op('JFalse', cond=pab, offset='pdrop')  # pillage mode: not an Annex target (no Authority reserved for it)
    pv0 = b.call('haxe.ds.ObjectMap.get', res, fb.dyn(pse))
    fb.op('JNull', reg=pv0, offset='ps')
    fb.op('SafeCast', dst=psc, src=pv0)
    fb.op('Mul', dst=psc, a=psc, b=b.const('f64', PRESS_W))
    b.call('haxe.ds.ObjectMap.set', res, fb.dyn(pse), fb.dyn(psc))
    fb.op('JAlways', offset='ps')
    fb.label('pdrop')
    b.call('haxe.ds.ObjectMap.remove', res, fb.dyn(pse))
    fb.op('JAlways', offset='ps')
    fb.label('nopress')
    mine = b.cast(fb.get(1, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=mine, offset='end')
    mn = b.field(mine, 'length')
    i, j = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    zero = b.const('f64', 0)
    cover, br, w = b.const('f64', COVER_R), b.const('f64', BUNKER_R), _ratio(fb, b, BUNKER_W)
    sc, r = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    se, te = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    now = b.field(_state(fb, b, cx), 'time')
    b.loop_head('s')
    fb.op('JSGte', a=i, b=n, offset='annex')
    s = b.cast(b.call('hl.types.ArrayObj.getDyn', 0, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=s, offset='s')
    fb.op('Mov', dst=se, src=s)
    v = b.call('haxe.ds.ObjectMap.get', res, fb.dyn(se))
    fb.op('JNull', reg=v, offset='s')
    _recent_launch(fb, b, cx, se, now, 'retry')
    fb.op('SafeCast', dst=sc, src=v)
    fb.op('JSLte', a=sc, b=zero, offset='s')
    fb.op('Mov', dst=j, src=b.const('i32', 0))
    b.loop_head('m')
    fb.op('JSGte', a=j, b=mn, offset='s')
    t = b.cast(b.call('hl.types.ArrayObj.getDyn', mine, j), 'ent.Structure')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=t, offset='m')
    fb.op('Mov', dst=te, src=t)
    fb.op('JEq', a=te, b=se, offset='m')
    z = b.call('ent.Entity.get_zone', te)
    fb.op('JNull', reg=z, offset='m')
    fb.op('JNotEq', a=b.field(z, 'owner'), b=1, offset='m')  # on our land (not a UWHeadquarters in theirs)
    fb.op('Mov', dst=r, src=cover)
    fb.op('JFalse', cond=b.call('ent.Structure.get_isMainBase', t), offset='rset')
    fb.op('Mov', dst=r, src=br)
    fb.label('rset')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', se, te), b=r, offset='m')
    fb.op('Mul', dst=sc, a=sc, b=w)
    b.call('haxe.ds.ObjectMap.set', res, fb.dyn(se), fb.dyn(sc))
    fb.op('JAlways', offset='s')
    fb.label('retry')
    b.call('haxe.ds.ObjectMap.remove', res, fb.dyn(se))
    _throttle(fb, b, cx, 'space', 1, 10, 's')
    near = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=near)
    _log_ev(fb, b, cx, helpers, 'space', [('f', fb.get(1, 'kind')), ('k', 2), ('why', 'retry'), ('tgt', se),
                                          ('near', near)])
    fb.op('JAlways', offset='s')
    fb.label('annex')
    _annex_value(fb, b, cx, helpers, res, mine, mn)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    wr = fb.build()
    new_ids.add(wr)
    helpers['scores'] = wr  # raid ranks vanilla's Annex choices with the same scores
    return {'bunker-score': _redirect(cx, 'logic.ai.$HScoring.structures', ['logic.ai.AIMilitary.tryAction'], wr)}


def build_spacing(cx, helpers, defend):
    """Wrapper for the single tryAction -> tryArmyAction(k, s, data) call (every vanilla siege launch: Annex,
    Pillage, Raze, ...), strategic order of checks:
    1. defend: one of our structures is besieged (aimod_defend) -> no new offensive: refuse (log `space`, why defend,
       near = our besieged structure).
    2. bunker: an Annex goes first to a village within BUNKER_R of our active main base that we don't own (lost or
       never taken; neutral or at war with us) and no Military order of ours targets yet: s is replaced (log
       `bunker`). Bypasses vanilla's target score and aggressiveness gate on purpose.
    3. annex-spacing: one of our Military orders already targets another structure within ADJ_R of s (two thin
       sieges side by side split the force) -> refuse (log `space`, why space).
    Refusal = onActionEnd(gauge(k), Dismiss, data): gauge un-paused, no decay, no onFailure blocks; `space` logged
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
    fb.op('JNull', reg=dfs, offset='bunker')
    fb.op('Mov', dst=near, src=dfs)
    fb.op('Mov', dst=why, src=fb.string('defend'))
    fb.op('Bool', dst=blocked, value=True)
    fb.op('JAlways', offset='done')

    # 2. bunker: Annex only
    fb.label('bunker')
    cmp = b.call('String.__compare', 1, fb.dyn(fb.string('Annex')))
    fb.op('JNotEq', a=cmp, b=zi, offset='spacing')
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
    fb.op('JNull', reg=vo, offset='bfree')
    fb.op('JEq', a=vo, b=fac, offset='bv')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, vo), offset='bv')
    fb.label('bfree')
    fb.op('Mov', dst=s_e, src=tgt)
    fb.op('JEq', a=ve, b=s_e, offset='spacing')  # vanilla picked it already
    _recent_launch(fb, b, cx, ve, b.field(state, 'time'), 'bv')  # its last launch ended at once
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

    # 3. annex-spacing
    fb.label('spacing')
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
    fb.op('JSLte', a=k3, b=b.const('i32', 0), offset='rec_done')
    fb.op('Sub', dst=k3, a=k3, b=b.const('i32', 1))
    o3 = b.cast(b.call('hl.types.ArrayObj.getDyn', ords, k3), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o3, offset='rec')
    tt3 = b.field(o3, 'targetType')
    fb.op('JNull', reg=tt3, offset='rec')
    fb.op('EnumIndex', dst=ix3, value=tt3)
    fb.op('JNotEq', a=ix3, b=b.const('i32', T_STRUCT), offset='rec')
    fb.op('JNotEq', a=b.call('logic.ai.AIOrder.getTarget', o3), b=s_e3, offset='rec')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'alaunch'), fb.dyn(s_e3),
           fb.dyn(b.field(_state(fb, b, cx), 'time')))
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
    fb.op('Call4', dst=void, fun=end.findex.value, arg0=0, arg1=gk, arg2=reason, arg3=3)
    fb.op('Ret', ret=void)
    w = fb.build()
    caller = cx.fn('logic.ai.AIMilitary.tryAction')
    sites = [op for op in caller.ops if op.df.get('fun') is not None and op.df['fun'].value == orig.findex.value]
    if len(sites) != 1:
        raise ValueError(f'annex-spacing: expected 1 tryArmyAction call in tryAction, found {len(sites)}')
    sites[0].df['fun'].value = w
    return w


def _vfield(fb, b, obj, name):
    """Field of a virtual (anonymous struct) register by name -> (register of the field's type, field index)."""
    cx = fb.cx
    fields = cx.code.types[fb.regs[obj]].definition.fields
    idx = [i for i, f in enumerate(fields) if f.name.resolve(cx.code) == name]
    if len(idx) != 1:
        raise ValueError(f'siege-join: field {name} not found')
    dst = fb.reg(fields[idx[0]].type.value)
    fb.op('Field', dst=dst, obj=obj, field=idx[0])
    return dst, idx[0]


def build_join(cx, helpers, supok, land, pw, threat, cover, militia, terrain, new_ids):
    """Siege launch sizing: the pickUnits call(s) in tryArmyAction (every vanilla siege launch after the gate).
    Vanilla requires balance 1.0 flat for a neutral target and adds idle armies closest-first only until it is
    reached, so a village gets 2 armies while more sit idle next to it: the militia fight drags on (~50 s), drains
    supply the whole time and can kill one of the two (Fremen on Ashdak, 3 attempts, 18 bunker redirects, none taken).
    1. neutral target (targetFaction null): requiredPowerBalance raised to NEUTRAL_REQ, except in the opening (we own
       fewer than EARLY_VILLAGES villages: vanilla's EARLY_REQ, so the starting armies take the first villages);
    2. after the pick, the nearest other considered armies (vanilla getUnits idle list: life/supply >= 90%, not in
       an order of the action's priority or higher, so Discovery/Patrol armies are taken as vanilla does) within
       JOIN_R of the target with supok(a, land(target), SUP_ENTER) are appended one by one until our power there
       (+ our turret cover) reaches JOIN_TO x (at-war threat within LOCAL + enemy turret cover + militia) / terrain:
       a short militia fight, while the rest stays free for parallel captures (joining everyone sent 8 armies to a
       33k militia at match start and made captures sequential).
    Simulated picks (simulatePendingArmies: counts armies in recruitment) pass through unchanged. Logs `join` when
    armies were added (H, M = the power after joining). Original result on any error."""
    pick = cx.fn('logic.ai.AIUnits.pickUnits')
    taa = cx.fn('logic.ai.AIMilitary.tryArmyAction')
    ftypes = {f.findex.value: f.type.value for f in cx.code.functions}
    sites = [op for op in taa.ops if op.op == 'Call2' and ftypes.get(op.df['fun'].value) == pick.type.value]
    if len(sites) != 3:
        raise ValueError(f'siege-join: expected 3 pickUnits calls in tryArmyAction, found {len(sites)}')
    inner = {op.df['fun'].value for op in sites}
    if len(inner) != 1:
        raise ValueError(f'siege-join: pickUnits call sites differ ({inner})')
    inner = inner.pop()  # the logging wrapper when installed (same signature)
    ft = cx.code.types[pick.type.value].definition
    args = [a.value for a in ft.args]
    fb = FB(cx, args, ft.ret.value, fun_type=pick.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    req = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=req, src=b.const('f64', 0))
    sim = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=sim, value=False)
    # 1. required ratio for neutral targets
    guard = fb.try_()
    sp, _ = _vfield(fb, b, 1, 'simulatePendingArmies')
    fb.op('JNull', reg=sp, offset='nosim')
    fb.op('SafeCast', dst=sim, src=sp)
    fb.label('nosim')
    fb.op('JTrue', cond=sim, offset='req_done')
    enter = _ratio(fb, b, NEUTRAL_REQ)
    # opening: fewer than EARLY_VILLAGES villages -> vanilla's EARLY_REQ (the first captures with the starting armies)
    owner = b.call('logic.ai.AIModule.get_aiOwner', 0)
    fb.op('JNull', reg=owner, offset='req_early')
    fb.op('JSGte', a=b.field(b.call('ent.Faction.getVillages', owner), 'length'), b=b.const('i32', EARLY_VILLAGES),
          offset='req_early')
    fb.op('Mov', dst=enter, src=_ratio(fb, b, EARLY_REQ))
    fb.label('req_early')
    rq, ri = _vfield(fb, b, 1, 'requiredPowerBalance')
    fb.op('JNull', reg=rq, offset='req_tf')
    fb.op('SafeCast', dst=req, src=rq)
    fb.label('req_tf')
    tfac, _ = _vfield(fb, b, 1, 'targetFaction')
    fb.op('JNotNull', reg=tfac, offset='req_done')
    fb.op('JNull', reg=rq, offset='req_set')
    fb.op('JSGte', a=req, b=enter, offset='req_done')
    fb.label('req_set')
    fb.op('Mov', dst=req, src=enter)
    nr = fb.reg(fb.regs[rq])
    fb.op('ToDyn', dst=nr, src=req)  # Null<Float>, the way the compiler boxes it
    fb.op('SetField', obj=1, field=ri, src=nr)
    fb.label('req_done')
    fb.end_try(guard)
    fb.op('Call2', dst=res, fun=inner, arg0=0, arg1=1)
    # 2. idle armies near the target join
    guard2 = fb.try_()
    fb.op('JTrue', cond=sim, offset='done')
    fb.op('JNull', reg=res, offset='done')
    n0 = b.field(res, 'length')
    fb.op('JSLte', a=n0, b=b.const('i32', 0), offset='done')
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='done')
    es, _ = _vfield(fb, b, 1, 'enemyStructure')
    fb.op('JNull', reg=es, offset='done')
    s = fb.reg(cx.t('ent.Entity'))
    fb.op('SafeCast', dst=s, src=fb.dyn(es))
    cu, _ = _vfield(fb, b, 1, 'consideredUnits')
    fb.op('JNull', reg=cu, offset='done')
    cand = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('SafeCast', dst=cand, src=fb.dyn(cu))
    cn = b.field(cand, 'length')
    d_home = fb.reg(cx.t('f64'))
    fb.op('Call2', dst=d_home, fun=land, arg0=fac, arg1=s)
    k = _ratio(fb, b, SUP_ENTER)
    r = b.const('f64', JOIN_R)
    added = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=added, src=b.const('i32', 0))
    ok = fb.reg(cx.t('bool'))
    ae = fb.reg(cx.t('ent.Entity'))
    i = fb.reg(cx.t('i32'))
    h, m, p, q, tf, dd, bd = (fb.reg(cx.t('f64')) for _ in range(7))
    t_false, t_true = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_false, value=False)
    fb.op('Bool', dst=t_true, value=True)
    no_arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=no_arr)
    st = b.cast(fb.dyn(s), 'ent.Structure')
    # their side (same measure as siege-engage) and the power we want there: JOIN_TO x that / terrain
    fb.op('Call3', dst=h, fun=threat, arg0=fac, arg1=s, arg2=b.const('f64', LOCAL))
    fb.op('CallN', dst=q, fun=cover, args=[fac, s, s, t_false, no_arr])
    fb.op('Add', dst=h, a=h, b=q)
    fb.op('Call1', dst=q, fun=militia, arg0=st)
    fb.op('Add', dst=h, a=h, b=q)
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', s))
    fb.op('Mul', dst=q, a=h, b=_ratio(fb, b, JOIN_TO))
    fb.op('SDiv', dst=q, a=q, b=tf)
    # ours: vanilla's pick (+ our turret cover there)
    fb.op('CallN', dst=m, fun=cover, args=[fac, s, s, t_true, no_arr])
    sa = _army_loop(fb, b, res, n0, i, 'sl', 'sdone')
    fb.op('Call1', dst=p, fun=pw, arg0=sa)
    fb.op('Add', dst=m, a=m, b=p)
    fb.op('JAlways', offset='sl')
    fb.label('sdone')
    # add the nearest eligible idle army until we have q
    best = fb.reg(cx.t('ent.Army'))
    big = b.const('f64', 1 << 30)
    b.loop_head('jo')
    fb.op('JSGte', a=m, b=q, offset='jdone')
    fb.op('Null', dst=best)
    fb.op('Mov', dst=bd, src=big)
    a = _army_loop(fb, b, cand, cn, i, 'jl', 'jpick')
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', res, fb.dyn(a)), offset='jnew')
    fb.op('JAlways', offset='jl')
    fb.label('jnew')
    fb.op('Mov', dst=ae, src=a)
    fb.op('Mov', dst=dd, src=b.call('ent.Entity.getDistTo', ae, s))
    fb.op('JSGt', a=dd, b=r, offset='jl')
    fb.op('JSGte', a=dd, b=bd, offset='jl')
    fb.op('Call3', dst=ok, fun=supok, arg0=a, arg1=d_home, arg2=k)
    fb.op('JFalse', cond=ok, offset='jl')
    fb.op('Mov', dst=best, src=a)
    fb.op('Mov', dst=bd, src=dd)
    fb.op('JAlways', offset='jl')
    fb.label('jpick')
    fb.op('JNull', reg=best, offset='jdone')
    b.call('hl.types.ArrayObj.push', res, fb.dyn(best))
    fb.op('Incr', dst=added)
    fb.op('Call1', dst=p, fun=pw, arg0=best)
    fb.op('Add', dst=m, a=m, b=p)
    fb.op('JAlways', offset='jo')
    fb.label('jdone')
    fb.op('JSLte', a=added, b=b.const('i32', 0), offset='done')
    _log_ev(fb, b, cx, helpers, 'join', [('f', fb.get(fac, 'kind')), ('tgt', s), ('sel', n0), ('add', added),
                                         ('req%', req), ('H', h), ('M', m), ('tf%', tf)])
    fb.label('done')
    fb.end_try(guard2)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    for op in sites:
        op.df['fun'].value = w
    return {'siege-join': len(sites)}


def build_siege_engage(cx, helpers, pw, threat, cover, militia, terrain):
    """aimod_sengage(mil, dt), every CHECK s: early Engage for our siege orders (Military on a Structure: vanilla
    Annex/Pillage/Raze/..., `raid`). Vanilla Regroup waits until every order army reached the regroup point, so a
    stack standing next to the target walked away from it towards a far member first (Fremen raid on Tuoron: 5 armies
    36-55 from it went to 85-106 while a 6th came from home); siege-join makes far members common. An order in
    Regroup moves on to Engage (nextPhase) once its armies within ENGAGE_R of the target (+ our turret cover) have
    ENTER (NEUTRAL_REQ for a neutral target, EARLY_REQ in the opening, as at launch) x (at-war threat within LOCAL + enemy turret cover +
    militia) / terrain, and at least one army is there; the others walk straight in (policy §4 Gathering). Only
    armies at the target count: armies strung out within LOCAL walked in one by one, the weakest first (Harkonnen
    raid on Har-Al'sud lost H_Demo 2v3 before its third army arrived). Logs `sengage`. In a trap: nothing on error."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = b.field(_state(fb, b, cx), 'time')
    _tick(fb, b, cx, t, CHECK, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    on = b.field(orders, 'length')
    zi, zero = b.const('i32', 0), b.const('f64', 0)
    local, at = b.const('f64', LOCAL), b.const('f64', ENGAGE_R)
    enter, nreq = _ratio(fb, b, ENTER), _ratio(fb, b, NEUTRAL_REQ)
    t_false, t_true = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_false, value=False)
    fb.op('Bool', dst=t_true, value=True)
    no_arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=no_arr)
    i, j, idx, near = (fb.reg(cx.t('i32')) for _ in range(4))
    h, m, p, q, tf, req = (fb.reg(cx.t('f64')) for _ in range(6))
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=i, src=zi)
    b.loop_head('o')
    fb.op('JSGte', a=i, b=on, offset='end')
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, i), 'logic.ai.AIOrder')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=o, offset='o')
    fb.op('JNotEq', a=b.field(o, 'phase'), b=b.const('i32', REGROUP), offset='o')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='o')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='o')
    fb.op('EnumIndex', dst=idx, value=tt)
    fb.op('JNotEq', a=idx, b=b.const('i32', T_STRUCT), offset='o')
    tg = b.call('logic.ai.AIOrder.getTarget', o)
    fb.op('JNull', reg=tg, offset='o')
    s = b.cast(fb.dyn(tg), 'ent.Structure')
    fb.op('Mov', dst=se, src=s)
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='o')
    un = b.field(units, 'length')
    # ours near the target (+ our cover there)
    fb.op('CallN', dst=m, fun=cover, args=[fac, se, se, t_true, no_arr])
    fb.op('Mov', dst=near, src=zi)
    u = _army_loop(fb, b, units, un, j, 'u', 'udone')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', u, se), b=at, offset='u')
    fb.op('Call1', dst=p, fun=pw, arg0=u)
    fb.op('Add', dst=m, a=m, b=p)
    fb.op('Incr', dst=near)
    fb.op('JAlways', offset='u')
    fb.label('udone')
    fb.op('JSLte', a=near, b=zi, offset='o')
    # theirs: at-war armies in reach, turrets covering it (its own go silent under siege), its militia
    fb.op('Call3', dst=h, fun=threat, arg0=fac, arg1=se, arg2=local)
    fb.op('CallN', dst=q, fun=cover, args=[fac, se, se, t_false, no_arr])
    fb.op('Add', dst=h, a=h, b=q)
    fb.op('Call1', dst=q, fun=militia, arg0=s)
    fb.op('Add', dst=h, a=h, b=q)
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', se))
    fb.op('Mov', dst=req, src=enter)
    fb.op('JNotNull', reg=b.call('ent.Entity.get_owner', se), offset='owned')
    fb.op('Mov', dst=req, src=nreq)
    fb.op('JSGte', a=b.field(b.call('ent.Faction.getVillages', fac), 'length'), b=b.const('i32', EARLY_VILLAGES),
          offset='owned')
    fb.op('Mov', dst=req, src=_ratio(fb, b, EARLY_REQ))  # opening (as at launch)
    fb.label('owned')
    fb.op('Mul', dst=q, a=h, b=req)
    fb.op('SDiv', dst=q, a=q, b=tf)
    fb.op('JSLt', a=m, b=q, offset='o')
    fb.op('Call1', dst=void, fun=helpers.get('nextPhase', cx.fn('logic.ai.AIOrder.nextPhase').findex.value), arg0=o)
    _log_ev(fb, b, cx, helpers, 'sengage', [('f', fb.get(fac, 'kind')), ('tgt', se), ('H', h), ('M', m),
                                            ('near', near), ('n', un), ('tf%', tf)])
    fb.op('JAlways', offset='o')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


def build_discovery(cx, helpers, threat, pw, terrain, new_ids):
    """Discovery gate on the single addOrder call in AIController.checkWorldEvents. Vanilla sends its nearest idle
    army, alone, to a world event (ruins, black market, ...) up to one zone into anyone's land, with no threat check:
    lone armies wandered next to a rival's army blob and got picked off or dragged into sieges from there. Refused
    when the army has less than ENTER x the at-war threat at the event (aimod_threat within LOCAL, / terrain there),
    and for DISC_RETRY s after build_disc_abort gave the event up (map `dfail`), and for DISC_RELAUNCH s after a
    launch on the same event (map `dlaunch`: a re-pick means the trip ended at once; Fremen re-launched one on
    AbandonnedFremenCamp every 1.5-7 s for a minute, cancelled in Waiting each time).
    Refusal = no order (the result is unused; vanilla still stamps lastResolvedWorldEventTime and retries later).
    Logs `disc` (refusals only). Original call otherwise or on any error."""
    add = cx.fn('logic.ai.AIOrders.addOrder')
    orig = helpers.get('addOrder', add.findex.value)  # the logging wrapper when installed (same signature)
    ft = cx.code.types[add.type.value].definition
    args = [a.value for a in ft.args]
    fb = FB(cx, args, ft.ret.value, fun_type=add.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    blocked = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=blocked, value=False)
    h, m, tf = (fb.reg(cx.t('f64')) for _ in range(3))
    tgt = fb.reg(cx.t('ent.Entity'))
    guard = fb.try_()
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='done')
    fb.op('JNull', reg=3, offset='done')
    fb.op('JNull', reg=4, offset='done')
    fb.op('Mov', dst=tgt, src=4)
    fb.op('JSLte', a=b.field(3, 'length'), b=b.const('i32', 0), offset='done')
    u = b.cast(b.call('hl.types.ArrayObj.getDyn', 3, b.const('i32', 0)), 'ent.Unit')
    fb.op('JNull', reg=u, offset='done')
    fb.op('Call3', dst=h, fun=threat, arg0=fac, arg1=tgt, arg2=b.const('f64', LOCAL))
    fb.op('Mov', dst=m, src=b.const('f64', 0))
    # given up recently (hostiles came): refused, logged with M 0
    m0 = fb.reg(cx.t('f64'))
    df = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'dfail'), fb.dyn(tgt))
    fb.op('JNull', reg=df, offset='dfresh')
    fb.op('SafeCast', dst=m0, src=df)
    fb.op('Sub', dst=m0, a=b.field(_state(fb, b, cx), 'time'), b=m0)
    fb.op('JSGte', a=m0, b=b.const('f64', DISC_RETRY), offset='dfresh')
    fb.op('Bool', dst=blocked, value=True)
    fb.op('JAlways', offset='done')
    fb.label('dfresh')
    # launched on this event less than DISC_RELAUNCH s ago: its trip ended at once (vanilla re-picks it every tick)
    dl = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'dlaunch'), fb.dyn(tgt))
    fb.op('JNull', reg=dl, offset='dlok')
    fb.op('SafeCast', dst=m0, src=dl)
    fb.op('Sub', dst=m0, a=b.field(_state(fb, b, cx), 'time'), b=m0)
    fb.op('JSGte', a=m0, b=b.const('f64', DISC_RELAUNCH), offset='dlok')
    fb.op('Bool', dst=blocked, value=True)
    fb.op('JAlways', offset='done')
    fb.label('dlok')
    fb.op('JSLte', a=h, b=b.const('f64', 0), offset='done')
    fb.op('Call1', dst=m, fun=pw, arg0=u)
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', tgt))
    need = fb.reg(cx.t('f64'))
    fb.op('Mul', dst=need, a=h, b=_ratio(fb, b, ENTER))
    fb.op('SDiv', dst=need, a=need, b=tf)
    fb.op('JSGte', a=m, b=need, offset='done')
    fb.op('Bool', dst=blocked, value=True)
    fb.label('done')
    fb.end_try(guard)
    fb.op('JTrue', cond=blocked, offset='block')
    g3 = fb.try_()
    fb.op('JNull', reg=4, offset='nodl')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'dlaunch'), fb.dyn(tgt), fb.dyn(b.field(_state(fb, b, cx), 'time')))
    fb.label('nodl')
    fb.end_try(g3)
    fb.op('CallN', dst=res, fun=orig, args=list(range(len(args))))
    fb.op('Ret', ret=res)
    fb.label('block')
    guard2 = fb.try_()
    owner = b.field(b.field(0, 'controller'), 'owner')
    ue = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ue, src=u)
    _throttle(fb, b, cx, 'discx', tgt, 30, 'dnolog')  # re-asked every 1-2 s for the same event: once per 30 s
    _log_ev(fb, b, cx, helpers, 'disc', [('f', fb.get(owner, 'kind')), ('tgt', tgt), ('army', ue), ('H', h),
                                         ('M', m), ('tf%', tf)])
    fb.label('dnolog')
    fb.end_try(guard2)
    fb.op('Null', dst=res)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    caller = cx.fn('logic.ai.AIController.checkWorldEvents')
    sites = [op for op in caller.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == orig]
    if len(sites) != 1:
        raise ValueError(f'discovery-gate: expected 1 addOrder call in checkWorldEvents, found {len(sites)}')
    sites[0].df['fun'].value = w
    return 1


def build_disc_abort(cx, helpers, pw, threat_far, terrain):
    """aimod_discabort(mil, dt), every CHECK s: retreat from a world event. A running Discovery order of ours (a lone
    army walking to or investigating an event) is cancelled when its armies have less than ENTER x the hostile power
    at the event / terrain there, counting movers that can arrive within DISC_HORIZON (aimod_threat with that
    horizon; the launch gate looks HORIZON ahead). Vanilla never re-checks: a Harkonnen H_Soldier kept investigating a
    relic while 8 Smugglers armies walked 290 units straight at it and only left in contact (1v8, dead). The event
    goes into `dfail` (the gate refuses it for DISC_RETRY s: no launch / abort loop). The army is then in no order:
    `strand` patrols it home on its next pass (an idle army on hostile / neutral land), the fight retreat handles a
    contact. Logs `disc` act=abort. In a trap: nothing on error."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = b.field(_state(fb, b, cx), 'time')
    _tick(fb, b, cx, t, CHECK, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    zi, one, zero = b.const('i32', 0), b.const('i32', 1), b.const('f64', 0)
    enter = _ratio(fb, b, ENTER)
    i, j, idx = (fb.reg(cx.t('i32')) for _ in range(3))
    h, m, p, q, tf = (fb.reg(cx.t('f64')) for _ in range(5))
    ve = fb.reg(cx.t('ent.Entity'))
    reason = cx.code.types[cx.fn('logic.ai.AIOrder.stop').type.value].definition.args[1].value
    cancel = fb.reg(reason)
    fb.op('MakeEnum', dst=cancel, construct=CANCEL, args=[])
    fb.op('Mov', dst=i, src=b.field(orders, 'length'))
    b.loop_head('ord')  # backwards: stop() removes the order from the list
    fb.op('JSLte', a=i, b=zi, offset='end')
    fb.op('Sub', dst=i, a=i, b=one)
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, i), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset='ord')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', DISCOVERY), offset='ord')
    fb.op('Mov', dst=ve, src=b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'ent.Entity'))
    fb.op('JNull', reg=ve, offset='ord')
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='ord')
    un = b.field(units, 'length')
    fb.op('Mov', dst=m, src=zero)
    u = _army_loop(fb, b, units, un, j, 'u', 'udone')
    fb.op('Call1', dst=p, fun=pw, arg0=u)
    fb.op('Add', dst=m, a=m, b=p)
    fb.op('JAlways', offset='u')
    fb.label('udone')
    fb.op('JSLte', a=m, b=zero, offset='ord')
    fb.op('Call3', dst=h, fun=threat_far, arg0=fac, arg1=ve, arg2=b.const('f64', LOCAL))
    fb.op('JSLte', a=h, b=zero, offset='ord')
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', ve))
    fb.op('Mul', dst=q, a=h, b=enter)
    fb.op('SDiv', dst=q, a=q, b=tf)
    fb.op('JSGte', a=m, b=q, offset='ord')
    b.call('logic.ai.AIOrder.stop', o, cancel)
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'dfail'), fb.dyn(ve), fb.dyn(t))
    _log_ev(fb, b, cx, helpers, 'disc', [('f', fb.get(fac, 'kind')), ('act', 'abort'), ('tgt', ve), ('H', h),
                                         ('M', m), ('tf%', tf), ('n', un)])
    fb.op('JAlways', offset='ord')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


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
