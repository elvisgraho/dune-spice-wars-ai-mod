# Progress

Open work and checks. What exists is described in README / docs; this file lists only what is left to do or verify.

## Working (in-game confirmed)
- Tooling (`mod.cmd`), baseline/backup, testbed start flow (O in menu, P in game)
- `ai-log` events + `mod log` (HEALTH line, orders, fights, marks, `--around`), `aw` scan
- `hunt` runs without game exceptions; `busy-siege` removes the getUnits `.siege` crash
- hunt armies-only force, chase-in-contact progress, contest size, `stuck` vs NoAvailableArmy (first Annex 20 s after the first pick), rally here / commit / `rlyk`, `pick-life`, raid refuse `alt`
- raid start / `weak` abort (one measure; Harkonnen Birbat 71:50 aborted 7 s after start as Atreides' stack walked in, 303k -> 887k),
- launch gate `Skip` (1-2 fires/min while `exposed`), sietch / renegade strike gate, contest floor, raider-contest group, far annex, siege position, Fremen ring, `dstop`

## Verify in-game (built, offline-checked only)

**Pruning rule (every match analysis):** check each row against that match's `mod log` / archived log. Pass (the rule fired and the criterion holds) → delete the row; the docs already describe the behavior. Fail → move it to Open issues with the evidence (time, factions, numbers). Not exercised → keep it and bump `n/a`; at 3, make the scenario trigger it (testbed/scenario.json) or delete the row. New rows only for rules built in the same session; one row per rule, one line each.

| Check | Pass when (per match) | n/a |
|---|---|---|
| peaceful annex | Atreides `pannex` rows (r Success) only after an Annex pick with no army order (NoAvailableArmy etc.) and never before 4 villages owned; army Annexes still launch when armies are free; fewer `NoAvailableArmy` / `stuck` Annex outcomes (25 / 21 before); Influence never below 50 from it | 1 |
| annex wait cap | `aswap` rows with `wait` >= 120 when the top 3 are unaffordable; no 28-min Annex gap with an affordable candidate listed (Atreides 05:23-33:50); the `Stocks` lines show whether Authority itself was short | 0 |
| contest arrival | hunt `nogo late` rows for contests that couldn't arrive; no contest arriving after the capture ended (Smugglers Tuoiel 70:00 -> 70:36); contests on stalled captures still start | 0 |
| gather 20 s | no Military order cancelled (`src <none>`) in Action seconds after it started with its armies 100+ out (Atreides Pel-fir Dismantle 75:04 -> 75:09, A_Ship alone) | 0 |
| rally standoff / raiders | no rally -> giveup -> rally loop on a village whose only active attackers are raiders or a stack shuffling inside its own land (Harkonnen Tab-esek vs rebels + Atreides at Nundad, 22:16-72:24, 4 `dstop`); the rebels at a rebelling village of ours die within minutes (vanilla Defense picks with cand > 0) | 0 |
| discovery reach | `disc` rows with `FAR dl...`; no Smugglers-like Discovery orders to events 1000+ from our land (CrashedShuttle (1710,936), InfiltrationCell (1081,421) every 1-2 min) | 0 |
| renegade base / sietch sizing | Dismantle and PillageSietch picks at req 1.50 and >= 10 / 8 armies (`pick` rows, RenegadeBase / Sietch*; `floor` rows in Refused siege launches; Smugglers lost 8 armies, its whole army, at est 1.32 on Bur-Al'ur); `sengage` on one only at M >= 1.5 x H; fewer Dismantles cancelled in Action (Atreides 75:09 at 1.2, 86:13 at 1.33) | 0 |
| busy defenders | raids / presses on a village next to its owner's running capture count that capture's armies in full (`raid` H); no raid losing > 50% to a relief from an Annex next door (Smugglers Aidval 60:10, -57%) | 0 |
| defense ratio data | vanilla Defense `pick` rows (`Rejected picks ... def`) show req 1.15 flat instead of 1.00-3.50 / 0.80-2.50; *unverified* that VillageDefense is the constant they read | 0 |
| turret steering | `turret` rows at a village facing a standing at-war stack; MissileBatteries appear there within a few minutes (rows seen: Sad-san / Aidval with vanilla sc -2, check whether a battery slot existed) and stop once our cover reaches ENTER x the stack; one set per bunker pair | 0 |
| force peace | Atreides `fpeace` rows (r 1) only right after a `giveup` / `dhope` on a village besieged by a non-Fremen at-war faction; the attacker's siege ends at once (treaty cancel), war becomes peace; never without a siege on us; <= 1 try per 60 s | 2 |
| wind fallback | `wind` rows when the windy-village filter empties the Annex list; Annex launches follow (Atreides `wind` 05:00-11:06 then no Annex until 33:50: Authority-starved, see Open issues) | 1 |
| home guard movers | `raid` `home` aborts / `strat` hold / `exposed` refusals no longer triggered by an at-war stack patrolling inside its own land (Fremen Yelat 04:03: 8 Atreides armies on Patrol near Fonbat, H 237k, never came); a stack walking to our border still counts in full | 0 |
| home floor | no `raid` `home` abort / `exposed` refusal with hh < 80k (Fremen Grimwan 17:21 h20k m0k, Smugglers Fondah 18:24 / Grimwan 23:06 aborted at 0-10%) | 0 |
| raid reach | `raid` start / refuse rows during the Devastated gaps (Smugglers had none 06:50-15:20, 26:20-34:50, 39:10-50:50) incl. targets 2 zones out; far ones refused by supply / relief / home, not silence | 0 |
| release | `release` rows on occupations under way with no danger (n released of); armies under 90% supply stay; the keeper is a permanent army (no capture cancelled when a temporary keeper disbands); no siege order cancelled by `AIOrder.removeUnit` in Action; no release while an enemy army could reach the target before the capture ends (radius = remaining time x 6); no keeper lost to relief after a release | 0 |
| raid split | `raid` act split (defend / home) instead of abort in Action; the pillage still ends Success; the released armies join the defense (vanilla Defense / contest rows) | 0 |
| rally Defense trickle | during a `rally`, no vanilla Defense of D with armies from the rally point (`pick` rows on D with sel > 0 only for armies at D); no Defense army walking out and back at R; after `commit` a full Defense / contest hunt goes in (Fremen Ulmara 15:52: 2 armies from Tabr, 45 s tug-of-war, in alone at balance 0.25 at 17:20) | 0 |
| rally here / gate | `rally` act here never counts the armies at the running rally point (M within 250 of D: Fremen Grim-po 22:12 committed with Tabr 236 away); `space` rows why rally instead of sieges launched from the rally point (Fremen Annex of Sabbat 22:22) | 0 |
| one fall-back point | fight retreats near one fight flee to one structure (`micro` Flee targets equal within 30 s); the main base taken when the enemy is at a nearby village (Fremen Grim-po 23:07: 2 armies fled 320 to Sabnun past Tabr) | 0 |
| thumper zones | no `whold` / `wflee` rows for armies inside a region next to a Decoy Thumper (Zone_NoSandworm); a flee ends inside such a region when it is the nearest safe point (Fremen at Aeg-wahad's edge 30:08-31:02: 6 flees of 20, held out of Resupply / Defense) | 0 |
| ride reinforcements | no `dhope` / `dstop` on a structure while our Defense armies ride a worm / shuttle to it; no siege launched off it then (Fremen Sandmur 05:46-05:57: hopeless at 107k mid-ride, Defense stopped, Annex of Burtar took the last 2 armies) | 0 |
| contest turret | no hunt `start` + `abort turret` pairs within seconds on a contest; `nogo turret` instead (Fremen Sandmur 08:00) | 0 |
| DMZ war | `dmz on` rows; no `raid` start / vanilla Pillage on those villages, `raid` start lib=true (Liberate) or Annex orders on them instead | 0 |
| DMZ truce | `dmz war` rows only when the partner holds 3 border villages or 2 + a capture next to us; r 1 (Success) then a contest of that capture | 0 |
| walk through enemy | during an at-war capture / liberation of our village, no `strand` / `heal` target and no `rally` point (r) on the far side of it from our armies (Harkonnen at Tsimlat 25:08-25:54: r Had-Al'riyah, strand 4 armies from Tabiel past the Fremen stack) | 0 |
| strand near home | `strand` rows with near=move for idle armies next to our village but losing supply (Smugglers' pillage armies on Sandnun 15-30 from Allon, 264 -> 230 supply for 25+ s, 15:16-15:40); no army re-moved every 15 s (it ends inside our zone) | 0 |
| hunt proximity | a chase `start` goes to the at-war group nearest our free armies when it is within half the distance of a bigger one; no `objective` abort right after a chase start | 2 |
| minor contest | hunt contest `start` on a non-own village > 300 from our land only when no closer chase scores higher; no `objective` abort for one; no contest of a raider siege of a third faction's village | 2 |

Dropped after 3 matches without a trigger (built, *unverified* in game): hunt chase / retreat `pursuit`, hunt `desert` abort, `peace-gate`, threat busy / outside weights, tension contest, `keep-capture`, bunker score, `unstick`, main-base guns x3, `disengage`, sietch value, renegade Takeover defend.

## Open issues (evidence in logs)
- [ ] Harvester run didn't save it: Fremen F_Harvester_Mobile `hrun` 21:50 and 22:10 (H 165k, M 0, ok), killed by the Smugglers hunt ~22:27; every `hfield` pick in between was a SpiceArea at danger 100 (dg 100 / 99 / 93): the field list offered nothing outside the danger zone, or DANGER_KEY lost to distance. Next: log the candidate count and the best non-danger field's distance in `hfield`
- [ ] No reinforcement of a running siege (user note: "commit more army"): Harkonnen's Birbat Annex (10 armies, Action 62:07, held b 1-11) collapsed when Atreides relieved it (~65:00, b 0.12); vanilla has no add-to-order (AIOrder has only removeUnit(s)). In this match no Harkonnen army was free (strat `hold`, the rest rallying vs 2x Fremen at Ara-Al'wan), so a relief rule wouldn't have changed it; build it as a hunt on the relief group (§4 "reinforce if free armies arrive in time") once a log shows idle armies within JOIN_R of a losing siege
- [ ] Raid army taken by a vanilla Annex 1 s after launch (Smugglers Arstah 61:00, Annex Sandmon prio 3 took its only army): the raid-gauge hold had timed out (gauge full > 20 s on NotEnoughArmies) and armies freed at once. Raid should also skip while vanilla's Annex pick could take its armies, or the Annex should not take a raid army before Action
- [ ] Sietch strikes oversized: 15 armies at 12-18× live order balance (Ub-Al'khelon 54:41, Gur-Al'iel 58:57: siege-join added 2 / 7 at JOIN_TO KILL × 212.5k static militia); vanilla's pick counted Fremen armies standing at the sietch (est 444M vs live 57M). User: sietch / renegade-base defenders don't respawn during the strike, so live militia sizing is safe (`release` now frees the spares once the strike is under way)
- [ ] Enemy villages almost never targeted: vanilla desiredStatus is 0 toward most at-war factions, so Annex / Pillage skip them (`Annexation:Invalid` 73-132× per faction). Raid lifts the gate (3 of 43 raids hit at-war villages); Annex only via a `strat` press. Next: post-fight Annex / pillage choice (policy §5b utility)
- [ ] Raid relief underestimated: Atreides raided Pel-Al'ram (Fremen) 49:10, 10 armies 440k vs h 111k, lost 73% when Fremen relieved it (rally 49:44). Read `--around 49:10`: where were those armies, why not in REACT_R
- [ ] Raid militia losses 30-70% at est 2-2.5× (Harkonnen Aegdud 12:20, Smugglers Haanim 04:40, Fremen Gunpo 05:00): armies gather inside militia reach during Regroup. Needs a regroup point outside it (start: `fillAttackSteps` closure f@40868 `--asm`, REVERSING Regroup)
- [ ] Lone army fights on after its hunt ends (Harkonnen H_Soldier at Ubras 06:20, hp 100 → 47, no retreat row): the warzone balance / `pursuit` ignore raiders and militia. Read a `wzb` "Fight balance" run of such a fight, then fix the measure
- [ ] Supply budget (SUP_U) assumes the normal drain everywhere; deep desert / wind drain faster (`Army.getSupplyChanges(null, null)` gives the real rate). Discovery trips into the deep desert are uncovered
- [ ] Siege supply starvation: the militia fight drains (Alwahad: 5 armies 85 → 0-1 supply in ~50 s before occupation). Design a §4 trigger (step into supply / rotate) before code; never cancel a near-complete capture
- [ ] Undersized neutral Annex (vanilla 1.0): 2 armies, ~50 s militia fight, one focused down (Fremen Ashdak ×3). Open: fight retreat exemption for a capture whose militia is nearly dead; no vanilla add-to-order for armies freed after launch
- [ ] Orders cancelled right after start (`src <none>`, 0.04-1 s): hunts, and Discovery re-issued every 1-2 s (Fremen CrashedHarvester 26 s). Likely a refused Shuttle path step (`checkOrderTerminations`); log the ability result
- [ ] Rally timeout commit sends a strung-out force: armies 300-500 out arrive in waves (Harkonnen Qafiel 48:40, front 7-8 fought at raw 0-20); `gather` holds a leader 10 s at most
- [ ] Harkonnen villages rebelled (Tab-esek, Fon-ron: `Rebels` hunts 13:00-52:50): stability falls on water shortage (REVERSING Rebellion). Economy: the AI never fixes the cause
- [ ] Neutral siege wipes vs militia only (Fremen: Ubdah 09:57 3 armies -100% in 2 min, Bir-kus 30:23 -69% at engage M/H 4.1, Kul-po 47:47 -93% at 2.2 with F_Demo + Discovery_FremenTrooper picked 684 away, raid Fondah 52:20 1 army -93% at 1.55); other militia fights at 2-4x lost < 25%; supply was fine (250/360). Next: read `sact` rows (armies' kind / hp / supply at Action vs H) and decide (weak / temporary units, a militia ratio, or picks from far)
- [ ] Order army idle outside its capture: Atreides' Gurlon Annex (Action 3:46, 4 armies, militia dead ~4:11): its A_Elite left to fight a raider at Ara-dud, then stood idle 35 from Gurlon on a neutral cell (not occupying, draining supply) from 7:17 until vanilla re-sent it after 7:56; `unstick` doesn't apply (it clears while the village is occupied, STUCK_R 30). If such idles exceed ~60 s again: `rejoin` in spos.py (our order in Action, we occupy, army idle / not occupying / > 30 out -> Move to 20 from the centre, <= 1 per 12 s)
- [ ] Smugglers micro `None` switches x234 in a 6-min match (others 12-22): stealth units idling or a stuck micro state; read `--around` a burst next match
- [ ] Memory: global maps keyed by orders / armies never drop dead keys and keep them alive (strong refs): hunt progress `hcrush` / `pst` / `psp` / `psd`, gather `ghold`, `rallied`, spos `stkx` / `stky` / `sposm`, heal warzone `pst` / `psp` / `psl`, throttle maps keyed by armies. Size unmeasured; fix: drop the key when the order ends / the army is removed, or sweep every few minutes
- [ ] Tooling: `fight` me% counts armies leaving the order as losses (Harkonnen Gur-Al'iel 58:57 "-92%" = expiring Landsraad temporaries); `mod log` "Enemy siege actions near us" reads besiegers' `aiOrder` (often null): use `aimod_sieged`

## Next (policy-ordered)
- [ ] Strategy candidates from expert play: [docs/strategy/CANDIDATES.md](docs/strategy/CANDIDATES.md) (C1-C17 biases with exits; C16 / C17 gear sets and operations: docs/strategy/ARMORY-OPS.md, built when a log shows the failure; R1-R6 research first, R1 operations, R4 faction abilities and R5 hegemony reads unlock the most; overrides O1-O5 in GENERAL)
- [ ] Force peace for a besieged main base (needs its own hopeless test: `dhl` / rally concession never mark a main base)
- [ ] Contact tension step 3 (policy §5c, after the contest row passes): truce partners not attacked by default, Fremen excepted (free betrayal at T 1 held T_HOLD); others declare war at B ≥ 1 on a soft contact village, one per long cooldown (code facts in §5c)
- [ ] Threat weighting: check BUSY_W 0.25 isn't low (armies finishing a capture next door break off in seconds; built only for a target of their own faction: `busy defenders`); consider ETA weighting
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
- Temporary armies (no safe regen) leaving lost fights: vanilla drops them from the retreat on purpose; left as is (user decision).
- Power-loss cancel constants (`AI_*Attack_PowerLossCancelRatio`): no AI code reads them (no constant index load, no name reference).
- Traced `checkPeacefulAnnexation` (~186/min) and `tryLaunchOperationFromOrder` (~109/min, always False): flood the log.
- Fandom wiki (dunespicewars.fandom.com) via WebFetch / curl: HTTP 402 / Cloudflare challenge; read effects from `work/data.original.cdb` instead (building / ability sheets).
- Running `D4X.exe [boot file]` directly as a load check: vanilla `backup/hlbootdx.dat` starts, but every testbed build prints `JIT ERROR 0 (jit.c line 1242)` and exits, including builds that start fine through Steam. Not a valid crash test; launch through Steam. An offline register-kind check of appended functions (Mov / arithmetic / compares / call args / fields) found one real bug (discovery gate register reuse) but not this.
