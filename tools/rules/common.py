"""Bytecode-building helpers and shared build state for the AI rules.
Tuning values live in thresholds.py; CastleDB reads and their cache live in game_data.py.
Rules import this shared interface; `__all__` exports the underscore helpers too."""
import json
from pathlib import Path

from inject import FB  # noqa: F401
from aware import B  # noqa: F401

from rules.game_data import _WORK, _DB, game_rows, const_index, no_building_factions
from rules.thresholds import *  # noqa: F401,F403


def _fcache_int(fb, b, cx, idx, fac):
    """i32 = Const.fValuesCache[const_index(idx)][fac.aiDifficulty] (idx: constant id; per-difficulty, read as tryAction does)."""
    c = fb.reg(cx.t('$Const'))
    fb.op('GetGlobal', dst=c, **{'global': cx.global_of('$Const')})
    out = b.const('i32', 0)
    done = _uid('fc')
    cache = b.field(c, 'fValuesCache')
    fb.op('JNull', reg=cache, offset=done)
    row = b.cast(b.call('hl.types.ArrayObj.getDyn', cache, b.const('i32', const_index(idx))), 'hl.types.ArrayBytes_Float')
    fb.op('JNull', reg=row, offset=done)
    v = b.call('hl.types.ArrayBytes_Float.getDyn', row, b.call('ent.Faction.get_aiDifficulty', fac))
    fb.op('JNull', reg=v, offset=done)
    f = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=f, src=v)
    fb.op('ToInt', dst=out, src=f)
    fb.label(done)
    return out


def _alloc_fn(cx):
    """Static ArrayObj.alloc (unnamed): the Call1 after `Type; Call2 alloc_array; UnsafeCast` in tryArmyAction.
    Returns (alloc_array, alloc, [type reg type, native array type, cast type]) copied from that site."""
    f = cx.fn('logic.ai.AIMilitary.tryArmyAction')
    ops = f.ops
    nat = {n.findex.value for n in cx.code.natives if n.name.resolve(cx.code) == 'alloc_array'}
    for i in range(len(ops) - 2):
        if ops[i].op == 'Call2' and ops[i].df['fun'].value in nat and ops[i + 1].op == 'UnsafeCast' \
                and ops[i + 2].op == 'Call1':
            c = ops[i].df
            regs = [f.regs[c['arg0'].value].value, f.regs[c['dst'].value].value, f.regs[ops[i + 1].df['dst'].value].value]
            return c['fun'].value, ops[i + 2].df['fun'].value, regs
    raise ValueError('behave: ArrayObj.alloc pattern not found')


def _ratio(fb, b, v):
    """f64 register = v (float constant via int/100; crashlink has no float constants)."""
    r = fb.reg(fb.cx.t('f64'))
    fb.op('SDiv', dst=r, a=b.const('f64', int(round(v * 100))), b=b.const('f64', 100))
    return r


def _state(fb, b, cx):
    gs = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gs, **{'global': cx.global_of('$Game')})
    return b.field(b.field(gs, 'inst'), 'state')


def _army_loop(fb, b, arr, alen, i, name, done, transported=False):
    """Loop head: next live ent.Army from arr (skips null, militia, transported, dead). Returns the army register.
    transported=True keeps armies in transit (worm ride, shuttle): the hostile-army queries judge them by the fog
    memory only (rules/intel._ghost), where they were last seen boarding."""
    fb.op('Int', dst=i, ptr=b.code.add_i32(0).value)
    b.loop_head(name)
    fb.op('JSGte', a=i, b=alen, offset=done)
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', arr, i), 'ent.Army')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=a, offset=name)
    fb.op('JTrue', cond=b.field(a, 'isMilitia'), offset=name)
    if not transported:
        fb.op('JTrue', cond=b.call('ent.Entity.isTransported', a), offset=name)
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', a), offset=name)
    return a


def _defends(fb, b, cx, fac, a, ds, none):
    """ds = the entity fac's Defense order defends (AIOrderType 2 Defense(ent.Entity): a structure of ours) for
    the order army a is in; jump to `none` when a is in no Defense order."""
    ords = b.field(b.field(b.field(fac, 'aiController'), 'aiOrders'), 'orders')
    fb.op('JNull', reg=ords, offset=none)
    k, ix = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    lo = _uid('dfo')
    fb.op('Mov', dst=k, src=b.field(ords, 'length'))
    b.loop_head(lo)
    fb.op('JSLte', a=k, b=b.const('i32', 0), offset=none)
    fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', ords, k), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset=lo)
    ou = b.field(o, 'units')
    fb.op('JNull', reg=ou, offset=lo)
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', ou, fb.dyn(a)), offset=lo)
    ot = b.field(o, 'type')
    fb.op('EnumIndex', dst=ix, value=ot)
    fb.op('JNotEq', a=ix, b=b.const('i32', DEFENSE), offset=none)
    st = fb.reg(cx.t('ent.Entity'))
    fb.op('EnumField', dst=st, value=ot, construct=DEFENSE, field=0)
    fb.op('JNull', reg=st, offset=none)
    fb.op('Mov', dst=ds, src=st)


def _order_of(fb, b, cx, fac, a, dst, none):
    """dst = the live order of fac holding army a (highest priority, the newest on a tie: vanilla's hasOrder scan);
    jump to `none` when it is in none. Never read `Unit.aiOrder`: only AIOrders.init (controller start / save load)
    writes it, so it is null all match long and stale after a load."""
    fb.op('Null', dst=dst)
    fb.op('JNull', reg=fac, offset=none)
    ctl = b.field(fac, 'aiController')  # null for a human player
    fb.op('JNull', reg=ctl, offset=none)
    aio = b.field(ctl, 'aiOrders')
    fb.op('JNull', reg=aio, offset=none)
    ords = b.field(aio, 'orders')
    fb.op('JNull', reg=ords, offset=none)
    k, bp = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=bp, src=b.const('i32', -1))
    lo, dn = _uid('oof'), _uid('oofd')
    fb.op('Mov', dst=k, src=b.field(ords, 'length'))
    b.loop_head(lo)
    fb.op('JSLte', a=k, b=b.const('i32', 0), offset=dn)
    fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', ords, k), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset=lo)
    ou = b.field(o, 'units')
    fb.op('JNull', reg=ou, offset=lo)
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', ou, fb.dyn(a)), offset=lo)
    pr = b.field(o, 'priority')
    fb.op('JSLte', a=pr, b=bp, offset=lo)  # newest first (backwards): a tie keeps the newer one
    fb.op('Mov', dst=bp, src=pr)
    fb.op('Mov', dst=dst, src=o)
    fb.op('JAlways', offset=lo)
    fb.label(dn)
    fb.op('JNull', reg=dst, offset=none)


def _unreach(fb, b, cx, s_e, t, yes, fac=None):
    """Jump to `yes` when siege target s_e is out of supply reach: our last order on it (map `aord`, set by the
    launch gate; fac given: only an order of fac's, the maps are keyed by target and another faction's launch must not
    block us) died in Waiting (phase < REGROUP, units emptied by stop: vanilla's path supply check or a refused
    Shuttle step), launched (map `alaunch`) less than UNREACH_T before t, and its faction holds no free Supply Drop
    (map `sdfree` within SD_FRESH: sdrop-trip lifts the check) or that launch already ran with one (map `asd`)."""
    no = _uid('unr')
    ov = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'aord'), fb.dyn(s_e))
    fb.op('JNull', reg=ov, offset=no)
    po = b.cast(ov, 'logic.ai.AIOrder')
    fb.op('JNull', reg=po, offset=no)
    pos = b.field(po, 'orders')
    fb.op('JNull', reg=pos, offset=no)
    pct = b.field(pos, 'controller')
    fb.op('JNull', reg=pct, offset=no)
    pfac = b.field(pct, 'owner')
    fb.op('JNull', reg=pfac, offset=no)
    if fac is not None:
        fb.op('JNotEq', a=pfac, b=fac, offset=no)
    fb.op('JSGte', a=b.field(po, 'phase'), b=b.const('i32', REGROUP), offset=no)
    pu = b.field(po, 'units')
    fb.op('JNull', reg=pu, offset=no + 'd')
    fb.op('JSGt', a=b.field(pu, 'length'), b=b.const('i32', 0), offset=no)  # still waiting, alive
    fb.label(no + 'd')
    lv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'alaunch'), fb.dyn(s_e))
    fb.op('JNull', reg=lv, offset=no)
    lq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=lq, src=lv)
    fb.op('Sub', dst=lq, a=t, b=lq)
    fb.op('JSGte', a=lq, b=b.const('f64', UNREACH_T), offset=no)
    # that launch already had a free drop's lift (map `asd`, siege.py launch record) and still died: the drop can't
    # make this trip, no waiver
    fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'asd'), fb.dyn(s_e)), offset=yes)
    sv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'sdfree'), fb.dyn(pfac))
    fb.op('JNull', reg=sv, offset=no + 'w')
    sq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=sq, src=sv)
    fb.op('Sub', dst=sq, a=t, b=sq)
    fb.op('JSLte', a=sq, b=b.const('f64', SD_FRESH), offset=no)
    # a worm ride available (rules/ride.py map `wfree`): the worm plan has no supply check and rides most of the way;
    # not for a target whose ride plan failed lately (map `wbad`, within UNREACH_T: no thumper slots from there)
    fb.label(no + 'w')
    wbv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'wbad'), fb.dyn(s_e))
    fb.op('JNull', reg=wbv, offset=no + 'wr')
    wbq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=wbq, src=wbv)
    fb.op('Sub', dst=wbq, a=t, b=wbq)
    fb.op('JSLt', a=wbq, b=b.const('f64', UNREACH_T), offset=yes)
    fb.label(no + 'wr')
    _ride_free(fb, b, cx, pfac, t, yes)
    fb.label(no)


def _heal_dead(fb, b, cx, s, skip):
    """Jump to `skip` when structure s (entity reg) is a dead heal / home target (map `hbad` s -> until, set by
    rules/orders.build_heal_dead: Move orders to it keep being cancelled in Waiting)."""
    hv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'hbad'), fb.dyn(s))
    no = _uid('hdn')
    fb.op('JNull', reg=hv, offset=no)
    hq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=hq, src=hv)
    fb.op('JSGt', a=hq, b=b.field(_state(fb, b, cx), 'time'), offset=skip)
    fb.label(no)


def _box_true(fb, cx, dst):
    """dst (a Null<Bool> register, e.g. Zone.getDistanceToPlayerTerritory's considerAirfields) = boxed true. A raw
    Bool op into a Null<Bool> register leaves a non-pointer the callee dereferences: it threw inside our traps, and
    the rules calling it (Annex scores, the Supply Drop / worm reach in isInSupplyRange, raid expansion room, the
    sdrop trip lock) silently fell back to vanilla (bcheck `Bool ptr`)."""
    tb = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=tb, value=True)
    fb.op('ToDyn', dst=dst, src=tb)


def _ride_free(fb, b, cx, fac, t, no):
    """Jump to `no` unless fac can ride a worm now (rules/ride.py map `wfree`: a thumper not claimed by another
    order, refreshed every RIDE_CHECK s, fresh within RIDE_FRESH)."""
    rv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'wfree'), fb.dyn(fac))
    fb.op('JNull', reg=rv, offset=no)
    rq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=rq, src=rv)
    fb.op('Sub', dst=rq, a=t, b=rq)
    fb.op('JSGt', a=rq, b=b.const('f64', RIDE_FRESH), offset=no)


def _ride_leg(fb, b, cx, fac, t, d, critical=False):
    """d (f64 reg) -> the walking part of a trip d long when fac's plan gate (rules/ride.py) would ride it, in place:
    a thumper free (_ride_free), d >= RIDE_MIN, and d >= RIDE_FAR or RIDE_SPARE free (map `wfreen`; critical=True: a
    contest, the last free one is enough). The ride covers RIDE_LEG of it at no supply. Unchanged otherwise."""
    u = _uid('rleg')
    fb.op('JSLt', a=d, b=b.const('f64', RIDE_MIN), offset=u)
    _ride_free(fb, b, cx, fac, t, u)
    if not critical:
        fb.op('JSGte', a=d, b=b.const('f64', RIDE_FAR), offset=u + 'f')
        fv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'wfreen'), fb.dyn(fac))
        fb.op('JNull', reg=fv, offset=u)
        fq = fb.reg(cx.t('f64'))
        fb.op('SafeCast', dst=fq, src=fv)
        fb.op('JSLt', a=fq, b=b.const('f64', RIDE_SPARE), offset=u)
        fb.label(u + 'f')
    fb.op('Sub', dst=d, a=d, b=b.const('f64', RIDE_LEG))
    fb.op('JSGte', a=d, b=b.const('f64', 0), offset=u)
    fb.op('Mov', dst=d, src=b.const('f64', 0))
    fb.label(u)


def _my_armies(fb, b, fac, fail):
    arr = b.cast(fb.get(fac, 'armies', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=arr, offset=fail)
    return arr, b.field(arr, 'length')


def _riding(fb, b, cx, helpers, fac, order, units, event, skip):
    """Jump to `skip` when an army of `units` is transported (worm ride, shuttle: _army_loop skips it, so an order's
    power reads 0 in transit); logs `event` (f, a) once per order per 10 s."""
    k = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    head, done, clr = _uid('rd'), _uid('rdd'), _uid('rdc')
    rm = _global_map(fb, b, cx, 'ride')
    b.loop_head(head)
    fb.op('JSGte', a=k, b=b.field(units, 'length'), offset=clr)
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', units, k), 'ent.Army')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=a, offset=head)
    fb.op('JFalse', cond=b.call('ent.Entity.isTransported', a), offset=head)
    # held at most RIDE_MAX s per order (map `ride` order -> first seen): a hidden army must not freeze it
    q = fb.reg(cx.t('f64'))
    rv = b.call('haxe.ds.ObjectMap.get', rm, fb.dyn(order))
    tnow = b.field(_state(fb, b, cx), 'time')
    first = _uid('rdf')
    fb.op('JNull', reg=rv, offset=first)
    fb.op('SafeCast', dst=q, src=rv)
    fb.op('Sub', dst=q, a=tnow, b=q)
    fb.op('JSGt', a=q, b=b.const('f64', RIDE_MAX), offset=done)
    fb.op('JAlways', offset=first + 'l')
    fb.label(first)
    b.call('haxe.ds.ObjectMap.set', rm, fb.dyn(order), fb.dyn(tnow))
    fb.label(first + 'l')
    _throttle(fb, b, cx, event, order, 10, skip)
    _log_ev(fb, b, cx, helpers, event, [('f', fb.get(fac, 'kind')), ('a', a)])
    fb.op('JAlways', offset=skip)
    fb.label(clr)  # nobody in transit: the next ride gets a fresh RIDE_MAX
    b.call('haxe.ds.ObjectMap.remove', rm, fb.dyn(order))
    fb.label(done)


def _redirect(cx, target, callers, wrapper):
    tid = cx.fn(target).findex.value
    n = 0
    for caller in callers:
        sites = [op for op in cx.fn(caller).ops if op.op.startswith('Call') and op.df.get('fun') is not None
                 and op.df['fun'].value == tid]
        if len(sites) != 1:
            raise ValueError(f'turret cover: expected 1 {target} call in {caller}, found {len(sites)}')
        sites[0].df['fun'].value = wrapper
        n += 1
    return n


def _new_array(fb, b, cx):
    """Empty hl.types.ArrayObj, built the way the compiler does it."""
    nat, alloc, (t_ty, t_raw, t_cast) = _alloc_fn(cx)
    ty = fb.reg(t_ty)
    fb.op('Type', dst=ty, ty=cx.t('ent.Unit'))
    raw, raw2 = fb.reg(t_raw), fb.reg(t_cast)
    fb.op('Call2', dst=raw, fun=nat, arg0=ty, arg1=b.const('i32', 0))
    fb.op('UnsafeCast', dst=raw2, src=raw)
    arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Call1', dst=arr, fun=alloc, arg0=raw2)
    return arr


def _tick(fb, b, cx, t, period, skip):
    """Jump to `skip` unless floor(t/period) != floor((t-dt)/period) (dt = reg 1)."""
    p = b.const('f64', period)
    q1, t2, q2 = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('SDiv', dst=q1, a=t, b=p)
    fb.op('Sub', dst=t2, a=t, b=1)
    fb.op('SDiv', dst=q2, a=t2, b=p)
    fb.op('JEq', a=b.to_int(q1), b=b.to_int(q2), offset=skip)


GLOBALS = {}       # name -> (code, global index): added globals, one set per boot file build


_UID = [0]


def _strong_site(fb, b, st, yes):
    """Jump to `yes` if structure st (ent.Structure reg, may be null) is a sietch or a renegade base."""
    no = _uid('_ss')
    fb.op('JNull', reg=st, offset=no)
    fb.op('JTrue', cond=b.call('ent.Structure.isSietch', st), offset=yes)
    fb.op('JTrue', cond=b.call('ent.Structure.isRenegadeBase', st), offset=yes)
    fb.label(no)


def _atk_cover(fb, b, m, st=None):
    """m = our turret cover at an attack target -> x OWN_COVER_ATK; 0 when st (the target structure, ent.Structure
    reg) is a sietch / renegade base: its garrison is fought at the target, not under our guns."""
    z, d = _uid('_acz'), _uid('_acd')
    if st is not None:
        _strong_site(fb, b, st, z)
    fb.op('Mul', dst=m, a=m, b=_ratio(fb, b, OWN_COVER_ATK))
    fb.op('JAlways', offset=d)
    fb.label(z)
    fb.op('Mov', dst=m, src=b.const('f64', 0))
    fb.label(d)


def _strong_tf(fb, b, tf, st):
    """tf = 1 when st is a sietch / renegade base: the terrain factor's reasons (we heal and resupply on our zone,
    they drain) don't hold for a garrison that needs neither (Tabmah lay in Harkonnen's zone: bar / 1.3)."""
    d = _uid('_stf')
    one = _uid('_st1')
    _strong_site(fb, b, st, one)
    fb.op('JAlways', offset=d)
    fb.label(one)
    fb.op('Mov', dst=tf, src=b.const('f64', 1))
    fb.label(d)


def _uid(prefix):
    _UID[0] += 1
    return f'{prefix}{_UID[0]}'


def _global_map(fb, b, cx, name):
    """Added global haxe.ds.ObjectMap `name` (state kept between calls; not saved with the game), created on
    first use. Maps: 'hunt' faction -> last hunt start time; 'heal'/'retreat' key -> last log time (throttle)."""
    om_t = cx.t('haxe.ds.ObjectMap')
    if name not in GLOBALS or GLOBALS[name][0] is not cx.code:
        from crashlink.core import tIndex
        ti = tIndex()
        ti.value = om_t
        cx.code.global_types.append(ti)
        GLOBALS[name] = (cx.code, len(cx.code.global_types) - 1)
    g = GLOBALS[name][1]
    r = fb.reg(om_t)
    have = _uid('havemap')
    fb.op('GetGlobal', dst=r, **{'global': g})
    fb.op('JNotNull', reg=r, offset=have)
    fb.op('New', dst=r)
    v = fb.reg(cx.t('void'))
    ctor = cx.fn('haxe.ds.$ObjectMap.__constructor__')
    fb.op('Call1', dst=v, fun=ctor.findex.value, arg0=r)
    fb.op('SetGlobal', src=r, **{'global': g})
    fb.label(have)
    return r


def _fac_map(fb, b, cx, name, fac):
    """Per-faction ObjectMap: global map `name` faction -> its own ObjectMap (created on first use). For state two
    factions must not overwrite (one-value-per-key maps flip when both write the same key)."""
    top = _global_map(fb, b, cx, name)
    om_t = cx.t('haxe.ds.ObjectMap')
    r = fb.reg(om_t)
    have, new = _uid('fmh'), _uid('fmn')
    cur = b.call('haxe.ds.ObjectMap.get', top, fb.dyn(fac))
    fb.op('JNull', reg=cur, offset=new)
    fb.op('Mov', dst=r, src=b.cast(cur, 'haxe.ds.ObjectMap'))
    fb.op('JAlways', offset=have)
    fb.label(new)
    fb.op('New', dst=r)
    v = fb.reg(cx.t('void'))
    fb.op('Call1', dst=v, fun=cx.fn('haxe.ds.$ObjectMap.__constructor__').findex.value, arg0=r)
    b.call('haxe.ds.ObjectMap.set', top, fb.dyn(fac), fb.dyn(r))
    fb.label(have)
    return r


def _throttle(fb, b, cx, name, key, period, skip):
    """Jump to `skip` if map `name` saw `key` less than `period` game seconds ago; else record now and fall through."""
    mp = _global_map(fb, b, cx, name)
    t = b.field(_state(fb, b, cx), 'time')
    last = b.call('haxe.ds.ObjectMap.get', mp, fb.dyn(key))
    go = _uid('thr')
    fb.op('JNull', reg=last, offset=go)
    lf = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=lf, src=last)
    fb.op('Sub', dst=lf, a=t, b=lf)
    fb.op('JSLt', a=lf, b=b.const('f64', period), offset=skip)
    fb.label(go)
    b.call('haxe.ds.ObjectMap.set', mp, fb.dyn(key), fb.dyn(t))




def _annex_cost(fb, b, cx, st, fac):
    """f64 register: structure `st`'s Annex cost for faction `fac` (sum of the cost entries' qty, as rules/annex.py
    reads it; 0 when it has no siege component or no cost)."""
    oc = cx.fn('ent.comp.SiegeComponent.getOccupationActionCost')
    ft = cx.code.types[oc.type.value].definition
    onull = fb.reg(ft.args[2].value)
    fb.op('Null', dst=onull)
    dst, q = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=dst, src=b.const('f64', 0))
    done, head = _uid('acd'), _uid('acl')
    sg = b.field(st, 'siege')
    fb.op('JNull', reg=sg, offset=done)
    arr = fb.reg(ft.ret.value)
    fb.op('Call4', dst=arr, fun=oc.findex.value, arg0=sg, arg1=fb.string('Annex'), arg2=onull, arg3=fac)
    fb.op('JNull', reg=arr, offset=done)
    k = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head(head)
    fb.op('JSGte', a=k, b=b.field(arr, 'length'), offset=done)
    qd = fb.get(b.call('hl.types.ArrayObj.getDyn', arr, k), 'qty')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=qd, offset=head)
    fb.op('SafeCast', dst=q, src=qd)
    fb.op('Add', dst=dst, a=dst, b=q)
    fb.op('JAlways', offset=head)
    fb.label(done)
    return dst


def _has_trait(fb, b, cx, obj, tid, yes):
    """Jump to `yes` when game object `obj` (a zone, structure, unit) carries trait `tid` (TraitsManager.has)."""
    tm = b.call('ent.Object.get_traits', obj)
    no = _uid('htn')
    fb.op('JNull', reg=tm, offset=no)
    hf = cx.fn('logic.TraitsManager.has')
    ha = [a.value for a in cx.code.types[hf.type.value].definition.args]
    regs = [tm, fb.string(tid)]
    for k in range(2, len(ha)):
        r = fb.reg(ha[k])
        fb.op('Null', dst=r)
        regs.append(r)
    hr = fb.reg(cx.t('bool'))
    fb.op('CallN', dst=hr, fun=hf.findex.value, args=regs)
    fb.op('JTrue', cond=hr, offset=yes)
    fb.label(no)


def _map_val(fb, b, cx, m, key, missing, dst=None, typ='f64'):
    """Map `m`[key] cast to `typ` in a register (`dst`, or a new one allocated after the read, like the inline form);
    jump to `missing` when the key is absent."""
    v = b.call('haxe.ds.ObjectMap.get', m, fb.dyn(key))
    fb.op('JNull', reg=v, offset=missing)
    q = dst if dst is not None else fb.reg(cx.t(typ))
    fb.op('SafeCast', dst=q, src=v)
    return q

def _age(fb, b, cx, m, key, t, missing, dst=None):
    """Age of a time stamp: `t` - map `m`[key] (an f64 game time) in an f64 register (`dst`, or a new one allocated
    after the read, like the inline form); jump to `missing` when the key is absent. The caller compares it."""
    v = b.call('haxe.ds.ObjectMap.get', m, fb.dyn(key))
    fb.op('JNull', reg=v, offset=missing)
    q = dst if dst is not None else fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=q, src=v)
    fb.op('Sub', dst=q, a=t, b=q)
    return q


def _dist2(fb, b, e, x, y, dst, tmp):
    """`dst` = squared distance from entity `e` to point (x, y) (registers); `tmp` is scratch."""
    fb.op('Sub', dst=dst, a=b.field(e, 'posx'), b=x)
    fb.op('Mul', dst=dst, a=dst, b=dst)
    fb.op('Sub', dst=tmp, a=b.field(e, 'posy'), b=y)
    fb.op('Mul', dst=tmp, a=tmp, b=tmp)
    fb.op('Add', dst=dst, a=dst, b=tmp)


def _supply_share(fb, b, cx, a, nosup, q=None):
    """Army `a`'s supply / max supply in an f64 register (`q`, or a new one allocated after the max-supply test, like
    the inline form); jump to `nosup` for an army without supply (max <= 0)."""
    fb.op('JSLte', a=b.call('ent.Army.get_maxSupply', a), b=b.const('f64', 0), offset=nosup)
    if q is None:
        q = fb.reg(cx.t('f64'))
    fb.op('SDiv', dst=q, a=b.call('ent.Army.get_supply', a), b=b.call('ent.Army.get_maxSupply', a))
    return q

def _log_ev(fb, b, cx, helpers, event, fields):
    """Log one AIMOD event: fields = [(key, reg | str)]; f64 regs are logged x100 as ints when key ends with '%',
    entities through the entity describer, strings as given."""
    d = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=d)
    b.put(d, 'e', fb.string(event))
    for k, r in fields:
        if isinstance(r, str):
            b.put(d, k, fb.string(r))
        elif k.endswith('%'):
            x = fb.reg(cx.t('f64'))
            fb.op('Mul', dst=x, a=r, b=b.const('f64', 100))
            b.put(d, k[:-1], b.to_int(x))
        elif fb.regs[r] == cx.t('f64'):
            b.put(d, k, b.to_int(r))
        elif fb.regs[r] in (cx.t('ent.Entity'), cx.t('ent.Army'), cx.t('ent.Structure')):
            er = fb.reg(cx.t('dyn'))
            src = r
            if fb.regs[r] != cx.t('ent.Entity'):
                src = fb.reg(cx.t('ent.Entity'))
                fb.op('Mov', dst=src, src=r)
            fb.op('Call1', dst=er, fun=helpers['ent'], arg0=fb.dyn(src))
            b.put(d, k, er)
        else:
            b.put(d, k, r)
    v = fb.reg(cx.t('void'))
    fb.op('Call1', dst=v, fun=helpers['log'], arg0=fb.dyn(d))


def field_name_t(cx, obj_type, index):
    return cx.code.types[obj_type].definition.resolve_fields(cx.code)[index].name.resolve(cx.code)



def _fc_theirs(fb, b, cx, helpers, fac, place, dst, T=FC_REACT_T, contest=False, partner_credit=True):
    """dst = the battle forecast's their side at entity `place` over T (rules/forecast.py: hostile armies that can be
    there, at least the owner's armies as we know them for another faction's structure, enemy turret cover, the
    militia of a structure not ours): the one sizing measure for hunt / raid / strat (ARCHITECTURE-PLAN step 1; was
    aimod_react within LOCAL + each rule's cover / militia sum). Our side isn't computed (an empty unit list). 0 when
    the forecast failed. Neutral raiders aren't in it: callers that face them add aimod_neutral. contest=True: the
    place is a village we contest against its besieger: its militia / owner aren't counted (aimod_forecast_c).
    partner_credit=False reads the same forecast before partner credit, for callers summing coalition armies."""
    arr = _new_array(fb, b, cx)
    tt = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=tt, value=True)
    r = fb.reg(cx.t('f64'))
    pe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=pe, src=place)
    fb.op('CallN', dst=r, fun=helpers['forecast_c' if contest else 'forecast'], args=[fac, pe, b.const('f64', T), tt, arr])
    fb.op('Mov', dst=dst, src=b.const('f64', 0))
    skip = _uid('fcth')
    # A caller summing coalition armies on its own side must not also discount them from the enemy.
    side = 'fct' if partner_credit else 'fct_raw'
    vt = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, side), fb.dyn(fac))
    fb.op('JNull', reg=vt, offset=skip)
    fb.op('SafeCast', dst=dst, src=vt)
    fb.label(skip)


def _has_op(fb, b, cx, fac, mid, yes):
    """Jump to `yes` when faction fac has mission `mid` in preparation (started) or complete and unused (any
    target). Each getMissions result is a shared static array: scanned before the next mission call."""
    no = _uid('hop')
    mm = b.call('ent.Faction.get_missionManager', fac)
    fb.op('JNull', reg=mm, offset=no)
    for getter, held in (('getStartedMissions', False), ('getCompleteMissions', True)):
        gf = cx.fn('logic.faction.MissionManager.' + getter)
        nul = fb.reg(cx.code.types[gf.type.value].definition.args[1].value)
        fb.op('Null', dst=nul)
        arr = b.call('logic.faction.MissionManager.' + getter, mm, nul)
        u = _uid('hopl')
        fb.op('JNull', reg=arr, offset=u + 'd')
        i = fb.reg(cx.t('i32'))
        fb.op('Mov', dst=i, src=b.const('i32', 0))
        b.loop_head(u)
        fb.op('JSGte', a=i, b=b.field(arr, 'length'), offset=u + 'd')
        m = b.cast(b.call('hl.types.ArrayObj.getDyn', arr, i), 'logic.faction.Mission')
        fb.op('Incr', dst=i)
        fb.op('JNull', reg=m, offset=u)
        mi = b.field(m, 'id')
        fb.op('JNull', reg=mi, offset=u)
        fb.op('JNotEq', a=b.call('String.__compare', mi, fb.dyn(fb.string(mid))), b=b.const('i32', 0), offset=u)
        if held:
            fb.op('JTrue', cond=b.field(m, 'hasBeenUsed'), offset=u)
        fb.op('JAlways', offset=yes)
        fb.label(u + 'd')
    fb.label(no)


def _bk_partner(fb, b, cx, fac, e, yes):
    """Jump to `yes` when fac and e are both in a base-kill plan (rules/bkill.py, level >= 1) and e isn't the leader:
    partners (no war between them; user: the coalition broke its own truces over border villages)."""
    no = _uid('bkpn')
    bkt = _bk_target(fb, b, cx, fac, no)
    fb.op('JEq', a=bkt, b=e, offset=no)
    ev = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'bkv'), fb.dyn(e))
    fb.op('JNull', reg=ev, offset=no)
    ei = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=ei, src=ev)
    fb.op('JSGte', a=ei, b=b.const('i32', 1), offset=yes)
    fb.label(no)


def _bk_split(fb, b, cx, fac, owner, yes, no):
    """Jump to `yes` when `owner` (a Faction register) is fac's base-kill leader (rules/bkill.py, fac's level >= 1)
    and another faction in the plan (level >= 1, not fac, not the leader) is at war with it: the leader's army is
    pulled several ways (BK_SPLIT); else to `no`. Used by the siege sizing (siege.py), the forecast's their side
    (forecast.py) and the home need (world.aimod_home)."""
    bkt = _bk_target(fb, b, cx, fac, no)
    fb.op('JNull', reg=owner, offset=no)
    fb.op('JNotEq', a=bkt, b=owner, offset=no)
    pst = _state(fb, b, cx)
    pfs = b.cast(fb.get(pst, 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=pfs, offset=no)
    pk = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=pk, src=b.const('i32', 0))
    lp = _uid('bks')
    b.loop_head(lp)
    fb.op('JSGte', a=pk, b=b.field(pfs, 'length'), offset=no)
    pfx = b.cast(b.call('hl.types.ArrayObj.getDyn', pfs, pk), 'ent.Faction')
    fb.op('Incr', dst=pk)
    fb.op('JNull', reg=pfx, offset=lp)
    fb.op('JEq', a=pfx, b=fac, offset=lp)
    fb.op('JEq', a=pfx, b=owner, offset=lp)
    pvl = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'bkv'), fb.dyn(pfx))
    fb.op('JNull', reg=pvl, offset=lp)
    pli = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=pli, src=pvl)
    fb.op('JSLt', a=pli, b=b.const('i32', 1), offset=lp)
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', pst, pfx, owner), offset=lp)
    fb.op('JAlways', offset=yes)


def _fc_sides(fb, b, cx, fac, ours, theirs, missing):
    """ours / theirs registers = the last forecast's sides for fac (maps `fco` / `fct`); jump to `missing` if unset."""
    vo = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'fco'), fb.dyn(fac))
    vt = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'fct'), fb.dyn(fac))
    fb.op('JNull', reg=vo, offset=missing)
    fb.op('JNull', reg=vt, offset=missing)
    fb.op('SafeCast', dst=ours, src=vo)
    fb.op('SafeCast', dst=theirs, src=vt)


def _claimed(fb, b, cx, a, prio, t, held, free):
    """Jump to `held` if army a holds a live claim above register prio at time t, else to `free`."""
    u = _uid('cl')
    pv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'tkp'), fb.dyn(a))
    fb.op('JNull', reg=pv, offset=free)
    tv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'tkt'), fb.dyn(a))
    fb.op('JNull', reg=tv, offset=free)
    cp, ct = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=cp, src=pv)
    fb.op('SafeCast', dst=ct, src=tv)
    fb.op('Sub', dst=ct, a=t, b=ct)
    fb.op('JSGt', a=ct, b=b.const('f64', CLAIM_TTL), offset=free)
    fb.op('JSGt', a=cp, b=prio, offset=held)
    fb.op('JAlways', offset=free)
    return cp


def _bk_target(fb, b, cx, fac, no):
    """Base-kill plan (rules/bkill.py): the leader register when fac's level is >= 1 (check / assault), else jump to
    `no`. Maps `bkv` faction -> level, `bkl` State -> leader."""
    lv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'bkv'), fb.dyn(fac))
    fb.op('JNull', reg=lv, offset=no)
    li = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=li, src=lv)
    fb.op('JSLt', a=li, b=b.const('i32', 1), offset=no)
    ld = fb.reg(cx.t('ent.Faction'))
    fb.op('Mov', dst=ld, src=b.cast(b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'bkl'),
                                           fb.dyn(_state(fb, b, cx))), 'ent.Faction'))
    fb.op('JNull', reg=ld, offset=no)
    fb.op('JEq', a=ld, b=fac, offset=no)
    return ld


def _rallying(fb, b, cx, a, t, yes, no):
    """Jump to `yes` if army a holds a live rally claim (P_RALLY: walking to a rally point) at time t, else to `no`."""
    pv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'tkp'), fb.dyn(a))
    fb.op('JNull', reg=pv, offset=no)
    tv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'tkt'), fb.dyn(a))
    fb.op('JNull', reg=tv, offset=no)
    cp, ct = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=cp, src=pv)
    fb.op('SafeCast', dst=ct, src=tv)
    fb.op('Sub', dst=ct, a=t, b=ct)
    fb.op('JSGt', a=ct, b=b.const('f64', CLAIM_TTL), offset=no)
    fb.op('JEq', a=cp, b=b.const('f64', P_RALLY), offset=yes)
    fb.op('JAlways', offset=no)


def _pick_filter(fb, b, cx, helpers, res, ask, tag, keep_lbl):
    """In a pick wrapper: remove from array register `res` every army held above `ask` (an f64 register); log
    `claimx`. Jumps to keep_lbl when done."""
    u = _uid('pf')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.field(res, 'length'))
    b.loop_head(u)
    fb.op('JSLte', a=i, b=b.const('i32', 0), offset=keep_lbl)
    fb.op('Sub', dst=i, a=i, b=b.const('i32', 1))
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', res, i), 'ent.Army')
    fb.op('JNull', reg=a, offset=u)
    cp = _claimed(fb, b, cx, a, ask, t, u + 'h', u)
    fb.label(u + 'h')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
    _throttle(fb, b, cx, 'claimx', a, 30, u)
    _log_ev(fb, b, cx, helpers, 'claimx', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')), ('a', a),
                                           ('held', cp), ('ask', ask), ('src', tag)])
    fb.op('JAlways', offset=u)


def _cap_rem(fb, b, cx, v, t, stalled, unknown=None):
    """Remaining s of the occupation at village v (anyone's: contest hunt, release): (1 - progress) / the progress
    rate since v was first judged (maps `cpgt` / `cpgp`; restarted when progress drops or the record is older than
    CAP_STALE), (1 - progress) x CAP_EST before a rate is known (< 5 s). Jumps to `stalled` when v has no siege or
    its occupation makes no progress. Returns the (remaining, progress) registers (0 on the stalled path).
    unknown: jump there instead of using the CAP_EST guess while no rate is measured yet (the rally race conceded on
    the guess: 90 s for captures that took 100-370 s)."""
    u = _uid('cr')
    sg = b.field(v, 'siege')
    lp, lq, lrem, lp0 = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('Mov', dst=lrem, src=b.const('f64', 0))
    fb.op('Mov', dst=lp, src=b.const('f64', 0))
    fb.op('JNull', reg=sg, offset=stalled)
    fb.op('Mov', dst=lp, src=b.call('ent.comp.SiegeComponent.getOccupationActionProgress', sg))
    cpgt, cpgp = _global_map(fb, b, cx, 'cpgt'), _global_map(fb, b, cx, 'cpgp')
    vt = b.call('haxe.ds.ObjectMap.get', cpgt, fb.dyn(v))
    fb.op('JNull', reg=vt, offset=u + 'new')
    fb.op('SafeCast', dst=lp0, src=b.call('haxe.ds.ObjectMap.get', cpgp, fb.dyn(v)))
    fb.op('JSLt', a=lp, b=lp0, offset=u + 'new')  # a new capture there: restart
    fb.op('SafeCast', dst=lq, src=vt)
    fb.op('Sub', dst=lq, a=t, b=lq)
    fb.op('JSGt', a=lq, b=b.const('f64', CAP_STALE), offset=u + 'new')
    fb.op('JSLt', a=lq, b=b.const('f64', 5), offset=unknown or u + 'est')
    fb.op('Sub', dst=lp0, a=lp, b=lp0)
    fb.op('JSLte', a=lp0, b=b.const('f64', 0), offset=stalled)  # no progress: stalled
    fb.op('SDiv', dst=lp0, a=lp0, b=lq)  # rate per s
    fb.op('Sub', dst=lrem, a=b.const('f64', 1), b=lp)
    fb.op('SDiv', dst=lrem, a=lrem, b=lp0)
    fb.op('JAlways', offset=u + 'done')
    fb.label(u + 'new')
    b.call('haxe.ds.ObjectMap.set', cpgt, fb.dyn(v), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', cpgp, fb.dyn(v), fb.dyn(lp))
    if unknown:
        fb.op('JAlways', offset=unknown)
    fb.label(u + 'est')
    fb.op('Sub', dst=lrem, a=b.const('f64', 1), b=lp)
    fb.op('Mul', dst=lrem, a=lrem, b=b.const('f64', CAP_EST))
    fb.label(u + 'done')
    return lrem, lp


def _crosses(fb, b, cx, ax, ay, sx, sy, px, py, r, yes):
    """Jump to `yes` when the straight walk (ax, ay) -> (sx, sy) passes within r of (px, py) on the way: the point
    projects strictly inside the segment and lies within r of it (f64 registers; a point behind the start or past
    the end is not on the way)."""
    no = _uid('cr')
    vx, vy, wx, wy, dt, ll = (fb.reg(cx.t('f64')) for _ in range(6))
    fb.op('Sub', dst=vx, a=sx, b=ax)
    fb.op('Sub', dst=vy, a=sy, b=ay)
    fb.op('Sub', dst=wx, a=px, b=ax)
    fb.op('Sub', dst=wy, a=py, b=ay)
    fb.op('Mul', dst=dt, a=vx, b=wx)
    fb.op('Mul', dst=ll, a=vy, b=wy)
    fb.op('Add', dst=dt, a=dt, b=ll)
    fb.op('JSLte', a=dt, b=b.const('f64', 0), offset=no)
    fb.op('Mul', dst=ll, a=vx, b=vx)
    fb.op('Mul', dst=vy, a=vy, b=vy)
    fb.op('Add', dst=ll, a=ll, b=vy)
    fb.op('JSGte', a=dt, b=ll, offset=no)
    # squared distance to the line: |w|^2 - (v.w)^2 / |v|^2
    fb.op('Mul', dst=dt, a=dt, b=dt)
    fb.op('SDiv', dst=dt, a=dt, b=ll)
    fb.op('Mul', dst=wx, a=wx, b=wx)
    fb.op('Mul', dst=wy, a=wy, b=wy)
    fb.op('Add', dst=wx, a=wx, b=wy)
    fb.op('Sub', dst=wx, a=wx, b=dt)
    fb.op('JSLt', a=wx, b=b.const('f64', r * r), offset=yes)
    fb.label(no)


def build_chain(cx, fns):
    """One (AIMilitary, dt) -> void function calling each of fns in order (each has its own throttle and trap)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    void = fb.reg(cx.t('void'))
    for f in fns:
        fb.op('Call2', dst=void, fun=f, arg0=0, arg1=1)
    fb.op('Ret', ret=void)
    return fb.build()


def _skip_striking(fb, b, cx, helpers, army, skip):
    """Jump to `skip` while army is in an en-route strike (aimod_striking, rules/strike.py) or waits on rock after a
    worm flee (aimod_wormonly, rules/worm.py: a siege army keeps its order there): rules that move order armies
    (gather, stage, desert-step, spos) leave it alone (desert-step ran right after worm-flee in the same tick and
    walked it back across the sand to the village)."""
    e = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=e, src=army)
    r = fb.reg(cx.t('bool'))
    fb.op('Call1', dst=r, fun=helpers['striking'], arg0=e)
    fb.op('JTrue', cond=r, offset=skip)
    fb.op('Call1', dst=r, fun=helpers['wormonly'], arg0=e)
    fb.op('JTrue', cond=r, offset=skip)




CRUMBS = []        # step id -> 'module.py:line' (_crumb_begin), reset per build, written to work/crumbs.json
CRUMB_LOG_T = 30   # s: `rfail` at most this often per rule and faction


def _crumb_src():
    import sys
    from pathlib import Path
    f = sys._getframe(2)
    while f is not None:
        stem = Path(f.f_code.co_filename).stem
        if stem == '__init__':  # a package (rules/bkcamp/): its name
            stem = Path(f.f_code.co_filename).parent.name
        if stem not in ('inject', 'aware', 'common'):
            return f'{stem}.py:{f.f_lineno}'
        f = f.f_back
    return 'unknown'


def _crumb_begin(fb, b, cx, helpers, rule):
    """Step probe for a tick rule (reg 0 = AIMilitary), no exception handler involved (logging trap handlers
    crashed the game): map `crumb_<rule>` faction module -> step. A run sets 0, then before every Call op the step
    id of that call (CRUMBS: its source line), and _crumb_end sets -1. A run that finds a step >= 0 knows the last run
    died there (an exception its trap swallowed) and logs `rfail` {r, f, at = step id; mod log maps it to the line}."""
    name = 'crumb_' + rule
    m = _global_map(fb, b, cx, name)
    prev = b.call('haxe.ds.ObjectMap.get', m, fb.dyn(0))
    go = _uid('cbg')
    fb.op('JNull', reg=prev, offset=go)
    pi = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=pi, src=prev)
    fb.op('JSLt', a=pi, b=b.const('i32', 0), offset=go)
    _throttle(fb, b, cx, 'rfail_' + rule, 0, CRUMB_LOG_T, go)
    _log_ev(fb, b, cx, helpers, 'rfail', [('r', rule), ('f', fb.get(0, 'controller', 'owner', 'kind')),
                                          ('at', fb.dyn(pi))])
    fb.label(go)
    b.call('haxe.ds.ObjectMap.set', m, fb.dyn(0), fb.dyn(b.const('i32', 0)))
    gidx = GLOBALS[name][1]
    om_t = cx.t('haxe.ds.ObjectMap')

    def hook(fb_):
        cid = len(CRUMBS)
        CRUMBS.append(_crumb_src())
        bb = B(fb_)
        r = fb_.reg(om_t)
        fb_.op('GetGlobal', dst=r, **{'global': gidx})
        bb.call('haxe.ds.ObjectMap.set', r, fb_.dyn(0), fb_.dyn(bb.const('i32', cid)))
    fb.crumb = hook


def _crumb_end(fb, b, cx, rule):
    """Normal end of the probed run (after the rule's 'end' label, inside its trap): step -1."""
    fb.crumb = None
    r = fb.reg(cx.t('haxe.ds.ObjectMap'))
    fb.op('GetGlobal', dst=r, **{'global': GLOBALS['crumb_' + rule][1]})
    b.call('haxe.ds.ObjectMap.set', r, fb.dyn(0), fb.dyn(b.const('i32', -1)))


TRAP_LOG = False   # crash bisect: logging trap handlers off (the game quit at match start since they came in)
TRAP_LOG_T = 30    # s: a rule's caught exception is logged (`trap` src, err) at most this often per rule


def make_trap_hook(helpers):
    """FB.trap_hook for the rule builds (behave.install): a trap's handler logs `trap` {src: building function, err:
    the exception} at most every TRAP_LOG_T s per src, inside its own trap (the log can't throw into vanilla).
    Rule traps were silent: Atreides' strat and every rally stopped logging mid-match with no trace."""
    def hook(fb, exc, src):
        b = B(fb)
        cx = fb.cx
        iexc, ih, skip = fb.reg(cx.t('dyn')), _uid('trh'), _uid('trs')
        fb.op('Trap', exc=iexc, offset=ih)
        _throttle(fb, b, cx, 'trap_' + src, _state(fb, b, cx), TRAP_LOG_T, skip)
        err = fb.reg(cx.t('String'))
        fb.op('Call1', dst=err, fun=cx.fn('$Std.string').findex.value, arg0=exc)
        _log_ev(fb, b, cx, helpers, 'trap', [('src', src), ('err', err)])
        fb.label(skip)
        fb.op('EndTrap', exc=iexc)
        fb.label(ih)
    return hook


def _pillaging(fb, b, cx, s, yes):
    """Jump to `yes` when structure s's running occupation is a Pillage (`SiegeComponent.getOccupationActionKind`):
    a 20-day loss of production, while an Annex / Liberate / Takeover loses the village. A siege still in its militia
    fight (no occupation yet) isn't known to be one and counts as a capture."""
    sg = b.field(s, 'siege')
    no = _uid('pln')
    fb.op('JNull', reg=sg, offset=no)
    k = b.call('ent.comp.SiegeComponent.getOccupationActionKind', sg)
    fb.op('JNull', reg=k, offset=no)
    fb.op('JEq', a=b.call('String.__compare', k, fb.dyn(fb.string('Pillage'))), b=b.const('i32', 0), offset=yes)
    fb.label(no)


def _base_near(fb, b, cx, fac, e, r, yes):
    """Jump to `yes` when entity e is within r of one of fac's active main bases."""
    lo = _uid('bnr')
    k = fb.reg(cx.t('i32'))
    ee, me = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ee, src=e)
    mbs = b.field(fac, 'mainBases')
    fb.op('JNull', reg=mbs, offset=lo + 'd')
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head(lo)
    fb.op('JSGte', a=k, b=b.field(mbs, 'length'), offset=lo + 'd')
    mb = b.cast(b.call('hl.types.ArrayObj.getDyn', mbs, k), 'ent.Structure')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=mb, offset=lo)
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', mb), offset=lo)
    fb.op('Mov', dst=me, src=mb)
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', ee, me), b=b.const('f64', r), offset=yes)
    fb.op('JAlways', offset=lo)
    fb.label(lo + 'd')


def _pannex_ok(fb, b, cx, fac, s, no):
    """Jump to `no` unless fac may spend PeacefullyAnnex on structure s (pannex fallback and vanilla's
    checkPeacefulAnnexation, rules/pannex.py): we own >= PANNEX_MIN_VILLAGES villages, hold >= PANNEX_INF Influence
    and s's zone lies >= PANNEX_HOPS zones from our main base (no main base: any distance)."""
    fb.op('JSLt', a=b.field(b.call('ent.Faction.getVillages', fac), 'length'), b=b.const('i32', PANNEX_MIN_VILLAGES),
          offset=no)
    inf = fb.reg(cx.t('f64'))
    fb.op('Call2', dst=inf, fun=cx.fn('ent.Faction.getResource').findex.value, arg0=fac,
          arg1=b.const('i32', RES_INFLUENCE))
    fb.op('JSLt', a=inf, b=b.const('f64', PANNEX_INF), offset=no)
    z = b.call('ent.Entity.get_zone', s)
    fb.op('JNull', reg=z, offset=no)
    gdb = cx.fn('ent.Zone.getDistanceToPlayerBase')
    gnull = fb.reg(cx.code.types[gdb.type.value].definition.args[2].value)
    fb.op('Null', dst=gnull)
    hops = fb.reg(cx.t('i32'))
    fb.op('Call3', dst=hops, fun=gdb.findex.value, arg0=z, arg1=fac, arg2=gnull)
    fb.op('JSLt', a=hops, b=b.const('i32', PANNEX_HOPS), offset=no)


def _base_dist(fb, b, s, fac):
    """Distance from structure s to fac's nearest active main base (1 << 30: none)."""
    cx = fb.cx
    d, bd = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    k = fb.reg(cx.t('i32'))
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=s)
    fb.op('Mov', dst=bd, src=b.const('f64', 1 << 30))
    lo = _uid('bdl')
    mbs = b.field(fac, 'mainBases')
    fb.op('JNull', reg=mbs, offset=lo + 'd')
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head(lo)
    fb.op('JSGte', a=k, b=b.field(mbs, 'length'), offset=lo + 'd')
    mb = b.cast(b.call('hl.types.ArrayObj.getDyn', mbs, k), 'ent.Structure')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=mb, offset=lo)
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', mb), offset=lo)
    me = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=me, src=mb)
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', se, me))
    fb.op('JSGte', a=d, b=bd, offset=lo)
    fb.op('Mov', dst=bd, src=d)
    fb.op('JAlways', offset=lo)
    fb.label(lo + 'd')
    return bd


def _af_remote(fb, b, cx, s, z, fac, yes, no, none):
    """Airfield-steer's remote test for village s (zone z) of fac: jump to `yes` when >= TURRET_REMOTE zones
    (Zone.getDistanceToPlayerBase) or >= REMOTE_D in a straight line from fac's nearest active main base, `none` when
    fac has no active main base (no measure), else `no`. Returns (db, hops) registers."""
    db = _base_dist(fb, b, s, fac)
    hops = fb.reg(cx.t('i32'))
    gdb = cx.fn('ent.Zone.getDistanceToPlayerBase')
    gnull = fb.reg(cx.code.types[gdb.type.value].definition.args[2].value)
    fb.op('Null', dst=gnull)
    fb.op('Call3', dst=hops, fun=gdb.findex.value, arg0=z, arg1=fac, arg2=gnull)
    fb.op('JSGte', a=db, b=b.const('f64', 1 << 29), offset=none)  # no main base of ours: no measure
    fb.op('JSGte', a=db, b=b.const('f64', REMOTE_D), offset=yes)
    fb.op('JSGte', a=hops, b=b.const('i32', 99), offset=no)
    fb.op('JSGte', a=hops, b=b.const('i32', TURRET_REMOTE), offset=yes)
    fb.op('JAlways', offset=no)
    return db, hops


def _af_behind(fb, b, cx, se, fac, fail):
    """Bool register: entity se lies behind fac's nearest active main base B (every other faction's active main base
    M has d(se, M) >= d(B, M): between us and the map border). `fail` when fac has no main base list / none active."""
    zi = b.const('i32', 0)
    L = {n: _uid('afb' + n) for n in ('mb', 'mbd', 'of', 'ofd', 'om', 'bhd')}
    bm = fb.reg(cx.t('ent.Entity'))  # our nearest active main base
    fb.op('Null', dst=bm)
    d, bd = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=bd, src=b.const('f64', 1 << 30))
    i, j = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    me = fb.reg(cx.t('ent.Entity'))
    mbs = b.field(fac, 'mainBases')
    fb.op('JNull', reg=mbs, offset=fail)
    fb.op('Mov', dst=i, src=zi)
    b.loop_head(L['mb'])
    fb.op('JSGte', a=i, b=b.field(mbs, 'length'), offset=L['mbd'])
    mb = b.cast(b.call('hl.types.ArrayObj.getDyn', mbs, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=mb, offset=L['mb'])
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', mb), offset=L['mb'])
    fb.op('Mov', dst=me, src=mb)
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', se, me))
    fb.op('JSGte', a=d, b=bd, offset=L['mb'])
    fb.op('Mov', dst=bd, src=d)
    fb.op('Mov', dst=bm, src=me)
    fb.op('JAlways', offset=L['mb'])
    fb.label(L['mbd'])
    fb.op('JNull', reg=bm, offset=fail)
    behind = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=behind, value=False)
    facs = b.cast(fb.get(_state(fb, b, cx), 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=facs, offset=L['bhd'])
    nb = fb.reg(cx.t('i32'))  # other active main bases seen
    fb.op('Mov', dst=nb, src=zi)
    fb.op('Mov', dst=i, src=zi)
    b.loop_head(L['of'])
    fb.op('JSGte', a=i, b=b.field(facs, 'length'), offset=L['ofd'])
    of = b.cast(b.call('hl.types.ArrayObj.getDyn', facs, i), 'ent.Faction')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=of, offset=L['of'])
    fb.op('JEq', a=of, b=fac, offset=L['of'])
    ombs = b.field(of, 'mainBases')
    fb.op('JNull', reg=ombs, offset=L['of'])
    fb.op('Mov', dst=j, src=zi)
    b.loop_head(L['om'])
    fb.op('JSGte', a=j, b=b.field(ombs, 'length'), offset=L['of'])
    om = b.cast(b.call('hl.types.ArrayObj.getDyn', ombs, j), 'ent.Structure')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=om, offset=L['om'])
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', om), offset=L['om'])
    fb.op('Mov', dst=me, src=om)
    fb.op('Incr', dst=nb)
    # s nearer to this base than our base is: s is on the way somewhere, not behind us
    fb.op('JSLt', a=b.call('ent.Entity.getDistTo', se, me), b=b.call('ent.Entity.getDistTo', bm, me), offset=L['bhd'])
    fb.op('JAlways', offset=L['om'])
    fb.label(L['ofd'])
    fb.op('JSLte', a=nb, b=zi, offset=L['bhd'])  # nobody else: no "behind"
    fb.op('Bool', dst=behind, value=True)
    fb.label(L['bhd'])
    return behind


def _af_spaced(fb, b, cx, s, se, fac, airfield, gk, gkn, ku):
    """Bool register: another structure of fac (not s) within AF_SPACING of se holds an Airfield (built or going
    up: Upgrades.getKind)."""
    zi = b.const('i32', 0)
    lo = _uid('afs')
    i = fb.reg(cx.t('i32'))
    me = fb.reg(cx.t('ent.Entity'))
    spaced = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=spaced, value=False)
    mine = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=mine, offset=lo + 'd')
    fb.op('Mov', dst=i, src=zi)
    b.loop_head(lo)
    fb.op('JSGte', a=i, b=b.field(mine, 'length'), offset=lo + 'd')
    st = b.cast(b.call('hl.types.ArrayObj.getDyn', mine, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=st, offset=lo)
    fb.op('JEq', a=st, b=s, offset=lo)
    fb.op('Mov', dst=me, src=st)
    fb.op('JSGte', a=b.call('ent.Entity.getDistTo', se, me), b=b.const('f64', AF_SPACING), offset=lo)
    sup = b.field(st, 'upgrades')
    fb.op('JNull', reg=sup, offset=lo)
    fb.op('CallN', dst=ku, fun=gk.findex.value, args=[sup, airfield] + gkn)
    fb.op('JNull', reg=ku, offset=lo)
    fb.op('Bool', dst=spaced, value=True)
    fb.label(lo + 'd')
    return spaced


def _neutral_village(fb, b, cx, s_e, no):
    """Jump to `no` unless s_e is a neutral village (no owner; not a sietch / renegade base, which keep the lost-siege
    memory and SITE_REQ: their garrison spawns harass units mid-strike)."""
    fb.op('JNotNull', reg=b.call('ent.Entity.get_owner', s_e), offset=no)
    ss = b.cast(fb.dyn(s_e), 'ent.Structure')
    fb.op('JNull', reg=ss, offset=no)
    _strong_site(fb, b, ss, no)


def _nbump_mark(fb, b, cx, fac, s_e, t):
    """Our siege of neutral village s_e lost to its militia: map `nbump` (per faction) s_e -> t (read by _nbump)."""
    b.call('haxe.ds.ObjectMap.set', _fac_map(fb, b, cx, 'nbump', fac), fb.dyn(s_e), fb.dyn(t))


def _nbump(fb, b, cx, fac, s_e, r):
    """r (f64 reg) x NBUMP_K in place while fac's siege of s_e lost to its militia within NBUMP_T (user: a neutral
    village that beat us gets a little more next time, no fear memory)."""
    u = _uid('nbp')
    fb.op('JNull', reg=fac, offset=u)
    v = b.call('haxe.ds.ObjectMap.get', _fac_map(fb, b, cx, 'nbump', fac), fb.dyn(s_e))
    fb.op('JNull', reg=v, offset=u)
    q = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=q, src=v)
    fb.op('Sub', dst=q, a=b.field(_state(fb, b, cx), 'time'), b=q)
    fb.op('JSGt', a=q, b=b.const('f64', NBUMP_T), offset=u)
    fb.op('Mul', dst=r, a=r, b=_ratio(fb, b, NBUMP_K))
    fb.label(u)


def _recent_launch(fb, b, cx, s_e, t, recent, fac=None, helpers=None):
    """Jump to `recent` if vanilla launched a siege on s_e less than its block ago (map 'alaunch', set by the
    tryArmyAction wrapper; block = map 'ablk', RETRY doubling up to RETRY_MAX for a target relaunched right after
    its block ran out; at least UNREACH_T when its last order died in Waiting: out of supply reach).
    fac given: the records (keyed by target) count only when the last order on s_e (map `aord`) is fac's: another
    faction's failed launch on a village blocked ours too. Lost siege (fac given): that order reached Engage and
    ended with at least 1 / LOST_SHARE_DEN of the armies it launched with (map `aunits`, copied at launch) dead ->
    s_e is out for LOST_T s from when this is first seen within LOST_WIN of that launch, never on a village of
    ours (maps `slost` / `slostf`; log `slost`): Harkonnen lost 10
    armies under Mar-iel / Qartnin's batteries at Atreides' Yawan (28:16) and sent 14 more the same way at 43:47."""
    old = _uid('old')
    if fac is not None:
        ao = b.cast(b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'aord'), fb.dyn(s_e)), 'logic.ai.AIOrder')
        fb.op('JNull', reg=ao, offset=old + 'own')
        aos = b.field(ao, 'orders')
        fb.op('JNull', reg=aos, offset=old + 'own')
        fb.op('JNotEq', a=b.field(b.field(aos, 'controller'), 'owner'), b=fac, offset=old)
        fb.label(old + 'own')
        # lost siege memory
        slm, slf = _global_map(fb, b, cx, 'slost'), _global_map(fb, b, cx, 'slostf')
        lsv = b.call('haxe.ds.ObjectMap.get', slm, fb.dyn(s_e))
        fb.op('JNull', reg=lsv, offset=old + 'det')
        fb.op('JNotEq', a=b.call('haxe.ds.ObjectMap.get', slf, fb.dyn(s_e)), b=fb.dyn(fac), offset=old + 'det')
        lsq = fb.reg(cx.t('f64'))
        fb.op('SafeCast', dst=lsq, src=lsv)
        fb.op('Sub', dst=lsq, a=t, b=lsq)
        fb.op('JSLt', a=lsq, b=b.const('f64', LOST_T), offset=recent)
        fb.label(old + 'det')
        aum = _global_map(fb, b, cx, 'aunits')
        au = b.cast(b.call('haxe.ds.ObjectMap.get', aum, fb.dyn(s_e)), 'hl.types.ArrayObj')
        fb.op('JNull', reg=au, offset=old + 'n')
        fb.op('JNull', reg=ao, offset=old + 'n')
        aou = b.field(ao, 'units')
        fb.op('JNull', reg=aou, offset=old + 'nd')
        fb.op('JSGt', a=b.field(aou, 'length'), b=b.const('i32', 0), offset=old + 'n')  # still running
        fb.label(old + 'nd')
        fb.op('JSLte', a=b.field(ao, 'phase'), b=b.const('i32', REGROUP), offset=old + 'n')  # never fought there
        # judged only soon after it (LOST_WIN from its launch) and not on a village of ours: a costly capture that
        # succeeded and was lost much later must stay a target (the bunker retake)
        fb.op('JEq', a=b.call('ent.Entity.get_owner', s_e), b=fac, offset=old + 'n')
        alv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'alaunch'), fb.dyn(s_e))
        fb.op('JNull', reg=alv, offset=old + 'n')
        alq = fb.reg(cx.t('f64'))
        fb.op('SafeCast', dst=alq, src=alv)
        fb.op('Sub', dst=alq, a=t, b=alq)
        fb.op('JSGt', a=alq, b=b.const('f64', LOST_WIN), offset=old + 'n')
        an, ad, ai = fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
        fb.op('Mov', dst=an, src=b.field(au, 'length'))
        fb.op('Mov', dst=ad, src=b.const('i32', 0))
        fb.op('Mov', dst=ai, src=b.const('i32', 0))
        b.loop_head(old + 'l')
        fb.op('JSGte', a=ai, b=an, offset=old + 'ld')
        ae = b.cast(b.call('hl.types.ArrayObj.getDyn', au, ai), 'ent.Entity')
        fb.op('Incr', dst=ai)
        fb.op('JNull', reg=ae, offset=old + 'l')
        fb.op('JFalse', cond=b.call('ent.Entity.isDead', ae), offset=old + 'l')
        fb.op('Incr', dst=ad)
        fb.op('JAlways', offset=old + 'l')
        fb.label(old + 'ld')
        b.call('haxe.ds.ObjectMap.remove', aum, fb.dyn(s_e))  # judged once
        aq = fb.reg(cx.t('i32'))
        fb.op('Mul', dst=aq, a=ad, b=b.const('i32', LOST_SHARE_DEN))
        fb.op('JSLt', a=aq, b=an, offset=old + 'n')
        # a neutral village (militia only) is no fear memory (user: we always bring enough for a neutral village; if
        # we got it wrong, a little more next time): `nbump`, no block
        _neutral_village(fb, b, cx, s_e, old + 'nn')
        _nbump_mark(fb, b, cx, fac, s_e, t)
        if helpers is not None:
            _log_ev(fb, b, cx, helpers, 'slost', [('f', fb.get(fac, 'kind')), ('tgt', s_e), ('why', 'bump')])
        fb.op('JAlways', offset=old + 'n')
        fb.label(old + 'nn')
        b.call('haxe.ds.ObjectMap.set', slm, fb.dyn(s_e), fb.dyn(t))
        b.call('haxe.ds.ObjectMap.set', slf, fb.dyn(s_e), fb.dyn(fac))
        if helpers is not None:
            anf, adf = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
            fb.op('ToSFloat', dst=anf, src=an)
            fb.op('ToSFloat', dst=adf, src=ad)
            _log_ev(fb, b, cx, helpers, 'slost', [('f', fb.get(fac, 'kind')), ('tgt', s_e), ('n', anf), ('dead', adf),
                                                  ('ph', fb.dyn(b.field(ao, 'phase')))])
        fb.op('JAlways', offset=recent)
        fb.label(old + 'n')
    last = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'alaunch'), fb.dyn(s_e))
    fb.op('JNull', reg=last, offset=old)
    lf, bl = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=lf, src=last)
    fb.op('Sub', dst=lf, a=t, b=lf)
    fb.op('Mov', dst=bl, src=b.const('f64', RETRY))
    bv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'ablk'), fb.dyn(s_e))
    fb.op('JNull', reg=bv, offset=old + 'b')
    fb.op('SafeCast', dst=bl, src=bv)
    fb.label(old + 'b')
    # out of reach (common._unreach): at least UNREACH_T from that launch
    chk = old + 'c'
    _unreach(fb, b, cx, s_e, t, old + 'u', fac)
    fb.op('JAlways', offset=chk)
    fb.label(old + 'u')
    fb.op('JSGte', a=bl, b=b.const('f64', UNREACH_T), offset=chk)
    fb.op('Mov', dst=bl, src=b.const('f64', UNREACH_T))
    fb.label(chk)
    fb.op('JSLt', a=lf, b=bl, offset=recent)
    fb.label(old)


def _vfield(fb, b, obj, name):
    """Field of a virtual (anonymous struct) register by name -> (register of the field's type, field index)."""
    cx = fb.cx
    fields = cx.code.types[fb.regs[obj]].definition.fields
    idx = [i for i, f in enumerate(fields) if f.name.resolve(cx.code) == name]
    if len(idx) != 1:
        raise ValueError(f'siege-join: field {name} not found')
    dst = fb.reg(fields[idx[0]].type.value)
    fb.op('Field', dst=dst, obj=obj, field=idx[0])
    return dst, idx[0]


__all__ = [n for n in dir() if not n.startswith('__')]
