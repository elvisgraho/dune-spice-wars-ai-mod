"""Base-kill campaign section: muster / regroup / attrition (partner foothold backing, our foothold / stepping-stone
capture as one pack, the staging walk)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules import bkstate as bks
from rules.worm import _do_on, _move_to
from rules.bkcamp.shared import *  # noqa: F401,F403

FF_MIN = 90          # foothold capture: villages this far from the base at least (its guns: 80) ...
BC_FF_GATHER_D = 180  # ... its armies gather this far from the village on our staging's side ...
BC_STEP_GAIN = 150   # ... or a stepping stone: this much nearer the base than our staging ...
BC_STEP_R = 450      # ... and within this of our staging (reachable from our land)
BC_STEP_KEY = 4000   # (pick order: every foothold before any step)
FF_AUTH = 150        # ... with this much Authority (an Annex costs it) ...
FF_CLAIM_T = 60      # ... not claimed by another member within this many s ...
BC_ATT_R = 900       # attrition: our capture takes free armies within this of the village ...
BC_ATT_K = 2.0       # ... until their power reaches this x the capture's H (threat + militia)
BC_FF_R = 250        # ... our free muster power >= BC_FF_K x (at-war armies within BC_FF_R of it + BC_FF_MIL)
BC_FF_K = 1.5
BC_FF_MIL = 150000


def _emit_muster(c):
    """Muster / regroup / attrition: partner foothold backing, our own foothold / stepping-stone capture (as one
    pack), the staging walk."""
    (_ours_claimed, _route_move, add, at, att, b, bcmc, be, ctrl, cx, fac, fb, ffcap, ffneed, ffsp, free, helpers,
     j, ld, mlen, my, n, ok, orders, ph, pw, st, stg, t, zero,) = _take(c, '_ours_claimed _route_move add at att b bcmc be ctrl cx fac fb ffcap ffneed ffsp free helpers j ld '
        'mlen my n ok orders ph pw st stg t zero')
    fb.label('mu_start')  # (also a go member with no campaign armies: it musters / takes its foothold or step)
    # muster / regroup: free armies to our staging structure (found above)
    # a foothold siege (user 2026-10-24: try to take a foothold near the base): a leader village within BC_FOOT_NEAR of
    # B besieged / occupied by another plan member: our muster armies back it there instead of staging (they shoot
    # what comes; the leader's army near its base kept single Annexes from holding)
    fsv = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=fsv)
    ocap = fb.reg(cx.t('bool'))  # our own capture runs (below)
    fb.op('Bool', dst=ocap, value=False)
    # our own capture runs (map `bcfan` village, our claim on it fresh within FF_CLAIM_T, not ours yet): no switch to
    # a partner's foothold (match 65: Fremen walked to Grimwan for its capture, to Smugglers' Annagah, back to Grimwan:
    # user "walking, then dragged back")
    oce = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=oce)
    ocv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.FOOT_ANNEX), fb.dyn(fac))
    fb.op('JNull', reg=ocv, offset='fs_srch')
    fb.op('SafeCast', dst=oce, src=ocv)
    fb.op('JNull', reg=oce, offset='fs_srch')
    fb.op('JEq', a=b.call('ent.Entity.get_owner', oce), b=fac, offset='fs_srch')  # taken: done
    occ = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.FOOT_CLAIM), fb.dyn(oce))
    fb.op('JNull', reg=occ, offset='fs_srch')
    fb.op('JNotEq', a=b.cast(occ, 'ent.Faction'), b=fac, offset='fs_srch')
    ocq2 = _age(fb, b, cx, _global_map(fb, b, cx, bks.FOOT_CLAIM_T), oce, t, 'fs_srch')
    fb.op('JSGte', a=ocq2, b=b.const('f64', FF_CLAIM_T), offset='fs_srch')
    fb.op('Bool', dst=ocap, value=True)
    fb.op('JAlways', offset='fs_d')
    fb.label('fs_srch')
    fb.op('JTrue', cond=att, offset='fs_d')  # attrition: no partner backing
    fls = b.cast(fb.get(ld, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=fls, offset='fs_d')
    fsk = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=fsk, src=b.const('i32', 0))
    b.loop_head('fsl')
    fb.op('JSGte', a=fsk, b=b.field(fls, 'length'), offset='fs_d')
    fss = b.cast(b.call('hl.types.ArrayObj.getDyn', fls, fsk), 'ent.Structure')
    fb.op('Incr', dst=fsk)
    fb.op('JNull', reg=fss, offset='fsl')
    fse_ = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=fse_, src=fss)
    fb.op('JEq', a=fse_, b=be, offset='fsl')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', fse_, be), b=b.const('f64', BC_FOOT_NEAR), offset='fsl')
    fsg = b.field(fss, 'siege')
    fb.op('JNull', reg=fsg, offset='fsl')
    fsf = fb.reg(cx.t('ent.Faction'))
    fb.op('Mov', dst=fsf, src=b.field(fsg, 'besiegingFaction'))
    fb.op('JNotNull', reg=fsf, offset='fs_h')
    fb.op('Mov', dst=fsf, src=b.call('ent.comp.SiegeComponent.getOccupierFaction', fsg))
    fb.op('JNull', reg=fsf, offset='fsl')
    fb.label('fs_h')
    fb.op('JEq', a=fsf, b=fac, offset='fsl')  # our own: its order's armies are on it
    # won already: the partner occupies it and no at-war army is within BC_FF_R: nothing to back (user 2026-10-25:
    # Smugglers stood at Fremen's Arknun losing supply while Fremen's Annex ran)
    fb.op('JFalse', cond=b.call('ent.comp.SiegeComponent.isOccupied', fsg), offset='fs_nw')
    fsth = fb.reg(cx.t('f64'))
    fb.op('Call3', dst=fsth, fun=helpers['threat'], arg0=fac, arg1=fse_, arg2=b.const('f64', BC_FF_R))
    fb.op('JSLte', a=fsth, b=b.const('f64', 0), offset='fsl')
    fb.label('fs_nw')
    _bk_partner(fb, b, cx, fac, fsf, 'fs_y')
    fb.op('JAlways', offset='fsl')
    fb.label('fs_y')
    fb.op('Mov', dst=fsv, src=fse_)
    fb.label('fs_d')
    # our own foothold capture (user 2026-10-25: Fremen could have taken Dal-nit, 102 from Smugglers' Tuek, neutral
    # most of the match; vanilla never offers such a village: its Annex candidates lie within a few zone hops of our
    # land): no structure of ours within BC_FOOT_NEAR of B, no partner foothold to back, Authority >= FOOT_AUTH: the
    # nearest village (to our staging) FOOT_MIN..BC_FOOT_NEAR from B, neutral or the leader's, not deep desert, not
    # besieged / occupied by anyone else, not claimed by another member (maps `bcffv` / `bcffvt` village -> faction /
    # time), and our free muster power >= BC_FF_K x (the at-war armies within BC_FF_R of it + BC_FF_MIL militia): the
    # muster armies walk to it and get doAction(ArmySiege) within BC_DR_AT; once we occupy it,
    # startOccupationAction(Annex). Then it is our structure near B: the staging point and strike point (own land:
    # vanilla rallies there). Log `bcamp` act footcap (tgt, P, H) / footann (r)
    ffv = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=ffv)
    ffse = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ffse, src=stg)  # null without a staging structure (its reads are behind the same test)
    fb.op('JNotNull', reg=fsv, offset='ff_d')
    fb.op('JNull', reg=stg, offset='ff_srch')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', ffse, be), b=b.const('f64', BC_FOOT_NEAR), offset='ff_d')
    fb.label('ff_srch')
    fb.op('JTrue', cond=ocap, offset='ff_au')  # a capture under way isn't dropped when the Annex cost dips Authority
    fb.op('JSLt', a=b.call('ent.Faction.getResource', fac, b.const('i32', RES_AUTHORITY)),
          b=b.const('f64', FF_AUTH), offset='ff_d')
    fb.label('ff_au')
    ffvl = b.field(st, 'villages')
    fb.op('JNull', reg=ffvl, offset='ff_d')
    ffk = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=ffk, src=b.const('i32', 0))
    ffbd, ffq = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=ffbd, src=b.const('f64', 1 << 20))
    ffc = fb.reg(cx.t('ent.Entity'))
    # stepping stones (user 2026-10-25, match 61: Fremen, far from Arrakeen, did nothing for 17 min; it could have
    # taken villages to extend its reach): with no foothold candidate, a village >= BC_STEP_GAIN nearer B than our
    # staging and within BC_STEP_R of it (reachable from our land) qualifies too; footholds come first
    ffsd, ffdb = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=ffsd, src=b.const('f64', 1 << 20))
    fb.op('JNull', reg=stg, offset='ffsd_d')
    fb.op('Mov', dst=ffsd, src=b.call('ent.Entity.getDistTo', ffse, be))
    fb.label('ffsd_d')
    ffst, ffbs = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))  # this candidate is a step / the pick is one
    fb.op('Bool', dst=ffbs, value=False)
    ffbv = _global_map(fb, b, cx, bks.FOOT_CLAIM)
    ffbt = _global_map(fb, b, cx, bks.FOOT_CLAIM_T)
    b.loop_head('ffl')
    fb.op('JSGte', a=ffk, b=b.field(ffvl, 'length'), offset='ffl_d')
    ffs = b.cast(b.call('hl.types.ArrayObj.getDyn', ffvl, ffk), 'ent.Structure')
    fb.op('Incr', dst=ffk)
    fb.op('JNull', reg=ffs, offset='ffl')
    fb.op('Mov', dst=ffc, src=ffs)
    fb.op('Mov', dst=ffdb, src=b.call('ent.Entity.getDistTo', ffc, be))
    fb.op('JSLt', a=ffdb, b=b.const('f64', FF_MIN), offset='ffl')
    fb.op('Bool', dst=ffst, value=False)
    fb.op('JSLte', a=ffdb, b=b.const('f64', BC_FOOT_NEAR), offset='ffl_ft')
    fb.op('JNull', reg=stg, offset='ffl')
    fb.op('Sub', dst=ffq, a=ffsd, b=b.const('f64', BC_STEP_GAIN))
    fb.op('JSGt', a=ffdb, b=ffq, offset='ffl')  # not nearer the base
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ffc, ffse), b=b.const('f64', BC_STEP_R), offset='ffl')
    fb.op('Bool', dst=ffst, value=True)
    fb.op('JAlways', offset='ffl_k')
    # a foothold within reach too (BC_STEP_R of our staging; user 2026-10-25, match 67: Harkonnen walked from Hayras
    # 850 through enemy land toward Lamtah next to Arrakeen and turned back starving): else a step gets us closer
    fb.label('ffl_ft')
    fb.op('JNull', reg=stg, offset='ffl_k')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ffc, ffse), b=b.const('f64', BC_STEP_R), offset='ffl')
    fb.label('ffl_k')
    ffo = b.call('ent.Entity.get_owner', ffc)
    fb.op('JNull', reg=ffo, offset='ffl_own')
    fb.op('JNotEq', a=ffo, b=ld, offset='ffl')  # neutral or the leader's only
    fb.label('ffl_own')
    ffz = b.call('ent.Entity.get_zone', ffc)
    fb.op('JNull', reg=ffz, offset='ffl')
    fb.op('JTrue', cond=b.call('ent.Zone.isDeepDesert', ffz), offset='ffl')
    ffsg = b.field(ffs, 'siege')
    fb.op('JNull', reg=ffsg, offset='ffl')
    ffbf = b.field(ffsg, 'besiegingFaction')
    fb.op('JNull', reg=ffbf, offset='ffl_bs')
    fb.op('JNotEq', a=ffbf, b=fac, offset='ffl')  # someone else besieges it
    fb.label('ffl_bs')
    ffof = b.call('ent.comp.SiegeComponent.getOccupierFaction', ffsg)
    fb.op('JNull', reg=ffof, offset='ffl_oc')
    fb.op('JNotEq', a=ffof, b=fac, offset='ffl')
    fb.label('ffl_oc')
    # not started by us yet: a pillaged village (trait Devastated: untargetable) or one whose Annex we can't pay now
    # isn't taken (user 2026-10-25, match 73: Fremen occupied Sadnih with no Authority and its armies froze there)
    fb.op('JEq', a=ffbf, b=fac, offset='ffl_pay')
    fb.op('JEq', a=ffof, b=fac, offset='ffl_pay')
    _has_trait(fb, b, cx, ffs, 'Devastated', 'ffl')
    fb.op('JSGt', a=_annex_cost(fb, b, cx, ffs, fac),
          b=b.call('ent.Faction.getResource', fac, b.const('i32', RES_AUTHORITY)), offset='ffl')
    fb.label('ffl_pay')
    ffcv = b.call('haxe.ds.ObjectMap.get', ffbv, fb.dyn(ffc))  # another member's claim, fresh
    fb.op('JNull', reg=ffcv, offset='ffl_cl')
    fb.op('JEq', a=b.cast(ffcv, 'ent.Faction'), b=fac, offset='ffl_cl')
    ffcq = _age(fb, b, cx, ffbt, ffc, t, 'ffl_cl')
    fb.op('JSLt', a=ffcq, b=b.const('f64', FF_CLAIM_T), offset='ffl')
    fb.label('ffl_cl')
    # a foothold: nearest to our staging (our side), else to the base; a step: BC_STEP_KEY + its distance to B (any
    # foothold first, then the step that gains most)
    fb.op('Mov', dst=ffq, src=ffdb)
    fb.op('JTrue', cond=ffst, offset='ffl_st')
    fb.op('JNull', reg=stg, offset='ffl_pick')
    fb.op('Mov', dst=ffq, src=b.call('ent.Entity.getDistTo', ffc, ffse))
    fb.op('JAlways', offset='ffl_pick')
    fb.label('ffl_st')
    fb.op('Add', dst=ffq, a=ffq, b=b.const('f64', BC_STEP_KEY))
    fb.label('ffl_pick')
    # Prefer the running capture only after it passes every eligibility check.
    fb.op('JFalse', cond=ocap, offset='ffl_score')
    fb.op('JEq', a=ffc, b=oce, offset='ffl_keep')
    fb.label('ffl_score')
    fb.op('JSGte', a=ffq, b=ffbd, offset='ffl')
    fb.label('ffl_keep')
    fb.op('Mov', dst=ffbd, src=ffq)
    fb.op('Mov', dst=ffv, src=ffc)
    fb.op('Mov', dst=ffbs, src=ffst)
    fb.op('JFalse', cond=ocap, offset='ffl')
    fb.op('JEq', a=ffc, b=oce, offset='ffl_d')
    fb.op('JAlways', offset='ffl')
    fb.label('ffl_d')
    fb.op('JNull', reg=ffv, offset='ff_d')
    # strong enough: our free muster power vs the at-war armies near it + a militia
    ffp, ffh = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=ffp, src=zero)
    ffj = fb.reg(cx.t('i32'))
    ffa = _army_loop(fb, b, my, mlen, ffj, 'ffp', 'ffpd')
    fb.op('JNotNull', reg=b.field(ffa, 'harvestComponent'), offset='ffp')
    fb.op('Call2', dst=ok, fun=free, arg0=ffa, arg1=orders)
    fb.op('JTrue', cond=ok, offset='ffp_ok')
    _ours_claimed(ffa, 'ffp_ok', 'ffp')
    fb.label('ffp_ok')
    fb.op('JFalse', cond=att, offset='ffp_c')  # attrition: only the armies it would take (within BC_ATT_R)
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ffa, ffv), b=b.const('f64', BC_ATT_R), offset='ffp')
    fb.label('ffp_c')
    # one the muster would refill first (BC_DEP_LIFE / BC_DEP_SUP, away from the village) isn't counted
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', ffa, ffv), b=b.const('f64', BC_DR_AT), offset='ffp_w')
    _refill_gate(fb, b, cx, ffa, 'ffp', 'ffp_w', q=ffq)
    fb.op('Call1', dst=ffq, fun=pw, arg0=ffa)
    fb.op('Add', dst=ffp, a=ffp, b=ffq)
    fb.op('JAlways', offset='ffp')
    fb.label('ffpd')
    fb.op('Call3', dst=ffh, fun=helpers['threat'], arg0=fac, arg1=ffv, arg2=b.const('f64', BC_FF_R))
    fb.op('Add', dst=ffh, a=ffh, b=b.const('f64', BC_FF_MIL))
    fb.op('Mul', dst=ffq, a=ffh, b=_ratio(fb, b, BC_FF_K))
    fb.op('JSGte', a=ffp, b=ffq, offset='ff_ok')
    fb.op('Null', dst=ffv)  # too strong there: stage as before
    fb.op('JAlways', offset='ff_d')
    fb.label('ff_ok')
    fb.op('Mul', dst=ffcap, a=ffh, b=_ratio(fb, b, BC_ATT_K))  # the attrition send cap
    fb.op('Mul', dst=ffneed, a=ffh, b=_ratio(fb, b, BC_FF_K))
    b.call('haxe.ds.ObjectMap.set', ffbv, fb.dyn(ffv), fb.dyn(fac))
    b.call('haxe.ds.ObjectMap.set', ffbt, fb.dyn(ffv), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.FOOT_ANNEX), fb.dyn(fac), fb.dyn(ffv))  # held through a go
    # occupied by us with no action yet: the Annex
    ffsg2 = b.field(b.cast(fb.dyn(ffv), 'ent.Structure'), 'siege')
    fb.op('JNull', reg=ffsg2, offset='ff_log')
    fb.op('JNotEq', a=b.call('ent.comp.SiegeComponent.getOccupierFaction', ffsg2), b=fac, offset='ff_log')
    fb.op('JNotNull', reg=b.field(ffsg2, 'occupationAction'), offset='ff_log')
    ffsoa = cx.fn('ent.comp.SiegeComponent.startOccupationAction')
    ffsat = [a_.value for a_ in cx.code.types[ffsoa.type.value].definition.args]
    fffr = fb.reg(ffsat[3])
    fb.op('Null', dst=fffr)
    ffer = fb.reg(cx.code.types[ffsoa.type.value].definition.ret.value)
    fb.op('Call4', dst=ffer, fun=ffsoa.findex.value, arg0=ffsg2, arg1=fb.string('Annex'), arg2=fac, arg3=fffr)
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'footann'), ('tgt', ffv), ('r', ffer)])
    fb.op('JNotNull', reg=b.field(ffsg2, 'occupationAction'), offset='ff_ann')
    # no Annex (the Authority went meanwhile): Liberate, else Pillage, so the occupation resolves and the armies move
    # on (user: a capture waiting for Authority froze them); the capture ends (FOOT_ANNEX / our claim dropped)
    for act_ in ('Liberate', 'Pillage'):
        fb.op('Call4', dst=ffer, fun=ffsoa.findex.value, arg0=ffsg2, arg1=fb.string(act_), arg2=fac, arg3=fffr)
        fb.op('JNotNull', reg=b.field(ffsg2, 'occupationAction'), offset='ff_alt')
    fb.op('JAlways', offset='ff_log')
    fb.label('ff_alt')
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'footalt'), ('tgt', ffv), ('r', ffer)])
    b.call('haxe.ds.ObjectMap.remove', _global_map(fb, b, cx, bks.FOOT_ANNEX), fb.dyn(fac))
    b.call('haxe.ds.ObjectMap.remove', ffbv, fb.dyn(ffv))
    fb.op('JAlways', offset='ff_log')
    fb.label('ff_ann')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, bks.FOOT_ANNEX), fb.dyn(fac), fb.dyn(ffv))  # held through a go
    fb.label('ff_log')
    _throttle(fb, b, cx, 'bcffl', fac, 30, 'ff_d')
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'footcap'), ('tgt', ffv), ('P', ffp),
                                          ('H', ffh), ('step', ffbs)])
    fb.label('ff_d')
    fb.op('JNotNull', reg=ffv, offset='fs_go')
    fb.op('JTrue', cond=att, offset='end')  # attrition without a capture: nothing of ours to do
    fb.op('JNotNull', reg=fsv, offset='fs_go')
    fb.op('JNull', reg=stg, offset='end')  # nowhere to stage: attrition tools only
    fb.label('fs_go')
    # our capture as one pack (match 68: Fremen's armies reached Eyno one or two at a time, fought its militia and
    # vanilla's fight retreat sent them home at 1315 s): they gather at BC_FF_GATHER_D from the village on our
    # staging's side; the siege goes out once ours there and at the village (BC_AT_RING of either) hold ffneed, and
    # stays out BC_FF_GO_T s (map `bcffgo` village -> launch time). Log `bcamp` act footgo (tgt, K)
    ffgo = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=ffgo, value=True)
    gpx, gpy, gpq, gpd = (fb.reg(cx.t('f64')) for _ in range(4))
    for r_ in (gpx, gpy, gpq, gpd):
        fb.op('Mov', dst=r_, src=zero)
    fb.op('JNull', reg=ffv, offset='ffg_d')
    fb.op('Mov', dst=gpx, src=b.field(ffv, 'posx'))
    fb.op('Mov', dst=gpy, src=b.field(ffv, 'posy'))
    fb.op('JNull', reg=stg, offset='ffg_p')
    fb.op('Sub', dst=gpq, a=b.field(stg, 'posx'), b=gpx)
    fb.op('Sub', dst=gpd, a=b.field(stg, 'posy'), b=gpy)
    ffgl = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=ffgl, src=b.call('ent.Entity.getDistTo', stg, ffv))
    fb.op('JSLt', a=ffgl, b=b.const('f64', BC_FF_GATHER_D + 20), offset='ffg_home')
    fb.op('SDiv', dst=gpq, a=gpq, b=ffgl)
    fb.op('SDiv', dst=gpd, a=gpd, b=ffgl)
    fb.op('Mul', dst=gpq, a=gpq, b=b.const('f64', BC_FF_GATHER_D))
    fb.op('Mul', dst=gpd, a=gpd, b=b.const('f64', BC_FF_GATHER_D))
    fb.op('Add', dst=gpx, a=gpx, b=gpq)
    fb.op('Add', dst=gpy, a=gpy, b=gpd)
    fb.op('JAlways', offset='ffg_p')
    fb.label('ffg_home')
    fb.op('Mov', dst=gpx, src=b.field(stg, 'posx'))
    fb.op('Mov', dst=gpy, src=b.field(stg, 'posy'))
    fb.label('ffg_p')
    ffgm = _global_map(fb, b, cx, bks.FOOT_GO)
    _age(fb, b, cx, ffgm, ffv, t, 'ffg_k', dst=gpq)
    fb.op('JSLte', a=gpq, b=b.const('f64', BC_FF_GO_T), offset='ffg_d')  # launched: stays out
    fb.label('ffg_k')
    fb.op('Bool', dst=ffgo, value=False)
    ffgk = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=ffgk, src=zero)
    ffgj = fb.reg(cx.t('i32'))
    ffga = _army_loop(fb, b, my, mlen, ffgj, 'ffgl', 'ffgld')
    fb.op('JNotNull', reg=b.field(ffga, 'harvestComponent'), offset='ffgl')
    # The pack may count only armies that its executor can actually send.
    fb.op('Call2', dst=ok, fun=free, arg0=ffga, arg1=orders)
    fb.op('JTrue', cond=ok, offset='ffgl_free')
    _ours_claimed(ffga, 'ffgl_free', 'ffgl')
    fb.label('ffgl_free')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', ffga, ffv), b=b.const('f64', BC_AT_RING), offset='ffgl_y')
    _dist2(fb, b, ffga, gpx, gpy, gpq, gpd)
    fb.op('JSGt', a=gpq, b=b.const('f64', BC_AT_RING * BC_AT_RING), offset='ffgl')
    fb.label('ffgl_y')
    fb.op('Call1', dst=gpq, fun=pw, arg0=ffga)
    fb.op('Add', dst=ffgk, a=ffgk, b=gpq)
    fb.op('JAlways', offset='ffgl')
    fb.label('ffgld')
    fb.op('JSLt', a=ffgk, b=ffneed, offset='ffg_d')
    fb.op('JSLte', a=ffgk, b=zero, offset='ffg_d')
    b.call('haxe.ds.ObjectMap.set', ffgm, fb.dyn(ffv), fb.dyn(t))
    fb.op('Bool', dst=ffgo, value=True)
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'footgo'), ('tgt', ffv), ('K', ffgk)])
    fb.label('ffg_d')
    # Route to the gathering point's zone before launch, not into the village's zone.
    fgz = fb.reg(cx.t('ent.Zone'))
    fb.op('Null', dst=fgz)
    fb.op('JNull', reg=ffv, offset='ffgz_d')
    fgg = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=fgg, **{'global': cx.global_of('$Game')})
    fgw = b.field(b.field(fgg, 'inst'), 'world')
    fb.op('JNull', reg=fgw, offset='ffgz_d')
    fb.op('Mov', dst=fgz, src=b.call('world.World.getZoneAt', fgw, gpx, gpy))
    fb.label('ffgz_d')
    x = _army_loop(fb, b, my, mlen, j, 'mu', 'mud')
    fb.op('JNotNull', reg=b.field(x, 'harvestComponent'), offset='mu')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', x), offset='mu')
    # refill first (user 2026-10-25: Harkonnen turned back with bleeding units; it could have resupplied first): below
    # BC_DEP_SUP supply or BC_DEP_LIFE life it isn't mustered: vanilla resupplies it
    # ... except at our capture (within BC_DR_AT of it): its besiegers stay on it (review 2026-10-25)
    fb.op('JNull', reg=ffv, offset='muw_g')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', x, ffv), b=b.const('f64', BC_DR_AT), offset='muw_ok')
    fb.label('muw_g')
    _refill_gate(fb, b, cx, x, 'mu', 'muw_ok')
    fb.op('Call2', dst=ok, fun=free, arg0=x, arg1=orders)
    fb.op('JTrue', cond=ok, offset='mu_ok')
    _ours_claimed(x, 'mu_ok', 'mu')
    fb.label('mu_ok')
    fb.op('JFalse', cond=att, offset='mu_att')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', x, ffv), b=b.const('f64', BC_ATT_R), offset='mu')  # far: vanilla's
    fb.op('JSGte', a=ffsp, b=ffcap, offset='mu')  # enough sent: the rest stays vanilla's
    muap = fb.reg(cx.t('f64'))
    fb.op('Call1', dst=muap, fun=pw, arg0=x)
    fb.op('Add', dst=ffsp, a=ffsp, b=muap)
    fb.label('mu_att')
    b.call('haxe.ds.ObjectMap.set', bcmc, fb.dyn(x), fb.dyn(t))
    # every free army belongs to the muster (P_RALLY, refreshed each pass: vanilla's siege picks leave it), on its way
    # or already there
    rcl = fb.reg(cx.t('bool'))
    fb.op('Call2', dst=rcl, fun=helpers['claim'], arg0=x, arg1=b.const('f64', P_RALLY))
    _skip_striking(fb, b, cx, helpers, x, 'mu')  # in an en-route strike (rules/strike.py) or waiting out a worm
    fb.op('JNull', reg=ffv, offset='mu_nff')
    ffxd = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=ffxd, src=b.call('ent.Entity.getDistTo', x, ffv))
    # not launched yet (above): to the gathering point; there, or already at the village, it waits
    fb.op('JTrue', cond=ffgo, offset='mu_ffl')
    fb.op('JSLte', a=ffxd, b=b.const('f64', BC_AT_RING), offset='mu_ffh')
    _dist2(fb, b, x, gpx, gpy, gpq, gpd)
    fb.op('JSLte', a=gpq, b=b.const('f64', BC_AT_RING * BC_AT_RING), offset='mu_ffh')
    _throttle(fb, b, cx, 'bcmv', x, BC_MOVE_T, 'mu_ffh')
    _route_move(x, None, 'mu_ffgd', 'mu', tzone=fgz, tx=gpx, ty=gpy)
    fb.label('mu_ffgd')
    _move_to(fb, b, cx, x, gpx, gpy, fac)
    fb.label('mu_ffh')
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset='mu')
    fb.label('mu_ffl')
    # launched: siege it from BC_DR_AT (the action walks the army in), else walk there
    fb.op('JSGt', a=ffxd, b=b.const('f64', BC_DR_AT), offset='mu_ffw')
    fb.op('JNull', reg=b.call('ent.Entity.getActionDesc', x), offset='mu_ffi')  # idle: now; busy: every BC_DR_BUSY_T
    _throttle(fb, b, cx, 'bcffb', x, BC_DR_BUSY_T, 'mu')
    fb.label('mu_ffi')
    _throttle(fb, b, cx, 'bcffs', x, BC_DR_T, 'mu')
    ffxe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ffxe, src=x)
    _do_on(fb, b, cx, ffxe, 'ArmySiege', ffv, fac)
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset='mu')
    fb.label('mu_ffw')
    _throttle(fb, b, cx, 'bcmv', x, BC_MOVE_T, 'mu')
    _route_move(x, ffv, 'mu_ffd', 'mu')
    fb.label('mu_ffd')
    _move_to(fb, b, cx, x, b.field(ffv, 'posx'), b.field(ffv, 'posy'), fac)
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset='mu')
    fb.label('mu_nff')
    fb.op('JNull', reg=fsv, offset='mu_st')
    # backing a partner's foothold siege: walk (around the deep desert) to it
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', x, fsv), b=b.const('f64', BC_AT_RING), offset='mu')
    _throttle(fb, b, cx, 'bcmv', x, BC_MOVE_T, 'mu')
    _route_move(x, fsv, 'mu_fd', 'mu')
    fb.label('mu_fd')
    _move_to(fb, b, cx, x, b.field(fsv, 'posx'), b.field(fsv, 'posy'), fac)
    fb.op('Incr', dst=n)
    _throttle(fb, b, cx, 'bcftl', fac, 30, 'mu')
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'foot'), ('tgt', fsv)])
    fb.op('JAlways', offset='mu')
    fb.label('mu_st')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', x, stg), b=b.const('f64', BC_STAGE_AT), offset='mu')
    _throttle(fb, b, cx, 'bcmv', x, BC_MOVE_T, 'mu')
    # around the deep desert (aimod_route): while the staging zone isn't the next zone on a desert-free zone path,
    # walk to the next zone's centre; vanilla's Patrol path goes straight over it (user 2026-10-24: they just die in
    # the deep desert, not running around it)
    _route_move(x, stg, 'mu_pat', 'mu')
    fb.label('mu_pat')
    parr = _new_array(fb, b, cx)
    b.call('hl.types.ArrayObj.push', parr, fb.dyn(x))
    pk = fb.reg(cx.t('logic.ai.AIOrderType'))
    fb.op('MakeEnum', dst=pk, construct=PATROL, args=[stg])
    pnul = []
    for n_ in (6, 7, 8, 9, 10):  # sa, mm, om, data, onComplete
        r_ = fb.reg(at[n_])
        fb.op('Null', dst=r_)
        pnul.append(r_)
    pres = fb.reg(cx.t('logic.ai.AIOrder'))
    fb.op('CallN', dst=pres, fun=helpers.get('addOrder', add.findex.value),
          args=[b.field(ctrl, 'aiOrders'), pk, b.const('i32', 0), parr, stg, fb.string('Move')] + pnul)
    fb.op('JNull', reg=pres, offset='mu')
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset='mu')
    fb.label('mud')
    fb.op('JSLte', a=n, b=b.const('i32', 0), offset='end')
    _throttle(fb, b, cx, 'bcmu', fac, 30, 'end')
    _log_ev(fb, b, cx, helpers, 'bcamp', [('f', fb.get(fac, 'kind')), ('act', 'muster'), ('tgt', be), ('s', stg),
                                          ('n', fb.dyn(n)), ('ph', fb.dyn(ph))])
    fb.op('JAlways', offset='end')
    # go: once per go time, our armies near the base launch the assault together
    _give(c, gpq=gpq, gpx=gpx, gpy=gpy, n_=n_, r_=r_)
