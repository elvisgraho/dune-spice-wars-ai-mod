"""Task board (docs/ARCHITECTURE-PLAN.md step 2 stage 3b): one place ranks a faction's open tasks before a launch.

aimod_board(fac, k, tgt, fc, T, armies, ask) -> bool. Every launching rule calls it with the candidate it evaluated
(k kind: contest / guard / chase / raid / siege / defense / rally; tgt the valued entity and the task's anchor; fc
its battle forecast; T its time to act in s, <= 0: the armies' nearest walk to tgt at CONTEST_SPD; armies the ones it
would send, null for a post only):
- post: V = aimod_sval(fac, tgt) for a structure, aimod_aval(tgt) for an army; A = sum aimod_aval(armies);
  p = clamp((fc - ABORT) / (ENTER - ABORT), 0, 1); gain = V x p - A x (1 - p) x LOSS_K; sc = gain / (T + T0).
  Per faction: list `bls` (targets) and maps `bsc` (score), `bst` (time), `bsk` (kind); an entry counts BOARD_T s.
  Log `tpost` (f, k, tgt, V, A, fc%, T, sc) per target per TPOST_T s;
- ask (a launch): another live entry Y (not tgt, sc_Y > 0, sc_Y >= RANK_HYST x sc_X) needing some of the same armies
  (one of them within BOARD_R of Y's target) beats it: log `tyield` (f, k, tgt, sc, by, byk, bysc, live). Y's
  counter `byc` +1 (map `byt`: since when; a count older than YIELD_WIN starts over); a Y with YIELD_MAX yields
  counted and no launch of its own since is stale (skipped; log `tstale` once) until YIELD_WIN after its first counted
  yield. A launch that passes clears its own target's counter (it acted). V counts at most BOARD_VCAP; one entry per
  target: a live entry of another kind scoring higher isn't overwritten.
Never yields: a task on the base-kill leader (rules/bkill.py; also no main-base Defense and no rally commit reach
the board: heal.py dgate skips them). Live per kind (BOARD_LIVE: the kinds whose yield is real, the answer false); every other kind: shadow, always true
(launch as today), the rows show what would change (`live`). Fails open: true on any error."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

BOARD_LIVE = ()     # kinds whose launches really yield (step 2: ('raid', 'siege')); others: shadow, log only
BOARD_T = 12        # s an entry stays live without a re-post
BOARD_R = 450       # an army within this of a task's target is one it could use (HUNT_R)
RANK_HYST = 1.3     # a launch yields only to a task this much better
T0 = 30             # s added to every task's time (no blow-up next door)
LOSS_K = 1.0        # weight of the armies' value lost in a losing fight
YIELD_MAX = 3       # a winner that made this many launches yield without acting itself is stale ...
YIELD_WIN = 120     # s: ... within this window from its first counted yield (then the count starts over)
TPOST_T = 30        # s: `tpost` log throttle per target
BOARD_VCAP = 20000  # V counts at most this (a main base's VAL_MB 1M outranked every task near it; review)


def build_board(cx, helpers):
    """aimod_board(fac, k, tgt, fc, T, armies, ask) -> bool (see module doc)."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('String'), cx.t('ent.Entity'), cx.t('f64'), cx.t('f64'),
                 cx.t('hl.types.ArrayObj'), cx.t('bool')], cx.t('bool'))
    b = B(fb)
    ok = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=ok, value=True)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=2, offset='end')
    zero = b.const('f64', 0)
    now = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=now, src=b.field(_state(fb, b, cx), 'time'))
    v, a, p, g, q, t, sc = (fb.reg(cx.t('f64')) for _ in range(7))
    # V: the stake
    fb.op('Mov', dst=v, src=zero)
    scl = fb.reg(cx.t('ent.$Structure'))
    fb.op('GetGlobal', dst=scl, **{'global': cx.global_of('ent.$Structure')})
    fb.op('JFalse', cond=b.call('hl.BaseType.check', scl, fb.dyn(2)), offset='v_a')
    ts = fb.reg(cx.t('ent.Structure'))
    fb.op('SafeCast', dst=ts, src=fb.dyn(2))
    fb.op('Call2', dst=v, fun=helpers['sval'], arg0=0, arg1=ts)
    fb.op('JAlways', offset='v_d')
    fb.label('v_a')
    acl = fb.reg(cx.t('ent.$Army'))
    fb.op('GetGlobal', dst=acl, **{'global': cx.global_of('ent.$Army')})
    fb.op('JFalse', cond=b.call('hl.BaseType.check', acl, fb.dyn(2)), offset='v_d')
    ta = fb.reg(cx.t('ent.Army'))
    fb.op('SafeCast', dst=ta, src=fb.dyn(2))
    fb.op('Call1', dst=v, fun=helpers['aval'], arg0=ta)
    fb.label('v_d')
    # A: the armies it would send; T: given, else their nearest walk
    fb.op('Mov', dst=a, src=zero)
    fb.op('Mov', dst=t, src=4)
    dmin = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=dmin, src=b.const('f64', 1 << 30))
    j = fb.reg(cx.t('i32'))
    fb.op('JNull', reg=5, offset='a_d')
    x = _army_loop(fb, b, 5, b.field(5, 'length'), j, 'a', 'a_d', transported=True)
    fb.op('Call1', dst=q, fun=helpers['aval'], arg0=x)
    fb.op('Add', dst=a, a=a, b=q)
    fb.op('Mov', dst=q, src=b.call('ent.Entity.getDistTo', x, 2))
    fb.op('JSGte', a=q, b=dmin, offset='a')
    fb.op('Mov', dst=dmin, src=q)
    fb.op('JAlways', offset='a')
    fb.label('a_d')
    fb.op('JSGt', a=t, b=zero, offset='t_ok')
    fb.op('Mov', dst=t, src=zero)
    fb.op('JSGte', a=dmin, b=b.const('f64', 1 << 29), offset='t_ok')
    fb.op('SDiv', dst=t, a=dmin, b=b.const('f64', CONTEST_SPD))
    fb.label('t_ok')
    fb.op('JSLte', a=v, b=b.const('f64', BOARD_VCAP), offset='v_cap')
    fb.op('Mov', dst=v, src=b.const('f64', BOARD_VCAP))
    fb.label('v_cap')
    # p, gain, score
    fb.op('Sub', dst=p, a=3, b=_ratio(fb, b, ABORT))
    fb.op('SDiv', dst=p, a=p, b=_ratio(fb, b, ENTER - ABORT))
    fb.op('JSGte', a=p, b=zero, offset='p_lo')
    fb.op('Mov', dst=p, src=zero)
    fb.label('p_lo')
    one = b.const('f64', 1)
    fb.op('JSLte', a=p, b=one, offset='p_hi')
    fb.op('Mov', dst=p, src=one)
    fb.label('p_hi')
    fb.op('Mul', dst=g, a=v, b=p)
    fb.op('Sub', dst=q, a=one, b=p)
    fb.op('Mul', dst=q, a=q, b=a)
    fb.op('Mul', dst=q, a=q, b=_ratio(fb, b, LOSS_K))
    fb.op('Sub', dst=g, a=g, b=q)
    fb.op('Add', dst=q, a=t, b=b.const('f64', T0))
    fb.op('SDiv', dst=sc, a=g, b=q)
    # post
    msc, mst, msk, myc = (_fac_map(fb, b, cx, n, 0) for n in ('bsc', 'bst', 'bsk', 'byc'))
    top = _global_map(fb, b, cx, 'bls')
    lst = fb.reg(cx.t('hl.types.ArrayObj'))
    lv = b.call('haxe.ds.ObjectMap.get', top, fb.dyn(0))
    fb.op('JNull', reg=lv, offset='l_new')
    fb.op('SafeCast', dst=lst, src=lv)
    fb.op('JAlways', offset='l_have')
    fb.label('l_new')
    fb.op('Mov', dst=lst, src=_new_array(fb, b, cx))
    b.call('haxe.ds.ObjectMap.set', top, fb.dyn(0), fb.dyn(lst))
    fb.label('l_have')
    fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', lst, fb.dyn(2)), offset='l_in')
    b.call('hl.types.ArrayObj.push', lst, fb.dyn(2))
    fb.label('l_in')
    # one entry per target: a live entry of another kind scoring higher stays (review: a contest and a defense on one
    # village overwrote each other, last post won)
    ov = b.call('haxe.ds.ObjectMap.get', msc, fb.dyn(2))
    fb.op('JNull', reg=ov, offset='p_wr')
    otv = b.call('haxe.ds.ObjectMap.get', mst, fb.dyn(2))
    fb.op('JNull', reg=otv, offset='p_wr')
    oq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=oq, src=otv)
    fb.op('Sub', dst=oq, a=now, b=oq)
    fb.op('JSGt', a=oq, b=b.const('f64', BOARD_T), offset='p_wr')
    okv = b.call('haxe.ds.ObjectMap.get', msk, fb.dyn(2))
    fb.op('JNull', reg=okv, offset='p_wr')
    fb.op('JEq', a=b.call('String.__compare', 1, okv), b=b.const('i32', 0), offset='p_wr')  # same kind: refreshed
    fb.op('SafeCast', dst=oq, src=ov)
    fb.op('JSLte', a=oq, b=sc, offset='p_wr')
    fb.op('JAlways', offset='p_keep')
    fb.label('p_wr')
    b.call('haxe.ds.ObjectMap.set', msc, fb.dyn(2), fb.dyn(sc))
    b.call('haxe.ds.ObjectMap.set', mst, fb.dyn(2), fb.dyn(now))
    b.call('haxe.ds.ObjectMap.set', msk, fb.dyn(2), fb.dyn(1))
    fb.label('p_keep')
    _throttle(fb, b, cx, 'tpost', 2, TPOST_T, 'posted')
    _log_ev(fb, b, cx, helpers, 'tpost', [('f', fb.get(0, 'kind')), ('k', 1), ('tgt', 2), ('V', v), ('A', a),
                                          ('fc%', 3), ('T', t), ('sc', sc)])
    fb.label('posted')
    fb.op('JFalse', cond=6, offset='end')
    fb.op('JNull', reg=5, offset='end')
    # the base-kill campaign never yields (user: finish what was started): a task on the leader or its structure
    bld = _bk_target(fb, b, cx, 0, 'bk_no')
    fb.op('JEq', a=b.call('ent.Entity.get_owner', 2), b=bld, offset='end')
    fb.label('bk_no')
    # ask: the best live entry that beats this one by RANK_HYST and could use one of its armies
    need = fb.reg(cx.t('f64'))
    fb.op('Mul', dst=need, a=sc, b=_ratio(fb, b, RANK_HYST))
    fb.op('JSGte', a=need, b=zero, offset='n_ok')  # a losing launch (gain < 0): any positive task beats it
    fb.op('Mov', dst=need, src=zero)
    fb.label('n_ok')
    best, ye = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=best)
    bsc, ysc, yq = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=bsc, src=need)
    k, yn = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k, src=b.field(lst, 'length'))
    b.loop_head('y')
    fb.op('JSLte', a=k, b=b.const('i32', 0), offset='y_d')
    fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
    fb.op('Mov', dst=ye, src=b.cast(b.call('hl.types.ArrayObj.getDyn', lst, k), 'ent.Entity'))
    fb.op('JNull', reg=ye, offset='y')
    fb.op('JEq', a=ye, b=2, offset='y')
    tv = b.call('haxe.ds.ObjectMap.get', mst, fb.dyn(ye))
    fb.op('JNull', reg=tv, offset='y_rm')
    fb.op('SafeCast', dst=yq, src=tv)
    fb.op('Sub', dst=yq, a=now, b=yq)
    fb.op('JSGt', a=yq, b=b.const('f64', BOARD_T), offset='y_rm')
    sv = b.call('haxe.ds.ObjectMap.get', msc, fb.dyn(ye))
    fb.op('JNull', reg=sv, offset='y')
    fb.op('SafeCast', dst=ysc, src=sv)
    fb.op('JSLte', a=ysc, b=bsc, offset='y')
    fb.op('JSLte', a=ysc, b=zero, offset='y')
    # stale winner: YIELD_MAX yields without a launch of its own
    cv = b.call('haxe.ds.ObjectMap.get', myc, fb.dyn(ye))
    fb.op('JNull', reg=cv, offset='y_fresh')
    fb.op('SafeCast', dst=yn, src=cv)
    fb.op('JSLt', a=yn, b=b.const('i32', YIELD_MAX), offset='y_fresh')
    # stale since longer than YIELD_WIN: it may compete again (review: stale stayed stale for the match)
    stv = b.call('haxe.ds.ObjectMap.get', _fac_map(fb, b, cx, 'byt', 0), fb.dyn(ye))
    fb.op('JNull', reg=stv, offset='y_old')
    fb.op('SafeCast', dst=yq, src=stv)
    fb.op('Sub', dst=yq, a=now, b=yq)
    fb.op('JSLte', a=yq, b=b.const('f64', YIELD_WIN), offset='y_st')
    fb.label('y_old')
    b.call('haxe.ds.ObjectMap.set', myc, fb.dyn(ye), fb.dyn(b.const('i32', 0)))
    fb.op('JAlways', offset='y_fresh')
    fb.label('y_st')
    fb.op('JNotEq', a=yn, b=b.const('i32', YIELD_MAX), offset='y')  # logged once
    fb.op('Incr', dst=yn)
    b.call('haxe.ds.ObjectMap.set', myc, fb.dyn(ye), fb.dyn(yn))
    _log_ev(fb, b, cx, helpers, 'tstale', [('f', fb.get(0, 'kind')), ('tgt', ye), ('sc', ysc)])
    fb.op('JAlways', offset='y')
    fb.label('y_fresh')
    # needs one of these armies: within BOARD_R of Y's target
    jj = fb.reg(cx.t('i32'))
    lp = _uid('yo')
    xa = _army_loop(fb, b, 5, b.field(5, 'length'), jj, lp, 'y', transported=True)  # none near: next entry
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', xa, ye), b=b.const('f64', BOARD_R), offset=lp)
    fb.op('Mov', dst=bsc, src=ysc)
    fb.op('Mov', dst=best, src=ye)
    fb.op('JAlways', offset='y')
    fb.label('y_rm')
    b.call('hl.types.ArrayObj.splice', lst, k, b.const('i32', 1))  # expired: off the list (k counts down)
    fb.op('JAlways', offset='y')
    fb.label('y_d')
    fb.op('JNotNull', reg=best, offset='yield')
    b.call('haxe.ds.ObjectMap.set', myc, fb.dyn(2), fb.dyn(b.const('i32', 0)))  # it acts: not stale
    fb.op('JAlways', offset='end')
    fb.label('yield')
    myt = _fac_map(fb, b, cx, 'byt', 0)
    cv2 = b.call('haxe.ds.ObjectMap.get', myc, fb.dyn(best))
    fb.op('Mov', dst=yn, src=b.const('i32', 0))
    fb.op('JNull', reg=cv2, offset='yc0')
    fb.op('SafeCast', dst=yn, src=cv2)
    fb.op('JSLte', a=yn, b=b.const('i32', 0), offset='yc0')
    ytv = b.call('haxe.ds.ObjectMap.get', myt, fb.dyn(best))
    fb.op('JNull', reg=ytv, offset='yc0')
    fb.op('SafeCast', dst=yq, src=ytv)
    fb.op('Sub', dst=yq, a=now, b=yq)
    fb.op('JSLte', a=yq, b=b.const('f64', YIELD_WIN), offset='yc1')
    fb.label('yc0')  # a fresh count
    fb.op('Mov', dst=yn, src=b.const('i32', 0))
    b.call('haxe.ds.ObjectMap.set', myt, fb.dyn(best), fb.dyn(now))
    fb.label('yc1')
    fb.op('Incr', dst=yn)
    b.call('haxe.ds.ObjectMap.set', myc, fb.dyn(best), fb.dyn(yn))
    bk_ = b.call('haxe.ds.ObjectMap.get', msk, fb.dyn(best))
    live = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=live, value=False)
    for lk in BOARD_LIVE:
        fb.op('JNotEq', a=b.call('String.__compare', 1, fb.dyn(fb.string(lk))), b=b.const('i32', 0),
              offset=f'lv_{lk}')
        fb.op('Bool', dst=live, value=True)
        fb.label(f'lv_{lk}')
    _log_ev(fb, b, cx, helpers, 'tyield', [('f', fb.get(0, 'kind')), ('k', 1), ('tgt', 2), ('sc', sc), ('by', best),
                                           ('byk', bk_), ('bysc', bsc), ('live', live)])
    fb.op('JFalse', cond=live, offset='end')
    fb.op('Bool', dst=ok, value=False)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=ok)
    return fb.build()
