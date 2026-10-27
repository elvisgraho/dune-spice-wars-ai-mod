"""Task values (docs/ARCHITECTURE-PLAN.md step 2 stage 2): what a task puts at stake, on one scale for every task kind.

The scale is the economy model's (rules/econ.py RES_VALUE, step 3): Solari-equivalent at the faction's current resource
values (a resource in surplus is worth ~0, a short one ~2 x its base).
- aimod_sval(fac, s) -> the value of structure s to fac: VAL_DAYS x (its buildings' daily output x quirk factor x
  value - their upkeep, never below 0, + VAL_VILLAGE_DAY for the village itself: territory, supply, hegemony;
  + VAL_SPICE_DAY with a spice field in its zone, + VAL_AIW_DAY x the region's aiWeight for a special region);
  another faction's structure x VAL_ENEMY (a capture swings both sides: they lose it, we gain it); our or anyone's
  main base VAL_MB (losing it ends the game). Buildings: econ.value_table (flat / per-wind producers of a valued
  resource; a per-wind one counts VAL_WIND levels).
- aimod_aval(a) -> an army's value: its power (aimod_pw, current life) x VAL_PW_K / 1000, calibrated on recruit cost (H_Trooper:
  40 Manpower x 12 = 480 at 43.6k power): a worn army is worth less, an elite more.
- decision record (`_task_record`, called by the claim refresher, rules/tasks.py): the first time one of our
  Military / Defense orders is seen (map `tvr` order -> time), log `tval` (f, k kind, tgt, V target value, A armies'
  value, fc% battle forecast with the order's armies at the target over TVAL_FC_T, n armies). The scorecard sums them
  per kind (value at stake, armies risked, forecast at start). Stage 3 (assignment) ranks tasks with these; until
  then they change no decision.
Fails safe: 0 on error (aimod_sval / aimod_aval), no record."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.econ import value_table, _res_value

VAL_DAYS = 20          # days of production a structure is worth (10 min: a capture's horizon before it flips again)
VAL_VILLAGE_DAY = 20   # Solari-eq / day for a village itself (territory, supply range, hegemony)
VAL_ENEMY = 2          # another faction's structure x this (a capture swings both sides)
VAL_MB = 1000000       # a main base (losing it ends the game)
VAL_SPICE_DAY = 60     # Solari-eq / day for a spice field in the zone (a harvester's take, sold or stockpiled)
VAL_AIW_DAY = 1        # Solari-eq / day per point of the region's aiWeight (special regions 20, the Pole 40: what
                       # the Annex scoring's special bonus prices)
VAL_WIND = 2           # wind levels counted for a per-wind producer (Wind Trap)
VAL_PW_K = 11          # Solari-eq per 1000 power points (H_Trooper: 480 recruit value / 43.6k power; integer math:
                       # _ratio rounds to 1/100 and read 0.011 as 0.01)
TVAL_FC_T = 60         # s: the record's forecast window


def build_sval(cx):
    """aimod_sval(fac, s) -> f64 (see module doc)."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Structure')], cx.t('f64'))
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=res, src=b.const('f64', 0))
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    fb.op('JFalse', cond=b.call('ent.Structure.get_isMainBase', 1), offset='nomb')
    fb.op('Mov', dst=res, src=b.const('f64', VAL_MB))
    fb.op('JAlways', offset='end')
    fb.label('nomb')
    tab = value_table()
    used = sorted({ri for prod, upk in tab.values() for ri, *_ in prod + upk})
    rv = {}
    for ri in used:  # each resource's value once
        rv[ri] = fb.reg(cx.t('f64'))
        _res_value(fb, b, cx, 0, ri, rv[ri])
    tot, f, q = (fb.reg(cx.t('f64')) for _ in range(3))
    fb.op('Mov', dst=tot, src=b.const('f64', 0))
    up = b.field(1, 'upgrades')
    fb.op('JNull', reg=up, offset='sum')
    gk = cx.fn('logic.Upgrades.getKind')
    gkt = [a.value for a in cx.code.types[gk.type.value].definition.args]
    gkn = []
    for t_ in gkt[2:]:
        r_ = fb.reg(t_)
        fb.op('Null', dst=r_)
        gkn.append(r_)
    ku = fb.reg(cx.code.types[gk.type.value].definition.ret.value)
    for kind, (prod, upk) in tab.items():
        nxt = _uid('sv')
        ks = fb.string(kind)
        fb.op('CallN', dst=ku, fun=gk.findex.value, args=[up, ks] + gkn)
        fb.op('JNull', reg=ku, offset=nxt)
        fb.op('Mov', dst=f, src=b.call('logic.Upgrades.getUpgradeFactor', up, ks))
        for ri, amt, wind in prod:
            fb.op('Mul', dst=q, a=rv[ri], b=_ratio(fb, b, amt * (VAL_WIND if wind else 1)))
            fb.op('Mul', dst=q, a=q, b=f)
            fb.op('Add', dst=tot, a=tot, b=q)
        for ri, qty in upk:
            fb.op('Mul', dst=q, a=rv[ri], b=_ratio(fb, b, qty))
            fb.op('Sub', dst=tot, a=tot, b=q)
        fb.label(nxt)
    fb.label('sum')
    fb.op('JSGte', a=tot, b=b.const('f64', 0), offset='pos')
    fb.op('Mov', dst=tot, src=b.const('f64', 0))
    fb.label('pos')
    fb.op('Add', dst=tot, a=tot, b=b.const('f64', VAL_VILLAGE_DAY))
    vz = b.call('ent.Entity.get_zone', 1)
    fb.op('JNull', reg=vz, offset='zdone')
    fb.op('JFalse', cond=b.call('ent.Zone.hasSpice', vz), offset='nosp')
    fb.op('Add', dst=tot, a=tot, b=b.const('f64', VAL_SPICE_DAY))
    fb.label('nosp')
    aw = fb.get(vz, 'inf', 'props', 'aiWeight')
    fb.op('JNull', reg=aw, offset='zdone')
    awf = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=awf, src=aw)
    fb.op('JSLte', a=awf, b=b.const('f64', 0), offset='zdone')
    fb.op('Mul', dst=awf, a=awf, b=b.const('f64', VAL_AIW_DAY))
    fb.op('Add', dst=tot, a=tot, b=awf)
    fb.label('zdone')
    fb.op('Mul', dst=res, a=tot, b=b.const('f64', VAL_DAYS))
    ow = b.call('ent.Entity.get_owner', 1)
    fb.op('JNull', reg=ow, offset='end')
    fb.op('JEq', a=ow, b=0, offset='end')
    fb.op('Mul', dst=res, a=res, b=b.const('f64', VAL_ENEMY))
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    return fb.build()


def build_aval(cx, pw):
    """aimod_aval(a) -> f64 (see module doc)."""
    fb = FB(cx, [cx.t('ent.Army')], cx.t('f64'))
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=res, src=b.const('f64', 0))
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fb.op('Call1', dst=res, fun=pw, arg0=0)
    fb.op('Mul', dst=res, a=res, b=b.const('f64', VAL_PW_K))
    fb.op('SDiv', dst=res, a=res, b=b.const('f64', 1000))
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    return fb.build()


def _task_record(fb, b, cx, helpers, fac, o, t, units, kind, attack, target=None):
    """The decision record of order o (see module doc): once per order (map `tvr`). kind: a Python str or a String
    register; attack: a Python bool (Military: attack, Defense: defend); target: an entity register to value instead
    of the order's target (a Defense: its target is the attacking group, the stake is our structure). Falls through."""
    done = _uid('tvd')
    tvr = _global_map(fb, b, cx, 'tvr')
    fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', tvr, fb.dyn(o)), offset=done)
    b.call('haxe.ds.ObjectMap.set', tvr, fb.dyn(o), fb.dyn(t))
    tg = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=tg, src=target if target is not None else b.call('logic.ai.AIOrder.getTarget', o))
    fb.op('JNull', reg=tg, offset=done)
    v, av, q, fc = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('Mov', dst=v, src=b.const('f64', 0))
    sv = _uid('tvs')
    scl = fb.reg(cx.t('ent.$Structure'))
    fb.op('GetGlobal', dst=scl, **{'global': cx.global_of('ent.$Structure')})
    fb.op('JFalse', cond=b.call('hl.BaseType.check', scl, fb.dyn(tg)), offset=sv + 'a')
    ts = fb.reg(cx.t('ent.Structure'))
    fb.op('SafeCast', dst=ts, src=fb.dyn(tg))
    fb.op('Call2', dst=v, fun=helpers['sval'], arg0=fac, arg1=ts)
    fb.op('JAlways', offset=sv)
    fb.label(sv + 'a')
    acl = fb.reg(cx.t('ent.$Army'))
    fb.op('GetGlobal', dst=acl, **{'global': cx.global_of('ent.$Army')})
    fb.op('JFalse', cond=b.call('hl.BaseType.check', acl, fb.dyn(tg)), offset=sv)
    ta = fb.reg(cx.t('ent.Army'))  # a chase / contest: the prey army
    fb.op('SafeCast', dst=ta, src=fb.dyn(tg))
    fb.op('Call1', dst=v, fun=helpers['aval'], arg0=ta)
    fb.label(sv)
    fb.op('Mov', dst=av, src=b.const('f64', 0))
    j = fb.reg(cx.t('i32'))
    lp = _uid('tva')
    a = _army_loop(fb, b, units, b.field(units, 'length'), j, lp, lp + 'd', transported=True)
    fb.op('Call1', dst=q, fun=helpers['aval'], arg0=a)
    fb.op('Add', dst=av, a=av, b=q)
    fb.op('JAlways', offset=lp)
    fb.label(lp + 'd')
    fa = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=fa, value=bool(attack))
    fb.op('CallN', dst=fc, fun=helpers['forecast'], args=[fac, tg, b.const('f64', TVAL_FC_T), fa, units])
    _log_ev(fb, b, cx, helpers, 'tval', [('f', fb.get(fac, 'kind')), ('k', kind), ('tgt', tg), ('V', v), ('A', av),
                                         ('fc%', fc), ('n', fb.dyn(b.field(units, 'length')))])
    fb.label(done)
