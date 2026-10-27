"""CastleDB sheet reads, constant indices and faction building support.

Owns the per-process data cache used while building both boot files.
"""
import json
from pathlib import Path

_WORK = Path(__file__).resolve().parents[2] / 'work'
_DB = {}


def game_rows(sheet, vanilla=True):
    """Rows of a data.cdb sheet: vanilla = this build's own data (work/data.original.cdb), else the data the game
    runs with (work/data.effective.cdb: other mods' data + ours, written by `mod build`; vanilla if absent)."""
    key = 'original' if vanilla or not (_WORK / 'data.effective.cdb').exists() else 'effective'
    if key not in _DB:
        _DB[key] = {s['name']: s for s in json.loads((_WORK / f'data.{key}.cdb').read_text(encoding='utf-8'))['sheets']}
    return _DB[key][sheet]['lines'] if sheet in _DB[key] else []


def const_index(cid):
    """Row index of data constant `cid` (= its Const.valueCache / fValuesCache index) in this build's vanilla data.
    Game updates insert constants and shift every later index, so never write the number itself."""
    return [r['id'] for r in game_rows('constant')].index(cid)


def no_building_factions(bid):
    """Factions that can never build `bid` (its props notForFactions / onlyForFactions), modded factions included."""
    row = next((r for r in game_rows('building', False) if r.get('id') == bid), None)
    facs = [r['id'] for r in game_rows('faction', False)]
    if row is None:
        return tuple(facs)
    props = row.get('props') or {}
    only = [e.get('faction') for e in props.get('onlyForFactions') or []]
    return tuple(f for f in facs if f in [e.get('faction') for e in props.get('notForFactions') or []]
                 or (only and f not in only))
