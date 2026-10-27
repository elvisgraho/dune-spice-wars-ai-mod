"""Worn-army leash (`leash`, user): a worn army that is being shot to pieces in a chase going nowhere, in at-war land or
under at-war guns, leaves the chase and walks to our nearest structure.

Why: hunts are judged per group (power, supply, cover at the group's core), never per army: a chase that still wins
on paper keeps an army at a few % life shooting under enemy turrets deep in their land (user, match 2026-10-23 18:17:
Atreides' chases of Fremen harvesters next to Al-mur; the hero too). User: only when it chases there "for no reason
and taking damage"; the AI must not throw units away, but a fight worth finishing is finished.

aimod_leash(mil, dt), tick chain after hunt, every LEASH_T s per faction, over our hunts (Military orders on an
AIEntityGroup) that are not contests (map `hcon`: an order defending our village keeps its armies; rally / Defense own
those fights). Samples since the last pass: the prey group's power (map `lshp` order -> Σ aimod_pw of its live
members), each army's life (maps `lsha` army -> life, `lsht` -> time). A chase whose prey lost >= LEASH_PREY of its
power since then is making progress (a kill is coming): nobody leaves. Otherwise an army (not in transit) leaves when
  - worn: life < LEASH_LIFE (LEASH_HERO for an army with a hero: Unit.isHero, modded heroes too), and
  - being hit: it lost life since its sample (<= 3 x LEASH_T old) and at that rate dies within LEASH_TTL s
    (LEASH_TTL_HERO for a hero), and
  - exposed: on a zone of a faction at war with us, or with at-war turret cover > 0 (aimod_cover) at it.
It is removed from the order (the last army: the order is stopped, Cancel) and Moves to our nearest structure not
marked dead (as `rsguard`; vanilla's checkUnits then gives it a Resupply: life < 0.9). One per order per pass. Logs
`leash` (f, a, hp%, ttl s, prey% progress, hero, why zone / gun, s = where it walks, ds, last). Fails safe: in a trap."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.worm import _move_to

LEASH_T = 5          # s between passes per faction (= the sampling window)
LEASH_PREY = 0.1     # prey power lost since the last pass at least this share: the chase is getting somewhere
LEASH_LIFE = 0.2     # worn: below this life ...
LEASH_HERO = 0.35    # ... a hero below this (user: better retreat than spend that asset; 0.3 / 0.5 was too eager)
LEASH_TTL = 20       # s: at the life it lost since the last pass it would be dead within this
LEASH_TTL_HERO = 30  # ... a hero within this


def build_leash(cx, helpers, cover, pw):
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    state = _state(fb, b, cx)
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(state, 'time'))
    _tick(fb, b, cx, t, LEASH_T, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    conmap = _global_map(fb, b, cx, 'hcon')  # contest order -> the village it defends (rules/hunt.py)
    mpp = _global_map(fb, b, cx, 'lshp')  # order -> prey power at the last pass
    mpa = _global_map(fb, b, cx, 'lsha')  # army -> life at the last pass
    mpt = _global_map(fb, b, cx, 'lsht')  # army -> when
    reason = cx.code.types[cx.fn('logic.ai.AIOrder.stop').type.value].definition.args[1].value
    cancel = fb.reg(reason)
    fb.op('MakeEnum', dst=cancel, construct=CANCEL, args=[])
    no_ent = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=no_ent)
    no_arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=no_arr)
    t_false = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_false, value=False)
    zero = b.const('f64', 0)
    k, ix, j, si = (fb.reg(cx.t('i32')) for _ in range(4))
    lr, l0, t0, q, ttl, tc, nd, sd, pp, p0, prog = (fb.reg(cx.t('f64')) for _ in range(11))
    hero, moving = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    why = fb.reg(cx.t('String'))
    o = fb.reg(cx.t('logic.ai.AIOrder'))
    ae, near = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=k, src=b.field(orders, 'length'))
    b.loop_head('o')  # backwards: a stop removes the order from the list
    fb.op('JSLte', a=k, b=b.const('i32', 0), offset='end')
    fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
    fb.op('Mov', dst=o, src=b.cast(b.call('hl.types.ArrayObj.getDyn', orders, k), 'logic.ai.AIOrder'))
    fb.op('JNull', reg=o, offset='o')
    fb.op('EnumIndex', dst=ix, value=b.field(o, 'type'))
    fb.op('JNotEq', a=ix, b=b.const('i32', MILITARY), offset='o')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='o')
    fb.op('EnumIndex', dst=ix, value=tt)
    fb.op('JNotEq', a=ix, b=b.const('i32', T_GROUP), offset='o')
    fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', conmap, fb.dyn(o)), offset='o')  # a contest
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='o')
    # prey progress since the last pass (none known yet: 0, i.e. no progress)
    g = b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'logic.ai.AIEntityGroup')
    fb.op('JNull', reg=g, offset='o')
    mem = b.field(g, 'entities')
    fb.op('JNull', reg=mem, offset='o')
    fb.op('Mov', dst=pp, src=zero)
    pm = _army_loop(fb, b, mem, b.field(mem, 'length'), j, 'pm', 'pmd', transported=True)
    fb.op('Call1', dst=q, fun=pw, arg0=pm)
    fb.op('Add', dst=pp, a=pp, b=q)
    fb.op('JAlways', offset='pm')
    fb.label('pmd')
    fb.op('Mov', dst=prog, src=zero)
    pv = b.call('haxe.ds.ObjectMap.get', mpp, fb.dyn(o))
    b.call('haxe.ds.ObjectMap.set', mpp, fb.dyn(o), fb.dyn(pp))
    fb.op('JNull', reg=pv, offset='pgd')
    fb.op('SafeCast', dst=p0, src=pv)
    fb.op('JSLte', a=p0, b=zero, offset='pgd')
    fb.op('Sub', dst=prog, a=p0, b=pp)
    fb.op('SDiv', dst=prog, a=prog, b=p0)
    fb.label('pgd')
    fb.op('Bool', dst=moving, value=False)  # the chase is getting somewhere: samples only, nobody leaves
    fb.op('JSLt', a=prog, b=_ratio(fb, b, LEASH_PREY), offset='arm')
    fb.op('Bool', dst=moving, value=True)
    fb.label('arm')
    a = _army_loop(fb, b, units, b.field(units, 'length'), j, 'u', 'o')
    fb.op('Mov', dst=ae, src=a)
    fb.op('Mov', dst=lr, src=b.call('ent.Entity.get_lifeRatio', a))
    av = b.call('haxe.ds.ObjectMap.get', mpa, fb.dyn(a))
    tv = b.call('haxe.ds.ObjectMap.get', mpt, fb.dyn(a))
    b.call('haxe.ds.ObjectMap.set', mpa, fb.dyn(a), fb.dyn(lr))
    b.call('haxe.ds.ObjectMap.set', mpt, fb.dyn(a), fb.dyn(t))
    fb.op('JTrue', cond=moving, offset='u')
    fb.op('JNull', reg=av, offset='u')
    fb.op('JNull', reg=tv, offset='u')
    fb.op('SafeCast', dst=l0, src=av)
    fb.op('SafeCast', dst=t0, src=tv)
    # worn
    fb.op('Mov', dst=hero, src=b.call('ent.Unit.isHero', a))
    fb.op('JTrue', cond=hero, offset='hf')
    fb.op('JSGte', a=lr, b=_ratio(fb, b, LEASH_LIFE), offset='u')
    fb.op('JAlways', offset='hit')
    fb.label('hf')
    fb.op('JSGte', a=lr, b=_ratio(fb, b, LEASH_HERO), offset='u')
    # being hit: life lost since a fresh sample, dead within the TTL at that rate (ttl = life x dt / loss)
    fb.label('hit')
    fb.op('Sub', dst=q, a=t, b=t0)
    fb.op('JSLte', a=q, b=zero, offset='u')
    fb.op('JSGt', a=q, b=b.const('f64', 3 * LEASH_T), offset='u')
    fb.op('Sub', dst=sd, a=l0, b=lr)
    fb.op('JSLte', a=sd, b=zero, offset='u')
    fb.op('Mul', dst=ttl, a=lr, b=q)
    fb.op('SDiv', dst=ttl, a=ttl, b=sd)
    fb.op('JTrue', cond=hero, offset='th')
    fb.op('JSGte', a=ttl, b=b.const('f64', LEASH_TTL), offset='u')
    fb.op('JAlways', offset='exp')
    fb.label('th')
    fb.op('JSGte', a=ttl, b=b.const('f64', LEASH_TTL_HERO), offset='u')
    # exposed: in at-war land, or under at-war guns
    fb.label('exp')
    fb.op('Mov', dst=why, src=fb.string('zone'))
    z = b.call('ent.Entity.get_zone', a)
    fb.op('JNull', reg=z, offset='gun')
    zo = b.field(z, 'owner')
    fb.op('JNull', reg=zo, offset='gun')
    fb.op('JEq', a=zo, b=fac, offset='gun')
    fb.op('JTrue', cond=b.call('logic.state.State.areAtWar', state, fac, zo), offset='go')
    fb.label('gun')
    fb.op('Mov', dst=why, src=fb.string('gun'))
    fb.op('CallN', dst=tc, fun=cover, args=[fac, ae, no_ent, t_false, no_arr])
    fb.op('JSLte', a=tc, b=zero, offset='u')
    fb.label('go')
    # our nearest structure (rsguard's walk target)
    ss = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=ss, offset='u')
    fb.op('Null', dst=near)
    fb.op('Mov', dst=nd, src=b.const('f64', 1 << 30))
    fb.op('Mov', dst=si, src=b.const('i32', 0))
    b.loop_head('s')
    fb.op('JSGte', a=si, b=b.field(ss, 'length'), offset='sd')
    se = b.cast(b.call('hl.types.ArrayObj.getDyn', ss, si), 'ent.Entity')
    fb.op('Incr', dst=si)
    fb.op('JNull', reg=se, offset='s')
    _heal_dead(fb, b, cx, se, 's')
    fb.op('Mov', dst=sd, src=b.call('ent.Entity.getDistTo', ae, se))
    fb.op('JSGte', a=sd, b=nd, offset='s')
    fb.op('Mov', dst=nd, src=sd)
    fb.op('Mov', dst=near, src=se)
    fb.op('JAlways', offset='s')
    fb.label('sd')
    fb.op('JNull', reg=near, offset='u')
    last = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=last, src=zero)
    fb.op('JSGt', a=b.field(units, 'length'), b=b.const('i32', 1), offset='rm')
    fb.op('Mov', dst=last, src=b.const('f64', 1))
    b.call('logic.ai.AIOrder.stop', o, cancel)  # its last army: the chase ends
    fb.op('JAlways', offset='mv')
    fb.label('rm')
    b.call('logic.ai.AIOrder.removeUnit', o, a)
    fb.label('mv')
    _move_to(fb, b, cx, ae, b.field(near, 'posx'), b.field(near, 'posy'), fac)
    hf = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=hf, src=zero)
    fb.op('JFalse', cond=hero, offset='lg')
    fb.op('Mov', dst=hf, src=b.const('f64', 1))
    fb.label('lg')
    _log_ev(fb, b, cx, helpers, 'leash', [('f', fb.get(fac, 'kind')), ('a', ae), ('hp%', lr), ('ttl', ttl),
                                          ('prey%', prog), ('hero', hf), ('why', why), ('s', near), ('ds', nd),
                                          ('last', last)])
    fb.op('JAlways', offset='o')  # one per order per pass: its unit list changed
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
