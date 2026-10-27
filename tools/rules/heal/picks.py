"""Army selection: protect healing and retreating armies, and reinforce local defenses."""
from rules.common import *  # noqa: F401,F403
from rules import bkstate as bks


def build_flee_stamp(cx, helpers, new_ids):
    """flee-stamp: every AIUnits.changeArmyMicro call (the ai-log wrapper's when installed) -> wrapper: the original
    call, then for a Flee behaviour map `fled` army -> now. Vanilla's fight retreat sends Resupply only for armies
    with safe regen and force-flees the rest with no order (a local `forceFlee` map): the retreat lock reads the
    stamp (Fremen at Aliftar, match 2026-10-04 20:00: 13 orderless fleeing armies re-picked into a Defense ~100
    times in 1:40)."""
    orig = cx.fn('logic.ai.AIUnits.changeArmyMicro')
    tid = helpers.get('changeArmyMicro', orig.findex.value)
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    names = [c.name.resolve(cx.code) for c in cx.code.types[args[3]].definition.constructs]
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    r = fb.reg(ft.ret.value)
    fb.op('CallN', dst=r, fun=tid, args=list(range(len(args))))
    guard = fb.try_()
    ix = fb.reg(cx.t('i32'))
    fb.op('JNull', reg=3, offset='end')
    fb.op('EnumIndex', dst=ix, value=3)
    fb.op('JNotEq', a=ix, b=b.const('i32', names.index('Flee')), offset='end')
    fb.op('JNull', reg=2, offset='end')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'fled'), fb.dyn(2), fb.dyn(b.field(_state(fb, b, cx), 'time')))
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=r)
    w = fb.build()
    n = 0
    for f in cx.code.functions:
        if f.findex.value in (w, tid):
            continue
        for op in f.ops:
            if op.op.startswith('Call') and op.df.get('fun') is not None and op.df['fun'].value == tid:
                op.df['fun'].value = w
                n += 1
    if not n:
        raise ValueError('flee-stamp: no changeArmyMicro call')
    new_ids.add(w)
    return {'flee-stamp': n}



def pick_life(cx, helpers, idle, new_ids):
    """pick-life: worn armies heal instead of joining missions. Vanilla getUnits applies minLife (0.9) only to armies
    with hasSafeRegen, so a Harkonnen Discovery_Sniper at < 50% that sat in a Resupply order at Tsim-Al'rekh was
    pulled (AIOrder.removeUnit) into a Defense of Talwaz against 2 rebels and died; 25% armies went on Annex /
    Pillage. The getUnits calls of the mission callers (tryArmyAction: sieges, checkStructures: Defense,
    checkWorldEvents: Discovery; not checkUnits = the Resupply query) are wrapped: armies with life ratio < PICK_LIFE
    are removed from the result, unless already fighting (isFighting: at the spot, a Defense coordinates it).
    Worn temporary units (no safe regen: they never heal, and disband soon) still defend our structures, as extras:
    at the main base (Defense query priority >= 10: vanilla sends every idle army) they stay in the list; elsewhere
    the checkStructures pickUnits call is wrapped and, once vanilla's pick of healthy armies is non-empty, idle
    (`idle`: in no order) no-regen armies under PICK_LIFE within JOIN_R of the structure are appended (logged
    `lowpick` src=extra). They are never counted toward the required power.
    Logs `lowpick` (a, hp%, src) once per army per PICK_LOG_T s. Original result on any error."""
    gu = cx.fn('logic.ai.AIUnits.getUnits')
    ftypes = {f.findex.value: f.type.value for f in cx.code.functions}
    ft = cx.code.types[gu.type.value].definition
    n = 0
    wrappers = {}
    for caller, want, tag in (('logic.ai.AIMilitary.tryArmyAction', 1, 'siege'),
                              ('logic.ai.AIMilitary.checkStructures', 1, 'defense'),
                              ('logic.ai.AIController.checkWorldEvents', 2, 'discovery')):
        sites = [op for op in cx.fn(caller).ops if op.op.startswith('Call') and op.df.get('fun') is not None
                 and ftypes.get(op.df['fun'].value) == gu.type.value]
        if len(sites) != want:
            raise ValueError(f'pick-life: expected {want} getUnits calls in {caller}, found {len(sites)}')
        for op in sites:
            key = (op.df['fun'].value, tag)
            if key not in wrappers:
                wrappers[key] = _pick_life_wrapper(cx, helpers, ft, gu.type.value, op.df['fun'].value, tag)
                new_ids.add(wrappers[key])
            op.df['fun'].value = wrappers[key]
            n += 1
    n += _defense_extras(cx, helpers, idle, new_ids)
    return {'pick-life': n}



def _defense_extras(cx, helpers, idle, new_ids):
    pk = cx.fn('logic.ai.AIUnits.pickUnits')
    ftypes = {f.findex.value: f.type.value for f in cx.code.functions}
    sites = [op for op in cx.fn('logic.ai.AIMilitary.checkStructures').ops if op.op.startswith('Call')
             and op.df.get('fun') is not None and ftypes.get(op.df['fun'].value) == pk.type.value]
    if len(sites) != 1:
        raise ValueError(f'pick-life: expected 1 pickUnits call in checkStructures, found {len(sites)}')

    ft = cx.code.types[pk.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=pk.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    # rally: a Defense of a structure within RALLY_MIN of the rally's danger D gets only armies already within
    # RALLY_HERE of D (the rest gather first; a Defense elsewhere gets them: the pick-life getUnits wrapper keeps
    # them in the list)
    guard0 = fb.try_()
    rde, ale = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    alv, _ = _vfield(fb, b, 1, 'allyStructure')
    fb.op('JNull', reg=alv, offset='rk_done')
    fb.op('SafeCast', dst=ale, src=fb.dyn(alv))
    cuv, _ = _vfield(fb, b, 1, 'consideredUnits')
    fb.op('JNull', reg=cuv, offset='rk_done')
    cand = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('SafeCast', dst=cand, src=fb.dyn(cuv))
    # a lost cause: conceded by the rally (map `rlygu` within RALLY_COOL) or judged hopeless by aimod_defend (map `dhl`
    # within 30 s, the window in which the rally pass stops a running Defense of it): no Defense trickle into it
    rgq = fb.reg(cx.t('f64'))
    for mname, lim in (('rlygu', RALLY_COOL), ('dhl', 30)):
        nx = _uid('rkn')
        rgv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, mname), fb.dyn(ale))
        fb.op('JNull', reg=rgv, offset=nx)
        fb.op('SafeCast', dst=rgq, src=rgv)
        fb.op('Sub', dst=rgq, a=b.field(_state(fb, b, cx), 'time'), b=rgq)
        fb.op('JSLt', a=rgq, b=b.const('f64', lim), offset='rk_lost')
        fb.label(nx)
    fb.op('JAlways', offset='rk_live')
    fb.label('rk_lost')
    b.call('hl.types.ArrayObj.splice', cand, b.const('i32', 0), b.field(cand, 'length'))
    fb.op('JAlways', offset='rk_done')
    fb.label('rk_live')
    # committed by the rally (map `rlyc` within RALLY_COOL): the whole army goes (vanilla's allIn: every considered
    # army, not just enough for its own estimate: Harkonnen's Eydak commit counted 11 armies, the Defense took 7, the
    # other 4 were walked back to Rabnih by a Patrol and the defense read even and was conceded 10 s later)
    cmv2 = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rlyc'), fb.dyn(ale))
    fb.op('JNull', reg=cmv2, offset='rk_nc')
    fb.op('SafeCast', dst=rgq, src=cmv2)
    fb.op('Sub', dst=rgq, a=b.field(_state(fb, b, cx), 'time'), b=rgq)
    fb.op('JSGt', a=rgq, b=b.const('f64', RALLY_COOL), offset='rk_nc')
    # ... the army the commit counted: vanilla's idle list has no distance limit (getUnits by life / supply /
    # priority, pickUnits takes the nearest first and stops at its estimate), all-in would pull every idle army of
    # the map off other fronts; keep those within RALLY_R of D (the rally's measure)
    ci = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=ci, src=b.field(cand, 'length'))
    b.loop_head('rk_cut')
    fb.op('JSLte', a=ci, b=b.const('i32', 0), offset='rk_cutd')
    fb.op('Sub', dst=ci, a=ci, b=b.const('i32', 1))
    cu = b.cast(b.call('hl.types.ArrayObj.getDyn', cand, ci), 'ent.Entity')
    fb.op('JNull', reg=cu, offset='rk_cut')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', cu, ale), b=b.const('f64', RALLY_R), offset='rk_cut')
    b.call('hl.types.ArrayObj.splice', cand, ci, b.const('i32', 1))
    fb.op('JAlways', offset='rk_cut')
    fb.label('rk_cutd')
    aiv, aii = _vfield(fb, b, 1, 'allIn')
    tb = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=tb, value=True)
    nb = fb.reg(fb.regs[aiv])
    fb.op('ToDyn', dst=nb, src=tb)  # Null<Bool>, the way the compiler boxes it
    fb.op('SetField', obj=1, field=aii, src=nb)
    owf = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=owf, offset='rk_nc')
    _throttle(fb, b, cx, 'dall', ale, 10, 'rk_nc')
    _log_ev(fb, b, cx, helpers, 'dall', [('f', fb.get(owf, 'kind')), ('s', ale), ('n', b.field(cand, 'length'))])
    fb.label('rk_nc')
    rdz = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rly'), fb.dyn(b.field(b.field(0, 'controller'), 'owner')))
    fb.op('JNull', reg=rdz, offset='rk_done')
    fb.op('SafeCast', dst=rde, src=rdz)
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ale, rde), b=b.const('f64', RALLY_MIN), offset='rk_done')
    rpe = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=rpe)
    rpv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rlyp'), fb.dyn(b.field(b.field(0, 'controller'), 'owner')))
    fb.op('JNull', reg=rpv, offset='rk_np')
    fb.op('SafeCast', dst=rpe, src=rpv)
    fb.label('rk_np')
    rk = fb.reg(cx.t('i32'))
    rnow = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=rnow, src=b.field(_state(fb, b, cx), 'time'))
    fb.op('Mov', dst=rk, src=b.field(cand, 'length'))
    b.loop_head('rk')  # backwards: removal shifts the tail
    fb.op('JSLte', a=rk, b=b.const('i32', 0), offset='rk_done')
    fb.op('Sub', dst=rk, a=rk, b=b.const('i32', 1))
    rv = b.call('hl.types.ArrayObj.getDyn', cand, rk)
    fb.op('JNull', reg=rv, offset='rk')
    # an army already at D (within RALLY_HERE) may defend it; any other (walking to the rally point, or arrived
    # there) waits for the gathered force: Fremen's Defense of Ulmara took 2 armies standing at the rally point
    # Tabr, 285 away, and went in 2 v 6
    rva = b.cast(rv, 'ent.Army')
    fb.op('JNull', reg=rva, offset='rk')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', rva, rde), b=b.const('f64', RALLY_HERE), offset='rk_rm')
    fb.op('JNull', reg=rpe, offset='rk_rp')  # at the rally point (within RALLY_HERE of D too): the gathered force
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', rva, rpe), b=b.const('f64', RALLY_AT), offset='rk_rm')
    fb.label('rk_rp')
    _rallying(fb, b, cx, rva, rnow, 'rk_rm', 'rk')  # walking to the rally point: a live rally claim
    fb.label('rk_rm')
    b.call('hl.types.ArrayObj.remove', cand, rv)
    fb.op('JAlways', offset='rk')
    fb.label('rk_done')
    fb.end_try(guard0)
    # retreat lock: an army in one of our Resupply orders isn't picked for a Defense (prio 5 > Resupply 0, so the pick
    # took it straight back): vanilla's fight retreat cancelled the Defense and sent Resupply, the next checkStructures
    # pass re-picked the same armies, every ~0.5 s (Fremen at Ub-anim, match 2026-10-04 16:35: 50 Defense / Resupply
    # cycles in 23 s, 5 armies rocking in place). Also at an active main base (both stamps; it rejoins after the short lock)
    guard1 = fb.try_()
    lfac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=lfac, offset='rl_done')
    lav, _ = _vfield(fb, b, 1, 'allyStructure')
    fb.op('JNull', reg=lav, offset='rl_done')
    lst = fb.reg(cx.t('ent.Structure'))
    fb.op('SafeCast', dst=lst, src=fb.dyn(lav))
    fb.op('JNull', reg=lst, offset='rl_done')
    lmb = fb.reg(cx.t('bool'))  # an active main base: only the `dwf` test (vanilla refused that Defense itself)
    fb.op('Mov', dst=lmb, src=b.call('ent.Structure.get_isActiveMainBase', lst))
    lcv, _ = _vfield(fb, b, 1, 'consideredUnits')
    fb.op('JNull', reg=lcv, offset='rl_done')
    lcand = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('SafeCast', dst=lcand, src=fb.dyn(lcv))
    fb.op('JNull', reg=lcand, offset='rl_done')
    lk, lidx, lrm = fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Int', dst=lrm, ptr=cx.code.add_i32(0).value)
    lo = fb.reg(cx.t('logic.ai.AIOrder'))
    fb.op('Mov', dst=lk, src=b.field(lcand, 'length'))
    b.loop_head('rl')  # backwards: removal shifts the tail
    fb.op('JSLte', a=lk, b=b.const('i32', 0), offset='rl_end')
    fb.op('Sub', dst=lk, a=lk, b=b.const('i32', 1))
    lu = b.cast(b.call('hl.types.ArrayObj.getDyn', lcand, lk), 'ent.Army')
    fb.op('JNull', reg=lu, offset='rl')
    # force-fled by a fight retreat (no order: flee-stamp map `fled`) within RLOCK_FLEE_T, or in a Defense vanilla
    # cancelled in Waiting (orders.py heal-dead map `dwf`) within DWF_T
    lfq = fb.reg(cx.t('f64'))
    # both stamps also at an active main base (a lone Atreides army lost at its capital, retreated and was re-sent by the
    # prio-10 all-in Defense every 0.5 s, x21 from 14:21, match 2026-10-05 04:38): it rejoins after RLOCK_FLEE_T
    for mname, lim in (('dwf', DWF_T), ('fled', RLOCK_FLEE_T)):
        nx = _uid('rlf')
        lfv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, mname), fb.dyn(lu))
        fb.op('JNull', reg=lfv, offset=nx)
        fb.op('SafeCast', dst=lfq, src=lfv)
        fb.op('Sub', dst=lfq, a=b.field(_state(fb, b, cx), 'time'), b=lfq)
        fb.op('JSLt', a=lfq, b=b.const('f64', lim), offset='rl_rm')
        fb.label(nx)
    # not every army in a Resupply order (that kept 10 healthy Harkonnen armies, sent home by `disengage` after a won
    # fight, out of the committed all-in Defense of Zayur until it fell, match 2026-10-04 21:4x): only the stamps
    fb.op('JAlways', offset='rl')
    fb.label('rl_rm')
    b.call('hl.types.ArrayObj.splice', lcand, lk, b.const('i32', 1))
    fb.op('Incr', dst=lrm)
    fb.op('JAlways', offset='rl')
    fb.label('rl_end')
    fb.op('JSLte', a=lrm, b=b.const('i32', 0), offset='rl_done')
    _throttle(fb, b, cx, 'rlock', lst, 10, 'rl_done')
    _log_ev(fb, b, cx, helpers, 'rlock', [('f', fb.get(lfac, 'kind')), ('s', lst), ('n', lrm)])
    fb.label('rl_done')
    fb.end_try(guard1)
    # pillage / raiders only (user): a structure of ours being pillaged, or attacked by raiders only (no takeover):
    # armies on one of our Military orders (attacks, liberations, raids) aren't recalled to defend it (vanilla's
    # Defense, prio 5, takes them from any lower order); idle ones still defend. Log `dkeep` (s, n)
    guard2 = fb.try_()
    kfac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=kfac, offset='dk_done')
    kav, _ = _vfield(fb, b, 1, 'allyStructure')
    fb.op('JNull', reg=kav, offset='dk_done')
    kst = fb.reg(cx.t('ent.Structure'))
    fb.op('SafeCast', dst=kst, src=fb.dyn(kav))
    fb.op('JNull', reg=kst, offset='dk_done')
    ksg = b.field(kst, 'siege')
    fb.op('JNull', reg=ksg, offset='dk_done')
    # a pillage under way (any attacker; user: the distinction is pillaging vs liberating), or raiders only: no faction
    # besieging / occupying, no at-war army at it, no renegade Takeover (world._renegades_at)
    _pillaging(fb, b, cx, kst, 'dk_go')
    fb.op('JNotNull', reg=b.field(ksg, 'besiegingFaction'), offset='dk_done')
    fb.op('JNotNull', reg=b.call('ent.comp.SiegeComponent.getOccupierFaction', ksg), offset='dk_done')
    kse = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=kse, src=kst)
    ktq = fb.reg(cx.t('f64'))
    fb.op('Call3', dst=ktq, fun=helpers['threat'], arg0=kfac, arg1=kse, arg2=b.const('f64', LOCAL))
    fb.op('JSGt', a=ktq, b=b.const('f64', 0), offset='dk_done')
    from rules.world import _renegades_at
    _renegades_at(fb, b, cx, kst, 'dk_done')
    fb.label('dk_go')
    kcv, _ = _vfield(fb, b, 1, 'consideredUnits')
    fb.op('JNull', reg=kcv, offset='dk_done')
    kcand = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('SafeCast', dst=kcand, src=fb.dyn(kcv))
    fb.op('JNull', reg=kcand, offset='dk_done')
    kk, kix, krm = fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Int', dst=krm, ptr=cx.code.add_i32(0).value)
    ko = fb.reg(cx.t('logic.ai.AIOrder'))
    fb.op('Mov', dst=kk, src=b.field(kcand, 'length'))
    b.loop_head('dk')
    fb.op('JSLte', a=kk, b=b.const('i32', 0), offset='dk_end')
    fb.op('Sub', dst=kk, a=kk, b=b.const('i32', 1))
    ku = b.cast(b.call('hl.types.ArrayObj.getDyn', kcand, kk), 'ent.Army')
    fb.op('JNull', reg=ku, offset='dk')
    # Direct campaign attacks have claims but no Military order. Minor raids must not take those armies either
    # (Altar: a priority-10 rebel defense recalled the capture's 13 armies just after Annex began).
    kh = fb.reg(cx.t('bool'))
    fb.op('Call2', dst=kh, fun=helpers['held'], arg0=ku, arg1=b.const('f64', P_DEFENSE))
    fb.op('JTrue', cond=kh, offset='dk_rm')
    _order_of(fb, b, cx, kfac, ku, ko, 'dk')
    fb.op('EnumIndex', dst=kix, value=b.field(ko, 'type'))
    fb.op('JNotEq', a=kix, b=b.const('i32', MILITARY), offset='dk')
    fb.label('dk_rm')
    b.call('hl.types.ArrayObj.splice', kcand, kk, b.const('i32', 1))
    fb.op('Incr', dst=krm)
    fb.op('JAlways', offset='dk')
    fb.label('dk_end')
    fb.op('JSLte', a=krm, b=b.const('i32', 0), offset='dk_done')
    _throttle(fb, b, cx, 'dkeep', kst, 10, 'dk_done')
    _log_ev(fb, b, cx, helpers, 'dkeep', [('f', fb.get(kfac, 'kind')), ('s', kst), ('n', krm)])
    fb.label('dk_done')
    fb.end_try(guard2)
    fb.op('Call2', dst=res, fun=sites[0].df['fun'].value, arg0=0, arg1=1)
    # forecast gate (user, ARCHITECTURE-PLAN step 1): the Defense goes only if the battle forecast at the structure with
    # every army of ours that can be there within DEF_FC_T (defend; the rally's measure) is at least DEF_GATE; else none
    # go (log `dgate` s, fc%, n) and the rally gathers them or concedes it. Not on vanilla's pick alone (review: the pick
    # stops at vanilla's own small estimate while their side counts everyone who can come, so most defenses read < 1:
    # 39 of 52 Atreides Defenses in match 2026-10-24 10:40). Not at an active main base (always defended), not for a Defense the rally
    # committed (map `rlyc` within RALLY_COOL: it judged the gathered force itself). Neutral raiders aren't in the
    # forecast (FC_NONE): a Defense against rebels / marauders always passes. Harkonnen's 9-army Defense of Aswnun
    # went in at forecast 0.61 against Atreides' Pillage, retreated at balance 0.07 and lost 4-5 armies (match
    # 2026-10-24 late, 5:44-6:15), then a second one at 0.64
    guard3 = fb.try_()
    fb.op('JNull', reg=res, offset='dg_done')
    fb.op('JSLte', a=b.field(res, 'length'), b=b.const('i32', 0), offset='dg_done')
    gav, _ = _vfield(fb, b, 1, 'allyStructure')
    fb.op('JNull', reg=gav, offset='dg_done')
    gst = fb.reg(cx.t('ent.Structure'))
    fb.op('SafeCast', dst=gst, src=fb.dyn(gav))
    fb.op('JNull', reg=gst, offset='dg_done')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isActiveMainBase', gst), offset='dg_done')
    gse = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=gse, src=gst)
    gcv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rlyc'), fb.dyn(gse))
    fb.op('JNull', reg=gcv, offset='dg_nc')
    gq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=gq, src=gcv)
    fb.op('Sub', dst=gq, a=b.field(_state(fb, b, cx), 'time'), b=gq)
    fb.op('JSLte', a=gq, b=b.const('f64', RALLY_COOL), offset='dg_done')
    fb.label('dg_nc')
    gfac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=gfac, offset='dg_done')
    gfa = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=gfa, value=False)
    garr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('SafeCast', dst=garr, src=fb.dyn(res))
    gfc = fb.reg(cx.t('f64'))
    gnul = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=gnul)
    fb.op('CallN', dst=gfc, fun=helpers['forecast'], args=[gfac, gse, b.const('f64', DEF_FC_T), gfa, gnul])
    fb.op('JSGte', a=gfc, b=_ratio(fb, b, DEF_GATE), offset='dg_pick')
    fb.op('JAlways', offset='dg_cut')
    fb.label('dg_pick')
    # the board (shadow) ranks the Defense that goes on its own armies
    fb.op('CallN', dst=gfc, fun=helpers['forecast'], args=[gfac, gse, b.const('f64', DEF_FC_T), gfa, garr])
    fb.label('dg_go')
    # task board (rules/board.py, shadow): the Defense that goes
    _bd = fb.reg(cx.t('bool'))
    _bk = fb.reg(cx.t('String'))
    fb.op('Mov', dst=_bk, src=fb.string('defense'))
    _bT = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=_bT, src=b.const('f64', 0))
    _ba = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Mov', dst=_ba, src=garr)
    _bq = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=_bq, value=True)
    _be = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=_be, src=gse)
    fb.op('CallN', dst=_bd, fun=helpers['board'], args=[gfac, _bk, _be, gfc, _bT, _ba, _bq])
    fb.op('JTrue', cond=_bd, offset='dg_done')  # true = go; false (a live kind yields to a better task): no Defense this pass
    b.call('hl.types.ArrayObj.splice', garr, b.const('i32', 0), b.field(garr, 'length'))
    fb.op('JAlways', offset='dg_done')
    fb.label('dg_cut')
    gn = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=gn, src=b.field(res, 'length'))
    b.call('hl.types.ArrayObj.splice', garr, b.const('i32', 0), b.field(garr, 'length'))
    _throttle(fb, b, cx, 'dgate', gse, 10, 'dg_done')
    _log_ev(fb, b, cx, helpers, 'dgate', [('f', fb.get(gfac, 'kind')), ('s', gse), ('fc%', gfc), ('n', fb.dyn(gn))])
    fb.label('dg_done')
    fb.end_try(guard3)
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    fb.op('JSLte', a=b.field(res, 'length'), b=b.const('i32', 0), offset='end')
    al, _ = _vfield(fb, b, 1, 'allyStructure')
    fb.op('JNull', reg=al, offset='end')
    s = fb.reg(cx.t('ent.Entity'))
    fb.op('SafeCast', dst=s, src=fb.dyn(al))
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    my_armies, mlen = _my_armies(fb, b, fac, 'end')
    i = fb.reg(cx.t('i32'))
    ok = fb.reg(cx.t('bool'))
    floor, r = _ratio(fb, b, PICK_LIFE), b.const('f64', JOIN_R)
    lr = fb.reg(cx.t('f64'))
    a = _army_loop(fb, b, my_armies, mlen, i, 'l', 'end')
    fb.op('JTrue', cond=b.call('ent.Unit.hasSafeRegen', a), offset='l')
    fb.op('Mov', dst=lr, src=b.call('ent.Entity.get_lifeRatio', a))
    fb.op('JSGte', a=lr, b=floor, offset='l')
    fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', res, fb.dyn(a)), offset='l')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', a, s), b=r, offset='l')
    fb.op('Call2', dst=ok, fun=idle, arg0=a, arg1=orders)
    fb.op('JFalse', cond=ok, offset='l')
    b.call('hl.types.ArrayObj.push', res, fb.dyn(a))
    _log_ev(fb, b, cx, helpers, 'lowpick', [('f', fb.get(fac, 'kind')), ('a', a), ('hp%', lr), ('src', 'extra')])
    fb.op('JAlways', offset='l')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    sites[0].df['fun'].value = w
    new_ids.add(w)
    return 1



def _pick_life_wrapper(cx, helpers, ft, fun_type, inner, tag):
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=fun_type)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    if tag == 'defense':
        # a Defense of our structure takes armies by their absolute supply (not `short`: below the walk home while
        # losing supply, below), not vanilla's minSupply 0.9 share: a max-supply rise (Atreides 65 -> 125) left every
        # full-health army at home under 90% and out of the Sandsud Defense. The query args are a fresh object per
        # call (HAI.getDefaultUnitQueryArgs)
        g0 = fb.try_()
        msv, msi = _vfield(fb, b, 1, 'minSupply')
        zs = fb.reg(fb.regs[msv])
        fb.op('ToDyn', dst=zs, src=b.const('f64', 0))
        fb.op('SetField', obj=1, field=msi, src=zs)
        fb.end_try(g0)
    fb.op('Call2', dst=res, fun=inner, arg0=0, arg1=1)
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    zi, one = b.const('i32', 0), b.const('i32', 1)
    floor = _ratio(fb, b, PICK_LIFE)
    lr = fb.reg(cx.t('f64'))
    if tag == 'defense':
        prio = fb.reg(cx.t('i32'))
        fb.op('Mov', dst=prio, src=zi)
        pv, _ = _vfield(fb, b, 1, 'priority')
        if fb.regs[pv] == cx.t('i32'):
            fb.op('Mov', dst=prio, src=pv)
        else:  # Null<Int>
            fb.op('JNull', reg=pv, offset='pdone')
            fb.op('SafeCast', dst=prio, src=fb.dyn(pv))
            fb.label('pdone')
    # task claims (rules/tasks.py): armies held above what this pick asks stay with their task (a siege asks
    # SIEGE_P, a Defense DEFENSE_P, a main-base Defense (priority >= 10) MAINBASE_P, a world event DISC_P)
    ask = fb.reg(cx.t('f64'))
    if tag == 'defense':
        fb.op('Mov', dst=ask, src=b.const('f64', DEFENSE_P))
        fb.op('JSLt', a=prio, b=b.const('i32', 10), offset='askd')
        fb.op('Mov', dst=ask, src=b.const('f64', MAINBASE_P))
        fb.label('askd')
    else:
        fb.op('Mov', dst=ask, src=b.const('f64', SIEGE_P if tag == 'siege' else DISC_P))
    _pick_filter(fb, b, cx, helpers, res, ask, tag, 'pfdone')
    fb.label('pfdone')
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.field(res, 'length'))
    b.loop_head('l')  # backwards: removal shifts the tail
    fb.op('JSLte', a=i, b=zi, offset='end')
    fb.op('Sub', dst=i, a=i, b=one)
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', res, i), 'ent.Army')
    fb.op('JNull', reg=a, offset='l')
    if tag == 'defense':
        # a rallying army is still a defender: the Defense pick drops it only for a structure next to the rally's
        # danger D (_defense_extras); Atreides' Tuo-tar Defense found 0 candidates while all were held for Tuonah
        rlq = fb.reg(cx.t('f64'))
        fb.op('Mov', dst=rlq, src=b.field(_state(fb, b, cx), 'time'))
        _rallying(fb, b, cx, a, rlq, 'nwh', 'nrl')  # walking to the rally point
        fb.label('nrl')
    whr = fb.reg(cx.t('bool'))
    fb.op('Call1', dst=whr, fun=helpers['wormheld'], arg0=a)
    fb.op('JFalse', cond=whr, offset='nwh')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))  # waits on the rock while the worm is near (worm.py)
    _throttle(fb, b, cx, 'whold', a, 10, 'l')
    _log_ev(fb, b, cx, helpers, 'whold', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')), ('a', a),
                                          ('src', tag)])
    fb.op('JAlways', offset='l')
    fb.label('nwh')
    if tag == 'defense':
        shf = b.field(b.field(0, 'controller'), 'owner')
        fb.op('JNull', reg=shf, offset='nshort')
        sh = fb.reg(cx.t('bool'))
        fb.op('Call2', dst=sh, fun=helpers['short'], arg0=shf, arg1=a)
        fb.op('JFalse', cond=sh, offset='nshort')
        b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
        _throttle(fb, b, cx, 'lowpick', a, PICK_LOG_T, 'l')
        _log_ev(fb, b, cx, helpers, 'lowpick', [('f', fb.get(shf, 'kind')), ('a', a),
                                                ('hp%', b.call('ent.Entity.get_lifeRatio', a)), ('src', 'short')])
        fb.op('JAlways', offset='l')
        fb.label('nshort')
        # main base (priority >= 10): vanilla skips pickUnits there (selected = this idle list), so the retreat lock
        # of _defense_extras never sees it; the stamps apply here (Harkonnen prio-10 Defense of 8 armies cancelled
        # by the retreat x31 every ~1 s, 43:56-44:03, match 2026-10-05 05:22). Log `mblock` (a)
        fb.op('JSLt', a=prio, b=b.const('i32', 10), offset='nmbl')
        mq = fb.reg(cx.t('f64'))
        for mname, lim in (('dwf', DWF_T), ('fled', RLOCK_FLEE_T)):
            nx = _uid('mbl')
            mv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, mname), fb.dyn(a))
            fb.op('JNull', reg=mv, offset=nx)
            fb.op('SafeCast', dst=mq, src=mv)
            fb.op('Sub', dst=mq, a=b.field(_state(fb, b, cx), 'time'), b=mq)
            fb.op('JSLt', a=mq, b=b.const('f64', lim), offset='mbl_rm')
            fb.label(nx)
        fb.op('JAlways', offset='nmbl')
        fb.label('mbl_rm')
        b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
        _throttle(fb, b, cx, 'mblock', a, 10, 'l')
        _log_ev(fb, b, cx, helpers, 'mblock', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')), ('a', a)])
        fb.op('JAlways', offset='l')
        fb.label('nmbl')
    if tag in ('siege', 'defense'):
        # the last army of one of our Military orders in Action finishes an occupation alone (rules/release.py split
        # the rest off): taking it empties the order (removeUnit cancels it). A main-base defense still may
        kords = b.field(b.field(b.field(0, 'controller'), 'aiOrders'), 'orders')
        fb.op('JNull', reg=kords, offset='nkeep')
        if tag == 'defense':
            fb.op('JSGte', a=prio, b=b.const('i32', 10), offset='nkeep')
        kk, kx = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
        fb.op('Mov', dst=kk, src=b.field(kords, 'length'))
        b.loop_head('kp')
        fb.op('JSLte', a=kk, b=zi, offset='nkeep')
        fb.op('Sub', dst=kk, a=kk, b=one)
        ko = b.cast(b.call('hl.types.ArrayObj.getDyn', kords, kk), 'logic.ai.AIOrder')
        fb.op('JNull', reg=ko, offset='kp')
        kou = b.field(ko, 'units')
        fb.op('JNull', reg=kou, offset='kp')
        fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', kou, fb.dyn(a)), offset='kp')
        fb.op('EnumIndex', dst=kx, value=b.field(ko, 'type'))
        fb.op('JNotEq', a=kx, b=b.const('i32', MILITARY), offset='nkeep')
        fb.op('JSGt', a=b.field(kou, 'length'), b=one, offset='nkeep')
        fb.op('JSLt', a=b.field(ko, 'phase'), b=b.const('i32', ACTION), offset='nkeep')
        b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
        fb.op('JAlways', offset='l')
        fb.label('nkeep')
    # (a siege launch taking an army of another order before Action cancels that order: the task claims hold every
    # order's armies above SIEGE_P, rules/tasks.py; was the `keepord` lock here)
    fb.op('Mov', dst=lr, src=b.call('ent.Entity.get_lifeRatio', a))
    fb.op('JSGte', a=lr, b=floor, offset='l')
    if tag == 'defense':  # in a fight at the spot: a Defense coordinates it. An offensive pick never takes a worn
        # army, fighting or not: one limping home under fire counts as fighting (Smugglers' worn army, sent to heal at
        # Damnin by the drain split, was taken from its Resupply into the Annex of Lar-Al'mara at 66:16 and walked
        # back out; user, match 2026-10-23 20:1x)
        fb.op('JTrue', cond=b.call('ent.Entity.isFighting', a), offset='l')
    if tag == 'defense':  # main base defense (priority >= 10) takes every idle army: worn temporary units too
        fb.op('JTrue', cond=b.call('ent.Unit.hasSafeRegen', a), offset='rm')
        fb.op('JSGte', a=prio, b=b.const('i32', 10), offset='l')
        fb.label('rm')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
    _throttle(fb, b, cx, 'lowpick', a, PICK_LOG_T, 'l')
    _log_ev(fb, b, cx, helpers, 'lowpick', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')), ('a', a),
                                            ('hp%', lr), ('src', tag)])
    fb.op('JAlways', offset='l')
    fb.label('end')
    if tag == 'siege':
        # map `sidle` faction -> size of this idle list: empty = vanilla's NoAvailableArmy (tryArmyAction), which
        # the stuck counter (siege.py) must not blame on the target
        sn = fb.reg(cx.t('i32'))
        fb.op('Mov', dst=sn, src=b.const('i32', 0))  # fresh load: `zi` is set after the JNull to 'end'
        fb.op('JNull', reg=res, offset='sidset')
        fb.op('Mov', dst=sn, src=b.field(res, 'length'))
        fb.label('sidset')
        b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'sidle'),
               fb.dyn(b.field(b.field(0, 'controller'), 'owner')), fb.dyn(sn))
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    return fb.build()



def no_regen_heal(cx, helpers, new_ids):
    """no-regen-heal: vanilla checkUnits orders Resupply(1,1) for any army with life < AI_UnitLife_LowValue (0.9), but
    the order's termination test (closure f40841) checks life only when `hasSafeRegen()` (attribute
    SafeRegen_MRatio > 0, no NoSafeRegen): temporary units (Discovery_* recruits: Temporary_Trait, Scavenged
    ornithopters, NoHealthRegen, H_Sting) never recover life, so with full supply the order ends Success in phase 1
    and is re-issued every tick (Harkonnen Discovery_Sniper < 50% cycling Tsim-Al'rekh / Carthag / Burron every
    ~0.5 s and never moving). The checkUnits getUnits call that feeds the Resupply loop (the second one; the first is
    the upkeep disband) is wrapped: armies without safe regen whose supply needs nothing (no supply, or supply >=
    AI_UnitSupply_LowValue) are removed from the result; one that needs supply still gets its Resupply (it ends once
    refilled). Also removed: an army above the life trigger that gains supply where it stands (Army.isGainingSupply):
    its Resupply would only hold it there (logs `selfsup` a, sup, ms). Logs `noregen` (a, hp%) once per army per
    PICK_LOG_T s. Original result on any error."""
    gu = cx.fn('logic.ai.AIUnits.getUnits')
    ftypes = {f.findex.value: f.type.value for f in cx.code.functions}
    ft = cx.code.types[gu.type.value].definition
    sites = [op for op in cx.fn('logic.ai.AIUnits.checkUnits').ops if op.op.startswith('Call')
             and op.df.get('fun') is not None and ftypes.get(op.df['fun'].value) == gu.type.value]
    if len(sites) != 2:
        raise ValueError(f'no-regen-heal: expected 2 getUnits calls in checkUnits, found {len(sites)}')
    site = sites[1]
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=gu.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('Call2', dst=res, fun=site.df['fun'].value, arg0=0, arg1=1)
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    # supply trigger AI_UnitSupply_LowValue (0.9 if unreadable)
    sup_t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=sup_t, src=_ratio(fb, b, 0.9))
    c = fb.reg(cx.t('$Const'))
    fb.op('GetGlobal', dst=c, **{'global': cx.global_of('$Const')})
    vc = b.cast(b.field(c, 'valueCache'), 'hl.types.ArrayBytes_Float')
    fb.op('JNull', reg=vc, offset='vc_done')
    v = b.call('hl.types.ArrayBytes_Float.getDyn', vc, b.const('i32', const_index('AI_UnitSupply_LowValue')))
    fb.op('JNull', reg=v, offset='vc_done')
    fb.op('SafeCast', dst=sup_t, src=v)
    fb.label('vc_done')
    life_t = fb.reg(cx.t('f64'))  # life trigger AI_UnitLife_LowValue (0.9 if unreadable)
    fb.op('Mov', dst=life_t, src=_ratio(fb, b, 0.9))
    fb.op('JNull', reg=vc, offset='lt_done')
    lv = b.call('hl.types.ArrayBytes_Float.getDyn', vc, b.const('i32', const_index('AI_UnitLife_LowValue')))
    fb.op('JNull', reg=lv, offset='lt_done')
    fb.op('SafeCast', dst=life_t, src=lv)
    fb.label('lt_done')
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.field(res, 'length'))
    zi, one = b.const('i32', 0), b.const('i32', 1)
    full = _ratio(fb, b, 1)
    sr = fb.reg(cx.t('f64'))
    b.loop_head('l')
    fb.op('JSLte', a=i, b=zi, offset='end')
    fb.op('Sub', dst=i, a=i, b=one)
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', res, i), 'ent.Army')
    fb.op('JNull', reg=a, offset='l')
    whr = fb.reg(cx.t('bool'))
    fb.op('Call1', dst=whr, fun=helpers['wormheld'], arg0=a)
    fb.op('JFalse', cond=whr, offset='nwh')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))  # waits on the rock while the worm is near (worm.py)
    _throttle(fb, b, cx, 'whold', a, 10, 'l')
    _log_ev(fb, b, cx, helpers, 'whold', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')), ('a', a),
                                          ('src', 'resupply')])
    fb.op('JAlways', offset='l')
    fb.label('nwh')
    # a direct-raze army (rules/bkill.py map `bcdk`: sent by the base-kill campaign within DR_HOLD_T s) stays in the
    # attack: vanilla resupplies any idle army below AI_UnitSupply_LowValue / AI_UnitLife_LowValue 0.9, and an
    # orderless raze army is idle whenever it isn't shooting (match 53: Fremen's 13 and Smugglers' 10 at Arrakeen left
    # one by one on Resupply orders within ~150 s, few died, base 100 -> 89%). Our drop at the attack refills it
    # (rules/sdrop.py). Only a starving (< DR_HOLD_SUP supply) or dying (< LIFE_CRIT life) one goes. Logs `stay` why
    # raze
    # only an army that left with a wave (`bcdpa` within DR_WAVE_T s): one still gathering may refill (user
    # 2026-10-25: Harkonnen's starving armies were kept from resupplying and turned back bleeding)
    dkwq = bks.wave_left(fb, b, cx, a, 'dk_go')
    # ... of its faction's current go (bkill `bcgt` faction -> go time; review 2026-10-25: one from the last go was held)
    dkg = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.GO_TIME), fb.dyn(b.call('ent.Entity.get_owner', a)))
    fb.op('JNull', reg=dkg, offset='dk_go')
    dkgq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=dkgq, src=dkg)
    fb.op('JSLt', a=dkwq, b=dkgq, offset='dk_go')
    fb.op('Sub', dst=dkwq, a=b.field(_state(fb, b, cx), 'time'), b=dkwq)
    fb.op('JSGt', a=dkwq, b=b.const('f64', DR_WAVE_T), offset='dk_go')
    dkv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.SENT), fb.dyn(a))
    fb.op('JNull', reg=dkv, offset='dk_go')
    dkq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=dkq, src=dkv)
    fb.op('Sub', dst=dkq, a=b.field(_state(fb, b, cx), 'time'), b=dkq)
    fb.op('JSGt', a=dkq, b=b.const('f64', DR_HOLD_T), offset='dk_go')
    fb.op('JSLt', a=b.call('ent.Entity.get_lifeRatio', a), b=_ratio(fb, b, LIFE_CRIT), offset='dk_go')
    _supply_share(fb, b, cx, a, 'dk_hold', q=dkq)
    fb.op('JSLt', a=dkq, b=_ratio(fb, b, DR_HOLD_SUP), offset='dk_go')
    fb.label('dk_hold')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
    _throttle(fb, b, cx, 'stay', a, 30, 'l')
    _log_ev(fb, b, cx, helpers, 'stay', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')), ('a', a),
                                         ('hp%', b.call('ent.Entity.get_lifeRatio', a)), ('why', 'raze')])
    fb.op('JAlways', offset='l')
    fb.label('dk_go')
    # doomed (the fight retreat's measure): on hostile land, its supply can't pay the walk to our land (< SUP_WALK x
    # aimod_land) and the dry stretch is at least DRY_DEATH_D x its health ratio: walking home kills it. With at-war
    # armies within FLEE_R it isn't sent off alone (it stays with its order / stack; the fight retreat decides for the
    # whole stack, and holds doomed ones in). User: Atreides' 8 starved armies at Harkonnen's Aswnun were sent home one
    # by one to Runkus 350 away and 6 died walking through Harkonnen's army while the fight there read 2.7 (match
    # 2026-10-24 late, 6:07-6:19). Logs `stay` (a, hp%, why doomed)
    dmo = b.call('ent.Entity.get_owner', a)
    fb.op('JNull', reg=dmo, offset='dm_go')
    fb.op('JFalse', cond=b.call('ent.Army.isInHostileZone', a), offset='dm_go')
    dme = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=dme, src=a)
    dneed, dsup, dlim = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Call2', dst=dneed, fun=helpers['land'], arg0=dmo, arg1=dme)
    fb.op('JSGte', a=dneed, b=b.const('f64', 1 << 29), offset='dm_go')  # no land of ours (2^30): no measure (review)
    fb.op('Mul', dst=dneed, a=dneed, b=_ratio(fb, b, SUP_WALK))
    fb.op('Mov', dst=dsup, src=b.call('ent.Army.get_supply', a))
    fb.op('JSGte', a=dsup, b=dneed, offset='dm_go')  # can pay the walk
    fb.op('Sub', dst=dsup, a=dneed, b=dsup)
    fb.op('SDiv', dst=dsup, a=dsup, b=_ratio(fb, b, SUP_WALK))  # the dry stretch
    fb.op('Mul', dst=dlim, a=b.call('ent.Entity.get_lifeRatio', a), b=b.const('f64', DRY_DEATH_D))
    fb.op('JSLt', a=dsup, b=dlim, offset='dm_go')
    fb.op('Call3', dst=dlim, fun=helpers['threat'], arg0=dmo, arg1=dme, arg2=b.const('f64', FLEE_R))
    fb.op('JSLte', a=dlim, b=b.const('f64', 0), offset='dm_go')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
    _throttle(fb, b, cx, 'stay', a, 30, 'l')
    _log_ev(fb, b, cx, helpers, 'stay', [('f', fb.get(dmo, 'kind')), ('a', a),
                                         ('hp%', b.call('ent.Entity.get_lifeRatio', a)), ('why', 'doomed')])
    fb.op('JAlways', offset='l')
    fb.label('dm_go')
    # in a fight: one Resupply per RS_GAP s at most (map `rsq` army -> last handed out). Micro keeps a fighting army
    # shooting, its Resupply stalls in Regroup and is cancelled, and checkUnits issued a new one every ~2 s (Smugglers
    # at Sin-nin vs a powerless target, 52:10-52:38, user: "clicked like crazy"; progress open issue "Resupply out of a
    # fight"); the fight retreat is what pulls an army out of a fight
    fb.op('JFalse', cond=b.call('ent.Entity.isFighting', a), offset='nrsq')
    # stay with the stack: an army in a fight above LIFE_CRIT life with another of ours fighting within LOCAL isn't
    # sent off alone to heal (user: armies running away lose more than fighting; match 2026-10-24 late: 47 armies
    # died on their way to heal vs 41 on missions; Fremen's landed Annex of Tab-anim bled away one by one). A real
    # retreat is the fight retreat's, for the whole stack. Logs `stay` (a, hp%) per army per 30 s
    fb.op('JSLt', a=b.call('ent.Entity.get_lifeRatio', a), b=_ratio(fb, b, LIFE_CRIT), offset='st_go')
    sto = b.call('ent.Entity.get_owner', a)
    fb.op('JNull', reg=sto, offset='st_go')
    # ... and only while at-war armies are within LOCAL: a fight with structures only (a village's turrets / guns)
    # holds nobody (user 2026-10-25: after Atreides' Pillage of Arsnin was cancelled its armies idled under the
    # village's guns in Fremen land, `stay` rows, en 0)
    sth = fb.reg(cx.t('f64'))
    ste = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ste, src=a)
    fb.op('Call3', dst=sth, fun=helpers['threat'], arg0=sto, arg1=ste, arg2=b.const('f64', LOCAL))
    fb.op('JSLte', a=sth, b=b.const('f64', 0), offset='st_go')
    sarr, salen = _my_armies(fb, b, sto, 'st_go')
    sti = fb.reg(cx.t('i32'))
    so_ = _army_loop(fb, b, sarr, salen, sti, 'st_l', 'st_go')
    fb.op('JEq', a=so_, b=a, offset='st_l')
    fb.op('JFalse', cond=b.call('ent.Entity.isFighting', so_), offset='st_l')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', so_, a), b=b.const('f64', LOCAL), offset='st_l')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
    _throttle(fb, b, cx, 'stay', a, 30, 'l')
    _log_ev(fb, b, cx, helpers, 'stay', [('f', fb.get(sto, 'kind')), ('a', a),
                                         ('hp%', b.call('ent.Entity.get_lifeRatio', a))])
    fb.op('JAlways', offset='l')
    fb.label('st_go')
    rqm = _global_map(fb, b, cx, 'rsq')
    rqt = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=rqt, src=b.field(_state(fb, b, cx), 'time'))
    rq0 = _age(fb, b, cx, rqm, a, rqt, 'rqok')
    fb.op('JSGte', a=rq0, b=b.const('f64', RS_GAP), offset='rqok')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
    _throttle(fb, b, cx, 'rsloop', a, 30, 'l')
    _log_ev(fb, b, cx, helpers, 'rsloop', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')), ('a', a)])
    fb.op('JAlways', offset='l')
    fb.label('rqok')
    b.call('haxe.ds.ObjectMap.set', rqm, fb.dyn(a), fb.dyn(rqt))
    fb.label('nrsq')
    # supply only (life above the trigger) and refilling where it stands (Army.isGainingSupply: not fighting, a
    # supplying structure in its zone or a neighbour): the order would only hold it there, out of every defense
    # (Atreides' 6 armies at Sandkus, 82/125 after a max-supply rise, in Resupply while Harkonnen took Sandsud)
    fb.op('JSLt', a=b.call('ent.Entity.get_lifeRatio', a), b=life_t, offset='ngain')
    fb.op('JFalse', cond=b.call('ent.Army.isGainingSupply', a), offset='ngain')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
    _throttle(fb, b, cx, 'selfsup', a, PICK_LOG_T, 'l')
    _log_ev(fb, b, cx, helpers, 'selfsup', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')), ('a', a),
                                            ('sup', b.call('ent.Army.get_supply', a)),
                                            ('ms', b.call('ent.Army.get_maxSupply', a))])
    fb.op('JAlways', offset='l')
    fb.label('ngain')
    fb.op('JTrue', cond=b.call('ent.Unit.hasSafeRegen', a), offset='l')
    lr = b.call('ent.Entity.get_lifeRatio', a)
    fb.op('JSGte', a=lr, b=full, offset='l')
    fb.op('JFalse', cond=b.call('ent.Army.hasSupply', a), offset='drop')
    ms = b.call('ent.Army.get_maxSupply', a)
    fb.op('JSLte', a=ms, b=b.const('f64', 0), offset='drop')
    fb.op('SDiv', dst=sr, a=b.call('ent.Army.get_supply', a), b=ms)
    fb.op('JSLt', a=sr, b=sup_t, offset='l')  # needs supply: vanilla's Resupply refills it and ends
    fb.label('drop')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
    _throttle(fb, b, cx, 'noregen', a, PICK_LOG_T, 'l')
    _log_ev(fb, b, cx, helpers, 'noregen', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')), ('a', a),
                                            ('hp%', lr)])
    fb.op('JAlways', offset='l')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    site.df['fun'].value = w
    new_ids.add(w)
    return {'no-regen-heal': 1}
