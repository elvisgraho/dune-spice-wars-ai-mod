"""Running-hunt checks: engage, abandon, redirect and record chase progress.

The keyword inputs are register indices, helpers and callbacks allocated by
build_hunt. Only the shared bytecode builder is changed; no Python values are
returned to the new-hunt pass. Runtime labels may jump to that later pass.
"""
from rules.common import *  # noqa: F401,F403
from rules import bkstate as bks
from rules.worm import _move_to
from rules.hunt.support import HUNT_FC_T, _log_hunt, _near_base, _late


def _emit_running(
    *,
    _trip, abort, b, besieger, big, close, cnt, conmap, contact, contest_r, core, cover_at, cx,
    defend, dfs, drift_r, ent_r, enter, eta_fn, fac, fb, first, found, free, gap, givemap, h, hat,
    hax, hay, helpers, home, home_exit, hunt_r, i, idx, j, k, kill, land, lastmap, leash, local,
    losing, m, need, neu, neutral, nn, no_ent, no_orders, objmap, ok, one, orders, ourdd, p,
    pd_map, pf, pp, pp_map, prog, pt_map, pw, q, rdf, rpf, rtf, sd, sdx, short, sieged, state,
    sup_enter, supok, t, tc, terrain, tf, threat_at, tm, tripd, tv, ve, villages, vis, vlen, void,
    war, zero, zi,
):
    """Emit existing-order checks using the caller's register allocation and trap."""
    # ---- 1. abort pass: re-check running hunts (backwards: stop() removes the order from the list)
    _tick(fb, b, cx, t, CHECK, 'new')
    fb.op('Call1', dst=dfs, fun=defend, arg0=fac)
    reason = cx.code.types[cx.fn('logic.ai.AIOrder.stop').type.value].definition.args[1].value
    cancel = fb.reg(reason)
    fb.op('MakeEnum', dst=cancel, construct=CANCEL, args=[])
    fb.op('Mov', dst=i, src=b.field(orders, 'length'))
    b.loop_head('ord')
    fb.op('JSLte', a=i, b=zi, offset='new')
    fb.op('Sub', dst=i, a=i, b=one)
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, i), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset='ord')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='ord')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='ord')
    fb.op('EnumIndex', dst=idx, value=tt)
    fb.op('JNotEq', a=idx, b=b.const('i32', T_GROUP), offset='ord')
    g = b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'logic.ai.AIEntityGroup')
    fb.op('JNull', reg=g, offset='ab_nolog')
    fb.op('Mov', dst=ent_r, src=g)
    fb.op('Mov', dst=first, src=g)
    fb.op('Mov', dst=core, src=g)
    for r in (h, m, pp):
        fb.op('Mov', dst=r, src=zero)
    for r in (cnt, war, vis, home, nn):
        fb.op('Mov', dst=r, src=zi)
    fb.op('Mov', dst=sd, src=big)
    fb.op('Mov', dst=tc, src=zero)
    fb.op('JTrue', cond=b.field(g, 'removed'), offset='ab_gone')
    # members: alive / at war with us / visible / on their owner's own zone
    mem = b.field(g, 'entities')
    fb.op('JNull', reg=mem, offset='ab_gone')
    mn = b.field(mem, 'length')
    fb.op('Mov', dst=j, src=zi)
    b.loop_head('mem')
    fb.op('JSGte', a=j, b=mn, offset='mdone')
    e = b.cast(b.call('hl.types.ArrayObj.getDyn', mem, j), 'ent.Entity')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=e, offset='mem')
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', e), offset='mem')
    fb.op('Bool', dst=neu, value=False)
    eo = b.call('ent.Entity.get_owner', e)
    fb.op('JNotNull', reg=eo, offset='mown')
    fb.op('JNull', reg=fb.get(e, 'raid'), offset='mem')  # a neutral raider (neutral hunt): hostile, no home
    fb.op('Bool', dst=neu, value=True)
    fb.op('Add', dst=nn, a=nn, b=one)
    fb.label('mown')
    fb.op('Add', dst=cnt, a=cnt, b=one)
    fb.op('Call1', dst=p, fun=pw, arg0=b.cast(e, 'ent.Army'))
    fb.op('Add', dst=pp, a=pp, b=p)
    fb.op('Mov', dst=first, src=e)
    fb.op('Call2', dst=sdx, fun=land, arg0=fac, arg1=e)
    fb.op('JSGte', a=sdx, b=sd, offset='nomin')
    fb.op('Mov', dst=sd, src=sdx)
    fb.op('Mov', dst=core, src=e)
    fb.label('nomin')
    fb.op('JTrue', cond=neu, offset='mwar')
    fb.op('JEq', a=eo, b=fac, offset='nowar')  # areAtWar(us, us) logs a vanilla warning per call
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, eo), offset='nowar')
    fb.label('mwar')
    fb.op('Add', dst=war, a=war, b=one)
    fb.label('nowar')
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', e, fac), offset='novis')
    fb.op('Add', dst=vis, a=vis, b=one)
    fb.label('novis')
    fb.op('JTrue', cond=neu, offset='mem')
    z = b.call('ent.Entity.get_zone', e)
    fb.op('JNull', reg=z, offset='mem')
    fb.op('JNotEq', a=b.field(z, 'owner'), b=eo, offset='mem')
    fb.op('Add', dst=home, a=home, b=one)
    fb.op('JAlways', offset='mem')
    fb.label('mdone')
    # the group is judged at its core (the member nearest our land, sd), not at its centroid: a member walking home
    # dragged the centroid under its own base's guns and aborted a winning hunt as `weak`. Members more than LOCAL
    # from the core have split off: they leave the group, so the order's target (centroid) stays on the prey
    fb.op('Mov', dst=first, src=core)
    fb.op('Mov', dst=ent_r, src=core)
    fb.op('Mov', dst=j, src=mn)
    b.loop_head('prune')
    fb.op('JSLte', a=j, b=zi, offset='pdone')
    fb.op('Sub', dst=j, a=j, b=one)
    pe = b.cast(b.call('hl.types.ArrayObj.getDyn', mem, j), 'ent.Entity')
    fb.op('JNull', reg=pe, offset='prune')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', pe, core), b=local, offset='prune')
    b.call('hl.types.ArrayObj.remove', mem, fb.dyn(pe))
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', pe), offset='prune')
    fb.op('Call1', dst=p, fun=pw, arg0=b.cast(pe, 'ent.Army'))
    fb.op('Sub', dst=pp, a=pp, b=p)  # progress is measured on the members that stay
    fb.op('JAlways', offset='prune')
    fb.label('pdone')
    # our side: power, nearest order army to the core, anyone short of supply for the way back
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='ab_gone')
    un = b.field(units, 'length')
    fb.op('Mov', dst=need, src=big)
    fb.op('Bool', dst=losing, value=False)
    fb.op('Bool', dst=ourdd, value=False)
    # in transit (worm ride / shuttle): no re-decision until it lands; _army_loop skips transported armies, so
    # power read 0 (Fremen: 6 armies riding to contest Hadwaz, M 0, aborted `weak`, landed orderless as it fell)
    _riding(fb, b, cx, helpers, fac, o, units, 'hride', 'ord')
    u = _army_loop(fb, b, units, un, j, 'units', 'udone')
    fb.op('Call1', dst=p, fun=pw, arg0=u)
    fb.op('Add', dst=m, a=m, b=p)
    # one of ours in the deep desert (user: Atreides chased a Fremen group along the sand; the prey's own zone test
    # missed it): the desert abort below judges it like a prey there
    uz = b.call('ent.Entity.get_zone', u)
    fb.op('JNull', reg=uz, offset='udd')
    fb.op('JFalse', cond=b.call('ent.Zone.isDeepDesert', uz), offset='udd')
    fb.op('Bool', dst=ourdd, value=True)
    fb.label('udd')
    fb.op('Call2', dst=ok, fun=short, arg0=fac, arg1=u)
    fb.op('JFalse', cond=ok, offset='sup')  # hysteresis: the start needs SUP_ENTER x the budget
    fb.op('Bool', dst=losing, value=True)
    fb.label('sup')
    dd = b.call('ent.Entity.getDistTo', u, core)
    fb.op('JSGte', a=dd, b=need, offset='units')
    fb.op('Mov', dst=need, src=dd)
    fb.op('JAlways', offset='units')
    fb.label('udone')
    # triggers, in priority order (sd = the member nearest to our land, same measure as the start pass)
    fb.op('JSLte', a=cnt, b=zi, offset='ab_gone')
    fb.op('JSLte', a=war, b=zi, offset='ab_truce')
    # won: a contest (map `hcon` order -> its village) whose village is no longer besieged has done its job. Following
    # the beaten group is a chase into its land where a dying rear member in contact counts as progress every check
    # (Smugglers' 11 armies broke Harkonnen's Annex of Lam-nih, followed the group ~300 north, then drifted under
    # Carthag's guns). Ends once the core is WON_R from the village; the fight at the village itself is finished
    cv = b.call('haxe.ds.ObjectMap.get', conmap, fb.dyn(o))
    fb.op('JNull', reg=cv, offset='nowon')
    wv = b.cast(cv, 'ent.Structure')
    fb.op('JNull', reg=wv, offset='nowon')
    fb.op('Call2', dst=ok, fun=sieged, arg0=fac, arg1=wv)
    fb.op('JTrue', cond=ok, offset='nowon')
    fb.op('Mov', dst=ve, src=wv)
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', core, ve), b=b.const('f64', WON_R), offset='ab_won')
    fb.label('nowon')
    # a capture guard (map `hgrd`): while we still besiege / occupy its target no leash / home / drift; once the
    # capture has ended (taken, lost, cancelled) `won`
    # a base-kill campaign fight (rules/bkill.py `bcfo`): no leash / home / drift (the base is deep in the leader's
    # land), no weak (the campaign's joint numbers decide, not one member's forecast) and no chase checks (objective,
    # defend, turret: the leader's armies stand under its base guns, which is the target; desert); gone / truce /
    # supply / lost apply as to any hunt (user 2026-10-24: Fremen attacked while Harkonnen / Smugglers just chilled:
    # their fights aborted weak x 3, turret x 2, chase within seconds)
    isbc = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=isbc, value=False)
    fb.op('JNull', reg=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.FIGHT_ORDER), fb.dyn(o)), offset='nobc')
    fb.op('Bool', dst=isbc, value=True)
    fb.op('JAlways', offset='nodrift')
    fb.label('nobc')
    gdv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'hgrd'), fb.dyn(o))
    fb.op('JNull', reg=gdv, offset='nogrd')
    gds = b.cast(gdv, 'ent.Structure')
    fb.op('JNull', reg=gds, offset='ab_won')
    fb.op('Mov', dst=ve, src=gds)  # logged as obj
    gsg = b.field(gds, 'siege')
    fb.op('JNull', reg=gsg, offset='ab_won')
    fb.op('JEq', a=b.field(gsg, 'besiegingFaction'), b=fac, offset='nodrift')
    fb.op('JEq', a=b.call('ent.comp.SiegeComponent.getOccupierFaction', gsg), b=fac, offset='nodrift')
    fb.op('JAlways', offset='ab_won')
    fb.label('nogrd')
    # a contest reaches CONTEST_R (a worm ride: CONTEST_RIDE_R) from our land: its leash is CONTEST_LEASH, and no
    # `drift` (the besiegers stand at their village; our armies walking / riding there aren't in contact yet)
    fb.op('JNull', reg=cv, offset='lsh')
    fb.op('JSGt', a=sd, b=b.const('f64', CONTEST_LEASH), offset='ab_leash')
    fb.op('JNotEq', a=home, b=cnt, offset='nodrift')
    fb.op('JSGt', a=sd, b=home_exit, offset='ab_home')
    fb.op('JAlways', offset='nodrift')
    fb.label('lsh')
    fb.op('JSGt', a=sd, b=leash, offset='ab_leash')
    fb.op('JNotEq', a=home, b=cnt, offset='nothome')
    fb.op('JSGt', a=sd, b=home_exit, offset='ab_home')
    fb.label('nothome')
    fb.op('JSLte', a=sd, b=drift_r, offset='nodrift')  # moving away from our land and we never caught up
    fb.op('JSGt', a=need, b=contact, offset='ab_drift')
    fb.label('nodrift')
    fb.op('JSGt', a=vis, b=zi, offset='seen')
    fb.op('JSGt', a=need, b=local, offset='ab_lost')
    fb.label('seen')
    fb.op('Mov', dst=pf, src=b.call('ent.Entity.get_owner', core))  # the group is one faction (start pass)
    threat_at(h, ent_r, need)
    fb.op('JSLte', a=nn, b=zi, offset='noneu')  # neutral prey: raiders busy elsewhere fight back too
    fb.op('Call3', dst=q, fun=neutral, arg0=fac, arg1=ent_r, arg2=local)
    fb.op('Add', dst=h, a=h, b=q)
    fb.label('noneu')
    # turret cover at the group: enemy turrets / main base guns add to the threat, ours to our power
    cover_at(tc, ent_r, no_ent, False)
    cover_at(tm, ent_r, no_ent, True)
    # an enemy main base ahead: its defense weighs in before its guns reach us, growing from 0 at BASE_KEEP to all
    # of it at the base (soft: a strong enough stack still goes; Atreides' 8 armies chased a dying Fremen group from
    # Qalnih to 123 from Tabr on draining supply and were wiped out after). The larger of it and the cover at the
    # group: within gun range the base is already in that
    nbm, nbw = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('f64'))
    _near_base(fb, b, cx, state, fac, core, nbm, nbw)
    fb.op('JNull', reg=nbm, offset='nbdone')
    cover_at(q, nbm, no_ent, False)
    fb.op('Mul', dst=q, a=q, b=nbw)
    fb.op('JSLte', a=q, b=tc, offset='nbdone')
    fb.op('Mov', dst=tc, src=q)
    fb.label('nbdone')
    fb.op('Add', dst=h, a=h, b=tc)
    fb.op('Add', dst=m, a=m, b=tm)
    fb.op('Mul', dst=p, a=h, b=abort)
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', first))
    fb.op('SDiv', dst=p, a=p, b=tf)  # on their land we give up earlier, on ours later
    # weak: the battle forecast at the group's core (rules/forecast.py, docs/ARCHITECTURE-PLAN.md step 1) with the
    # hunt's own armies over HUNT_FC_T, attack for a chase, defense for a contest; below ABORT -> weak. Neutral prey
    # (raiders hostile to someone else, which the forecast doesn't count) keep the hunt's own measure
    fb.op('JSGt', a=nn, b=zi, offset='wold')
    fatk, fcr = fb.reg(cx.t('bool')), fb.reg(cx.t('f64'))
    fb.op('Bool', dst=fatk, value=True)
    fb.op('JNull', reg=cv, offset='fca')
    fb.op('Bool', dst=fatk, value=False)
    fb.label('fca')
    fb.op('JTrue', cond=isbc, offset='wok')
    fb.op('CallN', dst=fcr, fun=helpers['forecast'], args=[fac, ent_r, b.const('f64', HUNT_FC_T), fatk, units])
    fb.op('JSLt', a=fcr, b=abort, offset='ab_weak')
    fb.op('JAlways', offset='wok')
    fb.label('wold')
    fb.op('JTrue', cond=isbc, offset='wok')
    fb.op('JSLt', a=m, b=p, offset='ab_weak')
    fb.label('wok')
    # supply: turn back while the way home is affordable, in contact too, unless we are on the prey and crush it
    # (KILL x its threat: a few seconds to finish it; a stack walked home from a nearly dead army and gave it up).
    # A prey without power (a harvester) is no quick kill: KILL x 0 always held, and 2 Smugglers S_Troopers shot a
    # deployed F_Harvester for 30 s (hp -12 / 10 s) on hostile sand while supply fell 83 -> 26
    fb.op('JFalse', cond=losing, offset='supok')
    # a campaign fight under our Supply Drop (map `sdz` zone -> expiry, its first army's zone) isn't losing supply
    # (Fremen's campaign fights aborted `supply` within seconds, match 2026-10-24 22:09)
    fb.op('JFalse', cond=isbc, offset='sdz_no')
    sdzz = b.call('ent.Entity.get_zone', first)
    fb.op('JNull', reg=sdzz, offset='sdz_no')
    sdzv = b.call('haxe.ds.ObjectMap.get', _fac_map(fb, b, cx, 'sdz', fac), fb.dyn(sdzz))  # our own drop only
    fb.op('JNull', reg=sdzv, offset='sdz_no')
    sdzq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=sdzq, src=sdzv)
    fb.op('JSGt', a=sdzq, b=t, offset='supok')
    fb.label('sdz_no')
    fb.op('JSGt', a=need, b=contact, offset='ab_supply')
    fb.op('JSLte', a=pp, b=zero, offset='ab_supply')
    fb.op('Mul', dst=q, a=h, b=kill)
    fb.op('SDiv', dst=q, a=q, b=tf)
    fb.op('JSLt', a=m, b=q, offset='ab_supply')
    # ... for CRUSH_T s of the prey running at most (map `hcrush` order -> running s, CHECK per pass it moves; summed,
    # so a prey stopping now and then doesn't reset it): a dying prey that keeps running drags the stack on while
    # supply drains. A prey standing and fighting keeps the waiver until it dies (Atreides crushing Fremen at
    # Bir-rekh at 10-13x were pulled home by a wall-clock cap and lost an army left behind)
    fb.op('JFalse', cond=b.call('ent.Unit.isMoving', core), offset='supok')
    crm = _global_map(fb, b, cx, 'hcrush')
    crv = b.call('haxe.ds.ObjectMap.get', crm, fb.dyn(o))
    fb.op('Mov', dst=q, src=b.const('f64', 0))
    fb.op('JNull', reg=crv, offset='crnew')
    fb.op('SafeCast', dst=q, src=crv)
    fb.label('crnew')
    fb.op('Add', dst=q, a=q, b=b.const('f64', CHECK))
    b.call('haxe.ds.ObjectMap.set', crm, fb.dyn(o), fb.dyn(q))
    fb.op('JSGt', a=q, b=b.const('f64', CRUSH_T), offset='ab_supply')
    fb.label('supok')
    fb.op('JTrue', cond=isbc, offset='go')  # a campaign fight: no chase checks
    # objective: a chase (no besieged village within LOCAL of its group) yields to a siege near our land that its
    # own armies could stop (same entry test as a contest start: free, within HUNT_R, supply budget, ENTER x
    # threat / terrain)
    fb.op('Null', dst=found)
    fb.op('Mov', dst=k, src=zi)
    b.loop_head('obj')
    fb.op('JSGte', a=k, b=vlen, offset='objdone')
    v = b.cast(b.call('hl.types.ArrayObj.getDyn', villages, k), 'ent.Structure')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=v, offset='obj')
    fb.op('Call2', dst=ok, fun=sieged, arg0=fac, arg1=v)
    fb.op('JFalse', cond=ok, offset='obj')
    fb.op('Mov', dst=ve, src=v)
    # already contesting one: no chase checks (pursuit, home run, defend, turret, desert), but the Regroup push (`go`)
    # still applies (jumping to the next order left every contest waiting in vanilla Regroup for its last straggler:
    # Smugglers' 11 armies at Lam-nih 27:02-27:34 while Harkonnen's capture ran)
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', g, ve), b=local, offset='go')
    fb.op('JNotNull', reg=found, offset='obj')
    fb.op('Call2', dst=sdx, fun=land, arg0=fac, arg1=ve)
    fb.op('JSGt', a=sdx, b=contest_r, offset='obj')
    # a minor contest (not ours, farther than CONTEST_NEAR) doesn't cancel a running chase
    fb.op('JEq', a=b.call('ent.Entity.get_owner', ve), b=fac, offset='objmaj')
    fb.op('JSGt', a=sdx, b=b.const('f64', CONTEST_NEAR), offset='obj')
    fb.label('objmaj')
    mv, dv = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    dva = fb.reg(cx.t('ent.Entity'))  # the nearest of them (aimod_eta in the arrival test)
    fb.op('Null', dst=dva)
    fb.op('Mov', dst=mv, src=zero)
    fb.op('Mov', dst=dv, src=big)
    uu = _army_loop(fb, b, units, un, j, 'ou', 'oudone')
    du = b.call('ent.Entity.getDistTo', uu, ve)
    fb.op('JSGt', a=du, b=hunt_r, offset='ou')
    fb.op('Call2', dst=ok, fun=free, arg0=uu, arg1=no_orders)
    fb.op('JFalse', cond=ok, offset='ou')
    _trip(uu, du, sdx, tripd)  # same test as a contest start
    fb.op('Call3', dst=ok, fun=supok, arg0=uu, arg1=tripd, arg2=sup_enter)
    fb.op('JFalse', cond=ok, offset='ou')
    fb.op('Call1', dst=p, fun=pw, arg0=uu)
    fb.op('Add', dst=mv, a=mv, b=p)
    fb.op('JSGte', a=du, b=dv, offset='ou')
    fb.op('Mov', dst=dv, src=du)
    fb.op('Mov', dst=dva, src=uu)
    fb.op('JAlways', offset='ou')
    fb.label('oudone')
    fb.op('JSGte', a=dv, b=big, offset='obj')
    _late(fb, b, cx, v, dv, t, 'obj', _uid('olt'), fall=True, fac=fac, eta=(eta_fn, dva))  # same arrival test as the contest start
    hv, rv = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    besieger(v)  # same measure as the contest start
    threat_at(hv, ve, dv)
    cover_at(q, ve, ve, False)  # same measure as the contest start: + enemy cover, + our cover on our side
    fb.op('Add', dst=hv, a=hv, b=q)
    # ... and its size floor: armies alone >= DEF_HOPE_IN x max(threat, the forecast's their side) / terrain
    _fc_theirs(fb, b, cx, helpers, fac, ve, rv, contest=True)
    fb.op('JSGte', a=rv, b=hv, offset='rvmax')
    fb.op('Mov', dst=rv, src=hv)
    fb.label('rvmax')
    fb.op('Call2', dst=tv, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', ve))
    fb.op('SDiv', dst=rv, a=rv, b=tv)
    fb.op('Mul', dst=rv, a=rv, b=_ratio(fb, b, DEF_HOPE_IN))
    fb.op('JSLt', a=mv, b=rv, offset='obj')
    cover_at(q, ve, ve, True)
    fb.op('Add', dst=mv, a=mv, b=q)
    fb.op('Mul', dst=hv, a=hv, b=enter)
    fb.op('SDiv', dst=hv, a=hv, b=tv)
    fb.op('JSLt', a=mv, b=hv, offset='obj')
    fb.op('Mov', dst=found, src=ve)
    fb.op('JAlways', offset='obj')
    fb.label('objdone')
    fb.op('JNotNull', reg=found, offset='ab_objective')
    # chase: the prey runs and we follow without progress (it loses no power and we don't close in) for PURSUIT_T
    # s once engaged: give up (contests never get here: the objective loop above leaves for them). Smugglers' 8 armies followed an unhurt F_Trooper south from Larram toward Grimpo's
    # turret while Larram (57 away) was left unpillaged
    last = b.call('haxe.ds.ObjectMap.get', pt_map, fb.dyn(o))
    fb.op('JNull', reg=last, offset='prog_rec')
    fb.op('JSLt', a=b.field(o, 'phase'), b=b.const('i32', REGROUP + 1), offset='prog_rec')  # not engaged yet
    fb.op('SafeCast', dst=rtf, src=last)
    fb.op('SafeCast', dst=rpf, src=b.call('haxe.ds.ObjectMap.get', pp_map, fb.dyn(o)))
    fb.op('SafeCast', dst=rdf, src=b.call('haxe.ds.ObjectMap.get', pd_map, fb.dyn(o)))
    fb.op('Mul', dst=q, a=rpf, b=prog)
    fb.op('JSLte', a=pp, b=q, offset='prog_rec')  # it lost power
    # on it (within CATCH_R): a prey standing to fight isn't running, finish it (Fremen aborted `chase` at dn 9 on a
    # Raider fighting back at 64k vs 51k: closing in can't count once there); a losing fight is `weak`'s
    fb.op('JSLte', a=need, b=b.const('f64', CATCH_R), offset='prog_rec')
    # we closed in, fast enough to reach it within CATCH_T at this rate: max(CLOSE, (gap - CATCH_R) x PURSUIT_T /
    # CATCH_T) since the last progress
    cr = fb.reg(cx.t('f64'))
    fb.op('Sub', dst=cr, a=rdf, b=b.const('f64', CATCH_R))
    fb.op('Mul', dst=cr, a=cr, b=b.const('f64', PURSUIT_T))
    fb.op('SDiv', dst=cr, a=cr, b=b.const('f64', CATCH_T))
    fb.op('JSGte', a=cr, b=close, offset='catch_r')
    fb.op('Mov', dst=cr, src=close)
    fb.label('catch_r')
    fb.op('Sub', dst=q, a=rdf, b=cr)
    fb.op('JSLte', a=need, b=q, offset='prog_rec')  # we closed in
    fb.op('Sub', dst=q, a=t, b=rtf)
    fb.op('JSGt', a=q, b=b.const('f64', PURSUIT_T), offset='ab_chase')
    fb.op('JAlways', offset='prog_done')
    fb.label('prog_rec')
    b.call('haxe.ds.ObjectMap.set', pt_map, fb.dyn(o), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', pp_map, fb.dyn(o), fb.dyn(pp))
    b.call('haxe.ds.ObjectMap.set', pd_map, fb.dyn(o), fb.dyn(need))
    fb.label('prog_done')
    # home run: the prey runs on its own land with no member below CHASE_LIFE: nothing left to finish, only full-health
    # runners pulling us under their guns (Harkonnen chased Fremen off Gursan at 61x: a dying trooper was worth it,
    # then 20 s more after healthy ones into Fremen land, chip damage counting as progress). Ends as `chase`
    fb.op('JNull', reg=pf, offset='kdone')
    kz = b.call('ent.Entity.get_zone', core)
    fb.op('JNull', reg=kz, offset='kdone')
    fb.op('JNotEq', a=b.field(kz, 'owner'), b=pf, offset='kdone')
    fb.op('JFalse', cond=b.call('ent.Unit.isMoving', core), offset='kdone')  # standing and fighting: finish it
    # on it (within CATCH_R) at ENTER x (threat + cover) / terrain: a fight, not a run home (Smugglers' 365k vs 133k
    # in contact at Tabdalus, which Fremen had just annexed: its zone turned theirs mid-fight, aborted `chase` at dn 9)
    fb.op('JSGt', a=need, b=b.const('f64', CATCH_R), offset='krun')
    fb.op('Mul', dst=q, a=h, b=enter)
    fb.op('SDiv', dst=q, a=q, b=tf)
    fb.op('JSGte', a=m, b=q, offset='kdone')
    fb.label('krun')
    kn, kj = b.field(mem, 'length'), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=kj, src=zi)
    b.loop_head('kill')
    fb.op('JSGte', a=kj, b=kn, offset='ab_chase')
    ke = b.cast(b.call('hl.types.ArrayObj.getDyn', mem, kj), 'ent.Entity')
    fb.op('Incr', dst=kj)
    fb.op('JNull', reg=ke, offset='kill')
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', ke), offset='kill')
    fb.op('JSLt', a=b.call('ent.Entity.get_lifeRatio', ke), b=_ratio(fb, b, CHASE_LIFE), offset='kdone')
    fb.op('JAlways', offset='kill')
    fb.label('kdone')
    # defend: one of our structures is besieged -> a chase ends, unless the prey is in contact and we crush it
    # (h, tf: the group's threat and terrain from the `weak` test)
    fb.op('JNull', reg=dfs, offset='tur')
    fb.op('JSGt', a=need, b=contact, offset='ab_defend')
    fb.op('Mul', dst=q, a=h, b=kill)
    fb.op('SDiv', dst=q, a=q, b=tf)
    fb.op('JSLt', a=m, b=q, offset='ab_defend')
    # turret: a chase under enemy turret cover (a main base, a village's turrets) only while we are on the prey
    # and crush it (h includes the cover: we take a few shots and leave)
    fb.label('tur')
    fb.op('JSLte', a=tc, b=zero, offset='go')
    fb.op('JSGt', a=need, b=contact, offset='ab_turret')
    fb.op('Mul', dst=q, a=h, b=kill)
    fb.op('SDiv', dst=q, a=q, b=tf)
    fb.op('JSLt', a=m, b=q, offset='ab_turret')
    # desert: the prey runs into the deep desert (supply drain x several): only while we are on it and crush it
    fb.op('JTrue', cond=ourdd, offset='dd')
    fz = b.call('ent.Entity.get_zone', first)
    fb.op('JNull', reg=fz, offset='go')
    fb.op('JFalse', cond=b.call('ent.Zone.isDeepDesert', fz), offset='go')
    fb.label('dd')
    fb.op('JSGt', a=need, b=contact, offset='ab_desert')
    fb.op('Mul', dst=q, a=h, b=kill)
    fb.op('SDiv', dst=q, a=q, b=tf)
    fb.op('JSLt', a=m, b=q, offset='ab_desert')
    # go: vanilla Regroup waits until every army reached the regroup point, so the hunters next to the prey stood
    # still for the stragglers while single armies drifted into contact alone. Once the armies already within
    # LOCAL of the core (+ our cover) pass the entry test there (ENTER x threat / terrain), the order moves on to
    # Engage: everyone attacks now, the stragglers walk straight in (vanilla's own stall path does the same)
    fb.label('go')
    # ring: a contest stops the capture only from inside the village radius + Siege_Occupation_Distance 20 (code:
    # updateOccupationContenders); fighting the besiegers from weapon range outside it leaves the progress running.
    # While the occupation advances uncontested, every order army within LOCAL of the village and not fighting
    # steps to RING_IN inside its radius, on its own side; vanilla / micro take it from there
    fb.op('JNull', reg=cv, offset='noring')
    fb.op('JSLte', a=b.field(o, 'phase'), b=b.const('i32', REGROUP), offset='noring')
    rv = b.cast(cv, 'ent.Structure')
    fb.op('JNull', reg=rv, offset='noring')
    rsg = b.field(rv, 'siege')
    fb.op('JNull', reg=rsg, offset='noring')
    fb.op('JTrue', cond=b.call('ent.comp.SiegeComponent.isOccupationContested', rsg), offset='noring')
    fb.op('JSLte', a=b.call('ent.comp.SiegeComponent.getOccupationActionProgress', rsg), b=zero, offset='noring')
    rr, rd, rx, ry = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('Mov', dst=rr, src=b.call('ent.Entity.get_radius', rv))
    ur = _army_loop(fb, b, units, un, j, 'ring', 'noring')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', ur), offset='ring')
    fb.op('Mov', dst=rd, src=b.call('ent.Entity.getDistTo', ur, rv))
    fb.op('JSGt', a=rd, b=local, offset='ring')
    fb.op('Add', dst=q, a=rr, b=b.const('f64', RING_IN))
    fb.op('JSLte', a=rd, b=q, offset='ring')  # already inside
    fb.op('JSLte', a=rd, b=zero, offset='ring')
    # already walking to a point inside the ring: leave it; else re-sent at most every RING_MOVE_T s per army (a Move
    # every pass, ~0.8 s, against vanilla Engage's own march calls: Atreides' 6 contest armies stood ~213 from Yawan
    # for 30 s, 47:39-48:12, while the capture ran)
    fb.op('JFalse', cond=b.call('ent.Unit.isMoving', ur), offset='rgthr')
    rpe = b.call('ent.MobileEntity.getCurrentPathEnd', ur)
    fb.op('JNull', reg=rpe, offset='rgthr')
    rpx, rpy = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Sub', dst=rpx, a=b.field(rpe, 'x'), b=b.field(rv, 'posx'))
    fb.op('Sub', dst=rpy, a=b.field(rpe, 'y'), b=b.field(rv, 'posy'))
    fb.op('Mul', dst=rpx, a=rpx, b=rpx)
    fb.op('Mul', dst=rpy, a=rpy, b=rpy)
    fb.op('Add', dst=rpx, a=rpx, b=rpy)
    fb.op('Mul', dst=rpy, a=q, b=q)  # q = rr + RING_IN (inside)
    fb.op('JSLte', a=rpx, b=rpy, offset='ring')
    fb.label('rgthr')
    _throttle(fb, b, cx, 'ringmv', ur, RING_MOVE_T, 'ring')
    # the point rr x RING_K from the village centre towards the army
    fb.op('Mul', dst=q, a=rr, b=_ratio(fb, b, RING_K))
    fb.op('SDiv', dst=q, a=q, b=rd)
    fb.op('Sub', dst=rx, a=b.field(ur, 'posx'), b=b.field(rv, 'posx'))
    fb.op('Mul', dst=rx, a=rx, b=q)
    fb.op('Add', dst=rx, a=rx, b=b.field(rv, 'posx'))
    fb.op('Sub', dst=ry, a=b.field(ur, 'posy'), b=b.field(rv, 'posy'))
    fb.op('Mul', dst=ry, a=ry, b=q)
    fb.op('Add', dst=ry, a=ry, b=b.field(rv, 'posy'))
    _move_to(fb, b, cx, ur, rx, ry, fac)
    _log_hunt(fb, b, cx, helpers, fac, 'ring', None, ur, h, m, {'d': rd, 'r': rr})
    fb.op('JAlways', offset='ring')
    fb.label('noring')
    fb.op('JNotEq', a=b.field(o, 'phase'), b=b.const('i32', REGROUP), offset='ord')
    fb.op('Mov', dst=q, src=tm)
    ug = _army_loop(fb, b, units, un, j, 'gu', 'gudone')
    # a contest (map `hcon`) counts its whole force, sized for it at start: the capture runs while vanilla Regroup
    # gathers in place (Smugglers' 11 armies at Tabdalus 16:52-17:15, nearest still 227 away; contact 4 s before
    # the capture ended)
    fb.op('JNotNull', reg=cv, offset='gall')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ug, core), b=local, offset='gu')
    fb.label('gall')
    fb.op('Call1', dst=p, fun=pw, arg0=ug)
    fb.op('Add', dst=q, a=q, b=p)
    fb.op('JAlways', offset='gu')
    fb.label('gudone')
    fb.op('Mul', dst=tv, a=h, b=enter)
    fb.op('SDiv', dst=tv, a=tv, b=tf)
    fb.op('JSLt', a=q, b=tv, offset='ord')
    fb.op('Call1', dst=void, fun=helpers.get('nextPhase', cx.fn('logic.ai.AIOrder.nextPhase').findex.value), arg0=o)
    _log_hunt(fb, b, cx, helpers, fac, 'engage', None, first, h, q, {'sd': sd, 'dn': need, 'T': tc})
    fb.op('JAlways', offset='ord')
    fb.label('ab_nolog')
    b.call('logic.ai.AIOrder.stop', o, cancel)
    fb.op('JAlways', offset='ord')
    fb.label('ab_objective')
    b.call('logic.ai.AIOrder.stop', o, cancel)
    # start the contest at the next start pass: lift the start gap, and allow only contests for HUNT_GAP s
    # (no chase restart that this trigger would cancel again)
    tg = fb.reg(cx.t('f64'))
    fb.op('Sub', dst=tg, a=t, b=gap)
    b.call('haxe.ds.ObjectMap.set', lastmap, fb.dyn(fac), fb.dyn(tg))
    b.call('haxe.ds.ObjectMap.set', objmap, fb.dyn(fac), fb.dyn(t))
    _log_hunt(fb, b, cx, helpers, fac, 'abort', 'objective', first, h, m, {'sd': sd, 'dn': need, 'obj': found})
    fb.op('JAlways', offset='ord')
    fb.label('ab_defend')
    b.call('logic.ai.AIOrder.stop', o, cancel)
    fb.op('Mov', dst=ve, src=dfs)
    _log_hunt(fb, b, cx, helpers, fac, 'abort', 'defend', first, h, m, {'sd': sd, 'dn': need, 'obj': ve})
    fb.op('JAlways', offset='ord')
    fb.label('ab_chase')
    b.call('logic.ai.AIOrder.stop', o, cancel)
    # remember the runners: no new chase on them for GIVEUP_T s (a chase start / `chase` abort loop otherwise)
    gn = b.field(mem, 'length')
    fb.op('Mov', dst=j, src=zi)
    b.loop_head('give')
    fb.op('JSGte', a=j, b=gn, offset='givedone')
    ge = b.call('hl.types.ArrayObj.getDyn', mem, j)
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=ge, offset='give')
    b.call('haxe.ds.ObjectMap.set', givemap, ge, fb.dyn(t))
    fb.op('JAlways', offset='give')
    fb.label('givedone')
    b.call('haxe.ds.ObjectMap.set', objmap, fb.dyn(fac), fb.dyn(t))  # only contests for HUNT_GAP s: no re-chase
    _log_hunt(fb, b, cx, helpers, fac, 'abort', 'chase', first, pp, m, {'sd': sd, 'dn': need, 'T': tc})
    fb.op('JAlways', offset='ord')
    fb.label('ab_won')
    b.call('logic.ai.AIOrder.stop', o, cancel)
    # the beaten group walks home: no chase on it for GIVEUP_T s (the start pass would follow it again)
    wn = b.field(mem, 'length')
    fb.op('Mov', dst=j, src=zi)
    b.loop_head('wgive')
    fb.op('JSGte', a=j, b=wn, offset='wgivedone')
    we = b.call('hl.types.ArrayObj.getDyn', mem, j)
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=we, offset='wgive')
    b.call('haxe.ds.ObjectMap.set', givemap, we, fb.dyn(t))
    fb.op('JAlways', offset='wgive')
    fb.label('wgivedone')
    _log_hunt(fb, b, cx, helpers, fac, 'abort', 'won', first, pp, m, {'sd': sd, 'dn': need, 'obj': ve})
    fb.op('JAlways', offset='ord')
    for why in ('gone', 'truce', 'leash', 'home', 'supply', 'drift', 'lost', 'weak', 'turret', 'desert'):
        fb.label(f'ab_{why}')
        b.call('logic.ai.AIOrder.stop', o, cancel)
        if why in ('supply', 'weak', 'turret'):
            # the place beat us: no new chase there for HUNT_AREA_T s (Smugglers hunted three Fremen targets at
            # Tab-Al'san in 90 s, aborted `turret` then `supply`, running out and back). Not after `desert`: the sand
            # is the obstacle, not the place; a prey stepping back out may be chased again at once (user: else a
            # dip into the deep desert would buy an enemy a minute of safety)
            for mp, v in ((hax, b.field(first, 'posx')), (hay, b.field(first, 'posy')), (hat, t)):
                b.call('haxe.ds.ObjectMap.set', mp, fb.dyn(fac), fb.dyn(v))
        _log_hunt(fb, b, cx, helpers, fac, 'abort', why, first, h, m, {'sd': sd, 'dn': need, 'T': tc})
        fb.op('JAlways', offset='ord')
