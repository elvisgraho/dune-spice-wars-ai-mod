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
    pack_check(load_state())


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


def apply_data_patches(db, strict=True):
    """strict (vanilla base): any mismatch is an error (game update). On another mod's data.cdb a row it removed or a
    value it changed is left as that mod has it (its change wins), with a warning."""
    changes = json.loads((MOD / 'patches' / 'data.json').read_text())['changes']
    n = 0
    for c in changes:
        where = f"{c['sheet']}.{c['id']}{c['path']}"
        try:
            target = db.row(c['sheet'], c['id'])
            for key in c['path'][:-1]:
                target = target[key]
            key = c['path'][-1]
            current = target[key]
        except (SystemExit, KeyError, IndexError, TypeError):
            if strict:
                raise
            print(f'WARNING: {where}: not in the other mod\'s data; skipped')
            continue
        if current == c['value']:
            n += 1
            continue
        if current != c['expected']:
            if strict:
                raise SystemExit(f"ERROR: {where}: expected {c['expected']!r}, found {current!r}")
            print(f"WARNING: {where}: the other mod set {current!r} (ours {c['value']!r}); kept theirs")
            continue
        target[key] = c['value']
        n += 1
    return n


def load_scenario(name=None):
    """testbed/scenario.json, with testbed/scenarios/<name>.json laid over it (top-level keys replace; `_doc` kept)."""
    sc = json.loads((MOD / 'testbed' / 'scenario.json').read_text())
    if name:
        path = MOD / 'testbed' / 'scenarios' / f'{name}.json'
        if not path.exists():
            raise SystemExit(f'ERROR: no scenario {path.relative_to(MOD)}')
        sc.update({k: v for k, v in json.loads(path.read_text()).items() if k != '_doc'})
        sc['name'] = name
    return sc


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

    # per-faction start resources over the shared ones (a mid / late game start: hegemony, Authority, ...)
    for faction, res_ in sc.get('factionResources', {}).items():
        if faction not in db.ids('faction'):
            raise SystemExit(f'ERROR: factionResources: unknown faction {faction}')
        start = db.row('faction', faction)['startResources']
        for res, qty in res_.items():
            if res not in resources:
                raise SystemExit(f'ERROR: factionResources.{faction}: unknown resource {res}')
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


# ---------------------------------------------------------------- other mods' packs

PACK_INFO = 'aimod.json'  # marker file inside our pack (the game loads only res.compressedN.pak: the name can't say it)


def pack_path(i):
    return GAME / ('res.compressed.pak' if i == 0 else f'res.compressed{i}.pak')


def mod_packs():
    """[(slot, path)] the game loads after the vanilla pack: res.compressed1..N up to the first gap (Main.loadPak)."""
    out, i = [], 1
    while pack_path(i).exists():
        out.append((i, pack_path(i)))
        i += 1
    return out


def is_ours(path, state=None):
    rec = (state or {}).get('pack')
    if rec and path.name == rec['name'] and sha256(path) == rec['sha256']:
        return True
    try:
        return PACK_INFO in pak.read_index(path)
    except (ValueError, OSError, IndexError):
        return False


def constant_count(raw):
    return [r['id'] for r in next(s for s in json.loads(raw)['sheets'] if s['name'] == 'constant')['lines']].index('Count')


def base_db(state):
    """(raw data.cdb, source) to build on: the data.cdb the game would use without our pack = the last other mod
    pack that has one (a later pack replaces the whole file), else vanilla. Building on it keeps that mod's changes
    (and its factions, units, ...) in the game while ours sits in the last slot."""
    vanilla = original_db()
    for _, path in reversed(mod_packs()):
        if is_ours(path, state):
            continue
        try:
            if 'data.cdb' not in pak.read_index(path):
                continue
            raw = pak.read_file(path, 'data.cdb')
        except (ValueError, OSError) as e:
            raise SystemExit(f'ERROR: {path.name} (another mod) is not a readable pack: {e}')
        if constant_count(raw) != constant_count(vanilla):
            raise SystemExit(f'ERROR: {path.name} (another mod) has a data.cdb from another game version (constants '
                             f'{constant_count(raw)} vs {constant_count(vanilla)}): the game rejects it '
                             '("Constants mismatch"). Update or remove that mod first.')
        return raw, path.name
    return vanilla, 'vanilla'


def base_fingerprint(state):
    return [[p.name, sha256(p)] for _, p in mod_packs() if not is_ours(p, state)]


def build(testbed, state=None):
    raw, source = base_db(state or load_state())
    db = Db(raw)
    if source != 'vanilla':
        print(f'Building on {source}\'s data.cdb (another mod): its changes are kept')
    n = apply_data_patches(db, strict=source == 'vanilla')
    if testbed:
        apply_scenario(db, load_scenario((state or {}).get('scenario')))
    elif not n:
        return None
    DIST.mkdir(exist_ok=True)
    raw = db.dump()
    (WORK / 'data.effective.cdb').write_bytes(raw)  # what the rules read for content lists (rules.common.game_rows)
    info = {'name': 'Dune Spice Wars AI mod (ai-mod)', 'kind': 'testbed' if testbed else 'aimod',
            'game_build': BASELINE['steam_build_id'], 'data_base': source}
    pack = pak.write({'data.cdb': raw, PACK_INFO: json.dumps(info, indent=1).encode()})
    out = DIST / ('testbed.pak' if testbed else 'aimod.pak')
    out.write_bytes(pack)
    print(f'Built {out.relative_to(MOD)}: {n} AI data change(s){" + testbed scenario" if testbed else ""}')
    return out


# ---------------------------------------------------------------- install / restore

def close_gap(slot):
    """Shift the packs after an emptied slot down by one: the game stops loading at the first gap."""
    i = slot
    while pack_path(i + 1).exists():
        pack_path(i + 1).rename(pack_path(i))
        print(f'{pack_path(i + 1).name} -> {pack_path(i).name} (another mod, load order kept)')
        i += 1


def install_pack(state, built):
    """Our pack goes in the last slot: its data.cdb (built on the other mods' one) must be the one the game uses."""
    remove_pack(state)
    base = base_fingerprint(state)
    dest = pack_path(len(mod_packs()) + 1)
    shutil.copyfile(built, dest)
    state['pack'] = {'name': dest.name, 'sha256': sha256(dest), 'kind': built.stem, 'base': base}
    others = [n for n, _ in base]
    print(f'Installed {dest.name}' + (f' (after other mods: {", ".join(others)})' if others else ''))


def remove_pack(state):
    """Our pack wherever it is (state record, else the marker inside), then close the gap behind it."""
    rec = state.pop('pack', None)
    for slot, path in mod_packs():
        if is_ours(path, {'pack': rec} if rec else None):
            path.unlink()
            print(f'Removed {path.name}')
            close_gap(slot)
            return


def pack_check(state):
    """Warn when our pack is no longer what the game uses: not last, or other mods changed since the build."""
    rec = state.get('pack')
    if not rec:
        return
    packs = mod_packs()
    if not packs or not is_ours(packs[-1][1], state):
        print(f'WARNING: our pack is not the last one loaded ({[p.name for _, p in packs]}): another mod\'s '
              'data.cdb replaces ours. Run `testbed on` / `install` again (game closed).')
    elif rec.get('base') is not None and rec['base'] != base_fingerprint(state):
        print('WARNING: other mods changed since our pack was built. Run `testbed on` / `install` again (game closed).')


def tool_hash():
    """Changes whenever the patch code changes, forcing a re-patch."""
    h = hashlib.sha256()
    files = ['tools/boot.py', 'tools/inject.py', 'tools/microtrace.py', 'tools/aware.py', 'tools/behave.py', 'testbed/ailog.json']
    files += sorted(str(p.relative_to(MOD)) for p in (MOD / 'tools' / 'rules').rglob('*.py'))  # rules/bkcamp/ too
    files += ['work/data.effective.cdb'] if (WORK / 'data.effective.cdb').exists() else []  # other mods' content
    for f in files:
        h.update((MOD / f).read_bytes())
    return h.hexdigest()[:16]


def patch_boots(state, patch_ids):
    import boot  # needs crashlink (.venv)
    BACKUP.mkdir(exist_ok=True)
    recs = state.setdefault('boot', {})
    todo = []
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
        todo.append(name)
    # both files at once (independent, ~1 min each); every check above ran first, nothing is written on an error
    results = {}
    if len(todo) > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=len(todo)) as ex:
            futs = {name: ex.submit(boot.apply, BACKUP / name, patch_ids) for name in todo}
            results = {name: f.result() for name, f in futs.items()}
    elif todo:
        results[todo[0]] = boot.apply(BACKUP / todo[0], patch_ids)
    for name in todo:
        out, report = results[name]
        path = GAME / name
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
        state['scenario'] = args.scenario
        sc = load_scenario(args.scenario)
        built = build(testbed=True, state=state)
        patch_boots(state, TESTBED_BOOT_PATCHES)
        save_state(state)
        set_prefs(state, sc)
        save_state(state)
        install_pack(state, built)
        save_state(state)
        print(f"Testbed ON{' (scenario ' + args.scenario + ')' if args.scenario else ''}. Menu: press O. In game: press P. "
              'See docs/TESTBED.md')
    else:
        cmd_uninstall(args)


def cmd_install(args):
    require_game_closed()
    state = load_state()
    if state.get('boot') or state.get('prefs'):
        raise SystemExit('ERROR: testbed is on; run `testbed off` first')
    built = build(testbed=False, state=state)
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
    state.pop('scenario', None)  # a later plain match must not run the old scenario's L macro (review)
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
    text = path.read_text(encoding='utf-8', errors='replace')
    for line in text.splitlines() + ['']:
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
    for m in re.finditer(r'AIMOD \{e : trap, src : ([\w.]+), err : (.{0,80})', text):
        k = f'{m.group(1)} ({m.group(2).split(", t : ")[0]})'
        traps[k] = traps.get(k, 0) + 1
    trap_s = ''
    if traps:
        trap_s = ' | RULE TRAPS (rule failing silently, x = rows at most 1 / 30 s): ' + '; '.join(
            f'{k} x{v}' for k, v in sorted(traps.items(), key=lambda kv: -kv[1])[:5])
    probes = len(re.findall(r'AIMOD \{e : rfail(?:,|})', text))
    if probes:
        trap_s += f' | RULE FAILURES: {probes} step-probe reports (silent rule exceptions)'
    if not errors:
        if traps or probes:
            return 'HEALTH ERROR: caught rule failures despite no uncaught game exceptions' + trap_s
        return 'HEALTH OK: no game exceptions in game.log' + trap_s
    top = ', '.join(f'{k} x{v}' for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])[:3])
    verdict = 'INJECTED CODE IS FAILING - run `testbed off` and report' if ours else 'not from injected code'
    return f'HEALTH: {errors} game exceptions ({ours} through injected code: {verdict}). {top}' + trap_s


def cmd_log(args):
    import aireport
    import logarchive
    import logfeedback
    import logdata
    for name in ('entity', 'order', 'session'):
        if getattr(args, name) is not None and getattr(args, name) <= 0:
            raise ValueError(f'--{name} must be a positive integer')
    src = Path(args.file) if args.file else GAME / 'game.log'
    raw = src.read_bytes()
    decode_errors = False
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        decode_errors = True
        text = raw.decode('utf-8', errors='replace')
    lines = text.splitlines()
    provenance = logarchive.inspect_archive(src, raw)
    crumbs = logarchive.source_map(src, provenance) if args.file else None
    archived = None
    if not args.file and 'AIMOD {' in text:
        installed = load_state().get('boot', {})
        tools_match = (set(installed) == set(BOOTS)
                       and {record.get('tool') for record in installed.values()} == {tool_hash()})
        boots_match = tools_match and all(sha256(GAME / name) == installed[name]['patched'] for name in BOOTS)
        log_is_newer = boots_match and src.stat().st_mtime_ns >= max((GAME / name).stat().st_mtime_ns for name in BOOTS)
        tools_match = bool(tools_match and boots_match and log_is_newer)
        if tools_match and (WORK / 'crumbs.json').exists():
            crumbs = json.loads((WORK / 'crumbs.json').read_text(encoding='utf-8'))
        archived = logarchive.archive(raw, WORK / 'logs', {'installed_boots': installed, 'crumbs': crumbs,
                                      'source_map_matches_build': tools_match})
        provenance = logarchive.inspect_archive(archived, raw)
        crumbs = logarchive.source_map(archived, provenance)
    health_text = health(src) if '[Game]' in text else 'HEALTH unavailable: AIMOD-only log; original game exceptions were not archived'
    events = aireport.parse_lines(lines)
    prepared = logdata.prepare(events)
    sessions = logdata.sessions(prepared)
    if args.session is not None and args.session not in sessions:
        raise ValueError(f'session {args.session} is not present; available sessions: {sessions}')
    if len(sessions) > 1:
        crumbs = None  # one sidecar cannot establish the build map for every concatenated run
        if args.session is None and (args.details or args.all or args.score or args.around):
            raise ValueError('multiple sessions detected; choose --session N for a detailed report or timeline')
    selected = [e for e in prepared if logdata.matches(e, args.faction, args.event, args.entity, args.order, args.session)]
    report = logfeedback.analyze(events, args.faction, args.event, crumbs, args.entity, args.order, args.session)
    report.update(health=health_text, archive=str(archived) if archived else None, source_map_available=crumbs is not None,
                  source={'path': str(src.resolve()), 'sha256': logarchive.digest(raw), 'bytes': len(raw),
                          'decode_errors': decode_errors},
                  provenance={k: v for k, v in provenance.items() if k != 'metadata'})

    def finish():
        if args.strict and (not selected or decode_errors or provenance['status'] in ('invalid', 'mismatch')
                            or health_text.startswith(('HEALTH ERROR', 'HEALTH:'))
                            or logfeedback.failed_validation(report)):
            print('STRICT: damaged/incomplete telemetry, integrity failure, or logged errors', file=sys.stderr)
            raise SystemExit(2)

    if args.events_jsonl:
        for e in selected:
            print(json.dumps(logdata.export_record(e, report['source']['sha256']), allow_nan=False))
        finish()
        return
    if args.raw:
        print('\n'.join(lines[e['_line'] - 1][lines[e['_line'] - 1].find('AIMOD'):]
                        for e in selected))
        finish()
        return
    if args.json:
        print(json.dumps(report, indent=2, allow_nan=False))
        finish()
        return
    print(health_text)
    print(f'Source: {report["source"]["sha256"][:16]} | archive={provenance["status"]} | source map={crumbs is not None}')
    if provenance['issues'] or decode_errors:
        print('DATA WARNING: ' + '; '.join(provenance['issues'] + (['invalid UTF-8; original bytes preserved'] if decode_errors else [])))
    if args.score:
        import scorecard
        print(scorecard.scorecard([e for e in selected if not e['_validation_errors'] and e.get('_parse', 'full') == 'full']))
    elif args.around:
        print(aireport.around(selected, aireport.parse_clock(args.around), args.window, args.faction,
                              include_noisy=bool(args.event)))
    elif args.details or args.all:
        print(aireport.summarize([e for e in selected if not e['_validation_errors'] and e.get('_parse', 'full') == 'full'],
                                args.faction, args.all, crumbs=crumbs))
    else:
        print(logfeedback.format_feedback(report))
    if archived:
        print(f'Archive: {archived}')
    finish()


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
    t.add_argument('--scenario', help='overlay testbed/scenarios/<name>.json on testbed/scenario.json (e.g. late)')
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
    view = lg.add_mutually_exclusive_group()
    view.add_argument('--raw', action='store_true', help='print raw AIMOD lines')
    view.add_argument('--details', action='store_true', help='full legacy report instead of concise feedback')
    view.add_argument('--json', action='store_true', help='machine-readable feedback, coverage and all findings')
    view.add_argument('--events-jsonl', action='store_true', help='normalized event records with source hash, session, line and validation errors')
    lg.add_argument('--event', action='append', metavar='KIND', help='only this event kind; repeat to combine kinds')
    lg.add_argument('--entity', type=int, help='events referencing this entity ID (including targets and awareness arrays)')
    lg.add_argument('--order', type=int, help='events carrying this exact order ID')
    lg.add_argument('--session', type=int, help='one detected match session; required for multi-session detailed views')
    lg.add_argument('--strict', action='store_true', help='exit 2 on malformed/incomplete data, integrity failures, or logged errors')
    view.add_argument('--score', action='store_true', help='per-faction scorecard: outcomes per task kind, economy')
    view.add_argument('--around', metavar='MM:SS', help='timeline of all decisions near a game time (e.g. a mark)')
    lg.add_argument('--window', type=int, default=60, help='seconds either side for --around (default 60)')
    sub.add_parser('launch', help='start the game through Steam')
    m = sub.add_parser('match', help='unattended testbed match: launch, O P Tab F10, run N minutes, close')
    m.add_argument('minutes', nargs='?', type=float, default=17)
    a = p.parse_args()
    if a.cmd == 'match':
        # a scenario's `lateMinutes`: the match script presses L (the scenario's mid-match macro) that long after start
        st_ = load_state()  # only while a testbed with a scenario is installed (prefs hold its macros)
        late = load_scenario(st_.get('scenario')).get('lateMinutes', 0) if st_.get('prefs') and st_.get('scenario') else 0
        raise SystemExit(subprocess.call(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                          str(Path(__file__).with_name('match.ps1')), '-Minutes', str(a.minutes),
                                          '-LateMin', str(late)]))
    {'verify': lambda _: verify(), 'build': lambda _: build(False) or print('No AI data changes'),
     'install': cmd_install, 'uninstall': cmd_uninstall, 'testbed': cmd_testbed, 'index': cmd_index,
     'find': cmd_find, 'dec': cmd_dec, 'log': cmd_log, 'launch': lambda _: os.startfile('steam://rungameid/1605220')}[a.cmd](a)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as e:
        raise SystemExit(f'ERROR: {e}')
