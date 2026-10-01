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
    fb.op('JSGte', a=i, b=n, offset='end')
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
    bunker village), and the launch time is recorded per target (map 'alaunch'; the bunker skips a village launched
    less than RETRY s ago, the scoring wrapper drops it)."""
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
    guard3 = fb.try_()  # remember the launch (retry, in the scoring wrapper)
    s_e3 = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=s_e3, src=tgt)
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'alaunch'), fb.dyn(s_e3),
           fb.dyn(b.field(_state(fb, b, cx), 'time')))
    fb.end_try(guard3)
    fb.op('Call4', dst=void, fun=orig.findex.value, arg0=0, arg1=1, arg2=tgt, arg3=3)
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
    1. neutral target (targetFaction null): requiredPowerBalance raised to NEUTRAL_REQ;
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
    ENTER (NEUTRAL_REQ for a neutral target, as at launch) x (at-war threat within LOCAL + enemy turret cover +
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
    when the army has less than ENTER x the at-war threat at the event (aimod_threat within LOCAL, / terrain there).
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
