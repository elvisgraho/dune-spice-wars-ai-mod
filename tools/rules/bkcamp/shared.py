"""Base-kill campaign: what more than one section uses: the emitter context (`_take` / `_give`), the refill gate,
and the shared constants (docs/AI-POLICY.md, base-kill campaign)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules import bkstate as bks
from rules.worm import _do_on, _move_to

BC_T = 5             # s between campaign passes per faction (under CLAIM_TTL: the muster claims hold)
BC_MUSTER_R = 450    # coalition armies this close to the leader's base are mustered (900 held nearly the whole
                     # coalition on a mid-size map: M = P in every row, match 2026-10-24 14:20)
BC_GO_WIN = 60       # s: a member launches within this of the go time (once per go)
BC_STAGE_AT = 150    # an army this close to its staging structure has mustered
BC_MOVE_T = 20       # s: an army is sent to the staging structure at most this often
BC_CLAIM_KEEP = 20   # s: an army the campaign claimed this recently stays in it wherever it walks
BC_DR_AT = 300       # direct raze: an army this close to the base gets ArmySiege on it (the action walks it in; a Move
                     # to the base stopped short of 100 and nobody sieged, match 43), else it walks there ...
BC_DR_T = 2          # ... re-sent this often while idle there (an idle army: at once)
BC_DR_BUSY_T = 20    # ... and this often while it has an action running (its ArmySiege walk: not restarted)
BC_DEP_SUP = 0.5     # muster / direct raze before its wave left: below this supply share or BC_DEP_LIFE life an army
BC_DEP_LIFE = 0.6    # isn't taken (vanilla resupplies it first)
BC_AT_RING = 120      # an army this close to the strike point is ready to strike
BC_FOOT_NEAR = 350   # our staging structure this close to the base is the strike point (a foothold: our land)
BC_FF_GO_T = 180     # ... and the siege, once out (they hold BC_FF_K x H there), stays out this many s
BC_PRIO = 4          # the assault's order priority (vanilla's Raze)


def _take(c, names):
    """The values of `names` (space-separated) in the emitter context `c` (build_bk_campaign's sections), as a tuple."""
    return tuple(getattr(c, n) for n in names.split())


def _give(c, **kv):
    """Hand names to the later sections (attributes of the emitter context `c`)."""
    c.__dict__.update(kv)


def _refill_gate(fb, b, cx, a, refill, ok, q=None):
    """Jump to `refill` when army `a` is below BC_DEP_LIFE life or BC_DEP_SUP supply share (it refills first: vanilla's
    resupply takes it); label `ok` is placed after the test (an army without supply passes its supply part). `q`: the
    share register; None allocates a new one where the inline form did (the emitted code stays byte-identical)."""
    fb.op('JSLt', a=b.call('ent.Entity.get_lifeRatio', a), b=_ratio(fb, b, BC_DEP_LIFE), offset=refill)
    fb.op('JSLte', a=b.call('ent.Army.get_maxSupply', a), b=b.const('f64', 0), offset=ok)
    if q is None:
        q = fb.reg(cx.t('f64'))
    fb.op('SDiv', dst=q, a=b.call('ent.Army.get_supply', a), b=b.call('ent.Army.get_maxSupply', a))
    fb.op('JSLt', a=q, b=_ratio(fb, b, BC_DEP_SUP), offset=refill)
    fb.label(ok)


__all__ = [n for n in dir() if not n.startswith('__')]  # the underscore helpers too (like rules.common)
