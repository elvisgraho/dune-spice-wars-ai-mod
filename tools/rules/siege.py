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


def build_scoring(cx, new_ids):
    """Bunker preference: the single tryAction -> $HScoring.structures(structures, faction, k, ...) call (target
    scores for Annex / Liberate / Pillage / ...) -> wrapper: a positive score x BUNKER_W when the structure is
    within COVER_R of one of our structures on our land (their turrets cover each other) or within BUNKER_R of our
    main base. Original scores on any error."""
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
    mine = b.cast(fb.get(1, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=mine, offset='end')
    n, mn = b.field(0, 'length'), b.field(mine, 'length')
    i, j = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    zero = b.const('f64', 0)
    cover, br, w = b.const('f64', COVER_R), b.const('f64', BUNKER_R), _ratio(fb, b, BUNKER_W)
    sc, r = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    se, te = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    b.loop_head('s')
    fb.op('JSGte', a=i, b=n, offset='end')
    s = b.cast(b.call('hl.types.ArrayObj.getDyn', 0, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=s, offset='s')
    fb.op('Mov', dst=se, src=s)
    v = b.call('haxe.ds.ObjectMap.get', res, fb.dyn(se))
    fb.op('JNull', reg=v, offset='s')
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
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    wr = fb.build()
    new_ids.add(wr)
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
    bunker village)."""
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
    _log_ev(fb, b, cx, helpers, 'bunker', [('f', fb.get(fac, 'kind')), ('k', 1), ('tgt', ve), ('was', 2),
                                           ('mb', mbe)])
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
    _log_ev(fb, b, cx, helpers, 'disc', [('f', fb.get(owner, 'kind')), ('tgt', tgt), ('army', ue), ('H', h),
                                         ('M', m), ('tf%', tf)])
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
