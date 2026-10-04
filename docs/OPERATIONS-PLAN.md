# Operations: design

What every AI faction buys, when and where it casts, and how it reacts to enemy operations. The user's play notes are the spec. The build (hooks, functions, maps, phases) is in [OPERATIONS-IMPL.md](OPERATIONS-IMPL.md); vanilla's paths are in [strategy/ARMORY-OPS.md](strategy/ARMORY-OPS.md) and REVERSING "AI gear and operations".

## Principles

- **Our rules own every military op.** Vanilla's launch paths are off for them. Spying and politics ops stay vanilla's (Cell Search, Infiltration Cells, Assassination, Marauders Raid, CB_*).
- **Best play first.** No dice or reaction delays: each trigger fires when its conditions hold. Imperfection, if wanted, comes later as tuning.
- **Fog of war.** Triggers read only what the faction sees: visible armies (`Entity.isVisibleForFaction`), reconned structures, our own orders, zone effects. Never another faction's orders or held ops. Same rule as for every other AI rule (OPERATIONS-IMPL "Stage 0").
- **No ops on cheap work.** Annexing or pillaging a plain village gets nothing. Ops go to:
  - money: sietch and renegade pillages, big fights (Scavenger Team);
  - fights against faction armies;
  - owned villages;
  - our besieged villages.
- **No plan waits for an op**, except the main-base kill ("Base-kill reservation").
- **Every cast and every block is logged with its reason.**

## Facts the design rests on (code-confirmed unless marked)

- **Target kinds:** `apply.need` is an enum: 0 zone (`args.zone`), 3 village (`args.struct`, must be reconned), 4 active main base (`args.struct`, reconned or `ignoreReconned`). The alignment and `validDiplomaticStatuses` checks follow.
- **Slots and buying:**
  - Slots: 3 (started + held, `Operation_NbSlotsBase`; max 5).
  - A held op unused for 15 days is cancelled and refunded.
  - Vanilla buys only when Intel ≥ the largest Intel cost among its candidates, and picks the best score on Insane.
- **Cease Fire** (zone attribute `NoFight` 626): nobody can fight or be attacked there. A capture gauge pauses while its occupiers are in range, and decays without them. A Cease Fire on a besieged village **cancels the attacker's AI siege order** (checkOrderTerminations' closure calls `canBeAttacked`).
- **Communication Jamming:**
  - On cast it removes every operation trait from the zone and its structures, any faction's, ours included (an active Supply Drop too).
  - For its duration nobody can cast an op there: `noUseReasonOn` returns `BlockedBy` for `Operation_Block` 75.
- **Extraction Network:** a circle of radius 29 around the zone's village. For 3 days, our non-flying armies inside it are hidden for 10 s and teleported to our main base 1 s later. Only the army's action is cancelled; its AI order is not.
- **Decoy Thumper:** needs worm activity > 0 in the target zone. The worm goes there; neighbouring zones get `Zone_NoSandworm`.
- **Worm warning:** `WormSign` rises once the worm is spotted by us and one of our units is within 65 of it, before `targettedByWorm`.
- **Combat Drugs:** +30% damage, already in `offensivePotential`, so our power reads include it.
- **Orbital Strike:** damage to our own village doesn't matter (user); damage to our own units does.
- **Poison the Reserves:** hurts only armies losing supply in the zone.

## Loadouts (what each faction holds; 3 slots, Supply Drop included)

| Faction | Always | Context |
|---|---|---|
| Atreides | Cease Fire (held always, peace too), Supply Drop | Scavenger Team; Decoy Thumper; EMP vs a ≥ 40% mech enemy; Arrakis Diplomacy while at peace with all |
| Harkonnen | Sleeper Agent, Combat Drugs | Scavenger Team; Decoy Thumper; Toxic Vapors when rich |
| Smugglers | Extraction Network, Supply Drop | Communication Jamming (held always: peace can be cancelled or betrayed); Scavenger Team; Poison the Reserves |
| Fremen | Decoy Thumper, Hiding Tracks | Awaken the People when liberating; Supply Drop |
| Corrino | Orbital Strike (when rich), Consolidation | Supply Drop; Interdiction Zone |
| Ecaz / Vernius | Supply Drop / Hidden Backdoor vs mech | Elacca Fog, Epic Quest / Ambient Connection |

Context slots are ranked by what the faction's situation calls for: wars, enemy mech share, money, the pillage targets in reach. Defense Breaches, Administrative Burden and main-base Defense Sabotage are bought only for a base kill.

## Trigger catalogue

**Terms:**
- "Fight": a warzone (`State.warzones`) where we are involved against at-war faction armies.
- B: the balance ours / theirs, from visible units, the same reading as the retreat check.
- "Big fight": total power on both sides ≥ OPS_BIGFIGHT.

### Shared

| Op | Fires when | Target | Not when |
|---|---|---|---|
| Scavenger Team | (a) our Pillage of a sietch or renegade base is in Action; (b) a big fight at B ≥ 0.8 | that zone | a plain village Annex / Pillage / Liberation; B < 0.5 (we'd be paying for our own dead) |
| Decoy Thumper, escort | `WormSign` near our army on sand that is on a march or a siege walk, and `worm-flee` land is further than the worm | a neighbour zone of the army's zone with worm activity and none of our armies; enemy-owned first, then one with enemy armies | the army reaches land first; that neighbour is our siege target zone |
| Decoy Thumper, deny | a visible hostile group (≥ OPS_THUMP_PW, or ≥ 0.5 × our nearest defence) on sand, moving toward our village (its distance to it fell between two scans), deep in its zone (≥ OPS_THUMP_DEPTH to land or to the zone edge along its heading), its zone not touching its own land | the army's zone | any of our units in that zone |
| Defense Sabotage | our siege of an enemy village with Missile Batteries reaches Engage, and turret cover ≥ 30% of the defence | that zone | a main base (reserved) |
| EMP Bomb | a fight or siege with enemy mech (units + batteries) ≥ 40% of their power, 0.5 ≤ B ≤ 2 | that zone | our own mech ≥ 40% |
| Supply Drop | `sdrop` (unchanged) | | |

### Atreides
- **Cease Fire, defence:**
  - Fires when an enemy faction occupies our village (`siege.occupier` EFaction), capture progress < 0.75, and our power that can arrive before the capture ends < 0.9 × theirs (the rally's hopeless reading).
  - Target: the village zone.
  - The cast also cancels the attacker's AI order. Our rally treats it as time bought and keeps gathering for its duration.
- **Cease Fire, protect:** a hostile group ≥ our cover moves within 400 of our peaceful-annex village.

### Harkonnen
- **Sleeper Agent + Combat Drugs:**
  - Fires in a big fight against faction armies (not militia, not a village), 0.5 ≤ B ≤ 2, with ≥ 3 of our armies in it.
  - Sleeper needs enemy non-temporary infantry ≥ 50% of their power.
  - Sleeper first, Drugs in the same tick.
  - One alone if only one is held: Drugs at 0.6 ≤ B ≤ 1.4, Sleeper when the enemy infantry is large.
- **Scavenger Team + Combat Drugs:** our sietch or renegade Pillage. Scavenger goes at Action, Drugs when the garrison fight starts.
- **Toxic Vapors:** an infantry siege on our village, or our long siege of an infantry-held enemy village. Only with Solari ≥ OPS_RICH.

### Smugglers
- **Communication Jamming:**
  - Weighs value against cost:
    - Value: enemy ops removed in the zone (a Cease Fire on our siege target × our capture progress; Combat Drugs / Sleeper / Toxic / Hiding Tracks on a fight at 0.5 ≤ B ≤ 2).
    - Cost: our own ops removed or blocked there (an active or locked Supply Drop with armies short of supply; a held op we'd want to cast there within 90 s).
  - Casts when value − cost ≥ OPS_JAM_MIN.
  - Pre-emptive casts too: a big fight against Harkonnen or Atreides at 0.7 ≤ B ≤ 1.5, cost 0, for denial.
- **Poison the Reserves:** visible hostile armies losing supply in a zone (not their land) where we defend or fight.
- **Extraction Network:**
  - Fires when our armies are at a village zone (our siege target or our defence) and either:
    - B < OPS_EXTRACT_B (0.45) with ≥ 25% lost since Engage; or
    - visible newly arriving hostile power ≥ 1.5 × ours within 400 heading in.
  - Also needs the walk home to be long (> 2 zones or over sand).
  - After the cast:
    - our order there is cancelled, and armies outside the circle are moved into it;
    - the village goes into `slost` for LOST_T;
    - our orders are kept off that village while the circle lasts.

### Fremen
- **Decoy Thumper:** as shared, Fremen's main op.
- **Hiding Tracks:** a fight in or next to our land at 0.5 ≤ B ≤ 2, or our attack order at Engage on an enemy village.
- **Awaken the People:** our Liberation of an enemy village (reconned, `checkStartRebellion` ok) reaches Regroup.

### Corrino (needs Corrino in the testbed)
- **Orbital Strike:** hopeless defence:
  - an enemy occupies our village, progress 0.2-0.7, our reachable power < 0.6 × theirs;
  - ≥ 4 enemy squads at the village, our units' power in the zone < 25% of theirs.
  - Never at ≥ 0.75 progress (too late).
- **Consolidation:** a siege on our turreted village, or our mech-heavy fight at 0.7 ≤ B ≤ 1.3.
- **Interdiction Zone:** our siege of an enemy village that has an Airfield or Refinery.

### Ecaz / Vernius (last)
- **Ecaz:** Elacca Fog at B ≥ 1.5, since it stops everyone's retreat. Epic Quest on a champion's fight.
- **Vernius:** Hidden Backdoor vs ≥ 40% enemy mech at 0.5 ≤ B ≤ 2; Ambient Connection on our off-node siege.

## Reactions to enemy ops (every faction)

| Seen | Where | Reaction |
|---|---|---|
| Cease Fire | our siege target. Vanilla cancels our order there at once | Progress ≥ OPS_CF_WAIT (0.4), our supply lasts, and no visible relief ≥ ours is coming: **wait**. Keep the order alive and the occupiers in range, since the gauge pauses instead of decaying, then continue. Smugglers holding Jamming: **jam** (removes the Cease Fire) and keep the order. Otherwise **pivot**: the target is blocked for the effect's remaining time, so the next pick goes elsewhere (near targets score first), and the armies go home if nothing is picked |
| Cease Fire | a zone on our order's path | the order goes on (walking through is allowed); a target inside is handled as above |
| Communication Jamming | any zone | the brain never casts there; a lock (Supply Drop) on that zone waits |
| Decoy Thumper worm | our army's zone | `worm-flee` (land or a protected neighbour) |
| Orbital Strike / Toxic Vapors | a zone with our armies not about to finish a capture (progress < 0.8) | leave to the nearest neighbour zone without it |
| Combat Drugs | the enemy side of our fight | nothing extra (already in their power) |
| Sleeper Agent | the enemy side of our fight | our infantry deaths feed them: retreat line + OPS_SLEEPER_K (0.1) while it lasts |
| Hiding Tracks / unseen Fremen | our fight zone | Probe Setup (data patch lifts `aiProhibited`), only vs Fremen; last phase |

## Base-kill reservation

When the main-base attack exists, it sets the intent `bkill` (faction → target base, t):
- **Buying:** Defense Breaches, then Defense Sabotage, then Administrative Burden ~2 days before the strike.
- **Casting:**
  - Administrative Burden at intent + 1 day.
  - Defense Sabotage / Breaches (`args.struct` = the base) when our siege armies reach Engage.
- **Holding:** the launch waits up to OPS_BK_HOLD (1 day) for an op ≤ 1 day from done. This is the only plan that waits.

Until then these ops are neither bought nor cast.
