"""Free Annex gate (AI-POLICY "Expansion and target value"): a village whose Annex costs us nothing is taken only by
a faction that can hold it, each AI deciding for itself (two that both can will meet there: that fight is wanted).

The failure: Landsraad Water Subsidies sets Polar Sink's Annex cost to 0 for 20 days. Normally its cost (+150% per
owned village, trait CT_NorthPole) prices it out of our value per cost; at 0 the value per cost step is skipped,
so it scores like the cheapest candidate for every faction at once, whatever its position or strength, and every
AI in reach would always pick it.

Query aimod_fclaim(fac, s) -> true when fac may annex the free neutral village s: not under another faction's
siege (it can't be annexed then), at most CLAIM_HOPS zones from fac's territory (Zone.getDistanceToPlayerTerritory:
1 = bordering), the battle forecast at s (aimod_forecast, attack, all our armies, over CLAIM_FC_T = the walk of
CLAIM_R: a rival stack standing there or heading there counts, with its militia) >= ENTER. Other factions' positions are not consulted.
True when s has an owner (taking it is a normal war decision) or no siege object (cost unknown). The caller gates
only while some other candidate has a cost (everything free: no lure). In a trap (true on error)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

CLAIM_FC_T = CLAIM_R // CONTEST_SPD  # s: the forecast window (the walk of CLAIM_R)


def build_fclaim(cx, forecast):
    """aimod_fclaim(fac, s) -> bool (see module doc)."""
    fb = FB(cx, [cx.t('ent.Faction'), cx.t('ent.Structure')], cx.t('bool'))
    b = B(fb)
    ok = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=ok, value=True)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=1)
    fb.op('JNotNull', reg=b.call('ent.Entity.get_owner', se), offset='end')  # owned: not a free-land claim
    sg = b.field(1, 'siege')
    fb.op('JNull', reg=sg, offset='end')
    # already besieged by another faction (or raiders): no Annex possible there now
    bf = b.field(sg, 'besiegingFaction')
    fb.op('JNull', reg=bf, offset='nosg')
    fb.op('JNotEq', a=bf, b=0, offset='no')
    fb.label('nosg')
    z = b.call('ent.Entity.get_zone', se)
    fb.op('JNull', reg=z, offset='end')
    gdt = cx.fn('ent.Zone.getDistanceToPlayerTerritory')
    anull = fb.reg(cx.code.types[gdt.type.value].definition.args[2].value)
    fb.op('Null', dst=anull)
    h0 = fb.reg(cx.t('i32'))
    fb.op('Call3', dst=h0, fun=gdt.findex.value, arg0=z, arg1=0, arg2=anull)
    fb.op('JSGt', a=h0, b=b.const('i32', CLAIM_HOPS), offset='no')
    # able: the battle forecast there (the shared measure, ARCHITECTURE-PLAN step 1; was aimod_own within CLAIM_R vs
    # aimod_react within LOCAL) clears ENTER
    fc = fb.reg(cx.t('f64'))
    t_true = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_true, value=True)
    no_arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=no_arr)
    fb.op('CallN', dst=fc, fun=forecast, args=[0, se, b.const('f64', CLAIM_FC_T), t_true, no_arr])
    # ... with armies of ours that get there (review: an unopposed village read FC_NONE and passed with none near)
    mo, mt = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    _fc_sides(fb, b, cx, 0, mo, mt, 'no')
    fb.op('JSLte', a=mo, b=b.const('f64', 0), offset='no')
    fb.op('JSGte', a=fc, b=_ratio(fb, b, ENTER), offset='end')
    fb.label('no')
    fb.op('Bool', dst=ok, value=False)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=ok)
    return fb.build()
