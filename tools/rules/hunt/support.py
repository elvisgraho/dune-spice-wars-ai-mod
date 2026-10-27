"""Shared hunt emitters: event logs, enemy-base proximity and contest arrival checks."""
from rules.common import *  # noqa: F401,F403

HUNT_FC_T = 30  # s: a running hunt is judged on what can join its fight within this (forecast window)


def _log_hunt(fb, b, cx, helpers, fac, act, why, tgt, h, m, extra):
    d = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=d)
    b.put(d, 'e', fb.string('hunt'))
    b.put(d, 'f', fb.get(fac, 'kind'))
    b.put(d, 'act', fb.string(act))
    if why:
        b.put(d, 'why', fb.string(why))
    tent = fb.reg(cx.t('dyn'))
    fb.op('Call1', dst=tent, fun=helpers['ent'], arg0=fb.dyn(tgt))
    b.put(d, 'tgt', tent)
    b.put(d, 'H', b.to_int(h))
    b.put(d, 'M', b.to_int(m))
    for k, r in extra.items():
        if fb.regs[r] == cx.t('ent.Entity'):
            er = fb.reg(cx.t('dyn'))
            fb.op('Call1', dst=er, fun=helpers['ent'], arg0=fb.dyn(r))
            b.put(d, k, er)
        else:
            b.put(d, k, b.to_int(r) if fb.regs[r] == cx.t('f64') else r)
    b.put(d, 'x', b.to_int(b.field(tgt, 'posx')))
    b.put(d, 'y', b.to_int(b.field(tgt, 'posy')))
    v = fb.reg(cx.t('void'))
    fb.op('Call1', dst=v, fun=helpers['log'], arg0=fb.dyn(d))



def _near_base(fb, b, cx, state, fac, e, mbr, wr):
    """mbr = the active main base of a faction at war with fac nearest to entity e within BASE_KEEP (else null),
    wr = its proximity 1 - d / BASE_KEEP (0..1)."""
    k, j = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    me, d = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('f64'))
    zi = b.const('i32', 0)
    lf, lm, ok = _uid('nbf'), _uid('nbm'), _uid('nbok')
    fb.op('Null', dst=mbr)
    fb.op('Mov', dst=wr, src=b.const('f64', 0))
    facs = b.cast(fb.get(state, 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=facs, offset=ok)
    fb.op('Mov', dst=k, src=zi)
    b.loop_head(lf)
    fb.op('JSGte', a=k, b=b.field(facs, 'length'), offset=ok)
    of = b.cast(b.call('hl.types.ArrayObj.getDyn', facs, k), 'ent.Faction')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=of, offset=lf)
    fb.op('JEq', a=of, b=fac, offset=lf)
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, of), offset=lf)
    mbs = b.field(of, 'mainBases')
    fb.op('JNull', reg=mbs, offset=lf)
    fb.op('Mov', dst=j, src=zi)
    b.loop_head(lm)
    fb.op('JSGte', a=j, b=b.field(mbs, 'length'), offset=lf)
    mb = b.cast(b.call('hl.types.ArrayObj.getDyn', mbs, j), 'ent.Structure')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=mb, offset=lm)
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', mb), offset=lm)
    fb.op('Mov', dst=me, src=mb)
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', e, me))
    fb.op('SDiv', dst=d, a=d, b=b.const('f64', BASE_KEEP))
    fb.op('Sub', dst=d, a=b.const('f64', 1), b=d)
    fb.op('JSLte', a=d, b=wr, offset=lm)
    fb.op('Mov', dst=wr, src=d)
    fb.op('Mov', dst=mbr, src=me)
    fb.op('JAlways', offset=lm)
    fb.label(ok)



def _late(fb, b, cx, v, d, t, late_lbl, ok_lbl, fall=False, fac=None, eta=None):
    """Contest arrival test (start and `objective` abort alike): jump to late_lbl when an army d away (CONTEST_SPD)
    arrives after the occupation at village v ends (+ CONTEST_SLACK), else to ok_lbl (fall=True: ok falls through).
    With fac: a trip of at least RIDE_MIN while fac can ride a worm (rules/ride.py: the contest gets the worm plan)
    arrives by worm (RIDE_LEG at RIDE_SPD + RIDE_OVER, the rest walked), when that is sooner.
    eta = (aimod_eta id, army register): that army's travel time via our airfields / main base when sooner (rules/travel.py).
    Remaining time: _cap_rem (rules/common.py); a capture making no progress is never late. Returns the (arrival, remaining, progress) registers."""
    u = _uid('lt')
    lq = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=lq, src=b.const('f64', 0))
    lrem, lp = _cap_rem(fb, b, cx, v, t, u + 'ok')  # stalled / no siege: never late, worth contesting
    fb.op('SDiv', dst=lq, a=d, b=b.const('f64', CONTEST_SPD))
    if fac is not None:
        rq, rw = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
        fb.op('Mov', dst=rw, src=d)
        _ride_leg(fb, b, cx, fac, t, rw, critical=True)  # a contest may take the last free thumper; unchanged: no ride
        fb.op('JEq', a=rw, b=d, offset=u + 'nr')
        fb.op('Sub', dst=rq, a=d, b=rw)  # the ridden part
        fb.op('SDiv', dst=rq, a=rq, b=b.const('f64', RIDE_SPD))
        fb.op('SDiv', dst=rw, a=rw, b=b.const('f64', CONTEST_SPD))
        fb.op('Add', dst=rw, a=rw, b=rq)
        fb.op('Add', dst=rw, a=rw, b=b.const('f64', RIDE_OVER))
        fb.op('JSGte', a=rw, b=lq, offset=u + 'nr')
        fb.op('Mov', dst=lq, src=rw)
        fb.label(u + 'nr')
    if eta is not None and fac is not None:
        eq, ve = fb.reg(cx.t('f64')), fb.reg(cx.t('ent.Entity'))
        fb.op('JNull', reg=eta[1], offset=u + 'ne')
        fb.op('Mov', dst=ve, src=v)
        fb.op('Call3', dst=eq, fun=eta[0], arg0=fac, arg1=eta[1], arg2=ve)
        fb.op('JSGte', a=eq, b=lq, offset=u + 'ne')
        fb.op('Mov', dst=lq, src=eq)
        fb.label(u + 'ne')
    fb.op('Add', dst=lrem, a=lrem, b=b.const('f64', CONTEST_SLACK))
    fb.op('JSGt', a=lq, b=lrem, offset=late_lbl)
    fb.label(u + 'ok')
    if not fall:
        fb.op('JAlways', offset=ok_lbl)
    return lq, lrem, lp
