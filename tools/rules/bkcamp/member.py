"""Base-kill campaign section: this member's pass setup and the shared move / claim helpers (`_route_move`, 
`_ours_claimed`), then the dispatch to the go or the muster."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules import bkstate as bks
from rules.worm import _do_on, _move_to
from rules.bkcamp.shared import *  # noqa: F401,F403

BC_BACK_D = 100      # a route hop this much farther from the target than the army: the plain (no worm pass) path
BC_HOP_AT = 25       # a route hop whose zone centre is this close to the army: walk straight on


def _emit_member(c):
    """This member's pass setup: the state log, the Siege-doctrine mark, our orders / armies, the shared move / claim
    helpers, and the dispatch to the go or the muster."""
    (b, be, ctrl, cx, dd, fac, fb, helpers, mm_, ph, pp, t, zero,) = _take(c, 'b be ctrl cx dd fac fb helpers mm_ ph pp t zero')
    fb.label('act')
    _throttle(fb, b, cx, 'bcst', fac, 60, 'act2')
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'state'), ('tgt', be), ('ph', fb.dyn(ph)),
                                          ('D', dd), ('M', mm_), ('P', pp),
                                          ('hp%', b.call('ent.Entity.get_lifeRatio', be))])
    fb.label('act2')
    # base-cracking prep (user 2026-10-25: "AI wants to crack the base, it prepares proper units for this"): a member
    # committed to the assault (plan level >= 2, map `bkv`) holds the doctrine's Siege mode (rules/doctrine.py: the
    # base-crack unit mix and gear, docs/strategy/DOCTRINE.md) from then on, not only from its first raze pass (the
    # mode needs CAND_T s as candidate first: at the go it came too late to re-recruit / re-gear)
    sgv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'bkv'), fb.dyn(fac))
    fb.op('JNull', reg=sgv, offset='sg_d')
    sgi = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=sgi, src=sgv)
    fb.op('JSLt', a=sgi, b=b.const('i32', 2), offset='sg_d')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'dsiege'), fb.dyn(fac), fb.dyn(t))
    fb.label('sg_d')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    my, mlen = _my_armies(fb, b, fac, 'end')
    # aimod_free rejects an army held above a chase, our own P_RALLY claim included, so the claim lapsed every
    # other pass (8 of 10 s held; review 2026-10-24): an army we claimed (map `bcmc` army -> time, within CLAIM_TTL)
    # that still holds a live P_RALLY claim stays ours
    bcmc = _global_map(fb, b, cx, bks.CLAIMED)
    ocq = fb.reg(cx.t('f64'))

    def _route_move(a_, target, direct, moved, tzone=None, tx=None, ty=None):
        """Army a_ toward entity `target` (or toward point tx, ty in zone `tzone`): the next zone of a desert-free
        zone path when that isn't the target's zone (doAction Move to its centre, then jump to `moved`); else (or no
        path / no zone) fall to `direct`."""
        u = _uid('rm')
        ae_ = fb.reg(cx.t('ent.Entity'))
        fb.op('Mov', dst=ae_, src=a_)
        az_ = b.call('ent.Entity.get_zone', ae_)
        fb.op('JNull', reg=az_, offset=direct)
        tpx, tpy = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
        if tzone is None:
            te_ = fb.reg(cx.t('ent.Entity'))
            fb.op('Mov', dst=te_, src=target)
            tz_ = b.call('ent.Entity.get_zone', te_)
            fb.op('Mov', dst=tpx, src=b.field(te_, 'posx'))
            fb.op('Mov', dst=tpy, src=b.field(te_, 'posy'))
        else:
            tz_ = fb.reg(cx.t('ent.Zone'))
            fb.op('Mov', dst=tz_, src=tzone)
            fb.op('Mov', dst=tpx, src=tx)
            fb.op('Mov', dst=tpy, src=ty)
        fb.op('JNull', reg=tz_, offset=direct)
        hop = fb.reg(cx.t('ent.Zone'))
        fb.op('Call2', dst=hop, fun=helpers['route'], arg0=az_, arg1=tz_)
        fb.op('JNull', reg=hop, offset=direct)
        fb.op('JEq', a=hop, b=tz_, offset=direct)
        hc = b.call('ent.Zone.getCenter', hop)
        fb.op('JNull', reg=hc, offset=direct)
        # a hop BC_BACK_D farther from the target than the army: the worm pass (zones with worm activity avoided) flips
        # as worms move, so take the plain path (match 66: Smugglers' capture walk to Sab-rekh went 784,1190 <->
        # 808,990 every 20 s for 4 min)
        hbq, hbt = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
        hbr = fb.reg(cx.t('f64'))
        _dist2(fb, b, ae_, tpx, tpy, hbt, hbr)
        fb.op('Mov', dst=hbt, src=b.call('hxd.$Math.sqrt', hbt))
        fb.op('Add', dst=hbt, a=hbt, b=b.const('f64', BC_BACK_D))
        fb.op('Sub', dst=hbq, a=tpx, b=b.field(hc, 'x'))
        fb.op('Mul', dst=hbq, a=hbq, b=hbq)
        fb.op('Sub', dst=hbr, a=tpy, b=b.field(hc, 'y'))
        fb.op('Mul', dst=hbr, a=hbr, b=hbr)
        fb.op('Add', dst=hbq, a=hbq, b=hbr)
        fb.op('Mul', dst=hbt, a=hbt, b=hbt)
        fb.op('JSLte', a=hbq, b=hbt, offset=u + 'f')
        fb.op('Call2', dst=hop, fun=helpers['route_nw'], arg0=az_, arg1=tz_)
        fb.op('JNull', reg=hop, offset=direct)
        fb.op('JEq', a=hop, b=tz_, offset=direct)
        fb.op('Mov', dst=hc, src=b.call('ent.Zone.getCenter', hop))
        fb.op('JNull', reg=hc, offset=direct)
        fb.label(u + 'f')
        # standing at the hop's centre already (its zone still reads the old one): straight on (match 66: two Fremen
        # Discovery troopers were sent to their own spot every pass and, as the column's rear, held it 2 min)
        hdx, hdy = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
        fb.op('Sub', dst=hdx, a=b.field(ae_, 'posx'), b=b.field(hc, 'x'))
        fb.op('Mul', dst=hdx, a=hdx, b=hdx)
        fb.op('Sub', dst=hdy, a=b.field(ae_, 'posy'), b=b.field(hc, 'y'))
        fb.op('Mul', dst=hdy, a=hdy, b=hdy)
        fb.op('Add', dst=hdx, a=hdx, b=hdy)
        fb.op('JSGte', a=hdx, b=b.const('f64', BC_HOP_AT * BC_HOP_AT), offset=u + 'm')
        fb.op('Call2', dst=hop, fun=helpers['route'], arg0=hop, arg1=tz_)  # the hop after it (review: no straight
        fb.op('JNull', reg=hop, offset=direct)  # walk over the desert from here)
        fb.op('JEq', a=hop, b=tz_, offset=direct)
        fb.op('Mov', dst=hc, src=b.call('ent.Zone.getCenter', hop))
        fb.op('JNull', reg=hc, offset=direct)
        fb.label(u + 'm')
        _move_to(fb, b, cx, a_, b.field(hc, 'x'), b.field(hc, 'y'), fac)
        fb.op('Incr', dst=n)
        fb.op('JAlways', offset=moved)

    def _ours_claimed(a_, yes, no):
        _age(fb, b, cx, bcmc, a_, t, no, dst=ocq)
        fb.op('JSGt', a=ocq, b=b.const('f64', CLAIM_TTL), offset=no)
        _rallying(fb, b, cx, a_, t, yes, no)
    add = cx.fn('logic.ai.AIOrders.addOrder')
    at = [x_.value for x_ in cx.code.types[add.type.value].definition.args]
    j = fb.reg(cx.t('i32'))
    ok = fb.reg(cx.t('bool'))
    n = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=n, src=b.const('i32', 0))
    # attrition (phase 0): only our own foothold / stepping-stone capture runs: no staging, no partner backing (match
    # 63: Smugglers' Qart-nun capture stopped when the campaign fell to attrition; user: keep expanding toward the base).
    # It takes the free armies within BC_ATT_R of the village, until BC_ATT_K x its H is sent
    att = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=att, value=False)
    ffcap, ffsp = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    ffneed = fb.reg(cx.t('f64'))  # the capture's launch need (BC_FF_K x its H), set with it
    fb.op('Mov', dst=ffneed, src=zero)
    fb.op('Mov', dst=ffcap, src=zero)
    fb.op('Mov', dst=ffsp, src=zero)
    fb.op('JEq', a=ph, b=b.const('i32', 2), offset='go')
    fb.op('JNotEq', a=ph, b=b.const('i32', 0), offset='mu_start')
    fb.op('Bool', dst=att, value=True)
    _give(c, _ours_claimed=_ours_claimed, _route_move=_route_move, add=add, at=at, att=att, bcmc=bcmc, ffcap=ffcap,
          ffneed=ffneed, ffsp=ffsp, j=j, mlen=mlen, my=my, n=n, ok=ok, orders=orders)
