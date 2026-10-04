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


def fix_retreat_all(cx):
    """Vanilla fight retreat (unitMicroManagement) runs only when every unit of every order related to the fight
    stands in that warzone: `for (order in cf.relatedOrders) for (u in order.units) if (!units.contains(u))
    checkPower = false`. One straggler, a worm-held army on rock or an order army elsewhere switched the retreat off
    for the whole fight: Harkonnen's 14-army Annex of Yawan lost 13 armies under Mar-iel / Qartnin's batteries (no
    balance read 29:33-30:57), Smugglers' 5-army harvester hunt (-100%) and Harkonnen's 2-army rebel hunt (-100% at
    12.9:1) all died with no `wzb` sample. In place, same size: that `Mov checkPower <- false` becomes `Mov x <- x`,
    so checkPower is vanilla's fight-age test alone (AI_Fight time >= valueCache[1104], 5 s). A lost fight then
    retreats and cancels its related orders, stragglers included (policy: no trickling in)."""
    f = cx.fn('logic.ai.AIUnits.unitMicroManagement')
    cont = cx.fn('hl.types.ArrayObj.contains').findex.value
    ops = f.ops
    hits = []
    for i in range(3, len(ops)):
        m, bo, jt, ca = ops[i], ops[i - 1], ops[i - 2], ops[i - 3]
        if (m.op == 'Mov' and bo.op == 'Bool' and bo.df['value'].value is False
                and bo.df['dst'].value == m.df['src'].value and jt.op == 'JTrue'
                and ca.op == 'Call2' and ca.df['fun'].value == cont):
            hits.append(i)
    if len(hits) != 1:
        raise ValueError(f'retreat-all: expected 1 contains / Bool false / Mov in unitMicroManagement, found {len(hits)}')
    i = hits[0]
    r = ops[i].df['dst'].value
    # the flag must be the one tested right before the warzone balance read (JFalse r; Bool; Ref; Call3)
    if not any(ops[k].op == 'JFalse' and ops[k].df['cond'].value == r and ops[k + 3].op == 'Call3'
               for k in range(i, min(i + 120, len(ops) - 3))):
        raise ValueError('retreat-all: the cleared flag is not the balance check guard')
    ops[i].df['dst'].value = ops[i].df['src'].value
    return {'retreat-all': f'op{i} Mov r{r} <- false -> no-op'}


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
    an enemy village it could pillage), except disengage: one of our armies there has a Resupply order and none a
    Military one -> 0 (log act `disengage`).
    Recall: when every one of our armies in the warzone is `short` and none is in a Military order (its hunt / siege
    ended, e.g. hunt abort `supply` -> Resupply), the balance is 0: vanilla force-flees them home. Otherwise micro keeps
    attacking whatever is in reach, and a winning stack pursues a fleeing enemy deep into its land (Atreides chased
    fleeing Smugglers ~170 past Huldad to Sin-Al'no for 40 s after the supply abort, all 5 armies starved to 0). A
    starving army that isn't on a mission has nothing to win.
    Stranded: a short army whose supply can't pay the walk to our land (< SUP_WALK x aimod_land) counts as not short
    (no supply penalty, no recall): fleeing would starve it on the way and get it shot in the back, so the plain
    terrain-adjusted balance decides and a fight it is winning is finished (log act `stranded` when that held it).
    Doomed: a stranded army whose dry stretch home (aimod_land - supply / SUP_WALK) >= DRY_DEATH_D x its health ratio
    would die walking (0 supply costs up to its whole health per day); when doomed armies hold DOOM_SHARE of our power
    in the fight, the balance is at least DOOM_HOLD: they fight it out (log act `doomed`; user: a far task whose drop
    ran out must not turn back into death). Trivial / pursuit still end a fight with nothing to win.
    Pursuit: the at-war power within CONTACT of the centroid lost less than PROGRESS in PURSUIT_T s (per warzone,
    measured all the time), none of our armies there is on a Military order and the fight is off our zone: balance
    0. Micro follows a fleeing army at our own speed forever.
    Trivial: off our zone, the at-war power within CONTACT < TRIVIAL x ours within FLEE_R, none of ours there on a
    Military order: balance 0 (log act `trivial`; overrides stranded: a stack held in enemy land for a dying army
    starves under their turrets, which the balance doesn't count)."""
    orig = cx.fn('$HAI.getWarzonePowerBalance')
    args = [a.value for a in cx.code.types[orig.type.value].definition.args]
    fb = FB(cx, args, cx.t('f64'), fun_type=orig.type.value)
    b = B(fb)
    bal, raw = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Call3', dst=bal, fun=orig.findex.value, arg0=0, arg1=1, arg2=2)
    fb.op('Mov', dst=raw, src=bal)
    sf = b.const('f64', 1)
    guard = fb.try_()
    fb.op('JEq', a=raw, b=b.const('f64', 1), offset='nopow')  # no enemy power in the warzone
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
    # bold ops of ours running in this zone (Sleeper Agent / Combat Drugs, rules/opsbrain.py map `opbold`): their
    # dead spawn our sleepers, drugs add 30% damage: hold the fight (user: Harkonnen retreated from Atreides with both on)
    # the balance here (terrain-adjusted, before bold) for the fight ops (rules/opsbrain.py): maps `wzbv` / `wzbt`
    # per faction, warzone -> value / time; an op on a fight this check is leaving anyway is wasted
    b.call('haxe.ds.ObjectMap.set', _fac_map(fb, b, cx, 'wzbv', 1), fb.dyn(0), fb.dyn(bal))
    b.call('haxe.ds.ObjectMap.set', _fac_map(fb, b, cx, 'wzbt', 1), fb.dyn(0),
           fb.dyn(b.field(_state(fb, b, cx), 'time')))
    bz = _uid('bold')
    fb.op('JNull', reg=z, offset=bz)
    bv = b.call('haxe.ds.ObjectMap.get', _fac_map(fb, b, cx, 'opbold', 1), fb.dyn(z))
    fb.op('JNull', reg=bv, offset=bz)
    bq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=bq, src=bv)
    fb.op('JSLt', a=bq, b=b.field(_state(fb, b, cx), 'time'), offset=bz)
    fb.op('Mul', dst=bal, a=bal, b=_ratio(fb, b, OPS_BOLD_K))
    fb.label(bz)
    # supply factor over our armies in the warzone (same radius as vanilla's balance)
    tot, st, p, dx, dy = (fb.reg(cx.t('f64')) for _ in range(5))
    zero = b.const('f64', 0)
    fb.op('Mov', dst=tot, src=zero)
    fb.op('Mov', dst=st, src=zero)
    dm, dd, dry, dlim = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('Mov', dst=dm, src=zero)
    fb.op('Mov', dst=dd, src=zero)
    doom = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=doom, value=False)
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
    fb.op('Mov', dst=dry, src=b.call('ent.Army.get_supply', a))
    fb.op('JSGte', a=dry, b=need, offset='notstr')
    fb.op('Add', dst=dm, a=dm, b=p)
    # doomed: the stretch it would walk at 0 supply kills it (DRY_DEATH_D x its health ratio)
    fb.op('Sub', dst=dry, a=need, b=dry)
    fb.op('SDiv', dst=dry, a=dry, b=walk)
    fb.op('Mul', dst=dlim, a=b.call('ent.Entity.get_lifeRatio', a), b=b.const('f64', DRY_DEATH_D))
    fb.op('JSLt', a=dry, b=dlim, offset='sfl')
    fb.op('Add', dst=dd, a=dd, b=p)
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
    # doomed armies hold DOOM_SHARE of our power here: no retreat (fleeing starves them on the way); trivial / pursuit
    # below still end a fight with nothing left to win
    fb.op('JSLte', a=dd, b=zero, offset='ndoom')
    fb.op('Mul', dst=p, a=tot, b=_ratio(fb, b, DOOM_SHARE))
    fb.op('JSLt', a=dd, b=p, offset='ndoom')
    fb.op('Bool', dst=doom, value=True)
    hold = _ratio(fb, b, DOOM_HOLD)
    fb.op('JSGte', a=bal, b=hold, offset='ndoom')
    fb.op('Mov', dst=bal, src=hold)
    fb.label('ndoom')
    r = _ratio(fb, b, RETREAT)
    # pursuit: the enemy within CONTACT of the fight loses less than PROGRESS of its power in PURSUIT_T s = we chase an
    # army as fast as we are. Measured per warzone all the time (so the clock keeps running when a hunt ends); acted
    # on only when none of our armies there is on a mission (Military order: its own aborts decide) and the fight is
    # off our land (at home a fleeing intruder costs nothing to follow): balance 0, vanilla's retreat pulls them out
    # (a Resupply order can't). Smugglers followed an unhurt F_Trooper ~100 south from Larram under Grimpo's turret
    # for 14 s after their hunt ended
    purs = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=purs, value=False)
    q2 = fb.reg(cx.t('f64'))
    en = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=en, src=zero)
    state = _state(fb, b, cx)
    now = b.field(state, 'time')
    all_a = b.field(state, 'armies')
    alen4 = b.field(all_a, 'length')
    i4 = fb.reg(cx.t('i32'))
    c2 = b.const('f64', CONTACT * CONTACT)
    x4 = _army_loop(fb, b, all_a, alen4, i4, 'pen', 'pendone')
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', x4, 1), offset='pen')  # fog: seen enemies only
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
    # trivial: off our zone, the enemy within CONTACT is worth < TRIVIAL of our power here and none of ours is on a
    # mission: nothing to win, balance 0 (stranded included). Atreides' 8 stranded armies (296k) followed a dying
    # F_Demo (en 2.6-4.5k: its power bounced, the pursuit clock kept resetting) into Fremen turret cover after the
    # hunt ended and were wiped out in 60 s
    triv = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=triv, value=False)
    fb.op('JSLte', a=en, b=zero, offset='tdone')
    fb.op('JSLte', a=bal, b=r, offset='tdone')  # leaving anyway
    fb.op('JSGt', a=t, b=b.const('f64', 1), offset='tdone')  # our own zone
    fb.op('Mul', dst=q2, a=tot, b=_ratio(fb, b, TRIVIAL))
    fb.op('JSGte', a=en, b=q2, offset='tdone')
    arr5, alen5 = _my_armies(fb, b, 1, 'tdone')
    i5 = fb.reg(cx.t('i32'))
    a5 = _army_loop(fb, b, arr5, alen5, i5, 'tms', 'tmsdone')
    fb.op('Sub', dst=dx, a=b.field(a5, 'posx'), b=cxp)
    fb.op('Sub', dst=dy, a=b.field(a5, 'posy'), b=cyp)
    fb.op('Mul', dst=dx, a=dx, b=dx)
    fb.op('Mul', dst=dy, a=dy, b=dy)
    fb.op('Add', dst=dx, a=dx, b=dy)
    fb.op('JSGt', a=dx, b=r2, offset='tms')
    fb.op('Call2', dst=ok, fun=mission, arg0=1, arg1=a5)
    fb.op('JTrue', cond=ok, offset='tdone')
    fb.op('JAlways', offset='tms')
    fb.label('tmsdone')
    fb.op('Mov', dst=bal, src=zero)
    fb.op('Bool', dst=triv, value=True)
    fb.label('tdone')
    # capture side fight: a fight CAPS_MIN..LOCAL from the target of one of our Military orders in Action whose
    # armies at the target (within CAPL_R) outweigh ours in this fight is a skirmish beside the capture: no retreat
    # (vanilla's retreat cancels every related order: Fremen's 11-army Annex of Had-fir, winning 12:1, was cancelled
    # by a 0.34 fight 134 out where its chasers had been, after the capture leash pulled them back in)
    csd = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=csd, value=False)
    fb.op('JSGt', a=bal, b=r, offset='csdone')
    cctl = b.field(1, 'aiController')
    fb.op('JNull', reg=cctl, offset='csdone')
    cords = b.field(b.field(cctl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=cords, offset='csdone')
    ck, cix, cj = fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    cdx, cdy, occ = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    cte = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ck, src=b.field(cords, 'length'))
    b.loop_head('csl')
    fb.op('JSLte', a=ck, b=b.const('i32', 0), offset='csdone')
    fb.op('Sub', dst=ck, a=ck, b=b.const('i32', 1))
    co = b.cast(b.call('hl.types.ArrayObj.getDyn', cords, ck), 'logic.ai.AIOrder')
    fb.op('JNull', reg=co, offset='csl')
    fb.op('JNotEq', a=b.field(co, 'phase'), b=b.const('i32', ACTION), offset='csl')
    fb.op('EnumIndex', dst=cix, value=b.field(co, 'type'))
    fb.op('JNotEq', a=cix, b=b.const('i32', MILITARY), offset='csl')
    ctt = b.field(co, 'targetType')
    fb.op('JNull', reg=ctt, offset='csl')
    fb.op('EnumIndex', dst=cix, value=ctt)
    fb.op('JNotEq', a=cix, b=b.const('i32', T_STRUCT), offset='csl')
    fb.op('Mov', dst=cte, src=b.cast(b.call('logic.ai.AIOrder.getTarget', co), 'ent.Entity'))
    fb.op('JNull', reg=cte, offset='csl')
    fb.op('Sub', dst=cdx, a=b.field(cte, 'posx'), b=cxp)
    fb.op('Sub', dst=cdy, a=b.field(cte, 'posy'), b=cyp)
    fb.op('Mul', dst=cdx, a=cdx, b=cdx)
    fb.op('Mul', dst=cdy, a=cdy, b=cdy)
    fb.op('Add', dst=cdx, a=cdx, b=cdy)
    fb.op('JSLte', a=cdx, b=b.const('f64', CAPS_MIN * CAPS_MIN), offset='csl')  # the capture's own fight
    fb.op('JSGt', a=cdx, b=b.const('f64', LOCAL * LOCAL), offset='csl')
    cu = b.field(co, 'units')
    fb.op('JNull', reg=cu, offset='csl')
    fb.op('Mov', dst=occ, src=zero)
    ca = _army_loop(fb, b, cu, b.field(cu, 'length'), cj, 'csu', 'csud')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ca, cte), b=b.const('f64', CAPL_R), offset='csu')
    fb.op('Call1', dst=p, fun=pw, arg0=ca)
    fb.op('Add', dst=occ, a=occ, b=p)
    fb.op('JAlways', offset='csu')
    fb.label('csud')
    fb.op('JSLte', a=occ, b=zero, offset='csl')
    fb.op('JSLt', a=occ, b=tot, offset='csl')
    fb.op('Bool', dst=csd, value=True)
    fb.op('Add', dst=bal, a=r, b=_ratio(fb, b, 0.01))
    fb.label('csdone')
    # approach under fire: no at-war army within CONTACT (only structures shoot) and every army of ours within FLEE_R
    # of the fight is on a Military order (walking to its siege): no retreat. Its cancel killed Fremen's split
    # Liberate of Ayn-mara 5 s after it started (raw 0 / en 0: none of ours yet within 80 of the turret's fight)
    apr = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=apr, value=False)
    fb.op('JSGt', a=bal, b=r, offset='apdone')
    fb.op('JSGt', a=en, b=zero, offset='apdone')
    arr6, alen6 = _my_armies(fb, b, 1, 'apdone')
    i6 = fb.reg(cx.t('i32'))
    a6 = _army_loop(fb, b, arr6, alen6, i6, 'apl', 'aphold')
    fb.op('Sub', dst=dx, a=b.field(a6, 'posx'), b=cxp)
    fb.op('Sub', dst=dy, a=b.field(a6, 'posy'), b=cyp)
    fb.op('Mul', dst=dx, a=dx, b=dx)
    fb.op('Mul', dst=dy, a=dy, b=dy)
    fb.op('Add', dst=dx, a=dx, b=dy)
    fb.op('JSGt', a=dx, b=r2, offset='apl')
    fb.op('Call2', dst=ok, fun=mission, arg0=1, arg1=a6)
    fb.op('JFalse', cond=ok, offset='apdone')  # one of ours there is on no mission: vanilla's call
    fb.op('JAlways', offset='apl')
    fb.label('aphold')
    fb.op('Bool', dst=apr, value=True)
    fb.op('Add', dst=bal, a=r, b=_ratio(fb, b, 0.01))
    fb.label('apdone')
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
    fb.op('JFalse', cond=doom, offset='hold')
    fb.op('Mov', dst=act, src=fb.string('doomed'))  # held in the fight: the way home kills them
    fb.label('hold')
    fb.op('JFalse', cond=csd, offset='ncs')
    fb.op('Mov', dst=act, src=fb.string('capside'))
    fb.op('JAlways', offset='act')
    fb.label('ncs')
    fb.op('JFalse', cond=apr, offset='napr')
    fb.op('Mov', dst=act, src=fb.string('approach'))
    fb.op('JAlways', offset='act')
    fb.label('napr')
    fb.op('JSGt', a=bal, b=r, offset='act')
    fb.op('Mov', dst=act, src=fb.string('trivial'))  # no mission, nothing worth fighting
    fb.op('JTrue', cond=triv, offset='act')
    fb.op('Mov', dst=act, src=fb.string('pursuit'))  # no mission, no progress
    fb.op('JTrue', cond=purs, offset='act')
    fb.op('Mov', dst=act, src=fb.string('retreat'))
    fb.op('JNotEq', a=sf, b=zero, offset='act')
    fb.op('Mov', dst=act, src=fb.string('recall'))  # all short, none on a mission
    fb.label('act')
    _log_ev(fb, b, cx, helpers, 'retreat', [('f', fb.get(1, 'kind')), ('act', act), ('raw%', raw), ('tf%', t),
                                            ('sf%', sf), ('adj%', bal), ('dm', dm), ('en', en), ('x', cxp),
                                            ('y', cyp)])
    fb.op('JAlways', offset='end')
    # disengage: nothing with power left to fight (a harvester, an empty structure) and one of our armies there has
    # a Resupply order, none a Military one: balance 0 so vanilla pulls them out. Else micro keeps them shooting the
    # target while the order walks them home: Atreides off their aborted hunt kept attacking the F_Harvester at
    # balance 1.0 for 60 s (stop / go, supply falling, Fremen closing in)
    fb.label('nopow')
    nc = b.call('logic.state.Warzone.get_centroid', 0)
    fb.op('JNull', reg=nc, offset='end')
    ncx, ncy = b.field(nc, 'x'), b.field(nc, 'y')
    ex, ey = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    rsp = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=rsp, value=False)
    oth = fb.reg(cx.t('bool'))  # one of ours there on another order (Discovery, Investigate, Defense, Patrol, ...)
    fb.op('Bool', dst=oth, value=False)
    oix = fb.reg(cx.t('i32'))
    arr5, alen5 = _my_armies(fb, b, 1, 'end')
    i5 = fb.reg(cx.t('i32'))
    a5 = _army_loop(fb, b, arr5, alen5, i5, 'npl', 'npdone')
    fb.op('Sub', dst=ex, a=b.field(a5, 'posx'), b=ncx)
    fb.op('Sub', dst=ey, a=b.field(a5, 'posy'), b=ncy)
    fb.op('Mul', dst=ex, a=ex, b=ex)
    fb.op('Mul', dst=ey, a=ey, b=ey)
    fb.op('Add', dst=ex, a=ex, b=ey)
    fb.op('JSGt', a=ex, b=b.const('f64', FLEE_R * FLEE_R), offset='npl')
    fb.op('Call2', dst=ok, fun=mission, arg0=1, arg1=a5)
    fb.op('JTrue', cond=ok, offset='end')  # a hunt / siege / raid there: its own rules decide
    o5 = fb.reg(cx.t('logic.ai.AIOrder'))
    _order_of(fb, b, cx, 1, a5, o5, 'npl')  # the live order holding it (Unit.aiOrder is never maintained)
    u5 = b.field(o5, 'units')
    fb.op('JNull', reg=u5, offset='npl')
    fb.op('JSLte', a=b.field(u5, 'length'), b=b.const('i32', 0), offset='npl')
    fb.op('EnumIndex', dst=oix, value=b.field(o5, 'type'))
    fb.op('JEq', a=oix, b=b.const('i32', RESUPPLY), offset='nprs')
    fb.op('Bool', dst=oth, value=True)
    fb.op('JAlways', offset='npl')
    fb.label('nprs')
    fb.op('Bool', dst=rsp, value=True)
    fb.op('JAlways', offset='npl')
    fb.label('npdone')
    dact = fb.reg(cx.t('String'))
    fb.op('Mov', dst=dact, src=fb.string('disengage'))
    fb.op('JTrue', cond=rsp, offset='dgo')
    # trespass only for armies without an order there: a Discovery / Investigate / Defense trip that brushes an enemy
    # building has its own gates, and cancelling it would re-launch it (a cancel / relaunch loop)
    fb.op('JTrue', cond=oth, offset='end')
    # trespass: the same on an at-war faction's zone with no order at all: micro walks orderless armies from one
    # structure to the next (turrets read 0 power), nothing to capture without an order. Smugglers' 9 armies, worm-held
    # after their contest chase, attacked their way from Hal-Al'mon to 30 from Carthag and lost the fight there
    gs2 = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gs2, **{'global': cx.global_of('$Game')})
    nworld = b.field(b.field(gs2, 'inst'), 'world')
    fb.op('JNull', reg=nworld, offset='end')
    nz = b.call('world.World.getZoneAt', nworld, ncx, ncy)
    fb.op('JNull', reg=nz, offset='end')
    zo = b.field(nz, 'owner')
    fb.op('JNull', reg=zo, offset='end')
    fb.op('JEq', a=zo, b=1, offset='end')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', _state(fb, b, cx), 1, zo), offset='end')
    fb.op('Mov', dst=dact, src=fb.string('trespass'))
    fb.label('dgo')
    fb.op('Mov', dst=bal, src=b.const('f64', 0))
    _throttle(fb, b, cx, 'retreat', 0, 5, 'end')
    _log_ev(fb, b, cx, helpers, 'retreat', [('f', fb.get(1, 'kind')), ('act', dact), ('raw%', raw),
                                            ('adj%', bal), ('x', ncx), ('y', ncy)])
    fb.label('end')
    fb.end_try(guard)
    # strike: the warzone balance doesn't see a sietch / renegade garrison (Harkonnen at Tabmah: raw 1.0 "no enemy"
    # while the order balance read 0.74 and 8 armies fell to 3 in 30 s): within SITE_WZ_R of such a target of our
    # Military order in Action, the balance is at most that order's live balance (vanilla getOrderPowerBalance:
    # counts the living defenders; no terrain / supply factor). Logs `sbal` when it lowers the balance
    g1 = fb.try_()
    ctl = b.field(1, 'aiController')
    fb.op('JNull', reg=ctl, offset='sb_end')
    aiu = b.field(ctl, 'aiUnits')
    fb.op('JNull', reg=aiu, offset='sb_end')
    sords = b.field(b.field(ctl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=sords, offset='sb_end')
    sc = b.call('logic.state.Warzone.get_centroid', 0)
    fb.op('JNull', reg=sc, offset='sb_end')
    scx, scy = b.field(sc, 'x'), b.field(sc, 'y')
    sk, sx = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    sdx, sdy, ob = (fb.reg(cx.t('f64')) for _ in range(3))
    sse = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=sk, src=b.field(sords, 'length'))
    b.loop_head('sbl')
    fb.op('JSLte', a=sk, b=b.const('i32', 0), offset='sb_end')
    fb.op('Sub', dst=sk, a=sk, b=b.const('i32', 1))
    so = b.cast(b.call('hl.types.ArrayObj.getDyn', sords, sk), 'logic.ai.AIOrder')
    fb.op('JNull', reg=so, offset='sbl')
    fb.op('JNotEq', a=b.field(so, 'phase'), b=b.const('i32', ACTION), offset='sbl')
    fb.op('EnumIndex', dst=sx, value=b.field(so, 'type'))
    fb.op('JNotEq', a=sx, b=b.const('i32', MILITARY), offset='sbl')
    stt = b.field(so, 'targetType')
    fb.op('JNull', reg=stt, offset='sbl')
    fb.op('EnumIndex', dst=sx, value=stt)
    fb.op('JNotEq', a=sx, b=b.const('i32', T_STRUCT), offset='sbl')
    stg = b.call('logic.ai.AIOrder.getTarget', so)
    fb.op('JNull', reg=stg, offset='sbl')
    sst = b.cast(fb.dyn(stg), 'ent.Structure')
    _strong_site(fb, b, sst, 'sb_site')
    fb.op('JAlways', offset='sbl')
    fb.label('sb_site')
    fb.op('Mov', dst=sse, src=sst)
    fb.op('Sub', dst=sdx, a=b.field(sse, 'posx'), b=scx)
    fb.op('Sub', dst=sdy, a=b.field(sse, 'posy'), b=scy)
    fb.op('Mul', dst=sdx, a=sdx, b=sdx)
    fb.op('Mul', dst=sdy, a=sdy, b=sdy)
    fb.op('Add', dst=sdx, a=sdx, b=sdy)
    fb.op('JSGt', a=sdx, b=b.const('f64', SITE_WZ_R * SITE_WZ_R), offset='sbl')
    # ... and this fight is the strike's: one of its armies within FLEE_R of the centroid (a defense fight at our
    # village next to the sietch, Ashrekh 50 from Tabmah, isn't judged by the strike)
    sun = b.field(so, 'units')
    fb.op('JNull', reg=sun, offset='sbl')
    su = _army_loop(fb, b, sun, b.field(sun, 'length'), sx, 'sbu', 'sbl')
    fb.op('Sub', dst=sdx, a=b.field(su, 'posx'), b=scx)
    fb.op('Sub', dst=sdy, a=b.field(su, 'posy'), b=scy)
    fb.op('Mul', dst=sdx, a=sdx, b=sdx)
    fb.op('Mul', dst=sdy, a=sdy, b=sdy)
    fb.op('Add', dst=sdx, a=sdx, b=sdy)
    fb.op('JSGt', a=sdx, b=b.const('f64', FLEE_R * FLEE_R), offset='sbu')
    fb.op('Mov', dst=ob, src=b.call('logic.ai.AIUnits.getOrderPowerBalance', aiu, so))
    # 0 = vanilla's "no units / no zone" answer, not a lost fight
    fb.op('JSLte', a=ob, b=b.const('f64', 0), offset='sbl')
    fb.op('JSGte', a=ob, b=bal, offset='sbl')
    fb.op('Mov', dst=bal, src=ob)
    _throttle(fb, b, cx, 'sbal', so, 5, 'sbl')
    _log_ev(fb, b, cx, helpers, 'sbal', [('f', fb.get(1, 'kind')), ('tgt', sst), ('raw%', raw), ('ob%', ob),
                                         ('x', scx), ('y', scy)])
    fb.op('JAlways', offset='sbl')
    fb.label('sb_end')
    fb.end_try(g1)
    # diagnostic `wzb`: every fight's balance once per WZB_T s per warzone (raw = vanilla, adj = what vanilla
    # compares with RETREAT): explains fights that never retreat (a lone army dying to village militia)
    g2 = fb.try_()
    fb.op('JNull', reg=0, offset='wz_end')
    _throttle(fb, b, cx, 'wzb', 0, WZB_T, 'wz_end')
    c2 = b.call('logic.state.Warzone.get_centroid', 0)
    fb.op('JNull', reg=c2, offset='wz_end')
    _log_ev(fb, b, cx, helpers, 'wzb', [('f', fb.get(1, 'kind')), ('raw%', raw), ('adj%', bal),
                                        ('x', fb.get(c2, 'x')), ('y', fb.get(c2, 'y'))])
    fb.label('wz_end')
    fb.end_try(g2)
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
    """aimod_unsafe(s, self, sticky, fac) -> judged for s's owner, else fac, else self's owner (an ownerless allied
    sietch: Fremen kept retreating to Karlon in Atreides land, into the fight there, rated safe as owner-less);
    0 safe, 1 contested: threat(owner, s) > own(owner, s, without self) *
    (sticky ? STICKY : 1), 2 overwhelming: threat > (own + power of self) * OVERWHELM, or within RALLY_MIN of the
    owner's running rally's danger structure (map `rly`, `rlyt` within RALLY_HOLD: no heal / flee trip next to it),
    or when self's straight walk to s passes within CROSS_R of the owner's structure under at-war siege (besieger or
    occupier at war with the owner, threat within LOCAL >= RALLY_MIN_H) or of the rally's danger structure (_crosses; not one self stands within
    CROSS_R of: that fight is the retreat logic's)."""
    fb = FB(cx, [cx.t('ent.Structure'), cx.t('ent.Army'), cx.t('bool'), cx.t('ent.Faction')], cx.t('i32'))
    b = B(fb)
    res = fb.reg(cx.t('i32'))
    fb.op('Int', dst=res, ptr=cx.code.add_i32(0).value)
    fb.op('JNull', reg=0, offset='end')
    owner = fb.reg(cx.t('ent.Faction'))
    fb.op('Mov', dst=owner, src=b.call('ent.Entity.get_owner', 0))
    fb.op('JNotNull', reg=owner, offset='ownok')
    fb.op('Mov', dst=owner, src=3)
    fb.op('JNotNull', reg=owner, offset='ownok')
    fb.op('JNull', reg=1, offset='end')
    fb.op('Mov', dst=owner, src=b.call('ent.Entity.get_owner', 1))
    fb.op('JNull', reg=owner, offset='end')
    fb.label('ownok')
    s = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=s, src=0)
    # rally running: structures next to the danger are off limits
    rd = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rly'), fb.dyn(owner))
    fb.op('JNull', reg=rd, offset='norly')
    rq = fb.reg(cx.t('f64'))
    rt = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rlyt'), fb.dyn(owner))
    fb.op('JNull', reg=rt, offset='norly')
    fb.op('SafeCast', dst=rq, src=rt)
    fb.op('Sub', dst=rq, a=b.field(_state(fb, b, cx), 'time'), b=rq)
    fb.op('JSGt', a=rq, b=b.const('f64', RALLY_HOLD), offset='norly')
    re_ = b.cast(rd, 'ent.Entity')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', s, re_), b=b.const('f64', RALLY_MIN), offset='norly')
    fb.op('Int', dst=res, ptr=cx.code.add_i32(2).value)
    fb.op('JAlways', offset='end')
    fb.label('norly')
    # the walk there passes our structure under at-war siege, or the rally's danger structure: through the enemy
    # (Fremen liberating Tsimlat: Harkonnen's strand sent 4 armies from Tabiel past them to Had-Al'riyah, rated safe
    # by the threat around it alone); not when self already stands within CROSS_R of it (in that fight)
    crossed = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=crossed, value=False)
    cguard = fb.try_()  # inside vanilla's heal sort: an exception here must not escape (flag, no jump out)
    fb.op('JNull', reg=1, offset='nocross')
    sx, sy = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    ax, ay = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    px, py = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=sx, src=b.field(s, 'posx'))
    fb.op('Mov', dst=sy, src=b.field(s, 'posy'))
    fb.op('Mov', dst=ax, src=b.field(1, 'posx'))
    fb.op('Mov', dst=ay, src=b.field(1, 'posy'))
    cr, ch = b.const('f64', CROSS_R), b.const('f64', RALLY_MIN_H)
    ce = fb.reg(cx.t('ent.Entity'))
    cq = fb.reg(cx.t('f64'))
    cbf = fb.reg(cx.t('ent.Faction'))
    crs = b.cast(fb.get(owner, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=crs, offset='crly')
    ci, cn = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=cn, src=b.field(crs, 'length'))
    fb.op('Mov', dst=ci, src=b.const('i32', 0))
    b.loop_head('cl')
    fb.op('JSGte', a=ci, b=cn, offset='crly')
    c = b.cast(b.call('hl.types.ArrayObj.getDyn', crs, ci), 'ent.Structure')
    fb.op('Incr', dst=ci)
    fb.op('JNull', reg=c, offset='cl')
    # an active siege (SiegeComponent is on every village: besieger or occupier set) by a faction at war with us;
    # cheap tests first: this runs inside vanilla's heal sort, once per key
    csg = b.field(c, 'siege')
    fb.op('JNull', reg=csg, offset='cl')
    fb.op('Mov', dst=cbf, src=b.field(csg, 'besiegingFaction'))
    fb.op('JNotNull', reg=cbf, offset='cbf')
    fb.op('Mov', dst=cbf, src=b.call('ent.comp.SiegeComponent.getOccupierFaction', csg))
    fb.op('JNull', reg=cbf, offset='cl')
    fb.label('cbf')
    fb.op('JEq', a=cbf, b=owner, offset='cl')
    fb.op('Mov', dst=ce, src=c)
    fb.op('JEq', a=ce, b=s, offset='cl')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', 1, ce), b=cr, offset='cl')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', _state(fb, b, cx), owner, cbf), offset='cl')
    fb.op('Call3', dst=cq, fun=threat, arg0=owner, arg1=ce, arg2=b.const('f64', LOCAL))
    fb.op('JSLt', a=cq, b=ch, offset='cl')
    fb.op('Mov', dst=px, src=b.field(ce, 'posx'))
    fb.op('Mov', dst=py, src=b.field(ce, 'posy'))
    _crosses(fb, b, cx, ax, ay, sx, sy, px, py, CROSS_R, 'cross')
    fb.op('JAlways', offset='cl')
    fb.label('crly')
    rd2 = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rly'), fb.dyn(owner))
    fb.op('JNull', reg=rd2, offset='nocross')
    fb.op('Mov', dst=ce, src=b.cast(rd2, 'ent.Entity'))
    fb.op('JNull', reg=ce, offset='nocross')
    fb.op('JEq', a=ce, b=s, offset='nocross')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', 1, ce), b=cr, offset='nocross')
    fb.op('Mov', dst=px, src=b.field(ce, 'posx'))
    fb.op('Mov', dst=py, src=b.field(ce, 'posy'))
    _crosses(fb, b, cx, ax, ay, sx, sy, px, py, CROSS_R, 'cross')
    fb.op('JAlways', offset='nocross')
    fb.label('cross')
    fb.op('Bool', dst=crossed, value=True)
    fb.label('nocross')
    fb.end_try(cguard)
    fb.op('JFalse', cond=crossed, offset='ncr')
    fb.op('Int', dst=res, ptr=cx.code.add_i32(2).value)
    fb.op('JAlways', offset='end')
    fb.label('ncr')
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
    # the owner's active main base: never merely contested, its guns fight with us (only overwhelming counts):
    # Fremen's retreat from Grim-po skipped Tabr 236 away as contested and fled 320 to Sabnun
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', 0), offset='nmb')
    fb.op('JNotEq', a=b.call('ent.Entity.get_owner', 0), b=owner, offset='nmb')
    fb.op('JSLte', a=h, b=m2, offset='end')
    fb.label('nmb')
    fb.op('Int', dst=res, ptr=cx.code.add_i32(1).value)
    fb.op('JSLte', a=h, b=m2, offset='end')
    fb.op('Int', dst=res, ptr=cx.code.add_i32(2).value)
    fb.label('end')
    fb.op('Ret', ret=res)
    return fb.build()


def _retreat_clear(fb, b, cx, d, heal_log):
    """Fight retreat (warzone key closure, arg 1 = a healing structure): a structure within RETREAT_CLEAR of the
    warzone centroid is inside the fight, + PENALTY (any farther one wins; all inside: the nearest still does); a main
    base never (its guns).
    Smugglers retreated from Tsimrekh to Annarekh, 75 from the fight: the retreat fired every 5 s for a minute
    while they stood there at balance 0.25 -> 0 and lost half their army (296k -> 154k). Logs heal act `infight`."""
    done = _uid('rc')
    # a main base is exempt: its guns fight with us (leaving it would abandon the base to a fight at its walls)
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', 1), offset=done)
    c = b.call('logic.state.Warzone.get_centroid', 0)
    fb.op('JNull', reg=c, offset=done)
    dx, dy = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Sub', dst=dx, a=b.field(1, 'posx'), b=b.field(c, 'x'))
    fb.op('Sub', dst=dy, a=b.field(1, 'posy'), b=b.field(c, 'y'))
    fb.op('Mul', dst=dx, a=dx, b=dx)
    fb.op('Mul', dst=dy, a=dy, b=dy)
    fb.op('Add', dst=dx, a=dx, b=dy)
    fb.op('JSGte', a=dx, b=b.const('f64', RETREAT_CLEAR * RETREAT_CLEAR), offset=done)
    fb.op('Add', dst=d, a=d, b=b.const('f64', PENALTY))
    heal_log('infight', None, None)
    fb.label(done)


def _retreat_side(fb, b, cx, d):
    """Fight retreat on our land (the warzone centroid's zone is the structure owner's): a healing structure on the
    enemy's side of the fight (dot(s - c, e - c) > 0, e = centroid of warzone.getEnemies) gets + DETOUR^2: the
    retreat goes back into our land, not into the pursuers' path (Fremen retreated to Qartsan, where Atreides were
    heading). Off our land nothing changes: home stays the goal even with the enemy in between."""
    done = _uid('rs')
    so = b.call('ent.Entity.get_owner', 1)
    fb.op('JNull', reg=so, offset=done)
    c = b.call('logic.state.Warzone.get_centroid', 0)
    fb.op('JNull', reg=c, offset=done)
    cxr, cyr = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=cxr, src=b.field(c, 'x'))
    fb.op('Mov', dst=cyr, src=b.field(c, 'y'))
    gs = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gs, **{'global': cx.global_of('$Game')})
    world = b.field(b.field(gs, 'inst'), 'world')
    fb.op('JNull', reg=world, offset=done)
    z = b.call('world.World.getZoneAt', world, cxr, cyr)
    fb.op('JNull', reg=z, offset=done)
    fb.op('JNotEq', a=b.field(z, 'owner'), b=so, offset=done)
    gen = cx.fn('logic.state.Warzone.getEnemies')
    gargs = [a.value for a in cx.code.types[gen.type.value].definition.args]
    n1, n2 = fb.reg(gargs[2]), fb.reg(gargs[3])
    fb.op('Null', dst=n1)
    fb.op('Null', dst=n2)
    fac = fb.reg(gargs[1])
    fb.op('Mov', dst=fac, src=so)
    en = b.call('logic.state.Warzone.getEnemies', 0, fac, n1, n2)
    fb.op('JNull', reg=en, offset=done)
    k, cnt = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    ex, ey, q, w = (fb.reg(cx.t('f64')) for _ in range(4))
    for r in (ex, ey):
        fb.op('Mov', dst=r, src=b.const('f64', 0))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    fb.op('Mov', dst=cnt, src=b.const('i32', 0))
    head, edone = _uid('rse'), _uid('rsd')
    b.loop_head(head)
    fb.op('JSGte', a=k, b=b.field(en, 'length'), offset=edone)
    e = b.cast(b.call('hl.types.ArrayObj.getDyn', en, k), 'ent.Entity')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=e, offset=head)
    fb.op('Add', dst=ex, a=ex, b=b.field(e, 'posx'))
    fb.op('Add', dst=ey, a=ey, b=b.field(e, 'posy'))
    fb.op('Incr', dst=cnt)
    fb.op('JAlways', offset=head)
    fb.label(edone)
    fb.op('JSLte', a=cnt, b=b.const('i32', 0), offset=done)
    fb.op('ToSFloat', dst=w, src=cnt)
    fb.op('SDiv', dst=ex, a=ex, b=w)
    fb.op('SDiv', dst=ey, a=ey, b=w)
    fb.op('Sub', dst=ex, a=ex, b=cxr)
    fb.op('Sub', dst=ey, a=ey, b=cyr)
    fb.op('Sub', dst=q, a=b.field(1, 'posx'), b=cxr)
    fb.op('Mul', dst=q, a=q, b=ex)
    fb.op('Sub', dst=w, a=b.field(1, 'posy'), b=cyr)
    fb.op('Mul', dst=w, a=w, b=ey)
    fb.op('Add', dst=q, a=q, b=w)
    fb.op('JSLte', a=q, b=b.const('f64', 0), offset=done)
    fb.op('Add', dst=d, a=d, b=b.const('f64', DETOUR * DETOUR))
    fb.label(done)


def _gather_point(fb, b, cx, jf, d, d0, lvl, is_army):
    """One place to fall back to (heal key, arg 1 = a healing structure): while jf's rally runs, its rally point
    (map `rlyp`) for an army / a fight within RALLY_R of the rally's D; else the structure jf's last fight retreat committed to (map `rgp`, set by _retreat_commit) within
    RG_T s, for a fight / an army within LOCAL of that fight's centroid (`rgx` / `rgy`). It wins (key 0) unless
    overwhelming (lvl 2), fled from (army at it in contact), in the fight or on the enemy's side (any penalty but the
    contested detour on the original key d0): each
    army otherwise picked its own nearest safe structure (Fremen at Grim-po: two fled 320 to Sabnun, the rest
    elsewhere) and the force couldn't regroup."""
    done, hit = _uid('gp'), _uid('gph')
    fb.op('JNull', reg=jf, offset=done)
    fb.op('JSGt', a=lvl, b=b.const('i32', 1), offset=done)
    # only the contested detour may have been added (no flee / overwhelming / in-fight / enemy-side penalty)
    lim = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=lim, src=d0)
    gl = _uid('gpl')
    fb.op('JSLt', a=lvl, b=b.const('i32', 1), offset=gl)
    fb.op('Add', dst=lim, a=lim, b=b.const('f64', DETOUR * DETOUR))
    fb.label(gl)
    fb.op('JSGt', a=d, b=lim, offset=done)
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=1)
    q, px, py = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    # where the asking army / the fight is
    if is_army:
        fb.op('Mov', dst=px, src=b.field(0, 'posx'))
        fb.op('Mov', dst=py, src=b.field(0, 'posy'))
    else:
        c = b.call('logic.state.Warzone.get_centroid', 0)
        fb.op('JNull', reg=c, offset=done)
        fb.op('Mov', dst=px, src=b.field(c, 'x'))
        fb.op('Mov', dst=py, src=b.field(c, 'y'))
    rly = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rly'), fb.dyn(jf))
    nor = _uid('gpn')
    fb.op('JNull', reg=rly, offset=nor)
    # a rally runs: its point, for armies / fights in its reach (RALLY_R of D; a fight at another front keeps its
    # own choice)
    rde = b.cast(rly, 'ent.Entity')
    fb.op('JNull', reg=rde, offset=nor)
    dx, dy = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Sub', dst=dx, a=px, b=b.field(rde, 'posx'))
    fb.op('Sub', dst=dy, a=py, b=b.field(rde, 'posy'))
    fb.op('Mul', dst=dx, a=dx, b=dx)
    fb.op('Mul', dst=dy, a=dy, b=dy)
    fb.op('Add', dst=dx, a=dx, b=dy)
    fb.op('JSGt', a=dx, b=b.const('f64', RALLY_R * RALLY_R), offset=nor)
    fb.op('JEq', a=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rlyp'), fb.dyn(jf)), b=fb.dyn(se),
          offset=hit)
    fb.op('JAlways', offset=done)  # in the rally's reach: only its point
    fb.label(nor)
    fb.op('JNotEq', a=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rgp'), fb.dyn(jf)), b=fb.dyn(se),
          offset=done)
    tv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rgpt'), fb.dyn(jf))
    fb.op('JNull', reg=tv, offset=done)
    fb.op('SafeCast', dst=q, src=tv)
    fb.op('Sub', dst=q, a=b.field(_state(fb, b, cx), 'time'), b=q)
    fb.op('JSGt', a=q, b=b.const('f64', RG_T), offset=done)
    for v, nm in ((px, 'rgx'), (py, 'rgy')):
        gv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, nm), fb.dyn(jf))
        fb.op('JNull', reg=gv, offset=done)
        fb.op('SafeCast', dst=q, src=gv)
        fb.op('Sub', dst=v, a=v, b=q)
        fb.op('Mul', dst=v, a=v, b=v)
    fb.op('Add', dst=px, a=px, b=py)
    fb.op('JSGt', a=px, b=b.const('f64', LOCAL * LOCAL), offset=done)
    fb.label(hit)
    fb.op('Mov', dst=d, src=b.const('f64', 0))
    fb.label(done)


def _retreat_commit(fb, b, cx, d, jf):
    """Fight retreat (warzone key closure, arg 0 = the Warzone, arg 1 = a healing structure, d = its key): the
    structure the retreat picks first is kept HEAL_COMMIT s (key 0: it wins the sort), then re-chosen. Vanilla
    re-issues the retreat Resupply every tick and the keys move with the threat, so the target flipped every few
    s (Fremen: Ur-Al'nun / Qartsan / Arkdad, armies turned back and forth and 2 died at Qartsan). Rounds: all calls
    of one tick share state.time; the min-key structure of a round (maps hcb / hck / hcr) is committed at the next
    round if that one follows within 1 s (maps hcs / hct)."""
    now = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=now, src=b.field(_state(fb, b, cx), 'time'))
    wz = fb.dyn(0)
    hcs, hct, hcb, hck, hcr = (_global_map(fb, b, cx, nm) for nm in ('hcs', 'hct', 'hcb', 'hck', 'hcr'))
    q, r = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=1)
    done, track, newr, keep = _uid('rc'), _uid('rct'), _uid('rcn'), _uid('rck')
    # an active commit: the committed structure wins
    ct = b.call('haxe.ds.ObjectMap.get', hct, wz)
    fb.op('JNull', reg=ct, offset=track)
    fb.op('SafeCast', dst=q, src=ct)
    fb.op('Sub', dst=q, a=now, b=q)
    fb.op('JSGte', a=q, b=b.const('f64', HEAL_COMMIT), offset=track)
    fb.op('JNotEq', a=b.call('haxe.ds.ObjectMap.get', hcs, wz), b=fb.dyn(se), offset=done)
    fb.op('Mov', dst=d, src=b.const('f64', 0))
    fb.op('JAlways', offset=done)
    # no commit: track this round's best; a new round commits the previous one's best (if it was the last tick)
    fb.label(track)
    rv = b.call('haxe.ds.ObjectMap.get', hcr, wz)
    fb.op('JNull', reg=rv, offset=newr)
    fb.op('SafeCast', dst=r, src=rv)
    fb.op('JEq', a=r, b=now, offset=keep)
    fb.op('Sub', dst=q, a=now, b=r)
    fb.op('JSGt', a=q, b=b.const('f64', 1), offset=newr)
    pb = b.call('haxe.ds.ObjectMap.get', hcb, wz)
    fb.op('JNull', reg=pb, offset=newr)
    b.call('haxe.ds.ObjectMap.set', hcs, wz, pb)
    b.call('haxe.ds.ObjectMap.set', hct, wz, fb.dyn(now))
    b.call('haxe.ds.ObjectMap.remove', hcr, wz)
    # the faction's fall-back point for this area (_gather_point): other retreats / heal trips nearby join it
    rgd = _uid('rgd')
    fb.op('JNull', reg=jf, offset=rgd)
    gc = b.call('logic.state.Warzone.get_centroid', 0)
    fb.op('JNull', reg=gc, offset=rgd)
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'rgp'), fb.dyn(jf), pb)
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'rgpt'), fb.dyn(jf), fb.dyn(now))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'rgx'), fb.dyn(jf), fb.dyn(b.field(gc, 'x')))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'rgy'), fb.dyn(jf), fb.dyn(b.field(gc, 'y')))
    fb.label(rgd)
    fb.op('JNotEq', a=pb, b=fb.dyn(se), offset=done)
    fb.op('Mov', dst=d, src=b.const('f64', 0))
    fb.op('JAlways', offset=done)
    fb.label(newr)
    b.call('haxe.ds.ObjectMap.set', hcr, wz, fb.dyn(now))
    b.call('haxe.ds.ObjectMap.set', hcb, wz, fb.dyn(se))
    b.call('haxe.ds.ObjectMap.set', hck, wz, fb.dyn(d))
    fb.op('JAlways', offset=done)
    fb.label(keep)
    kv = b.call('haxe.ds.ObjectMap.get', hck, wz)
    fb.op('JNull', reg=kv, offset=newr)
    fb.op('SafeCast', dst=q, src=kv)
    fb.op('JSGte', a=d, b=q, offset=done)
    b.call('haxe.ds.ObjectMap.set', hcb, wz, fb.dyn(se))
    b.call('haxe.ds.ObjectMap.set', hck, wz, fb.dyn(d))
    fb.label(done)


def _micro_owner(cx, new_ids):
    """Both AIUnits.unitMicroManagement call sites (onReady, regularUpdate) -> wrapper: map `umf` (State -> the
    faction whose micro runs) set around the call, so closures created and called inside it know their faction."""
    orig = cx.fn('logic.ai.AIUnits.unitMicroManagement')
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    g = fb.try_()
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'umf'), fb.dyn(_state(fb, b, cx)),
           fb.dyn(b.call('logic.ai.AIModule.get_aiOwner', 0)))
    fb.end_try(g)
    r = fb.reg(ft.ret.value)
    fb.op('CallN', dst=r, fun=orig.findex.value, args=list(range(len(args))))
    g2 = fb.try_()
    b.call('haxe.ds.ObjectMap.remove', _global_map(fb, b, cx, 'umf'), fb.dyn(_state(fb, b, cx)))
    fb.end_try(g2)
    fb.op('Ret', ret=r)
    w = fb.build()
    new_ids.add(w)
    return _redirect(cx, 'logic.ai.AIUnits.unitMicroManagement',
                     ['logic.ai.AIUnits.onReady', 'logic.ai.AIUnits.regularUpdate'], w)


def safe_heal(cx, unsafe, new_ids, threat_now, own, pw, threat, helpers):
    """Redirect the healing-structure sort closures to wrappers: key + PENALTY if the structure is unsafe."""
    report = {'micro-owner': _micro_owner(cx, new_ids)}
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
            d0 = fb.reg(cx.t('f64'))
            fb.op('Mov', dst=d0, src=d)

            jf_box = [None]  # the judging faction register, set below before any heal_log call

            def heal_log(act, h, m, fb=fb, b=b, is_army=args[0] == army_t):
                # `heal` {act stay|flee|detour|avoid, s, a, h, m, d}: once per structure per 3 s (the sort calls
                # this key many times); detour/avoid: h/m = threat / own (+ asking army) within SAFE_R
                done = _uid('hl')
                g2 = fb.try_()
                _throttle(fb, b, cx, 'heal', 1, 3, done)
                so = jf_box[0]
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
            # judging faction: the structure's owner; an ownerless one (allied sietch) for the asking side: the army's
            # owner, or (fight retreat) the first army owner in the warzone that the structure can supply
            jf = fb.reg(cx.t('ent.Faction'))
            fb.op('Mov', dst=jf, src=b.call('ent.Entity.get_owner', 1))
            jfok = _uid('jf')
            fb.op('JNotNull', reg=jf, offset=jfok)
            if args[0] == army_t:
                fb.op('Mov', dst=jf, src=b.call('ent.Entity.get_owner', 0))
            elif args[0] == cx.t('logic.state.Warzone'):
                # the fight-retreat key runs inside AIUnits.unitMicroManagement of the retreating faction (map `umf`,
                # set by _micro_owner); a warzone member's owner could be the enemy (Karlon supplies its zone's owner)
                mo = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'umf'), fb.dyn(_state(fb, b, cx)))
                fb.op('JNull', reg=mo, offset=jfok)
                fb.op('Mov', dst=jf, src=b.cast(mo, 'ent.Faction'))
            fb.label(jfok)
            jf_box[0] = jf
            # guest structure: stands in another faction's zone (Smugglers' UWHeadquarters at an enemy village's
            # centre; Headquarter.canSupply heals only units touching it, a village its whole zone): any real
            # healing structure wins (Smugglers sent 401-550 into Harkonnen's Arnkhelon / Walha at war, 50:09)
            gst = _uid('gst')
            so_ = b.call('ent.Entity.get_owner', 1)
            fb.op('JNull', reg=so_, offset=gst)
            sz = b.call('ent.Entity.get_zone', 1)
            fb.op('JNull', reg=sz, offset=gst)
            fb.op('JEq', a=b.field(sz, 'owner'), b=so_, offset=gst)
            fb.op('Add', dst=d, a=d, b=b.const('f64', PENALTY))
            heal_log('guest', None, None)
            fb.label(gst)
            # dead heal target (rules/orders.build_heal_dead): its Move orders keep being cancelled in Waiting
            hdk = _uid('hdk')
            hse = fb.reg(cx.t('ent.Entity'))
            fb.op('Mov', dst=hse, src=1)
            _heal_dead(fb, b, cx, hse, hdk + 'y')
            fb.op('JAlways', offset=hdk)
            fb.label(hdk + 'y')
            fb.op('Add', dst=d, a=d, b=b.const('f64', PENALTY))
            heal_log('dead', None, None)
            fb.label(hdk)
            sticky = fb.reg(cx.t('bool'))
            fb.op('Bool', dst=sticky, value=False)
            lvl = fb.reg(cx.t('i32'))
            fb.op('Int', dst=lvl, ptr=cx.code.add_i32(0).value)
            if args[0] == army_t:
                fb.op('Mov', dst=me, src=0)
                mfac = b.call('ent.Entity.get_owner', me)
                o = fb.reg(cx.t('logic.ai.AIOrder'))
                _order_of(fb, b, cx, mfac, me, o, 'ask')  # its live order (Unit.aiOrder is never maintained)
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
                sown = jf
                fb.op('JNull', reg=sown, offset='ok')
                se = fb.reg(cx.t('ent.Entity'))
                fb.op('Mov', dst=se, src=1)
                near_r = b.const('f64', FLEE_R)
                hn, mn_, pn = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
                fb.op('Call3', dst=hn, fun=threat_now, arg0=sown, arg1=se, arg2=near_r)
                fb.op('CallN', dst=mn_, fun=own, args=[sown, se, near_r, 0])
                fb.op('Call1', dst=pn, fun=pw, arg0=0)
                fb.op('Add', dst=mn_, a=mn_, b=pn)
                # in a fight there it heals nothing: it stays only while we hold the place (x terrain), the
                # fight retreat's question; the OVERWHELM margin is for resting next to idle hostiles
                # (Smugglers at Annarekh stayed vs 287k with 192k, fight balance 0.14 -> 0, lost half the army)
                # ... and for INFIGHT_T s after such a flee (map `infl` army -> time): out of contact on the way
                # out it would read the OVERWHELM margin again, turn back and be engaged again
                fx = fb.reg(cx.t('f64'))
                infl = _global_map(fb, b, cx, 'infl')
                inf = fb.reg(cx.t('bool'))
                fb.op('Mov', dst=inf, src=b.call('ent.Entity.isFighting', 0))
                fb.op('Mov', dst=fx, src=_ratio(fb, b, OWN_T))
                fxl, fxs = _uid('fx'), _uid('fxs')
                fb.op('JTrue', cond=inf, offset=fxl)
                iv = b.call('haxe.ds.ObjectMap.get', infl, fb.dyn(0))
                fb.op('JNull', reg=iv, offset=fxs)
                iq = fb.reg(cx.t('f64'))
                fb.op('SafeCast', dst=iq, src=iv)
                fb.op('Sub', dst=iq, a=b.field(_state(fb, b, cx), 'time'), b=iq)
                fb.op('JSLt', a=iq, b=b.const('f64', INFIGHT_T), offset=fxl)
                fb.label(fxs)
                fb.op('Mov', dst=fx, src=_ratio(fb, b, OVERWHELM * OWN_T))
                fb.label(fxl)
                fb.op('Mul', dst=mn_, a=mn_, b=fx)
                fb.op('JSLte', a=hn, b=mn_, offset='stay')
                fxn = _uid('fxn')
                fb.op('JFalse', cond=inf, offset=fxn)
                b.call('haxe.ds.ObjectMap.set', infl, fb.dyn(0), fb.dyn(b.field(_state(fb, b, cx), 'time')))
                fb.label(fxn)
                fb.op('Add', dst=d, a=d, b=b.const('f64', PENALTY))
                heal_log('flee', hn, mn_)
                fb.op('JAlways', offset='ok')
                fb.label('stay')  # log only when hostiles are actually close
                fb.op('JSLte', a=hn, b=b.const('f64', 0), offset='ok')
                heal_log('stay', hn, mn_)
                fb.op('JAlways', offset='ok')
                fb.label('away')
            fb.op('Call4', dst=lvl, fun=unsafe, arg0=1, arg1=me, arg2=sticky, arg3=jf)
            fb.op('JSLte', a=lvl, b=b.const('i32', 0), offset='ok')
            fb.op('JSGt', a=lvl, b=b.const('i32', 1), offset='hard')
            fb.op('Add', dst=d, a=d, b=b.const('f64', DETOUR * DETOUR))  # contested: worth a detour, not a trek
            heal_log('detour', None, None)
            fb.op('JAlways', offset='ok')
            fb.label('hard')
            fb.op('Add', dst=d, a=d, b=b.const('f64', PENALTY))
            heal_log('avoid', None, None)
            fb.label('ok')
            if args[0] == cx.t('logic.state.Warzone'):
                _retreat_clear(fb, b, cx, d, heal_log)
                _retreat_side(fb, b, cx, d)
            _gather_point(fb, b, cx, jf, d, d0, lvl, args[0] == army_t)
            if args[0] == cx.t('logic.state.Warzone'):
                _retreat_commit(fb, b, cx, d, jf)
            fb.end_try(guard)
            fb.op('Ret', ret=d)
            w = fb.build()
            op.df['fun'].value = w
            new_ids.add(w)
        report[f'safe-heal:{caller.split(".")[-1]}'] = len(refs)
    return report


def pick_life(cx, helpers, idle, new_ids):
    """pick-life: worn armies heal instead of joining missions. Vanilla getUnits applies minLife (0.9) only to armies
    with hasSafeRegen, so a Harkonnen Discovery_Sniper at < 50% that sat in a Resupply order at Tsim-Al'rekh was
    pulled (AIOrder.removeUnit) into a Defense of Talwaz against 2 rebels and died; 25% armies went on Annex /
    Pillage. The getUnits calls of the mission callers (tryArmyAction: sieges, checkStructures: Defense,
    checkWorldEvents: Discovery; not checkUnits = the Resupply query) are wrapped: armies with life ratio < PICK_LIFE
    are removed from the result, unless already fighting (isFighting: at the spot, a Defense coordinates it).
    Worn temporary units (no safe regen: they never heal, and disband soon) still defend our structures, as extras:
    at the main base (Defense query priority >= 10: vanilla sends every idle army) they stay in the list; elsewhere
    the checkStructures pickUnits call is wrapped and, once vanilla's pick of healthy armies is non-empty, idle
    (`idle`: in no order) no-regen armies under PICK_LIFE within JOIN_R of the structure are appended (logged
    `lowpick` src=extra). They are never counted toward the required power.
    Logs `lowpick` (a, hp%, src) once per army per PICK_LOG_T s. Original result on any error."""
    gu = cx.fn('logic.ai.AIUnits.getUnits')
    ftypes = {f.findex.value: f.type.value for f in cx.code.functions}
    ft = cx.code.types[gu.type.value].definition
    n = 0
    wrappers = {}
    for caller, want, tag in (('logic.ai.AIMilitary.tryArmyAction', 1, 'siege'),
                              ('logic.ai.AIMilitary.checkStructures', 1, 'defense'),
                              ('logic.ai.AIController.checkWorldEvents', 2, 'discovery')):
        sites = [op for op in cx.fn(caller).ops if op.op.startswith('Call') and op.df.get('fun') is not None
                 and ftypes.get(op.df['fun'].value) == gu.type.value]
        if len(sites) != want:
            raise ValueError(f'pick-life: expected {want} getUnits calls in {caller}, found {len(sites)}')
        for op in sites:
            key = (op.df['fun'].value, tag)
            if key not in wrappers:
                wrappers[key] = _pick_life_wrapper(cx, helpers, ft, gu.type.value, op.df['fun'].value, tag)
                new_ids.add(wrappers[key])
            op.df['fun'].value = wrappers[key]
            n += 1
    n += _defense_extras(cx, helpers, idle, new_ids)
    return {'pick-life': n}


def _defense_extras(cx, helpers, idle, new_ids):
    pk = cx.fn('logic.ai.AIUnits.pickUnits')
    ftypes = {f.findex.value: f.type.value for f in cx.code.functions}
    sites = [op for op in cx.fn('logic.ai.AIMilitary.checkStructures').ops if op.op.startswith('Call')
             and op.df.get('fun') is not None and ftypes.get(op.df['fun'].value) == pk.type.value]
    if len(sites) != 1:
        raise ValueError(f'pick-life: expected 1 pickUnits call in checkStructures, found {len(sites)}')

    ft = cx.code.types[pk.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=pk.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    # rally: a Defense of a structure within RALLY_MIN of the rally's danger D gets only armies already within
    # RALLY_HERE of D (the rest gather first; a Defense elsewhere gets them: the pick-life getUnits wrapper keeps
    # them in the list)
    guard0 = fb.try_()
    rde, ale = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    alv, _ = _vfield(fb, b, 1, 'allyStructure')
    fb.op('JNull', reg=alv, offset='rk_done')
    fb.op('SafeCast', dst=ale, src=fb.dyn(alv))
    cuv, _ = _vfield(fb, b, 1, 'consideredUnits')
    fb.op('JNull', reg=cuv, offset='rk_done')
    cand = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('SafeCast', dst=cand, src=fb.dyn(cuv))
    # a lost cause: conceded by the rally (map `rlygu` within RALLY_COOL) or judged hopeless by aimod_defend (map `dhl`
    # within 30 s, the window in which the rally pass stops a running Defense of it): no Defense trickle into it
    rgq = fb.reg(cx.t('f64'))
    for mname, lim in (('rlygu', RALLY_COOL), ('dhl', 30)):
        nx = _uid('rkn')
        rgv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, mname), fb.dyn(ale))
        fb.op('JNull', reg=rgv, offset=nx)
        fb.op('SafeCast', dst=rgq, src=rgv)
        fb.op('Sub', dst=rgq, a=b.field(_state(fb, b, cx), 'time'), b=rgq)
        fb.op('JSLt', a=rgq, b=b.const('f64', lim), offset='rk_lost')
        fb.label(nx)
    fb.op('JAlways', offset='rk_live')
    fb.label('rk_lost')
    b.call('hl.types.ArrayObj.splice', cand, b.const('i32', 0), b.field(cand, 'length'))
    fb.op('JAlways', offset='rk_done')
    fb.label('rk_live')
    # committed by the rally (map `rlyc` within RALLY_COOL): the whole army goes (vanilla's allIn: every considered
    # army, not just enough for its own estimate: Harkonnen's Eydak commit counted 11 armies, the Defense took 7, the
    # other 4 were walked back to Rabnih by a Patrol and the defense read even and was conceded 10 s later)
    cmv2 = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rlyc'), fb.dyn(ale))
    fb.op('JNull', reg=cmv2, offset='rk_nc')
    fb.op('SafeCast', dst=rgq, src=cmv2)
    fb.op('Sub', dst=rgq, a=b.field(_state(fb, b, cx), 'time'), b=rgq)
    fb.op('JSGt', a=rgq, b=b.const('f64', RALLY_COOL), offset='rk_nc')
    # ... the army the commit counted: vanilla's idle list has no distance limit (getUnits by life / supply /
    # priority, pickUnits takes the nearest first and stops at its estimate), all-in would pull every idle army of
    # the map off other fronts; keep those within RALLY_R of D (the rally's measure)
    ci = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=ci, src=b.field(cand, 'length'))
    b.loop_head('rk_cut')
    fb.op('JSLte', a=ci, b=b.const('i32', 0), offset='rk_cutd')
    fb.op('Sub', dst=ci, a=ci, b=b.const('i32', 1))
    cu = b.cast(b.call('hl.types.ArrayObj.getDyn', cand, ci), 'ent.Entity')
    fb.op('JNull', reg=cu, offset='rk_cut')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', cu, ale), b=b.const('f64', RALLY_R), offset='rk_cut')
    b.call('hl.types.ArrayObj.splice', cand, ci, b.const('i32', 1))
    fb.op('JAlways', offset='rk_cut')
    fb.label('rk_cutd')
    aiv, aii = _vfield(fb, b, 1, 'allIn')
    tb = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=tb, value=True)
    nb = fb.reg(fb.regs[aiv])
    fb.op('ToDyn', dst=nb, src=tb)  # Null<Bool>, the way the compiler boxes it
    fb.op('SetField', obj=1, field=aii, src=nb)
    owf = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=owf, offset='rk_nc')
    _throttle(fb, b, cx, 'dall', ale, 10, 'rk_nc')
    _log_ev(fb, b, cx, helpers, 'dall', [('f', fb.get(owf, 'kind')), ('s', ale), ('n', b.field(cand, 'length'))])
    fb.label('rk_nc')
    rdz = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rly'), fb.dyn(b.field(b.field(0, 'controller'), 'owner')))
    fb.op('JNull', reg=rdz, offset='rk_done')
    fb.op('SafeCast', dst=rde, src=rdz)
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ale, rde), b=b.const('f64', RALLY_MIN), offset='rk_done')
    rpe = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=rpe)
    rpv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rlyp'), fb.dyn(b.field(b.field(0, 'controller'), 'owner')))
    fb.op('JNull', reg=rpv, offset='rk_np')
    fb.op('SafeCast', dst=rpe, src=rpv)
    fb.label('rk_np')
    rk = fb.reg(cx.t('i32'))
    rlm = _global_map(fb, b, cx, 'rallied')
    rq, rnow = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=rnow, src=b.field(_state(fb, b, cx), 'time'))
    fb.op('Mov', dst=rk, src=b.field(cand, 'length'))
    b.loop_head('rk')  # backwards: removal shifts the tail
    fb.op('JSLte', a=rk, b=b.const('i32', 0), offset='rk_done')
    fb.op('Sub', dst=rk, a=rk, b=b.const('i32', 1))
    rv = b.call('hl.types.ArrayObj.getDyn', cand, rk)
    fb.op('JNull', reg=rv, offset='rk')
    # an army already at D (within RALLY_HERE) may defend it; any other (walking to the rally point, or arrived
    # there) waits for the gathered force: Fremen's Defense of Ulmara took 2 armies standing at the rally point
    # Tabr, 285 away, and went in 2 v 6
    rva = b.cast(rv, 'ent.Army')
    fb.op('JNull', reg=rva, offset='rk')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', rva, rde), b=b.const('f64', RALLY_HERE), offset='rk_rm')
    fb.op('JNull', reg=rpe, offset='rk_rp')  # at the rally point (within RALLY_HERE of D too): the gathered force
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', rva, rpe), b=b.const('f64', RALLY_AT), offset='rk_rm')
    fb.label('rk_rp')
    rsv = b.call('haxe.ds.ObjectMap.get', rlm, rv)
    fb.op('JNull', reg=rsv, offset='rk')
    fb.op('SafeCast', dst=rq, src=rsv)
    fb.op('Sub', dst=rq, a=rnow, b=rq)
    fb.op('JSGte', a=rq, b=b.const('f64', RALLY_HOLD), offset='rk')  # not walking to the rally point (anymore)
    fb.label('rk_rm')
    b.call('hl.types.ArrayObj.remove', cand, rv)
    fb.op('JAlways', offset='rk')
    fb.label('rk_done')
    fb.end_try(guard0)
    fb.op('Call2', dst=res, fun=sites[0].df['fun'].value, arg0=0, arg1=1)
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    fb.op('JSLte', a=b.field(res, 'length'), b=b.const('i32', 0), offset='end')
    al, _ = _vfield(fb, b, 1, 'allyStructure')
    fb.op('JNull', reg=al, offset='end')
    s = fb.reg(cx.t('ent.Entity'))
    fb.op('SafeCast', dst=s, src=fb.dyn(al))
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    my_armies, mlen = _my_armies(fb, b, fac, 'end')
    i = fb.reg(cx.t('i32'))
    ok = fb.reg(cx.t('bool'))
    floor, r = _ratio(fb, b, PICK_LIFE), b.const('f64', JOIN_R)
    lr = fb.reg(cx.t('f64'))
    a = _army_loop(fb, b, my_armies, mlen, i, 'l', 'end')
    fb.op('JTrue', cond=b.call('ent.Unit.hasSafeRegen', a), offset='l')
    fb.op('Mov', dst=lr, src=b.call('ent.Entity.get_lifeRatio', a))
    fb.op('JSGte', a=lr, b=floor, offset='l')
    fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', res, fb.dyn(a)), offset='l')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', a, s), b=r, offset='l')
    fb.op('Call2', dst=ok, fun=idle, arg0=a, arg1=orders)
    fb.op('JFalse', cond=ok, offset='l')
    b.call('hl.types.ArrayObj.push', res, fb.dyn(a))
    _log_ev(fb, b, cx, helpers, 'lowpick', [('f', fb.get(fac, 'kind')), ('a', a), ('hp%', lr), ('src', 'extra')])
    fb.op('JAlways', offset='l')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    sites[0].df['fun'].value = w
    new_ids.add(w)
    return 1


def _pick_life_wrapper(cx, helpers, ft, fun_type, inner, tag):
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=fun_type)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    if tag == 'defense':
        # a Defense of our structure takes armies by their absolute supply (not `short`: below the walk home while
        # losing supply, below), not vanilla's minSupply 0.9 share: a max-supply rise (Atreides 65 -> 125) left every
        # full-health army at home under 90% and out of the Sandsud Defense. The query args are a fresh object per
        # call (HAI.getDefaultUnitQueryArgs)
        g0 = fb.try_()
        msv, msi = _vfield(fb, b, 1, 'minSupply')
        zs = fb.reg(fb.regs[msv])
        fb.op('ToDyn', dst=zs, src=b.const('f64', 0))
        fb.op('SetField', obj=1, field=msi, src=zs)
        fb.end_try(g0)
    fb.op('Call2', dst=res, fun=inner, arg0=0, arg1=1)
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.field(res, 'length'))
    zi, one = b.const('i32', 0), b.const('i32', 1)
    floor = _ratio(fb, b, PICK_LIFE)
    lr = fb.reg(cx.t('f64'))
    if tag == 'defense':
        prio = fb.reg(cx.t('i32'))
        fb.op('Mov', dst=prio, src=zi)
        pv, _ = _vfield(fb, b, 1, 'priority')
        if fb.regs[pv] == cx.t('i32'):
            fb.op('Mov', dst=prio, src=pv)
        else:  # Null<Int>
            fb.op('JNull', reg=pv, offset='pdone')
            fb.op('SafeCast', dst=prio, src=fb.dyn(pv))
            fb.label('pdone')
    b.loop_head('l')  # backwards: removal shifts the tail
    fb.op('JSLte', a=i, b=zi, offset='end')
    fb.op('Sub', dst=i, a=i, b=one)
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', res, i), 'ent.Army')
    fb.op('JNull', reg=a, offset='l')
    if tag == 'defense':
        # a rallying army is still a defender: the Defense pick drops it only for a structure next to the rally's
        # danger D (_defense_extras); Atreides' Tuo-tar Defense found 0 candidates while all were held for Tuonah
        rlv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'rallied'), fb.dyn(a))
        fb.op('JNull', reg=rlv, offset='nrl')
        rlq = fb.reg(cx.t('f64'))
        fb.op('SafeCast', dst=rlq, src=rlv)
        fb.op('Sub', dst=rlq, a=b.field(_state(fb, b, cx), 'time'), b=rlq)
        fb.op('JSLt', a=rlq, b=b.const('f64', RALLY_HOLD), offset='nwh')  # walking to the rally point
        fb.label('nrl')
    whr = fb.reg(cx.t('bool'))
    fb.op('Call1', dst=whr, fun=helpers['wormheld'], arg0=a)
    fb.op('JFalse', cond=whr, offset='nwh')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))  # waits on the rock while the worm is near (worm.py)
    _throttle(fb, b, cx, 'whold', a, 10, 'l')
    _log_ev(fb, b, cx, helpers, 'whold', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')), ('a', a),
                                          ('src', tag)])
    fb.op('JAlways', offset='l')
    fb.label('nwh')
    if tag == 'defense':
        shf = b.field(b.field(0, 'controller'), 'owner')
        fb.op('JNull', reg=shf, offset='nshort')
        sh = fb.reg(cx.t('bool'))
        fb.op('Call2', dst=sh, fun=helpers['short'], arg0=shf, arg1=a)
        fb.op('JFalse', cond=sh, offset='nshort')
        b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
        _throttle(fb, b, cx, 'lowpick', a, PICK_LOG_T, 'l')
        _log_ev(fb, b, cx, helpers, 'lowpick', [('f', fb.get(shf, 'kind')), ('a', a),
                                                ('hp%', b.call('ent.Entity.get_lifeRatio', a)), ('src', 'short')])
        fb.op('JAlways', offset='l')
        fb.label('nshort')
    if tag in ('siege', 'defense'):
        # the last army of one of our Military orders in Action finishes an occupation alone (rules/release.py split
        # the rest off): taking it empties the order (removeUnit cancels it). A main-base defense still may
        kords = b.field(b.field(b.field(0, 'controller'), 'aiOrders'), 'orders')
        fb.op('JNull', reg=kords, offset='nkeep')
        if tag == 'defense':
            fb.op('JSGte', a=prio, b=b.const('i32', 10), offset='nkeep')
        kk, kx = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
        fb.op('Mov', dst=kk, src=b.field(kords, 'length'))
        b.loop_head('kp')
        fb.op('JSLte', a=kk, b=zi, offset='nkeep')
        fb.op('Sub', dst=kk, a=kk, b=one)
        ko = b.cast(b.call('hl.types.ArrayObj.getDyn', kords, kk), 'logic.ai.AIOrder')
        fb.op('JNull', reg=ko, offset='kp')
        kou = b.field(ko, 'units')
        fb.op('JNull', reg=kou, offset='kp')
        fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', kou, fb.dyn(a)), offset='kp')
        fb.op('EnumIndex', dst=kx, value=b.field(ko, 'type'))
        fb.op('JNotEq', a=kx, b=b.const('i32', MILITARY), offset='nkeep')
        fb.op('JSGt', a=b.field(kou, 'length'), b=one, offset='nkeep')
        fb.op('JSLt', a=b.field(ko, 'phase'), b=b.const('i32', ACTION), offset='nkeep')
        b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
        fb.op('JAlways', offset='l')
        fb.label('nkeep')
    if tag == 'siege':
        # a siege launch takes no army from another Military order of 2+ armies before Action: removeUnit cancels
        # that whole order (Fremen's 8-army Liberate of Tuonah, 117 s in Regroup, died when a prio-3 Annex of
        # Arsmara took one of its armies). Defense still may (higher on the ladder)
        ords = b.field(b.field(b.field(0, 'controller'), 'aiOrders'), 'orders')
        fb.op('JNull', reg=ords, offset='nown')
        k, ix = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
        fb.op('Mov', dst=k, src=b.field(ords, 'length'))
        b.loop_head('ko')
        fb.op('JSLte', a=k, b=zi, offset='nown')
        fb.op('Sub', dst=k, a=k, b=one)
        o = b.cast(b.call('hl.types.ArrayObj.getDyn', ords, k), 'logic.ai.AIOrder')
        fb.op('JNull', reg=o, offset='ko')
        ou = b.field(o, 'units')
        fb.op('JNull', reg=ou, offset='ko')
        fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', ou, fb.dyn(a)), offset='ko')
        fb.op('EnumIndex', dst=ix, value=b.field(o, 'type'))
        fb.op('JNotEq', a=ix, b=b.const('i32', MILITARY), offset='nown')
        fb.op('JSLt', a=b.field(ou, 'length'), b=b.const('i32', 2), offset='nown')
        fb.op('JSGte', a=b.field(o, 'phase'), b=b.const('i32', ACTION), offset='nown')
        b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
        _throttle(fb, b, cx, 'keepord', a, PICK_LOG_T, 'l')
        _log_ev(fb, b, cx, helpers, 'keepord', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')),
                                                ('a', a), ('sa', b.cast(fb.get(o, 'siegeAction'), 'String')),
                                                ('n', b.field(ou, 'length')), ('ph', b.field(o, 'phase'))])
        fb.op('JAlways', offset='l')
        fb.label('nown')
    fb.op('Mov', dst=lr, src=b.call('ent.Entity.get_lifeRatio', a))
    fb.op('JSGte', a=lr, b=floor, offset='l')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', a), offset='l')
    if tag == 'defense':  # main base defense (priority >= 10) takes every idle army: worn temporary units too
        fb.op('JTrue', cond=b.call('ent.Unit.hasSafeRegen', a), offset='rm')
        fb.op('JSGte', a=prio, b=b.const('i32', 10), offset='l')
        fb.label('rm')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
    _throttle(fb, b, cx, 'lowpick', a, PICK_LOG_T, 'l')
    _log_ev(fb, b, cx, helpers, 'lowpick', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')), ('a', a),
                                            ('hp%', lr), ('src', tag)])
    fb.op('JAlways', offset='l')
    fb.label('end')
    if tag == 'siege':
        # map `sidle` faction -> size of this idle list: empty = vanilla's NoAvailableArmy (tryArmyAction), which
        # the stuck counter (siege.py) must not blame on the target
        sn = fb.reg(cx.t('i32'))
        fb.op('Mov', dst=sn, src=b.const('i32', 0))  # fresh load: `zi` is set after the JNull to 'end'
        fb.op('JNull', reg=res, offset='sidset')
        fb.op('Mov', dst=sn, src=b.field(res, 'length'))
        fb.label('sidset')
        b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'sidle'),
               fb.dyn(b.field(b.field(0, 'controller'), 'owner')), fb.dyn(sn))
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    return fb.build()


def no_regen_heal(cx, helpers, new_ids):
    """no-regen-heal: vanilla checkUnits orders Resupply(1,1) for any army with life < valueCache[1063] (0.9), but
    the order's termination test (closure f40841) checks life only when `hasSafeRegen()` (attribute
    SafeRegen_MRatio > 0, no NoSafeRegen): temporary units (Discovery_* recruits: Temporary_Trait, Scavenged
    ornithopters, NoHealthRegen, H_Sting) never recover life, so with full supply the order ends Success in phase 1
    and is re-issued every tick (Harkonnen Discovery_Sniper < 50% cycling Tsim-Al'rekh / Carthag / Burron every
    ~0.5 s and never moving). The checkUnits getUnits call that feeds the Resupply loop (the second one; the first is
    the upkeep disband) is wrapped: armies without safe regen whose supply needs nothing (no supply, or supply >=
    valueCache[1062]) are removed from the result; one that needs supply still gets its Resupply (it ends once
    refilled). Also removed: an army above the life trigger that gains supply where it stands (Army.isGainingSupply):
    its Resupply would only hold it there (logs `selfsup` a, sup, ms). Logs `noregen` (a, hp%) once per army per
    PICK_LOG_T s. Original result on any error."""
    gu = cx.fn('logic.ai.AIUnits.getUnits')
    ftypes = {f.findex.value: f.type.value for f in cx.code.functions}
    ft = cx.code.types[gu.type.value].definition
    sites = [op for op in cx.fn('logic.ai.AIUnits.checkUnits').ops if op.op.startswith('Call')
             and op.df.get('fun') is not None and ftypes.get(op.df['fun'].value) == gu.type.value]
    if len(sites) != 2:
        raise ValueError(f'no-regen-heal: expected 2 getUnits calls in checkUnits, found {len(sites)}')
    site = sites[1]
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=gu.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('Call2', dst=res, fun=site.df['fun'].value, arg0=0, arg1=1)
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    # supply trigger valueCache[1062] (0.9 if unreadable)
    sup_t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=sup_t, src=_ratio(fb, b, 0.9))
    c = fb.reg(cx.t('$Const'))
    fb.op('GetGlobal', dst=c, **{'global': cx.global_of('$Const')})
    vc = b.cast(b.field(c, 'valueCache'), 'hl.types.ArrayBytes_Float')
    fb.op('JNull', reg=vc, offset='vc_done')
    v = b.call('hl.types.ArrayBytes_Float.getDyn', vc, b.const('i32', 1062))
    fb.op('JNull', reg=v, offset='vc_done')
    fb.op('SafeCast', dst=sup_t, src=v)
    fb.label('vc_done')
    life_t = fb.reg(cx.t('f64'))  # life trigger valueCache[1063] (0.9 if unreadable)
    fb.op('Mov', dst=life_t, src=_ratio(fb, b, 0.9))
    fb.op('JNull', reg=vc, offset='lt_done')
    lv = b.call('hl.types.ArrayBytes_Float.getDyn', vc, b.const('i32', 1063))
    fb.op('JNull', reg=lv, offset='lt_done')
    fb.op('SafeCast', dst=life_t, src=lv)
    fb.label('lt_done')
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.field(res, 'length'))
    zi, one = b.const('i32', 0), b.const('i32', 1)
    full = _ratio(fb, b, 1)
    sr = fb.reg(cx.t('f64'))
    b.loop_head('l')
    fb.op('JSLte', a=i, b=zi, offset='end')
    fb.op('Sub', dst=i, a=i, b=one)
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', res, i), 'ent.Army')
    fb.op('JNull', reg=a, offset='l')
    whr = fb.reg(cx.t('bool'))
    fb.op('Call1', dst=whr, fun=helpers['wormheld'], arg0=a)
    fb.op('JFalse', cond=whr, offset='nwh')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))  # waits on the rock while the worm is near (worm.py)
    _throttle(fb, b, cx, 'whold', a, 10, 'l')
    _log_ev(fb, b, cx, helpers, 'whold', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')), ('a', a),
                                          ('src', 'resupply')])
    fb.op('JAlways', offset='l')
    fb.label('nwh')
    # supply only (life above the trigger) and refilling where it stands (Army.isGainingSupply: not fighting, a
    # supplying structure in its zone or a neighbour): the order would only hold it there, out of every defense
    # (Atreides' 6 armies at Sandkus, 82/125 after a max-supply rise, in Resupply while Harkonnen took Sandsud)
    fb.op('JSLt', a=b.call('ent.Entity.get_lifeRatio', a), b=life_t, offset='ngain')
    fb.op('JFalse', cond=b.call('ent.Army.isGainingSupply', a), offset='ngain')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
    _throttle(fb, b, cx, 'selfsup', a, PICK_LOG_T, 'l')
    _log_ev(fb, b, cx, helpers, 'selfsup', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')), ('a', a),
                                            ('sup', b.call('ent.Army.get_supply', a)),
                                            ('ms', b.call('ent.Army.get_maxSupply', a))])
    fb.op('JAlways', offset='l')
    fb.label('ngain')
    fb.op('JTrue', cond=b.call('ent.Unit.hasSafeRegen', a), offset='l')
    lr = b.call('ent.Entity.get_lifeRatio', a)
    fb.op('JSGte', a=lr, b=full, offset='l')
    fb.op('JFalse', cond=b.call('ent.Army.hasSupply', a), offset='drop')
    ms = b.call('ent.Army.get_maxSupply', a)
    fb.op('JSLte', a=ms, b=b.const('f64', 0), offset='drop')
    fb.op('SDiv', dst=sr, a=b.call('ent.Army.get_supply', a), b=ms)
    fb.op('JSLt', a=sr, b=sup_t, offset='l')  # needs supply: vanilla's Resupply refills it and ends
    fb.label('drop')
    b.call('hl.types.ArrayObj.remove', res, fb.dyn(a))
    _throttle(fb, b, cx, 'noregen', a, PICK_LOG_T, 'l')
    _log_ev(fb, b, cx, helpers, 'noregen', [('f', fb.get(b.call('ent.Entity.get_owner', a), 'kind')), ('a', a),
                                            ('hp%', lr)])
    fb.op('JAlways', offset='l')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    site.df['fun'].value = w
    new_ids.add(w)
    return {'no-regen-heal': 1}
