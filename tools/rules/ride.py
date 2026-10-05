"""Worm rides (Fremen thumpers), offensive use (docs/WORMRIDE-PLAN.md; user: Fremen ride to reach farther and to stop
enemy captures in time, thumpers reserved as soon as a ride is planned).

Vanilla (REVERSING "Worm riding"): `addOrder` picks the worm plan (`fillWormAttackSteps`) only for ArmyFight /
ArmySiege orders of >= 4 armies with a thumper, by a priority rule (Raze always, Annex far or owned, Liberate / Pillage
/ sietch strikes never; Defense with an enemy at the structure; our hunts, prio 5, always); the worm plan has no
supply check. `checkRegroupOrder` calls `WormRiding.requestRide` every tick once every waiting army sits at its sync
Worm step, ignores the result and never times out (no thumper left, another ride of ours, combat at the thumper:
the order waits in Regroup for good). Fremen armies were in transit 5 times in 33 matches.

- `wplan` (the two plan calls in addOrder -> wrappers): for a faction with thumpers (hasAccessToRes Thumper) our
  gate decides instead of vanilla, for Military orders on a structure (every siege action: Annex, Liberate, Pillage
  and raids, Raze, sietch / renegade strikes), our contest hunts (map `wcon` set by hunt around its addOrder; a
  chase never rides: a moving prey isn't where the worm lands) and Defense orders: worm when the trip (order armies'
  centroid -> order position) is >= RIDE_MIN and a thumper is free (stock - claims >= 1), any order size; else walk.
  A Pillage of a neutral village always walks (why npil, user: a thumper on militia loot is wasted).
  The last free thumper only for a trip >= RIDE_FAR, a contest or a Defense; shorter trips ride while RIDE_SPARE are
  free (3 at start, none back before 5k hegemony: 3 short early Annex rides spent them all by 6 min).
  A worm plan claims a thumper at once (map `wres` order -> time): it counts against the stock while the order is in
  Waiting .. Regroup, at most RIDE_CLAIM_T, until its ride is granted (the stock drops then) or falls back. The
  order's own gates (sizing, supply budget of the walking legs, threat) decided whether it goes at all; the ride
  only changes how it gets there. Log `wplan` (worm, why near / stock / spare / chase / grp, d, n, stock, cl, van = vanilla's
  choice). Other factions and order kinds: vanilla's choice.
  The worm plan runs with our completion closure (InstanceClosure over a dynobj {ao, o, d}): a failure runs the
  walk plan for the order with its own completion d (log `wstall` why plan, r = EReason); Success -> d.
- `wride` (the requestRide call in checkRegroupOrder -> wrapper with the order as an extra argument): Success
  releases the claim (log `wride`: d, stock left) and the order asks no more (map `wdone`: vanilla re-asks every
  tick until the riders land; an army still on its Worm step after RIDE_PICKUP_T walks: landed outside the step's arrival tolerance (vanilla would
  call a second ride: second thumper) or not picked up; log `wstall` why off; within RIDE_LAND_R of the landing point at once: why land). A ride whose foot path (PathGrid.getCost
  from -> to, at least the straight hop) is shorter than RIDE_HOP isn't asked for: the armies walk it (why short, foot). A refusal (log `wreq` why, once per order per 5 s) repeated for
  RIDE_STALL_T (refusals more than RIDE_GAP apart restart the clock) turns the waiting armies' Worm steps into Walk
  steps (vanilla's own fallback for a refused Shuttle step): they walk to the landing point and on (log `wstall`).
- `aimod_ride` tick (every RIDE_CHECK s per faction with thumpers): map `wfree` faction -> now while a thumper is
  free, read like the free Supply Drop's `sdfree`: + RIDE_ZONES military target reach (rules/strat.py), the trip
  supply filter / raid budget / out-of-reach memory judge only the walking legs (common._ride_leg / _ride_free),
  contest arrival times use the ride (hunt._late). Log `tstk` (stock, claims) every RIDE_LOG_T s.
In traps: vanilla's plan / walk on any error."""
from crashlink.core import Opcode, Reg
from crashlink.opcodes import opcodes

from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.stage import _virtual, _vidx

RIDE_CLAIM_T = 180  # s: a worm plan's thumper claim lapses after this (its order still waiting: the stall fallback walks it)
RIDE_PICKUP_T = 15  # s: after a granted ride, an order army still at its Worm step (landed off its landing point, or not picked up) walks the rest
RIDE_LAND_R = 60    # ... at once when it stands within this of the landing point (it rode: every ride of the first match
                    # touched down outside vanilla's arrival tolerance and idled until RIDE_PICKUP_T)
RIDE_HOP = 200      # a requested ride replacing less foot path than this isn't asked for: the armies walk it (Qartiel:
                    # 27 ridden; Mar-rekh: 123 ridden after a 17 s walk to the thumper, slower than walking; ~33 s on foot
                    # vs ~16 s by worm incl. pickup at 200)


def _stock(fb, b, cx, fac):
    """f64 = fac's Thumper stock."""
    return b.call('ent.Faction.getResource', fac, b.const('i32', RIDE_RES))


def _claims(fb, b, cx, fac, t):
    """i32 = fac's live orders holding a thumper claim (map `wres` within RIDE_CLAIM_T, phase <= REGROUP)."""
    n = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=n, src=b.const('i32', 0))
    u = _uid('wcl')
    ctl = b.field(fac, 'aiController')
    fb.op('JNull', reg=ctl, offset=u + 'd')
    aio = b.field(ctl, 'aiOrders')
    fb.op('JNull', reg=aio, offset=u + 'd')
    ords = b.field(aio, 'orders')
    fb.op('JNull', reg=ords, offset=u + 'd')
    wres = _global_map(fb, b, cx, 'wres')
    k = fb.reg(cx.t('i32'))
    q = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=k, src=b.field(ords, 'length'))
    b.loop_head(u)
    fb.op('JSLte', a=k, b=b.const('i32', 0), offset=u + 'd')
    fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', ords, k), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset=u)
    rv = b.call('haxe.ds.ObjectMap.get', wres, fb.dyn(o))
    fb.op('JNull', reg=rv, offset=u)
    fb.op('JSGt', a=b.field(o, 'phase'), b=b.const('i32', REGROUP), offset=u)
    fb.op('SafeCast', dst=q, src=rv)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSGt', a=q, b=b.const('f64', RIDE_CLAIM_T), offset=u)
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset=u)
    fb.label(u + 'd')
    return n


def _otgt(fb, b, cx, o):
    """ent.Entity = o's target when it is a structure (logged), else null."""
    tg = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=tg)
    u = _uid('otg')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset=u)
    ix = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ix, value=tt)
    fb.op('JNotEq', a=ix, b=b.const('i32', T_STRUCT), offset=u)
    fb.op('Mov', dst=tg, src=b.call('logic.ai.AIOrder.getTarget', o))
    fb.label(u)
    return tg


def _build_decide(cx, helpers):
    """aimod_wplan(aiOrders, o, van) -> Bool: worm plan for o (see module doc); van = vanilla's choice."""
    fb = FB(cx, [cx.t('logic.ai.AIOrders'), cx.t('logic.ai.AIOrder'), cx.t('bool')], cx.t('bool'))
    b = B(fb)
    res = fb.reg(cx.t('bool'))
    fb.op('Mov', dst=res, src=2)
    guard = fb.try_()
    fb.op('JNull', reg=1, offset='end')
    fac = b.call('logic.ai.AIModule.get_aiOwner', 0)
    fb.op('JNull', reg=fac, offset='end')
    fb.op('JFalse', cond=b.call('ent.Faction.hasAccessToRes', fac, b.const('i32', RIDE_RES)), offset='end')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    why = fb.reg(cx.t('String'))
    d, q, cx_, cy_ = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('Mov', dst=d, src=b.const('f64', 0))
    n = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=n, src=b.const('i32', 0))
    stk = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=stk, src=b.const('f64', 0))
    cl = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=cl, src=b.const('i32', 0))
    ix = fb.reg(cx.t('i32'))
    # contest flag (hunt): read once, cleared here too (a trap in hunt's addOrder must not leave it set)
    wcon = _global_map(fb, b, cx, 'wcon')
    wc = b.call('haxe.ds.ObjectMap.get', wcon, fb.dyn(fac))
    b.call('haxe.ds.ObjectMap.remove', wcon, fb.dyn(fac))
    fb.op('EnumIndex', dst=ix, value=b.field(1, 'type'))
    fb.op('JEq', a=ix, b=b.const('i32', DEFENSE), offset='go')
    fb.op('JNotEq', a=ix, b=b.const('i32', MILITARY), offset='end')  # other kinds: vanilla (never ArmyFight / ArmySiege)
    tt = b.field(1, 'targetType')
    fb.op('JNull', reg=tt, offset='end')
    fb.op('EnumIndex', dst=ix, value=tt)
    fb.op('JNotEq', a=ix, b=b.const('i32', T_STRUCT), offset='nst')
    # a Pillage of a neutral village walks (user: a thumper spent on loot from a militia village is wasted; rides are
    # for reach against enemies and contests)
    fb.op('Mov', dst=why, src=fb.string('npil'))
    psa = b.cast(fb.get(1, 'siegeAction'), 'String')
    fb.op('JNull', reg=psa, offset='go')
    fb.op('JNotEq', a=b.call('String.__compare', psa, fb.dyn(fb.string('Pillage'))), b=b.const('i32', 0), offset='go')
    pst = b.cast(b.call('logic.ai.AIOrder.getTarget', 1), 'ent.Structure')
    fb.op('JNull', reg=pst, offset='go')
    pse = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=pse, src=pst)
    fb.op('JNull', reg=b.call('ent.Entity.get_owner', pse), offset='walk')
    fb.op('JAlways', offset='go')
    fb.label('nst')
    fb.op('Mov', dst=why, src=fb.string('grp'))
    fb.op('JNotEq', a=ix, b=b.const('i32', T_GROUP), offset='walk')
    fb.op('Mov', dst=why, src=fb.string('chase'))
    fb.op('JNull', reg=wc, offset='walk')  # a chase (or a vanilla group fight): walk
    fb.label('go')
    # trip: the order armies' centroid -> the order's position (a structure, or the attackers' group centroid)
    units = b.field(1, 'units')
    fb.op('JNull', reg=units, offset='end')
    fb.op('Mov', dst=cx_, src=b.const('f64', 0))
    fb.op('Mov', dst=cy_, src=b.const('f64', 0))
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('cu')
    fb.op('JSGte', a=i, b=b.field(units, 'length'), offset='cud')
    u = b.cast(b.call('hl.types.ArrayObj.getDyn', units, i), 'ent.Unit')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=u, offset='cu')
    fb.op('Add', dst=cx_, a=cx_, b=b.field(u, 'posx'))
    fb.op('Add', dst=cy_, a=cy_, b=b.field(u, 'posy'))
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset='cu')
    fb.label('cud')
    fb.op('JSLte', a=n, b=b.const('i32', 0), offset='end')
    fb.op('ToSFloat', dst=q, src=n)
    fb.op('SDiv', dst=cx_, a=cx_, b=q)
    fb.op('SDiv', dst=cy_, a=cy_, b=q)
    pp = b.call('logic.ai.AIOrder.getPosPoint', 1)
    fb.op('JNull', reg=pp, offset='end')
    fb.op('Sub', dst=d, a=b.field(pp, 'x'), b=cx_)
    fb.op('Sub', dst=q, a=b.field(pp, 'y'), b=cy_)
    fb.op('Mul', dst=d, a=d, b=d)
    fb.op('Mul', dst=q, a=q, b=q)
    fb.op('Add', dst=d, a=d, b=q)
    fb.op('Mov', dst=d, src=b.call('hxd.$Math.sqrt', d))
    fb.op('Mov', dst=stk, src=_stock(fb, b, cx, fac))
    fb.op('Mov', dst=cl, src=_claims(fb, b, cx, fac, t))
    fb.op('Mov', dst=why, src=fb.string('near'))
    fb.op('JSLt', a=d, b=b.const('f64', RIDE_MIN), offset='walk')
    # a thumper free: stock minus the thumpers other worm plans have claimed
    fb.op('Mov', dst=why, src=fb.string('stock'))
    fb.op('ToSFloat', dst=q, src=cl)
    fb.op('Sub', dst=q, a=stk, b=q)
    fb.op('JSLt', a=q, b=b.const('f64', 1), offset='walk')
    # the last free thumper only for reach or time (thumpers don't come back before 5k hegemony: 3 short early
    # Annex rides spent the whole stock by 6 min): a far trip (>= RIDE_FAR), a contest or a Defense; a shorter
    # trip rides only while RIDE_SPARE are free
    fb.op('JSGte', a=d, b=b.const('f64', RIDE_FAR), offset='ride')
    fb.op('JNotNull', reg=wc, offset='ride')
    fb.op('EnumIndex', dst=ix, value=b.field(1, 'type'))
    fb.op('JEq', a=ix, b=b.const('i32', DEFENSE), offset='ride')
    fb.op('Mov', dst=why, src=fb.string('spare'))
    fb.op('JSLt', a=q, b=b.const('f64', RIDE_SPARE), offset='walk')
    fb.label('ride')
    fb.op('Bool', dst=res, value=True)
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'wres'), fb.dyn(1), fb.dyn(t))  # claimed now
    fb.op('Mov', dst=why, src=fb.string('ride'))
    fb.op('JAlways', offset='log')
    fb.label('walk')
    fb.op('Bool', dst=res, value=False)
    fb.label('log')
    _log_ev(fb, b, cx, helpers, 'wplan', [('f', fb.get(fac, 'kind')), ('worm', res), ('why', why),
                                          ('tgt', _otgt(fb, b, cx, 1)), ('act', fb.get(1, 'action')),
                                          ('sa', fb.get(1, 'siegeAction')), ('d', d), ('n', n), ('stock', stk),
                                          ('cl', cl), ('van', 2)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    return fb.build()


def build_wplan(cx, helpers, new_ids):
    """Redirect addOrder's fillWormAttackSteps / fillAttackSteps calls (one each) through the gate (module doc)."""
    add = cx.fn('logic.ai.AIOrders.addOrder')
    worm = cx.fn('logic.ai.AIOrders.fillWormAttackSteps')
    walk = cx.fn('logic.ai.AIOrders.fillAttackSteps')
    decide = _build_decide(cx, helpers)
    new_ids.add(decide)
    # the worm plan's completion: any failure (no thumper / rally point or slots: vanilla falls back to walking only on
    # InvalidThumperSlots, else the order is cancelled in Waiting: Fremen's Annex of Alno died 7 times, Defenses were
    # re-created every few s) -> the walk plan with the order's own completion; Success -> that completion
    done_t = [a.value for a in cx.code.types[worm.type.value].definition.args][2]
    er_t = cx.code.types[done_t].definition.args[0].value
    ctx_t = cx.t('dynobj')
    fb = FB(cx, [ctx_t, er_t], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    d = fb.reg(done_t)
    fb.op('DynGet', dst=d, obj=0, field=cx.s('d'))
    ix = fb.reg(cx.t('i32'))
    fb.op('JNull', reg=1, offset='pass')
    fb.op('EnumIndex', dst=ix, value=1)
    fb.op('JEq', a=ix, b=b.const('i32', 1), offset='pass')  # EReason Success
    fell = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=fell, value=False)
    g = fb.try_()
    ao = fb.reg(cx.t('logic.ai.AIOrders'))
    o = fb.reg(cx.t('logic.ai.AIOrder'))
    fb.op('DynGet', dst=ao, obj=0, field=cx.s('ao'))
    fb.op('DynGet', dst=o, obj=0, field=cx.s('o'))
    fb.op('JNull', reg=ao, offset='fb_no')
    fb.op('JNull', reg=o, offset='fb_no')
    b.call('haxe.ds.ObjectMap.remove', _global_map(fb, b, cx, 'wres'), fb.dyn(o))  # no ride: the claim ends
    fac = b.call('logic.ai.AIModule.get_aiOwner', ao)
    _log_ev(fb, b, cx, helpers, 'wstall', [('f', fb.get(fac, 'kind')), ('tgt', _otgt(fb, b, cx, o)), ('why', 'plan'),
                                           ('r', 1)])
    # remember the target (map `wbad` target -> now): a ride there can't be planned from where our armies gather, the
    # supply waiver for a free thumper (common._unreach) no longer applies to it (Fremen's Annex of Ashfir across the
    # desert: InvalidThumperSlots, the walk failed the supply check, match 2026-10-04 22:0x)
    wbt = b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'ent.Entity')
    fb.op('JNull', reg=wbt, offset='wb_no')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'wbad'), fb.dyn(wbt),
           fb.dyn(b.field(_state(fb, b, cx), 'time')))
    fb.label('wb_no')
    r2 = fb.reg(cx.code.types[walk.type.value].definition.ret.value)
    fb.op('Call3', dst=r2, fun=walk.findex.value, arg0=ao, arg1=o, arg2=d)
    fb.op('Bool', dst=fell, value=True)
    fb.label('fb_no')
    fb.end_try(g)
    fb.op('JTrue', cond=fell, offset='out')  # the walk plan completes the order through d
    fb.label('pass')
    fb.op('JNull', reg=d, offset='out')
    fb.op('CallClosure', dst=void, fun=d, args=[1])
    fb.label('out')
    fb.op('Ret', ret=void)
    wdone = fb.build()
    new_ids.add(wdone)
    wrappers = {}
    for orig, van in ((worm, True), (walk, False)):
        ft = cx.code.types[orig.type.value].definition
        args = [a.value for a in ft.args]
        fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
        b = B(fb)
        out = fb.reg(ft.ret.value)
        fb.op('Null', dst=out)
        vb = fb.reg(cx.t('bool'))
        fb.op('Bool', dst=vb, value=van)
        w = fb.reg(cx.t('bool'))
        fb.op('Call3', dst=w, fun=decide, arg0=0, arg1=1, arg2=vb)  # traps inside: vanilla's choice on any error
        fb.op('JFalse', cond=w, offset='walk')
        ctx = fb.reg(ctx_t)
        fb.op('New', dst=ctx)
        for k, r in (('ao', 0), ('o', 1), ('d', 2)):
            fb.op('DynSet', obj=ctx, field=cx.s(k), src=fb.dyn(r))
        clo = fb.reg(done_t)
        fb.op('InstanceClosure', dst=clo, fun=wdone, obj=ctx)  # failure -> walk plan (above)
        r1 = fb.reg(cx.code.types[worm.type.value].definition.ret.value)
        fb.op('Call3', dst=r1, fun=worm.findex.value, arg0=0, arg1=1, arg2=clo)
        if van:
            fb.op('Mov', dst=out, src=r1)
        fb.op('Ret', ret=out)
        fb.label('walk')
        r2 = fb.reg(cx.code.types[walk.type.value].definition.ret.value)
        fb.op('Call3', dst=r2, fun=walk.findex.value, arg0=0, arg1=1, arg2=2)
        if not van:
            fb.op('Mov', dst=out, src=r2)
        fb.op('Ret', ret=out)  # addOrder never reads the coroutine instance
        wrappers[orig.findex.value] = fb.build()
        new_ids.add(wrappers[orig.findex.value])
    n = 0
    for fid, w in wrappers.items():
        sites = [op for op in add.ops if op.op.startswith('Call') and op.df.get('fun') is not None
                 and op.df['fun'].value == fid]
        if len(sites) != 1:
            raise ValueError(f'wplan: expected 1 call of f{fid} in addOrder, found {len(sites)}')
        sites[0].df['fun'].value = w
        n += 1
    return {'wplan': n}


def build_wride(cx, helpers, new_ids):
    """The requestRide call in checkRegroupOrder -> wrapper(wormRiding, from, to, checkPath, order) (module doc)."""
    reg_fn = cx.fn('logic.ai.AIOrders.checkRegroupOrder')
    rr = cx.fn('logic.faction.WormRiding.requestRide')
    order_t = cx.t('logic.ai.AIOrder')
    if reg_fn.regs[1].value != order_t:
        raise ValueError('wride: checkRegroupOrder arg 1 is not the AIOrder')
    if any(op.df.get('dst') is not None and op.df['dst'].value == 1 for op in reg_fn.ops):
        raise ValueError('wride: checkRegroupOrder overwrites its order register')
    sites = [k for k, op in enumerate(reg_fn.ops) if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == rr.findex.value]
    if len(sites) != 1 or reg_fn.ops[sites[0]].op != 'Call4':
        raise ValueError(f'wride: expected 1 Call4 requestRide in checkRegroupOrder, found {len(sites)}')
    ft = cx.code.types[rr.type.value].definition
    rargs = [a.value for a in ft.args]
    ret_t = ft.ret.value
    path_t = _virtual(cx, 'logic.ai.AIOrders.checkRegroupOrder', ['current', 'steps'])
    step_t = _virtual(cx, 'logic.ai.AIOrders.checkRegroupOrder', ['from', 'mode', 'sync', 'to'])
    cur_i, cur_t = _vidx(cx, path_t, 'current')
    steps_i, steps_t = _vidx(cx, path_t, 'steps')
    mode_i, mode_t = _vidx(cx, step_t, 'mode')
    to_i, pt_t = _vidx(cx, step_t, 'to')
    x_i, x_t = _vidx(cx, pt_t, 'x')
    y_i, y_t = _vidx(cx, pt_t, 'y')
    names = [c.name.resolve(cx.code) for c in cx.code.types[mode_t].definition.constructs]
    if names[:3] != ['Walk', 'Shuttle', 'Worm']:
        raise ValueError(f'wride: AITransportMode {names}')

    fb = FB(cx, rargs + [order_t], ret_t)
    b = B(fb)
    o = len(rargs)
    res = fb.reg(ret_t)
    fb.op('Null', dst=res)
    walk = fb.reg(mode_t)
    fb.op('MakeEnum', dst=walk, construct=0, args=[])
    path, step = fb.reg(path_t), fb.reg(step_t)
    steps = fb.reg(steps_t)
    ci = fb.reg(cur_t)
    cur = fb.reg(cx.t('i32'))
    mode = fb.reg(mode_t)
    nf = fb.reg(cx.t('i32'))
    ix = fb.reg(cx.t('i32'))
    pto = fb.reg(pt_t)
    px, py = fb.reg(x_t), fb.reg(y_t)
    lx, ly = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))

    def flip(tag, landed=False):
        """Every order army not in transit whose current step is a Worm step gets a Walk step (vanilla's fallback for
        a refused Shuttle step: its Walk branch moves it to the landing point, then on to its attack slot). nf = count.
        landed=True: only armies within RIDE_LAND_R of that step's landing point (they rode and touched down outside
        vanilla's arrival tolerance: the step would never complete)."""
        fb.op('Mov', dst=nf, src=b.const('i32', 0))
        ups = b.field(o, 'unitPaths')
        fb.op('JNull', reg=ups, offset=tag + 'd')
        units = b.field(o, 'units')
        fb.op('JNull', reg=units, offset=tag + 'd')
        i = fb.reg(cx.t('i32'))
        a = _army_loop(fb, b, units, b.field(units, 'length'), i, tag, tag + 'd')  # riders (in transit) are skipped
        pv = b.call('haxe.ds.ObjectMap.get', ups, fb.dyn(a))
        fb.op('JNull', reg=pv, offset=tag)
        fb.op('ToVirtual', dst=path, src=pv)
        fb.op('Field', dst=steps, obj=path, field=steps_i)
        fb.op('JNull', reg=steps, offset=tag)
        fb.op('Field', dst=ci, obj=path, field=cur_i)
        fb.op('Mov', dst=cur, src=ci)
        fb.op('JSGte', a=cur, b=b.field(steps, 'length'), offset=tag)
        sv = b.call('hl.types.ArrayObj.getDyn', steps, cur)
        fb.op('JNull', reg=sv, offset=tag)
        fb.op('ToVirtual', dst=step, src=sv)
        fb.op('Field', dst=mode, obj=step, field=mode_i)
        fb.op('JNull', reg=mode, offset=tag)
        fb.op('EnumIndex', dst=ix, value=mode)
        fb.op('JNotEq', a=ix, b=b.const('i32', 2), offset=tag)
        if landed:
            fb.op('Field', dst=pto, obj=step, field=to_i)
            fb.op('JNull', reg=pto, offset=tag)
            fb.op('Field', dst=px, obj=pto, field=x_i)
            fb.op('Field', dst=py, obj=pto, field=y_i)
            fb.op('Sub', dst=lx, a=b.field(a, 'posx'), b=px)
            fb.op('Sub', dst=ly, a=b.field(a, 'posy'), b=py)
            fb.op('Mul', dst=lx, a=lx, b=lx)
            fb.op('Mul', dst=ly, a=ly, b=ly)
            fb.op('Add', dst=lx, a=lx, b=ly)
            fb.op('JSGt', a=lx, b=b.const('f64', RIDE_LAND_R * RIDE_LAND_R), offset=tag)
        fb.op('SetField', obj=step, field=mode_i, src=walk)
        fb.op('Incr', dst=nf)
        fb.op('JAlways', offset=tag)
        fb.label(tag + 'd')

    # this order's ride was already granted (map `wdone` order -> time): vanilla re-asks every tick until the riders
    # land (they count as not arrived); no second thumper for it. After RIDE_PICKUP_T an army still waiting at its
    # Worm step (landed outside the step's arrival tolerance: vanilla would ask a second ride; or not picked up) walks
    # A ride of less than RIDE_HOP (the worm plan's thumper point lies next to its landing point when no sand is
    # near the armies: Fremen rode 27 to Qartiel) costs a thumper for nothing: the armies walk it (flag `short`)
    skip, late, short = fb.reg(cx.t('bool')), fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('Bool', dst=skip, value=False)
    fb.op('Bool', dst=late, value=False)
    fb.op('Bool', dst=short, value=False)
    hd, hq = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=hd, src=b.const('f64', 0))
    g0 = fb.try_()
    fb.op('JNull', reg=o, offset='pre')
    dv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'wdone'), fb.dyn(o))
    fb.op('JNull', reg=dv, offset='hop')
    fb.op('Bool', dst=skip, value=True)
    dq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=dq, src=dv)
    fb.op('Sub', dst=dq, a=b.field(_state(fb, b, cx), 'time'), b=dq)
    fb.op('JSLt', a=dq, b=b.const('f64', RIDE_PICKUP_T), offset='pre')
    fb.op('Bool', dst=late, value=True)
    fb.op('JAlways', offset='pre')
    fb.label('hop')
    fb.op('JNull', reg=1, offset='pre')
    fb.op('JNull', reg=2, offset='pre')
    h4 = [fb.reg(cx.t('f64')) for _ in range(4)]
    for dst, src, k in ((h4[0], 1, 'x'), (h4[1], 1, 'y'), (h4[2], 2, 'x'), (h4[3], 2, 'y')):
        fb.op('DynGet', dst=dst, obj=src, field=cx.s(k))
    fb.op('Sub', dst=hd, a=h4[2], b=h4[0])
    fb.op('Sub', dst=hq, a=h4[3], b=h4[1])
    fb.op('Mul', dst=hd, a=hd, b=hd)
    fb.op('Mul', dst=hq, a=hq, b=hq)
    fb.op('Add', dst=hd, a=hd, b=hq)
    fb.op('Mov', dst=hd, src=b.call('hxd.$Math.sqrt', hd))
    fb.op('Mov', dst=hq, src=hd)
    fb.op('JSLt', a=hd, b=b.const('f64', RIDE_HOP), offset='hshort')
    # the foot path the ride replaces (user: judge the walk saved, not the worm's trip; Fremen walked 17 s to the
    # thumper and rode 123 to Mar-rekh: 41 s against ~35 s on foot): PathGrid.getCost(from, to) (A*, default ground
    # mask, synchronous without a callback), at least the straight hop; once per order (map `whop` order -> 1 ok)
    fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'whop'), fb.dyn(o)), offset='pre')
    pg = b.call('logic.ai.AIOrders.get_pathGrid', b.field(o, 'orders'))
    fb.op('JNull', reg=pg, offset='pre')
    gct = cx.fn('world.PathGrid.getCost')
    gca = [x.value for x in cx.code.types[gct.type.value].definition.args]
    pa, pb_ = fb.reg(gca[1]), fb.reg(gca[2])
    for p_, xr, yr in ((pa, h4[0], h4[1]), (pb_, h4[2], h4[3])):
        fb.op('New', dst=p_)
        fb.op('SetField', obj=p_, field=cx.field(gca[1], 'x'), src=xr)
        fb.op('SetField', obj=p_, field=cx.field(gca[1], 'y'), src=yr)
    nulls = []
    for tix in gca[3:]:
        r_ = fb.reg(tix)
        fb.op('Null', dst=r_)
        nulls.append(r_)
    fc = fb.reg(cx.t('f64'))
    fb.op('CallN', dst=fc, fun=gct.findex.value, args=[pg, pa, pb_] + nulls)
    fb.op('Mov', dst=hq, src=fc)
    fb.op('JSGte', a=hq, b=hd, offset='hfoot')
    fb.op('Mov', dst=hq, src=hd)
    fb.label('hfoot')
    fb.op('JSLt', a=hq, b=b.const('f64', RIDE_HOP), offset='hshort')  # an unreachable hop (infinite cost) rides
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'whop'), fb.dyn(o), fb.dyn(fc))
    fb.op('JAlways', offset='pre')
    fb.label('hshort')
    fb.op('Bool', dst=short, value=True)
    fb.label('pre')
    fb.end_try(g0)
    fb.op('JTrue', cond=short, offset='shortp')
    fb.op('JFalse', cond=skip, offset='ask')
    g1 = fb.try_()
    ofac = b.field(b.field(b.field(o, 'orders'), 'controller'), 'owner')
    fb.op('JTrue', cond=late, offset='lfall')
    # riders that touched down within RIDE_LAND_R of the landing point: walk the rest now
    flip('ll', landed=True)
    fb.op('JSLte', a=nf, b=b.const('i32', 0), offset='lfn')
    _log_ev(fb, b, cx, helpers, 'wstall', [('f', fb.get(ofac, 'kind')), ('tgt', _otgt(fb, b, cx, o)), ('why', 'land'),
                                           ('n', nf)])
    fb.op('JAlways', offset='lfn')
    fb.label('lfall')
    flip('lf')
    fb.op('JSLte', a=nf, b=b.const('i32', 0), offset='lfn')
    _log_ev(fb, b, cx, helpers, 'wstall', [('f', fb.get(ofac, 'kind')), ('tgt', _otgt(fb, b, cx, o)), ('why', 'off'),
                                           ('n', nf)])
    fb.label('lfn')
    fb.end_try(g1)
    fb.label('ret')
    fb.op('Ret', ret=res)
    fb.label('shortp')
    g2 = fb.try_()
    flip('sh')
    for m in ('wres', 'wst', 'wsl'):
        b.call('haxe.ds.ObjectMap.remove', _global_map(fb, b, cx, m), fb.dyn(o))
    sfac = b.field(b.field(b.field(o, 'orders'), 'controller'), 'owner')
    _log_ev(fb, b, cx, helpers, 'wstall', [('f', fb.get(sfac, 'kind')), ('tgt', _otgt(fb, b, cx, o)), ('why', 'short'),
                                           ('n', nf), ('d', hd), ('foot', hq)])
    fb.end_try(g2)
    fb.op('Ret', ret=res)
    fb.label('ask')
    fb.op('Call4', dst=res, fun=rr.findex.value, arg0=0, arg1=1, arg2=2, arg3=3)  # vanilla, outside any trap
    guard = fb.try_()
    fb.op('JNull', reg=o, offset='end')
    fb.op('JNull', reg=res, offset='end')
    ords = b.field(o, 'orders')
    fb.op('JNull', reg=ords, offset='end')
    fac = b.field(b.field(ords, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    wres, wst, wsl = (_global_map(fb, b, cx, m) for m in ('wres', 'wst', 'wsl'))
    fb.op('EnumIndex', dst=ix, value=res)
    # trip length (log)
    d, q = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=d, src=b.const('f64', 0))
    fx, fy, tx, ty = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('JNull', reg=1, offset='nod')
    fb.op('JNull', reg=2, offset='nod')
    for dst, src, k in ((fx, 1, 'x'), (fy, 1, 'y'), (tx, 2, 'x'), (ty, 2, 'y')):
        fb.op('DynGet', dst=dst, obj=src, field=cx.s(k))
    fb.op('Sub', dst=d, a=tx, b=fx)
    fb.op('Sub', dst=q, a=ty, b=fy)
    fb.op('Mul', dst=d, a=d, b=d)
    fb.op('Mul', dst=q, a=q, b=q)
    fb.op('Add', dst=d, a=d, b=q)
    fb.op('Mov', dst=d, src=b.call('hxd.$Math.sqrt', d))
    fb.label('nod')
    fb.op('JNotEq', a=ix, b=b.const('i32', 1), offset='refused')  # EReason Success = 1 (canRequestRide)
    # granted: the thumper is spent (the stock dropped), the claim ends
    b.call('haxe.ds.ObjectMap.remove', wres, fb.dyn(o))
    b.call('haxe.ds.ObjectMap.remove', wst, fb.dyn(o))
    b.call('haxe.ds.ObjectMap.remove', wsl, fb.dyn(o))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'wdone'), fb.dyn(o), fb.dyn(t))
    _log_ev(fb, b, cx, helpers, 'wride', [('f', fb.get(fac, 'kind')), ('tgt', _otgt(fb, b, cx, o)),
                                          ('act', fb.get(o, 'action')), ('d', d), ('n', b.field(b.field(o, 'units'), 'length')),
                                          ('stock', _stock(fb, b, cx, fac))])
    fb.op('JAlways', offset='end')
    fb.label('refused')
    # stall clock: first refusal of this waiting spell (map `wst`), restarted after a gap > RIDE_GAP (map `wsl` = last)
    lv = b.call('haxe.ds.ObjectMap.get', wsl, fb.dyn(o))
    fb.op('JNull', reg=lv, offset='first')
    fb.op('SafeCast', dst=q, src=lv)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSGt', a=q, b=b.const('f64', RIDE_GAP), offset='first')
    fb.op('JNull', reg=b.call('haxe.ds.ObjectMap.get', wst, fb.dyn(o)), offset='first')
    fb.op('JAlways', offset='have')
    fb.label('first')
    b.call('haxe.ds.ObjectMap.set', wst, fb.dyn(o), fb.dyn(t))
    fb.label('have')
    b.call('haxe.ds.ObjectMap.set', wsl, fb.dyn(o), fb.dyn(t))
    st = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=st, src=b.call('haxe.ds.ObjectMap.get', wst, fb.dyn(o)))
    fb.op('Sub', dst=st, a=t, b=st)
    fb.op('JSGte', a=st, b=b.const('f64', RIDE_STALL_T), offset='stall')
    _throttle(fb, b, cx, 'wreqlog', o, 5, 'end')
    _log_ev(fb, b, cx, helpers, 'wreq', [('f', fb.get(fac, 'kind')), ('tgt', _otgt(fb, b, cx, o)), ('why', res),
                                         ('w', st), ('d', d), ('stock', _stock(fb, b, cx, fac))])
    fb.op('JAlways', offset='end')
    # stalled: the waiting armies' Worm steps become Walk steps (vanilla's fallback for a refused Shuttle step):
    # vanilla's Walk branch moves them to the landing point, then on to their attack slots
    fb.label('stall')
    flip('su')
    b.call('haxe.ds.ObjectMap.remove', wres, fb.dyn(o))
    b.call('haxe.ds.ObjectMap.remove', wst, fb.dyn(o))
    b.call('haxe.ds.ObjectMap.remove', wsl, fb.dyn(o))
    _log_ev(fb, b, cx, helpers, 'wstall', [('f', fb.get(fac, 'kind')), ('tgt', _otgt(fb, b, cx, o)), ('why', res),
                                           ('w', st), ('n', nf), ('d', d), ('stock', _stock(fb, b, cx, fac))])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    # the call gains the order argument: Call4 -> CallN
    k = sites[0]
    old = reg_fn.ops[k]
    new = Opcode('CallN', {})
    for field, typ in opcodes['CallN'].items():
        new.df[field] = Opcode.TYPE_MAP[typ]()
    new.df['dst'].value = old.df['dst'].value
    new.df['fun'].value = w
    new.df['args'].value = [Reg(old.df[f'arg{j}'].value) for j in range(4)] + [Reg(1)]
    reg_fn.ops[k] = new
    return {'wride': 1}


def build_ride_tick(cx, helpers):
    """aimod_ride(mil, dt): every RIDE_CHECK s, for a faction with thumpers: map `wfree` faction -> now while a thumper
    is free (stock - claims >= 1), else removed; `tstk` row every RIDE_LOG_T s."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    _tick(fb, b, cx, t, RIDE_CHECK, 'end')
    fb.op('JFalse', cond=b.call('ent.Faction.hasAccessToRes', fac, b.const('i32', RIDE_RES)), offset='end')
    stk = _stock(fb, b, cx, fac)
    cl = _claims(fb, b, cx, fac, t)
    q = fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=q, src=cl)
    fb.op('Sub', dst=q, a=stk, b=q)
    wfree = _global_map(fb, b, cx, 'wfree')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'wfreen'), fb.dyn(fac), fb.dyn(q))  # free count (_ride_leg)
    fb.op('JSLt', a=q, b=b.const('f64', 1), offset='none')
    b.call('haxe.ds.ObjectMap.set', wfree, fb.dyn(fac), fb.dyn(t))
    fb.op('JAlways', offset='log')
    fb.label('none')
    b.call('haxe.ds.ObjectMap.remove', wfree, fb.dyn(fac))
    fb.label('log')
    _throttle(fb, b, cx, 'tstk', fac, RIDE_LOG_T, 'end')
    _log_ev(fb, b, cx, helpers, 'tstk', [('f', fb.get(fac, 'kind')), ('n', stk), ('cl', cl)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
