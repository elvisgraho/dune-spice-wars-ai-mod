"""Travel time with airfields (user: the AI walked to defenses it could have flown to from its main base).

Vanilla plans Shuttle steps itself (AIOrders.findPathSteps: Walk to the nearest airfield in range, Shuttle, Walk; only
for hops >= AI_Army_Shuttle_MinDist 250 and airfields within AI_Army_MaxWalkDist 2000; main bases have airfieldRange
80 and count). Our arrival tests judged every army as walking the straight line, so an army at the main base that
vanilla would fly in counted as unable to arrive (rally race, contest `late`).

aimod_eta(fac, from, to) -> s: min(walk, shuttle). walk = d / CONTEST_SPD; shuttle (d >= SHUTTLE_MIN only) =
(gap(from) + gap(to)) / CONTEST_SPD + SHUTTLE_T, gap(x) = distance from x into the range of fac's nearest airfield
(Faction.getAirfields: structures and buildings with an airfield range, main bases included; max(0, d - range)), none
within SHUTTLE_MAXD: no shuttle. Fails safe: the walking time on error."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

SHUTTLE_MIN = 250   # AI_Army_Shuttle_MinDist: vanilla shuttles only hops at least this long
SHUTTLE_MAXD = 2000  # AI_Army_MaxWalkDist: an airfield farther than this from either end isn't used
SHUTTLE_T = 20      # s: take-off, flight and landing (*unverified*: flight speed unmeasured)


def build_eta(cx):
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Entity'), cx.t('ent.Entity')], cx.t('f64'))
    b = B(fb)
    d, walk, ga, gt, q, rng = (fb.reg(cx.t('f64')) for _ in range(6))
    spd = b.const('f64', CONTEST_SPD)
    fb.op('Mov', dst=walk, src=b.const('f64', 1 << 30))
    guard = fb.try_()
    fb.op('JNull', reg=1, offset='end')
    fb.op('JNull', reg=2, offset='end')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', 1, 2))
    fb.op('SDiv', dst=walk, a=d, b=spd)
    fb.op('JSLt', a=d, b=b.const('f64', SHUTTLE_MIN), offset='end')
    fb.op('JNull', reg=0, offset='end')
    ga_ = cx.fn('ent.Faction.getAirfields')
    gat = [a.value for a in cx.code.types[ga_.type.value].definition.args]
    nul = fb.reg(gat[1])
    fb.op('Null', dst=nul)
    afs0 = fb.reg(cx.code.types[ga_.type.value].definition.ret.value)
    fb.op('Call2', dst=afs0, fun=ga_.findex.value, arg0=0, arg1=nul)
    fb.op('JNull', reg=afs0, offset='end')
    afs = b.call('hl.types.ArrayObj.copy', b.cast(fb.dyn(afs0), 'hl.types.ArrayObj'))  # a shared temp array
    big = b.const('f64', SHUTTLE_MAXD)
    i = fb.reg(cx.t('i32'))
    for gap, end in ((ga, 1), (gt, 2)):
        u = _uid('af')
        fb.op('Mov', dst=gap, src=big)
        fb.op('Mov', dst=i, src=b.const('i32', 0))
        b.loop_head(u)
        fb.op('JSGte', a=i, b=b.field(afs, 'length'), offset=u + 'd')
        e = b.cast(b.call('hl.types.ArrayObj.getDyn', afs, i), 'ent.Entity')
        fb.op('Incr', dst=i)
        fb.op('JNull', reg=e, offset=u)
        fb.op('Mov', dst=q, src=b.call('ent.Entity.getDistTo', end, e))
        fb.op('Mov', dst=rng, src=b.call('ent.Entity.getAirfieldRange', e))
        fb.op('Sub', dst=q, a=q, b=rng)
        fb.op('JSGte', a=q, b=b.const('f64', 0), offset=u + 'p')
        fb.op('Mov', dst=q, src=b.const('f64', 0))
        fb.label(u + 'p')
        fb.op('JSGte', a=q, b=gap, offset=u)
        fb.op('Mov', dst=gap, src=q)
        fb.op('JAlways', offset=u)
        fb.label(u + 'd')
        fb.op('JSGte', a=gap, b=big, offset='end')  # no airfield of ours near this end
    fb.op('Add', dst=q, a=ga, b=gt)
    fb.op('SDiv', dst=q, a=q, b=spd)
    fb.op('Add', dst=q, a=q, b=b.const('f64', SHUTTLE_T))
    fb.op('JSGte', a=q, b=walk, offset='end')
    fb.op('Mov', dst=walk, src=q)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=walk)
    return fb.build()


TRIP_SEG = 40     # trip sampling step along the straight path
TRIP_MAX = 40     # at most this many samples (a longer path: coarser steps)
DD_DRAIN_ATB = 455  # attribute Army_DeepDesertDailySupplyDrain_MRatio: Army.getSupplyChanges x this in a DeepDesert zone


def build_trip(cx):
    """aimod_trip(a, to) -> effective walk distance for supply: the straight path from army a to `to` sampled every
    TRIP_SEG (at most TRIP_MAX samples), a stretch in a deep desert zone counted x a's own drain factor there
    (getAtbVal(Army_DeepDesertDailySupplyDrain_MRatio): faction-specific, as Army.getSupplyChanges reads it; >= 1).
    Supply budgets multiply it by SUP_U as they did the plain distance (Smugglers' raid of O-Al'wahad crossed 374 of
    sand budgeted as normal ground: 3 of 6 armies starved to 0 health before the capture, match 2026-10-23 21:5x).
    Fails safe: the straight distance on error."""
    fb = FB(cx, [cx.t('ent.Army'), cx.t('ent.Entity')], cx.t('f64'))
    b = B(fb)
    d, eff, m, seg, x, y, dx, dy, q = (fb.reg(cx.t('f64')) for _ in range(9))
    fb.op('Mov', dst=eff, src=b.const('f64', 0))
    fb.op('JNull', reg=0, offset='out')
    fb.op('JNull', reg=1, offset='out')
    ae = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ae, src=0)
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', ae, 1))
    fb.op('Mov', dst=eff, src=d)
    guard = fb.try_()
    gav = cx.fn('ent.Object.getAtbVal')
    gat = [a_.value for a_ in cx.code.types[gav.type.value].definition.args]
    gref, gfac = fb.reg(gat[2]), fb.reg(gat[3])
    fb.op('Null', dst=gref)
    fb.op('Null', dst=gfac)
    gobj = fb.reg(gat[0])
    fb.op('Mov', dst=gobj, src=0)
    fb.op('Call4', dst=m, fun=gav.findex.value, arg0=gobj, arg1=b.const('i32', DD_DRAIN_ATB), arg2=gref, arg3=gfac)
    one = b.const('f64', 1)
    fb.op('JSLte', a=m, b=one, offset='end')  # no extra drain in the desert: the plain distance
    gm = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gm, **{'global': cx.global_of('$Game')})
    wd = b.field(b.field(gm, 'inst'), 'world')
    fb.op('JNull', reg=wd, offset='end')
    n = fb.reg(cx.t('i32'))
    nf = fb.reg(cx.t('f64'))
    fb.op('SDiv', dst=nf, a=d, b=b.const('f64', TRIP_SEG))
    fb.op('ToInt', dst=n, src=nf)
    fb.op('Incr', dst=n)
    fb.op('JSLte', a=n, b=b.const('i32', TRIP_MAX), offset='nok')
    fb.op('Mov', dst=n, src=b.const('i32', TRIP_MAX))
    fb.label('nok')
    fb.op('ToSFloat', dst=nf, src=n)
    fb.op('SDiv', dst=seg, a=d, b=nf)
    fb.op('Sub', dst=dx, a=b.field(1, 'posx'), b=b.field(ae, 'posx'))
    fb.op('Sub', dst=dy, a=b.field(1, 'posy'), b=b.field(ae, 'posy'))
    fb.op('SDiv', dst=dx, a=dx, b=nf)
    fb.op('SDiv', dst=dy, a=dy, b=nf)
    fb.op('Mov', dst=x, src=b.field(ae, 'posx'))
    fb.op('Mov', dst=y, src=b.field(ae, 'posy'))
    half = _ratio(fb, b, 0.5)
    fb.op('Mul', dst=q, a=dx, b=half)
    fb.op('Add', dst=x, a=x, b=q)
    fb.op('Mul', dst=q, a=dy, b=half)
    fb.op('Add', dst=y, a=y, b=q)
    extra = fb.reg(cx.t('f64'))
    fb.op('Sub', dst=extra, a=m, b=one)
    fb.op('Mul', dst=extra, a=extra, b=seg)  # extra distance per desert sample
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('s')
    fb.op('JSGte', a=i, b=n, offset='end')
    fb.op('Incr', dst=i)
    z = b.call('world.World.getZoneAt', wd, x, y)
    fb.op('Add', dst=x, a=x, b=dx)
    fb.op('Add', dst=y, a=y, b=dy)
    fb.op('JNull', reg=z, offset='s')
    fb.op('JFalse', cond=b.call('ent.Zone.isDeepDesert', z), offset='s')
    fb.op('Add', dst=eff, a=eff, b=extra)
    fb.op('JAlways', offset='s')
    fb.label('end')
    fb.end_try(guard)
    fb.label('out')
    fb.op('Ret', ret=eff)
    return fb.build()


DDL_SEG = 50   # aimod_ddline: the line is sampled this often
DDL_END = 30   # ... skipping this much at both ends (the endpoints' own zones)
DDL_MAX = 60   # ... at most this many samples


def build_ddline(cx):
    """aimod_ddline(a, b) -> bool: the straight line from entity a to entity b crosses a deep desert zone (sampled
    every DDL_SEG, DDL_END kept off both ends, at most DDL_MAX samples). Fails safe: false on error. (User
    2026-10-24: coalition armies walked over the deep desert straight to the leader's base and died there.)"""
    fb = FB(cx, [cx.t('ent.Entity'), cx.t('ent.Entity')], cx.t('bool'))
    b = B(fb)
    r = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=r, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    d, s, f, x, y = (fb.reg(cx.t('f64')) for _ in range(5))
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', 0, 1))
    fb.op('JSLte', a=d, b=b.const('f64', 2 * DDL_END), offset='end')
    gm = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gm, **{'global': cx.global_of('$Game')})
    wd = b.field(b.field(gm, 'inst'), 'world')
    fb.op('JNull', reg=wd, offset='end')
    n = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=n, src=b.const('i32', 0))
    fb.op('Mov', dst=s, src=b.const('f64', DDL_END))
    b.loop_head('s')
    fb.op('Mov', dst=f, src=d)
    fb.op('Sub', dst=f, a=f, b=b.const('f64', DDL_END))
    fb.op('JSGt', a=s, b=f, offset='end')
    fb.op('JSGte', a=n, b=b.const('i32', DDL_MAX), offset='end')
    fb.op('Incr', dst=n)
    fb.op('SDiv', dst=f, a=s, b=d)
    fb.op('Sub', dst=x, a=b.field(1, 'posx'), b=b.field(0, 'posx'))
    fb.op('Mul', dst=x, a=x, b=f)
    fb.op('Add', dst=x, a=x, b=b.field(0, 'posx'))
    fb.op('Sub', dst=y, a=b.field(1, 'posy'), b=b.field(0, 'posy'))
    fb.op('Mul', dst=y, a=y, b=f)
    fb.op('Add', dst=y, a=y, b=b.field(0, 'posy'))
    fb.op('Add', dst=s, a=s, b=b.const('f64', DDL_SEG))
    z = b.call('world.World.getZoneAt', wd, x, y)
    fb.op('JNull', reg=z, offset='s')
    fb.op('JFalse', cond=b.call('ent.Zone.isDeepDesert', z), offset='s')
    fb.op('Bool', dst=r, value=True)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=r)
    return fb.build()


def build_route(cx, worm=True):
    """aimod_route(from, to) -> ent.Zone: the next zone on a shortest zone path (Zone.neighbors, breadth first) from
    zone `from` to zone `to` that never enters a deep desert zone other than `to` itself (`from` may be one: the
    way out); `to` when they are neighbours or equal; null when no such path exists or on error. (User 2026-10-24:
    armies walked straight over the deep desert to the leader's base and died instead of going around it.)
    Two passes: first a path that also avoids zones with current worm activity (Zone.getCurrentWormActivity > 0, `to`
    excepted), else the deep-desert-only one (match 53: Harkonnen's 12 campaign armies crossed worm sand, fled to
    rock again and again (`wflee` 46, `whold` 310 in 5 min) and never reached Arrakeen). worm=False: the
    deep-desert pass only (aimod_route_nw: callers fall back to it when the worm pass leads backwards)."""
    fb = FB(cx, [cx.t('ent.Zone'), cx.t('ent.Zone')], cx.t('ent.Zone'))
    b = B(fb)
    res = fb.reg(cx.t('ent.Zone'))
    fb.op('Null', dst=res)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    fb.op('Mov', dst=res, src=1)
    fb.op('JEq', a=0, b=1, offset='end')
    fb.op('Null', dst=res)
    i, k = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    z, nb = fb.reg(cx.t('ent.Zone')), fb.reg(cx.t('ent.Zone'))
    c, p = fb.reg(cx.t('ent.Zone')), fb.reg(cx.t('ent.Zone'))
    v = fb.reg(cx.t('void'))
    for ps, worm in ((('a', True), ('b', False)) if worm else (('b', False),)):
        nxt = 'end' if ps == 'b' else 'pass_b'
        prev = fb.reg(cx.t('haxe.ds.ObjectMap'))
        fb.op('New', dst=prev)
        fb.op('Call1', dst=v, fun=cx.fn('haxe.ds.$ObjectMap.__constructor__').findex.value, arg0=prev)
        q = _new_array(fb, b, cx)
        b.call('hl.types.ArrayObj.push', q, fb.dyn(0))
        b.call('haxe.ds.ObjectMap.set', prev, fb.dyn(0), fb.dyn(0))
        fb.op('Mov', dst=i, src=b.const('i32', 0))
        b.loop_head(ps + 'q')
        fb.op('JSGte', a=i, b=b.field(q, 'length'), offset=nxt)  # no path
        fb.op('Mov', dst=z, src=b.cast(b.call('hl.types.ArrayObj.getDyn', q, i), 'ent.Zone'))
        fb.op('Incr', dst=i)
        fb.op('JNull', reg=z, offset=ps + 'q')
        nbs = b.field(z, 'neighbors')
        fb.op('JNull', reg=nbs, offset=ps + 'q')
        fb.op('Mov', dst=k, src=b.const('i32', 0))
        b.loop_head(ps + 'n')
        fb.op('JSGte', a=k, b=b.field(nbs, 'length'), offset=ps + 'q')
        fb.op('Mov', dst=nb, src=b.cast(b.call('hl.types.ArrayObj.getDyn', nbs, k), 'ent.Zone'))
        fb.op('Incr', dst=k)
        fb.op('JNull', reg=nb, offset=ps + 'n')
        fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', prev, fb.dyn(nb)), offset=ps + 'n')
        fb.op('JEq', a=nb, b=1, offset=ps + 'n_ok')
        fb.op('JTrue', cond=b.call('ent.Zone.isDeepDesert', nb), offset=ps + 'n')
        if worm:
            fb.op('JSGt', a=b.call('ent.Zone.getCurrentWormActivity', nb), b=b.const('f64', 0), offset=ps + 'n')
        fb.label(ps + 'n_ok')
        b.call('haxe.ds.ObjectMap.set', prev, fb.dyn(nb), fb.dyn(z))
        b.call('hl.types.ArrayObj.push', q, fb.dyn(nb))
        fb.op('JNotEq', a=nb, b=1, offset=ps + 'n')
        # found: walk back from `to` to the zone right after `from`
        fb.op('Mov', dst=c, src=1)
        b.loop_head(ps + 'w')
        fb.op('Mov', dst=p, src=b.cast(b.call('haxe.ds.ObjectMap.get', prev, fb.dyn(c)), 'ent.Zone'))
        fb.op('JNull', reg=p, offset=nxt)
        fb.op('JEq', a=p, b=0, offset=ps + 'w_d')
        fb.op('Mov', dst=c, src=p)
        fb.op('JAlways', offset=ps + 'w')
        fb.label(ps + 'w_d')
        fb.op('Mov', dst=res, src=c)
        fb.op('JAlways', offset='end')
        if ps == 'a':
            fb.label('pass_b')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    return fb.build()
