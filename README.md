# Dune: Spice Wars AI mod

Better skirmish AI, with combat first: engagement, retreat, targeting and army cohesion, then economy and diplomacy.
AI rules run through the testbed patch. The data pack can also be installed separately.
Pinned game build: 26131664, game version 2.2.8.33024.

Read [progress.md](progress.md) for current work. Before changing AI behavior, read
[AI-POLICY.md](docs/AI-POLICY.md) and [ARCHITECTURE-PLAN.md](docs/ARCHITECTURE-PLAN.md).
Both are binding: use the shared world model, battle forecast and task claims instead of private measures.

## Start and inspect a match

Run from the game directory:

```powershell
powershell -ExecutionPolicy Bypass -File ai-mod\setup.ps1
ai-mod\mod.cmd testbed on --scenario raze
ai-mod\mod.cmd match 20
ai-mod\mod.cmd log
```

Close the game before installation or removal. For manual play, `mod.cmd launch` starts through Steam;
press O in the main menu, then P in game. Tab takes control of a faction and can disable its AI; press P to restore it.

- [CHEATSHEET.md](docs/CHEATSHEET.md): commands, hotkeys and console reference.
- [TESTBED.md](docs/TESTBED.md): scenarios, unattended matches and log/export formats.
- [REVERSING.md](docs/REVERSING.md): verified engine facts, hook points and function identities.
- [AI-POLICY.md](docs/AI-POLICY.md): rule behavior, priorities and thresholds.
- [strategy/GENERAL.md](docs/strategy/GENERAL.md): expert-play reference;
  [CANDIDATES.md](docs/strategy/CANDIDATES.md): ideas to evaluate.

## Change and verify AI behavior

1. Reproduce a weakness in the testbed. Press L to mark an incident and inspect it with `mod log`.
2. Check the policy and architecture, then locate code with `mod find` and `mod dec`.
   Read existing findings before researching the same path again.
3. Prefer `patches/data.json` when data can express the change. Put code rules under `tools/rules/`
   and wire them through `tools/behave.py`.
4. Run `.venv\Scripts\python.exe tools\bcheck.py`; it must report zero issues.
   Review new findings before changing `tools/bcheck_baseline.txt`.
5. Rebuild with `mod.cmd testbed on`, run through Steam, and check health plus the intended behavioral metric.
   A direct `D4X.exe` launch is not a valid test of patched boot files.
6. For a data-pack release, run `testbed off`, then `install`.

Patch code by function name and expected instruction, never by a function ID shared between boot files.
Both `hlboot.dat` and `hlbootdx.dat` must patch and re-parse. Keep CastleDB row order and IDs unchanged;
resolve constants by name. Use `mod.cmd` for installed game files; it checks hashes and keeps backups.
Game updates require `verify`, a locator review and an updated `baseline.json`.
Do not play online with the testbed installed.

## Engine and installation boundaries

- Haxe compiles to HashLink bytecode. Names and source lines survive; crashlink round-trips the boot files.
  The anti-piracy hash does not cover those files.
- Packs load as `res.compressed.pak`, then numbered packs up to the first gap. A later `data.cdb` replaces the
  whole table set. Constant `Count` must remain at its compiled index, 1310 for this pinned build.
- Our installer takes the last pack slot, merges the last other mod's data into `work/data.effective.cdb`, and
  preserves conflicting values changed by that mod with a warning. `aimod.json` identifies our pack. Another
  version's data or externally patched boot files are refused; uninstall closes pack-number gaps.
- `prefs.sav` is Haxe-serialized and rewritten on exit. `tools/hxser.py` implements its checksum,
  `sha1(d+sha1(d+"s*al!t"))[4:36]`; edit only while the game is closed.

## Code structure and refactor checks

| Location | Responsibility |
|---|---|
| `tools/mod.py`, `tools/match.ps1` | Installation, CLI and unattended matches |
| `tools/boot.py`, `tools/inject.py`, `tools/aware.py` | Bytecode patches, diagnostic wrappers and world scan |
| `tools/behave.py`, `tools/rules/` | Rule wiring and behavior emitters |
| `rules/common.py`, `thresholds.py`, `game_data.py` | Bytecode helpers/build state, shared tuning and CastleDB access |
| `rules/world.py`, `forecast.py`, `tasks.py`, `value.py`, `board.py` | Shared queries, forecasts, claims, values and task ranking |
| `rules/heal/`, `hunt/`, `annex/`, `opsbrain/`, `bkcamp/` | Rule packages split by responsibility |
| `tools/aireport.py`, `logfeedback.py`, `logdata.py`, `logarchive.py`, `scorecard.py` | Reports, validation, export and archives |
| `patches/`, `testbed/`, `validation/` | Patch definitions, scenarios and evidence records |
| `.venv/`, `work/`, `dist/`, `backup/` | Generated files, ignored by Git |

A rule module has one concern and stays within 1,300 lines. Thresholds need names and a short reason;
shared values live in `rules/thresholds.py`, re-exported by `rules/common.py`.
Import package helpers from their owning modules. Shared support depends in one direction:
`common` -> `thresholds` -> `game_data`. `common` owns mutable emitter state; `game_data` owns `_DB`.
Module docstrings explain the failure a rule fixes; REVERSING holds its hook points.
`RULE_LOG_GROUP` preserves diagnostic identities across file moves while source maps retain physical paths.

A pure refactor must produce byte-identical boot files. From `ai-mod/`, save a fresh baseline before editing:

```powershell
.venv\Scripts\python.exe tools\bhash.py --save work\refactor-before.json
.venv\Scripts\python.exe tools\check_rule_size.py
.venv\Scripts\python.exe tools\bhash.py --check work\refactor-before.json
.venv\Scripts\python.exe tools\bcheck.py
```

`bhash` fixes `PYTHONHASHSEED=0`, refuses to overwrite a baseline, and fails if either boot's hash or size changes.
Tool regression tests run with `.venv\Scripts\python.exe -m unittest discover -s tools -p 'test_*.py'`.
Campaign regressions execute bounded sections of the emitted bytecode with explicit engine fixtures
(`tools/campaign_probe.py`, `tools/test_campaign_review.py`). `$env:AIMOD_TEST_BOOT='hlbootdx.dat'` selects the
DirectX boot for that targeted test module; the default is `hlboot.dat`.

## Documentation rule (mandatory)

Docs describe the current state. Keep match narratives and completed implementation steps out of active references.

- README owns orientation and workflow; CHEATSHEET owns command lookup; TESTBED owns testing and logging.
  AI-POLICY owns behavior; REVERSING owns code facts. Link to the owner instead of copying its catalog.
- `progress.md` owns current checks, unresolved issues and next work. Keep evidence only where it justifies an open
  issue. Remove passed checks; after three matches without coverage, trigger the case deliberately or drop the check.
- Mark unverified behavior explicitly. Update findings in the same session. Keep ruled-out approaches terse so
  later work does not repeat them.
- [Earlier match notes](docs/archive/progress-log-2026-10.md) are frozen history, not the default reading path.
  Superseded prose is recoverable from Git; do not create another archive for routine edits.
