"""Strand: idle armies left on hostile land walk home (AI-POLICY §5a goal 1: armies never starve outside our land).

Vanilla has a gap: `checkPatrols` takes only idle armies at 100% life AND supply, and `checkUnits` sends Resupply only
below 90%. An idle army at 90-99% supply in a neutral or enemy zone gets no order and stands there draining supply
(3 full-health Fremen stood ~55 s next to Harkonnen's Dal-Al'tar after auto-fighting a raider, while a Harkonnen hunt
on them gathered).

Every START s per faction, after hunt and raid (they claim armies first): each of our armies in no order at all
(strand variant of aimod_free: any life / supply, a Patrol order counts as busy, never a harvester), not fighting,
with `Army.isInHostileZone` gets a vanilla-style Patrol (prio 0, "Move") to the nearest structure on our land, keyed
like safe-heal: aimod_unsafe level 1 (contested) costs DETOUR, level 2 (overwhelming) is skipped. Not when the army is
within AT_HOME_R of it (the Patrol would end at once: re-issue loop); there, an army still losing supply
(outside the structure's supply radius, in the neighbouring zone) is moved straight into its safe position instead
(once per STRAND_NEAR_T s; logged near=move). Patrol armies stay free
for hunts, raids and sieges; once home the army is off hostile land, so it is never re-issued (no loop).
Logs `strand` (a army, s target, d distance). Fails safe: in a trap, nothing issued on error."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.worm import _move_to


def build_strand(cx, helpers, idle, unsafe):
    """aimod_strand(mil, dt) (see module doc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = b.field(_state(fb, b, cx), 'time')
    _tick(fb, b, cx, t, START, 'end')
    orders_obj = b.field(ctrl, 'aiOrders')
    orders = b.field(orders_obj, 'orders')
    fb.op('JNull', reg=orders, offset='end')
    structs = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=structs, offset='end')
    sn = b.field(structs, 'length')
    my_armies, mlen = _my_armies(fb, b, fac, 'end')
    zi = b.const('i32', 0)
    detour2, big = b.const('f64', DETOUR * DETOUR), b.const('f64', 1 << 30)
    t_false = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_false, value=False)
    i, k, lvl = fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    ok = fb.reg(cx.t('bool'))
    key, bk, d, bd = (fb.reg(cx.t('f64')) for _ in range(4))
    best = fb.reg(cx.t('ent.Structure'))
    add = cx.fn('logic.ai.AIOrders.addOrder')
    at = [a.value for a in cx.code.types[add.type.value].definition.args]

    a = _army_loop(fb, b, my_armies, mlen, i, 'army', 'end')
    fb.op('Call2', dst=ok, fun=idle, arg0=a, arg1=orders)
    fb.op('JFalse', cond=ok, offset='army')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', a), offset='army')
    fb.op('JFalse', cond=b.call('ent.Army.isInHostileZone', a), offset='army')
    # nearest structure on our land, safe-heal penalties
    fb.op('Null', dst=best)
    fb.op('Mov', dst=bk, src=big)
    fb.op('Mov', dst=k, src=zi)
    b.loop_head('st')
    fb.op('JSGte', a=k, b=sn, offset='stdone')
    s = b.cast(b.call('hl.types.ArrayObj.getDyn', structs, k), 'ent.Structure')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=s, offset='st')
    z = b.call('ent.Entity.get_zone', s)
    fb.op('JNull', reg=z, offset='st')
    fb.op('JNotEq', a=b.field(z, 'owner'), b=fac, offset='st')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', a, s))
    fb.op('Mul', dst=key, a=d, b=d)
    nf = fb.reg(cx.t('ent.Faction'))
    fb.op('Null', dst=nf)  # ownerless structure: judged for the army's owner
    fb.op('Call4', dst=lvl, fun=unsafe, arg0=s, arg1=a, arg2=t_false, arg3=nf)
    fb.op('JSGt', a=lvl, b=b.const('i32', 1), offset='st')  # overwhelming: never walk into it
    fb.op('JSLte', a=lvl, b=zi, offset='safe')
    fb.op('Add', dst=key, a=key, b=detour2)
    fb.label('safe')
    fb.op('JSGte', a=key, b=bk, offset='st')
    fb.op('Mov', dst=bk, src=key)
    fb.op('Mov', dst=bd, src=d)
    fb.op('Mov', dst=best, src=s)
    fb.op('JAlways', offset='st')
    fb.label('stdone')
    fb.op('JNull', reg=best, offset='army')
    # already next to it (a zone border runs close to our village): a Patrol there ends at once and was re-issued
    # every scan. Its supply radius doesn't always cover the spot: Smugglers' 3 pillage armies stood 15-30 from
    # Allon on Devastated Sandnun losing supply (264 -> 230) for 25+ s; Atreides' A_Elite 19 from Ara-dud. So an army
    # there still losing supply is moved straight into the structure's safe position (our zone: no longer stranded,
    # no loop), at most once per STRAND_NEAR_T s
    fb.op('JSGt', a=bd, b=b.const('f64', AT_HOME_R), offset='patrol')
    fb.op('JFalse', cond=b.call('ent.Army.isLosingSupply', a), offset='army')
    _throttle(fb, b, cx, 'strandn', a, STRAND_NEAR_T, 'army')
    gsp = cx.fn('ent.Entity.getSafePosition')
    sp_args = [fb.reg(x.value) for x in cx.code.types[gsp.type.value].definition.args[1:]]
    for r_ in sp_args:
        fb.op('Null', dst=r_)
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=best)
    pt = b.call('ent.Entity.getSafePosition', se, *sp_args)
    fb.op('JNull', reg=pt, offset='army')
    px, py = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=px, src=b.field(pt, 'x'))
    fb.op('Mov', dst=py, src=b.field(pt, 'y'))
    mok = _move_to(fb, b, cx, a, px, py, fac)
    _log_ev(fb, b, cx, helpers, 'strand', [('f', fb.get(fac, 'kind')), ('a', a), ('s', se), ('d', bd), ('ok', mok),
                                           ('near', 'move')])
    fb.op('JAlways', offset='army')
    fb.label('patrol')
    # vanilla checkPatrols order: Patrol(village), prio 0, "Move", no missions
    arr = _new_array(fb, b, cx)
    b.call('hl.types.ArrayObj.push', arr, fb.dyn(a))
    kind = fb.reg(cx.t('logic.ai.AIOrderType'))
    fb.op('MakeEnum', dst=kind, construct=PATROL, args=[best])
    tgt = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=tgt, src=best)
    nulls = []
    for n in (6, 7, 8, 9, 10):  # sa, mm, om, data, onComplete
        r = fb.reg(at[n])
        fb.op('Null', dst=r)
        nulls.append(r)
    res = fb.reg(cx.t('logic.ai.AIOrder'))
    fb.op('CallN', dst=res, fun=helpers.get('addOrder', add.findex.value),
          args=[orders_obj, kind, zi, arr, tgt, fb.string('Move')] + nulls)
    fb.op('Bool', dst=ok, value=False)
    fb.op('JNull', reg=res, offset='lg')
    fb.op('Bool', dst=ok, value=True)
    fb.label('lg')
    _log_ev(fb, b, cx, helpers, 'strand', [('f', fb.get(fac, 'kind')), ('a', a), ('s', tgt), ('d', bd), ('ok', ok)])
    fb.op('JAlways', offset='army')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


def build_patrol_gate(cx, helpers, hsafe, own, pw, new_ids):
    """Patrol gate: vanilla `checkPatrols` walks idle 100% armies to its best border village with no threat check.
    Harkonnen sent 4 armies (247k) to patrol Ara-Al'wan, 25 from the Fremen stack (450k+) pillaging Aeg-waz: they
    walked into it and were ground down (fight balance 0.07 -> 0, 31:30-33:10). The per-border call site (not the
    main-base one) goes through this wrapper: a Patrol is dropped when the hostile power at its village (undiscounted
    threat within SAFE_R, the heal / strand safety measure: armies rest there) exceeds OWN_T x (our armies there +
    the whole patrol group): the group couldn't hold it. A group that would win still reinforces a threatened border.
    Dropped: the armies stay idle where they are (free for rally, hunts, sieges). Logs `patrol` (s, a first army,
    n armies, h, m) once per village per 30 s. Fails safe: in a trap, vanilla's order on error."""
    orig = cx.fn('logic.ai.AIOrders.addOrder')
    ids = {orig.findex.value, helpers.get('addOrder')}
    cp = cx.fn('logic.ai.AIMilitary.checkPatrols')
    sites = [op for op in cp.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value in ids]
    if len(sites) != 2:
        raise ValueError(f'patrol-gate: expected 2 addOrder calls in checkPatrols, found {len(sites)}')
    site = sites[1]  # the per-border loop (the first one sends everyone to the main base when no border exists)
    callee = site.df['fun'].value
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('Null', dst=res)
    skip = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=skip, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=1, offset='end')
    idx = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=idx, value=1)
    fb.op('JNotEq', a=idx, b=b.const('i32', PATROL), offset='end')
    fb.op('JNull', reg=3, offset='end')
    n = b.field(3, 'length')
    fb.op('JSLte', a=n, b=b.const('i32', 0), offset='end')
    fb.op('JNull', reg=4, offset='end')
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    h, m, p = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    rr = b.const('f64', SAFE_R)
    fb.op('Call3', dst=h, fun=hsafe, arg0=fac, arg1=4, arg2=rr)
    fb.op('JSLte', a=h, b=b.const('f64', 0), offset='end')
    na = fb.reg(cx.t('ent.Army'))
    fb.op('Null', dst=na)
    fb.op('CallN', dst=m, fun=own, args=[fac, 4, rr, na])
    k = fb.reg(cx.t('i32'))
    a0 = fb.reg(cx.t('ent.Army'))
    fb.op('Null', dst=a0)
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head('grp')
    fb.op('JSGte', a=k, b=n, offset='grpd')
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', 3, k), 'ent.Army')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=a, offset='grp')
    fb.op('Mov', dst=a0, src=a)
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', a, 4), b=rr, offset='grp')  # already counted in own
    fb.op('Call1', dst=p, fun=pw, arg0=a)
    fb.op('Add', dst=m, a=m, b=p)
    fb.op('JAlways', offset='grp')
    fb.label('grpd')
    fb.op('Mul', dst=p, a=m, b=_ratio(fb, b, OWN_T))
    fb.op('JSLte', a=h, b=p, offset='end')
    fb.op('Bool', dst=skip, value=True)
    s = b.cast(4, 'ent.Structure')
    _throttle(fb, b, cx, 'patrol', s, 30, 'end')
    _log_ev(fb, b, cx, helpers, 'patrol', [('f', fb.get(fac, 'kind')), ('s', s), ('a', a0), ('n', n), ('h', h),
                                           ('m', m)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('JTrue', cond=skip, offset='ret')
    fb.op('CallN', dst=res, fun=callee, args=list(range(len(args))))
    fb.label('ret')
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    site.df['fun'].value = w
    return {'patrol-gate': 1}
