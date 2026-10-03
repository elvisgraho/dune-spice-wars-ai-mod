"""Underworld HQs (Smugglers; AI-POLICY §5a "Underworld HQs"): how many, where, and which extensions.

The failure (user match notes): vanilla `AIController.checkUWHeadquarters` installs a new HQ whenever at most one of
ours has no extension, with no cap, so Smugglers sank all Authority into HQs (escalating cost 5, 10, 15, ...). Its
village score (`HScoring.headquarterStructures`) has no faction spread and no recapture risk. Regular extensions have
no case in `getBuildingStructureScore`: base + cdb aiWeights, so Whisperers Lair went onto villages with no Intel and
host-gain extensions were built.

- **Cap** (`uhq-cap`, wrapper of the regularUpdate -> checkUWHeadquarters call): no new HQ while ours (kind
  UWHeadquarters, not major ones) >= max(UHQ_MIN, UHQ_PER_VILLAGE x our villages). Built ones stay. Log `uhqcap`.
- **Placement** (`uhq-place`, wrapper of the headquarterStructures call): one HQ in every faction first (while a
  candidate's owner hosts none of ours, candidates of covered owners are dropped); score = (vanilla + UHQ_PLACE_W x the
  best production-extension gain there) x (1 + UHQ_MB_W x closeness to the owner's main base within UHQ_MB_R). Vanilla
  still picks among its top 2 at random by weight. Log `uhqp` (throttled).
- **Extensions** (`uhq-ext`, wrapper under turret-steer on the scoring closure's getBuildingStructureScore call): a pair
  on a regular HQ of ours scores aimod_uhqval(host village, k): UHQ_EXT table (Harvesters' Union flat UHQ_HU; a
  production extension UHQ_EXT_BASE + its gain from the host's current production, only once the host produces a
  listed resource at its minimum); anything
  else NaN (dropped: the slot waits until the village produces something worth taking). Vanilla NaN (not buildable)
  stays NaN; a pair on a full HQ (no empty slot) is NaN too: vanilla scores pairs without slots, picks among its top 2
  only, and a full HQ's Harvesters' Union pair at UHQ_HU failed every pick and starved the village buildings. Log
  `uhqx` once per HQ per 60 s.
Fails safe: every wrapper runs vanilla on error (trap), and the score wrappers keep vanilla's value."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def _nan(fb, b, cx):
    r = fb.reg(cx.t('f64'))
    z = b.const('f64', 0)
    fb.op('SDiv', dst=r, a=z, b=z)
    return r


def _is_kind(fb, b, s, kind, no):
    """Jump to `no` unless structure s has kind `kind` (a dyn String register built once, outside loops: a string
    per iteration allocates)."""
    k = b.field(s, 'kind')
    fb.op('JNull', reg=k, offset=no)
    fb.op('JNotEq', a=b.call('String.__compare', k, kind), b=b.const('i32', 0), offset=no)


def _gain(fb, b, cx, v, spec, out, ok):
    """out = sum over spec of max(0, v's production of the resource) x share x weight; ok = some resource reaches
    its minimum production."""
    gp = cx.fn('ent.Structure.getResourceProduction')
    gpa = [a.value for a in cx.code.types[gp.type.value].definition.args]
    fb.op('Mov', dst=out, src=b.const('f64', 0))
    fb.op('Bool', dst=ok, value=False)
    zero = b.const('f64', 0)
    for res, share, w, lo in spec:
        nul = []
        for t_ in gpa[2:]:
            r_ = fb.reg(t_)
            fb.op('Null', dst=r_)
            nul.append(r_)
        p = fb.reg(cx.t('f64'))
        fb.op('CallN', dst=p, fun=gp.findex.value, args=[v, b.const('i32', res)] + nul)
        skip = _uid('gneg')
        fb.op('JSLte', a=p, b=zero, offset=skip)  # NaN fails too
        low = _uid('glow')
        fb.op('JSLt', a=p, b=_ratio(fb, b, lo), offset=low)
        fb.op('Bool', dst=ok, value=True)
        fb.label(low)
        fb.op('Mul', dst=p, a=p, b=_ratio(fb, b, share * w))
        fb.op('Add', dst=out, a=out, b=p)
        fb.label(skip)


def build_uhq_value(cx):
    """aimod_uhqval(v: village, k: extension id) -> f64 score of extension k on a regular HQ in v (NaN = don't)."""
    fb = FB(cx, [cx.t('ent.Structure'), cx.t('String')], cx.t('f64'))
    b = B(fb)
    res = _nan(fb, b, cx)
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    g = fb.reg(cx.t('f64'))
    ok = fb.reg(cx.t('bool'))
    for ext, spec in UHQ_EXT.items():
        nxt = _uid('ext')
        fb.op('JNotEq', a=b.call('String.__compare', 1, fb.dyn(fb.string(ext))), b=b.const('i32', 0), offset=nxt)
        if isinstance(spec, (int, float)):
            fb.op('Mov', dst=res, src=b.const('f64', spec))
        else:
            _gain(fb, b, cx, 0, spec, g, ok)
            fb.op('JFalse', cond=ok, offset='end')
            fb.op('Add', dst=res, a=g, b=b.const('f64', UHQ_EXT_BASE))
        fb.op('JAlways', offset='end')
        fb.label(nxt)
    fb.label('end')
    fb.op('Ret', ret=res)
    return fb.build()


def build_uhq_best_gain(cx):
    """aimod_uhqgain(v) -> the best gain at village v among production extensions it qualifies for (0 if none)."""
    fb = FB(cx, [cx.t('ent.Structure')], cx.t('f64'))
    b = B(fb)
    best = b.const('f64', 0)
    fb.op('JNull', reg=0, offset='end')
    g = fb.reg(cx.t('f64'))
    ok = fb.reg(cx.t('bool'))
    for spec in UHQ_EXT.values():
        if isinstance(spec, (int, float)):
            continue
        _gain(fb, b, cx, 0, spec, g, ok)
        lo = _uid('gb')
        fb.op('JFalse', cond=ok, offset=lo)
        fb.op('JSLte', a=g, b=best, offset=lo)
        fb.op('Mov', dst=best, src=g)
        fb.label(lo)
    fb.label('end')
    fb.op('Ret', ret=best)
    return fb.build()


def _count_hqs(fb, b, cx, fac, n, no):
    """n = our regular UWHeadquarters count."""
    uwk = fb.dyn(fb.string('UWHeadquarters'))
    structs = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=structs, offset=no)
    ln = b.field(structs, 'length')
    i = b.const('i32', 0)
    fb.op('Mov', dst=n, src=b.const('i32', 0))
    loop, done, skip = _uid('hq'), _uid('hqd'), _uid('hqs')
    b.loop_head(loop)
    fb.op('JSGte', a=i, b=ln, offset=done)
    s = b.cast(b.call('hl.types.ArrayObj.getDyn', structs, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=s, offset=loop)
    _is_kind(fb, b, s, uwk, loop)
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset=loop)
    fb.label(done)


def build_uhq_cap(cx, helpers, new_ids):
    """Wrapper of AIController.regularUpdate's checkUWHeadquarters call (see module doc)."""
    orig = cx.fn('logic.ai.AIController.checkUWHeadquarters')
    ft = cx.code.types[orig.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    void = fb.reg(cx.t('void'))
    stop = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=stop, value=False)
    guard = fb.try_()
    fac = b.field(0, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    n = fb.reg(cx.t('i32'))
    _count_hqs(fb, b, cx, fac, n, 'end')
    cap = fb.reg(cx.t('i32'))
    fb.op('Mul', dst=cap, a=b.field(b.call('ent.Faction.getVillages', fac), 'length'), b=b.const('i32', UHQ_PER_VILLAGE))
    fb.op('JSGte', a=cap, b=b.const('i32', UHQ_MIN), offset='capok')
    fb.op('Mov', dst=cap, src=b.const('i32', UHQ_MIN))
    fb.label('capok')
    fb.op('JSGte', a=n, b=cap, offset='capped')
    # Annex reserve: the next HQ costs UHQ_AUTH x (HQs + 1) Authority; no install that leaves less than our cheapest
    # Annex candidate (annex.py `acmin`, scored within UHQ_RES_T), but only while we hold >= UHQ_SOFT_PER_VILLAGE x
    # villages HQs or the Annex is near (Authority + UHQ_NEAR_AU >= its cost). Smugglers held 11 HQs (cap 18 at 6 villages) and
    # sat at 35-94 Authority for 13 min with a 123-cost Annex queued. No candidate scored lately: no reserve
    # Smugglers only: regularUpdate calls checkUWHeadquarters for every AI faction (vanilla returns at once without
    # the Smugglers-only ability); the reserve skipped that call and logged `uhqres` n 0 for Atreides / Fremen /
    # Harkonnen 22 times in one match
    ukd = b.field(fac, 'kind')
    fb.op('JNull', reg=ukd, offset='end')
    fb.op('JNotEq', a=b.call('String.__compare', ukd, fb.dyn(fb.string('Smugglers'))), b=b.const('i32', 0),
          offset='end')
    cmv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'acmin'), fb.dyn(fac))
    fb.op('JNull', reg=cmv, offset='end')
    cmt = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'acmt'), fb.dyn(fac))
    fb.op('JNull', reg=cmt, offset='end')
    cmf, age, au, nxt = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('SafeCast', dst=age, src=cmt)
    fb.op('Sub', dst=age, a=b.field(_state(fb, b, cx), 'time'), b=age)
    fb.op('JSGt', a=age, b=b.const('f64', UHQ_RES_T), offset='end')
    fb.op('SafeCast', dst=cmf, src=cmv)
    fb.op('Call2', dst=au, fun=cx.fn('ent.Faction.getResource').findex.value, arg0=fac, arg1=b.const('i32', 6))
    fb.op('ToSFloat', dst=nxt, src=n)
    fb.op('Add', dst=nxt, a=nxt, b=b.const('f64', 1))
    fb.op('Mul', dst=nxt, a=nxt, b=b.const('f64', UHQ_AUTH))
    fb.op('Sub', dst=nxt, a=au, b=nxt)  # Authority left after the install
    fb.op('JSGte', a=nxt, b=cmf, offset='end')
    # looser below the soft count: the reserve holds only while the Annex is near (Authority within UHQ_NEAR_AU of it).
    # HQs stuck at 7 for 40 min (8:00-50:00) while the cheapest Annex rose 123 -> 500 and took 10-20 min to save for;
    # an HQ costs 40-55. Past UHQ_SOFT_PER_VILLAGE x villages: strict (more HQs need more villages first)
    soft = fb.reg(cx.t('i32'))
    fb.op('Mul', dst=soft, a=b.field(b.call('ent.Faction.getVillages', fac), 'length'),
          b=b.const('i32', UHQ_SOFT_PER_VILLAGE))
    fb.op('JSGte', a=n, b=soft, offset='strict')
    near = fb.reg(cx.t('f64'))
    fb.op('Add', dst=near, a=au, b=b.const('f64', UHQ_NEAR_AU))
    fb.op('JSLt', a=near, b=cmf, offset='end')  # the Annex is far off: build
    fb.label('strict')
    fb.op('Bool', dst=stop, value=True)
    _throttle(fb, b, cx, 'uhqres', fac, 120, 'end')
    nf2 = fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=nf2, src=n)
    _log_ev(fb, b, cx, helpers, 'uhqres', [('f', fb.get(fac, 'kind')), ('n', nf2), ('au', au), ('left', nxt),
                                           ('cmin', cmf)])
    fb.op('JAlways', offset='end')
    fb.label('capped')
    fb.op('Bool', dst=stop, value=True)
    _throttle(fb, b, cx, 'uhqcap', fac, 120, 'end')
    nf, cf = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=nf, src=n)
    fb.op('ToSFloat', dst=cf, src=cap)
    _log_ev(fb, b, cx, helpers, 'uhqcap', [('f', fb.get(fac, 'kind')), ('n', nf), ('cap', cf)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('JTrue', cond=stop, offset='ret')
    fb.op('Call1', dst=void, fun=orig.findex.value, arg0=0)
    fb.label('ret')
    fb.op('Ret', ret=void)
    w = fb.build()
    new_ids.add(w)
    _redirect(cx, 'logic.ai.AIController.checkUWHeadquarters', ['logic.ai.AIController.regularUpdate'], w)
    return {'uhq-cap': 1}


def build_uhq_place(cx, helpers, gain, new_ids):
    """Wrapper of checkUWHeadquarters' headquarterStructures(villages, f) call (see module doc)."""
    orig = cx.fn('logic.ai.$HScoring.headquarterStructures')
    ft = cx.code.types[orig.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('Call2', dst=res, fun=orig.findex.value, arg0=0, arg1=1)  # vanilla scores, outside the trap
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    structs = b.cast(fb.get(1, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=structs, offset='end')
    sn = b.field(structs, 'length')
    cn = b.field(0, 'length')
    i, j = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    any_new, cov = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('Bool', dst=any_new, value=False)
    nnew, nkept = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=nnew, src=b.const('f64', 0))
    fb.op('Mov', dst=nkept, src=b.const('f64', 0))
    v = fb.reg(cx.t('ent.Structure'))
    own = fb.reg(cx.t('ent.Faction'))
    uwk = fb.dyn(fb.string('UWHeadquarters'))

    def covered(tag):
        """cov = one of our regular HQs stands in a village owned by `own`."""
        fb.op('Bool', dst=cov, value=False)
        fb.op('Mov', dst=j, src=b.const('i32', 0))
        b.loop_head(f'{tag}c')
        fb.op('JSGte', a=j, b=sn, offset=f'{tag}cd')
        s = b.cast(b.call('hl.types.ArrayObj.getDyn', structs, j), 'ent.Structure')
        fb.op('Incr', dst=j)
        fb.op('JNull', reg=s, offset=f'{tag}c')
        _is_kind(fb, b, s, uwk, f'{tag}c')
        host = b.field(b.cast(fb.dyn(s), 'ent.Headquarter'), 'structHost')
        fb.op('JNull', reg=host, offset=f'{tag}c')
        fb.op('JNotEq', a=b.call('ent.Entity.get_owner', host), b=own, offset=f'{tag}c')
        fb.op('Bool', dst=cov, value=True)
        fb.label(f'{tag}cd')

    def candidate(tag, skip):
        """v = candidate i (i advanced), own = its owner; jump to `skip` when unusable."""
        fb.op('Mov', dst=v, src=b.cast(b.call('hl.types.ArrayObj.getDyn', 0, i), 'ent.Structure'))
        fb.op('Incr', dst=i)
        fb.op('JNull', reg=v, offset=skip)
        fb.op('Mov', dst=own, src=b.cast(b.call('ent.Entity.get_owner', v), 'ent.Faction'))
        fb.op('JNull', reg=own, offset=skip)

    # pass 1: does any candidate's owner host none of our HQs yet?
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('p1')
    fb.op('JSGte', a=i, b=cn, offset='p1d')
    candidate('a', 'p1')
    covered('a')
    fb.op('JTrue', cond=cov, offset='p1')
    fb.op('Bool', dst=any_new, value=True)
    fb.label('p1d')
    # pass 2: drop covered owners' villages while a new faction is available; re-score the rest
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    sc, d, md, f_ = (fb.reg(cx.t('f64')) for _ in range(4))
    b.loop_head('p2')
    fb.op('JSGte', a=i, b=cn, offset='end_log')
    candidate('b', 'p2')
    scv = b.call('haxe.ds.ObjectMap.get', res, fb.dyn(v))
    fb.op('JNull', reg=scv, offset='p2')
    fb.op('SafeCast', dst=sc, src=scv)
    fb.op('JFalse', cond=any_new, offset='keep')
    covered('b')
    fb.op('JFalse', cond=cov, offset='newf')
    b.call('haxe.ds.ObjectMap.remove', res, fb.dyn(v))
    fb.op('JAlways', offset='p2')
    fb.label('newf')
    fb.op('Add', dst=nnew, a=nnew, b=b.const('f64', 1))
    fb.label('keep')
    fb.op('Add', dst=nkept, a=nkept, b=b.const('f64', 1))
    gv = fb.reg(cx.t('f64'))
    fb.op('Call1', dst=gv, fun=gain, arg0=v)
    fb.op('Mul', dst=gv, a=gv, b=_ratio(fb, b, UHQ_PLACE_W))
    fb.op('Add', dst=sc, a=sc, b=gv)
    # closeness to the owner's nearest main base
    fb.op('Mov', dst=md, src=b.const('f64', 1 << 30))
    bases = b.field(own, 'mainBases')
    fb.op('JNull', reg=bases, offset='mbd')
    bn = b.field(bases, 'length')
    fb.op('Mov', dst=j, src=b.const('i32', 0))
    b.loop_head('mb')
    fb.op('JSGte', a=j, b=bn, offset='mbd')
    me = b.cast(b.call('hl.types.ArrayObj.getDyn', bases, j), 'ent.Entity')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=me, offset='mb')
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', me, v))
    fb.op('JSGte', a=d, b=md, offset='mb')
    fb.op('Mov', dst=md, src=d)
    fb.op('JAlways', offset='mb')
    fb.label('mbd')
    r = b.const('f64', UHQ_MB_R)
    fb.op('JSGte', a=md, b=r, offset='set')
    fb.op('SDiv', dst=f_, a=md, b=r)
    fb.op('Sub', dst=f_, a=b.const('f64', 1), b=f_)
    fb.op('Mul', dst=f_, a=f_, b=_ratio(fb, b, UHQ_MB_W))
    fb.op('Add', dst=f_, a=f_, b=b.const('f64', 1))
    fb.op('Mul', dst=sc, a=sc, b=f_)
    fb.label('set')
    b.call('haxe.ds.ObjectMap.set', res, fb.dyn(v), fb.dyn(sc))
    fb.op('JAlways', offset='p2')
    fb.label('end_log')
    _throttle(fb, b, cx, 'uhqp', 1, 60, 'end')
    nc = fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=nc, src=cn)
    _log_ev(fb, b, cx, helpers, 'uhqp', [('f', fb.get(1, 'kind')), ('cand', nc), ('kept', nkept), ('newf', nnew)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    _redirect(cx, 'logic.ai.$HScoring.headquarterStructures', ['logic.ai.AIController.checkUWHeadquarters'], w)
    return {'uhq-place': 1}


def build_uhq_ext(cx, helpers, val, new_ids):
    """Score wrapper for getBuildingStructureScore (pair {s, k}, f, context, noStocks); returns its function id for
    turret-steer to call instead of vanilla (see module doc)."""
    orig = cx.fn('logic.ai.$HScoring.getBuildingStructureScore')
    ft = cx.code.types[orig.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Call4', dst=res, fun=orig.findex.value, arg0=0, arg1=1, arg2=2, arg3=3)  # vanilla, outside the trap
    guard = fb.try_()
    fb.op('JSGte', a=res, b=b.const('f64', -(1 << 30)), offset='real')  # NaN = not buildable: keep it
    fb.op('JAlways', offset='end')
    fb.label('real')
    fb.op('JNull', reg=1, offset='end')
    so = fb.get(0, 's')
    fb.op('JNull', reg=so, offset='end')
    s = b.cast(so, 'ent.Structure')
    fb.op('JNull', reg=s, offset='end')
    _is_kind(fb, b, s, fb.dyn(fb.string('UWHeadquarters')), 'end')
    fb.op('JNotEq', a=b.call('ent.Entity.get_owner', s), b=1, offset='end')
    hq = b.cast(fb.dyn(s), 'ent.Headquarter')
    host = b.field(hq, 'structHost')
    fb.op('JNull', reg=host, offset='end')
    # full HQ (extensions built or under way fill every slot): NaN, vanilla drops the pair. Vanilla scores pairs
    # without slots and builds only one of its top 2 (Insane): a full HQ's pair at UHQ_HU stayed on top for 30 min,
    # failed every pick (its replace step re-scores in vanilla terms: nothing to swap) and starved the village
    # buildings (Smugglers at the Plascrete cap, Harvesters' Union pairs on Tallon / Sharekh 01:49-33:06)
    occ = cx.fn('ent.Headquarter.getOccupiedOutpostSlots')
    onull = fb.reg(cx.code.types[occ.type.value].definition.args[1].value)
    fb.op('Null', dst=onull)
    used = fb.reg(cx.t('i32'))
    fb.op('Call2', dst=used, fun=occ.findex.value, arg0=hq, arg1=onull)
    fb.op('JSLt', a=used, b=b.call('ent.Headquarter.getTotalOutpostSlots', hq), offset='free')
    fb.op('Mov', dst=res, src=_nan(fb, b, cx))
    fb.op('JAlways', offset='end')
    fb.label('free')
    k = fb.get(0, 'k')
    fb.op('JNull', reg=k, offset='end')
    ks = b.cast(k, 'String')
    v0 = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=v0, src=res)
    fb.op('Call2', dst=res, fun=val, arg0=host, arg1=ks)
    # log only an extension we'd build (NaN = skip): the first pair scored was always a skipped Bootleg Market, so the
    # per-HQ throttle hid every Harvesters' Union / production pick
    fb.op('JSGte', a=res, b=b.const('f64', -(1 << 30)), offset='lg')
    fb.op('JAlways', offset='end')
    fb.label('lg')
    _throttle(fb, b, cx, 'uhqx', s, 60, 'end')
    _log_ev(fb, b, cx, helpers, 'uhqx', [('f', fb.get(1, 'kind')), ('s', host), ('k', ks), ('sc', res), ('van', v0)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    return w
