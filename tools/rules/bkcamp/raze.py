"""Base-kill campaign section: the direct raze (waves, one column, field-army / turret-village targets, the drop
step-in, the siege of B, the go hold, the occupation Raze)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules import bkstate as bks
from rules.worm import _do_on, _move_to
from rules.bkcamp.shared import *  # noqa: F401,F403

BC_COH_FAR = 1450    # one column: a walker farther than this from the base is no anchor (a straggler far behind)
BC_RAZE_SHARE = 0.4  # a Raze needs this share of the member's campaign power ready
BC_RAZE_T = 8        # s: one Raze launch per member this often at most
BC_DR_SUP = 0.15     # ... unless below this supply share (starving; 0.3 dropped Fremen's walkers 550 out, before the
                     # drop at the attack could refill them, match 55)
BC_WALK_SPD = 6      # units / s an army walks (match 52: 400 -> 176 in 40 s, 820 -> 534 in 45 s): staggered departure
BC_WAIT_MAX = 150    # s after the strike: nobody waits longer
BC_SD_IN_T = 6       # direct raze: with our drop on the base's zone, an army outside it is walked in this often
BC_GUARD_R = 120     # ... while we occupy it, a field army counts only this close to it (the wave guards the occupation)
BC_TUR_R = 220       # direct raze: the base owner's turreted village this close to B is besieged before the base
BC_FIELD_R = 300     # direct raze: an at-war army this close to B is fought first (the strongest visible) ...
BC_FIELD_K = 0.3     # ... only while the owner's visible armies there are >= this x ours within BC_DR_AT of B
BC_FIELD_K_KEEP = 0.2  # ... a sticky one is kept down to this x ours (hysteresis)
BC_FIELD_T = 4       # ... its ArmyFight re-sent at most this often per army
BC_COH_WAIT = 60     # ... on our own land only, at most this many s
BC_COH = 150         # direct raze: an army this much nearer the base than its member's rearmost walker waits for it
BC_DR_PACK_K = 0.75  # ... the armies at the strike point leave once they hold this share of all its walkers' power
BC_WAVE_JOIN = 40    # ... an army reaching the strike point this many s after its wave left follows it
BC_WAVE2_K = 0.5     # ... a second wave in the same go needs this share of the first wave's power
BC_PACK_WORM_T = 40  # ... and no walker of ours waits out a worm (it holds the wave at most this many s)


def _emit_raze(c):
    """The direct raze: waves at the strike point, one column, the field-army / turret-village targets, the drop step-in,
    the siege of B, the go hold and the occupation Raze."""
    (_route_move, add, apok, apx, apy, apz, at, b, bcl, bcmc, be, ctrl, cx, dd, fac, fb, garr, gminr, gt, helpers,
     lb, ld, mm_, n, nbusy, ndd, nlow, ok, orders, pw, rarr, st, stg, t, zero,) = _take(c, '_route_move add apok apx apy apz at b bcl bcmc be ctrl cx dd fac fb garr gminr gt helpers lb ld mm_ '
        'n nbusy ndd nlow ok orders pw rarr st stg t zero')
    fb.label('go_dr')
    b.call('haxe.ds.ObjectMap.set', bcl, fb.dyn(fac), fb.dyn(t))
    # staggered departure, one arrival: each member posts its walk from its strike point (our land's edge: no drain
    # while waiting there) to the base (maps `bcwd` / `bcwdt`); the farthest leaves at the strike, a nearer one
    # (farthest - its walk) / BC_WALK_SPD s later, so all reach the base together (match 52: Harkonnen from 400 out
    # arrived 60 s before Fremen from 820 and Smugglers after them, each beaten alone; user: no waiting in enemy land)
    dwd, dwq, dwm = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=dwd, src=zero)
    fb.op('JFalse', cond=apok, offset='dw_post')
    fb.op('Sub', dst=dwq, a=apx, b=b.field(be, 'posx'))
    fb.op('Mul', dst=dwq, a=dwq, b=dwq)
    fb.op('Sub', dst=dwm, a=apy, b=b.field(be, 'posy'))
    fb.op('Mul', dst=dwm, a=dwm, b=dwm)
    fb.op('Add', dst=dwq, a=dwq, b=dwm)
    fb.op('Mov', dst=dwd, src=b.call('hxd.$Math.sqrt', dwq))
    fb.label('dw_post')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.WALK), fb.dyn(fac), fb.dyn(dwd))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.WALK_T), fb.dyn(fac), fb.dyn(t))
    dskv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.STRIKE), fb.dyn(be))
    fb.op('JNull', reg=dskv, offset='dw_go')
    dsk = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=dsk, src=dskv)
    fb.op('Sub', dst=dsk, a=t, b=dsk)  # s since the strike
    fb.op('JSGte', a=dsk, b=b.const('f64', BC_WAIT_MAX), offset='dw_go')
    fb.op('Mov', dst=dwm, src=dwd)  # the farthest fresh walk
    dwfs = b.cast(fb.get(st, 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=dwfs, offset='dw_go')
    dwk = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=dwk, src=b.const('i32', 0))
    b.loop_head('dwl')
    fb.op('JSGte', a=dwk, b=b.field(dwfs, 'length'), offset='dwld')
    dwfx = b.call('hl.types.ArrayObj.getDyn', dwfs, dwk)
    fb.op('Incr', dst=dwk)
    dwtv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.WALK_T), dwfx)
    fb.op('JNull', reg=dwtv, offset='dwl')
    fb.op('SafeCast', dst=dwq, src=dwtv)
    fb.op('Sub', dst=dwq, a=t, b=dwq)
    fb.op('JSGt', a=dwq, b=b.const('f64', 2 * BC_T + 1), offset='dwl')
    dwvv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.WALK), dwfx)
    fb.op('JNull', reg=dwvv, offset='dwl')
    fb.op('SafeCast', dst=dwq, src=dwvv)
    fb.op('JSLte', a=dwq, b=dwm, offset='dwl')
    fb.op('Mov', dst=dwm, src=dwq)
    fb.op('JAlways', offset='dwl')
    fb.label('dwld')
    fb.op('Sub', dst=dwq, a=dwm, b=dwd)
    fb.op('SDiv', dst=dwq, a=dwq, b=b.const('f64', BC_WALK_SPD))  # this member's delay
    fb.op('JSGte', a=dsk, b=dwq, offset='dw_go')
    # not yet: our armies wait at (or march to) our strike point on our own land
    _throttle(fb, b, cx, 'bcwl', fac, 20, 'gap')
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'wait'), ('tgt', be), ('d', dwd),
                                          ('dmax', dwm), ('left', dsk), ('delay', dwq)])
    fb.op('JAlways', offset='gap')
    fb.label('dw_go')
    dns, dfg = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=n, src=b.const('i32', 0))
    fb.op('Mov', dst=dns, src=b.const('i32', 0))
    fb.op('Mov', dst=dfg, src=b.const('i32', 0))  # ours fighting near the base
    dk = fb.reg(cx.t('i32'))
    dq, dmn = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=dmn, src=b.const('f64', 1 << 20))
    # one column: the rearmost walker's distance to the base (not fighting, not dying, beyond BC_DR_AT); an army more
    # than BC_COH nearer the base than it waits (user 2026-10-25: Fremen's 10 armies walked strung out over 300+, each
    # at its own speed and worm stops, and arrived one by one)
    dleft = fb.reg(cx.t('bool'))  # a wave left from the ring this pass
    fb.op('Bool', dst=dleft, value=False)
    drear = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=drear, src=zero)
    drk = fb.reg(cx.t('i32'))
    drx_ = _army_loop(fb, b, garr, b.field(garr, 'length'), drk, 'drr', 'drrd')
    fb.op('JNotNull', reg=b.field(drx_, 'harvestComponent'), offset='drr')
    fb.op('JSLt', a=b.call('ent.Entity.get_lifeRatio', drx_), b=_ratio(fb, b, LIFE_CRIT), offset='drr')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', drx_), offset='drr')
    drkv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.SENT), fb.dyn(drx_))  # one we send (not resupplying)
    fb.op('JNull', reg=drkv, offset='drr')
    fb.op('SafeCast', dst=dq, src=drkv)
    fb.op('Sub', dst=dq, a=t, b=dq)
    fb.op('JSGt', a=dq, b=b.const('f64', BC_CLAIM_KEEP), offset='drr')
    # with a strike point only a wave member of this go anchors the column (review 2026-10-25: an army parked for the
    # next go held the wave on its way in)
    fb.op('JFalse', cond=apok, offset='drr_ok')
    bks.wave_left(fb, b, cx, drx_, 'drr', dst=dq)
    fb.op('JSLt', a=dq, b=gt, offset='drr')
    fb.label('drr_ok')
    fb.op('Mov', dst=dq, src=b.call('ent.Entity.getDistTo', drx_, be))
    fb.op('JSLte', a=dq, b=b.const('f64', BC_DR_AT), offset='drr')
    fb.op('JSGt', a=dq, b=b.const('f64', BC_COH_FAR), offset='drr')  # a straggler far behind: no anchor
    fb.op('JSLte', a=dq, b=drear, offset='drr')
    fb.op('Mov', dst=drear, src=dq)
    fb.op('JAlways', offset='drr')
    fb.label('drrd')
    # whole-army waves (user 2026-10-25, match 61: Harkonnen's armies came free one at a time and each walked into
    # Arrakeen's guns alone; "people go for the base with whole armies for impact"): an army behind our strike point
    # goes there first; the armies at it leave once they hold BC_DR_PACK_K of all our walkers' power (dpk at the strike
    # point, dall all walkers beyond BC_DR_AT); after this go's wave left (map `bcdep` faction -> time), later
    # arrivals wait there for the next go
    dpk, dall, dpp = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=dpk, src=zero)
    fb.op('Mov', dst=dall, src=zero)
    dpq = fb.reg(cx.t('f64'))
    dwh = fb.reg(cx.t('f64'))  # ... of which waiting out a worm (aimod_wormonly)
    fb.op('Mov', dst=dwh, src=zero)
    dwhb = fb.reg(cx.t('bool'))
    fb.op('JFalse', cond=apok, offset='drpd')
    dpx_ = _army_loop(fb, b, garr, b.field(garr, 'length'), drk, 'drp', 'drpd')
    fb.op('JNotNull', reg=b.field(dpx_, 'harvestComponent'), offset='drp')
    # only an army the raze holds (`bcmc` within BC_CLAIM_KEEP: it passed the order / starving filters last pass;
    # review 2026-10-25: armies on vanilla's Resupply / heal orders kept the pack from ever leaving)
    _age(fb, b, cx, bcmc, dpx_, t, 'drp', dst=dpq)
    fb.op('JSGt', a=dpq, b=b.const('f64', BC_CLAIM_KEEP), offset='drp')
    fb.op('JSLt', a=b.call('ent.Entity.get_lifeRatio', dpx_), b=_ratio(fb, b, LIFE_CRIT), offset='drp')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', dpx_), offset='drp')
    _refill_gate(fb, b, cx, dpx_, 'drp', 'drp_s', q=dpq)  # refilling: not waited for
    # only one that hasn't left with a wave of this go (map `bcdpa`), within BC_DR_AT too (the strike point may lie
    # inside): a second wave is measured against the armies still here
    bks.wave_left(fb, b, cx, dpx_, 'drp_far', dst=dpq)
    fb.op('JSGte', a=dpq, b=gt, offset='drp')
    fb.label('drp_far')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', dpx_, be), b=b.const('f64', BC_COH_FAR), offset='drp')  # far: no
    fb.op('Call1', dst=dpp, fun=pw, arg0=dpx_)
    fb.op('Add', dst=dall, a=dall, b=dpp)
    fb.op('Call1', dst=dwhb, fun=helpers['wormonly'], arg0=dpx_)
    fb.op('JFalse', cond=dwhb, offset='drp_nw')
    fb.op('Add', dst=dwh, a=dwh, b=dpp)
    fb.label('drp_nw')
    _dist2(fb, b, dpx_, apx, apy, dpq, dwm)
    fb.op('JSGt', a=dpq, b=b.const('f64', BC_AT_RING * BC_AT_RING), offset='drp')
    fb.op('Add', dst=dpk, a=dpk, b=dpp)
    fb.op('JAlways', offset='drp')
    fb.label('drpd')
    dgone = fb.reg(cx.t('bool'))  # this go's wave already left
    fb.op('Bool', dst=dgone, value=False)
    dgv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.WAVE_GONE), fb.dyn(fac))
    fb.op('JNull', reg=dgv, offset='dg_d')
    fb.op('SafeCast', dst=dpq, src=dgv)
    fb.op('JSLt', a=dpq, b=gt, offset='dg_d')
    fb.op('Bool', dst=dgone, value=True)
    fb.label('dg_d')
    # the field army first (user 2026-10-25, match 67: Fremen's wave split at Arrakeen, some sieging, some fighting an
    # A_Soldier, some pulled home; "it could have focused Atreides' units first"): the strongest visible armed at-war
    # army within BC_FIELD_R of B (sticky in map `bcfa` faction -> it while alive, visible and in range) is the target
    # of every wave army inside BC_DR_AT; the base after it. Log `bcamp` act field (tgt, pw)
    fte = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=fte)
    ftbar = fb.reg(cx.t('f64'))  # the threat bar: BC_FIELD_K to take a new one, BC_FIELD_K_KEEP to keep the sticky one
    fb.op('Mov', dst=ftbar, src=_ratio(fb, b, BC_FIELD_K))
    ftq, ftb = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    bcft = _global_map(fb, b, cx, bks.FIELD)
    ftv = b.call('haxe.ds.ObjectMap.get', bcft, fb.dyn(fac))
    fb.op('JNull', reg=ftv, offset='ft_s')
    fb.op('SafeCast', dst=fte, src=ftv)
    fb.op('JNull', reg=fte, offset='ft_s')
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', fte), offset='ft_x')
    fb.op('JNotEq', a=b.call('ent.Entity.get_owner', fte), b=ld, offset='ft_x')
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', fte, fac), offset='ft_x')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', fte, be), b=b.const('f64', BC_FIELD_R), offset='ft_x')
    fb.op('Mov', dst=ftbar, src=_ratio(fb, b, BC_FIELD_K_KEEP))  # hysteresis (the target flipped on / off at the bar)
    fb.op('JAlways', offset='ft_d')
    fb.label('ft_x')
    fb.op('Null', dst=fte)
    fb.label('ft_s')
    fb.op('Mov', dst=ftb, src=zero)
    ftar = b.field(st, 'armies')
    fb.op('JNull', reg=ftar, offset='ft_d')
    ftk = fb.reg(cx.t('i32'))
    ftx = _army_loop(fb, b, ftar, b.field(ftar, 'length'), ftk, 'ftl', 'ft_d')
    fto = b.call('ent.Entity.get_owner', ftx)
    fb.op('JNull', reg=fto, offset='ftl')
    fb.op('JNotEq', a=fto, b=ld, offset='ftl')  # the base owner's (a partner at war with us is not the target)
    fb.op('JNotNull', reg=b.field(ftx, 'harvestComponent'), offset='ftl')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ftx, be), b=b.const('f64', BC_FIELD_R), offset='ftl')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', st, fac, fto), offset='ftl')
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', ftx, fac), offset='ftl')
    fb.op('Call1', dst=ftq, fun=pw, arg0=ftx)
    fb.op('JSLte', a=ftq, b=ftb, offset='ftl')
    fb.op('Mov', dst=ftb, src=ftq)
    fb.op('Mov', dst=fte, src=ftx)
    fb.op('JAlways', offset='ftl')
    fb.label('ft_d')
    # ... only while the base owner's visible armies within BC_FIELD_R are a real threat: >= BC_FIELD_K x our armies
    # within BC_DR_AT of B (match 69: the waves chased one fresh 40-48k A_Trooper after another for 600 s and Arrakeen
    # lost 1%; a lone spawn is left to vanilla's fight micro and the base comes first)
    fb.op('JNull', reg=fte, offset='ft_rm')
    fts, fto2 = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=fts, src=zero)
    fb.op('Mov', dst=fto2, src=zero)
    ftar2 = b.field(st, 'armies')
    fb.op('JNull', reg=ftar2, offset='fts_d')
    ftk2 = fb.reg(cx.t('i32'))
    ftx2 = _army_loop(fb, b, ftar2, b.field(ftar2, 'length'), ftk2, 'fts', 'fts_d')
    fb.op('JNotNull', reg=b.field(ftx2, 'harvestComponent'), offset='fts')
    ftw = b.call('ent.Entity.get_owner', ftx2)
    fb.op('JNull', reg=ftw, offset='fts')
    fb.op('JEq', a=ftw, b=fac, offset='fts_m')
    fb.op('JNotEq', a=ftw, b=ld, offset='fts')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ftx2, be), b=b.const('f64', BC_FIELD_R), offset='fts')
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', ftx2, fac), offset='fts')
    fb.op('Call1', dst=ftq, fun=pw, arg0=ftx2)
    fb.op('Add', dst=fts, a=fts, b=ftq)
    fb.op('JAlways', offset='fts')
    fb.label('fts_m')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ftx2, be), b=b.const('f64', BC_DR_AT), offset='fts')
    fb.op('Call1', dst=ftq, fun=pw, arg0=ftx2)
    fb.op('Add', dst=fto2, a=fto2, b=ftq)
    fb.op('JAlways', offset='fts')
    fb.label('fts_d')
    fb.op('Mul', dst=ftq, a=fto2, b=ftbar)
    fb.op('JSGte', a=fts, b=ftq, offset='ft_k2')
    fb.op('Null', dst=fte)
    fb.op('JAlways', offset='ft_rm')
    fb.label('ft_k2')
    b.call('haxe.ds.ObjectMap.set', bcft, fb.dyn(fac), fb.dyn(fte))
    _throttle(fb, b, cx, 'bcfal', fac, 30, 'ft_e')
    fb.op('Call1', dst=ftq, fun=pw, arg0=fte)
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'field'), ('tgt', fte), ('pw', ftq)])
    fb.op('JAlways', offset='ft_e')
    fb.label('ft_rm')
    b.call('haxe.ds.ObjectMap.remove', bcft, fb.dyn(fac))
    fb.label('ft_e')
    # turret villages first (user 2026-10-25, match 70: villages next to the base have turrets that reach our base
    # attack; "annex them or liberate"): the base owner's village within BC_TUR_R of B with turrets (aimod_cover1 at it
    # > 0), not besieged / occupied by another faction, nearest our staging side, is the wave's siege target before
    # the base (after the field army). Occupied by us with no occupation action: Annex, else Liberate, else Pillage
    # (startOccupationAction; the first that starts one). Map `bctv` faction -> it; log `bcamp` act turret (tgt, c, r)
    tve = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=tve)
    tvbd, tvq = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=tvbd, src=b.const('f64', 1 << 20))
    tvna = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=tvna)
    tvs = b.cast(fb.get(ld, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=tvs, offset='tv_d')
    tvk = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=tvk, src=b.const('i32', 0))
    tvse = fb.reg(cx.t('ent.Entity'))
    b.loop_head('tvl')
    fb.op('JSGte', a=tvk, b=b.field(tvs, 'length'), offset='tv_d')
    tvst = b.cast(b.call('hl.types.ArrayObj.getDyn', tvs, tvk), 'ent.Structure')
    fb.op('Incr', dst=tvk)
    fb.op('JNull', reg=tvst, offset='tvl')
    fb.op('Mov', dst=tvse, src=tvst)
    fb.op('JEq', a=tvse, b=be, offset='tvl')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', tvse, be), b=b.const('f64', BC_TUR_R), offset='tvl')
    tvsg = b.field(tvst, 'siege')
    fb.op('JNull', reg=tvsg, offset='tvl')
    tvbf = b.field(tvsg, 'besiegingFaction')
    fb.op('JNull', reg=tvbf, offset='tv_bs')
    fb.op('JNotEq', a=tvbf, b=fac, offset='tvl')  # another faction's siege (one besieger per structure)
    fb.label('tv_bs')
    tvof = b.call('ent.comp.SiegeComponent.getOccupierFaction', tvsg)
    fb.op('JNull', reg=tvof, offset='tv_oc')
    fb.op('JNotEq', a=tvof, b=fac, offset='tvl')
    fb.label('tv_oc')
    # ours under siege / occupied: its turrets are silent (aimod_cover1 reads 0) but it stays the target until the
    # occupation is done (it is no longer the owner's): the wave guards the running Annex / Liberate / Pillage (user
    # 2026-10-25, match 73: Fremen ran from its Liberate of Aswtah the moment it began; no supply is lost there)
    fb.op('JEq', a=tvbf, b=fac, offset='tv_dd')
    fb.op('JEq', a=tvof, b=fac, offset='tv_dd')
    fb.op('Call3', dst=tvq, fun=helpers['cover1'], arg0=tvse, arg1=tvst, arg2=tvna)
    fb.op('JSLte', a=tvq, b=zero, offset='tvl')
    fb.label('tv_dd')
    fb.op('Mov', dst=tvq, src=b.call('ent.Entity.getDistTo', tvse, be))
    fb.op('JNull', reg=stg, offset='tv_pk')
    fb.op('Mov', dst=tvq, src=b.call('ent.Entity.getDistTo', tvse, stg))
    fb.label('tv_pk')
    fb.op('JSGte', a=tvq, b=tvbd, offset='tvl')
    fb.op('Mov', dst=tvbd, src=tvq)
    fb.op('Mov', dst=tve, src=tvse)
    fb.op('JAlways', offset='tvl')
    fb.label('tv_d')
    # our occupation of it runs: the wave guards it, so a field army counts only when it comes within BC_GUARD_R of the
    # village (user 2026-10-25, match 74: at Ha-ron the field target A_Hero_1 140-190 out pulled half the wave away
    # every few s while vanilla's occupation walked it back to the village: splits and flip-flops)
    fb.op('JNull', reg=tve, offset='tv_e')
    fb.op('JNull', reg=fte, offset='tvg_d')
    tvsg3 = b.field(b.cast(fb.dyn(tve), 'ent.Structure'), 'siege')
    fb.op('JNull', reg=tvsg3, offset='tvg_d')
    fb.op('JNotEq', a=b.call('ent.comp.SiegeComponent.getOccupierFaction', tvsg3), b=fac, offset='tvg_d')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', fte, tve), b=b.const('f64', BC_GUARD_R), offset='tvg_d')
    fb.op('Null', dst=fte)
    fb.label('tvg_d')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.TURRET), fb.dyn(fac), fb.dyn(tve))
    tvr = fb.reg(cx.code.types[cx.fn('ent.comp.SiegeComponent.startOccupationAction').type.value].definition.ret.value)
    fb.op('Null', dst=tvr)
    tvsg2 = b.field(b.cast(fb.dyn(tve), 'ent.Structure'), 'siege')
    fb.op('JNull', reg=tvsg2, offset='tv_log')
    fb.op('JNotEq', a=b.call('ent.comp.SiegeComponent.getOccupierFaction', tvsg2), b=fac, offset='tv_log')
    fb.op('JNotNull', reg=b.field(tvsg2, 'occupationAction'), offset='tv_log')
    tvsoa = cx.fn('ent.comp.SiegeComponent.startOccupationAction')
    tvsat = [a_.value for a_ in cx.code.types[tvsoa.type.value].definition.args]
    tvfr = fb.reg(tvsat[3])
    fb.op('Null', dst=tvfr)
    for act_ in ('Annex', 'Liberate', 'Pillage'):
        fb.op('Call4', dst=tvr, fun=tvsoa.findex.value, arg0=tvsg2, arg1=fb.string(act_), arg2=fac, arg3=tvfr)
        fb.op('JNotNull', reg=b.field(tvsg2, 'occupationAction'), offset='tv_occ')
    fb.label('tv_occ')
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'turocc'), ('tgt', tve), ('r', tvr)])
    fb.label('tv_log')
    _throttle(fb, b, cx, 'bctvl', fac, 30, 'tv_e')
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'turret'), ('tgt', tve), ('d', tvbd)])
    fb.label('tv_e')
    dob = fb.reg(cx.t('ent.Entity'))  # the wave's objective this pass (dr_go / dr_mv)
    fb.op('Mov', dst=dob, src=be)
    fb.op('JNull', reg=tve, offset='dob_f')
    fb.op('Mov', dst=dob, src=tve)
    fb.label('dob_f')
    fb.op('JNull', reg=fte, offset='dob_d')
    fb.op('Mov', dst=dob, src=fte)
    fb.label('dob_d')
    # our Supply Drop on the base's zone (rules/sdrop.py casts the campaign drop there; our `sdz` zone -> expiry):
    # while it runs, wave armies step into that zone and attack from inside it (user 2026-10-25: a main base is a
    # small zone, the attackers stood in the zones around it and got nothing from the drop)
    bdz = fb.reg(cx.t('ent.Zone'))
    fb.op('Mov', dst=bdz, src=b.call('ent.Entity.get_zone', be))
    fb.op('JNull', reg=bdz, offset='bdz_d')
    bdzv = b.call('haxe.ds.ObjectMap.get', _fac_map(fb, b, cx, 'sdz', fac), fb.dyn(bdz))
    fb.op('JNull', reg=bdzv, offset='bdz_x')
    bdzq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=bdzq, src=bdzv)
    fb.op('JSGt', a=bdzq, b=t, offset='bdz_d')
    fb.label('bdz_x')
    fb.op('Null', dst=bdz)
    fb.label('bdz_d')
    dx_ = _army_loop(fb, b, garr, b.field(garr, 'length'), dk, 'dr', 'drd')
    fb.op('JNotNull', reg=b.field(dx_, 'harvestComponent'), offset='dr')
    dbk = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=dbk, src=b.field(orders, 'length'))
    b.loop_head('drb')
    fb.op('JSLte', a=dbk, b=b.const('i32', 0), offset='drb_d')
    fb.op('Sub', dst=dbk, a=dbk, b=b.const('i32', 1))
    dbo = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, dbk), 'logic.ai.AIOrder')
    fb.op('JNull', reg=dbo, offset='drb')
    dbu = b.field(dbo, 'units')
    fb.op('JNull', reg=dbu, offset='drb')
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', dbu, fb.dyn(dx_)), offset='drb')
    # in any order (a strike, a Resupply after a flee, a heal trip): not ours to send (review 2026-10-25: fled /
    # healing armies were pulled back to the base every pass)
    fb.op('JAlways', offset='dr')
    fb.label('drb_d')
    fb.op('JSLt', a=b.call('ent.Entity.get_lifeRatio', dx_), b=_ratio(fb, b, LIFE_CRIT), offset='dr')  # dying
    _supply_share(fb, b, cx, dx_, 'dr_s', q=dq)
    fb.op('JSLt', a=dq, b=_ratio(fb, b, BC_DR_SUP), offset='dr')  # starving: the drop / home first
    fb.label('dr_s')
    # not gone with this go's wave yet (`bcdpa`) and weak: not claimed or sent, it refills first (vanilla resupply)
    drdq = bks.wave_left(fb, b, cx, dx_, 'dr_wk')
    fb.op('JSGte', a=drdq, b=gt, offset='dr_wd')
    fb.label('dr_wk')
    _refill_gate(fb, b, cx, dx_, 'dr', 'drw_ok')
    fb.label('dr_wd')
    # still ours before the strike / worm skip below: a worm-held army (waiting on rock) kept its claim lapsing and
    # dropped out of the campaign after BC_CLAIM_KEEP (match 54: Fremen's 10 walkers 10 -> 0 on its own sand, 118
    # worm holds, none dead)
    b.call('haxe.ds.ObjectMap.set', bcmc, fb.dyn(dx_), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.SENT), fb.dyn(dx_), fb.dyn(t))  # stays in garr
    drc = fb.reg(cx.t('bool'))
    fb.op('Call2', dst=drc, fun=helpers['claim'], arg0=dx_, arg1=b.const('f64', P_RAZE))
    _skip_striking(fb, b, cx, helpers, dx_, 'dr')  # in an en-route strike, or waiting out a worm: not moved now
    fb.op('Mov', dst=dq, src=b.call('ent.Entity.getDistTo', dx_, be))
    fb.op('JSGte', a=dq, b=dmn, offset='dr_mn')
    fb.op('Mov', dst=dmn, src=dq)
    fb.label('dr_mn')
    fb.op('JFalse', cond=b.call('ent.Entity.isFighting', dx_), offset='dr_nf')
    fb.op('JSGt', a=dq, b=b.const('f64', BK_BAL_R), offset='dr')
    fb.op('Incr', dst=dfg)  # micro has it, at the base
    fb.op('JAlways', offset='dr')
    fb.label('dr_nf')
    # one decision per army (review 2026-10-25: the wave, column, field-army and late-arrival rules had grown into
    # separate jumps: an army inside BC_DR_AT off the ring was orphaned, throttled armies stopped holding the go):
    #   in a wave of this go (`bcdpa` >= gt), or no strike point: inside BC_DR_AT engage (dr_in: the field army, else
    #   the base), else walk in as one column (dr_cc);
    #   not yet: to the strike point; at it (BC_AT_RING) the pack decides: leave (a wave), follow the wave that just
    #   left (BC_WAVE_JOIN), or wait.
    # Every branch that acts or is only throttled counts (`dr_actn` / `dr_acts`): the go holds while armies walk in.
    ddep = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=ddep, value=False)
    bks.wave_left(fb, b, cx, dx_, 'dr_dpn', dst=dpq)
    fb.op('JSLt', a=dpq, b=gt, offset='dr_dpn')
    fb.op('Bool', dst=ddep, value=True)
    fb.label('dr_dpn')
    fb.op('JTrue', cond=ddep, offset='dr_go')
    fb.op('JTrue', cond=apok, offset='dr_wv')
    # no strike point: committed once sent (the refill gate above then leaves it alone mid-attack)
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.WAVE_LEFT), fb.dyn(dx_), fb.dyn(t))
    fb.label('dr_go')
    # one objective for the wave (user 2026-10-25, match 75: Harkonnen's wave scattered, some at the field target, some
    # at the turret village, the rest walking at B, flip-flopping as the target came and went): inside / outside and
    # the column walk are measured to it (`dob`: the field army, else the turret village, else B)
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', dx_, dob), b=b.const('f64', BC_DR_AT), offset='dr_cc')
    fb.op('JAlways', offset='dr_in')
    # ---- not in a wave yet: the strike point
    fb.label('dr_wv')
    _dist2(fb, b, dx_, apx, apy, dpq, dwm)
    fb.op('JSLte', a=dpq, b=b.const('f64', BC_AT_RING * BC_AT_RING), offset='dr_sp')
    _throttle(fb, b, cx, 'bcdm', dx_, BC_MOVE_T, 'dr_actn')
    _route_move(dx_, None, 'dr_spd', 'dr', tzone=apz, tx=apx, ty=apy)
    fb.label('dr_spd')
    _move_to(fb, b, cx, dx_, apx, apy, fac)
    fb.op('JAlways', offset='dr_actn')
    fb.label('dr_sp')
    # the wave left: an army arriving within BC_WAVE_JOIN s follows it (match 67: Smugglers' wave left with 75%, the
    # rest stood at the strike point while the front was beaten back); later ones form a second wave once they hold
    # BC_DR_PACK_K of the walkers still here and at least BC_WAVE2_K of the first wave's power (map `bcdepw`), else
    # they wait for the next go without holding this one
    fb.op('JFalse', cond=dgone, offset='dr_w1')
    wjq = _age(fb, b, cx, _global_map(fb, b, cx, bks.WAVE_GONE), fac, t, 'dr_wj_n')
    fb.op('JSGt', a=wjq, b=b.const('f64', BC_WAVE_JOIN), offset='dr_wj_n')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.WAVE_LEFT), fb.dyn(dx_), fb.dyn(t))  # joins it
    fb.op('JAlways', offset='dr_go')
    fb.label('dr_wj_n')
    w1v = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.WAVE_PW), fb.dyn(fac))
    fb.op('JNull', reg=w1v, offset='dr_late')
    fb.op('SafeCast', dst=dpq, src=w1v)
    fb.op('Mul', dst=dpq, a=dpq, b=_ratio(fb, b, BC_WAVE2_K))
    fb.op('JSLt', a=dpk, b=dpq, offset='dr_late')
    fb.label('dr_w1')
    fb.op('JSLte', a=dpk, b=zero, offset='dr_late')  # nobody counted at the ring yet (a newly claimed army)
    fb.op('Mul', dst=dpq, a=dall, b=_ratio(fb, b, BC_DR_PACK_K))
    fb.op('JSLt', a=dpk, b=dpq, offset='dr_late')
    # a walker of ours waiting out a worm (on rock, WORM_HOLD s at most per flee) holds the wave up to BC_PACK_WORM_T s
    # (map `bcpw` faction -> since, older than this go: a new wait; user 2026-10-25, match 65: a worm split
    # Smugglers' column, the wave left with 75%); once one army of the pack left this pass, the rest follow (`dleft`)
    bcpw = _global_map(fb, b, cx, bks.WORM_WAIT)
    fb.op('JTrue', cond=dleft, offset='dr_pw_ok')
    fb.op('JSLte', a=dwh, b=zero, offset='dr_pw_ok')
    pwv = b.call('haxe.ds.ObjectMap.get', bcpw, fb.dyn(fac))
    fb.op('JNull', reg=pwv, offset='dr_pw_n')
    pwq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=pwq, src=pwv)
    fb.op('JSLt', a=pwq, b=gt, offset='dr_pw_n')
    fb.op('Sub', dst=pwq, a=t, b=pwq)
    fb.op('JSLt', a=pwq, b=b.const('f64', BC_PACK_WORM_T), offset='dr_late')
    fb.op('JAlways', offset='dr_pw_ok')
    fb.label('dr_pw_n')
    b.call('haxe.ds.ObjectMap.set', bcpw, fb.dyn(fac), fb.dyn(t))
    _throttle(fb, b, cx, 'bcpwl', fac, 30, 'dr_late')
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'wormwait'), ('tgt', be), ('W', dwh),
                                          ('K', dpk), ('A', dall)])
    fb.op('JAlways', offset='dr_late')
    fb.label('dr_pw_ok')
    b.call('haxe.ds.ObjectMap.remove', bcpw, fb.dyn(fac))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.WAVE_GONE), fb.dyn(fac), fb.dyn(t))  # the wave leaves
    fb.op('JTrue', cond=dgone, offset='dr_w2')  # (a second wave keeps the first wave's power)
    fb.op('JTrue', cond=dleft, offset='dr_w2')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.WAVE_PW), fb.dyn(fac), fb.dyn(dpk))
    fb.label('dr_w2')
    fb.op('Bool', dst=dleft, value=True)
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.WAVE_LEFT), fb.dyn(dx_), fb.dyn(t))  # ... with this army
    fb.op('JAlways', offset='dr_go')
    fb.label('dr_late')
    fb.op('JTrue', cond=dgone, offset='dr')  # after the wave left, a waiting army doesn't hold the go (match 61: it
    fb.op('JAlways', offset='dr_actn')  # ran 17 min on trickles); waiting for the wave to form does
    # ---- in a wave, outside BC_DR_AT: one column
    fb.label('dr_cc')
    # ahead of the column: wait for it (counted as acting: the go holds), only on our own land (match 66: Fremen's 11
    # armies waited 110 s in Atreides' land, supply 274 -> 94, and starved home 30 s after they left) and at most
    # BC_COH_WAIT s per army (map `bccw` army -> since; a wait older than 2 x that is a new one)
    fb.op('Sub', dst=dwq, a=drear, b=dq)
    fb.op('JSLte', a=dwq, b=b.const('f64', BC_COH), offset='dr_mv')
    dcz = b.call('ent.Entity.get_zone', dx_)
    fb.op('JNull', reg=dcz, offset='dr_mv')
    fb.op('JNotEq', a=b.field(dcz, 'owner'), b=fac, offset='dr_mv')
    bccw = _global_map(fb, b, cx, bks.COH_WAIT)
    dcwv = b.call('haxe.ds.ObjectMap.get', bccw, fb.dyn(dx_))
    dcwq = fb.reg(cx.t('f64'))
    fb.op('JNull', reg=dcwv, offset='dr_cw_n')
    fb.op('SafeCast', dst=dcwq, src=dcwv)
    fb.op('Sub', dst=dcwq, a=t, b=dcwq)
    fb.op('JSGt', a=dcwq, b=b.const('f64', 2 * BC_COH_WAIT), offset='dr_cw_n')
    fb.op('JSGt', a=dcwq, b=b.const('f64', BC_COH_WAIT), offset='dr_mv')  # waited enough: on
    fb.op('JAlways', offset='dr_actn')
    fb.label('dr_cw_n')
    b.call('haxe.ds.ObjectMap.set', bccw, fb.dyn(dx_), fb.dyn(t))
    fb.op('JAlways', offset='dr_actn')
    fb.label('dr_mv')
    _throttle(fb, b, cx, 'bcdm', dx_, BC_MOVE_T, 'dr_actn')
    _route_move(dx_, dob, 'dr_dir', 'dr')
    fb.label('dr_dir')
    _move_to(fb, b, cx, dx_, b.field(dob, 'posx'), b.field(dob, 'posy'), fac)
    fb.label('dr_actn')
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset='dr')
    # ---- in a wave, inside BC_DR_AT: the field army first (above), else the base
    fb.label('dr_in')
    # Enter the base's drop zone only while the base is the wave's objective. Field targets and turret captures
    # keep their own approach; a supply effect must not pull their armies off the selected objective.
    fb.op('JNull', reg=bdz, offset='dr_in2')
    fb.op('JNotEq', a=dob, b=be, offset='dr_in2')
    fb.op('JEq', a=b.call('ent.Entity.get_zone', dx_), b=bdz, offset='dr_in2')
    _throttle(fb, b, cx, 'bcsdi', dx_, BC_SD_IN_T, 'dr_actn')
    _move_to(fb, b, cx, dx_, b.field(be, 'posx'), b.field(be, 'posy'), fac)
    fb.op('JAlways', offset='dr_actn')
    fb.label('dr_in2')
    fb.op('JNull', reg=fte, offset='dr_sg')
    fb.op('JEq', a=b.call('ent.Entity.getFightingTarget', dx_), b=fte, offset='dr_acts')
    # sent this target already and still busy on its way (getFightingTarget is null while walking): re-sent only every
    # BC_DR_BUSY_T s (the INPUT-SPAM-TODO 8 pattern); a new target or an idle army: now (map `bcdfe` army -> target)
    dfev = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.FIELD_SENT), fb.dyn(dx_))
    fb.op('JNull', reg=dfev, offset='dr_ff')
    fb.op('JNotEq', a=dfev, b=fb.dyn(fte), offset='dr_ff')
    fb.op('JNull', reg=b.call('ent.Entity.getActionDesc', dx_), offset='dr_ff')
    _throttle(fb, b, cx, 'bcdfb', dx_, BC_DR_BUSY_T, 'dr_acts')
    fb.label('dr_ff')
    _throttle(fb, b, cx, 'bcdf', dx_, BC_FIELD_T, 'dr_acts')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.FIELD_SENT), fb.dyn(dx_), fb.dyn(fte))
    dfe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=dfe, src=dx_)
    _do_on(fb, b, cx, dfe, 'ArmyFight', fte, fac)
    fb.op('JAlways', offset='dr_acts')
    fb.label('dr_sg')
    # the siege target: a turret village first (above), else the base
    dstg = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=dstg, src=be)
    fb.op('JNull', reg=tve, offset='dr_sgt')
    fb.op('Mov', dst=dstg, src=tve)
    fb.label('dr_sgt')
    # re-sent only when idle (docs/INPUT-SPAM-TODO.md 8: a running ArmySiege walk was re-sent every pass); a busy army
    # (another action) at most every BC_DR_BUSY_T s
    fb.op('JNull', reg=b.call('ent.Entity.getActionDesc', dx_), offset='dr_idle')
    _throttle(fb, b, cx, 'bcdsb', dx_, BC_DR_BUSY_T, 'dr_acts')
    fb.label('dr_idle')
    _throttle(fb, b, cx, 'bcds', dx_, BC_DR_T, 'dr_acts')
    dxe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=dxe, src=dx_)
    _do_on(fb, b, cx, dxe, 'ArmySiege', dstg, fac)
    fb.label('dr_acts')
    fb.op('Incr', dst=dns)
    fb.op('JAlways', offset='dr')
    fb.label('drd')
    # the go holds only while this raze does something: armies walking in, sent to siege or fighting at the base
    # (review 2026-10-25: reaching the label held the go up to 1200 s with every army skipped)
    fb.op('Add', dst=dfg, a=dfg, b=n)
    fb.op('Add', dst=dfg, a=dfg, b=dns)
    fb.op('JSLte', a=dfg, b=b.const('i32', 0), offset='dr_nh')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.RAZE_ACT), fb.dyn(fac), fb.dyn(t))  # holds the go
    # the doctrine's Siege mode (unit mix / gear for structures), as a Raze order would mark it (tasks._siege_mark)
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'dsiege'), fb.dyn(fac), fb.dyn(t))
    fb.label('dr_nh')
    # occupied by us with no occupation action yet: the Raze
    dsg = b.field(b.cast(fb.dyn(be), 'ent.Structure'), 'siege')
    fb.op('JNull', reg=dsg, offset='dr_log')
    fb.op('JNotEq', a=b.call('ent.comp.SiegeComponent.getOccupierFaction', dsg), b=fac, offset='dr_log')
    fb.op('JNotNull', reg=b.field(dsg, 'occupationAction'), offset='dr_log')
    soa = cx.fn('ent.comp.SiegeComponent.startOccupationAction')
    soat = [a_.value for a_ in cx.code.types[soa.type.value].definition.args]
    dfr = fb.reg(soat[3])
    fb.op('Null', dst=dfr)
    der = fb.reg(cx.code.types[soa.type.value].definition.ret.value)
    fb.op('Call4', dst=der, fun=soa.findex.value, arg0=dsg, arg1=fb.string('Raze'), arg2=fac, arg3=dfr)
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'raze'), ('tgt', be), ('r', der)])
    fb.label('dr_log')
    _throttle(fb, b, cx, 'bcdl', fac, 20, 'end')
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'direct'), ('tgt', be),
                                          ('n', fb.dyn(n)), ('ns', fb.dyn(dns)), ('dmin', dmn),
                                          ('hp%', b.call('ent.Entity.get_lifeRatio', be))])
    fb.op('JAlways', offset='end')
    fb.label('dr_no')
    # a real Raze: the ready armies hold >= BC_RAZE_SHARE of this member's campaign power (match 34: Fremen launched
    # 1-army Razes every second while 11 armies were still marching; each death raised the cut), and one launch per
    # BC_RAZE_T at most
    rzr, rzg, rzq = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=rzr, src=zero)
    fb.op('Mov', dst=rzg, src=zero)
    rzk = fb.reg(cx.t('i32'))
    rza = _army_loop(fb, b, rarr, b.field(rarr, 'length'), rzk, 'rzr', 'rzrd')
    fb.op('Call1', dst=rzq, fun=pw, arg0=rza)
    fb.op('Add', dst=rzr, a=rzr, b=rzq)
    fb.op('JAlways', offset='rzr')
    fb.label('rzrd')
    rzb = _army_loop(fb, b, garr, b.field(garr, 'length'), rzk, 'rzg', 'rzgd')
    fb.op('Call1', dst=rzq, fun=pw, arg0=rzb)
    fb.op('Add', dst=rzg, a=rzg, b=rzq)
    fb.op('JAlways', offset='rzg')
    fb.label('rzgd')
    fb.op('Mul', dst=rzq, a=rzg, b=_ratio(fb, b, BC_RAZE_SHARE))
    fb.op('JSLt', a=rzr, b=rzq, offset='gap')
    _throttle(fb, b, cx, 'bcrz', fac, BC_RAZE_T, 'gap')
    kind = fb.reg(cx.t('logic.ai.AIOrderType'))
    fb.op('MakeEnum', dst=kind, construct=MILITARY, args=[])
    gmm, gom = _new_array(fb, b, cx), _new_array(fb, b, cx)  # no missions (vanilla iterates these arrays)
    gnul = []
    for n_ in (9, 10):  # data, onComplete
        r_ = fb.reg(at[n_])
        fb.op('Null', dst=r_)
        gnul.append(r_)
    gres = fb.reg(cx.t('logic.ai.AIOrder'))
    fb.op('CallN', dst=gres, fun=helpers.get('addOrder', add.findex.value),
          args=[b.field(ctrl, 'aiOrders'), kind, b.const('i32', BC_PRIO), rarr, lb, fb.string('ArmySiege'),
                fb.string('Raze'), gmm, gom] + gnul)
    fb.op('Bool', dst=ok, value=False)
    fb.op('JNull', reg=gres, offset='go_log')  # refused: no launch recorded, the next pass may try again
    fb.op('Bool', dst=ok, value=True)
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.MIN_SUP), fb.dyn(fac), fb.dyn(gminr))
    b.call('haxe.ds.ObjectMap.set', bcl, fb.dyn(fac), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.LAUNCH_ORDER), fb.dyn(fac), fb.dyn(gres))
    fb.label('go_log')
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'go'), ('tgt', be),
                                          ('n', b.field(rarr, 'length')), ('low', fb.dyn(nlow)), ('busy', fb.dyn(nbusy)),
                                          ('dd', fb.dyn(ndd)), ('minr%', gminr), ('ok', ok), ('D', dd), ('M', mm_),
                                          ('ax', apx), ('ay', apy)])
    fb.op('JAlways', offset='gap')  # the lead's other armies approach too
