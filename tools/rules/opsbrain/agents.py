"""Agent assignment scores for each faction's loadout infiltration requirements.

Category ranks preserve free slots, the opening Authority preference and vanilla
scores for categories outside the faction's table.
"""
from rules.common import *  # noqa: F401,F403


AGENT_CATS = {
    'Atreides': ['ILandsraad', 'ISpaceGuild', 'IChoam', 'IField', 'ICounterIntel'],
    'Harkonnen': ['IField', 'IChoam', 'ISpaceGuild', 'ICounterIntel'],
    'Smugglers': ['ISpaceGuild', 'IChoam', 'IField', 'ICounterIntel'],
    'Fremen': ['IField', 'ISpaceGuild', 'IChoam', 'ICounterIntel'],
    'Corrino': ['ISpaceGuild', 'ICounterIntel'], 'Ecaz': ['ISpaceGuild', 'ICounterIntel'],
    'Vernius': ['ISpaceGuild', 'ICounterIntel'],
}  # ICounterIntel last: every faction sat at level 0 there (match 00:25), Atreides needed 7 Cell Searches in 10 min


AG_W = 10000   # score of the first wanted category with a free slot (vanilla's weights are far below)


AG_STEP = 1000  # ... minus this per rank


AG_AUTH_N = 2   # opening: Arrakis (IField, +1 Authority per agent) first until it holds this many agents (user)


def build_agent_steer(cx, helpers, new_ids):
    """agent-steer: Spying.checkAgentAssignments' HScoring.agentAssignments call -> wrapper: vanilla's category
    scores, then each category of the faction's AGENT_CATS still offered (it has a free slot) scores AG_W - rank x
    AG_STEP, so agents fill the infiltrations the loadout ops need (Cease Fire: Landsraad 2, Sleeper Agent: Field 2,
    Extraction Network: Spacing Guild 2, Communication Jamming / Awaken the People: CHOAM 2) before any other;
    Counter-Intel and faction slots follow by vanilla's weights."""
    orig = cx.fn('logic.ai.$HScoring.agentAssignments')
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('Call2', dst=res, fun=orig.findex.value, arg0=0, arg1=1)  # vanilla, outside any trap
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    fb.op('JNull', reg=1, offset='end')
    kind = b.cast(fb.get(1, 'kind'), 'String')
    fb.op('JNull', reg=kind, offset='end')
    for fk, cats in AGENT_CATS.items():
        nxt = 'k' + fk
        fb.op('JNotEq', a=b.call('String.__compare', kind, fb.dyn(fb.string(fk))), b=b.const('i32', 0), offset=nxt)
        for rank, cat in enumerate(cats):
            sk = _uid('ag')
            fb.op('JFalse', cond=b.call('haxe.ds.StringMap.exists', res, fb.string(cat)), offset=sk)
            b.call('haxe.ds.StringMap.set', res, fb.string(cat), fb.dyn(b.const('f64', AG_W - rank * AG_STEP)))
            fb.label(sk)
        fb.op('JAlways', offset='auth')
        fb.label(nxt)
    # base-kill Landsraad (common.BK_OPS: Defense Breaches needs Landsraad 2, which no member reached in 7 late
    # matches): one plan member (level >= 2) pushes Landsraad above every category until it holds level 2, the one
    # whose Landsraad is highest among the partners (level >= 1, not the leader; ties: the first in faction order);
    # none once any partner holds level 2 (the op is bought once for the coalition: never stacked)
    fb.label('auth')
    bgaf = cx.fn('$HSpying.getAssignmentFromInfiltration')
    bgaf_a = [a_.value for a_ in cx.code.types[bgaf.type.value].definition.args]
    bgcl = cx.fn('logic.faction.SpyManager.getCurrentLevel')
    bgcl_a = [a_.value for a_ in cx.code.types[bgcl.type.value].definition.args]
    btn, brn = fb.reg(bgaf_a[1]), fb.reg(bgcl_a[2])
    fb.op('Null', dst=btn)
    fb.op('Null', dst=brn)
    # (diagnostic 2026-10-25: no `bkland` row in any raze match; `bklandx` (f, why) says which gate stopped a member
    # at level >= 2, once per 120 s: noslot = vanilla offered no Landsraad slot, have / partner / closer / tie)
    bkwhy = fb.reg(cx.t('String'))
    fb.op('Mov', dst=bkwhy, src=fb.string('noslot'))
    bkl = _bk_target(fb, b, cx, 1, 'bkl_d')
    bkv = _global_map(fb, b, cx, 'bkv')
    blv = b.call('haxe.ds.ObjectMap.get', bkv, fb.dyn(1))
    fb.op('JNull', reg=blv, offset='bkl_d')
    bli = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=bli, src=blv)
    fb.op('JSLt', a=bli, b=b.const('i32', 2), offset='bkl_d')
    fb.op('JFalse', cond=b.call('haxe.ds.StringMap.exists', res, fb.string('ILandsraad')), offset='bkl_x')
    basg = fb.reg(cx.code.types[bgaf.type.value].definition.ret.value)
    fb.op('Call2', dst=basg, fun=bgaf.findex.value, arg0=fb.string('ILandsraad'), arg1=btn)
    bspm = b.call('ent.Faction.get_spyManager', 1)
    fb.op('JNull', reg=bspm, offset='bkl_d')
    bmy, bot = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Call3', dst=bmy, fun=bgcl.findex.value, arg0=bspm, arg1=basg, arg2=brn)
    fb.op('Mov', dst=bkwhy, src=fb.string('have'))
    fb.op('JSGte', a=bmy, b=b.const('i32', 2), offset='bkl_x')  # ours already
    bseen = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=bseen, value=False)
    bfs = b.cast(fb.get(_state(fb, b, cx), 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=bfs, offset='bkl_d')
    bk = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=bk, src=b.const('i32', 0))
    b.loop_head('bkl_f')
    fb.op('JSGte', a=bk, b=b.field(bfs, 'length'), offset='bkl_set')
    bf = b.cast(b.call('hl.types.ArrayObj.getDyn', bfs, bk), 'ent.Faction')
    fb.op('Incr', dst=bk)
    fb.op('JNull', reg=bf, offset='bkl_f')
    fb.op('JNotEq', a=bf, b=1, offset='bkl_o')
    fb.op('Bool', dst=bseen, value=True)
    fb.op('JAlways', offset='bkl_f')
    fb.label('bkl_o')
    fb.op('JEq', a=bf, b=bkl, offset='bkl_f')
    bfv = b.call('haxe.ds.ObjectMap.get', bkv, fb.dyn(bf))
    fb.op('JNull', reg=bfv, offset='bkl_f')
    bfi = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=bfi, src=bfv)
    fb.op('JSLt', a=bfi, b=b.const('i32', 1), offset='bkl_f')
    bfsp = b.call('ent.Faction.get_spyManager', bf)
    fb.op('JNull', reg=bfsp, offset='bkl_f')
    fb.op('Call3', dst=bot, fun=bgcl.findex.value, arg0=bfsp, arg1=basg, arg2=brn)
    fb.op('Mov', dst=bkwhy, src=fb.string('partner'))
    fb.op('JSGte', a=bot, b=b.const('i32', 2), offset='bkl_x')  # a partner holds it
    fb.op('Mov', dst=bkwhy, src=fb.string('closer'))
    fb.op('JSGt', a=bot, b=bmy, offset='bkl_x')  # a partner is closer
    fb.op('JNotEq', a=bot, b=bmy, offset='bkl_f')
    fb.op('Mov', dst=bkwhy, src=fb.string('tie'))
    fb.op('JFalse', cond=bseen, offset='bkl_x')  # a tie with a faction before us: theirs
    fb.op('JAlways', offset='bkl_f')
    fb.label('bkl_set')
    b.call('haxe.ds.StringMap.set', res, fb.string('ILandsraad'), fb.dyn(b.const('f64', AG_W + 2 * AG_STEP)))
    _throttle(fb, b, cx, 'bkland', 1, 60, 'bkl_d')
    _log_ev(fb, b, cx, helpers, 'bkland', [('f', fb.get(1, 'kind')), ('lvl', fb.dyn(bmy))])
    fb.op('JAlways', offset='bkl_d')
    fb.label('bkl_x')
    _throttle(fb, b, cx, 'bklandx', 1, 120, 'bkl_d')
    _log_ev(fb, b, cx, helpers, 'bklandx', [('f', fb.get(1, 'kind')), ('why', bkwhy)])
    fb.label('bkl_d')
    fb.op('JFalse', cond=b.call('haxe.ds.StringMap.exists', res, fb.string('IField')), offset='end')
    gaf = cx.fn('$HSpying.getAssignmentFromInfiltration')
    gaf_a = [a_.value for a_ in cx.code.types[gaf.type.value].definition.args]
    tnul = fb.reg(gaf_a[1])
    fb.op('Null', dst=tnul)
    asg = fb.reg(cx.code.types[gaf.type.value].definition.ret.value)
    fb.op('Call2', dst=asg, fun=gaf.findex.value, arg0=fb.string('IField'), arg1=tnul)
    spm = b.call('ent.Faction.get_spyManager', 1)
    fb.op('JNull', reg=spm, offset='end')
    nf = b.call('logic.faction.SpyManager.getNbAgentsAssignedOnSlot', spm, asg)
    fb.op('JSGte', a=nf, b=b.const('i32', AG_AUTH_N), offset='end')
    b.call('haxe.ds.StringMap.set', res, fb.string('IField'), fb.dyn(b.const('f64', AG_W + AG_STEP)))
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    caller = cx.fn('logic.ai.Spying.checkAgentAssignments')
    sites = [op for op in caller.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == orig.findex.value]
    if len(sites) != 1:
        raise ValueError(f'agent-steer: expected 1 agentAssignments call in checkAgentAssignments, found {len(sites)}')
    sites[0].df['fun'].value = w
    return {'agent-steer': 1}
