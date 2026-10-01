"""Shared thresholds (docs/AI-POLICY.md §4) and bytecode-building helpers for the AI rules.
Every rules module does `from rules.common import *`; `__all__` exports the underscore helpers too."""
from inject import FB  # noqa: F401
from aware import B  # noqa: F401

SAFE_R = 300       # radius around a healing structure for the safety check
STICKY = 2.0       # current resupply target is abandoned only when threat > own * STICKY
PENALTY = 1 << 28  # overwhelming threat: added to squared distance (map ~2000 -> 4e6), so any safe structure wins
DETOUR = 250       # contested threat: key + DETOUR^2, i.e. a safe structure wins only if not much farther
OVERWHELM = 2.0    # threat > (own + self) * OVERWHELM = overwhelming
HORIZON = 20       # s: moving hostile armies that can reach the circle within this count as threat (speed ~6 u/s)
HUNT_R = 450       # our free armies within this distance of the target join
LOCAL = 250        # threat radius around the target
DEFEND_R = 500     # enter: prey must be within this of one of our structures (defensive posture)
LEASH = 650        # abort: nearest group member farther than this from all our structures
CONTACT = 150      # "in contact" distance (supply trigger only fires when out of contact)
CHECK = 3          # s between abort passes
START = 10         # s between start passes
HOME_R = 300       # enter: an enemy on its own zone is huntable only this close to one of our structures
HOME_EXIT = 400    # abort: ... and the hunt is cancelled once it is farther than this from all of them
DRIFT_R = 575      # abort `drift`: nearest group member farther than this from our structures, none of ours in CONTACT
CONTEST_W = 3      # start score weight when the prey is besieging a structure (objective)
DIST0 = 100        # start score = weight * H / (distance of our nearest free army + DIST0)
ENTER = 1.5        # policy enter ratio
ABORT = 0.7        # policy abort ratio (buffer: an even-ish open-field fight, 1-2 armies down, is kept)
OWN_T = 1.3        # terrain factor on our own zone: we heal and resupply there, they drain (defender advantage)
ENEMY_T = 0.8      # terrain factor on an at-war faction's zone: they heal, we drain (attack there needs 1.5/0.8)
RETREAT = 0.65     # = data AI_WarzonePowerEstimation_RetreatRatio (patches/data.json); balance x terrain is compared
FLEE_ETA = 3       # s: 'imminent' = hostiles in contact range or able to get there within this
FLEE_R = 80        # contact range around a structure / army (warzone radius is 80)
AT_HOME_R = 120    # an army this close to a healing structure is 'at home': it stays unless attack is imminent
HUNT_GAP = 30      # s between two hunt starts of one faction (policy commit; also covers vanilla early cancels)
MIN_LIFE = 0.9     # free army life ratio (= vanilla getUnits minLife)
MIN_SUPPLY = 0.9   # free army supply ratio (= vanilla getUnits minSupply)
SUP_U = 0.35       # supply budget per map unit to our land: drain 50/day (data Army_Supply_DailyDrain, 30 s day)
                   # = 1.67/s at ~6 u/s = 0.28/u, x1.25 margin
SUP_RES = 0.1      # ... plus this share of max supply in reserve. `short` = losing supply and below the budget
SUP_WALK = 0.28    # raw drain per map unit walked (SUP_U without the margin). Fight retreat: a short army with
                   # supply < SUP_WALK x distance to our land is `stranded`: fleeing starves it on the way anyway (and
                   # gets it shot in the back), so it isn't penalised and keeps a fight it is winning (Atreides left a
                   # 1.9:1 fight at 0 supply 250 from home: 4 of 5 armies died fleeing)
SUP_ENTER = 1.25   # hunt start: joining armies need this x the budget at the target (hysteresis vs abort `supply`)
SUP_PEN = 0.6      # fight retreat: balance x (1 - SUP_PEN x share of our fight power that is short on supply)
COVER_R = 130      # turret cover: a structure's turrets / main base guns reach this far from its centre (data: range
                   # 80 for MissileBattery and main bases, + turrets placed around the centre). Also the bunker pair
                   # distance: two villages this close cover each other
TURRET_H = 1500    # turret -> army power: offensivePotential x this HP (~one 3-unit army's health): a MissileBattery
                   # ~ one army, a main base ~ two ("feared more, not overwhelmingly"); calibrate from hunt `T`
KILL = 3.0         # "kill it on the way": a chase under enemy turret cover, or while we defend, only if the prey is
                   # in CONTACT of our free armies and we have KILL x (its threat + turret cover)
BUNKER_W = 1.3     # vanilla target score x this for a village that forms a bunker with ours (Annex / Liberate)
GATHER_R = 900     # contest of our OWN besieged village: free armies this far away join (vanilla Regroup gathers)
BUNKER_R = 200     # villages this close to our main base (under its guns) are its bunker: a lost one is the Annex
                   # target first
MILITARY, RESUPPLY, PATROL = 1, 4, 6  # AIOrderType: Basic Military Defense Protect Resupply Discovery Patrol ...
ADJ_R = 100        # annex-spacing: no second siege on a structure this close to one we already target
                   # (village nearest-neighbour median 110-155)
T_STRUCT, T_GROUP = 5, 6  # AIOrderTargetType: Entity Unit Army Ornithopter Harvester Structure Group
RAID_R = 400       # raid: our armies within this of a village may pillage it (~65 s walk; the supply budget and the
                   # home race bound it further). 250 left an army stack idle at home next to pillageable villages
RAID_TO = KILL     # raid force: nearest raid-ready armies first, until they have this x (threat + cover + militia)
                   # / terrain there (at least ENTER); the rest stays home or raids elsewhere
HOME_M = 100       # raid home race: hostile armies within (target's distance to our land + this) of our land get
                   # there before the raiders could return (~17 s reaction margin)
RECALL_R = DEFEND_R  # raid abort `defend`: a pillage this close to our besieged structure yields its armies
RAID_DONE = 0.5    # a pillage in Action at this progress (0-1, getOccupationActionProgress) is finished, never
                   # aborted (~30 s left of 2 days; the pillage also refills 50% supply)
RAID_GAP = 30      # s between two raid launches of one faction (commit, like HUNT_GAP)
RAID_LIFE = 0.6    # raid army life floor (a pillage is short; vanilla sieges want 0.9 and a full refill)
RAID_ARRIVE = 0.25  # raid: supply share an army must still have on arrival (militia fight drains)
REACT_R = 480      # raid: idle at-war armies this close can reach the village before a pillage ends (militia fight
                   # ~20 s + 2 days = 60 s, at ~6 u/s); fighting, besieging or elsewhere-bound ones don't count
DANGER_T = 180     # faction memory: a zone where our harvester was attacked stays dangerous this long (6 game days),
                   # linearly fading (cooldown); longer would strand good fields, shorter re-sends into the same raiders
DANGER_KEY = 600 * 600  # harvester field choice: squared-distance penalty at full danger (a field up to ~600 farther wins)
ALLY_WIN = 150    # hunt: a third party allied / at peace with the prey counts only if it is within our nearest army's
                   # distance + this (~25 s of fight at ~6 u/s): farther ones arrive after the kill. A third party at
                   # war with the prey doesn't count (it fights the prey too). Log: Harkonnen hunt on 3 Fremen next
                   # to an Atreides stack at war with both
ENGAGE_R = 100    # siege-engage: order armies this close to the target are at it (in the militia fight); farther
                   # ones are still walking and would arrive one by one (Harkonnen raid on Har-Al'sud)
OCC_REFILL = 0.5   # = data Army_Supply_Resupply_OccupationRatio: share of max supply a finished pillage refills
NEUTRAL_REQ = 1.25 # siege launch: required ratio on a neutral target (vanilla 1.0). Below ENTER: militia is known and
                   # never reinforced, and siege-join adds the idle armies nearby on top
JOIN_R = HUNT_R    # siege launch: idle armies this close to the target may join (vanilla sends the minimum) ...
JOIN_TO = KILL    # ... nearest first, until we have this x their power there (KILL: a fight over in seconds)
RETRY = 30         # s: a vanilla siege target launched again this soon after its last launch ended at once
                   # (e.g. InsufficientSupply at +0 s) is dropped from the target scores until then
PURSUIT_T = 15    # s without progress that end a chase (hunt abort `chase`) or a mission-less fight (fight retreat
                   # `pursuit`): a fleeing army at our speed keeps its distance forever (~90 units per 15 s)
PROGRESS = 0.1     # progress = the enemy there lost this share of its power since the last progress ...
CLOSE = 30         # ... or (hunt) our nearest army got this much closer to the prey (~5 s of walking)
PURSUIT_STALE = 3  # s: a warzone record not refreshed for this long belongs to an earlier fight (the balance is read
                   # every tick while the fight runs)
GIVEUP_T = 90      # s: an army a chase gave up on (`chase` abort) isn't chased again for this long (it outruns us;
                   # a new chase would end the same way 45 s later)
RAID_RETRY = 60    # s: a village our raid left (aborted, or cancelled at once by vanilla) isn't raided again this soon
FRONT_R = 600      # director: enemy villages this close to our land are the front (policy §5b)
PRESS = KILL       # ... soft = the spare armies in reach have this x (armies in reach + cover + militia) / terrain
PRESS_R = HUNT_R   # ... spare armies this close to a village can take part (same reach as siege-join)
PRESS_KEEP = ABORT  # a press is dropped when our power there (any task) x terrain < this x their side
PRESS_MAX = 240    # s: a press not finished by then is dropped (`slow`); enemy Annex ~ walk + militia + 6 days
PRESS_RETRY = 120  # s: a dropped press target isn't pressed again this soon
PRESS_W = 10       # Annex score x this for the pressed village (vanilla picks at random among the top scores)
GAUGE_FIRE = 100   # = data AI_Gauge_GoalValue: a military gauge fires at this value (failures x0.85 sink it)
STRAT_LOG = 60     # s: a `strat` row per faction at least this often, and on every posture / target change
CANCEL = 2      # ent.ActionEndReason: Success Fail Cancel Override
REGROUP = 3        # AIOrder.phase: Paused Waiting Preparation Regroup Engage Action Retreat
ACTION = 5
BEST_COUNT = 877   # Const.fValuesCache index of AI_StructureScore_BestStructuresCount: vanilla picks its siege
                   # target at random among this many best scores (Insane 2 ... Easy 5)


def _fcache_int(fb, b, cx, idx, fac):
    """i32 = Const.fValuesCache[idx][fac.aiDifficulty] (per-difficulty data constant, read as tryAction does)."""
    c = fb.reg(cx.t('$Const'))
    fb.op('GetGlobal', dst=c, **{'global': cx.global_of('$Const')})
    out = b.const('i32', 0)
    done = _uid('fc')
    cache = b.field(c, 'fValuesCache')
    fb.op('JNull', reg=cache, offset=done)
    row = b.cast(b.call('hl.types.ArrayObj.getDyn', cache, b.const('i32', idx)), 'hl.types.ArrayBytes_Float')
    fb.op('JNull', reg=row, offset=done)
    v = b.call('hl.types.ArrayBytes_Float.getDyn', row, b.call('ent.Faction.get_aiDifficulty', fac))
    fb.op('JNull', reg=v, offset=done)
    f = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=f, src=v)
    fb.op('ToInt', dst=out, src=f)
    fb.label(done)
    return out


def _alloc_fn(cx):
    """Static ArrayObj.alloc (unnamed): the Call1 after `Type; Call2 alloc_array; UnsafeCast` in tryArmyAction.
    Returns (alloc_array, alloc, [type reg type, native array type, cast type]) copied from that site."""
    f = cx.fn('logic.ai.AIMilitary.tryArmyAction')
    ops = f.ops
    nat = {n.findex.value for n in cx.code.natives if n.name.resolve(cx.code) == 'alloc_array'}
    for i in range(len(ops) - 2):
        if ops[i].op == 'Call2' and ops[i].df['fun'].value in nat and ops[i + 1].op == 'UnsafeCast' \
                and ops[i + 2].op == 'Call1':
            c = ops[i].df
            regs = [f.regs[c['arg0'].value].value, f.regs[c['dst'].value].value, f.regs[ops[i + 1].df['dst'].value].value]
            return c['fun'].value, ops[i + 2].df['fun'].value, regs
    raise ValueError('behave: ArrayObj.alloc pattern not found')


def _ratio(fb, b, v):
    """f64 register = v (float constant via int/100; crashlink has no float constants)."""
    r = fb.reg(fb.cx.t('f64'))
    fb.op('SDiv', dst=r, a=b.const('f64', int(round(v * 100))), b=b.const('f64', 100))
    return r


def _state(fb, b, cx):
    gs = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gs, **{'global': cx.global_of('$Game')})
    return b.field(b.field(gs, 'inst'), 'state')


def _army_loop(fb, b, arr, alen, i, name, done):
    """Loop head: next live ent.Army from arr (skips null, militia, transported, dead). Returns the army register."""
    fb.op('Int', dst=i, ptr=b.code.add_i32(0).value)
    b.loop_head(name)
    fb.op('JSGte', a=i, b=alen, offset=done)
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', arr, i), 'ent.Army')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=a, offset=name)
    fb.op('JTrue', cond=b.field(a, 'isMilitia'), offset=name)
    fb.op('JTrue', cond=b.call('ent.Entity.isTransported', a), offset=name)
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', a), offset=name)
    return a


def _my_armies(fb, b, fac, fail):
    arr = b.cast(fb.get(fac, 'armies', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=arr, offset=fail)
    return arr, b.field(arr, 'length')


def _redirect(cx, target, callers, wrapper):
    tid = cx.fn(target).findex.value
    n = 0
    for caller in callers:
        sites = [op for op in cx.fn(caller).ops if op.op.startswith('Call') and op.df.get('fun') is not None
                 and op.df['fun'].value == tid]
        if len(sites) != 1:
            raise ValueError(f'turret cover: expected 1 {target} call in {caller}, found {len(sites)}')
        sites[0].df['fun'].value = wrapper
        n += 1
    return n


def _new_array(fb, b, cx):
    """Empty hl.types.ArrayObj, built the way the compiler does it."""
    nat, alloc, (t_ty, t_raw, t_cast) = _alloc_fn(cx)
    ty = fb.reg(t_ty)
    fb.op('Type', dst=ty, ty=cx.t('ent.Unit'))
    raw, raw2 = fb.reg(t_raw), fb.reg(t_cast)
    fb.op('Call2', dst=raw, fun=nat, arg0=ty, arg1=b.const('i32', 0))
    fb.op('UnsafeCast', dst=raw2, src=raw)
    arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Call1', dst=arr, fun=alloc, arg0=raw2)
    return arr


def _tick(fb, b, cx, t, period, skip):
    """Jump to `skip` unless floor(t/period) != floor((t-dt)/period) (dt = reg 1)."""
    p = b.const('f64', period)
    q1, t2, q2 = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('SDiv', dst=q1, a=t, b=p)
    fb.op('Sub', dst=t2, a=t, b=1)
    fb.op('SDiv', dst=q2, a=t2, b=p)
    fb.op('JEq', a=b.to_int(q1), b=b.to_int(q2), offset=skip)


GLOBALS = {}       # name -> (code, global index): added globals, one set per boot file build


_UID = [0]


def _uid(prefix):
    _UID[0] += 1
    return f'{prefix}{_UID[0]}'


def _global_map(fb, b, cx, name):
    """Added global haxe.ds.ObjectMap `name` (state kept between calls; not saved with the game), created on
    first use. Maps: 'hunt' faction -> last hunt start time; 'heal'/'retreat' key -> last log time (throttle)."""
    om_t = cx.t('haxe.ds.ObjectMap')
    if name not in GLOBALS or GLOBALS[name][0] is not cx.code:
        from crashlink.core import tIndex
        ti = tIndex()
        ti.value = om_t
        cx.code.global_types.append(ti)
        GLOBALS[name] = (cx.code, len(cx.code.global_types) - 1)
    g = GLOBALS[name][1]
    r = fb.reg(om_t)
    have = _uid('havemap')
    fb.op('GetGlobal', dst=r, **{'global': g})
    fb.op('JNotNull', reg=r, offset=have)
    fb.op('New', dst=r)
    v = fb.reg(cx.t('void'))
    ctor = cx.fn('haxe.ds.$ObjectMap.__constructor__')
    fb.op('Call1', dst=v, fun=ctor.findex.value, arg0=r)
    fb.op('SetGlobal', src=r, **{'global': g})
    fb.label(have)
    return r


def _throttle(fb, b, cx, name, key, period, skip):
    """Jump to `skip` if map `name` saw `key` less than `period` game seconds ago; else record now and fall through."""
    mp = _global_map(fb, b, cx, name)
    t = b.field(_state(fb, b, cx), 'time')
    last = b.call('haxe.ds.ObjectMap.get', mp, fb.dyn(key))
    go = _uid('thr')
    fb.op('JNull', reg=last, offset=go)
    lf = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=lf, src=last)
    fb.op('Sub', dst=lf, a=t, b=lf)
    fb.op('JSLt', a=lf, b=b.const('f64', period), offset=skip)
    fb.label(go)
    b.call('haxe.ds.ObjectMap.set', mp, fb.dyn(key), fb.dyn(t))


def _log_ev(fb, b, cx, helpers, event, fields):
    """Log one AIMOD event: fields = [(key, reg | str)]; f64 regs are logged x100 as ints when key ends with '%',
    entities through the entity describer, strings as given."""
    d = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=d)
    b.put(d, 'e', fb.string(event))
    for k, r in fields:
        if isinstance(r, str):
            b.put(d, k, fb.string(r))
        elif k.endswith('%'):
            x = fb.reg(cx.t('f64'))
            fb.op('Mul', dst=x, a=r, b=b.const('f64', 100))
            b.put(d, k[:-1], b.to_int(x))
        elif fb.regs[r] == cx.t('f64'):
            b.put(d, k, b.to_int(r))
        elif fb.regs[r] in (cx.t('ent.Entity'), cx.t('ent.Army'), cx.t('ent.Structure')):
            er = fb.reg(cx.t('dyn'))
            src = r
            if fb.regs[r] != cx.t('ent.Entity'):
                src = fb.reg(cx.t('ent.Entity'))
                fb.op('Mov', dst=src, src=r)
            fb.op('Call1', dst=er, fun=helpers['ent'], arg0=fb.dyn(src))
            b.put(d, k, er)
        else:
            b.put(d, k, r)
    v = fb.reg(cx.t('void'))
    fb.op('Call1', dst=v, fun=helpers['log'], arg0=fb.dyn(d))


def field_name_t(cx, obj_type, index):
    return cx.code.types[obj_type].definition.resolve_fields(cx.code)[index].name.resolve(cx.code)



def build_chain(cx, fns):
    """One (AIMilitary, dt) -> void function calling each of fns in order (each has its own throttle and trap)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    void = fb.reg(cx.t('void'))
    for f in fns:
        fb.op('Call2', dst=void, fun=f, arg0=0, arg1=1)
    fb.op('Ret', ret=void)
    return fb.build()


__all__ = [n for n in dir() if not n.startswith('__')]
