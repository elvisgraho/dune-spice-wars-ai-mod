# AI design policy

Binding for every AI behavior change. Goal: an AI that is **functional, predictable and hard to exploit**, built from a few general mechanisms instead of many special cases. Read before writing a rule; check it against §7. Thresholds below are the constants in `tools/rules/common.py` (values there win if they differ); hook points and ids are in REVERSING.

## 1. Principles

1. **Evidence first.** Add or change a rule only for a failure seen in a log or proven in code. State the failure and the expected log change up front. No speculative features.
2. **Steer vanilla, don't replace it.** Vanilla has gauges → actions → orders (phases, priorities, fight retreat). Fix its inputs (threat, targets, force size) and fill gaps (hunting, contesting). Rewrite a subsystem only when hooking inputs can't express the fix.
3. **One world model, one power metric.** Every decision reads the shared queries (§3) with power from `HPowerScore.singlePowerScore(HCombatStats.unitCombatStats)`. No private scans, radii or formulas.
4. **One question, one measure.** Every judgment of the same situation (start / keep / commit / concede a plan; the same structure judged by two rules) uses the same function at the same place, so two rules can't contradict each other or a plan start and abort on consecutive checks. Turret silencing is decided only inside `aimod_cover`; callers never emulate it with `exclude`.
5. **Plans are commitments.** A decision holds until a declared trigger fires (§4). No re-deciding on a timer, no flip-flopping.
6. **Concentrate force.** Enough to win with margin, all together; never trickle armies in. Can't gather enough: don't go.
7. **Every army has one owner.** Only a higher ladder step (§5) may take an army. Taking one army from an order before Action cancels the whole order, so a siege launch never takes from another gathering Military order of 2+ armies (a Defense may). Rules never issue raw unit commands behind an order's back.
8. **Fail safe.** Injected code runs in traps; if it fails or finds nothing, vanilla continues unchanged.
9. **Observable.** Every decision logs one event with inputs, choice and reason code.
10. **Small complexity budget.** One general mechanism over N special cases; delete rules that don't measurably help.

## 2. Decision layers

| Layer | Scope | Cadence | Who decides |
|---|---|---|---|
| Strategic | faction | aware scan, posture held ≥ 60 s | director (§5b) over vanilla gauges, aggressiveness, diplomatic targets |
| Operational | army group ↔ one target | aware scan (10 s), acts only on triggers | vanilla orders + our rules (hunt, contest, raid, rally, aborts) |
| Tactical | units in one fight | per tick | vanilla `unitMicroManagement` |

A layer may constrain the one below, never micromanage it.

## 3. World model (per faction, every aware scan)

- **Hostile groups:** at-war armies clustered by proximity (250): power, position, heading, on own territory, supply, intent when known.
- **Threat at a point** `aimod_threat(fac, p, r)`: at-war armies + raiders whose raid targets us within r, plus movers heading to p that arrive within 20 s (≈ 120 units). Weights: an army occupying a structure > 60 from p counts 0.25 when p is on our land, 0.5 off it; for p on our land an idle army off our land > 100 away counts 0.5; full at their own position / capture. Heal / retreat / strand safety uses the undiscounted threat (an army rests there; a busy stack is free once its capture ends).
- **Diplomacy:** combat only at `War`; Truce / Tribute / Alliance forbid it, Hostility never fights. Threat = at-war armies only, read live; a declaration or truce is a trigger for every running plan.
- **Shared queries** (`rules/world.py`; every rule uses them): `aimod_threat`, `aimod_threat_now` (3 s), `aimod_react` (+ free at-war armies within REACT_R 480; capturing ones at half), `aimod_neutral` (raiders busy with someone else: they fight back), `aimod_hthreat` (hunt: the prey's side; its allies only if they arrive before the kill), `aimod_own`, `aimod_terrain`, `aimod_land` (distance to our land), `aimod_supok` / `aimod_short`, `aimod_sieged`, `aimod_cover` (turret cover, §5a), `aimod_defend`, `aimod_danger` (place memory). `threat` is armies only; rules add `aimod_cover` where structures matter.
- **Our land** = our structures on zones we own (UWHeadquarters in others' zones don't count).

### 3a. Intel (place memory built)

Built: per faction, zone → last danger event (our harvester attacked); `aimod_danger` = 1 fading to 0 over DANGER_T 180 s; harvesting teams avoid dangerous fields. Grows one event kind / consumer at a time, each from a logged failure; every rule reads the same `aimod_danger`.

Design: decisions should use what the faction has seen, not true strength. Memory per enemy army (last position, power, time; refreshed when visible); position confidence decays (`last_pos + speed × age`), strength decays slower toward a floor; `perceived(F)` = Σ remembered power. Not saved with the game; conservative until re-seen.

### 3b. Diplomacy goals (part 1 built)

`B(F)` = our strength / perceived(F): ≥ 1.5 in charge, ≤ 0.67 losing. Refuse a peace offer from F while our order on F's structure is in Engage / Action (**built**: `peace-gate`, unless one of our structures is besieged), or while in charge and the offer pays less than what we'd take by force (design). Offer peace when losing or when a stronger third enemy appears (never instead of defending). Declare war only with a goal. Hysteresis as §4. Vanilla accepts by trade value only and offers peace at status 0 by random chance.

## 4. Plans, ratios, triggers

A plan = a vanilla `AIOrder` plus our enter / keep / abort thresholds and triggers.

**Ratios** (ours / theirs at the place; × terrain first):

| Name | Value | Meaning |
|---|---|---|
| keep | 1.0 | continue; also "at least even" (DEF_HOPE_IN, rally commit, opening EARLY_REQ, tension floor) |
| neutral | 1.25 | siege launch on a neutral target (NEUTRAL_REQ; vanilla 1.0); supply hysteresis SUP_ENTER |
| enter | 1.5 | start an offensive; rally ends at enter × 1.15 |
| abort | 0.7 | re-decide below this (also the press keep) |
| retreat | 0.65 | fight retreat (fixed; vanilla re-rolls a range every tick); the no-enemy 1.0 is never multiplied |
| PART_X | 2 × enter | engage with part of the order still on the way |
| HUNT_TO | 2.5 | hunt force target |
| KILL | 3 | force target of raids / sieges (RAID_TO, JOIN_TO), director softness (PRESS), restricted hunts (far, under cover, deep desert, defensive posture) |
| terrain | × 1.3 own zone, × 0.8 at-war zone | attack on their land needs ≈ 1.9; home defense holds to ≈ 0.5 |

Entry and exit measure the same thing at the same place (hunt: the prey at start, then the group's core = the member nearest our land; never a centroid). Members > LOCAL from the core leave the target group.

**Timers** (commitments and cooldowns; a plan's own triggers can end it earlier):

| Tier | Uses |
|---|---|
| 10-15 s | gather hold (10 per attack), CRUSH_T 10, PURSUIT_T 15, HEAL_COMMIT 15 |
| 20-30 s | worm hold 20, raid gauge hold RAID_GAUGE_T 20, HUNT_GAP 30, commit 30, DISC_RELAUNCH 30, objective switch 30 |
| 60-90 s | HUNT_AREA_T 60, DISC_RETRY 60, RAID_RETRY 60, RALLY_GIVEUP 60, posture 60, RIDE_MAX 60, GIVEUP_T 90, RALLY_COOL 90 |
| 120 s + backoff | PRESS_RETRY 120, PRESS_MAX 240, retry 30 → 240, stuck 120 → 480 |

**Supply budget:** an army needs 0.35 × distance to our land + 10% max supply to walk home (drain ≈ 0.28 / unit). `short` = losing supply and below it: hunts abort (in contact too, unless on the prey with KILL ×, never for a powerless prey); in a fight the balance × (1 − 0.6 × short share). Joining a hunt needs SUP_ENTER × the budget at the target. **Recall:** every army of ours in a fight short and none on a Military order → balance 0 (leave, even winning). **Stranded:** a short army that can't pay the walk home anyway gets neither penalty nor recall: withdrawal is impossible, so it fights all-in (below). Our supply budget assumes the normal drain rate (deep desert is faster: open issue).

**Re-decide only on triggers:** (1) a new hostile group can reach our armies or target before we finish; (2) the projected ratio crosses abort; (3) the target is invalid (dead, owner changed, invisible, a hunt prey home); (4) stuck: no progress for N s (chase: PURSUIT_T without the prey losing PROGRESS 10% power or us closing max(CLOSE 30, (gap − CATCH_R 40) × PURSUIT_T / CATCH_T 30); within CATCH_R counts as progress); (5) expiry.

**On a trigger, in order:** continue if projected ≥ keep (threat ETA included) → reinforce if free armies arrive in time → withdraw to the nearest safe point if we get there before contact → fight all-in if withdrawal is impossible, or ratio ≥ abort and the objective is worth it (own structure, nearly done capture) → otherwise withdraw.

## 5. Priority ladder

| Prio | Orders |
|---|---|
| 10 | defend main base (vanilla) |
| 5 | Defense of own structure (vanilla), hunts: contest of a siege near us, chase, neutral-raider hunt (only when no at-war hunt qualifies) |
| 4 | Raze |
| 3 | Annex |
| 1 | Pillage (vanilla and `raid`), Liberate |
| 0 | Patrol, Resupply, Discovery, `strand` |

New rules pick a priority here and add themselves. An army in Resupply is never free. A short army on hostile land starts nothing.

## 5a. Faction goals (highest first)

A lower goal starts only when every higher one is satisfied or impossible; a running lower plan yields when a higher one appears (except a fight about to be won in contact).

| # | Goal | Means | Posture |
|---|---|---|---|
| 1 | Survive / supply | supply budget, `strand` (idle army on hostile land → Patrol home), `undeploy` (installed F_Special_2 off-fight on hostile land), `ability-gate` (no emergency abilities at balance 1.0) | short army starts nothing |
| 2 | Defend what we own | `aimod_defend` (below): contest hunt, free armies within GATHER_R 900 join; our pillages and Annexes within 500 still walking / < 25% done yield when the defenders fall short; `rally` when outmatched | defensive: no new vanilla siege, no chase starts, chases abort (`defend`); exception: prey in contact with ≥ KILL ×; short of the ratio, gather at home, never trickle in |
| 3 | Bunker | a lost village under our main base (≤ 110): vanilla Annex redirected to it; a neutral one × 1.5 in the Annex value; a village pairing with ours (≤ 130): target score × 1.3 | – |
| 4 | Stop captures next to us | contest hunt on an enemy siege ≤ 500 from our land (weight 3); a running chase yields (`objective`) | – |
| 5 | Opportunity | chase hunt ≤ 500 from our land (≤ 300 if the prey is on its own land) | – |
| 5a | Neutral raiders | neutral hunt near our land; elsewhere only in contact at KILL × | – |
| 5b | Raid | `raid` (below) | – |
| 6 | Expand | vanilla Annex / Pillage / Raze, spaced and sized (below) | – |

**Sieges near us (`aimod_sieged`):** an at-war faction's siege / occupation of a neutral village, ours, or a non-at-war faction's; a raider siege only of a neutral village or ours.

**Defend (`aimod_defend`):** our village or main base besieged by an at-war faction or taken over by renegades, else a neutral village ≤ HOME_RING_R 250 of our active main base besieged / occupied by one. Skipped when hopeless (all ours within GATHER_R + cover, × terrain, < DEF_HOPE_IN × threat + neutral raiders + enemy cover; re-included at DEF_HOPE_OUT 1.2; map `dhl`) or conceded by the rally; never skips a main base. A running Defense of a hopeless or conceded structure is stopped (`dstop`) and gets no armies (vanilla re-sends fled armies one by one). Raider sieges are the contest hunt's, not a posture.

**Turret awareness.** Turrets (MissileBattery 40, main base guns 80, range 80) cover COVER_R 130. A village under a faction's siege has silent turrets (both views). Attack sizing adds every other at-war structure covering the target and drops the target's own while besieged; defense sizing likewise. Main-base guns count MB_GUN_W 3× everywhere (their power score understates them). Hunts count enemy cover as threat and ours as power in the evaluation; a chase under enemy cover only in contact with KILL × (else `turret`). *Unverified:* whether a raider siege (no `besiegingFaction`) silences turrets; `aimod_cover` counts them.

### Force size

- **Hunts:** nearest free armies until HUNT_TO × their side (prey + `aimod_react` + enemy cover) / terrain (KILL restricted); past HUNT_CAP 2 × prey group + 1 armies stop once enter holds. Armies alone fill goal and gate (cover counts in the evaluation only: the prey doesn't stay under our guns). Contests take armies until HUNT_TO however many (all in reach if short). The force must still have enter × their side (KILL restricted), else no hunt; a contest goes short of that but not below DEF_HOPE_IN × their side (the defense's hopeless measure: rally / Defense own it); the candidate test and the `objective` abort apply the same floor.
- **Sieges (`siege-join`):** vanilla's pick, then the nearest idle armies within JOIN_R 450 that pass the supply budget join until JOIN_TO × (threat + enemy cover + militia + other raiders) / terrain. Required NEUTRAL_REQ on neutral targets, EARLY_REQ while we own < 2 villages (the opening's 2 armies take the first villages). Vanilla sizing counts every at-war army near the target, not only the owner's.
- **Raids:** nearest raid-ready armies until RAID_TO × their side.

### Gathering and engage

Don't idle next to the prey, never wait in the deep desert, never wait for a prey moving away. A hunt leaves Regroup once the armies within LOCAL of the core pass enter; stragglers walk in. Our sieges (`siege-engage`) leave Regroup once the armies within ENGAGE_R 100 of the target pass enter (neutral 1.25) vs threat + enemy cover + militia; PART_X × that while some are still on the way. In Engage a leader > 15 ahead of the farthest attack army (within 400) waits out of contact, ≤ 10 s per attack (`gather`). Siege picks don't take armies on a Discovery trip farther than JOIN_R from the target. Siege judgments count neutral raiders at the village with its militia.

### Rally

When one of our structures D is actively threatened (an at-war army at it or heading there; a stack idling on its own border zone is a standoff, not an attack) by ≥ RALLY_MIN_H 80k that our defenders within RALLY_R 600 + our turrets, × terrain, can't beat by enter: every defender not in contact walks to one rally point R (main base if clear within 150, else our nearest structure ≥ 150 from D and clear), its Resupply / Defense / Patrol dropped and vanilla kept from re-sending it; structures within 150 of D aren't heal / flee targets. Defenses of other structures (> 150 from D) keep their armies. Our armies on a Military mission count as defenders only within LOCAL of D and are never moved. Ends at enter × 1.15: the contest hunt or vanilla's Defense takes them in together.
- **Here:** defenders already within LOCAL of D (+ our turrets there, × terrain) at least even → commit at once.
- **Timeout:** after RALLY_GIVEUP 60 s still short: commit if the gathered force is at least even (always for a main base), else concede D for RALLY_COOL 90 s (and its neighbours within LOCAL). A D judged hopeless < 30 s ago is never committed (here) and is conceded at the timeout.
- **After a commit:** D and its neighbours within LOCAL get no rally for RALLY_COOL (a neighbour's rally would walk the committed force away).

### Hunts

Score = threat / (nearest free army distance + 100)²: the enemy in front of us first (half the distance needs ~¼ the threat); every contest outranks every chase (goal 4 over 5, no `objective` flip), except a **minor** one: a village not ours (neutral / a third faction's) farther than CONTEST_NEAR 300 from our land is scored like a chase and never triggers `objective`. An objective-anchored plan ends when the fight drifts from our land (`drift`); a chase aborts (`objective`) when its armies could contest a siege near our land, then only contests start for 30 s. A hunt starts only when the trip (walk out + way back) fits the supply budget. After a `supply` / `weak` / `turret` / `desert` abort, no chase within LOCAL for HUNT_AREA_T. A prey running on its own land is followed only while a member is below CHASE_LIFE 0.35. An at-war main base within BASE_KEEP 250 of the prey adds its defense × (1 − d/250) to the threat (start and abort alike); the "we crush it" supply waiver lasts CRUSH_T of prey running, summed. `chase` abort (trigger 4) bars the runners for GIVEUP_T. Deep desert prey: start only in contact at KILL ×, abort `desert` once the core is there. The first Engage target is the armed enemy nearest the anchor (a powerless member only if none is armed). Group = the prey faction's armies within LOCAL of the anchor; with no prey faction (raider-siege contest, neutral hunt) raiders only. An order in transit (worm, shuttle) isn't re-judged until it lands (≤ RIDE_MAX).

**Fight retreat (`retreat-terrain`):** balance × terrain × supply. `trivial`: off our zone, no Military order, enemy < 10% of us → leave (stranded too). `pursuit`: enemy within 150 lost < 10% in PURSUIT_T, none of ours on a Military order, off our zone → leave. **Retreat target (`safe-heal`):** an ownerless heal structure (allied sietch) is judged for the asking faction like its own; keeps its first heal structure HEAL_COMMIT; on our land a structure on the enemy's side costs + DETOUR²; a contested healing structure costs DETOUR 250 (only an overwhelming threat rules it out); an army at its own healing structure leaves only if hostiles within 80 / 3 s exceed 2 × 1.3 × it. **Disengage:** an army on Resupply still shooting a powerless target is pulled out, unless a mission of ours fights there.

### Raid (goal 5b)

Candidates: vanilla's pillage list with the desiredStatus gate lifted (every at-war owner's villages), minus vanilla's top RAID_KEEP 3 Annex choices, villages behind another faction's main base (seen from our nearest main base B: a base M nearer B with d(B,M) + d(M,v) ≤ 1.25 d(B,v)), bunker villages, villages with our Underworld HQ, uncontested Fremen ring villages, and villages our raid left < RAID_RETRY. Held while the Annexation gauge is ≥ 85, at most RAID_GAUGE_T. Armies: raid-ready (≥ 60% life) within RAID_R 400, not fighting; armies walking home to resupply count. Launch at enter × (armies within LOCAL + turrets + militia + other raiders) / terrain and RAID_FAR × that + free relief within REACT_R; supply budget (arrive with 25%, the pillage refills 50%, then home); **home race**: hostile armies free to strike within (target's distance to our land + HOME_M 100) of our land, i.e. that could reach it before the raiders return, must be held by our armies near home × 1.3 at enter. Aborts (every CHECK, every Pillage order incl. vanilla's; never in Action at ≥ 50%): `defend` (our structure besieged within RECALL_R 500 lacks defenders and the raid can help), `home` (race at abort), `weak` (walking, below the launch test × ABORT / ENTER at the target: ABORT × the local side, ABORT × RAID_FAR / ENTER × all within REACT_R).

### Expansion and target value

- **Spacing / launch gate (`annex-spacing`):** no siege within 100 of one we run; no new one while ours is besieged (`defend`); refusal = `Dismiss` (no gauge decay). A Liberate / Raze / sietch strike (PillageSietch) / renegade-base strike (Dismantle) waits while our Annex is pending and doesn't go when at-war armies that could reach our land before we're back × enter exceed half our army × OWN_T (`exposed`, judged at launch; the pressed village is exempt); `exposed` lasts, so it ends with `Skip` (gauge × 0.85, re-asks in ~30 s) instead of `Dismiss`.
- **Reach:** vanilla lists siege targets within 1 zone of our territory; a faction without Annex distance cost (Smugglers) gets FAR_ZONES 1 more.
- **Annex value** (value per cost): vanilla score + 30 special region + 10 sietch zone, × compactness (1.25 next to our structures → 0.75 from 800; not Smugglers), × 1.3 bunker pair, × cheapest / its Authority cost. Opening: spice villages × 2 while we own none (not Fremen / Vernius, whose vanilla +100 is removed). Best unaffordable → best affordable of the top 3 (`aswap`). **Lone candidate:** past EARLY_VILLAGES 2, a single plain candidate (no ring / special / spice) is dropped (the press target is exempt).
- **Fremen deep desert:** a deep desert becomes Fremen land once every neighbouring village / main-base zone is theirs (hegemony bonus 1). Ring villages score × (1 + Σ chance / (1 + villages still missing)) (cap × 3) + DD_ADD 40 × the best chance; a missing village held by another faction or within 350 of its main base halves the chance; a desert bordered by another faction's main base scores nothing; villages touching only deep desert of ours get half. One ring at a time: the ringable desert fewest zone hops from our main base is the focus, others × DD_FAR 0.5. **Ring first:** with the bonus, while an uncontested close ring (≤ 2 villages missing besides the candidate) has a village as candidate / under Annex, Fremen annex nothing off the ring (pillage it instead); ends when contested or after DD_TRIES 3 launches there. Raid and pillage press never hit an uncontested ring village. The press and the bunker redirect go first.
- **No thinking loops:** a target with FAIL_N 3 orderless launches in FAIL_WIN 120 s while an army was free and the cost payable leaves the list for 120 s doubling to 480 s; `NoAvailableArmy` (vanilla's own idle list empty) and wiped / all busy never count. A launch that ends at once is blocked RETRY 30 s doubling to 240 s. World events: no relaunch on one event within DISC_RELAUNCH.

### Armies, positions, hazards

- **Worn armies:** < 50% life joins no vanilla mission unless already fighting there; worn temporary units (no regeneration) still defend as extras (never counted toward required power; main-base defenses take them). Hunts take ≥ 90%, raids ≥ 60%.
- **Siege position:** a siege army under at-war cover other than the target's (Action within 250, Engage within 80) steps to 25 from the village centre on the far side from the nearest enemy structure, at most every 4 s. **Keep capture:** an army within 60 of a village we besiege / occupy never takes micro's 'defend the flagged structure' role. **Unstick:** a siege army within 30 of the target that hasn't moved 3 in 12 s while nothing is besieged / occupied walks to `getSafePosition`. **Deep desert at a target** (Engage / Action only): a draining siege / raid army steps onto the village's side, 40 from it, and keeps fighting.
- **Discovery (`discovery-gate`):** a lone trip needs enter × the at-war threat at the event / terrain; a running one is cancelled once hostiles reaching it within DISC_HORIZON 40 s outmatch it; the event is skipped DISC_RETRY, `strand` walks the army home.
- **Worms (reaction only):** a worm-targeted army on sand drops its order and walks to the nearest rock (with its order's armies on sand within 150); moved armies wait while a worm is within 150 (≤ 20 s), no re-order back over the sand; a moved harvester marks its zone as danger.
- **Harvester under fire:** escort within 150 weaker than the attackers → run to the nearest safe field (other zone, no danger, no hostiles within 250, free), else home; left alone 20 s by vanilla's re-route.

## 5b. Strategic director (`rules/strat.py`)

Goals 1-2 stay reflexes; the director decides what the **spare** armies do from goal 3 down. Why: vanilla targets an enemy village only at aggressiveness ≥ 50 and desiredStatus ≥ 1 toward its owner, so a faction at war with a weak neighbour never touches its villages and the mid game idles.

**Built** (every scan, posture held ≥ 60 s unless a higher one triggers, `strat` rows): spare force S = free armies (not defending, not resupplying below RAID_LIFE) minus ENTER × `aimod_home` / OWN_T held nearest home. Postures, first match wins:
1. **defend**: our structure besieged.
2. **recover**: worn power (life < RAID_LIFE or short) > 0.5 × total, left below 0.35: no new press; `raid` only raids that are a recovery (village nearer than home for every raid army, RAID_TO). Hunts, vanilla sieges and defense aren't gated.
3. **hold**: no spare force.
4. **press E**: the nearest soft village of an at-war E within FRONT_R 600 (spare armies within 450 have PRESS × hold(v) = `aimod_react` + enemy cover + militia, / terrain; softness falls to enter with contact tension), B(E) ≥ 1. Annex if in supply range, available and affordable (gates lifted, score × PRESS_W, E's other villages dropped), else pillage via `raid`. Keep = our power within PRESS_R + cover ≥ PRESS_KEEP × their side; dropped on done / gone / Devastated / truce / PRESS_MAX (`slow`) / weak, then skipped PRESS_RETRY, our orders on it cancelled.
5. **expand** / **harass**: vanilla Annex; `raid` and hunts.

**Planned** (each verified before the next): utility ranking U = value × swing / time (swing 2 for enemy villages; pillage = loot + their halved production − our doubled Annex cost) across neutral Annex, enemy Annex and pillage, with an expiry of 1.5 × estimated time; home race on every offensive; front patrols (never idle > 60 s with spare armies). Anti-exploit targets: kiting (`chase` / `pursuit`, built), turret baits (cover, built), pull-away (home race), split raids (defend the most value at risk first), predictability (keep vanilla's random top pick), omniscience (§3a).

## 5c. Contact tension (`rules/tension.py`)

Contact points are worth more than their production: whoever holds both has a bunker pair and a safe border. Pair = our village V and the nearest other-owned or neutral village W within TEN_R 140 (main bases excluded). Tension T(V) ∈ [0, 1], updated every TEN_T: + TEN_UP × closeness (1 at ≤ 60 → 0.25 at 140), × TEN_HOT 2 while W's owner's armies stand within COVER_R of V or anyone besieges W; − TEN_DOWN once the pair is gone. T only scales existing thresholds; posture order and supply rules still win; never against a stronger owner (B ≥ 1).
1. **Contest (built):** a siege of W next to V → contest hunt at entry enter → keep as T goes 0 → 1, even while our rally gathers elsewhere.
2. **Take (built):** Annex value × (1 + T) for a neutral W; press softness PRESS → enter for an enemy W. **Gate:** at war and T ≥ TEN_GATE, W's owner is listed for vanilla Annex / Pillage at desiredStatus 0, only W kept; a launch on W creating no order while an army was free halves T (TEN_FAIL).
3. **Truce (design, after 1-2 verified):** no attack on a truce partner by default (a default, not an invariant). Fremen (no Standing: treason is nearly free) may press at T 1 held T_HOLD. Others: T 1 for T_HOLD, `checkDeclareWar` Success, B ≥ 1, W soft → let the target through; vanilla declares war itself on the launch (REVERSING "War declaration"), so no second declaration path. One per faction per long cooldown; logged.

## 6. Code rules

- One concern per module (README "Code structure"); a rule = one function: read the model, decide, issue at most one order, log one event.
- Thresholds are named constants in `rules/common.py` (§4 values where one applies).
- Rules run in the aware scan or a CHECK tick; nothing per game tick; worst case O(armies²) per scan.
- Reuse vanilla entry points (`addOrder`, `tryArmyAction`, `pickUnits`) so its bookkeeping stays consistent.
- Offline check: both boot files patch and re-parse (no bulk decompiles). In game: `HEALTH OK`, then the target metric.

## 7. Checklist for a new rule

1. Which logged failure does it fix; which `mod log` number should change?
2. Which layer and priority?
3. Shared world model only (no private scan)?
4. Enter / keep / abort and triggers; can it flip-flop?
5. Does another rule judge the same situation? Then use the same measure (§1.4), or one of them will contradict the other.
6. Can it loop with another rule or vanilla (hunt → lose → retreat → hunt)? What breaks the loop?
7. Target moves, disappears or runs home?
8. Concentrates force (no trickle)?
9. Log event and reason code?
10. On error or nothing found, does vanilla continue?
