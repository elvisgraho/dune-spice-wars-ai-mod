"""Battle forecast (docs/ARCHITECTURE-PLAN.md step 1): one measure of "who wins at this place within the time that
matters", for every decision, instead of each rule's own radius / discount / ratio.

aimod_forecast(fac, place, T, attack, units) -> ratio ours / theirs (theirs 0: FC_NONE). Maps `fco` / `fct` faction ->
our / their side of the last call (logs).
- theirs: hostile armies that can be at `place` within T (aimod_threat, fog-aware, radius T x CONTEST_SPD clamped to
  [LOCAL, FC_MAX_R]: standing within it or moving towards `place`); for a structure owned by another faction at least
  aimod_owner_pw (the owner's armies as we know them, unseen ones at its main base: raids on at-war villages were sized
  on the seen part only); + at-war turret cover at `place` (aimod_cover) + the militia of a structure not ours
  (aimod_militia);
- ours: `units` (an order's armies, in full: committed, on their way) or, null, all our non-harvester armies whose
  travel time (aimod_eta: walking or via our airfields / main base) is <= T (an army on a Military mission only if
  already within RALLY_HERE of `place`), + our
  turret cover (attack: x OWN_COVER_ATK: a battery doesn't follow the fight), + the militia of our own structure,
  x terrain at `place`; at the base-kill leader's structure their side minus our partners' armies within LOCAL x PARTNER_W (floor
  PARTNER_FLOOR x their side).
Fails safe: ratio FC_NONE (no decision changes on an error); the maps are cleared to 0 / 0 at entry, so a reader of a
failed call's sides (_fc_sides / _fc_theirs) sees 0, never the previous call's place (review 2026-10-24)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

FC_MAX_R = 900     # their armies counted within at most this (a long T must not pull in the whole map)
FC_NONE = 1 << 20  # ratio when their side is 0
PARTNER_W = 0.7    # a base-kill partner's army at the leader's structure takes this much off the leader's side (it
                   # fights its own plan, not ours) ...
PARTNER_FLOOR = 0.3  # ... the leader's side never below this share of itself


def build_forecast(cx, helpers, pw, threat, cover, terrain, eta, militia, mission, owner_pw, contest=False):
    """contest=True (aimod_forecast_c, the hunt's contest sizing): a place we contest against its besieger: its own
    militia and its owner's armies are not on their side (they fight the besieger too)."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Entity'), cx.t('f64'), cx.t('bool'), cx.t('hl.types.ArrayObj')],
            cx.t('f64'))
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=res, src=b.const('f64', FC_NONE))
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    zero = b.const('f64', 0)
    for mn in ('fco', 'fct'):
        b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, mn), fb.dyn(0), fb.dyn(zero))
    fb.op('JNull', reg=1, offset='end')
    ours, theirs, q, r, d = (fb.reg(cx.t('f64')) for _ in range(5))
    no_ent = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=no_ent)
    no_arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=no_arr)
    t_true, t_false = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_true, value=True)
    fb.op('Bool', dst=t_false, value=False)
    st = fb.reg(cx.t('ent.Structure'))  # the place as a structure (null for an army / point)
    fb.op('Null', dst=st)
    scl = fb.reg(cx.t('ent.$Structure'))
    fb.op('GetGlobal', dst=scl, **{'global': cx.global_of('ent.$Structure')})
    fb.op('JFalse', cond=b.call('hl.BaseType.check', scl, fb.dyn(1)), offset='nost')
    fb.op('SafeCast', dst=st, src=fb.dyn(1))
    fb.label('nost')
    po = fb.reg(cx.t('ent.Faction'))
    fb.op('Mov', dst=po, src=b.call('ent.Entity.get_owner', 1))
    # their side: armies that can be there within T
    fb.op('Mul', dst=r, a=2, b=b.const('f64', CONTEST_SPD))
    fb.op('JSGte', a=r, b=b.const('f64', LOCAL), offset='rlo')
    fb.op('Mov', dst=r, src=b.const('f64', LOCAL))
    fb.label('rlo')
    fb.op('JSLte', a=r, b=b.const('f64', FC_MAX_R), offset='rhi')
    fb.op('Mov', dst=r, src=b.const('f64', FC_MAX_R))
    fb.label('rhi')
    fb.op('Call3', dst=theirs, fun=threat, arg0=0, arg1=1, arg2=r)
    # base-kill plan: at the leader's structure, with another plan member at war with it, what isn't there yet (beyond
    # LOCAL) counts x BK_SPLIT (common._bk_split; user: the coalition never chipped at a parked leader)
    fb.op('JNull', reg=po, offset='nosplit')
    fb.op('JNull', reg=st, offset='nosplit')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', st), offset='nosplit')  # its whole army comes home
    _bk_split(fb, b, cx, 0, po, 'split', 'nosplit')
    fb.label('split')
    fb.op('Call3', dst=q, fun=threat, arg0=0, arg1=1, arg2=b.const('f64', LOCAL))
    fb.op('Sub', dst=d, a=theirs, b=q)
    fb.op('JSLte', a=d, b=zero, offset='nosplit')
    fb.op('Mul', dst=d, a=d, b=_ratio(fb, b, BK_SPLIT))
    fb.op('Add', dst=theirs, a=q, b=d)
    fb.label('nosplit')
    # ... at least the owner's armies as we know them (another faction's structure; not for a contest)
    if contest:
        fb.op('JAlways', offset='noown')
    fb.op('JNull', reg=st, offset='noown')
    fb.op('JNull', reg=po, offset='noown')
    fb.op('JEq', a=po, b=0, offset='noown')
    fb.op('Call2', dst=q, fun=owner_pw, arg0=0, arg1=st)
    fb.op('JSLte', a=q, b=theirs, offset='noown')
    fb.op('Mov', dst=theirs, src=q)
    fb.label('noown')
    fb.op('CallN', dst=q, fun=cover, args=[0, 1, no_ent, t_false, no_arr])
    fb.op('Add', dst=theirs, a=theirs, b=q)
    # our turrets (attack: x OWN_COVER_ATK)
    fb.op('CallN', dst=ours, fun=cover, args=[0, 1, no_ent, t_true, no_arr])
    fb.op('JFalse', cond=3, offset='cdef')
    fb.op('Mul', dst=ours, a=ours, b=_ratio(fb, b, OWN_COVER_ATK))
    fb.label('cdef')
    # the place's militia: ours on our structure, theirs elsewhere
    fb.op('JNull', reg=st, offset='nomil')
    fb.op('Call1', dst=q, fun=militia, arg0=st)
    fb.op('JEq', a=po, b=0, offset='milo')
    if contest:  # a contested village's militia fights its besieger, not us
        fb.op('JAlways', offset='nomil')
    fb.op('Add', dst=theirs, a=theirs, b=q)
    fb.op('JAlways', offset='nomil')
    fb.label('milo')
    fb.op('Add', dst=ours, a=ours, b=q)
    fb.label('nomil')
    # our armies that arrive in time: the given units, else all ours
    j = fb.reg(cx.t('i32'))
    ok = fb.reg(cx.t('bool'))
    ae = fb.reg(cx.t('ent.Entity'))
    arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Mov', dst=arr, src=4)
    fb.op('JNotNull', reg=arr, offset='given')
    fb.op('Mov', dst=arr, src=b.cast(fb.get(0, 'armies', 'array'), 'hl.types.ArrayObj'))
    fb.op('JNull', reg=arr, offset='adone')
    a = _army_loop(fb, b, arr, b.field(arr, 'length'), j, 'a', 'adone')
    fb.op('JNotNull', reg=b.field(a, 'harvestComponent'), offset='a')
    fb.op('Mov', dst=ae, src=a)
    fb.op('Call2', dst=ok, fun=mission, arg0=0, arg1=a)
    fb.op('JFalse', cond=ok, offset='tm')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ae, 1), b=b.const('f64', RALLY_HERE), offset='a')
    fb.op('JAlways', offset='tm')
    fb.label('given')
    # an order's own armies count in full wherever they are: they are committed and on their way (the window limits
    # who else can join; Fremen's 8-army Liberate of Ashmon, 447 out, read 0 vs 0 at RAID_FC_T 75 s and was aborted
    # `weak` 2 s after launch, match 2026-10-23 21:3x)
    a2 = _army_loop(fb, b, arr, b.field(arr, 'length'), j, 'g', 'adone')
    fb.op('Mov', dst=ae, src=a2)
    fb.op('JAlways', offset='add')
    fb.label('tm')
    fb.op('Call3', dst=d, fun=eta, arg0=0, arg1=ae, arg2=1)
    fb.op('JSGt', a=d, b=2, offset='next')
    fb.label('add')
    fb.op('Call1', dst=q, fun=pw, arg0=b.cast(fb.dyn(ae), 'ent.Army'))
    fb.op('Add', dst=ours, a=ours, b=q)
    fb.label('next')
    fb.op('JNotNull', reg=4, offset='g')
    fb.op('JAlways', offset='a')
    fb.label('adone')
    # base-kill plan, a joint attack: at the leader's structure (common._bk_split holds), the armies of our partners
    # (plan members at war with the leader, not with us) already within LOCAL fight the leader too: x PARTNER_W taken
    # off their side, never below PARTNER_FLOOR of it (one place for every reader: the ratio and every sizing through
    # _fc_theirs; user: the coalition should chip at the leader together, not one by one)
    jh = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=jh, src=zero)
    fb.op('JNull', reg=po, offset='nojoint')
    _bk_split(fb, b, cx, 0, po, 'joint', 'nojoint')
    fb.label('joint')
    jst = _state(fb, b, cx)
    jarr = b.field(jst, 'armies')
    fb.op('JNull', reg=jarr, offset='nojoint')
    jk = fb.reg(cx.t('i32'))
    ja = _army_loop(fb, b, jarr, b.field(jarr, 'length'), jk, 'jl', 'nojoint')
    jo = b.call('ent.Entity.get_owner', ja)
    fb.op('JNull', reg=jo, offset='jl')
    fb.op('JEq', a=jo, b=0, offset='jl')
    fb.op('JEq', a=jo, b=po, offset='jl')
    fb.op('JNotNull', reg=b.field(ja, 'harvestComponent'), offset='jl')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', ja, 1), b=b.const('f64', LOCAL), offset='jl')
    fb.op('JTrue', cond=b.call('logic.state.State.areAtWar', jst, 0, jo), offset='jl')  # not a partner of ours
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', jst, jo, po), offset='jl')
    jv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'bkv'), fb.dyn(jo))
    fb.op('JNull', reg=jv, offset='jl')
    jli = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=jli, src=jv)
    fb.op('JSLt', a=jli, b=b.const('i32', 1), offset='jl')
    fb.op('Call1', dst=q, fun=pw, arg0=ja)
    fb.op('Mul', dst=q, a=q, b=_ratio(fb, b, PARTNER_W))
    fb.op('Add', dst=jh, a=jh, b=q)
    fb.op('JAlways', offset='jl')
    fb.label('nojoint')
    fb.op('JSLte', a=jh, b=zero, offset='jdone')
    jf = fb.reg(cx.t('f64'))
    fb.op('Mul', dst=jf, a=theirs, b=_ratio(fb, b, PARTNER_FLOOR))
    fb.op('Sub', dst=theirs, a=theirs, b=jh)
    fb.op('JSGte', a=theirs, b=jf, offset='jdone')
    fb.op('Mov', dst=theirs, src=jf)
    fb.label('jdone')
    z = b.call('ent.Entity.get_zone', 1)
    fb.op('JNull', reg=z, offset='noterr')
    fb.op('Call2', dst=q, fun=terrain, arg0=0, arg1=z)
    fb.op('Mul', dst=ours, a=ours, b=q)
    fb.label('noterr')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'fco'), fb.dyn(0), fb.dyn(ours))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'fct'), fb.dyn(0), fb.dyn(theirs))
    fb.op('JSLte', a=theirs, b=zero, offset='end')
    fb.op('SDiv', dst=res, a=ours, b=theirs)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    return fb.build()

