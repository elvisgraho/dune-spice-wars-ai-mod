"""Harkonnen Oppression (AI-POLICY "Harkonnen oppression").

Vanilla `AIController.checkOppression` (regularUpdate, every need cycle): Harkonnen's villages without TOppression and
with <= AI_Ability_Oppression_MaxEndedStacks 2 TOppression_Ended stacks; running oppressions < floor(armies /
(TroopsPerRebels 1 x the Rebels raid's unit count)); every cost line (20 Manpower) must pass
`ResourceManager.compareGoals(res, 0, false, 2, 0, -qty) >= 1`, i.e. Manpower left above the AI's goals after paying;
then `$HScoring.scoreOppression` -> pickMapWeight -> `useAbilityOn("Oppression", {src: Structure(v)})`.
The Manpower goals follow recruiting (our CP prodGoals keep the army at its cap and the mp-gate lifts the unit-pick
test), so the goal test reads Manpower as needed while Harkonnen holds 60-120 of it mid-match. User: oppress villages
when there is enough Manpower (the Office of Order, Martial Economy, does it for free on its village).

- `oppgate`: the compareGoals call in checkOppression -> wrapper: vanilla's answer, or 1 when the stock
  (getResource Manpower) >= OPP_MP (cost 20 + a reinforcement's worth). Logs `oppgate` (f, van, mp) once per
  faction per OPP_LOG_T s when ours differs from vanilla's.
- `opick`: the pickMapWeight call -> logs the chosen village (s, f).
- `oppress`: the useAbilityOn call -> logs its result (f, r), except NoVillageSelected (vanilla casts with an
  empty pick every cycle: 1811 of 2013 calls in match 2026-10-04 19:36).
Original answer / call on any error."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.army import _one_site, MP_RES

OPP_MP = 40       # Manpower stock at which Harkonnen oppresses (cost 20 + 20 kept for a reinforcement)
OPP_LOG_T = 60    # s: `oppgate` log throttle per faction
CHECK = 'logic.ai.AIController.checkOppression'


def build_oppress(cx, helpers, new_ids):
    # 1. Manpower gate
    cg = cx.fn('logic.ai.ResourceManager.compareGoals')
    site = _one_site(cx, CHECK, 'logic.ai.ResourceManager.compareGoals')
    ct = cx.code.types[cg.type.value].definition
    fb = FB(cx, [x.value for x in ct.args], ct.ret.value, fun_type=cg.type.value)
    b = B(fb)
    r = fb.reg(ct.ret.value)
    fb.op('CallN', dst=r, fun=site.df['fun'].value, args=list(range(len(ct.args))))
    guard = fb.try_()
    one = b.const('i32', 1)
    fb.op('JSGte', a=r, b=one, offset='end')
    fac = b.cast(b.field(b.field(0, 'controller'), 'owner'), 'ent.Faction')
    fb.op('JNull', reg=fac, offset='end')
    mp = b.call('ent.Faction.getResource', fac, b.const('i32', MP_RES))
    fb.op('JSLt', a=mp, b=b.const('f64', OPP_MP), offset='end')
    van = fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=van, src=r)
    fb.op('Mov', dst=r, src=one)
    _throttle(fb, b, cx, 'oppgate', fac, OPP_LOG_T, 'end')
    _log_ev(fb, b, cx, helpers, 'oppgate', [('f', fb.get(fac, 'kind')), ('van', van), ('mp', mp)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=r)
    w = fb.build()
    site.df['fun'].value = w
    new_ids.add(w)

    # 2. chosen village
    pk_site = _one_site(cx, CHECK, 'lib.$Extensions_pickMapWeight_ent_Structure.pickMapWeight')
    pk = cx.fn('lib.$Extensions_pickMapWeight_ent_Structure.pickMapWeight')
    pt = cx.code.types[pk.type.value].definition
    fb = FB(cx, [x.value for x in pt.args], pt.ret.value, fun_type=pk.type.value)
    b = B(fb)
    s = fb.reg(pt.ret.value)
    fb.op('CallN', dst=s, fun=pk_site.df['fun'].value, args=list(range(len(pt.args))))
    guard = fb.try_()
    fb.op('JNull', reg=s, offset='end')
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=s)
    ow = b.call('ent.Entity.get_owner', se)
    fb.op('JNull', reg=ow, offset='end')
    _log_ev(fb, b, cx, helpers, 'opick', [('f', fb.get(ow, 'kind')), ('s', se)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=s)
    w2 = fb.build()
    pk_site.df['fun'].value = w2
    new_ids.add(w2)

    # 3. cast result
    ua_site = _one_site(cx, CHECK, 'logic.faction.AbilityManager.useAbilityOn')
    ua = cx.fn('logic.faction.AbilityManager.useAbilityOn')
    ut = cx.code.types[ua.type.value].definition
    fb = FB(cx, [x.value for x in ut.args], ut.ret.value, fun_type=ua.type.value)
    b = B(fb)
    res = fb.reg(ut.ret.value)
    fb.op('CallN', dst=res, fun=ua_site.df['fun'].value, args=list(range(len(ut.args))))
    guard = fb.try_()
    rn = [c.name.resolve(cx.code) for c in cx.code.types[ut.ret.value].definition.constructs]
    rix = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=rix, value=res)
    fb.op('JEq', a=rix, b=b.const('i32', rn.index('NoVillageSelected')), offset='end')  # nothing picked: every cycle
    ow = b.field(0, 'owner')
    fb.op('JNull', reg=ow, offset='end')
    _log_ev(fb, b, cx, helpers, 'oppress', [('f', fb.get(ow, 'kind')), ('r', fb.dyn(res))])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w3 = fb.build()
    ua_site.df['fun'].value = w3
    new_ids.add(w3)
    return {'oppress': 3}
