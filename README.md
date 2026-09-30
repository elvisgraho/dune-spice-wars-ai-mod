# Dune: Spice Wars — AI mod

Goal: better skirmish AI, **combat first** (engage/retreat, targeting, army cohesion), then economy/diplomacy.

State: tooling, combat testbed and AI decision logging work in-game. AI behavior rules (tools/rules/, wired by tools/behave.py) run in the testbed only; open checks are in [progress.md](progress.md).

**Read in this order:** this file → [progress.md](progress.md) → [docs/AI-POLICY.md](docs/AI-POLICY.md) (**binding** for any AI behavior change) → [docs/REVERSING.md](docs/REVERSING.md) (code facts, ids) → [docs/TESTBED.md](docs/TESTBED.md). Don't re-research anything listed under Key facts.

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
| `log [file] [--faction F] [--all] [--raw] [--around MM:SS]` | Summarize AI decisions from `game.log`; archives raw lines to `work/logs/` |
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
- `logic.ai.*` ≈ 830 functions, 415 `AI_*` constants (per-difficulty values). Combat loop: `AIUnits.unitMicroManagement`.
- Military actions come only from structure gauges (`militaryGauge`: Annexation, Pillage, Liberation, Raze, Sietch, Dismantle → `tryGauge` → `tryAction` → `tryArmyAction`). Army-vs-army fights happen only defending own structures (`checkStructures`) or when armies meet. The AI never chooses to attack an exposed army, and ignores enemy sieges of neutral villages (`checkStructures` = own structures only).
- Attack sizing: `pickUnits` adds armies closest-first and stops as soon as the estimated balance ≥ required. Required = `getAttackRandomPowerBalance()` for owned targets, **1.0 flat for neutral ones**. `getEnemyCombatStats` counts the target owner's forces only, never third-party armies nearby (a neutral village next to a rival's army blob reads as militia only). The live order balance (`getOrderPowerBalance`) only triggers emergency order abilities in Action; it cancels nothing.
- Regroup (`checkRegroupOrder`) advances only when **every** order army reached the regroup point (or a stalled one's path is short): armies next to the target wait for stragglers, and single armies drift into contact alone meanwhile.
- World events (`checkWorldEvents`): the nearest idle army is sent **alone** (Discovery, prio 0) to an event up to one zone from own territory, into anyone's land, with no threat check.
- Pillage: only from the Pillage gauge (no gain modifiers; stays near 0 in practice) with idle armies at ≥ 90% life/supply; duration 2 days. Who may pillage what: `SiegeComponent.getAvailableOccupationActions(faction)` (faction attributes 68/69/70 block enemy / all / neutral villages, e.g. Atreides); **neutral villages are pillageable**. Loot = the village's production. Costs: trait `Devastated` 20 days (production ×0.5, no siege action there), and the pillager gets `Pillaged` (+100% Authority cost to Annex that village, long duration). Occupation progress (`getOccupationActionProgress`) is 0-1.
- Vanilla target choice: `getSiegeableVillages(k)` (pillage allowed, devastation, running orders, supply range `maxSupplyDistZones`, sandstorms, diplomacy) → `HScoring.structures` → `pickMapBest` top `AI_StructureScore_BestStructuresCount` (Insane 2 … Easy 5) → weighted random. Short of the cost (e.g. Smugglers' Authority), `tryAction` reserves resources for that pick and launches nothing.
- Enemy villages need aggressiveness ≥ 50 (`allowEnemy`); water-starved factions skip low-wind villages (`NoStructuresWithSufficientWind`).
- Action results feed the gauge (`impactNeeds`): Success ×0, `NotImplemented`/`Dismiss` unchanged, anything else ×0.85 (`AI_MilitaryGauge_FailureFactor`).
- Fight retreat: after 5 s of fight, `unitMicroManagement` retreats when `HAI.getWarzonePowerBalance` (units within 80 of the warzone centroid) ≤ `AI_WarzonePowerEstimation_RetreatRatio`, re-rolled **every tick** from its [min,max] (so it acts as the max). It cancels the related orders and sends `Resupply` to the nearest non-fighting healing structure, every tick while the condition holds (`Resupply n=0` rows: empty re-issues). The balance is my/enemy power and **exactly 1.0 when no enemy power is left** (a neutral or a structure keeps the warzone alive).
- Neutral armies are raiders: `Army.raid` set, owner null (rebels, Fremen raids, marauders, ...); a raid is hostile only to `raid.targetFaction`. Vanilla AI orders and threat checks ignore them.
- Siege orders cancel at +0 s with `InsufficientSupply` when the lowest army supply < the path's estimated supply cost (`fillAttackSteps`); the gauge stays full and re-picks the same target every ~2.5 s.
- Resupply: an army not in a Military order goes to the nearest healing structure (own/allied village, main base, `canSupplyFaction`) when life or supply < 0.9. Patrols (`checkPatrols`) take only idle armies at 100% life and supply: an idle army at 90-99% gets no order at all (`strand` covers it on hostile land).
- Harvesting teams (factions without Refinery, e.g. Fremen: harvesters are armies with power, moved by `doAction("MoveAndDeploy")`, no AI order): each harvester without an action goes to its nearest free usable spice field (neutral/own zone ≤ 2 zones from our territory); no threat check, and team harvesters are never recalled under attack (only Refinery harvesters recall when fighting / in storms).
- Supply drains only in hostile zones (`isInHostileZone`; neutral zones count) and refills only **near** a structure that `canSupply` the army, not anywhere in the zone. Drain = `Army_Supply_DailyDrain` 50/day, a game day = 30 s: ≈ 1.7/s, ≈ 0.28 per map unit walked (speed ≈ 6). An army occupying a structure (in occupation range: capture / pillage running) does not drain (`isInHostileZone` false), nor does one investigating a world event; walking there and fighting the militia does. A finished Pillage refills 50% of max supply to every occupying army (`Army_Supply_Resupply_OccupationRatio`). Siege orders never check own supply.
- Fremen artillery: the AI installs F_Special → F_Special_2 (speed 0) as an "emergency" ability in Action whenever the order balance < 4 (Insane), including 1.0 = no enemy left; vanilla never uninstalls it (Move can't auto-undeploy F_Special_2, the Uninstall ability is AI-`Ignored`, the order's `noMoveAbilities` blocks its Move into occupation range): an installed AI turret on hostile land starves.
- A unit dying in an order before Action cancels the whole order (`removeUnits`): a retreat that loses armies is cancelled and re-issued at each death.
- A plain `Resupply` order does not pull armies out of a fight: micro keeps attacking, the order sits in Regroup and `checkRegroupOrder` cancels it as stuck (re-issued, cancelled again). Only the fight retreat (force-flee) disengages. Micro keeps attacking a fleeing enemy for as long as it stays in reach, with or without an order: a stack at the same speed follows it indefinitely (Smugglers followed an unhurt F_Trooper ~100 south from Larram under Grimpo's turret after their hunt ended).
- `Army.aiOrder` is often null on AI besiegers (siege seen only via the structure: `siege.besiegingFaction` / `getOccupierFaction()`). Smugglers' `UWHeadquarters` are in `faction.structures` but stand in other factions' villages.
- An `ArmyFight` order on a group walks every army to `group.entities[0]` only (first member), ignoring others on the way; Action starts on contact with any member.
- Army-attack orders (`ArmyFight`) need an `AIEntityGroup` target (`checkEngageOrder` calls `getEntities()` unconditionally). Two vanilla closures break on non-structure Military targets: the `getUnits` busy filter (patched by `busy-siege`) and the dev right-click path.
- Orders are cancelled from unnamed closures (log `src <none>`): `checkOrderTerminations` (all units dead, Group target removed, a Shuttle path step refused with Invalid/BlockedBy) and `addOrder`'s onComplete (a Success cancels other orders sharing units).
- Breakable treaties (trade, research, political agreement, non-aggression, open borders) cancel every order targeting either party (`AIOrders.onEvent(OnNewTreaty)`); the AI accepts peace by trade value only, even mid-capture.
- Diplomacy: combat only at `War` (`State.areAtWar`). Truce/Tribute/Alliance forbid it; `Hostility` never fights. Vanilla `ArmyFight` targets any non-ally, so our army-attack orders must cancel on truce.
- Shipped AI logging is stripped (7 warnings left); console `report` is a static data audit.

**Our layer** (testbed patch `ai-log`, tools/inject.py + aware.py + behave.py + rules/)
- Logging: wrapper functions are appended and existing `Call` ops redirected (no jump fixups); events go to `game.log` as `AIMOD {…}`, summarized by `mod log`.
- `aw` scan (every 10 s per AI faction): the AI-side world model of at-war armies, the base for every army-aware rule.
- Rules follow the faction goal order in AI-POLICY §5a (supply > defend own > bunker > stop nearby captures > opportunity chase > expand; turret-aware throughout): `hunt` (contests and chases, then neutral raiders; group = the prey's faction only, nearest first; third parties at war with the prey ignored, its allies counted only if they arrive before the kill; judged at the group's core member, supply budget (kept while crushing the prey in contact), turret cover, `defend`/`objective`/`turret` aborts, `chase` abort (engaged 15 s without the prey losing 10% power or us closing 30: a fleeing prey is given up and not chased again for 90 s; not for contests), early Engage once the armies near the prey suffice), threat = at-war armies + raiders targeting us, movers only when heading our way, siege launch gate on vanilla `tryArmyAction` (defensive posture refuses new offensives, main base bunker Annex redirect, `annex-spacing`), turret- and third-party-aware vanilla sizing (`getEnemyCombatStats`: neighbours' turrets and other factions' at-war armies near the target added, a besieged village's own turrets silenced; ally structure stats likewise), `discovery-gate` (no lone world-event trip into superior at-war armies), `siege-join` (vanilla siege launches: neutral targets need 1.25 (vanilla 1.0), the nearest idle armies within 450 join until we have 3× the defense there), `siege-engage` (our siege orders leave Regroup once the armies within 100 of the target pass the entry test; stragglers walk straight in), `raid` (pillage for loot with raid-ready armies within 400 that aren't fighting: vanilla's pillage list, neutral or at-war villages, never vanilla's next Annex choices, a bunker village, one with our own Underworld HQ, or one our raid left < 60 s ago; local ratio counting free at-war armies within 480 that could relieve it, supply budget with the pillage refill, home race = no raid farther from our land than hostile armies are unless those at home hold them; force sized nearest-first to 3×; running pillages (vanilla's too) abort for `defend` (our besieged structure within 500 lacks defenders: those at it + free ones within 900), `home` or `weak` (relief while walking), never past 50% progress; refusals logged), bunker target score ×1.3, `retry` (a siege target whose last launch ended at once is skipped for 30 s), `safe-heal` (heal/retreat target choice), `retreat-terrain` (fight retreat balance × terrain × supply; the no-enemy 1.0 passes unchanged; `recall`: all our armies there short of supply and none in a Military order → 0, so a stack whose hunt ended on supply stops pursuing; a `stranded` army that can't pay the walk home anyway gets no supply penalty and finishes a fight it is winning; `pursuit`: the enemy within 150 lost < 10% power for 15 s (clock runs through missions), none of ours there on a Military order, off our zone → 0, so micro stops following a fleeing army after its order ended), `strand` (an idle army on hostile land gets a Patrol home to the nearest safe structure), `undeploy` (an installed Fremen turret not fighting on hostile land is uninstalled and unblocked, so vanilla walks it into occupation range or home), `ability-gate` (no emergency order abilities at balance 1.0 = no enemy), `memory` (faction memory: zone danger from our harvesters being attacked, fading over 180 s; harvesting teams avoid dangerous fields), `busy-siege` (vanilla crash fix). "Our land" = our structures on zones we own. State between calls lives in added globals (ObjectMaps).
- Vanilla attack sizing counts only the target's own turrets and its owner's main base in range; turrets of neighbouring villages ("bunkers": villages ~1 turret range apart) are ignored. Turrets have health 0 in combat stats: they add offense only.
- `AIEntityGroup` removes itself only when every member is dead/removed; a Group-target order is otherwise cancelled by vanilla (`src <none>`) only for a refused Shuttle path step or when it has no units left.
- Vanilla defense (`checkStructures`) re-rolls its required ratio every 0.5 s from data `AI_PowerBalance_VillageDefense_Min/Max` (Insane 1.0-3.5) and sends nothing when no pick reaches it: a besieged village can go undefended for minutes while the faction launches new Annexes elsewhere.

## Documentation rule (mandatory)

Docs are a reference for a fresh agent: they describe the **current** state, not a change history. No dates, no "now fixed", no log-file narratives; evidence only where it justifies an open item.
- Facts: one line here, details (function names + ids) in `docs/REVERSING.md`; testbed behavior in `docs/TESTBED.md`; rules and thresholds in `docs/AI-POLICY.md`.
- `progress.md`: open work and in-game checks; dead ends go to its "Tried / ruled out" list. After every match analysis, prune its "Verify in-game" table by the rule at its top (pass → delete, fail → Open issues, never exercised 3× → trigger or drop): it must shrink, not grow.
- Mark anything not verified in-game as *unverified*. Terse: tables and one-liners. Update docs in the same session as the finding.

## Layout

- `tools/` `mod.py` CLI · `boot.py` bytecode patching · `inject.py` decision logging · `aware.py` enemy army scan · `behave.py` wiring of the AI rules · `rules/` the rules (`common` thresholds + bytecode helpers, `world` shared queries, `heal`, `hunt`, `siege`, `raid`, `strand`, `memory`, `deploy`) · `aireport.py` log summary · `pak.py` Heaps archives · `hxser.py` Haxe serializer
- `patches/data.json` data changes (checked old→new) · `patches/bytecode.json` code patch registry
- `testbed/scenario.json` test scenario · `testbed/ailog.json` extra traced functions · `validation/` test-case records
- Generated, git-ignored: `.venv/ work/ dist/ backup/`

## Workflow for an AI change

1. `testbed on`, reproduce the weakness (L marks), read it with `mod log`.
2. Check the idea against [docs/AI-POLICY.md](docs/AI-POLICY.md). Locate code with `find` / `dec`.
3. Data first (`patches/data.json`); code only when data can't express it (a `tools/rules/` rule wired in `tools/behave.py`, or a locator in `tools/boot.py`, registered in `patches/bytecode.json`).
4. Offline check (both boot files patch, re-parse, new functions decompile correctly), `testbed on`, run, `mod log` (`HEALTH OK` + the target metric).
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
