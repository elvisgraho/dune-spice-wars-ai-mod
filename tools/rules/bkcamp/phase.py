"""Base-kill campaign section: the shared phase machine per base (attrition / muster / go / regroup)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules import bkstate as bks
from rules.worm import _do_on, _move_to
from rules.bkcamp.shared import *  # noqa: F401,F403

BC_KILL = 1.5        # muster -> go: the mustered power >= this x the defense
BC_POT = BC_KILL * 1.1  # attrition -> muster: the coalition's whole army >= this x the base's defense (it can reach
                     # go; match 2026-10-24 13:3x: muster at P 1.44 D could never reach M 1.5 D and held its armies)
BC_POT_OUT = 1.3     # ... muster -> attrition below this (and only after BC_COMMIT in the campaign)
BC_MUSTER_MAX = 300  # s: a muster still short of go after this: go at M >= BC_EVEN x D, else back to attrition
BC_EVEN = 1.0
BC_URG_ETA = 10     # days: the leader this close to winning (map `bke`) -> urgent: the bars below replace BC_POT / BC_KILL /
BC_POT_URG = 1.2    # BC_POT_OUT (match 2026-10-24 18:00: P 1.5M vs D 1.2M all match, ETA 1 day, the coalition never
BC_KILL_URG = 1.25  # mustered; better a thin go than a leader's win)
BC_POT_OUT_URG = 1.0
BC_KEEP = 0.7        # go -> regroup: the mustered power < this x the defense
BC_HOLD = 20         # s a phase change's condition must hold
BC_COMMIT = 600      # s: no return to attrition sooner than this after leaving it
BC_REGROUP = 120     # s of regroup before mustering again
BC_GO_MAX = 300      # s: a try lasts at most this, then regroup (300: a Raze dead in Waiting gets its drop and a retry) (match 2026-10-24 15:00: one failed try, then go held
                     # to the end with nobody launching again)
BC_GO_CAP = 600      # s: a go held by its live Raze ends after this anyway ...
BC_GO_CAP_DMG = 1200 # ... this long once the base is below BC_DMG_HP of its life (keep pressing)
BC_DMG_HP = 0.97
BC_NORAZE_T = 300    # s: a go with no Raze launched by then ends in regroup (route around the desert, refill under
                     # the campaign Supply Drop at the approach ring, then strike)
BC_STALE = 30       # s: a campaign no member ran this long starts over in attrition


def _emit_phase(c):
    """The shared phase machine per base B (attrition / muster / go / regroup) and its change log."""
    (b, be, cx, dd, fac, fb, gm, helpers, ld, mm_, pp, q, st, t, zero,) = _take(c, 'b be cx dd fac fb gm helpers ld mm_ pp q st t zero')
    # the phase (shared per base)
    bcp, bcpt, bcgo = (_global_map(fb, b, cx, n) for n in (bks.PHASE, bks.PHASE_T, bks.GO))
    # the change's hold timer is per member (map `bccs` faction -> base -> since): one member's view held BC_HOLD s
    # moves the shared phase (a shared timer was reset by members seeing other numbers: Smugglers / Harkonnen read
    # P = 2 D for 3 min while Fremen's pass reset it every 10 s, match 2026-10-24 14:20)
    bccs = _fac_map(fb, b, cx, bks.COND_SINCE, fac)
    ph, nph = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=ph, src=b.const('i32', 0))
    pv = b.call('haxe.ds.ObjectMap.get', bcp, fb.dyn(be))
    fb.op('JNull', reg=pv, offset='ph_n')
    fb.op('SafeCast', dst=ph, src=pv)
    fb.label('ph_n')
    since = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=since, src=t)
    sv = b.call('haxe.ds.ObjectMap.get', bcpt, fb.dyn(be))
    fb.op('JNull', reg=sv, offset='pt_n')
    fb.op('SafeCast', dst=since, src=sv)
    fb.label('pt_n')
    # a campaign nobody ran for BC_STALE s (the plan stopped: level drop, truce) starts over in attrition (map
    # `bcseen` base -> last pass; a stale muster / go phase fired its timeouts at once on resume; review 2026-10-24)
    bcseen = _global_map(fb, b, cx, bks.SEEN)
    snq = _age(fb, b, cx, bcseen, be, t, 'seen_ok')
    fb.op('JSLte', a=snq, b=b.const('f64', BC_STALE), offset='seen_ok')
    fb.op('Mov', dst=ph, src=b.const('i32', 0))
    fb.op('Mov', dst=since, src=t)
    b.call('haxe.ds.ObjectMap.set', bcp, fb.dyn(be), fb.dyn(ph))
    b.call('haxe.ds.ObjectMap.set', bcpt, fb.dyn(be), fb.dyn(t))
    fb.label('seen_ok')
    b.call('haxe.ds.ObjectMap.set', bcseen, fb.dyn(be), fb.dyn(t))
    el = fb.reg(cx.t('f64'))
    fb.op('Sub', dst=el, a=t, b=since)
    fb.op('Mov', dst=nph, src=ph)
    thr = fb.reg(cx.t('f64'))
    # the bars: urgent (the leader's ETA <= BC_URG_ETA) or normal
    kpot, kkill, kout = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    urg = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=urg, value=False)
    fb.op('Mov', dst=kpot, src=_ratio(fb, b, BC_POT))
    fb.op('Mov', dst=kkill, src=_ratio(fb, b, BC_KILL))
    fb.op('Mov', dst=kout, src=_ratio(fb, b, BC_POT_OUT))
    uev = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'bke'), fb.dyn(ld))
    fb.op('JNull', reg=uev, offset='urg_d')
    uq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=uq, src=uev)
    fb.op('JSGt', a=uq, b=b.const('f64', BC_URG_ETA), offset='urg_d')
    fb.op('Bool', dst=urg, value=True)
    fb.op('Mov', dst=kpot, src=_ratio(fb, b, BC_POT_URG))
    fb.op('Mov', dst=kkill, src=_ratio(fb, b, BC_KILL_URG))
    fb.op('Mov', dst=kout, src=_ratio(fb, b, BC_POT_OUT_URG))
    fb.label('urg_d')
    fb.op('JSLte', a=dd, b=zero, offset='p_none')  # no defense reading (forecast failed): every bar would be 0
    for n_ in range(4):
        fb.op('JEq', a=ph, b=b.const('i32', n_), offset=f'p{n_}')
    fb.op('JAlways', offset='p_none')
    fb.label('p0')  # attrition -> muster
    fb.op('Mul', dst=thr, a=dd, b=kpot)
    fb.op('JSLt', a=pp, b=thr, offset='p_none')
    fb.op('Mov', dst=nph, src=b.const('i32', 1))
    fb.op('JAlways', offset='p_cond')
    fb.label('p1')  # muster -> go / attrition
    fb.op('Mul', dst=thr, a=dd, b=kkill)
    fb.op('JSLt', a=mm_, b=thr, offset='p1b')
    fb.op('Mov', dst=nph, src=b.const('i32', 2))
    fb.op('JAlways', offset='p_cond')
    fb.label('p1b')
    # a muster that doesn't reach go within BC_MUSTER_MAX: go at an even fight, else attrition (no muster holding the
    # armies forever)
    fb.op('JSLt', a=el, b=b.const('f64', BC_MUSTER_MAX), offset='p1c')
    fb.op('Mul', dst=thr, a=dd, b=_ratio(fb, b, BC_EVEN))
    fb.op('JSLt', a=mm_, b=thr, offset='p1c')
    fb.op('Mov', dst=nph, src=b.const('i32', 2))
    fb.op('JAlways', offset='p_set')
    fb.label('p1c')
    # back to attrition only BC_COMMIT s after leaving it (map `bcat` base -> time) and with the potential gone
    # (the old test measured the time since the last phase change and never fired: review 2026-10-24)
    atq = _age(fb, b, cx, _global_map(fb, b, cx, bks.LEFT_ATT), be, t, 'p1o')
    fb.op('JSLt', a=atq, b=b.const('f64', BC_COMMIT), offset='p_none')
    fb.label('p1o')
    fb.op('Mul', dst=thr, a=dd, b=kout)
    fb.op('JSGte', a=pp, b=thr, offset='p_none')
    fb.op('Mov', dst=nph, src=b.const('i32', 0))
    fb.op('JAlways', offset='p_cond')
    fb.label('p2')  # go -> regroup: the try's time is up, or too weak to go on, or nobody razed
    fb.op('Mov', dst=nph, src=b.const('i32', 3))
    fb.op('JSLt', a=el, b=b.const('f64', BC_GO_MAX), offset='p2t')
    gcap = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=gcap, src=b.const('f64', BC_GO_CAP))
    # a damaged base (no regen: REVERSING 'Main-base Raze') keeps the go longer
    fb.op('JSGte', a=b.call('ent.Entity.get_lifeRatio', be), b=_ratio(fb, b, BC_DMG_HP), offset='gcap_d')
    fb.op('Mov', dst=gcap, src=b.const('f64', BC_GO_CAP_DMG))
    fb.label('gcap_d')
    fb.op('JSGte', a=el, b=gcap, offset='p_set')  # never longer than the cap
    # time is up, unless this go's Raze still lives (map `bclo`, launched at >= the go time, units left): the go
    # holds while it does, so the supporters keep fighting (user 2026-10-24: Fremen committed while the others
    # mustered back: the go timed out at 240 s with Fremen's Raze on Arrakeen at 87%)
    rgv = b.call('haxe.ds.ObjectMap.get', bcgo, fb.dyn(be))
    fb.op('JNull', reg=rgv, offset='p_set')
    rgq, rlq = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=rgq, src=rgv)
    rbcl, rbclo = _global_map(fb, b, cx, bks.LAUNCH), _global_map(fb, b, cx, bks.LAUNCH_ORDER)
    rfs = b.cast(fb.get(st, 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=rfs, offset='p_set')
    rk_ = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=rk_, src=b.const('i32', 0))
    b.loop_head('p2r')
    fb.op('JSGte', a=rk_, b=b.field(rfs, 'length'), offset='p_set')  # no live Raze: regroup now
    rfx = b.call('hl.types.ArrayObj.getDyn', rfs, rk_)
    fb.op('Incr', dst=rk_)
    rbv = b.call('haxe.ds.ObjectMap.get', rbcl, rfx)
    fb.op('JNull', reg=rbv, offset='p2r')
    fb.op('SafeCast', dst=rlq, src=rbv)
    fb.op('JSLt', a=rlq, b=rgq, offset='p2r')
    rov = b.call('haxe.ds.ObjectMap.get', rbclo, rfx)
    fb.op('JNull', reg=rov, offset='p2dr')
    rou = b.field(b.cast(rov, 'logic.ai.AIOrder'), 'units')
    fb.op('JNull', reg=rou, offset='p2r')
    fb.op('JSLte', a=b.field(rou, 'length'), b=b.const('i32', 0), offset='p2r')
    fb.op('JAlways', offset='p2t')
    # ... or its direct raze (no order: map `bcdr` faction -> last pass) ran within 15 s (match 42: 6-14 armies walking
    # 740-960 from their land were called back by the regroup at 300 s)
    fb.label('p2dr')
    rdv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.RAZE_ACT), rfx)
    fb.op('JNull', reg=rdv, offset='p2r')
    fb.op('SafeCast', dst=rlq, src=rdv)
    fb.op('Sub', dst=rlq, a=t, b=rlq)
    fb.op('JSGt', a=rlq, b=b.const('f64', BK_DR_LIVE), offset='p2r')
    fb.label('p2t')
    # no Raze launched by any member BC_GO_WIN + 15 s into the go (no army passed the supply filter): the go ends
    # (user 2026-10-24: Fremen moved forwards and backwards: with no Raze every member only fought / approached)
    fb.op('JSLt', a=el, b=b.const('f64', BC_NORAZE_T), offset='p2k')
    pgv = b.call('haxe.ds.ObjectMap.get', bcgo, fb.dyn(be))
    fb.op('JNull', reg=pgv, offset='p2k')
    pgq, plq = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=pgq, src=pgv)
    pbcl = _global_map(fb, b, cx, bks.LAUNCH)
    pfs = b.cast(fb.get(st, 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=pfs, offset='p2k')
    pk_ = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=pk_, src=b.const('i32', 0))
    b.loop_head('p2l')
    fb.op('JSGte', a=pk_, b=b.field(pfs, 'length'), offset='p_set')  # nobody launched: regroup now
    pfx = b.call('hl.types.ArrayObj.getDyn', pfs, pk_)
    fb.op('Incr', dst=pk_)
    pbv = b.call('haxe.ds.ObjectMap.get', pbcl, pfx)
    fb.op('JNull', reg=pbv, offset='p2l')
    fb.op('SafeCast', dst=plq, src=pbv)
    fb.op('JSLt', a=plq, b=pgq, offset='p2l')
    fb.label('p2k')
    fb.op('Mov', dst=nph, src=ph)
    fb.op('Mul', dst=thr, a=dd, b=_ratio(fb, b, BC_KEEP))
    fb.op('JSGte', a=gm, b=thr, offset='p_none')  # the strongest member's M (above)
    fb.op('Mov', dst=nph, src=b.const('i32', 3))
    fb.op('JAlways', offset='p_cond')
    fb.label('p3')  # regroup -> muster after BC_REGROUP
    fb.op('JSLt', a=el, b=b.const('f64', BC_REGROUP), offset='p_none')
    fb.op('Mov', dst=nph, src=b.const('i32', 1))
    fb.op('JAlways', offset='p_set')  # a timed change: no hold
    fb.label('p_none')
    b.call('haxe.ds.ObjectMap.remove', bccs, fb.dyn(be))
    fb.op('JAlways', offset='act')
    fb.label('p_cond')  # the change's condition must hold BC_HOLD s, in the phase it started in (map `bccp`: another
    # member's change left a running timer that then moved the next phase within 5 s; review 2026-10-24)
    bccp = _fac_map(fb, b, cx, bks.COND_PHASE, fac)
    bccn = _fac_map(fb, b, cx, bks.COND_TO, fac)
    cv = b.call('haxe.ds.ObjectMap.get', bccs, fb.dyn(be))
    fb.op('JNull', reg=cv, offset='p_start')
    cpv = b.call('haxe.ds.ObjectMap.get', bccp, fb.dyn(be))
    fb.op('JNull', reg=cpv, offset='p_start')
    cpi = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=cpi, src=cpv)
    fb.op('JNotEq', a=cpi, b=ph, offset='p_start')
    cnv = b.call('haxe.ds.ObjectMap.get', bccn, fb.dyn(be))
    fb.op('JNull', reg=cnv, offset='p_start')
    fb.op('SafeCast', dst=cpi, src=cnv)
    fb.op('JEq', a=cpi, b=nph, offset='p_held')
    fb.label('p_start')
    b.call('haxe.ds.ObjectMap.set', bccs, fb.dyn(be), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', bccp, fb.dyn(be), fb.dyn(ph))
    b.call('haxe.ds.ObjectMap.set', bccn, fb.dyn(be), fb.dyn(nph))
    fb.op('JAlways', offset='act')
    fb.label('p_held')
    fb.op('SafeCast', dst=q, src=cv)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSLt', a=q, b=b.const('f64', BC_HOLD), offset='act')
    fb.label('p_set')
    b.call('haxe.ds.ObjectMap.remove', bccs, fb.dyn(be))
    b.call('haxe.ds.ObjectMap.set', bcp, fb.dyn(be), fb.dyn(nph))
    b.call('haxe.ds.ObjectMap.set', bcpt, fb.dyn(be), fb.dyn(t))
    fb.op('JNotEq', a=ph, b=b.const('i32', 0), offset='p_at')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.LEFT_ATT), fb.dyn(be), fb.dyn(t))  # left attrition
    fb.label('p_at')
    fb.op('JNotEq', a=nph, b=b.const('i32', 2), offset='p_log')
    b.call('haxe.ds.ObjectMap.set', bcgo, fb.dyn(be), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.clear', _global_map(fb, b, cx, bks.CUT))  # a new go: cuts start over
    b.call('haxe.ds.ObjectMap.remove', _global_map(fb, b, cx, bks.STRIKE), fb.dyn(be))  # ... and the strike
    fb.label('p_log')
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'phase'), ('tgt', be), ('from', fb.dyn(ph)),
                                          ('to', fb.dyn(nph)), ('D', dd), ('M', mm_), ('P', pp), ('urg', urg),
                                          ('hp%', b.call('ent.Entity.get_lifeRatio', be))])
    fb.op('Mov', dst=ph, src=nph)
    # this member's part
    _give(c, bcgo=bcgo, n_=n_, ph=ph)
