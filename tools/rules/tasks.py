"""Task claims (docs/ARCHITECTURE-PLAN.md step 2 stage 1): every army belongs to at most one task, by priority.

Before this, each rule that took armies had its own lock map (`rallied`, `rlock`, `keepord`, `take-keep`, worm
hold) to keep the others off, and what one lock didn't name, another rule took (vanilla's siege pick taking a
contest's or a capture's army, a rally walk pulled into a Defense). Claims are one shared answer:
- maps `tkp` army -> priority, `tkt` army -> when claimed; a claim older than CLAIM_TTL s has lapsed;
- `aimod_claim(fac, a, prio)`: a lapsed / absent / lower claim is replaced, returns true; a higher live claim
  stays, false. A rule that moves an army without an order claims it (the rally gather);
- `aimod_held(a, prio)`: a live claim above prio holds the army: pickers skip it;
- the refresher (`aimod_tasks`, tick chain, every TASK_T s per faction) re-claims every army of our orders by what
  the order is (never lowering a live higher claim): main-base Defense 100, contest hunt 80 (map `hcon`), a capture in Action 70,
  (rally gather 65, claimed by rally.py), Defense 60, a siege / raid walking 50, chase hunt 40, Resupply 30, Patrol / Discovery 10. Orders keep their armies claimed
  while they run; an army whose order ended keeps the claim at most CLAIM_TTL. The first sight of each Military /
  Defense order also writes its decision record (rules/value.py `tval`: value at stake, armies' value, forecast).
Consumers: vanilla's mission picks (pick-life wrappers: a siege pick asks SIEGE_P, a Defense DEFENSE_P, a main-base
Defense MAINBASE_P, a world event DISC_P) and aimod_free (hunts, raids, strand: FREE_P) drop armies held above
their own priority. Logs `claimx` (a, held prio, asked prio, src) when a pick drops an army, per army per 30 s.
Replaced: `keepord`, `rallied` (common._rallying). Kept by design: `rlock` (post-retreat cooldown), `take-keep` (share limit)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules import bkstate as bks
from rules.value import _task_record

def build_held(cx):
    """aimod_held(a, prio) -> bool (see module doc)."""
    fb = FB(cx, [cx.t('ent.Army'), cx.t('f64')], cx.t('bool'))
    b = B(fb)
    r = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=r, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    _claimed(fb, b, cx, 0, 1, t, 'held', 'end')
    fb.label('held')
    fb.op('Bool', dst=r, value=True)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=r)
    return fb.build()


def build_claim(cx):
    """aimod_claim(a, prio) -> bool (see module doc)."""
    fb = FB(cx, [cx.t('ent.Army'), cx.t('f64')], cx.t('bool'))
    b = B(fb)
    r = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=r, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    _claimed(fb, b, cx, 0, 1, t, 'end', 'take')
    fb.label('take')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'tkp'), fb.dyn(0), fb.dyn(1))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'tkt'), fb.dyn(0), fb.dyn(t))
    fb.op('Bool', dst=r, value=True)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=r)
    return fb.build()


def _siege_mark(fb, b, cx, fac, o, t):
    """Base assault: a Military order of fac at Regroup or later on a main base, or with siegeAction Raze, marks map
    `dsiege` fac -> now: the army doctrine's Siege mode (rules/doctrine.py: unit mix and gear for structures)."""
    u = _uid('sm')
    fb.op('JSLt', a=b.field(o, 'phase'), b=b.const('i32', REGROUP), offset=u)
    sa = b.cast(fb.get(o, 'siegeAction'), 'String')
    fb.op('JNull', reg=sa, offset=u + 'mb')
    fb.op('JEq', a=b.call('String.__compare', sa, fb.dyn(fb.string('Raze'))), b=b.const('i32', 0), offset=u + 'y')
    fb.label(u + 'mb')
    st = b.cast(fb.dyn(b.call('logic.ai.AIOrder.getTarget', o)), 'ent.Structure')
    fb.op('JNull', reg=st, offset=u)
    fb.op('JFalse', cond=b.call('ent.Structure.get_isMainBase', st), offset=u)
    fb.label(u + 'y')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'dsiege'), fb.dyn(fac), fb.dyn(t))
    fb.label(u)


def _siege_memory(fb, b, cx, helpers, fac, o, t, units):
    """A Military order on a structure in Action: map `sxa` order -> every army seen in it (an array); once SX_MIN or
    more were seen and at least half of them are dead, its target is marked lost for fac (`_fac_map` `sxf` target ->
    time, once per order: map `sxd`) once the survivors also read a battle forecast below SX_FC there (over SX_FC_T),
    log `sxfail` (f, s, n0 seen, n dead). Deaths only: armies leaving alive (our
    `release` of spare occupiers) don't count. Harkonnen took 4 runs each at Atreides' Waldah and Admara, every one
    beaten in Action (14 armies down to 3), match 2026-10-24 02:10: rules/annex.py drops a lost target for SX_MEM."""
    u = _uid('sx')
    sxa = _global_map(fb, b, cx, 'sxa')
    seen = fb.reg(cx.t('hl.types.ArrayObj'))
    sv = b.call('haxe.ds.ObjectMap.get', sxa, fb.dyn(o))
    fb.op('JNull', reg=sv, offset=u + 'new')
    fb.op('Mov', dst=seen, src=b.cast(sv, 'hl.types.ArrayObj'))
    fb.op('JAlways', offset=u + 'have')
    fb.label(u + 'new')
    fb.op('Mov', dst=seen, src=_new_array(fb, b, cx))
    b.call('haxe.ds.ObjectMap.set', sxa, fb.dyn(o), fb.dyn(seen))
    fb.label(u + 'have')
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head(u + 'a')
    fb.op('JSGte', a=i, b=b.field(units, 'length'), offset=u + 'ad')
    av = b.call('hl.types.ArrayObj.getDyn', units, i)
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=av, offset=u + 'a')
    fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', seen, av), offset=u + 'a')
    b.call('hl.types.ArrayObj.push', seen, av)
    fb.op('JAlways', offset=u + 'a')
    fb.label(u + 'ad')
    n0, nd = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=n0, src=b.field(seen, 'length'))
    fb.op('JSLt', a=n0, b=b.const('i32', SX_MIN), offset=u + 'd')
    fb.op('Mov', dst=nd, src=b.const('i32', 0))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head(u + 'k')
    fb.op('JSGte', a=i, b=n0, offset=u + 'kd')
    ke = b.cast(b.call('hl.types.ArrayObj.getDyn', seen, i), 'ent.Entity')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=ke, offset=u + 'k')
    fb.op('JFalse', cond=b.call('ent.Entity.isDead', ke), offset=u + 'k')
    fb.op('Incr', dst=nd)
    fb.op('JAlways', offset=u + 'k')
    fb.label(u + 'kd')
    h = fb.reg(cx.t('i32'))
    fb.op('Mul', dst=h, a=nd, b=b.const('i32', 2))
    fb.op('JSLt', a=h, b=n0, offset=u + 'd')
    # ... and the survivors lose it: the battle forecast at the target with the order's armies now < SX_FC (review: 2 of
    # 4 dead in a Pillage that then succeeded marked the target lost for SX_MEM); a won fight is judged again next pass
    tg0 = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=tg0, src=b.call('logic.ai.AIOrder.getTarget', o))
    fb.op('JNull', reg=tg0, offset=u + 'd')
    sfc = fb.reg(cx.t('f64'))
    sfa = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=sfa, value=True)
    fb.op('CallN', dst=sfc, fun=helpers['forecast'], args=[fac, tg0, b.const('f64', SX_FC_T), sfa, units])
    fb.op('JSGte', a=sfc, b=_ratio(fb, b, SX_FC), offset=u + 'd')
    sxd = _global_map(fb, b, cx, 'sxd')
    fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', sxd, fb.dyn(o)), offset=u + 'd')
    b.call('haxe.ds.ObjectMap.set', sxd, fb.dyn(o), fb.dyn(t))
    tg = b.call('logic.ai.AIOrder.getTarget', o)
    fb.op('JNull', reg=tg, offset=u + 'd')
    b.call('haxe.ds.ObjectMap.set', _fac_map(fb, b, cx, 'sxf', fac), fb.dyn(tg), fb.dyn(t))
    _log_ev(fb, b, cx, helpers, 'sxfail', [('f', fb.get(fac, 'kind')), ('s', b.cast(fb.dyn(tg), 'ent.Entity')),
                                           ('n0', fb.dyn(n0)), ('n', fb.dyn(nd))])
    fb.label(u + 'd')


def build_tasks_tick(cx, helpers):
    """aimod_tasks(mil, dt): the refresher (see module doc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    _tick(fb, b, cx, t, TASK_T, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    tkp, tkt = _global_map(fb, b, cx, 'tkp'), _global_map(fb, b, cx, 'tkt')
    conmap = _global_map(fb, b, cx, 'hcon')
    k, ix, j = (fb.reg(cx.t('i32')) for _ in range(3))
    pr = fb.reg(cx.t('f64'))
    de = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head('o')
    fb.op('JSGte', a=k, b=b.field(orders, 'length'), offset='end')
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, k), 'logic.ai.AIOrder')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=o, offset='o')
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='o')
    ot = b.field(o, 'type')
    fb.op('EnumIndex', dst=ix, value=ot)
    fb.op('Mov', dst=pr, src=b.const('f64', P_IDLE))
    fb.op('JEq', a=ix, b=b.const('i32', MILITARY), offset='mil')
    fb.op('JEq', a=ix, b=b.const('i32', DEFENSE), offset='dfn')
    fb.op('JNotEq', a=ix, b=b.const('i32', RESUPPLY), offset='set')
    fb.op('Mov', dst=pr, src=b.const('f64', P_HEAL))
    fb.op('JAlways', offset='set')
    fb.label('dfn')
    fb.op('Mov', dst=pr, src=b.const('f64', P_DEFENSE))
    fb.op('EnumField', dst=de, value=ot, construct=DEFENSE, field=0)
    _task_record(fb, b, cx, helpers, fac, o, t, units, 'defense', False, target=de)
    fb.op('JNull', reg=de, offset='set')
    ds = b.cast(fb.dyn(de), 'ent.Structure')
    fb.op('JNull', reg=ds, offset='set')
    fb.op('JFalse', cond=b.call('ent.Structure.get_isMainBase', ds), offset='set')
    fb.op('Mov', dst=pr, src=b.const('f64', P_MAINBASE))
    fb.op('JAlways', offset='set')
    fb.label('mil')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='set')
    fb.op('EnumIndex', dst=ix, value=tt)
    fb.op('JNotEq', a=ix, b=b.const('i32', T_GROUP), offset='struct')
    fb.op('Mov', dst=pr, src=b.const('f64', P_CHASE))
    fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'hgrd'), fb.dyn(o)), offset='guard')
    fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.FIGHT_ORDER), fb.dyn(o)), offset='guard')
    fb.op('JNull', reg=b.call('haxe.ds.ObjectMap.get', conmap, fb.dyn(o)), offset='chase')
    _task_record(fb, b, cx, helpers, fac, o, t, units, 'contest', False)
    fb.op('Mov', dst=pr, src=b.const('f64', P_CONTEST))
    fb.op('JAlways', offset='set')
    fb.label('chase')
    _task_record(fb, b, cx, helpers, fac, o, t, units, 'chase', True)
    fb.op('JAlways', offset='set')
    fb.label('guard')  # a capture guard (rules/hunt.py `hgrd`): the capture's own rank of claim
    _task_record(fb, b, cx, helpers, fac, o, t, units, 'guard', True)
    fb.op('Mov', dst=pr, src=b.const('f64', P_CONTEST))
    fb.op('JAlways', offset='set')
    fb.label('struct')
    _siege_mark(fb, b, cx, fac, o, t)
    _task_record(fb, b, cx, helpers, fac, o, t, units, b.field(o, 'siegeAction'), True)
    fb.op('Mov', dst=pr, src=b.const('f64', P_SIEGE))
    fb.op('JSLt', a=b.field(o, 'phase'), b=b.const('i32', ACTION), offset='set')
    fb.op('Mov', dst=pr, src=b.const('f64', P_CAPTURE))
    _siege_memory(fb, b, cx, helpers, fac, o, t, units)
    fb.label('set')
    a = _army_loop(fb, b, units, b.field(units, 'length'), j, 'u', 'o', transported=True)
    # a live higher claim stays (its owner refreshes it, else it lapses): the rally's gather walk rides a Patrol order
    _claimed(fb, b, cx, a, pr, t, 'u', 'uset')
    fb.label('uset')
    b.call('haxe.ds.ObjectMap.set', tkp, fb.dyn(a), fb.dyn(pr))
    b.call('haxe.ds.ObjectMap.set', tkt, fb.dyn(a), fb.dyn(t))
    fb.op('JAlways', offset='u')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
