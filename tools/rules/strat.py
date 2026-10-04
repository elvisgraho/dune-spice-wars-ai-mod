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
power there (any task, + cover) x terrain < PRESS_KEEP x their side (`weak`; while our occupation of it progresses
only at-war armies arriving before it ends count: aimod_threat (horizon 0, any heading) within max(LOCAL,
(_cap_rem + CONTEST_SLACK) x CONTEST_SPD)); a dropped target is skipped for
PRESS_RETRY s and our Military orders on it are cancelled (vanilla would keep a lost siege going).
The levers (strat_levers, scores in siege.build_scoring, raid) read the press maps: spv faction -> village,
spf -> its owner, spa -> annex mode, spt -> start time. Annex mode also lifts the Annexation gauge to GAUGE_FIRE so
vanilla tries it now.
Logs `strat` on every posture / target change and at least every STRAT_LOG s: post, S, need, T, tgt, mode, hold,
reach, war = [{f, ds (desiredStatus toward it), pw (its army power)}] per at-war faction; `strat` act drop on a
dropped press (why done | gone | truce | slow | weak; + ha hc hm hn = their armies / cover / militia / raiders, tf,
pr = our occupation progress, rem = its remaining s, -1 when not occupying). Fails safe: in a trap."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.intel import _seen_map, _rec_get, _rec_of

POSTURES = ('', 'defend', 'hold', 'press', 'expand', 'harass', 'recover')  # index RECOVER_POST = recover


def build_fpow(cx, pw):
    """aimod_fpow(f, obs) -> power of faction f's combat armies (no militia, harvesters, transported, dead) as obs
    knows it (fog of war, rules/intel.py): obs null or f itself: the truth; else each army at its power when obs
    last saw it (any age: the stack still exists somewhere), armies obs never saw not at all."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Faction')], cx.t('f64'))
    b = B(fb)
    tot = b.const('f64', 0)
    fb.op('JNull', reg=0, offset='end')
    mp = _seen_map(fb, b, cx, 1)
    arr, alen = _my_armies(fb, b, 0, 'end')
    i, p = fb.reg(cx.t('i32')), fb.reg(cx.t('f64'))
    x = _army_loop(fb, b, arr, alen, i, 'loop', 'end')
    fb.op('JNotNull', reg=b.field(x, 'harvestComponent'), offset='loop')
    fb.op('JNull', reg=1, offset='live')
    fb.op('JEq', a=1, b=0, offset='live')
    fb.op('JTrue', cond=b.call('ent.Entity.isVisibleForFaction', x, 1), offset='live')
    rec = _rec_of(fb, b, cx, mp, x, 'loop')
    fb.op('Add', dst=tot, a=tot, b=_rec_get(fb, b, cx, rec, 'p'))
    fb.op('JAlways', offset='loop')
    fb.label('live')
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


def build_strat(cx, helpers, pw, fpow, raidable, react, land, terrain, cover, defend, militia, home, short, neutral,
                threat, threat_in):
    """aimod_strat(mil, dt) (see module doc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    _crumb_begin(fb, b, cx, helpers, 'strat')  # step probe: `rfail` names a run that died silently
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
    # keep-test parts for the drop log: their armies / cover / militia / raiders, terrain, our occupation progress and
    # its remaining s (-1: not occupying, the full test)
    ha, hc, hm, hn, kpr, krem = (fb.reg(cx.t('f64')) for _ in range(6))
    for _r in (ha, hc, hm, hn, kpr, tf):
        fb.op('Mov', dst=_r, src=zero)
    fb.op('Mov', dst=krem, src=b.const('f64', -1))

    def cover_at(dst, at, own, atk=False):
        """atk: our cover at a press target counts x OWN_COVER_ATK."""
        fb.op('CallN', dst=dst, fun=cover, args=[fac, at, at, t_true if own else t_false, no_arr])
        if atk:
            _atk_cover(fb, b, dst)

    def their_side(dst, s):
        """dst = at-war armies in reach + enemy turret cover + militia at structure s (entity in ve)."""
        fb.op('Call3', dst=dst, fun=react, arg0=fac, arg1=ve, arg2=local)
        cover_at(q, ve, False)
        fb.op('Add', dst=dst, a=dst, b=q)
        fb.op('Call1', dst=q, fun=militia, arg0=s)
        fb.op('Add', dst=dst, a=dst, b=q)
        fb.op('Call3', dst=q, fun=neutral, arg0=fac, arg1=ve, arg2=local)  # other raiders at it fight us too
        fb.op('Add', dst=dst, a=dst, b=q)

    def clear_press():
        for mp in (spv, spf, spa, spt):
            b.call('haxe.ds.ObjectMap.remove', mp, fb.dyn(fac))

    # ---- picture: spare power (free for an offensive, minus the home need) and our total
    fb.op('Mov', dst=S, src=zero)
    fb.op('Mov', dst=T, src=zero)
    W = fb.reg(cx.t('f64'))  # worn power: life < RAID_LIFE or short of supply for the way home (RECOVER)
    fb.op('Mov', dst=W, src=zero)
    y = _army_loop(fb, b, my_armies, mlen, j, 'sp', 'spdone')
    fb.op('JNotNull', reg=b.field(y, 'harvestComponent'), offset='sp')
    fb.op('Call1', dst=p, fun=pw, arg0=y)
    fb.op('Add', dst=T, a=T, b=p)
    fb.op('JSLt', a=b.call('ent.Entity.get_lifeRatio', y), b=_ratio(fb, b, RAID_LIFE), offset='worn')
    fb.op('Call2', dst=ok, fun=short, arg0=fac, arg1=y)
    fb.op('JFalse', cond=ok, offset='notworn')
    fb.label('worn')
    fb.op('Add', dst=W, a=W, b=p)
    fb.label('notworn')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', y), offset='sp')
    fb.op('Call2', dst=ok, fun=raidable, arg0=y, arg1=orders)
    fb.op('JFalse', cond=ok, offset='sp')
    fb.op('Add', dst=S, a=S, b=p)
    fb.op('JAlways', offset='sp')
    fb.label('spdone')
    fb.op('Call2', dst=need, fun=home, arg0=fac, arg1=b.const('f64', HOME_R))
    fb.op('Mul', dst=need, a=need, b=enter)
    fb.op('SDiv', dst=need, a=need, b=own_t)
    # turrets hold too: at each structure of ours on our land with at-war power standing within STAND_R, our cover
    # there (its own guns included) replaces guard armies, min(cover, ENTER x that power) / OWN_T (the standoff
    # guard (stack x ENTER - cover) / OWN_T). A battery built by turret-steer frees armies here
    cvc = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=cvc, src=zero)
    sts = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=sts, offset='cvdone')
    nul_e = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=nul_e)
    se_ = fb.reg(cx.t('ent.Entity'))
    cvs = _new_array(fb, b, cx)  # structures credited so far
    k_ = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k_, src=zi)
    b.loop_head('cvl')
    fb.op('JSGte', a=k_, b=b.field(sts, 'length'), offset='cvdone')
    s_ = b.cast(b.call('hl.types.ArrayObj.getDyn', sts, k_), 'ent.Structure')
    fb.op('Incr', dst=k_)
    fb.op('JNull', reg=s_, offset='cvl')
    z_ = b.call('ent.Entity.get_zone', s_)
    fb.op('JNull', reg=z_, offset='cvl')
    fb.op('JNotEq', a=b.field(z_, 'owner'), b=fac, offset='cvl')
    fb.op('Mov', dst=se_, src=s_)
    fb.op('Call3', dst=h, fun=threat, arg0=fac, arg1=se_, arg2=b.const('f64', STAND_R))
    fb.op('JSLte', a=h, b=zero, offset='cvl')
    # one credit per turret cluster: a structure within COVER_R of one already credited shares its batteries (a
    # bunker pair would count the same battery twice)
    ck = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=ck, src=zi)
    b.loop_head('cvd')
    fb.op('JSGte', a=ck, b=b.field(cvs, 'length'), offset='cvnew')
    ce_ = b.cast(b.call('hl.types.ArrayObj.getDyn', cvs, ck), 'ent.Entity')
    fb.op('Incr', dst=ck)
    fb.op('JNull', reg=ce_, offset='cvd')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', se_, ce_), b=b.const('f64', COVER_R), offset='cvl')
    fb.op('JAlways', offset='cvd')
    fb.label('cvnew')
    b.call('hl.types.ArrayObj.push', cvs, fb.dyn(se_))
    fb.op('CallN', dst=q, fun=cover, args=[fac, se_, nul_e, t_true, no_arr])
    fb.op('Mul', dst=h, a=h, b=enter)
    fb.op('JSLte', a=q, b=h, offset='cvmin')
    fb.op('Mov', dst=q, src=h)
    fb.label('cvmin')
    fb.op('SDiv', dst=q, a=q, b=own_t)
    fb.op('Add', dst=cvc, a=cvc, b=q)
    fb.op('JAlways', offset='cvl')
    fb.label('cvdone')
    fb.op('Sub', dst=need, a=need, b=cvc)
    fb.op('JSGte', a=need, b=zero, offset='cvpos')
    fb.op('Mov', dst=need, src=zero)
    fb.label('cvpos')
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
    # our occupation of it under way (besieged by us, progress > 0): remaining s (krem; -1 otherwise)
    kocc = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=kocc, value=False)
    ksg = b.field(pv, 'siege')
    fb.op('JNull', reg=ksg, offset='knocc')
    fb.op('JNotEq', a=b.field(ksg, 'besiegingFaction'), b=fac, offset='knocc')
    fb.op('JSLte', a=b.call('ent.comp.SiegeComponent.getOccupationActionProgress', ksg), b=zero, offset='knocc')
    krr, kpp = _cap_rem(fb, b, cx, pv, t, 'knocc')
    fb.op('Mov', dst=kpr, src=kpp)
    fb.op('Mov', dst=krem, src=krr)
    fb.op('Bool', dst=kocc, value=True)
    fb.label('knocc')
    # slow: never while our occupation progresses (a capture near its end isn't stale)
    fb.op('Mov', dst=why, src=fb.string('slow'))
    fb.op('JTrue', cond=kocc, offset='kslow')
    fb.op('JSGt', a=age, b=b.const('f64', PRESS_MAX), offset='drop')
    fb.label('kslow')
    # keep: our power there (any task: the siege armies are busy) + our cover vs their side
    cover_at(reach, ve, True, atk=True)
    y = _army_loop(fb, b, my_armies, mlen, j, 'kp', 'kpdone')
    fb.op('JNotNull', reg=b.field(y, 'harvestComponent'), offset='kp')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', y, ve), b=press_r, offset='kp')
    fb.op('Call1', dst=p, fun=pw, arg0=y)
    fb.op('Add', dst=reach, a=reach, b=p)
    fb.op('JAlways', offset='kp')
    fb.label('kpdone')
    # their side: at-war armies that can reach it (aimod_react, LOCAL) + enemy cover + militia + other raiders; while
    # our occupation progresses only armies that arrive before it ends count: within max(LOCAL, (remaining s +
    # CONTEST_SLACK) x CONTEST_SPD) (AI-POLICY §4: threat ETA included, a nearly done capture fights on). Smugglers
    # dropped Ash-bat 16 s before the pillage ended at a 4.6 order balance for a Fremen stack 400 away that never came
    fb.op('Call3', dst=ha, fun=react, arg0=fac, arg1=ve, arg2=local)
    fb.op('JFalse', cond=kocc, offset='kfull')
    fb.op('Add', dst=q, a=krem, b=b.const('f64', CONTEST_SLACK))
    fb.op('Mul', dst=q, a=q, b=b.const('f64', CONTEST_SPD))
    fb.op('JSGte', a=q, b=local, offset='krad')
    fb.op('Mov', dst=q, src=local)
    fb.label('krad')
    fb.op('Call3', dst=ha, fun=threat_in, arg0=fac, arg1=ve, arg2=q)  # no movers from outside q: it is the ETA
    fb.label('kfull')
    cover_at(hc, ve, False)
    fb.op('Call1', dst=hm, fun=militia, arg0=pv)
    fb.op('Call3', dst=hn, fun=neutral, arg0=fac, arg1=ve, arg2=local)
    fb.op('Add', dst=hold, a=ha, b=hc)
    fb.op('Add', dst=hold, a=hold, b=hm)
    fb.op('Add', dst=hold, a=hold, b=hn)
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
                                          ('age', age), ('hold', hold), ('reach', reach), ('ha', ha), ('hc', hc),
                                          ('hm', hm), ('hn', hn), ('tf%', tf), ('pr%', kpr), ('rem', krem)])
    fb.op('Null', dst=tgt)
    fb.op('Mov', dst=hold, src=zero)
    fb.op('Mov', dst=reach, src=zero)

    # find: the nearest soft enemy village on the front, with spare force only (2 hold: none)
    fb.label('find')
    # 2 recover: most of our power is worn (hysteresis: leave only below RECOVER_OUT)
    fb.op('Mov', dst=post, src=b.const('i32', RECOVER_POST))
    rthr = _ratio(fb, b, RECOVER_IN)
    lastp = b.call('haxe.ds.ObjectMap.get', spost, fb.dyn(fac))
    fb.op('JNull', reg=lastp, offset='rthr')
    lpost = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=lpost, src=lastp)
    fb.op('JNotEq', a=lpost, b=b.const('i32', RECOVER_POST), offset='rthr')
    fb.op('Mov', dst=rthr, src=_ratio(fb, b, RECOVER_OUT))
    fb.label('rthr')
    fb.op('Mul', dst=q, a=T, b=rthr)
    fb.op('JSGt', a=W, b=q, offset='nopress')
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
    fb.op('Call2', dst=et, fun=fpow, arg0=vo, arg1=fac)
    fb.op('JSLt', a=T, b=et, offset='v')  # never poke the stronger side
    # our spare armies in reach (+ our cover) vs their side
    cover_at(m, ve, True, atk=True)
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
    # contact tension (AI-POLICY §5c step 2): softness PRESS -> ENTER as T goes 0 -> 1
    prx, tq = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Call2', dst=tq, fun=helpers['tension'], arg0=fac, arg1=ve)
    fb.op('Mul', dst=tq, a=tq, b=_ratio(fb, b, PRESS - ENTER))
    fb.op('Sub', dst=prx, a=press, b=tq)
    fb.op('Mul', dst=r, a=h, b=prx)
    fb.op('JSLt', a=q, b=r, offset='v')  # not soft: not worth the time
    # DMZ (rules/dmz.py): a border village of an at-war neighbour holding >= DMZ_WAR of them ranks first
    fb.op('Call2', dst=ok, fun=helpers['dmzv'], arg0=fac, arg1=v)
    fb.op('JFalse', cond=ok, offset='nodmz')
    fb.op('Mul', dst=dm, a=dm, b=_ratio(fb, b, DMZ_PREF))
    fb.label('nodmz')
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
    # never pillage a village on an uncontested deep-desert ring we are closing (aimod_ddclean: Devastated = no Annex)
    pz = b.call('ent.Entity.get_zone', ve)
    fb.op('JNull', reg=pz, offset='pring')
    prc = fb.reg(cx.t('bool'))
    fb.op('Call2', dst=prc, fun=helpers['ddclean'], arg0=fac, arg1=pz)
    fb.op('JTrue', cond=prc, offset='nomode')
    fb.label('pring')
    # ... nor one of our next Annex choices (map `akeep`, rules/raid.py annex-keep) we just can't pay yet: a pillage
    # doubles our cost there, a liberation makes it untargetable for 20 days; vanilla annexes it once affordable
    akt = b.call('haxe.ds.ObjectMap.get', _fac_map(fb, b, cx, 'akeep', fac), fb.dyn(ve))
    fb.op('JNull', reg=akt, offset='pnokeep')
    akq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=akq, src=akt)
    fb.op('Sub', dst=akq, a=t, b=akq)
    fb.op('JSLt', a=akq, b=b.const('f64', AKEEP_T), offset='nomode')
    fb.label('pnokeep')
    # a DMZ village: `raid` liberates it (rules/dmz.py), so Liberate available is enough
    fb.op('Call2', dst=ok, fun=helpers['dmzv'], arg0=fac, arg1=best)
    fb.op('JFalse', cond=ok, offset='pmpil')
    _has_action(fb, b, cx, best, fac, 'Liberate', 'setpress', 'pmpil')
    fb.label('pmpil')
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

    # 1 defend / 2 hold / 6 recover / 4 expand / 5 harass: no press
    fb.label('nopress')
    fb.op('JNull', reg=b.call('haxe.ds.ObjectMap.get', spv, fb.dyn(fac)), offset='noclear')
    clear_press()  # defend ends a press (its siege runs on under vanilla and the fight retreat)
    fb.label('noclear')
    fb.op('JSLte', a=post, b=b.const('i32', 2), offset='log')
    fb.op('JEq', a=post, b=b.const('i32', RECOVER_POST), offset='log')
    # expand if vanilla has neutral Annex candidates, else harass
    aargs = b.call('$HAI.getDefaultStructureArgs', fb.string('Annex'))
    fb.op('SetField', obj=aargs, field=cx.field(fb.regs[aargs], 'allowEnemy'), src=t_false)
    ann = _new_array(fb, b, cx)
    # vanilla's Annex reach (map `ascan`, annex-reach below): expand iff vanilla's Annex has a candidate
    ascan = _global_map(fb, b, cx, 'ascan')
    b.call('haxe.ds.ObjectMap.set', ascan, fb.dyn(fac), fb.dyn(b.field(_state(fb, b, cx), 'time')))
    b.call('logic.ai.$AIMilitary.getSiegeableVillages', ann, fb.string('Annex'), fac, aargs)
    asnul = fb.reg(cx.t('dyn'))
    fb.op('Null', dst=asnul)
    b.call('haxe.ds.ObjectMap.set', ascan, fb.dyn(fac), asnul)
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
    fb.op('Call2', dst=et, fun=fpow, arg0=ef, arg1=fac)
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
    _log_ev(fb, b, cx, helpers, 'strat', [('f', fb.get(fac, 'kind')), ('post', ps), ('S', S), ('need', need), ('cv', cvc),
                                          ('T', T), ('tgt', tgt), ('mode', mode), ('hold', hold),
                                          ('reach', reach), ('war', war)])
    fb.label('end')
    _crumb_end(fb, b, cx, 'strat')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()



def strat_levers(cx, new_ids):
    """Vanilla gates opened for the pressed faction only (policy §5b levers):
    - `Diplomacy.getTargetStatus` in getSiegeableVillages -> >= 1 for the pressed village's owner (vanilla lists an
      enemy's villages only for its daily diplomatic target); also for an at-war owner one of whose villages is our
      contact partner at tension >= TEN_GATE (the target scores keep only such partner villages of it);
    - `isInSupplyRange` in getSiegeableVillages -> + FAR_ZONES zones for a faction without Annex distance cost, + RAID_ZONES
      during raid's own pillage scan (`rscan`); for an at-war owner with the DMZ on (rules/dmz.py cache `dmz`);
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
    fb.op('JEq', a=owner, b=1, offset='end')  # our own villages: vanilla's answer (areAtWar(us, us) logs a warning)
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
    fb.op('JNull', reg=pf, offset='dmzg')
    fb.op('JEq', a=pf, b=1, offset='lift')
    # DMZ on against this at-war owner (rules/dmz.py: it holds >= DMZ_WAR regions next to ours): listed, so vanilla
    # can annex / liberate its border villages (the target scores keep only those and drop them from Pillage)
    fb.label('dmzg')
    from rules.dmz import _pair_map
    dcv = b.call('haxe.ds.ObjectMap.get', _pair_map(fb, b, cx, 'dmz', owner), fb.dyn(1))
    fb.op('JNull', reg=dcv, offset='tens')
    dcn = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=dcn, src=dcv)
    fb.op('JSLt', a=dcn, b=b.const('i32', DMZ_WAR), offset='tens')
    fb.op('JTrue', cond=b.call('logic.state.State.areAtWar', _state(fb, b, cx), owner, 1), offset='lift')
    # contact tension at the cap (rules/tension.py, AI-POLICY §5c): one of our villages rubs a village of this at-war
    # owner at T >= TEN_GATE: its villages are listed; the target scores keep only the partner ones (annex.py)
    fb.label('tens')
    st2 = _state(fb, b, cx)
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', st2, owner, 1), offset='end')
    tenw, tenv = _global_map(fb, b, cx, 'tenw'), _global_map(fb, b, cx, 'tenv')
    mine = b.cast(fb.get(owner, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=mine, offset='end')
    ti = fb.reg(cx.t('i32'))
    tq = fb.reg(cx.t('f64'))
    twe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ti, src=b.const('i32', 0))
    b.loop_head('tl')
    fb.op('JSGte', a=ti, b=b.field(mine, 'length'), offset='end')
    tsv = b.call('hl.types.ArrayObj.getDyn', mine, ti)
    fb.op('Incr', dst=ti)
    fb.op('JNull', reg=tsv, offset='tl')
    tw = b.call('haxe.ds.ObjectMap.get', tenw, tsv)
    fb.op('JNull', reg=tw, offset='tl')
    fb.op('Mov', dst=twe, src=b.cast(tw, 'ent.Entity'))
    fb.op('JNotEq', a=b.call('ent.Entity.get_owner', twe), b=1, offset='tl')
    tvv = b.call('haxe.ds.ObjectMap.get', tenv, tsv)
    fb.op('JNull', reg=tvv, offset='tl')
    fb.op('SafeCast', dst=tq, src=tvv)
    fb.op('JSLt', a=tq, b=_ratio(fb, b, TEN_GATE), offset='tl')
    fb.label('lift')
    fb.op('Int', dst=res, ptr=cx.code.add_i32(1).value)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    report['press-target'] = _redirect(cx, 'logic.ai.Diplomacy.getTargetStatus',
                                       ['logic.ai.$AIMilitary.getSiegeableVillages'], w)
    # supply range of siege targets: vanilla lists villages within maxSupplyDistZones of our territory, 1 zone in
    # practice (+1 per AI_SupplyEstimation_MaxDistance_BonusesCount 3 / 5 / 15 reached by Recycling Vats + Spectral
    # Imaging, at most 2). A faction whose Annex cost doesn't grow with distance (attribute 952
    # Outpost_DistanceCost_MRatio <= 0: Smugglers) gets FAR_ZONES more: far villages cost them the same (Smugglers
    # saw 1-8 candidates all match and annexed 8 villages in 69 min). Vanilla's -10 / zone score keeps near ones first
    orig = cx.fn('logic.ai.AIMilitary.isInSupplyRange')
    args = [a.value for a in cx.code.types[orig.type.value].definition.args]
    fb = FB(cx, args, cx.t('bool'), fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(cx.t('bool'))
    fb.op('Call2', dst=res, fun=orig.findex.value, arg0=0, arg1=1)
    guard = fb.try_()
    fb.op('JTrue', cond=res, offset='end')
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    owner = b.call('logic.ai.AIModule.get_aiOwner', 0)
    fb.op('JNull', reg=owner, offset='end')
    gav = cx.fn('ent.Object.getAtbVal')
    gat = [a.value for a in cx.code.types[gav.type.value].definition.args]
    gobj, gref, gfac = fb.reg(gat[0]), fb.reg(gat[2]), fb.reg(gat[3])
    fb.op('Mov', dst=gobj, src=owner)
    fb.op('Null', dst=gref)
    fb.op('Null', dst=gfac)
    dcr = fb.reg(cx.t('f64'))
    fb.op('Call4', dst=dcr, fun=gav.findex.value, arg0=gobj, arg1=b.const('i32', DIST_COST_ATB), arg2=gref, arg3=gfac)
    # extra zones: FAR_ZONES without Annex distance cost; + RAID_ZONES during raid's own pillage scan (map `rscan`,
    # set around that one call): Smugglers raided the same 5 neutral villages in reach and sat 8-11 min between
    # waves while they were Devastated (no candidate, no row); the raid's supply budget, relief and home tests still
    # judge the farther ones
    ext = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=ext, src=b.const('i32', 0))
    fb.op('JSGt', a=dcr, b=b.const('f64', 0), offset='nofar')
    fb.op('Mov', dst=ext, src=b.const('i32', FAR_ZONES))
    fb.label('nofar')
    fb.op('JNull', reg=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rscan'), fb.dyn(owner)), offset='noraid')
    fb.op('Add', dst=ext, a=ext, b=b.const('i32', RAID_ZONES))
    fb.label('noraid')
    # vanilla's Annex scan (map `ascan` faction -> the game time of the call, set by the getSiegeableVillages wrapper
    # below; stale next frame): + ANNEX_ZONES for every faction (1-2 candidates per pick gave the Annex value nothing
    # to choose; far ones still pay vanilla's per-zone score, the cost ratio and compactness)
    fb.op('JSLte', a=dcr, b=b.const('f64', 0), offset='noann')  # no distance cost: FAR_ZONES already (not both)
    asv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'ascan'), fb.dyn(owner))
    fb.op('JNull', reg=asv, offset='noann')
    asq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=asq, src=asv)
    fb.op('JNotEq', a=asq, b=b.field(_state(fb, b, cx), 'time'), offset='noann')
    fb.op('Add', dst=ext, a=ext, b=b.const('i32', ANNEX_ZONES))
    fb.label('noann')
    # a free Supply Drop (rules/sdrop.py map `sdfree`, refreshed every SD_CHECK s while held and unlocked): + SD_ZONES
    # for every siege kind, in military target scans only (vanilla's pickers: `mscan` / Annex `ascan` == now; raid's
    # own scan: `rscan`); the first far order locks it (sdrop-trip) and the reach shrinks back
    now_t = b.field(_state(fb, b, cx), 'time')
    fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rscan'), fb.dyn(owner)), offset='sdmil')
    for mp in ('mscan', 'ascan'):
        mv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, mp), fb.dyn(owner))
        nx = mp + '_no'
        fb.op('JNull', reg=mv, offset=nx)
        mq = fb.reg(cx.t('f64'))
        fb.op('SafeCast', dst=mq, src=mv)
        fb.op('JEq', a=mq, b=now_t, offset='sdmil')
        fb.label(nx)
    fb.op('JAlways', offset='nosd')
    fb.label('sdmil')
    sdv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'sdfree'), fb.dyn(owner))
    fb.op('JNull', reg=sdv, offset='nosd')
    sdq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=sdq, src=sdv)
    fb.op('Sub', dst=sdq, a=b.field(_state(fb, b, cx), 'time'), b=sdq)
    fb.op('JSGt', a=sdq, b=b.const('f64', SD_FRESH), offset='nosd')
    fb.op('Add', dst=ext, a=ext, b=b.const('i32', SD_ZONES))
    fb.label('nosd')
    fb.op('JSLte', a=ext, b=b.const('i32', 0), offset='end')
    z = b.call('ent.Entity.get_zone', 1)
    fb.op('JNull', reg=z, offset='end')
    gd = cx.fn('ent.Zone.getDistanceToPlayerTerritory')
    gdt = [a.value for a in cx.code.types[gd.type.value].definition.args]
    pf, tr = fb.reg(gdt[1]), fb.reg(gdt[2])
    fb.op('Mov', dst=pf, src=owner)
    fb.op('Bool', dst=tr, value=True)
    zd = fb.reg(cx.t('i32'))
    fb.op('Call3', dst=zd, fun=gd.findex.value, arg0=z, arg1=pf, arg2=tr)
    mx = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=mx, src=b.field(0, 'maxSupplyDistZones'))
    fb.op('Add', dst=mx, a=mx, b=ext)
    fb.op('JSGt', a=zd, b=mx, offset='end')
    fb.op('Bool', dst=res, value=True)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    report['far-annex'] = _redirect(cx, 'logic.ai.AIMilitary.isInSupplyRange',
                                    ['logic.ai.$AIMilitary.getSiegeableVillages'], w)
    # Annex scan marker: vanilla's getSiegeableVillages(out, k, faction, args) calls with k "Annex" (target choice in
    # tryAction / forceAction, the gauge's target test in increaseGauges, peaceful annex) set map `ascan`
    # faction -> now around the call, read by the supply-range wrapper above
    orig = cx.fn('logic.ai.$AIMilitary.getSiegeableVillages')
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    g0 = fb.try_()
    fb.op('JNull', reg=1, offset='mk')
    fb.op('JNull', reg=2, offset='mk')
    # any siege kind from these callers: map `mscan` (a military target scan: the Supply Drop reach applies, not to
    # Underworld HQ placement or building scores, which call getSiegeableVillages too)
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'mscan'), fb.dyn(2), fb.dyn(b.field(_state(fb, b, cx), 'time')))
    fb.op('JNotEq', a=b.call('String.__compare', 1, fb.dyn(fb.string('Annex'))), b=b.const('i32', 0), offset='mk')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'ascan'), fb.dyn(2), fb.dyn(b.field(_state(fb, b, cx), 'time')))
    fb.label('mk')
    fb.end_try(g0)
    fb.op('CallN', dst=res, fun=orig.findex.value, args=list(range(len(args))))
    g1 = fb.try_()
    fb.op('JNull', reg=2, offset='um')
    nd = fb.reg(cx.t('dyn'))
    fb.op('Null', dst=nd)
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'ascan'), fb.dyn(2), nd)
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'mscan'), fb.dyn(2), nd)
    fb.label('um')
    fb.end_try(g1)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    tid = orig.findex.value
    nr = 0
    for caller, want in (('logic.ai.AIMilitary.tryAction', 1), ('logic.ai.AIMilitary.forceAction', 1),
                         ('logic.ai.AIMilitary.increaseGauges', 0),  # 0: any number (one per gauge kind)
                         ('logic.ai.ResourceManager.checkPeacefulAnnexation', 1)):
        sites = [op for op in cx.fn(caller).ops if op.op.startswith('Call') and op.df.get('fun') is not None
                 and op.df['fun'].value == tid]
        if (want and len(sites) != want) or not sites:
            raise ValueError(f'annex-reach: expected {want} getSiegeableVillages calls in {caller}, found {len(sites)}')
        for op in sites:
            op.df['fun'].value = w
        nr += len(sites)
    report['annex-reach'] = nr
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
