"""Faction memory (AI-POLICY §3a, first step): what a faction learned about places, with a cooldown.

The failure: a Fremen harvester was sent twice to the same spice field next to Smugglers' Kulur and shot down both
times while deployed; vanilla picks the nearest free field (harvesting teams) and never recalls a team harvester.

Model: per faction, zone -> time of the last danger event there. danger(fac, zone) = 1 right after it, falling
linearly to 0 over DANGER_T. Event kinds so far: one of our harvesters fighting (attacked) in the zone, sampled every
START s. Consumers so far: harvesting-team field choice (squared-distance key + danger x DANGER_KEY), so a harvester
under attack is sent to another field at the next team check and new ones avoid the field until it cools down.
Storage: added global 'mem' ObjectMap faction -> ObjectMap(zone -> last event time); not saved with the game (after a
load the faction has forgotten, never misremembers). Extend with new event kinds (own maps or weights, own decay) and
new consumers reading aimod_danger; keep one query so every rule sees the same memory."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def _faction_mem(fb, b, cx, fac, create, miss):
    """ObjectMap zone -> time for faction `fac`. create=True: make it if missing; else jump to `miss`."""
    om_t = cx.t('haxe.ds.ObjectMap')
    outer = _global_map(fb, b, cx, 'mem')
    got = b.call('haxe.ds.ObjectMap.get', outer, fb.dyn(fac))
    inner = fb.reg(om_t)
    have = _uid('memhave')
    if create:
        done = _uid('memdone')
        fb.op('JNotNull', reg=got, offset=have)
        fb.op('New', dst=inner)
        v = fb.reg(cx.t('void'))
        fb.op('Call1', dst=v, fun=cx.fn('haxe.ds.$ObjectMap.__constructor__').findex.value, arg0=inner)
        b.call('haxe.ds.ObjectMap.set', outer, fb.dyn(fac), fb.dyn(inner))
        fb.op('JAlways', offset=done)
        fb.label(have)
        fb.op('Mov', dst=inner, src=b.cast(got, 'haxe.ds.ObjectMap'))
        fb.label(done)
    else:
        fb.op('JNull', reg=got, offset=miss)
        fb.op('Mov', dst=inner, src=b.cast(got, 'haxe.ds.ObjectMap'))
    return inner


def build_danger(cx):
    """aimod_danger(fac, zone) -> 0..1: 1 right after the last danger event fac recorded in zone, 0 after DANGER_T."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Zone')], cx.t('f64'))
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=res, src=b.const('f64', 0))
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    mem = _faction_mem(fb, b, cx, 0, False, 'end')
    last = b.call('haxe.ds.ObjectMap.get', mem, fb.dyn(1))
    fb.op('JNull', reg=last, offset='end')
    age = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=age, src=last)
    fb.op('Sub', dst=age, a=b.field(_state(fb, b, cx), 'time'), b=age)
    span = b.const('f64', DANGER_T)
    fb.op('JSGte', a=age, b=span, offset='end')
    fb.op('SDiv', dst=age, a=age, b=span)
    fb.op('Sub', dst=res, a=b.const('f64', 1), b=age)
    fb.label('end')
    fb.op('Ret', ret=res)
    return fb.build()


def build_memory(cx, helpers):
    """aimod_memory(mil, dt), every START s, first in the tick chain: record danger events for this faction (our
    harvesters fighting). Logs `mem` (k harvester, a unit) per recorded event. In a trap: nothing on error."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = b.field(_state(fb, b, cx), 'time')
    _tick(fb, b, cx, t, START, 'end')
    my_armies, mlen = _my_armies(fb, b, fac, 'end')
    mem = _faction_mem(fb, b, cx, fac, True, None)
    i = fb.reg(cx.t('i32'))
    a = _army_loop(fb, b, my_armies, mlen, i, 'army', 'end')
    fb.op('JNull', reg=b.field(a, 'harvestComponent'), offset='army')
    fb.op('JFalse', cond=b.call('ent.Entity.isFighting', a), offset='army')
    z = b.call('ent.Entity.get_zone', a)
    fb.op('JNull', reg=z, offset='army')
    b.call('haxe.ds.ObjectMap.set', mem, fb.dyn(z), fb.dyn(t))
    _log_ev(fb, b, cx, helpers, 'mem', [('f', fb.get(fac, 'kind')), ('k', 'harvester'), ('a', a)])
    fb.op('JAlways', offset='army')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


def harvest_fields(cx, danger, helpers, new_ids):
    """Harvesting-team field choice: AIController.checkHarvestingTeams binds findClosestFreeSpice(unit) (a closure),
    which sorts usableSpiceFields by a (unit, field) -> squared-distance closure. That key closure is redirected to a
    wrapper: key + aimod_danger(unit owner, field zone) x DANGER_KEY. Logs `hfield` (a unit, s field, dg%) when a
    penalty applies, once per field per 10 s. Original key on any error."""
    unit_t, struct_t, f64 = cx.t('ent.Unit'), cx.t('ent.Structure'), cx.t('f64')

    def closures(fn, want):
        out = []
        for op in fn.ops:
            if op.op != 'InstanceClosure':
                continue
            tgt = next(g for g in cx.code.functions if g.findex.value == op.df['fun'].value)
            ft = cx.code.types[tgt.type.value].definition
            if want([a.value for a in ft.args], ft.ret.value):
                out.append((op, tgt))
        return out
    finder = closures(cx.fn('logic.ai.AIController.checkHarvestingTeams'),
                      lambda args, ret: len(args) == 2 and args[1] == unit_t and ret == struct_t)
    if len(finder) != 1:
        raise ValueError(f'memory: expected 1 findClosestFreeSpice closure, found {len(finder)}')
    keys = closures(finder[0][1], lambda args, ret: args == [unit_t, struct_t] and ret == f64)
    if len(keys) != 1:
        raise ValueError(f'memory: expected 1 field key closure in findClosestFreeSpice, found {len(keys)}')
    op, tgt = keys[0]
    fb = FB(cx, [unit_t, struct_t], f64, fun_type=tgt.type.value)
    b = B(fb)
    d = fb.reg(f64)
    fb.op('Call2', dst=d, fun=tgt.findex.value, arg0=0, arg1=1)  # original key, outside any trap
    guard = fb.try_()
    w = fb.reg(f64)
    fb.op('Call2', dst=w, fun=danger, arg0=b.call('ent.Entity.get_owner', 0), arg1=b.call('ent.Entity.get_zone', 1))
    fb.op('JSLte', a=w, b=b.const('f64', 0), offset='ok')
    p = fb.reg(f64)
    fb.op('Mul', dst=p, a=w, b=b.const('f64', DANGER_KEY))
    fb.op('Add', dst=d, a=d, b=p)
    _throttle(fb, b, cx, 'hfield', 1, 10, 'ok')
    ue = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ue, src=0)
    _log_ev(fb, b, cx, helpers, 'hfield', [('f', fb.get(b.call('ent.Entity.get_owner', 0), 'kind')), ('a', ue),
                                           ('s', 1), ('dg%', w)])
    fb.label('ok')
    fb.end_try(guard)
    fb.op('Ret', ret=d)
    wr = fb.build()
    op.df['fun'].value = wr
    new_ids.add(wr)
    return {'memory:harvest-fields': 1}
