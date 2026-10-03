"""Order keep (dead units): vanilla checkOrderTerminations (closure f40838) removes an order's dead units with
AIOrder.removeUnits, which cancels the whole order before Action when one of them isn't a timed temporary unit (no
DisbandOnTimerEnd in its data traits). Harkonnen's 12-army Liberate of Marrekh (12:12) was cancelled that way in
Regroup at 12:49 with no visible death (CP and army count don't show one either): one unit read dead and the attack
was scrapped.

Wrapper around that removeUnits call: every removed unit logs `odead` (f, a, tgt = the order's target, hp, ph, n =
order armies before; `mod log` counts them per order as deaths). For
our Military order before Action of at least KEEP_MIN armies losing at most 1 / KEEP_SHARE of them, the units are taken out the way removeUnits
does it (units.remove, unitPaths.remove, removeAbilitiesOfUnit) without the cancel; logs `okeep` (f, n left, ph).
The rest of the plan re-judges the smaller force (siege-engage needs ENTER at the target, stage gathers first).
Other orders, Action, or nothing left: vanilla removeUnits. Fails safe: vanilla call on any error.

Take keep: AIOrder.removeUnit (an army taken by a new order: AIOrders.addOrder / removeUnitFromOrders) cancels the
whole order before Action the same way. Harkonnen's 14-army Annex of Kargah (Regroup, 82:55) was scrapped when
vanilla's Defense of Tabha took one army. Wrapper on those two calls: our Military order of at least KEEP_MIN armies
before Action keeps the rest (units.remove, unitPaths.remove, removeAbilitiesOfUnit, no cancel) while it still holds
>= (1 - 1 / KEEP_SHARE) of its armies when first trimmed (map `tk0`: order -> that count); logs `tkeep` (f, a, n
left, ph). Smaller orders, a deeper cut, Action or other orders: vanilla removeUnit.

Siege keep (lone besieger): the same closure cancels a Military ArmySiege / ArmyFight order on a structure in any
phase when the structure is under siege and none of its besiegers is ours (AIOrders.hx:906: someone else's siege).
The first of our armies to arrive starts the siege alone; when it dies the list holds no unit of ours and the whole
order is scrapped while the rest walk in (Fremen's 14-army Dismantle of a renegade base, 43:48, live balance 5.8:
Action 45:32, its F_Ship killed 45:33, cancelled). Wrapper on that one cancel call: no occupier, no live besieger of
another faction, and the order still has a live unit -> no cancel (vanilla's Action re-sends doAction(ArmySiege) to
its idle armies and a new besieger starts), for at most BKEEP_T s per episode (map `bkeep`: first skip; `bkeepz`: last skip, a gap > BKEEP_GAP starts a new
episode), then vanilla's cancel. Logs `bkeep` (f, tgt, n units, ph) once per order per 10 s."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

MILITARY_T = 1     # AIOrderType Military
KEEP_MIN = 4       # order-keep: only orders of at least this many armies ...
KEEP_SHARE = 4     # ... losing at most 1 / this of them (a 3-army Annex down to 2 is re-sized by vanilla's relaunch)
BKEEP_T = 30       # s: siege keep: a target whose last besieger of ours died keeps the order this long for a new one
BKEEP_GAP = 5      # s: ... a skip this long after the previous one starts a new episode (a besieger of ours held it between)


def _closure(cx):
    """checkOrderTerminations' closure (f40838 in hlboot): the only function calling AIOrder.removeUnits and
    Unit.isDead."""
    rid = cx.fn('logic.ai.AIOrder.removeUnits').findex.value
    isdead = cx.fn('ent.Entity.isDead').findex.value
    hits = []
    for f in cx.code.functions:
        calls = {op.df['fun'].value for op in f.ops if op.op.startswith('Call') and op.df.get('fun') is not None}
        if rid in calls and isdead in calls:
            hits.append(f)
    if len(hits) != 1:
        raise ValueError(f'order closure: expected 1 function calling removeUnits and isDead, found {len(hits)}')
    return hits[0]


def build_siege_keep(cx, helpers, new_ids):
    """Wrap the cancel call after the closure's besieger test (see module doc). Locator: the first Field read of
    SiegeComponent.isUnderSiege, the InstanceClosure after it (the besieger predicate), then the next Call2 of the
    order-cancel helper (AIOrder, ActionEndReason) -> Void."""
    f = _closure(cx)
    st = cx.t('ent.comp.SiegeComponent')
    fi = cx.field(st, 'isUnderSiege')
    order_t, void_t = cx.t('logic.ai.AIOrder'), cx.t('void')
    ops = f.ops
    k0 = next(i for i, op in enumerate(ops) if op.op == 'Field' and f.regs[op.df['obj'].value].value == st
              and op.df['field'].value == fi)
    k1 = next(i for i in range(k0, len(ops)) if ops[i].op == 'InstanceClosure')
    funs = {g.findex.value: g for g in cx.code.functions}

    def is_cancel(op):
        g = funs.get(op.df['fun'].value) if op.op == 'Call2' else None
        if g is None:
            return False
        d = cx.code.types[g.type.value].definition
        return [a.value for a in d.args][:1] == [order_t] and len(d.args) == 2 and d.ret.value == void_t             and cx.code.types[d.args[1].value].definition.name.resolve(cx.code) == 'ent.ActionEndReason'

    k2 = next(i for i in range(k1, len(ops)) if is_cancel(ops[i]))
    site = ops[k2]
    fid = site.df['fun'].value
    fn = funs[fid]
    fargs = [a.value for a in cx.code.types[fn.type.value].definition.args]
    # the besieger test sits between the isUnderSiege read and this cancel: no other cancel in between
    if any(is_cancel(ops[i]) for i in range(k0, k2)):
        raise ValueError('siege-keep: unexpected cancel between isUnderSiege and the besieger test')
    fb = FB(cx, fargs, void_t, fun_type=fn.type.value)
    b = B(fb)
    void = fb.reg(void_t)
    keep = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=keep, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='orig')
    fac = b.call('logic.ai.AIOrder.get_faction', 0)
    fb.op('JNull', reg=fac, offset='orig')
    te = b.call('logic.ai.AIOrder.getTarget', 0)
    fb.op('JNull', reg=te, offset='orig')
    s_ = b.cast(fb.dyn(te), 'ent.Structure')
    fb.op('JNull', reg=s_, offset='orig')
    sg = b.field(s_, 'siege')
    fb.op('JNull', reg=sg, offset='orig')
    fb.op('JNotNull', reg=b.field(sg, 'occupier'), offset='orig')  # occupied by another: a real loss
    bs = b.field(sg, 'besiegers')
    i, nu = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('JNull', reg=bs, offset='bsd')
    ba = b.cast(b.field(bs, 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=ba, offset='bsd')
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('bsl')
    fb.op('JSGte', a=i, b=b.field(ba, 'length'), offset='bsd')
    be = b.cast(b.call('hl.types.ArrayObj.getDyn', ba, i), 'ent.Entity')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=be, offset='bsl')
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', be), offset='bsl')
    fb.op('JNotEq', a=b.call('ent.Entity.get_owner', be), b=fac, offset='orig')  # another faction besieges it
    fb.op('JAlways', offset='bsl')
    fb.label('bsd')
    # a live unit of the order left to start a new siege
    ou = b.field(0, 'units')
    fb.op('JNull', reg=ou, offset='orig')
    fb.op('Mov', dst=nu, src=b.const('i32', 0))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('oul')
    fb.op('JSGte', a=i, b=b.field(ou, 'length'), offset='oud')
    ue = b.cast(b.call('hl.types.ArrayObj.getDyn', ou, i), 'ent.Entity')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=ue, offset='oul')
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', ue), offset='oul')
    fb.op('Incr', dst=nu)
    fb.op('JAlways', offset='oul')
    fb.label('oud')
    fb.op('JSLte', a=nu, b=b.const('i32', 0), offset='orig')
    # time bound: BKEEP_T from the first skip of this order
    mp, ml = _global_map(fb, b, cx, 'bkeep'), _global_map(fb, b, cx, 'bkeepz')
    now, q = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=now, src=b.field(_state(fb, b, cx), 'time'))
    od = fb.dyn(0)
    # a new episode (last skip > BKEEP_GAP s ago: a besieger of ours took over in between) gets a fresh BKEEP_T
    lv = b.call('haxe.ds.ObjectMap.get', ml, od)
    b.call('haxe.ds.ObjectMap.set', ml, od, fb.dyn(now))
    fb.op('JNull', reg=lv, offset='fresh')
    fb.op('SafeCast', dst=q, src=lv)
    fb.op('Sub', dst=q, a=now, b=q)
    fb.op('JSGt', a=q, b=b.const('f64', BKEEP_GAP), offset='fresh')
    fv = b.call('haxe.ds.ObjectMap.get', mp, od)
    fb.op('JNotNull', reg=fv, offset='old')
    fb.label('fresh')
    b.call('haxe.ds.ObjectMap.set', mp, od, fb.dyn(now))
    fb.op('JAlways', offset='go')
    fb.label('old')
    fb.op('SafeCast', dst=q, src=fv)
    fb.op('Sub', dst=q, a=now, b=q)
    fb.op('JSGt', a=q, b=b.const('f64', BKEEP_T), offset='orig')
    fb.label('go')
    fb.op('Bool', dst=keep, value=True)
    _throttle(fb, b, cx, 'bkeepl', 0, 10, 'orig')
    _log_ev(fb, b, cx, helpers, 'bkeep', [('f', fb.get(fac, 'kind')), ('tgt', te), ('n', fb.dyn(nu)),
                                          ('ph', fb.dyn(b.field(0, 'phase')))])
    fb.label('orig')
    fb.end_try(guard)
    fb.op('JTrue', cond=keep, offset='ret')
    fb.op('Call2', dst=void, fun=fid, arg0=0, arg1=1)
    fb.label('ret')
    fb.op('Ret', ret=void)
    w = fb.build()
    site.df['fun'].value = w
    new_ids.add(w)
    return {'siege-keep': 1}


def build_order_keep(cx, helpers, new_ids):
    """Redirect the removeUnits call in checkOrderTerminations' closure (f40838 in hlboot: found as the only function
    calling it alongside Unit.isDead and the Shuttle ability check) to the wrapper (see module doc)."""
    ru = cx.fn('logic.ai.AIOrder.removeUnits')
    rid = ru.findex.value
    rft = cx.code.types[ru.type.value].definition
    isdead = cx.fn('ent.Entity.isDead').findex.value
    sites = []
    for f in cx.code.functions:
        ops = f.ops
        calls = {op.df['fun'].value for op in ops if op.op.startswith('Call') and op.df.get('fun') is not None}
        if rid in calls and isdead in calls:
            sites += [op for op in ops if op.op.startswith('Call') and op.df.get('fun') is not None
                      and op.df['fun'].value == rid]
    if len(sites) != 1:
        raise ValueError(f'order-keep: expected 1 removeUnits call next to isDead, found {len(sites)}')
    fb = FB(cx, [a.value for a in rft.args], rft.ret.value, fun_type=ru.type.value)
    b = B(fb)
    res = fb.reg(rft.ret.value)
    kept = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=kept, value=False)
    ue = fb.reg(cx.t('ent.Entity'))
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='orig')
    fb.op('JNull', reg=1, offset='orig')
    rn = b.field(1, 'length')
    fb.op('JSLte', a=rn, b=b.const('i32', 0), offset='orig')
    ou = b.field(0, 'units')
    fb.op('JNull', reg=ou, offset='orig')
    n0 = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=n0, src=b.field(ou, 'length'))
    ph = b.field(0, 'phase')
    # log every removed unit; count those still in the order
    i, inn = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    fb.op('Mov', dst=inn, src=b.const('i32', 0))
    b.loop_head('lg')
    fb.op('JSGte', a=i, b=rn, offset='lgd')
    u = b.cast(b.call('hl.types.ArrayObj.getDyn', 1, i), 'ent.Unit')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=u, offset='lg')
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', ou, fb.dyn(u)), offset='lg')
    fb.op('Incr', dst=inn)
    fb.op('Mov', dst=ue, src=u)
    _log_ev(fb, b, cx, helpers, 'odead', [('f', fb.get(b.call('ent.Entity.get_owner', ue), 'kind')), ('a', ue),
                                          ('tgt', b.cast(fb.dyn(b.call('logic.ai.AIOrder.getTarget', 0)), 'ent.Entity')),
                                          ('hp%', b.call('ent.Entity.get_lifeRatio', ue)), ('ph', fb.dyn(ph)),
                                          ('n', fb.dyn(n0))])
    fb.op('JAlways', offset='lg')
    fb.label('lgd')
    # keep: our Military order before Action with armies left
    ix = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ix, value=b.field(0, 'type'))
    fb.op('JNotEq', a=ix, b=b.const('i32', MILITARY_T), offset='orig')
    fb.op('JSGte', a=ph, b=b.const('i32', ACTION), offset='orig')
    left = fb.reg(cx.t('i32'))
    fb.op('Sub', dst=left, a=n0, b=inn)
    fb.op('JSLte', a=left, b=b.const('i32', 0), offset='orig')
    fb.op('JSLte', a=inn, b=b.const('i32', 0), offset='orig')  # nothing of ours to remove: vanilla (no-op)
    fb.op('JSLt', a=n0, b=b.const('i32', KEEP_MIN), offset='orig')
    q = fb.reg(cx.t('i32'))
    fb.op('Mul', dst=q, a=inn, b=b.const('i32', KEEP_SHARE))
    fb.op('JSGt', a=q, b=n0, offset='orig')
    paths = b.field(0, 'unitPaths')
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('rm')
    fb.op('JSGte', a=i, b=rn, offset='rmd')
    u2 = b.cast(b.call('hl.types.ArrayObj.getDyn', 1, i), 'ent.Unit')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=u2, offset='rm')
    b.call('hl.types.ArrayObj.remove', ou, fb.dyn(u2))
    fb.op('JNull', reg=paths, offset='rmp')
    b.call('haxe.ds.ObjectMap.remove', paths, fb.dyn(u2))
    fb.label('rmp')
    b.call('logic.ai.AIOrder.removeAbilitiesOfUnit', 0, u2)
    fb.op('JAlways', offset='rm')
    fb.label('rmd')
    fb.op('Bool', dst=kept, value=True)
    _log_ev(fb, b, cx, helpers, 'okeep', [('f', fb.get(b.call('ent.Entity.get_owner', ue), 'kind')), ('n', fb.dyn(left)),
                                          ('ph', fb.dyn(ph))])
    fb.label('orig')
    fb.end_try(guard)
    fb.op('JFalse', cond=kept, offset='van')
    fb.op('Bool', dst=res, value=True)
    fb.op('Ret', ret=res)
    fb.label('van')
    fb.op('Call2', dst=res, fun=rid, arg0=0, arg1=1)
    fb.op('Ret', ret=res)
    w = fb.build()
    sites[0].df['fun'].value = w
    new_ids.add(w)
    return {'order-keep': 1}


def build_take_keep(cx, helpers, new_ids):
    """Redirect AIOrder.removeUnit in AIOrders.addOrder and AIOrders.removeUnitFromOrders (see module doc)."""
    ru = cx.fn('logic.ai.AIOrder.removeUnit')
    rid = ru.findex.value
    rft = cx.code.types[ru.type.value].definition
    sites = []
    for caller in ('logic.ai.AIOrders.addOrder', 'logic.ai.AIOrders.removeUnitFromOrders'):
        hit = [op for op in cx.fn(caller).ops if op.op.startswith('Call') and op.df.get('fun') is not None
               and op.df['fun'].value == rid]
        if len(hit) != 1:
            raise ValueError(f'take-keep: expected 1 removeUnit call in {caller}, found {len(hit)}')
        sites += hit
    fb = FB(cx, [a.value for a in rft.args], rft.ret.value, fun_type=ru.type.value)
    b = B(fb)
    res = fb.reg(rft.ret.value)
    kept = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=kept, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='orig')
    fb.op('JNull', reg=1, offset='orig')
    ix = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ix, value=b.field(0, 'type'))
    fb.op('JNotEq', a=ix, b=b.const('i32', MILITARY_T), offset='orig')
    ph = b.field(0, 'phase')
    fb.op('JSGte', a=ph, b=b.const('i32', ACTION), offset='orig')
    ou = b.field(0, 'units')
    fb.op('JNull', reg=ou, offset='orig')
    n0 = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=n0, src=b.field(ou, 'length'))
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', ou, fb.dyn(1)), offset='orig')
    # the size when first trimmed (map tk0): never below (1 - 1/KEEP_SHARE) of it, never below KEEP_MIN - 1
    mp = _global_map(fb, b, cx, 'tk0')
    od = fb.dyn(0)
    base = fb.reg(cx.t('i32'))
    bv = b.call('haxe.ds.ObjectMap.get', mp, od)
    fb.op('JNotNull', reg=bv, offset='hasb')
    fb.op('JSLt', a=n0, b=b.const('i32', KEEP_MIN), offset='orig')
    fb.op('Mov', dst=base, src=n0)
    b.call('haxe.ds.ObjectMap.set', mp, od, fb.dyn(base))
    fb.op('JAlways', offset='cut')
    fb.label('hasb')
    fb.op('SafeCast', dst=base, src=bv)
    fb.label('cut')
    left = fb.reg(cx.t('i32'))
    fb.op('Sub', dst=left, a=n0, b=b.const('i32', 1))
    fb.op('JSLt', a=left, b=b.const('i32', KEEP_MIN - 1), offset='orig')
    q, r = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mul', dst=q, a=left, b=b.const('i32', KEEP_SHARE))  # left / base >= (KEEP_SHARE - 1) / KEEP_SHARE
    fb.op('Mul', dst=r, a=base, b=b.const('i32', KEEP_SHARE - 1))
    fb.op('JSLt', a=q, b=r, offset='orig')
    b.call('hl.types.ArrayObj.remove', ou, fb.dyn(1))
    paths = b.field(0, 'unitPaths')
    fb.op('JNull', reg=paths, offset='np')
    b.call('haxe.ds.ObjectMap.remove', paths, fb.dyn(1))
    fb.label('np')
    b.call('logic.ai.AIOrder.removeAbilitiesOfUnit', 0, 1)
    fb.op('Bool', dst=kept, value=True)
    ue = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ue, src=1)
    _log_ev(fb, b, cx, helpers, 'tkeep', [('f', fb.get(b.call('ent.Entity.get_owner', ue), 'kind')), ('a', ue), ('n', fb.dyn(left)),
                                          ('ph', fb.dyn(ph))])
    fb.label('orig')
    fb.end_try(guard)
    fb.op('JFalse', cond=kept, offset='van')
    fb.op('Bool', dst=res, value=True)
    fb.op('Ret', ret=res)
    fb.label('van')
    fb.op('Call2', dst=res, fun=rid, arg0=0, arg1=1)
    fb.op('Ret', ret=res)
    w = fb.build()
    for op in sites:
        op.df['fun'].value = w
    new_ids.add(w)
    return {'take-keep': len(sites)}


def build_term_probe(cx, helpers, new_ids):
    """Diagnostics for orders cancelled right after start (`stop src <none>`, Preparation, 0.04-1 s: Fremen's 14-army
    hunts on Atreides' stack at Gunbu, every 40 s from 45:50). checkOrderTerminations' closure cancels on a removed
    Group target or on a refused `Shuttle` path step (checkUseAbilityOn Invalid / BlockedBy); this wraps its
    checkUseAbilityOn calls and logs `oterm` (ab, r) when the result isn't Success, at most once per 2 s per
    AbilityManager. A cancel with no `oterm` row at that time = the Group branch."""
    cu = cx.fn('logic.faction.AbilityManager.checkUseAbilityOn')
    cid = cu.findex.value
    cft = cx.code.types[cu.type.value].definition
    ru = cx.fn('logic.ai.AIOrder.removeUnits').findex.value
    isdead = cx.fn('ent.Entity.isDead').findex.value
    sites = []
    for f in cx.code.functions:
        calls = [op for op in f.ops if op.op.startswith('Call') and op.df.get('fun') is not None]
        ids = {op.df['fun'].value for op in calls}
        if ru in ids and isdead in ids:
            sites += [op for op in calls if op.df['fun'].value == cid]
    if not sites:
        raise ValueError('term-probe: no checkUseAbilityOn call next to removeUnits / isDead')
    args = [a.value for a in cft.args]
    fb = FB(cx, args, cft.ret.value, fun_type=cu.type.value)
    b = B(fb)
    res = fb.reg(cft.ret.value)
    fb.op('CallN', dst=res, fun=cid, args=list(range(len(args))))  # vanilla first, outside the trap
    names = [c.name.resolve(cx.code) for c in cx.code.types[cft.ret.value].definition.constructs]
    idx = fb.reg(cx.t('i32'))
    guard = fb.try_()
    fb.op('EnumIndex', dst=idx, value=res)
    fb.op('JEq', a=idx, b=b.const('i32', names.index('Success')), offset='done')
    _throttle(fb, b, cx, 'oterm', 0, 2, 'done')
    _log_ev(fb, b, cx, helpers, 'oterm', [('ab', fb.dyn(1)), ('r', fb.dyn(res))])
    fb.label('done')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    for op in sites:
        op.df['fun'].value = w
    new_ids.add(w)
    return {'term-probe': len(sites)}
