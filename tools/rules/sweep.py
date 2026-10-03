"""Map sweep (memory): our added global ObjectMaps keyed by armies, orders or fights never dropped their dead keys
and kept those objects alive (strong refs): hunt progress, gather holds, spos, heal / retreat commits, throttles,
en-route strikes, ... one entry per army / order / fight ever seen, for the whole match.

Every SWEEP_T s (in the tick chain, any faction's tick): for every added map (all names in GLOBALS at the end of the
build, so maps created by rules built after the chain are swept too), the key snapshot (std hokeys, as
ObjectMap.keys) is walked and a key is removed when it is a dead / removed entity (ent.Entity.isDead: army,
structure, ...), an AIOrder with no units left (AIOrder.stop empties them; an order whose armies all died too), or
a Warzone no longer in State.warzones.warzones (the fight ended). Other keys (factions, the State, live entities) stay.
Each test runs in its own trap (a key of another type fails the cast and is skipped). Logs `sweep` (n removed,
keys = keys seen, maps, m1 / k1 and m2 / k2 the two largest maps by name and key count)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def sweep_stub(cx):
    """Placeholder in the tick chain: install swaps its call for the real sweeper once every map exists."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    void = fb.reg(cx.t('void'))
    fb.op('Ret', ret=void)
    return fb.build()


def build_sweep(cx, helpers, names):
    """aimod_sweep(mil, dt) (see module doc); names = the global map names to sweep."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    state = _state(fb, b, cx)
    t = b.field(state, 'time')
    _tick(fb, b, cx, t, SWEEP_T, 'end')
    nat = next(f for f in cx.code.natives if f.name.resolve(cx.code) == 'hokeys' and f.lib.resolve(cx.code) == 'std')
    arr_t = cx.code.types[nat.type.value].definition.ret.value
    # State.warzones (logic.state.Warzones).warzones (hxbit ArrayProxyData).array: the live fights
    wz_arr = b.cast(b.field(b.field(b.field(state, 'warzones'), 'warzones'), 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=wz_arr, offset='end')
    wz_ok = True
    rem, seen = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=rem, src=b.const('i32', 0))
    fb.op('Mov', dst=seen, src=b.const('i32', 0))
    i, n = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    key = fb.reg(cx.t('dyn'))
    ke = fb.reg(cx.t('ent.Entity'))
    # the two largest maps (name, keys): which map keeps growing (keys 165 -> 1275 over 106 min, n ~0 per pass)
    t1n, t2n = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    t1s, t2s = fb.reg(cx.t('String')), fb.reg(cx.t('String'))
    fb.op('Mov', dst=t1n, src=b.const('i32', -1))
    fb.op('Mov', dst=t2n, src=b.const('i32', -1))
    fb.op('Null', dst=t1s)
    fb.op('Null', dst=t2s)
    ko = fb.reg(cx.t('logic.ai.AIOrder'))
    for name in names:
        u = _uid('sw')
        mp = _global_map(fb, b, cx, name)
        arr = fb.reg(arr_t)
        fb.op('Call1', dst=arr, fun=nat.findex.value, arg0=b.field(mp, 'h'))
        fb.op('JNull', reg=arr, offset=u + 'x')
        fb.op('ArraySize', dst=n, array=arr)
        fb.op('Add', dst=seen, a=seen, b=n)
        fb.op('JSLte', a=n, b=t2n, offset=u + 't')
        fb.op('JSLte', a=n, b=t1n, offset=u + 't2')
        fb.op('Mov', dst=t2n, src=t1n)
        fb.op('Mov', dst=t2s, src=t1s)
        fb.op('Mov', dst=t1n, src=n)
        fb.op('Mov', dst=t1s, src=fb.string(name))
        fb.op('JAlways', offset=u + 't')
        fb.label(u + 't2')
        fb.op('Mov', dst=t2n, src=n)
        fb.op('Mov', dst=t2s, src=fb.string(name))
        fb.label(u + 't')
        fb.op('Mov', dst=i, src=b.const('i32', 0))
        b.loop_head(u + 'l')
        fb.op('JSGte', a=i, b=n, offset=u + 'x')
        fb.op('GetArray', dst=key, array=arr, index=i)
        fb.op('Incr', dst=i)
        fb.op('JNull', reg=key, offset=u + 'l')
        # a dead / removed entity
        g1 = fb.try_()
        fb.op('SafeCast', dst=ke, src=key)
        fb.op('JNull', reg=ke, offset=u + 'e')
        fb.op('JFalse', cond=b.call('ent.Entity.isDead', ke), offset=u + 'e')
        b.call('haxe.ds.ObjectMap.remove', mp, key)
        fb.op('Incr', dst=rem)
        fb.label(u + 'e')
        fb.end_try(g1)
        # an order with no units left (stopped, or all its armies dead)
        g2 = fb.try_()
        fb.op('SafeCast', dst=ko, src=key)
        fb.op('JNull', reg=ko, offset=u + 'o')
        un = b.field(ko, 'units')
        fb.op('JNull', reg=un, offset=u + 'o')
        fb.op('JSGt', a=b.field(un, 'length'), b=b.const('i32', 0), offset=u + 'o')
        b.call('haxe.ds.ObjectMap.remove', mp, key)
        fb.op('Incr', dst=rem)
        fb.label(u + 'o')
        fb.end_try(g2)
        if wz_ok:
            # a fight that ended (no longer in State.warzones)
            g3 = fb.try_()
            kw = fb.reg(cx.t('logic.state.Warzone'))
            fb.op('SafeCast', dst=kw, src=key)
            fb.op('JNull', reg=kw, offset=u + 'w')
            fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', wz_arr, key), offset=u + 'w')
            b.call('haxe.ds.ObjectMap.remove', mp, key)
            fb.op('Incr', dst=rem)
            fb.label(u + 'w')
            fb.end_try(g3)
        fb.op('JAlways', offset=u + 'l')
        fb.label(u + 'x')
    remf, seenf, mapsf = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), b.const('f64', len(names))
    fb.op('ToSFloat', dst=remf, src=rem)
    fb.op('ToSFloat', dst=seenf, src=seen)
    t1f, t2f = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=t1f, src=t1n)
    fb.op('ToSFloat', dst=t2f, src=t2n)
    _log_ev(fb, b, cx, helpers, 'sweep', [('f', fb.get(fac, 'kind')), ('n', remf), ('keys', seenf),
                                          ('maps', mapsf), ('m1', t1s), ('k1', t1f), ('m2', t2s), ('k2', t2f)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


def install_sweep(cx, helpers, new_ids, tick, stub):
    """Build the sweeper over every added map (call last) and point the tick chain's stub call at it."""
    names = sorted(nm for nm, (c, _) in GLOBALS.items() if c is cx.code)
    w = build_sweep(cx, helpers, names)
    new_ids.add(w)
    fn = next(g for g in cx.code.functions if g.findex.value == tick)
    sites = [op for op in fn.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == stub]
    if len(sites) != 1:
        raise ValueError(f'sweep: expected 1 stub call in the tick chain, found {len(sites)}')
    sites[0].df['fun'].value = w
    return {'sweep': len(names)}
