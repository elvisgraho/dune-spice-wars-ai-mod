"""World-event trips: `discovery-gate` (no lone trip into superior at-war armies or past the supply budget) and its
abort of a running trip once hostiles reaching it outmatch it."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def build_discovery(cx, helpers, threat, pw, terrain, land, supok, new_ids):
    """Discovery gate on the single addOrder call in AIController.checkWorldEvents. Vanilla sends its nearest idle
    army, alone, to a world event (ruins, black market, ...) up to one zone into anyone's land, with no threat check:
    lone armies wandered next to a rival's army blob and got picked off or dragged into sieges from there. Refused
    when the army has less than ENTER x the at-war threat at the event (aimod_threat within LOCAL, / terrain there),
    and for DISC_RETRY s after build_disc_abort gave the event up (map `dfail`), and for DISC_RELAUNCH s after a
    launch on the same event (map `dlaunch`: a re-pick means the trip ended at once; Fremen re-launched one on
    AbandonnedFremenCamp every 1.5-7 s for a minute, cancelled in Waiting each time).
    Also refused when the round trip doesn't fit the army's supply budget (aimod_supok(army, 2 x aimod_land(event))):
    vanilla picks events anywhere; Smugglers sent lone armies 1000-1160 from their land (CrashedShuttle, Hiereg,
    CrashedShip) every 1-2 min, each turned back by supply in Fremen land (log `dl` = the event's distance to our land).
    Refusal = no order (the result is unused; vanilla still stamps lastResolvedWorldEventTime and retries later).
    Logs `disc` (refusals only). Original call otherwise or on any error."""
    add = cx.fn('logic.ai.AIOrders.addOrder')
    orig = helpers.get('addOrder', add.findex.value)  # the logging wrapper when installed (same signature)
    ft = cx.code.types[add.type.value].definition
    args = [a.value for a in ft.args]
    fb = FB(cx, args, ft.ret.value, fun_type=add.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    blocked = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=blocked, value=False)
    h, m, tf, dl = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('Mov', dst=dl, src=b.const('f64', 0))
    tgt = fb.reg(cx.t('ent.Entity'))
    guard = fb.try_()
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='done')
    fb.op('JNull', reg=3, offset='done')
    fb.op('JNull', reg=4, offset='done')
    fb.op('Mov', dst=tgt, src=4)
    fb.op('JSLte', a=b.field(3, 'length'), b=b.const('i32', 0), offset='done')
    u = b.cast(b.call('hl.types.ArrayObj.getDyn', 3, b.const('i32', 0)), 'ent.Unit')
    fb.op('JNull', reg=u, offset='done')
    fb.op('Call3', dst=h, fun=threat, arg0=fac, arg1=tgt, arg2=b.const('f64', LOCAL))
    fb.op('Mov', dst=m, src=b.const('f64', 0))
    # given up recently (hostiles came): refused, logged with M 0
    m0 = fb.reg(cx.t('f64'))
    df = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'dfail'), fb.dyn(tgt))
    fb.op('JNull', reg=df, offset='dfresh')
    fb.op('SafeCast', dst=m0, src=df)
    fb.op('Sub', dst=m0, a=b.field(_state(fb, b, cx), 'time'), b=m0)
    fb.op('JSGte', a=m0, b=b.const('f64', DISC_RETRY), offset='dfresh')
    fb.op('Bool', dst=blocked, value=True)
    fb.op('JAlways', offset='done')
    fb.label('dfresh')
    # launched on this event less than DISC_RELAUNCH s ago: its trip ended at once (vanilla re-picks it every tick)
    dlv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'dlaunch'), fb.dyn(tgt))  # not `dl` (the f64 below)
    fb.op('JNull', reg=dlv, offset='dlok')
    fb.op('SafeCast', dst=m0, src=dlv)
    fb.op('Sub', dst=m0, a=b.field(_state(fb, b, cx), 'time'), b=m0)
    fb.op('JSGte', a=m0, b=b.const('f64', DISC_RELAUNCH), offset='dlok')
    fb.op('Bool', dst=blocked, value=True)
    fb.op('JAlways', offset='done')
    fb.label('dlok')
    # too far for the army's supply: out and back from our land (supply drains off our zones only)
    fb.op('Call2', dst=dl, fun=land, arg0=fac, arg1=tgt)
    ua = b.cast(u, 'ent.Army')
    fb.op('JNull', reg=ua, offset='dsup')
    fb.op('Add', dst=m0, a=dl, b=dl)
    sok = fb.reg(cx.t('bool'))
    fb.op('Call3', dst=sok, fun=supok, arg0=ua, arg1=m0, arg2=b.const('f64', 1))
    fb.op('JTrue', cond=sok, offset='dsup')
    fb.op('Bool', dst=blocked, value=True)
    fb.op('JAlways', offset='done')
    fb.label('dsup')
    fb.op('Mov', dst=dl, src=b.const('f64', 0))  # logged dl > 0 only for a FAR refusal
    fb.op('JSLte', a=h, b=b.const('f64', 0), offset='done')
    fb.op('Call1', dst=m, fun=pw, arg0=u)
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', tgt))
    need = fb.reg(cx.t('f64'))
    fb.op('Mul', dst=need, a=h, b=_ratio(fb, b, ENTER))
    fb.op('SDiv', dst=need, a=need, b=tf)
    fb.op('JSGte', a=m, b=need, offset='done')
    fb.op('Bool', dst=blocked, value=True)
    fb.label('done')
    fb.end_try(guard)
    fb.op('JTrue', cond=blocked, offset='block')
    g3 = fb.try_()
    fb.op('JNull', reg=4, offset='nodl')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'dlaunch'), fb.dyn(tgt), fb.dyn(b.field(_state(fb, b, cx), 'time')))
    fb.label('nodl')
    fb.end_try(g3)
    fb.op('CallN', dst=res, fun=orig, args=list(range(len(args))))
    fb.op('Ret', ret=res)
    fb.label('block')
    guard2 = fb.try_()
    owner = b.field(b.field(0, 'controller'), 'owner')
    ue = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ue, src=u)
    _throttle(fb, b, cx, 'discx', tgt, 30, 'dnolog')  # re-asked every 1-2 s for the same event: once per 30 s
    _log_ev(fb, b, cx, helpers, 'disc', [('f', fb.get(owner, 'kind')), ('tgt', tgt), ('army', ue), ('H', h),
                                         ('M', m), ('tf%', tf), ('dl', dl)])
    fb.label('dnolog')
    fb.end_try(guard2)
    fb.op('Null', dst=res)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    caller = cx.fn('logic.ai.AIController.checkWorldEvents')
    sites = [op for op in caller.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == orig]
    if len(sites) != 1:
        raise ValueError(f'discovery-gate: expected 1 addOrder call in checkWorldEvents, found {len(sites)}')
    sites[0].df['fun'].value = w
    return 1


def build_disc_abort(cx, helpers, pw, threat_far, terrain):
    """aimod_discabort(mil, dt), every CHECK s: retreat from a world event. A running Discovery order of ours (a lone
    army walking to or investigating an event) is cancelled when its armies have less than ENTER x the hostile power
    at the event / terrain there, counting movers that can arrive within DISC_HORIZON (aimod_threat with that
    horizon; the launch gate looks HORIZON ahead). Vanilla never re-checks: a Harkonnen H_Soldier kept investigating a
    relic while 8 Smugglers armies walked 290 units straight at it and only left in contact (1v8, dead). The event
    goes into `dfail` (the gate refuses it for DISC_RETRY s: no launch / abort loop). The army is then in no order:
    `strand` patrols it home on its next pass (an idle army on hostile / neutral land), the fight retreat handles a
    contact. Logs `disc` act=abort. In a trap: nothing on error."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = b.field(_state(fb, b, cx), 'time')
    _tick(fb, b, cx, t, CHECK, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    zi, one, zero = b.const('i32', 0), b.const('i32', 1), b.const('f64', 0)
    enter = _ratio(fb, b, ENTER)
    i, j, idx = (fb.reg(cx.t('i32')) for _ in range(3))
    h, m, p, q, tf = (fb.reg(cx.t('f64')) for _ in range(5))
    ve = fb.reg(cx.t('ent.Entity'))
    reason = cx.code.types[cx.fn('logic.ai.AIOrder.stop').type.value].definition.args[1].value
    cancel = fb.reg(reason)
    fb.op('MakeEnum', dst=cancel, construct=CANCEL, args=[])
    fb.op('Mov', dst=i, src=b.field(orders, 'length'))
    b.loop_head('ord')  # backwards: stop() removes the order from the list
    fb.op('JSLte', a=i, b=zi, offset='end')
    fb.op('Sub', dst=i, a=i, b=one)
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, i), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset='ord')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', DISCOVERY), offset='ord')
    fb.op('Mov', dst=ve, src=b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'ent.Entity'))
    fb.op('JNull', reg=ve, offset='ord')
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='ord')
    un = b.field(units, 'length')
    fb.op('Mov', dst=m, src=zero)
    u = _army_loop(fb, b, units, un, j, 'u', 'udone')
    fb.op('Call1', dst=p, fun=pw, arg0=u)
    fb.op('Add', dst=m, a=m, b=p)
    fb.op('JAlways', offset='u')
    fb.label('udone')
    fb.op('JSLte', a=m, b=zero, offset='ord')
    fb.op('Call3', dst=h, fun=threat_far, arg0=fac, arg1=ve, arg2=b.const('f64', LOCAL))
    fb.op('JSLte', a=h, b=zero, offset='ord')
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', ve))
    fb.op('Mul', dst=q, a=h, b=enter)
    fb.op('SDiv', dst=q, a=q, b=tf)
    fb.op('JSGte', a=m, b=q, offset='ord')
    b.call('logic.ai.AIOrder.stop', o, cancel)
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'dfail'), fb.dyn(ve), fb.dyn(t))
    _log_ev(fb, b, cx, helpers, 'disc', [('f', fb.get(fac, 'kind')), ('act', 'abort'), ('tgt', ve), ('H', h),
                                         ('M', m), ('tf%', tf), ('n', un)])
    fb.op('JAlways', offset='ord')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
