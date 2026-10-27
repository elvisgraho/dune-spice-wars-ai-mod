"""Peaceful annex gate on vanilla's own use (Atreides' PeacefullyAnnex; AI-POLICY "Peaceful annex").

Why: vanilla `ResourceManager.checkPeacefulAnnexation` spends 50 Influence + the full Annex cost from the first refinery
on, on villages within 3 zones, including those bordering our main base that an idle army takes for free (user: "don't
waste peaceful annex early game or on villages that literally touch base"). Our own fallback (siege.py launch gate
step 4) already waited for PANNEX_MIN_VILLAGES; vanilla's path bypassed it.

`pannex-gate`: the single `AbilityManager.canUseAbilityOn` call in checkPeacefulAnnexation goes through a wrapper
(vanilla first): id `PeacefullyAnnex` with `args.struct` failing `_pannex_ok` (villages, Influence, zone hops from our
main base) -> false, so vanilla tries the next candidate or nothing. Logs `pagate` (throttled per village, 60 s)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers


def build_pannex_gate(cx, helpers, new_ids):
    orig = cx.fn('logic.faction.AbilityManager.canUseAbilityOn')
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    if len(args) != 5 or ft.ret.value != cx.t('bool') or args[1] != cx.t('String'):
        raise ValueError('pannex-gate: canUseAbilityOn(mgr, id, args, ?, ?) -> Bool expected')
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(cx.t('bool'))
    fb.op('CallN', dst=res, fun=orig.findex.value, args=[0, 1, 2, 3, 4])  # vanilla, outside any trap
    guard = fb.try_()
    fb.op('JFalse', cond=res, offset='end')
    fb.op('JNull', reg=1, offset='end')
    fb.op('JNotEq', a=b.call('String.__compare', 1, fb.dyn(fb.string('PeacefullyAnnex'))), b=b.const('i32', 0),
          offset='end')
    fac = b.field(0, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    s = b.cast(fb.get(2, 'struct'), 'ent.Structure')
    fb.op('JNull', reg=s, offset='end')
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=s)
    _pannex_ok(fb, b, cx, fac, se, 'no')
    fb.op('JAlways', offset='end')
    fb.label('no')
    fb.op('Bool', dst=res, value=False)  # too early / next to our base / Influence reserve: armies take it
    _throttle(fb, b, cx, 'pagate', se, 60, 'end')
    _log_ev(fb, b, cx, helpers, 'pagate', [('f', fb.get(fac, 'kind')), ('tgt', se)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    caller = cx.fn('logic.ai.ResourceManager.checkPeacefulAnnexation')
    sites = [op for op in caller.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == orig.findex.value]
    if len(sites) != 1:
        raise ValueError(f'pannex-gate: expected 1 canUseAbilityOn call in checkPeacefulAnnexation, found {len(sites)}')
    for op in sites:
        op.df['fun'].value = w
    return {'pannex-gate': len(sites)}
