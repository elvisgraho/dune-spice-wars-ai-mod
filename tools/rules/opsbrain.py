"""Operations takeover (docs/OPERATIONS-PLAN.md design, docs/OPERATIONS-IMPL.md build).

Vanilla's operation use is off for every military op (rules/ops.py: launch block + empty order lists); what a
faction buys comes from its loadout (`opsbuy`), what it casts and where from the triggers here.

- `opsbuy` (checkMissions' getAllPossibleMissions call -> wrapper): candidates = the faction's wanted ops (WANTS,
  bought at peace too (user: a peace can be cancelled or betrayed at any time); conditions 'war' / 'war3' remain
  available for a want that should wait for a war, none uses them) + OPS_VANILLA (Cell
  Search, Infiltration Cells, Assassination, Marauders Raid, CB_*). Vanilla buys only when Intel >= the largest
  Intel cost among its candidates: an unwanted 500-intel op no longer holds back a cheap one. While Assassination is a
  candidate (500 Intel + 1000 Solari) every other candidate is dropped except MSupplyDrop and CellSearch (user: save
  for it). Scores
  (spyingMissions wrapper, sdrop-buy): a wanted op scores OPS_W - OPS_W_STEP x its rank.
- `aimod_ops(mil, dt)` (tick chain after rally, every OPS_CHECK s per AI faction holding an op): triggers in order,
  at most one cast per tick (a combo pair casts together):
  1 extract (Smugglers' Extraction Network): our siege order at Engage / Action on a village zone, our armies at
    it < OPS_EXTRACT_B x their side there (fog-aware threat + militia + cover), the walk home >= OPS_EXTRACT_LAND:
    cast on the zone, cancel the order, walk our armies in the zone into the circle (radius 29), target into
    lost-siege memory (`slost`).
  2 ceasefire (Atreides' Cease Fire): an at-war faction occupies / besieges our village, capture progress below
    OPS_LATE (and at least OPS_CF_MIN; an occupation under way, never a Pillage: user), our power within RALLY_R (+
    our cover) < OPS_CF_HOPE x theirs within LOCAL.
  3 thumper (Decoy Thumper): our army on sand off our own land (there it just walks on: user) targeted by a worm,
    called into a neighbour zone holding a visible at-war faction army (user: only against player armies, never
    militia / rebels)
    (Unit.isWormTarget): a neighbour zone of its zone, never one of ours (the worm comes there), with worm activity and none of our armies (an at-war faction's zone first) gets the worm; ours is then
    protected (Zone_NoSandworm).
  3b deny (Decoy Thumper, user): a big visible at-war group (>= OPS_THUMP_PW in its zone) on sand, off its own land,
    walking >= OPS_THUMP_DEPTH more to a structure of ours its path ends near (OPS_THUMP_NEAR) that we can't hold
    (our armies within RALLY_R + cover < theirs x OPS_THUMP_HOPE), none of ours in its zone: worm into that zone.
  4 combat (fights: State.warzones we are in against an at-war faction, total power >= OPS_BIGFIGHT, their visible side >= OPS_FIGHT_H,
    B = ours / theirs in [OPS_B_LO, OPS_B_HI], theirs = max(visible warzone enemies, aimod_threat at our first army there)): Harkonnen Sleeper Agent + Combat Drugs (Drugs alone at
    B <= OPS_DRUG_HI), Fremen Hiding Tracks, Smugglers Poison the Reserves (>= 2 enemy armies there losing supply),
    Smugglers Communication Jamming on JAM_MIN_OPS enemy ops at once in that zone (Combat Drugs / Sleeper / Hiding
    Tracks / Toxic Vapors traits) or an Orbital Strike there (user: never for a single op),
    Scavenger Team at B >= OPS_SCAV_B with their side >= OPS_SCAV_H.
  5 siege (our Military orders on structures): Scavenger Team (+ Harkonnen Combat Drugs while the order's armies hold OPS_DRUG_SITE x the
    garrison side) on a sietch / renegade base in Action; Defense Sabotage on an at-war village with turret cover >= OPS_SAB_SHARE of its side at Engage /
    Action; Awaken the People from Regroup on another surveyed village of the target's owner >= AWAKE_HOPS
    zones from it (a distraction; a revolt at the target itself cancels our order); Smugglers' Communication Jamming on a Cease Fire
    (NoFight) at our target.
  Cell Search: an assassination detected against us with no Cell Search held / started and every slot full ->
  the held op ranked lowest is cancelled for it (vanilla buys Cell Search itself next pass).
  Logs `opcast` (f, op, why, s / z, B, M, H), `opfail` (f, op, why), `opcell` (f, drop)."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.worm import _move_to

ENGAGE = 4
AWAKE_HOPS = 2  # Awaken the People: on a village of the target's owner at least this many zones from our target
OPH_T = 60   # s: `ophold` snapshot period per faction
OPB_LOG = 120  # s: `opbuy` (buy candidates after the loadout filter) log period per faction
OPS_ABILITY = {
    'MScavengerTeam': 'ScavengerTeam', 'MDecoyThumper': 'WormCalling', 'MGearSabotage': 'GearSabotage',
    'MCeaseFire': 'CeaseFire', 'MCombatDrugs': 'CombatDrugs', 'MSleeperAgents': 'SleeperAgent',
    'MCommunicationJamming': 'CommunicationJamming', 'MPoisonReserves': 'PoisonReserves',
    'MSmugglingOperation': 'ExtractionNetwork', 'MSandCloak': 'SandCloak', 'MAwakePeople': 'CrowdManipulation',
}
# loadouts: (mission id, condition) in rank order, all held at peace too (user: peace can be cancelled or
# betrayed any time); MSupplyDrop is cast by rules/sdrop.py
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
OPS_BOLD = ('MSleeperAgents', 'MCombatDrugs')  # fight retreat x OPS_BOLD_K in their zone while they run
OPS_RESTORE = ('MCeaseFire',)  # wanted ops vanilla's candidate filter drops wrongly: added back (opsbuy)
OPS_DUR = 90  # s: an operation's effect (3 days)
OPS_VANILLA = ('CellSearch', 'InfiltrationCells', 'Assassination', 'MMaraudersRaid')  # + prefix CB_
WAR3 = ('Atreides', 'Harkonnen', 'Fremen')
ATTR_NOFIGHT = 626     # attribute NoFight (Cease Fire)
ATTR_OPBLOCK = 75      # attribute Operation_Block (Communication Jamming)
JAM_MIN_OPS = 2        # Communication Jamming in a fight: at least this many enemy op traits in the zone (user)
EXTRACT_R = 29         # Extraction Network circle radius around the village (trait TExtractionNetwork, attr 1403)


class Ops:
    """Bytecode helpers for one built function (fb / b) acting for faction register `fac`."""

    def __init__(self, cx, fb, b, helpers, fac, t):
        self.cx, self.fb, self.b, self.helpers, self.fac, self.t = cx, fb, b, helpers, fac, t
        cua = cx.fn('logic.faction.AbilityManager.canUseAbilityOn')
        uao = cx.fn('logic.faction.AbilityManager.useAbilityOn')
        self.cua, self.uao = cua, uao
        self.cua_a = [a.value for a in cx.code.types[cua.type.value].definition.args]
        self.uao_a = [a.value for a in cx.code.types[uao.type.value].definition.args]
        dt_t = cx.t('DisplayTarget')
        self.dt_t = dt_t
        self.dt_names = [c.name.resolve(cx.code) for c in cx.code.types[dt_t].definition.constructs]
        rt = cx.code.types[uao.type.value].definition.ret.value
        self.rt = rt
        self.rnames = [c.name.resolve(cx.code) for c in cx.code.types[rt].definition.constructs]
        has = cx.fn('ent.Object.hasAttribute')
        self.has = has
        self.hat = [a.value for a in cx.code.types[has.type.value].definition.args]

    def held(self, lst, mid, miss):
        """Mission register: an unused complete mission `mid` in lst; jump to `miss` when none."""
        fb, b, cx = self.fb, self.b, self.cx
        u = _uid('hl')
        m = fb.reg(cx.t('logic.faction.Mission'))
        i = fb.reg(cx.t('i32'))
        fb.op('JNull', reg=lst, offset=miss)
        fb.op('Mov', dst=i, src=b.const('i32', 0))
        b.loop_head(u)
        fb.op('JSGte', a=i, b=b.field(lst, 'length'), offset=miss)
        fb.op('Mov', dst=m, src=b.cast(b.call('hl.types.ArrayObj.getDyn', lst, i), 'logic.faction.Mission'))
        fb.op('Incr', dst=i)
        fb.op('JNull', reg=m, offset=u)
        mi = b.field(m, 'id')
        fb.op('JNull', reg=mi, offset=u)
        fb.op('JNotEq', a=b.call('String.__compare', mi, fb.dyn(fb.string(mid))), b=b.const('i32', 0), offset=u)
        fb.op('JTrue', cond=b.field(m, 'hasBeenUsed'), offset=u)
        return m

    def attr(self, z, atb, yes):
        """Jump to `yes` when zone z (ent.Zone) has attribute atb (any source)."""
        fb, b, cx = self.fb, self.b, self.cx
        zo, n2, n3 = fb.reg(self.hat[0]), fb.reg(self.hat[2]), fb.reg(self.hat[3])
        fb.op('Mov', dst=zo, src=z)
        fb.op('Null', dst=n2)
        fb.op('Null', dst=n3)
        hr = fb.reg(cx.t('bool'))
        fb.op('Call4', dst=hr, fun=self.has.findex.value, arg0=zo, arg1=b.const('i32', atb), arg2=n2, arg3=n3)
        fb.op('JTrue', cond=hr, offset=yes)

    def ztrait(self, z, tid, yes):
        """Jump to `yes` when zone z carries trait `tid` (TraitsManager.has(id, null...))."""
        fb, b, cx = self.fb, self.b, self.cx
        tm = b.call('ent.Object.get_traits', z)
        no = _uid('ztn')
        fb.op('JNull', reg=tm, offset=no)
        hf = cx.fn('logic.TraitsManager.has')
        ha = [a.value for a in cx.code.types[hf.type.value].definition.args]
        regs = [tm, fb.string(tid)]
        for k in range(2, len(ha)):
            r = fb.reg(ha[k])
            fb.op('Null', dst=r)
            regs.append(r)
        hr = fb.reg(cx.t('bool'))
        fb.op('CallN', dst=hr, fun=hf.findex.value, args=regs)
        fb.op('JTrue', cond=hr, offset=yes)
        fb.label(no)

    def cast(self, mid, m, why, fail, zone=None, struct=None, extra=()):
        """Cast held mission m (`mid`) for the faction: args {src: Spying(fac), zone | struct}; canUseAbilityOn,
        then useAbilityOn; falls through on Success (logs opcast, records map `opz` zone -> expiry), else logs
        opfail (throttled per faction + op) and jumps to `fail`."""
        fb, b, cx = self.fb, self.b, self.cx
        abid = fb.string(OPS_ABILITY[mid])
        u = _uid('oc')
        abm = b.call('ent.Faction.get_abilities', self.fac)
        fb.op('JNull', reg=abm, offset=fail)
        pdt = fb.reg(self.dt_t)
        fb.op('MakeEnum', dst=pdt, construct=self.dt_names.index('Spying'), args=[self.fac])
        pdo = fb.reg(cx.t('dynobj'))
        fb.op('New', dst=pdo)
        fb.op('DynSet', obj=pdo, field=cx.s('src'), src=fb.dyn(pdt))
        if zone is not None:
            fb.op('DynSet', obj=pdo, field=cx.s('zone'), src=fb.dyn(zone))
        if struct is not None:
            fb.op('DynSet', obj=pdo, field=cx.s('struct'), src=fb.dyn(struct))
        ca, ua = fb.reg(self.cua_a[2]), fb.reg(self.uao_a[2])
        fb.op('ToVirtual', dst=ca, src=pdo)
        fb.op('ToVirtual', dst=ua, src=pdo)
        c3, c4, u3, u4 = fb.reg(self.cua_a[3]), fb.reg(self.cua_a[4]), fb.reg(self.uao_a[3]), fb.reg(self.uao_a[4])
        for r in (c3, c4, u3, u4):
            fb.op('Null', dst=r)
        # checkUseAbilityOn (canUseAbilityOn = its result == Success): its index goes into `opfail` (r; names:
        # REVERSING EReason). A string switch over every reason at each cast site made the game quit at match start
        chk = cx.fn('logic.faction.AbilityManager.checkUseAbilityOn')
        rt2 = cx.code.types[chk.type.value].definition.ret.value
        rnames2 = [c_.name.resolve(cx.code) for c_ in cx.code.types[rt2].definition.constructs]
        cres0 = fb.reg(rt2)
        fb.op('CallN', dst=cres0, fun=chk.findex.value, args=[abm, abid, ca, c3, c4])
        why_ = fb.reg(cx.t('i32'))
        fb.op('EnumIndex', dst=why_, value=cres0)
        fb.op('JNotEq', a=why_, b=b.const('i32', rnames2.index('Success')), offset=u + 'f')
        cres = fb.reg(self.rt)
        cix = fb.reg(cx.t('i32'))
        fb.op('CallN', dst=cres, fun=self.uao.findex.value, args=[abm, abid, ua, u3, u4])
        fb.op('Mov', dst=why_, src=b.const('i32', -1))  # passed the check, refused on use
        fb.op('EnumIndex', dst=cix, value=cres)
        fb.op('JNotEq', a=cix, b=b.const('i32', self.rnames.index('Success')), offset=u + 'f')
        fields = [('f', fb.get(self.fac, 'kind')), ('op', mid), ('why', why)]
        if struct is not None:
            se = fb.reg(cx.t('ent.Entity'))
            fb.op('Mov', dst=se, src=struct)
            fields.append(('s', se))
        if zone is not None:
            zv = b.call('ent.Zone.getVillage', zone)
            zs = fb.reg(cx.t('ent.Entity'))
            fb.op('Null', dst=zs)
            fb.op('JNull', reg=zv, offset=u + 'nz')
            fb.op('Mov', dst=zs, src=zv)
            fb.label(u + 'nz')
            fields.append(('zs', zs))
            fields.append(('zid', fb.dyn(b.field(zone, 'id'))))
        fields.extend(extra)
        _log_ev(fb, b, cx, self.helpers, 'opcast', fields)
        if zone is not None and mid in OPS_BOLD:  # fight retreat holds there while it runs (rules/heal.py)
            exp = fb.reg(cx.t('f64'))
            fb.op('Add', dst=exp, a=self.t, b=b.const('f64', OPS_DUR))
            b.call('haxe.ds.ObjectMap.set', _fac_map(fb, b, cx, 'opbold', self.fac), fb.dyn(zone), fb.dyn(exp))
        fb.op('JAlways', offset=u + 'ok')
        fb.label(u + 'f')
        # throttled per held mission object (one per faction and op)
        _throttle(fb, b, cx, 'opfail', m, 30, fail)
        ff = [('f', fb.get(self.fac, 'kind')), ('op', mid), ('why', why), ('r', fb.dyn(why_))]
        if struct is not None:
            se2 = fb.reg(cx.t('ent.Entity'))
            fb.op('Mov', dst=se2, src=struct)
            ff.append(('s', se2))
        if zone is not None:
            ff.append(('zid', fb.dyn(b.field(zone, 'id'))))
        _log_ev(fb, b, cx, self.helpers, 'opfail', ff + list(extra))
        fb.op('JAlways', offset=fail)
        fb.label(u + 'ok')


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
    for fk_, wants in WANTS.items():
        nxt = done + 'k' + fk_
        fb.op('JNotEq', a=b.call('String.__compare', kind, fb.dyn(fb.string(fk_))), b=b.const('i32', 0), offset=nxt)
        for rank, (mid, cond) in enumerate(wants):
            skip = done + 'c' + fk_ + mid
            if cond == 'war':
                fb.op('JFalse', cond=war, offset=skip)
            elif cond == 'war3':
                fb.op('JFalse', cond=war3, offset=skip)
            emit(mid, rank)
            fb.label(skip)
        fb.op('JAlways', offset=done)
        fb.label(nxt)
    fb.label(done)


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
        emit(mid, 0)
    _wants_for(fb, b, cx, fac, state, emit)
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
    for keepid in ('Assassination', 'MSupplyDrop', 'CellSearch'):
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


def build_ops(cx, helpers, pw, threat, own, cover, militia, land):
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    state = _state(fb, b, cx)
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(state, 'time'))
    _tick(fb, b, cx, t, OPS_CHECK, 'end')
    o_ = Ops(cx, fb, b, helpers, fac, t)
    mm = b.call('ent.Faction.get_missionManager', fac)
    fb.op('JNull', reg=mm, offset='end')
    gcm = cx.fn('logic.faction.MissionManager.getCompleteMissions')
    fnull = fb.reg(cx.code.types[gcm.type.value].definition.args[1].value)
    fb.op('Null', dst=fnull)
    # getMissions returns one shared static array (MissionManager.missionsTmp): copy before any other mission call
    lst0 = b.call('logic.faction.MissionManager.getCompleteMissions', mm, fnull)
    fb.op('JNull', reg=lst0, offset='end')
    lst = b.call('hl.types.ArrayObj.copy', lst0)

    # Cell Search slot: an assassination detected against us, no Cell Search started / held, slots full -> cancel
    # the held op ranked lowest of our wants (vanilla's checkMissions then buys Cell Search)
    gc = fb.try_()
    _cell_slot(fb, b, cx, helpers, fac, mm, lst)
    fb.end_try(gc)

    # `ophold` every OPH_T per faction: held / started ops, Intel, agents
    gh = fb.try_()
    _throttle(fb, b, cx, 'ophold', fac, OPH_T, 'oh_end')
    spm = b.call('ent.Faction.get_spyManager', fac)
    fb.op('JNull', reg=spm, offset='oh_end')
    gsm = cx.fn('logic.faction.MissionManager.getStartedMissions')
    snull = fb.reg(cx.code.types[gsm.type.value].definition.args[1].value)
    fb.op('Null', dst=snull)
    stl0 = b.call('logic.faction.MissionManager.getStartedMissions', mm, snull)
    stl = b.call('hl.types.ArrayObj.copy', stl0)
    outs = []
    for nm, arr in (('held', lst), ('started', stl)):
        out = _new_array(fb, b, cx)
        u = _uid('oh')
        hi = fb.reg(cx.t('i32'))
        fb.op('JNull', reg=arr, offset=u + 'd')
        fb.op('Mov', dst=hi, src=b.const('i32', 0))
        b.loop_head(u)
        fb.op('JSGte', a=hi, b=b.field(arr, 'length'), offset=u + 'd')
        hm = b.cast(b.call('hl.types.ArrayObj.getDyn', arr, hi), 'logic.faction.Mission')
        fb.op('Incr', dst=hi)
        fb.op('JNull', reg=hm, offset=u)
        if nm == 'held':
            fb.op('JTrue', cond=b.field(hm, 'hasBeenUsed'), offset=u)
        b.call('hl.types.ArrayObj.push', out, fb.dyn(b.field(hm, 'id')))
        fb.op('JAlways', offset=u)
        fb.label(u + 'd')
        outs.append((nm, out))
    # infiltration per category: level / slots / agents there (`inf`: [{c, l, s, a}])
    infs = _new_array(fb, b, cx)
    gaf = cx.fn('$HSpying.getAssignmentFromInfiltration')
    gaf_a = [a_.value for a_ in cx.code.types[gaf.type.value].definition.args]
    gcl = cx.fn('logic.faction.SpyManager.getCurrentLevel')
    gcl_a = [a_.value for a_ in cx.code.types[gcl.type.value].definition.args]
    tnul, rnul = fb.reg(gaf_a[1]), fb.reg(gcl_a[2])
    fb.op('Null', dst=tnul)
    fb.op('Null', dst=rnul)
    for cat in ('IField', 'ISpaceGuild', 'IChoam', 'ILandsraad', 'ICounterIntel'):
        asg = fb.reg(cx.code.types[gaf.type.value].definition.ret.value)
        fb.op('Call2', dst=asg, fun=gaf.findex.value, arg0=fb.string(cat), arg1=tnul)
        lv = fb.reg(cx.t('i32'))
        fb.op('Call3', dst=lv, fun=gcl.findex.value, arg0=spm, arg1=asg, arg2=rnul)
        e_ = fb.reg(cx.t('dynobj'))
        fb.op('New', dst=e_)
        b.put(e_, 'c', fb.string(cat))
        b.put(e_, 'l', lv)
        b.put(e_, 's', b.call('logic.faction.SpyManager.getNbSlots', spm, asg))
        b.call('hl.types.ArrayObj.push', infs, fb.dyn(e_))
    outs.append(('inf', infs))
    _log_ev(fb, b, cx, helpers, 'ophold', [('f', fb.get(fac, 'kind')),
                                           ('intel', b.call('ent.Faction.getResource', fac, b.const('i32', RES_INTEL))),
                                           ('ag', b.call('logic.faction.SpyManager.getCurrentAgentsNb', spm)),
                                           ('agmax', b.call('logic.faction.SpyManager.getMaxAgentsNb', spm)),
                                           ('slots', b.call('logic.faction.MissionManager.getOperationNbSlots', mm))]
            + outs)
    fb.label('oh_end')
    fb.end_try(gh)

    fb.op('JSLte', a=b.field(lst, 'length'), b=b.const('i32', 0), offset='end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    gs = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gs, **{'global': cx.global_of('$Game')})
    world = b.field(b.field(gs, 'inst'), 'world')
    fb.op('JNull', reg=world, offset='end')
    zero, local = b.const('f64', 0), b.const('f64', LOCAL)
    casted = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=casted, value=False)
    kind = b.cast(fb.get(fac, 'kind'), 'String')

    def is_kind(name, no):
        fb.op('JNull', reg=kind, offset=no)
        fb.op('JNotEq', a=b.call('String.__compare', kind, fb.dyn(fb.string(name))), b=b.const('i32', 0), offset=no)

    k = fb.reg(cx.t('i32'))
    o = fb.reg(cx.t('logic.ai.AIOrder'))
    s = fb.reg(cx.t('ent.Structure'))
    se = fb.reg(cx.t('ent.Entity'))
    z = fb.reg(cx.t('ent.Zone'))
    ph, idx = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    mpow, hpow, q, d = (fb.reg(cx.t('f64')) for _ in range(4))
    nul_a = fb.reg(cx.t('ent.Army'))
    fb.op('Null', dst=nul_a)
    nul_e = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=nul_e)
    nul_arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=nul_arr)
    fno, ftrue = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    fb.op('Bool', dst=fno, value=False)
    fb.op('Bool', dst=ftrue, value=True)

    def order_loop(name, done, min_ph, max_ph):
        """Loop over our Military orders on structures in phase [min_ph, max_ph]: sets o, s, se, z, ph."""
        fb.op('Mov', dst=k, src=b.field(orders, 'length'))
        b.loop_head(name)
        fb.op('JSLte', a=k, b=b.const('i32', 0), offset=done)
        fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
        fb.op('Mov', dst=o, src=b.cast(b.call('hl.types.ArrayObj.getDyn', orders, k), 'logic.ai.AIOrder'))
        fb.op('JNull', reg=o, offset=name)
        fb.op('EnumIndex', dst=idx, value=b.field(o, 'type'))
        fb.op('JNotEq', a=idx, b=b.const('i32', MILITARY), offset=name)
        fb.op('Mov', dst=ph, src=b.field(o, 'phase'))
        fb.op('JSLt', a=ph, b=b.const('i32', min_ph), offset=name)
        fb.op('JSGt', a=ph, b=b.const('i32', max_ph), offset=name)
        fb.op('Mov', dst=s, src=b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'ent.Structure'))
        fb.op('JNull', reg=s, offset=name)
        fb.op('Mov', dst=se, src=s)
        fb.op('Mov', dst=z, src=b.call('ent.Entity.get_zone', se))
        fb.op('JNull', reg=z, offset=name)

    def order_power(dst, r):
        """dst = power of order o's armies within r of se."""
        un = b.field(o, 'units')
        fb.op('Mov', dst=dst, src=zero)
        u = _uid('op')
        fb.op('JNull', reg=un, offset=u + 'd')
        j = fb.reg(cx.t('i32'))
        pv = fb.reg(cx.t('f64'))
        x = _army_loop(fb, b, un, b.field(un, 'length'), j, u, u + 'd')
        fb.op('JSGt', a=b.call('ent.Entity.getDistTo', x, se), b=b.const('f64', r), offset=u)
        fb.op('Call1', dst=pv, fun=pw, arg0=x)
        fb.op('Add', dst=dst, a=dst, b=pv)
        fb.op('JAlways', offset=u)
        fb.label(u + 'd')

    def their_side(dst):
        """dst = their side at se: fog-aware threat within LOCAL + militia + enemy turret cover (s excluded:
        silent while besieged)."""
        fb.op('Call3', dst=dst, fun=threat, arg0=fac, arg1=se, arg2=local)
        fb.op('Call1', dst=q, fun=militia, arg0=s)
        fb.op('Add', dst=dst, a=dst, b=q)
        fb.op('CallN', dst=q, fun=cover, args=[fac, se, se, fno, nul_arr])
        fb.op('Add', dst=dst, a=dst, b=q)

    # ---- 1 extract (Smugglers): a siege going badly far from home
    g = fb.try_()
    is_kind('Smugglers', 'x_end')
    mx = o_.held(lst, 'MSmugglingOperation', 'x_end')
    order_loop('x_o', 'x_end', ENGAGE, ACTION)
    vz = b.call('ent.Zone.getVillage', z)
    fb.op('JNull', reg=vz, offset='x_o')
    order_power(mpow, ENGAGE_R)
    fb.op('JSLte', a=mpow, b=zero, offset='x_o')
    their_side(hpow)
    fb.op('JSLt', a=hpow, b=b.const('f64', RALLY_MIN_H), offset='x_o')
    fb.op('Mul', dst=q, a=hpow, b=_ratio(fb, b, OPS_EXTRACT_B))
    fb.op('JSGte', a=mpow, b=q, offset='x_o')
    fb.op('Call2', dst=d, fun=land, arg0=fac, arg1=se)
    fb.op('JSLt', a=d, b=b.const('f64', OPS_EXTRACT_LAND), offset='x_o')
    o_.attr(z, ATTR_OPBLOCK, 'x_o')
    o_.cast('MSmugglingOperation', mx, 'extract', 'x_o', zone=z, extra=[('s', se), ('M', mpow), ('H', hpow)])
    # cancel the order, walk its armies in the zone into the circle, lost-siege memory
    vx, vy = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    vze = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=vze, src=vz)
    fb.op('Mov', dst=vx, src=b.field(vze, 'posx'))
    fb.op('Mov', dst=vy, src=b.field(vze, 'posy'))
    un = b.field(o, 'units')
    fb.op('JNull', reg=un, offset='x_mv')
    arr = b.call('hl.types.ArrayObj.copy', un)
    reason = cx.code.types[cx.fn('logic.ai.AIOrder.stop').type.value].definition.args[1].value
    cancel = fb.reg(reason)
    fb.op('MakeEnum', dst=cancel, construct=CANCEL, args=[])
    b.call('logic.ai.AIOrder.stop', o, cancel)
    j = fb.reg(cx.t('i32'))
    x = _army_loop(fb, b, arr, b.field(arr, 'length'), j, 'x_a', 'x_mv')
    xe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=xe, src=x)
    fb.op('JNotEq', a=b.call('ent.Entity.get_zone', xe), b=z, offset='x_a')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', xe, vze), b=b.const('f64', EXTRACT_R - 6), offset='x_a')
    _move_to(fb, b, cx, x, vx, vy, fac)
    fb.op('JAlways', offset='x_a')
    fb.label('x_mv')
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'slost'), fb.dyn(se), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'slostf'), fb.dyn(se), fb.dyn(fac))
    fb.op('Bool', dst=casted, value=True)
    fb.label('x_end')
    fb.end_try(g)
    fb.op('JTrue', cond=casted, offset='end')

    # ---- 2 ceasefire (Atreides): our village being captured, no relief that wins
    g = fb.try_()
    is_kind('Atreides', 'c_end')
    mc = o_.held(lst, 'MCeaseFire', 'c_end')
    sts = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=sts, offset='c_end')
    fb.op('Mov', dst=k, src=b.field(sts, 'length'))
    b.loop_head('c_s')
    fb.op('JSLte', a=k, b=b.const('i32', 0), offset='c_end')
    fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
    fb.op('Mov', dst=s, src=b.cast(b.call('hl.types.ArrayObj.getDyn', sts, k), 'ent.Structure'))
    fb.op('JNull', reg=s, offset='c_s')
    sg = b.field(s, 'siege')
    fb.op('JNull', reg=sg, offset='c_s')
    bf = fb.reg(cx.t('ent.Faction'))
    fb.op('Mov', dst=bf, src=b.field(sg, 'besiegingFaction'))
    fb.op('JNotNull', reg=bf, offset='c_bf')
    fb.op('Mov', dst=bf, src=b.call('ent.comp.SiegeComponent.getOccupierFaction', sg))
    fb.op('JNull', reg=bf, offset='c_s')
    fb.label('c_bf')
    fb.op('JEq', a=bf, b=fac, offset='c_s')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, bf), offset='c_s')
    # only an occupation under way, never a Pillage (user): the militia fight and a pillage aren't worth it; and
    # delayed to OPS_CF_MIN progress (user): the attacker commits and spends first (both casts of match 2026-10-04
    # 14:2x went out at progress 0)
    cak = b.call('ent.comp.SiegeComponent.getOccupationActionKind', sg)
    fb.op('JNull', reg=cak, offset='c_s')
    fb.op('JEq', a=b.call('String.__compare', cak, fb.dyn(fb.string('Pillage'))), b=b.const('i32', 0), offset='c_s')
    pr = b.call('ent.comp.SiegeComponent.getOccupationActionProgress', sg)
    fb.op('JSLt', a=pr, b=_ratio(fb, b, OPS_CF_MIN), offset='c_s')
    fb.op('JSGte', a=pr, b=_ratio(fb, b, OPS_LATE), offset='c_s')
    fb.op('Mov', dst=se, src=s)
    fb.op('Mov', dst=z, src=b.call('ent.Entity.get_zone', se))
    fb.op('JNull', reg=z, offset='c_s')
    o_.attr(z, ATTR_NOFIGHT, 'c_s')
    o_.attr(z, ATTR_OPBLOCK, 'c_s')
    fb.op('Call3', dst=hpow, fun=threat, arg0=fac, arg1=se, arg2=local)
    fb.op('CallN', dst=mpow, fun=own, args=[fac, se, b.const('f64', RALLY_R), nul_a])
    fb.op('CallN', dst=q, fun=cover, args=[fac, se, nul_e, ftrue, nul_arr])
    fb.op('Add', dst=mpow, a=mpow, b=q)
    # `opcf` (20 s per village): a capture of ours the trigger judged (why no Cease Fire)
    _throttle(fb, b, cx, 'opcf', se, 20, 'c_nl')
    _log_ev(fb, b, cx, helpers, 'opcf', [('f', fb.get(fac, 'kind')), ('s', se), ('pr%', pr), ('M', mpow),
                                         ('H', hpow)])
    fb.label('c_nl')
    fb.op('JSLt', a=hpow, b=b.const('f64', RALLY_MIN_H), offset='c_s')
    fb.op('Mul', dst=q, a=hpow, b=_ratio(fb, b, OPS_CF_HOPE))
    fb.op('JSGte', a=mpow, b=q, offset='c_s')
    o_.cast('MCeaseFire', mc, 'defend', 'c_s', zone=z, extra=[('s', se), ('M', mpow), ('H', hpow), ('pr%', pr)])
    fb.op('Bool', dst=casted, value=True)
    fb.label('c_end')
    fb.end_try(g)
    fb.op('JTrue', cond=casted, offset='end')

    # ---- 3 thumper: our army on sand targeted by a worm -> worm called next door
    g = fb.try_()
    mt = o_.held(lst, 'MDecoyThumper', 't_end')
    arr2, alen2 = _my_armies(fb, b, fac, 't_end')
    j2 = fb.reg(cx.t('i32'))
    a = _army_loop(fb, b, arr2, alen2, j2, 't_a', 't_end')
    fb.op('JFalse', cond=b.call('ent.Unit.isWormTarget', a), offset='t_a')
    fb.op('JNotNull', reg=b.field(a, 'harvestComponent'), offset='t_a')  # harvesters: worm-flee / recall
    fb.op('JFalse', cond=b.call('ent.Entity.isOnSand', a), offset='t_a')
    ae = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ae, src=a)
    az = b.call('ent.Entity.get_zone', ae)
    fb.op('JNull', reg=az, offset='t_a')
    fb.op('JEq', a=b.field(az, 'owner'), b=fac, offset='t_a')  # on our own land: no thumper for an alert (user)
    nb = b.field(az, 'neighbors')
    fb.op('JNull', reg=nb, offset='t_a')
    best = fb.reg(cx.t('ent.Zone'))
    bsc, sc = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Null', dst=best)
    fb.op('Mov', dst=bsc, src=b.const('i32', -1))
    kk = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=kk, src=b.const('i32', 0))
    b.loop_head('t_n')
    fb.op('JSGte', a=kk, b=b.field(nb, 'length'), offset='t_nd')
    nz = b.cast(b.call('hl.types.ArrayObj.getDyn', nb, kk), 'ent.Zone')
    fb.op('Incr', dst=kk)
    fb.op('JNull', reg=nz, offset='t_n')
    fb.op('JSLte', a=b.call('ent.Zone.getCurrentWormActivity', nz), b=zero, offset='t_n')
    fb.op('JEq', a=b.field(nz, 'owner'), b=fac, offset='t_n')  # never a worm into our own region (user)
    o_.attr(nz, ATTR_OPBLOCK, 't_n')
    # none of our armies in it
    j3 = fb.reg(cx.t('i32'))
    y = _army_loop(fb, b, arr2, alen2, j3, 't_m', 't_md')
    ye = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ye, src=y)
    fb.op('JEq', a=b.call('ent.Entity.get_zone', ye), b=nz, offset='t_n')
    fb.op('JAlways', offset='t_m')
    fb.label('t_md')
    # only onto a player's army (user: never against militia / rebels: Harkonnen called a worm for an H_Elite on a
    # Discovery walk): a visible army of a faction at war with us stands in it
    tsa = b.field(state, 'armies')
    fb.op('JNull', reg=tsa, offset='t_n')
    jt = fb.reg(cx.t('i32'))
    w5 = _army_loop(fb, b, tsa, b.field(tsa, 'length'), jt, 't_w', 't_n')
    wo5 = b.call('ent.Entity.get_owner', w5)
    fb.op('JNull', reg=wo5, offset='t_w')
    fb.op('JEq', a=wo5, b=fac, offset='t_w')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, wo5), offset='t_w')
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', w5, fac), offset='t_w')
    w5e = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=w5e, src=w5)
    fb.op('JNotEq', a=b.call('ent.Entity.get_zone', w5e), b=nz, offset='t_w')
    fb.op('Mov', dst=sc, src=b.const('i32', 0))
    no_ = b.field(nz, 'owner')
    fb.op('JNull', reg=no_, offset='t_sc')
    fb.op('JEq', a=no_, b=fac, offset='t_sc')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, no_), offset='t_sc')
    fb.op('Mov', dst=sc, src=b.const('i32', 1))
    fb.label('t_sc')
    fb.op('JSLte', a=sc, b=bsc, offset='t_n')
    fb.op('Mov', dst=bsc, src=sc)
    fb.op('Mov', dst=best, src=nz)
    fb.op('JAlways', offset='t_n')
    fb.label('t_nd')
    fb.op('JNull', reg=best, offset='t_a')
    o_.cast('MDecoyThumper', mt, 'worm', 't_a', zone=best, extra=[('a', ae)])
    fb.op('Bool', dst=casted, value=True)
    fb.label('t_end')
    fb.end_try(g)
    fb.op('JTrue', cond=casted, offset='end')

    # ---- 3b deny thumper (user): a big visible hostile group on sand still far from the village of ours its path
    # ends at (>= OPS_THUMP_DEPTH to go), which we can't hold there (our armies within RALLY_R + our cover < theirs
    # x OPS_THUMP_HOPE): the worm is called into its zone (ours too); none of our armies in it
    g = fb.try_()
    mt2 = o_.held(lst, 'MDecoyThumper', 'd_end')
    sarr = b.field(state, 'armies')
    fb.op('JNull', reg=sarr, offset='d_end')
    ours = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=ours, offset='d_end')
    marr, mlen = _my_armies(fb, b, fac, 'd_end')
    jd = fb.reg(cx.t('i32'))
    dx_, dy_, dd_, bd_, gp_, pv2 = (fb.reg(cx.t('f64')) for _ in range(6))
    tv = fb.reg(cx.t('ent.Structure'))
    x5 = _army_loop(fb, b, sarr, b.field(sarr, 'length'), jd, 'd_x', 'd_end')
    xo5 = b.call('ent.Entity.get_owner', x5)
    fb.op('JNull', reg=xo5, offset='d_x')
    fb.op('JEq', a=xo5, b=fac, offset='d_x')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, xo5), offset='d_x')
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', x5, fac), offset='d_x')
    fb.op('JFalse', cond=b.call('ent.Unit.isMoving', x5), offset='d_x')
    fb.op('JFalse', cond=b.call('ent.Entity.isOnSand', x5), offset='d_x')
    x5e = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=x5e, src=x5)
    xz5 = b.call('ent.Entity.get_zone', x5e)
    fb.op('JNull', reg=xz5, offset='d_x')
    fb.op('JSLte', a=b.call('ent.Zone.getCurrentWormActivity', xz5), b=zero, offset='d_x')
    fb.op('JEq', a=b.field(xz5, 'owner'), b=xo5, offset='d_x')  # on its own land it is home before any worm
    o_.attr(xz5, ATTR_OPBLOCK, 'd_x')
    pe5 = b.call('ent.MobileEntity.getCurrentPathEnd', x5)
    fb.op('JNull', reg=pe5, offset='d_x')
    ex5, ey5 = b.field(pe5, 'x'), b.field(pe5, 'y')
    # still far to go
    fb.op('Sub', dst=dx_, a=ex5, b=b.field(x5, 'posx'))
    fb.op('Sub', dst=dy_, a=ey5, b=b.field(x5, 'posy'))
    fb.op('Mul', dst=dx_, a=dx_, b=dx_)
    fb.op('Mul', dst=dy_, a=dy_, b=dy_)
    fb.op('Add', dst=dd_, a=dx_, b=dy_)
    fb.op('JSLt', a=dd_, b=b.const('f64', OPS_THUMP_DEPTH * OPS_THUMP_DEPTH), offset='d_x')
    # headed for one of our structures: the one nearest its path end, within OPS_THUMP_NEAR
    fb.op('Null', dst=tv)
    fb.op('Mov', dst=bd_, src=b.const('f64', OPS_THUMP_NEAR * OPS_THUMP_NEAR))
    ks = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=ks, src=b.const('i32', 0))
    b.loop_head('d_s')
    fb.op('JSGte', a=ks, b=b.field(ours, 'length'), offset='d_sd')
    sv = b.cast(b.call('hl.types.ArrayObj.getDyn', ours, ks), 'ent.Structure')
    fb.op('Incr', dst=ks)
    fb.op('JNull', reg=sv, offset='d_s')
    fb.op('Sub', dst=dx_, a=ex5, b=b.field(sv, 'posx'))
    fb.op('Sub', dst=dy_, a=ey5, b=b.field(sv, 'posy'))
    fb.op('Mul', dst=dx_, a=dx_, b=dx_)
    fb.op('Mul', dst=dy_, a=dy_, b=dy_)
    fb.op('Add', dst=dd_, a=dx_, b=dy_)
    fb.op('JSGte', a=dd_, b=bd_, offset='d_s')
    fb.op('Mov', dst=bd_, src=dd_)
    fb.op('Mov', dst=tv, src=sv)
    fb.op('JAlways', offset='d_s')
    fb.label('d_sd')
    fb.op('JNull', reg=tv, offset='d_x')
    # their group in that zone (visible, at war)
    fb.op('Mov', dst=gp_, src=zero)
    jg = fb.reg(cx.t('i32'))
    y5 = _army_loop(fb, b, sarr, b.field(sarr, 'length'), jg, 'd_g', 'd_gd')
    yo5 = b.call('ent.Entity.get_owner', y5)
    fb.op('JNull', reg=yo5, offset='d_g')
    fb.op('JEq', a=yo5, b=fac, offset='d_g')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, yo5), offset='d_g')
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', y5, fac), offset='d_g')
    y5e = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=y5e, src=y5)
    fb.op('JNotEq', a=b.call('ent.Entity.get_zone', y5e), b=xz5, offset='d_g')
    fb.op('Call1', dst=pv2, fun=pw, arg0=y5)
    fb.op('Add', dst=gp_, a=gp_, b=pv2)
    fb.op('JAlways', offset='d_g')
    fb.label('d_gd')
    fb.op('JSLt', a=gp_, b=b.const('f64', OPS_THUMP_PW), offset='d_x')
    # none of our armies in that zone
    jm = fb.reg(cx.t('i32'))
    m5 = _army_loop(fb, b, marr, mlen, jm, 'd_m', 'd_md')
    m5e = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=m5e, src=m5)
    fb.op('JEq', a=b.call('ent.Entity.get_zone', m5e), b=xz5, offset='d_x')
    fb.op('JAlways', offset='d_m')
    fb.label('d_md')
    # we can't hold the village: our armies near it + our cover < theirs x OPS_THUMP_HOPE
    tve = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=tve, src=tv)
    fb.op('CallN', dst=mpow, fun=own, args=[fac, tve, b.const('f64', RALLY_R), nul_a])
    fb.op('CallN', dst=q, fun=cover, args=[fac, tve, nul_e, ftrue, nul_arr])
    fb.op('Add', dst=mpow, a=mpow, b=q)
    fb.op('Mul', dst=q, a=gp_, b=_ratio(fb, b, OPS_THUMP_HOPE))
    fb.op('JSGte', a=mpow, b=q, offset='d_x')
    o_.cast('MDecoyThumper', mt2, 'deny', 'd_x', zone=xz5, extra=[('s', tve), ('a', x5e), ('M', mpow), ('H', gp_)])
    fb.op('Bool', dst=casted, value=True)
    fb.label('d_end')
    fb.end_try(g)
    fb.op('JTrue', cond=casted, offset='end')

    # ---- 4 fights
    g = fb.try_()
    wza = b.cast(b.field(b.field(b.field(state, 'warzones'), 'warzones'), 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=wza, offset='f_end')
    gfa = cx.fn('logic.state.Warzone.getFactionArmies')
    gfa_a = [a_.value for a_ in cx.code.types[gfa.type.value].definition.args]
    gea = cx.fn('logic.state.Warzone.getEnemyArmies')
    gea_a = [a_.value for a_ in cx.code.types[gea.type.value].definition.args]
    fq1, fq2, eq1, eq2 = fb.reg(gfa_a[2]), fb.reg(gfa_a[3]), fb.reg(gea_a[2]), fb.reg(gea_a[3])
    for r in (fq1, fq2, eq1, eq2):
        fb.op('Null', dst=r)
    bal, tot = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    nours, nlose = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    wz = fb.reg(cx.t('logic.state.Warzone'))
    pv = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head('f_w')
    fb.op('JSGte', a=k, b=b.field(wza, 'length'), offset='f_end')
    fb.op('Mov', dst=wz, src=b.cast(b.call('hl.types.ArrayObj.getDyn', wza, k), 'logic.state.Warzone'))
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=wz, offset='f_w')
    fb.op('JFalse', cond=b.call('logic.state.Warzone.isInvolved', wz, fac), offset='f_w')
    # our / their power and counts
    fb.op('Mov', dst=mpow, src=zero)
    fb.op('Mov', dst=hpow, src=zero)
    fb.op('Mov', dst=nours, src=b.const('i32', 0))
    fb.op('Mov', dst=nlose, src=b.const('i32', 0))
    oa = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('CallN', dst=oa, fun=gfa.findex.value, args=[wz, fac, fq1, fq2])
    fb.op('JNull', reg=oa, offset='f_od')
    j4 = fb.reg(cx.t('i32'))
    x4 = _army_loop(fb, b, oa, b.field(oa, 'length'), j4, 'f_o', 'f_od')
    fb.op('Call1', dst=pv, fun=pw, arg0=x4)
    fb.op('Add', dst=mpow, a=mpow, b=pv)
    fb.op('Incr', dst=nours)
    fb.op('JAlways', offset='f_o')
    fb.label('f_od')
    ea = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('CallN', dst=ea, fun=gea.findex.value, args=[wz, fac, eq1, eq2])
    fb.op('JNull', reg=ea, offset='f_ed')
    j5 = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=j5, src=b.const('i32', 0))
    b.loop_head('f_e')
    fb.op('JSGte', a=j5, b=b.field(ea, 'length'), offset='f_ed')
    ex = b.cast(b.call('hl.types.ArrayObj.getDyn', ea, j5), 'ent.Army')
    fb.op('Incr', dst=j5)
    fb.op('JNull', reg=ex, offset='f_e')
    # militia isn't a real fight (user: Harkonnen spent Combat Drugs + Scavenger Team on Fremen's Fondak, militia
    # only, H 158k, match 2026-10-04 20:5x): only armies count; the capture's militia fight needs no op
    # ... except a sietch / renegade base's garrison (user: beating those is a real fight)
    fb.op('JFalse', cond=b.field(ex, 'isMilitia'), offset='f_ecnt')
    _strong_site(fb, b, b.field(ex, 'militiaSource'), 'f_ecnt')
    fb.op('JAlways', offset='f_e')
    fb.label('f_ecnt')
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', ex, fac), offset='f_e')  # fog
    fb.op('Call1', dst=pv, fun=pw, arg0=ex)
    fb.op('Add', dst=hpow, a=hpow, b=pv)
    fb.op('JFalse', cond=b.call('ent.Army.isLosingSupply', ex), offset='f_e')
    fb.op('Incr', dst=nlose)
    fb.op('JAlways', offset='f_e')
    fb.label('f_ed')
    # their side also as our fog-aware threat around our first army there (the warzone's enemy list missed a relief
    # stack: Smugglers' Scavenger at Sinriyah 52:24 read H 147k while its fight retreat read 424k and was retreating)
    fb.op('JNull', reg=oa, offset='f_th')
    fb.op('JSLte', a=b.field(oa, 'length'), b=b.const('i32', 0), offset='f_th')
    x0 = b.cast(b.call('hl.types.ArrayObj.getDyn', oa, b.const('i32', 0)), 'ent.Army')
    fb.op('JNull', reg=x0, offset='f_th')
    x0e = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=x0e, src=x0)
    fb.op('Call3', dst=q, fun=threat, arg0=fac, arg1=x0e, arg2=local)
    fb.op('JSLte', a=q, b=hpow, offset='f_th')
    fb.op('Mov', dst=hpow, src=q)
    fb.label('f_th')
    opp = b.call('logic.state.Warzone.getMainOpponent', wz, fac)
    # `opfz` (every 20 s per faction): a fight of ours with an at-war faction's armies we see (why no combat op)
    fb.op('JSLt', a=hpow, b=b.const('f64', OPS_FIGHT_H), offset='f_nl')
    _throttle(fb, b, cx, 'opfz', fac, 20, 'f_nl')
    oppk = fb.reg(cx.t('String'))
    fb.op('Null', dst=oppk)
    fb.op('JNull', reg=opp, offset='f_lg')
    fb.op('Mov', dst=oppk, src=b.cast(fb.get(opp, 'kind'), 'String'))
    fb.label('f_lg')
    _log_ev(fb, b, cx, helpers, 'opfz', [('f', fb.get(fac, 'kind')), ('opp', oppk), ('M', mpow), ('H', hpow),
                                         ('n', fb.dyn(nours)), ('nl', fb.dyn(nlose))])
    fb.label('f_nl')
    fb.op('JNull', reg=opp, offset='f_w')  # militia / raiders: no faction opponent
    fb.op('JEq', a=opp, b=fac, offset='f_w')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, opp), offset='f_w')
    c = b.call('logic.state.Warzone.get_centroid', wz)
    fb.op('JNull', reg=c, offset='f_w')
    fb.op('Mov', dst=z, src=b.call('world.World.getZoneAt', world, b.field(c, 'x'), b.field(c, 'y')))
    fb.op('JNull', reg=z, offset='f_w')
    o_.attr(z, ATTR_OPBLOCK, 'f_w')
    fb.op('Add', dst=tot, a=mpow, b=hpow)
    fb.op('JSLt', a=tot, b=b.const('f64', OPS_BIGFIGHT), offset='f_w')
    # our fight retreat's balance there (rules/heal.py, < OPS_WZB_T s old): `rv` <= RETREAT = leaving anyway
    # (Harkonnen's Sleeper + Drugs at Ayn-tar 43:34 / 58:28 went out while it read 0.20-0.35 and retreated)
    rv = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=rv, src=b.const('f64', 99))
    wbt = b.call('haxe.ds.ObjectMap.get', _fac_map(fb, b, cx, 'wzbt', fac), fb.dyn(wz))
    fb.op('JNull', reg=wbt, offset='f_rv')
    fb.op('SafeCast', dst=q, src=wbt)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSGt', a=q, b=b.const('f64', OPS_WZB_T), offset='f_rv')
    wbv = b.call('haxe.ds.ObjectMap.get', _fac_map(fb, b, cx, 'wzbv', fac), fb.dyn(wz))
    fb.op('JNull', reg=wbv, offset='f_rv')
    fb.op('SafeCast', dst=rv, src=wbv)
    fb.label('f_rv')
    # Smugglers' Extraction Network on a fight our retreat check is leaving (rv <= RETREAT) next to a village far
    # from our land: the armies there walk into its circle (radius EXTRACT_R) and are taken home instead of fleeing
    # under fire (the siege trigger 1 needs a balance below OPS_EXTRACT_B the retreat never lets a fight reach)
    is_kind('Smugglers', 'f_xn')
    fb.op('JSGt', a=rv, b=_ratio(fb, b, RETREAT), offset='f_xn')
    mxf = o_.held(lst, 'MSmugglingOperation', 'f_xn')
    xvz = b.call('ent.Zone.getVillage', z)
    fb.op('JNull', reg=xvz, offset='f_xn')
    fb.op('JNull', reg=oa, offset='f_xn')
    fb.op('JSLte', a=b.field(oa, 'length'), b=b.const('i32', 0), offset='f_xn')
    xa0 = b.cast(b.call('hl.types.ArrayObj.getDyn', oa, b.const('i32', 0)), 'ent.Army')
    fb.op('JNull', reg=xa0, offset='f_xn')
    xa0e = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=xa0e, src=xa0)
    fb.op('Call2', dst=d, fun=land, arg0=fac, arg1=xa0e)
    fb.op('JSLt', a=d, b=b.const('f64', OPS_EXTRACT_LAND), offset='f_xn')
    xve = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=xve, src=xvz)
    xvx, xvy = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=xvx, src=b.field(xve, 'posx'))
    fb.op('Mov', dst=xvy, src=b.field(xve, 'posy'))
    # worth it only for armies that would use the circle (user: cast for one S_Trooper at 91% walking home, 100 from
    # Ayn-Al'dalus): our armies of the fight still fighting within 3 x EXTRACT_R of the village, at least
    # OPS_EXTRACT_MIN power together
    xu = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=xu, src=b.const('f64', 0))
    jx0 = fb.reg(cx.t('i32'))
    xu0 = _army_loop(fb, b, oa, b.field(oa, 'length'), jx0, 'f_xu', 'f_xud')
    xu0e = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=xu0e, src=xu0)
    fb.op('JFalse', cond=b.call('ent.Entity.isFighting', xu0e), offset='f_xu')
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', xu0e, xve), b=b.const('f64', 3 * EXTRACT_R), offset='f_xu')
    xup = fb.reg(cx.t('f64'))
    fb.op('Call1', dst=xup, fun=pw, arg0=xu0)
    fb.op('Add', dst=xu, a=xu, b=xup)
    fb.op('JAlways', offset='f_xu')
    fb.label('f_xud')
    fb.op('JSLt', a=xu, b=b.const('f64', OPS_EXTRACT_MIN), offset='f_xn')
    o_.cast('MSmugglingOperation', mxf, 'flee', 'f_xn', zone=z, extra=[('B%', rv), ('M', mpow), ('H', hpow), ('U', xu)])
    jx = fb.reg(cx.t('i32'))
    xx = _army_loop(fb, b, oa, b.field(oa, 'length'), jx, 'f_xa', 'f_cast')
    xxe = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=xxe, src=xx)
    fb.op('JSGt', a=b.call('ent.Entity.getDistTo', xxe, xve), b=b.const('f64', 3 * EXTRACT_R), offset='f_xa')
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', xxe, xve), b=b.const('f64', EXTRACT_R - 6), offset='f_xa')
    _move_to(fb, b, cx, xx, xvx, xvy, fac)
    fb.op('JAlways', offset='f_xa')
    fb.label('f_xn')
    # Fremen's Hiding Tracks to break off a fight our retreat check is leaving: the pursuers lose sight of the
    # fleeing armies (Fremen's Annex of Shano 29:21: 7 armies died running from Harkonnen's relief, 412k)
    is_kind('Fremen', 'f_hn')
    fb.op('JSGt', a=rv, b=_ratio(fb, b, RETREAT), offset='f_hn')
    mhe = o_.held(lst, 'MSandCloak', 'f_hn')
    o_.cast('MSandCloak', mhe, 'escape', 'f_hn', zone=z, extra=[('B%', rv), ('M', mpow), ('H', hpow)])
    fb.op('JAlways', offset='f_cast')
    fb.label('f_hn')
    fb.op('Mul', dst=q, a=rv, b=_ratio(fb, b, OPS_BOLD_K))
    fb.op('JSLte', a=q, b=_ratio(fb, b, RETREAT), offset='f_w')  # even bold would leave
    # B = ours / theirs from what we see (getWarzonePowerBalance reads 1.0 when it finds no enemy power)
    fb.op('JSLt', a=hpow, b=b.const('f64', OPS_FIGHT_H), offset='f_w')
    fb.op('SDiv', dst=bal, a=mpow, b=hpow)
    fb.op('JSLt', a=bal, b=_ratio(fb, b, OPS_B_LO), offset='f_w')
    fb.op('JSGt', a=bal, b=_ratio(fb, b, OPS_B_HI), offset='f_sm')  # lopsided: no combat op, Scavenger may pay
    ext = [('B%', bal), ('M', mpow), ('H', hpow)]
    # Harkonnen: Sleeper + Drugs (>= 2 armies of ours), Drugs alone in a close fight
    is_kind('Harkonnen', 'f_hk')
    fb.op('JSLt', a=nours, b=b.const('i32', 2), offset='f_hk')
    msl = o_.held(lst, 'MSleeperAgents', 'f_drug')
    o_.cast('MSleeperAgents', msl, 'fight', 'f_drug', zone=z, extra=ext)
    md2 = o_.held(lst, 'MCombatDrugs', 'f_cast')
    o_.cast('MCombatDrugs', md2, 'combo', 'f_cast', zone=z, extra=ext)
    fb.op('JAlways', offset='f_cast')
    fb.label('f_drug')
    md = o_.held(lst, 'MCombatDrugs', 'f_hk')
    fb.op('JSGt', a=bal, b=_ratio(fb, b, OPS_DRUG_HI), offset='f_hk')
    o_.cast('MCombatDrugs', md, 'fight', 'f_hk', zone=z, extra=ext)
    fb.op('JAlways', offset='f_cast')
    fb.label('f_hk')
    fb.op('JSLte', a=rv, b=_ratio(fb, b, RETREAT), offset='f_w')  # the rest don't hold a fight
    # Fremen: Hiding Tracks
    is_kind('Fremen', 'f_fr')
    mh = o_.held(lst, 'MSandCloak', 'f_fr')
    o_.cast('MSandCloak', mh, 'fight', 'f_fr', zone=z, extra=ext)
    fb.op('JAlways', offset='f_cast')
    fb.label('f_fr')
    # Smugglers: Comm Jamming on an enemy op there, Poison the Reserves on supply-losing enemies
    is_kind('Smugglers', 'f_sm')
    mj = o_.held(lst, 'MCommunicationJamming', 'f_po')
    # only on JAM_MIN_OPS enemy ops there at once, or an Orbital Strike (user: the jam is expensive, never for one
    # op; Cease Fire is jammed below)
    o_.ztrait(z, 'OrbitalStrike', 'f_jam')
    jn = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=jn, src=b.const('i32', 0))
    for tid in ('TCombatDrugs', 'TSleeperAgents', 'TFremenHiddingTracks', 'TToxicVapors'):
        jy, jx = _uid('jy'), _uid('jx')
        o_.ztrait(z, tid, jy)
        fb.op('JAlways', offset=jx)
        fb.label(jy)
        fb.op('Incr', dst=jn)
        fb.label(jx)
    fb.op('JSGte', a=jn, b=b.const('i32', JAM_MIN_OPS), offset='f_jam')
    fb.op('JAlways', offset='f_po')
    fb.label('f_jam')
    # cost: our own drop there (removed by the jam) while it runs
    sdv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'sdz'), fb.dyn(z))
    fb.op('JNull', reg=sdv, offset='f_jc')
    fb.op('SafeCast', dst=q, src=sdv)
    fb.op('JSGt', a=q, b=t, offset='f_po')
    fb.label('f_jc')
    o_.cast('MCommunicationJamming', mj, 'counter', 'f_po', zone=z, extra=ext)
    fb.op('JAlways', offset='f_cast')
    fb.label('f_po')
    mpo = o_.held(lst, 'MPoisonReserves', 'f_sm')
    fb.op('JSLt', a=nlose, b=b.const('i32', 2), offset='f_sm')
    o_.cast('MPoisonReserves', mpo, 'supply', 'f_sm', zone=z, extra=ext)
    fb.op('JAlways', offset='f_cast')
    fb.label('f_sm')
    # anyone: Scavenger Team on a won-ish big fight
    msc = o_.held(lst, 'MScavengerTeam', 'f_w')
    fb.op('JSLt', a=bal, b=_ratio(fb, b, OPS_SCAV_B), offset='f_w')
    fb.op('JSLt', a=hpow, b=b.const('f64', OPS_SCAV_H), offset='f_w')  # their dead must be worth it
    o_.cast('MScavengerTeam', msc, 'fight', 'f_w', zone=z, extra=ext)
    fb.op('JAlways', offset='f_cast')
    fb.op('JAlways', offset='f_w')
    fb.label('f_cast')
    fb.op('Bool', dst=casted, value=True)
    fb.label('f_end')
    fb.end_try(g)
    fb.op('JTrue', cond=casted, offset='end')

    # ---- 5 sieges
    g = fb.try_()
    order_loop('s_o', 's_end', REGROUP, ACTION)
    # Smugglers: a Cease Fire on our target -> jam it (removes every op trait there; ours too: no drop of ours there)
    is_kind('Smugglers', 's_cf')
    o_.attr(z, ATTR_NOFIGHT, 's_jam')
    fb.op('JAlways', offset='s_cf')
    fb.label('s_jam')
    mj2 = o_.held(lst, 'MCommunicationJamming', 's_cf')
    o_.cast('MCommunicationJamming', mj2, 'ceasefire', 's_cf', zone=z, extra=[('s', se)])
    fb.op('JAlways', offset='s_cast')
    fb.label('s_cf')
    o_.attr(z, ATTR_OPBLOCK, 's_o')
    # sietch / renegade base in Action: Scavenger Team (+ Harkonnen Combat Drugs)
    fb.op('JSLt', a=ph, b=b.const('i32', ACTION), offset='s_ns')
    _strong_site(fb, b, s, 's_site')
    fb.op('JAlways', offset='s_ns')
    fb.label('s_site')
    msc2 = o_.held(lst, 'MScavengerTeam', 's_dr')
    o_.cast('MScavengerTeam', msc2, 'pillage', 's_dr', zone=z, extra=[('s', se)])
    fb.op('Bool', dst=casted, value=True)
    fb.label('s_dr')
    is_kind('Harkonnen', 's_hd')
    md3 = o_.held(lst, 'MCombatDrugs', 's_hd')
    # Drugs only on a garrison fight we are winning (no regen: a long losing fight only dies faster)
    order_power(mpow, ENGAGE_R)
    their_side(hpow)
    fb.op('Mul', dst=q, a=hpow, b=_ratio(fb, b, OPS_DRUG_SITE))
    fb.op('JSLt', a=mpow, b=q, offset='s_hd')
    o_.cast('MCombatDrugs', md3, 'pillage', 's_hd', zone=z, extra=[('s', se)])
    fb.op('JAlways', offset='s_cast')
    fb.label('s_hd')
    fb.op('JTrue', cond=casted, offset='s_cast')
    fb.op('JAlways', offset='s_o')  # a sietch / renegade base: nothing else applies
    fb.label('s_ns')
    # an at-war village
    so = b.call('ent.Entity.get_owner', se)
    fb.op('JNull', reg=so, offset='s_o')
    fb.op('JEq', a=so, b=fac, offset='s_o')
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', state, fac, so), offset='s_o')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', s), offset='s_o')  # main base: reserved (base kill)
    # Awaken the People (Fremen) from Regroup
    is_kind('Fremen', 's_aw')
    maw = o_.held(lst, 'MAwakePeople', 's_aw')
    # a distraction, like vanilla's order case: never on our target (a revolt there cancelled our own Liberate of
    # Hadak 1 s after the cast, twice), on another village of its owner >= AWAKE_HOPS zones from it (nearest such),
    # surveyed by us: its defenders turn to the revolt
    sdist = b.call('ent.Zone.calcDistanceFrom', z)
    fb.op('JNull', reg=sdist, offset='s_aw')
    osts = b.cast(fb.get(so, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=osts, offset='s_aw')
    av = fb.reg(cx.t('ent.Structure'))
    fb.op('Null', dst=av)
    abd, adz, ai_, azid = (fb.reg(cx.t('i32')) for _ in range(4))
    fb.op('Mov', dst=abd, src=b.const('i32', 999))
    fb.op('Mov', dst=ai_, src=b.const('i32', 0))
    b.loop_head('s_awl')
    fb.op('JSGte', a=ai_, b=b.field(osts, 'length'), offset='s_awd')
    vv = b.cast(b.call('hl.types.ArrayObj.getDyn', osts, ai_), 'ent.Structure')
    fb.op('Incr', dst=ai_)
    fb.op('JNull', reg=vv, offset='s_awl')
    fb.op('JEq', a=vv, b=s, offset='s_awl')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', vv), offset='s_awl')
    fb.op('JFalse', cond=b.call('ent.Structure.isReconnedFaction', vv, fac), offset='s_awl')
    fb.op('JTrue', cond=b.call('ent.Structure.isRebelling', vv), offset='s_awl')  # opfail AlreadyRebelling
    vve = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=vve, src=vv)
    vz2 = b.call('ent.Entity.get_zone', vve)
    fb.op('JNull', reg=vz2, offset='s_awl')
    fb.op('JNotEq', a=b.field(vz2, 'owner'), b=so, offset='s_awl')  # its own village (not a guest HQ)
    fb.op('Mov', dst=azid, src=b.field(vz2, 'id'))
    fb.op('JSGte', a=azid, b=b.field(sdist, 'length'), offset='s_awl')
    fb.op('JSLt', a=azid, b=b.const('i32', 0), offset='s_awl')
    fb.op('SafeCast', dst=adz, src=b.call('hl.types.ArrayBytes_Int.getDyn', sdist, azid))
    fb.op('JSLt', a=adz, b=b.const('i32', AWAKE_HOPS), offset='s_awl')
    fb.op('JSGte', a=adz, b=abd, offset='s_awl')
    fb.op('Mov', dst=abd, src=adz)
    fb.op('Mov', dst=av, src=vv)
    fb.op('JAlways', offset='s_awl')
    fb.label('s_awd')
    fb.op('JNull', reg=av, offset='s_aw')
    o_.cast('MAwakePeople', maw, 'distract', 's_aw', struct=av, extra=[('tgt', se)])
    fb.op('JAlways', offset='s_cast')
    fb.label('s_aw')
    # Defense Sabotage at Engage / Action: its turrets a large share of its side
    fb.op('JSLt', a=ph, b=b.const('i32', ENGAGE), offset='s_o')
    mgs = o_.held(lst, 'MGearSabotage', 's_o')
    fb.op('CallN', dst=q, fun=cover, args=[fac, se, nul_e, fno, nul_arr])
    fb.op('JSLte', a=q, b=zero, offset='s_o')
    their_side(hpow)
    fb.op('Mul', dst=d, a=hpow, b=_ratio(fb, b, OPS_SAB_SHARE))
    fb.op('JSLt', a=q, b=d, offset='s_o')
    o_.cast('MGearSabotage', mgs, 'turrets', 's_o', zone=z, extra=[('s', se), ('T', q), ('H', hpow)])
    fb.op('JAlways', offset='s_o')
    fb.label('s_cast')
    fb.op('Bool', dst=casted, value=True)
    fb.label('s_end')
    fb.end_try(g)

    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()


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


# agent steer: the infiltration categories each loadout needs (mission requiredLevels), in want order
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
    # opening (user): the first AG_AUTH_N agents go to Arrakis (IField: +1 Authority each) before any loadout
    # category, so early Authority buys more villages; every faction
    fb.label('auth')
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
