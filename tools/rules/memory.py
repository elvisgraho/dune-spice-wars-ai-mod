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
from rules.worm import _move_to, _do_on


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


def build_memory(cx, helpers, danger, threat, own):
    """aimod_memory(mil, dt), every START s, first in the tick chain: record danger events for this faction (our
    harvesters fighting). Logs `mem` (k harvester, a unit) per recorded event.
    Harvester run: a fighting harvester with hostile power within CONTACT above our own there (the escort can't hold)
    is sent away at once, at most every HRUN_T s: doAction("MoveAndDeploy", EEntity(field)) to the nearest usable
    spice field (controller.usableSpiceFields) outside its zone with no danger memory and no hostile power within
    LOCAL, else Move to our main base. Vanilla's team re-route (harvest-flee) only moves it when another free field
    beats its own penalised one: the Fremen F_Harvester at (767,826) stayed deployed under 7 Atreides armies, hp
    100 -> 16 in 40 s, with no `hflee`. Logs `hrun` (a, s field or null, H, M, ok). In a trap: nothing on error."""
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
    # outgunned under fire: run to a safe field now
    ae = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ae, src=a)
    h, m, dd, bd, dg = (fb.reg(cx.t('f64')) for _ in range(5))
    fb.op('Call3', dst=h, fun=threat, arg0=fac, arg1=ae, arg2=b.const('f64', CONTACT))
    fb.op('JSLte', a=h, b=b.const('f64', 0), offset='army')
    fb.op('Call4', dst=m, fun=own, arg0=fac, arg1=ae, arg2=b.const('f64', CONTACT), arg3=a)
    fb.op('JSGte', a=m, b=h, offset='army')
    _throttle(fb, b, cx, 'hrun', a, HRUN_T, 'army')
    best = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=best)
    fb.op('Mov', dst=bd, src=b.const('f64', 1 << 30))
    fields = b.field(b.field(0, 'controller'), 'usableSpiceFields')
    fb.op('JNull', reg=fields, offset='fdone')
    k = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    fe = fb.reg(cx.t('ent.Entity'))
    b.loop_head('fl')
    fb.op('JSGte', a=k, b=b.field(fields, 'length'), offset='fdone')
    fb.op('Mov', dst=fe, src=b.cast(b.call('hl.types.ArrayObj.getDyn', fields, k), 'ent.Structure'))
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=fe, offset='fl')
    fz = b.call('ent.Entity.get_zone', fe)
    fb.op('JNull', reg=fz, offset='fl')
    fb.op('JEq', a=fz, b=z, offset='fl')
    fb.op('Call2', dst=dg, fun=danger, arg0=fac, arg1=fz)
    fb.op('JSGt', a=dg, b=b.const('f64', 0), offset='fl')
    fb.op('Mov', dst=dd, src=b.call('ent.Entity.getDistTo', ae, fe))
    fb.op('JSGte', a=dd, b=bd, offset='fl')
    # not a field another harvester's team entry holds
    teams = b.field(b.field(0, 'controller'), 'harvestingTeams')
    fb.op('JNull', reg=teams, offset='tfree')
    k2 = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k2, src=b.const('i32', 0))
    b.loop_head('tm')
    fb.op('JSGte', a=k2, b=b.field(teams, 'length'), offset='tfree')
    te = b.call('hl.types.ArrayObj.getDyn', teams, k2)
    fb.op('Incr', dst=k2)
    fb.op('JNull', reg=te, offset='tm')
    fb.op('JNotEq', a=fb.get(te, 'spice'), b=fb.dyn(fe), offset='tm')
    fb.op('JEq', a=fb.get(te, 'unit'), b=fb.dyn(a), offset='tm')
    fb.op('JAlways', offset='fl')  # taken
    fb.label('tfree')
    fb.op('Call3', dst=dg, fun=threat, arg0=fac, arg1=fe, arg2=b.const('f64', LOCAL))
    fb.op('JSGt', a=dg, b=b.const('f64', 0), offset='fl')
    fb.op('Mov', dst=bd, src=dd)
    fb.op('Mov', dst=best, src=fe)
    fb.op('JAlways', offset='fl')
    fb.label('fdone')
    okr = fb.reg(cx.t('bool'))
    fb.op('JNull', reg=best, offset='home')
    fb.op('Mov', dst=okr, src=_do_on(fb, b, cx, a, 'MoveAndDeploy', best, fac))
    fb.op('JAlways', offset='rlog')
    fb.label('home')
    mb = b.call('ent.Faction.get_mainBase', fac)
    fb.op('JNull', reg=mb, offset='army')
    fb.op('Mov', dst=okr, src=_move_to(fb, b, cx, a, b.field(mb, 'posx'), b.field(mb, 'posy'), fac))
    fb.label('rlog')
    _log_ev(fb, b, cx, helpers, 'hrun', [('f', fb.get(fac, 'kind')), ('a', a), ('s', best), ('H', h), ('M', m),
                                         ('ok', okr)])
    fb.op('JAlways', offset='army')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


def harvest_flee(cx, danger, threat, helpers, new_ids):
    """Attacked team harvesters move on. checkHarvestingTeams gives every harvester (deployed ones too) its nearest
    free field by the danger-weighted key (harvest_fields), but issues breakFightWith + doAction("MoveAndDeploy")
    only when unit.getActionDesc() is null, and a deployed harvester carries its harvesting action: a Fremen
    F_Harvester shot by 2 S_Troopers at Haththah stayed deployed, hp 100 -> 75 in 30 s, while its team entry
    already pointed at another field. The single getActionDesc call there is wrapped: null (= free to re-route)
    for a harvester that is fighting, stands in a zone our memory marks as dangerous (aimod_danger > 0: so its own
    field is penalised and the re-route goes elsewhere) and has hostile armies within CONTACT (aimod_threat), at
    most once per HFLEE_T s per harvester (the pack-up takes time). Logs `hflee` (a, H, dg%). Original otherwise."""
    fn = cx.fn('logic.ai.AIController.checkHarvestingTeams')
    gad = cx.fn('ent.Entity.getActionDesc')
    sites = [op for op in fn.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == gad.findex.value]
    if len(sites) != 1:
        raise ValueError(f'harvest-flee: expected 1 getActionDesc call in checkHarvestingTeams, found {len(sites)}')
    ft = cx.code.types[gad.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=gad.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('Call1', dst=res, fun=gad.findex.value, arg0=0)  # original, outside any trap
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=fb.get(0, 'harvestComponent'), offset='end')
    fb.op('JFalse', cond=b.call('ent.Entity.isFighting', 0), offset='end')
    owner = b.call('ent.Entity.get_owner', 0)
    fb.op('JNull', reg=owner, offset='end')
    z = b.call('ent.Entity.get_zone', 0)
    fb.op('JNull', reg=z, offset='end')
    w, h = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Call2', dst=w, fun=danger, arg0=owner, arg1=z)
    fb.op('JSLte', a=w, b=b.const('f64', 0), offset='end')
    # a harvester our run just sent away keeps its course (the re-route could pick its own field again)
    rv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'hrun'), fb.dyn(0))
    fb.op('JNull', reg=rv, offset='norun')
    fb.op('SafeCast', dst=h, src=rv)
    fb.op('Sub', dst=h, a=b.field(_state(fb, b, cx), 'time'), b=h)
    fb.op('JSLt', a=h, b=b.const('f64', HRUN_T), offset='end')
    fb.label('norun')
    fb.op('Call3', dst=h, fun=threat, arg0=owner, arg1=0, arg2=b.const('f64', CONTACT))
    fb.op('JSLte', a=h, b=b.const('f64', 0), offset='end')
    _throttle(fb, b, cx, 'hflee', 0, HFLEE_T, 'end')
    fb.op('Null', dst=res)
    _log_ev(fb, b, cx, helpers, 'hflee', [('f', fb.get(owner, 'kind')), ('a', 0), ('H', h), ('dg%', w)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    wr = fb.build()
    sites[0].df['fun'].value = wr
    new_ids.add(wr)
    return {'memory:harvest-flee': 1}


def harvest_fields(cx, danger, helpers, new_ids):
    """Harvesting-team field choice: AIController.checkHarvestingTeams binds findClosestFreeSpice(unit) (a closure),
    which sorts usableSpiceFields by a (unit, field) -> squared-distance closure. That key closure is redirected to a
    wrapper: key + aimod_danger(unit owner, field zone) x DANGER_KEY. Logs `hfield` (a unit, s field, dg%) when a
    penalty applies, once per field per 10 s, and `hpick` (a, s, dg%, d) when the field finally chosen is still
    dangerous. Original key / pick on any error."""
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
    # the pick itself (hfield rows are per evaluated field): `hpick` (a, s chosen field, dg% its danger, d) when the
    # chosen field is still dangerous, once per unit per 10 s: did the team re-route avoid the danger zone?
    fop, ftgt = finder[0]
    fft = cx.code.types[ftgt.type.value].definition
    fargs = [a.value for a in fft.args]
    fb = FB(cx, fargs, struct_t, fun_type=ftgt.type.value)
    b = B(fb)
    r = fb.reg(struct_t)
    fb.op('Call2', dst=r, fun=ftgt.findex.value, arg0=0, arg1=1)  # vanilla pick, outside any trap
    guard = fb.try_()
    fb.op('JNull', reg=r, offset='ok')
    w = fb.reg(f64)
    fb.op('Call2', dst=w, fun=danger, arg0=b.call('ent.Entity.get_owner', 1), arg1=b.call('ent.Entity.get_zone', r))
    fb.op('JSLte', a=w, b=b.const('f64', 0), offset='ok')
    ue = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ue, src=1)
    _throttle(fb, b, cx, 'hpick', ue, 10, 'ok')
    re_ = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=re_, src=r)
    _log_ev(fb, b, cx, helpers, 'hpick', [('f', fb.get(b.call('ent.Entity.get_owner', 1), 'kind')), ('a', ue),
                                          ('s', r), ('dg%', w), ('d', b.call('ent.Entity.getDistTo', ue, re_))])
    fb.label('ok')
    fb.end_try(guard)
    fb.op('Ret', ret=r)
    wp = fb.build()
    fop.df['fun'].value = wp
    new_ids.add(wp)
    return {'memory:harvest-fields': 1}
