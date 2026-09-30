"""Healing and fight retreat: retreat-terrain (fight retreat balance x terrain x supply) and safe-heal (healing
structure choice with threat penalties)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def build_mission(cx):
    """aimod_mission(fac, a) -> a is a unit of one of fac's Military orders (siege, hunt, raid, defense). Army.aiOrder
    is unreliable (null on many AI besiegers and on our hunts), so the order list is scanned."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Army')], cx.t('bool'))
    b = B(fb)
    res = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=res, value=False)
    guard = fb.try_()
    ctrl = b.field(0, 'aiController')
    fb.op('JNull', reg=ctrl, offset='end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    on = b.field(orders, 'length')
    k, idx = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Int', dst=k, ptr=cx.code.add_i32(0).value)
    b.loop_head('o')
    fb.op('JSGte', a=k, b=on, offset='end')
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, k), 'logic.ai.AIOrder')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=o, offset='o')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='o')
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='o')
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', units, fb.dyn(1)), offset='o')
    fb.op('Bool', dst=res, value=True)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    return fb.build()


def build_retreat(cx, terrain, new_ids, helpers, pw, short, mission, land):
    """Fight retreat (unitMicroManagement: retreat when HAI.getWarzonePowerBalance <= RetreatRatio): both calls go
    through a wrapper returning balance * aimod_terrain(faction, zone at the warzone centroid) * supply factor.
    Own land: hold to ~0.5 (we heal there); enemy land: leave below ~0.8; open field: RETREAT. Supply factor =
    1 - SUP_PEN * (power of our armies within FLEE_R of the centroid that are `short`) / (all of ours there): a
    starving army leaves a fight it isn't clearly winning, and vanilla's retreat then cancels its orders, sends
    Resupply and force-flees it (the only vanilla path that pulls armies out of a fight; a plain Resupply order
    stalls in Regroup while micro keeps attacking). Original value on any error.
    Vanilla returns exactly 1.0 when the warzone holds no enemy power (HPowerScore.compute), e.g. only a neutral
    unit or a structure left: that value passes unchanged (x terrain x supply made it 0.64 and a winning stack left
    an enemy village it could pillage).
    Recall: when every one of our armies in the warzone is `short` and none is in a Military order (its hunt / siege
    ended, e.g. hunt abort `supply` -> Resupply), the balance is 0: vanilla force-flees them home. Otherwise micro keeps
    attacking whatever is in reach, and a winning stack pursues a fleeing enemy deep into its land (Atreides chased
    fleeing Smugglers ~170 past Huldad to Sin-Al'no for 40 s after the supply abort, all 5 armies starved to 0). A
    starving army that isn't on a mission has nothing to win.
    Stranded: a short army whose supply can't pay the walk to our land (< SUP_WALK x aimod_land) counts as not short
    (no supply penalty, no recall): fleeing would starve it on the way and get it shot in the back, so the plain
    terrain-adjusted balance decides and a fight it is winning is finished (log act `stranded` when that held it).
    Pursuit: the at-war power within CONTACT of the centroid lost less than PROGRESS in PURSUIT_T s (per warzone,
    measured all the time), none of our armies there is on a Military order and the fight is off our zone: balance
    0. Micro follows a fleeing army at our own speed forever."""
    orig = cx.fn('$HAI.getWarzonePowerBalance')
    args = [a.value for a in cx.code.types[orig.type.value].definition.args]
    fb = FB(cx, args, cx.t('f64'), fun_type=orig.type.value)
    b = B(fb)
    bal, raw = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Call3', dst=bal, fun=orig.findex.value, arg0=0, arg1=1, arg2=2)
    fb.op('Mov', dst=raw, src=bal)
    sf = b.const('f64', 1)
    guard = fb.try_()
    fb.op('JEq', a=raw, b=b.const('f64', 1), offset='end')  # no enemy power in the warzone
    fb.op('JNull', reg=0, offset='end')
    c = b.call('logic.state.Warzone.get_centroid', 0)
    fb.op('JNull', reg=c, offset='end')
    gs = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gs, **{'global': cx.global_of('$Game')})
    world = b.field(b.field(gs, 'inst'), 'world')
    fb.op('JNull', reg=world, offset='end')
    cxp, cyp = b.field(c, 'x'), b.field(c, 'y')
    z = b.call('world.World.getZoneAt', world, cxp, cyp)
    t = fb.reg(cx.t('f64'))
    fb.op('Call2', dst=t, fun=terrain, arg0=1, arg1=z)
    fb.op('Mul', dst=bal, a=bal, b=t)
    # supply factor over our armies in the warzone (same radius as vanilla's balance)
    tot, st, p, dx, dy = (fb.reg(cx.t('f64')) for _ in range(5))
    zero = b.const('f64', 0)
    fb.op('Mov', dst=tot, src=zero)
    fb.op('Mov', dst=st, src=zero)
    dm = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=dm, src=zero)
    ent_r, need = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('f64'))
    walk = _ratio(fb, b, SUP_WALK)
    r2 = b.const('f64', FLEE_R * FLEE_R)
    i, ok = fb.reg(cx.t('i32')), fb.reg(cx.t('bool'))
    arr, alen = _my_armies(fb, b, 1, 'sfdone')
    a = _army_loop(fb, b, arr, alen, i, 'sfl', 'sfdone')
    fb.op('Sub', dst=dx, a=b.field(a, 'posx'), b=cxp)
    fb.op('Sub', dst=dy, a=b.field(a, 'posy'), b=cyp)
    fb.op('Mul', dst=dx, a=dx, b=dx)
    fb.op('Mul', dst=dy, a=dy, b=dy)
    fb.op('Add', dst=dx, a=dx, b=dy)
    fb.op('JSGt', a=dx, b=r2, offset='sfl')
    fb.op('Call1', dst=p, fun=pw, arg0=a)
    fb.op('Add', dst=tot, a=tot, b=p)
    fb.op('Call2', dst=ok, fun=short, arg0=1, arg1=a)
    fb.op('JFalse', cond=ok, offset='sfl')
    # stranded: can't pay the walk home anyway -> not counted as short
    fb.op('Mov', dst=ent_r, src=a)
    fb.op('Call2', dst=need, fun=land, arg0=1, arg1=ent_r)
    fb.op('Mul', dst=need, a=need, b=walk)
    fb.op('JSGte', a=b.call('ent.Army.get_supply', a), b=need, offset='notstr')
    fb.op('Add', dst=dm, a=dm, b=p)
    fb.op('JAlways', offset='sfl')
    fb.label('notstr')
    fb.op('Add', dst=st, a=st, b=p)
    fb.op('JAlways', offset='sfl')
    fb.label('sfdone')
    fb.op('JSLte', a=tot, b=zero, offset='sfend')
    # recall: all short and none on a mission
    fb.op('JSLt', a=st, b=tot, offset='share')
    arr2, alen2 = _my_armies(fb, b, 1, 'share')
    i2 = fb.reg(cx.t('i32'))
    a2 = _army_loop(fb, b, arr2, alen2, i2, 'rcl', 'recall')
    fb.op('Sub', dst=dx, a=b.field(a2, 'posx'), b=cxp)
    fb.op('Sub', dst=dy, a=b.field(a2, 'posy'), b=cyp)
    fb.op('Mul', dst=dx, a=dx, b=dx)
    fb.op('Mul', dst=dy, a=dy, b=dy)
    fb.op('Add', dst=dx, a=dx, b=dy)
    fb.op('JSGt', a=dx, b=r2, offset='rcl')
    fb.op('Call2', dst=ok, fun=mission, arg0=1, arg1=a2)
    fb.op('JTrue', cond=ok, offset='share')
    fb.op('JAlways', offset='rcl')
    fb.label('recall')
    fb.op('Mov', dst=sf, src=zero)
    fb.op('Mov', dst=bal, src=zero)
    fb.op('JAlways', offset='sfend')
    fb.label('share')
    fb.op('SDiv', dst=p, a=st, b=tot)
    fb.op('Mul', dst=p, a=p, b=_ratio(fb, b, SUP_PEN))
    fb.op('Sub', dst=sf, a=sf, b=p)
    fb.op('Mul', dst=bal, a=bal, b=sf)
    fb.label('sfend')
    r = _ratio(fb, b, RETREAT)
    # pursuit: the enemy within CONTACT of the fight loses less than PROGRESS of its power in PURSUIT_T s = we chase an
    # army as fast as we are. Measured per warzone all the time (so the clock keeps running when a hunt ends); acted
    # on only when none of our armies there is on a mission (Military order: its own aborts decide) and the fight is
    # off our land (at home a fleeing intruder costs nothing to follow): balance 0, vanilla's retreat pulls them out
    # (a Resupply order can't). Smugglers followed an unhurt F_Trooper ~100 south from Larram under Grimpo's turret
    # for 14 s after their hunt ended
    purs = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=purs, value=False)
    en = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=en, src=zero)
    state = _state(fb, b, cx)
    now = b.field(state, 'time')
    all_a = b.field(state, 'armies')
    alen4 = b.field(all_a, 'length')
    i4 = fb.reg(cx.t('i32'))
    c2 = b.const('f64', CONTACT * CONTACT)
    x4 = _army_loop(fb, b, all_a, alen4, i4, 'pen', 'pendone')
    xo = b.call('ent.Entity.get_owner', x4)
    fb.op('JNotNull', reg=xo, offset='powned')
    rd = b.field(x4, 'raid')  # a neutral raider counts only when it raids us
    fb.op('JNull', reg=rd, offset='pen')
    fb.op('JNotEq', a=b.field(rd, 'targetFaction'), b=1, offset='pen')
    fb.op('JAlways', offset='phost')
    fb.label('powned')
    fb.op('JEq', a=xo, b=1, offset='pen')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, 1, xo), offset='pen')
    fb.label('phost')
    fb.op('Sub', dst=dx, a=b.field(x4, 'posx'), b=cxp)
    fb.op('Sub', dst=dy, a=b.field(x4, 'posy'), b=cyp)
    fb.op('Mul', dst=dx, a=dx, b=dx)
    fb.op('Mul', dst=dy, a=dy, b=dy)
    fb.op('Add', dst=dx, a=dx, b=dy)
    fb.op('JSGt', a=dx, b=c2, offset='pen')
    fb.op('Call1', dst=p, fun=pw, arg0=x4)
    fb.op('Add', dst=en, a=en, b=p)
    fb.op('JAlways', offset='pen')
    fb.label('pendone')
    fb.op('JSLte', a=en, b=zero, offset='pdone')
    pt_map, pp_map, ps_map = (_global_map(fb, b, cx, n) for n in ('pst', 'psp', 'psl'))
    lt, lp, q, ls = (fb.reg(cx.t('f64')) for _ in range(4))
    # stale: this warzone wasn't evaluated for a while (an earlier fight with the same object)
    seen = b.call('haxe.ds.ObjectMap.get', ps_map, fb.dyn(0))
    b.call('haxe.ds.ObjectMap.set', ps_map, fb.dyn(0), fb.dyn(now))
    fb.op('JNull', reg=seen, offset='prec')
    fb.op('SafeCast', dst=ls, src=seen)
    fb.op('Sub', dst=ls, a=now, b=ls)
    fb.op('JSGt', a=ls, b=b.const('f64', PURSUIT_STALE), offset='prec')
    last = b.call('haxe.ds.ObjectMap.get', pt_map, fb.dyn(0))
    fb.op('JNull', reg=last, offset='prec')
    fb.op('SafeCast', dst=lt, src=last)
    fb.op('SafeCast', dst=lp, src=b.call('haxe.ds.ObjectMap.get', pp_map, fb.dyn(0)))
    fb.op('Sub', dst=lt, a=now, b=lt)
    fb.op('Mul', dst=q, a=lp, b=_ratio(fb, b, 1 - PROGRESS))
    fb.op('JSLte', a=en, b=q, offset='prec')  # they lost power: a fight
    fb.op('Mul', dst=q, a=lp, b=_ratio(fb, b, 1 + PROGRESS))
    fb.op('JSGte', a=en, b=q, offset='prec')  # more of them came: a new fight
    fb.op('JSLte', a=lt, b=b.const('f64', PURSUIT_T), offset='pdone')
    fb.op('JSLte', a=bal, b=r, offset='pdone')  # leaving anyway
    fb.op('JSGt', a=t, b=b.const('f64', 1), offset='pdone')  # our own zone: vanilla keeps defending it
    arr3, alen3 = _my_armies(fb, b, 1, 'pdone')
    i3 = fb.reg(cx.t('i32'))
    a3 = _army_loop(fb, b, arr3, alen3, i3, 'pms', 'pmsdone')
    fb.op('Sub', dst=dx, a=b.field(a3, 'posx'), b=cxp)
    fb.op('Sub', dst=dy, a=b.field(a3, 'posy'), b=cyp)
    fb.op('Mul', dst=dx, a=dx, b=dx)
    fb.op('Mul', dst=dy, a=dy, b=dy)
    fb.op('Add', dst=dx, a=dx, b=dy)
    fb.op('JSGt', a=dx, b=r2, offset='pms')
    fb.op('Call2', dst=ok, fun=mission, arg0=1, arg1=a3)
    fb.op('JTrue', cond=ok, offset='pdone')
    fb.op('JAlways', offset='pms')
    fb.label('pmsdone')
    fb.op('Mov', dst=bal, src=zero)
    fb.op('Bool', dst=purs, value=True)
    fb.op('JAlways', offset='pdone')
    fb.label('prec')
    b.call('haxe.ds.ObjectMap.set', pt_map, fb.dyn(0), fb.dyn(now))
    b.call('haxe.ds.ObjectMap.set', pp_map, fb.dyn(0), fb.dyn(en))
    fb.label('pdone')
    # log `retreat` when either the raw or the adjusted balance is at/below RETREAT (once per warzone per 5 s)
    fb.op('JSLte', a=raw, b=r, offset='lg')
    fb.op('JSGt', a=dm, b=zero, offset='lg')  # stranded armies present: log the hold
    fb.op('JSGt', a=bal, b=r, offset='end')
    fb.label('lg')
    _throttle(fb, b, cx, 'retreat', 0, 5, 'end')
    act = fb.reg(cx.t('String'))
    fb.op('Mov', dst=act, src=fb.string('hold'))
    fb.op('JSLte', a=dm, b=zero, offset='hold')
    fb.op('Mov', dst=act, src=fb.string('stranded'))
    fb.label('hold')
    fb.op('JSGt', a=bal, b=r, offset='act')
    fb.op('Mov', dst=act, src=fb.string('pursuit'))  # no mission, no progress
    fb.op('JTrue', cond=purs, offset='act')
    fb.op('Mov', dst=act, src=fb.string('retreat'))
    fb.op('JNotEq', a=sf, b=zero, offset='act')
    fb.op('Mov', dst=act, src=fb.string('recall'))  # all short, none on a mission
    fb.label('act')
    _log_ev(fb, b, cx, helpers, 'retreat', [('f', fb.get(1, 'kind')), ('act', act), ('raw%', raw), ('tf%', t),
                                            ('sf%', sf), ('adj%', bal), ('dm', dm), ('en', en), ('x', cxp),
                                            ('y', cyp)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=bal)
    w = fb.build()
    new_ids.add(w)
    f = cx.fn('logic.ai.AIUnits.unitMicroManagement')
    sites = [op for op in f.ops if op.df.get('fun') is not None and op.df['fun'].value == orig.findex.value]
    if len(sites) != 2:
        raise ValueError(f'retreat: expected 2 getWarzonePowerBalance calls in unitMicroManagement, found {len(sites)}')
    for op in sites:
        op.df['fun'].value = w
    return {'retreat-terrain': len(sites)}


def build_unsafe(cx, threat, own, pw, terrain):
    """aimod_unsafe(s, self, sticky) -> 0 safe, 1 contested: threat(owner, s) > own(owner, s, without self) *
    (sticky ? STICKY : 1), 2 overwhelming: threat > (own + power of self) * OVERWHELM."""
    fb = FB(cx, [cx.t('ent.Structure'), cx.t('ent.Army'), cx.t('bool')], cx.t('i32'))
    b = B(fb)
    res = fb.reg(cx.t('i32'))
    fb.op('Int', dst=res, ptr=cx.code.add_i32(0).value)
    fb.op('JNull', reg=0, offset='end')
    owner = b.call('ent.Entity.get_owner', 0)
    fb.op('JNull', reg=owner, offset='end')
    s = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=s, src=0)
    rng = b.const('f64', SAFE_R)
    h, m = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Call3', dst=h, fun=threat, arg0=owner, arg1=s, arg2=rng)
    fb.op('CallN', dst=m, fun=own, args=[owner, s, rng, 1])
    tf = fb.reg(cx.t('f64'))
    fb.op('Call2', dst=tf, fun=terrain, arg0=owner, arg1=b.call('ent.Entity.get_zone', s))
    fb.op('Mul', dst=m, a=m, b=tf)  # defending our own village: we heal and resupply there
    m2, p = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=m2, src=m)
    fb.op('JNull', reg=1, offset='noself')
    fb.op('Call1', dst=p, fun=pw, arg0=1)
    fb.op('Mul', dst=p, a=p, b=tf)
    fb.op('Add', dst=m2, a=m2, b=p)
    fb.label('noself')
    fb.op('Mul', dst=m2, a=m2, b=_ratio(fb, b, OVERWHELM))
    fb.op('JFalse', cond=2, offset='cmp')
    fb.op('Mul', dst=m, a=m, b=_ratio(fb, b, STICKY))
    fb.label('cmp')
    fb.op('JSLte', a=h, b=m, offset='end')
    fb.op('Int', dst=res, ptr=cx.code.add_i32(1).value)
    fb.op('JSLte', a=h, b=m2, offset='end')
    fb.op('Int', dst=res, ptr=cx.code.add_i32(2).value)
    fb.label('end')
    fb.op('Ret', ret=res)
    return fb.build()


def safe_heal(cx, unsafe, new_ids, threat_now, own, pw, threat, helpers):
    """Redirect the healing-structure sort closures to wrappers: key + PENALTY if the structure is unsafe."""
    report = {}
    army_t = cx.t('ent.Army')
    for caller, n_expect in (('logic.ai.AIUnits.checkUnits', 1), ('logic.ai.AIUnits.unitMicroManagement', 2)):
        f = cx.fn(caller)
        refs = []
        for op in f.ops:
            if op.op != 'InstanceClosure':
                continue
            tgt = next(g for g in cx.code.functions if g.findex.value == op.df['fun'].value)
            ft = cx.code.types[tgt.type.value].definition
            args = [a.value for a in ft.args]
            # (ctx, ent.Structure) -> F64 = a healing-structure distance key; ctx = the army, or the warzone
            if len(args) == 2 and args[1] == cx.t('ent.Structure') and ft.ret.value == cx.t('f64'):
                refs.append((op, tgt, args))
        if len(refs) != n_expect:
            raise ValueError(f'safe-heal: expected {n_expect} structure-key closures in {caller}, found {len(refs)}')
        for op, tgt, args in refs:
            fb = FB(cx, args, cx.t('f64'), fun_type=tgt.type.value)
            b = B(fb)
            d = fb.reg(cx.t('f64'))
            fb.op('Call2', dst=d, fun=tgt.findex.value, arg0=0, arg1=1)  # original key, outside any trap

            def heal_log(act, h, m, fb=fb, b=b, is_army=args[0] == army_t):
                # `heal` {act stay|flee|detour|avoid, s, a, h, m, d}: once per structure per 3 s (the sort calls
                # this key many times); detour/avoid: h/m = threat / own (+ asking army) within SAFE_R
                done = _uid('hl')
                g2 = fb.try_()
                _throttle(fb, b, cx, 'heal', 1, 3, done)
                so = b.call('ent.Entity.get_owner', 1)
                fb.op('JNull', reg=so, offset=done)
                se2 = fb.reg(cx.t('ent.Entity'))
                fb.op('Mov', dst=se2, src=1)
                if h is None:
                    h, m = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
                    rr = b.const('f64', SAFE_R)
                    fb.op('Call3', dst=h, fun=threat, arg0=so, arg1=se2, arg2=rr)
                    fb.op('CallN', dst=m, fun=own, args=[so, se2, rr, 0 if is_army else me])
                fields = [('f', fb.get(so, 'kind')), ('act', act), ('s', se2), ('h', h), ('m', m)]
                if is_army:
                    fields += [('a', 0), ('d', b.call('ent.Entity.getDistTo', 0, 1))]
                _log_ev(fb, b, cx, helpers, 'heal', fields)
                fb.label(done)
                fb.end_try(g2)
            guard = fb.try_()
            me = fb.reg(army_t)
            fb.op('Null', dst=me)
            sticky = fb.reg(cx.t('bool'))
            fb.op('Bool', dst=sticky, value=False)
            if args[0] == army_t:
                fb.op('Mov', dst=me, src=0)
                o = b.field(0, 'aiOrder')
                fb.op('JNull', reg=o, offset='ask')
                idx = fb.reg(cx.t('i32'))
                fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
                fb.op('JNotEq', a=idx, b=b.const('i32', RESUPPLY), offset='ask')
                s = fb.reg(cx.t('ent.Entity'))
                fb.op('Mov', dst=s, src=1)
                fb.op('JNotEq', a=b.call('logic.ai.AIOrder.getTarget', o), b=s, offset='ask')
                fb.op('Bool', dst=sticky, value=True)
            fb.label('ask')
            if args[0] == army_t:
                # at home: an army already at this structure stays and heals there; it leaves only when hostiles
                # are in contact range or FLEE_ETA away AND overwhelm it (last resort), not because some are around
                fb.op('JSGt', a=b.call('ent.Entity.getDistTo', 0, 1), b=b.const('f64', AT_HOME_R), offset='away')
                sown = b.call('ent.Entity.get_owner', 1)
                fb.op('JNull', reg=sown, offset='ok')
                se = fb.reg(cx.t('ent.Entity'))
                fb.op('Mov', dst=se, src=1)
                near_r = b.const('f64', FLEE_R)
                hn, mn_, pn = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
                fb.op('Call3', dst=hn, fun=threat_now, arg0=sown, arg1=se, arg2=near_r)
                fb.op('CallN', dst=mn_, fun=own, args=[sown, se, near_r, 0])
                fb.op('Call1', dst=pn, fun=pw, arg0=0)
                fb.op('Add', dst=mn_, a=mn_, b=pn)
                fb.op('Mul', dst=mn_, a=mn_, b=_ratio(fb, b, OVERWHELM * OWN_T))
                fb.op('JSLte', a=hn, b=mn_, offset='stay')
                fb.op('Add', dst=d, a=d, b=b.const('f64', PENALTY))
                heal_log('flee', hn, mn_)
                fb.op('JAlways', offset='ok')
                fb.label('stay')  # log only when hostiles are actually close
                fb.op('JSLte', a=hn, b=b.const('f64', 0), offset='ok')
                heal_log('stay', hn, mn_)
                fb.op('JAlways', offset='ok')
                fb.label('away')
            lvl = fb.reg(cx.t('i32'))
            fb.op('Call3', dst=lvl, fun=unsafe, arg0=1, arg1=me, arg2=sticky)
            fb.op('JSLte', a=lvl, b=b.const('i32', 0), offset='ok')
            fb.op('JSGt', a=lvl, b=b.const('i32', 1), offset='hard')
            fb.op('Add', dst=d, a=d, b=b.const('f64', DETOUR * DETOUR))  # contested: worth a detour, not a trek
            heal_log('detour', None, None)
            fb.op('JAlways', offset='ok')
            fb.label('hard')
            fb.op('Add', dst=d, a=d, b=b.const('f64', PENALTY))
            heal_log('avoid', None, None)
            fb.label('ok')
            fb.end_try(guard)
            fb.op('Ret', ret=d)
            w = fb.build()
            op.df['fun'].value = w
            new_ids.add(w)
        report[f'safe-heal:{caller.split(".")[-1]}'] = len(refs)
    return report
