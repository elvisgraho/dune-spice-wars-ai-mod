"""No-op AI switch guard (REVERSING "isai-guard").

Why: the console `ai true` (testbed P macro) calls `Faction.set_isAI(true)` on every faction, also on AIs already
running. Vanilla then disposes and rebuilds the faction's path grid and re-runs `AIController.onReady`. A siege order
still in Waiting at that moment never left it: Harkonnen's Annex of Alifras and Fremen's of Yaha (launched 0.3 s
before a P press) logged no phase change and no end, their Annexation gauges stayed paused for the rest of the match
(Harkonnen 1 village with 500 Authority banked).

- `isai-guard`: every reference to `ent.Faction.set_isAI` (the ai-log per-caller tracers included) -> wrapper: a call
  with v true on an inited faction that is already AI and has a path grid and an AI controller returns true without
  calling vanilla. Every other call is vanilla's. Fails safe: in a trap, vanilla's call.
"""
from rules.common import *  # noqa: F401,F403


def build_isai_guard(cx, helpers, new_ids):
    orig = cx.fn('ent.Faction.set_isAI')
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    skip = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=skip, value=False)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fb.op('JFalse', cond=1, offset='end')
    fb.op('JFalse', cond=b.field(0, 'isAI'), offset='end')
    fb.op('JFalse', cond=b.field(0, 'inited'), offset='end')
    fb.op('JNull', reg=b.field(0, 'pathGrid'), offset='end')
    fb.op('JNull', reg=b.field(0, 'aiController'), offset='end')
    fb.op('Bool', dst=skip, value=True)
    fb.label('end')
    fb.end_try(guard)
    fb.op('JFalse', cond=skip, offset='call')
    fb.op('Bool', dst=res, value=True)
    fb.op('Ret', ret=res)
    fb.label('call')
    fb.op('Call2', dst=res, fun=orig.findex.value, arg0=0, arg1=1)
    fb.op('Ret', ret=res)
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
    if not n:
        raise ValueError('isai-guard: no reference to Faction.set_isAI')
    return {'isai-guard': n}
