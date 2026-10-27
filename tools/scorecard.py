"""Per-match scorecard (docs/ARCHITECTURE-PLAN.md step 4): outcomes per task kind and faction, so a change is
judged by numbers (and tuned by a ratio) instead of by a new rule. `mod log --score`.

Per faction:
- sieges by action (Annex / Liberate / Pillage / ...): launched, Success, Cancel, cancelled within FAST_S (died at
  launch), armies dead on Military orders (`odead`);
- hunts: started / refused, aborts by reason; raids: started, aborts and refusals by reason;
- rally verdicts (race / commit / giveup / here); task-claim blocks (`claimx`); doctrine (`dpick` style, columns, `dmode` switches); failed unit buys by reason (`buyx`,
  one row per faction per 30 s: buy = vanilla's buy, check = the main base refusing the picked kind);
- economy: villages and armies at the end, net Solari min / end, Manpower rate and stock, water, plascrete.
- army at the end: unit kinds by share of the other factions' `aw` sightings in the last CENSUS_S s (doctrine check)."""
import collections
import json
from pathlib import Path

CENSUS_S = 240  # s: the army census reads the last this many seconds of `aw` scans
FAST_S = 5  # s: a siege cancelled this soon after its order died at launch


def _f(e):
    return e.get('f') or '?'


def _tgt_name(e):
    t = e.get('tgt')
    return (t.get('p') or t.get('k')) if isinstance(t, dict) else None


def _order_key(e):
    if isinstance(e.get('oid'), (int, float)):
        return (_f(e), 'id', e['oid'])
    return (_f(e), _tgt_name(e), e.get('sa'))


def scorecard(events):
    out = []
    facs = sorted({_f(e) for e in events if e.get('e') == 'snap'})
    sieges = collections.defaultdict(lambda: collections.Counter())
    started = {}  # (f, target, sa) -> launch g
    seen_end = set()  # an order's end is logged by more than one hook
    for e in events:
        k = e.get('e')
        f = _f(e)
        if k == 'order' and str(e.get('type', '')).startswith('Military') and e.get('sa'):
            sieges[f][(e['sa'], 'launch')] += 1
            started[_order_key(e)] = e.get('g') or 0
        elif k == 'end' and str(e.get('type', '')).startswith('Military') and e.get('sa'):
            key = _order_key(e) if isinstance(e.get('oid'), (int, float)) else (
                f, _tgt_name(e), e['sa'], round(float(e.get('g') or 0), 1))
            if key in seen_end:
                continue
            seen_end.add(key)
            why = e.get('why')
            sieges[f][(e['sa'], why)] += 1
            g0 = started.pop(_order_key(e), None)
            if why == 'Cancel' and g0 is not None and (e.get('g') or 0) - g0 <= FAST_S:
                sieges[f][(e['sa'], 'fast')] += 1
    dead = collections.Counter(_f(e) for e in events if e.get('e') == 'odead')
    hunts = collections.defaultdict(collections.Counter)
    raids = collections.defaultdict(collections.Counter)
    rally = collections.defaultdict(collections.Counter)
    claims = collections.defaultdict(collections.Counter)
    buys = collections.defaultdict(collections.Counter)
    doc = collections.defaultdict(collections.Counter)  # doctrine: style, columns picked, mode switches
    # decision records (rules/value.py `tval`): per kind, the value at stake, armies' value and forecast at start
    tval = collections.defaultdict(lambda: collections.defaultdict(list))
    try:
        rn = json.loads((Path(__file__).resolve().parents[1] / 'work' / 'eresult.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        rn = []
    for e in events:
        k, f = e.get('e'), _f(e)
        if k == 'hunt':
            a = e.get('act')
            if a == 'start':
                hunts[f]['start' if e.get('ok') in (True, 'true') else 'refused'] += 1
            elif a == 'abort':
                hunts[f]['abort ' + str(e.get('why'))] += 1
        elif k == 'raid':
            a = e.get('act')
            if a == 'start':
                raids[f]['start'] += 1
            elif a in ('abort', 'refuse'):
                raids[f][f"{a} {e.get('why')}"] += 1
        elif k == 'rally' and e.get('act') in ('race', 'commit', 'giveup', 'here'):
            rally[f][e['act'] + (f" {e.get('why')}" if e.get('act') in ('race', 'commit') else '')] += 1
        elif k in ('sxfail', 'sxblock', 'untgt'):
            claims[f][k] += 1
        elif k == 'claimx':
            claims[f][str(e.get('src'))] += 1
        elif k == 'dpick':
            doc[f][f"style {e.get('st')}"] = 1
            doc[f][f"col {('early', 'late', 'siege', 'hold')[int(float(e.get('col') or 0)) % 4]}"] += 1
        elif k == 'dmode':
            doc[f]['mode switches'] += 1
        elif k == 'hero' and int(float(e.get('r') or 0)) == 1:  # Success
            doc[f][f"hero {e.get('act')}"] += 1
        elif k == 'gear' and int(float(e.get('r') or 0)) == 1:  # Success
            doc[f]['gear changes'] += 1
        elif k == 'tval':
            tval[f][str(e.get('k'))].append((float(e.get('V') or 0), float(e.get('A') or 0),
                                             float(e.get('fc') or 0) / 100))  # `fc%` is logged as fc x 100
        elif k == 'buyx':
            ri = int(float(e.get('r') or 0))
            buys[f][f"{e.get('at')} {rn[ri] if ri < len(rn) else ri}" + (f" {e.get('k')}" if e.get('k') else '')] += 1
    # army census (doctrine check): unit kinds of each faction as the others' `aw` scans saw them in the last CENSUS_S
    # s (an army per kind, position rounded to 40, counted once): a rough share, sightings not a roster
    gmax = max((float(e.get('g') or 0) for e in events), default=0)
    seen = set()
    for e in events:
        if e.get('e') == 'aw' and float(e.get('g') or 0) >= gmax - CENSUS_S:
            for a in e.get('a') or []:
                if isinstance(a, dict) and a.get('o') and a.get('k'):
                    seen.add((a['o'], a['k'], round(float(a.get('x') or 0) / 40), round(float(a.get('y') or 0) / 40)))
    census = collections.defaultdict(collections.Counter)
    for o, k, _, _ in seen:
        census[o][k] += 1
    # base-kill plan (rules/bkill.py): leader changes, level changes, the last threat row per faction
    bk_lead = [e for e in events if e.get('e') == 'bkill' and e.get('act') == 'leader']
    bk_lvl = collections.defaultdict(list)
    bk_thr = {}
    for e in events:
        if e.get('e') == 'bkill' and e.get('act') == 'level':
            bk_lvl[_f(e)].append(f"{int(float(e.get('g') or 0)) // 60}m {e.get('why')}")
        elif e.get('e') == 'bthreat':
            bk_thr[_f(e)] = e
    snaps = collections.defaultdict(list)
    for e in events:
        if e.get('e') == 'snap':
            snaps[_f(e)].append(e)
    for f in facs:
        ss = snaps[f]

        def v(key):
            x = next((s_[key] for s_ in reversed(ss) if s_.get(key) is not None), None)  # last row carrying it
            return '-' if x is None else f'{float(x):.0f}'
        soln = [float(s['soln']) for s in ss if s.get('soln') is not None]
        out.append(f'== {f}: structures {v("structs")} armies {v("armies")} | Solari net min {min(soln):.0f} end '
                   f'{v("soln")} | Manpower {v("mpn")}/day stock {v("mp")} | water {v("watn")} | plascrete '
                   f'{v("pcn")}/day' if soln else f'== {f}')
        acts = sorted({a for a, _ in sieges[f]})
        rows = []
        for a in acts:
            c = sieges[f]
            rows.append(f"{a} {c[(a, 'launch')]}: ok {c[(a, 'Success')]} cancel {c[(a, 'Cancel')]} "
                        f"(at launch {c[(a, 'fast')]})")
        out.append('  sieges: ' + '; '.join(rows) + f' | armies dead on missions {dead[f]}')
        out.append('  hunts: ' + ', '.join(f'{k} {n}' for k, n in hunts[f].most_common()))
        out.append('  raids: ' + ', '.join(f'{k} {n}' for k, n in raids[f].most_common(8)))
        if rally[f]:
            out.append('  rally: ' + ', '.join(f'{k} {n}' for k, n in rally[f].most_common()))
        if claims[f]:
            out.append('  claims held off / siege memory: ' + ', '.join(f'{k} {n}' for k, n in claims[f].most_common()))
        if doc[f]:
            out.append('  doctrine: ' + ', '.join(f'{k} {n}' if not k.startswith('style') else k for k, n in doc[f].most_common()))
        if census[f]:
            tot = sum(census[f].values())
            out.append('  army at the end (sightings): ' + ', '.join(f'{k} {100 * n // tot}%' for k, n in census[f].most_common(7)))
        if tval[f]:
            def _med(xs):
                xs = sorted(xs)
                return xs[len(xs) // 2]
            rows = []
            for kd, rs in sorted(tval[f].items(), key=lambda x: -len(x[1])):
                fcs = [min(r[2], 99) for r in rs]  # FC_NONE (nobody against us) shown as 99
                rows.append(f'{kd} {len(rs)}: V {_med([r[0] for r in rs]):.0f} A {_med([r[1] for r in rs]):.0f} '
                            f'fc {_med(fcs):.2f} (<1: {sum(1 for x in fcs if x < 1)})')
            out.append('  task records (median value at stake / armies risked / forecast at start): ' + '; '.join(rows))
        if buys[f]:
            out.append('  buys failed (per 30 s): ' + ', '.join(f'{k} {n}' for k, n in buys[f].most_common(6)))
    # task board (rules/board.py): launches that would yield (shadow) per kind -> winner kind, and how those launches
    # ended: the first Military `end` on the same structure after that yield (army targets have no place to match)
    yields = collections.Counter()
    posts = collections.Counter()
    open_y = {}  # (f, place) -> kind of the yielding launch, waiting for its end
    yend = collections.Counter()
    for e in events:  # in log order: an end before the yield is not its outcome
        k = e.get('e')
        if k == 'tyield':
            yields[(_f(e), str(e.get('k')), str(e.get('byk')))] += 1
            pl = _tgt_name(e)
            if pl:
                open_y[(_f(e), pl)] = str(e.get('k'))
        elif k == 'tpost':
            posts[(_f(e), str(e.get('k')))] += 1
        elif k == 'end' and str(e.get('type', '')).startswith('Military'):
            key = (_f(e), _tgt_name(e))
            if key in open_y:
                yend[(key[0], open_y.pop(key), e.get('why'))] += 1
    if yields or posts:
        out.append('== task board (shadow): would-yield launches k -> winner, and their ends')
        for f in facs:
            ys = sorted(((k, w, n) for (ff, k, w), n in yields.items() if ff == f), key=lambda x: -x[2])
            ps = ', '.join(f'{k} {n}' for (ff, k), n in sorted(posts.items()) if ff == f)
            ends = ', '.join(f'{k} {w} {n}' for (ff, k, w), n in sorted(yend.items(), key=lambda x: str(x)) if ff == f)
            out.append(f"  {f}: posts {ps or '-'} | yields " + (', '.join(f'{k}->{w} {n}' for k, w, n in ys) or '-')
                       + (f' | yielded ones ended: {ends}' if ends else ''))
    if bk_thr or bk_lead:
        out.append('== base-kill plan: leader ' + (', '.join(f"{int(float(e.get('g') or 0)) // 60}m {e.get('tgt')}"
                                                          for e in bk_lead) or 'never'))
        for f, e in sorted(bk_thr.items()):
            out.append(f"  {f}: hegemony {float(e.get('h') or 0):.0f} (+{float(e.get('r') or 0):.0f}/day) CHOAM "
                       f"{e.get('c')}% governor {e.get('gov')} ETA {float(e.get('eta') or 0):.0f} days | levels "
                       + (', '.join(bk_lvl.get(f, [])) or '-'))
    # stage 3 campaign (rules/bkill.py `bcamp`): phase changes with their numbers, muster sends and go launches
    names = {0: 'attrition', 1: 'muster', 2: 'go', 3: 'regroup'}
    camp = [e for e in events if e.get('e') == 'bcamp']
    if camp:
        ph = [f"{int(float(e.get('g') or 0)) // 60}m {names.get(int(float(e.get('to') or 0)), '?')} "
              f"(D {float(e.get('D') or 0) / 1000:.0f}k M {float(e.get('M') or 0) / 1000:.0f}k "
              f"P {float(e.get('P') or 0) / 1000:.0f}k hp {e.get('hp')}%)" for e in camp if e.get('act') == 'phase']
        sent = collections.Counter(_f(e) for e in camp if e.get('act') == 'muster')
        gos = [f"{_f(e)} {int(float(e.get('g') or 0)) // 60}m n{e.get('n')} {'ok' if e.get('ok') in (True, 'true') else 'refused'}"
               for e in camp if e.get('act') == 'go']
        out.append('  campaign: ' + ('; '.join(ph) or 'no phase change') + ' | muster rows '
                   + (', '.join(f'{f} {n}' for f, n in sent.most_common()) or '-') + ' | go ' + (', '.join(gos) or '-'))
        # supporters' fights / approaches, how each Raze on a leader base ended, the base-kill ops cast
        sup = collections.Counter(f"{_f(e)} {e.get('act')}{'' if e.get('ok') in (True, 'true', None) else ' refused'}"
                                  for e in camp if e.get('act') in ('fight', 'approach', 'gather', 'foot', 'cut', 'nogo'))
        bases = {str(e.get('tgt')) for e in camp}
        razes = [f"{_f(e)} {int(float(e.get('g') or 0)) // 60}m ph{e.get('ph')} n{e.get('n')} {e.get('why')}"
                 for e in events if e.get('e') == 'end' and e.get('sa') == 'Raze' and str(e.get('tgt')) in bases]
        bops = [f"{_f(e)} {int(float(e.get('g') or 0)) // 60}m {e.get('op')}"
                for e in events if e.get('e') == 'opcast' and e.get('why') == 'basekill']
        out.append('  supporters: ' + (', '.join(f'{k} {n}' for k, n in sup.most_common()) or '-')
                   + ' | raze ends ' + (', '.join(razes) or '-') + ' | ops ' + (', '.join(bops) or '-'))
    return '\n'.join(out)
