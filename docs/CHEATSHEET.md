# Cheat sheet

## Tool: `ai-mod\mod.cmd <command>` (run from `ai-mod\` as `.\mod.cmd …`)

Close the game before `testbed on/off`, `install` and `uninstall`.

| Command | What it does |
|---|---|
| `testbed on` | Install the test harness: console + hotkeys, AI logging, scenario pack. Re-run after editing `testbed/scenario.json` or `patches/data.json` |
| `testbed off` | Restore vanilla (same as `uninstall`) |
| `testbed status` | Show what is installed |
| `log` | Summarize the last match's AI decisions (+ `HEALTH` line). Archives to `work/logs/` |
| `log <work\logs\file.log>` | Summarize an older archived match |
| `log --faction Harkonnen` | Only one faction |
| `log --all` | Include patrol/resupply/discovery orders |
| `log --raw` | Raw AIMOD lines |
| `log --around 12:30` | Timeline of every AI decision within ±60 s of game time 12:30 (`--window 30` to narrow) |
| `launch` | Start the game via Steam |
| `verify` | Check game files match the pinned build (fails after a game update) |
| `build` / `install` | Build / install the AI mod data pack only (release; testbed must be off) |
| `uninstall` | Remove everything we installed |
| `find <regex>…` | Search game function names (`--strings` for text). Several patterns = OR |
| `dec <name or id>… [--asm]` | Decompile a game function (or raw disassembly) |
| `index` | Rebuild the function/string index in `work/` |

One-time setup: `powershell -ExecutionPolicy Bypass -File ai-mod\setup.ps1`

## Hotkeys (testbed on; not while Ctrl/Shift are held or the console is open)

| Key | Where | Does |
|---|---|---|
| **O** | Main menu | Start the test match (4 AIs, random map) |
| **P** | In game | You become AI too, all factions at war, speed x2 (press once) |
| **L** | In game | Drop a marker in the AI log. Press it when the AI does something dumb |
| **K** | In game | Toggle fog of war |
| **F9** / **F10** | In game | Speed 1 / speed 4 |
| **Tab** / Shift+Tab | In game | Switch to the next / previous faction (camera follows) |
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
