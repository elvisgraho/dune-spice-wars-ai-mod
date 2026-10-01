"""Rally: gather strength instead of feeding armies one at a time (AI-POLICY §1.5 concentrate, defense).

The failure: Fremen took Atreides' Aeganim with 10 armies (~350k) against Atreides' 7 (~235k, too few even at home
x1.3). Vanilla had no answer between "Defense with enough power" and nothing: 2 armies idled 330 away, 2 stopped 140
short, and 2 kept healing at Sadnin 84 from the siege: Fremen units reached them, they fought (balance 0), fled 26 to
Sadnin, healed, fought again, while another army walked in alone. Safe-heal saw no threat within 80 of Sadnin.

Every RALLY_T s per faction: the danger structure D = our structure on our land with the most at-war power around it
(aimod_react within LOCAL, at least RALLY_MIN_H) that our defenders within RALLY_R (non-harvester armies not on a Military mission) plus our
turret cover there, x terrain, can't beat by ENTER (enough: nothing to do, the contest hunt / vanilla Defense fight
it with everyone). The rally point R = our structure on our land at least RALLY_MIN from D with no at-war power
within RALLY_SAFE, the nearest to D (main base RALLY_MB closer: its guns fight with us). Each defender not fighting
(a fight in contact is the retreat logic's) and farther than RALLY_AT from R: its order (Resupply / Defense /
Patrol) is stopped and it walks to R (doAction Move, every RALLY_MOVE_T s at most); map `rallied` army -> time keeps
it out of vanilla's Resupply / mission picks (aimod_wormheld) while it walks. Map `rly` faction -> D (`rlyt` time):
aimod_unsafe rates every structure within RALLY_MIN of D overwhelming, so vanilla doesn't send heal / flee trips
next to the enemy. Once the gathered force (all within RALLY_R of D) passes ENTER, the rally stops and the contest
hunt (own village besieged) or vanilla's Defense takes them in together. Logs `rally` (D, R, H, M, n moved) once per
faction per 10 s. In a trap."""
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
    structs = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=structs, offset='end')
    sn = b.field(structs, 'length')
    my_armies, mlen = _my_armies(fb, b, fac, 'end')
    rly, rlyt, rallied = (_global_map(fb, b, cx, n) for n in ('rly', 'rlyt', 'rallied'))
    zi = b.const('i32', 0)
    zero = b.const('f64', 0)
    i, j = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    h, m, p, tf, bh, bm, d, bd, cv = (fb.reg(cx.t('f64')) for _ in range(9))
    ok = fb.reg(cx.t('bool'))
    se, dz, rp = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    rr, local = b.const('f64', RALLY_R), b.const('f64', LOCAL)
    nul_e = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=nul_e)
    t_true, no_arr = fb.reg(cx.t('bool')), fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Bool', dst=t_true, value=True)
    fb.op('Null', dst=no_arr)

    def our_power(at, dst, lbl):
        """dst = power of our defenders within RALLY_R of `at` (not on a Military mission, no harvesters)."""
        fb.op('Mov', dst=dst, src=zero)
        a = _army_loop(fb, b, my_armies, mlen, j, lbl, lbl + 'd')
        fb.op('JNotNull', reg=b.field(a, 'harvestComponent'), offset=lbl)
        fb.op('JSGt', a=b.call('ent.Entity.getDistTo', a, at), b=rr, offset=lbl)
        fb.op('Call2', dst=ok, fun=mission, arg0=fac, arg1=a)
        fb.op('JTrue', cond=ok, offset=lbl)
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
    fb.op('Call3', dst=h, fun=react, arg0=fac, arg1=se, arg2=local)
    fb.op('JSLt', a=h, b=b.const('f64', RALLY_MIN_H), offset='s')
    fb.op('JSLte', a=h, b=bh, offset='s')
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
    b.call('haxe.ds.ObjectMap.set', rly, fb.dyn(fac), fb.dyn(dz))
    b.call('haxe.ds.ObjectMap.set', rlyt, fb.dyn(fac), fb.dyn(t))
    # 2. the rally point
    fb.op('Null', dst=rp)
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
    b.call('haxe.ds.ObjectMap.remove', rly, fb.dyn(fac))
    _log_ev(fb, b, cx, helpers, 'rally', [('f', fb.get(fac, 'kind')), ('act', 'off')])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
