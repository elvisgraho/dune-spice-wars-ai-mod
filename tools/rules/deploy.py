"""Deploy: the Fremen artillery turret (F_Special_2) never gets mobile again once the AI installs it (AI-POLICY §5a
goal 1: armies never starve outside our land).

Vanilla gap, three parts:
- `AIOrders.tryUseOrderAbilities` fires "emergency" abilities (ai state CombatPowerBalanceLow, e.g. FSpecialInstall)
  in Action of Military/Defense/Protect orders while the order balance < AI_InCombatAbilities_MinPowerBalance (Insane
  4). `HPowerScore.compute` returns exactly 1.0 when no enemy power is left (a neutral village whose militia died), so
  the turret is installed, and hero last stands etc. are spent, with nobody to fight.
- F_Special_2 has speed 0; `ent.Unit.canAutoUndeploy` is hard-coded false for it (Move orders never undeploy it) and
  its FSpecialLeave ability has ai state Ignored, which no vanilla path fires.
- The order keeps the Install ability in `noMoveAbilities` (never cleared; same unit entity after `convertToUnitKind`),
  so `checkActionOrder` never sends it the Move into occupation range.
Log: Fremen Annex on Alwahad, F_Special_2 installed 35 from the village during the militia fight, the 3 melee armies
stepped into occupation range (drain stops) once the militia died, the turret stood there at 0 supply until dead;
~10 such starvations across the archived logs.

Fix:
- `ability-gate`: the 3 balance calls in tryUseOrderAbilities go through a wrapper: exactly 1.0 (no enemy power)
  returns NO_ENEMY, so no emergency ability fires without an enemy. Any other value passes unchanged.
- F_Special_2 is an anti-air turret (trait F_Special2_Trait "can only attack flying units", attack F_Turret_Attack
  plane 2): installed in a ground fight it shoots nothing and sits camouflaged (TAmbushCamouflage_Buff gives
  Army_Supply_Protected, so `Army.isInHostileZone` reads false). Log: 3 installed 47 from Atreides' Arkwaz held
  Fremen's Annex there in Action at order balance 0.00-0.01 for 15 min after the rest died (65:32-80:01); the
  pending Annex also held Fremen's Authority reserve, so no other Annex launched meanwhile.
- `aa-gate`: the AbilityManager.canUseAbilityOn call in AIOrder.useAbilities goes through a wrapper: FSpecialInstall
  on a unit with no at-war flying army (`aimod_air`) within AA_R is refused (vanilla skips it: no install, no
  noMoveAbilities entry); logs `aagate` (a) once per unit per 30 s. Every other ability passes unchanged.
- `undeploy` (every CHECK s per faction, before strand): each of our armies that vanilla can't auto-undeploy but
  that can undeploy (`canUndeploy`: an installed F_Special_2 whose Leave is usable) and has nothing to shoot (no
  at-war flying army within AA_R: the gate's measure, so no install / undeploy flip), or is not fighting on hostile
  land (`Army.isInHostileZone`: it drains; an occupying army doesn't) -> `tryUndeploy(auto=false)`, then its stale
  `noMoveAbilities` entries are removed from every order (vanilla's own `type_enum_eq(src, Unit(u))` test), so
  vanilla's Action phase walks it into occupation range, or a Resupply / strand Patrol walks it home. Once per army
  per UNDEPLOY_GAP s (an enemy that stays near without fighting could make vanilla re-install it).
Logs `undeploy` (a army, ok, nm = blocks removed, sup, air = flying hostiles in reach). Fails safe: in a trap, nothing done on error."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

NO_ENEMY = 1 << 20  # order balance returned instead of vanilla's 1.0 "no enemy power": above every ability threshold
UNDEPLOY_GAP = 20   # s between two undeploy attempts on one army (bounds an install / undeploy loop)
UNIT_TGT = 3        # DisplayTarget construct Unit(u) (moveBlockedByAbility / tryUseOrderAbilities)


def build_ability_gate(cx, new_ids):
    """Wrap the order-balance calls of tryUseOrderAbilities (unnamed (AIUnits, AIOrder) -> f64 helper, 3 sites)."""
    f = cx.fn('logic.ai.AIOrders.tryUseOrderAbilities')
    f64 = cx.t('f64')
    units_t, order_t = cx.t('logic.ai.AIUnits'), cx.t('logic.ai.AIOrder')
    sites = [op for op in f.ops if op.op == 'Call2' and f.regs[op.df['dst'].value].value == f64
             and f.regs[op.df['arg0'].value].value == units_t and f.regs[op.df['arg1'].value].value == order_t]
    tids = {op.df['fun'].value for op in sites}
    if len(sites) != 3 or len(tids) != 1:
        raise ValueError(f'ability-gate: expected 3 calls to one balance helper, found {len(sites)} to {tids}')
    tid = tids.pop()
    fb = FB(cx, [units_t, order_t], f64)
    b = B(fb)
    bal = fb.reg(f64)
    fb.op('Call2', dst=bal, fun=tid, arg0=0, arg1=1)
    fb.op('JNotEq', a=bal, b=b.const('f64', 1), offset='end')
    fb.op('Mov', dst=bal, src=b.const('f64', NO_ENEMY))
    fb.label('end')
    fb.op('Ret', ret=bal)
    w = fb.build()
    new_ids.add(w)
    for op in sites:
        op.df['fun'].value = w
    return {'ability-gate': len(sites)}


def build_air(cx):
    """aimod_air(fac, p, r) -> number of armies of factions at war with fac flying (Unit.isFlying: ships, frigates)
    within r of p: what an installed F_Special_2 can shoot."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Entity'), cx.t('f64')], cx.t('i32'))
    b = B(fb)
    n = b.const('i32', 0)
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    st = _state(fb, b, cx)
    armies = b.field(st, 'armies')
    fb.op('JNull', reg=armies, offset='end')
    alen = b.field(armies, 'length')
    i = fb.reg(cx.t('i32'))
    x = _army_loop(fb, b, armies, alen, i, 'loop', 'end')
    o = b.call('ent.Entity.get_owner', x)
    fb.op('JNull', reg=o, offset='loop')
    fb.op('JEq', a=o, b=0, offset='loop')
    fb.op('JFalse', cond=b.call('ent.Unit.isFlying', x), offset='loop')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', x, 1), b=2, offset='loop')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', st, 0, o), offset='loop')
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset='loop')
    fb.label('end')
    fb.op('Ret', ret=n)
    return fb.build()


def build_aa_gate(cx, helpers, air, new_ids):
    """Wrap AIOrder.useAbilities' canUseAbilityOn call: FSpecialInstall needs an at-war flying army within AA_R of
    the unit (see module doc)."""
    orig = cx.fn('logic.faction.AbilityManager.canUseAbilityOn')
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    if len(args) != 5 or ft.ret.value != cx.t('bool') or args[1] != cx.t('String'):
        raise ValueError('aa-gate: canUseAbilityOn(mgr, id, args, ?, ?) -> Bool expected')
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(cx.t('bool'))
    fb.op('CallN', dst=res, fun=orig.findex.value, args=[0, 1, 2, 3, 4])  # vanilla, outside any trap
    guard = fb.try_()
    fb.op('JFalse', cond=res, offset='end')
    fb.op('JNull', reg=1, offset='end')
    fb.op('JNotEq', a=b.call('String.__compare', 1, fb.dyn(fb.string('FSpecialInstall'))), b=b.const('i32', 0),
          offset='end')
    srcd = fb.get(2, 'src')
    fb.op('JNull', reg=srcd, offset='end')
    dt = b.cast(srcd, 'DisplayTarget')
    fb.op('JNull', reg=dt, offset='end')
    ix = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ix, value=dt)
    fb.op('JNotEq', a=ix, b=b.const('i32', UNIT_TGT), offset='end')
    u = fb.reg(cx.t('ent.Unit'))
    fb.op('EnumField', dst=u, value=dt, construct=UNIT_TGT, field=0)
    fb.op('JNull', reg=u, offset='end')
    ue = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ue, src=u)
    fac = b.call('ent.Entity.get_owner', ue)
    fb.op('JNull', reg=fac, offset='end')
    na = fb.reg(cx.t('i32'))
    fb.op('Call3', dst=na, fun=air, arg0=fac, arg1=ue, arg2=b.const('f64', AA_R))
    fb.op('JSGt', a=na, b=b.const('i32', 0), offset='end')
    fb.op('Bool', dst=res, value=False)  # nothing it could shoot: no install
    _throttle(fb, b, cx, 'aagate', ue, 30, 'end')
    _log_ev(fb, b, cx, helpers, 'aagate', [('f', fb.get(fac, 'kind')), ('a', ue)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    caller = cx.fn('logic.ai.AIOrder.useAbilities')
    sites = [op for op in caller.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == orig.findex.value]
    if len(sites) != 1:
        raise ValueError(f'aa-gate: expected 1 canUseAbilityOn call in useAbilities, found {len(sites)}')
    for op in sites:
        op.df['fun'].value = w
    return {'aa-gate': len(sites)}


def build_undeploy(cx, helpers, air):
    """aimod_undeploy(mil, dt) (see module doc)."""
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
    my_armies, mlen = _my_armies(fb, b, fac, 'end')
    tu = cx.fn('ent.Unit.tryUndeploy')
    ref_t = cx.code.types[tu.type.value].definition.args[1].value
    eq = [n.findex.value for n in cx.code.natives if n.name.resolve(cx.code) == 'type_enum_eq']
    if len(eq) != 1:
        raise ValueError(f'undeploy: expected one native type_enum_eq, found {eq}')
    i, k, j, nm = (fb.reg(cx.t('i32')) for _ in range(4))
    ok, same = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    auto, ref = fb.reg(cx.t('bool')), fb.reg(ref_t)
    unit = fb.reg(cx.t('ent.Unit'))
    tgt = fb.reg(cx.t('DisplayTarget'))
    zi, one = b.const('i32', 0), b.const('i32', 1)

    a = _army_loop(fb, b, my_armies, mlen, i, 'army', 'end')
    fb.op('JTrue', cond=b.call('ent.Unit.canAutoUndeploy', a), offset='army')
    fb.op('JFalse', cond=b.call('ent.Unit.canUndeploy', a), offset='army')
    ae = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ae, src=a)
    na = fb.reg(cx.t('i32'))
    fb.op('Call3', dst=na, fun=air, arg0=fac, arg1=ae, arg2=b.const('f64', AA_R))
    fb.op('JSLte', a=na, b=zi, offset='go')  # an anti-air turret with nothing flying in reach: useless installed
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', a), offset='army')
    fb.op('JFalse', cond=b.call('ent.Army.isInHostileZone', a), offset='army')
    fb.label('go')
    _throttle(fb, b, cx, 'undeploy', a, UNDEPLOY_GAP, 'army')
    fb.op('Bool', dst=auto, value=False)
    fb.op('Ref', dst=ref, src=auto)
    fb.op('Call2', dst=ok, fun=tu.findex.value, arg0=a, arg1=ref)
    fb.op('Mov', dst=nm, src=zi)
    fb.op('JFalse', cond=ok, offset='lg')
    # drop the stale Install block of this unit from every order (vanilla moveBlockedByAbility test)
    fb.op('Mov', dst=unit, src=a)
    fb.op('MakeEnum', dst=tgt, construct=UNIT_TGT, args=[unit])
    fb.op('Mov', dst=k, src=zi)
    b.loop_head('ord')
    fb.op('JSGte', a=k, b=on, offset='lg')
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, k), 'logic.ai.AIOrder')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=o, offset='ord')
    blocks = b.field(o, 'noMoveAbilities')
    fb.op('JNull', reg=blocks, offset='ord')
    fb.op('Mov', dst=j, src=b.field(blocks, 'length'))
    b.loop_head('blk')  # backwards: removal keeps the lower indices valid
    fb.op('JSLte', a=j, b=zi, offset='ord')
    fb.op('Sub', dst=j, a=j, b=one)
    ab = b.cast(b.call('hl.types.ArrayObj.getDyn', blocks, j), 'logic.faction.Ability')
    fb.op('JNull', reg=ab, offset='blk')
    fb.op('Call2', dst=same, fun=eq[0], arg0=b.field(ab, 'src'), arg1=tgt)
    fb.op('JFalse', cond=same, offset='blk')
    b.call('hl.types.ArrayObj.remove', blocks, fb.dyn(ab))
    fb.op('Incr', dst=nm)
    fb.op('JAlways', offset='blk')
    fb.label('lg')
    _log_ev(fb, b, cx, helpers, 'undeploy', [('f', fb.get(fac, 'kind')), ('a', a), ('ok', ok), ('nm', nm),
                                             ('sup', b.call('ent.Army.get_supply', a)), ('air', na)])
    fb.op('JAlways', offset='army')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
