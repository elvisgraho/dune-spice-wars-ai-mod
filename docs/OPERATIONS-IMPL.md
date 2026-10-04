# Operations takeover: implementation plan

How to build [OPERATIONS-PLAN.md](OPERATIONS-PLAN.md): hooks, new rule files, maps, log rows and the per-stage match checks. Stage 0 (fog of war) applies to every AI rule, not only operations, and comes first.

**Status:** Stage 0 (fog of war, `rules/intel.py`), 2 (`rules/ops.py` block / strip, `opsbuy`) and 4 (`rules/opsbrain.py`: triggers 1-5, Cell Search slot) are built; Stage 1 logs `opveto` / `opvan` / `opcast` / `ophold` / `opbuy` (no separate vanilla baseline: vanilla is blocked in the same build); Stage 3's helpers live in `opsbrain.Ops` (sdrop keeps its own cast); added after the plan: agent steer (loadout infiltrations first, then Counter-Intel), the Cease Fire candidate restore (vanilla's filter drops it whenever we are at war), fight ops gated by our retreat balance, `opfz` / `opcf` / opfail reason diagnostics. In-game confirmed (matches 2026-10-04): every loadout op cast at least once except Extraction Network (held, its trigger never met); Cease Fire cancelled two Fremen captures of Yaras. Stages 5-7 are open. Current behaviour: AI-POLICY "Operations" and §3a.

`f@` ids are hlboot; resolve every function by name (the ids differ in hlbootdx). Each stage is one loop: build → `bcheck` → 17-minute match → `mod log` → adversarial pass → progress.md.

## Code facts used here

| What | Where |
|---|---|
| Vanilla launch, held ops | `Spying.checkOperations` f@8605 → `tryLaunchOperation` f@8609 (one call site, wrapped by `sdrop-block`) |
| Vanilla launch, order lists | `tryLaunchOperationFromOrder` f@8611 ← `AIMilitary.getActionMandatoryMissions` f@8406 / `getActionOptionalMissions` f@8407, given to `addOrder` in `tryArmyAction` (wrapped by `ops-gate`) |
| Plain-ops path | `tryDefaultLaunchOperation` f@8610: Marauders Raid only |
| Buying | `Spying.checkMissions` f@8603: candidates `getAllPossibleMissions` f@8608 (filter f@41070); Intel ≥ max candidate Intel cost; `$HScoring.spyingMissions` scores (one call site, wrapped by `sdrop-buy`); `pickMapWeight(scores, [1018][difficulty])`, Insane 1 = best |
| Slots / expiry | `MissionManager.getOperationNbSlots` f@11959 (3 + attr 1297, max 5); `Spying.regularUpdate` f@8600 cancels and refunds ops held 15 days (`[1162]`); buy cooldown 5 days per id (`[1163]`) |
| Held ops | `ent.Faction.get_missionManager().getCompleteMissions(null)`, `Mission.id`, `hasBeenUsed`; `getStartedMissions` |
| Cast | `f.get_abilities()`: `canUseAbilityOn(id, args, null, null)` → `useAbilityOn(...)`, result enum `Success`; ability id = `mission.getAbility().id`; `args = {src: DisplayTarget.Spying(f), zone}` or `{src, struct}` (+ `ignoreReconned: true` for an unreconned main base). `HAbility.initDefaultArgs` f@22441 fills zone / faction from struct |
| Cast refusals | `$HAbility.noUseReasonOn`: need 0 needs a discovered zone; 3 a reconned village; 4 an active, reconned main base; then alignment / War-Hostility. `AbilityManager.noUseReasonOn` f@7118: `BlockedBy` on `Operation_Block` 75. Per ability: Extraction needs a village in the zone, WormCalling / HiddenThumpers worm activity > 0, CrowdManipulation `checkStartRebellion`, InterdictionZone an Airfield or Refinery |
| Zone effects | `zone.get_traits().has / getAll` (`logic.Application`: id, faction, startTime, style ETemporary(d)); end = `TraitsManager.getAppEndTime`. Caster and time left, reliably: each faction's `get_abilities().ongoingAbilities` (`logic.faction.ActiveAbility`: kind, src Spying(f), target, launchTime, duration; filter as `$HSpying.countOngoingOperationOnZone` f@23384). Attributes: `NoFight` 626, `Operation_Block` 75, `Zone_NoSandworm` 1641 via `hasAttribute(id, null, owner)` |
| Fights | `State.warzones.warzones.array` (sweep.py reads it): `Warzone.isInvolved`, `getFactionArmies`, `getEnemyArmies`, `getMainOpponent`, `get_centroid`; `$HAI.getWarzonePowerBalance` f@22345 |
| Captures | `structure.siege` (SiegeComponent): `occupationAction.progress` 0..1, `occupier` EFaction(f) / ERaid, `contested`, `occupiersInRange` |
| Cease Fire cancel | `checkOrderTerminations`' closure (f40838) calls `canBeAttacked` (false under NoFight) → order cancel |
| Extraction | trait `TExtractionNetwork` on the village: attr 1403, radius 29; filter f@25757 (owner = caster, not militia / flying / transported) → `TExtraction` (hidden 10 s) → f@25758 `cancelAction` + teleport to `mainBase.getSafePosition()`; AIOrder untouched |
| Worm warning | `Sandworm.updateFactionsSpotting` f@9028 (`spotted[player]`); WormSign within 40 + 25 of a spotted worm; `targetEntity` f@9030 sets `targettedByWorm` |
| Visibility | `ent.Entity.isVisibleForFaction(f)` f@2791 (model: owner / team / `teamVisibleCells`; gameplay: cloaked enemies need `isDetected`); structures `isReconnedFaction(f)` f@4713; `Faction.isPointVisible` f@3478; espionage `Faction.canSeeInformation(kind, f)` f@3473 (`CumulatedUnitsPower`, `NbArmies`, `ArmiesDirection`, `UnitSupply`); `Faction.applyVisibility` f@3479 marks every cell visible for every faction when `PREFS.admin.noFog` |

## Stage 0: fog of war (every AI rule)

**Finding:** our rules read true positions and power of every army.
- Only the hunt starts (hunt.py:731, :959) and the strike start (strike.py:245) test visibility.
- The shared `build_threat` loop (world.py:73-87), which feeds threat, react, hsafe, threat_now, hthreat, threat_stats, threat_far and threat_arrive, has no test.
- No test either in `aimod_neutral`, `aimod_home`, `aimod_cover`, `aimod_militia`, `_renegades_at`, `aimod_sieged` (other factions' villages), `aimod_fpow` (whole-faction power), `_approaching` (enemy path ends), or the local loops in heal.py:214, rally.py:213, deploy.py:69, hunt.py:1017/1040 and strike.py:165.
- The testbed's `noFog: true` gives every AI full vision, so even vanilla's few checks pass.
- Vanilla's own AI (target scoring, `getEnemyCombatStats`, micro) never checks visibility. It stays as it is: out of scope.

**0a. Memory first, then the filter.** A plain visibility filter makes a threat vanish the moment it leaves vision (suicidal raids, early heals). So:
- New `rules/intel.py`, tick at the front of the chain (with `memory`), every 2 s per AI faction:
  - Every at-war or raider army visible to the faction is written to map `seen_<fac>`: army → {t, x, y, pw, vx, vy}. The velocity comes from the last two sightings, our own observation, not `getCurrentPathEnd`.
  - Entries older than SEEN_T (60 s) or of dead armies are dropped; `sweep` handles dead keys.
- Helper `_known(fb, b, cx, x, fac, no)` (common.py): visible now → live values; else a fresh `seen` entry → last position, with power × SEEN_DECAY (1.0 until 30 s, then linear down to 0.5 at SEEN_T); else jump to `no`.

**0b. Shared choke points** (covers ~80% of rules at once):
- `build_threat` loop: `_known` after the at-war / raider test. Position and power come from it, and so does the heading in `_approaching`: observed velocity for an unseen army, the path end only while visible and `canSeeInformation(ArmiesDirection)`.
- `aimod_neutral`, `aimod_home`, `_renegades_at`: the same `_known` test.
- `aimod_cover` / `aimod_militia` / `aimod_sieged` for structures not ours: `isReconnedFaction(s, fac)`; garrison and siege state only while the village's cell is visible (`isPointVisible`), else the last reading (map `sseen` s → {t, values}).
- `aimod_fpow(F)` for another faction: `canSeeInformation("CumulatedUnitsPower", F)` → true value; else Σ of `seen_<fac>` entries of F's armies.

**0c. Local loops:** heal pursuit, rally standoff, deploy `aimod_air`, hunt group build and abort, strike re-judge. Each gets `_known` (or plain `isVisibleForFaction` where a live position is needed: a strike target that went invisible ends as `lost`).

**0d. Testbed:**
- `scenario.json` `noFog: false` (the AI then sees only what it should).
- The `K` macro toggles the AI's fog as well, so don't press it in test matches. Document in TESTBED.
- `aw` rows already carry the V flag; add `kn` (known through memory) so `mod log` can show decisions taken on remembered armies.

**Check:**
- Unchanged health.
- `hunt` / `raid` / `rally` row counts within noise of the 4-loop average.
- A fog-on match where `mod log` shows no decision with an unseen and unremembered enemy: a debug field `vis` on threat-driven rows during this stage.

**Risks:**
- Cloaked Fremen now ambush us as they ambush a player: expected.
- Fewer contest hunts on far enemies: expected; Intel memory (AI-POLICY §3a) is this stage.
- Policy text: AI-POLICY §3a becomes current state, and README gets a key fact.

## Stage 1: logging baseline (no behaviour change)

- **`opveto`:** the `sdrop-block` wrapper logs every vanilla `tryLaunchOperation` call that would run (mission id, f), throttled 60 s per (f, id). Then a second wrapper around `tryLaunchOperationFromOrder` (all call sites) logs id + order target + result. This shows what vanilla does and how often it succeeds; the trace said ~104 / ~109 calls a minute, always False, so vanilla may hardly cast at all.
- **`opcast`:** wrap the `useAbilityOn` call sites inside f@8609 / f@8611. Log f, op, zone / struct (+ owner), result, path (vanilla / order). Our own casts log in the cast helper (Stage 3).
- **`ophold`** (in the existing daily snapshot): per faction, held ids, started ids, Intel, Solari.
- **`opseen`:** every 10 s, zones with an op trait (from every faction's `ongoingAbilities`: caster, kind, target, time left).
- **`aireport` "Operations":** casts per faction × op, held time before use, refunds (expired), enemy ops met per zone.

**Check:** a 17-minute match gives the vanilla baseline: casts per faction per hour and which ops. Recorded in progress.md.

## Stage 2: takeover

- **H1, launch block** (rules/ops.py; replaces `sdrop-block`):
  - The wrapper returns false for every mission id outside OPS_VANILLA {CellSearch, InfiltrationCells, Assassination, MMaraudersRaid, prefix CB_}.
  - `tryLaunchOperationFromOrder` is wrapped too, returning false for the same set.
- **H2, order lists** (`ops-gate` → `ops-strip`): the addOrder wrapper in `tryArmyAction` empties both reg 7 (mandatory: Raze → Defense Breaches) and reg 8 (optional) for every target, not only ownerless ones. `opgate` keeps logging what was dropped, for the baseline.
- **H3, buying** (new rules/opsbuy.py; `sdrop-buy` folds in):
  - **H3a:** wrap the `getAllPossibleMissions` call in checkMissions: the candidate list is filtered to the faction's current loadout wants (wanted − started − held > 0), plus OPS_VANILLA ids. This also fixes the Intel bar, which vanilla takes as the max cost over the candidates: an unwanted 500-intel op no longer holds back a 100-intel buy.
  - **H3b:** in the `spyingMissions` wrapper, the score per wanted op = its loadout rank weight (OPS_W1 100 / 60 / 30). The Supply Drop rule from `sdrop-buy` is kept: no second unlocked drop.
  - **Wants, recomputed per call** from the faction kind and state:
    - wars (`areAtWar` with Atreides / Harkonnen / Fremen for Comm Jamming);
    - enemy mech share (Σ `seen` power of mech armies / all);
    - Solari ≥ OPS_RICH for the 500/500 ops;
    - a sietch or renegade base within the raid reach for Scavenger Team;
    - peace with all for Arrakis Diplomacy.
  - **Reserve:** a 500/500 want needs Solari ≥ 500 + OPS_RESERVE.
  - The 3 slots count the Supply Drop; the loadout table orders the wants.
- **Check:**
  - `opcast path=vanilla` is 0 for managed ids, and `opveto` rows appear instead.
  - Every `ophold` set is a subset of the loadout table.
  - CellSearch still answers an assassination.

## Stage 3: cast engine (rules/opsc.py, shared helpers)

- **`_op_held(fb, b, cx, fac, mid, no)` → Mission:** a complete, unused mission with that id, else jump. One `getCompleteMissions` read per faction per tick is cached in map `oph` (fac → array), reset each tick.
- **`_op_cast(fb, b, cx, helpers, fac, mission, zone=None, struct=None, why, fail)`:**
  - Generalises sdrop's `cast_drop`: `{src: Spying(fac), zone | struct}` → `canUseAbilityOn` → `useAbilityOn` → Success.
  - On success: map `opz_<abid>` zone → expiry (t + 90 s), and the log row `opcast` {f, op, z, s, why, B, extra}.
  - On a refusal: `opfail` {f, op, z, reason enum index}; the (op, zone) pair is blocked OPS_FAIL_T 30 s (map `opfb`).
  - The ability id comes from `Mission.getAbility().id`, not a hard-coded string.
- **`_zone_op(fb, b, cx, z, abid, yes)`:** any faction's ongoing ability `abid` targets z (or a structure in z), via the `ongoingAbilities` scan. Also gives the caster and time left (registers out). The scan is built once per tick into map `zops` zone → array of {kind, f, end} from all factions; read by the brain and the reactions.
- **`_jammed(z)`:** `hasAttribute(75)`. **`_ceasefire(z)`:** `hasAttribute(626)`.
- **`sdrop`** moves onto `_op_cast`, with its behaviour unchanged (bhash-identical apart from the call).

## Stage 4: the brain (rules/opsbrain.py)

**Tick:**
- In the chain after `rally` (it sees this tick's orders, hunts and rallies), every OPS_CHECK 2 s per AI faction (`isAI`).
- It exits early when nothing is held.
- At most one cast per faction per tick, except a combo pair (Sleeper + Drugs, Scavenger + Drugs) cast together.

**Shared inputs, built once per tick per faction:**
- **`fights`:** warzones where `isInvolved(fac)` and the main opponent is an at-war faction (not militia or raid). For each:
  - zone, our armies and power, their visible power (`_known`), B, total power;
  - their non-temporary infantry share, their mech share, our mech share;
  - our order on it (`_order_of`).
- **`sieges`:** our Military orders on structures: target, kind (`siegeAction`), phase, target owner and kind (village / sietch / renegade base / main base), `occupationAction.progress`, the turret cover share (`aimod_cover` vs order power).
- **`besieged`:** our villages with `siege.occupier` = EFaction(enemy), progress, their visible power at the village, our reachable power (rally's reading: `aimod_free` + `aimod_react`).

**Triggers in priority order** (first that fires wins):

| # | Trigger | Op | Condition source |
|---|---|---|---|
| 1 | Extraction | Smugglers' Extraction Network | `sieges` / `besieged` entry at a village with B < OPS_EXTRACT_B and ≥ 25% lost since Engage (map `aeng` order → power at Engage) or visible arriving power ≥ 1.5 × ours (`aimod_react`), walk home > 2 zones or over sand (`aimod_land`, `isSandAt` on the line) |
| 2 | Hopeless defence | Atreides' Cease Fire; Corrino's Orbital Strike | `besieged`: progress < 0.75 (Orbital 0.2-0.7), reachable < 0.9 (Orbital 0.6) × theirs, for Orbital our units' power at the village < 25% of theirs |
| 3 | Worm escort | Decoy Thumper | our armies on sand (`isSandAt`) on a march / siege walk; a visible spotted worm (`Sandworm.spotted[fac]`) within 65 of any of them, or `targettedByWorm`; worm-flee's land point further than the worm's distance; neighbour zone pick as in the design |
| 4 | Combat combo | Harkonnen Sleeper + Drugs; Fremen Hiding Tracks; EMP; Consolidation; Elacca; Backdoor | `fights` entry: big, window and shares as in the design |
| 5 | Siege support | Defense Sabotage; Interdiction; Awaken the People; Toxic Vapors | `sieges` at Engage / Regroup with the design's conditions |
| 6 | Money | Scavenger Team (+ Harkonnen Drugs) | `sieges` Pillage of a sietch / renegade base in Action; or a big `fights` entry at B ≥ 0.8 |
| 7 | Smugglers jam | Communication Jamming | value − cost ≥ OPS_JAM_MIN; value from `zops` (enemy ops) on our siege target / fight zones; cost from our `opz_*` and `sdlk` there |
| 8 | Supply denial | Poison the Reserves | visible hostile armies in a zone not theirs, losing supply (`Army.isLosingSupply` *to resolve*), where we have a fight or a besieged village |
| 9 | Deny thumper | Decoy Thumper | `seen` hostile groups on sand: heading from observed velocity toward our village, depth test, none of our units in the zone |

**Never cast:**
- into a jammed zone;
- the same op on a zone where ours still runs (`opz_*`);
- an op that hits us harder than them: Orbital or Elacca with our units in the area, EMP with our mech share ≥ 40%.

**After an Extraction:**
- Cancel our order there (`cancel(order, Abort)`, like `release`), and tag its armies `rel@` so `odead` / `slost` don't count them as dead.
- Move our armies in the zone but outside 29 of the village to the village position (`doAction Move`).
- `ablk[village]` = t + 90 s, so no order of ours walks in.

**Combos:** both ops cast in the same tick: Sleeper first, so deaths from the Drugs fight count.

## Stage 5: reactions (rules/opsreact.py)

- **Cease Fire on our siege target:**
  - Wrap the `canBeAttacked` call in checkOrderTerminations' closure (found by its NoFight-false path next to the besieger test that `siege-keep` uses).
  - For our Military order whose target is under NoFight: return true (keep the order) when either:
    - progress ≥ OPS_CF_WAIT (0.4), every order army's supply lasts the remaining time (`supok` with the Cease Fire's time left), and no visible relief ≥ our power is within REACT_R; or
    - we are Smugglers holding Jamming (then rule 7 casts it on that zone this tick, value = the Cease Fire × progress).
  - While waiting, the occupiers stay in range: `spos` already holds siege positions; the gauge pauses instead of decaying.
  - Otherwise vanilla's cancel goes ahead, and the target gets `ablk` until the effect ends + 10 s, so it isn't re-picked into a pause.
  - Log `cfwait` / `cfpivot` / `cfjam`.
- **Our rally under our own Cease Fire:** rally.py's hopeless line skips a village under our NoFight. It keeps gathering for the effect's duration, since the time is bought.
- **Orbital Strike / Toxic Vapors on our armies' zone:**
  - Our armies there with no capture ≥ 0.8 move to the nearest neighbour zone point without the effect, the same Move as `worm-flee`.
  - Log `opflee`.
- **Sleeper on our fight:** heal.py retreat balance − OPS_SLEEPER_K while the enemy's Sleeper runs on that zone (`zops`).
- **Jammed zones:** the brain skips them (`_jammed`). `sdrop`'s lock waits (it already re-checks the cast result).

## Stage 6: DLC factions, Probe Setup

- **Scenario variants:** swap one faction for Corrino, Ecaz or Vernius per loop (`testbed/scenario.json` factions; armies for that faction).
- **Probe Setup:**
  - A data patch lifts `aiProhibited` on `MProbeSetup` (`patches/data.json`) so the buy filter can want it.
  - It is wanted vs Fremen at war, and cast when our fight zone shows enemy Fremen armies remembered (`seen`) but not visible now.

## Stage 7: base-kill hook

- **Map `bkill`:** fac → base, t, set by the future main-base rule.
- **Wants:** H3 adds Defense Breaches, Defense Sabotage and Administrative Burden while it is set.
- **Casts:** Administrative Burden with `args.struct` = the base (need 4, `ignoreReconned` if needed) at intent + OPS_BK_AB. Defense Sabotage (zone of the base) and Breaches (struct) when our siege order on the base reaches Engage.
- **Hold:** the launch gate (siege.py) holds a base siege up to OPS_BK_HOLD while one of them is started and ≤ 1 day from done.

## New state, constants, log rows

- **Maps:**
  - Intel: `seen_<fac>`, `sseen`.
  - Caching: `oph`, `zops`.
  - Casts: `opz_<abid>`, `opfb`.
  - Orders: `aeng`, `bkill`. Reuses `ablk`, `slost`, `sdlk`, `sdz`.
  - `sweep` gets every new map (dead armies, ended orders, expired times).
- **Constants** (common.py): SEEN_T 60, SEEN_DECAY 0.5, OPS_CHECK 2, OPS_BIGFIGHT (from the Stage 1 baseline: median fight total), OPS_RICH 1500, OPS_RESERVE 300, OPS_W1/W2/W3 100/60/30, OPS_EXTRACT_B 0.45, OPS_CF_WAIT 0.4, OPS_JAM_MIN, OPS_THUMP_PW, OPS_THUMP_DEPTH, OPS_FAIL_T 30, OPS_SLEEPER_K 0.1, OPS_BK_HOLD 30, OPS_BK_AB 30.
- **Log rows:** `opveto`, `opcast`, `opfail`, `ophold`, `opseen`, `opbuy` (wants and what was bought), `cfwait` / `cfpivot` / `cfjam`, `opflee`, and the existing `opgate`. `aireport` "Operations" summarises them. TESTBED's reading list gets one line.
- **Docs per stage:** README rules list, AI-POLICY (an "Operations" section replacing the ops-gate paragraph), REVERSING (the facts table above, moved there once used), progress.md.

## Per-stage pass checks

| Stage | Pass in `mod log` |
|---|---|
| 0 | fog-on match, `HEALTH OK`; no `vis=0` decision rows without memory; hunts / raids / rallies within noise |
| 1 | Operations section lists vanilla's casts (or shows it hardly casts); baseline in progress.md |
| 2 | 0 vanilla casts of managed ids; holds ⊆ loadouts; CellSearch intact |
| 3 | Supply Drop rows unchanged in kind and rate; `opfail` reasons readable |
| 4 | every cast has a trigger row; no op on a plain village; Harkonnen combos in fights ≥ OPS_BIGFIGHT; Scavenger on sietch / renegade pillages; Extraction followed by an order cancel and teleported armies |
| 5 | each seen Cease Fire on our target ends in `cfwait` (capture resumes after it), `cfjam` or `cfpivot` (target blocked, no re-pick into the pause); armies leave Orbital / Toxic zones |
| 6-7 | per-faction rows as in 4 |

## Risks and open checks

- **Order cancel on Cease Fire:**
  - Confirm the `canBeAttacked` call in f40838 is the path that cancels; there may be a second one in `checkActionOrder`.
  - `siege-keep` wraps a neighbouring call there: build order and bhash checks matter.
- **Extraction:** does vanilla re-path the cancelled-action army back to its order? We cancel the order, so it shouldn't.
- **`Army.isLosingSupply`** (or the attribute behind `Army_LosingSupply_GainTTrait`): resolve the name for Poison.
- **Fog stage scope:** largest behaviour change since the rules began. If the fog-on match drops a key metric (captures, defence success), fix the gap (usually missing memory) before the ops stages.
- **Vanilla stays omniscient** in its own targeting and micro. Wrapping that is a separate project.
