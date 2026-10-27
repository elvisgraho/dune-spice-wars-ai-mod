"""Stage: a siege's armies regroup out of the target's reach (AI-POLICY §4 Gathering: a structure can't run, so we
gather strength next to it, never inside its turrets / militia trigger).

Vanilla Regroup (checkRegroupOrder) walks each order army along its own path (`order.unitPaths[army]`: {current,
steps}, step {from, mode, sync, to}) and counts it arrived at the `to` of its second-to-last step (the last one when
the path has a single step). That point is often 15-50 from the target: the first armies stand inside its turrets /
militia while the order waits for the rest (Fremen's Annex of Atreides' Hadur: F_Trooper and F_Special 150 s in
Regroup at 15-50 from it, the trooper shot down by the village's turret and militia with no Atreides army near, the
fight balance at 1.0: turrets and militia read no power, so no retreat). Fast armies (ships) arrive first and
alone the same way.

Every CHECK s per faction: our Military orders in Regroup on a structure not ours; for each order army whose regroup
step (walking mode) ends within STAGE_R of the target, that step's `to` becomes a new point STAGE_R from the target
towards the army, judged once the army is on that step within STAGE_SEE (or arrived); skipped when that point is in
the deep desert. The army is moved there now; an army already arrived at vanilla's point stays counted as arrived
(set back a step, vanilla's 5 s stall test would cancel the whole order while micro holds it in the militia fight). Vanilla then counts arrival at
the staged point as usual; siege-engage counts armies within ENGAGE_R (> STAGE_R) as at the target, so an early
Engage still fires when the staged part is strong enough, and Engage sends them in together. Logs `stage` (a, tgt,
d = old point's distance, arr = had arrived). In a trap: vanilla's point on any error."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.worm import _move_to


def _virtual(cx, fn_name, fields):
    """Type index of the virtual with exactly these field names among fn_name's registers."""
    want = set(fields)
    for r in cx.fn(fn_name).regs:
        t = cx.code.types[r.value]
        if t.kind.value == 15 and {f.name.resolve(cx.code) for f in t.definition.fields} == want:
            return r.value
    raise ValueError(f'stage: virtual {sorted(want)} not found in {fn_name}')


def _vidx(cx, t, name):
    fields = cx.code.types[t].definition.fields
    hits = [i for i, f in enumerate(fields) if f.name.resolve(cx.code) == name]
    if len(hits) != 1:
        raise ValueError(f'stage: field {name} not found on t@{t}')
    return hits[0], fields[hits[0]].type.value


def build_stage(cx, helpers):
    """aimod_stage(mil, dt) (see module doc)."""
    path_t = _virtual(cx, 'logic.ai.AIOrders.checkRegroupOrder', ['current', 'steps'])
    step_t = _virtual(cx, 'logic.ai.AIOrders.checkRegroupOrder', ['from', 'mode', 'sync', 'to'])
    cur_i, cur_t = _vidx(cx, path_t, 'current')
    steps_i, steps_t = _vidx(cx, path_t, 'steps')
    mode_i, mode_t = _vidx(cx, step_t, 'mode')
    to_i, pt_t = _vidx(cx, step_t, 'to')
    from_i, from_t = _vidx(cx, step_t, 'from')
    if from_t != pt_t:
        raise ValueError(f'stage: step.from t@{from_t} != step.to t@{pt_t}')
    x_i, x_t = _vidx(cx, pt_t, 'x')
    y_i, y_t = _vidx(cx, pt_t, 'y')
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = b.field(_state(fb, b, cx), 'time')
    _tick(fb, b, cx, t, CHECK, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    gs = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gs, **{'global': cx.global_of('$Game')})
    world = b.field(b.field(gs, 'inst'), 'world')
    fb.op('JNull', reg=world, offset='end')
    zi, one = b.const('i32', 0), b.const('i32', 1)
    i, j, idx, n, ri, cur = (fb.reg(cx.t('i32')) for _ in range(6))
    tx, ty, dx, dy, d, q, px, py = (fb.reg(cx.t('f64')) for _ in range(8))
    r2 = b.const('f64', (STAGE_R - 1) ** 2)
    arr = fb.reg(cx.t('bool'))
    tgt = fb.reg(cx.t('ent.Entity'))
    path, step = fb.reg(path_t), fb.reg(step_t)
    steps = fb.reg(steps_t)
    to, pt, fr = fb.reg(pt_t), fb.reg(pt_t), fb.reg(pt_t)
    rx, ry, rq = (fb.reg(cx.t('f64')) for _ in range(3))
    mode = fb.reg(mode_t)
    fx, fy = fb.reg(x_t), fb.reg(y_t)
    ci = fb.reg(cur_t)
    fb.op('Mov', dst=i, src=b.field(orders, 'length'))
    b.loop_head('o')
    fb.op('JSLte', a=i, b=zi, offset='end')
    fb.op('Sub', dst=i, a=i, b=one)
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, i), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset='o')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='o')
    fb.op('JNotEq', a=b.field(o, 'phase'), b=b.const('i32', REGROUP), offset='o')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='o')
    fb.op('EnumIndex', dst=idx, value=tt)
    fb.op('JNotEq', a=idx, b=b.const('i32', T_STRUCT), offset='o')
    fb.op('Mov', dst=tgt, src=b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'ent.Entity'))
    fb.op('JNull', reg=tgt, offset='o')
    fb.op('JEq', a=b.call('ent.Entity.get_owner', tgt), b=fac, offset='o')  # a move to our own structure
    ups = b.field(o, 'unitPaths')
    fb.op('JNull', reg=ups, offset='o')
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='o')
    fb.op('Mov', dst=tx, src=b.field(tgt, 'posx'))
    fb.op('Mov', dst=ty, src=b.field(tgt, 'posy'))
    a = _army_loop(fb, b, units, b.field(units, 'length'), j, 'u', 'o')
    pv = b.call('haxe.ds.ObjectMap.get', ups, fb.dyn(a))
    fb.op('JNull', reg=pv, offset='u')
    fb.op('ToVirtual', dst=path, src=pv)
    fb.op('Field', dst=steps, obj=path, field=steps_i)
    fb.op('JNull', reg=steps, offset='u')
    # the regroup step: arrivalIndex = max(1, steps - 1) in Regroup, i.e. step max(0, steps - 2)
    fb.op('Mov', dst=n, src=b.field(steps, 'length'))
    fb.op('JSLte', a=n, b=zi, offset='u')
    fb.op('Sub', dst=ri, a=n, b=b.const('i32', 2))
    fb.op('JSGte', a=ri, b=zi, offset='ri_ok')
    fb.op('Mov', dst=ri, src=zi)
    fb.label('ri_ok')
    sv = b.call('hl.types.ArrayObj.getDyn', steps, ri)
    fb.op('JNull', reg=sv, offset='u')
    fb.op('ToVirtual', dst=step, src=sv)
    fb.op('Field', dst=mode, obj=step, field=mode_i)
    fb.op('JNull', reg=mode, offset='u')
    fb.op('EnumIndex', dst=idx, value=mode)
    fb.op('JNotEq', a=idx, b=zi, offset='u')  # walking only (no shuttle / worm step)
    # still on an earlier step (a walk to a shuttle pad, a worm ride): staged later, once on its regroup step (a Move
    # now would skip the transport)
    fb.op('Bool', dst=arr, value=False)
    fb.op('Field', dst=ci, obj=path, field=cur_i)
    fb.op('Mov', dst=cur, src=ci)
    fb.op('JSLt', a=cur, b=ri, offset='u')
    fb.op('JSLte', a=cur, b=ri, offset='walking')
    # arrived: it stays counted as arrived (vanilla neither re-moves nor stall-checks it); setting it back a step
    # would let vanilla's stall test (AI_Army_StuckTime 5 s, > AI_Army_StuckCancelDistance 20 to go) cancel the whole
    # order when micro holds it in the militia fight
    fb.op('Bool', dst=arr, value=True)
    fb.label('walking')
    fb.op('Field', dst=to, obj=step, field=to_i)
    fb.op('JNull', reg=to, offset='u')
    fb.op('Field', dst=fx, obj=to, field=x_i)
    fb.op('Field', dst=fy, obj=to, field=y_i)
    fb.op('Sub', dst=dx, a=fx, b=tx)
    fb.op('Sub', dst=dy, a=fy, b=ty)
    fb.op('Mul', dst=d, a=dx, b=dx)
    fb.op('Mul', dst=q, a=dy, b=dy)
    fb.op('Add', dst=d, a=d, b=q)
    fb.op('JSGte', a=d, b=r2, offset='u')  # already out of reach (staged or vanilla's own)
    fb.op('Mov', dst=d, src=b.call('hxd.$Math.sqrt', d))
    # STAGE_R from the target towards the army (its approach side: the point lies on the stretch it walks). An army
    # already inside the ring takes the side its regroup step starts from (a point beyond the army could be off the
    # map / unwalkable), else its own side, else vanilla's point's side
    fb.op('Sub', dst=px, a=b.field(a, 'posx'), b=tx)
    fb.op('Sub', dst=py, a=b.field(a, 'posy'), b=ty)
    fb.op('Mul', dst=q, a=px, b=px)
    fb.op('Mul', dst=dy, a=py, b=py)
    fb.op('Add', dst=q, a=q, b=dy)
    # walking: judged once within STAGE_SEE, where its own position shows the side it comes in from (from far away a
    # path round a cliff or along a ramp enters elsewhere, and a point on the straight line would walk it round the
    # village under its turrets)
    fb.op('JTrue', cond=arr, offset='near_ok')
    fb.op('JSGt', a=q, b=b.const('f64', STAGE_SEE ** 2), offset='u')
    fb.label('near_ok')
    fb.op('JSGte', a=q, b=r2, offset='dir_ok')
    fb.op('Field', dst=fr, obj=step, field=from_i)
    fb.op('JNull', reg=fr, offset='dir_own')
    fb.op('Field', dst=fx, obj=fr, field=x_i)
    fb.op('Field', dst=fy, obj=fr, field=y_i)
    fb.op('Sub', dst=rx, a=fx, b=tx)
    fb.op('Sub', dst=ry, a=fy, b=ty)
    fb.op('Mul', dst=rq, a=rx, b=rx)
    fb.op('Mul', dst=dy, a=ry, b=ry)
    fb.op('Add', dst=rq, a=rq, b=dy)
    fb.op('JSLt', a=rq, b=r2, offset='dir_own')
    fb.op('Mov', dst=px, src=rx)
    fb.op('Mov', dst=py, src=ry)
    fb.op('Mov', dst=q, src=rq)
    fb.op('JAlways', offset='dir_ok')
    fb.label('dir_own')
    fb.op('JSGte', a=q, b=b.const('f64', 1), offset='dir_ok')
    fb.op('Mov', dst=px, src=dx)  # standing on the centre: vanilla's point gives the side
    fb.op('Mov', dst=py, src=dy)
    fb.op('Mul', dst=q, a=px, b=px)
    fb.op('Mul', dst=dy, a=py, b=py)
    fb.op('Add', dst=q, a=q, b=dy)
    fb.op('JSLt', a=q, b=b.const('f64', 1), offset='u')
    fb.label('dir_ok')
    fb.op('Mov', dst=q, src=b.call('hxd.$Math.sqrt', q))
    fb.op('SDiv', dst=q, a=b.const('f64', STAGE_R), b=q)
    fb.op('Mul', dst=px, a=px, b=q)
    fb.op('Mul', dst=py, a=py, b=q)
    fb.op('Add', dst=px, a=px, b=tx)
    fb.op('Add', dst=py, a=py, b=ty)
    # never wait in the deep desert (policy §4 Gathering): keep vanilla's point there
    z = b.call('world.World.getZoneAt', world, px, py)
    fb.op('JNull', reg=z, offset='u')
    fb.op('JTrue', cond=b.call('ent.Zone.isDeepDesert', z), offset='u')
    fb.op('New', dst=pt)
    fb.op('Mov', dst=fx, src=px)
    fb.op('Mov', dst=fy, src=py)
    fb.op('SetField', obj=pt, field=x_i, src=fx)
    fb.op('SetField', obj=pt, field=y_i, src=fy)
    fb.op('SetField', obj=step, field=to_i, src=pt)
    _skip_striking(fb, b, cx, helpers, a, 'u')  # en-route strike: it fights first, staged afterwards
    # moved now (else it finishes the walk to vanilla's point first; an arrived one stands there)
    _move_to(fb, b, cx, a, px, py, fac)
    _log_ev(fb, b, cx, helpers, 'stage', [('f', fb.get(fac, 'kind')), ('a', a), ('tgt', tgt), ('d', d),
                                          ('arr', arr)])
    fb.op('JAlways', offset='u')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
