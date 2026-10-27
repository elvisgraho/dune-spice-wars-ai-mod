"""Rally: gather strength instead of feeding armies one at a time (AI-POLICY §1.6 concentrate, defense).

The failure: Fremen took Atreides' Aeganim with 10 armies (~350k) against Atreides' 7 (~235k, too few even at home
x1.3). Vanilla had no answer between "Defense with enough power" and nothing: 2 armies idled 330 away, 2 stopped 140
short, and 2 kept healing at Sadnin 84 from the siege: Fremen units reached them, they fought (balance 0), fled 26 to
Sadnin, healed, fought again, while another army walked in alone. Safe-heal saw no threat within 80 of Sadnin.

Every RALLY_T s per faction: the danger structure D = our structure on our land with the most at-war power around it
(aimod_react within LOCAL, at least RALLY_MIN_H; active: aimod_threat (arrive variant: movers count only if their path ends there) within FLEE_R minus at-war armies standing still
on their own faction's zone there > 0: someone at it or heading there, not a standoff at the border) that our defenders within RALLY_R (non-harvester armies not on a Military mission) plus our
turret cover there, x terrain, can't beat by ENTER (enough: nothing to do, the contest hunt / vanilla Defense fight
it with everyone). The rally point R = our structure on our land at least RALLY_MIN from D with no at-war power
within RALLY_SAFE, the nearest to D (main base RALLY_MB closer: its guns fight with us; one whose walk from the
defenders' centroid passes within CROSS_R of D, i.e. on the enemy's side, loses to any on their side; never farther than
RALLY_PT_MAX from D: none = no rally). Each defender not fighting
(a fight in contact is the retreat logic's), not on a Defense of a structure farther than RALLY_MIN from D (that fight is its own),
and farther than R's radius + RALLY_AT from R (and, on hostile land, with supply for the walk: SUP_WALK x distance +
SUP_RESERVE): its order (Resupply / Defense / Patrol) is stopped and it walks to the
gather point RALLY_OFF outside R's radius on D's side (a Patrol order to R, prio 0, "Move": vanilla plans the path, shuttles included; a plain Move never flies; a
refused order falls back to doAction Move; every RALLY_MOVE_T s at most, and an army already in our Patrol to R is
left alone; R's centre is unreachable for a main base: armies were re-sent there every 5 s); a live P_RALLY claim (rules/tasks.py) keeps
it out of vanilla's Resupply / mission picks (aimod_wormheld, claims) while it walks, except a Defense of a structure
farther than RALLY_MIN from D (pick-life wrappers: Atreides' Tuo-tar Defense against a lone raider found 0 candidates
while all armies were held for Tuonah). Map `rly` faction -> D (`rlyt` time):
aimod_unsafe rates every structure within RALLY_MIN of D overwhelming, so vanilla doesn't send heal / flee trips
next to the enemy. Once the gathered force (all within RALLY_R of D) passes ENTER, the rally stops and the contest
hunt (own village besieged) or vanilla's Defense takes them in together. The rally point is kept while it still
qualifies (map `rlyp`). A rally still short after RALLY_GIVEUP s (map `rly0` = since when) commits when the gathered force is at least even
(M >= DEF_HOPE_IN x H, terrain-adjusted; always for a main base): the rally ends, D and its neighbours within LOCAL
(map `rlyk` faction -> committed D) aren't rally targets for RALLY_COOL s (map `rlyc`), vanilla's Defense and the
contest hunt fight it (log act commit). Below even, or judged hopeless (`dhl` < 30 s), it concedes D for RALLY_COOL s
(map `rlygu` structure -> time, `rlyguh` -> the local threat then (aimod_threat within FLEE_R): reopened (log act reopen) as soon
as that same measure drops below CONCEDE_DROP x it, not within CONCEDE_HOLD s of the concession; never a main base; every pass first stops our running Defense orders of a conceded
or hopeless (`dhl` < 30 s) structure, log `dstop`: vanilla's Defense re-sends idle members at the enemy one by one): D and its neighbours within LOCAL (map `rlyg`) can't be picked again, aimod_defend skips it, vanilla's Defense
of it gets no armies (no trickle into a lost cause), and the armies are free for other work (log act giveup).
Race (first, user: arrival time): while D's occupation progresses (_cap_rem), only defenders that walk to D before it
ends (+ CONTEST_SLACK; aimod_eta: walking or via our airfields / main base) count, with our turrets there, x terrain: at least DEF_HOPE_IN x H -> commit
now (why race), else concede now (log act race, rem, why race / late); no gathering then. (The `cap` commit below is
for a progress the race couldn't read.)
While D's occupation progresses, the rally commits as soon as the gathered force is at least DEF_HOPE_IN x H
(terrain-adjusted; not on a D judged hopeless within 30 s): log act commit why cap (timeout: why time).
Before any of this: when the defenders already within RALLY_HERE of D (+ turrets, x terrain) are at least
DEF_HOPE_IN x H, the rally commits at once (log act here, M = that force, Mall = all within RALLY_R): gathering
elsewhere would walk an army that stands together at D away and back (Harkonnen at Qafiel).
Logs `rally` (D, R, H, M, n moved) once per faction per 10 s. In a trap."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.worm import _move_to

RALLY_FC_T = RALLY_R // CONTEST_SPD  # s: the rally's pick, off and commit tests read the battle forecast at D over this window
RP_FC_T = LOCAL // CONTEST_SPD  # s: the recruit point's forecast window (the fight there is now)


def build_rally(cx, helpers, pw, threat, mission, forecast):
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
    rly, rlyt = (_global_map(fb, b, cx, n) for n in ('rly', 'rlyt'))
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
    # the last committed D (map `rlyk` faction -> D, `here` / timeout commit) while within RALLY_COOL: its neighbours
    # within LOCAL face the same stack; a rally for one of them would walk the committed force at D away (vanilla's
    # Defense of D may not have picked them yet: its required ratio re-rolls every 0.5 s)
    gce = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=gce)
    lkv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rlyk'), fb.dyn(fac))
    fb.op('JNull', reg=lkv, offset='lkdone')
    lkt = b.call('haxe.ds.ObjectMap.get', rlyc, lkv)
    fb.op('JNull', reg=lkt, offset='lkdone')
    fb.op('SafeCast', dst=gq, src=lkt)
    fb.op('Sub', dst=gq, a=t, b=gq)
    fb.op('JSGte', a=gq, b=b.const('f64', RALLY_COOL), offset='lkdone')
    fb.op('SafeCast', dst=gce, src=lkv)
    fb.label('lkdone')
    zi = b.const('i32', 0)
    zero = b.const('f64', 0)
    i, j = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    h, m, p, tf, bh, bm, d, bd, cv, act = (fb.reg(cx.t('f64')) for _ in range(10))
    ok = fb.reg(cx.t('bool'))
    se, dz, rp = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    rr, local = b.const('f64', RALLY_R), b.const('f64', LOCAL)
    nul_e = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=nul_e)
    t_true, t_false, no_arr = fb.reg(cx.t('bool')), fb.reg(cx.t('bool')), fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Bool', dst=t_true, value=True)
    fb.op('Bool', dst=t_false, value=False)
    fb.op('Null', dst=no_arr)

    def our_power(at, dst, lbl, rad=rr, excl=None, into=None):
        """dst = power of our defenders within rad (RALLY_R) of `at` (no harvesters; an army on a Military mission
        only within RALLY_HERE: it stands in that fight, e.g. our contest of `at`; never moved by the rally; excl:
        an entity register (may be null), armies within RALLY_AT of it don't count; into: an array register that
        collects the counted armies)."""
        fb.op('Mov', dst=dst, src=zero)
        a = _army_loop(fb, b, my_armies, mlen, j, lbl, lbl + 'd')
        fb.op('JNotNull', reg=b.field(a, 'harvestComponent'), offset=lbl)
        if excl is not None:
            xl = _uid('xl')
            fb.op('JNull', reg=excl, offset=xl)
            fb.op('JSLte', a=b.call('ent.Entity.getDistTo', a, excl), b=b.const('f64', RALLY_AT), offset=lbl)
            fb.label(xl)
        fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', a, at))
        fb.op('JSGt', a=d, b=rad, offset=lbl)
        fb.op('Call2', dst=ok, fun=mission, arg0=fac, arg1=a)
        fb.op('JFalse', cond=ok, offset=lbl + 'c')
        fb.op('JSGt', a=d, b=b.const('f64', RALLY_HERE), offset=lbl)
        fb.label(lbl + 'c')
        fb.op('Call1', dst=p, fun=pw, arg0=a)
        fb.op('Add', dst=dst, a=dst, b=p)
        if into is not None:
            b.call('hl.types.ArrayObj.push', into, fb.dyn(a))
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
    fb.op('JSGte', a=gq, b=b.const('f64', RALLY_COOL), offset='sgu')
    # reopened: the threat that made us concede has left (now < CONCEDE_DROP x their side then): the concession ends,
    # so vanilla's Defense, the contest hunt and the rally may take it back (Smugglers conceded Nunmah to 905k of
    # Fremen; Fremen left and a 23-power remnant finished the liberation inside the cooldown, match 2026-10-24 late)
    # ... but not within CONCEDE_HOLD s of the concession (one empty reading as the stack steps out of FLEE_R reopened
    # Smugglers' remote Nun-Al'khelon 15-22 s after each give-up, twice, armies walking back and forth)
    fb.op('JSLt', a=gq, b=b.const('f64', CONCEDE_HOLD), offset='s')
    ghv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rlyguh'), fb.dyn(se))
    fb.op('JNull', reg=ghv, offset='s')
    gh0, gh1 = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=gh0, src=ghv)
    fb.op('Mul', dst=gh0, a=gh0, b=_ratio(fb, b, CONCEDE_DROP))
    fb.op('Call3', dst=gh1, fun=threat, arg0=fac, arg1=se, arg2=b.const('f64', FLEE_R))
    fb.op('JSGte', a=gh1, b=gh0, offset='s')
    b.call('haxe.ds.ObjectMap.remove', rlygu, fb.dyn(se))
    _log_ev(fb, b, cx, helpers, 'rally', [('f', fb.get(fac, 'kind')), ('act', 'reopen'), ('s', se), ('H', gh1)])
    fb.label('sgu')
    # committed less than RALLY_COOL s ago (map `rlyc`): the gathered force is fighting it, no new rally
    cmv = b.call('haxe.ds.ObjectMap.get', rlyc, fb.dyn(se))
    fb.op('JNull', reg=cmv, offset='sgc')
    fb.op('SafeCast', dst=gq, src=cmv)
    fb.op('Sub', dst=gq, a=t, b=gq)
    fb.op('JSLt', a=gq, b=b.const('f64', RALLY_COOL), offset='s')
    fb.label('sgc')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', s), offset='sgn')  # the capital always rallies
    fb.op('JNull', reg=gde, offset='sgk')
    fb.op('JSLt', a=b.call('ent.Entity.getDistTo', se, gde), b=local, offset='s')
    fb.label('sgk')
    fb.op('JNull', reg=gce, offset='sgn')
    fb.op('JSLt', a=b.call('ent.Entity.getDistTo', se, gce), b=local, offset='s')
    fb.label('sgn')
    # nobody at it or heading there: no danger (the cheap gate before the forecast; the active test below refines it)
    fb.op('Call3', dst=act, fun=threat, arg0=fac, arg1=se, arg2=b.const('f64', FLEE_R))
    fb.op('JSLte', a=act, b=zero, offset='s')
    # both sides from the battle forecast at it over RALLY_FC_T, the window the rally's commit tests read (ARCHITECTURE-
    # PLAN step 1; was aimod_react within LOCAL + at-war cover vs our armies within RALLY_R + our cover x terrain: the
    # pick and the commit judged one fight on two measures). Theirs: who can be there, at-war turret cover (as
    # aimod_defend's hopeless test: Smugglers at Tuo-Al'waz once counted Ash-bat's battery on one side only); ours:
    # who arrives in time (Military missions only within RALLY_HERE), our cover, D's militia, x terrain
    dfc = fb.reg(cx.t('f64'))
    fb.op('CallN', dst=dfc, fun=forecast, args=[fac, se, b.const('f64', RALLY_FC_T), t_false, no_arr])
    _fc_sides(fb, b, cx, fac, m, h, 's')
    fb.op('JSLt', a=h, b=b.const('f64', RALLY_MIN_H), offset='s')
    fb.op('JSLte', a=h, b=bh, offset='s')
    # active: an at-war army at it (FLEE_R) or heading there; a stack idling at its own border is a standoff, not
    # an attack (Smugglers walked 8 armies Shariyah -> Tuek -> Shariyah every 30-60 s: vanilla Patrol out, rally
    # home, for Atreides armies standing at Hadnin 113 away): `act` was read above
    # ... minus at-war armies standing still on their own land: a border standoff, not an attack (Atreides' 7 armies
    # idled 90 from Qafmah on their zone; Smugglers rallied, gave up and rallied again for minutes while vanilla
    # Patrols walked the same armies to Hul-Al'ha)
    sarr = b.field(_state(fb, b, cx), 'armies')
    fb.op('JNull', reg=sarr, offset='sok')
    sk = fb.reg(cx.t('i32'))
    sx = _army_loop(fb, b, sarr, b.field(sarr, 'length'), sk, 'so', 'sok')
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', sx, fac), offset='so')  # fog: unseen ones stay counted
    sxo = b.call('ent.Entity.get_owner', sx)
    spe_t = cx.code.types[cx.fn('ent.MobileEntity.getCurrentPathEnd').type.value].definition.ret.value
    spe = fb.reg(spe_t)
    fb.op('JNotNull', reg=sxo, offset='so_ow')
    # ... and neutral raiders on us (rebels of a rebelling village, marauders): raider sieges are the contest hunt's
    # and vanilla Defense's, not a rally posture. Rebels at Harkonnen's Tab-esek, with Atreides' stack standing 82
    # away, made a rally -> giveup -> `dstop` of the Defense against the rebels every ~150 s: the rebellion never ended
    srd = b.field(sx, 'raid')
    fb.op('JNull', reg=srd, offset='so')
    fb.op('JNotEq', a=b.field(srd, 'targetFaction'), b=fac, offset='so')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', sx, se), b=b.const('f64', FLEE_R), offset='so_sub')
    fb.op('JFalse', cond=b.call('ent.Unit.isMoving', sx), offset='so')
    fb.op('Mov', dst=spe, src=b.call('ent.MobileEntity.getCurrentPathEnd', sx))
    fb.op('JNull', reg=spe, offset='so')
    fb.op('JAlways', offset='so_pe')
    fb.label('so_ow')
    # our own armies first: areAtWar(us, us) logs a vanilla warning + entity dump per call (12k in one match log)
    fb.op('JEq', a=sxo, b=fac, offset='so')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', _state(fb, b, cx), fac, sxo), offset='so')
    sxz = b.call('ent.Entity.get_zone', sx)
    fb.op('JNull', reg=sxz, offset='so')
    fb.op('JNotEq', a=b.field(sxz, 'owner'), b=sxo, offset='so')
    fb.op('JFalse', cond=b.call('ent.Unit.isMoving', sx), offset='so_st')
    # a mover whose path ends on its own land too shuffles inside it (Patrol / Resupply at its border village):
    # Atreides' stack at Nundad, 82 from Harkonnen's Tab-esek, kept Harkonnen in rally -> giveup -> rally all match
    fb.op('Mov', dst=spe, src=b.call('ent.MobileEntity.getCurrentPathEnd', sx))
    fb.op('JNull', reg=spe, offset='so')
    sgs = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=sgs, **{'global': cx.global_of('$Game')})
    swd = b.field(b.field(sgs, 'inst'), 'world')
    fb.op('JNull', reg=swd, offset='so')
    spz = b.call('world.World.getZoneAt', swd, b.field(spe, 'x'), b.field(spe, 'y'))
    fb.op('JNull', reg=spz, offset='so')
    fb.op('JNotEq', a=b.field(spz, 'owner'), b=sxo, offset='so')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', sx, se), b=b.const('f64', FLEE_R), offset='so_sub')
    fb.label('so_pe')
    sdx, sdy = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))  # not near yet: counted only if its path ends within FLEE_R
    fb.op('Sub', dst=sdx, a=b.field(spe, 'x'), b=b.field(se, 'posx'))
    fb.op('Sub', dst=sdy, a=b.field(spe, 'y'), b=b.field(se, 'posy'))
    fb.op('Mul', dst=sdx, a=sdx, b=sdx)
    fb.op('Mul', dst=sdy, a=sdy, b=sdy)
    fb.op('Add', dst=sdx, a=sdx, b=sdy)
    fb.op('JSGt', a=sdx, b=b.const('f64', FLEE_R * FLEE_R), offset='so')
    fb.op('JAlways', offset='so_sub')
    fb.label('so_st')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', sx, se), b=b.const('f64', FLEE_R), offset='so')
    fb.label('so_sub')
    fb.op('Call1', dst=p, fun=pw, arg0=sx)
    fb.op('Sub', dst=act, a=act, b=p)
    fb.op('JAlways', offset='so')
    fb.label('sok')
    fb.op('JSLte', a=act, b=zero, offset='s')
    fb.op('JSGte', a=dfc, b=need, offset='s')  # enough to fight it with everyone: not a rally
    fb.op('Mov', dst=bh, src=h)
    fb.op('Mov', dst=bm, src=m)
    fb.op('Mov', dst=dz, src=se)
    fb.op('JAlways', offset='s')
    fb.label('sdone')
    fb.op('JNull', reg=dz, offset='off')
    # task board (rules/board.py): the danger structure, posted (a rally launches nothing itself)
    rbf = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=rbf, src=b.const('f64', 0))
    fb.op('JSLte', a=bh, b=zero, offset='rb_z')
    fb.op('SDiv', dst=rbf, a=bm, b=bh)
    fb.label('rb_z')
    _bd = fb.reg(cx.t('bool'))
    _bk = fb.reg(cx.t('String'))
    fb.op('Mov', dst=_bk, src=fb.string('rally'))
    _bT = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=_bT, src=b.const('f64', RALLY_FC_T))
    _ba = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=_ba)
    _bq = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=_bq, value=False)
    _be = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=_be, src=dz)
    fb.op('CallN', dst=_bd, fun=helpers['board'], args=[fac, _bk, _be, rbf, _bT, _ba, _bq])

    # race (user: defense decisions must weigh arrival time): once D's capture progresses, gathering is too slow by
    # definition. Only defenders that walk to D (CONTEST_SPD) before it ends (_cap_rem + CONTEST_SLACK) count, with our
    # turrets there, x terrain: at least DEF_HOPE_IN x their side -> commit now (they go straight in), else concede
    # now and free the armies. Smugglers committed for Dalsud 67 s before Harkonnen's Liberate ended, from Tuek, and
    # gathered for Qalnin at Aeg-tar until it was lost (match 2026-10-23 19:32). Main bases can't be captured: skipped
    cwhy = fb.reg(cx.t('String'))  # the commit's reason (log)
    rs = b.cast(fb.dyn(dz), 'ent.Structure')
    fb.op('JNull', reg=rs, offset='norace')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', rs), offset='norace')
    rrem, _rp = _cap_rem(fb, b, cx, rs, t, 'norace', 'norace')  # measured rate only
    # the battle forecast at D within the remaining time (rules/forecast.py: their armies that can be there, their
    # cover; ours that arrive in time, walking or flying, our cover and D's militia, x terrain)
    lim, fc = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Add', dst=lim, a=rrem, b=b.const('f64', CONTEST_SLACK))
    fb.op('CallN', dst=fc, fun=forecast, args=[fac, dz, lim, t_false, no_arr])
    _fc_sides(fb, b, cx, fac, bm, bh, 'norace')
    rwhy = fb.reg(cx.t('String'))
    fb.op('Mov', dst=rwhy, src=fb.string('late'))
    fb.op('Mov', dst=p, src=_ratio(fb, b, DEF_HOPE_IN))
    fb.op('JSLt', a=fc, b=p, offset='rlog')
    fb.op('Mov', dst=rwhy, src=fb.string('race'))
    fb.label('rlog')
    _throttle(fb, b, cx, 'rrace', dz, 10, 'rgo')
    _log_ev(fb, b, cx, helpers, 'rally', [('f', fb.get(fac, 'kind')), ('act', 'race'), ('s', dz), ('H', bh),
                                          ('M', bm), ('rem', rrem), ('why', rwhy)])
    fb.label('rgo')
    fb.op('JSLt', a=fc, b=p, offset='gcede')
    fb.op('Mov', dst=cwhy, src=fb.string('race'))
    fb.op('JAlways', offset='gcommit')
    fb.label('norace')
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
    # not the armies standing at the running rally point (the gathered force: Tabr, 236 from Grim-po)
    hrp = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=hrp)
    hpv = b.call('haxe.ds.ObjectMap.get', rlyp, fb.dyn(fac))
    fb.op('JNull', reg=hpv, offset='hrpn')
    fb.op('JNull', reg=b.call('haxe.ds.ObjectMap.get', rly, fb.dyn(fac)), offset='hrpn')
    fb.op('SafeCast', dst=hrp, src=hpv)
    fb.label('hrpn')
    # the battle forecast at D (defend, RALLY_FC_T: their side as the pick read it) with only these armies (the
    # forecast adds our turrets at D, D's own included: aimod_cover silences a village under a faction's siege by
    # itself, and excluding D dropped a main base's guns, whose defenders the rally then walked away; D's militia;
    # x terrain) >= DEF_HOPE_IN (ARCHITECTURE-PLAN step 1; was the same sum against the pick's side)
    harr = _new_array(fb, b, cx)
    our_power(dz, m, 'hp', b.const('f64', RALLY_HERE), hrp, into=harr)
    hfc = fb.reg(cx.t('f64'))
    fb.op('CallN', dst=hfc, fun=forecast, args=[fac, dz, b.const('f64', RALLY_FC_T), t_false, harr])
    _fc_sides(fb, b, cx, fac, m, p, 'nothere')
    fb.op('JSLt', a=hfc, b=_ratio(fb, b, DEF_HOPE_IN), offset='nothere')
    b.call('haxe.ds.ObjectMap.set', rlyc, fb.dyn(dz), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'rlyk'), fb.dyn(fac), fb.dyn(dz))
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
    # D's capture is under way (occupation progress > 0): commit as soon as the gathered force is at least even
    # (terrain-adjusted, the timeout's measure), not at ENTER x RALLY_HYST or the timeout: the gathering costs the
    # village (Fremen held 443-468k vs 340-376k at Grimpo from 14:24 and committed at the 15:04 timeout, 30 s before
    # Smugglers' Liberate ended; user). Never on a D judged hopeless within 30 s (as `here`)
    fb.op('Mov', dst=cwhy, src=fb.string('time'))
    dzs = b.cast(fb.dyn(dz), 'ent.Structure')
    fb.op('JNull', reg=dzs, offset='gtime')
    dsg = b.field(dzs, 'siege')
    fb.op('JNull', reg=dsg, offset='gtime')
    fb.op('JSLte', a=b.call('ent.comp.SiegeComponent.getOccupationActionProgress', dsg), b=zero, offset='gtime')
    cdv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'dhl'), fb.dyn(dz))
    fb.op('JNull', reg=cdv, offset='gcap_h')
    cq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=cq, src=cdv)
    fb.op('Sub', dst=cq, a=t, b=cq)
    fb.op('JSLt', a=cq, b=b.const('f64', 30), offset='gtime')
    fb.label('gcap_h')
    # the battle forecast at D within RALLY_FC_T (everyone who can be there in that time, both sides)
    gfc = fb.reg(cx.t('f64'))
    fb.op('CallN', dst=gfc, fun=forecast, args=[fac, dz, b.const('f64', RALLY_FC_T), t_false, no_arr])
    _fc_sides(fb, b, cx, fac, bm, bh, 'gtime')
    fb.op('JSLt', a=gfc, b=_ratio(fb, b, DEF_HOPE_IN), offset='gtime')
    fb.op('Mov', dst=cwhy, src=fb.string('cap'))
    fb.op('JAlways', offset='gcommit')
    fb.label('gtime')
    fb.op('SafeCast', dst=gq, src=g0)
    fb.op('Sub', dst=gq, a=t, b=gq)
    fb.op('JSLte', a=gq, b=b.const('f64', RALLY_GIVEUP), offset='gkeep')
    # at least even (terrain-adjusted, as the hopeless test): commit, the gathered force fights it (Smugglers had 334k
    # vs Atreides' 284k at Qafmah, gave up for not reaching 1.7x, and its Defense got no armies while the pillage
    # ran); below even: concede (never the capital: a main base commits)
    # judged hopeless by aimod_defend within 30 s (map `dhl`, never a main base): concede, as for `here` (a commit
    # would leave the armies idle at D: dstop ends its Defense every pass while RALLY_COOL keeps the rally off)
    gdv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'dhl'), fb.dyn(dz))
    fb.op('JNull', reg=gdv, offset='gnoh')
    fb.op('SafeCast', dst=gq, src=gdv)
    fb.op('Sub', dst=gq, a=t, b=gq)
    fb.op('JSLt', a=gq, b=b.const('f64', 30), offset='gcede')
    fb.label('gnoh')
    gfc2 = fb.reg(cx.t('f64'))
    fb.op('CallN', dst=gfc2, fun=forecast, args=[fac, dz, b.const('f64', RALLY_FC_T), t_false, no_arr])
    _fc_sides(fb, b, cx, fac, bm, bh, 'gcede')
    fb.op('JSGte', a=gfc2, b=_ratio(fb, b, DEF_HOPE_IN), offset='gcommit')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', b.cast(fb.dyn(dz), 'ent.Structure')), offset='gcommit')
    fb.label('gcede')
    b.call('haxe.ds.ObjectMap.set', rlygu, fb.dyn(dz), fb.dyn(t))
    # the local threat when conceded, the same measure the reopen test reads (the forecast's side counts everything
    # that can arrive within its horizon: Guntar was conceded to 1.46M and reopened 2 s later at 247k local, 39 x)
    ghc = fb.reg(cx.t('f64'))
    fb.op('Call3', dst=ghc, fun=threat, arg0=fac, arg1=dz, arg2=b.const('f64', FLEE_R))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'rlyguh'), fb.dyn(dz), fb.dyn(ghc))
    b.call('haxe.ds.ObjectMap.set', rlyg, fb.dyn(fac), fb.dyn(dz))
    for mp in (rly, rly0, rlyp):
        b.call('haxe.ds.ObjectMap.remove', mp, fb.dyn(fac))
    _log_ev(fb, b, cx, helpers, 'rally', [('f', fb.get(fac, 'kind')), ('act', 'giveup'), ('s', dz), ('H', bh),
                                          ('M', bm)])
    fb.op('JAlways', offset='end')
    fb.label('gcommit')
    b.call('haxe.ds.ObjectMap.set', rlyc, fb.dyn(dz), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'rlyk'), fb.dyn(fac), fb.dyn(dz))
    for mp in (rly, rly0, rlyp):
        b.call('haxe.ds.ObjectMap.remove', mp, fb.dyn(fac))
    _log_ev(fb, b, cx, helpers, 'rally', [('f', fb.get(fac, 'kind')), ('act', 'commit'), ('s', dz), ('H', bh),
                                          ('M', bm), ('why', cwhy)])
    fb.op('JAlways', offset='end')
    fb.label('gnew')
    # a rally back on within RALLY_RESUME s of its last qualifying pass (map `rlyt`) keeps its clock (rly0): Smugglers
    # at Ashtar went rally / off / rally every 12-24 s for 2.5 min (23:54-26:16) and never reached RALLY_GIVEUP
    r0v = b.call('haxe.ds.ObjectMap.get', rly0, fb.dyn(fac))
    fb.op('JNull', reg=r0v, offset='g0set')
    rtv = b.call('haxe.ds.ObjectMap.get', rlyt, fb.dyn(fac))
    fb.op('JNull', reg=rtv, offset='g0set')
    fb.op('SafeCast', dst=gq, src=rtv)
    fb.op('Sub', dst=gq, a=t, b=gq)
    fb.op('JSLt', a=gq, b=b.const('f64', RALLY_RESUME), offset='gkeep')
    fb.label('g0set')
    b.call('haxe.ds.ObjectMap.set', rly0, fb.dyn(fac), fb.dyn(t))
    fb.label('gkeep')
    b.call('haxe.ds.ObjectMap.set', rly, fb.dyn(fac), fb.dyn(dz))
    b.call('haxe.ds.ObjectMap.set', rlyt, fb.dyn(fac), fb.dyn(t))
    # 2a. where the defenders stand (centroid of our non-harvester armies within RALLY_R of D): a rally point whose
    # walk from there passes D is on the enemy's side (Fremen liberating Tsimlat: Harkonnen's point Had-Al'riyah lay
    # behind them, the defenders stood at Tabiel / Carthag)
    gx, gy, gc = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    dpx, dpy, rpx, rpy = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('Mov', dst=gx, src=zero)
    fb.op('Mov', dst=gy, src=zero)
    fb.op('Mov', dst=gc, src=zero)
    one = b.const('f64', 1)
    ga = _army_loop(fb, b, my_armies, mlen, j, 'gc', 'gcd')
    fb.op('JNotNull', reg=b.field(ga, 'harvestComponent'), offset='gc')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ga, dz), b=rr, offset='gc')
    fb.op('Add', dst=gx, a=gx, b=b.field(ga, 'posx'))
    fb.op('Add', dst=gy, a=gy, b=b.field(ga, 'posy'))
    fb.op('Add', dst=gc, a=gc, b=one)
    fb.op('JAlways', offset='gc')
    fb.label('gcd')
    fb.op('JSLte', a=gc, b=zero, offset='gcz')
    fb.op('SDiv', dst=gx, a=gx, b=gc)
    fb.op('SDiv', dst=gy, a=gy, b=gc)
    fb.label('gcz')
    fb.op('Mov', dst=dpx, src=b.field(dz, 'posx'))
    fb.op('Mov', dst=dpy, src=b.field(dz, 'posy'))
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
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', se, dz), b=b.const('f64', RALLY_PT_MAX), offset='rnew')
    fb.op('Call3', dst=h, fun=threat, arg0=fac, arg1=se, arg2=b.const('f64', RALLY_SAFE))
    fb.op('JSGt', a=h, b=zero, offset='rnew')
    fb.op('JSLte', a=gc, b=zero, offset='rkeep')
    fb.op('Mov', dst=rpx, src=b.field(se, 'posx'))
    fb.op('Mov', dst=rpy, src=b.field(se, 'posy'))
    _crosses(fb, b, cx, gx, gy, rpx, rpy, dpx, dpy, CROSS_R, 'rnew')
    fb.label('rkeep')
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
    # within reach of D (user: Smugglers' rally for Larbu, every nearer structure under at-war power, took Nun-Al'khelon
    # 860 away at the map's other end; 2 worn armies walked there across Atreides' land and starved): no point within
    # RALLY_PT_MAX = no rally (vanilla's Defense / the contest hunt decide)
    fb.op('JSGt', a=d, b=b.const('f64', RALLY_PT_MAX), offset='r')
    fb.op('Call3', dst=h, fun=threat, arg0=fac, arg1=se, arg2=b.const('f64', RALLY_SAFE))
    fb.op('JSGt', a=h, b=zero, offset='r')
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', s2), offset='rmb')
    fb.op('Sub', dst=d, a=d, b=b.const('f64', RALLY_MB))
    fb.label('rmb')
    # on the enemy's side of D for the defenders: any point on their side wins
    fb.op('JSLte', a=gc, b=zero, offset='rside')
    fb.op('Mov', dst=rpx, src=b.field(se, 'posx'))
    fb.op('Mov', dst=rpy, src=b.field(se, 'posy'))
    _crosses(fb, b, cx, gx, gy, rpx, rpy, dpx, dpy, CROSS_R, 'rfar')
    fb.op('JAlways', offset='rside')
    fb.label('rfar')
    fb.op('Add', dst=d, a=d, b=b.const('f64', 4 * RALLY_R))
    fb.label('rside')
    fb.op('JSGte', a=d, b=bd, offset='r')
    fb.op('Mov', dst=bd, src=d)
    fb.op('Mov', dst=rp, src=se)
    fb.op('JAlways', offset='r')
    fb.label('rdone')
    fb.op('JNotNull', reg=rp, offset='rp_ok')
    # no rally point within reach: no rally at all (review: the state written above kept the faction 'rallying' with
    # nobody moving, sieges blocked, and conceded D after RALLY_GIVEUP); vanilla's Defense / the contest hunt decide
    for mp in (rly, rly0, rlyp, rlyt):
        b.call('haxe.ds.ObjectMap.remove', mp, fb.dyn(fac))
    _throttle(fb, b, cx, 'rnopt', dz, 30, 'end')
    _log_ev(fb, b, cx, helpers, 'rally', [('f', fb.get(fac, 'kind')), ('act', 'nopoint'), ('s', dz)])
    fb.op('JAlways', offset='end')
    fb.label('rp_ok')
    b.call('haxe.ds.ObjectMap.set', rlyp, fb.dyn(fac), fb.dyn(rp))
    # the gather point: just outside R's footprint on D's side (radius + RALLY_OFF), not its centre: armies can't
    # stand in a main base, never came within RALLY_AT of the centre and were re-sent every RALLY_MOVE_T s (user:
    # "spams base center"); arrived = within R's radius + RALLY_AT of R
    rgx, rgy, rgo, rgl = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('Add', dst=rgo, a=b.call('ent.Entity.get_radius', rp), b=b.const('f64', RALLY_OFF))
    fb.op('Mov', dst=rgx, src=b.field(rp, 'posx'))
    fb.op('Mov', dst=rgy, src=b.field(rp, 'posy'))
    fb.op('Mov', dst=rgl, src=b.call('ent.Entity.getDistTo', rp, dz))
    fb.op('JSLte', a=rgl, b=rgo, offset='rg_c')
    fb.op('SDiv', dst=rgo, a=rgo, b=rgl)
    fb.op('Sub', dst=rgl, a=b.field(dz, 'posx'), b=rgx)
    fb.op('Mul', dst=rgl, a=rgl, b=rgo)
    fb.op('Add', dst=rgx, a=rgx, b=rgl)
    fb.op('Sub', dst=rgl, a=b.field(dz, 'posy'), b=rgy)
    fb.op('Mul', dst=rgl, a=rgl, b=rgo)
    fb.op('Add', dst=rgy, a=rgy, b=rgl)
    fb.label('rg_c')
    rat = fb.reg(cx.t('f64'))
    fb.op('Add', dst=rat, a=b.call('ent.Entity.get_radius', rp), b=b.const('f64', RALLY_AT))
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
    # its order (Army.aiOrder is unreliable: the order list): a Defense of D's surroundings is stopped even at the
    # rally point, any order once it must walk (Fremen's rally at Tabr for Ulmara: a vanilla Defense of Ulmara took
    # 2 armies from the point, walked them out, the rally walked them back, 45 s of tug-of-war; the 2-army Defense
    # then blocked vanilla's full one after the commit and went in alone at balance 0.25)
    rarr = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=rarr, value=False)
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', a, rp), b=rat, offset='rpt_in')
    # ... or within RALLY_AT_HYST more, once we sent it there (map `rallymv`, within RALLY_HYST_T s): armies at the
    # edge were re-sent forever (docs/INPUT-SPAM-TODO.md 7: Atreides -> Ya-no, 144 Patrol orders, armies 66-76 out,
    # each Patrol ended Success at once and the next went out 9 s later)
    rhq = fb.reg(cx.t('f64'))
    fb.op('Add', dst=rhq, a=rat, b=b.const('f64', RALLY_AT_HYST))
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', a, rp), b=rhq, offset='rptfar')
    rmv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rallymv'), fb.dyn(a))
    fb.op('JNull', reg=rmv, offset='rptfar')
    fb.op('SafeCast', dst=rhq, src=rmv)
    fb.op('Sub', dst=rhq, a=b.field(_state(fb, b, cx), 'time'), b=rhq)
    fb.op('JSGt', a=rhq, b=b.const('f64', RALLY_HYST_T), offset='rptfar')
    fb.label('rpt_in')
    fb.op('Bool', dst=rarr, value=True)  # arrived
    fb.label('rptfar')
    rao = fb.reg(cx.t('logic.ai.AIOrder'))
    fb.op('Null', dst=rao)
    fb.op('JNull', reg=dords, offset='rord')
    rk, rix = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=rk, src=b.field(dords, 'length'))
    b.loop_head('rol')
    fb.op('JSLte', a=rk, b=zi, offset='rord')
    fb.op('Sub', dst=rk, a=rk, b=b.const('i32', 1))
    ro = b.cast(b.call('hl.types.ArrayObj.getDyn', dords, rk), 'logic.ai.AIOrder')
    fb.op('JNull', reg=ro, offset='rol')
    rou = b.field(ro, 'units')
    fb.op('JNull', reg=rou, offset='rol')
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', rou, fb.dyn(a)), offset='rol')
    fb.op('Mov', dst=rao, src=ro)
    fb.label('rord')
    fb.op('JFalse', cond=rarr, offset='rwalk')
    # at the point: only a Defense is stopped (a Resupply / Patrol there is harmless)
    fb.op('JNull', reg=rao, offset='a')
    fb.op('EnumIndex', dst=rix, value=b.field(rao, 'type'))
    fb.op('JNotEq', a=rix, b=b.const('i32', DEFENSE), offset='a')
    b.call('logic.ai.AIOrder.stop', rao, cancel)
    fb.op('JAlways', offset='a')
    fb.label('rwalk')
    # the walk must be payable: an army on hostile land (it drains) with less supply than SUP_WALK x the walk to the point
    # + SUP_RESERVE is left alone (its heal / strand trip home is vanilla's and ours; the two that starved above had 93
    # for ~700)
    fb.op('JFalse', cond=b.call('ent.Army.isInHostileZone', a), offset='rpay')
    rsq = fb.reg(cx.t('f64'))
    fb.op('Mul', dst=rsq, a=b.call('ent.Entity.getDistTo', a, rp), b=_ratio(fb, b, SUP_WALK))
    fb.op('Add', dst=rsq, a=rsq, b=b.const('f64', int(round(SUP_RESERVE))))
    fb.op('JSLt', a=b.call('ent.Army.get_supply', a), b=rsq, offset='a')
    fb.label('rpay')
    # task claim (rules/tasks.py): every pass while it walks to the point, P_RALLY (its Patrol order alone reads P_IDLE);
    # the live claim keeps it out of vanilla's Resupply / mission picks (common._rallying; was the `rallied` map)
    rcl = fb.reg(cx.t('bool'))
    fb.op('Call2', dst=rcl, fun=helpers['claim'], arg0=a, arg1=b.const('f64', P_RALLY))
    # already on its way in our Patrol order to the point: leave it (it may be flying)
    fb.op('JNull', reg=rao, offset='rthr')
    fb.op('EnumIndex', dst=rix, value=b.field(rao, 'type'))
    fb.op('JNotEq', a=rix, b=b.const('i32', PATROL), offset='rthr')
    fb.op('JEq', a=b.call('logic.ai.AIOrder.getTarget', rao), b=rp, offset='a')
    fb.label('rthr')
    _throttle(fb, b, cx, 'rallymv', a, RALLY_MOVE_T, 'a')
    fb.op('JNull', reg=rao, offset='nord')
    b.call('logic.ai.AIOrder.stop', rao, cancel)
    fb.label('nord')
    # a Patrol order to the point (vanilla checkPatrols' shape, as strand's): vanilla plans the path, shuttles
    # included (user: armies walked across the map where they'd fly from the main base); a plain Move never shuttles
    add = cx.fn('logic.ai.AIOrders.addOrder')
    at = [x_.value for x_ in cx.code.types[add.type.value].definition.args]
    parr = _new_array(fb, b, cx)
    b.call('hl.types.ArrayObj.push', parr, fb.dyn(a))
    pk = fb.reg(cx.t('logic.ai.AIOrderType'))
    fb.op('MakeEnum', dst=pk, construct=PATROL, args=[rp])
    pnul = []
    for n_ in (6, 7, 8, 9, 10):  # sa, mm, om, data, onComplete
        r_ = fb.reg(at[n_])
        fb.op('Null', dst=r_)
        pnul.append(r_)
    pres = fb.reg(cx.t('logic.ai.AIOrder'))
    fb.op('CallN', dst=pres, fun=helpers.get('addOrder', add.findex.value),
          args=[b.field(ctrl, 'aiOrders'), pk, zi, parr, rp, fb.string('Move')] + pnul)
    fb.op('JNotNull', reg=pres, offset='rmok')
    _move_to(fb, b, cx, a, rgx, rgy, fac)  # refused: walk there as before
    fb.label('rmok')
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset='a')
    fb.label('adone')
    _throttle(fb, b, cx, 'rally', fac, 10, 'end')
    _log_ev(fb, b, cx, helpers, 'rally', [('f', fb.get(fac, 'kind')), ('act', 'rally'), ('s', dz), ('r', rp),
                                          ('H', bh), ('M', bm), ('n', n)])
    fb.op('JAlways', offset='end')
    fb.label('off')  # no danger structure: rally over
    pdv = b.call('haxe.ds.ObjectMap.get', rly, fb.dyn(fac))
    fb.op('JNull', reg=pdv, offset='end')
    # ... unless its D missed one pass only: the active test (an at-war army within FLEE_R or heading there) flickers
    # as a stack shuffles at 70-90 from D, and every `off` restarted RALLY_GIVEUP (map rly0): Atreides' rally on
    # Yawaz went rally / off every 4-8 s for 30 s (62:06-62:36, H 600k vs M 130k), never committing or conceding.
    # D keeps the rally for RALLY_OFF_T s since its last qualifying pass while our side there is still short
    # (same measure as the pick); a gathered force past ENTER x RALLY_HYST ends it at once
    pd = b.cast(pdv, 'ent.Entity')
    fb.op('JNull', reg=pd, offset='offgo')
    ptv = b.call('haxe.ds.ObjectMap.get', rlyt, fb.dyn(fac))
    fb.op('JNull', reg=ptv, offset='offgo')
    fb.op('SafeCast', dst=gq, src=ptv)
    fb.op('Sub', dst=gq, a=t, b=gq)
    fb.op('JSGte', a=gq, b=b.const('f64', RALLY_OFF_T), offset='offgo')
    ofc = fb.reg(cx.t('f64'))
    fb.op('CallN', dst=ofc, fun=forecast, args=[fac, pd, b.const('f64', RALLY_FC_T), t_false, no_arr])
    _fc_sides(fb, b, cx, fac, m, h, 'offgo')
    fb.op('JSLt', a=h, b=b.const('f64', RALLY_MIN_H), offset='offgo')
    fb.op('JSLt', a=ofc, b=need, offset='end')  # still short at D: the rally holds through the gap
    fb.label('offgo')
    # rly0 (the rally clock) stays: a rally on again within RALLY_RESUME of its last qualifying pass resumes it
    for mp in (rly, rlyp):
        b.call('haxe.ds.ObjectMap.remove', mp, fb.dyn(fac))
    _log_ev(fb, b, cx, helpers, 'rally', [('f', fb.get(fac, 'kind')), ('act', 'off')])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


def build_rpoint(cx, helpers, threat, new_ids):
    """Recruit point (user: "when enemies cap villages near my base, the spawn of my units should be set somewhere
    else, not to die 1 by 1"). Vanilla `AIUnits.checkRallyPoint` (every `buyUnit`) sets the faction rally point, where
    recruits are delivered, to our Airfield nearest the closest fight we are in (`getClosestAirfieldAsync`, closure
    calling `Faction.setRallyPoint`): with an enemy stack capturing a village next to it, every recruit lands in that
    fight alone. That call goes through this wrapper: while our rally runs (map `rlyp`: its gather point R), recruits
    go to R; else when the structure at vanilla's point (ours, within RP_SNAP) has at-war power >= RALLY_MIN_H within
    LOCAL where the battle forecast (defend, RP_FC_T) is below 1, to our main base's own recruit point (`resetRallyPoint`'s
    target; none when that structure is the main base itself: nowhere safer). Logs `rpoint` (why rally / danger, s,
    h, m) once per faction per 30 s. Fails safe: vanilla's point on error."""
    orig = cx.fn('ent.Faction.setRallyPoint')
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    if len(args) != 3:
        raise ValueError('rpoint: setRallyPoint(fac, x, y) expected')
    crp = cx.fn('logic.ai.AIUnits.checkRallyPoint')
    clo = [op.df['fun'].value for op in crp.ops if op.op in ('InstanceClosure', 'Closure')]
    if len(clo) != 1:
        raise ValueError(f'rpoint: expected 1 closure in checkRallyPoint, found {len(clo)}')
    cfn = next(f for f in cx.code.functions if f.findex.value == clo[0])
    sites = [op for op in cfn.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == orig.findex.value]
    if len(sites) != 1:
        raise ValueError(f'rpoint: expected 1 setRallyPoint call in the checkRallyPoint closure, found {len(sites)}')
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    nx, ny = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=nx, src=1)
    fb.op('Mov', dst=ny, src=2)
    why = fb.reg(cx.t('String'))
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=se)
    h, m, d, bd = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('Mov', dst=h, src=b.const('f64', 0))
    fb.op('Mov', dst=m, src=b.const('f64', 0))
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    # our rally runs: recruits join the gathered force
    rp = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rlyp'), fb.dyn(0))
    fb.op('JNull', reg=rp, offset='judge')
    re_ = b.cast(rp, 'ent.Entity')
    fb.op('JNull', reg=re_, offset='judge')
    fb.op('Mov', dst=se, src=re_)
    fb.op('Mov', dst=nx, src=b.field(re_, 'posx'))
    fb.op('Mov', dst=ny, src=b.field(re_, 'posy'))
    fb.op('Mov', dst=why, src=fb.string('rally'))
    fb.op('JAlways', offset='log')
    fb.label('judge')
    # the structure of ours at vanilla's point
    mine = b.cast(fb.get(0, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=mine, offset='end')
    k = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    fb.op('Mov', dst=bd, src=b.const('f64', RP_SNAP))
    lq, lr = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    b.loop_head('st')
    fb.op('JSGte', a=k, b=b.field(mine, 'length'), offset='std')
    st = b.cast(b.call('hl.types.ArrayObj.getDyn', mine, k), 'ent.Structure')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=st, offset='st')
    fb.op('Sub', dst=lq, a=b.field(st, 'posx'), b=1)
    fb.op('Mul', dst=lq, a=lq, b=lq)
    fb.op('Sub', dst=lr, a=b.field(st, 'posy'), b=2)
    fb.op('Mul', dst=lr, a=lr, b=lr)
    fb.op('Add', dst=d, a=lq, b=lr)
    fb.op('Mov', dst=d, src=b.call('hxd.$Math.sqrt', d))
    fb.op('JSGte', a=d, b=bd, offset='st')
    fb.op('Mov', dst=bd, src=d)
    fb.op('Mov', dst=se, src=st)
    fb.op('JAlways', offset='st')
    fb.label('std')
    fb.op('JNull', reg=se, offset='end')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', b.cast(fb.dyn(se), 'ent.Structure')), offset='end')
    loc = b.const('f64', LOCAL)
    fb.op('Call3', dst=h, fun=threat, arg0=0, arg1=se, arg2=loc)
    fb.op('JSLt', a=h, b=b.const('f64', RALLY_MIN_H), offset='end')
    # our side holds there (the battle forecast, defend, over RP_FC_T: ARCHITECTURE-PLAN step 1; was aimod_own
    # within LOCAL x OWN_T vs the threat): recruits join a fight we win
    rfa = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=rfa, value=False)
    rna = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=rna)
    fb.op('CallN', dst=m, fun=helpers['forecast'], args=[0, se, b.const('f64', RP_FC_T), rfa, rna])
    fb.op('JSGte', a=m, b=b.const('f64', 1), offset='end')
    mb = b.call('ent.Faction.get_mainBase', 0)
    fb.op('JNull', reg=mb, offset='end')
    fb.op('Mov', dst=nx, src=b.field(mb, 'originalRecruitPointX'))
    fb.op('Mov', dst=ny, src=b.field(mb, 'originalRecruitPointY'))
    fb.op('Mov', dst=why, src=fb.string('danger'))
    fb.label('log')
    fac_e = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=fac_e, src=0)
    _throttle(fb, b, cx, 'rpoint', fac_e, 30, 'end')
    _log_ev(fb, b, cx, helpers, 'rpoint', [('f', fb.get(0, 'kind')), ('why', why), ('s', se), ('h', h), ('fc%', m)])
    fb.label('end')
    fb.end_try(guard)
    res = fb.reg(ft.ret.value)
    fb.op('Call3', dst=res, fun=orig.findex.value, arg0=0, arg1=nx, arg2=ny)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    for op in sites:
        op.df['fun'].value = w
    return {'rpoint': 1}
