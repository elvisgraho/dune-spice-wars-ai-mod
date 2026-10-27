"""Fight-retreat eligibility and terrain, supply and mission balance adjustments."""
from rules.common import *  # noqa: F401,F403
from rules import bkstate as bks
from rules.bkcamp.shared import BC_FF_GO_T

MISSION_BC_T = 20  # s: an army the base-kill campaign claimed this recently is on a mission


def build_mission(cx):
    """aimod_mission(fac, a) -> a is a unit of one of fac's Military orders (siege, hunt, raid, defense), or an army
    the base-kill campaign claimed within MISSION_BC_T (rules/bkill.py `bcmc`: marching to the strike point has no
    order; the low-supply recall pulled such armies home, `recall` x 11 next to Arrakeen). Army.aiOrder is unreliable
    (null on many AI besiegers and on our hunts), so the order list is scanned."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Army')], cx.t('bool'))
    b = B(fb)
    res = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=res, value=False)
    guard = fb.try_()
    mbv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.CLAIMED), fb.dyn(1))
    fb.op('JNull', reg=mbv, offset='nobc')
    mbq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=mbq, src=mbv)
    fb.op('Sub', dst=mbq, a=b.field(_state(fb, b, cx), 'time'), b=mbq)
    fb.op('JSGt', a=mbq, b=b.const('f64', MISSION_BC_T), offset='nobc')
    fb.op('Bool', dst=res, value=True)
    fb.op('JAlways', offset='end')
    fb.label('nobc')
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
    so checkPower is vanilla's fight-age test alone (AI_Fight time >= AI_UnitMicroManagement_PowerBalanceCheck_Delay, 5 s). A lost fight then
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
    Military one -> 0 (log act `disengage`); not while one of ours there is on a Defense order.
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
    # a deliberate 0 (latch / forced retreat below): the raise-only passes after `end` (bkbal, bkdr) leave it alone
    # (review 2026-10-25: they raised a latched direct-raze fight back in the same tick)
    zforce = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=zforce, value=False)
    guard = fb.try_()
    # latch (docs/INPUT-SPAM-TODO.md 5): a forced retreat of ours (disengage / trespass: balance 0) holds this fight at 0
    # for RETREAT_LATCH_T s for this faction (map `rlatch` per faction: warzone -> time), not flipping back to 1.0 while
    # its armies walk out (the Flee / Attack alternation in two fights followed trespass rows)
    fb.op('JNull', reg=0, offset='lt_d')
    fb.op('JNull', reg=1, offset='lt_d')
    ltv = b.call('haxe.ds.ObjectMap.get', _fac_map(fb, b, cx, 'rlatch', 1), fb.dyn(0))
    fb.op('JNull', reg=ltv, offset='lt_d')
    ltq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=ltq, src=ltv)
    fb.op('Sub', dst=ltq, a=b.field(_state(fb, b, cx), 'time'), b=ltq)
    fb.op('JSGte', a=ltq, b=b.const('f64', RETREAT_LATCH_T), offset='lt_d')
    fb.op('Mov', dst=bal, src=b.const('f64', 0))
    fb.op('Bool', dst=zforce, value=True)
    fb.op('JAlways', offset='end')
    fb.label('lt_d')
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
    # ... and the side fight's enemy doesn't outweigh the capture's holders: a relief stack is no side fight (Atreides'
    # Tabdah raid held at raw 0.03 vs 237k, then 384k arrived: 3 of 9 dead, 100% lost, match 2026-10-04 22:53)
    fb.op('JSGt', a=en, b=occ, offset='csl')
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
    dfn = fb.reg(cx.t('bool'))  # one of ours there on a Defense order
    fb.op('Bool', dst=dfn, value=False)
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
    fb.op('JNotEq', a=oix, b=b.const('i32', DEFENSE), offset='npl')
    fb.op('Bool', dst=dfn, value=True)
    fb.op('JAlways', offset='npl')
    fb.label('nprs')
    fb.op('Bool', dst=rsp, value=True)
    fb.op('JAlways', offset='npl')
    fb.label('npdone')
    # ... or a Defense order of ours (with armies, wherever they stand: the one walking in is not in the warzone yet)
    # for a structure within FLEE_R of this fight (Smugglers' 1-army Defense cancelled 168 times from 20:51 while
    # retreating armies stood at the fight, match 2026-10-04 20:27)
    dords = b.field(b.field(b.field(1, 'aiController'), 'aiOrders'), 'orders')
    fb.op('JNull', reg=dords, offset='dfo_end')
    dk, dtx = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=dk, src=b.field(dords, 'length'))
    b.loop_head('dfo')
    fb.op('JSLte', a=dk, b=b.const('i32', 0), offset='dfo_end')
    fb.op('Sub', dst=dk, a=dk, b=b.const('i32', 1))
    dor = b.cast(b.call('hl.types.ArrayObj.getDyn', dords, dk), 'logic.ai.AIOrder')
    fb.op('JNull', reg=dor, offset='dfo')
    dot = b.field(dor, 'type')
    fb.op('EnumIndex', dst=dtx, value=dot)
    fb.op('JNotEq', a=dtx, b=b.const('i32', MILITARY), offset='dfo_df')
    # ... or a Military order of ours engaged there (Engage / Action on a target within LOCAL of this fight), whatever
    # its armies read per army: Atreides' 7-army Pillage of Tabdalus at order balance 12 was cut off by `disengage`
    # (a resupplying army stood near, the raid's armies weren't matched; match 2026-10-23 22:01)
    fb.op('JSLt', a=b.field(dor, 'phase'), b=b.const('i32', REGROUP + 1), offset='dfo')
    dmt0 = b.call('logic.ai.AIOrder.getTarget', dor)
    dmt = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=dmt, src=b.cast(fb.dyn(dmt0), 'ent.Entity'))
    fb.op('JNotNull', reg=dmt, offset='dfo_t')
    # a contest hunt (ArmyFight on an army group: no structure target) stands for the village it defends (map `hcon`):
    # Harkonnen's 7-army contest of Arklon (210k vs 150k) was cut off 6 s after its start while its armies walked in,
    # then fed one by one into the 266k there (match 2026-10-24 00:40, 34:46)
    dcv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'hcon'), fb.dyn(dor))
    fb.op('JNull', reg=dcv, offset='dfo')
    fb.op('Mov', dst=dmt, src=b.cast(dcv, 'ent.Entity'))
    fb.op('JNull', reg=dmt, offset='dfo')
    fb.label('dfo_t')
    fb.op('JNull', reg=b.field(dor, 'units'), offset='dfo')
    fb.op('JSLte', a=b.field(b.field(dor, 'units'), 'length'), b=b.const('i32', 0), offset='dfo')
    fb.op('Sub', dst=ex, a=b.field(dmt, 'posx'), b=ncx)
    fb.op('Sub', dst=ey, a=b.field(dmt, 'posy'), b=ncy)
    fb.op('Mul', dst=ex, a=ex, b=ex)
    fb.op('Mul', dst=ey, a=ey, b=ey)
    fb.op('Add', dst=ex, a=ex, b=ey)
    fb.op('JSLte', a=ex, b=b.const('f64', LOCAL * LOCAL), offset='end')  # our mission there: its own rules decide
    fb.op('JAlways', offset='dfo')
    fb.label('dfo_df')
    fb.op('JNotEq', a=dtx, b=b.const('i32', DEFENSE), offset='dfo')
    dou = b.field(dor, 'units')
    fb.op('JNull', reg=dou, offset='dfo')
    fb.op('JSLte', a=b.field(dou, 'length'), b=b.const('i32', 0), offset='dfo')
    dst_ = fb.reg(cx.t('ent.Entity'))
    fb.op('EnumField', dst=dst_, value=dot, construct=DEFENSE, field=0)
    fb.op('JNull', reg=dst_, offset='dfo')
    fb.op('Sub', dst=ex, a=b.field(dst_, 'posx'), b=ncx)
    fb.op('Sub', dst=ey, a=b.field(dst_, 'posy'), b=ncy)
    fb.op('Mul', dst=ex, a=ex, b=ex)
    fb.op('Mul', dst=ey, a=ey, b=ey)
    fb.op('Add', dst=ex, a=ex, b=ey)
    fb.op('JSGt', a=ex, b=b.const('f64', FLEE_R * FLEE_R), offset='dfo')
    fb.op('Bool', dst=dfn, value=True)
    fb.label('dfo_end')
    # a campaign capture or raze of ours there (rules/bkcamp: its armies have no order, so `mission` / the Military
    # test don't see them): its own rules decide (match 73: Fremen's foothold capture of Sadnih was pulled out twice
    # when vanilla's Resupply took 4 of its armies). Capture: our capture village (bkstate FOOT_ANNEX) within LOCAL of
    # the fight, its pack launched within BC_FF_GO_T s (FOOT_GO); raze: ours live (RAZE_ACT within BK_DR_LIVE s) and
    # the campaign base within BK_BAL_R
    cgt = b.field(_state(fb, b, cx), 'time')
    cgv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.FOOT_ANNEX), fb.dyn(1))
    fb.op('JNull', reg=cgv, offset='cg_rz')
    cge = fb.reg(cx.t('ent.Entity'))
    fb.op('SafeCast', dst=cge, src=cgv)
    fb.op('JNull', reg=cge, offset='cg_rz')
    _dist2(fb, b, cge, ncx, ncy, ex, ey)
    fb.op('JSGt', a=ex, b=b.const('f64', LOCAL * LOCAL), offset='cg_rz')
    cgq = _age(fb, b, cx, _global_map(fb, b, cx, bks.FOOT_GO), cge, cgt, 'cg_rz')
    fb.op('JSLte', a=cgq, b=b.const('f64', BC_FF_GO_T), offset='end')
    fb.label('cg_rz')
    cgl = _bk_target(fb, b, cx, 1, 'cg_d')
    cgb = b.call('ent.Faction.get_mainBase', cgl)
    fb.op('JNull', reg=cgb, offset='cg_d')
    cgbe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=cgbe, src=cgb)
    _dist2(fb, b, cgbe, ncx, ncy, ex, ey)
    fb.op('JSGt', a=ex, b=b.const('f64', BK_BAL_R * BK_BAL_R), offset='cg_d')
    cgr = _age(fb, b, cx, _global_map(fb, b, cx, bks.RAZE_ACT), 1, cgt, 'cg_d')
    fb.op('JSLte', a=cgr, b=b.const('f64', BK_DR_LIVE), offset='end')
    fb.label('cg_d')
    dact = fb.reg(cx.t('String'))
    fb.op('Mov', dst=dact, src=fb.string('disengage'))
    # a Defense of ours there (vs rebels / raiders: no power counted, raw 1.0) fights on: one healing army there made
    # it retreat every tick, checkStructures re-sent the rest (Harkonnen at Fa-nit vs Rebels, 85 Defense cancel /
    # re-order cycles from 19:29, match 2026-10-04 19:36)
    fb.op('JTrue', cond=dfn, offset='end')
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
    fb.op('Bool', dst=zforce, value=True)
    b.call('haxe.ds.ObjectMap.set', _fac_map(fb, b, cx, 'rlatch', 1), fb.dyn(0),
           fb.dyn(b.field(_state(fb, b, cx), 'time')))  # the latch above
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
    # base Raze (the base-kill campaign): a fight within BK_BAL_R of the main base our Military Raze order in Engage /
    # Action targets, with one of its armies within FLEE_R of the centroid, takes at least that order's live balance
    # (vanilla getOrderPowerBalance: all its armies vs the defenders, the base included), up or down. The first armies
    # to arrive fought alone at raw 0.03 and the retreat cancelled Fremen's 18-army Raze of Arrakeen while the order
    # stood at 5.6 : 1 (match 36). Logs `bkbal`
    g3 = fb.try_()
    fb.op('JTrue', cond=zforce, offset='kb_end')
    kctl = b.field(1, 'aiController')
    fb.op('JNull', reg=kctl, offset='kb_end')
    kaiu = b.field(kctl, 'aiUnits')
    fb.op('JNull', reg=kaiu, offset='kb_end')
    kords = b.field(b.field(kctl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=kords, offset='kb_end')
    kc = b.call('logic.state.Warzone.get_centroid', 0)
    fb.op('JNull', reg=kc, offset='kb_end')
    kcx, kcy = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=kcx, src=b.field(kc, 'x'))
    fb.op('Mov', dst=kcy, src=b.field(kc, 'y'))
    kk, kx = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    kdx, kdy, kob = (fb.reg(cx.t('f64')) for _ in range(3))
    kse = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=kk, src=b.field(kords, 'length'))
    b.loop_head('kbl')
    fb.op('JSLte', a=kk, b=b.const('i32', 0), offset='kb_end')
    fb.op('Sub', dst=kk, a=kk, b=b.const('i32', 1))
    ko = b.cast(b.call('hl.types.ArrayObj.getDyn', kords, kk), 'logic.ai.AIOrder')
    fb.op('JNull', reg=ko, offset='kbl')
    fb.op('JSLt', a=b.field(ko, 'phase'), b=b.const('i32', ACTION - 1), offset='kbl')
    fb.op('JSGt', a=b.field(ko, 'phase'), b=b.const('i32', ACTION), offset='kbl')
    fb.op('EnumIndex', dst=kx, value=b.field(ko, 'type'))
    fb.op('JNotEq', a=kx, b=b.const('i32', MILITARY), offset='kbl')
    # any siege order of ours on a structure (user 2026-10-25: Atreides' Pillage of Arsnin at order balance 2.0 was
    # cancelled by a fight at the village reading 0.58 x terrain 0.8 = 0.46, no enemy army there: the warzone sees
    # the village's turrets / militia but not the rest of the order; the armies then idled in enemy land)
    ktt = b.field(ko, 'targetType')
    fb.op('JNull', reg=ktt, offset='kbl')
    fb.op('EnumIndex', dst=kx, value=ktt)
    fb.op('JNotEq', a=kx, b=b.const('i32', T_STRUCT), offset='kbl')
    kst = b.cast(b.call('logic.ai.AIOrder.getTarget', ko), 'ent.Structure')
    fb.op('JNull', reg=kst, offset='kbl')
    fb.op('Mov', dst=kse, src=kst)
    krr = fb.reg(cx.t('f64'))
    kmbf = fb.reg(cx.t('bool'))  # a main base: two-sided; a village: raise only (review 2026-10-25)
    fb.op('Bool', dst=kmbf, value=False)
    fb.op('Mov', dst=krr, src=b.const('f64', SITE_WZ_R * SITE_WZ_R))  # a village / site: the fight at it
    kow = b.call('ent.Entity.get_owner', kse)
    fb.op('JNull', reg=kow, offset='kb_v')
    kmb = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=kmb, src=b.call('ent.Faction.get_mainBase', kow))
    fb.op('JNotEq', a=kmb, b=kse, offset='kb_v')
    fb.op('Mov', dst=krr, src=b.const('f64', BK_BAL_R * BK_BAL_R))  # a main base: its guns reach far
    fb.op('Bool', dst=kmbf, value=True)
    fb.op('JAlways', offset='kb_r')
    fb.label('kb_v')
    # a village: in Action only (in Engage the order counts armies still walking in), never a sietch / renegade base
    # (`sbal` above caps those at the order balance on purpose), never over a deliberate 0 (trespass / disengage /
    # pursuit / trivial / recall pulls)
    fb.op('JNotEq', a=b.field(ko, 'phase'), b=b.const('i32', ACTION), offset='kbl')
    _strong_site(fb, b, kst, 'kbl')
    fb.op('JSLte', a=bal, b=b.const('f64', 0), offset='kb_end')
    fb.label('kb_r')
    fb.op('Sub', dst=kdx, a=b.field(kse, 'posx'), b=kcx)
    fb.op('Sub', dst=kdy, a=b.field(kse, 'posy'), b=kcy)
    fb.op('Mul', dst=kdx, a=kdx, b=kdx)
    fb.op('Mul', dst=kdy, a=kdy, b=kdy)
    fb.op('Add', dst=kdx, a=kdx, b=kdy)
    fb.op('JSGt', a=kdx, b=krr, offset='kbl')
    kun = b.field(ko, 'units')
    fb.op('JNull', reg=kun, offset='kbl')
    ku = _army_loop(fb, b, kun, b.field(kun, 'length'), kx, 'kbu', 'kbl')
    fb.op('Sub', dst=kdx, a=b.field(ku, 'posx'), b=kcx)
    fb.op('Sub', dst=kdy, a=b.field(ku, 'posy'), b=kcy)
    fb.op('Mul', dst=kdx, a=kdx, b=kdx)
    fb.op('Mul', dst=kdy, a=kdy, b=kdy)
    fb.op('Add', dst=kdx, a=kdx, b=kdy)
    fb.op('JSGt', a=kdx, b=b.const('f64', BK_BAL_NEAR * BK_BAL_NEAR), offset='kbu')
    fb.op('Mov', dst=kob, src=b.call('logic.ai.AIUnits.getOrderPowerBalance', kaiu, ko))
    # two-sided (match 40: Fremen's Razes fought on at local raw 2-7 while the base's own guns, which the warzone
    # doesn't count, took the order from 0.85 to 0.003: 18 of 24 armies dead): the order's balance is the fight's
    fb.op('JSLte', a=kob, b=b.const('f64', 0), offset='kb_end')  # 0 = vanilla's "no units / no zone"
    fb.op('JTrue', cond=kmbf, offset='kb_set')
    fb.op('JSLte', a=kob, b=bal, offset='kb_end')  # a village: raise only
    fb.label('kb_set')
    fb.op('Mov', dst=bal, src=kob)
    _throttle(fb, b, cx, 'bkbal', ko, 5, 'kb_end')
    _log_ev(fb, b, cx, helpers, 'bkbal', [('f', fb.get(1, 'kind')), ('tgt', kst), ('raw%', raw), ('ob%', kob),
                                          ('x', kcx), ('y', kcy)])
    fb.label('kb_end')
    fb.end_try(g3)
    # direct raze (rules/bkill.py: no order, so `bkbal` above never saw it): while our raze on the campaign base runs
    # (`bcdr` faction -> last acting pass, within BK_DR_LIVE s) a fight within BK_BAL_R of that base reads the
    # coalition's balance there: our armies + the plan partners' within BK_BAL_R of the base / the campaign's defense
    # reading D (`bcdsh`: the shared trimmed D, the forecast's their side at the base, guns included), raise only (match 69: Fremen's raze
    # armies at Arrakeen retreated 71 times at local raw 0.4-0.8 while the partners stood next to them). Logs `bkdr`
    g4 = fb.try_()
    fb.op('JTrue', cond=zforce, offset='dz_end')
    dzl = _bk_target(fb, b, cx, 1, 'dz_end')
    dzb = b.call('ent.Faction.get_mainBase', dzl)
    fb.op('JNull', reg=dzb, offset='dz_end')
    dzbe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=dzbe, src=dzb)
    dzt = fb.reg(cx.t('f64'))
    dzv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, bks.RAZE_ACT), fb.dyn(1))
    fb.op('JNull', reg=dzv, offset='dz_end')
    fb.op('SafeCast', dst=dzt, src=dzv)
    fb.op('Sub', dst=dzt, a=b.field(_state(fb, b, cx), 'time'), b=dzt)
    fb.op('JSGt', a=dzt, b=b.const('f64', BK_DR_LIVE), offset='dz_end')
    dzc = b.call('logic.state.Warzone.get_centroid', 0)
    fb.op('JNull', reg=dzc, offset='dz_end')
    dzx, dzy = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Sub', dst=dzx, a=b.field(dzbe, 'posx'), b=b.field(dzc, 'x'))
    fb.op('Mul', dst=dzx, a=dzx, b=dzx)
    fb.op('Sub', dst=dzy, a=b.field(dzbe, 'posy'), b=b.field(dzc, 'y'))
    fb.op('Mul', dst=dzy, a=dzy, b=dzy)
    fb.op('Add', dst=dzx, a=dzx, b=dzy)
    fb.op('JSGt', a=dzx, b=b.const('f64', BK_BAL_R * BK_BAL_R), offset='dz_end')
    dzd = bks.shared_defense(fb, b, cx, 1, 'dz_end')  # the shared (trimmed) D
    fb.op('JSLte', a=dzd, b=b.const('f64', 0), offset='dz_end')
    dzm, dzq = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=dzm, src=b.const('f64', 0))
    dzar = b.field(_state(fb, b, cx), 'armies')
    fb.op('JNull', reg=dzar, offset='dz_end')
    dzk = fb.reg(cx.t('i32'))
    dza = _army_loop(fb, b, dzar, b.field(dzar, 'length'), dzk, 'dzl', 'dzld')
    fb.op('JNotNull', reg=b.field(dza, 'harvestComponent'), offset='dzl')
    dzo = fb.reg(cx.t('ent.Faction'))
    fb.op('Mov', dst=dzo, src=b.call('ent.Entity.get_owner', dza))
    fb.op('JNull', reg=dzo, offset='dzl')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', dza, dzbe), b=b.const('f64', BK_BAL_R), offset='dzl')
    fb.op('JEq', a=dzo, b=1, offset='dz_add')
    fb.op('JTrue', cond=b.call('logic.state.State.areAtWar', _state(fb, b, cx), 1, dzo), offset='dzl')
    _bk_partner(fb, b, cx, 1, dzo, 'dz_add')
    fb.op('JAlways', offset='dzl')
    fb.label('dz_add')
    fb.op('Call1', dst=dzq, fun=pw, arg0=dza)
    fb.op('Add', dst=dzm, a=dzm, b=dzq)
    fb.op('JAlways', offset='dzl')
    fb.label('dzld')
    # raise only (match 71: two-sided, it read Harkonnen's 13:1 and 108:1 fights at Arrakeen as 0.37, M 386k / D 1.02M,
    # and pulled the wave out; D counts every army that can reach the base and its guns, far more than one fight):
    # the coalition keeps early arrivals in, a fight winning locally stays won
    dzr = fb.reg(cx.t('f64'))
    fb.op('SDiv', dst=dzr, a=dzm, b=dzd)
    fb.op('JSLte', a=dzr, b=bal, offset='dz_end')
    fb.op('Mov', dst=bal, src=dzr)
    _throttle(fb, b, cx, 'bkdr', 0, 5, 'dz_end')
    _log_ev(fb, b, cx, helpers, 'bkdr', [('f', fb.get(1, 'kind')), ('raw%', raw), ('ob%', bal), ('M', dzm),
                                         ('D', dzd)])
    fb.label('dz_end')
    fb.end_try(g4)
    # vanilla's own retreat (the balance we return is <= RETREAT) is held RETREAT_LATCH_T s like ours (map `rlatch`):
    # a balance hovering at the bar flipped armies Attack / Flee every 0.5 s (user 2026-10-25, match 74: Fremen's
    # armies ran around clicking; F_Hero_1 flipped 43 times in 160 s, F_Sneak 28). Not over a deliberate 0 (already
    # latched there)
    g5 = fb.try_()
    fb.op('JTrue', cond=zforce, offset='lv_d')
    fb.op('JNull', reg=0, offset='lv_d')
    fb.op('JNull', reg=1, offset='lv_d')
    fb.op('JSGt', a=bal, b=_ratio(fb, b, RETREAT), offset='lv_d')
    b.call('haxe.ds.ObjectMap.set', _fac_map(fb, b, cx, 'rlatch', 1), fb.dyn(0),
           fb.dyn(b.field(_state(fb, b, cx), 'time')))
    fb.label('lv_d')
    fb.end_try(g5)
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
