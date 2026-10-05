"""Parse AIMOD lines (from the `ai-log` boot patch) and print a compact report.

Every event: e=event, t=app seconds, g=game seconds, f=faction (usually). Events (tools/inject.py):
  pick  : tgt, tf, req, allIn, ign3rd, sim, cand, eu, sel, ax, ay  (army chosen for a target; ax/ay = closest picked army)
  pw    : b, my, en         (power estimate inside pickUnits; last before pick = final)
  order : type, prio, n, tgt, act, sa, ax, ay
  phase : order fields + ph (before), to
  fpw   : b, my, en         (live power in getOrderPowerBalance; precedes fightb)
  fightb: order fields + b
  stop  : order fields + why, src (code path that stopped the order); end: order fields + why
  fight : wx, wy, ents, ok  (AIUnits.initFight: a fight/warzone started)
  micro : army, from, to, n (changeArmyMicro: Idle/Attack/Reposition/Flee)
  snap  : aggr, gauges, armies, structs (daily per AI faction)
  aw    : n, en, mine, a=[{o,k,x,y,pw,hp,sup,ms,ls,hz,zo,sand,worm,vis,mv,d,near,sa,ty,tgt,oc,ct}] (tools/aware.py:
          every 10 s per AI faction: hostile armies within 600 of its structures or armies, or visible; da/na/nsa/nty/ntgt = our nearest army and its task)
  hunt  : act (start|abort|engage), why (abort: gone truce won leash home supply drift lost weak turret objective defend chase desert), T
          (enemy turret cover at the anchor / group, power units; included in H), tgt (prey / first
          member; the village for a contest), H, M, n, ng (group size), ok, sd (dist to our land), dn (our nearest order
          army), dm (start: our nearest free army), anc (start: the besieged village for a contest, else the prey),
          obj (abort objective: the besieged village the chase yields to), x, y (tools/rules: attack on an exposed
          army or contest of a siege; H = threat around it, M = our free power in reach (abort: order power), n armies
          sent; the order itself is a Military ArmyFight order). engage: the order left Regroup early because the
          armies within LOCAL of the core (member nearest our land) already pass the entry test (M = their power)
  retreat: act (retreat|hold|recall|pursuit|disengage: Resupply armies left shooting a powerless target|trespass: no-order armies shooting at-war structures on their zone), raw, tf, sf, adj (fight balance x100: vanilla, terrain factor, supply factor,
          adjusted; recall = every army of ours there short of supply and none in a Military order: balance 0; pursuit =
          none of ours there in a Military order and the enemy there (en, power within CONTACT) lost < 10% for 15 s:
          balance 0 (chasing a fleeing army); stranded = held
          while dm (power of short armies that can't pay the walk home) > 0: they get no supply penalty;
          logged when raw or adj <= RETREAT, once per warzone per 5 s), x, y
  heal  : act (stay|flee|detour|avoid), s (healing structure), a (asking army), h, m (hostile / own power near s), d
          (army to s); once per structure per 3 s. stay/flee = army at s (<= AT_HOME_R); detour/avoid = key penalty
  space : k, why (defend|space|retry), tgt, near (siege action on tgt refused: defend = our structure `near` is
          besieged; space = we already target `near` within ADJ_R; retry = tgt's last launch ended at once, dropped
          from the target scores for RETRY s); once per faction per 10 s
  bunker: k, tgt, was, mb (Annex redirected from `was` to the village tgt next to our main base mb)
  disc  : tgt, army, H, M, tf (world-event Discovery trip refused: the lone army's power M < ENTER x at-war threat H
          around the event / terrain tf x100)
  strand: a, s, d, ok (idle army on hostile land sent home: Patrol Move to our structure s, d = its distance)
  tension: f, v, w, T (x100), d (hottest contact pair per faction every 30 s, rules/tension.py)
  hride / rride: f, a (hunt / raid army in transit: the order isn't re-judged, at most RIDE_MAX s)
  keepcap: f, a, s, v (vanilla micro wanted army a to defend our structure s; kept at village v we capture)
  unstick: f, a, tgt, st, ok (siege army standing still in the village with no siege running moved to the target's safe position; st = s still)
  undeploy: a, ok, nm, sup, air (installed AA turret uninstalled: nothing flying within AA_R, or idle on hostile land; nm = order move blocks removed)
  wlet  : f, a, d, pe (worm-targeted army left to walk out on its own: d worm distance, pe path left; rules/worm.py)
  aagate: f, a (FSpecialInstall refused: no at-war flying army within AA_R; rules/deploy.py)
  opgate: f, s, k, n (siege order: its n operations dropped, vanilla launches no military op; rules/ops.py)
  opcast / opfail: f, op, why, s / zs (zone village), zid, B (x100), M, H, r (opfail: checkUseAbilityOn EReason index, named via tools/ereason.json; -1 = refused on use) (our cast / refused; rules/opsbrain.py)
  opveto / opvan: f, op (vanilla launch blocked / a vanilla-kept op launched: Cell Search, ...)
  opcell: f, drop (held op cancelled for a Cell Search slot)
  ophold: f, intel, ag, slots, held, started (every 60 s per faction)
  opfz: f, opp, M, H, n, nl (a fight of ours with >= OPS_FIGHT_H visible enemy power, 20 s per faction)
  opcf: f, s, pr%, M, H (Atreides: our village under capture the Cease Fire trigger judged, 20 s per village)
  drain: f, s, hp%, hp0%, pr%, n (siege in Action worn down: cancelled; rules/drain.py)
  fopen : f, act, n (Fremen opening: first Annex held, n neutral villages surveyed; rules/fopen.py)
  afield / afveto: f, s, sc, d, hops / why (Airfield lifted on a remote village / vanilla's Airfield dropped: behind | spaced; rules/build.py)
  bkeep : f, tgt, n, ph (siege order kept after its last besieger of ours died; rules/orders.py siege-keep)
  tkeep : f, a, n, ph (our Military order kept before Action when another order took army a; rules/orders.py take-keep)
  scout: f, tgt, w, n, need (early village: too few Annex candidates (n < need), held while ornithopters scout, w s waited; rules/annex.py)
  alone: f, tgt, s, c (sole Annex candidate past the opening with no ring / special / spice value: dropped)
  ascore: f, tgt, s, c, cmin, vb, v0, vs, n, dd (x100: Fremen deep-desert surround sum of the best), hold (off-ring candidates dropped by the Fremen ring hold), rt / rs / rdd (best ring village, its score, dd x100), ddh (zone hops of the focus deep desert, 999 none) (Annex value: our best target vs vanilla's best; tools/rules/annex.py)
  noregen: f, a, hp (army without safe regen and full supply removed from the checkUnits Resupply query)
  aring : f, v, v0 (uncontested deep-desert ring village scored for Annex although vanilla's score v0 <= 0; rules/annex.py)
  pkeep : f, v (ring village dropped from vanilla's Pillage targets)
  tveto : f, s, sc, n, hops (vanilla MissileBattery score sc > 0 at a village no turret rule of ours calls for: dropped; rules/build.py)
  odead : f, a, hp, ph, n (unit checkOrderTerminations removes from an order as dead; rules/orders.py)
  okeep : f, n, ph (our Military order kept before Action after that removal, n armies left)
  rfail : r, f, at (step probe: the last run of rule r for faction f died at step id `at` = work/crumbs.json source line)
  dfull : f (checkStructures' all-in fallback on full CP blocked; rules/army.py cp-defense)
  cpdis : f, a, cp, free (CP overflow: temporary army a disbanded, cp = its CP upkeep, free = net CP before; rules/army.py)
  mpgate: f, mp (unit pick that vanilla's Manpower goals would have blocked, let through; once per faction per 60 s)
  lowpick: f, a, hp, src (siege|defense|discovery: army under PICK_LIFE removed from vanilla's getUnits result; extra: worn
          temporary unit appended to a Defense the healthy armies already carry)
  rally : f, act (rally|off|commit|giveup|here: already at D), s (danger structure), r (rally point), H, M, n (defenders sent), Mall (here: all within RALLY_R; rules/rally.py)
  gather: f, a, tgt, d, dmax, n (Engage leader held for the pack; rules/gather.py)
  spos  : f, a, tgt, es, cv, ok (siege army under at-war guns moved to the target's far side from e; rules/spos.py)
  dstep : f, a, tgt, d, ok (our siege / raid army on the deep-desert side of its target moved 40 from it; rules/desert.py)
  wflee : f, a, rock, d, w, ok (worm-targeted army on sand sent to the nearest rock point; tools/rules/worm.py)
  weaten: o, a, fled (any army eaten by a worm; fled = s since our wflee moved it, -1 never)
  hflee : f, a, H, dg (attacked team harvester released to vanilla's re-route)
  hrun  : f, a, s, H, M, ok (fighting harvester outgunned within CONTACT sent to the nearest safe field, s null = main base; rules/memory.py)
  whold : f, a, src (worm-moved army dropped from a vanilla pick / Resupply query while a worm is within 150; rules/worm.py)
  mem   : k, a (faction memory event: k harvester = our harvester a fighting, its zone stamped dangerous)
  hfield: a, s, dg (harvester a's field choice: field s penalised, dg = zone danger x100; once per field per 10 s)
  strat : f, post (defend|hold|press|expand|harass; hold = no spare force for a new target), S (spare power after home need), need, T (our army power),
          tgt (pressed village), mode (annex|pillage), hold (their side there), reach (our power there), war =
          [{f, ds (our desiredStatus toward it: 0 peace wish, 1 war target, 2 total war, -1 unknown), pw}] (director,
          every posture / target change and at least every 60 s); act drop: why (done|gone|truce|slow|weak), tgt, age
  raid  : act start: tgt, H, M, n, dm (0 = the pressed village), sd, hh, ms, ax, nc, ok (pillage launched: H = at-war threat + enemy turret
          cover + militia at the village, M = the sized raid force (+ our cover), n armies, dm = nearest, sd = village
          to our land, hh / ms = hostile / our power within sd + HOME_M of our land (ms minus the raid), ax = the
          vanilla Annex choice kept out, nc = vanilla pillage candidates; the order itself is a Military ArmySiege
          Pillage row). act refuse (nearest candidate with our armies within RAID_R, once per faction per 30 s): why
          (ready|weak|home), H armies, C turrets, Mi militia, M, tf (x100), nr armies near / n raid-ready, dm, sd, hh,
          ms, ax, nc. act abort (any Pillage order of ours): why (defend|home|weak), tgt, H, M, ph phase, pr progress
          (x100), sd, n units
  call  : fn, a<i>, r, src  (generic traces from testbed/ailog.json)
  mark  : player pressed L
"""
import json
import math
import re
from collections import Counter, defaultdict

PH = ['Pa', 'W', 'P', 'Rg', 'E', 'A', 'R']
LEGEND = ('phases Pa=Paused W=Waiting P=Preparation Rg=Regroup E=Engage A=Action R=Retreat | dist = attacking army '
          'to target at order start | est = planned my/enemy power (req = required ratio) | fight = live power '
          'first->last (me/en change; rel@ = armies released alive then, compared up to it; deadK/N = armies removed as dead, the loss flag when logged) | end = reason [code path that stopped it] | ! = est<1.25, own loss>30% (half the armies dead when logged) or failed')


_EREASON = None


def _ereason(i):
    """EReason constructor name of index i (tools/ereason.json, dumped from hlboot.dat); -1 = refused on use."""
    global _EREASON
    try:
        i = int(float(i))
    except (TypeError, ValueError):
        return str(i)
    if i < 0:
        return 'UseFailed'
    if _EREASON is None:
        import json as _j
        from pathlib import Path as _P
        try:
            _EREASON = _j.load(open(_P(__file__).with_name('ereason.json')))
        except OSError:
            _EREASON = []
    return _EREASON[i] if i < len(_EREASON) else str(i)


def parse_value(s, i):
    if s.startswith('[{', i) or s.startswith('[]', i):  # list of objects (event `aw`)
        items, i = [], i + 1
        while s[i] != ']':
            if s.startswith(', ', i):  # truncated list, no ']' (e.g. snap gauges: `},, armies`): end it here
                return items, i
            v, j = parse_value(s, i)
            if j == i:  # no progress on malformed input: fail (-> 'unparsed') instead of looping forever
                raise ValueError(f'stuck at {i}')
            items.append(v)
            i = j
            if s[i] == ',':
                i += 1
        return items, i + 1
    if s[i] == '{':
        obj, i = {}, i + 1
        while s[i] != '}':
            j = s.index(' : ', i)
            obj[s[i:j]], i = parse_value(s, j + 3)
            if s.startswith(', ', i):
                i += 2
        return obj, i + 1
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c in '({[':
            depth += 1
        elif c in ')]':
            depth -= 1
        elif depth == 0 and (c == '}' or s.startswith(', ', j)):
            break
        j += 1
    return atom(s[i:j]), j


def atom(v):
    if v == 'null':
        return None
    if v in ('true', 'false'):
        return v == 'true'
    return float(v) if re.fullmatch(r'-?\d+(\.\d+)?(e[-+]?\d+)?', v) else v


def director(strats):
    """Director (tools/rules/strat.py): posture time per faction, press targets with their outcome, war wishes."""
    out = ['\n## Director (tools/rules/strat.py): posture per faction (share of rows), presses and their end; '
           'ds = our desiredStatus toward an at-war faction (0 = vanilla never targets its villages)']
    rows = [e for e in strats if e.get('act') != 'drop']
    drops = [e for e in strats if e.get('act') == 'drop']
    by = defaultdict(Counter)
    for e in rows:
        by[e.get('f')][e.get('post')] += 1
    for f, c in sorted(by.items(), key=lambda kv: str(kv[0])):
        n = sum(c.values())
        last = [e for e in rows if e.get('f') == f][-1]
        war = ' '.join(f"{w.get('f')}:ds{num(w.get('ds'), 0)}/{kpw(w.get('pw'))}" for w in (last.get('war') or [])
                       if isinstance(w, dict))
        out.append(f"{f}: " + ', '.join(f'{p} {100 * k // n}%' for p, k in c.most_common())
                   + f" | last S{kpw(last.get('S'))} need{kpw(last.get('need'))} T{kpw(last.get('T'))} | {war}")
    starts = [e for e in rows if e.get('post') == 'press' and e.get('tgt')]
    seen = set()
    for e in starts:
        key = (e.get('f'), ent(e.get('tgt')))
        if key in seen:
            continue
        seen.add(key)
        end = next((d for d in drops if d.get('f') == e.get('f') and ent(d.get('tgt')) == key[1]
                    and d['_t'] >= e['_t']), None)
        out.append(f"  {clock(e['_t'])} {e.get('f')} press {key[1][:22]:<22} {e.get('mode')} hold{kpw(e.get('hold'))} "
                   f"reach{kpw(e.get('reach'))} -> " + (f"{end.get('why')} at {clock(end['_t'])}" if end else 'open'))
    return out


def parse_lines(lines):
    events = []
    for line in lines:
        k = line.find('AIMOD {')
        if k < 0:
            continue
        try:
            ev = parse_value(line, k + 6)[0]
            if isinstance(ev.get('e'), dict) and 'cv' in ev:   # old spos rows logged the enemy structure as `e`
                ev['es'], ev['e'] = ev['e'], 'spos'
            elif isinstance(ev.get('e'), dict) and 'M' in ev:   # old strike start rows logged the enemy army as `e`
                ev['en'], ev['e'] = ev['e'], 'strike'
            events.append(ev)
        except (ValueError, IndexError):
            events.append(_salvage(line[k:]) or {'e': 'unparsed'})
    return events


def _salvage(s):
    """Flat `key : number|word` fields of a line the parser couldn't read (the log truncates long values, e.g. the
    snap gauge list cut inside an entry): snap aggr / armies / structs, stocks (au / aup / inf / sol / mp), army size
    (cp / cpf) and the g / t clocks."""
    m = re.match(r'AIMOD \{e : (\w+), f : (\w+)', s)
    if not m:
        return None
    e = {'e': m.group(1), 'f': m.group(2)}
    for key, val in re.findall(r'(?:^|[{,] )(aggr|armies|structs|au|aup|inf|sol|mp|cp|cpf|g|t) : (-?[\d.]+(?:e[+-]?\d+)?)', s):
        e[key] = float(val)
    return e if 'g' in e else None


def ent(d):
    if not isinstance(d, dict):
        return '-' if d is None else str(d)
    name = d.get('p') or d.get('k') or '?'
    return f"{name}({d['o']})" if d.get('o') else str(name)


def ent_key(d):
    return (d.get('k'), d.get('p'), round(d.get('x') or 0), round(d.get('y') or 0)) if isinstance(d, dict) else None


def num(v, nd=2):
    return '-' if v is None else f'{v:.{nd}f}' if isinstance(v, float) else str(v)


def kpw(v):
    return f'{v / 1e3:.0f}k' if isinstance(v, (int, float)) else '-'


def big(v):
    if not isinstance(v, float):
        return '-'
    return f'{v / 1e6:.1f}M' if abs(v) >= 1e6 else f'{v / 1e3:.0f}k'


def clock(sec):
    return '--:--' if sec is None else f'{int(sec // 60):02d}:{int(sec % 60):02d}'


def parse_clock(text):
    m, s = text.split(':')
    return int(m) * 60 + int(s)


def when(e, t0):
    return e['g'] if isinstance(e.get('g'), float) else (e.get('t') or 0) - t0


def change(first, last):
    if not first or last is None:
        return '?'
    c = (last - first) / first
    return f'{c:+.0%}'


def dist(e, tgt):
    try:
        return math.hypot(e['ax'] - tgt['x'], e['ay'] - tgt['y'])
    except (KeyError, TypeError):
        return None


def aw_owner(a):
    """Owner of an `aw` entry; neutral raiders as raid:<kind> (* = their raid targets the observer)."""
    if a.get('rk'):
        return f"raid:{a['rk']}{'*' if a.get('rt') else ''}"
    return a.get('o')


def aw_army(a):
    """Compact hostile army from an `aw` entry."""
    act = f" {a.get('sa') or str(a.get('ty') or '').split('(')[0]}>{a.get('tgt')}" if a.get('ty') or a.get('sa') else ''
    flags = ''.join(c for c, key in (('S', 'sand'), ('V', 'vis'), ('M', 'mv'), ('L', 'ls'), ('H', 'hz')) if a.get(key))
    return (f"{aw_owner(a)}:{a.get('k')} pw{big(a.get('pw'))} hp{num(a.get('hp'), 0)} sup{num(a.get('sup'), 0)}/{num(a.get('ms'), 0)}"
            f" d{num(a.get('d'), 0)}@{a.get('near')} zone={a.get('zo') or '-'} worm{num(a.get('worm'), 1)} {flags}{act}"
            + (f" ct={a['ct']}" if a.get('ct') else '') + (f" oc={a['oc']}" if a.get('oc') else '')
            + f" | our {a.get('na') or '-'} d{num(a.get('da'), 0)}{my_task(a)}")


def my_task(a):
    """What our nearest army (to this hostile army) was doing."""
    if not (a.get('nty') or a.get('nsa')):
        return ''
    return f" busy {a.get('nsa') or str(a.get('nty') or '').split('(')[0]}>{a.get('ntgt')}"


def short(e):
    """One compact line for the --around timeline."""
    k = e.get('e')
    if k == 'aw':
        armies = e.get('a') if isinstance(e.get('a'), list) else []
        return (f"{e.get('f') or '-':<10} {'aw':<28} n={num(e.get('n'), 0)} en={big(e.get('en'))} mine={big(e.get('mine'))}"
                + ''.join('\n        ' + aw_army(a) for a in armies if isinstance(a, dict)))
    skip = {'e', 't', 'g', 'f', 'fn'}
    parts = []
    for key, v in e.items():
        if key in skip or v is None:
            continue
        v = ent(v) if isinstance(v, dict) and ('k' in v or 'p' in v) else v
        v = (str(int(v)) if v.is_integer() else num(v)) if isinstance(v, float) else str(v)
        parts.append(f'{key}={v[:60]}')
    return f"{e.get('f') or '-':<10} {e.get('fn') or k:<28} {' '.join(parts)}"


def around(events, center, window=60, faction=None):
    t0 = events[0].get('t') or 0
    noisy = {'pw', 'fpw', 'fightb'}
    out = [f'# Events {clock(center - window)}..{clock(center + window)} (pw/fpw/fightb omitted)'
           + (f', faction {faction}' if faction else '')]
    for e in events:
        t = when(e, t0)
        if faction and e.get('f') != faction:
            continue
        if abs(t - center) <= window and e.get('e') not in noisy:
            out.append(f'{clock(t)} {short(e)}')
    return '\n'.join(out)


def ai_control(events, t0, span):
    """`!AI OFF` lines from the traced `ent.Faction.set_isAI` calls: a faction whose AI is off (the player's own
    faction after Player.onConnect, e.g. a Landsraad vote or taking control) does nothing, so judge no rule there."""
    sw = [e for e in events if e.get('e') == 'call' and str(e.get('fn', '')).endswith('set_isAI')]
    off, out = {}, []
    for e in sw:
        f = e.get('f') if isinstance(e.get('f'), str) else str(e.get('f'))
        on = e.get('r') if isinstance(e.get('r'), bool) else bool(e.get('a1'))
        at = when(e, t0)
        if not on and f not in off:
            off[f] = (at, e.get('src') or '-')
        elif on and f in off:
            start, src = off.pop(f)
            out.append(f'!AI OFF: {f} {clock(start)}-{clock(at)} (off by {src}, on by {e.get("src") or "-"})')
    for f, (start, src) in off.items():
        out.append(f'!AI OFF: {f} since {clock(start)}, still off at {clock(span)} (off by {src}): press P or `ai true`')
    return out


def stuck_fights(wzbs, thr=65, run=3, near=40):
    """`wzb` samples (fight balance per warzone every 5 s): runs of >= `run` samples of one faction within `near` of
    each other with adjusted balance <= thr = a fight below the retreat line that went on (vanilla should have left)."""
    out = ['\n## Fight balance (wzb samples): losing fights that kept going (adj <= 0.65 for >= 15 s at one place): '
           'faction from-to at (x,y) raw/adj min, samples']
    by = defaultdict(list)
    for e in wzbs:
        by[e.get('f')].append(e)
    found = 0
    for f, es in by.items():
        cur = []
        for e in es + [None]:
            low = e is not None and isinstance(e.get('adj'), (int, float)) and e['adj'] <= thr
            if low and cur and (abs(e['x'] - cur[-1]['x']) > near or abs(e['y'] - cur[-1]['y']) > near
                                or e['_t'] - cur[-1]['_t'] > 12):
                low_run, cur = cur, [e]
            elif low:
                low_run, cur = None, cur + [e]
            else:
                low_run, cur = cur, []
            if low_run and len(low_run) >= run:
                found += 1
                a, z = low_run[0], low_run[-1]
                out.append(f"  {f} {clock(a['_t'])}-{clock(z['_t'])} at ({a['x']:.0f},{a['y']:.0f}) "
                           f"raw{min(x['raw'] for x in low_run)} adj{min(x['adj'] for x in low_run)} n{len(low_run)}")
    out.append(f'  ({found} runs; {len(wzbs)} samples)')
    return out


def summarize(events, faction=None, all_orders=False):
    if not events:
        return 'No AIMOD events. Is the testbed on (`mod testbed on`) and did a match run?'
    t0 = events[0].get('t') or 0
    kinds = Counter(e.get('e') for e in events)
    facs = sorted({e.get('f') for e in events if isinstance(e.get('f'), str)})
    span = when(events[-1], t0) - when(events[0], t0)
    minutes = max(span / 60, 1)
    out = [f'# AI log: {len(events)} events, {clock(span)} game time ({", ".join(f"{k}={v}" for k, v in kinds.most_common())})',
           f'factions: {", ".join(facs)}. Times = game mm:ss. {LEGEND}']
    out += ai_control(events, t0, span)

    orders, open_orders, marks = [], defaultdict(list), []
    fight_orders = defaultdict(list)  # faction -> its ArmyFight orders (moving group targets)
    snap_hist = defaultdict(list)  # faction -> its daily snapshots (resources)
    last_pw, last_fpw, last_pick, last_stop = None, None, {}, {}
    rejected = defaultdict(lambda: {'n': 0, 'req': []})
    intents = defaultdict(Counter)          # faction -> Counter((gaugeKind, outcome))
    fights, micro, snaps, aws = [], defaultdict(Counter), {}, []
    armysz = []  # rules/army.py: cpdis / mpgate
    rfails = []  # rules/common.py step probe: a tick rule run that died silently
    sweeps = []  # sweep.py map sweep rows
    cvbads, rfirsts, rnots = [], [], []  # world.py aimod_cover1 trap (a structure that threw) / build.py spice-first
    calls = defaultdict(lambda: {'n': 0, 'f': Counter(), 'r': Counter()})
    stops = Counter()
    hunts = Counter()                       # (faction, act, why)
    spaced = Counter()                      # (faction, why, kind, tgt, near)
    retreats, heals, bunkers, discs, raids, strats, peaces, wzbs = [], [], [], [], [], [], [], []
    worms, lowpicks, ascores, gathers, rallies = [], [], [], [], []
    acands = []
    standoff = []                           # treaty / patrol / turret rows (rules/peace.py, strand.py, build.py)
    opsev = []                              # operations (rules/ops.py, opsbrain.py)
    rides = []                              # worm rides (rules/ride.py)
    for e in events:
        k, f, t = e.get('e'), e.get('f'), when(e, t0)
        e['_t'] = t
        if k == 'mark':
            marks.append(t)
            continue
        if faction and isinstance(f, str) and f != faction:
            continue
        if k == 'pw':
            last_pw = e
        elif k == 'fpw':
            last_fpw = e
        elif k == 'pick':
            e['_pw'], last_pw = last_pw, None
            if e.get('sel'):
                last_pick[(f, ent_key(e.get('tgt')))] = e
            else:
                tgt = e.get('tgt') or {}
                r = rejected[(f, ent(tgt), 'def' if tgt.get('o') == f else 'atk')]
                r['n'] += 1
                if isinstance(e.get('req'), float):
                    r['req'].append(e['req'])
        elif k == 'order':
            key = (f, ent_key(e.get('tgt')))
            o = {'t': t, 'ev': e, 'pick': last_pick.pop(key, None), 'ph': [], 'fight': [], 'end': None, 'src': None,
                 'dist': dist(e, e.get('tgt'))}
            orders.append(o)
            open_orders[key].append(o)
            if e.get('act') == 'ArmyFight':
                o['pos'] = ((e.get('tgt') or {}).get('x') or 0, (e.get('tgt') or {}).get('y') or 0)
                fight_orders[f].append(o)
        elif k in ('phase', 'fightb', 'end', 'stop') or (k == 'odead' and e.get('tgt') is not None):
            if k == 'odead':
                standoff.append(e)
            live = [o for o in open_orders.get((f, ent_key(e.get('tgt'))), []) if o['end'] is None]
            if not live and e.get('act') == 'ArmyFight':  # a hunt's group target moves: nearest open ArmyFight
                tg = e.get('tgt') or {}
                xy = (tg.get('x') or 0, tg.get('y') or 0)
                cand = [o for o in fight_orders[f] if o['end'] is None]
                live = sorted(cand, key=lambda o: (o['pos'][0] - xy[0]) ** 2 + (o['pos'][1] - xy[1]) ** 2)[:1]
                if live:
                    live[0]['pos'] = xy
            if k == 'stop':
                last_stop[(f, ent_key(e.get('tgt')))] = e.get('src')
                if str(e.get('type')) == 'Military':
                    stops[(f, e.get('src'), str(e.get('why')))] += 1
            if not live:
                continue
            o = live[0]
            if k == 'phase' and isinstance(e.get('to'), float):
                p = int(e['to'])
                name = PH[p] if 0 <= p < len(PH) else str(p)
                if not o['ph'] or o['ph'][-1] != name:
                    o['ph'].append(name)
            elif k == 'fightb':
                pw = last_fpw or {}
                o['fight'].append((t, e.get('b'), pw.get('my'), pw.get('en')))
                last_fpw = None
            elif k == 'odead':  # one of its armies removed as dead (rules/orders.py): a real loss
                o['dead'] = o.get('dead', 0) + 1
            elif k == 'end':
                o['end'] = (t, e.get('why'), e.get('n'))
                o['src'] = last_stop.pop((f, ent_key(e.get('tgt'))), None)
        elif k == 'retreat':
            retreats.append(e)
        elif k == 'sbal':  # sietch / renegade strike fight: balance lowered to the live order balance (ob)
            retreats.append(dict(e, act='sbal', adj=e.get('ob')))
        elif k == 'heal':
            heals.append(e)
        elif k == 'space':
            spaced[(f, e.get('why') or 'space', e.get('k'), ent(e.get('tgt')), ent(e.get('near')))] += 1
        elif k == 'sfloor':  # sietch / renegade-base strike short of its garrison's army count
            spaced[(f, 'floor', 'n%s<%s' % (e.get('n'), e.get('min')), ent(e.get('tgt')), '-')] += 1
        elif k == 'sweak':  # sietch / renegade-base pick below ENTER x militia + threat by our measure
            spaced[(f, 'weak', 'n%s M%dk H%dk' % (e.get('n'), (e.get('M') or 0) // 1000, (e.get('H') or 0) // 1000),
                    ent(e.get('tgt')), '-')] += 1
        elif k == 'sgo':  # sietch / renegade-base pick that passed (armies only, tf 1): not a refusal, compare to `sact`
            spaced[(f, 'sgo', 'n%s M%dk H%dk tf%s' % (e.get('n'), (e.get('M') or 0) // 1000, (e.get('H') or 0) // 1000,
                                                     e.get('tf')), ent(e.get('tgt')), '-')] += 1
        elif k == 'bunker':
            bunkers.append(e)
        elif k == 'disc':
            discs.append(e)
        elif k == 'strat':
            strats.append(e)
        elif k in ('raid', 'release'):
            raids.append(e)
            if k == 'release' or e.get('act') == 'split':  # armies left the order alive: not losses (fight me%)
                rel = [o for o in open_orders.get((f, ent_key(e.get('tgt'))), []) if o['end'] is None]
                if rel:
                    rel[0].setdefault('rel', t)
        elif k == 'peace':
            peaces.append(e)
        elif k == 'rally':
            rallies.append(e)
        elif k in ('gather', 'stage'):
            gathers.append(e)
        elif k in ('opcast', 'opfail', 'opveto', 'opvan', 'opcell', 'ophold', 'opgate', 'opbuy', 'opfz', 'drain', 'opcf'):
            opsev.append(e)
        elif k in ('wplan', 'wreq', 'wride', 'wstall', 'tstk'):
            rides.append(e)
        elif k in ('treaty', 'patrol', 'turret', 'tveto', 'aring', 'pkeep', 'odead', 'okeep', 'fpeace', 'pannex', 'pagate', 'sdrop', 'airpick', 'rejoin', 'dall', 'uhqcap',
                   'uhqres', 'uhqp', 'uhqx', 'dmz', 'wsteer', 'wveto', 'afield', 'afveto', 'aagate', 'undeploy', 'bkeep', 'tkeep', 'tdem',
                   'rpoint', 'rfaf', 'bpick', 'trippick'):
            standoff.append(e)
        elif k in ('wflee', 'weaten', 'dstep', 'whold', 'hrun', 'hpick', 'spos', 'unstick', 'keepcap', 'tension', 'hride', 'rride'):
            worms.append(e)
        elif k in ('ascore', 'alone', 'scout'):
            ascores.append(e)
        elif k == 'acand':
            acands.append(e)
        elif k in ('lowpick', 'noregen', 'selfsup'):
            lowpicks.append(e)
        elif k in ('cpdis', 'mpgate', 'dfull'):
            armysz.append(e)
        elif k == 'rfail':
            rfails.append(e)
        elif k == 'cvbad':
            cvbads.append(e)
        elif k == 'rfirst':
            rfirsts.append(e)
        elif k == 'rnot':
            rnots.append(e)
        elif k == 'sweep':
            sweeps.append(e)
        elif k == 'wzb':
            wzbs.append(e)
        elif k == 'hunt':
            # hunt orders target an AIEntityGroup: match by faction + ArmyFight + time, not by target
            hunts[(f, e.get('act'), e.get('why'))] += 1
            cands = [o for o in reversed(orders) if o['ev'].get('f') == f and o['ev'].get('act') == 'ArmyFight'
                     and ((e.get('act') == 'start' and abs(o['t'] - t) < 0.5)
                          or (e.get('act') == 'abort' and o['end'] and abs(o['end'][0] - t) < 0.5))]
            if cands:
                o = cands[0]
                if e.get('act') == 'start' and e.get('ok') is False:
                    orders.remove(o)  # addOrder refused (armies busy): no order was created
                else:
                    o['hunt' if e.get('act') == 'start' else 'abort'] = e
        elif k == 'fight':
            fights.append(e)
        elif k == 'micro':
            micro[f][str(e.get('to'))] += 1
        elif k == 'snap':
            snaps[f] = e
            snap_hist[f].append(e)
        elif k == 'aw':
            aws.append(e)
        elif k == 'call':
            fn = e.get('fn')
            c = calls[fn]
            c['n'] += 1
            c['f'][f] += 1
            if 'r' in e:
                c['r'][str(e['r'])[:40]] += 1
            if fn == 'AIMilitary.tryGauge':
                g = e.get('a1') if isinstance(e.get('a1'), dict) else {}
                intents[f][(g.get('kind'), 'fired')] += 1
            elif fn == 'AIMilitary.onActionEnd':
                intents[f][(e.get('a1'), str(e.get('a2')))] += 1

    # odead rows carry the order's target (newer logs): every order's deaths are counted, 0 included
    if any(e.get('e') == 'odead' and e.get('tgt') is not None for e in events):
        for o in orders:
            o['ev']['_odt'] = True

    def row(o):
        e, p = o['ev'], o['pick'] or {}
        pw = p.get('_pw') or {}
        est = pw.get('b')
        h = o.get('hunt')
        if h and not p:  # hunt order: local power ours/theirs from behave.hunt
            H, M = h.get('H') or 0, h.get('M') or 0
            pw = {'my': float(M), 'en': float(H)}
            est = M / H if H else None
            p = {'sel': h.get('n'), 'cand': h.get('n'), 'req': 1.5}
        n0 = o['ev'].get('n') if isinstance(o['ev'].get('n'), float) else None
        fights_ = [x for x in o['fight'] if isinstance(x[2], float)]
        if o.get('rel') is not None:  # released armies leave the order alive: compare up to the release only
            fights_ = [x for x in fights_ if x[0] < o['rel']] or fights_[:1]
        own = (fights_[-1][2] - fights_[0][2]) / fights_[0][2] if fights_ and fights_[0][2] else 0
        fight = (f'{big(fights_[0][2])}/{big(fights_[0][3])}->{big(fights_[-1][2])}/{big(fights_[-1][3])} '
                 f'(me{change(fights_[0][2], fights_[-1][2])} en{change(fights_[0][3], fights_[-1][3])})') if fights_ else '-'
        if o.get('rel') is not None:
            fight += f" rel@{clock(o['rel'])}"
        if o['ev'].get('_odt'):
            fight += f" dead{o.get('dead', 0)}/{num(n0, 0)}"
        why = str(o['end'][1]) if o['end'] else 'open'
        dur = f"+{o['end'][0] - o['t']:.0f}s" if o['end'] else ''
        src = f"[{o['src']}]" if o['src'] and why != 'Success' else ''
        if o.get('abort'):
            src += f"[hunt abort: {o['abort'].get('why')}]"
        ok_end = ('Success', 'open', 'None') if o['ev'].get('act') == 'ArmyFight' else ('Success', 'open')  # a hunt ends None
        if o.get('dead') is not None or (n0 and o['ev'].get('_odt')):
            lost = 2 * o.get('dead', 0) >= (n0 or 1)  # deaths logged (odead with tgt): count them, not the power drop
        else:
            lost = own < -0.3
        bad = (isinstance(est, float) and est < 1.25) or lost or why not in ok_end
        flags = (' 3rdIgnored' if p.get('ign3rd') else '') + (' allIn' if p.get('allIn') else '')
        return (f"{'!' if bad else ' '}{clock(o['t'])} {str(e.get('f'))[:10]:<10} {str(e.get('sa') or e.get('act'))[:13]:<13} "
                f"{ent((o.get('hunt') or e).get('tgt'))[:22]:<22} {num(p.get('sel'), 0)}/{num(p.get('cand'), 0):<3} dist{num(o['dist'], 0):<5} "
                f"req{num(p.get('req'))} est{num(est)}({big(pw.get('my'))}/{big(pw.get('en'))}) {'>'.join(o['ph']) or '-'} "
                f"| {fight} | {why}{dur}{src}{flags}")

    mil = [o for o in orders if all_orders or str(o['ev'].get('type')) == 'Military']
    out.append(f'\n## Military orders ({len(mil)}; --all adds patrol/resupply/etc.)')
    out += [row(o) for o in mil]

    if intents:
        out.append('\n## Military intents: gauge fired -> action outcome (onActionEnd reason) per faction')
        for f in sorted(intents, key=str):
            out.append(f'{f}: ' + ', '.join(f'{k}:{r} x{n}' for (k, r), n in sorted(intents[f].items(), key=lambda kv: -kv[1])))

    if hunts:
        out.append('\n## Hunts (tools/rules): faction start / engage (left Regroup early) / abort reasons '
                   '(gone truce won leash home supply drift lost weak turret objective defend chase)')
        for f in sorted({k[0] for k in hunts}, key=str):
            out.append(f'{f}: ' + ', '.join(f"{a}{('-' + w) if w else ''} x{n}" for (ff, a, w), n in sorted(hunts.items(), key=str) if ff == f))

    if retreats:
        out.append('\n## Fight retreat checks (tools/rules): balance x100 raw*terrain*supply=adj vs 65; '
                   'flip = terrain or supply (our armies short of supply for the way home) changed the outcome; '
                   'sbal = sietch / renegade strike: balance lowered to the live order balance (adj = ob)')
        c = Counter()
        for e in retreats:
            raw, adj = e.get('raw') or 0, e.get('adj') or 0
            tadj = raw * (e.get('tf') or 100) / 100  # terrain only
            flip = ('' if e.get('act') == 'pursuit' else 'held by terrain' if raw <= 65 < adj
                    else 'retreat by terrain' if tadj <= 65 < raw
                    else 'retreat by supply' if adj <= 65 < tadj else '')
            c[(e.get('f'), e.get('act'), flip)] += 1
        out += [f'{f} {a}{(" (" + fl + ")") if fl else ""} x{n}' for (f, a, fl), n in sorted(c.items(), key=str)]
        for e in retreats[-12:]:
            out.append(f"  {clock(e['_t'])} {e.get('f')} {e.get('act')} raw{e.get('raw')} tf{e.get('tf')} "
                       f"sf{e.get('sf', 100)} adj{e.get('adj')} en{kpw(e.get('en'))} at ({e.get('x')},{e.get('y')})")

    if heals:
        out.append('\n## Heal target choices (tools/rules): stay/flee = army at its structure, '
                   'detour/avoid = structure penalised; h/m = hostile/own power near it')
        c = Counter((e.get('f'), e.get('act')) for e in heals)
        out.append(', '.join(f'{f}:{a} x{n}' for (f, a), n in sorted(c.items(), key=str)))
        for e in heals[-15:]:
            out.append(f"  {clock(e['_t'])} {e.get('f')} {e.get('act'):<6} {ent(e.get('s'))[:18]:<18} "
                       f"army {ent(e.get('a'))[:16]:<16} d{e.get('d', '-')} h{kpw(e.get('h'))} m{kpw(e.get('m'))}")

    if spaced:
        out.append('\n## Refused siege launches (tools/rules; logged once per faction per 10 s): faction why kind '
                   'target <- reason structure (defend = ours under siege, space = one we already run nearby, '
                   'retry = its last launch ended at once, weak = sietch / renegade-base pick below 1.5 x its side (our measure), floor = sietch / renegade-base pick with fewer armies than '
                   'its garrison; sgo = such a pick that passed, armies only, tf 1: not refused), count')
        out += [f'{f} {w} {kk} {tg} <- {nr} x{n}' for (f, w, kk, tg, nr), n in spaced.most_common(12)]

    if bunkers:
        out.append('\n## Bunker (tools/rules): Annex redirected to a village next to our main base: '
                   'faction target (vanilla pick), count (logged once per faction per 10 s)')
        c = Counter((e.get('f'), ent(e.get('tgt')), ent(e.get('was'))) for e in bunkers)
        out += [f'{f} {tg} (was {w}) x{n}' for (f, tg, w), n in c.most_common(12)]

    if strats:
        out += director(strats)

    if wzbs:
        out += stuck_fights(wzbs)

    if rallies:
        out.append('\n## Rally (tools/rules/rally.py): our side too weak at a structure: defenders gathered at a rally point '
                   'instead of fed one at a time: faction danger structure -> rally point, H their power, M ours (x terrain, + turrets), n sent')
        for e in rallies[-16:]:
            if e.get('act') == 'off':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} rally off")
            elif e.get('act') in ('commit', 'giveup', 'here'):
                extra = f" (Mall{kpw(e.get('Mall'))})" if e.get('act') == 'here' else ''
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {ent(e.get('s'))[:20]:<20} {e.get('act').upper():<22} "
                           f"H{kpw(e.get('H'))} M{kpw(e.get('M'))}{extra}")
            else:
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {ent(e.get('s'))[:20]:<20} -> {ent(e.get('r'))[:20]:<20} "
                           f"H{kpw(e.get('H'))} M{kpw(e.get('M'))} n{e.get('n')}")

    if gathers:
        out.append('\n## Gather (tools/rules/gather.py): leaders held in Engage until the pack is within 15 '
                   '(max 10 s per order): faction army -> target, d its distance, dmax the farthest counted, n; '
                   "stage (stage.py) = Regroup point moved out to 130 from the target, d = vanilla point's "
                   'distance, arr = had arrived there')
        for e in gathers[-16:]:
            if e.get('e') == 'stage':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {ent(e.get('a'))[:20]:<20} -> "
                           f"{ent(e.get('tgt'))[:20]:<20} stage d{e.get('d')} arr{e.get('arr')}")
                continue
            out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {ent(e.get('a'))[:20]:<20} -> {ent(e.get('tgt'))[:20]:<20} "
                       f"d{e.get('d')} dmax{e.get('dmax')} n{e.get('n')}")

    if rides:
        out.append('\n## Worm rides (rules/ride.py; docs/WORMRIDE-PLAN.md): plan = worm / walk chosen at addOrder (why: ride, '
                   'near < RIDE_MIN, stock = no free thumper, spare = short trip with the last free one, chase / grp = group fight not a contest; van = vanilla would '
                   'have ridden), ride = granted, req = refused (why = EReason, w = s waiting), stall = Worm steps turned to '
                   'Walk (n armies; why land = touched down off the landing point: walks the rest, off = not on it after 15 s, short = ride < 100 walked), tstk = thumper stock / claims')

        def _yes(v):
            return str(v).lower() == 'true'
        c = Counter((e.get('f'), 'worm' if _yes(e.get('worm')) else 'walk', e.get('why'), _yes(e.get('van')))
                    for e in rides if e['e'] == 'wplan')
        out.append('  plans: ' + ', '.join(f'{f}:{w}:{y} van={int(v)} x{n}' for (f, w, y, v), n in sorted(c.items(), key=str)))
        c = Counter((e.get('f'), e['e']) for e in rides if e['e'] in ('wride', 'wreq', 'wstall'))
        out.append('  results: ' + ', '.join(f'{f}:{k} x{n}' for (f, k), n in sorted(c.items(), key=str)))
        stk = defaultdict(list)
        for e in rides:
            if e['e'] == 'tstk':
                stk[e.get('f')].append(e)
        for f, es in sorted(stk.items(), key=str):
            out.append(f"  stock {str(f):<10} " + ' '.join(f"{clock(e['_t'])}:{num(e.get('n'), 1)}/{e.get('cl')}"
                                                          for e in es[::max(1, len(es) // 12)]))
        for e in [e for e in rides if e['e'] != 'tstk' and (e['e'] != 'wplan' or _yes(e.get('worm')) or _yes(e.get('van')))][-40:]:
            out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {e['e'][1:]:<5} {ent(e.get('tgt'))[:22]:<22} "
                       f"{str(e.get('why') or ''):<14} {e.get('sa') or e.get('act') or ''} d{e.get('d')} n{e.get('n', '')} "
                       f"stock{num(e.get('stock'), 1)} cl{e.get('cl', '')} w{e.get('w', '')} van{e.get('van', '')}")

    if opsev:
        out.append('\n## Operations (rules/ops.py, opsbrain.py; docs/OPERATIONS-PLAN.md): cast = ours (why: trigger), '
                   'van = vanilla launch that went through (Cell Search, Assassination, ...), veto = vanilla wanted to '
                   'launch a military op (blocked), fail = our cast refused, cell = held op dropped for a Cell Search slot, '
                   'gate = siege order op lists emptied, hold = held / started ops + Intel / agents (last per faction)')
        c = Counter((e.get('f'), e['e'][2:], e.get('op') or '') for e in opsev
                    if e['e'] in ('opcast', 'opfail', 'opveto', 'opvan', 'opcell', 'opgate'))
        out.append('  ' + ', '.join(f'{f}:{k}:{o} x{n}' if o else f'{f}:{k} x{n}'
                                    for (f, k, o), n in sorted(c.items(), key=str)))
        last = {}
        for e in opsev:
            if e['e'] == 'ophold':
                last[e.get('f')] = e
        buys = {}
        for e in opsev:
            if e['e'] == 'opbuy':
                cs_ = e.get('cand') or []
                if isinstance(cs_, str):
                    cs_ = [x for x in cs_.strip('[]').split(',') if x]
                buys.setdefault(e.get('f'), set()).update(cs_)
        for f, cs in sorted(buys.items(), key=str):
            out.append(f"  buyable {str(f):<10} {sorted(cs)}")
        for f, e in sorted(last.items(), key=str):
            out.append(f"  hold {str(f):<10} {clock(e['_t'])} intel{e.get('intel')} agents{e.get('ag')}/{e.get('agmax')} slots{e.get('slots')} "
                       f"held{e.get('held')} started{e.get('started')} inf{e.get('inf') or ''}")
        fz = [e for e in opsev if e['e'] == 'opfz']
        if fz:
            out.append('  fights seen (opfz, 20 s per faction): ' + ', '.join(
                f"{f}>{o} x{n}" for (f, o), n in sorted(Counter((e.get('f'), e.get('opp')) for e in fz).items(), key=str)))
        for e in [e for e in opsev if e['e'] == 'opcf']:
            out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} CF?   {ent(e.get('s'))[:22]:<22} pr{e.get('pr')} "
                       f"M{kpw(e.get('M'))} H{kpw(e.get('H'))}")
        for e in [e for e in opsev if e['e'] == 'drain']:
            out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} DRAIN {ent(e.get('s'))[:22]:<22} hp{e.get('hp')} "
                       f"from{e.get('hp0')} pr{e.get('pr')} n{e.get('n')}")
        for e in [e for e in opsev if e['e'] in ('opcast', 'opfail', 'opvan', 'opcell')][-30:]:
            out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {e['e'][2:]:<4} {str(e.get('op') or e.get('drop')):<22} "
                       f"{(str(e.get('why') or '') + ('/' + _ereason(e.get('r')) if e.get('r') is not None else '')):<9} {ent(e.get('s') or e.get('zs'))[:22]:<22} "
                       f"B{e.get('B')} M{kpw(e.get('M'))} H{kpw(e.get('H'))}")

    if standoff:
        out.append('\n## Treaty scope / patrol gate / turret steering (tools/rules/peace.py, strand.py, build.py): '
                   'treaty skip = a third-party treaty no longer cancels our orders, narrow = only orders on the other '
                   'party; patrol = vanilla Patrol dropped: hostiles h at the village > 1.3 x m (ours there + the group); '
                   'turret = MissileBattery lifted at a village with at-war power h standing near (sc vanilla score); '
                   'tveto = vanilla wanted a MissileBattery (sc) where no turret rule of ours calls for one: dropped; '
                   'aring = ring village scored although vanilla put it <= 0 (v0); pkeep = ring village kept from the Pillage gauge; '
                   'fpeace = forced Non-aggression Pact on the attacker of a conceded village (r 1 = sent); '
                   'pannex = an Annex done by the Atreides PeacefullyAnnex ability instead of armies (inf = Influence before); '
                   'dmz on = at war, the neighbour holds n villages in regions next to ours (taken, not pillaged), dmz war = '
                   'truce broken by declareWar (cap = border villages it was capturing, r 1 = Success); '
                   'uhqcap = no new Underworld HQ (n ours >= cap); uhqres = no new HQ: Authority left after it < cheapest Annex (au, left, cmin); uhqp = HQ placement (cand candidates, kept, newf in factions '
                   'hosting none of ours); uhqx = HQ extension score (k, sc ours (NaN = skip), van vanilla); '
                   'afield = Airfield lifted on a remote village (d from our base, hops); afveto = vanilla Airfield dropped '
                   '(behind our base / spaced: another of ours within AF_SPACING); aagate = Fremen AA turret install refused '
                   '(nothing flying in reach); undeploy = installed AA turret uninstalled (air = flyers in reach); '
                   'bkeep = siege kept after its lone besieger died; tkeep = Military order kept when another order took '
                   'one army before Action; tdem = building demolished for a front battery')
        c = Counter((e.get('f'), e['e'], e.get('act') or '') for e in standoff)
        out.append('  ' + ', '.join(f'{f}:{k}{":" + a if a else ""} x{n}' for (f, k, a), n in sorted(c.items(), key=str)))
        for e in standoff[-16:]:
            if e['e'] == 'treaty':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} treaty {e.get('act')} {e.get('a')} {e.get('b') or ''}")
            elif e['e'] == 'fpeace':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} fpeace -> {e.get('to')} at {ent(e.get('s'))[:22]} r{e.get('r')}")
            elif e['e'] == 'uhqcap':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} uhqcap n{e.get('n')} cap{e.get('cap')}")
            elif e['e'] == 'uhqres':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} uhqres n{e.get('n')} au{num(e.get('au'), 0)} left{num(e.get('left'), 0)} cmin{num(e.get('cmin'), 0)}")
            elif e['e'] == 'uhqp':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} uhqp cand{e.get('cand')} kept{e.get('kept')} newf{e.get('newf')}")
            elif e['e'] == 'uhqx':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} uhqx {ent(e.get('s'))[:22]:<22} {e.get('k')} sc{e.get('sc')} van{e.get('van')}")
            elif e['e'] == 'dmz':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} dmz {e.get('act')} vs {e.get('vs')} n{e.get('n')}"
                           + (f" cap{e.get('cap')} r{e.get('r')} M{kpw(e.get('M'))} E{kpw(e.get('E'))}" if e.get('act') == 'war' else ''))
            elif e['e'] == 'pannex':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} pannex {ent(e.get('tgt'))[:22]} inf{num(e.get('inf'), 0)} r{e.get('r')}")
            elif e['e'] == 'dall':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} dall {ent(e.get('s'))[:22]} n{e.get('n')} (committed: Defense all-in)")
            elif e['e'] == 'rejoin':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} rejoin {ent(e.get('tgt'))[:22]} {ent(e.get('a'))[:18]} d{e.get('d')} pr{e.get('pr')} n{e.get('n')} (nobody occupied: ArmySiege re-sent)")
            elif e['e'] == 'airpick':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} airpick {ent(e.get('tgt'))[:22]} n{e.get('n')} sim{e.get('sim')} (flyers-only pick emptied)")
            elif e['e'] == 'pagate':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} pagate {ent(e.get('tgt'))[:22]} (vanilla peaceful annex refused)")
            elif e['e'] == 'sdrop':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} sdrop {e.get('act')} {e.get('why') or ''} "
                           f"{ent(e.get('tgt') or e.get('a'))[:22]} sa{e.get('sa')} arr{e.get('arr')} n{e.get('n')} "
                           f"sup{e.get('sup')} land{e.get('land')} pw{kpw(e.get('pw'))}")
            elif e['e'] == 'patrol':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} patrol {ent(e.get('s'))[:22]:<22} "
                           f"{ent(e.get('a'))[:20]} n{e.get('n')} h{kpw(e.get('h'))} m{kpw(e.get('m'))} {e.get('why') or ''}")
            elif e['e'] == 'rpoint':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} rpoint {e.get('why')} {ent(e.get('s'))[:22]:<22} "
                           f"h{kpw(e.get('h'))} m{kpw(e.get('m'))} (recruit point moved off vanilla's)")
            elif e['e'] == 'bpick':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} bpick  {ent(e.get('s'))[:22]:<22} {e.get('k')} sc{e.get('sc')} (building picked, vanilla score)")
            elif e['e'] == 'rfaf':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} rfaf   {ent(e.get('s'))[:22]:<22} (remote spice village: Airfield before Refinery)")
            elif e['e'] == 'odead':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} odead  {ent(e.get('a'))[:22]:<22} hp{e.get('hp')} ph{e.get('ph')} n{e.get('n')}")
            elif e['e'] == 'okeep':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} okeep  order kept with {e.get('n')} armies (ph{e.get('ph')})")
            elif e['e'] in ('aring', 'pkeep'):
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {e['e']:<6} {ent(e.get('v'))[:22]:<22} v0{e.get('v0', '')}")
            elif e['e'] in ('afield', 'afveto'):
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {e['e']:<6} {ent(e.get('s'))[:22]:<22} "
                           f"{e.get('why') or ''} sc{e.get('sc')} d{e.get('d')} hops{e.get('hops', '-')}")
            elif e['e'] in ('aagate', 'undeploy'):
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {e['e']:<8} {ent(e.get('a'))[:22]:<22} "
                           + (f"ok{e.get('ok')} nm{e.get('nm')} sup{e.get('sup')} air{e.get('air')}" if e['e'] == 'undeploy' else ''))
            elif e['e'] in ('wsteer', 'wveto'):
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {e['e']:<6} {ent(e.get('s'))[:22]:<22} {e.get('k')} "
                           f"{e.get('why') or ''} sc{e.get('sc')} m{e.get('m', '')} disc{e.get('disc', '')}")
            elif e['e'] in ('bkeep', 'tkeep'):
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {e['e']} {ent(e.get('tgt') or e.get('a'))[:22]:<22} n{e.get('n')} ph{e.get('ph')}")
            elif e['e'] == 'tdem':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} tdem   {ent(e.get('s'))[:22]:<22} {e.get('k')} n{e.get('n')} hops{e.get('hops')}")
            elif e['e'] == 'tveto':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} tveto  {ent(e.get('s'))[:22]:<22} "
                           f"sc{e.get('sc')} n{e.get('n')} hops{e.get('hops')}")
            else:
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} turret {ent(e.get('s'))[:22]:<22} "
                           f"h{kpw(e.get('h'))} sc{e.get('sc')}")

    if ascores:
        out.append('\n## Annex value (tools/rules/annex.py): our best Annex target (s = score after special / '
                   'compactness / cost ratio / first spice) vs vanilla\'s best (v0 its vanilla score, vs now); '
                   'c / cmin = its Authority cost / cheapest candidate (once per faction per 30 s)')
        for e in ascores[-16:]:
            if e['e'] == 'scout':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {ent(e.get('tgt'))[:22]:<22} SCOUT wait {e.get('w')} s ({e.get('n')} candidates, need {e.get('need')})")
                continue
            if e['e'] == 'alone':
                out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {ent(e.get('tgt'))[:22]:<22} s{e.get('s')} c{e.get('c')} LONE candidate, nothing special: dropped")
                continue
            same = ent(e.get('tgt')) == ent(e.get('vb'))
            out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {ent(e.get('tgt'))[:22]:<22} s{e.get('s')} c{e.get('c')}/{e.get('cmin')} "
                       + ('= vanilla' if same else f"<- vanilla {ent(e.get('vb'))[:22]} v0 {e.get('v0')} now {e.get('vs')}") + f" n{e.get('n')}" + (f" dd{e.get('dd')}" if e.get('dd') else '') + (f" HOLD{e.get('hold')}" if e.get('hold') else '')
                       + (f" ring {ent(e.get('rt'))[:18]} s{e.get('rs')} dd{e.get('rdd')} h{e.get('ddh')}" if e.get('rt') and ent(e.get('rt')) != ent(e.get('tgt')) else ''))

    if acands:
        out.append('\n## Annex candidates (tools/rules/annex.py `acand`, every candidate of one scoring per faction per 30 s): '
                   'v0 vanilla score, hops = zones from our main base (vanilla -10 each, capped at 3), sp special bonus, '
                   'cf compactness x100, cen centre factor x100, dd Fremen ring x100, c / cmin cost, s final; n candidates')
        for e in acands[-40:]:
            out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {ent(e.get('tgt'))[:22]:<22} v0 {e.get('v0')} h{e.get('hops')} "
                       f"sp{e.get('sp')} cf{e.get('cf')} cen{e.get('cen')} dd{e.get('dd')} c{e.get('c')}/{e.get('cmin')} "
                       f"s{e.get('s')} n{e.get('n')}")

    if lowpicks:
        out.append('\n## Low-life picks (tools/rules/heal.py pick-life): worn armies kept out of vanilla mission picks '
                   '(once per army per 30 s), noregen = no-regen army kept out of the Resupply query: faction army src')
        c = Counter((e.get('f'), ent(e.get('a'))[:22], e.get('src') or ('selfsup' if e.get('e') == 'selfsup' else 'noregen')) for e in lowpicks)
        out += [f'  {f} {a} {s} x{n}' for (f, a, s), n in c.most_common(12)]

    if rfails:
        try:
            from pathlib import Path as _P
            crumbs = json.loads((_P(__file__).resolve().parents[1] / 'work' / 'crumbs.json').read_text(encoding='utf-8'))
        except Exception:
            crumbs = []
        out.append('\n## RULE FAILURES (step probe): a strat / hunt run died silently (exception swallowed by its trap) '
                   'at the call on this source line; rows at most 1 / 30 s per rule and faction')
        c = Counter((e.get('r'), e.get('f'), e.get('at')) for e in rfails)
        for (r, f, at), n in c.most_common(10):
            ai = int(at) if isinstance(at, (int, float)) else -1  # parsed as a float (283.0)
            src = crumbs[ai] if 0 <= ai < len(crumbs) else f'step {at}'
            first = min(e['_t'] for e in rfails if (e.get('r'), e.get('f'), e.get('at')) == (r, f, at))
            out.append(f'  {r} {f} at {src} x{n} (first {clock(first)})')

    if cvbads:
        out.append('\n## Turret cover read failures (world.py aimod_cover1 trap): structure that threw, skipped '
                   '(asking faction, own)')
        c = Counter((e.get('f'), ent(e.get('s'))[:30], e.get('own')) for e in cvbads)
        for (f, s, own), n in c.most_common(10):
            out.append(f'  {f} {s} own={own} x{n}')
    if rfirsts:
        out.append('\n## Spice first (build.py): Refinery lifted on a spice village without one, other buildings '
                   'there dropped (sc = vanilla score)')
        for e in rfirsts[-12:]:
            out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} {ent(e.get('s'))[:24]:<24} sc{num(e.get('sc'))}")
    if rnots:
        try:
            from pathlib import Path as _P
            rn = json.loads((_P(__file__).resolve().parents[1] / 'work' / 'eresult.json').read_text(encoding='utf-8'))
        except Exception:
            rn = []
        out.append('\n## Spice villages where no Refinery can go up (build.py `rnot`: checkAddUpgrade result; '
                   'VillageUpgradesLimitReached = full: needs a demolition path)')
        c = Counter((e.get('f'), ent(e.get('s'))[:24], e.get('r')) for e in rnots)
        for (f, s, rr), n in c.most_common(12):
            ri = int(rr) if isinstance(rr, (int, float)) else -1
            out.append(f"  {f} {s} {rn[ri] if 0 <= ri < len(rn) else rr} x{n}")

    if sweeps:
        out.append('\n## Map sweep (sweep.py): keys held in our maps over time, the two largest maps (name keys)')
        step = max(1, len(sweeps) // 10)
        for e in sweeps[::step] + ([sweeps[-1]] if (len(sweeps) - 1) % step else []):
            out.append(f"  {clock(e['_t'])} {str(e.get('f')):<10} keys{e.get('keys')} removed{e.get('n')} "
                       f"{e.get('m1', '-')} {e.get('k1', '')} {e.get('m2', '-')} {e.get('k2', '')}")
    if armysz:
        out.append('\n## Army size (tools/rules/army.py): cpdis = temporary army disbanded on a CP overflow '
                   '(cp its upkeep, free = net CP before); mpgate = unit pick that vanilla Manpower goals would have blocked; '
                   'dfull = vanilla wanted to send every idle army to a defense it judged too strong because CP was full: blocked')
        out.append('  ' + ', '.join(f'{f} {k} x{n}' for (f, k), n in Counter((e.get('f'), e['e']) for e in armysz).most_common()))
        for e in [x for x in armysz if x['e'] == 'cpdis'][-10:]:
            out.append(f"  {clock(e['_t'])} {e.get('f')} cpdis {ent(e.get('a'))[:22]} cp{e.get('cp')} free{e.get('free')}")

    if worms:
        out.append('\n## Worms / deep desert (tools/rules/worm.py, desert.py): dstep = siege army moved off the deep desert to the village; wflee = worm-targeted army sent to rock (rock 0: away from the '
                   'worm), d to the point, w worm distance; weaten = army eaten (fled = s since its wflee, -1 never); hold = moved army kept out of vanilla picks while the worm is near; HARVESTER RUN = outgunned harvester sent to a safe field')
        for e in worms[-20:]:
            if e['e'] == 'wflee':
                out.append(f"  {clock(e['_t'])} {e.get('f')} flee  {ent(e.get('a'))[:22]:<22} rock{int(bool(e.get('rock')))} "
                           f"d{e.get('d')} w{e.get('w')} ok{int(bool(e.get('ok')))}")
            elif e['e'] == 'spos':
                out.append(f"  {clock(e['_t'])} {e.get('f')} siege-pos {ent(e.get('a'))[:22]:<22} at {ent(e.get('tgt'))[:18]} off guns of {ent(e.get('es'))[:18]} cv{kpw(e.get('cv'))}")
            elif e['e'] == 'tension':
                out.append(f"  {clock(e['_t'])} {e.get('f')} TENSION {ent(e.get('v'))[:18]} <-> {ent(e.get('w'))[:18]} T{e.get('T')}% d{e.get('d')}")
            elif e['e'] in ('hride', 'rride'):
                out.append(f"  {clock(e['_t'])} {e.get('f')} IN TRANSIT ({'hunt' if e['e'] == 'hride' else 'raid'}) {ent(e.get('a'))[:22]}: not re-judged until it lands")
            elif e['e'] == 'keepcap':
                out.append(f"  {clock(e['_t'])} {e.get('f')} KEEP-CAPTURE {ent(e.get('a'))[:22]:<22} stays at {ent(e.get('v'))[:18]} (not sent to defend {ent(e.get('s'))[:18]})")
            elif e['e'] == 'unstick':
                out.append(f"  {clock(e['_t'])} {e.get('f')} UNSTICK {ent(e.get('a'))[:22]:<22} at {ent(e.get('tgt'))[:18]} still {e.get('st')} s ok{int(bool(e.get('ok')))}")
            elif e['e'] == 'whold':
                out.append(f"  {clock(e['_t'])} {e.get('f')} hold  {ent(e.get('a'))[:22]:<22} (worm near: kept out of {e.get('src')})")
            elif e['e'] == 'hrun':
                out.append(f"  {clock(e['_t'])} {e.get('f')} HARVESTER RUN {ent(e.get('a'))[:22]:<22} -> {ent(e.get('s'))[:22] if e.get('s') else 'main base'} "
                           f"H{kpw(e.get('H'))} M{kpw(e.get('M'))} ok{int(bool(e.get('ok')))}")
            elif e['e'] == 'hpick':
                out.append(f"  {clock(e['_t'])} {e.get('f')} harvester field {ent(e.get('a'))[:22]:<22} -> {ent(e.get('s'))[:22]} "
                           f"danger{e.get('dg')} d{e.get('d')} (chosen field still dangerous)")
            elif e['e'] == 'dstep':
                out.append(f"  {clock(e['_t'])} {e.get('f')} desert-step {ent(e.get('a'))[:22]:<22} -> {ent(e.get('tgt'))[:22]} d{e.get('d')} ok{int(bool(e.get('ok')))}")
            else:
                out.append(f"  {clock(e['_t'])} {e.get('o')} EATEN {ent(e.get('a'))[:22]:<22} fled{e.get('fled')}")

    if peaces:
        out.append('\n## Peace gate (tools/rules/peace.py): treaty offers from an at-war faction refused while our '
                   'siege on its structure is in Engage/Action: faction <- sender, target, siege action, phase')
        for e in peaces[-12:]:
            out.append(f"  {clock(e['_t'])} {e.get('f')} <- {e.get('from')} {ent(e.get('tgt'))[:22]:<22} "
                       f"{e.get('sa')} ph{e.get('ph')} treaties{e.get('nt')}")

    if raids:
        out.append('\n## Raids (tools/rules/raid.py): pillage with idle armies (neutral or at-war villages, not the '
                   'next Annex); h = their threat+cover+militia, m = our raid force, hh/ms = hostile/our power near home')
        starts = [e for e in raids if e.get('act') == 'start']
        refused = [e for e in raids if e.get('act') == 'refuse']
        aborts = [e for e in raids if e.get('act') == 'abort']
        splits = [e for e in raids if e.get('act') in ('split', 'keep') or e['e'] == 'release']
        raids = [e for e in raids if e['e'] == 'raid']
        owned = lambda e: isinstance(e.get('tgt'), dict) and e['tgt'].get('o') not in (None, 'null')
        out.append('Enemy villages (at-war owner) / all: ' + ', '.join(
            f"{a} {sum(owned(e) for e in raids if e.get('act') == a)}/{sum(1 for e in raids if e.get('act') == a)}"
            for a in ('start', 'refuse', 'abort')))
        for e in starts[-12:]:
            out.append(f"  {clock(e['_t'])} {e.get('f')} {ent(e.get('tgt'))[:22]:<22} n{e.get('n')} dm{e.get('dm')} "
                       f"sd{e.get('sd')} h{kpw(e.get('H'))} m{kpw(e.get('M'))} hh{kpw(e.get('hh'))} "
                       f"ms{kpw(e.get('ms'))} ax {ent(e.get('ax'))[:16]}"
                       f"{'' if e.get('ok') is not False else ' REFUSED'}{' RECOVER' if e.get('rec') is True else ''}")
        if aborts:
            c = Counter((e.get('f'), e.get('why')) for e in aborts)
            out.append('Aborted pillages (defend = our besieged structure needs the armies, home = hostiles nearer our '
                       'land than the raid, weak = relief at the target): '
                       + ', '.join(f'{f} {w} x{n}' for (f, w), n in c.most_common(10)))
            for e in aborts[-10:]:
                out.append(f"  {clock(e['_t'])} {e.get('f')} {e.get('why'):<6} {ent(e.get('tgt'))[:20]:<20} "
                           f"ph{e.get('ph')} pr{e.get('pr')}% n{e.get('n')} sd{num(e.get('sd'), 0)} "
                           f"h{kpw(e.get('H'))} m{kpw(e.get('M'))}")
        if splits:
            c = Counter((e.get('f'), e.get('why') or 'safe') for e in splits)
            out.append('Released armies (occupation under way, one army finishes it; release = no danger at the target, '
                       'split defend / home = our structure needs them; n released of the order armies): '
                       + ', '.join(f'{f} {w} x{n}' for (f, w), n in c.most_common(10)))
            for e in splits[-10:]:
                out.append(f"  {clock(e['_t'])} {e.get('f')} {(e.get('why') or 'safe'):<6} {ent(e.get('tgt'))[:20]:<20} "
                           f"{e.get('sa')} pr{e.get('pr')}% released {e.get('rel') or e.get('n')} of "
                           f"{e.get('of') or e.get('n')}")
        if refused:
            c = Counter((e.get('f'), e.get('why'), ent(e.get('tgt'))) for e in refused)
            out.append('Refused (nearest candidate, once per faction per 30 s; ready = no army passes life/supply, '
                       'weak = M < 1.5 x (H armies + C turrets + Mi militia) / tf, home = ms x 1.3 < 1.5 x hh): '
                       + ', '.join(f'{f} {w} {tg} x{n}' for (f, w, tg), n in c.most_common(10)))
            for e in refused[-10:]:
                out.append(f"  {clock(e['_t'])} {e.get('f')} {e.get('why'):<5} {ent(e.get('tgt'))[:20]:<20} "
                           f"n{num(e.get('n'), 0)}/{num(e.get('nr'), 0)} dm{num(e.get('dm'), 0)} sd{num(e.get('sd'), 0)} "
                           f"h{kpw(e.get('H'))} c{kpw(e.get('C'))} mi{kpw(e.get('Mi'))} m{kpw(e.get('M'))} "
                           f"tf{num(e.get('tf'), 0)} hh{kpw(e.get('hh'))} ms{kpw(e.get('ms'))} "
                           f"ax {ent(e.get('ax'))[:16]} nc{num(e.get('nc'), 0)}"
                           f"{' RECOVER' if e.get('rec') is True else ''}")

    if discs:
        out.append('\n## Refused Discovery trips (tools/rules): lone army vs at-war threat at the world event; '
                   'FAR = round trip beyond its supply budget (dl = event to our land); faction target count (logged once per event per 30 s)')
        c = Counter((e.get('f'), ent(e.get('tgt'))) for e in discs)
        out += [f'{f} {tg} x{n}' for (f, tg), n in c.most_common(12)]
        far = Counter(e.get('f') for e in discs if (e.get('dl') or 0) > 0)
        if far:
            out.append('FAR refusals: ' + ', '.join(f'{f} x{n}' for f, n in far.most_common()))
        for e in discs[-8:]:
            out.append(f"  {clock(e['_t'])} {e.get('f')} {ent(e.get('tgt'))[:20]:<20} army {ent(e.get('army'))[:16]:<16} "
                       f"h{kpw(e.get('H'))} m{kpw(e.get('M'))} tf{e.get('tf')}" + (f" FAR dl{num(e.get('dl'), 0)}" if (e.get('dl') or 0) > 0 else ''))

    if stops:
        out.append('\n## Military orders stopped, by code path: faction src reason count')
        out += [f'{f} {src} {why} x{n}' for (f, src, why), n in stops.most_common(12)]

    if fights or micro:
        out.append(f'\n## Fights: {len(fights)} started (AIUnits.initFight). Micro switches per faction:')
        for f in sorted(micro, key=str):
            out.append(f'{f}: ' + ', '.join(f'{k} x{n}' for k, n in micro[f].most_common()))
        for e in fights[-8:]:
            out.append(f"  fight {clock(e['_t'])} {e.get('f')} at ({num(e.get('wx'), 0)},{num(e.get('wy'), 0)}) entities={num(e.get('ents'), 0)} ok={e.get('ok')}")

    if snaps:
        out.append('\n## Last daily snapshot per AI faction')
        for f, e in sorted(snaps.items(), key=lambda kv: str(kv[0])):
            g = e.get('gauges')
            gs = str(g)[:120] if g is not None else '-'
            out.append(f"{f} @{clock(e['_t'])}: aggr={num(e.get('aggr'))} armies={num(e.get('armies'), 0)} structs={num(e.get('structs'), 0)} gauges={gs}")
        if any(e.get('au') is not None for h in snap_hist.values() for e in h):
            out.append('Stocks every ~5 min (Authority stock / net rate, Influence): a stalled Annex gauge with a low stock = Authority-starved')
            for f, h in sorted(snap_hist.items(), key=lambda kv: str(kv[0])):
                pts, last = [], -1e9
                for e in h:
                    if e.get('au') is not None and e['_t'] - last >= 290:
                        pts.append(f"{clock(e['_t'])} {num(e.get('au'), 0)}/{num(e.get('aup'), 1)} i{num(e.get('inf'), 0)}")
                        last = e['_t']
                out.append(f'{f}: ' + ', '.join(pts))
        if any(e.get('cp') is not None for h in snap_hist.values() for e in h):
            out.append('Army size every ~5 min (CP used/cap, Manpower stock; rules/army.py): used < cap = army not maxed')
            for f, h in sorted(snap_hist.items(), key=lambda kv: str(kv[0])):
                pts, last = [], -1e9
                for e in h:
                    if e.get('cp') is not None and e['_t'] - last >= 290:
                        cp, cpf = e.get('cp') or 0, e.get('cpf') or 0
                        pts.append(f"{clock(e['_t'])} {num(cp - cpf, 0)}/{num(cp, 0)} mp{num(e.get('mp'), 0)}")
                        last = e['_t']
                out.append(f'{f}: ' + ', '.join(pts))

    if aws:
        out += awareness(aws)

    other = {fn: c for fn, c in calls.items() if fn not in ('AIMilitary.tryGauge', 'AIMilitary.onActionEnd')}
    if other:
        out.append('\n## Other traced calls (testbed/ailog.json): fn count by faction | results')
        for fn, c in sorted(other.items()):
            rate = c['n'] / minutes
            warn = f' !FLOOD {rate:.0f}/min: remove from ailog.json' if rate > 30 else ''
            res = ', '.join(f'{r} x{n}' for r, n in c['r'].most_common(4))
            out.append(f"{fn}: {', '.join(f'{f} x{n}' for f, n in c['f'].most_common())}{(' | ' + res) if res else ''}{warn}")

    if marks:
        out.append('\n## Marks (L key): military orders active within 60s; use `mod log --around MM:SS` for the full timeline')
        for m in marks:
            near = [o for o in mil if o['t'] <= m + 5 and (o['end'] is None or o['end'][0] >= m - 60)]
            nf = [e for e in fights if abs(e['_t'] - m) <= 60]
            out.append(f'MARK {clock(m)}: {len(near)} military orders, {len(nf)} fights started within 60s')
            out += ['  ' + row(o) for o in near]

    if rejected:
        out.append('\n## Rejected picks (no sufficient army): faction target atk/def count req-range')
        for (f, tgt, kind), r in sorted(rejected.items(), key=lambda kv: -kv[1]['n'])[:10]:
            rq = f"{min(r['req']):.2f}-{max(r['req']):.2f}" if r['req'] else '-'
            out.append(f'{f} {tgt} {kind} x{r["n"]} req {rq}')

    # order loops: a Cancel (order with units) followed within 2 s game by a new order of the same faction and type
    # (retreat / Defense tug, re-picked armies): flip-flop and command spam
    last, loops, lwhen = {}, Counter(), defaultdict(list)
    for e in events:
        if e.get('e') not in ('stop', 'order') or not (e.get('n') or 0) or not isinstance(e.get('g'), (int, float)):
            continue
        key = (e.get('f'), str(e.get('type')).split('(')[0])
        if e['e'] == 'stop' and e.get('why') == 'Cancel':
            last[key] = (e['g'], e.get('src'), e.get('ph'))
        elif e['e'] == 'order' and key in last and e['g'] - last[key][0] <= 2:
            lk = key + (last[key][1], last[key][2])
            loops[lk] += 1
            lwhen[lk].append(e['g'])
    if loops:
        out.append('\n## Order loops (Cancel then the same faction / type re-ordered within 2 s; >= 10 flagged)')
        for (f, t, src, ph), n in loops.most_common(8):
            out.append(f"{'!' if n >= 10 else ''}{f} {t} x{n} (cancel by {src} ph {ph}) at {', '.join(sorted({clock(g) for g in lwhen[(f, t, src, ph)]})[:6])}")
    # Waiting-cancel streaks per target (vanilla can't path there; re-issued orders may log n 0, which the loop count
    # above skips: Harkonnen's Resupply to Carthag was cancelled in Waiting 860 times, match 2026-10-05 03:55)
    wc = Counter()
    for e in events:
        if e.get('e') == 'stop' and e.get('src') == '<none>' and e.get('ph') == 1 and e.get('why') == 'Cancel':
            wc[(e.get('f'), str(e.get('type')).split('(')[0], ent(e.get('tgt')))] += 1
    wbig = [(n, k) for k, n in wc.items() if n >= 20]
    if wbig:
        out.append('\n## Waiting-cancel streaks (orders cancelled in Waiting >= 20x on one target: no path / refused plan)')
        out.append(', '.join(f"{'!' if n >= 50 else ''}{f}:{t}>{tg} x{n}" for n, (f, t, tg) in sorted(wbig, reverse=True)[:8]))
    churn = Counter((o['ev'].get('f'), str(o['ev'].get('type')).split('(')[0]) for o in orders if o not in mil)
    if churn:
        out.append('\n## Other orders (count, per game-minute; >5/min flagged as possible order loop)')
        out.append(', '.join(f"{'!' if n / minutes > 5 else ''}{f}:{t}={n} ({n / minutes:.1f}/min)" for (f, t), n in sorted(churn.items(), key=str)))
    return '\n'.join(out)


def awareness(aws):
    """Summary of `aw` events: threat level per faction, enemy siege actions near us, enemy armies on sand."""
    out = ['\n## Enemy army awareness (aw: every 10 s, hostile armies within 600 of our structures or armies, or visible anywhere)',
           'faction: scans, scans with hostiles, max hostile power near vs own total at that moment']
    per = defaultdict(list)
    for e in aws:
        per[e.get('f')].append(e)
    for f, es in sorted(per.items(), key=lambda kv: str(kv[0])):
        hot = [e for e in es if (e.get('n') or 0) > 0]
        top = max(hot, key=lambda e: e.get('en') or 0, default=None)
        peak = f"{big(top.get('en'))} vs mine {big(top.get('mine'))} @{clock(top['_t'])}" if top else '-'
        out.append(f'{f}: {len(es)} scans, {len(hot)} with hostiles, peak {peak}')
    sieges, sand, close, far = {}, Counter(), {}, Counter()
    for e in aws:
        scan = defaultdict(lambda: [0, 1 << 30])  # key -> [summed enemy pw on this target, closest dist]
        for a in e.get('a') or []:
            if not isinstance(a, dict):
                continue
            if a.get('sand'):
                sand[(e.get('f'), aw_owner(a))] += 1
            if (a.get('d') or 0) > 600 and (a.get('da') or 0) > 600:
                far[(e.get('f'), aw_owner(a))] += 1
            if (a.get('da') or 1e9) <= 300:
                key = (e.get('f'), a.get('na'), my_task(a).strip() or 'idle', aw_owner(a))
                c = close.setdefault(key, {'t0': e['_t'], 't1': e['_t'], 'da': a['da'], 'pw': 0})
                c['t1'], c['da'], c['pw'] = e['_t'], min(c['da'], a['da']), max(c['pw'], a.get('pw') or 0)
            if a.get('sa') or a.get('ct') or a.get('oc'):
                key = (e.get('f'), aw_owner(a), a.get('sa') or '-', a.get('tgt') or a.get('ct') or a.get('oc'))
                scan[key][0] += a.get('pw') or 0
                scan[key][1] = min(scan[key][1], a.get('d') or 0)
        for key, (pw, d) in scan.items():
            s = sieges.setdefault(key, {'t0': e['_t'], 't1': e['_t'], 'd': d, 'pw': 0, 'mine': 0})
            s['t1'], s['d'] = e['_t'], min(s['d'], d)
            s['pw'] = max(s['pw'], pw)
            s['mine'] = max(s['mine'], e.get('mine') or 0)
    if sieges:
        out.append('Enemy siege actions near us (observer <- enemy action>target: seen from-to, closest dist, '
                   'max enemy pw on it, our total army pw; ! = we had >2x their power)')
        for (f, o, sa, tgt), s in sorted(sieges.items(), key=lambda kv: kv[1]['t0']):
            flag = '!' if s['mine'] > 2 * s['pw'] > 0 else ' '
            out.append(f"{flag}{f} <- {o} {sa}>{tgt}: {clock(s['t0'])}-{clock(s['t1'])} d{num(s['d'], 0)} "
                       f"pw{big(s['pw'])} mine{big(s['mine'])}")
    if close:
        out.append('Hostile armies within 300 of our armies (observer our-army task <- enemy: seen from-to, closest, max enemy army pw)')
        for (f, na, task, o), c in sorted(close.items(), key=lambda kv: kv[1]['t0'])[:20]:
            out.append(f"  {f} {na} {task} <- {o}: {clock(c['t0'])}-{clock(c['t1'])} d{num(c['da'], 0)} pw{big(c['pw'])}")
    if far:
        out.append('Seen far away only (visible, >600 from our structures and armies): ' +
                   ', '.join(f'{f}<-{o} x{n}' for (f, o), n in far.most_common(8)))
    raiders = {}
    for e in aws:
        for a in e.get('a') or []:
            if isinstance(a, dict) and a.get('rk'):
                key = (e.get('f'), aw_owner(a), a.get('near'))
                r = raiders.setdefault(key, {'t0': e['_t'], 't1': e['_t'], 'd': a.get('d') or 0, 'pw': 0})
                r['t1'], r['d'] = e['_t'], min(r['d'], a.get('d') or 0)
                r['pw'] = max(r['pw'], a.get('pw') or 0)
    if raiders:
        out.append('Neutral raiders within 600 of us (observer <- raid:kind (* = targets us) near our structure: seen from-to, '
                   'closest, max army pw)')
        for (f, o, near), r in sorted(raiders.items(), key=lambda kv: kv[1]['t0'])[:30]:
            out.append(f"  {f} <- {o} @{near}: {clock(r['t0'])}-{clock(r['t1'])} d{num(r['d'], 0)} pw{big(r['pw'])}")
    if sand:
        out.append('Hostile armies seen on sand (thumper/worm candidates): ' +
                   ', '.join(f'{f}<-{o} x{n}' for (f, o), n in sand.most_common(8)))
    return out
