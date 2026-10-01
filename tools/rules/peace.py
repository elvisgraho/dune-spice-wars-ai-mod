"""Peace gate (AI-POLICY §3b, part 1): don't sell a winning siege for a peace treaty.

Vanilla accepts an offer from F by trade value alone (AIController.tradeRequestReceived; only desiredStatus 2 refuses
ImproveRelations), and every new Breakable treaty cancels each order targeting either party
(AIOrders.onEvent(OnNewTreaty)); at peace the siege can't go on anyway. So an enemy that is losing a village to our
Annex / Pillage can buy it back with a cheap offer mid-capture, and since `raid` pillages at-war owners' villages,
the victim is exactly the faction that offers.

Gate (wraps the single call site of tradeRequestReceived: the ai-log tracer when it traces it, else
AIController.callActionFunction): an offer whose sender is at war with us and that carries at least one treaty
(a pure resource trade creates none and cancels nothing) is refused (TradeManager.refuseTrade(sender), the vanilla
refusal) while one of our Military orders targets a structure of the sender in Engage or Action. Vanilla's fight
retreat cancels a siege that is losing (balance <= RETREAT), so an order still in Engage / Action is one we hold:
that stands for the policy's "local ratio >= keep" without another power query. Everything else, and any error,
goes to vanilla unchanged, and so does every offer while one of our structures is besieged (aimod_defend: the
DEFEND posture; peace may be what saves it, policy §3b "accept when losing"). Treaties are counted on both sides
of the deal (sendRes and receiveRes). Logs `peace` act=refuse with the sender and the protected target."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

ENGAGE = REGROUP + 1  # AIOrder.phase Engage; Action = ACTION


def build_peace_gate(cx, helpers, defend, new_ids):
    """Redirect the call site of AIController.tradeRequestReceived to the gate (see module doc)."""
    orig = cx.fn('logic.ai.AIController.tradeRequestReceived')
    tid = orig.findex.value
    args = [a.value for a in cx.code.types[orig.type.value].definition.args]
    ret_t = cx.code.types[orig.type.value].definition.ret.value
    fb = FB(cx, args, ret_t, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(ret_t)
    done = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=done, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    fac = b.field(0, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    # the offer: Type.enumParameters(alert.fkind)[0] = {sendRes: {object, treaties}, ...}
    params = b.call('$Type.enumParameters', b.field(1, 'fkind'))
    fb.op('JNull', reg=params, offset='end')
    fb.op('JSLte', a=b.call('hl.types.ArrayDyn.get_length', params), b=b.const('i32', 0), offset='end')
    trade = b.call('hl.types.ArrayDyn.getDyn', params, b.const('i32', 0))
    fb.op('JNull', reg=trade, offset='end')
    # treaties on either side of the deal (what F gives or asks for): any new treaty cancels our orders on F
    n, k = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Int', dst=n, ptr=cx.code.add_i32(0).value)
    for side in ('sendRes', 'receiveRes'):
        tl = fb.get(trade, side, 'treaties', 'length')
        skip = _uid('tl')
        fb.op('JNull', reg=tl, offset=skip)
        fb.op('SafeCast', dst=k, src=tl)
        fb.op('Add', dst=n, a=n, b=k)
        fb.label(skip)
    fb.op('JSLte', a=n, b=b.const('i32', 0), offset='end')
    so = fb.get(trade, 'sendRes', 'object')
    fb.op('JNull', reg=so, offset='end')
    fb.op('JFalse', cond=b.call('hl.BaseType.check', _faction_class(fb, cx), so), offset='end')
    sender = b.cast(so, 'ent.Faction')
    fb.op('JEq', a=sender, b=fac, offset='end')
    state = _state(fb, b, cx)
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, sender), offset='end')
    # defending (one of our structures besieged): peace may save it, vanilla decides (policy §3b: accept when losing)
    dfs = fb.reg(cx.t('ent.Structure'))
    fb.op('Call1', dst=dfs, fun=defend, arg0=fac)
    fb.op('JNotNull', reg=dfs, offset='end')
    # one of our Military orders on a structure of the sender, in Engage or Action
    orders = b.field(b.field(0, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    on = b.field(orders, 'length')
    i, idx, ph = (fb.reg(cx.t('i32')) for _ in range(3))
    fb.op('Int', dst=i, ptr=cx.code.add_i32(0).value)
    b.loop_head('ord')
    fb.op('JSGte', a=i, b=on, offset='end')
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, i), 'logic.ai.AIOrder')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=o, offset='ord')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='ord')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='ord')
    fb.op('EnumIndex', dst=idx, value=tt)
    fb.op('JNotEq', a=idx, b=b.const('i32', T_STRUCT), offset='ord')
    fb.op('Mov', dst=ph, src=b.field(o, 'phase'))
    fb.op('JSLt', a=ph, b=b.const('i32', ENGAGE), offset='ord')
    fb.op('JSGt', a=ph, b=b.const('i32', ACTION), offset='ord')
    s = b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'ent.Structure')
    fb.op('JNull', reg=s, offset='ord')
    fb.op('JNotEq', a=b.call('ent.Entity.get_owner', s), b=sender, offset='ord')
    # refuse the way vanilla does
    tm = b.field(fac, 'tradeManager')
    fb.op('JNull', reg=tm, offset='end')
    fb.op('Mov', dst=res, src=b.call('logic.TradeManager.refuseTrade', tm, sender))
    fb.op('Bool', dst=done, value=True)
    sa = fb.get(o, 'siegeAction')
    _log_ev(fb, b, cx, helpers, 'peace', [('f', fb.get(fac, 'kind')), ('act', 'refuse'), ('from', fb.get(sender, 'kind')),
                                          ('tgt', s), ('sa', sa), ('ph', ph), ('nt', n)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('JTrue', cond=done, offset='ret')
    fb.op('Call2', dst=res, fun=tid, arg0=0, arg1=1)
    fb.label('ret')
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    # the one call site, wherever it is (the ai-log tracer wraps callActionFunction's call when traced)
    sites = [(f, op) for f in cx.code.functions if f.findex.value != w for op in f.ops
             if op.op.startswith('Call') and op.df.get('fun') is not None and op.df['fun'].value == tid]
    if len(sites) != 1:
        raise ValueError(f'peace-gate: expected 1 tradeRequestReceived call site, found {len(sites)}')
    sites[0][1].df['fun'].value = w
    return {'peace-gate': 1}


def _faction_class(fb, cx):
    """The ent.Faction class object (global ent.$Faction), as vanilla passes it to hl.BaseType.check."""
    r = fb.reg(cx.t('ent.$Faction'))
    fb.op('GetGlobal', dst=r, **{'global': cx.global_of('ent.$Faction')})
    return r
