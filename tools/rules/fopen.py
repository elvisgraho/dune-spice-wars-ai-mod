"""Fremen opening scout hold (AI-POLICY "Fremen opening").

Why: at match start vanilla annexes the first surveyed village at once, while the ornithopter is still revealing the
map; a Fremen whose main base borders deep desert wants its first villages on that desert's ring (Zone.updateOwner:
the desert becomes theirs once every neighbour village is), and a commit to a village off the ring is permanent.

- `aimod_fopen(fac) -> Bool` (read by the siege launch gate, rules/siege.py build_spacing, Annex only): true = hold
  the Annex (refused with Dismiss, `space` why scout) while all of these hold: fac is Fremen, owns no village yet,
  game time < FOPEN_MAX, an active main base of fac is in a zone bordering deep desert, fewer than FOPEN_N neutral
  villages surveyed by fac (Structure.isReconnedFaction) and none of those in a zone bordering deep desert.
  Logs `fopen` (f, n surveyed, act hold) once per FOPEN_LOG s. Any error: false (vanilla).
"""
from rules.common import *  # noqa: F401,F403

FOPEN_N = 3  # surveyed neutral villages that are enough choice without a ring candidate
FOPEN_MAX = 90  # game s (3 days): never hold longer (a lost ornithopter must not stall the opening)
FOPEN_LOG = 15  # s between `fopen` rows (the gauge re-asks every 0.5 s)


def _touches_dd(fb, b, cx, z, yes):
    """Jump to `yes` when a neighbour of zone z is deep desert; fall through otherwise."""
    no, lo = _uid('fdn'), _uid('fdl')
    nb = b.field(z, 'neighbors')
    fb.op('JNull', reg=nb, offset=no)
    k = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head(lo)
    fb.op('JSGte', a=k, b=b.field(nb, 'length'), offset=no)
    nz = b.cast(b.call('hl.types.ArrayObj.getDyn', nb, k), 'ent.Zone')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=nz, offset=lo)
    fb.op('JTrue', cond=b.call('ent.Zone.isDeepDesert', nz), offset=yes)
    fb.op('JAlways', offset=lo)
    fb.label(no)


def build_fopen(cx, helpers):
    fb = FB(cx, [cx.t('ent.Faction')], cx.t('bool'))
    b = B(fb)
    res = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=res, value=False)
    zi = b.const('i32', 0)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    kd = b.field(0, 'kind')
    fb.op('JNull', reg=kd, offset='end')
    fb.op('JNotEq', a=b.call('String.__compare', kd, fb.dyn(fb.string('Fremen'))), b=zi, offset='end')
    state = _state(fb, b, cx)
    fb.op('JSGte', a=b.field(state, 'time'), b=b.const('f64', FOPEN_MAX), offset='end')
    # main base next to deep desert
    bases = b.field(0, 'mainBases')
    fb.op('JNull', reg=bases, offset='end')
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=zi)
    se = fb.reg(cx.t('ent.Entity'))
    b.loop_head('mb')
    fb.op('JSGte', a=i, b=b.field(bases, 'length'), offset='end')  # none: no hold
    mb = b.cast(b.call('hl.types.ArrayObj.getDyn', bases, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=mb, offset='mb')
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', mb), offset='mb')
    fb.op('Mov', dst=se, src=mb)
    mz = b.call('ent.Entity.get_zone', se)
    fb.op('JNull', reg=mz, offset='mb')
    _touches_dd(fb, b, cx, mz, 'base')
    fb.op('JAlways', offset='mb')
    # villages: none of ours yet; surveyed neutral ones counted, a ring candidate releases at once
    fb.label('base')
    villages = b.field(state, 'villages')
    fb.op('JNull', reg=villages, offset='end')
    n = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=n, src=zi)
    fb.op('Mov', dst=i, src=zi)
    b.loop_head('vl')
    fb.op('JSGte', a=i, b=b.field(villages, 'length'), offset='vd')
    v = b.cast(b.call('hl.types.ArrayObj.getDyn', villages, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=v, offset='vl')
    fb.op('Mov', dst=se, src=v)
    vo = b.call('ent.Entity.get_owner', se)
    fb.op('JEq', a=vo, b=0, offset='end')  # we own a village: the opening is over
    fb.op('JNotNull', reg=vo, offset='vl')
    fb.op('JFalse', cond=b.call('ent.Structure.isReconnedFaction', v, 0), offset='vl')
    fb.op('Incr', dst=n)
    vz = b.call('ent.Entity.get_zone', se)
    fb.op('JNull', reg=vz, offset='vl')
    _touches_dd(fb, b, cx, vz, 'end')  # a ring candidate is known: annex now
    fb.op('JAlways', offset='vl')
    fb.label('vd')
    fb.op('JSGte', a=n, b=b.const('i32', FOPEN_N), offset='end')
    fb.op('Bool', dst=res, value=True)
    _throttle(fb, b, cx, 'fopl', 0, FOPEN_LOG, 'end')
    _log_ev(fb, b, cx, helpers, 'fopen', [('f', kd), ('act', 'hold'), ('n', n)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    return fb.build()
