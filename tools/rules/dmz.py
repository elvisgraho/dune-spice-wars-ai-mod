"""DMZ: the border with a neighbour is taken, not burnt (AI-POLICY §5d).

Border region of E (for us): a region (zone) E owns that neighbours a region we own (territory: village-less regions
count); border village: a village of E (not a main base) in such a region. aimod_dmz(mil, dt), tick chain every DMZ_T
s per faction: for every other faction E, the count of its border regions is cached (map `dmz` faction -> ObjectMap
E -> count; read by aimod_dmzv inside vanilla's scoring, and by strat_levers' getTargetStatus wrapper, which lists
such an at-war E for vanilla's Annex / Liberate scans despite desiredStatus 0).

War with E and E holds >= DMZ_WAR 2 border regions (the DMZ is on): those villages are capture targets, never
pillaged. A pillage leaves the village Devastated for 20 days and doubles our own Annex cost there (trait Pillaged);
an Annex takes it, a Liberate leaves it neutral and untargetable for 20 days (Just Freed), a buffer nobody can take,
annexable by us after. aimod_dmzv(fac, v) = v is such a village. Readers:
- siege.build_scoring: vanilla's Pillage list drops them; its Annex / Liberate scores x DMZ_W;
- raid: liberates them when Liberate is available and affordable (unaffordable: waits; not available: left alone,
  unless pressed for pillage);
- strat (press): they rank first (distance x DMZ_PREF); pillage mode becomes a raid Liberate.

Peace / truce with E (not allied): two border villages are tolerable (user). E holding >= DMZ_PEACE 3, or 2 while
capturing a third (an at-war-less siege by E on a neutral village in a region next to ours), breaks the truce:
DiplomacyManager.declareWar(us, E) (vanilla's own declaration: Influence cost, refused in the peace-offer grace
period, with our units in E's land, ...; no treason), then the contest hunt and the press act as at war. Not while we
defend (aimod_defend), not against a stronger side (our army power >= DMZ_B x E's; Fremen DMZ_B_FREMEN: no Standing
to lose, treason is nearly free for them, so they also accept a slightly stronger E), at most once per DMZ_COOL s
per pair. Logs `dmz` act=war (r = EReason index, 1 Success) and act=on (DMZ active, once per DMZ_LOG s per pair).
Fails safe: in a trap."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def _pair_map(fb, b, cx, name, fac):
    """ObjectMap key -> value for faction `fac` under global map `name` (created when missing)."""
    outer = _global_map(fb, b, cx, name)
    got = b.call('haxe.ds.ObjectMap.get', outer, fb.dyn(fac))
    inner = fb.reg(cx.t('haxe.ds.ObjectMap'))
    have, done = _uid('pmh'), _uid('pmd')
    fb.op('JNotNull', reg=got, offset=have)
    fb.op('New', dst=inner)
    v = fb.reg(cx.t('void'))
    fb.op('Call1', dst=v, fun=cx.fn('haxe.ds.$ObjectMap.__constructor__').findex.value, arg0=inner)
    b.call('haxe.ds.ObjectMap.set', outer, fb.dyn(fac), fb.dyn(inner))
    fb.op('JAlways', offset=done)
    fb.label(have)
    fb.op('Mov', dst=inner, src=b.cast(got, 'haxe.ds.ObjectMap'))
    fb.label(done)
    return inner


def _borders(fb, b, cx, z, fac, yes):
    """Jump to `yes` when a neighbour region of zone z is owned by fac; fall through otherwise."""
    no, lo = _uid('bdn'), _uid('bdl')
    nb = b.field(z, 'neighbors')
    fb.op('JNull', reg=nb, offset=no)
    k = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head(lo)
    fb.op('JSGte', a=k, b=b.field(nb, 'length'), offset=no)
    nz = b.cast(b.call('hl.types.ArrayObj.getDyn', nb, k), 'ent.Zone')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=nz, offset=lo)
    fb.op('JEq', a=b.field(nz, 'owner'), b=fac, offset=yes)
    fb.op('JAlways', offset=lo)
    fb.label(no)


def build_dmzv(cx):
    """aimod_dmzv(fac, v) -> v is a border village of an at-war E holding >= DMZ_WAR border regions (cached count)."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Structure')], cx.t('bool'))
    b = B(fb)
    res = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=res, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    e = b.call('ent.Entity.get_owner', 1)
    fb.op('JNull', reg=e, offset='end')
    fb.op('JEq', a=e, b=0, offset='end')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', 1), offset='end')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', _state(fb, b, cx), 0, e), offset='end')
    cv = b.call('haxe.ds.ObjectMap.get', _pair_map(fb, b, cx, 'dmz', 0), fb.dyn(e))
    fb.op('JNull', reg=cv, offset='end')
    n = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=n, src=cv)
    fb.op('JSLt', a=n, b=b.const('i32', DMZ_WAR), offset='end')
    z = b.call('ent.Entity.get_zone', 1)
    fb.op('JNull', reg=z, offset='end')
    _borders(fb, b, cx, z, 0, 'yes')
    fb.op('JAlways', offset='end')
    fb.label('yes')
    fb.op('Bool', dst=res, value=True)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    return fb.build()


def build_dmz(cx, helpers, fpow, defend):
    """aimod_dmz(mil, dt) (see module doc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    state = _state(fb, b, cx)
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(state, 'time'))
    _tick(fb, b, cx, t, DMZ_T, 'end')
    cache = _pair_map(fb, b, cx, 'dmz', fac)
    cool = _pair_map(fb, b, cx, 'dmzt', fac)
    logm = _pair_map(fb, b, cx, 'dmzl', fac)
    facs = b.cast(fb.get(state, 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=facs, offset='end')
    villages = b.field(state, 'villages')
    fb.op('JNull', reg=villages, offset='end')
    vn = b.field(villages, 'length')
    fremen = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=fremen, value=False)
    fk = b.field(fac, 'kind')
    fb.op('JNull', reg=fk, offset='nfr')
    fb.op('JNotEq', a=b.call('String.__compare', fk, fb.dyn(fb.string('Fremen'))), b=b.const('i32', 0), offset='nfr')
    fb.op('Bool', dst=fremen, value=True)
    fb.label('nfr')
    k, i, n, cap, nz, zi_ = (fb.reg(cx.t('i32')) for _ in range(6))
    mp, ep, q = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Call1', dst=mp, fun=fpow, arg0=fac)
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head('f')
    fb.op('JSGte', a=k, b=b.field(facs, 'length'), offset='end')
    e = b.cast(b.call('hl.types.ArrayObj.getDyn', facs, k), 'ent.Faction')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=e, offset='f')
    fb.op('JEq', a=e, b=fac, offset='f')
    # E's border villages; neutral border villages E is capturing
    fb.op('Mov', dst=n, src=b.const('i32', 0))
    fb.op('Mov', dst=cap, src=b.const('i32', 0))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('v')
    fb.op('JSGte', a=i, b=vn, offset='vdone')
    v = b.cast(b.call('hl.types.ArrayObj.getDyn', villages, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=v, offset='v')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', v), offset='v')
    vz = b.call('ent.Entity.get_zone', v)
    fb.op('JNull', reg=vz, offset='v')
    vo = b.call('ent.Entity.get_owner', v)
    fb.op('JEq', a=vo, b=e, offset='own')
    fb.op('JNotNull', reg=vo, offset='v')
    # neutral: E besieging it (a capture)
    vsg = b.field(v, 'siege')
    fb.op('JNull', reg=vsg, offset='v')
    fb.op('JNotEq', a=b.field(vsg, 'besiegingFaction'), b=e, offset='v')
    _borders(fb, b, cx, vz, fac, 'capy')
    fb.op('JAlways', offset='v')
    fb.label('capy')
    fb.op('Incr', dst=cap)
    fb.op('JAlways', offset='v')
    fb.label('own')
    _borders(fb, b, cx, vz, fac, 'owny')
    fb.op('JAlways', offset='v')
    fb.label('owny')
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset='v')
    fb.label('vdone')
    # E's regions next to ours (territory: village-less regions too); the cache holds this count
    fb.op('Mov', dst=nz, src=b.const('i32', 0))
    ezs = b.cast(fb.get(e, 'zones', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=ezs, offset='zdone')
    fb.op('Mov', dst=zi_, src=b.const('i32', 0))
    b.loop_head('z')
    fb.op('JSGte', a=zi_, b=b.field(ezs, 'length'), offset='zdone')
    ez = b.cast(b.call('hl.types.ArrayObj.getDyn', ezs, zi_), 'ent.Zone')
    fb.op('Incr', dst=zi_)
    fb.op('JNull', reg=ez, offset='z')
    _borders(fb, b, cx, ez, fac, 'zy')
    fb.op('JAlways', offset='z')
    fb.label('zy')
    fb.op('Incr', dst=nz)
    fb.op('JAlways', offset='z')
    fb.label('zdone')
    b.call('haxe.ds.ObjectMap.set', cache, fb.dyn(e), fb.dyn(nz))
    fb.op('JTrue', cond=b.call('logic.state.State.areAtWar', state, fac, e), offset='war')
    # peace / truce: two border villages are tolerable; a third (held or being captured) breaks it
    # (an ally: declareWar refuses with IsAlly; DMZ_COOL keeps that to one try per pair)
    fb.op('JSGte', a=n, b=b.const('i32', DMZ_PEACE), offset='trig')
    fb.op('JSLt', a=n, b=b.const('i32', DMZ_PEACE - 1), offset='f')
    fb.op('JSLte', a=cap, b=b.const('i32', 0), offset='f')
    fb.label('trig')
    dfs = fb.reg(cx.t('ent.Structure'))
    fb.op('Call1', dst=dfs, fun=defend, arg0=fac)
    fb.op('JNotNull', reg=dfs, offset='f')
    fb.op('Call1', dst=ep, fun=fpow, arg0=e)
    fb.op('Mov', dst=q, src=_ratio(fb, b, DMZ_B))
    fb.op('JFalse', cond=fremen, offset='bq')
    fb.op('Mov', dst=q, src=_ratio(fb, b, DMZ_B_FREMEN))
    fb.label('bq')
    fb.op('Mul', dst=q, a=q, b=ep)
    fb.op('JSLt', a=mp, b=q, offset='f')
    cv = b.call('haxe.ds.ObjectMap.get', cool, fb.dyn(e))
    fb.op('JNull', reg=cv, offset='go')
    fb.op('SafeCast', dst=q, src=cv)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSLt', a=q, b=b.const('f64', DMZ_COOL), offset='f')
    fb.label('go')
    b.call('haxe.ds.ObjectMap.set', cool, fb.dyn(e), fb.dyn(t))
    dm = b.field(state, 'diplomacy')
    fb.op('JNull', reg=dm, offset='f')
    rr = b.call('logic.state.DiplomacyManager.declareWar', dm, fac, e)
    ri = fb.reg(cx.t('i32'))
    fb.op('Int', dst=ri, ptr=cx.code.add_i32(-1).value)
    fb.op('JNull', reg=rr, offset='rlog')
    fb.op('EnumIndex', dst=ri, value=rr)
    fb.label('rlog')
    _log_ev(fb, b, cx, helpers, 'dmz', [('f', fb.get(fac, 'kind')), ('act', 'war'), ('vs', fb.get(e, 'kind')),
                                        ('n', n), ('cap', cap), ('r', ri), ('M', mp), ('E', ep)])
    fb.op('JAlways', offset='f')
    # war: DMZ on (logged once per DMZ_LOG s per pair)
    fb.label('war')
    fb.op('JSLt', a=nz, b=b.const('i32', DMZ_WAR), offset='f')
    lv = b.call('haxe.ds.ObjectMap.get', logm, fb.dyn(e))
    fb.op('JNull', reg=lv, offset='lg')
    fb.op('SafeCast', dst=q, src=lv)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSLt', a=q, b=b.const('f64', DMZ_LOG), offset='f')
    fb.label('lg')
    b.call('haxe.ds.ObjectMap.set', logm, fb.dyn(e), fb.dyn(t))
    _log_ev(fb, b, cx, helpers, 'dmz', [('f', fb.get(fac, 'kind')), ('act', 'on'), ('vs', fb.get(e, 'kind')),
                                        ('n', nz), ('nv', n)])
    fb.op('JAlways', offset='f')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
