"""Rally: gather strength instead of feeding armies one at a time (AI-POLICY §1.5 concentrate, defense).

The failure: Fremen took Atreides' Aeganim with 10 armies (~350k) against Atreides' 7 (~235k, too few even at home
x1.3). Vanilla had no answer between "Defense with enough power" and nothing: 2 armies idled 330 away, 2 stopped 140
short, and 2 kept healing at Sadnin 84 from the siege: Fremen units reached them, they fought (balance 0), fled 26 to
Sadnin, healed, fought again, while another army walked in alone. Safe-heal saw no threat within 80 of Sadnin.

Every RALLY_T s per faction: the danger structure D = our structure on our land with the most at-war power around it
(aimod_react within LOCAL, at least RALLY_MIN_H; active: aimod_threat within FLEE_R minus at-war armies standing still
on their own faction's zone there > 0: someone at it or heading there, not a standoff at the border) that our defenders within RALLY_R (non-harvester armies not on a Military mission) plus our
turret cover there, x terrain, can't beat by ENTER (enough: nothing to do, the contest hunt / vanilla Defense fight
it with everyone). The rally point R = our structure on our land at least RALLY_MIN from D with no at-war power
within RALLY_SAFE, the nearest to D (main base RALLY_MB closer: its guns fight with us). Each defender not fighting
(a fight in contact is the retreat logic's), not on a Defense of a structure farther than RALLY_MIN from D (that fight is its own),
and farther than RALLY_AT from R: its order (Resupply / Defense / Patrol) is stopped and it walks to R (doAction Move, every RALLY_MOVE_T s at most); map `rallied` army -> time keeps
it out of vanilla's Resupply / mission picks (aimod_wormheld) while it walks, except a Defense of a structure
farther than RALLY_MIN from D (pick-life wrappers: Atreides' Tuo-tar Defense against a lone raider found 0 candidates
while all armies were held for Tuonah). Map `rly` faction -> D (`rlyt` time):
aimod_unsafe rates every structure within RALLY_MIN of D overwhelming, so vanilla doesn't send heal / flee trips
next to the enemy. Once the gathered force (all within RALLY_R of D) passes ENTER, the rally stops and the contest
hunt (own village besieged) or vanilla's Defense takes them in together. The rally point is kept while it still
qualifies (map `rlyp`). A rally still short after RALLY_GIVEUP s (map `rly0` = since when) commits when the gathered force is at least even
(M >= DEF_HOPE_IN x H, terrain-adjusted; always for a main base): the rally ends, D isn't a rally target for RALLY_COOL s
(map `rlyc`), vanilla's Defense and the contest hunt fight it (log act commit). Below even it concedes D for RALLY_COOL s
(map `rlygu` structure -> time; never a main base; every pass first stops our running Defense orders of a conceded
or hopeless (`dhl` < 30 s) structure, log `dstop`: vanilla's Defense re-sends idle members at the enemy one by one): D and its neighbours within LOCAL (map `rlyg`) can't be picked again, aimod_defend skips it, vanilla's Defense
of it gets no armies (no trickle into a lost cause), and the armies are free for other work (log act giveup).
Before any of this: when the defenders already within RALLY_HERE of D (+ turrets, x terrain) are at least
DEF_HOPE_IN x H, the rally commits at once (log act here, M = that force, Mall = all within RALLY_R): gathering
elsewhere would walk an army that stands together at D away and back (Harkonnen at Qafiel).
Logs `rally` (D, R, H, M, n moved) once per faction per 10 s. In a trap."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.worm import _move_to


def build_rally(cx, helpers, pw, react, threat, terrain, cover, mission):
    """aimod_rally(mil, dt) (see module doc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    _tick(fb, b, cx, t, RALLY_T, 'end')
    # a running Defense of a lost cause (map `rlygu`: conceded within RALLY_COOL; `dhl`: aimod_defend judged it
    # hopeless within 30 s) is stopped: vanilla's Defense sends every idle member back at the enemy, so armies the
    # fight retreat pulled out walked back in one by one (Smugglers' 9-army Defense of Qaf-Al'wan vs 640k Fremen ran
    # on in Action after the retreat; a 24% S_Elite and an S_Sneak went back alone and died)
    reason0 = cx.code.types[cx.fn('logic.ai.AIOrder.stop').type.value].definition.args[1].value
    cancel0 = fb.reg(reason0)
    fb.op('MakeEnum', dst=cancel0, construct=CANCEL, args=[])
    dords = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=dords, offset='ds_done')
    dk, dix = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    dq = fb.reg(cx.t('f64'))
    dst_e = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=dk, src=b.field(dords, 'length'))
    b.loop_head('ds')  # backwards: stop() removes the order from the list
    fb.op('JSLte', a=dk, b=b.const('i32', 0), offset='ds_done')
    fb.op('Sub', dst=dk, a=dk, b=b.const('i32', 1))
    do_ = b.cast(b.call('hl.types.ArrayObj.getDyn', dords, dk), 'logic.ai.AIOrder')
    fb.op('JNull', reg=do_, offset='ds')
    dot = b.field(do_, 'type')
    fb.op('EnumIndex', dst=dix, value=dot)
    fb.op('JNotEq', a=dix, b=b.const('i32', DEFENSE), offset='ds')
    fb.op('EnumField', dst=dst_e, value=dot, construct=DEFENSE, field=0)
    fb.op('JNull', reg=dst_e, offset='ds')
    for mname, lim in (('rlygu', RALLY_COOL), ('dhl', 30)):
        nx = _uid('dsn')
        mv_ = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, mname), fb.dyn(dst_e))
        fb.op('JNull', reg=mv_, offset=nx)
        fb.op('SafeCast', dst=dq, src=mv_)
        fb.op('Sub', dst=dq, a=t, b=dq)
        fb.op('JSLt', a=dq, b=b.const('f64', lim), offset='ds_stop')
        fb.label(nx)
    fb.op('JAlways', offset='ds')
    fb.label('ds_stop')
    b.call('logic.ai.AIOrder.stop', do_, cancel0)
    _log_ev(fb, b, cx, helpers, 'dstop', [('f', fb.get(fac, 'kind')), ('s', dst_e), ('n', b.field(b.field(do_, 'units'), 'length'))])
    fb.op('JAlways', offset='ds')
    fb.label('ds_done')
    structs = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=structs, offset='end')
    sn = b.field(structs, 'length')
    my_armies, mlen = _my_armies(fb, b, fac, 'end')
    rly, rlyt, rallied = (_global_map(fb, b, cx, n) for n in ('rly', 'rlyt', 'rallied'))
    rly0, rlyp, rlygu, rlyg, rlyc = (_global_map(fb, b, cx, n) for n in ('rly0', 'rlyp', 'rlygu', 'rlyg', 'rlyc'))
    gq = fb.reg(cx.t('f64'))
    # the last conceded D (map `rlyg` faction -> D) while within RALLY_COOL: its neighbours within LOCAL face the
    # same stack, no new rally for them either
    gde = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=gde)
    lgv = b.call('haxe.ds.ObjectMap.get', rlyg, fb.dyn(fac))
    fb.op('JNull', reg=lgv, offset='lgdone')
    lgt = b.call('haxe.ds.ObjectMap.get', rlygu, lgv)
    fb.op('JNull', reg=lgt, offset='lgdone')
    fb.op('SafeCast', dst=gq, src=lgt)
    fb.op('Sub', dst=gq, a=t, b=gq)
    fb.op('JSGte', a=gq, b=b.const('f64', RALLY_COOL), offset='lgdone')
    fb.op('SafeCast', dst=gde, src=lgv)
    fb.label('lgdone')
    zi = b.const('i32', 0)
    zero = b.const('f64', 0)
    i, j = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    h, m, p, tf, bh, bm, d, bd, cv, act = (fb.reg(cx.t('f64')) for _ in range(10))
    ok = fb.reg(cx.t('bool'))
    se, dz, rp = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    rr, local = b.const('f64', RALLY_R), b.const('f64', LOCAL)
    nul_e = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=nul_e)
    t_true, no_arr = fb.reg(cx.t('bool')), fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Bool', dst=t_true, value=True)
    fb.op('Null', dst=no_arr)

    def our_power(at, dst, lbl, rad=rr):
        """dst = power of our defenders within rad (RALLY_R) of `at` (no harvesters; an army on a Military mission
        only within RALLY_HERE: it stands in that fight, e.g. our contest of `at`; never moved by the rally)."""
        fb.op('Mov', dst=dst, src=zero)
        a = _army_loop(fb, b, my_armies, mlen, j, lbl, lbl + 'd')
        fb.op('JNotNull', reg=b.field(a, 'harvestComponent'), offset=lbl)
        fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', a, at))
        fb.op('JSGt', a=d, b=rad, offset=lbl)
        fb.op('Call2', dst=ok, fun=mission, arg0=fac, arg1=a)
        fb.op('JFalse', cond=ok, offset=lbl + 'c')
        fb.op('JSGt', a=d, b=b.const('f64', RALLY_HERE), offset=lbl)
        fb.label(lbl + 'c')
        fb.op('Call1', dst=p, fun=pw, arg0=a)
        fb.op('Add', dst=dst, a=dst, b=p)
        fb.op('JAlways', offset=lbl)
        fb.label(lbl + 'd')

    # 1. the danger structure: most at-war power around it, our side short of ENTER (x RALLY_HYST while one runs)
    need = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=need, src=_ratio(fb, b, ENTER))
    fb.op('JNull', reg=b.call('haxe.ds.ObjectMap.get', rly, fb.dyn(fac)), offset='hy')
    fb.op('Mul', dst=need, a=need, b=_ratio(fb, b, RALLY_HYST))
    fb.label('hy')
    fb.op('Null', dst=dz)
    fb.op('Mov', dst=bh, src=zero)
    fb.op('Mov', dst=i, src=zi)
    b.loop_head('s')
    fb.op('JSGte', a=i, b=sn, offset='sdone')
    s = b.cast(b.call('hl.types.ArrayObj.getDyn', structs, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=s, offset='s')
    fb.op('Mov', dst=se, src=s)
    z = b.call('ent.Entity.get_zone', se)
    fb.op('JNull', reg=z, offset='s')
    fb.op('JNotEq', a=b.field(z, 'owner'), b=fac, offset='s')  # on our land
    # given up less than RALLY_COOL s ago (map `rlygu` structure -> time): conceded, the armies do other things
    guv = b.call('haxe.ds.ObjectMap.get', rlygu, fb.dyn(se))
    fb.op('JNull', reg=guv, offset='sgu')
    fb.op('SafeCast', dst=gq, src=guv)
    fb.op('Sub', dst=gq, a=t, b=gq)
    fb.op('JSLt', a=gq, b=b.const('f64', RALLY_COOL), offset='s')
    fb.label('sgu')
    # committed less than RALLY_COOL s ago (map `rlyc`): the gathered force is fighting it, no new rally
    cmv = b.call('haxe.ds.ObjectMap.get', rlyc, fb.dyn(se))
    fb.op('JNull', reg=cmv, offset='sgc')
    fb.op('SafeCast', dst=gq, src=cmv)
    fb.op('Sub', dst=gq, a=t, b=gq)
    fb.op('JSLt', a=gq, b=b.const('f64', RALLY_COOL), offset='s')
    fb.label('sgc')
    fb.op('JNull', reg=gde, offset='sgn')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', s), offset='sgn')  # the capital always rallies
    fb.op('JSLt', a=b.call('ent.Entity.getDistTo', se, gde), b=local, offset='s')
    fb.label('sgn')
    fb.op('Call3', dst=h, fun=react, arg0=fac, arg1=se, arg2=local)
    fb.op('JSLt', a=h, b=b.const('f64', RALLY_MIN_H), offset='s')
    fb.op('JSLte', a=h, b=bh, offset='s')
    # active: an at-war army at it (FLEE_R) or heading there; a stack idling at its own border is a standoff, not
    # an attack (Smugglers walked 8 armies Shariyah -> Tuek -> Shariyah every 30-60 s: vanilla Patrol out, rally
    # home, for Atreides armies standing at Hadnin 113 away)
    fb.op('Call3', dst=act, fun=threat, arg0=fac, arg1=se, arg2=b.const('f64', FLEE_R))
    fb.op('JSLte', a=act, b=zero, offset='s')
    # ... minus at-war armies standing still on their own land: a border standoff, not an attack (Atreides' 7 armies
    # idled 90 from Qafmah on their zone; Smugglers rallied, gave up and rallied again for minutes while vanilla
    # Patrols walked the same armies to Hul-Al'ha)
    sarr = b.field(_state(fb, b, cx), 'armies')
    fb.op('JNull', reg=sarr, offset='sok')
    sk = fb.reg(cx.t('i32'))
    sx = _army_loop(fb, b, sarr, b.field(sarr, 'length'), sk, 'so', 'sok')
    sxo = b.call('ent.Entity.get_owner', sx)
    fb.op('JNull', reg=sxo, offset='so')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', _state(fb, b, cx), fac, sxo), offset='so')
    fb.op('JTrue', cond=b.call('ent.Unit.isMoving', sx), offset='so')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', sx, se), b=b.const('f64', FLEE_R), offset='so')
    sxz = b.call('ent.Entity.get_zone', sx)
    fb.op('JNull', reg=sxz, offset='so')
    fb.op('JNotEq', a=b.field(sxz, 'owner'), b=sxo, offset='so')
    fb.op('Call1', dst=p, fun=pw, arg0=sx)
    fb.op('Sub', dst=act, a=act, b=p)
    fb.op('JAlways', offset='so')
    fb.label('sok')
    fb.op('JSLte', a=act, b=zero, offset='s')
    our_power(se, m, 'dp')
    fb.op('CallN', dst=cv, fun=cover, args=[fac, se, nul_e, t_true, no_arr])  # our turrets there
    fb.op('Add', dst=m, a=m, b=cv)
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=z)
    fb.op('Mul', dst=m, a=m, b=tf)
    fb.op('Mul', dst=p, a=h, b=need)
    fb.op('JSGte', a=m, b=p, offset='s')  # enough to fight it with everyone: not a rally
    fb.op('Mov', dst=bh, src=h)
    fb.op('Mov', dst=bm, src=m)
    fb.op('Mov', dst=dz, src=se)
    fb.op('JAlways', offset='s')
    fb.label('sdone')
    fb.op('JNull', reg=dz, offset='off')
    # the defenders already at D (within RALLY_HERE) + our turrets there, x terrain, are at least even: fight it
    # now with them, the rest walks in (same commit as below, without the wait). Gathering elsewhere would walk an
    # army that is already together away from D and back: Harkonnen's 21 armies (1.28M vs 0.75-1.0M Fremen, all
    # within 170 of Qafiel) rallied to Had-tah, then Carthag 530 away, came back after the 60 s commit in three
    # waves 150 apart and lost the front ones at raw 0-20 (and again at 52:44 with 10 armies at the village)
    # never on a D aimod_defend judged hopeless within 30 s (map `dhl`, its own measure): its Defense would be
    # stopped by the dstop pass above every 2 s while RALLY_COOL keeps the rally off: armies idle at D
    hdv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'dhl'), fb.dyn(dz))
    fb.op('JNull', reg=hdv, offset='hdok')
    fb.op('SafeCast', dst=gq, src=hdv)
    fb.op('Sub', dst=gq, a=t, b=gq)
    fb.op('JSLt', a=gq, b=b.const('f64', 30), offset='nothere')
    fb.label('hdok')
    our_power(dz, m, 'hp', b.const('f64', RALLY_HERE))
    # turrets around D but not D's own: a besieged village's turrets are silent (as aimod_defend counts them)
    fb.op('CallN', dst=cv, fun=cover, args=[fac, dz, dz, t_true, no_arr])
    fb.op('Add', dst=m, a=m, b=cv)
    hz = b.call('ent.Entity.get_zone', dz)
    fb.op('JNull', reg=hz, offset='nothere')
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=hz)
    fb.op('Mul', dst=m, a=m, b=tf)
    fb.op('Mul', dst=p, a=bh, b=_ratio(fb, b, DEF_HOPE_IN))
    fb.op('JSLt', a=m, b=p, offset='nothere')
    b.call('haxe.ds.ObjectMap.set', rlyc, fb.dyn(dz), fb.dyn(t))
    for mp in (rly, rly0, rlyp):
        b.call('haxe.ds.ObjectMap.remove', mp, fb.dyn(fac))
    _log_ev(fb, b, cx, helpers, 'rally', [('f', fb.get(fac, 'kind')), ('act', 'here'), ('s', dz), ('H', bh),
                                          ('M', m), ('Mall', bm)])
    fb.op('JAlways', offset='end')
    fb.label('nothere')
    # a rally running RALLY_GIVEUP s (map `rly0` = since when, whichever D) and still short (a running rally is
    # short by definition: the gathered force would have ended it): concede D for RALLY_COOL s instead of holding
    # every army for strength that never comes (Atreides rallied 4.5 min for Tuonah, 607k vs 600-900k Fremen,
    # while a raider hit Tuo-tar)
    fb.op('JNull', reg=b.call('haxe.ds.ObjectMap.get', rly, fb.dyn(fac)), offset='gnew')
    g0 = b.call('haxe.ds.ObjectMap.get', rly0, fb.dyn(fac))
    fb.op('JNull', reg=g0, offset='gnew')
    fb.op('SafeCast', dst=gq, src=g0)
    fb.op('Sub', dst=gq, a=t, b=gq)
    fb.op('JSLte', a=gq, b=b.const('f64', RALLY_GIVEUP), offset='gkeep')
    # at least even (terrain-adjusted, as the hopeless test): commit, the gathered force fights it (Smugglers had 334k
    # vs Atreides' 284k at Qafmah, gave up for not reaching 1.7x, and its Defense got no armies while the pillage
    # ran); below even: concede (never the capital: a main base commits)
    fb.op('Mul', dst=p, a=bh, b=_ratio(fb, b, DEF_HOPE_IN))
    fb.op('JSGte', a=bm, b=p, offset='gcommit')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', b.cast(fb.dyn(dz), 'ent.Structure')), offset='gcommit')
    b.call('haxe.ds.ObjectMap.set', rlygu, fb.dyn(dz), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', rlyg, fb.dyn(fac), fb.dyn(dz))
    for mp in (rly, rly0, rlyp):
        b.call('haxe.ds.ObjectMap.remove', mp, fb.dyn(fac))
    _log_ev(fb, b, cx, helpers, 'rally', [('f', fb.get(fac, 'kind')), ('act', 'giveup'), ('s', dz), ('H', bh),
                                          ('M', bm)])
    fb.op('JAlways', offset='end')
    fb.label('gcommit')
    b.call('haxe.ds.ObjectMap.set', rlyc, fb.dyn(dz), fb.dyn(t))
    for mp in (rly, rly0, rlyp):
        b.call('haxe.ds.ObjectMap.remove', mp, fb.dyn(fac))
    _log_ev(fb, b, cx, helpers, 'rally', [('f', fb.get(fac, 'kind')), ('act', 'commit'), ('s', dz), ('H', bh),
                                          ('M', bm)])
    fb.op('JAlways', offset='end')
    fb.label('gnew')
    b.call('haxe.ds.ObjectMap.set', rly0, fb.dyn(fac), fb.dyn(t))
    fb.label('gkeep')
    b.call('haxe.ds.ObjectMap.set', rly, fb.dyn(fac), fb.dyn(dz))
    b.call('haxe.ds.ObjectMap.set', rlyt, fb.dyn(fac), fb.dyn(t))
    # 2. the rally point: the last one while it still qualifies (map `rlyp`: armies don't walk between points as
    # the enemy moves: Atreides' went Arrakeen -> Pelsan -> Ultah -> Fondad -> Ursan in 3 min), else the nearest
    fb.op('Null', dst=rp)
    pv = b.call('haxe.ds.ObjectMap.get', rlyp, fb.dyn(fac))
    fb.op('JNull', reg=pv, offset='rnew')
    fb.op('SafeCast', dst=se, src=pv)
    fb.op('JNotEq', a=b.call('ent.Entity.get_owner', se), b=fac, offset='rnew')
    zp = b.call('ent.Entity.get_zone', se)
    fb.op('JNull', reg=zp, offset='rnew')
    fb.op('JNotEq', a=b.field(zp, 'owner'), b=fac, offset='rnew')
    fb.op('JSLt', a=b.call('ent.Entity.getDistTo', se, dz), b=b.const('f64', RALLY_MIN), offset='rnew')
    fb.op('Call3', dst=h, fun=threat, arg0=fac, arg1=se, arg2=b.const('f64', RALLY_SAFE))
    fb.op('JSGt', a=h, b=zero, offset='rnew')
    fb.op('Mov', dst=rp, src=se)
    fb.op('JAlways', offset='rdone')
    fb.label('rnew')
    fb.op('Mov', dst=bd, src=b.const('f64', 1 << 30))
    fb.op('Mov', dst=i, src=zi)
    b.loop_head('r')
    fb.op('JSGte', a=i, b=sn, offset='rdone')
    s2 = b.cast(b.call('hl.types.ArrayObj.getDyn', structs, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=s2, offset='r')
    fb.op('Mov', dst=se, src=s2)
    z2 = b.call('ent.Entity.get_zone', se)
    fb.op('JNull', reg=z2, offset='r')
    fb.op('JNotEq', a=b.field(z2, 'owner'), b=fac, offset='r')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', se, dz))
    fb.op('JSLt', a=d, b=b.const('f64', RALLY_MIN), offset='r')
    fb.op('Call3', dst=h, fun=threat, arg0=fac, arg1=se, arg2=b.const('f64', RALLY_SAFE))
    fb.op('JSGt', a=h, b=zero, offset='r')
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', s2), offset='rmb')
    fb.op('Sub', dst=d, a=d, b=b.const('f64', RALLY_MB))
    fb.label('rmb')
    fb.op('JSGte', a=d, b=bd, offset='r')
    fb.op('Mov', dst=bd, src=d)
    fb.op('Mov', dst=rp, src=se)
    fb.op('JAlways', offset='r')
    fb.label('rdone')
    fb.op('JNull', reg=rp, offset='end')
    b.call('haxe.ds.ObjectMap.set', rlyp, fb.dyn(fac), fb.dyn(rp))
    # 3. bring the defenders to it
    n = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=n, src=zi)
    reason = cx.code.types[cx.fn('logic.ai.AIOrder.stop').type.value].definition.args[1].value
    cancel = fb.reg(reason)
    fb.op('MakeEnum', dst=cancel, construct=CANCEL, args=[])
    a = _army_loop(fb, b, my_armies, mlen, j, 'a', 'adone')
    fb.op('JNotNull', reg=b.field(a, 'harvestComponent'), offset='a')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', a, dz), b=rr, offset='a')
    fb.op('Call2', dst=ok, fun=mission, arg0=fac, arg1=a)
    fb.op('JTrue', cond=ok, offset='a')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', a), offset='a')  # in contact: the retreat logic decides
    # defending another structure (vanilla Defense of one farther than RALLY_MIN from D): that fight is winnable on
    # its own (Atreides' rally for Tuonah stopped the Defense of Tuo-tar against a lone neutral raider)
    dse = fb.reg(cx.t('ent.Entity'))
    _defends(fb, b, cx, fac, a, dse, 'ndef')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', dse, dz), b=b.const('f64', RALLY_MIN), offset='a')
    fb.label('ndef')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', a, rp), b=b.const('f64', RALLY_AT), offset='a')  # arrived
    b.call('haxe.ds.ObjectMap.set', rallied, fb.dyn(a), fb.dyn(t))
    _throttle(fb, b, cx, 'rallymv', a, RALLY_MOVE_T, 'a')
    ao = b.field(a, 'aiOrder')
    fb.op('JNull', reg=ao, offset='nord')
    b.call('logic.ai.AIOrder.stop', ao, cancel)
    fb.label('nord')
    _move_to(fb, b, cx, a, b.field(rp, 'posx'), b.field(rp, 'posy'), fac)
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset='a')
    fb.label('adone')
    _throttle(fb, b, cx, 'rally', fac, 10, 'end')
    _log_ev(fb, b, cx, helpers, 'rally', [('f', fb.get(fac, 'kind')), ('act', 'rally'), ('s', dz), ('r', rp),
                                          ('H', bh), ('M', bm), ('n', n)])
    fb.op('JAlways', offset='end')
    fb.label('off')  # no danger structure: rally over
    fb.op('JNull', reg=b.call('haxe.ds.ObjectMap.get', rly, fb.dyn(fac)), offset='end')
    for mp in (rly, rly0, rlyp):
        b.call('haxe.ds.ObjectMap.remove', mp, fb.dyn(fac))
    _log_ev(fb, b, cx, helpers, 'rally', [('f', fb.get(fac, 'kind')), ('act', 'off')])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
