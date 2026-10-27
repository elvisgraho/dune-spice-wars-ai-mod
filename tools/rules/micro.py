"""Vanilla fight-micro input fixes (docs/INPUT-SPAM-TODO.md): flee-move and attack-resend (see _attack_resend).

flee-move: `AIUnits.unitMicroManagement` dispatches each army's micro at its end (AIUnits.hx:1081 Attack -> doAction
ArmyFight / ArmySiege, :1100 Reposition -> Move, :1114 Flee -> Move). Reposition sends its Move only when the army's
`movementMode` isn't already `Target(pos)`; Flee has the same test with an empty body and sends a Move every tick
(0.5 s) for as long as the fight retreat holds: 2400-4900 Moves per match, up to 40 / min for one faction (matches
2026-10-25 0850 / 0936 / 0950). The third doAction site (Flee) -> wrapper: skip the Move when the army already walks
to the same point it was sent within FLEE_RESEND_T s (re-sent every 3 s, not every 0.5 s tick); otherwise the call it had (the ai-log `dact` tracer
when installed, else doAction). Logs `fskip` (f, a, n skipped since the last row) per army per FSKIP_T s."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

FSKIP_T = 30  # s: one `fskip` row per army this often
FLEE_RESEND_T = 3  # s: the same Flee point is re-sent this often at most (vanilla: every 0.5 s tick)
OUR_HOLD_T = 4  # s: after one of our Moves on an army, micro's commands to it wait this long
FLEE_OWN_T = 4  # s: an army sent a Flee Move this recently gets no Attack from another fight
ATK_RESEND_T = 6  # s: the same Attack target / kind is re-sent this often at most (vanilla: every tick while walking;
                  # 2 still re-sent every 2 s at Fonbat, each re-send can restart the attack)
FOCUS_R = 100     # focus fire: the faction's focus in the zone is an attacking army's target while this close to it
STICK_R = 120     # attack-resend: keep the last target while it's this close ...
STICK_MAX = 20    # ... and was first sent less than this many s ago


def fix_micro_inputs(cx, helpers, new_ids):
    """The 3 doAction sites of unitMicroManagement (Attack, Reposition, Flee; the ai-log `dact` tracer's when
    installed): attack-resend on the first, flee-move on the third."""
    um = cx.fn('logic.ai.AIUnits.unitMicroManagement')
    da = cx.fn('ent.Entity.doAction')
    tids = {da.findex.value}
    if helpers.get('dact_w') is not None:
        tids.add(helpers['dact_w'])
    sites = [op for op in um.ops if op.op == 'Call4' and op.df.get('fun') is not None and op.df['fun'].value in tids]
    if len(sites) != 3:
        raise ValueError(f'micro inputs: expected 3 doAction calls in unitMicroManagement, found {len(sites)}')
    _attack_resend(cx, helpers, new_ids, sites[0])  # AIUnits.hx:1081 Attack
    _flee_move(cx, helpers, new_ids, sites[2])  # AIUnits.hx:1114 Flee
    for s_ in sites:  # all three (Reposition included), around what they call now
        _our_hold(cx, helpers, new_ids, s_)
    return {'attack-resend': 1, 'flee-move': 1, 'our-hold': 3}


def _flee_move(cx, helpers, new_ids, flee):
    da = cx.fn('ent.Entity.doAction')
    orig = flee.df['fun'].value
    ft = cx.code.types[da.type.value].definition
    args = [a.value for a in ft.args]  # entity, kind, options {actionTarget}, faction
    fb = FB(cx, args, ft.ret.value, fun_type=da.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('Null', dst=res)
    skip = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=skip, value=False)
    g = fb.try_()
    army = b.cast(fb.dyn(0), 'ent.Army')
    fb.op('JNull', reg=army, offset='chk_d')
    et_t = cx.code.types[args[2]].definition.fields[0].type.value
    tg = fb.reg(et_t)
    fb.op('JNull', reg=2, offset='chk_d')
    fb.op('Field', dst=tg, obj=2, field=0)
    fb.op('JNull', reg=tg, offset='chk_d')
    et = cx.code.types[et_t].definition
    wi = [c.name.resolve(cx.code) for c in et.constructs].index('EWorldPosition')
    ix = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ix, value=tg)
    fb.op('JNotEq', a=ix, b=b.const('i32', wi), offset='chk_d')
    pt = fb.reg(et.constructs[wi].params[0].value)
    fb.op('EnumField', dst=pt, value=tg, construct=wi, field=0)
    px, py, q = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=px, src=b.field(pt, 'x'))
    fb.op('Mov', dst=py, src=b.field(pt, 'y'))
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    # the same point sent within FLEE_RESEND_T s: skip (the movementMode test vanilla's Reposition uses never
    # matched here: the Move's stored Target isn't the point as given, match 2026-10-25 1028)
    fmt, fmx, fmy = _global_map(fb, b, cx, 'fmt'), _global_map(fb, b, cx, 'fmx'), _global_map(fb, b, cx, 'fmy')
    lt = b.call('haxe.ds.ObjectMap.get', fmt, fb.dyn(army))
    fb.op('JNull', reg=lt, offset='send')
    lx = b.call('haxe.ds.ObjectMap.get', fmx, fb.dyn(army))
    ly = b.call('haxe.ds.ObjectMap.get', fmy, fb.dyn(army))
    fb.op('JNull', reg=lx, offset='send')
    fb.op('JNull', reg=ly, offset='send')
    fb.op('SafeCast', dst=q, src=lx)
    fb.op('JNotEq', a=q, b=px, offset='send')
    fb.op('SafeCast', dst=q, src=ly)
    fb.op('JNotEq', a=q, b=py, offset='send')
    fb.op('SafeCast', dst=q, src=lt)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSGte', a=q, b=b.const('f64', FLEE_RESEND_T), offset='send')
    fb.op('Bool', dst=skip, value=True)
    # count it; log per army per FSKIP_T s
    fsk = _global_map(fb, b, cx, 'fskn')
    cnv = b.call('haxe.ds.ObjectMap.get', fsk, fb.dyn(army))
    cn = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=cn, src=b.const('i32', 0))
    fb.op('JNull', reg=cnv, offset='cn_d')
    fb.op('SafeCast', dst=cn, src=cnv)
    fb.label('cn_d')
    fb.op('Incr', dst=cn)
    b.call('haxe.ds.ObjectMap.set', fsk, fb.dyn(army), fb.dyn(cn))
    _throttle(fb, b, cx, 'fskip', army, FSKIP_T, 'chk_d')
    ae = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ae, src=army)
    _log_ev(fb, b, cx, helpers, 'fskip', [('f', fb.get(b.call('ent.Entity.get_owner', ae), 'kind')), ('a', ae),
                                          ('n', fb.dyn(cn))])
    b.call('haxe.ds.ObjectMap.remove', fsk, fb.dyn(army))
    fb.op('JAlways', offset='chk_d')
    fb.label('send')  # sent: remember the point and the time
    b.call('haxe.ds.ObjectMap.set', fmt, fb.dyn(army), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', fmx, fb.dyn(army), fb.dyn(px))
    b.call('haxe.ds.ObjectMap.set', fmy, fb.dyn(army), fb.dyn(py))
    fb.label('chk_d')
    fb.end_try(g)
    fb.op('JTrue', cond=skip, offset='ret')
    fb.op('Call4', dst=res, fun=orig, arg0=0, arg1=1, arg2=2, arg3=3)  # outside the trap: vanilla's call as it was
    fb.label('ret')
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    flee.df['fun'].value = w


def _attack_resend(cx, helpers, new_ids, site):
    """attack-resend: the Attack site (AIUnits.hx:1081) sends doAction(ArmyFight / ArmySiege, target) whenever the army's
    getFightingTarget() isn't the target, i.e. on every tick while it walks to it (Engage / Fight only set it): about
    1100 of micro's 2025 ArmyFight sends in match 2026-10-25 1041 were the same target again. Skip the same kind on the
    same target sent to this army within ATK_RESEND_T s. Logs `askip` (f, a, n) per army per FSKIP_T s."""
    da = cx.fn('ent.Entity.doAction')
    orig = site.df['fun'].value
    ft = cx.code.types[da.type.value].definition
    args = [a.value for a in ft.args]  # entity, kind, options {actionTarget}, faction
    fb = FB(cx, args, ft.ret.value, fun_type=da.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('Null', dst=res)
    skip = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=skip, value=False)
    opt2 = fb.reg(args[2])  # the options vanilla sends (replaced by the focus retarget below)
    fb.op('Mov', dst=opt2, src=2)
    g = fb.try_()
    army = b.cast(fb.dyn(0), 'ent.Army')
    fb.op('JNull', reg=army, offset='chk_d')
    fb.op('JNull', reg=1, offset='chk_d')
    et_t = cx.code.types[args[2]].definition.fields[0].type.value
    tg = fb.reg(et_t)
    fb.op('JNull', reg=2, offset='chk_d')
    fb.op('Field', dst=tg, obj=2, field=0)
    fb.op('JNull', reg=tg, offset='chk_d')
    et = cx.code.types[et_t].definition
    ei = [c.name.resolve(cx.code) for c in et.constructs].index('EEntity')
    ix = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ix, value=tg)
    fb.op('JNotEq', a=ix, b=b.const('i32', ei), offset='chk_d')
    te = fb.reg(et.constructs[ei].params[0].value)
    fb.op('EnumField', dst=te, value=tg, construct=ei, field=0)
    fb.op('JNull', reg=te, offset='chk_d')
    t, q = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    # focus fire (user 2026-10-25, match 75: "humans take a stack and bash units one by one for faster kills"; Fremen's
    # armies at Qafnit spread over 2-4 targets per 10 s and were wiped): per faction and zone (map `ffoc` per faction:
    # the attacking army's zone -> target), the focus is everyone's ArmyFight target while it lives, is visible and lies
    # within FOCUS_R of the attacking army; otherwise micro's pick becomes the focus. Logs `focus` (a, fr, to)
    fb.op('JNull', reg=3, offset='fc_d')
    fb.op('JNotEq', a=b.call('String.__compare', 1, fb.dyn(fb.string('ArmyFight'))), b=b.const('i32', 0), offset='fc_d')
    fb.op('JNull', reg=b.cast(fb.dyn(te), 'ent.Army'), offset='fc_d')  # armies only (not a structure / turret)
    fcz = b.call('ent.Entity.get_zone', 0)
    fb.op('JNull', reg=fcz, offset='fc_d')
    fcm = _fac_map(fb, b, cx, 'ffoc', 3)
    fcv = b.call('haxe.ds.ObjectMap.get', fcm, fb.dyn(fcz))
    fb.op('JNull', reg=fcv, offset='fc_set')
    fce = fb.reg(cx.t('ent.Entity'))
    fb.op('SafeCast', dst=fce, src=fcv)
    fb.op('JNull', reg=fce, offset='fc_set')
    fb.op('JEq', a=fce, b=te, offset='fc_d')  # micro picked the focus itself
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', fce), offset='fc_set')
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', fce, 3), offset='fc_set')
    fca = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=fca, src=army)
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', fca, fce), b=b.const('f64', FOCUS_R), offset='fc_set')
    # retarget: a new options object {actionTarget: EEntity(focus)} (as rules/sdrop.py builds ability args)
    fco = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=fco)
    fct = fb.reg(et_t)
    fb.op('MakeEnum', dst=fct, construct=ei, args=[fce])
    fb.op('DynSet', obj=fco, field=cx.s('actionTarget'), src=fb.dyn(fct))
    fb.op('ToVirtual', dst=opt2, src=fco)
    _throttle(fb, b, cx, 'focus', army, FSKIP_T, 'fc_mv')
    _log_ev(fb, b, cx, helpers, 'focus', [('f', fb.get(3, 'kind')), ('a', fca), ('fr', te), ('to', fce)])
    fb.label('fc_mv')
    fb.op('Mov', dst=te, src=fce)
    fb.op('JAlways', offset='fc_d')
    fb.label('fc_set')
    b.call('haxe.ds.ObjectMap.set', fcm, fb.dyn(fcz), fb.dyn(te))
    fb.label('fc_d')
    # one owner across fights (docs/INPUT-SPAM-TODO.md 3: an army in two fights got a Flee Move from one and an
    # ArmyFight from the other every tick): fleeing (a Flee Move sent within FLEE_OWN_T s, map `fmt`) -> no attack
    ffv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'fmt'), fb.dyn(army))
    fb.op('JNull', reg=ffv, offset='nfl')
    fb.op('SafeCast', dst=q, src=ffv)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSGte', a=q, b=b.const('f64', FLEE_OWN_T), offset='nfl')
    fb.op('Bool', dst=skip, value=True)
    fb.op('JAlways', offset='chk_d')
    fb.label('nfl')
    amt, amg, amk = _global_map(fb, b, cx, 'amt'), _global_map(fb, b, cx, 'amg'), _global_map(fb, b, cx, 'amk')
    lt = b.call('haxe.ds.ObjectMap.get', amt, fb.dyn(army))
    fb.op('JNull', reg=lt, offset='send')
    lg = b.call('haxe.ds.ObjectMap.get', amg, fb.dyn(army))
    fb.op('JNull', reg=lg, offset='send')
    fb.op('JNotEq', a=lg, b=fb.dyn(te), offset='stick')  # another target: keep the last one?
    lk = b.call('haxe.ds.ObjectMap.get', amk, fb.dyn(army))
    fb.op('JNull', reg=lk, offset='send')
    lks = b.cast(lk, 'String')
    fb.op('JNull', reg=lks, offset='send')
    fb.op('JNotEq', a=b.call('String.__compare', lks, fb.dyn(1)), b=b.const('i32', 0), offset='send')  # another kind
    fb.op('SafeCast', dst=q, src=lt)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSGte', a=q, b=b.const('f64', ATK_RESEND_T), offset='send')
    fb.op('Bool', dst=skip, value=True)
    ask = _global_map(fb, b, cx, 'askn')
    cnv = b.call('haxe.ds.ObjectMap.get', ask, fb.dyn(army))
    cn = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=cn, src=b.const('i32', 0))
    fb.op('JNull', reg=cnv, offset='cn_d')
    fb.op('SafeCast', dst=cn, src=cnv)
    fb.label('cn_d')
    fb.op('Incr', dst=cn)
    b.call('haxe.ds.ObjectMap.set', ask, fb.dyn(army), fb.dyn(cn))
    _throttle(fb, b, cx, 'askip', army, FSKIP_T, 'chk_d')
    ae = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ae, src=army)
    _log_ev(fb, b, cx, helpers, 'askip', [('f', fb.get(b.call('ent.Entity.get_owner', ae), 'kind')), ('a', ae),
                                          ('n', fb.dyn(cn))])
    b.call('haxe.ds.ObjectMap.remove', ask, fb.dyn(army))
    fb.op('JAlways', offset='chk_d')
    # stick to the target (user 2026-10-25: "click on the unit and try to kill it"; at Fonbat Atreides' armies flipped
    # between two militia every 1-2 s): another target while the last one we sent is alive, within STICK_R and was
    # first sent less than STICK_MAX s ago -> skip. Logs `astick` (f, a, n) per army per FSKIP_T s
    fb.label('stick')
    lga = b.cast(lg, 'ent.Army')  # armies only: away from a structure (a turret) to an army is a real switch
    fb.op('JNull', reg=lga, offset='send')
    lge = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=lge, src=lga)
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', lge), offset='send')
    ae2 = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ae2, src=army)
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ae2, lge), b=b.const('f64', STICK_R), offset='send')
    sv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'ams'), fb.dyn(army))
    fb.op('JNull', reg=sv, offset='send')
    fb.op('SafeCast', dst=q, src=sv)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSGt', a=q, b=b.const('f64', STICK_MAX), offset='send')
    fb.op('Bool', dst=skip, value=True)
    asn = _global_map(fb, b, cx, 'astn')
    snv = b.call('haxe.ds.ObjectMap.get', asn, fb.dyn(army))
    sn = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=sn, src=b.const('i32', 0))
    fb.op('JNull', reg=snv, offset='sn_d')
    fb.op('SafeCast', dst=sn, src=snv)
    fb.label('sn_d')
    fb.op('Incr', dst=sn)
    b.call('haxe.ds.ObjectMap.set', asn, fb.dyn(army), fb.dyn(sn))
    _throttle(fb, b, cx, 'astick', army, FSKIP_T, 'chk_d')
    _log_ev(fb, b, cx, helpers, 'astick', [('f', fb.get(b.call('ent.Entity.get_owner', ae2), 'kind')), ('a', ae2),
                                           ('n', fb.dyn(sn)), ('tgt', lge)])
    b.call('haxe.ds.ObjectMap.remove', asn, fb.dyn(army))
    fb.op('JAlways', offset='chk_d')
    fb.label('send')  # sent: remember the target, the kind and the time (a new target: its first-send time)
    # (diagnostic 2026-10-25, match 74: an F_Sneak got ArmyFight on one Discovery_Sniper every 0.5 s for 20 s with no
    # `askip`): a send within ATK_RESEND_T s of the last one logs `adbg` (a, prev target / kind, now target / kind)
    dbv = b.call('haxe.ds.ObjectMap.get', amt, fb.dyn(army))
    fb.op('JNull', reg=dbv, offset='db_d')
    dbq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=dbq, src=dbv)
    fb.op('Sub', dst=dbq, a=t, b=dbq)
    fb.op('JSGte', a=dbq, b=b.const('f64', ATK_RESEND_T), offset='db_d')
    _throttle(fb, b, cx, 'adbg', army, 10, 'db_d')
    ae3 = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ae3, src=army)
    _log_ev(fb, b, cx, helpers, 'adbg', [('f', fb.get(b.call('ent.Entity.get_owner', ae3), 'kind')), ('a', ae3),
                                         ('pt', b.cast(b.call('haxe.ds.ObjectMap.get', amg, fb.dyn(army)), 'ent.Entity')),
                                         ('nt', te), ('pk', b.cast(b.call('haxe.ds.ObjectMap.get', amk, fb.dyn(army)), 'String')),
                                         ('nk', 1), ('dt%', dbq)])
    fb.label('db_d')
    lg2 = b.call('haxe.ds.ObjectMap.get', amg, fb.dyn(army))
    fb.op('JEq', a=lg2, b=fb.dyn(te), offset='same_t')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'ams'), fb.dyn(army), fb.dyn(t))
    fb.label('same_t')
    b.call('haxe.ds.ObjectMap.set', amt, fb.dyn(army), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', amg, fb.dyn(army), fb.dyn(te))
    b.call('haxe.ds.ObjectMap.set', amk, fb.dyn(army), fb.dyn(1))
    fb.label('chk_d')
    fb.end_try(g)
    fb.op('JTrue', cond=skip, offset='ret')
    fb.op('Call4', dst=res, fun=orig, arg0=0, arg1=1, arg2=opt2, arg3=3)  # outside the trap (the focus retarget, if any)
    fb.label('ret')
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    site.df['fun'].value = w


def _our_hold(cx, helpers, new_ids, site):
    """our-hold: one of our rules moved this army (worm._move_to stamps map `ourmv` army -> time) within OUR_HOLD_T s:
    the micro command at this site is skipped (docs/INPUT-SPAM-TODO.md 6: worm flee, spos, dstep, leash, rsguard and
    the strike stop moved armies in a fight, and micro sent ArmyFight / Reposition again on the next tick). Wraps the
    site's current callee (it chains with flee-move / attack-resend). Logs `ohold` (f, a, n) per army per FSKIP_T s."""
    da = cx.fn('ent.Entity.doAction')
    orig = site.df['fun'].value
    ft = cx.code.types[da.type.value].definition
    args = [a.value for a in ft.args]
    fb = FB(cx, args, ft.ret.value, fun_type=da.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('Null', dst=res)
    skip = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=skip, value=False)
    g = fb.try_()
    fb.op('JNull', reg=0, offset='chk_d')
    mv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'ourmv'), fb.dyn(0))
    fb.op('JNull', reg=mv, offset='chk_d')
    q = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=q, src=mv)
    fb.op('Sub', dst=q, a=b.field(_state(fb, b, cx), 'time'), b=q)
    fb.op('JSGte', a=q, b=b.const('f64', OUR_HOLD_T), offset='chk_d')
    fb.op('Bool', dst=skip, value=True)
    on = _global_map(fb, b, cx, 'ohn')
    cnv = b.call('haxe.ds.ObjectMap.get', on, fb.dyn(0))
    cn = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=cn, src=b.const('i32', 0))
    fb.op('JNull', reg=cnv, offset='cn_d')
    fb.op('SafeCast', dst=cn, src=cnv)
    fb.label('cn_d')
    fb.op('Incr', dst=cn)
    b.call('haxe.ds.ObjectMap.set', on, fb.dyn(0), fb.dyn(cn))
    _throttle(fb, b, cx, 'ohold', 0, FSKIP_T, 'chk_d')
    _log_ev(fb, b, cx, helpers, 'ohold', [('f', fb.get(b.call('ent.Entity.get_owner', 0), 'kind')), ('a', 0),
                                          ('n', fb.dyn(cn))])
    b.call('haxe.ds.ObjectMap.remove', on, fb.dyn(0))
    fb.label('chk_d')
    fb.end_try(g)
    fb.op('JTrue', cond=skip, offset='ret')
    fb.op('Call4', dst=res, fun=orig, arg0=0, arg1=1, arg2=2, arg3=3)  # outside the trap
    fb.label('ret')
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    site.df['fun'].value = w
