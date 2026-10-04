# Fremen worm riding (thumpers): plan

Goal (user): Fremen use worm rides **offensively**: reach farther across the map, attack, and get to enemy Annex / Pillage / Liberate in time to stop them. The surprise of a ride is kept: nobody reacts to a worm in transit. Out of scope for now (user): escape rides, thumper economy, other factions reacting to rides. Code facts: REVERSING "Worm riding (vanilla AI)" and "Worm rides (`rules/ride.py`)". Binding rules: AI-POLICY "Worm rides".

**Status:** stages 0-4 built together (user), `rules/ride.py` + edits in strat / join / world / common / siege / hunt / intel; offline-checked, in-game checks in progress.md "Verify in-game". Built differently from the text below:
- Thumper budget (first match: 3 at start, the cap; 3 short early Annex rides spent them all by game minute 6, none came back): the last free thumper goes only to a trip >= RIDE_FAR 350, a contest or a Defense; shorter trips ride while RIDE_SPARE 2 are free. The budget readers (`_ride_leg`: trip filter, raid budget; contest ETA counts as critical) apply the same rule.
- One trip test instead of RIDE_SAVE: a trip ≥ RIDE_MIN always saves well over 40% (a 200 walk ~33 s vs ~8 s ridden + overhead).
- No landing-threat walk test and no landing-point move: the order's own gates (siege-join / raid / hunt sizing at the target) already judge the place the worm lands next to, and the worm lands the group together (staging's goal); a moved landing point could fall off worm-able sand.
- Claims (user: reserve as soon as decided): map `wres` at plan time, lapsing after RIDE_CLAIM_T 180 s; a granted order stops asking (map `wdone`); an army still on its Worm step after RIDE_PICKUP_T 15 s walks the rest (landed off the landing point: vanilla would call a second ride; or not picked up).
- Stall fallback flips Worm steps to Walk in place (vanilla's own Shuttle fallback) instead of re-planning or cancelling.
- Raid budget: `aimod_raidsup` counts the walking leg only (trip − RIDE_LEG); the way home is still walked.
- `aw` rows (logging) still omit armies in transit; the shared threat queries count them from memory.

## 1. What vanilla does (code-confirmed)

| Topic | Vanilla |
|---|---|
| When | Only in `addOrder`, only `ArmyFight` / `ArmySiege` orders with ≥ 4 armies and ≥ 1 thumper. Raze: always. Annex: far (≥ 4 zone hops) or owned target, > 1 thumper. Liberate / Pillage / sietch / renegade strikes: never. Defense: only with an enemy at the structure. |
| Never | Raids and sieges of < 4 armies, Liberate (the Fremen's main tool), our contests of a siege next to us, Patrol / Resupply / Discovery. |
| Plan | Walk to a thumper point (the reachable sand cell nearest the armies), ride (≤ 400 path, 600 with `Wormriding_Range_Bonus`) to a landing point near the target, walk to the attack slots. Regroup ends on landing; Engage follows at once. |
| Execution | `checkRegroupOrder` calls `requestRide` every tick and ignores the result. **No timeout:** no thumper, another ride of ours active (one per faction), or an army within 30 fighting leaves the order in Regroup (*unverified* in game). |
| Side effects | The worm takes **every** ground army of ours within 30 of the thumper. Calling it removes the nearest wild worm within 120. |
| Ride | ~25 u/s vs ~6 u/s walking (+ ~5 s pickup / arrival; TruePeople ×2, invisible, stealth on drop). Riders: untargetable, 0 power in radius queries, **no supply loss**. |
| Stock | 3 at start (the cap; data says 5), no regeneration before 5k hegemony. A handful of rides per match: each must count. |

Logs (33 archived matches): Fremen armies were in transit 5 times (Harkonnen 65, Smugglers 73: shuttles). Fremen ride almost never.

**Our layer today:** `_army_loop` (rules/common.py, used by every shared query) and the `aw` scan skip transported armies **before** the fog-of-war memory is read, so an enemy stack seen boarding a worm or a shuttle vanishes from `aimod_threat` / `aimod_react` / `aimod_home` / owner sizing until it lands. Our own order's riders are held by `_riding` (RIDE_MAX 60 s) in hunt / raid judgement only.

## 2. Principles for rides

- **A ride is a path, not a plan.** It belongs to the order that owns the armies (siege, raid, contest hunt, Defense). No ride without an order; the order's own gates (sizing, supply, threat) decide whether we go at all. The ride only changes how we get there and how far "there" may be.
- **Surprise stays.** Land out of turret reach and out of sight where possible (the stage point), and go in together on landing. Other factions don't track the worm.
- **Seen is remembered.** An army seen boarding stays where it was seen, at its seen power, for the normal memory time. It isn't tracked to its landing point and doesn't vanish.
- **Spend thumpers on value.** With ~5 per match, a ride must unlock a target walking can't reach, or reach a contest walking would lose. No reserve while escape rides are out of scope.

## 3. Stages

### Stage 0: instrument (no behavior change)
Logs:
- `wplan` (addOrder, Fremen Military / Defense / our hunts): plan worm / walk, vanilla gate inputs (armies, thumpers, prio, hops, owned), walk distance.
- `wreq` (checkRegroupOrder): `checkRequestRide` reason while a Worm step is refused, one row per order per 5 s. Stall time per order.
- `wride` (implInlineRequestRide): from / to / distance, riders (order members vs outsiders swept up), thumpers left.
- `tstk` every 60 s per Fremen: thumper stock and max (settles the 5 vs 3 cap question).
- `mod log` "Worm rides": plans, rides, stall seconds, ridden orders' outcome vs walked ones.

Pass: 2-3 matches with Fremen, giving how often worm plans occur and stall, and the real stock.

### Stage 1: memory for riders (correctness, all factions)
- `_army_loop` gets a variant for the hostile-army queries: a transported army is not skipped; it goes straight to `_ghost`'s memory path (treated as unseen, even if `isVisibleForFaction` says otherwise), so it counts at its last sighting (boarding point, seen power, SEEN_T / SEEN_HOME_T, GHOST_R_MAX drift) and never at the worm's live position. Our own armies' loops keep skipping riders.
- `aimod_intel` writes no record for a transported army (the boarding sighting stays the record; the landing sighting replaces it).
- The `aw` world model lists a transported hostile army as remembered (`kn`, not `vis`), so `mod log` shows it and hunts don't read its group as gone.
- Hunt on a group a member of which boards: the member leaves the prey group (we can't chase a worm), the hunt ends `ride` if nothing is left, without counting a win and without barring it (GIVEUP_T is for runners).

Expected log change: no drop in `aimod_threat` / `aimod_home` totals at the moment an enemy boards (check via `aw` rows around a `wride` / shuttle `hride`); no rally / contest decisions flipping while a stack is in transit.

### Stage 2: no stalled worm orders
- **Stall fallback (`wstall`):** a Worm step refused for RIDE_STALL_T 15 s (no thumper, our other ride active, combat at the thumper) gives the order a walk plan (re-run `fillAttackSteps` for it; if that can't be done in place, cancel with `Dismiss` so the gauge relaunches at once and stage 3's gate picks walk). Log the reason.
- **Our rules vs the thumper point:** `stage`, `gather`, `desert-step`, `spos`, `strike` and `worm-flee` leave an army alone while its order's current step is Worm (all must be within 30 and out of combat for the call).
- **Landing point:** `stage` judges the landing point: within STAGE_R of the target it moves out to the stage point on the same side (lands out of turret reach and sight, then the group goes in together).
- **Wild worm at the thumper point:** an order army waiting there that a wild worm targets calls the ride now (the call removes that worm) instead of fleeing.
- **Swept-up outsiders:** logged in `wride`; fixed only if they show up.

### Stage 3: reach and attack (offense)
Like the free Supply Drop's reach (`sdrop`, SD_ZONES), while a ride is affordable (`aimod_ride_ok`: Fremen, stock ≥ 1 or a `Wormriding_NoCost` zone at either end, no ride of ours active or claimed):
- **Reach:** siege target scans (`mscan` / `ascan`, raid `rscan`; Annex, Liberate, Pillage, raid, sietch strike) reach RIDE_ZONES 1 zone farther (2 with `Wormriding_Range_Bonus`). Reach is checked only at pick time; a running order is never cancelled for it.
- **Supply:** the walk-leg budget only (to the thumper point, landing point → target, target → home); the ride leg costs nothing. `trippick`, vanilla's InsufficientSupply (lifted like `sdrop-trip`) and the raid budget use it. A far order that also needs to stay (fight, long capture) still uses `sdrop`'s locked drop: the ride gets there, the drop keeps it there.
- **Plan gate** (our redirect of the `fillAttackSteps` / `fillWormAttackSteps` calls in `addOrder`; vanilla's 4-army / priority gate no longer decides for Fremen):
  - Worm when the target lies beyond walking reach (it came from the extra zone), or the walk is ≥ RIDE_MIN 200 and the ride saves ≥ RIDE_SAVE 40% of the travel time. Any order size (a 2-army Liberate rides too), any siege action.
  - Walk when the at-war threat at the landing point (`aimod_threat` within LOCAL + enemy cover) beats the order by ENTER × terrain: landing in a stack means landing in contact.
  - Walk when the stock is 0 or the ride would wait on another ride of ours (one worm per faction).
- **Sizing:** `siege-join` / `raid` judge the force at the target as today; no en-route strike while riding (riders can't fight).
- **Annex value:** far villages already pay vanilla's distance term (VAN_HOPS_CAP); the extra zone only adds candidates. Ring / special / centre terms decide whether a far one wins; no ride bonus in the value.

Expected log change: Fremen launches on targets beyond vanilla's 1-zone reach (`wplan` worm, `wride`), fewer `InsufficientSupply` cancels, shorter launch → Action time, win rate of ridden attacks no lower than walked ones.

### Stage 4: rides to stop enemy captures (defense)
Fremen ride to an at-war Annex / Pillage / Liberate in time:
- **Contest hunts** (our `hunt`, a capture near us or of ours): the arrival test (`_cap_rem`: nearest free army / 6 u/s vs the remaining capture time) uses the ride ETA (walk to the thumper point + ride at 25 u/s + 5 s + walk in) when a ride is affordable and the walk is ≥ RIDE_MIN; such a contest gets the worm plan. Contests that are skipped today as too late become possible.
- **Vanilla Defense** of our structure: worm plan for any size when the walk is ≥ RIDE_MIN (vanilla: ≥ 4 armies only).
- **Rally commit** (`rally`): defenders > RIDE_MIN from D whose walk would arrive after the commit ride in, so the force arrives together (open issue: timeout commit sends a strung-out force).
- Same plan gate as stage 3 (walk if the landing point is held by more than us).

Expected log change: contests started with a ride ETA, captures of ours / near us stopped that a walk would have lost (`hunt won`), fewer strung-out rally commits.

## 4. Constants (proposed, rules/common.py)

| Name | Value | Meaning |
|---|---|---|
| RIDE_MIN | 200 | shortest worthwhile ride (vanilla's `AI_WormRiding_MinDist`, unread by vanilla) |
| RIDE_SAVE | 0.4 | a ride must save this share of the travel time (when the target is in walking reach) |
| RIDE_STALL_T | 15 s | a refused Worm step falls back to walking |
| RIDE_ZONES | 1 | extra target reach while a ride is affordable (2 with the range bonus) |
| RIDE_SPD | 25 | worm speed for ETAs (× (1 + `WormRiding_MoveSpeed_ARatio`)) |
| RIDE_MAX | 60 s | existing: transit hold of hunt / raid judgement |

## 5. Checklist answers (AI-POLICY §7)

- **Failures fixed:** unreachable far objectives (InsufficientSupply, vanilla's 1-zone reach), contests that arrive after the capture, strung-out rally commits, stalled worm orders (stage 0 measures), riders vanishing from our threat measures.
- **Layer:** operational; a ride is a path choice of the order that owns the armies (no new owner, no new priority).
- **One measure:** threat at the landing point = `aimod_threat` + `aimod_cover` (as siege-engage); supply = the existing trip budget minus the ride leg; ETA = one function used by contest, rally and the plan gate.
- **Loops:** a refused ride falls back to walking once per order (no ride ↔ walk flip-flop).
- **Target moves:** our riders are judged once they land (`_riding`); enemy riders count at their boarding sighting.
- **Force:** the worm carries the group together; outsiders swept up are logged.
- **Fail safe:** every hook runs in a trap; a refused or failed ride leaves vanilla's walk plan.

## 6. Later (not planned now)
Escape rides (stranded / losing fight / wild worm), thumper economy (Thumper Factory, Hidden Thumpers op), return ride after a far capture, other factions reacting to a worm in transit.
