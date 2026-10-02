"""Order keep (dead units): vanilla checkOrderTerminations (closure f40838) removes an order's dead units with
AIOrder.removeUnits, which cancels the whole order before Action when one of them isn't a timed temporary unit (no
DisbandOnTimerEnd in its data traits). Harkonnen's 12-army Liberate of Marrekh (12:12) was cancelled that way in
Regroup at 12:49 with no visible death (CP and army count don't show one either): one unit read dead and the attack
was scrapped.

Wrapper around that removeUnits call: every removed unit logs `odead` (f, a, hp, ph, n = order armies before). For
our Military order before Action of at least KEEP_MIN armies losing at most 1 / KEEP_SHARE of them, the units are taken out the way removeUnits
does it (units.remove, unitPaths.remove, removeAbilitiesOfUnit) without the cancel; logs `okeep` (f, n left, ph).
The rest of the plan re-judges the smaller force (siege-engage needs ENTER at the target, stage gathers first).
Other orders, Action, or nothing left: vanilla removeUnits. Fails safe: vanilla call on any error."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

MILITARY_T = 1     # AIOrderType Military
KEEP_MIN = 4       # order-keep: only orders of at least this many armies ...
KEEP_SHARE = 4     # ... losing at most 1 / this of them (a 3-army Annex down to 2 is re-sized by vanilla's relaunch)


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
    _log_ev(fb, b, cx, helpers, 'odead', [('f', fb.get(ue, 'owner', 'kind')), ('a', ue),
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
    _log_ev(fb, b, cx, helpers, 'okeep', [('f', fb.get(ue, 'owner', 'kind')), ('n', fb.dyn(left)),
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
