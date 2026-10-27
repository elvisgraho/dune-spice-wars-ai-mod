"""Faction loadouts, mission ownership and operation purchase scores.

Loadouts are held at peace too. Unknown factions use the default loadout; missions
added by other mods stay under vanilla control. Shared by buying and Supply Drop.
"""
from rules.common import *  # noqa: F401,F403


WANTS = {
    'Atreides': [('MCeaseFire', None), ('MSupplyDrop', None), ('MScavengerTeam', None), ('MDecoyThumper', None),
                 ('MGearSabotage', None)],
    'Harkonnen': [('MSleeperAgents', None), ('MCombatDrugs', None), ('MScavengerTeam', None), ('MDecoyThumper', None),
                  ('MSupplyDrop', None), ('MGearSabotage', None)],
    'Smugglers': [('MSmugglingOperation', None), ('MSupplyDrop', None), ('MCommunicationJamming', None),
                  ('MScavengerTeam', None), ('MPoisonReserves', None), ('MGearSabotage', None)],
    'Fremen': [('MDecoyThumper', None), ('MSandCloak', None), ('MSupplyDrop', None), ('MAwakePeople', None),
               ('MGearSabotage', None)],
    'Corrino': [('MSupplyDrop', None)], 'Ecaz': [('MSupplyDrop', None)], 'Vernius': [('MSupplyDrop', None)],
}


OPS_VANILLA = ('CellSearch', 'InfiltrationCells', 'Assassination', 'MMaraudersRaid')  # + prefix CB_


WAR3 = ('Atreides', 'Harkonnen', 'Fremen')


WANTS_DEFAULT = [('MSupplyDrop', None), ('MScavengerTeam', None), ('MDecoyThumper', None), ('MGearSabotage', None)]


OPS_MISSIONS = tuple(r['id'] for r in game_rows('mission'))


def _ops_mission(fb, b, mid, yes):
    """Jump to `yes` when mission id `mid` (String reg) is in the vanilla data (else modded: vanilla's)."""
    for m in OPS_MISSIONS:
        fb.op('JEq', a=b.call('String.__compare', mid, fb.dyn(fb.string(m))), b=b.const('i32', 0), offset=yes)


def _wants_for(fb, b, cx, fac, state, emit):
    """For the faction's kind, call emit(mid) inside the code path where that want's condition holds."""
    kind = b.cast(fb.get(fac, 'kind'), 'String')
    done = _uid('wf')
    facs = b.cast(fb.get(state, 'factions', 'array'), 'hl.types.ArrayObj')
    war, war3 = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('Bool', dst=war, value=False)
    fb.op('Bool', dst=war3, value=False)
    fb.op('JNull', reg=facs, offset=done + 'wd')
    k = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head(done + 'w')
    fb.op('JSGte', a=k, b=b.field(facs, 'length'), offset=done + 'wd')
    f = b.cast(b.call('hl.types.ArrayObj.getDyn', facs, k), 'ent.Faction')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=f, offset=done + 'w')
    fb.op('JEq', a=f, b=fac, offset=done + 'w')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, f), offset=done + 'w')
    fb.op('Bool', dst=war, value=True)
    fk = b.cast(fb.get(f, 'kind'), 'String')
    for w3 in WAR3:
        fb.op('JNotEq', a=b.call('String.__compare', fk, fb.dyn(fb.string(w3))), b=b.const('i32', 0),
              offset=done + 'n' + w3)
        fb.op('Bool', dst=war3, value=True)
        fb.label(done + 'n' + w3)
    fb.op('JAlways', offset=done + 'w')
    fb.label(done + 'wd')
    fb.op('JNull', reg=kind, offset=done)
    for fk_, wants in list(WANTS.items()) + [(None, WANTS_DEFAULT)]:
        nxt = done + 'k' + str(fk_)
        if fk_ is not None:  # None: the default loadout, reached by a faction no entry matched (modded)
            fb.op('JNotEq', a=b.call('String.__compare', kind, fb.dyn(fb.string(fk_))), b=b.const('i32', 0),
                  offset=nxt)
        for rank, (mid, cond) in enumerate(wants):
            skip = done + 'c' + str(fk_) + mid
            if cond == 'war':
                fb.op('JFalse', cond=war, offset=skip)
            elif cond == 'war3':
                fb.op('JFalse', cond=war3, offset=skip)
            emit(mid, rank)
            fb.label(skip)
        fb.op('JAlways', offset=done)
        fb.label(nxt)
    fb.label(done)


def ops_scores(fb, b, cx, res, fac):
    """In the spyingMissions wrapper (sdrop-buy): a wanted op present in the score map scores OPS_W - rank x
    OPS_W_STEP (vanilla data weights are mostly 0: the pick was random among ties)."""
    state = _state(fb, b, cx)

    def emit(mid, rank):
        sk = _uid('sc')
        fb.op('JFalse', cond=b.call('haxe.ds.StringMap.exists', res, fb.string(mid)), offset=sk)
        b.call('haxe.ds.StringMap.set', res, fb.string(mid), fb.dyn(b.const('f64', OPS_W - rank * OPS_W_STEP)))
        fb.label(sk)
    _wants_for(fb, b, cx, fac, state, emit)
    # offered only in a base-kill plan (opsbuy): Defense Breaches above every want, Administrative Burden below them
    # (user: used rarely, once the enemy army is wiped)
    # a plan member at level >= 2 buys a Supply Drop before anything (the campaign drop at the strike point: no
    # member held one at go time in 3 matches)
    sdl = _uid('sdl')
    sdlv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'bkv'), fb.dyn(fac))
    fb.op('JNull', reg=sdlv, offset=sdl)
    sdli = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=sdli, src=sdlv)
    fb.op('JSLt', a=sdli, b=b.const('i32', 2), offset=sdl)
    fb.op('JFalse', cond=b.call('haxe.ds.StringMap.exists', res, fb.string('MSupplyDrop')), offset=sdl)
    b.call('haxe.ds.StringMap.set', res, fb.string('MSupplyDrop'), fb.dyn(b.const('f64', OPS_W + 2 * OPS_W_STEP)))
    fb.label(sdl)
    for mid, sc in (('MDefenseSabotage', OPS_W + OPS_W_STEP), ('MAdministrativeBurden', 10)):
        sk = _uid('scb')
        fb.op('JFalse', cond=b.call('haxe.ds.StringMap.exists', res, fb.string(mid)), offset=sk)
        b.call('haxe.ds.StringMap.set', res, fb.string(mid), fb.dyn(b.const('f64', sc)))
        fb.label(sk)
