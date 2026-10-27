"""Filter operation purchases to loadout wants, preserving assassination priorities.

OPS_RESTORE adds wanted operations omitted by vanilla's candidate filter.
"""
from rules.common import *  # noqa: F401,F403
from rules.opsbrain.loadouts import OPS_VANILLA, _ops_mission, _wants_for


OPB_LOG = 120  # s: `opbuy` (buy candidates after the loadout filter) log period per faction


OPS_RESTORE = ('MCeaseFire', 'MDefenseSabotage')  # wanted ops vanilla's candidate filter drops wrongly: added back


def _assassination(fb, b, fac, none):
    """Jump to `none` unless an assassination against fac is detected (stateData.assassinationDetected non-empty)."""
    det = b.cast(fb.get(fac, 'stateData', 'assassinationDetected', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=det, offset=none)
    fb.op('JSLte', a=b.field(det, 'length'), b=b.const('i32', 0), offset=none)


def build_ops_buy(cx, helpers, new_ids):
    """opsbuy: checkMissions' getAllPossibleMissions call -> wrapper (candidates = wants + OPS_VANILLA); and the
    rank scores, applied by build_ops_scores on the spyingMissions result."""
    orig = cx.fn('logic.ai.Spying.getAllPossibleMissions')
    ft = cx.code.types[orig.type.value].definition
    args = [a.value for a in ft.args]
    fb = FB(cx, args, ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('Call1', dst=res, fun=orig.findex.value, arg0=0)  # vanilla, outside any trap
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    fac = b.cast(fb.get(0, 'f'), 'ent.Faction')
    fb.op('JNull', reg=fac, offset='end')
    state = _state(fb, b, cx)
    keep = fb.reg(cx.t('haxe.ds.StringMap'))
    fb.op('New', dst=keep)
    v = fb.reg(cx.t('void'))
    fb.op('Call1', dst=v, fun=cx.fn('haxe.ds.$StringMap.__constructor__').findex.value, arg0=keep)
    one = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=one, value=True)

    def emit(mid, rank):
        b.call('haxe.ds.StringMap.set', keep, fb.string(mid), fb.dyn(one))
    for mid in OPS_VANILLA:
        if mid != 'CellSearch':
            emit(mid, 0)
    # Cell Search only while an assassination against us is detected (user): it does nothing else
    _assassination(fb, b, fac, 'ncs')
    emit('CellSearch', 0)
    fb.label('ncs')
    _wants_for(fb, b, cx, fac, state, emit)
    # base-kill ops (common.BK_OPS, user: the base attack uses ops its members prepare, never stacked): candidates
    # for a member at level >= 2 while no other plan member (level >= 1, not the leader) prepares or holds the same
    bkl = _bk_target(fb, b, cx, fac, 'bko_end')
    bkv = _global_map(fb, b, cx, 'bkv')
    blv = b.call('haxe.ds.ObjectMap.get', bkv, fb.dyn(fac))
    fb.op('JNull', reg=blv, offset='bko_end')
    bli = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=bli, src=blv)
    fb.op('JSLt', a=bli, b=b.const('i32', 2), offset='bko_end')
    # at war with the leader (both ops need War / Hostility: a member whose declaration was refused would hold one
    # it can't cast, and the one-holder rule would keep it from a partner that can; review 2026-10-24)
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, bkl), offset='bko_end')
    bfs = b.cast(fb.get(state, 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=bfs, offset='bko_end')
    for mid in BK_OPS:
        u = _uid('bko')
        bk = fb.reg(cx.t('i32'))
        fb.op('Mov', dst=bk, src=b.const('i32', 0))
        b.loop_head(u)
        fb.op('JSGte', a=bk, b=b.field(bfs, 'length'), offset=u + 'd')
        bf = b.cast(b.call('hl.types.ArrayObj.getDyn', bfs, bk), 'ent.Faction')
        fb.op('Incr', dst=bk)
        fb.op('JNull', reg=bf, offset=u)
        fb.op('JEq', a=bf, b=fac, offset=u)
        fb.op('JEq', a=bf, b=bkl, offset=u)
        bfv = b.call('haxe.ds.ObjectMap.get', bkv, fb.dyn(bf))
        fb.op('JNull', reg=bfv, offset=u)
        bfi = fb.reg(cx.t('i32'))
        fb.op('SafeCast', dst=bfi, src=bfv)
        fb.op('JSLt', a=bfi, b=b.const('i32', 1), offset=u)
        _has_op(fb, b, cx, bf, mid, u + 'x')  # a partner has it: not stacked
        fb.op('JAlways', offset=u)
        fb.label(u + 'd')
        emit(mid, 0)
        fb.label(u + 'x')
    fb.label('bko_end')
    # drop candidates not kept (backwards)
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.field(res, 'length'))
    dids = _new_array(fb, b, cx)
    dropped = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=dropped, src=b.const('i32', 0))
    b.loop_head('l')
    fb.op('JSLte', a=i, b=b.const('i32', 0), offset='ld')
    fb.op('Sub', dst=i, a=i, b=b.const('i32', 1))
    el = b.call('hl.types.ArrayObj.getDyn', res, i)
    fb.op('JNull', reg=el, offset='l')
    mid = b.cast(fb.get(el, 'inf', 'id'), 'String')
    fb.op('JNull', reg=mid, offset='l')
    fb.op('JTrue', cond=b.call('haxe.ds.StringMap.exists', keep, mid), offset='l')
    fb.op('JTrue', cond=b.call('$StringTools.startsWith', mid, fb.string('CB_')), offset='l')
    _ops_mission(fb, b, mid, 'l_drop')
    fb.op('JAlways', offset='l')  # a modded mission: kept
    fb.label('l_drop')
    b.call('hl.types.ArrayObj.remove', res, el)
    b.call('hl.types.ArrayObj.push', dids, fb.dyn(mid))
    fb.op('Incr', dst=dropped)
    fb.op('JAlways', offset='l')
    fb.label('ld')
    # restore wanted ops vanilla's filter (closure f41070) drops for no reason of ours: MCeaseFire is removed while
    # ANY player is not at peace with us, i.e. offered only when it is useless (Atreides held Landsraad 2 all match
    # 23:25 and never saw it). Taken from getAvailableMissions: not locked (levels), not started / complete
    mmr = b.call('ent.Faction.get_missionManager', fac)
    fb.op('JNull', reg=mmr, offset='rs_end')
    avm = b.call('logic.faction.MissionManager.getAvailableMissions', mmr)
    fb.op('JNull', reg=avm, offset='rs_end')

    def restore(mid, rank):
        if mid not in OPS_RESTORE:
            return
        u = _uid('rs')
        j = fb.reg(cx.t('i32'))
        fb.op('Mov', dst=j, src=b.const('i32', 0))
        b.loop_head(u)
        fb.op('JSGte', a=j, b=b.field(avm, 'length'), offset=u + 'd')
        el3 = b.call('hl.types.ArrayObj.getDyn', avm, j)
        fb.op('Incr', dst=j)
        fb.op('JNull', reg=el3, offset=u)
        inf3 = fb.get(el3, 'inf')
        fb.op('JNull', reg=inf3, offset=u)
        id3 = b.cast(fb.get(inf3, 'id'), 'String')
        fb.op('JNull', reg=id3, offset=u)
        fb.op('JNotEq', a=b.call('String.__compare', id3, fb.dyn(fb.string(mid))), b=b.const('i32', 0), offset=u)
        tf3 = b.cast(fb.get(el3, 'targetFaction'), 'ent.Faction')
        fb.op('JTrue', cond=b.call('logic.faction.MissionManager.isMissionLocked', mmr, inf3, tf3), offset=u)
        fb.op('JTrue', cond=b.call('logic.faction.MissionManager.isMissionStarted', mmr, id3, tf3), offset=u)
        fb.op('JTrue', cond=b.call('logic.faction.MissionManager.isMissionComplete', mmr, id3, tf3), offset=u)
        fb.op('JTrue', cond=b.call('hl.types.ArrayObj.contains', res, el3), offset=u + 'd')
        b.call('hl.types.ArrayObj.push', res, el3)
        fb.op('JAlways', offset=u + 'd')
        fb.label(u + 'd')
    _wants_for(fb, b, cx, fac, state, restore)
    # base-kill ops this faction may buy now (in `keep`: the plan gates above) too
    for mid in BK_OPS:
        if mid in OPS_RESTORE:
            u = _uid('rsb')
            fb.op('JFalse', cond=b.call('haxe.ds.StringMap.exists', keep, fb.string(mid)), offset=u)
            restore(mid, 0)
            fb.label(u)
    fb.label('rs_end')
    # save for Assassination (user): while it is buyable (500 Intel + 1000 Solari), nothing else is bought except a
    # Supply Drop (and Cell Search: Solari only, vanilla's answer to an assassination against us)
    k2 = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k2, src=b.const('i32', 0))
    b.loop_head('as_f')
    fb.op('JSGte', a=k2, b=b.field(res, 'length'), offset='as_end')
    ela = b.call('hl.types.ArrayObj.getDyn', res, k2)
    fb.op('Incr', dst=k2)
    fb.op('JNull', reg=ela, offset='as_f')
    ida = b.cast(fb.get(ela, 'inf', 'id'), 'String')
    fb.op('JNull', reg=ida, offset='as_f')
    fb.op('JNotEq', a=b.call('String.__compare', ida, fb.dyn(fb.string('Assassination'))), b=b.const('i32', 0),
          offset='as_f')
    fb.op('Mov', dst=k2, src=b.field(res, 'length'))
    b.loop_head('as_d')  # backwards: removal shifts the tail
    fb.op('JSLte', a=k2, b=b.const('i32', 0), offset='as_end')
    fb.op('Sub', dst=k2, a=k2, b=b.const('i32', 1))
    elb = b.call('hl.types.ArrayObj.getDyn', res, k2)
    fb.op('JNull', reg=elb, offset='as_d')
    idb = b.cast(fb.get(elb, 'inf', 'id'), 'String')
    fb.op('JNull', reg=idb, offset='as_d')
    for keepid in ('Assassination', 'MSupplyDrop', 'CellSearch') + BK_OPS:  # base-kill ops: only offered in a plan
        fb.op('JEq', a=b.call('String.__compare', idb, fb.dyn(fb.string(keepid))), b=b.const('i32', 0),
              offset='as_d')
    b.call('hl.types.ArrayObj.splice', res, k2, b.const('i32', 1))
    b.call('hl.types.ArrayObj.push', dids, fb.dyn(idb))
    fb.op('JAlways', offset='as_d')
    fb.label('as_end')
    # `opbuy` (OPB_LOG per faction): the candidates vanilla may buy from now
    _throttle(fb, b, cx, 'opbuy', fac, OPB_LOG, 'end')
    ids = _new_array(fb, b, cx)
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('lg')
    fb.op('JSGte', a=i, b=b.field(res, 'length'), offset='lgd')
    el2 = b.call('hl.types.ArrayObj.getDyn', res, i)
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=el2, offset='lg')
    b.call('hl.types.ArrayObj.push', ids, fb.get(el2, 'inf', 'id'))
    fb.op('JAlways', offset='lg')
    fb.label('lgd')
    _log_ev(fb, b, cx, helpers, 'opbuy', [('f', fb.get(fac, 'kind')), ('cand', ids), ('drop', dids),
                                          ('intel', b.call('ent.Faction.getResource', fac, b.const('i32', RES_INTEL)))])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    caller = cx.fn('logic.ai.Spying.checkMissions')
    sites = [op for op in caller.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == orig.findex.value]
    if len(sites) != 1:
        raise ValueError(f'opsbuy: expected 1 getAllPossibleMissions call in checkMissions, found {len(sites)}')
    sites[0].df['fun'].value = w
    return {'opsbuy': 1}
