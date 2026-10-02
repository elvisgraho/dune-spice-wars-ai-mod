"""Turret steering (AI-POLICY §5a goal 2, standoff): a village that at-war armies keep standing next to gets a
MissileBattery first.

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
(below its defense minimum) is lifted; NaN (invalid pair) is kept. A standing record not refreshed for 2 x STAND_T
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
    fb.op('JNotEq', a=b.call('String.__compare', ks, fb.dyn(fb.string('MissileBattery'))), b=b.const('i32', 0),
          offset='end')
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
    h = fb.reg(cx.t('f64'))
    fb.op('Call3', dst=h, fun=threat, arg0=1, arg1=se, arg2=b.const('f64', STAND_R))
    stnd = _global_map(fb, b, cx, 'stnd')
    now = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=now, src=b.field(_state(fb, b, cx), 'time'))
    fb.op('JSGte', a=h, b=b.const('f64', STAND_MIN_H), offset='standing')
    b.call('haxe.ds.ObjectMap.remove', stnd, fb.dyn(s))
    fb.op('JAlways', offset='end')
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
    fb.op('JAlways', offset='end')
    fb.label('seen')
    fb.op('SafeCast', dst=el, src=first)
    fb.op('Sub', dst=el, a=now, b=el)
    fb.op('JSLt', a=el, b=b.const('f64', STAND_T), offset='end')
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
    fb.op('JSGte', a=c, b=hx, offset='end')
    # only a battery that can be built now or once paid for: a full village (VillageUpgradesLimitReached) would be
    # picked over and over, and in combat / occupied vanilla only queues it (the same check checkBuildings runs
    # before doAddBuilding)
    up = b.field(s, 'upgrades')
    fb.op('JNull', reg=up, offset='end')
    ca = cx.fn('logic.Upgrades.checkAddUpgrade')
    cat = [a.value for a in cx.code.types[ca.type.value].definition.args]
    cret = cx.code.types[ca.type.value].definition.ret.value
    di = b.const('i32', 0)
    dref = fb.reg(cat[2])
    fb.op('Ref', dst=dref, src=di)
    cnul = []
    for t_ in cat[3:]:
        r_ = fb.reg(t_)
        fb.op('Null', dst=r_)
        cnul.append(r_)
    rr = fb.reg(cret)
    fb.op('CallN', dst=rr, fun=ca.findex.value, args=[up, fb.string('MissileBattery'), dref] + cnul)
    ri = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ri, value=rr)
    rnames = [c_.name.resolve(cx.code) for c_ in cx.code.types[cret].definition.constructs]
    fb.op('JEq', a=ri, b=b.const('i32', rnames.index('Success')), offset='buildable')
    fb.op('JNotEq', a=ri, b=b.const('i32', rnames.index('MissingResources')), offset='end')
    fb.label('buildable')
    v0 = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=v0, src=res)
    zero = b.const('f64', 0)
    fb.op('JSGte', a=res, b=zero, offset='pos')
    fb.op('Mov', dst=res, src=zero)
    fb.label('pos')
    fb.op('Add', dst=res, a=res, b=b.const('f64', STAND_BONUS))
    _throttle(fb, b, cx, 'turret', s, 30, 'end')
    _log_ev(fb, b, cx, helpers, 'turret', [('f', fb.get(1, 'kind')), ('s', s), ('h', h), ('sc', v0)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    # only the pick's scoring closure (scoring_logic_ai_AIStructureBuilding): checkBuildings re-scores the pick and
    # the village's existing buildings for VillageUpgradesLimitReached and demolishes any scoring below the pick, so
    # a bonus there would tear down a standoff village's economy for a turret
    skip = {w, inner, cx.fn('logic.ai.BuildingManager.checkBuildings').findex.value}
    sites = [op for g in cx.code.functions if g.findex.value not in skip for op in g.ops
             if op.op.startswith('Call') and op.df.get('fun') is not None and op.df['fun'].value == oid]
    if len(sites) != 1:
        raise ValueError(f'turret-steer: expected 1 scoring-closure call of getBuildingStructureScore, found {len(sites)}')
    sites[0].df['fun'].value = w
    return {'turret-steer': 1}
