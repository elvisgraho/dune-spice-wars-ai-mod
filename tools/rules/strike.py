"""En-route strike (AI-POLICY §4 re-decide on contact): our siege armies on the march fight an at-war army that comes
within their reach, like a turret, when the local balance is at least even; then they march on.

The failure: Smugglers' Liberate of Pel-ur (8 armies, ~357k, Engage 45:40-47:29) walked past two Harkonnen units
(Discovery_Marauder 40k + Discovery_Sniper 23k) at 10-125 for 20 s and nobody fired: vanilla micro only acts on
existing warzones and an army walking under a Move never starts one; hunts take free armies only (taking one army
from an order before Action cancels the whole order).

Tick (every STRIKE_T s per faction), pass 2: our Military orders on a structure in Regroup / Engage. An order army not
striking: the nearest visible army of a faction at war with us (neutral raiders / militia ignored: they may be on
their way to someone else) within STRIKE_R (turret range + a little) and no farther from the order's target than our army (+ STRIKE_R / 2: on
the way, not a chase) starts a strike when the order's armies within STRIKE_JOIN_R (2 x STRIKE_R: the ones that can reach it; user, per army) of it
>= STRIKE_RATIO x (aimod_threat(fac, it, LOCAL) + enemy cover there). Only armed targets (aimod_pw > 0, no
harvester: Harkonnen sent 14 of 15 Annex armies at a Fremen harvester with Fremen armies near it). Order armies within
STRIKE_JOIN_R of it join nearest first until their power >= STRIKE_TO x that side; each gets doAction("ArmyFight",
EEntity(it)) (vanilla micro's attack call) without leaving the order (maps `strk`
army -> last refresh, `strt` -> target, `strs` -> start time, `strx` / `stry` -> start position).
Pass 1 re-judges every striking army of ours (map `stro` army -> its order), also one whose order ended: it ends
(log `strike` act end, why) when it left its order or the order ended / went past Action (`order`: no endless
chase), the target is dead or no longer at war (`done`), STRIKE_MAX s passed while not fighting (`time`: a fight under way is vanilla micro's), the army is
STRIKE_LEASH from where it started or the target 2 x STRIKE_R from it (`ran`: no chase across the map), or the
balance there fell below STRIKE_END_K x STRIKE_RATIO (`weak`; start at STRIKE_RATIO: hysteresis). Ending stops the army (Move to its own position: idle, so vanilla
re-sends the march at once), except a `done` / `time` / `weak` end of an army still fighting: that fight stays
vanilla micro's (its fight retreat judges it) and the march resumes after it; `ran` always stops it. While a strike is fresh (aimod_striking: refreshed within 2 x STRIKE_T) vanilla's march calls
(the doAction of checkRegroupOrder / checkEngageOrder) and our gather / stage / desert-step / spos moves skip the
army; an
army knocked off its target meanwhile is sent at it again. Logs `strike` act start (a, e, M, H, d, n) and end."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.worm import _move_to, _do_on


def build_striking(cx):
    """aimod_striking(a) -> bool: army a's strike was refreshed within 2 x STRIKE_T (map `strk`)."""
    fb = FB(cx, [cx.t('ent.Entity')], cx.t('bool'))
    b = B(fb)
    ok = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=ok, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    v = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'strk'), fb.dyn(0))
    fb.op('JNull', reg=v, offset='end')
    q = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=q, src=v)
    fb.op('Sub', dst=q, a=b.field(_state(fb, b, cx), 'time'), b=q)
    fb.op('JSGt', a=q, b=b.const('f64', 2 * STRIKE_T), offset='end')
    fb.op('Bool', dst=ok, value=True)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=ok)
    return fb.build()


def strike_skip(cx, new_ids, striking, wormheld):
    """The doAction call of checkRegroupOrder and of checkEngageOrder (one each) -> wrapper: null (nothing done) for
    a striking army or one waiting on rock after a worm flee (aimod_wormonly: a siege army keeps its order before
    Action, and vanilla's march would walk it straight back onto the sand while the worm is near); the original call
    otherwise. Safe in Regroup: its stall cancel (no path progress for AI_Army_StuckTime 5 s, more than
    AI_Army_StuckCancelDistance 20 left) only applies while `u.movementMode != null` (a unit trying to move); a held
    army stands idle. The `worm` flag per site stays for tuning."""
    da = cx.fn('ent.Entity.doAction')
    ft = cx.code.types[da.type.value].definition

    def wrapper(worm):
        fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=da.type.value)
        b = B(fb)
        res = fb.reg(ft.ret.value)
        st = fb.reg(cx.t('bool'))
        e = fb.reg(cx.t('ent.Entity'))
        fb.op('Mov', dst=e, src=0)
        fb.op('Call1', dst=st, fun=striking, arg0=e)
        if worm:
            fb.op('JTrue', cond=st, offset='skip')
            fb.op('Call1', dst=st, fun=wormheld, arg0=e)
        fb.op('JFalse', cond=st, offset='go')
        fb.label('skip')
        fb.op('Null', dst=res)  # Null<Bool>: nothing done (both callers ignore the result)
        fb.op('Ret', ret=res)
        fb.label('go')
        fb.op('Call4', dst=res, fun=da.findex.value, arg0=0, arg1=1, arg2=2, arg3=3)
        fb.op('Ret', ret=res)
        w = fb.build()
        new_ids.add(w)
        return w

    for name, worm in (('logic.ai.AIOrders.checkRegroupOrder', True), ('logic.ai.AIOrders.checkEngageOrder', True)):
        fn = cx.fn(name)
        sites = [op for op in fn.ops if op.op.startswith('Call') and op.df.get('fun') is not None
                 and op.df['fun'].value == da.findex.value]
        if len(sites) != 1:
            raise ValueError(f'strike: expected 1 doAction call in {name}, found {len(sites)}')
        sites[0].df['fun'].value = wrapper(worm)
    return {'strike-skip': 1}


def build_strike(cx, helpers, pw, threat, cover, striking):
    """aimod_strike(mil, dt) (see module doc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    state = _state(fb, b, cx)
    t = b.field(state, 'time')
    _tick(fb, b, cx, t, STRIKE_T, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    armies = b.field(state, 'armies')
    fb.op('JNull', reg=armies, offset='end')
    my_armies, mlen = _my_armies(fb, b, fac, 'end')
    strk, strt, strs, stro = (_global_map(fb, b, cx, n) for n in ('strk', 'strt', 'strs', 'stro'))
    strx, stry = _global_map(fb, b, cx, 'strx'), _global_map(fb, b, cx, 'stry')
    zi = b.const('i32', 0)
    zero = b.const('f64', 0)
    i, j, k, idx, n = (fb.reg(cx.t('i32')) for _ in range(5))
    d, dn, m, h, q, sx, sy = (fb.reg(cx.t('f64')) for _ in range(7))
    st, mv = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    e, ae, ee = fb.reg(cx.t('ent.Army')), fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    o = fb.reg(cx.t('logic.ai.AIOrder'))
    units = fb.reg(cx.t('hl.types.ArrayObj'))
    un = fb.reg(cx.t('i32'))
    why = fb.reg(cx.t('String'))
    ne = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=ne)
    na = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=na)
    t_false = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_false, value=False)
    local = b.const('f64', LOCAL)
    jr = b.const('f64', STRIKE_JOIN_R)

    def balance(tgt, lbl):
        """m = power of the order's armies (units / un) within STRIKE_JOIN_R of tgt (the ones a strike may send: user,
        judged per army; rear armies 220 back turned to a target that ran 2 s later at Sad-po); h = STRIKE_RATIO x (at-war armies
        within LOCAL of it + enemy cover there)."""
        fb.op('Mov', dst=m, src=zero)
        y = _army_loop(fb, b, units, un, k, lbl, lbl + 'd')
        fb.op('JSGt', a=b.call('ent.Entity.getDistTo', y, tgt), b=jr, offset=lbl)
        fb.op('Call1', dst=q, fun=pw, arg0=y)
        fb.op('Add', dst=m, a=m, b=q)
        fb.op('JAlways', offset=lbl)
        fb.label(lbl + 'd')
        fb.op('Call3', dst=h, fun=threat, arg0=fac, arg1=tgt, arg2=local)
        fb.op('CallN', dst=q, fun=cover, args=[fac, tgt, ne, t_false, na])
        fb.op('Add', dst=h, a=h, b=q)
        fb.op('Mul', dst=h, a=h, b=_ratio(fb, b, STRIKE_RATIO))

    def marching(lbl_no):
        """Fall through when order o is one of our Military orders on a structure in Regroup / Engage."""
        fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
        fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset=lbl_no)
        tt = b.field(o, 'targetType')
        fb.op('JNull', reg=tt, offset=lbl_no)
        fb.op('EnumIndex', dst=idx, value=tt)
        fb.op('JNotEq', a=idx, b=b.const('i32', T_STRUCT), offset=lbl_no)
        ph = b.field(o, 'phase')
        fb.op('JSLt', a=ph, b=b.const('i32', REGROUP), offset=lbl_no)
        fb.op('JSGt', a=ph, b=b.const('i32', REGROUP + 1), offset=lbl_no)

    # ---- pass 1: every striking army of ours is re-judged (also one whose order ended meanwhile: no endless chase)
    a = _army_loop(fb, b, my_armies, mlen, j, 'r', 'rdone')
    fb.op('Mov', dst=ae, src=a)
    fb.op('JNull', reg=b.call('haxe.ds.ObjectMap.get', strk, fb.dyn(a)), offset='r')
    fb.op('Bool', dst=mv, value=False)
    # its order: still ours, still has it, and still marching or capturing (a strike that ran into Action stays)
    fb.op('Mov', dst=why, src=fb.string('order'))
    fb.op('Mov', dst=o, src=b.cast(b.call('haxe.ds.ObjectMap.get', stro, fb.dyn(a)), 'logic.ai.AIOrder'))
    fb.op('JNull', reg=o, offset='stop')
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', orders, fb.dyn(o)), offset='stop')
    fb.op('Mov', dst=units, src=b.field(o, 'units'))
    fb.op('JNull', reg=units, offset='stop')
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', units, fb.dyn(a)), offset='stop')
    fb.op('JSGt', a=b.field(o, 'phase'), b=b.const('i32', ACTION), offset='stop')
    fb.op('Mov', dst=un, src=b.field(units, 'length'))
    fb.op('Mov', dst=why, src=fb.string('done'))
    tv = b.call('haxe.ds.ObjectMap.get', strt, fb.dyn(a))
    fb.op('JNull', reg=tv, offset='stop')
    fb.op('Mov', dst=e, src=b.cast(tv, 'ent.Army'))
    fb.op('JNull', reg=e, offset='stop')
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', e), offset='stop')
    eo = b.call('ent.Entity.get_owner', e)
    fb.op('JNull', reg=eo, offset='stop')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, eo), offset='stop')
    fb.op('Mov', dst=why, src=fb.string('ran'))  # fog: out of sight is gone for us
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', e, fac), offset='stop')
    # time: only while not in the fight itself (a fight under way is vanilla micro's, its retreat judges it)
    fb.op('Mov', dst=why, src=fb.string('time'))
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', ae), offset='ntime')
    fb.op('SafeCast', dst=q, src=b.call('haxe.ds.ObjectMap.get', strs, fb.dyn(a)))
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSGt', a=q, b=b.const('f64', STRIKE_MAX), offset='stop')
    fb.label('ntime')
    # ran: we were led STRIKE_LEASH from where we started, or it got 2 x STRIKE_R away
    fb.op('Mov', dst=why, src=fb.string('ran'))
    fb.op('Bool', dst=mv, value=True)  # a chase is broken off even mid-fight
    fb.op('SafeCast', dst=sx, src=b.call('haxe.ds.ObjectMap.get', strx, fb.dyn(a)))
    fb.op('SafeCast', dst=sy, src=b.call('haxe.ds.ObjectMap.get', stry, fb.dyn(a)))
    fb.op('Sub', dst=sx, a=b.field(a, 'posx'), b=sx)
    fb.op('Sub', dst=sy, a=b.field(a, 'posy'), b=sy)
    fb.op('Mul', dst=sx, a=sx, b=sx)
    fb.op('Mul', dst=sy, a=sy, b=sy)
    fb.op('Add', dst=sx, a=sx, b=sy)
    fb.op('JSGt', a=sx, b=b.const('f64', STRIKE_LEASH * STRIKE_LEASH), offset='stop')
    fb.op('Mov', dst=ee, src=e)
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', ae, ee))
    fb.op('JSGt', a=d, b=b.const('f64', 2 * STRIKE_R), offset='stop')
    fb.op('Bool', dst=mv, value=False)
    fb.op('Mov', dst=why, src=fb.string('weak'))
    balance(ee, 'kb')
    # hysteresis: a running strike ends below STRIKE_END_K x the start test (start and end at the same 1.0 flipped
    # every 2-4 s at 666k vs 630-660k: Fremen's 11 armies re-sent 6 times in 25 s, match 2026-10-05 02:50)
    fb.op('Mul', dst=h, a=h, b=_ratio(fb, b, STRIKE_END_K))
    fb.op('JSLt', a=m, b=h, offset='stop')
    # keep: refresh, and send it at the target again if something else took it off
    b.call('haxe.ds.ObjectMap.set', strk, fb.dyn(a), fb.dyn(t))
    fb.op('JEq', a=b.call('ent.Entity.getFightingTarget', ae), b=ee, offset='r')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', ae), offset='r')
    _do_on(fb, b, cx, ae, 'ArmyFight', ee, fac)
    fb.op('JAlways', offset='r')
    fb.label('stop')
    for mp in (strk, strt, strs, stro, strx, stry):
        b.call('haxe.ds.ObjectMap.remove', mp, fb.dyn(a))
    # stop it (idle: vanilla re-sends the march, or gives it new work) unless it is fighting and wasn't leashed: then
    # the fight is vanilla micro's (other enemies there, or the fight retreat), and the march resumes when it ends
    fb.op('JTrue', cond=mv, offset='smv')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', ae), offset='slog')
    fb.label('smv')
    _move_to(fb, b, cx, a, b.field(a, 'posx'), b.field(a, 'posy'), fac)
    fb.label('slog')
    _log_ev(fb, b, cx, helpers, 'strike', [('f', fb.get(fac, 'kind')), ('act', 'end'), ('why', why), ('a', a)])
    fb.op('JAlways', offset='r')
    fb.label('rdone')

    # ---- pass 2: order armies on the march, not striking: the nearest visible at-war army within STRIKE_R
    fb.op('Mov', dst=i, src=b.field(orders, 'length'))
    b.loop_head('o')
    fb.op('JSLte', a=i, b=zi, offset='end')
    fb.op('Sub', dst=i, a=i, b=b.const('i32', 1))
    fb.op('Mov', dst=o, src=b.cast(b.call('hl.types.ArrayObj.getDyn', orders, i), 'logic.ai.AIOrder'))
    fb.op('JNull', reg=o, offset='o')
    marching('o')
    fb.op('Mov', dst=units, src=b.field(o, 'units'))
    fb.op('JNull', reg=units, offset='o')
    fb.op('Mov', dst=un, src=b.field(units, 'length'))
    a2 = _army_loop(fb, b, units, un, j, 'u', 'o')
    fb.op('JNotNull', reg=b.field(a2, 'harvestComponent'), offset='u')
    fb.op('Mov', dst=ae, src=a2)
    fb.op('Call1', dst=st, fun=striking, arg0=ae)
    fb.op('JTrue', cond=st, offset='u')
    fb.op('Null', dst=e)
    fb.op('Mov', dst=dn, src=b.const('f64', STRIKE_R))
    # the order's target and this army's distance to it: only an enemy no farther from it than we are (+ STRIKE_R /
    # 2) is on the way; one off to the side or behind is a chase (Fremen's 14-army Annex of Harrekh 13:18-14:55:
    # strike after strike on Harkonnen armies falling back to Carthag drew the stack ~250 east under its main base
    # and 12 armies died)
    otg = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=otg, src=b.call('logic.ai.AIOrder.getTarget', o))
    fb.op('JNull', reg=otg, offset='u')
    dme = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=dme, src=b.call('ent.Entity.getDistTo', ae, otg))
    fb.op('Add', dst=dme, a=dme, b=b.const('f64', STRIKE_R // 2))
    x = _army_loop(fb, b, armies, b.field(armies, 'length'), n, 'x', 'xd')
    xo = b.call('ent.Entity.get_owner', x)
    fb.op('JNull', reg=xo, offset='x')  # neutral raiders: maybe on their way to someone else
    fb.op('JEq', a=xo, b=fac, offset='x')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', x, ae))
    fb.op('JSGt', a=d, b=dn, offset='x')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, xo), offset='x')
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', x, fac), offset='x')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', x, otg), b=dme, offset='x')  # not on the way: a chase
    # armed armies only: a harvester (or anything powerless) can't hurt the march; Harkonnen's 15-army Annex of
    # Ulrekh sent 14 armies at a Fremen harvester because Fremen armies stood within LOCAL of it (H 275k)
    fb.op('JNotNull', reg=b.field(x, 'harvestComponent'), offset='x')
    fb.op('Call1', dst=q, fun=pw, arg0=x)
    fb.op('JSLte', a=q, b=zero, offset='x')
    fb.op('Mov', dst=dn, src=d)
    fb.op('Mov', dst=e, src=x)
    fb.op('JAlways', offset='x')
    fb.label('xd')
    fb.op('JNull', reg=e, offset='u')
    fb.op('Mov', dst=ee, src=e)
    balance(ee, 'sb')
    fb.op('JSLte', a=h, b=zero, offset='u')  # nothing armed there
    fb.op('JSLt', a=m, b=h, offset='u')
    # start: order armies within STRIKE_JOIN_R of it that aren't striking yet, nearest first, until STRIKE_TO x its side
    need, sent, bd = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mul', dst=need, a=h, b=_ratio(fb, b, STRIKE_TO))
    fb.op('Mov', dst=sent, src=zero)
    fb.op('Mov', dst=n, src=zi)
    best = fb.reg(cx.t('ent.Army'))
    ye = fb.reg(cx.t('ent.Entity'))
    fb.label('gp')
    fb.op('JSLte', a=n, b=zi, offset='gpick')
    fb.op('JSGte', a=sent, b=need, offset='gd')
    fb.label('gpick')
    fb.op('Null', dst=best)
    fb.op('Mov', dst=bd, src=jr)  # only armies that can reach it before it gets away (STRIKE_JOIN_R)
    y = _army_loop(fb, b, units, un, k, 'g', 'gsel')
    fb.op('JNotNull', reg=b.field(y, 'harvestComponent'), offset='g')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', y, ee))
    fb.op('JSGt', a=d, b=bd, offset='g')
    fb.op('Mov', dst=ye, src=y)
    fb.op('Call1', dst=st, fun=striking, arg0=ye)
    fb.op('JTrue', cond=st, offset='g')
    fb.op('Call1', dst=st, fun=helpers['wormonly'], arg0=ye)  # waiting on rock from a worm: not sent onto the sand
    fb.op('JTrue', cond=st, offset='g')
    fb.op('Mov', dst=bd, src=d)
    fb.op('Mov', dst=best, src=y)
    fb.op('JAlways', offset='g')
    fb.label('gsel')
    fb.op('JNull', reg=best, offset='gd')
    fb.op('Mov', dst=ye, src=best)
    _do_on(fb, b, cx, ye, 'ArmyFight', ee, fac)
    b.call('haxe.ds.ObjectMap.set', strk, fb.dyn(best), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', strt, fb.dyn(best), fb.dyn(e))
    b.call('haxe.ds.ObjectMap.set', strs, fb.dyn(best), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', stro, fb.dyn(best), fb.dyn(o))
    b.call('haxe.ds.ObjectMap.set', strx, fb.dyn(best), fb.dyn(b.field(best, 'posx')))
    b.call('haxe.ds.ObjectMap.set', stry, fb.dyn(best), fb.dyn(b.field(best, 'posy')))
    fb.op('Call1', dst=q, fun=pw, arg0=best)
    fb.op('Add', dst=sent, a=sent, b=q)
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset='gp')
    fb.label('gd')
    fb.op('JSLte', a=n, b=zi, offset='u')  # nobody new sent (all already striking): no row
    nf = fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=nf, src=n)
    _log_ev(fb, b, cx, helpers, 'strike', [('f', fb.get(fac, 'kind')), ('act', 'start'), ('a', a2), ('en', e),
                                           ('M', m), ('H', h), ('d', dn), ('n', nf)])
    fb.op('JAlways', offset='u')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
