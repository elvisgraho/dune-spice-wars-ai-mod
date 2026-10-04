"""Fog of war (AI-POLICY §3a): our rules judge hostile armies by what the faction sees, plus a memory of sightings.

Vanilla's own AI never checks visibility, and our rules read every army's true position and power. A player sees
only `Entity.isVisibleForFaction(f)` (team vision cells; a cloaked enemy needs detection) and remembers what was
seen. Model:
- `aimod_intel(mil, dt)` (tick chain, first, every INTEL_T s per AI faction): every army hostile to fac (owned by a
  faction at war with it, or a neutral raider) that fac sees now writes its record in map `seen` (army -> ObjectMap
  faction -> dynobj {t time, x, y position, p power (aimod_pw), b 1 while fighting / occupying / contesting, l distance
  to fac's land (aimod_land)}); keyed by army so `sweep` drops a dead army's records. A sighting older than SEEN_T
  is ignored by the local queries.
- `_ghost` (army loops of the shared queries): a visible army is judged live as before; an unseen one by its record:
  assumed up to min(GHOST_SPD x age, GHOST_R_MAX) closer to the query point than where it was seen (a player
  expects a stack near where it was, not marching straight at him: the uncapped walk read every army seen in 3 min
  within ~800 as present, rallies x4 and no en-route strike passed in a whole match), at its remembered power (x BUSY_W while it was last seen busy, less than
  BUSY_SEEN_T ago, where the caller discounts busy armies); no record or a stale one: not counted.
- Owned siege targets (rules/siege.py getEnemyCombatStats): the owner's armies by what we know, unknown ones at
  the owner's main base (a player assumes the unseen army is home), never fewer than vanilla's zone weights say.
Logs nothing itself; `aw` rows carry `vis` / `kn`."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def _hostile_to(fb, b, cx, state, fac, x, yes, no):
    """Jump to `yes` if army x is hostile to fac (at-war owner, or a neutral raider: any raid), else `no`."""
    xo = b.call('ent.Entity.get_owner', x)
    own = _uid('hown')
    fb.op('JNotNull', reg=xo, offset=own)
    fb.op('JNull', reg=b.field(x, 'raid'), offset=no)
    fb.op('JAlways', offset=yes)
    fb.label(own)
    fb.op('JEq', a=xo, b=fac, offset=no)
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, xo), offset=no)
    fb.op('JAlways', offset=yes)


def _rec_get(fb, b, cx, rec, key):
    r = fb.reg(cx.t('f64'))
    fb.op('DynGet', dst=r, obj=rec, field=cx.s(key))
    return r


def _rec_set(fb, b, cx, rec, key, reg):
    fb.op('DynSet', obj=rec, field=cx.s(key), src=reg)


def build_intel(cx, helpers, pw, land):
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    state = _state(fb, b, cx)
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(state, 'time'))
    _tick(fb, b, cx, t, INTEL_T, 'end')
    top = _global_map(fb, b, cx, 'seen')
    armies = b.field(state, 'armies')
    fb.op('JNull', reg=armies, offset='end')
    i = fb.reg(cx.t('i32'))
    rec = fb.reg(cx.t('dyn'))
    pv, lv, bz = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    one, zero = b.const('f64', 1), b.const('f64', 0)
    x = _army_loop(fb, b, armies, b.field(armies, 'length'), i, 'loop', 'end')
    _hostile_to(fb, b, cx, state, fac, x, 'hos', 'loop')
    fb.label('hos')
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', x, fac), offset='loop')
    inner = fb.reg(cx.t('haxe.ds.ObjectMap'))
    cur = b.call('haxe.ds.ObjectMap.get', top, fb.dyn(x))
    fb.op('JNull', reg=cur, offset='newin')
    fb.op('Mov', dst=inner, src=b.cast(cur, 'haxe.ds.ObjectMap'))
    fb.op('JAlways', offset='hasin')
    fb.label('newin')
    fb.op('New', dst=inner)
    fb.op('Call1', dst=void, fun=cx.fn('haxe.ds.$ObjectMap.__constructor__').findex.value, arg0=inner)
    b.call('haxe.ds.ObjectMap.set', top, fb.dyn(x), fb.dyn(inner))
    fb.label('hasin')
    fb.op('Mov', dst=rec, src=b.call('haxe.ds.ObjectMap.get', inner, fb.dyn(fac)))
    fb.op('JNotNull', reg=rec, offset='have')
    nd = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=nd)
    fb.op('Mov', dst=rec, src=nd)
    b.call('haxe.ds.ObjectMap.set', inner, fb.dyn(fac), rec)
    fb.label('have')
    _rec_set(fb, b, cx, rec, 't', t)
    _rec_set(fb, b, cx, rec, 'x', b.field(x, 'posx'))
    _rec_set(fb, b, cx, rec, 'y', b.field(x, 'posy'))
    fb.op('Call1', dst=pv, fun=pw, arg0=x)
    _rec_set(fb, b, cx, rec, 'p', pv)
    xe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=xe, src=x)
    fb.op('Call2', dst=lv, fun=land, arg0=fac, arg1=xe)
    _rec_set(fb, b, cx, rec, 'l', lv)
    fb.op('Mov', dst=bz, src=one)
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', x), offset='bz')
    fb.op('JNotNull', reg=b.field(x, 'occupiedStructure'), offset='bz')
    fb.op('JNotNull', reg=b.field(x, 'contestingStructure'), offset='bz')
    fb.op('Mov', dst=bz, src=zero)
    fb.label('bz')
    _rec_set(fb, b, cx, rec, 'b', bz)
    fb.op('JAlways', offset='loop')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


def _seen_map(fb, b, cx, fac):
    """Handle on fac's sightings (map `seen` army -> faction -> record) for _rec_of."""
    return (_global_map(fb, b, cx, 'seen'), fac)


def _rec_of(fb, b, cx, mp, x, miss):
    """fac's record of army x (dyn register; mp = _seen_map handle); jump to `miss` when there is none."""
    top, fac = mp
    inner = b.call('haxe.ds.ObjectMap.get', top, fb.dyn(x))
    fb.op('JNull', reg=inner, offset=miss)
    rec = b.call('haxe.ds.ObjectMap.get', b.cast(inner, 'haxe.ds.ObjectMap'), fb.dyn(fac))
    fb.op('JNull', reg=rec, offset=miss)
    return rec


def _ghost(fb, b, cx, fac, mp, now, x, live, skip, px=None, py=None, r=None, dist=None, busy=True):
    """Army loop gate. Falls to `live` when army x is visible to fac. Otherwise reads fac's record of x (mp:
    _seen_map) and jumps to `skip` when there is none or it is older than SEEN_T (SEEN_HOME_T when it was seen within
    SEEN_HOME_R of our land: a stack that went into stealth at our village stays remembered), or when its worst-case position
    (remembered point moved min(GHOST_SPD x age, GHOST_R_MAX) toward the query point (px, py)) is farther than r. With dist (f64 reg):
    the record's land distance minus GHOST_SPD x age goes there instead (aimod_home), and the r test is the caller's.
    Falls through (ghost path) with the remembered power, x BUSY_W when busy=True and x was last seen busy less than
    BUSY_SEEN_T ago (busy='skip': such an army jumps to `skip`). Returns the power register (only valid on the ghost path)."""
    gp = fb.reg(cx.t('f64'))
    fb.op('JTrue', cond=b.call('ent.Entity.isVisibleForFaction', x, fac), offset=live)
    rec = _rec_of(fb, b, cx, mp, x, skip)
    age = fb.reg(cx.t('f64'))
    fb.op('Sub', dst=age, a=now, b=_rec_get(fb, b, cx, rec, 't'))
    # seen on / next to our land (it vanished there: stealth at our village we conceded): SEEN_HOME_T, else SEEN_T
    hm = _uid('ghm')
    fb.op('JSGt', a=_rec_get(fb, b, cx, rec, 'l'), b=b.const('f64', SEEN_HOME_R), offset=hm)
    fb.op('JSGt', a=age, b=b.const('f64', SEEN_HOME_T), offset=skip)
    fb.op('JAlways', offset=hm + 'ok')
    fb.label(hm)
    fb.op('JSGt', a=age, b=b.const('f64', SEEN_T), offset=skip)
    fb.label(hm + 'ok')
    mv = fb.reg(cx.t('f64'))
    fb.op('Mul', dst=mv, a=age, b=_ratio(fb, b, GHOST_SPD))
    gmx = b.const('f64', GHOST_R_MAX)
    cap = _uid('gcap')
    fb.op('JSLte', a=mv, b=gmx, offset=cap)
    fb.op('Mov', dst=mv, src=gmx)
    fb.label(cap)
    if dist is not None:
        fb.op('Sub', dst=dist, a=_rec_get(fb, b, cx, rec, 'l'), b=mv)
    else:
        dx, dy = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
        fb.op('Sub', dst=dx, a=_rec_get(fb, b, cx, rec, 'x'), b=px)
        fb.op('Sub', dst=dy, a=_rec_get(fb, b, cx, rec, 'y'), b=py)
        fb.op('Mul', dst=dx, a=dx, b=dx)
        fb.op('Mul', dst=dy, a=dy, b=dy)
        fb.op('Add', dst=dx, a=dx, b=dy)
        fb.op('Add', dst=mv, a=mv, b=r)
        fb.op('Mul', dst=mv, a=mv, b=mv)
        fb.op('JSGt', a=dx, b=mv, offset=skip)
    fb.op('Mov', dst=gp, src=_rec_get(fb, b, cx, rec, 'p'))
    if busy:
        nb = _uid('gnb')
        fb.op('JSLt', a=_rec_get(fb, b, cx, rec, 'b'), b=b.const('f64', 1), offset=nb)
        fb.op('JSGt', a=age, b=b.const('f64', BUSY_SEEN_T), offset=nb)
        if busy == 'skip':
            fb.op('JAlways', offset=skip)
        else:
            fb.op('Mul', dst=gp, a=gp, b=_ratio(fb, b, BUSY_W))
        fb.label(nb)
    return gp


def _known_rec(fb, b, cx, fac, mp, now, x, live, skip):
    """Falls to `live` when x is visible to fac; jumps to `skip` without a fresh record (SEEN_T); else falls through
    with the record (dyn register) and its age."""
    fb.op('JTrue', cond=b.call('ent.Entity.isVisibleForFaction', x, fac), offset=live)
    rec = _rec_of(fb, b, cx, mp, x, skip)
    age = fb.reg(cx.t('f64'))
    fb.op('Sub', dst=age, a=now, b=_rec_get(fb, b, cx, rec, 't'))
    fb.op('JSGt', a=age, b=b.const('f64', SEEN_T), offset=skip)
    return rec, age
