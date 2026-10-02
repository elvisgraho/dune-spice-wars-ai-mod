#!/usr/bin/env python3
"""Dune: Spice Wars AI mod tool. Run via `ai-mod\\mod.cmd <command>` (uses the .venv).

Game files are only modified by `install`, `testbed on` and `uninstall`; originals are
hash-checked and backed up to ai-mod/backup/ first. Close the game before those commands.
"""
import argparse
import hashlib
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import hxser
import pak

MOD = Path(__file__).resolve().parents[1]
GAME = MOD.parent
WORK, DIST, BACKUP = MOD / 'work', MOD / 'dist', MOD / 'backup'
STATE = WORK / 'state.json'
BASELINE = json.loads((MOD / 'baseline.json').read_text())
BOOTS = ('hlboot.dat', 'hlbootdx.dat')
TESTBED_BOOT_PATCHES = ['admin-always-on', 'ai-log']
MACRO_KEYS = {'O': 0, 'P': 1, 'K': 2, 'L': 3, 'F9': 4, 'F10': 5}  # Menu/Game.adminKeys slot order


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(state):
    WORK.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2))


def require_game_closed():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq D4X.exe'], capture_output=True, text=True).stdout
    if 'D4X.exe' in out:
        raise SystemExit('ERROR: close the game first (it rewrites prefs.sav and locks boot files)')


# ---------------------------------------------------------------- baseline / data

def verify():
    bad = [n for n, h in BASELINE['files'].items() if sha256(GAME / n) != h and not patched_by_us(n)]
    if bad:
        raise SystemExit(f'ERROR: files differ from baseline build {BASELINE["steam_build_id"]}: {bad}. '
                         'Game updated? Re-verify all function lookups, then update baseline.json.')
    print(f'OK: build {BASELINE["steam_build_id"]} (patched by us: {[n for n in BOOTS if patched_by_us(n)] or "none"})')


def patched_by_us(name):
    rec = load_state().get('boot', {}).get(name)
    return bool(rec) and (GAME / name).exists() and sha256(GAME / name) == rec['patched']


def original_db():
    cached = WORK / 'data.original.cdb'
    if cached.exists() and hashlib.sha256(cached.read_bytes()).hexdigest() == BASELINE['database_sha256']:
        return cached.read_bytes()
    raw = pak.read_file(GAME / 'res.compressed.pak', 'data.cdb')
    if hashlib.sha256(raw).hexdigest() != BASELINE['database_sha256']:
        raise SystemExit('ERROR: data.cdb differs from baseline')
    WORK.mkdir(exist_ok=True)
    cached.write_bytes(raw)
    return raw


class Db:
    def __init__(self, raw):
        self.doc = json.loads(raw)
        self.sheets = {s['name']: s for s in self.doc['sheets']}

    def rows(self, sheet):
        return self.sheets[sheet]['lines']

    def row(self, sheet, rid):
        hits = [r for r in self.rows(sheet) if r.get('id') == rid]
        if len(hits) != 1:
            raise SystemExit(f'ERROR: {sheet}.{rid}: expected 1 row, found {len(hits)}')
        return hits[0]

    def ids(self, sheet):
        return {r.get('id') for r in self.rows(sheet)}

    def dump(self):
        return json.dumps(self.doc, ensure_ascii=False, indent='\t', allow_nan=False).encode('utf-8')


def apply_data_patches(db):
    changes = json.loads((MOD / 'patches' / 'data.json').read_text())['changes']
    for c in changes:
        target = db.row(c['sheet'], c['id'])
        for key in c['path'][:-1]:
            target = target[key]
        key = c['path'][-1]
        if target[key] != c['expected']:
            raise SystemExit(f"ERROR: {c['sheet']}.{c['id']}{c['path']}: expected {c['expected']!r}, found {target[key]!r}")
        target[key] = c['value']
    return len(changes)


def apply_scenario(db, sc):
    factions = sc['factions']
    unknown = set(factions) - db.ids('faction')
    if unknown or not 2 <= len(factions) <= 7 or not 0 <= sc['humanSlot'] < len(factions):
        raise SystemExit(f'ERROR: scenario factions/humanSlot invalid ({unknown or factions})')
    db.row('gameMode', 'Default')['props']['playableFactions'] = [{'ref': f, 'availableForAI': True} for f in factions]
    db.row('mapType', 'AllFactions')['props']['numCells'] = sc['mapCells']

    units = {u['id']: u for u in db.rows('unit')}
    resources = db.ids('resource')
    for faction, army in sc['armies'].items():
        if faction not in db.ids('faction'):
            raise SystemExit(f'ERROR: armies: unknown faction {faction}')
        bad = [u for u in army if units.get(u, {}).get('faction') != faction]
        if bad:
            raise SystemExit(f'ERROR: armies.{faction}: not units of that faction: {bad}')
        bases = [s for s in db.rows('structure') if not s['id'].startswith('TEST')
                 and any(units.get(e['unit'], {}).get('faction') == faction for e in s.get('startUnits') or [])]
        if len(bases) != 1:
            raise SystemExit(f'ERROR: {faction}: expected one main base with startUnits, found {[b["id"] for b in bases]}')
        bases[0]['startUnits'] += [{'unit': u} for u in army]
        start = db.row('faction', faction)['startResources']
        for res, qty in sc['startResources'].items():
            if res not in resources:
                raise SystemExit(f'ERROR: startResources: unknown resource {res}')
            entry = next((e for e in start if e['res'] == res and not e.get('gameMode')), None)
            if entry:
                entry['qty'] = qty
            else:
                start.append({'qty': qty, 'res': res})

    for cid, value in sc.get('constants', {}).items():
        row = db.row('constant', cid)
        if isinstance(value, list):
            if len(value) != len(row.get('values', [])):
                raise SystemExit(f'ERROR: constant {cid}: expected {len(row.get("values", []))} per-difficulty values')
            for slot, v in zip(row['values'], value):
                slot['val'] = v
        else:
            row['value'] = value


def build(testbed):
    db = Db(original_db())
    n = apply_data_patches(db)
    if testbed:
        apply_scenario(db, json.loads((MOD / 'testbed' / 'scenario.json').read_text()))
    elif not n:
        return None
    DIST.mkdir(exist_ok=True)
    raw = db.dump()
    pack = pak.write({'data.cdb': raw})
    out = DIST / ('testbed.pak' if testbed else 'aimod.pak')
    out.write_bytes(pack)
    print(f'Built {out.relative_to(MOD)}: {n} AI data change(s){" + testbed scenario" if testbed else ""}')
    return out


# ---------------------------------------------------------------- install / restore

def pack_slot(state):
    if state.get('pack'):
        return GAME / state['pack']['name']
    i = 1
    while (GAME / f'res.compressed{i}.pak').exists():
        i += 1  # game loads res.compressed1..N until the first gap; never overwrite others' packs
    return GAME / f'res.compressed{i}.pak'


def install_pack(state, built):
    dest = pack_slot(state)
    if dest.exists() and (not state.get('pack') or sha256(dest) != state['pack']['sha256']):
        raise SystemExit(f'ERROR: {dest.name} was modified by something else; resolve manually')
    shutil.copyfile(built, dest)
    state['pack'] = {'name': dest.name, 'sha256': sha256(dest), 'kind': built.stem}
    print(f'Installed {dest.name}')


def remove_pack(state):
    rec = state.pop('pack', None)
    if rec and (GAME / rec['name']).exists():
        if sha256(GAME / rec['name']) != rec['sha256']:
            raise SystemExit(f'ERROR: {rec["name"]} changed since install; not removing')
        (GAME / rec['name']).unlink()
        print(f'Removed {rec["name"]}')


def tool_hash():
    """Changes whenever the patch code changes, forcing a re-patch."""
    h = hashlib.sha256()
    files = ['tools/boot.py', 'tools/inject.py', 'tools/aware.py', 'tools/behave.py', 'testbed/ailog.json']
    files += sorted(str(p.relative_to(MOD)) for p in (MOD / 'tools' / 'rules').glob('*.py'))
    for f in files:
        h.update((MOD / f).read_bytes())
    return h.hexdigest()[:16]


def patch_boots(state, patch_ids):
    import boot  # needs crashlink (.venv)
    BACKUP.mkdir(exist_ok=True)
    recs = state.setdefault('boot', {})
    for name in BOOTS:
        path = GAME / name
        current = sha256(path)
        ours = name in recs and current == recs[name]['patched']
        if ours and recs[name]['patches'] == patch_ids and recs[name].get('tool') == tool_hash():
            print(f'{name}: already patched')
            continue
        if ours:  # patch set or injector changed: start again from the verified original
            if sha256(BACKUP / name) != BASELINE['files'][name]:
                raise SystemExit(f'ERROR: backup of {name} is invalid; use Steam > Verify files')
        elif current == BASELINE['files'][name]:
            shutil.copyfile(path, BACKUP / name)
        else:
            raise SystemExit(f'ERROR: {name} is not the baseline original; restore it (Steam > Verify files) first')
        out, report = boot.apply(BACKUP / name, patch_ids)
        path.write_bytes(out)
        recs[name] = {'patches': patch_ids, 'patched': sha256(path), 'tool': tool_hash()}
        print(f'{name}: patched {report}')


def restore_boots(state):
    for name, rec in list(state.get('boot', {}).items()):
        path, backup = GAME / name, BACKUP / name
        if sha256(path) == rec['patched']:
            if sha256(backup) != BASELINE['files'][name]:
                raise SystemExit(f'ERROR: backup of {name} is invalid; use Steam > Verify files')
            shutil.copyfile(backup, path)
            print(f'{name}: restored')
        else:
            print(f'{name}: not our patched version (game updated?); left untouched')
        del state['boot'][name]


def expand_macros(sc):
    wars = [f'relationship {a} {b} War' for a, b in itertools.combinations(sc['factions'], 2)]
    slots = [[] for _ in MACRO_KEYS]
    for key, cmds in sc['macros'].items():
        out = []
        for c in cmds:
            out += wars if c == '{WAR_ALL}' else [c.replace('{humanSlot}', str(sc['humanSlot']))]
        slots[MACRO_KEYS[key]] = out
    return slots


def set_prefs(state, sc):
    path = GAME / 'prefs.sav'
    prefs = hxser.load_save(path.read_text(encoding='utf-8'))
    state.setdefault('prefs', {'shortcutCommands': prefs['shortcutCommands'], 'noFog': prefs['admin']['noFog']})
    prefs['shortcutCommands'] = expand_macros(sc)
    prefs['admin']['noFog'] = bool(sc['noFog'])
    path.write_text(hxser.dump_save(prefs), encoding='utf-8')
    print('prefs.sav: macros ' + ', '.join(f'{k}={len(v)}' for k, v in zip(MACRO_KEYS, prefs['shortcutCommands'])))


def restore_prefs(state):
    old = state.pop('prefs', None)
    if not old:
        return
    path = GAME / 'prefs.sav'
    prefs = hxser.load_save(path.read_text(encoding='utf-8'))
    prefs['shortcutCommands'], prefs['admin']['noFog'] = old['shortcutCommands'], old['noFog']
    path.write_text(hxser.dump_save(prefs), encoding='utf-8')
    print('prefs.sav: restored macros/fog')


# ---------------------------------------------------------------- commands

def cmd_testbed(args):
    state = load_state()
    if args.action == 'status':
        print(json.dumps(state, indent=2) if state else 'Nothing installed')
        return
    require_game_closed()
    if args.action == 'on':
        verify()
        sc = json.loads((MOD / 'testbed' / 'scenario.json').read_text())
        built = build(testbed=True)
        patch_boots(state, TESTBED_BOOT_PATCHES)
        save_state(state)
        set_prefs(state, sc)
        save_state(state)
        install_pack(state, built)
        save_state(state)
        print('Testbed ON. Menu: press O. In game: press P. See docs/TESTBED.md')
    else:
        cmd_uninstall(args)


def cmd_install(args):
    require_game_closed()
    state = load_state()
    if state.get('boot') or state.get('prefs'):
        raise SystemExit('ERROR: testbed is on; run `testbed off` first')
    built = build(testbed=False)
    if not built:
        raise SystemExit('Nothing to install: patches/data.json is empty')
    install_pack(state, built)
    save_state(state)


def cmd_uninstall(args):
    require_game_closed()
    state = load_state()
    remove_pack(state)
    restore_prefs(state)
    restore_boots(state)
    save_state(state)
    print('Game restored to vanilla (our files only)')


def funcs_index():
    idx = WORK / 'funcs.tsv'
    if not idx.exists():
        cmd_index(None)
    return [line.split('\t', 1) for line in idx.read_text(encoding='utf-8').splitlines()]


def health(path):
    """Game exceptions in game.log; injected functions have debug info 'hxd/App.hx line 0'."""
    errors, ours, kinds = 0, 0, {}
    block = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines() + ['']:
        if re.match(r'^\s*[\d.]+\s+\[Game\] ', line) or not line.strip():
            if block and ('Access violation' in block[0] or 'Invalid' in block[0] or 'Exception' in block[0]
                          or 'Null access' in block[0]):
                errors += 1
                msg = block[0].split('] ', 1)[-1][:60]
                kinds[msg] = kinds.get(msg, 0) + 1
                ours += any('hxd/App.hx line 0' in b for b in block)
            block = [line] if line.strip() else []
        elif block:
            block.append(line)
    # exceptions our rules caught themselves (rules.common.make_trap_hook: `trap` rows, 1 per rule per 30 s)
    traps = {}
    for m in re.finditer(r'AIMOD \{e : trap, src : ([\w.]+), err : (.{0,80})', path.read_text(encoding='utf-8',
                                                                                         errors='replace')):
        k = f'{m.group(1)} ({m.group(2).split(", t : ")[0]})'
        traps[k] = traps.get(k, 0) + 1
    trap_s = ''
    if traps:
        trap_s = ' | RULE TRAPS (rule failing silently, x = rows at most 1 / 30 s): ' + '; '.join(
            f'{k} x{v}' for k, v in sorted(traps.items(), key=lambda kv: -kv[1])[:5])
    if not errors:
        return 'HEALTH OK: no game exceptions in game.log' + trap_s
    top = ', '.join(f'{k} x{v}' for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])[:3])
    verdict = 'INJECTED CODE IS FAILING - run `testbed off` and report' if ours else 'not from injected code'
    return f'HEALTH: {errors} game exceptions ({ours} through injected code: {verdict}). {top}' + trap_s


def cmd_log(args):
    import aireport
    src = Path(args.file) if args.file else GAME / 'game.log'
    lines = [l for l in src.read_text(encoding='utf-8', errors='replace').splitlines() if 'AIMOD {' in l]
    if not args.file and lines:  # game.log is overwritten each launch: archive it
        logs = WORK / 'logs'
        logs.mkdir(parents=True, exist_ok=True)
        text = '\n'.join(lines)
        digest = hashlib.sha256(text.encode()).hexdigest()[:10]
        if not any(p.name.endswith(f'{digest}.log') for p in logs.iterdir()):
            import datetime
            (logs / f'{datetime.datetime.now():%Y%m%d-%H%M}-{digest}.log').write_text(text, encoding='utf-8')
    if not args.file:
        print(health(src))
    events = aireport.parse_lines(lines)
    if args.around:
        print(aireport.around(events, aireport.parse_clock(args.around), args.window, args.faction))
    elif args.raw:
        print('\n'.join(l[l.find('AIMOD'):] for l in lines if not args.faction or args.faction in l))
    else:
        print(aireport.summarize(events, args.faction, args.all))


def cmd_index(args):
    import boot
    code = boot.load(GAME / 'hlboot.dat')
    WORK.mkdir(exist_ok=True)
    (WORK / 'funcs.tsv').write_text('\n'.join(f'{f.findex.value}\t{boot._name(code, f)}' for f in code.functions),
                                    encoding='utf-8')
    (WORK / 'strings.txt').write_text('\n'.join(s.replace('\n', '\\n') for s in code.strings.value), encoding='utf-8')
    print(f'Indexed {len(code.functions)} functions, {len(code.strings.value)} strings -> work/')


def cmd_find(args):
    rx = re.compile('|'.join(f'(?:{x})' for x in args.pattern), re.I)
    if args.strings:
        for i, s in enumerate((WORK / 'strings.txt').read_text(encoding='utf-8').splitlines()):
            if rx.search(s):
                print(i, s[:200])
    else:
        for fid, name in funcs_index():
            if rx.search(name):
                print(fid, name)


def cmd_dec(args):
    import boot
    names = {name: int(fid) for fid, name in funcs_index()}
    code = boot.load(GAME / 'hlboot.dat')
    for target in args.targets:
        fid = int(target) if target.isdigit() else names.get(target)
        if fid is None:
            print(f'// not found: {target} (use `find`; names look like logic.ai.AIUnits.pickUnits)')
            continue
        print(f'// f@{fid}')
        try:
            print(boot.disasm(code, fid) if args.asm else boot.decompile(code, fid))
        except Exception as e:  # decompiler is incomplete on some functions
            print(f'// decompile failed ({e}); falling back to disassembly')
            print(boot.disasm(code, fid))


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('verify', help='check game files match baseline.json')
    sub.add_parser('build', help='build dist/aimod.pak from patches/data.json (no install)')
    sub.add_parser('install', help='install the AI mod data pack')
    sub.add_parser('uninstall', help='remove everything we installed (pack, boot patch, prefs macros)')
    t = sub.add_parser('testbed', help='combat test harness: on | off | status')
    t.add_argument('action', choices=['on', 'off', 'status'])
    sub.add_parser('index', help='write work/funcs.tsv + work/strings.txt from hlboot.dat')
    f = sub.add_parser('find', help='regex search function names (or --strings); several patterns = OR')
    f.add_argument('pattern', nargs='+')
    f.add_argument('--strings', action='store_true')
    d = sub.add_parser('dec', help='decompile functions by findex or full name')
    d.add_argument('targets', nargs='+')
    d.add_argument('--asm', action='store_true', help='raw disassembly instead of pseudo-Haxe')
    lg = sub.add_parser('log', help='summarize AI decisions from game.log (testbed ai-log); archives to work/logs/')
    lg.add_argument('file', nargs='?', help='a work/logs/*.log file instead of game.log')
    lg.add_argument('--faction')
    lg.add_argument('--all', action='store_true', help='include non-military orders')
    lg.add_argument('--raw', action='store_true', help='print raw AIMOD lines')
    lg.add_argument('--around', metavar='MM:SS', help='timeline of all decisions near a game time (e.g. a mark)')
    lg.add_argument('--window', type=int, default=60, help='seconds either side for --around (default 60)')
    sub.add_parser('launch', help='start the game through Steam')
    a = p.parse_args()
    {'verify': lambda _: verify(), 'build': lambda _: build(False) or print('No AI data changes'),
     'install': cmd_install, 'uninstall': cmd_uninstall, 'testbed': cmd_testbed, 'index': cmd_index,
     'find': cmd_find, 'dec': cmd_dec, 'log': cmd_log, 'launch': lambda _: os.startfile('steam://rungameid/1605220')}[a.cmd](a)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as e:
        raise SystemExit(f'ERROR: {e}')
