"""Operations takeover, vanilla side (docs/OPERATIONS-IMPL.md Stage 2): vanilla launches no military operation.

- `ops-block`: checkOperations' tryLaunchOperation call -> wrapper: a held op outside OPS_VANILLA (Cell Search,
  Infiltration Cells, Assassination, Marauders Raid, CB_*: spying / politics, vanilla's) is never launched by
  vanilla (logs `opveto` f, op: what vanilla would have tried, once per held mission per OPV_LOG s; a vanilla op that
  launched logs `opvan` f, op). Every call of
  tryLaunchOperationFromOrder (order-phase launches) returns false the same way.
- `ops-strip`: tryArmyAction's addOrder call(s) -> wrapper: the order's mandatory (Raze -> Defense Breaches) and
  optional (per gauge kind) operation lists become empty for every target. Logs `opgate` (f, s, k siege action,
  n dropped) once per target per OPG_LOG s.
Our casts: rules/opsbrain.py (triggers), rules/sdrop.py (Supply Drop)."""
from rules.common import *  # noqa: F401,F403
from rules.opsbrain import OPS_VANILLA

OPG_LOG = 120  # s between `opgate` rows per target (a refused launch re-fires every 0.5 s)
OPV_LOG = 120  # s between `opveto` rows per held mission


def _vanilla_op(fb, b, mid, yes):
    """Jump to `yes` when mission id `mid` (String reg) stays vanilla's."""
    for v in OPS_VANILLA:
        fb.op('JEq', a=b.call('String.__compare', mid, fb.dyn(fb.string(v))), b=b.const('i32', 0), offset=yes)
    fb.op('JTrue', cond=b.call('$StringTools.startsWith', mid, fb.string('CB_')), offset=yes)


def build_ops_block(cx, helpers, new_ids):
    report = {}
    orig = cx.fn('logic.ai.Spying.tryLaunchOperation')
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    if len(args) != 2 or ft.ret.value != cx.t('bool') or args[1] != cx.t('logic.faction.Mission'):
        raise ValueError('ops-block: tryLaunchOperation(spying, mission) -> Bool expected')
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res, blk = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('Bool', dst=blk, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=1, offset='g_end')
    mid = b.field(1, 'id')
    fb.op('JNull', reg=mid, offset='g_end')
    _vanilla_op(fb, b, mid, 'g_end')
    fb.op('Bool', dst=blk, value=True)
    fac = b.field(0, 'f')
    fb.op('JNull', reg=fac, offset='g_end')
    _throttle(fb, b, cx, 'opveto', 1, OPV_LOG, 'g_end')
    _log_ev(fb, b, cx, helpers, 'opveto', [('f', fb.get(fac, 'kind')), ('op', mid)])
    fb.label('g_end')
    fb.end_try(guard)
    fb.op('JTrue', cond=blk, offset='no')
    fb.op('Call2', dst=res, fun=orig.findex.value, arg0=0, arg1=1)  # vanilla, outside any trap
    # a vanilla launch that went through (Cell Search during an assassination, ...): `opvan` f, op
    fb.op('JFalse', cond=res, offset='ret')
    g2 = fb.try_()
    vf = b.field(0, 'f')
    fb.op('JNull', reg=vf, offset='v_end')
    _log_ev(fb, b, cx, helpers, 'opvan', [('f', fb.get(vf, 'kind')), ('op', b.field(1, 'id'))])
    fb.label('v_end')
    fb.end_try(g2)
    fb.label('ret')
    fb.op('Ret', ret=res)
    fb.label('no')
    fb.op('Bool', dst=res, value=False)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    caller = cx.fn('logic.ai.Spying.checkOperations')
    sites = [op for op in caller.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == orig.findex.value]
    if len(sites) != 1:
        raise ValueError(f'ops-block: expected 1 tryLaunchOperation call in checkOperations, found {len(sites)}')
    sites[0].df['fun'].value = w
    report['ops-block'] = 1
    # order-phase launches: always false (the lists are empty anyway: ops-strip)
    orig2 = cx.fn('logic.ai.Spying.tryLaunchOperationFromOrder')
    ft2 = cx.code.types[orig2.type.value].definition
    fb = FB(cx, [a.value for a in ft2.args], ft2.ret.value, fun_type=orig2.type.value)
    r2 = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=r2, value=False)
    fb.op('Ret', ret=r2)
    w2 = fb.build()
    new_ids.add(w2)
    n = 0
    for f in cx.code.functions:
        if f.findex.value in new_ids:
            continue
        for op in f.ops:
            if op.op.startswith('Call') and op.df.get('fun') is not None and op.df['fun'].value == orig2.findex.value:
                op.df['fun'].value = w2
                n += 1
    report['ops-block:fromOrder'] = n
    return report


def build_ops_gate(cx, helpers, new_ids):
    add = cx.fn('logic.ai.AIOrders.addOrder')
    ids = {add.findex.value, helpers.get('addOrder', add.findex.value)}
    taa = cx.fn('logic.ai.AIMilitary.tryArmyAction')
    sites = [op for op in taa.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value in ids]
    if not sites:
        raise ValueError('ops-strip: no addOrder call in tryArmyAction')
    ft = cx.code.types[add.type.value].definition
    args = [a.value for a in ft.args]  # 0 AIOrders, 1 type, 2 prio, 3 armies, 4 target, 5 action, 6 siegeAction,
    #                                    7 mandatory, 8 optional, 9 data, 10 onComplete
    done = {}
    for site in sites:
        callee = site.df['fun'].value
        if callee in done:
            site.df['fun'].value = done[callee]
            continue
        fb = FB(cx, args, ft.ret.value, fun_type=add.type.value)
        b = B(fb)
        res = fb.reg(ft.ret.value)
        fb.op('Null', dst=res)
        guard = fb.try_()
        n = fb.reg(cx.t('i32'))
        fb.op('Mov', dst=n, src=b.const('i32', 0))
        for r in (7, 8):
            sk = _uid('st')
            fb.op('JNull', reg=r, offset=sk)
            fb.op('Add', dst=n, a=n, b=b.field(r, 'length'))
            fb.op('Mov', dst=r, src=_new_array(fb, b, cx))
            fb.label(sk)
        fb.op('JSLte', a=n, b=b.const('i32', 0), offset='end')
        fb.op('JNull', reg=4, offset='end')
        fac = b.field(b.field(0, 'controller'), 'owner')
        fb.op('JNull', reg=fac, offset='end')
        _throttle(fb, b, cx, 'opgl', 4, OPG_LOG, 'end')
        _log_ev(fb, b, cx, helpers, 'opgate', [('f', fb.get(fac, 'kind')), ('s', 4), ('k', 6), ('n', n)])
        fb.label('end')
        fb.end_try(guard)
        fb.op('CallN', dst=res, fun=callee, args=list(range(len(args))))
        fb.op('Ret', ret=res)
        w = fb.build()
        new_ids.add(w)
        done[callee] = w
        site.df['fun'].value = w
    return {'ops-strip': len(sites)}
