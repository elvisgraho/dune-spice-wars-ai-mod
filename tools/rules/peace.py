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


def build_treaty_scope(cx, helpers, new_ids):
    """Treaty scope (vanilla bug fix): AIOrders.onEvent(OnNewTreaty(tk, f1, f2)) cancels every order of ours whose
    targetFaction is f1 or f2 without checking that we are a party, and when we are one it also cancels our own
    Resupply / Patrol orders (targetFaction = us). Atreides' Liberate of Smugglers' Tsimrekh, in Action at en -59%,
    was cancelled by a Harkonnen-Smugglers treaty (25:58). The wrapper (installed through AIOrders' proto entry:
    onEvent has no direct call sites) passes a treaty we are not party to nowhere, and narrows one we are party to
    to the other side: OnNewTreaty(tk, other, other). Other events and any error go to vanilla unchanged.
    Logs `treaty` (f, act skip | narrow, a / b the parties)."""
    orig = cx.fn('logic.ai.AIOrders.onEvent')
    oid = orig.findex.value
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    ev_t = cx.code.types[args[1]].definition
    names = [c.name.resolve(cx.code) for c in ev_t.constructs]
    new_treaty = names.index('OnNewTreaty')
    ptypes = [p.value for p in ev_t.constructs[new_treaty].params]
    if len(ptypes) != 3 or ptypes[1] != cx.t('ent.Faction') or ptypes[2] != cx.t('ent.Faction'):
        raise ValueError('treaty-scope: OnNewTreaty(String, Faction, Faction) expected')
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    void = fb.reg(ft.ret.value)
    ev = fb.reg(args[1])
    fb.op('Mov', dst=ev, src=1)
    skip = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=skip, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=1, offset='end')
    idx = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=idx, value=1)
    fb.op('JNotEq', a=idx, b=b.const('i32', new_treaty), offset='end')
    tk, f1, f2 = fb.reg(ptypes[0]), fb.reg(ptypes[1]), fb.reg(ptypes[2])
    for n, r in enumerate((tk, f1, f2)):
        fb.op('EnumField', dst=r, value=1, construct=new_treaty, field=n)
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    other = fb.reg(cx.t('ent.Faction'))
    fb.op('JEq', a=fac, b=f1, offset='p1')
    fb.op('JEq', a=fac, b=f2, offset='p2')
    fb.op('Bool', dst=skip, value=True)
    _log_ev(fb, b, cx, helpers, 'treaty', [('f', fb.get(fac, 'kind')), ('act', 'skip'), ('a', fb.get(f1, 'kind')),
                                           ('b', fb.get(f2, 'kind'))])
    fb.op('JAlways', offset='end')
    fb.label('p1')
    fb.op('Mov', dst=other, src=f2)
    fb.op('JAlways', offset='narrow')
    fb.label('p2')
    fb.op('Mov', dst=other, src=f1)
    fb.label('narrow')
    fb.op('JNull', reg=other, offset='end')
    fb.op('MakeEnum', dst=ev, construct=new_treaty, args=[tk, other, other])
    _log_ev(fb, b, cx, helpers, 'treaty', [('f', fb.get(fac, 'kind')), ('act', 'narrow'), ('a', fb.get(other, 'kind'))])
    fb.label('end')
    fb.end_try(guard)
    fb.op('JTrue', cond=skip, offset='ret')
    fb.op('Call2', dst=void, fun=oid, arg0=0, arg1=ev)
    fb.label('ret')
    fb.op('Ret', ret=void)
    w = fb.build()
    new_ids.add(w)
    protos = [p for p in cx.code.types[cx.t('logic.ai.AIOrders')].definition.protos
              if p.name.resolve(cx.code) == 'onEvent']
    if len(protos) != 1 or protos[0].findex.value != oid:
        raise ValueError('treaty-scope: AIOrders proto onEvent not found')
    protos[0].findex.value = w
    return {'treaty-scope': 1}


def _faction_class(fb, cx):
    """The ent.Faction class object (global ent.$Faction), as vanilla passes it to hl.BaseType.check."""
    r = fb.reg(cx.t('ent.$Faction'))
    fb.op('GetGlobal', dst=r, **{'global': cx.global_of('ent.$Faction')})
    return r


def build_force_peace(cx, helpers):
    """aimod_fpeace(mil, dt): a faction that can impose a Non-aggression Pact (attribute Allow_PeaceForce: Atreides,
    Lady Jessica) uses it as a last-resort defense. Every START s: one of our structures on our land is besieged by
    an at-war faction F and we gave its defense up (map `dhl`: aimod_defend judged it hopeless < 30 s ago, or `rlygu`:
    the rally conceded it < RALLY_COOL ago), F isn't in FP_SKIP (Fremen break treaties at no cost) -> a trade with
    treaty ImproveRelations is sent with ProposeStyle ForcePeace (TradeManager: checkStartTrade, startTrade,
    addTreaty, sendTrade). Vanilla charges the Influence force cost, checks the attribute and the war grace period,
    and confirms it at once (`proposeTrade`); the treaty is Breakable, so both sides' orders on each other end
    (treaty-scope). Never without an attack on us. At most one try per FP_RETRY s per faction; a refused send is
    reset (resetTrade). The vanilla AI never forces treaties (its `nextPossibleForceTreaty` is never read).
    Logs `fpeace` (f, to, s, r = EReason index, 1 Success). Fails safe: in a trap."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    state = _state(fb, b, cx)
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(state, 'time'))
    _tick(fb, b, cx, t, START, 'end')
    ha = cx.fn('ent.Object.hasAttribute')
    hat = [a.value for a in cx.code.types[ha.type.value].definition.args]
    n2, n3 = fb.reg(hat[2]), fb.reg(hat[3])
    fb.op('Null', dst=n2)
    fb.op('Null', dst=n3)
    fo = fb.reg(hat[0])
    fb.op('Mov', dst=fo, src=fac)
    has = fb.reg(cx.t('bool'))
    fb.op('Call4', dst=has, fun=ha.findex.value, arg0=fo, arg1=b.const('i32', ATTR_PEACE_FORCE), arg2=n2, arg3=n3)
    fb.op('JFalse', cond=has, offset='end')
    sts = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=sts, offset='end')
    k = fb.reg(cx.t('i32'))
    q = fb.reg(cx.t('f64'))
    s = fb.reg(cx.t('ent.Structure'))
    bf = fb.reg(cx.t('ent.Faction'))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head('sl')
    fb.op('JSGte', a=k, b=b.field(sts, 'length'), offset='end')
    fb.op('Mov', dst=s, src=b.cast(b.call('hl.types.ArrayObj.getDyn', sts, k), 'ent.Structure'))
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=s, offset='sl')
    z = b.call('ent.Entity.get_zone', s)
    fb.op('JNull', reg=z, offset='sl')
    fb.op('JNotEq', a=b.field(z, 'owner'), b=fac, offset='sl')
    sg = b.field(s, 'siege')
    fb.op('JNull', reg=sg, offset='sl')
    fb.op('Mov', dst=bf, src=b.field(sg, 'besiegingFaction'))
    fb.op('JNull', reg=bf, offset='sl')
    fb.op('JEq', a=bf, b=fac, offset='sl')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, bf), offset='sl')
    for name in FP_SKIP:
        fb.op('JEq', a=b.call('String.__compare', b.field(bf, 'kind'), fb.dyn(fb.string(name))),
              b=b.const('i32', 0), offset='sl')
    for mname, lim in (('dhl', 30), ('rlygu', RALLY_COOL)):
        nx = _uid('fpn')
        mv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, mname), fb.dyn(s))
        fb.op('JNull', reg=mv, offset=nx)
        fb.op('SafeCast', dst=q, src=mv)
        fb.op('Sub', dst=q, a=t, b=q)
        fb.op('JSLt', a=q, b=b.const('f64', lim), offset='lost')
        fb.label(nx)
    fb.op('JAlways', offset='sl')
    fb.label('lost')
    _throttle(fb, b, cx, 'fpeace', fac, FP_RETRY, 'end')
    tm = b.field(fac, 'tradeManager')
    fb.op('JNull', reg=tm, offset='end')
    bo = fb.reg(cx.t('ent.Object'))
    fb.op('Mov', dst=bo, src=bf)
    r = b.call('logic.TradeManager.checkStartTrade', tm, bo)
    ri = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ri, value=r)
    succ = _enum_index(cx, cx.code.types[cx.fn('logic.TradeManager.sendTrade').type.value].definition.ret.value,
                       'Success')
    fb.op('JNotEq', a=ri, b=b.const('i32', succ), offset='log')
    b.call('logic.TradeManager.startTrade', tm, bo)
    trade = b.field(tm, 'activeTrade')
    fb.op('JNull', reg=trade, offset='end')
    b.call('logic.TradeManager.addTreaty', tm, fb.string('ImproveRelations'), fac)
    st = cx.fn('logic.TradeManager.sendTrade')
    style_t = cx.code.types[st.type.value].definition.args[2].value
    style = fb.reg(style_t)
    fb.op('MakeEnum', dst=style, construct=_enum_index(cx, style_t, 'ForcePeace'), args=[])
    r2 = b.call('logic.TradeManager.sendTrade', tm, trade, style)
    fb.op('EnumIndex', dst=ri, value=r2)
    fb.op('JEq', a=ri, b=b.const('i32', succ), offset='log')
    b.call('logic.TradeManager.resetTrade', tm, trade)
    fb.label('log')
    _log_ev(fb, b, cx, helpers, 'fpeace', [('f', fb.get(fac, 'kind')), ('to', fb.get(bf, 'kind')), ('s', s),
                                           ('r', ri)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


def _enum_index(cx, t, name):
    names = [c.name.resolve(cx.code) for c in cx.code.types[t].definition.constructs]
    if name not in names:
        raise ValueError(f'force-peace: enum construct {name} not found')
    return names.index(name)
