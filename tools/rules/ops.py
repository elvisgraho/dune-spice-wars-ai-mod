"""Operations gate on plain captures (AI-POLICY "Operations").

Why: vanilla `tryArmyAction` hands every siege order the optional operations of its gauge kind
(`AIMilitary.getActionOptionalMissions`: Annexation {MAwakePeople, MInterdictionZone, MCommunicationJamming},
Pillage {MScavengerTeam, MDecoyThumper}, ...), and the order phases launch any we hold. On a neutral village
(no owner: a plain capture or pillage against militia only) that burns Intel / Solari and a held op that would
swing a fight later: Fremen spent one on a neutral village capture.

- `ops-gate`: tryArmyAction's addOrder call(s) -> wrapper: target an `ent.Entity` with no owner (neutral village,
  sietch, renegade base) -> the optional missions become an empty list; mandatory missions (Raze only) are kept.
  Logs `opgate` (f, s, k siege action, n dropped) once per target per OPG_LOG s. Supply Drop is not on these lists:
  `sdrop` (rules/sdrop.py) decides it alone.
"""
from rules.common import *  # noqa: F401,F403

OPG_LOG = 120  # s between `opgate` rows per target (a refused launch re-fires every 0.5 s)


def build_ops_gate(cx, helpers, new_ids):
    add = cx.fn('logic.ai.AIOrders.addOrder')
    ids = {add.findex.value, helpers.get('addOrder', add.findex.value)}
    taa = cx.fn('logic.ai.AIMilitary.tryArmyAction')
    sites = [op for op in taa.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value in ids]
    if not sites:
        raise ValueError('ops-gate: no addOrder call in tryArmyAction')
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
        fb.op('JNull', reg=4, offset='end')
        fb.op('JNull', reg=8, offset='end')
        n = b.field(8, 'length')
        fb.op('JSLte', a=n, b=b.const('i32', 0), offset='end')
        fb.op('JNotNull', reg=b.call('ent.Entity.get_owner', 4), offset='end')  # owned: a real fight, ops may pay
        fb.op('Mov', dst=8, src=_new_array(fb, b, cx))
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
    return {'ops-gate': len(sites)}
