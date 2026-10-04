"""Square-law militia measure (`aimod_sqr`).

Why: a fight goes by total damage x total health (Lanchester), not by the sum of each squad's damage x health that
aimod_pw / aimod_militia use. Over 743 militia fights of matches 2026-10-03/04 (`sact` rows vs the order's end):
summed-power ratio >= 1.75 with a square-law ratio < 1.5 won 55-59%; square-law >= 1.5 won 97% (< 0.8: 39%,
< 1.2: 61%, < 2: 89%, < 4: 96%). One or two armies against 3-6 militia squads lose that way (Harkonnen's 1-army
raid of Tabmara 18:20: aimod 64k vs 40.5k, lost half its life and was drained out).

aimod_sqr(armies, s) -> f64: (sum of the armies' offensivePotential) x (sum of their health) / the same over s's
militia squads ($HCombatStats.structureCombatStats, health > 0: turrets carry none); 1e9 when s has no militia,
0 for no armies. Used by raid (pick until SQ_MIN, else skip the village for RAID_RETRY)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def build_sqr(cx):
    fb = FB(cx, [cx.t('hl.types.ArrayObj'), cx.t('ent.Structure')], cx.t('f64'))
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=res, src=b.const('f64', 1000000000))
    guard = fb.try_()
    zero = b.const('f64', 0)
    so, sh, ao, ah, q = (fb.reg(cx.t('f64')) for _ in range(5))
    for r_ in (so, sh, ao, ah):
        fb.op('Mov', dst=r_, src=zero)
    fb.op('JNull', reg=1, offset='end')
    sts = b.call('$HCombatStats.structureCombatStats', 1)
    fb.op('JNull', reg=sts, offset='end')
    si = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=si, src=b.const('i32', 0))
    b.loop_head('sq')
    fb.op('JSGte', a=si, b=b.field(sts, 'length'), offset='sqd')
    st = b.call('hl.types.ArrayObj.getDyn', sts, si)
    fb.op('Incr', dst=si)
    fb.op('JNull', reg=st, offset='sq')
    fb.op('SafeCast', dst=q, src=fb.get(st, 'health'))
    fb.op('JSLte', a=q, b=zero, offset='sq')  # turrets: no health
    fb.op('Add', dst=sh, a=sh, b=q)
    fb.op('Add', dst=so, a=so, b=b.call('$HPowerScore.offensivePotential', fb.dyn(st), zero))
    fb.op('JAlways', offset='sq')
    fb.label('sqd')
    fb.op('JSLte', a=sh, b=zero, offset='end')  # no militia
    fb.op('JSLte', a=so, b=zero, offset='end')
    fb.op('Mov', dst=res, src=zero)
    fb.op('JNull', reg=0, offset='end')
    j = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=j, src=b.const('i32', 0))
    b.loop_head('u')
    fb.op('JSGte', a=j, b=b.field(0, 'length'), offset='ud')
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', 0, j), 'ent.Army')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=a, offset='u')
    ust = b.call('$HCombatStats.unitCombatStats', a)
    fb.op('JNull', reg=ust, offset='u')
    fb.op('SafeCast', dst=q, src=fb.get(ust, 'health'))
    fb.op('Add', dst=ah, a=ah, b=q)
    fb.op('Add', dst=ao, a=ao, b=b.call('$HPowerScore.offensivePotential', fb.dyn(ust), zero))
    fb.op('JAlways', offset='u')
    fb.label('ud')
    fb.op('Mul', dst=res, a=ao, b=ah)
    fb.op('Mul', dst=q, a=so, b=sh)
    fb.op('SDiv', dst=res, a=res, b=q)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    return fb.build()
