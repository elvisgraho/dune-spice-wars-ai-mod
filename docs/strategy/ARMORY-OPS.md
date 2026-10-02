# Armory gear sets and operation priorities

Per-faction gear sets (Field / Siege / Hold) and operation priorities, with how vanilla AI handles both today and where we'd hook. Tags as in [GENERAL.md](GENERAL.md) (T transcript, W wiki, D data, C code). Gear effects below are D (`equipment` sheet + its traits); "T:" marks what experts run. Candidates: [CANDIDATES.md](CANDIDATES.md) C16 (gear), C17 (operations).

## How vanilla does it (C)

**Gear** (`AIController.checkEquipments` f@8259, per AI tick):
- Candidates: every (unit kind, gear) pair `Equipments.canApply` allows whose cost passes `ResourceManager.compareGoals` (stricter for non-Military AI types).
- Score (`$HScoring.equipments` f@40762 → closure f@41010) = the gear's data `aiWeights` (per aiType / councilor) + `valueCache[1027]` if a gear in `props.aiCombo` is already on that unit + `valueCache[1028]` if one in `aiComboMalus` is; special case `AdditionalBags` by unit armor.
- Pick: `pickMapBest(scores, fValuesCache[1029][difficulty])` then a random one of those; it's applied to a free slot, or replaces the lowest-scored current gear when the new one scores higher. One change per call.
- **Gap (D):** 125 of 157 gear rows have empty `aiWeights` (score 0): AI gear is mostly a random pick among ties. Cost (D `props.cost`): 500 Solari for 149 rows, 5 Scraps for the 8 flagship (Altar) rows. A tie doesn't replace an equal-scored gear (strictly higher needed), so it fills empty slots randomly and then mostly stays.
- Gear is per **unit kind, faction-wide**: one set at a time for all armies. 2 slots: slot 1 from the generic Survival Training development, slot 2 from Army Logistics (D: generic Military T1; Atreides and Ecaz use it) or the faction's replacement: Corrino Imperial Command and Vernius Water Batteries (T1), Smugglers Industrial Scavenging and Fremen Stalwart Alliance (T2), Harkonnen Adrenaline Addiction (T3: Harkonnen run one slot for most of the game); Vernius C'Tair +1 slot per unit for +1 fuel cell.

**Operations** (`logic.ai.Spying`):
- Acquisition: `$HScoring.spyingMissions` f@41035 → closure f@41045 = the mission's `aiWeights` only. D: most faction ops have empty weights; `MProbeSetup` and `NukeTargeting` are `aiProhibited`.
- Launch, two paths: (1) `tryLaunchOperation` f@8609 (from `checkOperations` f@8605, each held op) has hand-written targeting for 18 ids: Assassination, CellSearch, InfiltrationCells, MArrakisDiplomacy, MCeaseFire, MCombatDrugs, MConsolidation, MCrowdManipulation, MEMPBomb, MGearSabotage, MGhostMarket, MMaraudersRaid, MProbeSetup, MSandCloak, MSleeperAgents, MSupplyDrop, MWormCalling, NukeTargeting. Combat ops (CombatDrugs, EMP, SleeperAgents) go to warzones whose balance is ≥ 0.5 and ≤ a max (close fights). (2) Order phases: `AIMilitary.getActionMandatoryMissions` f@8406 (Raze → MDefenseSabotage DuringSiege) and `getActionOptionalMissions` f@8407 per gauge kind: Annexation {MAwakePeople EnRoute, MInterdictionZone During, MCommunicationJamming EnRoute / During}; Liberation {MEMPBomb, MToxicVapors Regroup, MGearSabotage, MDecoyThumper ×3 phases, MAwakePeople, MPoisonReserves ×2, MInterdictionZone, MCommunicationJamming ×2}; Pillage {MScavengerTeam ×2, MDecoyThumper ×3}; Raze {MGearSabotage, MCommunicationJamming}. (Traced earlier: `tryLaunchOperationFromOrder` ~109/min, always False; why is unread.)
- **No launch path at all** (neither list): `MOrbitalStrike`, `MHiddenThumpers`, `MHiddenBackdoor`, `MElaccaFog`, `MEpicQuest`, `MLivePerformance`, `MAmbientConnection`, `MEmpiricalData`, `MSupportIntelligence`, `MAdministrativeBurden`, `MLeaveOrder`, `MSmugglingOperation`, `MSupplyCaches`. `MToxicVapors`, `MCommunicationJamming`, `MInterdictionZone`, `MPoisonReserves`, `MDecoyThumper` only around our own sieges, not for defense or field fights.

**Id ↔ UI name** (D faction + cost / difficulty; names inferred where the data has no text): `MGearSabotage` = Defense Sabotage (easy, turrets / main base -30% power), `MDefenseSabotage` = Defense Breaches (hard, main base +50% damage taken, -3 armor), `MSmugglingOperation` = Extraction Network, `MSandCloak` = Hiding Tracks, `MAwakePeople` = Awaken the People, `MSupportIntelligence` = Support Intelligence. Costs: easy 100 intel, medium 200 intel + 200 Solari, hard 500 + 500 (D).

## The three gear sets

| Set | When (triggers) | Goal |
|---|---|---|
| **Field** (default) | no other trigger | win army fights at even odds; vet up |
| **Siege** | a planned assault on fortified targets lasting several fights: `strat` press on a bunker / main base, Raze, O1 (a rival about to win must lose villages or its base), Corrino / Smugglers base-kill plans | damage vs structures and armor, out-range turrets, survive turret fire |
| **Hold** | posture defend / hold dominant for long, O4 (we lead and expect a coalition), a turtle phase (C8) | survive at home under own turrets, cheap remax |

Plus **counter swaps** (one gear on one unit kind, any set): anti-air when the main enemy army has a large air share (Hawks, Harpies, Spires, Sirens, Banshees, flagships); anti-stealth (Shadow Scan) against Fremen / Smugglers / Vernius (C'Tair) / Harkonnen Cerberus; anti-mech against Vernius or drone-heavy Corrino / Atreides.

**Switching rules** (shared): a gear change costs Solari (500 each) and applies faction-wide, so: hold a set ≥ SET_HOLD (5 game days ≈ 150 s) after switching; switch only with Solari ≥ changes × 500 + a reserve; change the unit kinds that matter most first (vanilla applies one change per call anyway); leave the set when its trigger has been off for SET_HOLD. Early game (one slot): take the first-listed gear of the Field set.

### Atreides
Units: Trooper, Ranger, Heavy Weapon Squad (HWS), Support Drone, Warden. Gear: Trooper {Front Line Tactics: allies in melee +1 armor, self -1 power · Offensive Mindset: +2 power, +15% damage taken · Parrying Armguards: -10% melee damage taken · Prana Bindu: +5% health per XP level}; Ranger {Crossfire: +10% damage per ally on the same target, -10% attack speed · Long Rifle: +40% range · Automatic Weapons: +50% attack speed, -30% power · War Memoirs: +5% power per XP level}; HWS {Distracting Flashes: allies in melee -10% damage taken · Heavy Loads: +30% power, -25% attack speed · Whistling Ammo: +20% vs air · War Memoirs}; Support Drone {Kraken Protocols · Supporting Field · Evasion Booster · Optimized Bed: +1 carry, 2 fuel cells}; Warden {Cover Tactics: idle allies nearby +30% speed, +5 armor · Last Stand Protocols · Parrying · Prana Bindu}.

| Unit | Field (T: memoirs everywhere, +1 carry, HWS -10%) | Siege | Hold |
|---|---|---|---|
| Trooper | Prana Bindu + Parrying | Prana Bindu + Offensive Mindset | Front Line Tactics + Parrying |
| Ranger | War Memoirs + Long Rifle | War Memoirs + Crossfire (focus fire) | War Memoirs + Long Rifle |
| HWS | Distracting Flashes + War Memoirs | Heavy Loads + War Memoirs | Distracting Flashes + War Memoirs |
| Support Drone | Optimized Bed + Supporting Field | Optimized Bed + Evasion Booster | Optimized Bed + Kraken Protocols |
| Warden | Parrying + Prana Bindu | Parrying + Last Stand Protocols | Cover Tactics + Parrying |

Counters: anti-air HWS Whistling Ammo. No anti-structure armor-ignore gear: Atreides sieges lean on Defense Breaches / HWS (*assumption*: higher per-hit power matters more vs armored structures).

### Harkonnen
Gear: Trooper {Scarring Armor: +6 armor scaling with missing health, -3 base · Morbid Climax: fights on briefly at 0 health · Fix-up Kit: +30% health at combat start, lost after · Red Fluid: +30% attack speed, health drain in combat}; Gunner {Blood Thinner: drops to 75% health at combat start (gunners gain power at low health), restored after · Heavy Loads · Bird Slayer: +40% vs damaged air · Red Fluid}; Cerberus {Elacca Injector: splits into 2 on death, -150 health · Stealth Gear · Endocrine Arouser: speed by missing health · Red Fluid}; Combat Probe {Torture Tools: melee, ignores half armor · Mounted Explosives: death blast, 2 fuel · Optic Camouflage · Virtual Black Box: +10 intel on death}; Executioner {Hibernation Breastplate: buff while no bloodthirst stacks · Parrying · Meat Armor: spend a stack to revive at 40 health, -150 health · Red Fluid}. D: Red Fluid is the one weighted gear (Military 15, Iakin 10) with a malus next to Stealth / Heavy Armor.

| Unit | Field (T: meat + hibernation, split + stealth, morbid climax) | Siege | Hold |
|---|---|---|---|
| Trooper | Morbid Climax + Fix-up Kit | Morbid Climax + Red Fluid (T: red fluid for base kills) | Scarring Armor + Fix-up Kit |
| Gunner | Blood Thinner + Red Fluid | Heavy Loads + Blood Thinner | Blood Thinner + Heavy Loads |
| Cerberus | Elacca Injector + Stealth Gear (early: Stealth + Endocrine, T: splitting costs manpower early) | Elacca Injector + Stealth Gear | Elacca Injector + Endocrine Arouser |
| Combat Probe | Torture Tools + Virtual Black Box | Torture Tools + Mounted Explosives | Optic Camouflage + Virtual Black Box |
| Executioner | Meat Armor + Hibernation Breastplate | Meat Armor + Red Fluid | Meat Armor + Parrying |

Counters: anti-air Gunner Bird Slayer. Vs Corrino (Sardaukar execute executioners): Field with more gunners (comp, not gear).

### Fremen
Gear: Warrior {Dry Training: +1 health per water · Sand Cover: -20% ranged damage taken · Confusing Tactics: -10% damage taken per adjacent enemy (×3) · Shelter Maps: -15% damage taken in own / neutral land}; Skirmisher {Camouflage Fabric: unseen out of combat · Scatter Grenades: +40% AoE radius · Anti-personnel Shrapnel: +10% vs non-mech · Loud Bang: damaged enemies -10% damage}; Infiltrator {Camouflage Fabric · Electronic Scrambler: a mech target -20% speed and attack speed · Chasing Stance: target -20% speed · Focused Mind: no speed loss, +1 armor}; Mobile Turret {Folding Frame: deploy 4× faster · Ambush Camouflage · Shadow Scan: detects stealth at long range · Pre-loaded Weapons: +100% power attacking undetected}; Fedaykin {Maker's Effigy: +2 power, -1 armor · Devastating Strikes: +10% damage per enemy hit · Confusing Tactics · Self-sufficiency: +6 power, +1 CP}; Altar (flagship) {Sky Facade (stealth) · Wreck Harness · Makeshift Workshop (regenerates) · Symbol of Freedom (+50 Authority per liberation in its region) · Storm Sails · Recon Stations (detects stealth very long range) · Sand Cloud (nearby ground allies stealthy) · Supply Hold (nearby allies regain supply)}.

| Unit | Field (T: "middle two" warriors / Fedaykin, right two skirmishers, turret 2nd + 4th) | Siege | Hold |
|---|---|---|---|
| Warrior | Sand Cover + Confusing Tactics | Sand Cover + Confusing Tactics (turrets are ranged) | Shelter Maps + Sand Cover |
| Skirmisher | Anti-personnel Shrapnel + Loud Bang | Scatter Grenades + Anti-personnel Shrapnel | Camouflage Fabric + Loud Bang |
| Infiltrator | Camouflage Fabric + Chasing Stance | Camouflage Fabric + Focused Mind | Camouflage Fabric + Chasing Stance |
| Mobile Turret | Ambush Camouflage + Pre-loaded Weapons | Folding Frame + Pre-loaded Weapons | Ambush Camouflage + Shadow Scan |
| Fedaykin | Devastating Strikes + Confusing Tactics | Self-sufficiency + Devastating Strikes | Devastating Strikes + Confusing Tactics |
| Altar | Symbol of Freedom + Sky Facade (T) | Supply Hold + Makeshift Workshop | Recon Stations + Makeshift Workshop |

Counters: anti-mech Infiltrator Electronic Scrambler (vs Vernius); anti-stealth Mobile Turret Shadow Scan or Altar Recon Stations (T: a turret per village stops assassins). Fremen have no anti-structure gear: their "siege" is mostly liberation (C11).

### Smugglers
Gear: Scavenger {Chasing Stance · Gnarly Recyclers: heal 20% of damage dealt · Heavy Armor: +2 armor, -2 power · Dismantling Tools: ignore half of mech and structure / building armor}; Wrecker {Concentrated Toxins · Bazooka: +50% range · Traumatic Repeater: damaged units -1 armor · Stinging Gas: damaged enemies take +10% damage from all sources}; Sniper {Propelling Ammo: up to +5 power at long range · Recursive Lens: +10% vs slowed · Barrel Cleaner: first attack at full health +100% power · Whistling Ammo}; Scavenging Drone {Shielding Straightener (armor ability) · Shock Dampener: +5 intel per loot delivery · Optic Camouflage · Motivational Cashbox}; Free Company {Running Sandshoes (Haste) · Stealth Gear · Dual Guns: ranged attacks · Dismantling Tools}.

| Unit | Field (T) | Siege (T: dismantling on everything for the base kill) | Hold |
|---|---|---|---|
| Scavenger | Heavy Armor + Gnarly Recyclers | Dismantling Tools + Gnarly Recyclers | Heavy Armor + Gnarly Recyclers |
| Wrecker | Traumatic Repeater + Stinging Gas | Bazooka + Stinging Gas | Traumatic Repeater + Stinging Gas |
| Sniper | Barrel Cleaner + Propelling Ammo | Barrel Cleaner + Propelling Ammo (out-range turrets) | Barrel Cleaner + Propelling Ammo |
| Scavenging Drone | Shock Dampener + Motivational Cashbox (late: Shielding Straightener) | Shielding Straightener + Motivational Cashbox | Shielding Straightener + Shock Dampener |
| Free Company | Stealth Gear + Dismantling Tools | Stealth Gear + Dismantling Tools | Stealth Gear + Running Sandshoes |

Counters: anti-air Sniper Whistling Ammo; vs renegade bases T used Dual Guns (ranged) on Free Company.

### Corrino
Gear: Conscript Swordsman / Rifleman {Small Formation: -1 CP, 65% damage and health, squad -1 (more bodies per CP, T: pairs with Wensicia) · Supporting Tactics: non-conscript allies nearby +1 armor · Live Reformation: health sharing · Parrying (swords) / Whistling Ammo (rifles)}; Incinerator {Wide Nozzle · Exotic Compounds: burn stacks 50% faster with 2+ incinerators · Phosphorus Mix: +30% vs non-mech · Terrifying Mask: -1% damage taken per burn stack}; Artillery Drone {Long Cannons: +20% range, bigger blind spot (D aiWeights 5) · Heavy Loads · Incendiary Ammo: 2 burn stacks per hit · Whistling Ammo}; Sardaukar {Frightening Reputation: +5 Influence per execution · Parrying · Sardaukar's Cleaver: execute threshold +10% (D aiWeight Military 15; T: buggy) · Battlefield Frenzy: +1% attack speed per nearby ally}.

| Unit | Field (T: small formation + live reformation with Wensicia) | Siege (T: flamers' burn stacks kill bases) | Hold |
|---|---|---|---|
| Swordsman | Live Reformation + Small Formation (Wensicia) / Supporting Tactics (else) | Live Reformation + Parrying | Supporting Tactics + Parrying |
| Rifleman | Live Reformation + Small Formation / Supporting Tactics | Live Reformation + Supporting Tactics | Live Reformation + Supporting Tactics |
| Incinerator | Phosphorus Mix + Exotic Compounds | Exotic Compounds + Wide Nozzle | Phosphorus Mix + Terrifying Mask |
| Artillery Drone | Long Cannons + Heavy Loads | Incendiary Ammo + Long Cannons (out-range turrets, burn) | Long Cannons + Heavy Loads |
| Sardaukar | Battlefield Frenzy + Parrying | Battlefield Frenzy + Parrying | Parrying + Frightening Reputation |

Counters: anti-air Rifleman / Drone Whistling Ammo. Burn stacks on a main base (T) are the reason incinerators belong in the Siege set (verify that structures take `Burned_Trait`).

### Ecaz
Gear: Squire {Front Line Tactics · Knightly Protector: +1 armor with a knight nearby · Sobering Medication: half of damage bonuses become damage reduction · Prickly Spear: its target deals -20% damage to non-squires}; Musketeer {Shadow Scan · Heavy Loads · Barrel Cleaner · Bird Slayer}; Fencer {Jumping Boot · Personal Mantlet: +5 armor until its first attack · Parrying · Chasing Stance}; War Banner {Distracting Lights: enemies targeting it take +20% · Marching Colors: +20% speed out of combat nearby · Propaganda Machine: enemies nearby -10% damage · Big Banner: long range auras, +100 health}; Knight {Vow of Bravery: ignore half armor, -2 armor · Vow of Fervor: +20% damage, -100 health · Vow of Heroism: +15 power, +3 CP · Vow of Honor: squires nearby buffed}.

| Unit | Field (T: musketeer stealth detection + barrel cleaner; knight heroism + honor) | Siege | Hold |
|---|---|---|---|
| Squire | Knightly Protector + Prickly Spear | Knightly Protector + Front Line Tactics | Knightly Protector + Sobering Medication |
| Musketeer | Barrel Cleaner + Shadow Scan | Barrel Cleaner + Heavy Loads | Barrel Cleaner + Shadow Scan |
| Fencer | Personal Mantlet + Parrying | Personal Mantlet + Chasing Stance | Personal Mantlet + Parrying |
| War Banner | Propaganda Machine + Big Banner | Marching Colors + Big Banner | Propaganda Machine + Big Banner |
| Knight | Vow of Heroism + Vow of Honor | Vow of Bravery + Vow of Heroism | Vow of Heroism + Vow of Honor |

Counters: anti-air Musketeer Bird Slayer (T switched to it vs a Wraith). A Champion knight benefits most from Heroism.

### Vernius
Gear: Fighting Mek {Material Pre-processor: +5% power and -5% attack speed per point of target armor · Heavy Shielding: +2 armor, 2 fuel · Anatomical Scanner: +15% vs non-mech · Learning Transistors: knowledge from combat}; Suboid {Tinkering Gear: drones nearby +10% power · DIY Kit: no Solari upkeep · Focused Mind · Dismantling Tools}; Railgun {Propelling Ammo · Strong Magnets: +3 power, 2 fuel · Whistling Ammo · Learning Transistors}; Resonance Drone {Fractal Frequencies: +50% aura damage, 2 fuel · Feedback Gate: +0.5 armor per drone nearby (×10) · Deep Signals: mech allies nearby +10% damage · Repeater Node: always tethered, tethers mech allies nearby}; Fight-Engineer {Work Shelter: +3 armor while repairing · Shadow Scan · Multi-purpose Parts: mech allies nearby -20% upkeep and regen cost · Memory Implant: +1 XP gain}.

| Unit | Field (T: DIY early, Strong Magnets, Fractal + Repeater, engineers vet up) | Siege / off-node attack | Hold (on nodes) |
|---|---|---|---|
| Fighting Mek | Anatomical Scanner + Heavy Shielding | Material Pre-processor + Heavy Shielding | Heavy Shielding + Anatomical Scanner |
| Suboid | DIY Kit + Tinkering Gear | Dismantling Tools + Tinkering Gear | DIY Kit + Tinkering Gear |
| Railgun | Strong Magnets + Propelling Ammo | Strong Magnets + Propelling Ammo | Strong Magnets + Learning Transistors |
| Resonance Drone | Fractal Frequencies + Repeater Node | **Repeater Node** + Deep Signals | Feedback Gate + Fractal Frequencies |
| Fight-Engineer | Memory Implant + Work Shelter | Work Shelter + Multi-purpose Parts | Work Shelter + Shadow Scan |

Repeater Node makes the army fight tethered away from nodes (D: always tethered, tethers mech allies nearby): it is what lets Vernius attack off its network at full strength, so the Siege set is also the "off-node offensive" set. Fuel cells: Heavy Shielding, Strong Magnets, Fractal Frequencies cost 2 each per unit (and C'Tair +1): a set can be unaffordable on fuel (vanilla's `compareGoals` check then skips it).

## Operation priorities

Slots: 3 by default (W). "V" = vanilla can launch it (hand-written targeting), "O" = only inside our own siege orders, "N" = no AI launch path (needs our code, C17). Supply Drop (V) is the universal first pick for non-mech armies; vanilla weights it only for the Military AI type (D aiWeight 5), so it isn't guaranteed.

| Faction | 1st | 2nd | 3rd | Siege / catch-up swap | Hold swap |
|---|---|---|---|---|---|
| Atreides | Supply Drop (V) | Cease Fire (V): protect a peaceful annex / a village under capture | EMP Bomb (V) vs mech-heavy enemies, else Arrakis Diplomacy (V: disbands raids / rebels) | Defense Breaches (`MDefenseSabotage`, O Raze) + Defense Sabotage (`MGearSabotage`, V) | Cease Fire on our besieged village |
| Harkonnen | Sleeper Agent (V) | Combat Drugs (V) | Supply Drop (V) | Toxic Vapors (O Liberation only → N elsewhere) on the defenders; Defense Breaches | Toxic Vapors on attackers in our region (N) |
| Smugglers | Supply Drop (V) | Communication Jamming (O → N for defense: cancel the enemy's key op, e.g. a ceasefire on a village we contest) | Extraction Network (`MSmugglingOperation`, N: pull a losing army home) | Defense Sabotage + Defense Breaches (T: base kill) | Poison the Reserves (O → N) on raiders in our land |
| Fremen | Hiding Tracks (`MSandCloak`, V) | Supply Drop (V) | Hidden Thumpers (N: worm transit + stealth) | Decoy Thumper (O) on sandy approaches; Awaken the People (O, already on vanilla's Annexation / Liberation lists) | Hiding Tracks around our villages |
| Corrino | Orbital Strike (N!) | Supply Drop (V) | Interdiction Zone (O → N for defense: block the enemy's airfield reinforcements) | Defense Breaches + Orbital on the main base | Consolidation (V: +2 armor to mech and structures) |
| Ecaz | Supply Drop (V) | Elacca Fog (N: protects champions in a won fight) | Epic Quest (N: champion +100% damage) | Defense Breaches | Live Performance (N, Influence) is low value; keep EMP (V) vs Vernius |
| Vernius | Hidden Backdoor (N) vs mech enemies, else Empirical Data (N) | Ambient Connection (N: remote tether for off-node attacks) | EMP Bomb (V) vs another mech army | Ambient Connection + Defense Breaches | Empirical Data (knowledge from fights at home) |

Shared rules (all factions): CellSearch (V) is automatic once an assassination is detected; Probe Setup is AI-prohibited (D), so stealth enemies need gear (Shadow Scan) unless the prohibition is lifted by a data patch. Vernius armies are mostly mechanical: Supply Drop (non-mech only, W) is a low pick for them.

## Edge cases

- **Faction-wide gear:** a Siege set also arms the armies defending at home. Pick the set by the dominant plan (where most CP is committed), not by one army.
- **Switch thrash:** the vanilla loop replaces the lowest-scored gear whenever a strictly higher one is picked; with set weights an off-set gear has to score below every in-set one, and scores change only with the mode (hysteresis above), so each mode switch costs one round of 500-Solari changes and nothing more.
- **Unaffordable sets:** fuel-cell gear (Vernius, Atreides Optimized Bed, Harkonnen Mounted Explosives) fails `compareGoals` when fuel is short; the next-best in-set gear should fill the slot rather than an off-set one.
- **One slot early:** before slot 2, the first gear listed per set is the one that matters.
- **Mode vs ops:** Siege set and siege ops (Defense Sabotage / Breaches) belong to the same plan; launching a 500/500 op without the army arriving wastes it (ops last ~3 days).
- **Ops with all-faction scope** (Elacca Fog, Comms Jam, Live Performance) also hit us: launch only where the fight is ours to win.
- **Unverified effects:** whether "ignores half armor" gear (Torture Tools, Vow of Bravery) applies to structures (Dismantling Tools states it does), and whether burn stacks apply to main bases (T says yes).
