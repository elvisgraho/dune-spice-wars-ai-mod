"""Supply Drop: our use only (AI-POLICY "Supply Drop").

Why: vanilla `Spying.tryLaunchOperation` (case MSupplyDrop) wastes it: (1) on any attack order of 8+ armies already in
Action, where occupying doesn't drain supply anyway; (2) on the zone of armies low on supply within 1-2 zones of our
territory, which then walk home out of the zone. The drop is a zone effect (TSupplyDrop, 3 days = SD_DUR): allied
non-mech units in that zone gain 80 supply / day and lose none. It pays off only where armies stay: a far siege's
militia fight, a fight off our land, a stranded army.

- vanilla never launches it (rules/ops.py ops-block, like every military op).
- `aimod_sdrop(mil, dt)` (tick chain before raid, every SD_CHECK s), only while we hold a ready MSupplyDrop
  (MissionManager.getCompleteMissions):
  1. Locked task (map `sdlk` faction -> order, one slot): kept while the order lives (phase <= Action) and its
     target zone isn't ours; cast on the target zone (Engage or Action) only when it is needed: a non-mech order
     army within SD_CAST_R of the target is losing supply now (a fight: a plain capture / pillage doesn't drain)
     and holds no more than the walk home from the target (SUP_WALK x aimod_land + SUP_RESERVE) + SD_CAST_FIGHT
     (act cast why lock); otherwise the lock just reserves the drop. Else
     unlock (act unlock why gone / own). While it waits, a second drop held (sdrop-buy allows one) goes on to the
     emergency step, never to a second lock or the free flag.
  2. No lock: lock the newest Military siege order (structure target, Preparation .. Action) off our zone with a
     non-mech army arriving below max(RAID_ARRIVE, the walk home from the target: SUP_U x aimod_land + SUP_RESERVE)
     (arrival = supply - SUP_U x distance): the far task the drop is for (act lock).
  3. No task: emergency, the strongest non-mech army off our zone >= SD_EMERG_LAND from our land, short for the
     walk home (aimod_supok k 1), with no drop of ours there yet (map `sdz` zone -> expiry), that stays in its zone:
     fighting in place (not moving: a chase leaves the zone) with our side >= SD_WIN x the threat within LOCAL (a
     relief at our occupation: vanilla's 8-army
     occupation case was right that those fights run long), or standing with supply < SD_EMERG (act cast why emerg).
     Under the drop the army isn't losing supply, so `short` / recall / the retreat's supply penalty leave it. Nothing cast: map `sdfree` faction ->
     now, read by aimod_raidsup: a raid may then arrive with SUP_RESERVE instead of RAID_ARRIVE (the drop covers its
     militia fight, and its refill SD_REFILL counts toward the walk home); its order is locked by step 2 on the
     next pass.
- `sdrop-trip`: the supply read in vanilla's siege supply check (AIOrders.hx:1943: InsufficientSupply when the path
  cost > SD_VAN_K x the lowest army supply; closure found by its estimateSupplyCost call) -> wrapper: for a non-mech
  army whose order holds our lock, or (then locking it: act lock why trip) whose faction holds a free drop and whose
  target lies beyond vanilla's reach (zones from our territory > maxSupplyDistZones: reached through SD_ZONES), it reads
  (supply - SUP_RESERVE) / SD_VAN_K: the trip may spend all but the reserve, the drop at the target covers the fight
  and refills for the way home.
Cast = `AbilityManager.canUseAbilityOn` / `useAbilityOn("SupplyDrop", {src: DisplayTarget.Spying(fac), zone})` as
vanilla's case. Fails safe: in a trap."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.opsbrain import ops_scores

ENGAGE = 4  # AIOrder.phase Engage (common: REGROUP 3, ACTION 5)
PREP = 2    # AIOrder.phase Preparation


def build_sdrop(cx, helpers, pw, land, supok, own, threat):
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    _tick(fb, b, cx, t, SD_CHECK, 'end')
    zi, zero, one_f = b.const('i32', 0), b.const('f64', 0), b.const('f64', 1)
    # a ready Supply Drop held?
    mm = b.call('ent.Faction.get_missionManager', fac)
    fb.op('JNull', reg=mm, offset='end')
    gcm = cx.fn('logic.faction.MissionManager.getCompleteMissions')
    fnull = fb.reg(cx.code.types[gcm.type.value].definition.args[1].value)
    fb.op('Null', dst=fnull)
    ops = b.call('logic.faction.MissionManager.getCompleteMissions', mm, fnull)
    fb.op('JNull', reg=ops, offset='end')
    i, nd = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))  # nd = ready drops held (the buy gate allows a 2nd while locked)
    sdop = fb.dyn(fb.string(SD_OP))
    fb.op('Mov', dst=i, src=zi)
    fb.op('Mov', dst=nd, src=zi)
    b.loop_head('op')
    fb.op('JSGte', a=i, b=b.field(ops, 'length'), offset='opdone')
    m = b.cast(b.call('hl.types.ArrayObj.getDyn', ops, i), 'logic.faction.Mission')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=m, offset='op')
    mid = b.field(m, 'id')
    fb.op('JNull', reg=mid, offset='op')
    fb.op('JNotEq', a=b.call('String.__compare', mid, sdop), b=zi, offset='op')
    fb.op('JTrue', cond=b.field(m, 'hasBeenUsed'), offset='op')
    fb.op('Incr', dst=nd)
    fb.op('JAlways', offset='op')
    fb.label('opdone')
    fb.op('JSLte', a=nd, b=zi, offset='nodrop')  # none held

    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    lk, sdz = _global_map(fb, b, cx, 'sdlk'), _global_map(fb, b, cx, 'sdz')
    ve = fb.reg(cx.t('ent.Entity'))
    s = fb.reg(cx.t('ent.Structure'))
    z = fb.reg(cx.t('ent.Zone'))
    ph = fb.reg(cx.t('i32'))
    d, q = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    o = fb.reg(cx.t('logic.ai.AIOrder'))
    k = fb.reg(cx.t('i32'))
    ae = fb.reg(cx.t('ent.Entity'))

    # the cast (vanilla's case: useAbilityOn(ability id, {src: Spying(f), zone}))
    cua = cx.fn('logic.faction.AbilityManager.canUseAbilityOn')
    uao = cx.fn('logic.faction.AbilityManager.useAbilityOn')
    cua_a = [a.value for a in cx.code.types[cua.type.value].definition.args]
    uao_a = [a.value for a in cx.code.types[uao.type.value].definition.args]
    dt_t = cx.t('DisplayTarget')
    dt_names = [c.name.resolve(cx.code) for c in cx.code.types[dt_t].definition.constructs]
    rt = cx.code.types[uao.type.value].definition.ret.value
    rnames = [c.name.resolve(cx.code) for c in cx.code.types[rt].definition.constructs]
    abid = fb.string('SupplyDrop')
    cres = fb.reg(rt)
    cix = fb.reg(cx.t('i32'))

    def _low(army, skip):
        """Jump to `skip` unless army's supply is at most SD_LOW of its max (user: a drop at 30-50% was wasted)."""
        lr = fb.reg(cx.t('f64'))
        ms = b.call('ent.Army.get_maxSupply', army)
        fb.op('JSLte', a=ms, b=b.const('f64', 0), offset=skip)
        fb.op('SDiv', dst=lr, a=b.call('ent.Army.get_supply', army), b=ms)
        fb.op('JSGt', a=lr, b=_ratio(fb, b, SD_LOW), offset=skip)

    def cast_drop(fail):
        """cast on zone z; falls through on success (sdz[z] = now + SD_DUR), else jumps to `fail`."""
        abm = b.call('ent.Faction.get_abilities', fac)
        fb.op('JNull', reg=abm, offset=fail)
        pdt = fb.reg(dt_t)
        fb.op('MakeEnum', dst=pdt, construct=dt_names.index('Spying'), args=[fac])
        pdo = fb.reg(cx.t('dynobj'))
        fb.op('New', dst=pdo)
        fb.op('DynSet', obj=pdo, field=cx.s('src'), src=fb.dyn(pdt))
        fb.op('DynSet', obj=pdo, field=cx.s('zone'), src=fb.dyn(z))
        ca, ua = fb.reg(cua_a[2]), fb.reg(uao_a[2])
        fb.op('ToVirtual', dst=ca, src=pdo)
        fb.op('ToVirtual', dst=ua, src=pdo)
        c3, c4, u3, u4 = fb.reg(cua_a[3]), fb.reg(cua_a[4]), fb.reg(uao_a[3]), fb.reg(uao_a[4])
        for r in (c3, c4, u3, u4):
            fb.op('Null', dst=r)
        ok = fb.reg(cx.t('bool'))
        fb.op('CallN', dst=ok, fun=cua.findex.value, args=[abm, abid, ca, c3, c4])
        fb.op('JFalse', cond=ok, offset=fail)
        fb.op('CallN', dst=cres, fun=uao.findex.value, args=[abm, abid, ua, u3, u4])
        fb.op('EnumIndex', dst=cix, value=cres)
        fb.op('JNotEq', a=cix, b=b.const('i32', rnames.index('Success')), offset=fail)
        exp = fb.reg(cx.t('f64'))
        fb.op('Add', dst=exp, a=t, b=b.const('f64', SD_DUR))
        b.call('haxe.ds.ObjectMap.set', sdz, fb.dyn(z), fb.dyn(exp))

    def struct_target(order, skip):
        """s / ve / z = the order's structure target and its zone; jump to `skip` when it has none."""
        fb.op('Mov', dst=s, src=b.cast(b.call('logic.ai.AIOrder.getTarget', order), 'ent.Structure'))
        fb.op('JNull', reg=s, offset=skip)
        fb.op('Mov', dst=ve, src=s)
        fb.op('Mov', dst=z, src=b.call('ent.Entity.get_zone', ve))
        fb.op('JNull', reg=z, offset=skip)

    # 1. the locked task
    cur = b.call('haxe.ds.ObjectMap.get', lk, fb.dyn(fac))
    fb.op('JNull', reg=cur, offset='nolock')
    fb.op('Mov', dst=o, src=b.cast(cur, 'logic.ai.AIOrder'))
    fb.op('JNull', reg=o, offset='un_gone')
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', orders, fb.dyn(o)), offset='un_gone')
    fb.op('Mov', dst=ph, src=b.field(o, 'phase'))
    fb.op('JSGt', a=ph, b=b.const('i32', ACTION), offset='un_gone')
    struct_target(o, 'un_gone')
    fb.op('JEq', a=b.field(z, 'owner'), b=fac, offset='un_own')
    # Engage / Action: the lock reserves the drop, the cast waits for the need. An order army at the target that is
    # losing supply now (a fight; a plain occupation doesn't drain) with no more than the walk home from the target
    # (SUP_WALK x aimod_land + SUP_RESERVE) + SD_CAST_FIGHT left. Harkonnen cast at Harnun at 125-135 of 225 with
    # ~100 needed for the way home (lock 3 s after Action, order cancelled 43 s later).
    fb.op('JSLt', a=ph, b=b.const('i32', ENGAGE), offset='lk_hold')  # still gathering / walking: hold it
    cneed = fb.reg(cx.t('f64'))
    fb.op('Call2', dst=cneed, fun=land, arg0=fac, arg1=ve)
    fb.op('Mul', dst=cneed, a=cneed, b=_ratio(fb, b, SUP_WALK))
    fb.op('Add', dst=cneed, a=cneed, b=_ratio(fb, b, SUP_RESERVE + SD_CAST_FIGHT))
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='lk_hold')
    a = _army_loop(fb, b, units, b.field(units, 'length'), k, 'lka', 'lk_hold')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', a, ve), b=b.const('f64', SD_CAST_R), offset='lka')
    fb.op('JTrue', cond=b.call('ent.Unit.isMechanical', a), offset='lka')
    fb.op('JFalse', cond=b.call('ent.Army.isLosingSupply', a), offset='lka')
    fb.op('JSGt', a=b.call('ent.Army.get_supply', a), b=cneed, offset='lka')
    _low(a, 'lka')
    fb.label('lk_cast')
    cast_drop('lk_fail')
    b.call('haxe.ds.ObjectMap.remove', lk, fb.dyn(fac))
    _log_ev(fb, b, cx, helpers, 'sdrop', [('f', fb.get(fac, 'kind')), ('act', 'cast'), ('why', 'lock'), ('tgt', ve),
                                          ('sa', fb.get(o, 'siegeAction')), ('a', a),
                                          ('sup', b.call('ent.Army.get_supply', a)),
                                          ('ms', b.call('ent.Army.get_maxSupply', a))])
    fb.op('JAlways', offset='end')
    fb.label('lk_fail')
    _throttle(fb, b, cx, 'sdfail', fac, 30, 'lk_hold')
    _log_ev(fb, b, cx, helpers, 'sdrop', [('f', fb.get(fac, 'kind')), ('act', 'fail'), ('why', 'lock'), ('tgt', ve)])
    # the lock waits: a second drop held serves emergencies (never a second far task: one lock slot)
    fb.label('lk_hold')
    fb.op('JSGte', a=nd, b=b.const('i32', 2), offset='emerg')
    fb.op('JAlways', offset='end')
    for why in ('gone', 'own'):
        fb.label('un_' + why)
        b.call('haxe.ds.ObjectMap.remove', lk, fb.dyn(fac))
        _log_ev(fb, b, cx, helpers, 'sdrop', [('f', fb.get(fac, 'kind')), ('act', 'unlock'), ('why', why)])
        fb.op('JAlways', offset='nolock')

    # 2. lock a far task: a siege order whose armies arrive short for the militia fight
    fb.label('nolock')
    fb.op('Mov', dst=k, src=b.field(orders, 'length'))
    ix = fb.reg(cx.t('i32'))
    j = fb.reg(cx.t('i32'))
    arrive, su = fb.reg(cx.t('f64')), _ratio(fb, b, SUP_U)
    ra = _ratio(fb, b, RAID_ARRIVE)
    b.loop_head('lo')
    fb.op('JSLte', a=k, b=zi, offset='emerg')
    fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
    fb.op('Mov', dst=o, src=b.cast(b.call('hl.types.ArrayObj.getDyn', orders, k), 'logic.ai.AIOrder'))
    fb.op('JNull', reg=o, offset='lo')
    fb.op('EnumIndex', dst=ix, value=b.field(o, 'type'))
    fb.op('JNotEq', a=ix, b=b.const('i32', MILITARY), offset='lo')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='lo')
    fb.op('EnumIndex', dst=ix, value=tt)
    fb.op('JNotEq', a=ix, b=b.const('i32', T_STRUCT), offset='lo')
    fb.op('Mov', dst=ph, src=b.field(o, 'phase'))
    fb.op('JSLt', a=ph, b=b.const('i32', PREP), offset='lo')
    fb.op('JSGt', a=ph, b=b.const('i32', ACTION), offset='lo')
    struct_target(o, 'lo')
    fb.op('JEq', a=b.field(z, 'owner'), b=fac, offset='lo')
    # need = what an army must still hold at the target: the militia fight (RAID_ARRIVE) and the walk home from it
    tneed = fb.reg(cx.t('f64'))
    fb.op('Call2', dst=tneed, fun=land, arg0=fac, arg1=ve)
    fb.op('Mul', dst=tneed, a=tneed, b=su)
    fb.op('Add', dst=tneed, a=tneed, b=_ratio(fb, b, SUP_RESERVE))
    fb.op('JSGte', a=tneed, b=ra, offset='tneed_ok')
    fb.op('Mov', dst=tneed, src=ra)
    fb.label('tneed_ok')
    lu = b.field(o, 'units')
    fb.op('JNull', reg=lu, offset='lo')
    a = _army_loop(fb, b, lu, b.field(lu, 'length'), j, 'lu', 'lo')
    fb.op('JTrue', cond=b.call('ent.Unit.isMechanical', a), offset='lu')
    fb.op('JSLte', a=b.call('ent.Army.get_maxSupply', a), b=zero, offset='lu')
    fb.op('Mul', dst=d, a=b.call('ent.Entity.getDistTo', a, ve), b=su)
    fb.op('Sub', dst=arrive, a=b.call('ent.Army.get_supply', a), b=d)
    fb.op('JSGte', a=arrive, b=tneed, offset='lu')
    b.call('haxe.ds.ObjectMap.set', lk, fb.dyn(fac), fb.dyn(o))
    _log_ev(fb, b, cx, helpers, 'sdrop', [('f', fb.get(fac, 'kind')), ('act', 'lock'), ('tgt', ve),
                                          ('sa', fb.get(o, 'siegeAction')), ('arr', arrive),
                                          ('n', b.field(lu, 'length'))])
    fb.op('JAlways', offset='end')

    # 3. emergency: the strongest stranded army that stays in its zone
    fb.label('emerg')
    my, mlen = _my_armies(fb, b, fac, 'end')
    best, p, ld, bsup, bld = (fb.reg(cx.t('f64')) for _ in range(5))
    fb.op('Mov', dst=best, src=zero)
    ba = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=ba)
    bz = fb.reg(cx.t('ent.Zone'))
    fb.op('Null', dst=bz)
    sup = fb.reg(cx.t('f64'))
    emerg, eland = _ratio(fb, b, SD_EMERG), b.const('f64', SD_EMERG_LAND)
    local, win = b.const('f64', LOCAL), _ratio(fb, b, SD_WIN)
    no_army = fb.reg(cx.t('ent.Army'))
    fb.op('Null', dst=no_army)
    a = _army_loop(fb, b, my, mlen, j, 'ea', 'eadone')
    fb.op('Mov', dst=ae, src=a)
    fb.op('JNotNull', reg=b.field(a, 'harvestComponent'), offset='ea')
    fb.op('JTrue', cond=b.call('ent.Unit.isMechanical', a), offset='ea')
    fb.op('JSLte', a=b.call('ent.Army.get_maxSupply', a), b=zero, offset='ea')
    fb.op('Mov', dst=sup, src=b.call('ent.Army.get_supply', a))
    _low(a, 'ea')
    fb.op('Call2', dst=ld, fun=land, arg0=fac, arg1=ae)
    fb.op('JSLt', a=ld, b=eland, offset='ea')
    sok = fb.reg(cx.t('bool'))
    fb.op('Call3', dst=sok, fun=supok, arg0=a, arg1=ld, arg2=one_f)
    fb.op('JTrue', cond=sok, offset='ea')  # can still walk home
    za = b.call('ent.Entity.get_zone', ae)
    fb.op('JNull', reg=za, offset='ea')
    fb.op('JEq', a=b.field(za, 'owner'), b=fac, offset='ea')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', ae), offset='efight')
    fb.op('JTrue', cond=b.call('ent.Unit.isMoving', a), offset='ea')  # walking out: a drop here is wasted
    fb.op('JSGte', a=sup, b=emerg, offset='ea')  # standing: only near empty
    fb.op('JAlways', offset='estay')
    # fighting (a relief at our occupation, a long field fight): as soon as it is short, if our side holds; the drop
    # stops the drain, so `short` (Army.isLosingSupply) clears and no recall / supply penalty pulls it out
    fb.label('efight')
    fb.op('JTrue', cond=b.call('ent.Unit.isMoving', a), offset='ea')  # a chase leaves the zone: wasted there
    fb.op('CallN', dst=q, fun=own, args=[fac, ae, local, no_army])
    fb.op('Call3', dst=d, fun=threat, arg0=fac, arg1=ae, arg2=local)
    fb.op('Mul', dst=d, a=d, b=win)
    fb.op('JSLt', a=q, b=d, offset='ea')  # losing: the fight retreat decides
    fb.label('estay')
    exp = b.call('haxe.ds.ObjectMap.get', sdz, fb.dyn(za))
    fb.op('JNull', reg=exp, offset='enew')
    fb.op('SafeCast', dst=q, src=exp)
    fb.op('JSGt', a=q, b=t, offset='ea')  # our drop already there
    fb.label('enew')
    fb.op('Call1', dst=p, fun=pw, arg0=a)
    fb.op('JSLte', a=p, b=best, offset='ea')
    fb.op('Mov', dst=best, src=p)
    fb.op('Mov', dst=ba, src=ae)
    fb.op('Mov', dst=bz, src=za)
    fb.op('Mov', dst=bsup, src=sup)
    fb.op('Mov', dst=bld, src=ld)
    fb.op('JAlways', offset='ea')
    fb.label('eadone')
    fb.op('JNull', reg=ba, offset='free')
    fb.op('Mov', dst=z, src=bz)
    cast_drop('e_fail')
    _log_ev(fb, b, cx, helpers, 'sdrop', [('f', fb.get(fac, 'kind')), ('act', 'cast'), ('why', 'emerg'), ('a', ba),
                                          ('sup', bsup), ('land', bld), ('pw', best)])
    fb.op('JAlways', offset='end')
    fb.label('e_fail')
    _throttle(fb, b, cx, 'sdfail', fac, 30, 'free')
    _log_ev(fb, b, cx, helpers, 'sdrop', [('f', fb.get(fac, 'kind')), ('act', 'fail'), ('why', 'emerg'), ('a', ba)])
    # a free drop: raids may count on it (aimod_raidsup)
    fb.label('free')
    fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', lk, fb.dyn(fac)), offset='end')  # a 2nd drop: emergencies only
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'sdfree'), fb.dyn(fac), fb.dyn(t))
    fb.op('JAlways', offset='end')
    fb.label('nodrop')  # used or never bought: no lock may outlive it (it would block the next drop's trip)
    b.call('haxe.ds.ObjectMap.remove', _global_map(fb, b, cx, 'sdlk'), fb.dyn(fac))
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


def build_sdrop_trip(cx, helpers, new_ids):
    """Wrap the supply read of vanilla's siege supply check (see module doc)."""
    est = cx.fn('logic.ai.AIOrders.estimateSupplyCost').findex.value
    gs = cx.fn('ent.Army.get_supply')
    floats = cx.code.floats

    def fval(op):
        try:
            return floats[op.df['ptr'].value].value
        except Exception:
            return None

    sites = []
    for f in cx.code.functions:
        if not any(op.op.startswith('Call') and op.df.get('fun') is not None and op.df['fun'].value == est
                   for op in f.ops):
            continue
        for n, op in enumerate(f.ops):
            if op.op != 'Call1' or op.df['fun'].value != gs.findex.value:
                continue
            dst = op.df['dst'].value
            nxt = f.ops[n + 1:n + 6]
            k = [x for x in nxt if x.op == 'Float' and fval(x) is not None and abs(fval(x) - SD_VAN_K) < 1e-9]
            if k and any(x.op == 'Mul' and dst in (x.df['a'].value, x.df['b'].value) for x in nxt):
                sites.append(op)
    if len(sites) != 1:
        raise ValueError(f'sdrop-trip: expected 1 supply x {SD_VAN_K} read next to estimateSupplyCost, found {len(sites)}')
    fb = FB(cx, [cx.t('ent.Army')], cx.t('f64'))
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Call1', dst=res, fun=gs.findex.value, arg0=0)  # vanilla, outside any trap
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fb.op('JTrue', cond=b.call('ent.Unit.isMechanical', 0), offset='end')  # the drop feeds non-mech units only
    ae = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ae, src=0)
    own = b.call('ent.Entity.get_owner', ae)
    fb.op('JNull', reg=own, offset='end')
    lk, free = _global_map(fb, b, cx, 'sdlk'), _global_map(fb, b, cx, 'sdfree')
    ordr = fb.reg(cx.t('logic.ai.AIOrder'))
    _order_of(fb, b, cx, own, ae, ordr, 'end')  # the order being checked (Unit.aiOrder is never maintained)
    cur = b.call('haxe.ds.ObjectMap.get', lk, fb.dyn(own))
    fb.op('JNull', reg=cur, offset='chkfree')
    fb.op('JNull', reg=ordr, offset='end')
    fb.op('JEq', a=b.cast(cur, 'logic.ai.AIOrder'), b=ordr, offset='bypass')  # another army of the locked trip
    fb.op('JAlways', offset='end')  # the drop is locked to another task
    fb.label('chkfree')
    seen = b.call('haxe.ds.ObjectMap.get', free, fb.dyn(own))
    fb.op('JNull', reg=seen, offset='end')
    ts = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=ts, src=seen)
    fb.op('Sub', dst=ts, a=b.field(_state(fb, b, cx), 'time'), b=ts)
    fb.op('JSGt', a=ts, b=b.const('f64', SD_FRESH), offset='end')
    # only a trip beyond vanilla's own reach needs it (near orders keep the normal check and leave the drop free)
    fb.op('JNull', reg=ordr, offset='end')
    tz = b.call('ent.Entity.get_zone', b.call('logic.ai.AIOrder.getTarget', ordr))
    fb.op('JNull', reg=tz, offset='end')
    mil = b.field(b.field(own, 'aiController'), 'aiMilitary')
    fb.op('JNull', reg=mil, offset='end')
    gd = cx.fn('ent.Zone.getDistanceToPlayerTerritory')
    gdt = [x.value for x in cx.code.types[gd.type.value].definition.args]
    pf, tr = fb.reg(gdt[1]), fb.reg(gdt[2])
    fb.op('Mov', dst=pf, src=own)
    _box_true(fb, cx, tr)  # considerAirfields is Null<Bool>: box it (a raw Bool there threw in the trap)
    zd = fb.reg(cx.t('i32'))
    fb.op('Call3', dst=zd, fun=gd.findex.value, arg0=tz, arg1=pf, arg2=tr)
    fb.op('JSLte', a=zd, b=b.field(mil, 'maxSupplyDistZones'), offset='end')
    b.call('haxe.ds.ObjectMap.remove', free, fb.dyn(own))  # one drop, one trip
    b.call('haxe.ds.ObjectMap.set', lk, fb.dyn(own), fb.dyn(ordr))
    _log_ev(fb, b, cx, helpers, 'sdrop', [('f', fb.get(own, 'kind')), ('act', 'lock'), ('why', 'trip'), ('a', ae),
                                          ('tgt', b.call('logic.ai.AIOrder.getTarget', ordr)), ('sup', res)])
    fb.label('bypass')
    q = fb.reg(cx.t('f64'))
    fb.op('Sub', dst=q, a=res, b=_ratio(fb, b, SUP_RESERVE))
    fb.op('SDiv', dst=q, a=q, b=_ratio(fb, b, SD_VAN_K))
    fb.op('JSLte', a=q, b=res, offset='end')  # never less than vanilla's own read
    fb.op('Mov', dst=res, src=q)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    for op in sites:
        op.df['fun'].value = w
    return {'sdrop-trip': len(sites)}


def build_sdrop_buy(cx, helpers, new_ids):
    """Wrap checkMissions' $HScoring.spyingMissions call: while we hold or prepare an unlocked Supply Drop, the score map
    loses MSupplyDrop (vanilla buys by a weighted random pick among the top scores with only a short per-mission
    cooldown: weighted 5 for every AI type and most ops 0, it could fill every operation slot with drops). One more
    may be bought while the held one is locked to a task (emergencies keep a drop). Log `sdrop` act nobuy (120 s)."""
    orig = cx.fn('logic.ai.$HScoring.spyingMissions')
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    if len(args) != 2 or args[1] != cx.t('ent.Faction') or ft.ret.value != cx.t('haxe.ds.StringMap'):
        raise ValueError('sdrop-buy: spyingMissions(missions, faction) -> StringMap expected')
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('Call2', dst=res, fun=orig.findex.value, arg0=0, arg1=1)  # vanilla, outside any trap
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    fb.op('JNull', reg=1, offset='end')
    ops_scores(fb, b, cx, res, 1)  # rules/opsbrain.py: loadout rank scores
    mm = b.call('ent.Faction.get_missionManager', 1)
    fb.op('JNull', reg=mm, offset='end')
    n = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=n, src=b.const('i32', 0))
    sdop = fb.dyn(fb.string(SD_OP))
    for k, getter in enumerate(('getStartedMissions', 'getCompleteMissions')):
        gf = cx.fn('logic.faction.MissionManager.' + getter)
        fn_ = fb.reg(cx.code.types[gf.type.value].definition.args[1].value)
        fb.op('Null', dst=fn_)
        lst = b.call('logic.faction.MissionManager.' + getter, mm, fn_)
        nxt = f'bl{k}d'
        fb.op('JNull', reg=lst, offset=nxt)
        i = fb.reg(cx.t('i32'))
        fb.op('Mov', dst=i, src=b.const('i32', 0))
        b.loop_head(f'bl{k}')
        fb.op('JSGte', a=i, b=b.field(lst, 'length'), offset=nxt)
        m = b.cast(b.call('hl.types.ArrayObj.getDyn', lst, i), 'logic.faction.Mission')
        fb.op('Incr', dst=i)
        fb.op('JNull', reg=m, offset=f'bl{k}')
        mid = b.field(m, 'id')
        fb.op('JNull', reg=mid, offset=f'bl{k}')
        fb.op('JNotEq', a=b.call('String.__compare', mid, sdop), b=b.const('i32', 0), offset=f'bl{k}')
        fb.op('JTrue', cond=b.field(m, 'hasBeenUsed'), offset=f'bl{k}')
        fb.op('Incr', dst=n)
        fb.op('JAlways', offset=f'bl{k}')
        fb.label(nxt)
    fb.op('JNull', reg=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'sdlk'), fb.dyn(1)), offset='nolk')
    fb.op('Sub', dst=n, a=n, b=b.const('i32', 1))  # the locked one is spoken for
    fb.label('nolk')
    fb.op('JSLte', a=n, b=b.const('i32', 0), offset='end')
    fb.op('JFalse', cond=b.call('haxe.ds.StringMap.remove', res, fb.string(SD_OP)), offset='end')
    _throttle(fb, b, cx, 'sdnobuy', 1, 120, 'end')
    _log_ev(fb, b, cx, helpers, 'sdrop', [('f', fb.get(1, 'kind')), ('act', 'nobuy'), ('n', n)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    caller = cx.fn('logic.ai.Spying.checkMissions')
    sites = [op for op in caller.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == orig.findex.value]
    if len(sites) != 1:
        raise ValueError(f'sdrop-buy: expected 1 spyingMissions call in checkMissions, found {len(sites)}')
    for op in sites:
        op.df['fun'].value = w
    return {'sdrop-buy': len(sites)}
