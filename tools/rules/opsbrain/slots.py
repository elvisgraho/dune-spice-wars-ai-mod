"""Free held-operation slots for Cell Search and base-kill operations.

Emits into the casting pass's builder, using that pass's copied mission list.
"""
from rules.common import *  # noqa: F401,F403


def _cell_drop(fb, b, cx, helpers, fac, mm, lst):
    """No assassination detected against us: cancel a held (complete, unused) Cell Search. Log `opcell` drop why end."""
    det = b.cast(fb.get(fac, 'stateData', 'assassinationDetected', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=det, offset='cd_go')
    fb.op('JSGt', a=b.field(det, 'length'), b=b.const('i32', 0), offset='cd_end')
    fb.label('cd_go')
    fb.op('JNull', reg=lst, offset='cd_end')
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('cd')
    fb.op('JSGte', a=i, b=b.field(lst, 'length'), offset='cd_end')
    m = b.cast(b.call('hl.types.ArrayObj.getDyn', lst, i), 'logic.faction.Mission')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=m, offset='cd')
    mi = b.field(m, 'id')
    fb.op('JNull', reg=mi, offset='cd')
    fb.op('JNotEq', a=b.call('String.__compare', mi, fb.dyn(fb.string('CellSearch'))), b=b.const('i32', 0), offset='cd')
    fb.op('JTrue', cond=b.field(m, 'hasBeenUsed'), offset='cd')
    cm = cx.fn('logic.faction.MissionManager.cancelMission')
    ca = [a.value for a in cx.code.types[cm.type.value].definition.args]
    tf = fb.reg(ca[2])
    fb.op('Mov', dst=tf, src=b.field(m, 'targetFaction'))
    wa = fb.reg(ca[3])
    fb.op('Bool', dst=wa, value=False)
    r = fb.reg(cx.code.types[cm.type.value].definition.ret.value)
    fb.op('Call4', dst=r, fun=cm.findex.value, arg0=mm, arg1=mi, arg2=tf, arg3=wa)
    _log_ev(fb, b, cx, helpers, 'opcell', [('f', fb.get(fac, 'kind')), ('drop', mi), ('why', 'end')])
    fb.label('cd_end')


def _bk_drop_slot(fb, b, cx, helpers, fac, mm, lst):
    """A base-kill member (level >= 2) without a Supply Drop started or held and every op slot full cancels its
    newest held op (not a Supply Drop, base-kill op, Cell Search or Cease Fire): vanilla then buys the drop (scored
    first for a member, ops_scores). The members' slots were full of other ops and Supply Drop was never offered after
    the plan began (match 2026-10-24 23:3x: no campaign drop in 5 matches). Log `opcell` why bkdrop."""
    lv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'bkv'), fb.dyn(fac))
    fb.op('JNull', reg=lv, offset='bds_end')
    lvi = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=lvi, src=lv)
    fb.op('JSLt', a=lvi, b=b.const('i32', 2), offset='bds_end')
    sdid = fb.dyn(fb.string('MSupplyDrop'))
    gsm = cx.fn('logic.faction.MissionManager.getStartedMissions')
    snull = fb.reg(cx.code.types[gsm.type.value].definition.args[1].value)
    fb.op('Null', dst=snull)
    started = b.call('hl.types.ArrayObj.copy', b.call('logic.faction.MissionManager.getStartedMissions', mm, snull))
    n = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=n, src=b.const('i32', 0))
    i = fb.reg(cx.t('i32'))
    low = fb.reg(cx.t('logic.faction.Mission'))
    fb.op('Null', dst=low)
    keep = ('MSupplyDrop', 'CellSearch', 'MCeaseFire') + BK_OPS
    for k_, arr in enumerate((started, lst)):
        u = f'bds{k_}'
        fb.op('JNull', reg=arr, offset=u + 'd')
        fb.op('Mov', dst=i, src=b.const('i32', 0))
        b.loop_head(u)
        fb.op('JSGte', a=i, b=b.field(arr, 'length'), offset=u + 'd')
        m = b.cast(b.call('hl.types.ArrayObj.getDyn', arr, i), 'logic.faction.Mission')
        fb.op('Incr', dst=i)
        fb.op('JNull', reg=m, offset=u)
        mi = b.field(m, 'id')
        fb.op('JNull', reg=mi, offset=u)
        if k_ == 1:
            fb.op('JTrue', cond=b.field(m, 'hasBeenUsed'), offset=u)
        fb.op('JEq', a=b.call('String.__compare', mi, sdid), b=b.const('i32', 0), offset='bds_end')  # have one
        fb.op('Incr', dst=n)
        if k_ == 1:
            for kid in keep:
                fb.op('JEq', a=b.call('String.__compare', mi, fb.dyn(fb.string(kid))), b=b.const('i32', 0), offset=u)
            fb.op('Mov', dst=low, src=m)  # the newest other held op: cheapest to lose
        fb.op('JAlways', offset=u)
        fb.label(u + 'd')
    fb.op('JSLt', a=n, b=b.call('logic.faction.MissionManager.getOperationNbSlots', mm), offset='bds_end')
    fb.op('JNull', reg=low, offset='bds_end')
    _throttle(fb, b, cx, 'opbkd', fac, 60, 'bds_end')
    cm = cx.fn('logic.faction.MissionManager.cancelMission')
    ca = [a.value for a in cx.code.types[cm.type.value].definition.args]
    tf = fb.reg(ca[2])
    fb.op('Mov', dst=tf, src=b.field(low, 'targetFaction'))
    wa = fb.reg(ca[3])
    fb.op('Bool', dst=wa, value=False)
    r = fb.reg(cx.code.types[cm.type.value].definition.ret.value)
    fb.op('Call4', dst=r, fun=cm.findex.value, arg0=mm, arg1=b.field(low, 'id'), arg2=tf, arg3=wa)
    _log_ev(fb, b, cx, helpers, 'opcell', [('f', fb.get(fac, 'kind')), ('why', 'bkdrop'), ('drop', b.field(low, 'id'))])
    fb.label('bds_end')


def _cell_slot(fb, b, cx, helpers, fac, mm, lst):
    """Free an operation slot for Cell Search during an assassination against us (see module doc)."""
    det = b.cast(fb.get(fac, 'stateData', 'assassinationDetected', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=det, offset='cs_end')
    fb.op('JSLte', a=b.field(det, 'length'), b=b.const('i32', 0), offset='cs_end')
    csid = fb.dyn(fb.string('CellSearch'))
    gsm = cx.fn('logic.faction.MissionManager.getStartedMissions')
    snull = fb.reg(cx.code.types[gsm.type.value].definition.args[1].value)
    fb.op('Null', dst=snull)
    started = b.call('hl.types.ArrayObj.copy', b.call('logic.faction.MissionManager.getStartedMissions', mm, snull))
    n = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=n, src=b.const('i32', 0))
    i = fb.reg(cx.t('i32'))
    low = fb.reg(cx.t('logic.faction.Mission'))
    fb.op('Null', dst=low)
    for k_, arr in enumerate((started, lst)):
        u = f'cs{k_}'
        fb.op('JNull', reg=arr, offset=u + 'd')
        fb.op('Mov', dst=i, src=b.const('i32', 0))
        b.loop_head(u)
        fb.op('JSGte', a=i, b=b.field(arr, 'length'), offset=u + 'd')
        m = b.cast(b.call('hl.types.ArrayObj.getDyn', arr, i), 'logic.faction.Mission')
        fb.op('Incr', dst=i)
        fb.op('JNull', reg=m, offset=u)
        mi = b.field(m, 'id')
        fb.op('JNull', reg=mi, offset=u)
        fb.op('JEq', a=b.call('String.__compare', mi, csid), b=b.const('i32', 0), offset='cs_end')  # have one
        if k_ == 1:
            fb.op('JTrue', cond=b.field(m, 'hasBeenUsed'), offset=u)
            fb.op('Mov', dst=low, src=m)  # the last held one (newest): cheapest to lose
        fb.op('Incr', dst=n)
        fb.op('JAlways', offset=u)
        fb.label(u + 'd')
    fb.op('JSLt', a=n, b=b.call('logic.faction.MissionManager.getOperationNbSlots', mm), offset='cs_end')
    fb.op('JNull', reg=low, offset='cs_end')
    _throttle(fb, b, cx, 'opcell', fac, 30, 'cs_end')
    cm = cx.fn('logic.faction.MissionManager.cancelMission')
    ca = [a.value for a in cx.code.types[cm.type.value].definition.args]
    tf = fb.reg(ca[2])
    fb.op('Mov', dst=tf, src=b.field(low, 'targetFaction'))
    wa = fb.reg(ca[3])
    fb.op('Bool', dst=wa, value=False)
    r = fb.reg(cx.code.types[cm.type.value].definition.ret.value)
    fb.op('Call4', dst=r, fun=cm.findex.value, arg0=mm, arg1=b.field(low, 'id'), arg2=tf, arg3=wa)
    _log_ev(fb, b, cx, helpers, 'opcell', [('f', fb.get(fac, 'kind')), ('drop', b.field(low, 'id'))])
    fb.label('cs_end')
