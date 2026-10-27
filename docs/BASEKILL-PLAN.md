# Base-kill plan: containing a leader, up to killing its main base

Threat detection, coalition checks and the assault campaign are implemented. The current assault uses each
member's direct raze commands; a successful base kill remains unverified. Current rules:
[AI-POLICY.md](AI-POLICY.md). Validation and next checks: [progress.md](../progress.md).
This document retains the design constraints and mechanics behind those rules.

## 1. What players do (user)

- **Partner up out of necessity.** When someone approaches a win condition, the others truce each other and go for
  that player's base. Triggers, usually late game (someone above ~20k hegemony):
  - CHOAM: one faction above ~38% while nobody else is close and it has Solari stacked to buy more. If several hold a
    lot of CHOAM, reaching 50% is not a threat.
  - Governor: someone is elected Dune governor: everybody scrambles to shut it down.
  - Hegemony: someone is very high and producing it fast ("cooking").
- **Crabs in a bucket.** Several factions can approach win conditions at once; whoever is the bigger threat right
  now gets pulled down, and the ranking changes.
- **Check before kill.** While someone clearly leads, the others often liberate a few of its villages to keep it in
  check or stop its expansion; a base kill isn't always the move, because power on the map can flip during sieges.
- **Commitment.** Once a base attack starts, players usually finish what they started (one threat less); after a
  wipe they regroup and come back. But everyone also looks out for themselves and can get ahead while the others
  are busy: if the kill will take long and someone else is now clearly ahead, the truce with that one breaks and the
  coalition turns on it. If the kill is within reach, they finish it first. No flip-flopping.

## 2. Threat model (one number per faction, shared by every AI)

Every AI computes the same picture from public state (hegemony, CHOAM shares, Governor), so the coalition agrees on
the target without messaging. Fog doesn't apply: these are UI-visible numbers.

- **Win ETA per condition**, in game days (ETA_x = days until F would win by x at its recent pace):
  - Hegemony: (H_WIN - h) / max(rate, eps), rate = hegemony gained over the last RATE_WIN days (spice taxes are
    step jumps: a window smooths them), capped at ETA_MAX.
  - CHOAM: share s(F); threat only if s >= CHOAM_MIN (0.38) and no other faction >= CHOAM_RIVAL (0.30); ETA from
    the buy pace and Solari banked (Solari / share price = shares it could buy now: an immediate path to 50% means
    ETA ~ 0).
  - Governor: elected and the governor countdown running: ETA = days left on it.
- **Threat T(F) = 1 / min(ETA_x)**, gated: nobody is a threat before LATE_HEG (20k) on anyone's hegemony, a
  Governor countdown, or a CHOAM share >= CHOAM_MIN.
- **Leader L** = argmax T over all factions (the human included). **Relative**: L must lead the next threat by
  LEAD_RATIO (e.g. ETA 30% shorter) for LEAD_CONFIRM days before the coalition forms (crabs in a bucket: two close
  threats keep fighting each other; nobody partners up on a coin flip).
- **Self-interest**: an AI whose own ETA is close to L's (within SELF_RACE) races instead of joining: it keeps its
  war on L but spends nothing on the coalition beyond checks. An AI that *is* L does O4: defend, close out.

## 3. Response ladder (proportional, reversible first)

| Level | When | What |
|---|---|---|
| 0 none | no qualified leader | normal play (strat director) |
| 1 check | L qualified | war on L (desiredStatus up, peace offers from L refused); press / liberate L's border villages first (strat press targets L, DMZ liberate-first), hunts on L's armies near us; truce offers to the other coalition members accepted / sent |
| 2 assault | L's ETA short (< ASSAULT_ETA) or L's base reachable and killable (coalition power within reach >= KILL x (L's army near home + base guns)), and the kill ETA (gather + walk + base HP / our damage rate) < L's win ETA | gather near L's base (rally-style staging point out of turret range), Siege mode (doctrine: Siege mix, Siege gear), base ops (Defense Sabotage / Breaches, Supply Drop), Raze / main-base attack order; the claim registry holds assault armies above sieges / hunts |
| 3 regroup | the assault force wiped / below RETREAT ratio | fall back to the staging point, heal, recruit (doctrine Siege column), re-assault when the force passes KILL again; L stays the target |

Levels 1-2 also cover O5: a leader killing a third faction's base makes that siege our contest target.

## 4. Commitment and switching (no flip-flop)

- The plan keeps its target L until: L's base is destroyed (done); L is no longer the leader by SWITCH_GAP (another
  faction's ETA is shorter by a large margin) **and** the kill isn't close (base above KILL_CLOSE health, or our
  force can't finish within KILL_SOON days); we can't recover a force within REGROUP_MAX after a wipe; or our own
  structures are besieged (the defend reflex always outranks).
- Hysteresis everywhere: entering a level needs its condition for N checks; leaving needs the condition clearly
  gone (lower thresholds) or the timeouts above. A level change is logged with its reason.
- Minimum commitment: once an assault starts, at least COMMIT_MIN days unless the base dies or we're besieged.
- Switching target means: war on the new leader, truce offers to the old one (they're no longer the threat),
  Siege mode stays if the new target's base is the plan, else back to check.

## 5. Integration (existing pieces it drives, not new parallel rules)

- strat director: a new posture `assault` (above press), its target L's main base; press picks L's villages at
  level 1 (the press target filter gets an owner preference).
- Diplomacy: peace gate refuses L's offers; truce offers to coalition partners; war on L (rules/peace.py, dmz.py).
- Doctrine (rules/doctrine.py): `dsiege` set while the assault runs (Siege mix / gear, e.g. Corrino Pyre flamers).
- Forecast + claims (step 1 / 2): the assault force is sized by the forecast at L's base (base guns are cover),
  claimed above sieges / hunts / Discovery.
- Operations (docs/OPERATIONS-PLAN.md): Defense Sabotage / Defense Breaches on L's base as the assault arrives.
- Research: Siege Incentives (+50% vs main bases) when the plan reaches level 2.

## 6. Logs and scorecard

`bkill` rows: level changes (f, lvl, tgt, why, eta_l, eta_next, kill_eta), the threat table every THREAT_LOG s
(per faction: h, rate, choam, gov, eta), assault progress (base health, our force, their defense). Scorecard: time
at each level, target switches, base kills done / abandoned.

## 7. Mechanics (hlboot identities)

User: vanilla never attacks a base over win conditions. Confirmed in effect: vanilla's diplomatic target
(`$HScoring.diplomaticTarget` 41301, closure f41304) scores a faction +inf (Total War) past 0.7 x 30000 hegemony or 40%
CHOAM (Insane), and adds best victory advancement x 9, so desiredStatus reaches 1 toward a leader; but the Raze gauge
(`AIMilitary.increaseGauges` 8382) grows only when the target's main base is in supply range and its zone within 2 of
our territory, and for non-Military AI types only at desiredStatus 2 (set by data effects only): practically never.
Its Governor clause divides remaining seconds by 30 days (fires only on the last day: likely a vanilla bug).

- **Base death:** main bases have 40000 health (Corrino ImpBase 30000; Corrino holds up to 2 bases), armor 10, power
  80 / range 80, area damage ignoring half armor, cloak detection, no militia. Damage kills them
  (`Entity.set_life` 2995 -> die); the Raze occupation (siegeAction Raze, aiPrio 4, needs life 0) is a fallback.
  `Structure.die` 4737 -> `Faction.loseMainBase`; the last base -> `State.losePlayer(Destroyed)` (eliminated).
- **Vanilla attack path:** `tryRaze` 8389 -> `tryAction("Raze", getDefaultStructureArgs("Raze"))` (mainBasesOnly) ->
  getSiegeableVillages (getTargetStatus gate, supply range) -> HScoring.structures -> a Military order, prio 4,
  mandatory op MDefenseSabotage, optional MGearSabotage / MCommunicationJamming; militaryGauge Raze onFailure blocks
  Pillage / Liberation 3 days and Raze 6 days.
- **Readers:** hegemony `Faction.getResource(7)`, rate `getCachedResNetProd(7)`; win 30000 (const 8), "near" 20000
  (const 9). CHOAM `state.choamMarket.getFactionSharesRatio(f)` 14263 (win > 0.5, shown 0.4). Governor
  `state.resolutions.getCharterOwner("DuneGovernor")`, `ResolutionManager.getGovernorRemainingTime()` 15056 (seconds,
  null without a governor; win after 30 days). Vanilla's 0-1 summary: `Diplomacy.getFactionVictoryAdvancement(f,
  EndReason)` 8469 / `getFactionBestVictoryAdvancement(f)` 8468.
- **Diplomacy:** `DiplomacyManager.declareWar` 14781 (Influence 50 x attributes; 10-day grace after a status change),
  ForcePeace send chain (Atreides only), accept gate `AIController.tradeRequestReceived` 8283 (rules/peace.py);
  `Diplomacy.getTargetStatus` 8464 (strat redirects it inside getSiegeableVillages for the pressed owner).

## 7b. Assault campaign design

User: a base kill needs foresight a human has and the AI lacks: it can take more than one try (armies rebuilt in
between), and it needs coordination: wipe or draw off the enemy army first, then everyone attacks at the same time;
without edge-case code or flip-flops.

One shared campaign record per target base (global maps keyed by the base, so every coalition member reads the same
numbers and reaches the same decision without messaging):
- **Staging point:** our structure (or a neutral point) nearest L's base outside its gun range; members' armies
  muster there (the rally gather walk, claimed at P_RALLY).
- **Measured, not guessed** (the prediction):
  - base health and its damage rate while an assault runs (health drop per minute);
  - L's defense: base guns (cover) + L's army within reach of the base (the forecast's their side at the base);
  - coalition power mustered (sum over members of their armies within staging radius) and its rebuild rate (CP
    refill per minute after a wipe, from the snapshots).
  - Kill ETA = muster time + walk + remaining health / measured damage rate (first try: an estimate from our power
    vs armor), x attempts = remaining health / damage per attempt. Compared with L's win ETA: the campaign is worth
    it while kill ETA < L's ETA (else level 1 check keeps bleeding L instead).
- **Phases** (one per campaign, the same for all members, with entry / exit hysteresis):
  1. **Attrition / draw-off:** while L's army near its base is too big, the campaign fights L's field army where it
     is weaker (hunts on L's armies, contests of L's sieges, liberations of its villages: level 1 tools). This is
     the "wipe the army first" step, and the natural opportunity signal (O3): an L army away or wiped lowers the
     base's defense number.
  2. **Muster:** members walk to the staging point; nobody attacks alone.
  3. **Go (synchronized):** when mustered coalition power >= KILL x L's defense at the base, the campaign records a
     go time; every member launches its assault (Raze / main-base order) at that time, so they arrive together.
  4. **Siege:** stays while the forecast at the base >= KEEP; doctrine Siege mode (mix + gear) for every member.
  5. **Regroup:** below KEEP the members fall back to the staging point, heal and rebuild (Siege mode recruits), and
     the campaign returns to muster. A failed try is not an end: the base's lost health stays lost, the next try
     needs less.
- **Ends only by:** base destroyed; the switching rule (section 4: another faction clearly ahead and this kill not
  close: base health above KILL_CLOSE or kill ETA > KILL_SOON); kill ETA hopeless (> L's win ETA for long, back to
  check); or a member's own structure besieged (that member's defend reflex; the campaign goes on with the others).
- Anti flip-flop: phase changes need their condition for N checks and have separate enter / leave thresholds; a
  campaign lasts at least COMMIT_MIN unless the base dies; the "kill close" test makes finishing outrank switching.

## 7c. Module boundaries

- **One owner:** `rules/bkill.py` holds the plan state (threat table, leader, levels); `rules/bkcamp/` runs the
  campaign (one module per pass section: numbers, phase, member, muster, go, raze); `rules/bkstate.py` names every
  campaign map once, with accessors for the reads other rules make (heal/, strike.py).
- **Narrow reads:** other rules only ask two questions through common helpers: "who is our plan's target?"
  (`_bk_target`) and "what phase is our campaign in?" (one helper to add). No rule reads the plan's maps directly.
- **Reuse the executors where they work:** doctrine `dsiege` (Siege mix and gear), the forecast (every strength
  test), claims (who belongs to the campaign), `strike` (fights on the march). The campaign moves its own armies
  (Move / ArmySiege / ArmyFight) where vanilla's order path failed: a structure holds one besieging faction, and
  vanilla's Raze supply check prices the walk from our land, too far from the base for most members.
- **No special cases:** every decision is one of the measured numbers in 7b against a named threshold with
  separate enter / leave values; a situation that seems to need its own exception means a number is wrong, and that
  number gets fixed instead (tune, don't add: ARCHITECTURE-PLAN step 4).
- **Visible:** every phase change is logged with the numbers that caused it (`bkill`), the scorecard shows the
  campaign timeline, and each stage is tested in the late scenario (docs/TESTBED.md) before the next is built.

## 8. Build stages

1. **Threat picture (built first, no army moves):** every BK_T s per faction, the threat table (per faction: hegemony,
   its rate, CHOAM ratio, governor / remaining days, win ETA per condition, best ETA) and the shared leader with its
   confirmation; each faction's level (0 none / 1 check / 2 assault / 3 regroup) by section 3 / 4, logged (`bthreat`,
   `bkill`), so a match shows whether it picks the right leader at the right time.
2. **Check (level 1):** war on L (declareWar outside the grace period), L's peace offers refused, the press prefers
   L's villages (liberate first: DMZ), siege candidates of other at-war owners de-weighted (partner up), coalition
   members' peace offers accepted.
3. **Assault (level 2 / 3):** the Raze gauge lifted for the plan's faction, its target status toward L 1 inside the
   siege scans, Raze candidates L's base only, `dsiege` set (doctrine Siege mode), the siege memory never blocks L's
   base (regroup instead), the base ops (Defense Sabotage / Breaches), commitment and switching rules.

Hysteresis: a sitting leader is kept up to ETA_Q x KEEP_K (100 days; crowned at <= 80); a race stays a race up to SELF_RACE x LVL_HYST, an assault up to ASSAULT_ETA x LVL_HYST (39 days). BK_SPLIT (siege sizing) applies only while another plan member is at war with the leader, never at the leader's main base. A coalition truce is confirmed only when it asks no resources / agents of us.

Coalition pressure: the leader can be in one place only. With another plan member at war with it, the leader's armies count x BK_SPLIT 0.6 in (1) the siege estimate, (2) the battle forecast's their side at the leader's structures beyond LOCAL (chips at villages away from the stack pass; next to it they don't), (3) every member's home need (no member holds home against the whole stack; one at our structures stays full). Truce offers go both ways (the side with Influence gets it through: 14 of 18 single-side offers failed MissingResources). Joint attack: partners' armies within LOCAL of a leader target take PARTNER_W 0.7 x their power off the leader's side of the forecast (floor PARTNER_FLOOR 0.3). The campaign muster is described in section 7b.

**Stage 3 as built:** docs/AI-POLICY.md 'Base-kill campaign' (current rules) and progress.md (status, open items).
The first slice (one Raze order per go by a lead, supporters fighting off the base) is replaced by the direct raze of
every member (BC_ALL_DIRECT); its code stays dormant. Not yet: a kill ETA from measured base damage, the switching
rule's 'kill close' test.
