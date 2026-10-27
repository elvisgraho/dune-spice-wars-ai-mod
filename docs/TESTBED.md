# Combat testbed

Starts a random-map match with 4 AI factions that already have armies, money and war declared, so combat starts within minutes.

## Use

```powershell
ai-mod\mod.cmd testbed on      # game closed; re-run after editing scenario.json, patches/data.json or anything in tools/ (boot files are built only here)
ai-mod\mod.cmd launch          # or start normally
```
1. Main menu: press **O** → the match starts loading (no lobby).
2. In game: press **P** once. You become AI too, speed x4. Diplomacy is left to the AIs (no forced war, so truces survive pressing P again after a Tab).
3. Press L to mark an incident, F9/F10 for speed 2/4, K to toggle fog, or `/` for the console.
   Tab/Shift+Tab takes control of a faction and can switch its AI off, as can a player Landsraad vote.
   Press P to restore the AIs. Check the report's AI-off windows before judging behavior.

### Unattended match (agents)

`ai-mod\mod.cmd match [minutes]` (default 17; `tools/match.ps1`): launches through Steam (or uses the running game), waits 30 s for the menu, then O → 45 s load → P → Tab → F10 (x4), runs the given real minutes, closes the game normally (`CloseMainWindow`, killed after 30 s; prefs.sav is rewritten on exit). At x4, 17 min real ≈ 60-70 min game time. Exit 2 = the game vanished mid-run (crash). Run it in the background and read `mod log` afterwards.
- Keys: `keybd_event` with scan codes after an Alt tap + `SetForegroundWindow` on the game window, per key. Computer-use tools don't work for this: each screenshot / key call left the desktop in front and minimized the fullscreen game, so keys landed nowhere. No screen capture is needed; `mod log` (HEALTH, game time, AI OFF windows) is the check.

`ai-mod\mod.cmd testbed off` restores vanilla (boot files from `backup/`, pack removed, prefs macros restored).

## What `testbed on` changes

| Change | How |
|---|---|
| AI decision logging (`ai-log`) and behavior rules wired by `tools/behave.py` | appended functions and redirected calls in both boot files; behavior catalog in AI-POLICY |
| Dev console + admin hotkeys always on | 1 byte in `Main.initPrefs`, both boot files (`admin-always-on`) |
| Skirmish factions limited to `factions` | data: `gameMode.Default.props.playableFactions` (also limits the normal Skirmish lobby) |
| Map `AllFactions` resized to `mapCells` (vanilla 200; 130 ≈ Medium, for faster contact) | data: `mapType.AllFactions.props.numCells` |
| Each main base spawns `armies[faction]` at start | data: `structure.<base>.startUnits` (after the ornithopter) |
| Big starting stockpiles | data: `faction.startResources` (non-mode entries); applies to all modes while installed |
| Your `patches/data.json` AI changes | same pack, so you test your mod |
| O/P/K/L/F9/F10 macros and scenario fog setting | `prefs.sav` (`shortcutCommands`, `admin.noFog`) |

`noFog` is game-wide: `Faction.applyVisibility` marks every cell visible for every faction, AI included. The testbed runs with fog on (`noFog: false`, our AI respects fog); pressing K blinds-off every AI too. Factions start with 1000 Intel and 10 agents (`startResources` Intel / Agent) for operation tests.

Seed stays random (`PREFS.seed = 0`). AI difficulty is **Insane** (hard-coded in `allFactionsNewGame`). Hegemony, political and economy victories are blocked, so matches run until military supremacy.

## Scenario knobs (`testbed/scenario.json`)

`factions` (2–7, from Atreides/Harkonnen/Smugglers/Fremen/Corrino/Ecaz/Vernius; DLC factions need the DLC), `humanSlot` (index in data order of the faction you start as), `mapCells`, `noFog`, `startResources`, `armies` (unit ids must belong to that faction; see `unit` sheet), `constants` (`{"AI_X": 5}` or a per-difficulty list), `macros` (key → console lines; `{WAR_ALL}` expands to War between all `factions`, `{humanSlot}` to the index).

`mod testbed on --scenario <name>` overlays `testbed/scenarios/<name>.json` on the base scenario.
Top-level keys replace; later builds and `match` keep the selected variant until the next `testbed on`.
`factionResources` overrides shared starting resources for named factions.

| Variant | Use |
|---|---|
| `altar` | Altar capture-ownership reproduction, based on `raze` with map seed 5705907. Use `mod match 14`; verify claims against minor-raid defense. Combat timing can differ |
| `late` | Late-game leader containment; L boost after `lateMinutes` real minutes, normally 6 |
| `raze` | Short campaign test; boost after 1 real minute, larger armies and forced wars against the boosted leader. Use `mod match 20` to cover multiple attack windows; not an economy/expansion test |

Starting Hegemony resources are ignored by the game, so L grants the boost through `resAll` and `res`.
`res` targets the faction currently in view (`game.me`), which follows Tab; do not assume a fixed leader.
Check `bthreat` to confirm the recipient. `charter DuneGovernor <faction>` can set up a Governor test.

After the boost, the macro and match script restore x4. If the L press misses, the script checks `bthreat` after
90 seconds and retries, at most three presses, until a faction reaches 25k Hegemony.
Both boot files are patched; which renderer the launcher selects remains unverified.

## Reading what the AI did

After a match (game can stay open), run `ai-mod\mod.cmd log`. The default report puts health and evidence-linked findings first, followed by faction outcomes, campaign base HP/damage per observed attack window, command sources and log-volume contributors. Parser failures and partial recovery are visible. No detected patterns does not mean the AI played well.

Use `--json` for the same analysis with all findings and coverage metadata. Use `--details` for the full report described below, or `--score` for the existing scorecard. `--all` also selects the detailed report with non-military orders. `--around MM:SS --event KIND` narrows a timeline; repeat `--event` to combine kinds. Raw faction filtering matches `f` exactly.

Health includes uncaught game exceptions and caught rule failures. Historical AIMOD-only logs report game health as unavailable. A new full archive has a `.meta.json` sidecar; source locations for step probes come only from its frozen map, never a later build's `work/crumbs.json`.

`micro` uses `mode=changes` by default: previous state is read for that army, identical states/targets/points are omitted, and the original game call always runs. `testbed/ailog.json` `micro_repeats=true` restores all observations after `testbed on`. Real command attempts (`dact`) remain complete. Entity `id` and order `oid` are match-local identities. Economy snapshots omit the truncated gauge-map text; gauge attempt/outcome traces remain.

`--details` reports military order timelines, targets, force sizing, phase changes, outcomes, marks, rejected picks,
operations, awareness and rule diagnostics. `--all` includes non-military orders. `--around MM:SS --window 30`
shows nearby decisions; repeat `--event` to select kinds. For awareness rows, `S/V/M/L/H` mean sand, visible, moving,
losing supply and hostile zone. `raid:<kind>` identifies neutral raiders; `*` means the raid targets this faction.

Add traced functions in `testbed/ailog.json` and rebuild. Full logs and matching maps are archived in `work/logs/`
because the game overwrites `game.log` on launch. Report an incident with its time, faction and observed problem.

Filtering `log --raw` rows by game time: match the field as `, g : ` (hunt start rows also carry `ng : `, and a split on `g : ` takes that one and silently drops the rows).

### Data contracts and exports

`--entity ID` finds references to that entity, including targets and awareness arrays; `--order ID` matches `oid`
only. Clock resets greater than one second split concatenated logs into sessions, so reused match-local IDs do not
merge. Default feedback and JSON analyze each session separately; detailed views require `--session N` when several
sessions exist. Logs without a detectable reset cannot establish a match boundary. App seconds are never used as
game seconds in feedback timing metrics. Missing game clocks are reported; unfamiliar or null order-end reasons
appear under Other, with exact reasons in JSON.

Feedback JSON uses `schema_version=2`. `--events-jsonl` emits one normalized record per AIMOD row, with record schema
version 1, full source SHA-256, physical source line, session, parse status and validation errors. Its deterministic
`record_id` is the source hash plus line number; valid entity/order IDs are integers. Non-finite values become null
and carry validation errors. Failed parser rows retain a raw excerpt; the archived source preserves exact evidence.
The feedback reader validates required fields for 16 core event kinds, inventories unchecked kinds, and excludes
invalid or partially recovered records from behavioral metrics. Field checks do not prove that every event was
emitted or reached disk. Actor/order ID coverage is a fraction, including mixed legacy records.

Add `--strict` for scripts: output is still emitted, then exit status 2 signals parser/schema damage, missing core
game clocks, invalid UTF-8, archive integrity failure, logged game/rule errors, or no selected records. Behavioral
warnings alone do not fail it. A passing check does not validate unchecked event-specific fields or prove AI quality.
For example, `mod.cmd log --events-jsonl --entity 7729 --event dact --strict` exports one army's command attempts.

Format-3 archives preserve original bytes, including line endings. The `.meta.json` sidecar binds the full content,
source map and metadata by SHA-256. Writes use atomic replacement; an orphan or damaged archive is never reused as
verified. These checks detect accidental corruption, not deliberate modification of both data and digests.
Step-probe source locations require verified content binding and a matching installed build. Legacy format-1/2
sidecars remain readable but their maps are withheld as `legacy_unbound`; unknown provenance is reported and alone
does not fail strict mode. Concatenated sessions never share one sidecar's source map.

## Measuring

Copy `validation/case-template.json` per experiment: units lost, retreat success, target switches, engage/retreat oscillation, time to first contact. Keep scenario and difficulty identical between baseline and patched runs, and run several seeds; one match is noise.
