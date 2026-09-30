# AI design policy

Binding for every AI behavior change. Goal: an AI that is **functional, predictable and hard to exploit**, built from a few general mechanisms instead of many special cases. Read before writing a rule; check the rule against the checklist at the end.

## 1. Principles

1. **Evidence first.** Add or change a rule only for a failure seen in a log (`mod log`, L marks) or proven in code. State the failure and the expected log change up front. No speculative features.
2. **Steer vanilla, don't replace it.** Vanilla already has gauges → actions → orders (phases, priorities, fight power checks, retreat). We fix its inputs (threat estimates, targets, force size) and fill gaps (army hunting, contesting). We rewrite a subsystem only when hooking inputs can't express the fix.
3. **One world model, one power metric.** Every decision reads the same per-faction threat picture (§3), with power from `HPowerScore.singlePowerScore(HCombatStats.unitCombatStats)`. No rule scans the world with its own radius or formula.
4. **Plans are commitments.** A decision creates a plan (§4) that holds until one of its declared triggers fires. No re-deciding every tick, and no flip-flopping between two options.
5. **Concentrate force.** Send enough to win with margin, all together. Never trickle armies in one by one. If we can't gather enough, don't go.
6. **Every army has exactly one owner.** An army belongs to one order. Only a higher priority on the ladder (§5) may take it. Rules never issue raw unit commands behind an order's back.
7. **Fail safe.** Injected code runs in traps. If our logic fails or finds nothing, vanilla behavior continues unchanged.
8. **Observable.** Every decision logs one event with its inputs, the choice and a reason code, so `mod log` can show why.
9. **Small complexity budget.** Prefer one general mechanism (e.g. "local power ratio with hysteresis") over N special cases. Delete rules that don't measurably help.

## 2. Decision layers

| Layer | Scope | Cadence | Who decides | Examples |
|---|---|---|---|---|
| Strategic | faction | daily, or on a major event (war declared, main base threatened, >40% army lost) | vanilla gauges + aggressiveness; we tune their inputs | expand vs hold, which neighbor is the war target |
| Operational | army group ↔ one target | aware scan (10 s), acts **only on triggers** | vanilla orders + our rules (`hunt`, contest, abort) | take village X, hunt army Y, retreat to Z |
| Tactical | units in one fight | per tick | vanilla `unitMicroManagement` | focus fire, reposition, flee |

A layer may constrain the one below it, never micromanage it. Operational rules don't touch unit micro; tactical micro doesn't pick targets.

## 3. World model (per faction, refreshed every aware scan)

This is the only input for operational decisions:
- **Hostile groups:** at-war armies clustered by proximity (250). For each group: power, position, heading/moving, visible, on its own territory, supply state, and intent when known (`aiOrder`).
- **Own groups:** position, power, life/supply, owner order, free/busy.
- **Threat at a point:** `threat(p, r)` = at-war army power within r of p (all at-war factions, plus enemy structure defenses when relevant). `strength(p, r)` = own power that can arrive in time.
- **ETA:** distance divided by speed (approximate). "Can arrive before X" beats raw radius.

**Diplomacy:** combat is allowed only at `War` (`State.areAtWar`). Truce (`Peace`), Tribute and Alliance forbid it: fighting breaks the relationship. `Hostility` never fights. So threat = at-war armies only, read **live** on every query. A war declaration or a truce is therefore a trigger for every running plan at the next scan: an attack on a new truce partner is cancelled, and a new enemy's armies count at once. Truce partners are *potential* threats (they can declare war) but count 0 for now. Offensive vs defensive posture: later, from the strategic layer (aggressiveness), e.g. whether hunts may enter enemy home territory.

Implemented queries (tools/rules/world.py, every rule must use them): `aimod_threat(fac, p, r)` (at-war power within r plus moving armies able to arrive within 20 s; speed ≈ 6 units/s, so ≈ 120 units), `aimod_threat_now` (3 s horizon), `aimod_own(fac, p, r, exclude)`, `aimod_terrain(fac, zone)`, `aimod_land(fac, e)` (distance to our land), `aimod_supok` / `aimod_short` (supply budget), `aimod_sieged(fac, s)` (siege by an at-war faction, from the structure), `aimod_cover(fac, e, exclude, own, res)` (turret cover at e, §5a), `aimod_defend(fac)` (our besieged structure). `threat` itself is armies only; rules add `aimod_cover` where structures matter. State between scans: added-global maps (`_global_map`), not saved with the game. Not built: the persisted per-faction snapshot; village militia in hunt threat.

### 3a. Intel: what an AI may know (design, not built)

Today both vanilla (`cacheData.totalArmyPowerScores` in aggressiveness and diplomacy) and our `aimod_threat` read **true** enemy strength, seen or not. Target: decisions use what the faction has seen.
- **Memory per enemy army:** last seen position, power, time (refreshed whenever `isVisibleForFaction`). Seen dying → removed.
- **Position confidence decays:** an unseen army may be anywhere within `last_pos + speed × age` (capped). Local threat counts it only if that circle reaches the query point, and at a weight that falls with age.
- **Strength confidence decays slower:** armies don't vanish. Perceived faction strength = Σ remembered power, with old entries fading toward a floor (e.g. 50% after 5 min, never 0 while the faction lives). Unknown growth is estimated from the enemy's territory size.
- **Result:** `perceived(F)` = perceived total strength of faction F; `threat()` and the balance below use memory, not omniscience. Scouting (ornithopters, contact) gains real value.
- **Storage:** needs state kept between scans (a new global, or a field on an existing per-faction object); not persisted in saves, rebuilt after load (conservative until re-seen).

### 3b. Diplomacy: war goals and who is in charge (design, not built)

Peace, truce and war are strategic plans with the same commitment rules as orders (§4).
- **Balance:** `B(F) = our strength / perceived(F)`. `B ≥ 1.5` = we're in charge; `B ≤ 0.67` = they are; in between = contested.
- **Accepting peace (`tradeRequestReceived` gate):** refuse a peace offer from F while any of these holds:
  1. we have an order against F in Engage/Action with local ratio ≥ `keep` (finish the capture or pillage first; decide on peace after it completes);
  2. we're in charge (`B ≥ 1.5`) and the offer doesn't pay more than what we'd take by force (at least: not while we can still annex or pillage their villages near us).

  Accept when contested or losing, when we have nothing to gain nearby, or when the offer is worth more than continuing.
- **Offering peace:** the weaker side offers when losing (`B ≤ 0.67`) or when a stronger third enemy appears. Offering peace is not a substitute for defending: a faction under attack still defends.
- **Declaring war:** only with a goal (a reachable target and `B ≥ enter` locally), not by mood.
- **Hysteresis:** after a status change, no reversal for a minimum time unless the balance swings strongly (a new trigger), same as §4.

Vanilla today: daily `desiredStatus` (0 peace / 1 war / 2 total war) from `HScoring.diplomaticTarget` (hegemony, CHOAM, AI type, true army totals / distance). Offers a peace pact when at war and status 0 (random chance `valueCache[279]`). Accepts one unless status 2, by trade value only, with no look at running sieges (a winning capture gets cancelled by the peace).

## 4. Plans, triggers, hysteresis

A plan = `{goal, target, armies, ratio_at_commit, keep, abort, expiry}`. In practice that is a vanilla `AIOrder` plus our thresholds.

**Ratios (one scale for all rules):**

| Threshold | Value | Meaning |
|---|---|---|
| `enter` | 1.5 | start an offensive plan only at ≥ this local ratio (ours / all hostile) |
| `keep` | 1.0 | continue while projected ratio ≥ this |
| `abort` | 0.7 | below this, re-decide: an open-field fight 1-2 armies down is kept (operations can swing it) |
| `retreat` | 0.65 | vanilla fight retreat threshold (data `AI_WarzonePowerEstimation_RetreatRatio`, fixed; vanilla re-rolls a range every tick) |
| terrain | ×1.3 own zone, ×0.8 at-war zone | multiplies our ratio before any enter/abort/retreat test: at home we heal and resupply, on their land they do. Attack on their land needs 1.5/0.8 ≈ 1.9×; home defense holds to ≈ 0.5 |
| `flee ETA` | 3 s / contact 80 | an army at its own healing structure (≤ 120) leaves only if hostiles within 80 or 3 s of it overwhelm it (> 2 × 1.3 × ours): last resort |
| hunt gap | 30 s | one hunt start per faction per 30 s (commit; also covers vanilla cancelling a fresh order) |
| detour | 250 | a contested healing structure costs this much extra distance; only an overwhelming threat rules it out |
| `commit` | 30 s | after a switch, no switch back unless a **new** trigger makes things worse |
| supply budget | 0.35 × distance to our land + 10% max supply | supply an army needs to walk home (drain ≈ 0.28/unit, ×1.25 margin). `short` = losing supply and below it: hunts abort (in contact too), and in a fight the balance is × (1 − 0.6 × short share of our power), so a starving army leaves any fight it isn't clearly winning. Joining a hunt needs 1.25 × the budget at the target (hysteresis) |
| our land | structures on zones we own | every "distance to our structures" test; structures inside other factions' zones (UWHeadquarters) don't count |

The gap enter > keep > abort is the hysteresis that stops flip-flopping. Entry and exit must measure the same thing at the same place (hunt: the prey at start, the group's core = the member nearest our land afterwards; never a centroid, which a member walking home drags under its own guns); otherwise a plan can start and abort on consecutive checks. Members more than LOCAL from the core have split off and leave the target group.

**Gathering:** concentrate, but don't idle next to the prey. A hunt waits in Regroup only until the armies already within LOCAL of the core pass `enter` there; then all engage and the stragglers walk straight in (they reinforce a fight already won on paper, which is not trickling).

**Distance and objectives:** when several targets pass `enter`, prefer objectives (a village near our land being besieged by an enemy, read from the village's siege state: weight 3) and nearness: score = weight × threat / (distance of our nearest free army + 100). A plan anchored on an objective ends when the fight drifts away from our land (`drift`), not by chasing. A chase yields to an objective: when its own armies could contest a siege near our land, it aborts (`objective`) and only contests may start for 30 s. Chasing far from our land gains nothing: the supply budget ends it before the way home becomes unaffordable.

**Re-decide only on triggers**, never on a timer alone:
1. A new hostile group gets within threat range of our armies or target, and it can arrive before we finish.
2. The projected ratio crosses `abort`.
3. The target becomes invalid: dead, owner changed, invisible for > N s, or it entered the enemy's home territory (for hunts).
4. We are stuck: no progress for N s.
5. The plan expires.

**On a trigger, choose in this order:**
1. **Continue** if the projected ratio (including the threat's ETA) is still ≥ `keep`.
2. **Reinforce** if free armies can arrive in time and lift the ratio to ≥ `keep`.
3. **Withdraw** to the nearest *safe* point (`safe-heal` logic) if we can get there before contact.
4. **Fight all-in** if withdrawing is impossible (they're faster or closer to our escape path), or the ratio is still ≥ `abort` and the objective is worth it (own structure, nearly done capture).
5. Otherwise withdraw anyway. Losing slowly is worse than retreating late.

Example: marching to capture a village, a large hostile army is spotted heading our way. That is trigger 1. We project the ratio at the village at their ETA, then work down the list: finish if the capture completes first and we still hold ≥ `keep`, pull in reinforcements, fall back, or fight if we're cornered.

## 5. Priority ladder (who may take an army from whom)

| Prio | Orders |
|---|---|
| 10 | defend main base (vanilla) |
| 5 | defense of own structure (vanilla), `hunt`, contest of a siege near us |
| 4 | Raze |
| 3 | Annex (`annex-spacing`: no second siege within 100 of one we run; none at all while one of ours is besieged; bunker villages first; refusal = `Dismiss`, no gauge decay) |
| 1 | Pillage (vanilla gauge, and `raid`), Liberate |
| 0 | Patrol, Resupply, Discovery (vanilla; a lone Discovery trip needs `enter` × the at-war threat at the event / terrain, else refused: `discovery-gate`) |

Rule: new rules pick priorities from this table and add themselves to it. An army in Resupply is never "free", whatever its priority: healing comes first. An army short of supply on neutral or enemy land starts nothing new and leaves fights it isn't clearly winning (supply budget, §4).

## 5a. Faction goals, in order (strategic posture)

What a faction's armies are for, highest first. A lower goal starts only when every higher one is satisfied or impossible; a running lower plan yields when a higher one appears (except a fight it is about to win in contact).

| # | Goal | Means (built) | Posture while active |
|---|---|---|---|
| 1 | **Survive / supply**: armies never starve on neutral or enemy land | supply budget: hunt `supply` abort, fight retreat × supply factor | a short army starts nothing and walks home |
| 2 | **Defend what we own**: one of our villages or main bases besieged by an at-war faction (`aimod_defend`, read from the structure) | contest hunt on it, all free armies within 900 join (vanilla Regroup gathers them), entry 1.5 / terrain 1.3 ≈ 1.15 | **defensive**: every new vanilla siege launch refused (`space` why `defend`), no chase starts, running chases abort (`defend`). Only exception: prey in contact (≤ 150) of our free army and we have ≥ 3 × its threat (kill it on the way). If we can't reach 1.15 yet: stay home and gather (spawns add up), never trickle in |
| 3 | **Bunker**: villages whose turrets cover each other (≤ 130 apart) or that sit under our main base's guns (≤ 200) | a lost/untaken village under our main base: vanilla Annex is redirected to it (`bunker`, bypasses the aggressiveness gate); a village forming a pair with one of ours: target score × 1.3 (Annex, Liberate, ...) | – |
| 4 | **Stop captures next to us**: enemy siege of a neutral village ≤ 500 from our land | contest hunt (weight 3); a running chase yields (`objective`) | – |
| 5 | **Opportunity**: exposed enemy army near our land | chase hunt, on our side of the map only (≤ 500 from our land, ≤ 300 if it's on its own land), supply budget | – |
| 5b | **Raid**: an at-war village next to our armies, weakly held | `raid`: pillage with every raid-ready army within 250 when they have `enter` × (armies + turrets + militia there) / terrain and the raid supply budget (arrive with 25%, the pillage refills 50%, then the way home). Armies on their way home to resupply count as available: the refill beats the walk | – |
| 6 | **Expand**: vanilla Annex / Pillage / Raze gauges | vanilla, spaced (`annex-spacing`); sizing counts every at-war army near the target (`aimod_threat` measure, LOCAL), not only the owner's: a neutral village next to a rival's blob needs force against the blob | – |

**Turret awareness (every goal).** Turrets (buildings with power, e.g. MissileBattery 40, range 80) and main base guns (power 80, range 80) cover COVER_R = 130 around their structure. Vanilla ignored every turret but the target's own and its owner's main base, and counted the target's own turret although it stops while the village is annexed or pillaged. Rules:
- a village under siege has silent turrets (its own attacker's view and the defender's view);
- attack sizing (vanilla `pickUnits`, live order balance) adds the turrets of every other at-war structure covering the target, and drops the target's own; defense sizing drops our besieged village's turrets and adds our covering neighbours'. Vanilla's formula (Σ offense × Σ HP) makes turrets feared in proportion to the armies they support: more, not overwhelmingly;
- hunts count cover as threat (turret offense × one army's HP ≈ one army per turret, two per main base) and our own cover as power. A chase under enemy cover is allowed only in contact (≤ 150) with ≥ 3 × (threat + cover): kill it, take a few shots, leave; it aborts (`turret`) otherwise. Attacking a main base itself is a separate future plan that needs overwhelming force.

## 6. Code rules

- One concern per module: `aware.py` (world model + log), `rules/world.py` (shared queries), one `rules/` module per rule group, `behave.py` (wiring). Each rule is one function: read the model, decide, issue at most one order, log one event with a reason.
- All thresholds are named constants at the top of the module, from §4 where one applies. Move them to data (`constant` rows) once stable.
- Throttle: rules run in the aware scan (10 s per faction). Worst case O(armies²) per scan; nothing per tick.
- Reuse vanilla entry points (`addOrder`, `tryArmyAction`, `pickUnits`) so vanilla bookkeeping (reservations, phases, cancel) stays consistent.
- Offline check after every change: both boot files patch and re-parse, and a decompile of the new functions reads right. In game: `HEALTH OK`, then the targeted log metric.

## 7. Checklist for a new rule

1. Which logged failure does it fix, and which `mod log` number should change?
2. Which layer is it, and which priority?
3. Does it read the shared world model (no private scan)?
4. What are its enter / keep / abort values and triggers? Can it flip-flop with itself?
5. Can it loop with another rule or with vanilla (e.g. hunt → lose → retreat → hunt again)? What breaks the loop?
6. What happens if the target moves, disappears or runs home?
7. Does it concentrate force (no trickle)?
8. What does it log, and with which reason code?
9. If it throws or finds nothing, does vanilla behavior continue?
