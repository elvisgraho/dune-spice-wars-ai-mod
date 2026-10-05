"""Raid: pillage for loot with armies that have nothing better to do (AI-POLICY §5a goal 5b), and give pillages up when
something more important needs their armies.

Vanilla pillages only from its Pillage gauge, which barely rises, and only with idle armies at >= 90% supply: a
stack standing next to a weakly held enemy village walked home to resupply instead (Fremen at Od-lulah), and a stack
that can't annex (Smugglers short of authority) sat at home for minutes. A pillage loots the village's production,
refills OCC_REFILL of max supply and occupying doesn't drain. Its costs: the village is Devastated for 20 days
(production halved, no siege action possible) and the pillager's Annex authority cost there is doubled (trait
Pillaged), so the villages vanilla would annex next are never raided.

Abort pass, every CHECK s, over every Military ArmySiege "Pillage" order of ours (raid's and vanilla's), and while
aimod_defend is set over our "Annex" orders too (only the `defend` trigger, and only when its fit armies lift the
defense to `enter`; never on the defended village). In Action the militia fight (progress 0) is never broken off, and a
trigger on an occupation under way splits it instead of cancelling (aimod_relunits, rules/release.py: armies needing
the refill stay, else the weakest; the rest are released; logged act split). First trigger wins, else stop(Cancel):
- defend: our structure is besieged (aimod_defend) within RECALL_R of the target, our armies already at it (within
  LOCAL, any task) + free ones within GATHER_R (+ our cover) are short of ENTER x (threat + enemy cover) / terrain there, and the raid has armies fit to defend
  (life >= MIN_LIFE, what the contest hunt takes; supply is the hunt's absolute trip budget, not a share);
- home: hostile armies free to strike are closer to our land than the target + HOME_M (aimod_home) and our armies
  at home without the raid's (aimod_homeown) x OWN_T fall below ABORT x them;
- weak (still walking, phase < Engage): raid power + our cover below the launch test x ABORT / ENTER at the target:
  ABORT x (armies within LOCAL + enemy cover + militia + raiders), ABORT x RAID_FAR / ENTER (an at-war village:
  ABORT x RAID_OWNED_FAR / ENTER) x (aimod_react + the
  same) / terrain (relief arrived; in the fight the vanilla fight retreat decides).

Launch pass, every START s per faction, at most one launch per RAID_GAP s, never while defending (aimod_defend) or
while a Defense order of ours holds armies (logged act=refuse why=dfn, n its armies). While the
director's posture is RECOVER (most of our power worn, rules/strat.py) only a raid that is itself a recovery: each
of its armies has the village nearer than our land (the pillage refill replaces the walk home; a stack at home
doesn't go out) and the entry test is RAID_TO instead of ENTER (overwhelming, short). Logged rec=true:
- candidates: vanilla's own pillage list (AIMilitary.getSiegeableVillages "Pillage": pillage allowed for us, not
  Devastated, no order on it, in supply range, sandstorms, ...) with its desiredStatus gate lifted for this scan
  (map `rscan`, read by strat_levers: vanilla's daily wish is 0 toward most at-war factions, so the enemy village
  next to a won fight was never a candidate), owned by nobody or by a faction at war with us, not
  a main base, not besieged; minus the vanilla Annex choices (getSiegeableVillages "Annex" with tryAnnexation's
  aggressiveness gate, target scores, pickMapBest top RAID_KEEP) and the villages `annex-keep` listed within AKEEP_T
  (below; also kept out of vanilla's Pillage targets: siege.build_scoring), villages within
  BUNKER_R of our main base (the bunker redirect annexes them first), villages on an uncontested deep-desert ring
  we are closing (aimod_ddclean, Fremen), neutral villages on the ring of an unowned deep desert next to our land
  (Fremen / DD_ATB, user) unless another faction's main base is within DD_BASE_R or a hostile army stands at it (log
  act=skip why=ring), villages with our own Underworld HQ (our
  income there), villages our raid launched on less than RAID_RETRY s ago (aborted / cancelled at once: no loop)
  and villages behind another faction's main base (`_behind`, BEHIND_E: counted as bh in the start / refuse rows),
  and while we own fewer than RAID_GROW_N villages every neutral village within our Annex reach + RAID_GROW_ZONES
  (expansion room, user);
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
from rules.strat import _has_action


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
               homeown, scores, neutral, relunits, owner_pw, sqr):
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
    raid_to = _ratio(fb, b, RAID_TO)
    min_life = _ratio(fb, b, MIN_LIFE)
    t_false, t_true = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_false, value=False)
    fb.op('Bool', dst=t_true, value=True)
    no_arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=no_arr)
    pillage_s = fb.string('Pillage')
    pillage = fb.dyn(pillage_s)
    lib_s = fb.string('Liberate')
    vlib, best_lib = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))  # DMZ: this candidate / the chosen one is liberated
    fb.op('Bool', dst=best_lib, value=False)
    i, j, k, idx, ph = (fb.reg(cx.t('i32')) for _ in range(5))
    h, m, p, q, r, sd, lim, dy, tf, pr, hh, ms, hp, hl = (fb.reg(cx.t('f64')) for _ in range(14))
    ok, anx = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    ve, de = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    ye = fb.reg(cx.t('ent.Entity'))

    no_ent = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=no_ent)

    def cover_at(dst, at, own, target=False, atk=False):
        """target: the structure at `at` is the raid target; its own turrets count (they fire until the pillage
        starts; aimod_cover silences a besieged village by itself). atk: our cover at the raid target counts
        x OWN_COVER_ATK."""
        fb.op('CallN', dst=dst, fun=cover, args=[fac, at, no_ent if target else at, t_true if own else t_false,
                                                 no_arr])
        if atk:
            _atk_cover(fb, b, dst)

    def _owner_floor(dst, s):
        """dst = max(dst, aimod_owner_pw(fac, s)): an at-war village's owner armies we can't see count where we last
        saw them / at its main base (fog: never assume an unseen defender is gone)."""
        u = _uid('of')
        fb.op('Call2', dst=q, fun=owner_pw, arg0=fac, arg1=s)
        fb.op('JSLte', a=q, b=dst, offset=u)
        fb.op('Mov', dst=dst, src=q)
        fb.label(u)

    def their_side(dst, s):
        """dst = at-war armies in reach + enemy turret cover + militia at structure s (entity reg ve)."""
        fb.op('Call3', dst=dst, fun=react, arg0=fac, arg1=ve, arg2=local)
        _owner_floor(dst, s)
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
    # a bunker split (rules/bunker.py, map `bspo`) is part of its capture, not a raid: the defenders fighting the
    # capture next door read as its side (Harkonnen's Liberate of Lar-dah aborted `weak` 0.27 s after the split)
    fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'bspo'), fb.dyn(o)), offset='ord')
    # our Annex orders too, for `defend` only (a capture next door outweighs a new village: Harkonnen annexed Gurlab
    # while Smugglers took Zadak 177 from Carthag); never the defended village itself
    fb.op('Bool', dst=anx, value=False)
    fb.op('JEq', a=b.call('String.__compare', sa, pillage), b=zi, offset='ispil')
    fb.op('JEq', a=b.call('String.__compare', sa, fb.dyn(fb.string('Liberate'))), b=zi, offset='ispil')  # DMZ
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
    # in Action the militia fight (progress 0) is never broken off, and an occupation under way is split, not
    # cancelled (ab_* below): one army finishes it (removeUnit cancels an order only before Action or when empty)
    fb.op('JNotEq', a=ph, b=b.const('i32', ACTION), offset='running')
    fb.op('JSLte', a=pr, b=zero, offset='ord')
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
    # home: hostile armies closer to our land than the raid, and too few of ours at home without it. Off (user: react
    # to an attack on our structures only, `defend` above, which leaves one army to finish an occupation under way;
    # armies merely near our land don't recall a raid: Harkonnen's 9 armies left by Atreides' Cease Fire at Qal-val
    # never took Anna-ram next door, 360k hostile near home vs 66k there)
    fb.label('a_home')
    fb.op('JAlways', offset='a_weak')
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
    # the launch test scaled by ABORT / ENTER (the policy's enter -> abort gap) on both of its parts: the local side
    # (armies within LOCAL + cover + militia + raiders) at ABORT, everything in REACT_R at ABORT x RAID_FAR / ENTER.
    # A flat ABORT x all of it sat above the launch's RAID_FAR x all of it: Smugglers raided Ash-in at 92.4k vs
    # 132.6k (0.70 > 0.667) and aborted `weak` 1 s later on the same numbers
    fb.op('JSGte', a=ph, b=b.const('i32', REGROUP + 1), offset='ord')
    their_side(h, ov)
    fb.op('Call3', dst=q, fun=react, arg0=fac, arg1=ve, arg2=local)
    fb.op('Sub', dst=hl, a=h, b=q)
    fb.op('Call3', dst=q, fun=threat, arg0=fac, arg1=ve, arg2=local)
    fb.op('Add', dst=hl, a=hl, b=q)
    fb.op('Mul', dst=hl, a=hl, b=abort)
    fb.op('Mul', dst=q, a=h, b=_ratio(fb, b, ABORT * RAID_FAR / ENTER))
    fb.op('JNull', reg=b.call('ent.Entity.get_owner', ve), offset='aw_nown')
    fb.op('Mul', dst=q, a=h, b=_ratio(fb, b, ABORT * RAID_OWNED_FAR / ENTER))  # an at-war village: its whole
    # side at the launch test's RAID_OWNED_FAR, same launch / abort gap as the rest
    fb.label('aw_nown')
    fb.op('JSGte', a=hl, b=q, offset='aw_max')
    fb.op('Mov', dst=hl, src=q)
    fb.label('aw_max')
    cover_at(q, ve, True, atk=True)
    fb.op('Add', dst=r, a=m, b=q)
    fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', ve))
    fb.op('SDiv', dst=q, a=hl, b=tf)
    fb.op('JSLt', a=r, b=q, offset='ab_weak')
    fb.op('JAlways', offset='ord')
    rel = fb.reg(cx.t('i32'))
    for why, hr, mr in (('defend', h, r), ('home', hh, ms), ('weak', h, r)):
        fb.label(f'ab_{why}')
        if why != 'weak':  # weak is tested while walking only
            # Action, occupation under way: split instead of cancel (aimod_relunits: armies needing the refill stay,
            # else the weakest; user: "1 unit can always finish things"): a 20k force starting a capture next door no
            # longer costs a pillage at 30%
            fb.op('JNotEq', a=ph, b=b.const('i32', ACTION), offset=f'ab_{why}_stop')
            # what stays must still hold the capture: ENTER x (at-war armies in reach + enemy cover + militia +
            # raiders at it) / terrain (aimod_relunits keep)
            kp = fb.reg(cx.t('f64'))
            their_side(kp, ov)
            fb.op('Mul', dst=kp, a=kp, b=enter)
            fb.op('Call2', dst=tf, fun=terrain, arg0=fac, arg1=b.call('ent.Entity.get_zone', ve))
            fb.op('SDiv', dst=kp, a=kp, b=tf)
            fb.op('Call3', dst=rel, fun=relunits, arg0=o, arg1=anx, arg2=kp)
            fb.op('JSGt', a=rel, b=zi, offset=f'ab_{why}_rel')
            # nobody may leave without losing the capture: it is held, the need stays unanswered (visible in the log)
            _throttle(fb, b, cx, 'rkeep', o, 30, 'ord')
            _log_ev(fb, b, cx, helpers, 'raid', [('f', fb.get(fac, 'kind')), ('act', 'keep'), ('why', why),
                                                 ('tgt', ve), ('H', hr), ('M', mr), ('pr%', pr), ('n', un), ('sa', sa),
                                                 ('kp', kp)])
            fb.op('JAlways', offset='ord')
            fb.label(f'ab_{why}_rel')
            relf = fb.reg(cx.t('f64'))
            fb.op('ToSFloat', dst=relf, src=rel)
            _log_ev(fb, b, cx, helpers, 'raid', [('f', fb.get(fac, 'kind')), ('act', 'split'), ('why', why),
                                                 ('tgt', ve), ('H', hr), ('M', mr), ('ph', ph), ('pr%', pr),
                                                 ('sd', sd), ('n', un), ('sa', sa), ('rel', relf)])
            fb.op('JAlways', offset='ord')
            fb.label(f'ab_{why}_stop')
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
    # ... nor while a Defense order of ours holds armies (vanilla checkStructures: a fight at one of our structures,
    # siege or not): it takes the raid's armies (prio 5 > 1) seconds later, the raid relaunches next pass (Smugglers'
    # Hakhelon raids 49:40 / 51:00, emptied by Ey-bu Defenses 21 s / 3 s after launch, match 2026-10-04 19:14)
    dfo = b.field(b.field(b.field(0, 'controller'), 'aiOrders'), 'orders')
    fb.op('JNull', reg=dfo, offset='dfnok')
    dk, dix = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=dk, src=b.field(dfo, 'length'))
    b.loop_head('dfl')
    fb.op('JSLte', a=dk, b=b.const('i32', 0), offset='dfnok')
    fb.op('Sub', dst=dk, a=dk, b=b.const('i32', 1))
    dor = b.cast(b.call('hl.types.ArrayObj.getDyn', dfo, dk), 'logic.ai.AIOrder')
    fb.op('JNull', reg=dor, offset='dfl')
    fb.op('EnumIndex', dst=dix, value=b.field(dor, 'type'))
    fb.op('JNotEq', a=dix, b=b.const('i32', DEFENSE), offset='dfl')
    dou = b.field(dor, 'units')
    fb.op('JNull', reg=dou, offset='dfl')
    fb.op('JSLte', a=b.field(dou, 'length'), b=b.const('i32', 0), offset='dfl')
    _throttle(fb, b, cx, 'rdfn', fac, RAID_GAP, 'end')
    dnf = fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=dnf, src=b.field(dou, 'length'))
    _log_ev(fb, b, cx, helpers, 'raid', [('f', fb.get(fac, 'kind')), ('act', fb.string('refuse')),
                                         ('why', fb.string('dfn')), ('n', dnf)])
    fb.op('JAlways', offset='end')
    fb.label('dfnok')
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
    # ... but an Annex failing for lack of armies (map `anea`, rules/raid.build_annex_wait: NotEnoughArmies /
    # ArmyNotStrongEnough / NoAvailableArmy within RAID_ANNEX_FRESH s) is coming once armies are free: no raid takes
    # them, for at most RAID_ANNEX_MAX s of that failure streak (user: Fremen's Zayras Annex found 2-3 free armies
    # 11:03-12:50 while raids on Hamah / Eydah / Larnih held 6-9 each; 11 of 30 raids launched within 30 s of such a
    # failure; then the Annex went to Had-fir with 8 armies walking 338)
    anv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'anea'), fb.dyn(fac))
    fb.op('JNull', reg=anv, offset='gaugeok')
    fb.op('SafeCast', dst=gv, src=anv)
    fb.op('Sub', dst=gv, a=t, b=gv)
    fb.op('JSGt', a=gv, b=b.const('f64', RAID_ANNEX_FRESH), offset='gaugeok')
    an0 = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'anea0'), fb.dyn(fac))
    fb.op('JNull', reg=an0, offset='gaugeok')
    fb.op('SafeCast', dst=gv, src=an0)
    fb.op('Sub', dst=gv, a=t, b=gv)
    fb.op('JSGt', a=gv, b=b.const('f64', RAID_ANNEX_MAX), offset='gaugeok')
    _throttle(fb, b, cx, 'rawait', fac, 30, 'end')
    _log_ev(fb, b, cx, helpers, 'raid', [('f', fb.get(fac, 'kind')), ('act', 'refuse'), ('why', 'annexwait'),
                                         ('st', gv)])
    fb.op('JAlways', offset='end')
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
    # the Annex scan's reach (map `ascan`, rules/strat.py annex-reach: vanilla's Annex calls get ANNEX_ZONES more):
    # the same list vanilla's tryAction picks from, else a village 2 zones out that it is about to annex gets raided
    ascan = _global_map(fb, b, cx, 'ascan')
    b.call('haxe.ds.ObjectMap.set', ascan, fb.dyn(fac), fb.dyn(b.field(_state(fb, b, cx), 'time')))
    b.call('logic.ai.$AIMilitary.getSiegeableVillages', ann, annex_s, fac, aargs)
    b.call('haxe.ds.ObjectMap.set', ascan, fb.dyn(fac), nodyn)
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
    # ... nor what annex-keep listed as one of our Annex choices within AKEEP_T (a village sliding out of the top 3)
    akt = b.call('haxe.ds.ObjectMap.get', _fac_map(fb, b, cx, 'akeep', fac), fb.dyn(ve))
    fb.op('JNull', reg=akt, offset='akok')
    fb.op('SafeCast', dst=q, src=akt)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSLt', a=q, b=b.const('f64', AKEEP_T), offset='v')
    fb.label('akok')
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
    # ... nor any neutral village on the ring of an unowned deep desert next to our land (Fremen / DeepDesert_
    # Surounded_GainControl; the Annex ring reach's test, strat.py), unless an enemy is too close (user): another
    # faction's main base within DD_BASE_R of it, or a hostile army at it (aimod_threat within LOCAL). Fremen pillaged
    # their ring villages Bir-dalus / Hadanim 3x each (match 2026-10-04 20:53)
    fb.op('JNotNull', reg=vo, offset='noring')
    rpk = b.cast(fb.get(fac, 'kind'), 'String')
    fb.op('JNull', reg=rpk, offset='rp_atb')
    fb.op('JEq', a=b.call('String.__compare', rpk, fb.dyn(fb.string('Fremen'))), b=b.const('i32', 0), offset='rp_go')
    fb.label('rp_atb')
    rph = cx.fn('ent.Object.hasAttribute')
    rpt = [a_.value for a_ in cx.code.types[rph.type.value].definition.args]
    rpo, rpr, rpf = fb.reg(rpt[0]), fb.reg(rpt[2]), fb.reg(rpt[3])
    fb.op('Mov', dst=rpo, src=fac)
    fb.op('Null', dst=rpr)
    fb.op('Null', dst=rpf)
    rpb = fb.reg(cx.t('bool'))
    fb.op('Call4', dst=rpb, fun=rph.findex.value, arg0=rpo, arg1=b.const('i32', DD_ATB), arg2=rpr, arg3=rpf)
    fb.op('JFalse', cond=rpb, offset='noring')
    fb.label('rp_go')
    rpn = b.field(vz, 'neighbors')
    fb.op('JNull', reg=rpn, offset='noring')
    rpi, rpj = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=rpi, src=b.const('i32', 0))
    b.loop_head('rp_d')
    fb.op('JSGte', a=rpi, b=b.field(rpn, 'length'), offset='noring')
    rdz = b.cast(b.call('hl.types.ArrayObj.getDyn', rpn, rpi), 'ent.Zone')
    fb.op('Incr', dst=rpi)
    fb.op('JNull', reg=rdz, offset='rp_d')
    fb.op('JFalse', cond=b.call('ent.Zone.isDeepDesert', rdz), offset='rp_d')
    fb.op('JNotNull', reg=b.field(rdz, 'owner'), offset='rp_d')
    rdn = b.field(rdz, 'neighbors')
    fb.op('JNull', reg=rdn, offset='rp_d')
    fb.op('Mov', dst=rpj, src=b.const('i32', 0))
    b.loop_head('rp_e')
    fb.op('JSGte', a=rpj, b=b.field(rdn, 'length'), offset='rp_d')
    rmz = b.cast(b.call('hl.types.ArrayObj.getDyn', rdn, rpj), 'ent.Zone')
    fb.op('Incr', dst=rpj)
    fb.op('JNull', reg=rmz, offset='rp_e')
    fb.op('JNotEq', a=b.field(rmz, 'owner'), b=fac, offset='rp_e')
    # on our ring: an enemy too close? (another faction's main base within DD_BASE_R, a hostile army at it)
    rpq = fb.reg(cx.t('f64'))
    fb.op('Call3', dst=rpq, fun=threat, arg0=fac, arg1=ve, arg2=b.const('f64', LOCAL))
    fb.op('JSGt', a=rpq, b=b.const('f64', 0), offset='noring')
    rfs = b.cast(fb.get(_state(fb, b, cx), 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=rfs, offset='rp_keep')
    rk, rm = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=rk, src=b.const('i32', 0))
    b.loop_head('rp_f')
    fb.op('JSGte', a=rk, b=b.field(rfs, 'length'), offset='rp_keep')
    rof = b.cast(b.call('hl.types.ArrayObj.getDyn', rfs, rk), 'ent.Faction')
    fb.op('Incr', dst=rk)
    fb.op('JNull', reg=rof, offset='rp_f')
    fb.op('JEq', a=rof, b=fac, offset='rp_f')
    rmbs = b.field(rof, 'mainBases')
    fb.op('JNull', reg=rmbs, offset='rp_f')
    fb.op('Mov', dst=rm, src=b.const('i32', 0))
    b.loop_head('rp_g')
    fb.op('JSGte', a=rm, b=b.field(rmbs, 'length'), offset='rp_f')
    rmb = b.cast(b.call('hl.types.ArrayObj.getDyn', rmbs, rm), 'ent.Entity')
    fb.op('Incr', dst=rm)
    fb.op('JNull', reg=rmb, offset='rp_g')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', ve, rmb), b=b.const('f64', DD_BASE_R), offset='noring')
    fb.op('JAlways', offset='rp_g')
    fb.label('rp_keep')
    _throttle(fb, b, cx, 'rring', ve, 60, 'v')
    _log_ev(fb, b, cx, helpers, 'raid', [('f', fb.get(fac, 'kind')), ('act', fb.string('skip')),
                                         ('why', fb.string('ring')), ('tgt', ve)])
    fb.op('JAlways', offset='v')
    fb.label('noring')
    # expansion room (user): while we own fewer than RAID_GROW_N villages, no neutral village within our Annex reach
    # + RAID_GROW_ZONES (vanilla's maxSupplyDistZones + ANNEX_ZONES + 1): a pillage leaves it Devastated 20 days and
    # doubles our Annex cost there (Harkonnen raided its 4 neutral neighbours at 2:30-4:20 and again the moment they
    # recovered, 14:10-16:00, and sat at 1 village); from RAID_GROW_N on, only our Annex choices are kept (above)
    fb.op('JNotNull', reg=vo, offset='grow_ok')
    fb.op('JSGte', a=b.field(b.call('ent.Faction.getVillages', fac), 'length'), b=b.const('i32', RAID_GROW_N),
          offset='grow_ok')
    fb.op('JNull', reg=vz, offset='grow_ok')
    gd = cx.fn('ent.Zone.getDistanceToPlayerTerritory')
    gdt = [x.value for x in cx.code.types[gd.type.value].definition.args]
    gpf, gtr = fb.reg(gdt[1]), fb.reg(gdt[2])
    fb.op('Mov', dst=gpf, src=fac)
    _box_true(fb, cx, gtr)  # considerAirfields is Null<Bool>: box it (a raw Bool there threw in the trap)
    gzd = fb.reg(cx.t('i32'))
    fb.op('Call3', dst=gzd, fun=gd.findex.value, arg0=vz, arg1=gpf, arg2=gtr)
    gmx = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=gmx, src=b.field(0, 'maxSupplyDistZones'))
    fb.op('Add', dst=gmx, a=gmx, b=b.const('i32', ANNEX_ZONES + RAID_GROW_ZONES))
    fb.op('JSLte', a=gzd, b=gmx, offset='v')
    fb.label('grow_ok')
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
    # DMZ (rules/dmz.py): a border village of an at-war neighbour holding >= DMZ_WAR of them is liberated, not
    # pillaged (a pillage devastates it and doubles our Annex cost there); unaffordable: wait; Liberate not
    # available at all: left alone, unless the director pressed it for pillage
    fb.op('Bool', dst=vlib, value=False)
    fb.op('Call2', dst=ok, fun=helpers['dmzv'], arg0=fac, arg1=v)
    fb.op('JFalse', cond=ok, offset='dmz_ok')
    _has_action(fb, b, cx, v, fac, 'Liberate', 'dmz_av', 'dmz_no')
    fb.label('dmz_av')
    lcf = cx.fn('ent.comp.SiegeComponent.getOccupationActionCost')
    lcn = fb.reg(cx.code.types[lcf.type.value].definition.args[2].value)
    fb.op('Null', dst=lcn)
    lcost = fb.reg(cx.code.types[lcf.type.value].definition.ret.value)
    fb.op('Call4', dst=lcost, fun=lcf.findex.value, arg0=b.field(v, 'siege'), arg1=lib_s, arg2=lcn, arg3=fac)
    lhf = cx.fn('logic.ai.AIController.hasResources')
    lhn = fb.reg(cx.code.types[lhf.type.value].definition.args[2].value)
    fb.op('Null', dst=lhn)
    fb.op('Call3', dst=ok, fun=lhf.findex.value, arg0=b.field(0, 'controller'), arg1=lcost, arg2=lhn)
    fb.op('JFalse', cond=ok, offset='v')  # can liberate, can't pay yet: wait (never pillage it meanwhile)
    fb.op('Bool', dst=vlib, value=True)
    fb.op('JAlways', offset='dmz_ok')
    fb.label('dmz_no')
    fb.op('JFalse', cond=pref, offset='v')
    fb.label('dmz_ok')
    # our raid force there (+ our turret cover), with the supply for the raid and the way home; our armies at home
    fb.op('Call2', dst=sd, fun=land, arg0=fac, arg1=ve)
    fb.op('Add', dst=lim, a=sd, b=home_m)
    cover_at(m, ve, True, atk=True)
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
    rdo = fb.reg(cx.t('bool'))  # a neutral village: no worm ride there (ride.py `npil`)
    fb.op('Bool', dst=rdo, value=False)
    rde_ = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=rde_, src=ve)
    fb.op('JNull', reg=b.call('ent.Entity.get_owner', rde_), offset='rdo_ve')
    fb.op('Bool', dst=rdo, value=True)
    fb.label('rdo_ve')
    fb.op('CallN', dst=ok, fun=raidsup, args=[y, dy, sd, rdo])
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
    _owner_floor(hq, v)
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
    # an at-war village: its owner defends it (not "may come"): the whole side at RAID_OWNED_FAR (was ENTER), not RAID_FAR
    # (Smugglers' Liberate of Fremen's Nunesek 46:40 started at 408k vs 355k, lost 3 armies in 15 s when they came)
    fq = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=fq, src=_ratio(fb, b, RAID_FAR))
    fb.op('JNull', reg=b.call('ent.Entity.get_owner', ve), offset='rf_n')
    # ... at RAID_OWNED_FAR (user: too safe harassing enemies; Fremen skipped Smugglers' Ad-Al'lab at 390k vs
    # 267k armies within REACT_R + 100k turrets + 41k militia, x 1.5 / 0.8 terrain = 765k, and pillaged neutral
    # Sin-Al'in instead, match 2026-10-04 21:1x); what stands at the village still needs ENTER (above)
    fb.op('Mov', dst=fq, src=_ratio(fb, b, RAID_OWNED_FAR))
    fb.label('rf_n')
    fb.op('Mul', dst=q, a=h, b=fq)
    fb.op('SDiv', dst=q, a=q, b=tf)
    fb.op('JSLt', a=m, b=q, offset='refuse')
    # home race: hostile armies nearer our land than the raid must be held by what stays home. The raid takes
    # about RAID_TO x their side (the launch sizing), at most the raid-ready power standing at home (mh); the
    # launch re-checks with the armies actually picked
    # off (user): only an attack on our structures holds raids back (the `defend` gate at the start pass)
    fb.op('Mov', dst=hh, src=zero)
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
                     (best_hh, hh), (best_ms, ms), (best_lib, vlib)):
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
    cover_at(m, best, True, atk=True)
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
    # the first army picked walks (flyers can't occupy; nearest-first would otherwise pick a lone ship every time)
    fb.op('JSGt', a=b.field(arr, 'length'), b=zi, offset='gfly')
    fb.op('JTrue', cond=b.call('ent.Unit.isFlying', y), offset='g')
    fb.label('gfly')
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', y), offset='g')
    fb.op('Call2', dst=ok, fun=raidable, arg0=y, arg1=orders)
    fb.op('JFalse', cond=ok, offset='g')
    rdo = fb.reg(cx.t('bool'))  # a neutral village: no worm ride there (ride.py `npil`)
    fb.op('Bool', dst=rdo, value=False)
    rde_ = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=rde_, src=best)
    fb.op('JNull', reg=b.call('ent.Entity.get_owner', rde_), offset='rdo_best')
    fb.op('Bool', dst=rdo, value=True)
    fb.label('rdo_best')
    fb.op('CallN', dst=ok, fun=raidsup, args=[y, dy, best_sd, rdo])
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
    # square law vs its militia (rules/sqlaw.py): keep picking until SQ_MIN
    bst = fb.reg(cx.t('ent.Structure'))
    fb.op('Mov', dst=bst, src=b.cast(fb.dyn(best), 'ent.Structure'))
    sqv = fb.reg(cx.t('f64'))
    fb.op('Call2', dst=sqv, fun=sqr, arg0=arr, arg1=bst)
    sqm = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=sqm, src=_ratio(fb, b, SQ_MIN))
    _nbump(fb, b, cx, fac, best, sqm)  # a neutral village whose militia beat us lately: a little more
    fb.op('JSLt', a=sqv, b=sqm, offset='sel')
    fb.label('seldone')
    fb.op('JSLte', a=b.field(arr, 'length'), b=zi, offset='end')
    fb.op('Mov', dst=bst, src=b.cast(fb.dyn(best), 'ent.Structure'))
    fb.op('Call2', dst=sqv, fun=sqr, arg0=arr, arg1=bst)
    fb.op('Mov', dst=sqm, src=_ratio(fb, b, SQ_MIN))
    _nbump(fb, b, cx, fac, best, sqm)
    fb.op('JSGte', a=sqv, b=sqm, offset='sq_ok')
    b.call('haxe.ds.ObjectMap.set', retrymap, fb.dyn(best), fb.dyn(t))  # not this village again for RAID_RETRY
    _throttle(fb, b, cx, 'raidx', fac, RAID_GAP, 'end')
    _log_ev(fb, b, cx, helpers, 'raid', [('f', fb.get(fac, 'kind')), ('act', 'refuse'), ('why', 'sq'), ('tgt', best),
                                         ('sq%', sqv), ('M', m), ('H', best_h), ('n', b.field(arr, 'length'))])
    fb.op('JAlways', offset='end')
    fb.label('sq_ok')
    # flyers can't occupy (Unit.isFlying: ships, frigates): a pick of flyers only would stand at the village forever
    ga = fb.reg(cx.t('i32'))
    gi = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=ga, src=zi)
    gy = _army_loop(fb, b, arr, b.field(arr, 'length'), gi, 'gnd', 'gnddone')
    fb.op('JTrue', cond=b.call('ent.Unit.isFlying', gy), offset='gnd')
    fb.op('Incr', dst=ga)
    fb.label('gnddone')
    fb.op('JSGt', a=ga, b=zi, offset='gndok')
    _throttle(fb, b, cx, 'raidx', fac, RAID_GAP, 'end')
    _log_ev(fb, b, cx, helpers, 'raid', [('f', fb.get(fac, 'kind')), ('act', 'refuse'), ('why', 'air'), ('tgt', best),
                                         ('n', b.field(arr, 'length'))])
    fb.op('JAlways', offset='end')
    fb.label('gndok')
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
    sact = fb.reg(cx.t('String'))
    fb.op('Mov', dst=sact, src=pillage_s)
    fb.op('JFalse', cond=best_lib, offset='sact')
    fb.op('Mov', dst=sact, src=lib_s)  # DMZ: Liberate (aiPrio 1, as Pillage)
    fb.label('sact')
    fb.op('CallN', dst=res, fun=helpers.get('addOrder', add.findex.value),
          args=[orders_obj, kind, b.const('i32', 1), arr, best, fb.string('ArmySiege'), sact,
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
                                         ('nc', vn), ('ok', ok), ('rec', rec), ('bh', nbh), ('lib', best_lib)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


def build_annex_keep(cx, helpers, scores):
    """aimod_annex_keep(mil, dt): every START s per faction, its next Annex choices as vanilla's tryAction would pick
    them (getSiegeableVillages "Annex" with tryAnnexation's aggressiveness gate and the annex-reach marker `ascan`,
    our target scores, pickMapBest top RAID_KEEP) go into map `akeep` (faction -> village -> time): for AKEEP_T s
    they are no raid candidate and no target of vanilla's Pillage gauge (siege.build_scoring). Its own tick rule,
    not raid's launch pass: that one exits early for minutes (raid gap, defending, Annex gauge full) and the
    protection lapsed while vanilla's gauge kept pillaging (Smugglers' top choices Arslulah x3, Ya-lab). Per faction:
    two factions eyeing one village each keep it. Fails safe: in a trap."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = b.field(_state(fb, b, cx), 'time')
    _tick(fb, b, cx, t, START, 'end')
    zi = b.const('i32', 0)
    t_false = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_false, value=False)
    annex_s = fb.string('Annex')
    aargs = b.call('$HAI.getDefaultStructureArgs', annex_s)
    fb.op('JNotLt', a=b.call('logic.ai.AIMilitary.get_aggressiveness', 0),
          b=b.call('logic.ai.AIMilitary.getActionRequiredAggressivenessByKind', 0, fb.string('Annexation')),
          offset='aggr')
    fb.op('SetField', obj=aargs, field=cx.field(fb.regs[aargs], 'allowEnemy'), src=t_false)
    fb.label('aggr')
    ann = _new_array(fb, b, cx)
    nodyn = fb.reg(cx.t('dyn'))
    fb.op('Null', dst=nodyn)
    ascan = _global_map(fb, b, cx, 'ascan')
    b.call('haxe.ds.ObjectMap.set', ascan, fb.dyn(fac), fb.dyn(t))
    g2 = fb.try_()  # the marker must not outlive a throwing scan
    b.call('logic.ai.$AIMilitary.getSiegeableVillages', ann, annex_s, fac, aargs)
    fb.end_try(g2)
    b.call('haxe.ds.ObjectMap.set', ascan, fb.dyn(fac), nodyn)
    keep = _fac_map(fb, b, cx, 'akeep', fac)
    # a kept village that left the Annex scan (taken by another faction we can't annex, devastated, out of reach)
    # is no choice any more: protecting it AKEEP_T longer blocked the raid on it (Fremen annexed Smugglers' choice
    # Tabdalus at 18:03 under Smugglers' 365k; no raid until 21:20, by then Fremen's 557k and a turret were back)
    vs = b.field(_state(fb, b, cx), 'villages')
    fb.op('JNull', reg=vs, offset='kpdone')
    vi = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=vi, src=zi)
    b.loop_head('kprune')
    fb.op('JSGte', a=vi, b=b.field(vs, 'length'), offset='kpdone')
    vv = b.call('hl.types.ArrayObj.getDyn', vs, vi)
    fb.op('Incr', dst=vi)
    fb.op('JNull', reg=vv, offset='kprune')
    fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', ann, vv), offset='kprune')
    b.call('haxe.ds.ObjectMap.remove', keep, vv)
    fb.op('JAlways', offset='kprune')
    fb.label('kpdone')
    fb.op('JSLte', a=b.field(ann, 'length'), b=zi, offset='end')
    sfn = cx.fn('logic.ai.$HScoring.structures')
    sat = [a.value for a in cx.code.types[sfn.type.value].definition.args]
    snull = []
    for n in (3, 4, 5):
        rr = fb.reg(sat[n])
        fb.op('Null', dst=rr)
        snull.append(rr)
    sc = fb.reg(cx.code.types[sfn.type.value].definition.ret.value)
    fb.op('CallN', dst=sc, fun=scores, args=[ann, fac, annex_s] + snull)
    fb.op('JNull', reg=sc, offset='end')
    pmb = cx.fn('lib.$Extensions_pickMapBest_ent_Structure.pickMapBest')
    pat = [a.value for a in cx.code.types[pmb.type.value].definition.args]
    cnt, pnull = fb.reg(pat[1]), fb.reg(pat[2])
    fb.op('ToDyn', dst=cnt, src=b.const('i32', RAID_KEEP))
    fb.op('Null', dst=pnull)
    choices = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Call3', dst=choices, fun=pmb.findex.value, arg0=sc, arg1=cnt, arg2=pnull)
    fb.op('JNull', reg=choices, offset='end')
    ki = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=ki, src=zi)
    b.loop_head('akl')
    fb.op('JSGte', a=ki, b=b.field(choices, 'length'), offset='end')
    kc = b.call('hl.types.ArrayObj.getDyn', choices, ki)
    fb.op('Incr', dst=ki)
    fb.op('JNull', reg=kc, offset='akl')
    b.call('haxe.ds.ObjectMap.set', keep, kc, fb.dyn(t))
    fb.op('JAlways', offset='akl')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=fb.reg(cx.t('void')))
    return fb.build()


def build_annex_wait(cx, helpers, new_ids):
    """Annex waiting for armies: every call of AIMilitary.onActionEnd (vanilla's, ours, the ai-log trace) -> wrapper.
    k "Annexation" ending NotEnoughArmies / ArmyNotStrongEnough / NoAvailableArmy -> map `anea` faction -> now (and
    `anea0` -> start of that failure streak, kept until a Success); Success -> both cleared. Read by raid's gauge
    hold. Then the original. In a trap. Returns the number of redirected call sites."""
    orig = cx.fn('logic.ai.AIMilitary.onActionEnd')
    args = [a.value for a in cx.code.types[orig.type.value].definition.args]
    fb = FB(cx, args, cx.t('void'), fun_type=orig.type.value)
    b = B(fb)
    void = fb.reg(cx.t('void'))
    names = [c.name.resolve(cx.code) for c in cx.code.types[args[2]].definition.constructs]
    g = fb.try_()
    fb.op('JNull', reg=1, offset='orig')
    fb.op('JNull', reg=2, offset='orig')
    fb.op('JNotEq', a=b.call('String.__compare', 1, fb.dyn(fb.string('Annexation'))), b=b.const('i32', 0),
          offset='orig')
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='orig')
    ri = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ri, value=2)
    am, a0 = _global_map(fb, b, cx, 'anea'), _global_map(fb, b, cx, 'anea0')
    fb.op('JEq', a=ri, b=b.const('i32', names.index('Success')), offset='clr')
    for nm in ('NotEnoughArmies', 'ArmyNotStrongEnough', 'NoAvailableArmy'):
        fb.op('JEq', a=ri, b=b.const('i32', names.index(nm)), offset='rec')
    fb.op('JAlways', offset='orig')
    fb.label('rec')
    now = b.field(_state(fb, b, cx), 'time')
    b.call('haxe.ds.ObjectMap.set', am, fb.dyn(fac), fb.dyn(now))
    fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', a0, fb.dyn(fac)), offset='orig')
    b.call('haxe.ds.ObjectMap.set', a0, fb.dyn(fac), fb.dyn(now))
    fb.op('JAlways', offset='orig')
    fb.label('clr')
    b.call('haxe.ds.ObjectMap.remove', am, fb.dyn(fac))
    b.call('haxe.ds.ObjectMap.remove', a0, fb.dyn(fac))
    fb.label('orig')
    fb.end_try(g)
    fb.op('Call4', dst=void, fun=orig.findex.value, arg0=0, arg1=1, arg2=2, arg3=3)
    fb.op('Ret', ret=void)
    w = fb.build()
    new_ids.add(w)
    n = 0
    for f in cx.code.functions:
        if f.findex.value == w:
            continue
        for op in f.ops:
            if op.op.startswith('Call') and op.df.get('fun') is not None and op.df['fun'].value == orig.findex.value:
                op.df['fun'].value = w
                n += 1
    if n == 0:
        raise ValueError('annex-wait: no onActionEnd call sites')
    return n
