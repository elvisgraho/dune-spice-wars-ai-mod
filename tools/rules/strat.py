"""Strategic director (AI-POLICY §5b): one bird's-eye look per faction every START s decides the posture, and while
pressing, which weak enemy village the spare armies take.

Vanilla never compares "take the weakly held enemy village next door" with "annex a far neutral one": enemy villages
are candidates only for the daily diplomatic target (Diplomacy.desiredStatus >= 1) and above aggressiveness 50, and
every "no candidate" shrinks the Annexation gauge (x0.85), so once neutral land ran out the armies idled for minutes
(testbed: aggressiveness 100, zero enemy villages targeted, Annexation:Invalid 59-140x per faction).

Picture: S = spare power (our armies free for an offensive: raid-ready, not fighting) minus the home need (ENTER x
hostile armies within HOME_R of our land / OWN_T); T = our total army power. Postures, first match wins:
1 defend (our structure besieged), 3 press (a running press is judged first: its armies aren't spare any more),
2 hold (no spare force for a new target: busy, healing or needed at home), 3 press (a new soft target), 4 expand
(vanilla has neutral Annex candidates), 5 harass (none: raid / hunt are the tools).
Press: an at-war faction's village within FRONT_R of our land, not a main base, not besieged, without our own
Underworld HQ, whose owner's army power <= ours (never poke the stronger side), and soft: the spare armies within
PRESS_R x terrain have PRESS x (armies in reach + enemy cover + militia). Nearest soft village wins (utility ranking
is a later step). Mode annex if the village is in supply range, Annex is available and we can pay it, else pillage
if available. The press holds until: the village changes owner (done / gone) or can't be
attacked any more (done: pillaged = Devastated), truce, PRESS_MAX s (`slow`), or our
power there (any task, + cover) x terrain < PRESS_KEEP x their side (`weak`); a dropped target is skipped for
PRESS_RETRY s and our Military orders on it are cancelled (vanilla would keep a lost siege going).
The levers (strat_levers, scores in siege.build_scoring, raid) read the press maps: spv faction -> village,
spf -> its owner, spa -> annex mode, spt -> start time. Annex mode also lifts the Annexation gauge to GAUGE_FIRE so
vanilla tries it now.
Logs `strat` on every posture / target change and at least every STRAT_LOG s: post, S, need, T, tgt, mode, hold,
reach, war = [{f, ds (desiredStatus toward it), pw (its army power)}] per at-war faction; `strat` act drop on a
dropped press (why done | gone | truce | slow | weak). Fails safe: in a trap."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

POSTURES = ('', 'defend', 'hold', 'press', 'expand', 'harass')


def build_fpow(cx, pw):
    """aimod_fpow(f) -> power of faction f's combat armies (no militia, harvesters, transported, dead)."""
    fb = FB(cx, [cx.t('ent.Faction')], cx.t('f64'))
    b = B(fb)
    tot = b.const('f64', 0)
    fb.op('JNull', reg=0, offset='end')
    arr, alen = _my_armies(fb, b, 0, 'end')
    i, p = fb.reg(cx.t('i32')), fb.reg(cx.t('f64'))
    x = _army_loop(fb, b, arr, alen, i, 'loop', 'end')
    fb.op('JNotNull', reg=b.field(x, 'harvestComponent'), offset='loop')
    fb.op('Call1', dst=p, fun=pw, arg0=x)
    fb.op('Add', dst=tot, a=tot, b=p)
    fb.op('JAlways', offset='loop')
    fb.label('end')
    fb.op('Ret', ret=tot)
    return fb.build()


def _has_action(fb, b, cx, s, fac, name, yes, no):
    """Jump to `yes` if `name` is among s.siege.getAvailableOccupationActions(fac), else to `no`."""
    sg = b.field(s, 'siege')
    fb.op('JNull', reg=sg, offset=no)
    acts = b.call('ent.comp.SiegeComponent.getAvailableOccupationActions', sg, fac)
    fb.op('JNull', reg=acts, offset=no)
    n = b.field(acts, 'length')
    i = b.const('i32', 0)
    key = fb.dyn(fb.string(name))
    lbl = _uid('act')
    b.loop_head(lbl)
    fb.op('JSGte', a=i, b=n, offset=no)
    a_s = b.cast(b.call('hl.types.ArrayObj.getDyn', acts, i), 'String')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=a_s, offset=lbl)
    fb.op('JNotEq', a=b.call('String.__compare', a_s, key), b=b.const('i32', 0), offset=lbl)
    fb.op('JAlways', offset=yes)


def build_strat(cx, helpers, pw, fpow, raidable, react, land, terrain, cover, defend, militia, home):
    """aimod_strat(mil, dt) (see module doc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    state = _state(fb, b, cx)
    t = b.field(state, 'time')
    _tick(fb, b, cx, t, START, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    villages = b.field(state, 'villages')
    fb.op('JNull', reg=villages, offset='end')
    vn = b.field(villages, 'length')
    my_armies, mlen = _my_armies(fb, b, fac, 'end')
    spv, spf, spa, spt = (_global_map(fb, b, cx, n) for n in ('spv', 'spf', 'spa', 'spt'))
    sfail, spost, stgt = (_global_map(fb, b, cx, n) for n in ('sfail', 'spost', 'stgt'))

    zi, zero, big, one = b.const('i32', 0), b.const('f64', 0), b.const('f64', 1 << 30), b.const('i32', 1)
    local, press_r, front_r = b.const('f64', LOCAL), b.const('f64', PRESS_R), b.const('f64', FRONT_R)
    enter, own_t = _ratio(fb, b, ENTER), _ratio(fb, b, OWN_T)
    press, keep = _ratio(fb, b, PRESS), _ratio(fb, b, PRESS_KEEP)
    t_false, t_true = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_false, value=False)
    fb.op('Bool', dst=t_true, value=True)
    no_arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=no_arr)
    i, j, idx, post = (fb.reg(cx.t('i32')) for _ in range(4))
    S, T, need, p, q, r, h, m, tf, d, dm, et, age = (fb.reg(cx.t('f64')) for _ in range(13))
    hold, reach = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    ok, annex = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    ve, tgt, ye = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    pv = fb.reg(cx.t('ent.Structure'))
    pf = fb.reg(cx.t('ent.Faction'))
    why = fb.reg(cx.t('String'))
    fb.op('Null', dst=tgt)
    fb.op('Mov', dst=hold, src=zero)
    fb.op('Mov', dst=reach, src=zero)
    fb.op('Mov', dst=age, src=zero)
    fb.op('Bool', dst=annex, value=False)

    def cover_at(dst, at, own):
        fb.op('CallN', dst=dst, fun=cover, args=[fac, at, at, t_true if own else t_false, no_arr])

    def their_side(dst, s):
        """dst = at-war armies in reach + enemy turret cover + militia at structure s (entity in ve)."""
        fb.op('Call3', dst=dst, fun=react, arg0=fac, arg1=ve, arg2=local)
        cover_at(q, ve, False)
        fb.op('Add', dst=dst, a=dst, b=q)
        fb.op('Call1', dst=q, fun=militia, arg0=s)
        fb.op('Add', dst=dst, a=dst, b=q)

    def clear_press():
        for mp in (spv, spf, spa, spt):
            b.call('haxe.ds.ObjectMap.remove', mp, fb.dyn(fac))

    # ---- picture: spare power (free for an offensive, minus the home need) and our total
    fb.op('Mov', dst=S, src=zero)
    fb.op('Mov', dst=T, src=zero)
    y = _army_loop(fb, b, my_armies, mlen, j, 'sp', 'spdone')
    fb.op('JNotNull', reg=b.field(y, 'harvestComponent'), offset='sp')
    fb.op('Call1', dst=p, fun=pw, arg0=y)
    fb.op('Add', dst=T, a=T, b=p)
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', y), offset='sp')
    fb.op('Call2', dst=ok, fun=raidable, arg0=y, arg1=orders)
    fb.op('JFalse', cond=ok, offset='sp')
    fb.op('Add', dst=S, a=S, b=p)
    fb.op('JAlways', offset='sp')
    fb.label('spdone')
    fb.op('Call2', dst=need, fun=home, arg0=fac, arg1=b.const('f64', HOME_R))
    fb.op('Mul', dst=need, a=need, b=enter)
    fb.op('SDiv', dst=need, a=need, b=own_t)
    fb.op('Sub', dst=S, a=S, b=need)

    # ---- 1 defend: no press
    fb.op('Mov', dst=post, src=one)
    dfs = fb.reg(cx.t('ent.Structure'))
    fb.op('Call1', dst=dfs, fun=defend, arg0=fac)
    fb.op('JNotNull', reg=dfs, offset='nopress')

    # ---- 3 press: keep the current target while it holds (before the spare test: its armies are busy now)
    fb.op('Mov', dst=post, src=b.const('i32', 3))
    cur = b.call('haxe.ds.ObjectMap.get', spv, fb.dyn(fac))
    fb.op('JNull', reg=cur, offset='find')
    fb.op('Mov', dst=pv, src=b.cast(cur, 'ent.Structure'))
    fb.op('Mov', dst=pf, src=b.cast(b.call('haxe.ds.ObjectMap.get', spf, fb.dyn(fac)), 'ent.Faction'))
    fb.op('JNull', reg=pv, offset='find')
    fb.op('Mov', dst=ve, src=pv)
    fb.op('Mov', dst=tgt, src=pv)
    fb.op('SafeCast', dst=annex, src=b.call('haxe.ds.ObjectMap.get', spa, fb.dyn(fac)))
    po = b.call('ent.Entity.get_owner', ve)
    fb.op('Mov', dst=why, src=fb.string('done'))
    fb.op('JEq', a=po, b=fac, offset='drop_quiet')  # ours now
    fb.op('Mov', dst=why, src=fb.string('gone'))
    fb.op('JNotEq', a=po, b=pf, offset='drop_quiet')  # someone else took it
    fb.op('JNull', reg=pf, offset='drop_quiet')
    fb.op('Mov', dst=why, src=fb.string('truce'))
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, pf), offset='drop')
    fb.op('Mov', dst=why, src=fb.string('gone'))
    psg = b.field(pv, 'siege')
    fb.op('JNull', reg=psg, offset='drop_quiet')
    bf = b.field(psg, 'besiegingFaction')
    fb.op('JNull', reg=bf, offset='pfree')
    fb.op('JNotEq', a=bf, b=fac, offset='drop_quiet')  # another faction besieges it
    fb.label('pfree')
    fb.op('Mov', dst=why, src=fb.string('done'))
    fb.op('JFalse', cond=b.call('ent.Entity.canBeAttacked', ve, fac), offset='drop_quiet')  # pillaged: Devastated
    fb.op('SafeCast', dst=age, src=b.call('haxe.ds.ObjectMap.get', spt, fb.dyn(fac)))
    fb.op('Sub', dst=age, a=t, b=age)
    fb.op('Mov', dst=why, src=fb.string('slow'))
    fb.op('JSGt', a=age, b=b.const('f64', PRESS_MAX), offset='drop')
    # keep: our power there (any task: the siege armies are busy) + our cover vs their side
    cover_at(reach, ve, True)
    y = _army_loop(fb, b, my_armies, mlen, j, 'kp', 'kpdone')
    fb.op('JNotNull', reg=b.field(y, 'harvestComponent'), offset='kp')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', y, ve), b=press_r, offset='kp')
    fb.op('Call1', dst=p, fun=pw, arg0=y)
    fb.op('Add', dst=reach, a=reach, b=p)
    fb.op('JAlways', offset='kp')
    fb.label('kpdone')
    their_side(hold, pv)
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', ve))
    fb.op('Mul', dst=q, a=reach, b=tf)
    fb.op('Mul', dst=r, a=hold, b=keep)
    fb.op('Mov', dst=why, src=fb.string('weak'))
    fb.op('JSLt', a=q, b=r, offset='drop')
    fb.op('JAlways', offset='pressing')

    # drop: cancel our Military orders on it (a lost / stale siege), skip it for PRESS_RETRY s, log
    fb.label('drop')
    reason = cx.code.types[cx.fn('logic.ai.AIOrder.stop').type.value].definition.args[1].value
    cancel = fb.reg(reason)
    fb.op('MakeEnum', dst=cancel, construct=CANCEL, args=[])
    fb.op('Mov', dst=i, src=b.field(orders, 'length'))
    b.loop_head('co')
    fb.op('JSLte', a=i, b=zi, offset='codone')
    fb.op('Sub', dst=i, a=i, b=one)
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, i), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset='co')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='co')
    ott = b.field(o, 'targetType')
    fb.op('JNull', reg=ott, offset='co')
    fb.op('EnumIndex', dst=idx, value=ott)
    fb.op('JNotEq', a=idx, b=b.const('i32', T_STRUCT), offset='co')
    fb.op('JNotEq', a=b.call('logic.ai.AIOrder.getTarget', o), b=ve, offset='co')
    b.call('logic.ai.AIOrder.stop', o, cancel)
    fb.op('JAlways', offset='co')
    fb.label('codone')
    b.call('haxe.ds.ObjectMap.set', sfail, fb.dyn(ve), fb.dyn(t))
    fb.label('drop_quiet')
    clear_press()
    _log_ev(fb, b, cx, helpers, 'strat', [('f', fb.get(fac, 'kind')), ('act', 'drop'), ('why', why), ('tgt', ve),
                                          ('age', age), ('hold', hold), ('reach', reach)])
    fb.op('Null', dst=tgt)
    fb.op('Mov', dst=hold, src=zero)
    fb.op('Mov', dst=reach, src=zero)

    # find: the nearest soft enemy village on the front, with spare force only (2 hold: none)
    fb.label('find')
    fb.op('Mov', dst=post, src=b.const('i32', 2))
    fb.op('JSLte', a=S, b=zero, offset='nopress')
    fb.op('Mov', dst=post, src=b.const('i32', 3))
    best = fb.reg(cx.t('ent.Structure'))
    best_f = fb.reg(cx.t('ent.Faction'))
    fb.op('Null', dst=best)
    fb.op('Null', dst=best_f)
    best_d, best_h, best_m = b.const('f64', 1 << 30), b.const('f64', 0), b.const('f64', 0)
    fb.op('Mov', dst=i, src=zi)
    b.loop_head('v')
    fb.op('JSGte', a=i, b=vn, offset='vdone')
    v = b.cast(b.call('hl.types.ArrayObj.getDyn', villages, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=v, offset='v')
    fb.op('Mov', dst=ve, src=v)
    vo = b.call('ent.Entity.get_owner', ve)
    fb.op('JNull', reg=vo, offset='v')
    fb.op('JEq', a=vo, b=fac, offset='v')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, vo), offset='v')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', v), offset='v')
    vsg = b.field(v, 'siege')
    fb.op('JNull', reg=vsg, offset='v')
    fb.op('JNotNull', reg=b.field(vsg, 'besiegingFaction'), offset='v')
    fb.op('JTrue', cond=b.call('ent.Structure.hasUWHeadquarters', v, fac), offset='v')
    fb.op('JFalse', cond=b.call('ent.Entity.canBeAttacked', ve, fac), offset='v')  # Devastated (pillaged) etc.
    fl = b.call('haxe.ds.ObjectMap.get', sfail, fb.dyn(ve))
    fb.op('JNull', reg=fl, offset='fresh')
    fb.op('SafeCast', dst=q, src=fl)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSLt', a=q, b=b.const('f64', PRESS_RETRY), offset='v')
    fb.label('fresh')
    fb.op('Call2', dst=d, fun=land, arg0=fac, arg1=ve)
    fb.op('JSGt', a=d, b=front_r, offset='v')
    fb.op('Call1', dst=et, fun=fpow, arg0=vo)
    fb.op('JSLt', a=T, b=et, offset='v')  # never poke the stronger side
    # our spare armies in reach (+ our cover) vs their side
    cover_at(m, ve, True)
    fb.op('Mov', dst=dm, src=big)
    y = _army_loop(fb, b, my_armies, mlen, j, 'rc', 'rcdone')
    fb.op('JNotNull', reg=b.field(y, 'harvestComponent'), offset='rc')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', y, ve))
    fb.op('JSGt', a=d, b=press_r, offset='rc')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', y), offset='rc')
    fb.op('Call2', dst=ok, fun=raidable, arg0=y, arg1=orders)
    fb.op('JFalse', cond=ok, offset='rc')
    fb.op('Call1', dst=p, fun=pw, arg0=y)
    fb.op('Add', dst=m, a=m, b=p)
    fb.op('JSGte', a=d, b=dm, offset='rc')
    fb.op('Mov', dst=dm, src=d)
    fb.op('JAlways', offset='rc')
    fb.label('rcdone')
    fb.op('JSGte', a=dm, b=big, offset='v')  # none of our spare armies in reach
    their_side(h, v)
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', ve))
    fb.op('Mul', dst=q, a=m, b=tf)
    fb.op('Mul', dst=r, a=h, b=press)
    fb.op('JSLt', a=q, b=r, offset='v')  # not soft: not worth the time
    fb.op('JSGte', a=dm, b=best_d, offset='v')
    for dst, src in ((best, v), (best_f, vo), (best_d, dm), (best_h, h), (best_m, m)):
        fb.op('Mov', dst=dst, src=src)
    fb.op('JAlways', offset='v')
    fb.label('vdone')
    fb.op('JNull', reg=best, offset='nopress')
    # mode: annex if in supply range, Annex available and affordable; else pillage if available; else skip it
    fb.op('Mov', dst=ve, src=best)
    fb.op('Bool', dst=annex, value=False)
    fb.op('JFalse', cond=b.call('logic.ai.AIMilitary.isInSupplyRange', 0, ve), offset='trypil')
    _has_action(fb, b, cx, best, fac, 'Annex', 'annexok', 'trypil')
    fb.label('annexok')
    cfn = cx.fn('ent.comp.SiegeComponent.getOccupationActionCost')
    carg = cx.code.types[cfn.type.value].definition.args[2].value
    cnull = fb.reg(carg)
    fb.op('Null', dst=cnull)
    costs = fb.reg(cx.code.types[cfn.type.value].definition.ret.value)
    fb.op('Call4', dst=costs, fun=cfn.findex.value, arg0=b.field(best, 'siege'), arg1=fb.string('Annex'),
          arg2=cnull, arg3=fac)
    hfn = cx.fn('logic.ai.AIController.hasResources')
    hnull = fb.reg(cx.code.types[hfn.type.value].definition.args[2].value)
    fb.op('Null', dst=hnull)
    fb.op('Call3', dst=ok, fun=hfn.findex.value, arg0=ctrl, arg1=costs, arg2=hnull)
    fb.op('JFalse', cond=ok, offset='trypil')
    fb.op('Bool', dst=annex, value=True)
    fb.op('JAlways', offset='setpress')
    fb.label('trypil')
    _has_action(fb, b, cx, best, fac, 'Pillage', 'setpress', 'nomode')
    fb.label('nomode')
    b.call('haxe.ds.ObjectMap.set', sfail, fb.dyn(ve), fb.dyn(t))  # can't act on it: look elsewhere next scan
    fb.op('JAlways', offset='nopress')
    fb.label('setpress')
    b.call('haxe.ds.ObjectMap.set', spv, fb.dyn(fac), fb.dyn(best))
    b.call('haxe.ds.ObjectMap.set', spf, fb.dyn(fac), fb.dyn(best_f))
    b.call('haxe.ds.ObjectMap.set', spa, fb.dyn(fac), fb.dyn(annex))
    b.call('haxe.ds.ObjectMap.set', spt, fb.dyn(fac), fb.dyn(t))
    fb.op('Mov', dst=tgt, src=best)
    fb.op('Mov', dst=hold, src=best_h)
    fb.op('Mov', dst=reach, src=best_m)

    # pressing: annex mode lifts the Annexation gauge so vanilla tries the (score-boosted) village now
    fb.label('pressing')
    fb.op('JFalse', cond=annex, offset='log')
    gauges = b.cast(fb.get(0, 'gauges'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=gauges, offset='log')
    gn = b.field(gauges, 'length')
    annexation = fb.dyn(fb.string('Annexation'))
    fire = b.const('f64', GAUGE_FIRE)
    gk = fb.reg(cx.t('String'))
    fb.op('Mov', dst=j, src=zi)
    b.loop_head('gl')
    fb.op('JSGte', a=j, b=gn, offset='log')
    g = b.call('hl.types.ArrayObj.getDyn', gauges, j)
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=g, offset='gl')
    fb.op('DynGet', dst=gk, obj=g, field=cx.s('kind'))
    fb.op('JNull', reg=gk, offset='gl')
    fb.op('JNotEq', a=b.call('String.__compare', gk, annexation), b=zi, offset='gl')
    fb.op('DynGet', dst=q, obj=g, field=cx.s('value'))
    fb.op('JSGte', a=q, b=fire, offset='log')
    fb.op('DynSet', obj=g, field=cx.s('value'), src=fire)
    fb.op('JAlways', offset='log')

    # 1 defend / 2 hold / 4 expand / 5 harass: no press
    fb.label('nopress')
    fb.op('JNull', reg=b.call('haxe.ds.ObjectMap.get', spv, fb.dyn(fac)), offset='noclear')
    clear_press()  # defend ends a press (its siege runs on under vanilla and the fight retreat)
    fb.label('noclear')
    fb.op('JSLte', a=post, b=b.const('i32', 2), offset='log')
    # expand if vanilla has neutral Annex candidates, else harass
    aargs = b.call('$HAI.getDefaultStructureArgs', fb.string('Annex'))
    fb.op('SetField', obj=aargs, field=cx.field(fb.regs[aargs], 'allowEnemy'), src=t_false)
    ann = _new_array(fb, b, cx)
    b.call('logic.ai.$AIMilitary.getSiegeableVillages', ann, fb.string('Annex'), fac, aargs)
    fb.op('Mov', dst=post, src=b.const('i32', 4))
    fb.op('JSGt', a=b.field(ann, 'length'), b=zi, offset='log')
    fb.op('Mov', dst=post, src=b.const('i32', 5))

    # log on a posture / target change, else at most every STRAT_LOG s
    fb.label('log')
    lp = b.call('haxe.ds.ObjectMap.get', spost, fb.dyn(fac))
    fb.op('JNull', reg=lp, offset='changed')
    lpi = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=lpi, src=lp)
    fb.op('JNotEq', a=lpi, b=post, offset='changed')
    fb.op('JNotEq', a=b.call('haxe.ds.ObjectMap.get', stgt, fb.dyn(fac)), b=fb.dyn(tgt), offset='changed')
    _throttle(fb, b, cx, 'stratx', fac, STRAT_LOG, 'end')
    fb.op('JAlways', offset='emit')
    fb.label('changed')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'stratx'), fb.dyn(fac), fb.dyn(t))
    fb.label('emit')
    b.call('haxe.ds.ObjectMap.set', spost, fb.dyn(fac), fb.dyn(post))
    b.call('haxe.ds.ObjectMap.set', stgt, fb.dyn(fac), fb.dyn(tgt))
    # per at-war faction: our diplomatic wish toward it (desiredStatus) and its army power
    war = _new_array(fb, b, cx)
    facs = b.cast(fb.get(state, 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=facs, offset='wdone')
    fnn = b.field(facs, 'length')
    dip = b.field(ctrl, 'diplomacy')
    ds = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=j, src=zi)
    b.loop_head('wf')
    fb.op('JSGte', a=j, b=fnn, offset='wdone')
    ef = b.cast(b.call('hl.types.ArrayObj.getDyn', facs, j), 'ent.Faction')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=ef, offset='wf')
    fb.op('JEq', a=ef, b=fac, offset='wf')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, ef), offset='wf')
    fb.op('Int', dst=ds, ptr=cx.code.add_i32(-1).value)
    gd = fb.try_()  # desiredStatus lookup throws for a faction the diplomacy module doesn't track
    fb.op('JNull', reg=dip, offset='nods')
    fb.op('Mov', dst=ds, src=b.call('logic.ai.Diplomacy.getTargetStatus', dip, ef))
    fb.label('nods')
    fb.end_try(gd)
    fb.op('Call1', dst=et, fun=fpow, arg0=ef)
    wd = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=wd)
    b.put(wd, 'f', fb.get(ef, 'kind'))
    b.put(wd, 'ds', ds)
    b.put(wd, 'pw', b.to_int(et))
    b.call('hl.types.ArrayObj.push', war, fb.dyn(wd))
    fb.op('JAlways', offset='wf')
    fb.label('wdone')
    ps = fb.reg(cx.t('String'))
    for n, name in enumerate(POSTURES):
        if not name:
            continue
        lbl = f'pn{n}'
        fb.op('JNotEq', a=post, b=b.const('i32', n), offset=lbl)
        fb.op('Mov', dst=ps, src=fb.string(name))
        fb.label(lbl)
    mode = fb.reg(cx.t('String'))
    fb.op('Mov', dst=mode, src=fb.string('-'))
    fb.op('JNull', reg=tgt, offset='mset')
    fb.op('Mov', dst=mode, src=fb.string('pillage'))
    fb.op('JFalse', cond=annex, offset='mset')
    fb.op('Mov', dst=mode, src=fb.string('annex'))
    fb.label('mset')
    _log_ev(fb, b, cx, helpers, 'strat', [('f', fb.get(fac, 'kind')), ('post', ps), ('S', S), ('need', need),
                                          ('T', T), ('tgt', tgt), ('mode', mode), ('hold', hold),
                                          ('reach', reach), ('war', war)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()



def strat_levers(cx, new_ids):
    """Vanilla gates opened for the pressed faction only (policy §5b levers):
    - `Diplomacy.getTargetStatus` in getSiegeableVillages -> >= 1 for the pressed village's owner (vanilla lists an
      enemy's villages only for its daily diplomatic target);
    - `get_aggressiveness` in tryAnnexation -> GAUGE_FIRE-scale max (100) while pressing in annex mode (enemy
      villages need aggressiveness >= 50).
    The target scores (siege.build_scoring) then keep only the pressed village among that faction's."""
    report = {}
    # desiredStatus gate
    orig = cx.fn('logic.ai.Diplomacy.getTargetStatus')
    args = [a.value for a in cx.code.types[orig.type.value].definition.args]
    fb = FB(cx, args, cx.t('i32'), fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(cx.t('i32'))
    fb.op('Call2', dst=res, fun=orig.findex.value, arg0=0, arg1=1)
    guard = fb.try_()
    fb.op('JSGte', a=res, b=b.const('i32', 1), offset='end')
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    owner = b.call('logic.ai.AIModule.get_aiOwner', 0)
    fb.op('JNull', reg=owner, offset='end')
    # raid's own pillage scan (rules/raid.py, map `rscan` = the game time it started): every at-war owner
    rs = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rscan'), fb.dyn(owner))
    fb.op('JNull', reg=rs, offset='press')
    rt = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=rt, src=rs)
    state = _state(fb, b, cx)
    fb.op('JNotEq', a=rt, b=b.field(state, 'time'), offset='press')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, owner, 1), offset='press')
    fb.op('JAlways', offset='lift')
    fb.label('press')
    pf = b.cast(b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'spf'), fb.dyn(owner)), 'ent.Faction')
    fb.op('JNull', reg=pf, offset='end')
    fb.op('JNotEq', a=pf, b=1, offset='end')
    fb.label('lift')
    fb.op('Int', dst=res, ptr=cx.code.add_i32(1).value)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    report['press-target'] = _redirect(cx, 'logic.ai.Diplomacy.getTargetStatus',
                                       ['logic.ai.$AIMilitary.getSiegeableVillages'], w)
    # aggressiveness gate (tryAnnexation only)
    orig = cx.fn('logic.ai.AIMilitary.get_aggressiveness')
    fb = FB(cx, [cx.t('logic.ai.AIMilitary')], cx.t('f64'), fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Call1', dst=res, fun=orig.findex.value, arg0=0)
    guard = fb.try_()
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    pa = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'spa'), fb.dyn(fac))
    fb.op('JNull', reg=pa, offset='end')
    ab = fb.reg(cx.t('bool'))
    fb.op('SafeCast', dst=ab, src=pa)
    fb.op('JFalse', cond=ab, offset='end')
    fb.op('Mov', dst=res, src=b.const('f64', 100))
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    report['press-aggr'] = _redirect(cx, 'logic.ai.AIMilitary.get_aggressiveness',
                                     ['logic.ai.AIMilitary.tryAnnexation'], w)
    return report
