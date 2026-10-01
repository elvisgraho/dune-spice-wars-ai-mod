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
  hunt  : act (start|abort|engage), why (abort: gone truce leash home supply drift lost weak turret objective defend chase), T
          (enemy turret cover at the anchor / group, power units; included in H), tgt (prey / first
          member; the village for a contest), H, M, n, ng (group size), ok, sd (dist to our land), dn (our nearest order
          army), dm (start: our nearest free army), anc (start: the besieged village for a contest, else the prey),
          obj (abort objective: the besieged village the chase yields to), x, y (tools/rules: attack on an exposed
          army or contest of a siege; H = threat around it, M = our free power in reach (abort: order power), n armies
          sent; the order itself is a Military ArmyFight order). engage: the order left Regroup early because the
          armies within LOCAL of the core (member nearest our land) already pass the entry test (M = their power)
  retreat: act (retreat|hold|recall|pursuit), raw, tf, sf, adj (fight balance x100: vanilla, terrain factor, supply factor,
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
  undeploy: a, ok, nm, sup (installed turret not fighting on hostile land uninstalled; nm = order move blocks removed)
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
import math
import re
from collections import Counter, defaultdict

PH = ['Pa', 'W', 'P', 'Rg', 'E', 'A', 'R']
LEGEND = ('phases Pa=Paused W=Waiting P=Preparation Rg=Regroup E=Engage A=Action R=Retreat | dist = attacking army '
          'to target at order start | est = planned my/enemy power (req = required ratio) | fight = live power '
          'first->last (me/en change) | end = reason [code path that stopped it] | ! = est<1.25, own loss>30% or failed')


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
            events.append(parse_value(line, k + 6)[0])
        except (ValueError, IndexError):
            events.append(_salvage(line[k:]) or {'e': 'unparsed'})
    return events


def _salvage(s):
    """Flat `key : number|word` fields of a line the parser couldn't read (the log truncates long values, e.g. the
    snap gauge list cut inside an entry): enough for snap aggr / armies / structs and the g / t clocks."""
    m = re.match(r'AIMOD \{e : (\w+), f : (\w+)', s)
    if not m:
        return None
    e = {'e': m.group(1), 'f': m.group(2)}
    for key, val in re.findall(r'(?:^|[{,] )(aggr|armies|structs|g|t) : (-?[\d.]+)', s):
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


def aw_army(a):
    """Compact hostile army from an `aw` entry."""
    act = f" {a.get('sa') or str(a.get('ty') or '').split('(')[0]}>{a.get('tgt')}" if a.get('ty') or a.get('sa') else ''
    flags = ''.join(c for c, key in (('S', 'sand'), ('V', 'vis'), ('M', 'mv'), ('L', 'ls'), ('H', 'hz')) if a.get(key))
    return (f"{a.get('o')}:{a.get('k')} pw{big(a.get('pw'))} hp{num(a.get('hp'), 0)} sup{num(a.get('sup'), 0)}/{num(a.get('ms'), 0)}"
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


def around(events, center, window=60):
    t0 = events[0].get('t') or 0
    noisy = {'pw', 'fpw', 'fightb'}
    out = [f'# Events {clock(center - window)}..{clock(center + window)} (pw/fpw/fightb omitted)']
    for e in events:
        t = when(e, t0)
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
    last_pw, last_fpw, last_pick, last_stop = None, None, {}, {}
    rejected = defaultdict(lambda: {'n': 0, 'req': []})
    intents = defaultdict(Counter)          # faction -> Counter((gaugeKind, outcome))
    fights, micro, snaps, aws = [], defaultdict(Counter), {}, []
    calls = defaultdict(lambda: {'n': 0, 'f': Counter(), 'r': Counter()})
    stops = Counter()
    hunts = Counter()                       # (faction, act, why)
    spaced = Counter()                      # (faction, why, kind, tgt, near)
    retreats, heals, bunkers, discs, raids, strats = [], [], [], [], [], []
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
        elif k in ('phase', 'fightb', 'end', 'stop'):
            live = [o for o in open_orders.get((f, ent_key(e.get('tgt'))), []) if o['end'] is None]
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
            elif k == 'end':
                o['end'] = (t, e.get('why'), e.get('n'))
                o['src'] = last_stop.pop((f, ent_key(e.get('tgt'))), None)
        elif k == 'retreat':
            retreats.append(e)
        elif k == 'heal':
            heals.append(e)
        elif k == 'space':
            spaced[(f, e.get('why') or 'space', e.get('k'), ent(e.get('tgt')), ent(e.get('near')))] += 1
        elif k == 'bunker':
            bunkers.append(e)
        elif k == 'disc':
            discs.append(e)
        elif k == 'strat':
            strats.append(e)
        elif k == 'raid':
            raids.append(e)
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
        fights_ = [x for x in o['fight'] if isinstance(x[2], float)]
        own = (fights_[-1][2] - fights_[0][2]) / fights_[0][2] if fights_ and fights_[0][2] else 0
        fight = (f'{big(fights_[0][2])}/{big(fights_[0][3])}->{big(fights_[-1][2])}/{big(fights_[-1][3])} '
                 f'(me{change(fights_[0][2], fights_[-1][2])} en{change(fights_[0][3], fights_[-1][3])})') if fights_ else '-'
        why = str(o['end'][1]) if o['end'] else 'open'
        dur = f"+{o['end'][0] - o['t']:.0f}s" if o['end'] else ''
        src = f"[{o['src']}]" if o['src'] and why != 'Success' else ''
        if o.get('abort'):
            src += f"[hunt abort: {o['abort'].get('why')}]"
        bad = (isinstance(est, float) and est < 1.25) or own < -0.3 or why not in ('Success', 'open')
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
                   '(gone truce leash home supply drift lost weak turret objective defend chase)')
        for f in sorted({k[0] for k in hunts}, key=str):
            out.append(f'{f}: ' + ', '.join(f"{a}{('-' + w) if w else ''} x{n}" for (ff, a, w), n in sorted(hunts.items(), key=str) if ff == f))

    if retreats:
        out.append('\n## Fight retreat checks (tools/rules): balance x100 raw*terrain*supply=adj vs 65; '
                   'flip = terrain or supply (our armies short of supply for the way home) changed the outcome')
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
                   'retry = its last launch ended at once), count')
        out += [f'{f} {w} {kk} {tg} <- {nr} x{n}' for (f, w, kk, tg, nr), n in spaced.most_common(12)]

    if bunkers:
        out.append('\n## Bunker (tools/rules): Annex redirected to a village next to our main base: '
                   'faction target (vanilla pick), count (logged once per faction per 10 s)')
        c = Counter((e.get('f'), ent(e.get('tgt')), ent(e.get('was'))) for e in bunkers)
        out += [f'{f} {tg} (was {w}) x{n}' for (f, tg, w), n in c.most_common(12)]

    if strats:
        out += director(strats)

    if raids:
        out.append('\n## Raids (tools/rules/raid.py): pillage with idle armies (neutral or at-war villages, not the '
                   'next Annex); h = their threat+cover+militia, m = our raid force, hh/ms = hostile/our power near home')
        starts = [e for e in raids if e.get('act') == 'start']
        refused = [e for e in raids if e.get('act') == 'refuse']
        aborts = [e for e in raids if e.get('act') == 'abort']
        for e in starts[-12:]:
            out.append(f"  {clock(e['_t'])} {e.get('f')} {ent(e.get('tgt'))[:22]:<22} n{e.get('n')} dm{e.get('dm')} "
                       f"sd{e.get('sd')} h{kpw(e.get('H'))} m{kpw(e.get('M'))} hh{kpw(e.get('hh'))} "
                       f"ms{kpw(e.get('ms'))} ax {ent(e.get('ax'))[:16]}"
                       f"{'' if e.get('ok') is not False else ' REFUSED'}")
        if aborts:
            c = Counter((e.get('f'), e.get('why')) for e in aborts)
            out.append('Aborted pillages (defend = our besieged structure needs the armies, home = hostiles nearer our '
                       'land than the raid, weak = relief at the target): '
                       + ', '.join(f'{f} {w} x{n}' for (f, w), n in c.most_common(10)))
            for e in aborts[-10:]:
                out.append(f"  {clock(e['_t'])} {e.get('f')} {e.get('why'):<6} {ent(e.get('tgt'))[:20]:<20} "
                           f"ph{e.get('ph')} pr{e.get('pr')}% n{e.get('n')} sd{num(e.get('sd'), 0)} "
                           f"h{kpw(e.get('H'))} m{kpw(e.get('M'))}")
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
                           f"ax {ent(e.get('ax'))[:16]} nc{num(e.get('nc'), 0)}")

    if discs:
        out.append('\n## Refused Discovery trips (tools/rules): lone army vs at-war threat at the world event; '
                   'faction target count (logged once per event per 30 s)')
        c = Counter((e.get('f'), ent(e.get('tgt'))) for e in discs)
        out += [f'{f} {tg} x{n}' for (f, tg), n in c.most_common(12)]
        for e in discs[-8:]:
            out.append(f"  {clock(e['_t'])} {e.get('f')} {ent(e.get('tgt'))[:20]:<20} army {ent(e.get('army'))[:16]:<16} "
                       f"h{kpw(e.get('H'))} m{kpw(e.get('M'))} tf{e.get('tf')}")

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
                sand[(e.get('f'), a.get('o'))] += 1
            if (a.get('d') or 0) > 600 and (a.get('da') or 0) > 600:
                far[(e.get('f'), a.get('o'))] += 1
            if (a.get('da') or 1e9) <= 300:
                key = (e.get('f'), a.get('na'), my_task(a).strip() or 'idle', a.get('o'))
                c = close.setdefault(key, {'t0': e['_t'], 't1': e['_t'], 'da': a['da'], 'pw': 0})
                c['t1'], c['da'], c['pw'] = e['_t'], min(c['da'], a['da']), max(c['pw'], a.get('pw') or 0)
            if a.get('sa') or a.get('ct') or a.get('oc'):
                key = (e.get('f'), a.get('o'), a.get('sa') or '-', a.get('tgt') or a.get('ct') or a.get('oc'))
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
    if sand:
        out.append('Hostile armies seen on sand (thumper/worm candidates): ' +
                   ', '.join(f'{f}<-{o} x{n}' for (f, o), n in sand.most_common(8)))
    return out
