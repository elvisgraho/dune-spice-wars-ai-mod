"""Ornithopters (`orni-keep`, `orni-refund`, `orni-crew`; user: 4 ornithopters asap and kept all match, one escort per
harvester, harvesters in safe mode).

Vanilla `AIController.checkOrnithopters` (f@8267, every regularUpdate): need = recon (2, Smugglers 3, only while a
zone is unreconned, else 0) + one per refinery (only once < AI_Ornithopters_ReconRatio_RefineryAssignment 0.2 of
the zones are unreconned and the faction has CrewPoints_Max_Flat (attribute 845) > 0) + 1 extra recon (0 < refineries
< 3, zones unreconned); buys one when below, refunds the last ones when above (so a scouted map refunds every scout);
ornis at index recon .. recon + refineries - 1 escort (`OrniEscortAlly`) the first harvester of refinery index - recon
when idle. Safe mode (trait Safe_Harvester: auto-recall at the first worm sign, never eaten; needs a live assigned
ornithopter within NEAR_DIST, `Harvester.tryActivateSafeMode` waits for it via `wantsSafeMode`, a dead escort turns it
off) is only ever switched on by the player's HarvesterUI.

- data: AI_Ornithopters_ReconRatio_RefineryAssignment 0.2 -> 1.01 (escorts from the first refinery on).
- `orni-crew`: checkOrnithopters' getAtbVal(845) -> max(vanilla, 1): every faction with a refinery escorts.
- `aimod_orni_need(f)` -> min(ORNI_CAP, max(ORNI_MIN, refineries + recon (Smugglers 3, else 2))): the escort slots
  come after vanilla's recon slots, so the count must cover both.
- `orni-refund`: its requestRefund call -> always refused (Invalid; user: never delete ornithopters, POI finds
  included, use them). checkOrnithopters is the AI's only ornithopter refund (checkCommandPoint refunds Command
  Point units only; the other callers are UI / quest / map-event code).
- `orni-keep`: regularUpdate's checkOrnithopters call -> vanilla, then (1) below the need: `buyUnit("Ornithopter")`
  at most every ORNI_BUY_T s (log `obuy` n / need / r = EReason index); (2) every harvester of our refineries with a
  live escort and not in (or waiting for) safe mode: `tryActivateSafeMode` (log `osafe` h); (3) every ORNI_LOG_T s
  `ostat` n / need / ref / esc (harvesters escorted) / safe; (3b) every ornithopter of ours
  not Autonomous (trait Autonomous_Ornithopter = the auto-recon toggle) is set Autonomous (log `oauto`, throttled). Fails safe: in a trap."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

ORNI_MIN = 4      # user: 4 ornithopters asap, kept all match
ORNI_CAP = 8      # data maxCount 12
ORNI_BUY_T = 15   # s between our buys (a bought orni trains a few s: no double buy)
ORNI_LOG_T = 60
INVALID = 2       # EReason: Do Success Invalid ...


def _units(fb, b, fac, fail):
    arr = b.cast(fb.get(fac, 'units', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=arr, offset=fail)
    return arr


def _orni_count(fb, b, cx, fac, n, done):
    """n = our live ornithopters."""
    fb.op('Mov', dst=n, src=b.const('i32', 0))
    arr = _units(fb, b, fac, done)
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    h = _uid('oc')
    b.loop_head(h)
    fb.op('JSGte', a=i, b=b.field(arr, 'length'), offset=done)
    u = b.cast(b.call('hl.types.ArrayObj.getDyn', arr, i), 'ent.Unit')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=u, offset=h)
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', u), offset=h)
    k = b.call('ent.Unit.get_baseKind', u)
    fb.op('JNull', reg=k, offset=h)
    fb.op('JNotEq', a=b.call('String.__compare', k, fb.dyn(fb.string('Ornithopter'))), b=b.const('i32', 0), offset=h)
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset=h)


def build_orni_need(cx):
    fb = FB(cx, [cx.t('ent.Faction')], cx.t('i32'))
    b = B(fb)
    need = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=need, src=b.const('i32', ORNI_MIN))
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    arr = b.cast(fb.get(0, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=arr, offset='end')
    r = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=r, src=b.const('i32', 2))
    kd = b.field(0, 'kind')
    fb.op('JNull', reg=kd, offset='rc')
    fb.op('JNotEq', a=b.call('String.__compare', kd, fb.dyn(fb.string('Smugglers'))), b=b.const('i32', 0),
          offset='rc')
    fb.op('Mov', dst=r, src=b.const('i32', 3))
    fb.label('rc')
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('s')
    fb.op('JSGte', a=i, b=b.field(arr, 'length'), offset='sd')
    s = b.cast(b.call('hl.types.ArrayObj.getDyn', arr, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=s, offset='s')
    fb.op('JNull', reg=b.call('ent.Structure.get_refinery', s), offset='s')
    fb.op('Incr', dst=r)
    fb.op('JAlways', offset='s')
    fb.label('sd')
    fb.op('JSLte', a=r, b=need, offset='cap')
    fb.op('Mov', dst=need, src=r)
    fb.label('cap')
    fb.op('JSLte', a=need, b=b.const('i32', ORNI_CAP), offset='umax')
    fb.op('Mov', dst=need, src=b.const('i32', ORNI_CAP))
    # never above the faction's ornithopter limit (Faction.getUnitMax; Fremen 2: match 08:38 bought into
    # MaxOrniLimitReached 197 times with 2)
    fb.label('umax')
    um = b.call('ent.Faction.getUnitMax', 0, fb.string('Ornithopter'))
    fb.op('JSLte', a=need, b=um, offset='end')
    fb.op('Mov', dst=need, src=um)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=need)
    return fb.build()


def build_orni_refund(cx, new_ids):
    orig = cx.fn('ent.Entity.requestRefund')
    ft = cx.code.types[orig.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=orig.type.value)
    res = fb.reg(ft.ret.value)
    fb.op('MakeEnum', dst=res, construct=INVALID, args=[])
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    _redirect(cx, 'ent.Entity.requestRefund', ['logic.ai.AIController.checkOrnithopters'], w)


def build_orni_crew(cx, new_ids):
    orig = cx.fn('ent.Object.getAtbVal')
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('Call4', dst=res, fun=orig.findex.value, arg0=0, arg1=1, arg2=2, arg3=3)
    one = b.const('f64', 1)
    fb.op('JSGte', a=res, b=one, offset='ret')
    fb.op('Mov', dst=res, src=one)
    fb.label('ret')
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    _redirect(cx, 'ent.Object.getAtbVal', ['logic.ai.AIController.checkOrnithopters'], w)


def build_orni_keep(cx, helpers, need_fn, new_ids, land):
    orig = cx.fn('logic.ai.AIController.checkOrnithopters')
    ft = cx.code.types[orig.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    void = fb.reg(cx.t('void'))
    fb.op('Call1', dst=void, fun=orig.findex.value, arg0=0)  # vanilla, outside any trap
    guard = fb.try_()
    fac = b.field(0, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    n, need = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    _orni_count(fb, b, cx, fac, n, 'cnt')
    fb.label('cnt')
    fb.op('Call1', dst=need, fun=need_fn, arg0=fac)
    nf, needf = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=nf, src=n)
    fb.op('ToSFloat', dst=needf, src=need)
    # (1) buy toward the need
    fb.op('JSGte', a=n, b=need, offset='safe')
    _throttle(fb, b, cx, 'obuy', fac, ORNI_BUY_T, 'safe')
    r = b.call('logic.ai.AIController.buyUnit', 0, fb.string('Ornithopter'))
    ri = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ri, value=r)
    _log_ev(fb, b, cx, helpers, 'obuy', [('f', fb.get(fac, 'kind')), ('n', nf), ('need', needf), ('r', fb.dyn(ri))])
    # (2) safe mode on every escorted harvester; (3) counts for `ostat`
    fb.label('safe')
    arr = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=arr, offset='end')
    ref, esc, sf = (fb.reg(cx.t('i32')) for _ in range(3))
    for r_ in (ref, esc, sf):
        fb.op('Mov', dst=r_, src=b.const('i32', 0))
    i, j = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('s')
    fb.op('JSGte', a=i, b=b.field(arr, 'length'), offset='sd')
    s = b.cast(b.call('hl.types.ArrayObj.getDyn', arr, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=s, offset='s')
    rf = b.call('ent.Structure.get_refinery', s)
    fb.op('JNull', reg=rf, offset='s')
    fb.op('Incr', dst=ref)
    hs = b.cast(fb.get(rf, 'harvesters', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=hs, offset='s')
    fb.op('Mov', dst=j, src=b.const('i32', 0))
    b.loop_head('h')
    fb.op('JSGte', a=j, b=b.field(hs, 'length'), offset='s')
    hd = b.call('hl.types.ArrayObj.getDyn', hs, j)
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=hd, offset='h')
    # ent.Harvester extends SpiceHarvester: only Harvesters carry an escort / safe mode
    hcl = fb.reg(cx.t('ent.$Harvester'))
    fb.op('GetGlobal', dst=hcl, **{'global': cx.global_of('ent.$Harvester')})
    fb.op('JFalse', cond=b.call('hl.BaseType.check', hcl, hd), offset='h')
    h = b.cast(hd, 'ent.Harvester')
    fb.op('JFalse', cond=b.call('ent.Harvester.get_isOrnithopterAssigned', h), offset='h')
    fb.op('Incr', dst=esc)
    fb.op('JFalse', cond=b.call('ent.Harvester.isInSafeMode', h), offset='h_on')
    fb.op('Incr', dst=sf)
    fb.op('JAlways', offset='h')
    fb.label('h_on')
    fb.op('JTrue', cond=b.field(h, 'wantsSafeMode'), offset='h')
    b.call('ent.Harvester.tryActivateSafeMode', h)
    _log_ev(fb, b, cx, helpers, 'osafe', [('f', fb.get(fac, 'kind')), ('h', h)])
    fb.op('JAlways', offset='h')
    fb.label('sd')
    _throttle(fb, b, cx, 'ostat', fac, ORNI_LOG_T, 'auto')
    _log_ev(fb, b, cx, helpers, 'ostat', [('f', fb.get(fac, 'kind')), ('n', nf), ('need', needf),
                                          ('ref', fb.dyn(ref)), ('esc', fb.dyn(esc)), ('safe', fb.dyn(sf))])
    # (3b) auto recon on for every ornithopter of ours (user: POI finds included; vanilla spawns them off, a
    # Follow-type order turns it off for a player owner). An AI's ornithopter scouts without it (canAutoRecon: isAI),
    # but a faction taken over by a player (Player.onConnect) needs the trait (attribute 893 Ornithopter_AutoRecon)
    fb.label('auto')
    ua = _units(fb, b, fac, 'spare')
    k = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head('au')
    fb.op('JSGte', a=k, b=b.field(ua, 'length'), offset='spare')
    ux = b.cast(b.call('hl.types.ArrayObj.getDyn', ua, k), 'ent.Unit')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=ux, offset='au')
    acl = fb.reg(cx.t('ent.$Ornithopter'))
    fb.op('GetGlobal', dst=acl, **{'global': cx.global_of('ent.$Ornithopter')})
    fb.op('JFalse', cond=b.call('hl.BaseType.check', acl, fb.dyn(ux)), offset='au')
    ox = b.cast(fb.dyn(ux), 'ent.Ornithopter')
    fb.op('JNull', reg=ox, offset='au')
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', ox), offset='au')
    fb.op('JTrue', cond=b.call('ent.Ornithopter.isAutonomous', ox), offset='au')
    tv = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=tv, value=True)
    b.call('ent.Ornithopter.setAutonomous', ox, tv)
    _throttle(fb, b, cx, 'oauto', fac, ORNI_LOG_T, 'au')
    _log_ev(fb, b, cx, helpers, 'oauto', [('f', fb.get(fac, 'kind')), ('o', ox)])
    fb.op('JAlways', offset='au')
    fb.label('spare')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    w = fb.build()
    new_ids.add(w)
    _redirect(cx, 'logic.ai.AIController.checkOrnithopters', ['logic.ai.AIController.regularUpdate'], w)


def build_orni(cx, helpers, new_ids, land):
    need_fn = build_orni_need(cx)
    new_ids.add(need_fn)
    build_orni_crew(cx, new_ids)
    build_orni_refund(cx, new_ids)
    build_orni_keep(cx, helpers, need_fn, new_ids, land)
    return {'orni-crew': 1, 'orni-refund': 1, 'orni-keep': 1}
