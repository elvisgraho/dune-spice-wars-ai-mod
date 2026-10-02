"""Army size (user rule: always max out the army; the economy is steered separately).

Vanilla recruits only while free CP exceeds a reserve by data (resource.CommandPoint.prodGoals, removed by
patches/data.json) and gates unit picks on Manpower goals; on a CP overflow (net CP < 0, e.g. free temporary
Mercenaries on top of a full army) its deficit path refunds the weakest army of the worst-scored kind every 15 s,
which can be a permanent unit, or nothing at all when only unbuyable kinds carry CP upkeep.

- cp-overflow: the checkCommandPoint call in ResourceManager.checkResources is wrapped. While net CP < 0 and
  vanilla's disband time is due, temporary armies (CP upkeep > 0, no safe regen: Temporary_Trait*) are disbanded,
  lowest life first (one holding our order in Action, e.g. a capture's keeper, last), until their CP covers the overflow; then nextDisbandTime = now + CP_DISBAND_T so vanilla
  refunds no permanent unit in the same pass. No temporary army: vanilla's refund runs unchanged. Logs `cpdis`
  (f, a, cp = its CP upkeep, free = net CP before).
- mp-gate: the Manpower goal tests in $AIUnits.pickBuyableUnit (compareGoals < -1 -> no unit; belowGoal per unit,
  the same test since units have no Manpower upkeep) are lifted: a unit is picked whenever it is affordable
  (canRecruit / the recruit cost check still apply). Logs `mpgate` (f, mp = Manpower stock) once per faction per
  MP_LOG_T s when the gate would have blocked."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

CP_RES = 13          # resource sheet index of CommandPoint
MP_RES = 3           # ... of Manpower
CP_DISBAND_T = 15    # s: vanilla's own deficit pacing (checkCommandPoint sets nextDisbandTime = now + 15)
MP_LOG_T = 60        # s: `mpgate` log throttle per faction
ACT_LAST = 10        # cp-overflow key: life ratio (<= 1) + this for an army in one of our orders in Action


def _one_site(cx, caller, target):
    tid = cx.fn(target).findex.value
    sites = [op for op in cx.fn(caller).ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == tid]
    if len(sites) != 1:
        raise ValueError(f'army: expected 1 {target} call in {caller}, found {len(sites)}')
    return sites[0]


def build_cp_overflow(cx, helpers, new_ids):
    """cp-overflow wrapper (see module doc): (ResourceManager) -> void, then vanilla checkCommandPoint."""
    ccp = cx.fn('logic.ai.ResourceManager.checkCommandPoint')
    site = _one_site(cx, 'logic.ai.ResourceManager.checkResources', 'logic.ai.ResourceManager.checkCommandPoint')
    up_t = cx.code.types[cx.fn('ent.Entity.getUpkeep').type.value].definition.args[2].value
    fb = FB(cx, [cx.t('logic.ai.ResourceManager')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    fac = b.cast(b.field(b.field(0, 'controller'), 'owner'), 'ent.Faction')
    fb.op('JNull', reg=fac, offset='orig')
    ki = b.const('i32', CP_RES)
    zero = b.const('f64', 0)
    free = b.call('ent.Faction.getCachedResNetProd', fac, ki)
    fb.op('JSGte', a=free, b=zero, offset='orig')
    t = b.field(_state(fb, b, cx), 'time')
    fb.op('JSLt', a=t, b=b.field(0, 'nextDisbandTime'), offset='orig')
    nul = fb.reg(up_t)
    fb.op('Null', dst=nul)
    # candidates: temporary armies carrying CP upkeep
    cands = _new_array(fb, b, cx)
    arr, alen = _my_armies(fb, b, fac, 'orig')
    i = fb.reg(cx.t('i32'))
    a = _army_loop(fb, b, arr, alen, i, 'scan', 'pick')
    fb.op('JSLte', a=b.call('ent.Entity.getUpkeep', a, ki, nul), b=zero, offset='scan')
    fb.op('JTrue', cond=b.call('ent.Unit.hasSafeRegen', a), offset='scan')
    b.call('hl.types.ArrayObj.push', cands, fb.dyn(a))
    fb.op('JAlways', offset='scan')
    fb.label('pick')
    need, got = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Sub', dst=need, a=zero, b=free)
    fb.op('Mov', dst=got, src=zero)
    n = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=n, src=b.const('i32', 0))
    best, bl, k = fb.reg(cx.t('ent.Army')), fb.reg(cx.t('f64')), fb.reg(cx.t('i32'))
    b.loop_head('sel')
    fb.op('JSGte', a=got, b=need, offset='done')
    # lowest life first
    fb.op('Null', dst=best)
    fb.op('Mov', dst=bl, src=b.const('f64', 1000))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head('mn')
    fb.op('JSGte', a=k, b=b.field(cands, 'length'), offset='mnd')
    c = b.cast(b.call('hl.types.ArrayObj.getDyn', cands, k), 'ent.Army')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=c, offset='mn')
    lr = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=lr, src=b.call('ent.Entity.get_lifeRatio', c))
    # an army holding one of our orders in Action (a capture's keeper) goes last: + ACT_LAST
    ords = b.field(b.field(b.field(fac, 'aiController'), 'aiOrders'), 'orders')
    fb.op('JNull', reg=ords, offset='mk')
    oi = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=oi, src=b.const('i32', 0))
    b.loop_head('ol')
    fb.op('JSGte', a=oi, b=b.field(ords, 'length'), offset='mk')
    oo = b.cast(b.call('hl.types.ArrayObj.getDyn', ords, oi), 'logic.ai.AIOrder')
    fb.op('Incr', dst=oi)
    fb.op('JNull', reg=oo, offset='ol')
    fb.op('JSLt', a=b.field(oo, 'phase'), b=b.const('i32', ACTION), offset='ol')
    ou = b.field(oo, 'units')
    fb.op('JNull', reg=ou, offset='ol')
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', ou, fb.dyn(c)), offset='ol')
    fb.op('Add', dst=lr, a=lr, b=b.const('f64', ACT_LAST))
    fb.label('mk')
    fb.op('JSGte', a=lr, b=bl, offset='mn')
    fb.op('Mov', dst=bl, src=lr)
    fb.op('Mov', dst=best, src=c)
    fb.op('JAlways', offset='mn')
    fb.label('mnd')
    fb.op('JNull', reg=best, offset='done')
    b.call('hl.types.ArrayObj.remove', cands, fb.dyn(best))
    upb = b.call('ent.Entity.getUpkeep', best, ki, nul)
    fb.op('Add', dst=got, a=got, b=upb)
    fb.op('Incr', dst=n)
    _log_ev(fb, b, cx, helpers, 'cpdis', [('f', fb.get(fac, 'kind')), ('a', best), ('cp', upb), ('free', free)])
    b.call('ent.Unit.disband', best)
    fb.op('JAlways', offset='sel')
    fb.label('done')
    fb.op('JSLte', a=n, b=b.const('i32', 0), offset='orig')
    nt = fb.reg(cx.t('f64'))
    fb.op('Add', dst=nt, a=t, b=b.const('f64', CP_DISBAND_T))
    fb.op('SetField', obj=0, field=cx.field(fb.regs[0], 'nextDisbandTime'), src=nt)
    fb.label('orig')
    fb.end_try(guard)
    fb.op('Call1', dst=void, fun=ccp.findex.value, arg0=0)
    fb.op('Ret', ret=void)
    w = fb.build()
    site.df['fun'].value = w
    new_ids.add(w)
    return {'cp-overflow': 1}


def build_mp_gate(cx, helpers, new_ids):
    """mp-gate wrappers (see module doc) on the compareGoals / belowGoal calls in $AIUnits.pickBuyableUnit."""
    pick = 'logic.ai.$AIUnits.pickBuyableUnit'
    cg = cx.fn('logic.ai.ResourceManager.compareGoals')
    bg = cx.fn('logic.ai.ResourceManager.belowGoal')
    cg_site = _one_site(cx, pick, 'logic.ai.ResourceManager.compareGoals')
    bg_site = _one_site(cx, pick, 'logic.ai.ResourceManager.belowGoal')
    # compareGoals: vanilla result, at least -1 (the pick returns null below -1)
    ct = cx.code.types[cg.type.value].definition
    fb = FB(cx, [x.value for x in ct.args], ct.ret.value, fun_type=cg.type.value)
    b = B(fb)
    r = fb.reg(ct.ret.value)
    fb.op('CallN', dst=r, fun=cg.findex.value, args=list(range(len(ct.args))))
    guard = fb.try_()
    m1 = b.const('i32', -1)
    fb.op('JSGte', a=r, b=m1, offset='end')
    fb.op('Mov', dst=r, src=m1)
    fac = b.cast(b.field(b.field(0, 'controller'), 'owner'), 'ent.Faction')
    fb.op('JNull', reg=fac, offset='end')
    _throttle(fb, b, cx, 'mpgate', fac, MP_LOG_T, 'end')
    _log_ev(fb, b, cx, helpers, 'mpgate', [('f', fb.get(fac, 'kind')),
                                           ('mp', b.call('ent.Faction.getResource', fac, b.const('i32', MP_RES)))])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=r)
    wc = fb.build()
    # belowGoal (per-unit Manpower filter): never below
    bt = cx.code.types[bg.type.value].definition
    fb = FB(cx, [x.value for x in bt.args], bt.ret.value, fun_type=bg.type.value)
    no = fb.reg(bt.ret.value)
    fb.op('Bool', dst=no, value=False)
    fb.op('Ret', ret=no)
    wb = fb.build()
    cg_site.df['fun'].value = wc
    bg_site.df['fun'].value = wb
    new_ids.update({wc, wb})
    return {'mp-gate': 1}


CP_SHORT = 5         # free CP below this = the army is at its cap (units cost 3-5 CP): more CP is needed
DFULL_LOG_T = 30     # s: `dfull` log throttle per faction


def build_cp_need(cx, helpers, new_ids):
    """cp-need: HScoring.prepareContext lists a resource as under-producing when compareGoals < 0 (its
    aiRelatedBuildings get AI_BuildingScore_UnderProducingResource_Weight, over-producing ones -2). CommandPoint's
    goals are inverted (< 0 = much free CP: buy units), so its building Main_Command (+10 CP) was pushed while CP
    was plentiful and penalised once the army was full. The compareGoals call there is wrapped: for "CommandPoint"
    the answer is -1 (under) when free CP (Faction.getCachedResNetProd) < CP_SHORT, else 0; other resources vanilla."""
    cg = cx.fn('logic.ai.ResourceManager.compareGoals')
    site = _one_site(cx, 'logic.ai.$HScoring.prepareContext', 'logic.ai.ResourceManager.compareGoals')
    ct = cx.code.types[cg.type.value].definition
    fb = FB(cx, [x.value for x in ct.args], ct.ret.value, fun_type=cg.type.value)
    b = B(fb)
    r = fb.reg(ct.ret.value)
    fb.op('CallN', dst=r, fun=cg.findex.value, args=list(range(len(ct.args))))
    guard = fb.try_()
    fb.op('JNull', reg=1, offset='end')
    fb.op('JNotEq', a=b.call('String.__compare', 1, fb.dyn(fb.string('CommandPoint'))), b=b.const('i32', 0),
          offset='end')
    fac = b.cast(b.field(b.field(0, 'controller'), 'owner'), 'ent.Faction')
    fb.op('JNull', reg=fac, offset='end')
    free = b.call('ent.Faction.getCachedResNetProd', fac, b.const('i32', CP_RES))
    fb.op('Mov', dst=r, src=b.const('i32', 0))
    fb.op('JSGte', a=free, b=b.const('f64', CP_SHORT), offset='end')
    fb.op('Mov', dst=r, src=b.const('i32', -1))
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=r)
    w = fb.build()
    site.df['fun'].value = w
    new_ids.add(w)
    return {'cp-need': 1}


def build_cp_defense(cx, helpers, new_ids):
    """cp-defense: AIMilitary.checkStructures, when its defense pick comes back empty (not enough power, or our
    pick-life / rally / hopeless filters emptied it) for a structure that isn't a main base, asks whether any of our
    unit kinds still fits in free CP (Faction.hasResource CommandPoint): yes -> sends nothing (recruit first), no ->
    sends every idle army (idleUnits) into the fight it just judged too strong, past every filter of ours (a
    conceded / hopeless village got the whole idle army). With the army always at full CP the second branch fired
    every time. That hasResource call is wrapped to answer true (logs `dfull` f once per faction per DFULL_LOG_T s
    when vanilla's answer was false): an insufficient defense sends nothing; rally / hunts gather the real one."""
    hr = cx.fn('ent.Faction.hasResource')
    site = _one_site(cx, 'logic.ai.AIMilitary.checkStructures', 'ent.Faction.hasResource')
    ht = cx.code.types[hr.type.value].definition
    fb = FB(cx, [x.value for x in ht.args], ht.ret.value, fun_type=hr.type.value)
    b = B(fb)
    r = fb.reg(ht.ret.value)
    fb.op('CallN', dst=r, fun=hr.findex.value, args=list(range(len(ht.args))))
    guard = fb.try_()
    fb.op('JTrue', cond=r, offset='end')
    fb.op('Bool', dst=r, value=True)
    fb.op('JNull', reg=0, offset='end')
    _throttle(fb, b, cx, 'dfull', 0, DFULL_LOG_T, 'end')
    _log_ev(fb, b, cx, helpers, 'dfull', [('f', fb.get(0, 'kind'))])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=r)
    w = fb.build()
    site.df['fun'].value = w
    new_ids.add(w)
    return {'cp-defense': 1}
