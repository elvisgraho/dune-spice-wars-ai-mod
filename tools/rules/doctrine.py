"""Army doctrine (user: steer vanilla's unit and gear picks by our strategy docs): docs/strategy/DOCTRINE.md (unit
mixes per faction, mode and style) and docs/strategy/ARMORY-OPS.md (gear sets per mode) are parsed at build time;
the docs are the data.

- Mode (`aimod_dmode(fac) -> column`): purpose Hold while the strat posture (map `spost`) is defend / recover,
  Siege while map `dsiege` faction -> time is younger than SIEGE_T (rules/tasks.py: one of its Military orders at
  Regroup or later on a main base or with Raze; rules/bkill.py: every campaign pass of a member at plan level >= 2,
  so a faction committed to a base kill recruits and gears for it before the go; Siege = cracking a main base),
  else Field. A new purpose is taken once it was the candidate for CAND_T s and the last switch is SET_HOLD s old
  (gear costs 500 Solari a change, faction-wide). Column: Siege 2, Hold 3, else Early 0 (game time < EARLY_T) /
  Late 1. Logs `dmode` (f, m) on a switch.
- Units (`dpick`): the HScoring.buyableUnits call in $AIUnits.pickBuyableUnit is wrapped. Before it: kinds the main
  base can't recruit now (`Structure.checkRecruit` != Success: cost, unlock, CP, training slots) leave the list:
  vanilla's weighted pick among the top 2 never tested the cost, so a top-ranked Guild-Favor ship / frigate failed
  every check and nothing was recruited (`buyx`: Smugglers / Harkonnen 31 / 18 free CP for 30+ min). After it, for
  a faction with a table: score = the kind's weight (percent of the column) - its share of the faction's table
  kinds (units + main-base queue) + 1 (at least 1); more than OVER points over its weight: removed; weight 0: removed (never recruited: fighter ships, early elites; a vanilla
  unit of the faction missing from its table is weight 0); a kind not in the vanilla data (modded): vanilla's score
  x MOD_K. The style is picked once per faction per match by the
  heading weights (`$Math.random`; log `dstyle`); a style fielding Fuel Cell units marks map `dfuel` (the economy
  values Fuel Cells for it, rules/econ.py). Logs `dpick` (f, st, col, n kinds offered, drop, top = the best-scored
  kind, sc its score, tot = the faction's table units counted) per DPICK_T s.
- Gear (`dgear`): both HScoring.equipments calls in AIController.checkEquipments are wrapped: each (unit, gear) of
  the mode's set gets + GEAR_W (the first-listed gear + GEAR_FIRST: it fills the only early slot), so in-set gear
  replaces off-set gear and is never replaced by it. Counter swap (anti-air): while at least AIR_MIN visible at-war
  armies are air (Ship / Frigate kinds) and AIR_PCT of the visible at-war armies (map `dair`, AIR_HOLD since the last
  such look; log `dcounter`), the faction's first armory unit with Bird Slayer / Whistling Ammo gets that gear at
  + AIR_W over the set's first gear. `gear` logs each change the AI applies (f, u, gr, slot, r). Fails safe: vanilla's result on error."""
import re
from pathlib import Path

from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers

EARLY_T = 1200     # s: Early column before this game time (~day 40), Late after
SET_HOLD = 600     # s: a mode is kept at least this long (gear changes cost 500 Solari each: Fremen re-geared 20 x
                   # at 300 s, 5 Field / Hold switches, match 2026-10-24 02:32)
CAND_T = 120       # s: a new purpose must be the candidate this long first
SIEGE_T = 120      # s: map `dsiege` faction -> time keeps the Siege purpose this long
OVER = 10          # percentage points: a kind this far above its weight isn't bought (CP gaps stay free instead)
MOD_K = 0.2        # a kind outside the faction's table keeps this share of vanilla's score
GEAR_W = 100       # gear set bonus (vanilla gear scores: data aiWeights, mostly 0, + combo bonuses)
GEAR_FIRST = 10    # ... + this for the set's first-listed gear (the only slot early)
AIR_MIN = 3        # anti-air counter: at least this many visible at-war air armies ...
AIR_PCT = 20       # ... making at least this percent of the visible at-war armies ...
AIR_HOLD = 600     # s: ... switch the counter on for this long (map `dair` faction -> since)
AIR_W = 30         # the counter gear's bonus on top of GEAR_W (it beats the set's first gear)
AA_GEAR = ('bird slayer', 'whistling ammo')
FUEL_MIN = 15      # percent of the Late column in Fuel Cell units: the style marks map `dfuel`
DPICK_T = 60       # s: `dpick` log throttle per faction
COLS = ('Early', 'Late', 'Siege', 'Hold')
SETS = ('Field', 'Siege', 'Hold')
DOCS = Path(__file__).resolve().parents[2] / 'docs' / 'strategy'
ALIASES = {('Atreides', 'HWS'): 'Heavy Weapon Squad', ('Corrino', 'Swordsman'): 'Conscript Swordman',
           ('Corrino', 'Conscript Swordsman'): 'Conscript Swordman'}


def _unit_names():
    """(faction, display name) -> unit id, from the data in effect."""
    out = {}
    for u in game_rows('unit', False):
        f, n = u.get('faction'), (u.get('texts') or {}).get('name')
        if f and n and (f, n) not in out:
            out[(f, n)] = u['id']
    return out


def _uid_of(names, fac, name):
    name = ALIASES.get((fac, name), name)
    if (fac, name) in names:
        return names[(fac, name)]
    hit = {v for (f, n), v in names.items() if f == fac and name.lower() in n.lower()}  # a short name (Rifleman)
    if len(hit) != 1:
        raise ValueError(f'doctrine: unknown unit {name!r} for {fac}')
    return hit.pop()


def parse_doctrine(path=DOCS / 'DOCTRINE.md'):
    """{faction: [(style, weight, {unit id: [Early, Late, Siege, Hold] percent of the column, rounded})]}."""
    names = _unit_names()
    out, fac, style = {}, None, None
    for line in path.read_text(encoding='utf-8').splitlines():
        m = re.match(r'## (\w+)\s*$', line)
        if m:
            fac, style = m.group(1), None
            continue
        m = re.match(r'#### Style (.+?) \((\d+)\)', line)
        if m and fac:
            style = (m.group(1), int(m.group(2)), {})
            out.setdefault(fac, []).append(style)
            continue
        if style and line.startswith('|') and not line.startswith(('| Unit', '|---')):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            style[2][_uid_of(names, fac, cells[0])] = [int(c) for c in cells[1:5]]
    vanilla = {}  # faction -> its vanilla unit ids: one missing from a table is weight 0 (Fremen bought Spires at
    for u in game_rows('unit', True):  # 0.2 x vanilla once the table's units met their shares)
        if u.get('faction'):
            vanilla.setdefault(u['faction'], set()).add(u['id'])
    for fac, styles in out.items():
        for st, w, tab in styles:
            for c in range(4):
                tot = sum(v[c] for v in tab.values())
                if tot <= 0:
                    raise ValueError(f'doctrine: {fac} {st} column {COLS[c]} sums to 0')
                for v in tab.values():
                    v[c] = round(100 * v[c] / tot)
            for uid in vanilla.get(fac, ()):
                tab.setdefault(uid, [0, 0, 0, 0])
    return out


def fuel_styles(doctrine):
    """{(faction, style): True} when the style's Fuel Cell units (upkeep) weigh at least FUEL_MIN in its Late column (a
    flagship for the Siege or a couple of early drones don't make a fuel economy)."""
    units = {u['id']: u for u in game_rows('unit', False)}

    def upkeep(uid):
        x, seen = units.get(uid), set()
        while x is not None and x['id'] not in seen:
            seen.add(x['id'])
            c = (x.get('costs') or {}).get('upkeep')
            if c:
                return {r.get('res') for r in c if (r.get('qty') or 0) > 0}
            x = units.get(x.get('inherits'))
        return set()
    return {(fac, st): sum(cells[1] for uid, cells in tab.items() if 'FuelCell' in upkeep(uid)) >= FUEL_MIN
            for fac, styles in doctrine.items() for st, _, tab in styles}


def variants(doctrine):
    """{faction: {variant id: base id}}: a unit kind of the faction outside its table whose id extends a table kind's
    id (H_Drone_Torture -> H_Drone, F_Special_2 -> F_Special, C_Trooper_Aramsham -> C_Trooper): an upgrade or
    deployment turns the base into it, so it counts toward the base's share (Harkonnen bought Combat Probes without end:
    the upgraded ones read as another kind, 43 of 70 deaths, match 2026-10-24 01:48)."""
    out = {}
    for fac, styles in doctrine.items():
        named = {uid for _, _, tab in styles for uid, cells in tab.items() if any(cells)}
        for uid in {u for _, _, tab in styles for u in tab}:
            if uid in named or 'Militia' in uid:  # village militia aren't recruits
                continue
            base = max((n for n in named if uid.startswith(n + '_')), key=len, default=None)
            if base:
                out.setdefault(fac, {})[uid] = base
    return out


def parse_armory(path=DOCS / 'ARMORY-OPS.md'):
    """{faction: {unit id: {set: [gear ids, first-listed first]}}} from the per-faction gear tables."""
    names = _unit_names()
    gear = {g['id']: (g.get('name') or '').lower() for g in game_rows('equipment', False)}
    units = {u['id']: u for u in game_rows('unit', False)}
    out, fac = {}, None
    for line in path.read_text(encoding='utf-8').splitlines():
        m = re.match(r'### (\w+)\s*$', line)
        if m:
            fac = m.group(1)
            continue
        if line.startswith('## '):
            fac = None
        if not fac or not line.startswith('|') or line.startswith(('| Unit', '|---')):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        uid = _uid_of(names, fac, cells[0])
        opts = {gear.get(r['ref'], ''): r['ref'] for r in units[uid].get('equipment') or []}
        row = {}
        for s, cell in zip(SETS, cells[1:4]):
            ids = []
            for g in re.sub(r'\(.*?\)', '', cell).replace('*', '').split('+'):
                g = g.strip().lower()
                hit = [v for k, v in opts.items() if k == g] or [v for k, v in opts.items() if g and (g in k or k in g)]
                if not hit:
                    raise ValueError(f'doctrine: unknown gear {g!r} for {fac} {cells[0]}')
                ids.append(hit[0])
            row[s] = ids
        out.setdefault(fac, {})[uid] = row
    return out


def _new_smap(fb, b, cx):
    r = fb.reg(cx.t('haxe.ds.StringMap'))
    fb.op('New', dst=r)
    v = fb.reg(cx.t('void'))
    fb.op('Call1', dst=v, fun=cx.fn('haxe.ds.$StringMap.__constructor__').findex.value, arg0=r)
    return r


def _is_fac(fb, b, cx, fac, name, no):
    """Jump to `no` unless faction register fac is `name`."""
    k = b.cast(fb.get(fac, 'kind'), 'String')
    fb.op('JNull', reg=k, offset=no)
    fb.op('JNotEq', a=b.call('String.__compare', k, fb.dyn(fb.string(name))), b=b.const('i32', 0), offset=no)


def build_dmode(cx, helpers):
    """aimod_dmode(fac) -> column (see module doc)."""
    fb = FB(cx, [cx.t('ent.Faction')], cx.t('i32'))
    b = B(fb)
    col, cand, cur, ci = (fb.reg(cx.t('i32')) for _ in range(4))
    fb.op('Mov', dst=col, src=b.const('i32', 1))
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    t, q = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    fb.op('Mov', dst=cand, src=b.const('i32', 0))
    sp = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'spost'), fb.dyn(0))
    fb.op('JNull', reg=sp, offset='nsp')
    fb.op('SafeCast', dst=ci, src=sp)
    fb.op('JEq', a=ci, b=b.const('i32', 1), offset='hold')
    fb.op('JNotEq', a=ci, b=b.const('i32', RECOVER_POST), offset='nsp')
    fb.label('hold')
    fb.op('Mov', dst=cand, src=b.const('i32', 2))
    fb.label('nsp')
    sg = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'dsiege'), fb.dyn(0))
    fb.op('JNull', reg=sg, offset='nsg')
    fb.op('SafeCast', dst=q, src=sg)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSGt', a=q, b=b.const('f64', SIEGE_T), offset='nsg')
    fb.op('Mov', dst=cand, src=b.const('i32', 1))
    fb.label('nsg')
    dmd, dmdt = _global_map(fb, b, cx, 'dmd'), _global_map(fb, b, cx, 'dmdt')
    dmc, dmct = _global_map(fb, b, cx, 'dmc'), _global_map(fb, b, cx, 'dmct')
    cv = b.call('haxe.ds.ObjectMap.get', dmd, fb.dyn(0))
    fb.op('JNull', reg=cv, offset='switch')  # first look: take the candidate
    fb.op('SafeCast', dst=cur, src=cv)
    fb.op('JNotEq', a=cand, b=cur, offset='diff')
    b.call('haxe.ds.ObjectMap.remove', dmc, fb.dyn(0))
    fb.op('JAlways', offset='col')
    fb.label('diff')
    cc = b.call('haxe.ds.ObjectMap.get', dmc, fb.dyn(0))
    fb.op('JNull', reg=cc, offset='newc')
    fb.op('SafeCast', dst=ci, src=cc)
    fb.op('JNotEq', a=ci, b=cand, offset='newc')
    ct = b.call('haxe.ds.ObjectMap.get', dmct, fb.dyn(0))
    fb.op('JNull', reg=ct, offset='newc')
    fb.op('SafeCast', dst=q, src=ct)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSLt', a=q, b=b.const('f64', CAND_T), offset='col')
    lt = b.call('haxe.ds.ObjectMap.get', dmdt, fb.dyn(0))
    fb.op('JNull', reg=lt, offset='switch')
    fb.op('SafeCast', dst=q, src=lt)
    fb.op('Sub', dst=q, a=t, b=q)
    fb.op('JSLt', a=q, b=b.const('f64', SET_HOLD), offset='col')
    fb.label('switch')
    fb.op('Mov', dst=cur, src=cand)
    b.call('haxe.ds.ObjectMap.set', dmd, fb.dyn(0), fb.dyn(cur))
    b.call('haxe.ds.ObjectMap.set', dmdt, fb.dyn(0), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.remove', dmc, fb.dyn(0))
    _log_ev(fb, b, cx, helpers, 'dmode', [('f', fb.get(0, 'kind')), ('m', fb.dyn(cur))])
    fb.op('JAlways', offset='col')
    fb.label('newc')
    b.call('haxe.ds.ObjectMap.set', dmc, fb.dyn(0), fb.dyn(cand))
    b.call('haxe.ds.ObjectMap.set', dmct, fb.dyn(0), fb.dyn(t))
    fb.label('col')
    fb.op('Mov', dst=col, src=b.const('i32', 2))
    fb.op('JEq', a=cur, b=b.const('i32', 1), offset='end')
    fb.op('Mov', dst=col, src=b.const('i32', 3))
    fb.op('JEq', a=cur, b=b.const('i32', 2), offset='end')
    fb.op('Mov', dst=col, src=b.const('i32', 0))
    fb.op('JSLt', a=t, b=b.const('f64', EARLY_T), offset='end')
    fb.op('Mov', dst=col, src=b.const('i32', 1))
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=col)
    return fb.build()


def _count_kinds(fb, b, cx, fac, tm, cnt, total, al):
    """cnt (StringMap kind -> count, f64 dyn) and total (f64) over fac's units and its main-base queue, kinds with a
    weight > 0 in tm."""
    total_op = total
    fb.op('Mov', dst=total_op, src=b.const('f64', 0))
    one = b.const('f64', 1)
    q = fb.reg(cx.t('f64'))
    for src in (('units', 'array'), None):
        u = _uid('dc')
        if src:
            arr = b.cast(fb.get(fac, *src), 'hl.types.ArrayObj')
        else:
            mb = b.call('ent.Faction.get_mainBase', fac)
            arr = b.cast(fb.get(mb, 'recruitments', 'array'), 'hl.types.ArrayObj')
        fb.op('JNull', reg=arr, offset=u + 'd')
        i = fb.reg(cx.t('i32'))
        fb.op('Mov', dst=i, src=b.const('i32', 0))
        b.loop_head(u)
        fb.op('JSGte', a=i, b=b.field(arr, 'length'), offset=u + 'd')
        e = b.call('hl.types.ArrayObj.getDyn', arr, i)
        fb.op('Incr', dst=i)
        k = fb.reg(cx.t('String'))
        fb.op('Mov', dst=k, src=b.cast(fb.get(e, 'kind'), 'String'))
        fb.op('JNull', reg=k, offset=u)
        av = b.call('haxe.ds.StringMap.get', al, k)  # a variant counts as its base (variants())
        fb.op('JNull', reg=av, offset=u + 'a')
        fb.op('Mov', dst=k, src=b.cast(av, 'String'))
        fb.label(u + 'a')
        tv = b.call('haxe.ds.StringMap.get', tm, k)
        fb.op('JNull', reg=tv, offset=u)
        fb.op('SafeCast', dst=q, src=tv)
        fb.op('JSLte', a=q, b=b.const('f64', 0), offset=u)  # weight 0 (harvesters, ornithopters, heroes): not the mix
        fb.op('Mov', dst=q, src=b.const('f64', 0))
        cv = b.call('haxe.ds.StringMap.get', cnt, k)
        fb.op('JNull', reg=cv, offset=u + 'z')
        fb.op('SafeCast', dst=q, src=cv)
        fb.label(u + 'z')
        fb.op('Add', dst=q, a=q, b=one)
        b.call('haxe.ds.StringMap.set', cnt, k, fb.dyn(q))
        fb.op('Add', dst=total_op, a=total_op, b=one)
        fb.op('JAlways', offset=u)
        fb.label(u + 'd')


def build_unit_pick(cx, helpers, doctrine, new_ids):
    """dpick wrapper on the buyableUnits call in $AIUnits.pickBuyableUnit (see module doc)."""
    bu = cx.fn('logic.ai.$HScoring.buyableUnits')
    pick = cx.fn('logic.ai.$AIUnits.pickBuyableUnit')
    sites = [op for op in pick.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == bu.findex.value]
    if len(sites) != 1:
        raise ValueError(f'dpick: expected 1 buyableUnits call in pickBuyableUnit, found {len(sites)}')
    cr = cx.fn('ent.Structure.checkRecruit')
    crt = cx.code.types[cr.type.value].definition
    ft = cx.code.types[bu.type.value].definition
    fb = FB(cx, [x.value for x in ft.args], ft.ret.value, fun_type=bu.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    drop, i, ri = (fb.reg(cx.t('i32')) for _ in range(3))
    fb.op('Mov', dst=drop, src=b.const('i32', 0))
    # affordable now: drop kinds the main base refuses
    g0 = fb.try_()
    fb.op('JNull', reg=0, offset='a_end')
    fb.op('JNull', reg=1, offset='a_end')
    mb = b.call('ent.Faction.get_mainBase', 1)
    fb.op('JNull', reg=mb, offset='a_end')
    nulls = []
    for a in crt.args[2:]:
        r = fb.reg(a.value)
        fb.op('Null', dst=r)  # as AIUnits.buyUnit calls it
        nulls.append(r)
    rr = fb.reg(crt.ret.value)
    fb.op('Mov', dst=i, src=b.field(0, 'length'))
    b.loop_head('a')
    fb.op('JSLte', a=i, b=b.const('i32', 0), offset='a_end')
    fb.op('Sub', dst=i, a=i, b=b.const('i32', 1))
    k = b.cast(b.call('hl.types.ArrayObj.getDyn', 0, i), 'String')
    fb.op('JNull', reg=k, offset='a')
    fb.op('CallN', dst=rr, fun=cr.findex.value, args=[mb, k] + nulls)
    fb.op('EnumIndex', dst=ri, value=rr)
    fb.op('JEq', a=ri, b=b.const('i32', 1), offset='a')  # Success
    b.call('hl.types.ArrayObj.splice', 0, i, b.const('i32', 1))
    fb.op('Incr', dst=drop)
    fb.op('JAlways', offset='a')
    fb.label('a_end')
    fb.end_try(g0)
    fb.op('CallN', dst=res, fun=bu.findex.value, args=[0, 1, 2])  # vanilla, outside the traps
    g1 = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    fb.op('JNull', reg=1, offset='end')
    col = fb.reg(cx.t('i32'))
    fb.op('Call1', dst=col, fun=helpers['dmode'], arg0=1)
    tm = _new_smap(fb, b, cx)  # kind -> weight (percent) for this faction / style / column
    al = _new_smap(fb, b, cx)  # variant kind -> base kind (variants())
    vmap = variants(doctrine)
    fuel = fuel_styles(doctrine)
    dfuel = _global_map(fb, b, cx, 'dfuel')
    sty = fb.reg(cx.t('i32'))
    sname = fb.reg(cx.t('String'))
    fb.op('Null', dst=sname)
    dsty = _global_map(fb, b, cx, 'dsty')
    rnd = cx.fn('$Math.random').findex.value
    for fac, styles in doctrine.items():
        nf = _uid('df')
        _is_fac(fb, b, cx, 1, fac, nf)
        for vid, base in vmap.get(fac, {}).items():
            b.call('haxe.ds.StringMap.set', al, fb.string(vid), fb.dyn(fb.string(base)))
        sv = b.call('haxe.ds.ObjectMap.get', dsty, fb.dyn(1))
        have = _uid('dsh')
        fb.op('JNull', reg=sv, offset=have + 'n')
        fb.op('SafeCast', dst=sty, src=sv)
        fb.op('JAlways', offset=have)
        fb.label(have + 'n')
        rv = fb.reg(cx.t('f64'))
        fb.op('Call0', dst=rv, fun=rnd)
        fb.op('Mul', dst=rv, a=rv, b=b.const('f64', sum(w for _, w, _ in styles)))
        acc = 0
        for n_, (st, w, _) in enumerate(styles):
            acc += w
            fb.op('Mov', dst=sty, src=b.const('i32', n_))
            fb.op('JSLt', a=rv, b=b.const('f64', acc), offset=have + 'p')
        fb.label(have + 'p')
        b.call('haxe.ds.ObjectMap.set', dsty, fb.dyn(1), fb.dyn(sty))
        _log_ev(fb, b, cx, helpers, 'dstyle', [('f', fb.get(1, 'kind')), ('st', fb.dyn(sty))])
        fb.label(have)
        for n_, (st, w, tab) in enumerate(styles):
            ns = _uid('ds')
            fb.op('JNotEq', a=sty, b=b.const('i32', n_), offset=ns)
            fb.op('Mov', dst=sname, src=fb.string(st))
            # Fuel Cells valued in the economy (rules/econ.py RES_GATE) while the style fields fuel units
            if fuel.get((fac, st)):
                b.call('haxe.ds.ObjectMap.set', dfuel, fb.dyn(1), fb.dyn(b.const('i32', 1)))
            else:
                b.call('haxe.ds.ObjectMap.remove', dfuel, fb.dyn(1))
            for c in range(4):
                nc = _uid('dcol')
                fb.op('JNotEq', a=col, b=b.const('i32', c), offset=nc)
                for uid, cells in tab.items():
                    b.call('haxe.ds.StringMap.set', tm, fb.string(uid), fb.dyn(b.const('f64', cells[c])))
                fb.op('JAlways', offset='apply')
                fb.label(nc)
            fb.label(ns)
        fb.op('JAlways', offset='apply')
        fb.label(nf)
    fb.op('JAlways', offset='end')  # a faction without a table (modded): vanilla
    fb.label('apply')
    cnt = _new_smap(fb, b, cx)
    total = fb.reg(cx.t('f64'))
    _count_kinds(fb, b, cx, 1, tm, cnt, total, al)
    w, sh, sc, best = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('Mov', dst=best, src=b.const('f64', -1))
    bk = fb.reg(cx.t('String'))
    fb.op('Null', dst=bk)
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('s')
    fb.op('JSGte', a=i, b=b.field(0, 'length'), offset='log')
    k2 = b.cast(b.call('hl.types.ArrayObj.getDyn', 0, i), 'String')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=k2, offset='s')
    wv = b.call('haxe.ds.StringMap.get', tm, k2)
    fb.op('JNull', reg=wv, offset='mod')
    fb.op('SafeCast', dst=w, src=wv)
    fb.op('JSGt', a=w, b=b.const('f64', 0), offset='want')
    b.call('haxe.ds.StringMap.remove', res, k2)  # weight 0: never recruited in this mode
    fb.op('JAlways', offset='s')
    fb.label('want')
    fb.op('Mov', dst=sh, src=b.const('f64', 0))
    cv = b.call('haxe.ds.StringMap.get', cnt, k2)
    fb.op('JNull', reg=cv, offset='nsh')
    fb.op('JSLte', a=total, b=b.const('f64', 0), offset='nsh')
    fb.op('SafeCast', dst=sh, src=cv)
    fb.op('Mul', dst=sh, a=sh, b=b.const('f64', 100))
    fb.op('SDiv', dst=sh, a=sh, b=total)
    fb.label('nsh')
    fb.op('Sub', dst=sc, a=w, b=sh)
    # far over its weight: not bought (the 1-CP Combat Probe was the only kind fitting the last CP free after each loss
    # and piled up to ~30% of Harkonnen's army against 5%, match 2026-10-24 03:17)
    fb.op('JSGte', a=sc, b=b.const('f64', -OVER), offset='nover')
    b.call('haxe.ds.StringMap.remove', res, k2)
    fb.op('JAlways', offset='s')
    fb.label('nover')
    fb.op('JSGte', a=sc, b=b.const('f64', 0), offset='pos')
    fb.op('Mov', dst=sc, src=b.const('f64', 0))
    fb.label('pos')
    fb.op('Add', dst=sc, a=sc, b=b.const('f64', 1))
    b.call('haxe.ds.StringMap.set', res, k2, fb.dyn(sc))
    fb.op('JSLte', a=sc, b=best, offset='s')
    fb.op('Mov', dst=best, src=sc)
    fb.op('Mov', dst=bk, src=k2)
    fb.op('JAlways', offset='s')
    fb.label('mod')  # outside the table (a modded kind): a share of vanilla's score
    vv = b.call('haxe.ds.StringMap.get', res, k2)
    fb.op('JNull', reg=vv, offset='s')
    fb.op('SafeCast', dst=sc, src=vv)
    fb.op('Mul', dst=sc, a=sc, b=_ratio(fb, b, MOD_K))
    b.call('haxe.ds.StringMap.set', res, k2, fb.dyn(sc))
    fb.op('JAlways', offset='s')
    fb.label('log')
    _throttle(fb, b, cx, 'dpick', 1, DPICK_T, 'end')
    _log_ev(fb, b, cx, helpers, 'dpick', [('f', fb.get(1, 'kind')), ('st', fb.dyn(sname)), ('col', fb.dyn(col)),
                                          ('n', fb.dyn(b.field(0, 'length'))), ('drop', fb.dyn(drop)),
                                          ('top', fb.dyn(bk)), ('sc', best), ('tot', total)])
    fb.label('end')
    fb.end_try(g1)
    fb.op('Ret', ret=res)
    wf = fb.build()
    sites[0].df['fun'].value = wf
    new_ids.add(wf)
    return {'dpick': 1}


def air_kinds():
    """Unit ids whose inheritance reaches the Ship / Frigate templates (combat air), faction units only."""
    units = {u['id']: u for u in game_rows('unit', False)}
    out = set()
    for uid, u in units.items():
        if not u.get('faction') or 'Freighter' in uid:
            continue
        x, seen = u, set()
        while x is not None and x['id'] not in seen:
            seen.add(x['id'])
            if x['id'] in ('Ship', 'Frigate'):
                out.add(uid)
                break
            x = units.get(x.get('inherits'))
    return out


def aa_gear(armory):
    """{faction: (unit id, gear id)}: the first unit of the faction's armory tables with an anti-air gear option."""
    units = {u['id']: u for u in game_rows('unit', False)}
    gear = {g['id']: (g.get('name') or '').lower() for g in game_rows('equipment', False)}
    out = {}
    for fac, us in armory.items():
        for uid in us:
            hit = [r['ref'] for r in units[uid].get('equipment') or [] if gear.get(r['ref']) in AA_GEAR]
            if hit:
                out[fac] = (uid, hit[0])
                break
    return out


def _air_check(fb, b, cx, helpers, fac, airk):
    """Counter swap trigger: the visible at-war armies (State.armies, Entity.isVisibleForFaction) with >= AIR_MIN air
    (kinds in StringMap airk) and >= AIR_PCT of them -> map `dair` fac -> now (log `dcounter` k air on a new spell)."""
    u = _uid('air')
    st = _state(fb, b, cx)
    arr = b.field(st, 'armies')
    na, nt, i = (fb.reg(cx.t('i32')) for _ in range(3))
    fb.op('Mov', dst=na, src=b.const('i32', 0))
    fb.op('Mov', dst=nt, src=b.const('i32', 0))
    a = _army_loop(fb, b, arr, b.field(arr, 'length'), i, u, u + 'd')
    ao = b.call('ent.Entity.get_owner', a)
    fb.op('JNull', reg=ao, offset=u)
    fb.op('JEq', a=ao, b=fac, offset=u)
    fb.op('JFalse', cond=b.call('logic.state.State.areAtWar', st, fac, ao), offset=u)
    fb.op('JFalse', cond=b.call('ent.Entity.isVisibleForFaction', a, fac), offset=u)
    fb.op('Incr', dst=nt)
    k = b.cast(fb.get(a, 'kind'), 'String')
    fb.op('JNull', reg=k, offset=u)
    fb.op('JNull', reg=b.call('haxe.ds.StringMap.get', airk, k), offset=u)
    fb.op('Incr', dst=na)
    fb.op('JAlways', offset=u)
    fb.label(u + 'd')
    fb.op('JSLt', a=na, b=b.const('i32', AIR_MIN), offset=u + 'x')
    q = fb.reg(cx.t('i32'))
    fb.op('Mul', dst=q, a=na, b=b.const('i32', 100))
    h = fb.reg(cx.t('i32'))
    fb.op('Mul', dst=h, a=nt, b=b.const('i32', AIR_PCT))
    fb.op('JSLt', a=q, b=h, offset=u + 'x')
    dair = _global_map(fb, b, cx, 'dair')
    t = b.field(st, 'time')
    old = b.call('haxe.ds.ObjectMap.get', dair, fb.dyn(fac))
    fb.op('JNotNull', reg=old, offset=u + 'set')
    _log_ev(fb, b, cx, helpers, 'dcounter', [('f', fb.get(fac, 'kind')), ('k', 'air'), ('n', fb.dyn(na)),
                                             ('of', fb.dyn(nt))])
    fb.label(u + 'set')
    b.call('haxe.ds.ObjectMap.set', dair, fb.dyn(fac), fb.dyn(t))
    fb.label(u + 'x')


def build_gear_pick(cx, helpers, armory, new_ids):
    """dgear wrapper on both HScoring.equipments calls in AIController.checkEquipments (see module doc)."""
    eqf = cx.fn('logic.ai.$HScoring.equipments')
    ce = cx.fn('logic.ai.AIController.checkEquipments')
    sites = [op for op in ce.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == eqf.findex.value]
    if len(sites) != 2:
        raise ValueError(f'dgear: expected 2 equipments calls in checkEquipments, found {len(sites)}')
    ft = cx.code.types[eqf.type.value].definition
    fb = FB(cx, [x.value for x in ft.args], ft.ret.value, fun_type=eqf.type.value)
    b = B(fb)
    res = fb.reg(ft.ret.value)
    fb.op('CallN', dst=res, fun=eqf.findex.value, args=[0, 1])  # vanilla, outside the trap
    guard = fb.try_()
    fb.op('JNull', reg=res, offset='end')
    fb.op('JNull', reg=0, offset='end')
    fb.op('JNull', reg=1, offset='end')
    col = fb.reg(cx.t('i32'))
    fb.op('Call1', dst=col, fun=helpers['dmode'], arg0=1)
    gs = _new_smap(fb, b, cx)  # unit id -> StringMap gear id -> bonus
    for fac, units in armory.items():
        nf = _uid('gf')
        _is_fac(fb, b, cx, 1, fac, nf)
        for s_, sname in enumerate(SETS):
            ns = _uid('gs')
            cols = (0, 1) if s_ == 0 else (s_ + 1,)
            for c in cols:
                fb.op('JEq', a=col, b=b.const('i32', c), offset=ns + 'y')
            fb.op('JAlways', offset=ns)
            fb.label(ns + 'y')
            for uid, row in units.items():
                inner = _new_smap(fb, b, cx)
                for n_, gid in enumerate(row[sname]):
                    bonus = GEAR_W + (GEAR_FIRST if n_ == 0 else 0)
                    b.call('haxe.ds.StringMap.set', inner, fb.string(gid), fb.dyn(b.const('f64', bonus)))
                b.call('haxe.ds.StringMap.set', gs, fb.string(uid), fb.dyn(inner))
            fb.op('JAlways', offset='apply')
            fb.label(ns)
        fb.op('JAlways', offset='end')
        fb.label(nf)
    fb.op('JAlways', offset='end')
    fb.label('apply')
    # anti-air counter swap: one gear on one unit kind while the enemy fields air (AIR_HOLD since the last sighting)
    airk = _new_smap(fb, b, cx)
    for aid in sorted(air_kinds()):
        b.call('haxe.ds.StringMap.set', airk, fb.string(aid), fb.dyn(b.const('i32', 1)))
    _air_check(fb, b, cx, helpers, 1, airk)
    dav = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'dair'), fb.dyn(1))
    fb.op('JNull', reg=dav, offset='noair')
    daq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=daq, src=dav)
    fb.op('Sub', dst=daq, a=b.field(_state(fb, b, cx), 'time'), b=daq)
    fb.op('JSGt', a=daq, b=b.const('f64', AIR_HOLD), offset='noair')
    for fac, (uid, gid) in aa_gear(armory).items():
        na_ = _uid('aa')
        _is_fac(fb, b, cx, 1, fac, na_)
        inn = fb.reg(cx.t('haxe.ds.StringMap'))
        iv0 = b.call('haxe.ds.StringMap.get', gs, fb.string(uid))
        fb.op('JNotNull', reg=iv0, offset=na_ + 'h')
        fb.op('Mov', dst=inn, src=_new_smap(fb, b, cx))
        b.call('haxe.ds.StringMap.set', gs, fb.string(uid), fb.dyn(inn))
        fb.op('JAlways', offset=na_ + 's')
        fb.label(na_ + 'h')
        fb.op('Mov', dst=inn, src=b.cast(iv0, 'haxe.ds.StringMap'))
        fb.label(na_ + 's')
        b.call('haxe.ds.StringMap.set', inn, fb.string(gid), fb.dyn(b.const('f64', GEAR_W + GEAR_FIRST + AIR_W)))
        fb.op('JAlways', offset='noair')
        fb.label(na_)
    fb.label('noair')
    i = fb.reg(cx.t('i32'))
    sc = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=i, src=b.const('i32', 0))
    b.loop_head('e')
    fb.op('JSGte', a=i, b=b.field(0, 'length'), offset='end')
    e = b.call('hl.types.ArrayObj.getDyn', 0, i)
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=e, offset='e')
    uk = b.cast(fb.get(e, 'unit', 'id'), 'String')
    gk = b.cast(fb.get(e, 'equipment', 'id'), 'String')
    fb.op('JNull', reg=uk, offset='e')
    fb.op('JNull', reg=gk, offset='e')
    iv = b.call('haxe.ds.StringMap.get', gs, uk)
    fb.op('JNull', reg=iv, offset='e')
    bv = b.call('haxe.ds.StringMap.get', b.cast(iv, 'haxe.ds.StringMap'), gk)
    fb.op('JNull', reg=bv, offset='e')
    fb.op('Mov', dst=sc, src=b.const('f64', 0))
    ov = b.call('haxe.ds.ObjectMap.get', res, e)
    fb.op('JNull', reg=ov, offset='e0')
    fb.op('SafeCast', dst=sc, src=ov)
    fb.label('e0')
    bf = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=bf, src=bv)
    fb.op('Add', dst=sc, a=sc, b=bf)
    b.call('haxe.ds.ObjectMap.set', res, e, fb.dyn(sc))
    fb.op('JAlways', offset='e')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=res)
    wf = fb.build()
    for s in sites:
        s.df['fun'].value = wf
    new_ids.add(wf)
    return {'dgear': 2}


def build_gear_log(cx, helpers, new_ids):
    """`gear` log: the Equipments.apply call in checkEquipments (the AI's one gear change per call) is wrapped; logs f,
    u (unit id), gr (gear id), slot, r (EReason index) after vanilla."""
    ap = cx.fn('logic.faction.Equipments.apply')
    ce = cx.fn('logic.ai.AIController.checkEquipments')
    sites = [op for op in ce.ops if op.op.startswith('Call') and op.df.get('fun') is not None
             and op.df['fun'].value == ap.findex.value]
    if len(sites) != 1:
        raise ValueError(f'gear: expected 1 Equipments.apply call in checkEquipments, found {len(sites)}')
    ft = cx.code.types[ap.type.value].definition
    fb = FB(cx, [x.value for x in ft.args], ft.ret.value, fun_type=ap.type.value)
    b = B(fb)
    r = fb.reg(ft.ret.value)
    fb.op('CallN', dst=r, fun=ap.findex.value, args=[0, 1, 2, 3])  # vanilla, outside the trap
    guard = fb.try_()
    ri = fb.reg(cx.t('i32'))
    fb.op('EnumIndex', dst=ri, value=r)
    _log_ev(fb, b, cx, helpers, 'gear', [('f', fb.get(0, 'owner', 'kind')), ('u', fb.dyn(1)), ('gr', fb.dyn(2)),
                                         ('slot', fb.dyn(3)), ('r', fb.dyn(ri))])
    fb.end_try(guard)
    fb.op('Ret', ret=r)
    w = fb.build()
    sites[0].df['fun'].value = w
    new_ids.add(w)
    return {'gear-log': 1}


def build_doctrine(cx, helpers, new_ids):
    doctrine, armory = parse_doctrine(), parse_armory()
    helpers['dmode'] = build_dmode(cx, helpers)
    new_ids.add(helpers['dmode'])
    rep = build_unit_pick(cx, helpers, doctrine, new_ids)
    rep.update(build_gear_pick(cx, helpers, armory, new_ids))
    rep.update(build_gear_log(cx, helpers, new_ids))
    return rep
