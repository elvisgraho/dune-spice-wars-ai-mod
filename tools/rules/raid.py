"""Raid: pillage for loot with armies that have nothing better to do (AI-POLICY §5a goal 5b), and give pillages up when
something more important needs their armies.

Vanilla pillages only from its Pillage gauge, which barely rises, and only with idle armies at >= 90% supply: a
stack standing next to a weakly held enemy village walked home to resupply instead (Fremen at Od-lulah), and a stack
that can't annex (Smugglers short of authority) sat at home for minutes. A pillage loots the village's production,
refills OCC_REFILL of max supply and occupying doesn't drain. Its costs: the village is Devastated for 20 days
(production halved, no siege action possible) and the pillager's Annex authority cost there is doubled (trait
Pillaged), so the villages vanilla would annex next are never raided.

Abort pass, every CHECK s, over every Military ArmySiege "Pillage" order of ours (raid's and vanilla's), unless it is
in Action at RAID_DONE progress or more (finish it), and while aimod_defend is set over our "Annex" orders too (only
the `defend` trigger, and only when its fit armies lift the defense to `enter`; not in Action at ANX_DONE progress or
more, never on the defended village). First trigger wins,
stop(Cancel):
- defend: our structure is besieged (aimod_defend) within RECALL_R of the target, our armies already at it (within
  LOCAL, any task) + free ones within GATHER_R (+ our cover) are short of ENTER x (threat + enemy cover) / terrain there, and the raid has armies fit to defend
  (life and supply >= MIN_LIFE / MIN_SUPPLY, what the contest hunt and vanilla defense take);
- home: hostile armies free to strike are closer to our land than the target + HOME_M (aimod_home) and our armies
  at home without the raid's (aimod_homeown) x OWN_T fall below ABORT x them;
- weak (still walking, phase < Engage): raid power + our cover < ABORT x (aimod_react + enemy cover + militia) /
  terrain at the target (relief arrived; in the fight the vanilla fight retreat decides).

Launch pass, every START s per faction, at most one launch per RAID_GAP s, never while defending. While the
director's posture is RECOVER (most of our power worn, rules/strat.py) only a raid that is itself a recovery: each
of its armies has the village nearer than our land (the pillage refill replaces the walk home; a stack at home
doesn't go out) and the entry test is RAID_TO instead of ENTER (overwhelming, short). Logged rec=true:
- candidates: vanilla's own pillage list (AIMilitary.getSiegeableVillages "Pillage": pillage allowed for us, not
  Devastated, no order on it, in supply range, sandstorms, ...) with its desiredStatus gate lifted for this scan
  (map `rscan`, read by strat_levers: vanilla's daily wish is 0 toward most at-war factions, so the enemy village
  next to a won fight was never a candidate), owned by nobody or by a faction at war with us, not
  a main base, not besieged; minus the vanilla Annex choices (getSiegeableVillages "Annex" with tryAnnexation's
  aggressiveness gate, target scores, pickMapBest top RAID_KEEP) and villages within
  BUNKER_R of our main base (the bunker redirect annexes them first), villages on an uncontested deep-desert ring
  we are closing (aimod_ddclean, Fremen), villages with our own Underworld HQ (our
  income there), villages our raid launched on less than RAID_RETRY s ago (aborted / cancelled at once: no loop)
  and villages behind another faction's main base (`_behind`, BEHIND_E: counted as bh in the start / refuse rows);
- force: our armies within RAID_R, not fighting (micro holds them; as a mission they'd escape the `pursuit` exit),
  that are free for a raid (aimod_free variant: life >= RAID_LIFE, any supply, a
  Resupply order doesn't count as busy) and pass the raid supply budget (aimod_raidsup);
- test: their power (+ our cover) >= ENTER x (aimod_react + enemy cover + militia) / terrain, and the home race: our
  armies within (target's distance to our land + HOME_M) of our land, minus what the raid takes, x OWN_T >= ENTER x
  the hostile armies as close (aimod_home). Enemy near home = only raids closer to home than it;
- pick: the candidate nearest to one of our armies; its nearest raid-ready armies join until RAID_TO x their side
  (at least one army). Order = Military prio 1 (Pillage aiPrio) ArmySiege "Pillage"; vanilla runs it like its own.
Logs `raid` act=start / abort (why defend | home | weak), and once per RAID_GAP per faction act=refuse for the nearest
refused candidate with our armies within RAID_R when nothing launched or it was nearer than the launched one (alt): why ready (no army passes life / supply budget), weak (H armies, C
turrets, Mi militia vs M, tf terrain) or home (hh hostile vs ms ours near home). ax = the first excluded Annex choice
(the top RAID_KEEP 3 by vanilla's Annex scores are excluded, affordable or not), nc = vanilla candidates. Fails safe: in a trap, nothing launched or cancelled on error."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def _behind(fb, b, cx, state, fac, ve, nbh, skip):
    """Jump to `skip` (counting nbh) when ve lies behind another faction's main base as seen from our main base
    nearest to it: some main base M nearer our base B than ve is, with d(B, M) + d(M, ve) <= d(B, ve) x (1 +
    BEHIND_E) (M on the way: pillaging there means crossing or passing their land; no whole-map pillage tours)."""
    bd, d, q = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    be, me = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    k, j = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    zi = b.const('i32', 0)
    ok, lo, lf, lm = _uid('bok'), _uid('bo'), _uid('bf'), _uid('bm')
    fb.op('Mov', dst=bd, src=b.const('f64', 1 << 30))
    fb.op('Null', dst=be)
    mbs = b.field(fac, 'mainBases')
    fb.op('JNull', reg=mbs, offset=ok)
    fb.op('Mov', dst=k, src=zi)
    b.loop_head(lo)
    fb.op('JSGte', a=k, b=b.field(mbs, 'length'), offset=lo + 'd')
    mb = b.cast(b.call('hl.types.ArrayObj.getDyn', mbs, k), 'ent.Structure')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=mb, offset=lo)
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', mb), offset=lo)
    fb.op('Mov', dst=me, src=mb)
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', ve, me))
    fb.op('JSGte', a=d, b=bd, offset=lo)
    fb.op('Mov', dst=bd, src=d)
    fb.op('Mov', dst=be, src=me)
    fb.op('JAlways', offset=lo)
    fb.label(lo + 'd')
    fb.op('JNull', reg=be, offset=ok)
    lim = fb.reg(cx.t('f64'))
    fb.op('Mul', dst=lim, a=bd, b=_ratio(fb, b, 1 + BEHIND_E))
    facs = b.cast(fb.get(state, 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=facs, offset=ok)
    fb.op('Mov', dst=k, src=zi)
    b.loop_head(lf)
    fb.op('JSGte', a=k, b=b.field(facs, 'length'), offset=ok)
    of = b.cast(b.call('hl.types.ArrayObj.getDyn', facs, k), 'ent.Faction')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=of, offset=lf)
    fb.op('JEq', a=of, b=fac, offset=lf)
    ombs = b.field(of, 'mainBases')
    fb.op('JNull', reg=ombs, offset=lf)
    fb.op('Mov', dst=j, src=zi)
    b.loop_head(lm)
    fb.op('JSGte', a=j, b=b.field(ombs, 'length'), offset=lf)
    om = b.cast(b.call('hl.types.ArrayObj.getDyn', ombs, j), 'ent.Structure')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=om, offset=lm)
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', om), offset=lm)
    fb.op('Mov', dst=me, src=om)
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', be, me))
    fb.op('JSGte', a=d, b=bd, offset=lm)  # not nearer to us than the village: not on the way
    fb.op('Mov', dst=q, src=b.call('ent.Entity.getDistTo', me, ve))
    fb.op('Add', dst=q, a=q, b=d)
    fb.op('JSGt', a=q, b=lim, offset=lm)
    fb.op('Incr', dst=nbh)
    fb.op('JAlways', offset=skip)
    fb.label(ok)


def build_raid(cx, helpers, pw, raidable, react, land, terrain, raidsup, cover, defend, militia, threat, free, home,
               homeown, scores, neutral):
    """aimod_raid(mil, dt) (see module doc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    state = _state(fb, b, cx)
    t = b.field(state, 'time')
    orders_obj = b.field(ctrl, 'aiOrders')
    orders = b.field(orders_obj, 'orders')
    fb.op('JNull', reg=orders, offset='end')
    my_armies, mlen = _my_armies(fb, b, fac, 'end')

    zi, zero, big = b.const('i32', 0), b.const('f64', 0), b.const('f64', 1 << 30)
    one = b.const('i32', 1)
    raid_r, local = b.const('f64', RAID_R), b.const('f64', LOCAL)
    home_m, recall_r, gather_r = b.const('f64', HOME_M), b.const('f64', RECALL_R), b.const('f64', GATHER_R)
    enter, abort, own_t = _ratio(fb, b, ENTER), _ratio(fb, b, ABORT), _ratio(fb, b, OWN_T)
    raid_to, done_r = _ratio(fb, b, RAID_TO), _ratio(fb, b, RAID_DONE)
    min_life, min_sup = _ratio(fb, b, MIN_LIFE), _ratio(fb, b, MIN_SUPPLY)
    t_false, t_true = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_false, value=False)
    fb.op('Bool', dst=t_true, value=True)
    no_arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=no_arr)
    pillage_s = fb.string('Pillage')
    pillage = fb.dyn(pillage_s)
    i, j, k, idx, ph = (fb.reg(cx.t('i32')) for _ in range(5))
    h, m, p, q, r, sd, lim, dy, tf, pr, hh, ms, hp = (fb.reg(cx.t('f64')) for _ in range(13))
    ok, anx = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    ve, de = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    ye = fb.reg(cx.t('ent.Entity'))

    no_ent = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=no_ent)

    def cover_at(dst, at, own, target=False):
        """target: the structure at `at` is the raid target; its own turrets count (they fire until the pillage
        starts; aimod_cover silences a besieged village by itself)."""
        fb.op('CallN', dst=dst, fun=cover, args=[fac, at, no_ent if target else at, t_true if own else t_false,
                                                 no_arr])

    def their_side(dst, s):
        """dst = at-war armies in reach + enemy turret cover + militia at structure s (entity reg ve)."""
        fb.op('Call3', dst=dst, fun=react, arg0=fac, arg1=ve, arg2=local)
        cover_at(q, ve, False, target=True)
        fb.op('Add', dst=dst, a=dst, b=q)
        fb.op('Call1', dst=q, fun=militia, arg0=s)
        fb.op('Add', dst=dst, a=dst, b=q)
        fb.op('Call3', dst=q, fun=neutral, arg0=fac, arg1=ve, arg2=local)  # other raiders at it fight us too
        fb.op('Add', dst=dst, a=dst, b=q)

    # ---- 1. abort pass: re-check running pillages (backwards: stop() removes the order from the list)
    _tick(fb, b, cx, t, CHECK, 'new')
    dfs = fb.reg(cx.t('ent.Structure'))
    fb.op('Call1', dst=dfs, fun=defend, arg0=fac)
    reason = cx.code.types[cx.fn('logic.ai.AIOrder.stop').type.value].definition.args[1].value
    cancel = fb.reg(reason)
    fb.op('MakeEnum', dst=cancel, construct=CANCEL, args=[])
    fb.op('Mov', dst=i, src=b.field(orders, 'length'))
    b.loop_head('ord')
    fb.op('JSLte', a=i, b=zi, offset='new')
    fb.op('Sub', dst=i, a=i, b=one)
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, i), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset='ord')
    fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='ord')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='ord')
    fb.op('EnumIndex', dst=idx, value=tt)
    fb.op('JNotEq', a=idx, b=b.const('i32', T_STRUCT), offset='ord')
    sa = b.cast(fb.get(o, 'siegeAction'), 'String')
    fb.op('JNull', reg=sa, offset='ord')
    # our Annex orders too, for `defend` only (a capture next door outweighs a new village: Harkonnen annexed Gurlab
    # while Smugglers took Zadak 177 from Carthag); never the defended village itself
    fb.op('Bool', dst=anx, value=False)
    fb.op('JEq', a=b.call('String.__compare', sa, pillage), b=zi, offset='ispil')
    fb.op('JNotEq', a=b.call('String.__compare', sa, fb.dyn(fb.string('Annex'))), b=zi, offset='ord')
    fb.op('JNull', reg=dfs, offset='ord')
    fb.op('Bool', dst=anx, value=True)
    fb.label('ispil')
    ov = b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'ent.Structure')
    fb.op('JNull', reg=ov, offset='ord')
    fb.op('Mov', dst=ve, src=ov)
    fb.op('JFalse', cond=anx, offset='notdf')
    fb.op('Mov', dst=de, src=dfs)
    fb.op('JEq', a=ve, b=de, offset='ord')
    fb.label('notdf')
    fb.op('Mov', dst=ph, src=b.field(o, 'phase'))
    fb.op('Mov', dst=pr, src=zero)
    osg = b.field(ov, 'siege')
    fb.op('JNull', reg=osg, offset='noprog')
    fb.op('Mov', dst=pr, src=b.call('ent.comp.SiegeComponent.getOccupationActionProgress', osg))
    fb.label('noprog')
    fb.op('JNotEq', a=ph, b=b.const('i32', ACTION), offset='running')
    fb.op('JFalse', cond=anx, offset='pdone')
    fb.op('JSGte', a=pr, b=_ratio(fb, b, ANX_DONE), offset='ord')  # an Annex well under way: finish it
    fb.label('pdone')
    fb.op('JSGte', a=pr, b=done_r, offset='ord')  # nearly done: finish it
    fb.label('running')
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='ord')
    un = b.field(units, 'length')
    _riding(fb, b, cx, helpers, fac, o, units, 'rride', 'ord')  # in transit: judged once it lands
    # raid power, and the part of it fit to defend (what the contest hunt / vanilla defense would take)
    fb.op('Mov', dst=m, src=zero)
    fb.op('Mov', dst=hp, src=zero)
    u = _army_loop(fb, b, units, un, j, 'u', 'udone')
    fb.op('Call1', dst=p, fun=pw, arg0=u)
    fb.op('Add', dst=m, a=m, b=p)
    fb.op('JSLt', a=b.call('ent.Entity.get_lifeRatio', u), b=min_life, offset='u')
    ums = b.call('ent.Army.get_maxSupply', u)
    fb.op('JSLte', a=ums, b=zero, offset='ufit')
    fb.op('SDiv', dst=q, a=b.call('ent.Army.get_supply', u), b=ums)
    fb.op('JSLt', a=q, b=min_sup, offset='u')
    fb.label('ufit')
    fb.op('Add', dst=hp, a=hp, b=p)
    fb.op('JAlways', offset='u')
    fb.label('udone')
    fb.op('Call2', dst=sd, fun=land, arg0=fac, arg1=ve)
    # defend: our besieged structure near the raid needs armies its free defenders lack
    fb.op('JNull', reg=dfs, offset='a_home')
    fb.op('JSLte', a=hp, b=zero, offset='a_home')
    fb.op('Mov', dst=de, src=dfs)
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ve, de), b=recall_r, offset='a_home')
    fb.op('Call3', dst=h, fun=threat, arg0=fac, arg1=de, arg2=local)
    cover_at(q, de, False)
    fb.op('Add', dst=h, a=h, b=q)
    cover_at(r, de, True)
    y = _army_loop(fb, b, my_armies, mlen, k, 'df', 'dfdone')
    fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', units, fb.dyn(y)), offset='df')
    fb.op('Mov', dst=dy, src=b.call('ent.Entity.getDistTo', y, de))
    fb.op('JSGt', a=dy, b=gather_r, offset='df')
    fb.op('JNotNull', reg=b.field(y, 'harvestComponent'), offset='df')
    fb.op('JSLte', a=dy, b=local, offset='dfin')  # already there (defending, in a contest hunt or idle)
    fb.op('Call2', dst=ok, fun=free, arg0=y, arg1=orders)
    fb.op('JFalse', cond=ok, offset='df')
    fb.label('dfin')
    fb.op('Call1', dst=p, fun=pw, arg0=y)
    fb.op('Add', dst=r, a=r, b=p)
    fb.op('JAlways', offset='df')
    fb.label('dfdone')
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', de))
    fb.op('Mul', dst=q, a=h, b=enter)
    fb.op('SDiv', dst=q, a=q, b=tf)
    # an Annex only yields when its armies make the defense winnable (hopeless: keep annexing)
    fb.op('JFalse', cond=anx, offset='dfwin')
    fb.op('Add', dst=lim, a=r, b=hp)
    fb.op('JSLt', a=lim, b=q, offset='ord')
    fb.label('dfwin')
    fb.op('JSLt', a=r, b=q, offset='ab_defend')
    # home: hostile armies closer to our land than the raid, and too few of ours at home without it
    fb.label('a_home')
    fb.op('JTrue', cond=anx, offset='ord')  # an Annex yields for `defend` only
    fb.op('Add', dst=lim, a=sd, b=home_m)
    fb.op('Call2', dst=hh, fun=home, arg0=fac, arg1=lim)
    fb.op('JSLte', a=hh, b=zero, offset='a_weak')
    fb.op('Call3', dst=ms, fun=homeown, arg0=fac, arg1=lim, arg2=units)
    fb.op('Mul', dst=q, a=ms, b=own_t)
    fb.op('Mul', dst=r, a=hh, b=abort)
    fb.op('JSLt', a=q, b=r, offset='ab_home')
    # weak: still walking and relief arrived at the target (in the fight the vanilla fight retreat decides)
    fb.label('a_weak')
    fb.op('JSGte', a=ph, b=b.const('i32', REGROUP + 1), offset='ord')
    their_side(h, ov)
    cover_at(q, ve, True)
    fb.op('Add', dst=r, a=m, b=q)
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', ve))
    fb.op('Mul', dst=q, a=h, b=abort)
    fb.op('SDiv', dst=q, a=q, b=tf)
    fb.op('JSLt', a=r, b=q, offset='ab_weak')
    fb.op('JAlways', offset='ord')
    for why, hr, mr in (('defend', h, r), ('home', hh, ms), ('weak', h, r)):
        fb.label(f'ab_{why}')
        b.call('logic.ai.AIOrder.stop', o, cancel)
        _log_ev(fb, b, cx, helpers, 'raid', [('f', fb.get(fac, 'kind')), ('act', 'abort'), ('why', why),
                                             ('tgt', ve), ('H', hr), ('M', mr), ('ph', ph), ('pr%', pr),
                                             ('sd', sd), ('n', un), ('sa', sa)])
        fb.op('JAlways', offset='ord')

    # ---- 2. launch pass: at most one new raid
    fb.label('new')
    _tick(fb, b, cx, t, START, 'end')
    # commit gap and defensive posture
    lastmap = _global_map(fb, b, cx, 'raid')
    retrymap = _global_map(fb, b, cx, 'rlaunch')  # village -> last raid launch on it
    # the director's press (rules/strat.py): annex mode = vanilla's siege takes it, never pillaged; pillage mode =
    # this rule takes it first (its annex-choice exclusion doesn't apply)
    pvd = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'spv'), fb.dyn(fac))
    pan = fb.reg(cx.t('bool'))
    fb.op('SafeCast', dst=pan, src=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'spa'), fb.dyn(fac)))
    pref = fb.reg(cx.t('bool'))
    eff = fb.reg(cx.t('f64'))
    last = b.call('haxe.ds.ObjectMap.get', lastmap, fb.dyn(fac))
    lastf = fb.reg(cx.t('f64'))
    fb.op('JNull', reg=last, offset='gapok')
    fb.op('SafeCast', dst=lastf, src=last)
    fb.op('Sub', dst=lastf, a=t, b=lastf)
    fb.op('JSLt', a=lastf, b=b.const('f64', RAID_GAP), offset='end')
    fb.label('gapok')
    fb.op('Call1', dst=dfs, fun=defend, arg0=fac)
    fb.op('JNotNull', reg=dfs, offset='end')
    # vanilla's Annex fires within seconds (gauge >= RAID_GAUGE) and takes the armies of a raid launched now
    gauges = b.cast(fb.get(0, 'gauges'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=gauges, offset='gaugeok')
    gk = fb.reg(cx.t('String'))
    gv = fb.reg(cx.t('f64'))
    gi = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=gi, src=b.const('i32', 0))
    b.loop_head('gl')
    fb.op('JSGte', a=gi, b=b.field(gauges, 'length'), offset='gaugeok')
    gg = b.call('hl.types.ArrayObj.getDyn', gauges, gi)
    fb.op('Incr', dst=gi)
    fb.op('JNull', reg=gg, offset='gl')
    fb.op('DynGet', dst=gk, obj=gg, field=cx.s('kind'))
    fb.op('JNull', reg=gk, offset='gl')
    fb.op('JNotEq', a=b.call('String.__compare', gk, fb.dyn(fb.string('Annexation'))), b=b.const('i32', 0), offset='gl')
    fb.op('DynGet', dst=gv, obj=gg, field=cx.s('value'))
    # ... unless it has stayed that full for RAID_GAUGE_T s (map `rgauge` = since when): its Annex isn't coming
    # (MissingResources / no army / no candidate: Smugglers' gauge sat at 85-99 for 7.5 min, every raid pass held)
    rgm = _global_map(fb, b, cx, 'rgauge')
    fb.op('JSGte', a=gv, b=b.const('f64', RAID_GAUGE), offset='gfull')
    b.call('haxe.ds.ObjectMap.remove', rgm, fb.dyn(fac))
    fb.op('JAlways', offset='gaugeok')
    fb.label('gfull')
    rgv = b.call('haxe.ds.ObjectMap.get', rgm, fb.dyn(fac))
    fb.op('JNotNull', reg=rgv, offset='gseen')
    b.call('haxe.ds.ObjectMap.set', rgm, fb.dyn(fac), fb.dyn(t))
    fb.op('JAlways', offset='end')
    fb.label('gseen')
    fb.op('SafeCast', dst=gv, src=rgv)
    fb.op('Sub', dst=gv, a=t, b=gv)
    fb.op('JSLt', a=gv, b=b.const('f64', RAID_GAUGE_T), offset='end')
    fb.label('gaugeok')
    # director RECOVER (rules/strat.py, posture in map `spost`, set earlier in this tick): only a raid that IS a
    # recovery: every raid army has the village nearer than our land (the pillage refill replaces the walk home)
    # and the win is overwhelming (RAID_TO instead of ENTER)
    rec = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=rec, value=False)
    gate = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=gate, src=enter)
    rp = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'spost'), fb.dyn(fac))
    fb.op('JNull', reg=rp, offset='norecover')
    rpi = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=rpi, src=rp)
    fb.op('JNotEq', a=rpi, b=b.const('i32', RECOVER_POST), offset='norecover')
    fb.op('Bool', dst=rec, value=True)
    fb.op('Mov', dst=gate, src=raid_to)
    fb.label('norecover')
    on = b.field(orders, 'length')
    structs = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=structs, offset='end')
    sn = b.field(structs, 'length')
    # vanilla's pillage candidates, every at-war owner's villages included: the desiredStatus gate is lifted for
    # this call only (map `rscan` faction -> now, read by strat_levers' getTargetStatus wrapper, stale next frame)
    scan = _global_map(fb, b, cx, 'rscan')
    b.call('haxe.ds.ObjectMap.set', scan, fb.dyn(fac), fb.dyn(t))
    cands = _new_array(fb, b, cx)
    b.call('logic.ai.$AIMilitary.getSiegeableVillages', cands, pillage_s, fac,
           b.call('$HAI.getDefaultStructureArgs', pillage_s))
    nodyn = fb.reg(cx.t('dyn'))
    fb.op('Null', dst=nodyn)
    b.call('haxe.ds.ObjectMap.set', scan, fb.dyn(fac), nodyn)
    vn = b.field(cands, 'length')
    # vanilla's next Annex choices (as tryAnnexation -> tryAction picks them): never raided
    annex_s = fb.string('Annex')
    aargs = b.call('$HAI.getDefaultStructureArgs', annex_s)
    fb.op('JNotLt', a=b.call('logic.ai.AIMilitary.get_aggressiveness', 0),
          b=b.call('logic.ai.AIMilitary.getActionRequiredAggressivenessByKind', 0, fb.string('Annexation')),
          offset='aggr')
    fb.op('SetField', obj=aargs, field=cx.field(fb.regs[aargs], 'allowEnemy'), src=t_false)
    fb.label('aggr')
    ann = _new_array(fb, b, cx)
    b.call('logic.ai.$AIMilitary.getSiegeableVillages', ann, annex_s, fac, aargs)
    choices = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=choices)
    ax = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=ax)
    fb.op('JSLte', a=b.field(ann, 'length'), b=zi, offset='noannex')
    sfn = cx.fn('logic.ai.$HScoring.structures')
    sat = [a.value for a in cx.code.types[sfn.type.value].definition.args]
    snull = []
    for n in (3, 4, 5):
        rr = fb.reg(sat[n])
        fb.op('Null', dst=rr)
        snull.append(rr)
    sc = fb.reg(cx.code.types[sfn.type.value].definition.ret.value)
    fb.op('CallN', dst=sc, fun=scores, args=[ann, fac, annex_s] + snull)
    fb.op('JNull', reg=sc, offset='noannex')
    pmb = cx.fn('lib.$Extensions_pickMapBest_ent_Structure.pickMapBest')
    pat = [a.value for a in cx.code.types[pmb.type.value].definition.args]
    cnt, pnull = fb.reg(pat[1]), fb.reg(pat[2])
    fb.op('ToDyn', dst=cnt, src=b.const('i32', RAID_KEEP))
    fb.op('Null', dst=pnull)
    fb.op('Call3', dst=choices, fun=pmb.findex.value, arg0=sc, arg1=cnt, arg2=pnull)
    fb.op('JNull', reg=choices, offset='noannex')
    fb.op('JSLte', a=b.field(choices, 'length'), b=zi, offset='noannex')
    fb.op('Mov', dst=ax, src=b.cast(b.call('hl.types.ArrayObj.getDyn', choices, zi), 'ent.Entity'))
    fb.label('noannex')

    need, dmin, dall, mh, ly = (fb.reg(cx.t('f64')) for _ in range(5))
    nr, nready = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    best = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=best)
    best_d, best_h, best_sd, best_tf = b.const('f64', 1 << 30), b.const('f64', 0), b.const('f64', 0), \
        b.const('f64', 1)
    best_hh, best_ms = b.const('f64', 0), b.const('f64', 0)
    # nearest refused candidate (logged when nothing launches): why, their armies / turrets / militia, our power
    hq, cq, mq = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    rej = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=rej)
    rej_d = b.const('f64', 1 << 30)
    rej_h, rej_c, rej_mi, rej_m, rej_tf, rej_sd, rej_hh, rej_ms = (b.const('f64', 0) for _ in range(8))
    rej_nr, rej_n = b.const('i32', 0), b.const('i32', 0)
    rej_why, rej_why_c = fb.reg(cx.t('String')), fb.reg(cx.t('String'))
    why_ready, why_weak, why_home = fb.string('ready'), fb.string('weak'), fb.string('home')
    fb.op('Mov', dst=rej_why, src=why_ready)
    nbh = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=nbh, src=zi)

    fb.op('Mov', dst=i, src=zi)
    b.loop_head('v')
    fb.op('JSGte', a=i, b=vn, offset='vdone')
    v = b.cast(b.call('hl.types.ArrayObj.getDyn', cands, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=v, offset='v')
    fb.op('Mov', dst=ve, src=v)
    # neutral or at war with us, not a main base, nobody besieging it
    vo = b.call('ent.Entity.get_owner', ve)
    fb.op('JNull', reg=vo, offset='owner_ok')
    fb.op('JEq', a=vo, b=fac, offset='v')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, vo), offset='v')
    fb.label('owner_ok')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', v), offset='v')
    sg = b.field(v, 'siege')
    fb.op('JNull', reg=sg, offset='v')
    fb.op('JNotNull', reg=b.field(sg, 'besiegingFaction'), offset='v')
    # not one our raid left less than RAID_RETRY s ago (aborted, or cancelled at once by vanilla)
    rl = b.call('haxe.ds.ObjectMap.get', retrymap, fb.dyn(ve))
    fb.op('JNull', reg=rl, offset='notrecent')
    fb.op('SafeCast', dst=q, src=rl)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSLt', a=q, b=b.const('f64', RAID_RETRY), offset='v')
    fb.label('notrecent')
    # not a village our own Underworld HQ exploits (a pillage devastates our income there)
    fb.op('JTrue', cond=b.call('ent.Structure.hasUWHeadquarters', v, fac), offset='v')
    fb.op('Bool', dst=pref, value=False)
    fb.op('JNull', reg=pvd, offset='notpress')
    fb.op('JNotEq', a=fb.dyn(ve), b=pvd, offset='notpress')
    fb.op('JTrue', cond=pan, offset='v')  # pressed for Annex: the siege takes it
    fb.op('Bool', dst=pref, value=True)
    fb.op('JAlways', offset='mbdone')  # pressed for pillage: no annex-choice / bunker exclusion
    fb.label('notpress')
    # not behind another faction's main base (BEHIND_E): no pillage tours across the map (the director's press
    # target above is its own call)
    _behind(fb, b, cx, state, fac, ve, nbh, 'v')
    # not what we annex next
    fb.op('JNull', reg=choices, offset='nochoice')
    fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', choices, fb.dyn(ve)), offset='v')
    fb.label('nochoice')
    # not a village the Annex value just dropped as a plain lone candidate (map `alonev`): we still annex it once
    # the supply range grows; a pillage would devastate it and double our cost there
    alv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'alonev'), fb.dyn(ve))
    fb.op('JNull', reg=alv, offset='alok')
    fb.op('SafeCast', dst=q, src=alv)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSLt', a=q, b=b.const('f64', ALONE_HOLD), offset='v')
    fb.label('alok')
    # not a village on an uncontested deep-desert ring we are closing (aimod_ddclean: Fremen; a pillage would leave it
    # Devastated and double our Annex cost there: Fremen pillaged its own ring village Tsim-tah)
    vz = b.call('ent.Entity.get_zone', ve)
    fb.op('JNull', reg=vz, offset='noring')
    rcl = fb.reg(cx.t('bool'))
    fb.op('Call2', dst=rcl, fun=helpers['ddclean'], arg0=fac, arg1=vz)
    fb.op('JTrue', cond=rcl, offset='v')
    fb.label('noring')
    fb.op('Mov', dst=j, src=zi)
    b.loop_head('mb')
    fb.op('JSGte', a=j, b=sn, offset='mbdone')
    st = b.cast(b.call('hl.types.ArrayObj.getDyn', structs, j), 'ent.Structure')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=st, offset='mb')
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', st), offset='mb')
    fb.op('Mov', dst=de, src=st)
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', ve, de), b=b.const('f64', BUNKER_R), offset='v')
    fb.op('JAlways', offset='mb')
    fb.label('mbdone')
    # not already one of our Military targets
    fb.op('Mov', dst=j, src=zi)
    b.loop_head('o')
    fb.op('JSGte', a=j, b=on, offset='odone')
    o2 = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, j), 'logic.ai.AIOrder')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=o2, offset='o')
    fb.op('EnumIndex', dst=idx, value=b.field(o2, 'type'))
    fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset='o')
    tt2 = b.field(o2, 'targetType')
    fb.op('JNull', reg=tt2, offset='o')
    fb.op('EnumIndex', dst=idx, value=tt2)
    fb.op('JNotEq', a=idx, b=b.const('i32', T_STRUCT), offset='o')
    fb.op('JEq', a=b.call('logic.ai.AIOrder.getTarget', o2), b=ve, offset='v')
    fb.op('JAlways', offset='o')
    fb.label('odone')
    # our raid force there (+ our turret cover), with the supply for the raid and the way home; our armies at home
    fb.op('Call2', dst=sd, fun=land, arg0=fac, arg1=ve)
    fb.op('Add', dst=lim, a=sd, b=home_m)
    cover_at(m, ve, True)
    fb.op('Mov', dst=ms, src=zero)
    fb.op('Mov', dst=dmin, src=big)
    fb.op('Mov', dst=dall, src=big)
    fb.op('Mov', dst=nr, src=zi)
    fb.op('Mov', dst=nready, src=zi)
    fb.op('Mov', dst=mh, src=zero)
    y = _army_loop(fb, b, my_armies, mlen, k, 'y', 'ydone')
    fb.op('Mov', dst=ye, src=y)
    fb.op('Mov', dst=ly, src=big)
    fb.op('JNotNull', reg=b.field(y, 'harvestComponent'), offset='yraid')
    fb.op('Call2', dst=ly, fun=land, arg0=fac, arg1=ye)
    fb.op('JSGt', a=ly, b=lim, offset='yraid')
    fb.op('Call1', dst=p, fun=pw, arg0=y)
    fb.op('Add', dst=ms, a=ms, b=p)
    fb.label('yraid')
    fb.op('Mov', dst=dy, src=b.call('ent.Entity.getDistTo', y, ve))
    fb.op('JSGt', a=dy, b=raid_r, offset='y')
    fb.op('Incr', dst=nr)
    fb.op('JSGte', a=dy, b=dall, offset='yall')
    fb.op('Mov', dst=dall, src=dy)
    fb.label('yall')
    # in a fight: micro holds it (a new order stalls in Regroup and, being a mission, keeps it chasing)
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', y), offset='y')
    fb.op('Call2', dst=ok, fun=raidable, arg0=y, arg1=orders)
    fb.op('JFalse', cond=ok, offset='y')
    fb.op('Call3', dst=ok, fun=raidsup, arg0=y, arg1=dy, arg2=sd)
    fb.op('JFalse', cond=ok, offset='y')
    fb.op('JFalse', cond=rec, offset='yrecok')
    fb.op('JSGt', a=dy, b=ly, offset='y')  # recovering: the village must be nearer than our land
    fb.label('yrecok')
    fb.op('Call1', dst=p, fun=pw, arg0=y)
    fb.op('Add', dst=m, a=m, b=p)
    fb.op('Incr', dst=nready)
    fb.op('JSGt', a=ly, b=lim, offset='ynh')
    fb.op('Add', dst=mh, a=mh, b=p)  # raid-ready and at home: leaves home if it joins
    fb.label('ynh')
    fb.op('JSGte', a=dy, b=dmin, offset='y')
    fb.op('Mov', dst=dmin, src=dy)
    fb.op('JAlways', offset='y')
    fb.label('ydone')
    fb.op('JSLte', a=nr, b=zi, offset='v')  # none of ours near it
    fb.op('Mov', dst=hq, src=zero)
    fb.op('Mov', dst=cq, src=zero)
    fb.op('Mov', dst=mq, src=zero)
    fb.op('Mov', dst=hh, src=zero)
    fb.op('Mov', dst=tf, src=b.const('f64', 1))
    fb.op('Mov', dst=rej_why_c, src=why_ready)
    fb.op('JSGte', a=dmin, b=big, offset='refuse')  # armies near it, none raid-ready (life / supply budget)
    # their side: armies in reach, turrets covering it, its militia
    fb.op('Call3', dst=hq, fun=react, arg0=fac, arg1=ve, arg2=local)
    cover_at(cq, ve, False, target=True)
    fb.op('Call1', dst=mq, fun=militia, arg0=v)
    fb.op('Call3', dst=q, fun=neutral, arg0=fac, arg1=ve, arg2=local)  # other raiders at it: counted as militia
    fb.op('Add', dst=mq, a=mq, b=q)
    fb.op('Add', dst=h, a=hq, b=cq)
    fb.op('Add', dst=h, a=h, b=mq)
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', ve))
    # gate x what is at the village (armies within LOCAL, turrets, militia, raiders); armies only within REACT_R
    # count at RAID_FAR: they come only with ENTER x our raid (our own contest rule), and if they come the abort pass
    # pulls the pillage out (Smugglers refused Anna-Al'dad for 6 min: Atreides' whole 300k idling in Arrakeen 390
    # away, 329k vs 1.5 x 333k)
    hloc = fb.reg(cx.t('f64'))
    fb.op('Call3', dst=hloc, fun=threat, arg0=fac, arg1=ve, arg2=local)
    fb.op('Add', dst=hloc, a=hloc, b=cq)
    fb.op('Add', dst=hloc, a=hloc, b=mq)
    fb.op('Mul', dst=q, a=hloc, b=gate)
    fb.op('SDiv', dst=q, a=q, b=tf)
    fb.op('Mov', dst=rej_why_c, src=why_weak)
    fb.op('JSLt', a=m, b=q, offset='refuse')
    fb.op('Mul', dst=q, a=h, b=_ratio(fb, b, RAID_FAR))
    fb.op('SDiv', dst=q, a=q, b=tf)
    fb.op('JSLt', a=m, b=q, offset='refuse')
    # home race: hostile armies nearer our land than the raid must be held by what stays home. The raid takes
    # about RAID_TO x their side (the launch sizing), at most the raid-ready power standing at home (mh); the
    # launch re-checks with the armies actually picked
    fb.op('Call2', dst=hh, fun=home, arg0=fac, arg1=lim)
    fb.op('JSLte', a=hh, b=zero, offset='pass')
    fb.op('Mul', dst=need, a=h, b=raid_to)
    fb.op('SDiv', dst=need, a=need, b=tf)
    fb.op('JSLte', a=need, b=mh, offset='take')
    fb.op('Mov', dst=need, src=mh)
    fb.label('take')
    fb.op('Sub', dst=ms, a=ms, b=need)
    fb.op('JSGte', a=ms, b=zero, offset='msok')
    fb.op('Mov', dst=ms, src=zero)
    fb.label('msok')
    fb.op('Mul', dst=q, a=ms, b=own_t)
    fb.op('Mul', dst=r, a=hh, b=enter)
    fb.op('Mov', dst=rej_why_c, src=why_home)
    fb.op('JSLt', a=q, b=r, offset='refuse')
    fb.label('pass')
    fb.op('Mov', dst=eff, src=dmin)  # the pressed village wins over any other candidate
    fb.op('JFalse', cond=pref, offset='noeff')
    fb.op('Mov', dst=eff, src=zero)
    fb.label('noeff')
    fb.op('JSGte', a=eff, b=best_d, offset='v')
    for dst, src in ((best, ve), (best_d, eff), (best_h, h), (best_sd, sd), (best_tf, tf),
                     (best_hh, hh), (best_ms, ms)):
        fb.op('Mov', dst=dst, src=src)
    fb.op('JAlways', offset='v')
    fb.label('refuse')
    fb.op('JSGte', a=dall, b=rej_d, offset='v')
    for dst, src in ((rej, ve), (rej_d, dall), (rej_h, hq), (rej_c, cq), (rej_mi, mq), (rej_m, m), (rej_tf, tf),
                     (rej_sd, sd), (rej_nr, nr), (rej_n, nready), (rej_why, rej_why_c), (rej_hh, hh),
                     (rej_ms, ms)):
        fb.op('Mov', dst=dst, src=src)
    fb.op('JAlways', offset='v')
    fb.label('vdone')
    # refused: logged when nothing launches, and when a nearer candidate was refused than the one launched (Fremen
    # next to Hadwaz raided Zay-waz, 262 away, and the reason Hadwaz failed was never logged)
    fb.op('JNull', reg=rej, offset='rlogd')
    fb.op('JNull', reg=best, offset='rlog')
    fb.op('JSGte', a=rej_d, b=best_d, offset='rlogd')
    fb.label('rlog')
    _throttle(fb, b, cx, 'raidx', fac, RAID_GAP, 'rlogd')
    _log_ev(fb, b, cx, helpers, 'raid', [('f', fb.get(fac, 'kind')), ('act', 'refuse'), ('why', rej_why),
                                         ('tgt', rej), ('H', rej_h), ('C', rej_c), ('Mi', rej_mi), ('M', rej_m),
                                         ('tf%', rej_tf), ('nr', rej_nr), ('n', rej_n), ('dm', rej_d),
                                         ('sd', rej_sd), ('hh', rej_hh), ('ms', rej_ms), ('ax', ax), ('nc', vn),
                                         ('rec', rec), ('alt', best), ('bh', nbh)])
    fb.label('rlogd')
    fb.op('JNotNull', reg=best, offset='launch')
    fb.op('JAlways', offset='end')
    fb.label('launch')

    # launch: the nearest raid-ready armies in reach until RAID_TO x their side (at least one)
    fb.op('Mul', dst=need, a=best_h, b=raid_to)
    fb.op('SDiv', dst=need, a=need, b=best_tf)
    cover_at(m, best, True)
    arr = _new_array(fb, b, cx)
    ny = fb.reg(cx.t('ent.Army'))
    nd = fb.reg(cx.t('f64'))
    b.loop_head('sel')
    fb.op('Null', dst=ny)
    fb.op('Mov', dst=nd, src=big)
    y = _army_loop(fb, b, my_armies, mlen, k, 'g', 'gdone')
    fb.op('Mov', dst=dy, src=b.call('ent.Entity.getDistTo', y, best))
    fb.op('JSGt', a=dy, b=raid_r, offset='g')
    fb.op('JSGte', a=dy, b=nd, offset='g')
    fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', arr, fb.dyn(y)), offset='g')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', y), offset='g')
    fb.op('Call2', dst=ok, fun=raidable, arg0=y, arg1=orders)
    fb.op('JFalse', cond=ok, offset='g')
    fb.op('Call3', dst=ok, fun=raidsup, arg0=y, arg1=dy, arg2=best_sd)
    fb.op('JFalse', cond=ok, offset='g')
    fb.op('JFalse', cond=rec, offset='grecok')
    fb.op('Mov', dst=ye, src=y)
    fb.op('Call2', dst=q, fun=land, arg0=fac, arg1=ye)
    fb.op('JSGt', a=dy, b=q, offset='g')  # recovering: the village must be nearer than our land
    fb.label('grecok')
    fb.op('Mov', dst=ny, src=y)
    fb.op('Mov', dst=nd, src=dy)
    fb.op('JAlways', offset='g')
    fb.label('gdone')
    fb.op('JNull', reg=ny, offset='seldone')
    b.call('hl.types.ArrayObj.push', arr, fb.dyn(ny))
    fb.op('Call1', dst=p, fun=pw, arg0=ny)
    fb.op('Add', dst=m, a=m, b=p)
    fb.op('JSLt', a=m, b=need, offset='sel')
    fb.label('seldone')
    fb.op('JSLte', a=b.field(arr, 'length'), b=zi, offset='end')
    # home race with the armies actually picked (the candidate test estimated them)
    fb.op('JSLte', a=best_hh, b=zero, offset='homeok')
    fb.op('Add', dst=lim, a=best_sd, b=home_m)
    fb.op('Call3', dst=best_ms, fun=homeown, arg0=fac, arg1=lim, arg2=arr)
    fb.op('Mul', dst=q, a=best_ms, b=own_t)
    fb.op('Mul', dst=r, a=best_hh, b=enter)
    fb.op('JSGte', a=q, b=r, offset='homeok')
    _throttle(fb, b, cx, 'raidx', fac, RAID_GAP, 'end')
    _log_ev(fb, b, cx, helpers, 'raid', [('f', fb.get(fac, 'kind')), ('act', 'refuse'), ('why', 'home'),
                                         ('tgt', best), ('H', best_h), ('M', m), ('n', b.field(arr, 'length')),
                                         ('dm', best_d), ('sd', best_sd), ('hh', best_hh), ('ms', best_ms),
                                         ('ax', ax), ('nc', vn)])
    fb.op('JAlways', offset='end')
    fb.label('homeok')
    add = cx.fn('logic.ai.AIOrders.addOrder')
    at = [a.value for a in cx.code.types[add.type.value].definition.args]
    kind = fb.reg(cx.t('logic.ai.AIOrderType'))
    fb.op('MakeEnum', dst=kind, construct=MILITARY, args=[])
    mm, om = _new_array(fb, b, cx), _new_array(fb, b, cx)  # no missions (vanilla iterates these arrays)
    nulls = []
    for n in (9, 10):  # data, onComplete (null-checked by addOrder's completion closure)
        rr = fb.reg(at[n])
        fb.op('Null', dst=rr)
        nulls.append(rr)
    res = fb.reg(cx.t('logic.ai.AIOrder'))
    fb.op('CallN', dst=res, fun=helpers.get('addOrder', add.findex.value),
          args=[orders_obj, kind, b.const('i32', 1), arr, best, fb.string('ArmySiege'), pillage_s,
                mm, om] + nulls)
    fb.op('Bool', dst=ok, value=False)
    fb.op('JNull', reg=res, offset='fail')
    fb.op('Bool', dst=ok, value=True)
    b.call('haxe.ds.ObjectMap.set', lastmap, fb.dyn(fac), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', retrymap, fb.dyn(best), fb.dyn(t))
    fb.label('fail')
    _log_ev(fb, b, cx, helpers, 'raid', [('f', fb.get(fac, 'kind')), ('act', 'start'), ('tgt', best), ('H', best_h),
                                         ('M', m), ('n', b.field(arr, 'length')), ('dm', best_d),
                                         ('sd', best_sd), ('hh', best_hh), ('ms', best_ms), ('ax', ax),
                                         ('nc', vn), ('ok', ok), ('rec', rec), ('bh', nbh)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
