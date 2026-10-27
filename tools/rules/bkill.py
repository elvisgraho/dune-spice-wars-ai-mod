"""Base-kill plan, stage 1: the threat picture (docs/BASEKILL-PLAN.md; user: players partner up against whoever
approaches a win condition, crabs in a bucket, no flip-flop). Logs only; no army moves yet.

`aimod_bkill(mil, dt)` (tick chain, every BK_T s per faction):
- Threat table, the same for every AI (public numbers): per alive faction X its win ETA in game days (DAY s each):
  hegemony (H_WIN - h) / rate, rate = hegemony gained per day over RATE_WIN (map `bkh0` / `bkt0` / `bkr`; the cached
  net production until a window closes, at least that: spice taxes are steps); CHOAM (0.5 - ratio) x CHOAM_DPD while
  X holds >= CHOAM_MIN and nobody else >= CHOAM_RIVAL (several big holders: no threat); Governor: X holds the charter
  and its countdown runs: remaining s / DAY. ETA = min, capped ETA_MAX, at least 0, + 1 day (several factions past
  the win line, possible in a testbed match that never ends, read as a tie, not one leader); map `bke` X -> ETA. Late gate: anyone at
  >= LATE_HEG hegemony, a governor, or a CHOAM threat. Log `bthreat` (f, h, r, c%, gov days or -1, eta) per X per
  THREAT_LOG s (gov: days left on its governor countdown, -1 when it holds none).
- Leader (shared, keyed by the State: maps `bkl` leader, `bkcand` / `bkct` candidate since): with none, the best ETA
  qualifies when late, <= ETA_Q and <= LEAD_RATIO x the next best; a sitting leader stays while late and <= ETA_Q x KEEP_K,
  unless another's ETA <= SWITCH_RATIO x its own (switching needs a clear new threat). A changed candidate must hold
  LEAD_CONFIRM s before it becomes the leader (log `bkill` act leader).
- Level of this faction (map `bkv`: 0 none, 1 check, 2 assault): no leader 0; we are the leader 0 (why lead); our own
  ETA <= SELF_RACE x the leader's: 0 (why race: we race instead of joining); else 1, 2 when the leader's ETA <=
  ASSAULT_ETA; both edges hold by LVL_HYST once reached (a race stays a race up to SELF_RACE x LVL_HYST, an assault up
  to ASSAULT_ETA x LVL_HYST). Log `bkill` act level (f, lvl, tgt, why, eta_l, eta_s) on a change.
Stage 2 (check, level >= 1): war on the leader (declareWar every BK_WAR_COOL s while not at war; log `bkill` act
war; a truce with a new leader breaks that way); a Normal Non-aggression Pact offer to each coalition member (or human)
we are at war with every TRUCE_RETRY s (both sides of an AI pair send; the peace gate accepts a member's offer: `peace`
act accept why coalition; log `bkill` act truce); readers of the level (common._bk_target): strat_levers lists the leader's villages in vanilla's siege scans,
the target scores drop other at-war owners' villages (partner up), the press picks only the leader's villages (also
when it is stronger), the peace gate refuses the leader's offers and leaves coalition members' to vanilla.
Fails safe: in a trap."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules import bkstate as bks
from rules.worm import _do_on, _move_to

BK_T = 10          # s between passes per faction
DAY = 30           # s per game day
H_WIN = 30000      # const Game_Victory_HegemonyScore
LATE_HEG = 20000   # const 9 (near victory): nobody is a threat before someone reaches it (or a governor / CHOAM threat)
RATE_WIN = 600     # s: hegemony rate window (20 days: spans spice taxes)
CHOAM_MIN = 0.38   # user: one faction above ~38% CHOAM ...
CHOAM_RIVAL = 0.30  # ... while nobody else is close
CHOAM_DPD = 200    # days per share ratio point left to 0.5 (~1% per 2 days; Solari banked not read yet)
ETA_MAX = 999      # days
ETA_Q = 80         # days: a leader's ETA at most this
LEAD_RATIO = 0.7   # a new leader's ETA <= this x the next best (crabs: a close race forms no coalition)
SWITCH_RATIO = 0.6  # another faction replaces the sitting leader only at <= this x its ETA
LEAD_CONFIRM = 90  # s a new candidate must hold
SELF_RACE = 1.25   # our own ETA within this x the leader's: we race, we don't join
ASSAULT_ETA = 30   # days: the leader this close -> level 2 (stage 3 adds kill feasibility)
KEEP_K = 1.25      # a sitting leader is kept up to ETA_Q x this (crowned at <= ETA_Q; review: the rate steps every
                   # RATE_WIN, an ETA around ETA_Q dropped and re-crowned the leader, war / truce each time)
LVL_HYST = 1.3     # the level edges hold: a race stays a race up to SELF_RACE x this, an assault up to ASSAULT_ETA x this
THREAT_LOG = 60    # s
BK_WAR_COOL = 60   # s between war declarations on the leader per faction (stage 2)
TRUCE_RETRY = 120  # s between Non-aggression Pact offers to one coalition member


def build_bkill_tick(cx, helpers):
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    st = _state(fb, b, cx)
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(st, 'time'))
    _tick(fb, b, cx, t, BK_T, 'end')
    facs = b.cast(fb.get(st, 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=facs, offset='end')
    zero = b.const('f64', 0)
    i = fb.reg(cx.t('i32'))
    x = fb.reg(cx.t('ent.Faction'))
    # pass 1: CHOAM ratios (the two largest) and the governor
    market = b.field(st, 'choamMarket')
    cm1, cm2, c = (fb.reg(cx.t('f64')) for _ in range(3))
    fb.op('Mov', dst=cm1, src=zero)
    fb.op('Mov', dst=cm2, src=zero)
    bkc = _global_map(fb, b, cx, 'bkc')
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('p1')
    fb.op('JSGte', a=i, b=b.field(facs, 'length'), offset='p1d')
    fb.op('Mov', dst=x, src=b.cast(b.call('hl.types.ArrayObj.getDyn', facs, i), 'ent.Faction'))
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=x, offset='p1')
    fb.op('Mov', dst=c, src=zero)
    fb.op('JNull', reg=market, offset='p1s')
    fb.op('Mov', dst=c, src=b.call('logic.state.ChoamMarket.getFactionSharesRatio', market, x))
    fb.label('p1s')
    b.call('haxe.ds.ObjectMap.set', bkc, fb.dyn(x), fb.dyn(c))
    fb.op('JSLte', a=c, b=cm2, offset='p1')
    fb.op('JSLte', a=c, b=cm1, offset='p1b')
    fb.op('Mov', dst=cm2, src=cm1)
    fb.op('Mov', dst=cm1, src=c)
    fb.op('JAlways', offset='p1')
    fb.label('p1b')
    fb.op('Mov', dst=cm2, src=c)
    fb.op('JAlways', offset='p1')
    fb.label('p1d')
    gov = fb.reg(cx.t('ent.Faction'))
    grem = fb.reg(cx.t('f64'))
    fb.op('Null', dst=gov)
    fb.op('Mov', dst=grem, src=b.const('f64', -1))
    res = b.field(st, 'resolutions')
    fb.op('JNull', reg=res, offset='nogov')
    gm = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gm, **{'global': cx.global_of('$Game')})
    ginst = b.field(gm, 'inst')
    fb.op('JNull', reg=ginst, offset='nogov')
    fb.op('Mov', dst=gov, src=b.call('logic.state.ResolutionManager.getCharterOwner', res,
                                     b.call('Game.getGovernorKind', ginst)))
    gr = b.call('logic.state.ResolutionManager.getGovernorRemainingTime', res)
    fb.op('JNull', reg=gr, offset='nogov')
    fb.op('SafeCast', dst=grem, src=fb.dyn(gr))
    fb.label('nogov')
    # pass 2: ETA per faction, the best two
    late = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=late, value=False)
    fb.op('JNull', reg=gov, offset='ng')
    fb.op('Bool', dst=late, value=True)
    fb.label('ng')
    h, r, prod, eta, e2, q, d = (fb.reg(cx.t('f64')) for _ in range(7))
    best, best2 = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    lead1 = fb.reg(cx.t('ent.Faction'))
    fb.op('Null', dst=lead1)
    fb.op('Mov', dst=best, src=b.const('f64', ETA_MAX))
    fb.op('Mov', dst=best2, src=b.const('f64', ETA_MAX))
    bkh0, bkt0, bkr, bke = (_global_map(fb, b, cx, n) for n in ('bkh0', 'bkt0', 'bkr', 'bke'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('p2')
    fb.op('JSGte', a=i, b=b.field(facs, 'length'), offset='p2d')
    fb.op('Mov', dst=x, src=b.cast(b.call('hl.types.ArrayObj.getDyn', facs, i), 'ent.Faction'))
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=x, offset='p2')
    fb.op('JNull', reg=b.call('ent.Faction.get_mainBase', x), offset='p2')  # eliminated / no base
    fb.op('Mov', dst=h, src=b.call('ent.Faction.getResource', x, b.const('i32', 7)))
    fb.op('Mov', dst=prod, src=b.call('ent.Faction.getCachedResNetProd', x, b.const('i32', 7)))
    # hegemony rate per day over RATE_WIN (map bkr), at least the cached production
    fb.op('Mov', dst=r, src=prod)
    _age(fb, b, cx, bkt0, x, t, 'rw_new', dst=d)
    fb.op('JSLt', a=d, b=b.const('f64', RATE_WIN), offset='rw_old')
    fb.op('SafeCast', dst=q, src=b.call('haxe.ds.ObjectMap.get', bkh0, fb.dyn(x)))
    fb.op('Sub', dst=q, a=h, b=q)
    fb.op('SDiv', dst=d, a=d, b=b.const('f64', DAY))
    fb.op('SDiv', dst=q, a=q, b=d)
    b.call('haxe.ds.ObjectMap.set', bkr, fb.dyn(x), fb.dyn(q))
    fb.label('rw_new')
    b.call('haxe.ds.ObjectMap.set', bkh0, fb.dyn(x), fb.dyn(h))
    b.call('haxe.ds.ObjectMap.set', bkt0, fb.dyn(x), fb.dyn(t))
    fb.label('rw_old')
    rv = b.call('haxe.ds.ObjectMap.get', bkr, fb.dyn(x))
    fb.op('JNull', reg=rv, offset='rw_d')
    fb.op('SafeCast', dst=q, src=rv)
    fb.op('JSLte', a=q, b=r, offset='rw_d')
    fb.op('Mov', dst=r, src=q)
    fb.label('rw_d')
    # hegemony ETA
    fb.op('JSLt', a=h, b=b.const('f64', LATE_HEG), offset='nlate')
    fb.op('Bool', dst=late, value=True)
    fb.label('nlate')
    fb.op('Mov', dst=eta, src=b.const('f64', ETA_MAX))
    fb.op('JSLte', a=r, b=b.const('f64', 1), offset='he_d')
    fb.op('Sub', dst=q, a=b.const('f64', H_WIN), b=h)
    fb.op('SDiv', dst=q, a=q, b=r)
    fb.op('JSGte', a=q, b=eta, offset='he_d')
    fb.op('Mov', dst=eta, src=q)
    fb.label('he_d')
    # CHOAM ETA: the clear top holder only
    fb.op('SafeCast', dst=c, src=b.call('haxe.ds.ObjectMap.get', bkc, fb.dyn(x)))
    fb.op('JSLt', a=c, b=_ratio(fb, b, CHOAM_MIN), offset='ce_d')
    fb.op('JSLt', a=c, b=cm1, offset='ce_d')
    fb.op('JSGte', a=cm2, b=_ratio(fb, b, CHOAM_RIVAL), offset='ce_d')
    fb.op('Bool', dst=late, value=True)
    fb.op('Sub', dst=q, a=_ratio(fb, b, 0.5), b=c)
    fb.op('Mul', dst=q, a=q, b=b.const('f64', CHOAM_DPD))
    fb.op('JSGte', a=q, b=eta, offset='ce_d')
    fb.op('Mov', dst=eta, src=q)
    fb.label('ce_d')
    # Governor ETA
    fb.op('JNotEq', a=x, b=gov, offset='ge_d')
    fb.op('JSLt', a=grem, b=zero, offset='ge_d')
    fb.op('SDiv', dst=q, a=grem, b=b.const('f64', DAY))
    fb.op('JSGte', a=q, b=eta, offset='ge_d')
    fb.op('Mov', dst=eta, src=q)
    fb.label('ge_d')
    # past the win line (a testbed match doesn't end at 30k: everyone reached 40k) the ETA would go negative and the
    # LEAD_RATIO test would crown one of several tied factions: clamp at 0, + 1 day, so a tie stays a tie (no leader)
    fb.op('JSGte', a=eta, b=zero, offset='eta_pos')
    fb.op('Mov', dst=eta, src=zero)
    fb.label('eta_pos')
    fb.op('Add', dst=eta, a=eta, b=b.const('f64', 1))
    b.call('haxe.ds.ObjectMap.set', bke, fb.dyn(x), fb.dyn(eta))
    # best two
    fb.op('JSGte', a=eta, b=best2, offset='bt_d')
    fb.op('JSGte', a=eta, b=best, offset='bt_2')
    fb.op('Mov', dst=best2, src=best)
    fb.op('Mov', dst=best, src=eta)
    fb.op('Mov', dst=lead1, src=x)
    fb.op('JAlways', offset='bt_d')
    fb.label('bt_2')
    fb.op('Mov', dst=best2, src=eta)
    fb.label('bt_d')
    # threat row
    _throttle(fb, b, cx, 'bthreatl', x, THREAT_LOG, 'p2')
    gd = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=gd, src=b.const('f64', -1))
    fb.op('JNotEq', a=x, b=gov, offset='tl_g')
    fb.op('SDiv', dst=gd, a=grem, b=b.const('f64', DAY))
    fb.label('tl_g')
    _log_ev(fb, b, cx, helpers, 'bthreat', [('f', fb.get(x, 'kind')), ('h', h), ('r', r), ('c%', c), ('gov', gd),
                                            ('eta', eta)])
    fb.op('JAlways', offset='p2')
    fb.label('p2d')
    # leader, shared (keyed by the State)
    sk = fb.dyn(st)
    bkl, bkcand, bkct = (_global_map(fb, b, cx, n) for n in ('bkl', 'bkcand', 'bkct'))
    cur, cand = fb.reg(cx.t('ent.Faction')), fb.reg(cx.t('ent.Faction'))
    fb.op('Null', dst=cand)
    fb.op('Mov', dst=cur, src=b.cast(b.call('haxe.ds.ObjectMap.get', bkl, sk), 'ent.Faction'))
    fb.op('JFalse', cond=late, offset='cand_d')
    fb.op('JNull', reg=cur, offset='c_new')
    ecv = b.call('haxe.ds.ObjectMap.get', bke, fb.dyn(cur))
    fb.op('JNull', reg=ecv, offset='c_new')  # the leader is gone (eliminated)
    ecur = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=ecur, src=ecv)
    fb.op('JNull', reg=b.call('ent.Faction.get_mainBase', cur), offset='c_new')
    # a sitting leader: kept while <= ETA_Q, unless another faction is clearly ahead
    fb.op('JSGt', a=ecur, b=b.const('f64', int(ETA_Q * KEEP_K)), offset='cand_d')
    fb.op('Mov', dst=cand, src=cur)
    fb.op('JEq', a=lead1, b=cur, offset='cand_d')
    fb.op('Mul', dst=q, a=ecur, b=_ratio(fb, b, SWITCH_RATIO))
    fb.op('JSGt', a=best, b=q, offset='cand_d')
    fb.op('Mov', dst=cand, src=lead1)
    fb.op('JAlways', offset='cand_d')
    fb.label('c_new')
    fb.op('JNull', reg=lead1, offset='cand_d')
    fb.op('JSGt', a=best, b=b.const('f64', ETA_Q), offset='cand_d')
    fb.op('Mul', dst=q, a=best2, b=_ratio(fb, b, LEAD_RATIO))
    fb.op('JSGt', a=best, b=q, offset='cand_d')
    fb.op('Mov', dst=cand, src=lead1)
    fb.label('cand_d')
    # confirmation: a changed candidate holds LEAD_CONFIRM s before it replaces the leader
    pcv = b.call('haxe.ds.ObjectMap.get', bkcand, sk)
    pc = fb.reg(cx.t('ent.Faction'))
    fb.op('Mov', dst=pc, src=b.cast(pcv, 'ent.Faction'))
    fb.op('JEq', a=pc, b=cand, offset='cf_same')
    fb.op('JNull', reg=pcv, offset='cf_set')
    fb.label('cf_set')
    fb.op('JNull', reg=cand, offset='cf_clr')
    b.call('haxe.ds.ObjectMap.set', bkcand, sk, fb.dyn(cand))
    fb.op('JAlways', offset='cf_t')
    fb.label('cf_clr')
    b.call('haxe.ds.ObjectMap.remove', bkcand, sk)
    fb.label('cf_t')
    b.call('haxe.ds.ObjectMap.set', bkct, sk, fb.dyn(t))
    fb.op('JAlways', offset='lv')
    fb.label('cf_same')
    fb.op('JEq', a=cand, b=cur, offset='lv')
    ctv = b.call('haxe.ds.ObjectMap.get', bkct, sk)
    fb.op('JNull', reg=ctv, offset='lv')
    fb.op('SafeCast', dst=q, src=ctv)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSLt', a=q, b=b.const('f64', LEAD_CONFIRM), offset='lv')
    fb.op('JNull', reg=cand, offset='ld_clr')
    b.call('haxe.ds.ObjectMap.set', bkl, sk, fb.dyn(cand))
    fb.op('JAlways', offset='ld_log')
    fb.label('ld_clr')
    b.call('haxe.ds.ObjectMap.remove', bkl, sk)
    fb.label('ld_log')
    fb.op('Mov', dst=cur, src=cand)
    _log_ev(fb, b, cx, helpers, 'bkill', [('f', fb.get(fac, 'kind')), ('act', 'leader'), ('tgt', fb.get(cand, 'kind')),
                                          ('eta_l', best), ('eta_2', best2)])
    # this faction's level
    fb.label('lv')
    lvl = fb.reg(cx.t('i32'))
    why = fb.reg(cx.t('String'))
    el, es = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=lvl, src=b.const('i32', 0))
    fb.op('Mov', dst=why, src=fb.string('none'))
    fb.op('Mov', dst=el, src=b.const('f64', ETA_MAX))
    fb.op('Mov', dst=es, src=b.const('f64', ETA_MAX))
    fb.op('JNull', reg=cur, offset='lv_set')
    elv = b.call('haxe.ds.ObjectMap.get', bke, fb.dyn(cur))
    fb.op('JNull', reg=elv, offset='lv_set')
    fb.op('SafeCast', dst=el, src=elv)
    esv = b.call('haxe.ds.ObjectMap.get', bke, fb.dyn(fac))
    fb.op('JNull', reg=esv, offset='lv_es')
    fb.op('SafeCast', dst=es, src=esv)
    fb.label('lv_es')
    fb.op('Mov', dst=why, src=fb.string('lead'))
    fb.op('JEq', a=cur, b=fac, offset='lv_set')
    # thresholds with hysteresis on our current level (map `bkw` = the last why, `bkv` = the last level)
    rq, aq = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=rq, src=_ratio(fb, b, SELF_RACE))
    fb.op('Mov', dst=aq, src=b.const('f64', ASSAULT_ETA))
    pwv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'bkw'), fb.dyn(fac))
    fb.op('JNull', reg=pwv, offset='hy_d')
    fb.op('JNotEq', a=b.call('String.__compare', b.cast(pwv, 'String'), fb.dyn(fb.string('race'))),
          b=b.const('i32', 0), offset='hy_a')
    fb.op('Mov', dst=rq, src=_ratio(fb, b, SELF_RACE * LVL_HYST))
    fb.label('hy_a')
    fb.op('JNotEq', a=b.call('String.__compare', b.cast(pwv, 'String'), fb.dyn(fb.string('assault'))),
          b=b.const('i32', 0), offset='hy_d')
    fb.op('Mov', dst=aq, src=b.const('f64', int(ASSAULT_ETA * LVL_HYST)))
    fb.label('hy_d')
    fb.op('Mov', dst=why, src=fb.string('race'))
    fb.op('Mul', dst=q, a=el, b=rq)
    fb.op('JSLte', a=es, b=q, offset='lv_set')
    fb.op('Mov', dst=why, src=fb.string('check'))
    fb.op('Mov', dst=lvl, src=b.const('i32', 1))
    fb.op('JSGt', a=el, b=aq, offset='lv_set')
    fb.op('Mov', dst=why, src=fb.string('assault'))
    fb.op('Mov', dst=lvl, src=b.const('i32', 2))
    fb.label('lv_set')
    bkv, bkw = _global_map(fb, b, cx, 'bkv'), _global_map(fb, b, cx, 'bkw')
    ov = b.call('haxe.ds.ObjectMap.get', bkw, fb.dyn(fac))
    fb.op('JNull', reg=ov, offset='lv_chg')
    fb.op('JEq', a=b.call('String.__compare', b.cast(ov, 'String'), fb.dyn(why)), b=b.const('i32', 0), offset='war')
    fb.label('lv_chg')
    b.call('haxe.ds.ObjectMap.set', bkw, fb.dyn(fac), fb.dyn(why))
    b.call('haxe.ds.ObjectMap.set', bkv, fb.dyn(fac), fb.dyn(lvl))
    _log_ev(fb, b, cx, helpers, 'bkill', [('f', fb.get(fac, 'kind')), ('act', 'level'), ('lvl', fb.dyn(lvl)),
                                          ('why', fb.dyn(why)), ('tgt', fb.get(cur, 'kind')), ('eta_l', el),
                                          ('eta_s', es)])
    # stage 2: at war with the leader (check / assault): declare it (vanilla's declareWar: Influence cost, refused
    # within the status grace period), at most every BK_WAR_COOL s; log `bkill` act war r = EReason index
    fb.label('war')
    fb.op('JSLt', a=lvl, b=b.const('i32', 1), offset='end')
    fb.op('JNull', reg=cur, offset='end')
    fb.op('JEq', a=cur, b=fac, offset='end')
    fb.op('JTrue', cond=b.call('logic.state.State.areAtWar', st, fac, cur), offset='truce')
    _throttle(fb, b, cx, 'bkwar', fac, BK_WAR_COOL, 'truce')
    dm = b.field(st, 'diplomacy')
    fb.op('JNull', reg=dm, offset='truce')
    rr = b.call('logic.state.DiplomacyManager.declareWar', dm, fac, cur)
    ri = fb.reg(cx.t('i32'))
    fb.op('Int', dst=ri, ptr=cx.code.add_i32(-1).value)
    fb.op('JNull', reg=rr, offset='wlog')
    fb.op('EnumIndex', dst=ri, value=rr)
    fb.label('wlog')
    _log_ev(fb, b, cx, helpers, 'bkill', [('f', fb.get(fac, 'kind')), ('act', 'war'), ('tgt', fb.get(cur, 'kind')),
                                          ('r', fb.dyn(ri))])
    # coalition truce (user: partner up means truce, broken when the plan turns on them: the war step above declares
    # war on a new leader): to every other alive faction at war with us that isn't the leader and is in the plan too
    # (level >= 1) or human, a Normal Non-aggression Pact offer (ImproveRelations) every TRUCE_RETRY s per pair; between
    # two AIs both send (the receiver's peace gate accepts it; was: only the kind sorting first). Vanilla checks the
    # grace period / cost (checkStartTrade, sendTrade; a refused send is reset). Log `bkill` act truce (to, r)
    fb.label('truce')
    from rules.dmz import _pair_map
    tm = b.field(fac, 'tradeManager')
    fb.op('JNull', reg=tm, offset='end')
    trm = _pair_map(fb, b, cx, 'bktr', fac)
    sendt = cx.fn('logic.TradeManager.sendTrade')
    style_t = cx.code.types[sendt.type.value].definition.args[2].value
    snames = [c_.name.resolve(cx.code) for c_ in cx.code.types[style_t].definition.constructs]
    rnames = [c_.name.resolve(cx.code) for c_ in
              cx.code.types[cx.code.types[sendt.type.value].definition.ret.value].definition.constructs]
    succ = rnames.index('Success')
    style = fb.reg(style_t)
    fb.op('MakeEnum', dst=style, construct=snames.index('Normal'), args=[])
    ti = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=ti, src=b.const('i32', 0))
    b.loop_head('tr')
    fb.op('JSGte', a=ti, b=b.field(facs, 'length'), offset='end')
    fb.op('Mov', dst=x, src=b.cast(b.call('hl.types.ArrayObj.getDyn', facs, ti), 'ent.Faction'))
    fb.op('Incr', dst=ti)
    fb.op('JNull', reg=x, offset='tr')
    fb.op('JEq', a=x, b=fac, offset='tr')
    fb.op('JEq', a=x, b=cur, offset='tr')
    fb.op('JNull', reg=b.call('ent.Faction.get_mainBase', x), offset='tr')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', st, fac, x), offset='tr')
    fb.op('JFalse', cond=b.call('ent.Faction.get_isAIPlayer', x), offset='tr_go')  # a human decides itself
    xl = b.call('haxe.ds.ObjectMap.get', bkv, fb.dyn(x))
    fb.op('JNull', reg=xl, offset='tr')
    xli = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=xli, src=xl)
    fb.op('JSLt', a=xli, b=b.const('i32', 1), offset='tr')
    # both sides of a pair send (each every TRUCE_RETRY s): the one with the Influence for it gets it through (user:
    # the coalition stayed at war with itself; the side the kind order picked had none, MissingResources 14 of 18)
    fb.label('tr_go')
    _age(fb, b, cx, trm, x, t, 'tr_send', dst=q)
    fb.op('JSLt', a=q, b=b.const('f64', TRUCE_RETRY), offset='tr')
    fb.label('tr_send')
    b.call('haxe.ds.ObjectMap.set', trm, fb.dyn(x), fb.dyn(t))
    xo = fb.reg(cx.t('ent.Object'))
    fb.op('Mov', dst=xo, src=x)
    tri = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=tri, value=b.call('logic.TradeManager.checkStartTrade', tm, xo))
    fb.op('JNotEq', a=tri, b=b.const('i32', succ), offset='tr_log')
    b.call('logic.TradeManager.startTrade', tm, xo)
    trade = b.field(tm, 'activeTrade')
    fb.op('JNull', reg=trade, offset='tr')
    b.call('logic.TradeManager.addTreaty', tm, fb.string('ImproveRelations'), fac)
    fb.op('EnumIndex', dst=tri, value=b.call('logic.TradeManager.sendTrade', tm, trade, style))
    fb.op('JEq', a=tri, b=b.const('i32', succ), offset='tr_log')
    b.call('logic.TradeManager.resetTrade', tm, trade)
    fb.label('tr_log')
    _log_ev(fb, b, cx, helpers, 'bkill', [('f', fb.get(fac, 'kind')), ('act', 'truce'), ('to', fb.get(x, 'kind')),
                                          ('r', fb.dyn(tri))])
    fb.op('JAlways', offset='tr')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


# ---- stage 3, the campaign: rules/bkcamp/ (docs/BASEKILL-PLAN.md 7b / 7c) -------------------------------------------
