# Dune: Spice Wars — AI mod

Goal: better skirmish AI, **combat first** (engage/retreat, targeting, army cohesion), then economy/diplomacy.

State: tooling, combat testbed and AI decision logging work in-game. AI behavior rules (tools/rules/, wired by tools/behave.py) run in the testbed only; open checks are in [progress.md](progress.md).

**Read in this order:** this file → [progress.md](progress.md) → [docs/AI-POLICY.md](docs/AI-POLICY.md) (**binding** for any AI behavior change) → [docs/REVERSING.md](docs/REVERSING.md) (code facts, ids) → [docs/TESTBED.md](docs/TESTBED.md). Expert-play knowledge per faction and the implementable ideas from it: [docs/strategy/](docs/strategy/GENERAL.md) ([CANDIDATES](docs/strategy/CANDIDATES.md)). Don't re-research anything listed under Key facts.

## Quick start (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File ai-mod\setup.ps1   # once: venv, crashlink, verify, index
ai-mod\mod.cmd testbed on                                    # game closed
```
Main menu: **O** starts the test match; in game press **P** once. Details: [docs/TESTBED.md](docs/TESTBED.md), all keys/commands: [docs/CHEATSHEET.md](docs/CHEATSHEET.md).

## Commands (`ai-mod\mod.cmd <cmd>`)

| Command | Does |
|---|---|
| `verify` | Game files match [baseline.json](baseline.json) (build 19145763) |
| `testbed on/off/status` | Install/remove the test harness (data pack, boot patches, hotkey macros) |
| `build` / `install` / `uninstall` | Build/install the release data pack from `patches/data.json`; `uninstall` reverts **all** our changes |
| `index` | Write `work/funcs.tsv` + `work/strings.txt` from `hlboot.dat` |
| `find <regex>...` | Search function names (`--strings` for the string table). Several args = OR (don't type `\|` in cmd) |
| `dec <findex or name>... [--asm]` | Decompile to pseudo-Haxe (or disassemble) |
| `log [file] [--faction F] [--all] [--raw] [--around MM:SS]` | Summarize AI decisions from `game.log` (`--faction` also filters `--around`); archives raw lines to `work/logs/` |
| `launch` | Start the game through Steam |

## Key facts (build 19145763)

Details and function ids: [docs/REVERSING.md](docs/REVERSING.md).

**Engine and files**
- Haxe → HashLink bytecode in `hlboot.dat` / `hlbootdx.dat` (DirectX). Names and source lines survive. crashlink round-trips both files byte-identically and decompiles to pseudo-Haxe. Function ids differ between the two files: resolve by name.
- `data.cdb` (CastleDB JSON) inside `res.compressed.pak`. Mods add `res.compressed1.pak`, `2`, …; a later pack replaces the whole `data.cdb`. Constants are read by row index: never reorder or delete rows. Official paks zero-pad the header with `DATA` in its last 4 bytes (`tools/pak.py`).
- The anti-piracy hash (`Main.main`) does not cover the boot files, so patching them is safe.
- `prefs.sav`: Haxe-serialized, checksum `sha1(d+sha1(d+"s*al!t"))[4:36]` (`tools/hxser.py`). The game rewrites it on exit: edit only while closed.

**Console and match start**
- Dev console `/` (~180 commands) needs `PREFS.isAdmin`, which `Main.initPrefs` resets every launch (password unknown); the testbed flips that reset (1 byte). Admin hotkeys `O P K L F9 F10` run `prefs.sav` macro slots (only these 6). Tab switches the controlled faction, and `Player.onConnect` then sets that faction's `isAI` false: its AI stops (also after a player Landsraad vote, *unverified* which path); `ai true` / P restores it.
- Menu: `allFactionsNewGame` starts a match with all `gameMode.Default.playableFactions`, AI Insane, random seed. `newgame` exists only in game; `-conf`/quickStart is dead in release.
- In game: `ai true` makes every player AI (you too); `relationship A B War` forces war.
- Scenario by data: main base `structure.startUnits` spawn at start; `faction.startResources`; `parameter` choices can carry `constOverrides`.

**Vanilla AI (code-confirmed)**
- `logic.ai.*` ≈ 830 functions, 415 `AI_*` constants (per-difficulty). Combat loop: `AIUnits.unitMicroManagement`. Shipped AI logging is stripped; console `report` is a static data audit.
- Military actions come only from structure gauges (`militaryGauge`: Annexation, Pillage, Liberation, Raze, Sietch, Dismantle → `tryGauge` → `tryAction` → `tryArmyAction`). Army fights happen only defending own structures (`checkStructures`, own structures only) or when armies meet: the AI never attacks an exposed army.
- Results feed the gauge (`impactNeeds`): Success ×0, `NotImplemented`/`Dismiss` unchanged, else ×0.85 (`Skip` too, without onFailure blocks). A refused launch left full re-fires every 0.5 s. `tryArmyAction`: `NoAvailableArmy` = its idle list (`getUnits(getDefaultUnitQueryArgs(k))`) is empty; `NotEnoughArmies` / `ArmyNotStrongEnough` = the pick falls short.
- Target choice: `getSiegeableVillages(k)` (pillage allowed, devastation, running orders, supply range, sandstorms, diplomacy) → `HScoring.structures` → top `AI_StructureScore_BestStructuresCount` (Insane 2 … Easy 5) → weighted random. Unaffordable pick: `tryAction` reserves and launches nothing. Annex score ignores the cost (Authority 20 + 10 × owned^1.2 + distance term; 0 for Smugglers); +100 for the first spice village.
- Enemy villages need aggressiveness ≥ 50 **and** `Diplomacy.desiredStatus` ≥ 1 toward the owner (set daily from `HScoring.diplomaticTarget`); Pillage has only the desiredStatus gate. In practice desiredStatus is 0 toward most at-war factions, so vanilla almost never targets enemy villages.
- Sietch / renegade-base strikes (`PillageSietch` / `Dismantle`, gauges Sietch / Dismantle, prio 2): no owner, so the estimate is the full militia spawn composition + hostile armies standing there; vanilla never weighs home exposure for them.
- Reach: siege targets only within `maxSupplyDistZones` of the AI's territory, 1 zone in practice (bonus thresholds 3/5/15 vs at most 2); Smugglers' trait zeroes the Annex distance cost (attribute 952).
- Sizing: `pickUnits` adds armies closest-first until the estimate ≥ required (`getAttackRandomPowerBalance()`, **1.0 for neutral targets**). `getEnemyCombatStats` counts the owner's forces, its own turrets and main base only (no neighbour turrets, no third-party armies). Turrets have health 0 in combat stats. The live order balance only triggers emergency abilities.
- Regroup (`checkRegroupOrder`) waits for **every** order army; single armies drift into contact meanwhile. Defense (`checkStructures`) re-rolls its required ratio every 0.5 s (Insane 1.0-3.5) and can send nothing for minutes.
- Fight retreat: after 5 s, retreat when `HAI.getWarzonePowerBalance` (units within 80) ≤ `AI_WarzonePowerEstimation_RetreatRatio` (re-rolled every tick: acts as its max); cancels the related orders, `Resupply` to the nearest healing structure every tick. Balance is **1.0 when no enemy power is left**. A Defense order survives the retreat and re-sends idle members one by one.
- A plain `Resupply` doesn't pull armies out of a fight (only the fight retreat does); micro keeps attacking a fleeing enemy while in reach. A unit dying before Action cancels its whole order; taking one army from an order before Action (Annex prio 3 > Liberate / Pillage 1) cancels it too.
- Resupply: armies not in a Military order heal when life or supply < 0.9. Patrols take only idle armies at 100%. Temporary units (`SafeRegen_MRatio` 0) never heal: their Resupply ends at once every tick; mission picks apply minLife 0.9 only with `hasSafeRegen`.
- Supply drains only in hostile / neutral zones, 50/day (day = 30 s, ≈ 0.28 per unit walked), refills only near a structure that `canSupply`; occupying (capture / pillage running) or investigating doesn't drain, the militia fight does. Deep desert drains several times faster (attribute 455). Siege orders cancel at once with `InsufficientSupply` when supply < the path estimate and never check supply after.
- Pillage: idle armies ≥ 90%, 2 days; `getAvailableOccupationActions(faction)` decides who may (attributes 68/69/70); neutral villages are pillageable. `Devastated` 20 days (×0.5, no siege action), pillager gets `Pillaged` (+100% Annex cost there).
- Village-less zones (deep desert too) go to the single owner of all neighbouring village / main-base zones (`Zone.updateOwner`); deep desert only with `DeepDesert_Surounded_GainControl` (Fremen hegemony bonus 1).
- Neutral armies are raiders (`Army.raid`, owner null), hostile only to `raid.targetFaction`; vanilla ignores them.
- Rebellion: a village at Critical stability (water) spawns a `Rebels` raid on itself; only killing those rebels ends it.
- Renegade bases: each faction's renegade raid score grows with every base not in a fight; past a threshold a `Renegade_Pillagers` raid spawns at the base nearest that faction and pillages it. A neighbouring base is a standing raid source; its garrison isn't hostile to us. A raider siege (no `besiegingFaction`) blocks every faction's siege actions there. `Army.aiOrder` is often null on besiegers: read siege state from the structure.
- World events (`checkWorldEvents`): the nearest idle army goes **alone**, no threat check. Liberation picks the daily target's villages anywhere on the map.
- Siege Action: idle order armies get `doAction(ArmySiege)` every tick while the village isn't under attack; an army inside the footprint never moves and loops. Micro Repositions a fight group's first army to any own structure with a besieger flag, however far.
- Fremen artillery: F_Special → F_Special_2 (speed 0) installed as an emergency ability whenever the order balance < 4 (also at 1.0); vanilla never uninstalls it.
- Harvesting teams (no Refinery, e.g. Fremen): harvesters are armies moved by `doAction("MoveAndDeploy")`, no threat check, never recalled. Sandworms: only `ent.Harvester` recalls (`isWormTarget`); armies fight on until eaten; a target off sand is dropped.
- Orders: AIOrderType 0 Basic, 1 Military, 2 Defense(Entity), 3 Protect, 4 Resupply, 5 Discovery, 6 Patrol, 7 Investigate, 8 SendAssassin. `ArmyFight` needs an `AIEntityGroup` target and walks every army to `entities[0]`. Unnamed cancels (`src <none>`): `checkOrderTerminations` (units dead, group gone, refused Shuttle step) and `addOrder`'s onComplete.
- Transport: `Entity.isTransported` = in transport / transit / hidden (worm ride); such armies read 0 power.
- Diplomacy: combat only at `War`; Truce / Tribute / Alliance forbid it. a Breakable treaty cancels every AI's orders targeting either party, also of AIs not in the treaty (vanilla; `treaty-scope` limits it to the parties' orders on each other); the AI accepts peace by trade value only, even mid-capture. Atreides (attribute Allow_PeaceForce) can impose a Non-aggression Pact for Influence (`sendTrade` style ForcePeace, confirmed at once); the vanilla AI never does (`force-peace` does it when a village's defense is lost).
- Water: with a spice village owned and the Water goal unmet, vanilla Annex takes only zones with wind >= 4 and returns `NoStructuresWithSufficientWind` when none is in reach (stalled Fremen for the rest of a match; `wind-fallback` drops the filter then).
- Polar Sink (region `Pole`, trait `CT_NorthPole`): Annex cost +150% per owned village (`Faction_Outpost_NumberBaseCost_MRatio` 1.5), normally priced out of our value-per-cost; Landsraad `WaterSubsidies` (trait `Res_WaterSubsidies`, 20 days) sets it to 0 (`Faction_OutpostZoneWithTTrait_Cost_MRatio` 0 on `R_Pole`). Our Annex value skips ÷cost at cost 0 (scores like the cheapest candidate), so `fclaim` keeps it only for an AI that can hold it (each judges itself).
- Building choice: `BuildingManager.checkBuildings` → `$HScoring.getBuildingStructureScore`, weighted random among the best 2 (Insane); turrets score on static border exposure only, never on enemy armies (`turret-steer` adds standing at-war stacks and front villages: ≥ 2 at-war neighbour zones, ≥ 3 zones from our main base, or touching the map's centre zone, demolishing Wholesale Market > Maintenance Center > Research Hub for the slot). Patrols (`checkPatrols`) walk idle 100% armies to a border village with no threat check.
- Smugglers' `UWHeadquarters` are in `faction.structures` but stand in other factions' villages (`ent.Headquarter.structHost`). Vanilla installs a new one whenever ≤ 1 has no extension (no cap) and scores regular extensions by cdb `aiWeights` only.

**Our layer** (testbed patch `ai-log`: tools/inject.py + aware.py + behave.py + rules/)
- Logging: wrapper functions appended, existing `Call` ops redirected; events in `game.log` as `AIMOD {…}`, summarized by `mod log` (`wzb`: every fight's retreat balance every 5 s).
- `aw` scan (every 10 s per AI faction): the world model of at-war armies, base of every army-aware rule.
- Rules (goal order AI-POLICY §5a; what each decides and its thresholds: AI-POLICY; hooks and ids: REVERSING): `strat` director, `hunt` (chases, contests, neutral raiders), `rally`, `raid`, siege launch gate / sizing / Annex value + reach (`annex-reach`, special table, map centre) / `siege-join` / `siege-engage` / `stage` / `retry` / `stuck`, Annex value, `discovery-gate`, `safe-heal`, `retreat-terrain`, `strand`, `undeploy`, `ability-gate`, `memory`, `worm-flee`, `desert-step`, `gather`, `siege-pos`, `keep-capture`, `unstick`, `release`, `tension`, `peace-gate`, `treaty-scope`, `force-peace`, `wind-fallback`, `patrol-gate`, `turret-steer`, `uhq` (Smugglers Underworld HQ cap / placement / extensions), `fclaim` (free Annex: only if we can hold it), `busy-siege` (vanilla crash fix), `strike` (siege armies on the march fight an at-war army within turret range when at least even), `sweep` (dead armies / ended orders / ended fights leave our global maps every 60 s). "Our land" = our structures on zones we own. State between calls: added global ObjectMaps.

## Documentation rule (mandatory)

Docs are a reference for a fresh agent: they describe the **current** state, not a change history. No dates, no "now fixed", no log-file narratives; evidence only where it justifies an open item.
- Facts: one line here, details (function names + ids) in `docs/REVERSING.md`; testbed behavior in `docs/TESTBED.md`; rules and thresholds in `docs/AI-POLICY.md`.
- `progress.md`: open work and in-game checks; dead ends go to its "Tried / ruled out" list. After every match analysis, prune its "Verify in-game" table by the rule at its top (pass → delete, fail → Open issues, never exercised 3× → trigger or drop): it must shrink, not grow.
- Mark anything not verified in-game as *unverified*. Terse: tables and one-liners. Update docs in the same session as the finding.

## Layout

- `tools/` `mod.py` CLI · `bcheck.py` offline lint of appended functions · `boot.py` bytecode patching · `inject.py` decision logging · `aware.py` enemy army scan · `behave.py` wiring of the AI rules · `rules/` the rules (`common` thresholds + bytecode helpers, `world` shared queries, `heal`, `hunt`, `siege`, `raid`, `strat`, `strand`, `memory`, `deploy`, `stage`, `peace`, `build`, `uhq`, `release` spare armies off occupations, `claim` free-Annex gate, `strike` en-route strike, `sweep` dead keys out of our maps, `dmz` border villages taken not burnt / truce break, `sdiag` siege diagnostics) · `aireport.py` log summary · `pak.py` Heaps archives · `hxser.py` Haxe serializer
- `patches/data.json` data changes (checked old→new) · `patches/bytecode.json` code patch registry
- `testbed/scenario.json` test scenario · `testbed/ailog.json` extra traced functions · `validation/` test-case records
- Generated, git-ignored: `.venv/ work/ dist/ backup/`

## Workflow for an AI change

1. `testbed on`, reproduce the weakness (L marks), read it with `mod log`.
2. Check the idea against [docs/AI-POLICY.md](docs/AI-POLICY.md). Locate code with `find` / `dec`.
3. Data first (`patches/data.json`); code only when data can't express it (a `tools/rules/` rule wired in `tools/behave.py`, or a locator in `tools/boot.py`, registered in `patches/bytecode.json`).
4. Offline check (both boot files patch and re-parse; `.venv\Scripts\python.exe tools\bcheck.py`: register-kind mismatches and trap leaks in appended functions, 3 known harmless Null<Bool> hits), `testbed on`, launch **through Steam** (a direct `D4X.exe` run fails on every testbed build), `mod log` (`HEALTH OK` + the target metric).
5. Release: `testbed off`, then `install`.

## Code structure

Not pristine, but every file has one clear job, so an agent can load only what a task needs.
- No file over ~1,300 lines (larger ones get split along their natural seams). One module = one concern; a rule = one `build_*` function (+ its log helper) in the module of its rule group.
- Thresholds are named constants with a one-line reason: shared ones (AI-POLICY §4) in `rules/common.py`, nowhere else as literals.
- Rule modules depend only on `rules.common` (`from rules.common import *`); rules get the shared queries as function ids from `behave.install`, never by importing each other.
- Module docstrings say what the module decides and why (the failure it fixes); REVERSING.md holds the hook points and ids.
- A pure refactor must build byte-identical boot files (compare sha256 of an offline `boot.apply` before and after).

## Rules

- Game updates replace boot files: `verify` fails; re-check every locator and update `baseline.json`.
- Patch code by **function name + expected instruction** only; `boot.apply` re-parses and checks diff size.
- Both `hlboot.dat` and `hlbootdx.dat` are patched (which one the launcher uses is *unverified*).
- Changes affect every mode that uses the AI. Don't play online with the testbed on.
