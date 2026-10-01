# Progress

Open work and checks. What exists is described in README / docs; this file lists only what is left to do or verify.

## Working (in-game confirmed)
- Tooling (`mod.cmd`), baseline/backup, testbed start flow (O in menu, P in game)
- `ai-log` events + `mod log` (HEALTH line, orders, fights, marks, `--around`), `aw` scan
- `hunt` runs without game exceptions; `busy-siege` removes the getUnits `.siege` crash
- hunt armies-only force, chase-in-contact progress, contest size, `stuck` vs NoAvailableArmy (first Annex 20 s after the first pick), rally here / commit / `rlyk`, `pick-life`, raid refuse `alt`

## Verify in-game (built, offline-checked only)

**Pruning rule (every match analysis):** check each row against that match's `mod log` / archived log. Pass (the rule fired and the criterion holds) → delete the row; the docs already describe the behavior. Fail → move it to Open issues with the evidence (time, factions, numbers). Not exercised → keep it and bump `n/a`; at 3, make the scenario trigger it (testbed/scenario.json) or delete the row. New rows only for rules built in the same session; one row per rule, one line each.

| Check | Pass when (per match) | n/a |
|---|---|---|
| launch gate `Skip` | `space` why exposed rows: the refused gauge (Liberation / Sietch / Raze / Dismantle) fires ≤ ~2/min while refused, not 120/min (Fremen Liberation 43:00-55:00, 1801 fires) | 0 |
| sietch / renegade strike gate | no PillageSietch / Dismantle order while the director holds with S ≤ 0 and hostiles near home (Smugglers sent 15 armies to Ub-Al'khelon 54:41 at `strat` hold); `space` why exposed rows with k PillageSietch; sietch strikes still happen when home is safe | 0 |
| contest floor | no contest `start` with `Ms` < DEF_HOPE_IN × their side (= goal / 2.5) (Atreides Fanih 27:10: 1 army 41k vs 297k); `objective` aborts are followed by a contest start or a `nogroup` row | 0 |
| raider-contest group | raider-siege contests / neutral hunts never engage an owned army (Atreides chased a Fremen F_Harvester from its Qartnah raider contest 38:20 and 47:50, H 0, until `supply`) | 0 |
| raid start / weak | no raid `abort weak` within 10 s of its `start` on the same numbers (Smugglers Ash-in 54:50) | 0 |
| hunt proximity | a chase `start` goes to the at-war group nearest our free armies when it is within half the distance of a bigger one; no `objective` abort right after a chase start | 0 |
| minor contest | hunt contest `start` on a non-own village > 300 from our land only when no closer chase scores higher; no `objective` abort for one; no contest of a raider siege of a third faction's village | 0 |
| sietch heal safety | `heal` rows (detour / avoid) for an ownerless sietch (Karlon-like) with a fight on it; no Resupply re-issued every second into a sietch where we fight at raw < 0.65 (Fremen 60:00-63:40 at Karlon) | 0 |
| far annex | Smugglers `ascore` n higher than before (1-8) and Annexes 2 zones out; none cancelled `InsufficientSupply` in a loop (`space` why retry) | 0 |
| hunt chase / retreat `pursuit` | `retreat act pursuit` rows end micro chases after an order ended within ~15 s, right after a `chase` abort; none out of a fight the enemy is losing or on our own zone; no new chase on a given-up runner within 90 s | 2 |
| hunt `desert` | `abort desert` rows when a chased prey enters the deep desert; no army at sup 0 after a chase | 2 |
| `peace-gate` | `## Peace gate` rows only while our siege on the sender's structure is in Engage/Action and none of ours is besieged; that siege then ends Success or by our retreat, not a treaty cancel | 2 |
| threat busy / outside | an at-war stack occupying a village > 60 away counts 25% in defense / rally on our land, 50% in offensives; a stack turning toward us counts fully | 2 |
| tension contest | a hunt `start` contest on a neutral village being captured next to ours at a ratio between 1.0 and 1.5 once T is high; none at T 0 | 2 |
| retreat commit | after a fight retreat the Resupply target stays the same ~15 s; on our land it lies away from the enemy | 2 |
| `keep-capture` | `keepcap` rows for armies at our capture that micro would send to defend another structure; none walks off to a structure with no enemy | 2 |
| bunker score | no `bunker` rows for neutral villages (only lost ones) | 2 |
| `unstick` | `unstick` rows only for a lone siege army in the village with no siege running; the siege starts within ~20 s; no repeat every 12 s on one army | 2 |
| siege position | `siege-pos` rows for our siege armies under enemy guns other than the target's: they stand on the far side and keep capturing | 2 |
| main-base guns ×3 | sieges next to an enemy main base size up (pick `req` higher, more armies or none); no order reading 'winning' while its armies melt under a main base | 2 |
| disengage | `retreat` act `disengage` when an army on Resupply still fights a powerless target: it leaves within seconds | 2 |
| harvester run / `memory` | `HARVESTER RUN` / `mem` / `hfield` / `hflee` rows when our harvester is shot by more than its escort; it moves to another field within ~20 s and survives; no hflee loop | 2 |
| Fremen ring | `## Annex value` Fremen rows with `dd` > 0 / `HOLD` once a desert can be ringed; ring village picked over special / spice ones; nearer ring kept (DD_FAR) | 2 |
| sietch value | Annex value +ANNEX_SIETCH 10 on sietch zones | 2 |
| renegade Takeover | a renegade Takeover of an own / home-ring village sets `defend` (`space` why defend), contest hunt from GATHER_R | 2 |
| border standoff | no `rally` rows for an idle at-war stack on its own zone next to our village | 2 |
| `dstop` | a Defense of a hopeless / conceded structure ends, no army walks back alone (Atreides Ye-wan 59:10 n 0: fired, outcome not readable) | 2 |

## Open issues (evidence in logs)
- [ ] Raid army taken by a vanilla Annex 1 s after launch (Smugglers Arstah 61:00, Annex Sandmon prio 3 took its only army): the raid-gauge hold had timed out (gauge full > 20 s on NotEnoughArmies) and armies freed at once. Raid should also skip while vanilla's Annex pick could take its armies, or the Annex should not take a raid army before Action
- [ ] Sietch strikes oversized: 15 armies at 12-18× live order balance (Ub-Al'khelon 54:41, Gur-Al'iel 58:57: siege-join added 2 / 7 at JOIN_TO KILL × 212.5k static militia); vanilla's pick counted Fremen armies standing at the sietch (est 444M vs live 57M). Read `canSpawnMilitia` / spawn timing before sizing on live militia
- [ ] `objective` abort followed by no contest (Fremen 41:36 → raider siege of Harkonnen's O-ram, Smugglers 50:33 → Tal-ras); raider sieges of third-faction villages no longer count (`aimod_sieged`); next match: read the hunt `nogroup` rows for any objective abort without a contest
- [ ] Enemy villages almost never targeted: vanilla desiredStatus is 0 toward most at-war factions, so Annex / Pillage skip them (`Annexation:Invalid` 73-132× per faction). Raid lifts the gate (3 of 43 raids hit at-war villages); Annex only via a `strat` press. Next: post-fight Annex / pillage choice (policy §5b utility)
- [ ] Raid relief underestimated: Atreides raided Pel-Al'ram (Fremen) 49:10, 10 armies 440k vs h 111k, lost 73% when Fremen relieved it (rally 49:44). Read `--around 49:10`: where were those armies, why not in REACT_R
- [ ] Raid militia losses 30-70% at est 2-2.5× (Harkonnen Aegdud 12:20, Smugglers Haanim 04:40, Fremen Gunpo 05:00): armies gather inside militia reach during Regroup. Needs a regroup point outside it (start: `fillAttackSteps` closure f@40868 `--asm`, REVERSING Regroup)
- [ ] Lone army fights on after its hunt ends (Harkonnen H_Soldier at Ubras 06:20, hp 100 → 47, no retreat row): the warzone balance / `pursuit` ignore raiders and militia. Read a `wzb` "Fight balance" run of such a fight, then fix the measure
- [ ] Supply budget (SUP_U) assumes the normal drain everywhere; deep desert / wind drain faster (`Army.getSupplyChanges(null, null)` gives the real rate). Discovery trips into the deep desert are uncovered
- [ ] Siege supply starvation: the militia fight drains (Alwahad: 5 armies 85 → 0-1 supply in ~50 s before occupation). Design a §4 trigger (step into supply / rotate) before code; never cancel a near-complete capture
- [ ] Undersized neutral Annex (vanilla 1.0): 2 armies, ~50 s militia fight, one focused down (Fremen Ashdak ×3). Open: fight retreat exemption for a capture whose militia is nearly dead; no vanilla add-to-order for armies freed after launch
- [ ] Orders cancelled right after start (`src <none>`, 0.04-1 s): hunts, and Discovery re-issued every 1-2 s (Fremen CrashedHarvester 26 s). Likely a refused Shuttle path step (`checkOrderTerminations`); log the ability result
- [ ] Vanilla Defense re-rolls its ratio every 0.5 s (Insane 1.0-3.5): failed picks ×37-120 on one structure. Contest hunts cover it; data patch Min = Max would fix vanilla
- [ ] Fremen Annexation gauge stuck near 100 with `NoStructuresWithSufficientWind` (`valueCache[1185]`)
- [ ] Rally point falls back far: R's safety counts movers heading to R, so an enemy walking at D disqualifies structures behind D (Harkonnen Qafiel → Carthag 530). Static threat for R, or cap R's distance
- [ ] Rally timeout commit sends a strung-out force: armies 300-500 out arrive in waves (Harkonnen Qafiel 48:40, front 7-8 fought at raw 0-20); `gather` holds a leader 10 s at most
- [ ] Tooling: `fight` me% counts armies leaving the order as losses (Harkonnen Gur-Al'iel 58:57 "-92%" = expiring Landsraad temporaries); `mod log` "Enemy siege actions near us" reads besiegers' `aiOrder` (often null): use `aimod_sieged`; `--around` ignores `--faction`; `aw` omits neutral raiders; hunt ArmyFight orders listed `open` after their `end`

## Next (policy-ordered)
- [ ] Standoff procedure (design agreed): idle at-war stack at our border (enter / leave 30 s) → home guard = (stack × ENTER − our cover) / OWN_T at the threatened village, surplus free for raid / annex; when the guard is most of the army, steer building to MissileBattery there (REVERSING "AI building choice")
- [ ] Contact tension step 3 (policy §5c, after the contest row passes): truce partners not attacked by default, Fremen excepted (free betrayal at T 1 held T_HOLD); others declare war at B ≥ 1 on a soft contact village, one per long cooldown (code facts in §5c)
- [ ] Threat weighting: check BUSY_W 0.25 isn't low (armies finishing a capture next door break off in seconds); consider ETA weighting
- [ ] Strategic director (§5b): utility ranking vs neutral expansion, home race on every offensive, front patrols
- [ ] Intel memory (§3a): remembered enemy armies with decaying confidence, `perceived(F)`, `aimod_threat` from memory
- [ ] Peace gate (§3b) part 2: hunts on F's armies as protected orders; our own peace offers to a faction we besiege (`Trading.doTrade` / `requestTrade`, trade kinds a2 1/6 undecoded); refuse while in charge (B ≥ 1.5)
- [ ] En-route re-evaluation: orders in Preparation / Regroup / Engage re-check hostile power near the army and cancel (vanilla never does)
- [ ] Objectives over chasing: annex weak enemy villages next to our strong free armies (bypass the aggressiveness gate)
- [ ] Later: unit-level events in `unitMicroManagement`; who offers peace to whom; `MDecoyThumper` vs hostile armies on worm sand; baseline of 3+ runs in `validation/`

## Tried / ruled out
- `Main.quickStart` / `-conf`: dead in release (`Const.flags.quickStart` false). `newgame` from the menu: in-game console only.
- `admin` password: unnecessary (1-byte `isAdmin` patch). F4 `aiDebug`: not registered.
- crashlink CLI with several `-c` flags runs only the last; use `mod dec a b c`.
- Console `report`: static attribute audit, no match data.
- Shipped AI logging: stripped (7 warnings); decisions need injected logging.
- `mod dec $AIMilitary.getSiegeableVillages`: decompiler hangs; use `--asm`.
- Decompiling all appended functions at once takes > 10 min; decompile one by id.
- Plain army target for `ArmyFight`: vanilla `checkEngageOrder` throws every tick; use an `AIEntityGroup`.
- Hunt priority "largest threat" without distance: chased far groups; score by distance + objective.
- Contest detection from the prey's `Army.aiOrder`: null on many AI besiegers (and on humans); read the village's siege state.
- Hunt supply abort only out of contact at < 50%: armies chasing in contact starved to 0; use the distance-based budget.
- Distance to "our structures" over all `faction.structures`: Smugglers' UWHeadquarters in enemy villages made deep chases look local; use our land only.
- Flat "any safe structure wins" heal penalty: sent armies across the map to the base; use a finite detour.
- Data-only fix for the stuck turret (FSpecialLeave `ai.state` = Move/Resupply): fires only in Regroup/Engage/Resupply phases, never in the siege Action where it is stuck, and the order's `noMoveAbilities` would still block its Move.
- Traced `checkPeacefulAnnexation` (~186/min) and `tryLaunchOperationFromOrder` (~109/min, always False): flood the log.
