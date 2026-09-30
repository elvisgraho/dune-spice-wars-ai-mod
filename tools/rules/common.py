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
RAID_R = 250       # raid: our armies within this of an enemy village may pillage it
RAID_GAP = 30      # s between two raid launches of one faction (commit, like HUNT_GAP)
RAID_LIFE = 0.6    # raid army life floor (a pillage is short; vanilla sieges want 0.9 and a full refill)
RAID_ARRIVE = 0.25  # raid: supply share an army must still have on arrival (militia fight drains)
OCC_REFILL = 0.5   # = data Army_Supply_Resupply_OccupationRatio: share of max supply a finished pillage refills
CANCEL = 2        # ent.ActionEndReason: Success Fail Cancel Override
REGROUP = 3        # AIOrder.phase: Paused Waiting Preparation Regroup Engage Action Retreat


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
