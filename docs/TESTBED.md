# Combat testbed

Starts a random-map match with 4 AI factions that already have armies, money and war declared, so combat starts within minutes.

## Use

```powershell
ai-mod\mod.cmd testbed on      # game closed; re-run after editing scenario.json, patches/data.json or anything in tools/ (boot files are built only here)
ai-mod\mod.cmd launch          # or start normally
```
1. Main menu: press **O** → the match starts loading (no lobby).
2. In game: press **P** once. You become AI too, speed x4. Diplomacy is left to the AIs (no forced war, so truces survive pressing P again after a Tab).
3. Watch: **L** drop a marker in the AI log (press it right when the AI does something dumb), **F9** / **F10** speed 2 / 4, **K** fog toggle, `/` console. **Tab** / Shift+Tab take control of a faction and switch its AI off (`Player.onConnect` → `set_isAI(false)`; a Landsraad vote as the player can do the same): press **P** again to turn every AI back on. `mod log` prints `!AI OFF: <faction> <from>-<to>` right under its header for every such window (traced `ent.Faction.set_isAI`, `src` = caller); rules judged in that window mean nothing.

### Unattended match (agents)

`ai-mod\mod.cmd match [minutes]` (default 17; `tools/match.ps1`): launches through Steam (or uses the running game), waits 30 s for the menu, then O → 45 s load → P → Tab → F10 (x4), runs the given real minutes, closes the game normally (`CloseMainWindow`, killed after 30 s; prefs.sav is rewritten on exit). At x4, 17 min real ≈ 60-70 min game time. Exit 2 = the game vanished mid-run (crash). Run it in the background and read `mod log` afterwards.
- Keys: `keybd_event` with scan codes after an Alt tap + `SetForegroundWindow` on the game window, per key. Computer-use tools don't work for this: each screenshot / key call left the desktop in front and minimized the fullscreen game, so keys landed nowhere. No screen capture is needed; `mod log` (HEALTH, game time, AI OFF windows) is the check.
- Tab after P selected another faction without an `!AI OFF` window in 5 runs (*unverified* why: Tab may only move the view when every faction is AI).

`ai-mod\mod.cmd testbed off` restores vanilla (boot files from `backup/`, pack removed, prefs macros restored).

## What `testbed on` changes

| Change | How |
|---|---|
| AI decision logging to `game.log` (`ai-log`) + AI rules (`aware-ai`: hunt, safe-heal, retreat-terrain, annex-spacing, turret/third-party sizing, discovery-gate, siege-join, siege-engage, raid, strat (director), strand, undeploy, ability-gate, memory, peace-gate, busy-siege, worm-flee, worm kill log, pick-life, no-regen-heal, desert-step, gather, Fremen ring hold, worm hold, harvester run, hunt awareness, rally, siege position, unstick, keep-capture, main-base guns, discovery relaunch, raid gauge, treaty scope, force peace, wind fallback, patrol gate, turret steering + home-need credit) | appended functions + redirected calls, both boot files |
| Dev console + admin hotkeys always on | 1 byte in `Main.initPrefs`, both boot files (`admin-always-on`) |
| Skirmish factions limited to `factions` | data: `gameMode.Default.props.playableFactions` (also limits the normal Skirmish lobby) |
| Map `AllFactions` resized to `mapCells` (vanilla 200; 130 ≈ Medium, for faster contact) | data: `mapType.AllFactions.props.numCells` |
| Each main base spawns `armies[faction]` at start | data: `structure.<base>.startUnits` (after the ornithopter) |
| Big starting stockpiles | data: `faction.startResources` (non-mode entries); applies to all modes while installed |
| Your `patches/data.json` AI changes | same pack, so you test your mod |
| O/P/K/L/F9/F10 macros (L = `info` = log marker, F9/F10 = speed 2/4, K = fog), fog off | `prefs.sav` (`shortcutCommands`, `admin.noFog`) |

`noFog` is game-wide: `Faction.applyVisibility` marks every cell visible for every faction, AI included. The testbed runs with fog on (`noFog: false`, our AI respects fog); pressing K blinds-off every AI too. Factions start with 1000 Intel and 10 agents (`startResources` Intel / Agent) for operation tests.

Seed stays random (`PREFS.seed = 0`). AI difficulty is **Insane** (hard-coded in `allFactionsNewGame`). Hegemony, political and economy victories are blocked, so matches run until military supremacy.

## Scenario knobs (`testbed/scenario.json`)

`factions` (2–7, from Atreides/Harkonnen/Smugglers/Fremen/Corrino/Ecaz/Vernius; DLC factions need the DLC), `humanSlot` (index in data order of the faction you start as), `mapCells`, `noFog`, `startResources`, `armies` (unit ids must belong to that faction; see `unit` sheet), `constants` (`{"AI_X": 5}` or a per-difficulty list), `macros` (key → console lines; `{WAR_ALL}` expands to War between all `factions`, `{humanSlot}` to the index).

## Status

`testbed on`, O in the menu and P in game work. *Unverified:* which boot file (DX/GL) the launcher uses (both are patched); whether `ai true` gives your faction a fully working AI mid-match; whether O/P/K/L collide with game hotkeys.

## Reading what the AI did

After a match (game can stay open): `ai-mod\mod.cmd log`. The first line is `HEALTH`: game exceptions in `game.log`, and whether any pass through our injected code. If they do, the AI may freeze: run `testbed off` and report. You get one row per military order: game time, target, armies sent/available, required vs planned balance (my/enemy power), phase path, live fight power first→last with % lost per side, and end reason. `!` flags a thin margin, heavy own losses or a failed order. Also: a **Marks** section (what every faction was doing around each L press), rejected picks split into attack/defense, and order rates per minute (>5/min flagged as a possible loop). `--faction Smugglers`, `--all` (patrols/moves too), `--raw` (lines), `--around MM:SS [--window 60]` (timeline of every decision near a moment, e.g. a mark). Sections also cover military intents (gauge fired → outcome reason), who stopped each order, fights and micro switches (Attack/Reposition/Flee), daily faction snapshots (Authority / Influence stocks and the Authority rate every ~5 min), operations and Landsraad calls. **Enemy army awareness** (`aw`, every 10 s per AI faction): peak hostile power near each faction vs its own, enemy siege actions near it (`!` = it had more than 2× their power but, so far, the AI ignores it), hostile armies within 300 of our armies (with what our army was busy doing), neutral raiders within 600 of us (`raid:<kind>`, `*` = their raid targets us: rebels, renegade pillagers), armies seen only far away, and hostile armies on sand. In `--around` (`--faction F` keeps one faction's rows), each `aw` lists the armies as `owner:kind pw hp sup d@nearest zone worm flags(S sand, V visible, M moving, L losing supply, H hostile zone) action>target`. **AI rules:** `hunt` rows (Military `ArmyFight` orders, est = our/their local power) and hunt start/abort reasons; **Fight retreat checks** (balance raw × terrain × supply = adjusted vs 0.65, `held by terrain` / `retreat by terrain` / `retreat by supply` when the zone or starving armies changed the outcome); **Heal target choices** (`stay`/`flee` = army at its structure, `detour`/`avoid` = structure penalised, with hostile/own power); **Annex spacing** (sieges refused next to a running one). Add functions to trace in `testbed/ailog.json`. Raw lines are archived in `work/logs/` because the game overwrites `game.log` on each launch. When reporting an incident, add a one-line note (time, factions, what looked wrong) so it can be matched to rows.

Filtering `log --raw` rows by game time: match the field as `, g : ` (hunt start rows also carry `ng : `, and a split on `g : ` takes that one and silently drops the rows).

## Measuring

Copy `validation/case-template.json` per experiment: units lost, retreat success, target switches, engage/retreat oscillation, time to first contact. Keep scenario and difficulty identical between baseline and patched runs, and run several seeds; one match is noise.
