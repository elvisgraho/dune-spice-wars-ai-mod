"""Economy buildout (user: the AI decides badly what to build; resources drop for a while (Harkonnen rebellions,
Landsraad resolutions, revolts) and it must not panic over it).

- `econ-score` (score wrapper on the scoring closure's getBuildingStructureScore chain, between wonder-steer and
  spice-first): a pair whose build stalled at that village (`bstall` below) scores NaN until its ban ends; a producer
  of a valued resource (value_table: flat / per-wind production from the data in effect) scores + ECON_K x (output x
  quirk factor x value - upkeep x value), value from RES_VALUE (docs/ARCHITECTURE-PLAN.md step 3: a resource in
  surplus is worth ~0, a short one ~2 x its base; RES_SOFT: Water's need above a net 18 / day counts x 0.3);
  Water Extractor + WX_BONUS on top (user: always, after turret and airfield); a per-wind water producer below WATER_EFF
  water per Solari upkeep at its village's wind is NaN while net water >= 18 (why weakwater). NaN stays NaN. Logs `esteer` (s, k, sc vanilla, why, new) once per village per 60 s.
- `water-rank` (same wrapper, per-wind water producers: Dew Collector, Fremen Wind Trap; user: water in the best-wind
  villages first, and the 2-3 low-wind villages next to the main base still get some): while net water < WATER_NEED
  25, + WFIRST_W x q at an open village (< WPER_VIL of them there, buildable without a demolition) whose wind is the
  best among our open villages, else + WMB_W x q at an open village next to our main base (getDistanceToPlayerBase 1)
  while >= WMB_MIN of ours are; q = 1 below 18 net, fading to 0 at 25. Such main-base neighbours are exempt from
  weakwater while net water < 25. Logs `wrank` (s, k, w wind, best, mb, wat net, sc vanilla, b bonus, new) once per
  village per 60 s.
- `bres` / `bstall`: the checkAddUpgrade call in BuildingManager.checkBuildings (the picked pair) -> wrapper: per
  village (Upgrades) the picked k and since when it has been refused (maps `bstk` / `bsts`; Success clears them); the
  same k refused for BSTALL_T s (BSTALL_RES_T while only resources are missing: saving is fine for a while) is banned
  there for BSTALL_BAN s (maps `bstb` until, `bstbk` k): vanilla re-picked one pair every ~30 s for 30-60 min while
  nothing else went up there (Atreides' Listening Post at Al-mur 52x 24:02-61:54, Fremen's Plascrete Factory at
  Tuo-Al'nit 50x, match 2026-10-23 18:17). Logs `bres` (s, k, r result name index) per village per 60 s, `bstall`
  (s, k, r, for s).
- `demo-gate`: the compareGoals call in BuildingManager.regularUpdate (vanilla demolishes the first aiRelatedBuildings
  building of a resource at a random village every 15 s while its net rate AND stock are above goal (= 2)) ->
  wrapper: 2 only once that has held for DEMO_HOLD s (maps `dsur` ResourceManager -> StringMap res -> since; one
  demolition per DEMO_HOLD), else 1; never for Manpower (its building is the Recruitment Office: the army is always
  at the CP cap, user rule). A dip in upkeep (an army lost) made a surplus for seconds. Logs `dsur` (res).
- `goal-smooth`: the compareGoals call in HScoring.prepareContext (over / under-producing resources: building scores
  -2 / +6 for their aiRelatedBuildings) -> wrapper: an exponential average of vanilla's result per resource
  (GOAL_TAU s; maps `gsm` / `gst` ResourceManager -> StringMap res -> average / time), rounded half away from 0: a
  production drop must last ~GOAL_TAU s before the buildout turns towards that resource, and a short surplus doesn't
  push it away (vanilla flips on any one reading).
- plascrete (user: vanilla builds plascrete factories until +100 / day and more): the value model prices it out once
  plascrete is plentiful (a quirk village's factor still counts); `pcdump` (late game, stock >= PC_DUMP): one factory
  without a quirk leaves a full village per PC_DUMP_T s; vanilla's own Plascrete surplus demolition (random village,
  quirks too) is off.
  *Unverified:* quirks that convert plascrete into Solari etc. aren't seen by the upgrade factor.
- faction buildings (FACTION_BUILD, strategy docs: Bazaar, Al-Gaib Temple, Council Chamber, Interrogation Center,
  Black Market Branch from BMB_HQS Underworld HQs, Office of Order: 2 x on a spice / special village, elsewhere
  while net Solari > 0) + FACTION_W where
  checkAddUpgrade allows it without a demolition (`esteer` why faction); Nuclear Silo NaN (why nuke).
- Manpower (user: +4 / +11 a day can't rebuild a wiped army): its RES_VALUE target 20 / day and bank 300 price
  Recruitment Offices up while short; vanilla's Manpower goals stay (raising them would starve crews / militia).
Fails safe: every wrapper returns vanilla's value on error."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.build import _nan_f, _write_names

WX_BONUS = 50       # Water Extractor + this (user: always, after the turret / airfield bonuses of 100)
BSTALL_T = 120      # s: the same picked building refused at a village this long is banned there ...
BSTALL_RES_T = 300  # ... this long while only resources are missing (saving for it)
BSTALL_BAN = 300    # s: ban length
DEMO_HOLD = 300     # s: vanilla's surplus demolition only after the surplus held this long, then one per this
GOAL_TAU = 120      # s: averaging time of the over / under-producing goal readings used by building scores
PC_BUILD = ('PlascreteFactory', 'SIHiddenPlascreteFactory')  # resource Plascrete aiRelatedBuildings
PC_DUMP = 2500      # plascrete stock: from here a plascrete factory without a quirk is removed from a full village ...
PC_DUMP_T = 300     # ... one per this many s per faction (user: late game, make room for other buildings)
FACTION_BUILD = ('Main_Bazaar', 'Main_Temple', 'Main_CouncilChamber', 'Main_InterrogationCenter',
                 'Main_BlackMarketBranch', 'OppressionHeadquarter')  # faction buildings the strategy docs rate
FACTION_W = 15      # ... + this where one can go up without a demolition (user: faction buildings never got built:
                    # 0 of these in match 2026-10-23 20:41 but Smugglers' Black Market Branch at 63 min)
BMB_HQS = 3         # Black Market Branch (+1% spice / plascrete / manpower / intel per Underworld HQ): from this many HQs
NUKE = ('NuclearSilo',)  # never: NukeTargeting is aiProhibited for Economy / Military / Statecraft AIs (3000 spent
                         # for nothing; Harkonnen picked it at 5 villages, Smugglers 3)
# Economy value model (docs/ARCHITECTURE-PLAN.md step 3): resource -> (base worth per unit in Solari terms, target net
# rate per day, target stock or 0). value = base x max(0, 1 + need); need = clamp((target - net) / target, -1, 1)
# + BANK_W x (bank - stock) / bank while below the bank. A producer's score + ECON_K x (output x quirk factor x value
# - upkeep at the current values): a resource in surplus is worth ~0 (no more water / plascrete buildings), a short
# one ~2 x base (Manpower at +4 / +11 with nothing banked: user; Solari upkeep counts as Solari gets short)
RES_SOFT = {'Water': (18, 0.3)}  # resource -> (floor, weight): at or above the floor net rate / day the need towards
                                 # the target counts only x weight (user: 25 water is a good target, but many play the
                                 # whole game on 18 or less: below 18 it is urgent, 18-25 a mild want)
WATER_EFF = 1.0     # a per-wind water producer making less water / day than this x its Solari upkeep (Dew Collector
                    # at wind 2: 2 for 4) is dropped (NaN, log `esteer` why weakwater) while net water >= the floor
WATER_NEED = 25     # net water / day below which per-wind water buildings (Dew Collector, Wind Trap) are steered:
WFIRST_W = 20       # + this x q at an open village with the best wind among our open villages (user: water in the
                    # best-wind villages first; q = 1 below RES_SOFT's floor 18, fading to 0 at WATER_NEED) ...
WMB_W = 10          # ... else + this x q at a village next to our main base while >= WMB_MIN of ours are (user: the
WMB_MIN = 2         # 2-3 low-wind villages around the base got none; Insulated Valley later helps wind <= 2), and
                    # weakwater doesn't drop it there while net water < WATER_NEED
WBUSY = ('ConstructionInProgress', 'UpgradeInProgress', 'SameConstructionInProgress')  # open while busy
WPER_VIL = 3        # open = fewer than this many per-wind water buildings there and one can go up without a demolition
WBEST_T = 5         # s: per-faction cache of the best open wind / main-base neighbour count
RES_VALUE = {'Solari': (1, 150, 2000), 'Plascrete': (2, 30, 500), 'Manpower': (12, 20, 300), 'Water': (4, 25, 0),
             'Knowledge': (25, 20, 0), 'Influence': (20, 4, 50), 'Intel': (6, 6, 200), 'FuelCell': (6, 15, 0)}
RES_GATE = {'FuelCell': 'dfuel'}  # valued only for a faction whose doctrine style fields fuel units (rules/doctrine.py
                                  # map `dfuel`); else 0, and a building making only it keeps vanilla's score
BANK_W = 0.5        # stock shortfall weight in need
ECON_K = 1.0        # value -> score units (vanilla building scores ~10-40)
PROD_REFS = ('TRes_Prod_Flat', 'TRes_ProdPerRegionWind_Flat')
NO_DEMO = ('Manpower', 'Plascrete')  # vanilla surplus demolition off (Recruitment Office: army at the CP cap;
                                     # plascrete: `pcdump` keeps the quirk villages' factories)


def _is(fb, b, ks, ids, yes):
    for i in ids:
        fb.op('JEq', a=b.call('String.__compare', ks, fb.dyn(fb.string(i))), b=b.const('i32', 0), offset=yes)


def _can_add(fb, b, cx, up, ks, extra=()):
    """Bool register: Upgrades.checkAddUpgrade(up, ks) is Success, MissingResources, TRANSIENT or one of `extra`
    (no demolition)."""
    ca = cx.fn('logic.Upgrades.checkAddUpgrade')
    cat = [a.value for a in cx.code.types[ca.type.value].definition.args]
    cret = cx.code.types[ca.type.value].definition.ret.value
    rnames = [c_.name.resolve(cx.code) for c_ in cx.code.types[cret].definition.constructs]
    dref = fb.reg(cat[2])
    fb.op('Ref', dst=dref, src=b.const('i32', 0))
    cnul = []
    for t_ in cat[3:]:
        r_ = fb.reg(t_)
        fb.op('Null', dst=r_)
        cnul.append(r_)
    rr = fb.reg(cret)
    fb.op('CallN', dst=rr, fun=ca.findex.value, args=[up, ks, dref] + cnul)
    ri = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ri, value=rr)
    ok = fb.reg(cx.t('bool'))
    u = _uid('ca')
    fb.op('Bool', dst=ok, value=True)
    for nm in ('Success', 'MissingResources') + TRANSIENT + tuple(extra):
        fb.op('JEq', a=ri, b=b.const('i32', rnames.index(nm)), offset=u)
    fb.op('Bool', dst=ok, value=False)
    fb.label(u)
    return ok


def _wind(fb, b, cx, z, dst):
    """dst (f64) = zone z's windForce (z non-null)."""
    wf = b.field(z, 'windForce')
    if fb.regs[wf] != cx.t('f64'):
        fb.op('ToSFloat', dst=dst, src=wf)
    else:
        fb.op('Mov', dst=dst, src=wf)


def _wopen(fb, b, cx, up, ks, no):
    """Jump to `no` unless village upgrades `up` (non-null) holds < WPER_VIL of ks and ks can go up there now or
    once paid (no demolition)."""
    gkc = cx.fn('logic.Upgrades.getKindCount')
    nref = fb.reg(cx.code.types[gkc.type.value].definition.args[2].value)
    fb.op('Null', dst=nref)
    n = fb.reg(cx.t('i32'))
    fb.op('Call3', dst=n, fun=gkc.findex.value, arg0=up, arg1=ks, arg2=nref)
    fb.op('JSGte', a=n, b=b.const('i32', WPER_VIL), offset=no)
    # busy building now is still open (at any moment most villages were mid-construction, so the best open wind read
    # 2 or none (-1) and every candidate counted as best: no wind steering at all, match 2026-10-24 22:3x)
    fb.op('JFalse', cond=_can_add(fb, b, cx, up, ks, WBUSY), offset=no)


def _wcache(fb, b, cx, t, ks):
    """(best, nmb) f64 registers for faction reg 1 and per-wind water building ks: the best windForce among our open
    villages (-1: none) and how many of our villages lie next to our main base (getDistanceToPlayerBase 1). Cached
    per faction for WBEST_T s (maps `wct` / `wcw` / `wcm`; one per-wind water kind per faction: Fremen Wind Trap,
    the others Dew Collector)."""
    best, nmb, w, tf = (fb.reg(cx.t('f64')) for _ in range(4))
    u = _uid('wc')
    mt, mw, mm = (_global_map(fb, b, cx, n) for n in ('wct', 'wcw', 'wcm'))
    fk = fb.dyn(1)
    tv = b.call('haxe.ds.ObjectMap.get', mt, fk)
    fb.op('JNull', reg=tv, offset=u + 'c')
    fb.op('SafeCast', dst=tf, src=tv)
    fb.op('Sub', dst=tf, a=t, b=tf)
    fb.op('JSGte', a=tf, b=b.const('f64', WBEST_T), offset=u + 'c')
    fb.op('JSLt', a=tf, b=b.const('f64', 0), offset=u + 'c')
    fb.op('SafeCast', dst=best, src=b.call('haxe.ds.ObjectMap.get', mw, fk))
    fb.op('SafeCast', dst=nmb, src=b.call('haxe.ds.ObjectMap.get', mm, fk))
    fb.op('JAlways', offset=u + 'd')
    fb.label(u + 'c')
    fb.op('Mov', dst=best, src=b.const('f64', -1))
    fb.op('Mov', dst=nmb, src=b.const('f64', 0))
    gdb = cx.fn('ent.Zone.getDistanceToPlayerBase')
    gnull = fb.reg(cx.code.types[gdb.type.value].definition.args[2].value)
    fb.op('Null', dst=gnull)
    hops = fb.reg(cx.t('i32'))
    ss = b.cast(fb.get(1, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=ss, offset=u + 'p')
    i = fb.reg(cx.t('i32'))
    ve = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head(u + 'l')
    fb.op('JSGte', a=i, b=b.field(ss, 'length'), offset=u + 'p')
    st = b.cast(b.call('hl.types.ArrayObj.getDyn', ss, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=st, offset=u + 'l')
    sk = fb.get(st, 'kind')
    fb.op('JNull', reg=sk, offset=u + 'l')
    sks = b.cast(sk, 'String')
    for vk in ('Village', 'VillageFortified'):
        fb.op('JEq', a=b.call('String.__compare', sks, fb.dyn(fb.string(vk))), b=b.const('i32', 0), offset=u + 'v')
    fb.op('JAlways', offset=u + 'l')
    fb.label(u + 'v')
    fb.op('Mov', dst=ve, src=st)
    z = b.call('ent.Entity.get_zone', ve)
    fb.op('JNull', reg=z, offset=u + 'l')
    fb.op('Call3', dst=hops, fun=gdb.findex.value, arg0=z, arg1=1, arg2=gnull)
    fb.op('JNotEq', a=hops, b=b.const('i32', 1), offset=u + 'nb')
    fb.op('Add', dst=nmb, a=nmb, b=b.const('f64', 1))
    fb.label(u + 'nb')
    up = b.field(st, 'upgrades')
    fb.op('JNull', reg=up, offset=u + 'l')
    _wopen(fb, b, cx, up, ks, u + 'l')
    _wind(fb, b, cx, z, w)
    fb.op('JSLte', a=w, b=best, offset=u + 'l')
    fb.op('Mov', dst=best, src=w)
    fb.op('JAlways', offset=u + 'l')
    fb.label(u + 'p')
    b.call('haxe.ds.ObjectMap.set', mt, fk, fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', mw, fk, fb.dyn(best))
    b.call('haxe.ds.ObjectMap.set', mm, fk, fb.dyn(nmb))
    fb.label(u + 'd')
    return best, nmb


def _wvillage(fb, b, cx, s, z, ks, nmb):
    """(mb, open) Bool registers for village s (ent.Structure) in zone z (may be null), faction reg 1: mb = s lies next
    to our main base while >= WMB_MIN of our villages do (nmb); open = _wopen."""
    mb, op = fb.reg(cx.t('bool')), fb.reg(cx.t('bool'))
    u = _uid('wv')
    fb.op('Bool', dst=mb, value=False)
    fb.op('Bool', dst=op, value=False)
    fb.op('JNull', reg=z, offset=u + 'o')
    fb.op('JSLt', a=nmb, b=b.const('f64', WMB_MIN), offset=u + 'o')
    gdb = cx.fn('ent.Zone.getDistanceToPlayerBase')
    gnull = fb.reg(cx.code.types[gdb.type.value].definition.args[2].value)
    fb.op('Null', dst=gnull)
    hops = fb.reg(cx.t('i32'))
    fb.op('Call3', dst=hops, fun=gdb.findex.value, arg0=z, arg1=1, arg2=gnull)
    fb.op('JNotEq', a=hops, b=b.const('i32', 1), offset=u + 'o')
    fb.op('Bool', dst=mb, value=True)
    fb.label(u + 'o')
    up = b.field(s, 'upgrades')
    fb.op('JNull', reg=up, offset=u + 'd')
    _wopen(fb, b, cx, up, ks, u + 'd')
    fb.op('Bool', dst=op, value=True)
    fb.label(u + 'd')
    return mb, op


def value_table():
    """{building id: ([(res index, amount, per wind level?)], [(res index, qty)])} for buildings whose first state
    produces a valued resource flat (or per wind level) without a faction condition, from the data in effect."""
    rows = game_rows('resource', False)
    ridx = {r['id']: i for i, r in enumerate(rows)}
    out = {}
    for r in game_rows('building', False):
        st = (r.get('states') or [{}])[0]
        prod = [(ridx[a['target']['resource']], float(a.get('val') or 0), a['ref'] == 'TRes_ProdPerRegionWind_Flat')
                for a in st.get('attributes') or []
                if a.get('ref') in PROD_REFS and not a.get('faction') and (a.get('target') or {}).get('resource') in RES_VALUE]
        if not prod:
            continue
        upk = [(ridx[u['res']], float(u.get('qty') or 0)) for u in st.get('upkeep') or [] if u.get('res') in RES_VALUE]
        out[r['id']] = (prod, upk)
    return out


def _res_value(fb, b, cx, fac, ri, dst):
    """dst = the current value of resource index ri for faction fac (RES_VALUE)."""
    rid = game_rows('resource', False)[ri]['id']
    base, target, bank = RES_VALUE[rid]
    net, need, q = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    u = _uid('rv')
    fb.op('Mov', dst=net, src=b.call('ent.Faction.getCachedResNetProd', fac, b.const('i32', ri)))
    fb.op('Sub', dst=need, a=b.const('f64', target), b=net)
    fb.op('SDiv', dst=need, a=need, b=b.const('f64', target))
    if rid in RES_SOFT:
        flo, w = RES_SOFT[rid]
        fb.op('JSLt', a=net, b=b.const('f64', flo), offset=u + 'sf')
        fb.op('JSLte', a=need, b=b.const('f64', 0), offset=u + 'sf')
        fb.op('Mul', dst=need, a=need, b=_ratio(fb, b, w))
        fb.label(u + 'sf')
    fb.op('JSLte', a=need, b=b.const('f64', 1), offset=u + 'hi')
    fb.op('Mov', dst=need, src=b.const('f64', 1))
    fb.label(u + 'hi')
    fb.op('JSGte', a=need, b=b.const('f64', -1), offset=u + 'lo')
    fb.op('Mov', dst=need, src=b.const('f64', -1))
    fb.label(u + 'lo')
    if bank:
        fb.op('Mov', dst=q, src=b.call('ent.Faction.getResource', fac, b.const('i32', ri)))
        fb.op('JSGte', a=q, b=b.const('f64', bank), offset=u + 'bk')
        fb.op('Sub', dst=q, a=b.const('f64', bank), b=q)
        fb.op('SDiv', dst=q, a=q, b=b.const('f64', bank))
        fb.op('Mul', dst=q, a=q, b=_ratio(fb, b, BANK_W))
        fb.op('Add', dst=need, a=need, b=q)
        fb.label(u + 'bk')
    fb.op('Add', dst=dst, a=need, b=b.const('f64', 1))
    fb.op('JSGte', a=dst, b=b.const('f64', 0), offset=u + 'z')
    fb.op('Mov', dst=dst, src=b.const('f64', 0))
    fb.label(u + 'z')
    fb.op('Mul', dst=dst, a=dst, b=b.const('f64', base))
    if rid in RES_GATE:
        fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, RES_GATE[rid]), fb.dyn(fac)),
              offset=u + 'g')
        fb.op('Mov', dst=dst, src=b.const('f64', 0))
        fb.label(u + 'g')


def build_econ_score(cx, helpers, new_ids, inner):
    orig = cx.fn('logic.ai.$HScoring.getBuildingStructureScore')
    ft = cx.code.types[orig.type.value].definition
    fb = FB(cx, [a.value for a in ft.args], ft.ret.value, fun_type=orig.type.value)
    b = B(fb)
    res = fb.reg(cx.t('f64'))
    fb.op('Call4', dst=res, fun=inner, arg0=0, arg1=1, arg2=2, arg3=3)  # outside the trap
    guard = fb.try_()
    fb.op('JSGte', a=res, b=b.const('f64', -(1 << 30)), offset='real')  # NaN = not buildable: keep it
    fb.op('JAlways', offset='end')
    fb.label('real')
    fb.op('JNull', reg=1, offset='end')
    k = fb.get(0, 'k')
    fb.op('JNull', reg=k, offset='end')
    ks = b.cast(k, 'String')
    so = fb.get(0, 's')
    fb.op('JNull', reg=so, offset='end')
    s = b.cast(so, 'ent.Structure')
    fb.op('JNull', reg=s, offset='end')
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=s)
    v0 = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=v0, src=res)
    why = fb.reg(cx.t('String'))
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    # a stalled pick banned at this village
    up = b.field(s, 'upgrades')
    fb.op('JNull', reg=up, offset='noban')
    bk = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'bstbk'), fb.dyn(up))
    fb.op('JNull', reg=bk, offset='noban')
    fb.op('JNotEq', a=b.call('String.__compare', ks, bk), b=b.const('i32', 0), offset='noban')
    bu = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'bstb'), fb.dyn(up))
    fb.op('JNull', reg=bu, offset='noban')
    until = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=until, src=bu)
    fb.op('JSGte', a=t, b=until, offset='noban')
    fb.op('Mov', dst=why, src=fb.string('stall'))
    fb.op('JAlways', offset='nan')
    fb.label('noban')
    _is(fb, b, ks, FACTION_BUILD, 'fac')
    _is(fb, b, ks, NUKE, 'nuke')
    vt = value_table()
    vids = sorted(vt)
    # the village's zone before the jump table (fetched after it, it was never set: per-wind output counted wind 1
    # and weakwater never fired, matches up to 2026-10-24)
    wz = b.call('ent.Entity.get_zone', se)
    for n_, bid in enumerate(vids):
        fb.op('JEq', a=b.call('String.__compare', ks, fb.dyn(fb.string(bid))), b=b.const('i32', 0), offset=f'vb{n_}')
    fb.op('JAlways', offset='end')
    # the value model: + ECON_K x (output x quirk factor x value - upkeep x value)
    acc, rv, amt, fct = (fb.reg(cx.t('f64')) for _ in range(4))
    for n_, bid in enumerate(vids):
        prod, upk = vt[bid]
        fb.label(f'vb{n_}')
        rids = {game_rows('resource', False)[ri]['id'] for ri, _, _ in prod}
        if rids and rids <= set(RES_GATE):  # only gated outputs, gate closed: vanilla's score unchanged
            for gm in {RES_GATE[r] for r in rids}:
                fb.op('JNull', reg=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, gm), fb.dyn(1)),
                      offset='end')
        fb.op('Mov', dst=acc, src=b.const('f64', 0))
        fb.op('Mov', dst=fct, src=b.const('f64', 1))
        fb.op('JNull', reg=up, offset=f'vf{n_}')
        fb.op('Mov', dst=fct, src=b.call('logic.Upgrades.getUpgradeFactor', up, ks))
        fb.label(f'vf{n_}')
        for ri, a_, wind in prod:
            fb.op('Mov', dst=amt, src=b.const('f64', int(a_)) if a_ == int(a_) else _ratio(fb, b, a_))
            if wind:  # per wind level of the region
                wk = _uid('wk')
                fb.op('JNull', reg=wz, offset=wk)
                wf = b.field(wz, 'windForce')
                if fb.regs[wf] != cx.t('f64'):
                    wff = fb.reg(cx.t('f64'))
                    fb.op('ToSFloat', dst=wff, src=wf)
                    wf = wff
                fb.op('Mul', dst=amt, a=amt, b=wf)
                fb.label(wk)
            fb.op('Mul', dst=amt, a=amt, b=fct)
            _res_value(fb, b, cx, 1, ri, rv)
            fb.op('Mul', dst=amt, a=amt, b=rv)
            fb.op('Add', dst=acc, a=acc, b=amt)
        for ri, qty in upk:
            _res_value(fb, b, cx, 1, ri, rv)
            fb.op('Mul', dst=amt, a=rv, b=b.const('f64', int(qty)) if qty == int(qty) else _ratio(fb, b, qty))
            fb.op('Sub', dst=acc, a=acc, b=amt)
        wprod = [(ri, a_) for ri, a_, wind in prod if wind and game_rows('resource', False)[ri]['id'] == 'Water']
        sol = sum(q_ for ri, q_ in upk if game_rows('resource', False)[ri]['id'] == 'Solari')
        if wprod:
            wri, wa = wprod[0]
            u = _uid('ww')
            wn, wfr, wb = (fb.reg(cx.t('f64')) for _ in range(3))
            fb.op('Mov', dst=wn, src=b.call('ent.Faction.getCachedResNetProd', 1, b.const('i32', wri)))
            fb.op('Mov', dst=wfr, src=b.const('f64', 0))
            fb.op('JNull', reg=wz, offset=u + 'nz')
            _wind(fb, b, cx, wz, wfr)
            fb.label(u + 'nz')
            best, nmb = _wcache(fb, b, cx, t, ks)
            wmb, wopen = _wvillage(fb, b, cx, s, wz, ks, nmb)
            if sol > 0:
                # weak water (user: Atreides built water on a 2-wind village): output / Solari upkeep < WATER_EFF
                # while net water >= RES_SOFT's floor -> dropped; below the floor any water is welcome; a village next
                # to our main base (wmb) is kept while net water < WATER_NEED (user: build there anyway)
                ww = fb.reg(cx.t('f64'))
                fb.op('JSLt', a=wn, b=b.const('f64', RES_SOFT['Water'][0]), offset=u + 'ok')
                fb.op('Mul', dst=ww, a=wfr, b=b.const('f64', int(wa)) if wa == int(wa) else _ratio(fb, b, wa))
                fb.op('Mul', dst=ww, a=ww, b=fct)
                fb.op('JSGte', a=ww, b=_ratio(fb, b, WATER_EFF * sol), offset=u + 'ok')
                fb.op('JFalse', cond=wmb, offset=u + 'weak')
                fb.op('JSLt', a=wn, b=b.const('f64', WATER_NEED), offset=u + 'ok')
                fb.label(u + 'weak')
                fb.op('Mov', dst=why, src=fb.string('weakwater'))
                fb.op('JAlways', offset='nan')
                fb.label(u + 'ok')
            # wind rank (user: water in the best-wind villages first): while net water < WATER_NEED, + WFIRST_W x q at
            # an open village with the best wind among our open ones, else + WMB_W x q next to our main base;
            # q = 1 below RES_SOFT's floor, fading to 0 at WATER_NEED
            fb.op('Mov', dst=wb, src=b.const('f64', 0))
            fb.op('JFalse', cond=wopen, offset=u + 'rd')
            fb.op('JSGte', a=wn, b=b.const('f64', WATER_NEED), offset=u + 'rd')
            q = fb.reg(cx.t('f64'))
            flo = RES_SOFT['Water'][0]
            fb.op('Sub', dst=q, a=b.const('f64', WATER_NEED), b=wn)
            fb.op('SDiv', dst=q, a=q, b=b.const('f64', WATER_NEED - flo))
            fb.op('JSLte', a=q, b=b.const('f64', 1), offset=u + 'q1')
            fb.op('Mov', dst=q, src=b.const('f64', 1))
            fb.label(u + 'q1')
            fb.op('JSLt', a=wfr, b=best, offset=u + 'mb')
            fb.op('Mul', dst=wb, a=q, b=b.const('f64', WFIRST_W))
            fb.op('JAlways', offset=u + 'rd')
            fb.label(u + 'mb')
            fb.op('JFalse', cond=wmb, offset=u + 'rd')
            fb.op('Mul', dst=wb, a=q, b=b.const('f64', WMB_W))
            fb.label(u + 'rd')
        fb.op('Mul', dst=acc, a=acc, b=_ratio(fb, b, ECON_K))
        fb.op('Add', dst=res, a=res, b=acc)
        if bid == 'WaterExtractor':  # user: always, after the turret / airfield
            fb.op('Add', dst=res, a=res, b=b.const('f64', WX_BONUS))
        fb.op('Mov', dst=why, src=fb.string('value'))
        if wprod:
            fb.op('Add', dst=res, a=res, b=wb)
            mbf = fb.reg(cx.t('f64'))
            fb.op('Mov', dst=mbf, src=b.const('f64', 0))
            fb.op('JFalse', cond=wmb, offset=u + 'lg')
            fb.op('Mov', dst=mbf, src=b.const('f64', 1))
            fb.label(u + 'lg')
            _throttle(fb, b, cx, 'wrank', se, 60, 'log')
            _log_ev(fb, b, cx, helpers, 'wrank', [('f', fb.get(1, 'kind')), ('s', se), ('k', ks), ('w', wfr),
                                                  ('best', best), ('mb', mbf), ('wat', wn), ('sc', v0), ('b', wb),
                                                  ('new', res)])
        fb.op('JAlways', offset='log')
    fb.label('nuke')
    fb.op('Mov', dst=why, src=fb.string('nuke'))
    fb.op('JAlways', offset='nan')
    fb.label('fac')
    fb.op('JNull', reg=up, offset='end')
    fb.op('JFalse', cond=_can_add(fb, b, cx, up, ks), offset='end')  # full (a demolition) or not possible: vanilla's
    # Office of Order (user: Harkonnen's economy core, it oppresses its village for free: +100% production): a spice
    # or special village + 2 x FACTION_W; elsewhere + FACTION_W while our net Solari rate is positive (high upkeep)
    fb.op('JNotEq', a=b.call('String.__compare', ks, fb.dyn(fb.string('OppressionHeadquarter'))), b=b.const('i32', 0),
          offset='fbmb')
    oz = b.call('ent.Entity.get_zone', se)
    fb.op('JNull', reg=oz, offset='end')
    fb.op('JTrue', cond=b.call('ent.Zone.hasSpice', oz), offset='ofbig')
    oaw = fb.get(oz, 'inf', 'props', 'aiWeight')
    fb.op('JNull', reg=oaw, offset='ofsol')
    oawf = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=oawf, src=oaw)
    fb.op('JSGte', a=oawf, b=b.const('f64', 20), offset='ofbig')
    fb.label('ofsol')
    fb.op('JSLte', a=b.call('ent.Faction.getCachedResNetProd', 1, b.const('i32', RES_SOLARI)), b=b.const('f64', 0),
          offset='end')
    fb.op('JAlways', offset='fadd')
    fb.label('ofbig')
    fb.op('Add', dst=res, a=res, b=b.const('f64', FACTION_W))
    # Black Market Branch: from BMB_HQS Underworld HQs
    fb.label('fbmb')
    fb.op('JNotEq', a=b.call('String.__compare', ks, fb.dyn(fb.string('Main_BlackMarketBranch'))),
          b=b.const('i32', 0), offset='fadd')
    hn = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=hn, src=b.const('i32', 0))
    hss = b.cast(fb.get(1, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=hss, offset='end')
    hi = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=hi, src=b.const('i32', 0))
    b.loop_head('hq')
    fb.op('JSGte', a=hi, b=b.field(hss, 'length'), offset='hqd')
    hs = b.cast(b.call('hl.types.ArrayObj.getDyn', hss, hi), 'ent.Entity')
    fb.op('Incr', dst=hi)
    fb.op('JNull', reg=hs, offset='hq')
    hk = fb.get(hs, 'kind')
    fb.op('JNull', reg=hk, offset='hq')
    fb.op('JNotEq', a=b.call('String.__compare', b.cast(hk, 'String'), fb.dyn(fb.string('UWHeadquarters'))),
          b=b.const('i32', 0), offset='hq')
    fb.op('Incr', dst=hn)
    fb.op('JAlways', offset='hq')
    fb.label('hqd')
    fb.op('JSLt', a=hn, b=b.const('i32', BMB_HQS), offset='end')
    fb.label('fadd')
    fb.op('Add', dst=res, a=res, b=b.const('f64', FACTION_W))
    fb.op('Mov', dst=why, src=fb.string('faction'))
    fb.op('JAlways', offset='log')
    fb.label('nan')
    fb.op('Mov', dst=res, src=_nan_f(fb, b, cx))
    fb.label('log')
    _throttle(fb, b, cx, 'esteer', se, 60, 'end')
    _log_ev(fb, b, cx, helpers, 'esteer', [('f', fb.get(1, 'kind')), ('s', se), ('k', ks), ('sc', v0), ('why', why),
                                           ('new', res)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    w = fb.build()
    new_ids.add(w)
    return w


def build_bres(cx, helpers, new_ids):
    cau = cx.fn('logic.Upgrades.checkAddUpgrade')
    cb = cx.fn('logic.ai.BuildingManager.checkBuildings')
    sites = [op for op in cb.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == cau.findex.value]
    if len(sites) != 1:
        raise ValueError(f'bres: expected 1 checkAddUpgrade call in checkBuildings, found {len(sites)}')
    ft = cx.code.types[cau.type.value].definition
    args = [a.value for a in ft.args]
    rnames = [c_.name.resolve(cx.code) for c_ in cx.code.types[ft.ret.value].definition.constructs]
    _write_names(rnames)
    fb = FB(cx, args, ft.ret.value, fun_type=cau.type.value)
    b = B(fb)
    r = fb.reg(ft.ret.value)
    fb.op('CallN', dst=r, fun=cau.findex.value, args=list(range(len(args))))  # vanilla, outside the trap
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    ri = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ri, value=r)
    mk, ms = _global_map(fb, b, cx, 'bstk'), _global_map(fb, b, cx, 'bsts')
    up = fb.dyn(0)
    fb.op('JNotEq', a=ri, b=b.const('i32', rnames.index('Success')), offset='fail')
    b.call('haxe.ds.ObjectMap.remove', mk, up)
    b.call('haxe.ds.ObjectMap.remove', ms, up)
    fb.op('JAlways', offset='end')
    fb.label('fail')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    se = b.cast(b.field(0, 'entity'), 'ent.Entity')
    fb.op('JNull', reg=se, offset='end')
    fac = b.call('ent.Entity.get_owner', se)
    fb.op('JNull', reg=fac, offset='end')
    rf = fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=rf, src=ri)
    _throttle(fb, b, cx, 'bres', se, 60, 'blog')
    _log_ev(fb, b, cx, helpers, 'bres', [('f', fb.get(fac, 'kind')), ('s', se), ('k', 1), ('r', rf)])
    fb.label('blog')
    # same k as the record: how long refused; else a new record
    ok_ = b.call('haxe.ds.ObjectMap.get', mk, up)
    fb.op('JNull', reg=ok_, offset='new')
    fb.op('JNotEq', a=b.call('String.__compare', 1, ok_), b=b.const('i32', 0), offset='new')
    sv = b.call('haxe.ds.ObjectMap.get', ms, up)
    fb.op('JNull', reg=sv, offset='new')
    since, el, lim = (fb.reg(cx.t('f64')) for _ in range(3))
    fb.op('SafeCast', dst=since, src=sv)
    fb.op('Sub', dst=el, a=t, b=since)
    fb.op('Mov', dst=lim, src=b.const('f64', BSTALL_T))
    fb.op('JNotEq', a=ri, b=b.const('i32', rnames.index('MissingResources')), offset='lim')
    fb.op('Mov', dst=lim, src=b.const('f64', BSTALL_RES_T))
    fb.label('lim')
    fb.op('JSLt', a=el, b=lim, offset='end')
    # stalled: banned at this village for BSTALL_BAN, the record restarts
    q = fb.reg(cx.t('f64'))
    fb.op('Add', dst=q, a=t, b=b.const('f64', BSTALL_BAN))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'bstb'), up, fb.dyn(q))
    b.call('haxe.ds.ObjectMap.set', _global_map(fb, b, cx, 'bstbk'), up, fb.dyn(1))
    b.call('haxe.ds.ObjectMap.remove', mk, up)
    b.call('haxe.ds.ObjectMap.remove', ms, up)
    _log_ev(fb, b, cx, helpers, 'bstall', [('f', fb.get(fac, 'kind')), ('s', se), ('k', 1), ('r', rf), ('for', el)])
    fb.op('JAlways', offset='end')
    fb.label('new')
    b.call('haxe.ds.ObjectMap.set', mk, up, fb.dyn(1))
    b.call('haxe.ds.ObjectMap.set', ms, up, fb.dyn(t))
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=r)
    w = fb.build()
    new_ids.add(w)
    sites[0].df['fun'].value = w
    return {'bres': 1}


def _sub_map(fb, b, cx, name, key):
    """StringMap stored under `key` in global ObjectMap `name` (created on first use)."""
    gm = _global_map(fb, b, cx, name)
    sm = fb.reg(cx.t('haxe.ds.StringMap'))
    u = _uid('sm')
    got = b.call('haxe.ds.ObjectMap.get', gm, fb.dyn(key))
    fb.op('JNull', reg=got, offset=u)
    fb.op('SafeCast', dst=sm, src=got)
    fb.op('JNotNull', reg=sm, offset=u + 'd')
    fb.label(u)
    fb.op('New', dst=sm)
    v = fb.reg(cx.t('void'))
    fb.op('Call1', dst=v, fun=cx.fn('haxe.ds.$StringMap.__constructor__').findex.value, arg0=sm)
    b.call('haxe.ds.ObjectMap.set', gm, fb.dyn(key), fb.dyn(sm))
    fb.label(u + 'd')
    return sm


def _cg_site(cx, caller, new_ids):
    """The single compareGoals call in `caller`, vanilla's or already redirected to a wrapper of ours (same type:
    cp-need wraps prepareContext's). Returns (compareGoals, site, args, ret, callee to chain to)."""
    cg = cx.fn('logic.ai.ResourceManager.compareGoals')
    f = cx.fn(caller)
    ours = {fn.findex.value for fn in cx.code.functions if fn.findex.value in new_ids and fn.type.value == cg.type.value}
    sites = [op for op in f.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value in ours | {cg.findex.value}]
    if len(sites) != 1:
        raise ValueError(f'econ: expected 1 compareGoals call in {caller}, found {len(sites)}')
    ft = cx.code.types[cg.type.value].definition
    return cg, sites[0], [a.value for a in ft.args], ft.ret.value, sites[0].df['fun'].value


def build_demo_gate(cx, helpers, new_ids):
    cg, site, args, ret, inner = _cg_site(cx, 'logic.ai.BuildingManager.regularUpdate', new_ids)
    fb = FB(cx, args, ret, fun_type=cg.type.value)
    b = B(fb)
    r = fb.reg(ret)
    fb.op('CallN', dst=r, fun=inner, args=list(range(len(args))))  # vanilla (or the wrapper there), outside the trap
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    sm = _sub_map(fb, b, cx, 'dsur', 0)
    fb.op('JSGte', a=r, b=b.const('i32', 2), offset='sur')
    b.call('haxe.ds.StringMap.remove', sm, 1)  # no surplus: the clock restarts
    fb.op('JAlways', offset='end')
    fb.label('sur')
    one = b.const('i32', 1)
    for nd in NO_DEMO:
        fb.op('JEq', a=b.call('String.__compare', 1, fb.dyn(fb.string(nd))), b=b.const('i32', 0), offset='nodemo')
    fb.op('JAlways', offset='nmp')
    fb.label('nodemo')
    fb.op('Mov', dst=r, src=one)
    fb.op('JAlways', offset='end')
    fb.label('nmp')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    sv = b.call('haxe.ds.StringMap.get', sm, 1)
    fb.op('JNotNull', reg=sv, offset='have')
    b.call('haxe.ds.StringMap.set', sm, 1, fb.dyn(t))
    fb.op('Mov', dst=r, src=one)
    fb.op('JAlways', offset='end')
    fb.label('have')
    since = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=since, src=sv)
    fb.op('Sub', dst=since, a=t, b=since)
    fb.op('JSGte', a=since, b=b.const('f64', DEMO_HOLD), offset='go')
    fb.op('Mov', dst=r, src=one)
    fb.op('JAlways', offset='end')
    fb.label('go')
    b.call('haxe.ds.StringMap.set', sm, 1, fb.dyn(t))  # one demolition per DEMO_HOLD
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    _log_ev(fb, b, cx, helpers, 'dsur', [('f', fb.get(fac, 'kind')), ('res', 1)])
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=r)
    w = fb.build()
    new_ids.add(w)
    site.df['fun'].value = w
    return {'demo-gate': 1}


def build_goal_smooth(cx, helpers, new_ids):
    cg, site, args, ret, inner = _cg_site(cx, 'logic.ai.$HScoring.prepareContext', new_ids)
    fb = FB(cx, args, ret, fun_type=cg.type.value)
    b = B(fb)
    r = fb.reg(ret)
    fb.op('CallN', dst=r, fun=inner, args=list(range(len(args))))  # vanilla (or the wrapper there), outside the trap
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    ma, mt = _sub_map(fb, b, cx, 'gsm', 0), _sub_map(fb, b, cx, 'gst', 0)
    t, v, avg, t0, k = (fb.reg(cx.t('f64')) for _ in range(5))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    fb.op('ToSFloat', dst=v, src=r)
    fb.op('Mov', dst=avg, src=v)  # first reading: as vanilla
    av = b.call('haxe.ds.StringMap.get', ma, 1)
    tv = b.call('haxe.ds.StringMap.get', mt, 1)
    fb.op('JNull', reg=av, offset='put')
    fb.op('JNull', reg=tv, offset='put')
    fb.op('SafeCast', dst=avg, src=av)
    fb.op('SafeCast', dst=t0, src=tv)
    # avg += (v - avg) x min(1, dt / GOAL_TAU)
    fb.op('Sub', dst=k, a=t, b=t0)
    fb.op('SDiv', dst=k, a=k, b=b.const('f64', GOAL_TAU))
    fb.op('JSLte', a=k, b=b.const('f64', 1), offset='kk')
    fb.op('Mov', dst=k, src=b.const('f64', 1))
    fb.label('kk')
    fb.op('JSGte', a=k, b=b.const('f64', 0), offset='kp')
    fb.op('Mov', dst=k, src=b.const('f64', 0))
    fb.label('kp')
    d = fb.reg(cx.t('f64'))
    fb.op('Sub', dst=d, a=v, b=avg)
    fb.op('Mul', dst=d, a=d, b=k)
    fb.op('Add', dst=avg, a=avg, b=d)
    fb.label('put')
    b.call('haxe.ds.StringMap.set', ma, 1, fb.dyn(avg))
    b.call('haxe.ds.StringMap.set', mt, 1, fb.dyn(t))
    # rounded half away from 0
    half = _ratio(fb, b, 0.5)
    fb.op('JSLt', a=avg, b=b.const('f64', 0), offset='neg')
    fb.op('Add', dst=d, a=avg, b=half)
    fb.op('JAlways', offset='rd')
    fb.label('neg')
    fb.op('Sub', dst=d, a=avg, b=half)
    fb.label('rd')
    fb.op('ToInt', dst=r, src=d)
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=r)
    w = fb.build()
    new_ids.add(w)
    site.df['fun'].value = w
    return {'goal-smooth': 1}


def build_pcdump(cx, helpers):
    """aimod_pcdump(mil, dt), tick chain, every PC_DUMP_T s per faction: plascrete stock >= PC_DUMP -> the first of our
    villages (not a main base) with no empty outpost slot (Structure.getEmptyOutpostSlots) holding a plascrete
    building whose Upgrades.getUpgradeFactor is <= 1 (no quirk for it) loses it (removeUpgrade(uid, null), vanilla's
    replace call: the slot frees once the demolition ends; vanilla's pick fills it). Log `pcdump` (s, k, pc)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    fac = b.field(b.field(0, 'controller'), 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    _tick(fb, b, cx, t, PC_DUMP_T, 'end')
    pc = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=pc, src=b.call('ent.Faction.getResource', fac, b.const('i32', RES_PLASCRETE)))
    fb.op('JSLt', a=pc, b=b.const('f64', PC_DUMP), offset='end')
    ss = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=ss, offset='end')
    gk = cx.fn('logic.Upgrades.getKind')
    gkt = [a.value for a in cx.code.types[gk.type.value].definition.args]
    gkn = []
    for t_ in gkt[2:]:
        r_ = fb.reg(t_)
        fb.op('Null', dst=r_)
        gkn.append(r_)
    ku = fb.reg(cx.code.types[gk.type.value].definition.ret.value)
    rm = cx.fn('logic.Upgrades.removeUpgrade')
    rmt = [a.value for a in cx.code.types[rm.type.value].definition.args]
    rmret = cx.code.types[rm.type.value].definition.ret.value
    inst = fb.reg(rmt[2])
    fb.op('Null', dst=inst)
    rr = fb.reg(rmret)
    uid = fb.reg(cx.t('i32'))
    se = fb.reg(cx.t('ent.Entity'))
    i = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('s')
    fb.op('JSGte', a=i, b=b.field(ss, 'length'), offset='end')
    st = b.cast(b.call('hl.types.ArrayObj.getDyn', ss, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=st, offset='s')
    fb.op('JTrue', cond=b.call('ent.Structure.get_isMainBase', st), offset='s')
    fb.op('JSGt', a=b.call('ent.Structure.getEmptyOutpostSlots', st), b=b.const('i32', 0), offset='s')
    up = b.field(st, 'upgrades')
    fb.op('JNull', reg=up, offset='s')
    for k in PC_BUILD:
        nxt = _uid('pk')
        ks = fb.string(k)
        fb.op('CallN', dst=ku, fun=gk.findex.value, args=[up, ks] + gkn)
        fb.op('JNull', reg=ku, offset=nxt)
        fb.op('JSGt', a=b.call('logic.Upgrades.getUpgradeFactor', up, ks), b=b.const('f64', 1), offset=nxt)
        fb.op('SafeCast', dst=uid, src=fb.get(ku, 'uid'))
        fb.op('CallN', dst=rr, fun=rm.findex.value, args=[up, uid, inst])
        fb.op('Mov', dst=se, src=st)
        _log_ev(fb, b, cx, helpers, 'pcdump', [('f', fb.get(fac, 'kind')), ('s', se), ('k', ks), ('pc', pc)])
        fb.op('JAlways', offset='end')  # one per pass
        fb.label(nxt)
    fb.op('JAlways', offset='s')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
