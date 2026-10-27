# Cheat sheet

## Tool: `ai-mod\mod.cmd <command>` (run from `ai-mod\` as `.\mod.cmd …`)

Close the game before `testbed on/off`, `install` and `uninstall`.

| Command | What it does |
|---|---|
| `testbed on` | Install the test harness: console + hotkeys, AI logging, scenario pack. Re-run after editing `testbed/scenario.json` or `patches/data.json` |
| `testbed on --scenario raze` | The short base-kill test (`late`: the late-game start); kept by later `match` / builds until the next `testbed on` |
| `testbed off` | Restore vanilla (same as `uninstall`) |
| `testbed status` | Show what is installed |
| `log` | Concise health / findings / outcomes / campaign damage. Archives the full game log and source map to `work/logs/` |
| `log <work\logs\file.log>` | Summarize an older archived match |
| `log --faction Harkonnen` | Only one faction |
| `log --details` | Full order / decision report |
| `log --all` | Full report including patrol/resupply/discovery orders |
| `log --json` | Structured coverage, outcomes, campaign windows and every finding |
| `log --json --strict` | Emit feedback JSON; exit 2 on damaged/incomplete telemetry, integrity failures or logged errors |
| `log --events-jsonl --entity 7729 --event dact` | Export command attempts for an entity, with source hash, physical line, session and validation errors |
| `log --order 123 --session 2 --around 06:00` | Inspect an exact order in one detected match session |
| `log --around 16:25 --event bcamp --event opcast` | Targeted campaign/operation timeline |
| `log --raw` | Raw AIMOD lines |
| `log --score` | Per-faction scorecard of outcomes |
| `log --around 12:30` | Timeline of every AI decision within ±60 s of game time 12:30 (`--window 30` to narrow, `--faction F` for one faction) |
| `launch` | Start the game via Steam |
| `match [min]` | Unattended match: launch, O, P, Tab, F10, run N real minutes (default 17), close the game (TESTBED "Unattended match") |
| `verify` | Check game files match the pinned build (fails after a game update) |
| `build` / `install` | Build / install the AI mod data pack only (release; testbed must be off) |
| `uninstall` | Remove everything we installed |
| `.venv\Scripts\python.exe tools\bcheck.py` | Offline lint of the appended functions; must report 0 issues before a match |
| `.venv\Scripts\python.exe tools\bhash.py` | Hashes of both built boot files; equal before / after = a pure refactor |
| `find <regex>…` | Search game function names (`--strings` for text). Several patterns = OR |
| `dec <name or id>… [--asm]` | Decompile a game function (or raw disassembly) |
| `index` | Rebuild the function/string index in `work/` |

One-time setup: `powershell -ExecutionPolicy Bypass -File ai-mod\setup.ps1`

## Hotkeys (testbed on; not while Ctrl/Shift are held or the console is open)

| Key | Where | Does |
|---|---|---|
| **O** | Main menu | Start the test match (4 AIs, random map) |
| **P** | In game | You become AI too, speed x4 (diplomacy untouched; `{WAR_ALL}` in a macro would force every pair to War and kill all truces). Press again after anything that took control of a faction (Tab, a Landsraad vote): it turns every AI back on |
| **L** | In game | Drop a marker in the AI log. Press it when the AI does something dumb |
| **F9** / **F10** | In game | Speed 2 / 4 |
| **K** | In game | Toggle fog (off from the testbed prefs) |
| **Tab** / Shift+Tab | In game | Take control of the next / previous faction: **its AI turns off** (`mod log` prints `!AI OFF`); P turns it back on |
| **`** (backtick) | Menu / game | Repeat the last console command |
| **/** | Menu / game | Open the dev console |
| Ctrl+Alt+X | In game | Spawn a sandworm |

Macros live in `testbed/scenario.json` → `macros`. Keys are fixed (O P K L F9 F10); the commands are yours to change.

## Dev console (`/`, testbed on)

`listCommands` prints every command. Useful ones:

| Command | Does |
|---|---|
| `ai true` / `ai false` | All players (you included) AI on/off |
| `speed 3` | Game speed multiplier |
| `fog` | Toggle fog |
| `relationship Atreides Harkonnen War` | Set diplomacy (War, Peace, Hostility, Team…) |
| `unit A_Trooper 5 Atreides` | Spawn units at the camera centre (unit id prefix, count, faction) |
| `army 2` | Spawn a 1-unit army for player 2 in the selected zone |
| `wipe [faction]` / `wipeOthers` | Delete all units (of a faction) |
| `heal` · `invincible` · `nocd` | Heal selection · make selection invincible · end all cooldowns |
| `powerScores` · `showDamages` · `showRegen` | Combat overlays on units |
| `resAll Solari 5000` · `prodAll …` | Give resources / production to everyone |
| `alldevs` · `fulldistricts` · `own all` | Research everything · finish your base districts · take every village |
| `addDays 10` | Skip game time |
| `win` / `lose` | End the match |
| `seed 1234` (menu) · `seed 0` | Force the map seed / back to random |
| `shortcut` | List macro slots (`shortcut 0 "cmd" "cmd"` sets one, but `testbed on` overwrites them) |
| `info` | Build info (also writes a log marker, like L) |

## Files you edit

| File | For |
|---|---|
| `testbed/ailog.json` | Extra AI functions to trace in the log (then `testbed on`) |
| `testbed/scenario.json` | Factions, starting armies/resources, map size, fog, macros, constant overrides |
| `patches/data.json` | AI data changes (the actual mod) |
| `progress.md` | What's done / next |
