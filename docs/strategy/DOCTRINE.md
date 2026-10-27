# Army doctrine: unit mixes per faction, mode and playstyle

What each AI faction recruits (`rules/doctrine.py` reads the tables below at build time: this file is the data).
Gear per mode: [ARMORY-OPS.md](ARMORY-OPS.md) (same modes). Tags as in [GENERAL.md](GENERAL.md) (T transcript, W
wiki / web, D data, C code); web sources: Steam discussions 2022-2025, TheGamer guides 2022-23 (research 2026-10-23;
no curated meta exists, ratios are rare).

## How it works

- **Modes:** Early (game time < EARLY_T), Late, Siege (one of its Military orders at Regroup or later targets a main base or is a Raze, or the faction is committed to a base kill: plan level 2),
  Hold (posture defend / recover held for SET_HOLD). One mode per faction, switched at most every SET_HOLD (600) s.
- **Table cells** are relative weights of the faction's recruitable army count (normalized per column; 0 = never
  wanted). A unit's pick score = how far its share is below its weight; the two most short units are vanilla's
  weighted pick; a unit more than OVER (10) points above its weight isn't bought (the cheapest unit would fill every
  CP gap and pile up). Units the main base can't recruit right now (cost, unlock, slots) are dropped first, so an
  unaffordable top pick (a Guild-Favor ship) no longer blocks recruiting.
- **Styles:** each faction plays one style per match, picked at its first recruit (weights in the heading). A
  style is a full table.
- Unit names are the in-game names (D `texts.name`); the build fails on an unknown name. A variant kind (an upgrade or
  deployment: Torture probe, deployed Mobile Turret, Aramsham conscripts) counts toward its base's share.
- Shared rules (W): melee holds, ranged works behind it (~1 ranged : 2 melee); demolition units break armor and
  structures; drones / support 1-2 early, CP goes to core units late; fighter ships kill little in the field (they
  force anti-air) but bombers / armor-breakers (Harpy, Hammer) and flagships (they tank base missiles) earn their
  place in Siege; flagships (no CP, Guild Favor) at most one.
- **Variety (user):** a player should meet different army loadouts in different games, but only strong ones: each
  faction has a main style (the meta or the transcript comp) and alternatives built on a documented strength (air,
  drones, artillery, a melee wall); the weights favour the main style. Ships, drones and flagships cost Fuel Cells:
  a style that fields them makes its faction value Fuel Cells in the economy (rules/econ.py, map `dfuel`), so it
  builds Fuel Cell Factories / a Fusion Plant instead of starving its upkeep.
- AI-recruitable since 2026-10-24 (data patch, flag bit 0; vanilla's flags left them out): Support Drone, Artillery
  Drone, Railgun Drone, Spire. Flagships of Fremen / Smugglers / Ecaz (Altar, Wraith, Monument) stay out (other
  recruit rules, unchecked).
- **Siege = cracking a main base (2026-10-25, user: the AI re-gears and re-recruits for this one task):** the mode
  starts when the faction commits to a base kill (plan level 2: rules/bkcamp/member.py sets `dsiege`), not at the go, so
  the units are bought and geared before the attack. The columns follow the damage per second against a main
  base's armor 10 (D + C, REVERSING 'Damage per hit': armor is subtracted per hit, minimum 1, and never wears
  down; unit debuffs such as the Grenadier's -2 armor or Stinging Gas hit units only): Fedaykin 5.7, Mobile Turret
  4.0 (deployed it hits air only), Warrior 2.5, Infiltrator 1.0, Skirmisher 0.5; Sniper 5.3 (Propelling Ammo
  +30%), Free Company 4.0 (9 with Dismantling Tools), Scavenger 2.5 (5 with Dismantling Tools), Wrecker 0.5;
  Gunner 3.7 (Heavy Loads +8%), Trooper / Executioner 2.5, Cerberus 1.0; HWS 6.0, Ranger 3.5, Warden 3.0, Trooper
  2.0. A trooper / warrior line (20-30%) stays to hold the defenders and soak the base's guns; flagships tank the
  missiles. Corrino / Ecaz / Vernius keep their earlier Siege columns (burn stacks, not measured yet).
- **Hero:** not in the tables: rules/army.py chooses it and rebuilds it whenever its recruit check passes (user: a
  strong unit).

## Atreides

#### Style Line (45)
Rangers stack behind troopers early (T, W); wardens anchor late; HWS breach; support drones keep the vets alive (T:
support drones in every comp).

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Trooper | 40 | 20 | 20 | 20 |
| Ranger | 35 | 25 | 25 | 30 |
| Heavy Weapon Squad | 15 | 15 | 40 | 10 |
| Support Drone | 10 | 10 | 5 | 15 |
| Warden | 0 | 30 | 5 | 25 |
| Hawk | 0 | 0 | 0 | 0 |
| Kraken | 0 | 0 | 5 | 0 |

#### Style Gun line (30)
Ranger-heavy (W: "rangers are worth stacking"; a couple of wardens + 5-6 heavy / rangers).

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Trooper | 35 | 20 | 15 | 25 |
| Ranger | 55 | 45 | 30 | 45 |
| Heavy Weapon Squad | 10 | 15 | 45 | 10 |
| Support Drone | 0 | 0 | 0 | 0 |
| Warden | 0 | 20 | 5 | 20 |
| Hawk | 0 | 0 | 0 | 0 |
| Kraken | 0 | 0 | 5 | 0 |

#### Style Air cavalry (25)
W: "a couple of wardens, 3 drone ships and 5-6 heavy / rangers": hawks harass the weakened, the Kraken carries the
wounded and tanks a base's missiles.

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Trooper | 40 | 15 | 20 | 20 |
| Ranger | 35 | 25 | 25 | 30 |
| Heavy Weapon Squad | 15 | 15 | 35 | 10 |
| Support Drone | 10 | 10 | 5 | 15 |
| Warden | 0 | 15 | 5 | 20 |
| Hawk | 0 | 20 | 0 | 5 |
| Kraken | 0 | 5 | 10 | 0 |

## Harkonnen

#### Style Meat grinder (55)
Numbers, expendable troopers; gunner splash triggers the troopers' berserk; gunners are the anti-armor (W).

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Trooper | 45 | 30 | 30 | 40 |
| Gunner | 35 | 30 | 50 | 35 |
| Cerberus | 20 | 10 | 0 | 0 |
| Combat Probe | 0 | 0 | 0 | 0 |
| Executioner | 0 | 30 | 15 | 25 |
| Harpy | 0 | 0 | 0 | 0 |
| Overlord | 0 | 0 | 5 | 0 |

#### Style Stealth (20)
Probes and Cerberus for annex / pillage / harvester pokes, executioners late (W theorycraft; probe spam is niche;
probes are 100-health fodder in AI hands: 43 of 70 Harkonnen deaths at 30 / 10, match 2026-10-24 01:48).

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Trooper | 35 | 20 | 30 | 35 |
| Gunner | 20 | 25 | 50 | 30 |
| Cerberus | 15 | 20 | 0 | 10 |
| Combat Probe | 15 | 5 | 0 | 0 |
| Executioner | 0 | 25 | 15 | 25 |
| Harpy | 0 | 0 | 0 | 0 |
| Overlord | 0 | 0 | 5 | 0 |

#### Style Harpy wing (25)
W theorycraft: Harpies (AoE, armor break vs bases) + an Overlord (tanks base missiles), executioners follow up.

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Trooper | 45 | 25 | 25 | 35 |
| Gunner | 35 | 20 | 45 | 30 |
| Cerberus | 20 | 5 | 0 | 0 |
| Combat Probe | 0 | 0 | 0 | 0 |
| Executioner | 0 | 25 | 15 | 25 |
| Harpy | 0 | 20 | 5 | 10 |
| Overlord | 0 | 5 | 10 | 0 |

## Fremen

#### Style Sietch host (60)
Never mass one type (W: the warrior debuff doesn't stack, infiltrators are fragile, Fedaykin lose their buff in big
stacks); late ≈ 2 warriors, 4 mobile turrets, rest Fedaykin (T).

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Warrior | 40 | 20 | 25 | 25 |
| Skirmisher | 25 | 10 | 0 | 10 |
| Infiltrator | 20 | 10 | 0 | 5 |
| Mobile Turret | 15 | 30 | 20 | 40 |
| Fedaykin | 0 | 30 | 55 | 20 |
| Spire | 0 | 0 | 0 | 0 |

#### Style Infiltrators (25)
Dive the enemy ranged line (W: mass infiltrators; good vs sniper comps), cloaked skirmishers for structures.

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Warrior | 30 | 20 | 25 | 30 |
| Skirmisher | 20 | 15 | 0 | 15 |
| Infiltrator | 45 | 35 | 5 | 25 |
| Mobile Turret | 5 | 10 | 15 | 20 |
| Fedaykin | 0 | 20 | 55 | 10 |
| Spire | 0 | 0 | 0 | 0 |

#### Style Desert sky (15)
Spires (Scraps, no Fuel Cells) over a turret line: air the enemy must answer while Fedaykin and skirmishers do the
killing.

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Warrior | 40 | 20 | 25 | 25 |
| Skirmisher | 25 | 15 | 0 | 10 |
| Infiltrator | 20 | 5 | 0 | 5 |
| Mobile Turret | 15 | 20 | 15 | 35 |
| Fedaykin | 0 | 25 | 55 | 15 |
| Spire | 0 | 15 | 5 | 10 |

## Smugglers

#### Style Sniper line (45)
Snipers behind scavengers, 1-2 Free Company as the cleanup crew; drones early only (W).

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Scavenger | 40 | 25 | 25 | 35 |
| Wrecker | 10 | 10 | 0 | 10 |
| Sniper | 35 | 45 | 35 | 45 |
| Scavenging Drone | 15 | 0 | 0 | 0 |
| Free Company | 0 | 20 | 40 | 10 |
| Banshee | 0 | 0 | 0 | 0 |

#### Style Wreckers (25)
Wrecker-heavy (user: some players play it): gas spoils supply and breaks armor, scavengers heal on kills; strongest
for pillage cycles and base kills.

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Scavenger | 40 | 30 | 35 | 40 |
| Wrecker | 40 | 40 | 10 | 30 |
| Sniper | 10 | 10 | 15 | 20 |
| Scavenging Drone | 10 | 0 | 0 | 0 |
| Free Company | 0 | 20 | 40 | 10 |
| Banshee | 0 | 0 | 0 | 0 |

#### Style Brawlers (15)
Melee comp (T: beats Fremen dives where snipers lose; pairs with Bannerjee).

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Scavenger | 55 | 35 | 40 | 45 |
| Wrecker | 20 | 15 | 0 | 15 |
| Sniper | 15 | 15 | 10 | 25 |
| Scavenging Drone | 10 | 0 | 0 | 0 |
| Free Company | 0 | 35 | 50 | 15 |
| Banshee | 0 | 0 | 0 | 0 |

#### Style Salvage fleet (15)
Scavenging drones loot and fight (500 health, 16 power), stealth Banshees scout and harass, snipers cover.

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Scavenger | 40 | 25 | 30 | 35 |
| Wrecker | 10 | 10 | 0 | 10 |
| Sniper | 30 | 30 | 30 | 35 |
| Scavenging Drone | 20 | 15 | 0 | 10 |
| Free Company | 0 | 10 | 30 | 5 |
| Banshee | 0 | 10 | 10 | 5 |

## Corrino

#### Style Legion (40)
Conscript lines with Wensicia, flamers break armor and kill bases, only 1-2 Sardaukar (they compete for executes) (T, W).

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Conscript Swordsman | 45 | 30 | 25 | 35 |
| Conscript Rifleman | 40 | 35 | 20 | 40 |
| Incinerator | 15 | 15 | 30 | 10 |
| Artillery Drone | 0 | 5 | 10 | 5 |
| Sardaukar | 0 | 15 | 10 | 10 |
| Hammer | 0 | 0 | 5 | 0 |
| Cronos | 0 | 0 | 5 | 0 |

#### Style Bombardment (30)
W: ~10 cannon drones from range with a frigate on top vs bases; artillery out-ranges bunkers, Hammers bomb defenses.

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Conscript Swordsman | 45 | 30 | 20 | 35 |
| Conscript Rifleman | 40 | 25 | 15 | 30 |
| Incinerator | 15 | 10 | 15 | 10 |
| Artillery Drone | 0 | 20 | 30 | 15 |
| Sardaukar | 0 | 10 | 5 | 10 |
| Hammer | 0 | 5 | 10 | 0 |
| Cronos | 0 | 0 | 5 | 0 |

#### Style Pyre (30)
User: Corrino's base strategy: enough Incinerators (more than survive the approach) stack the burn on a main base
with the armory's Exotic Compounds (D: burn 50% faster from 2+ incinerators) and Terrifying Mask (less damage taken
per burn stack). The flamer core is built in Late (units change only as they die: they must exist when the assault
starts); Siege replaces losses with more flamers. Conscripts screen, Sardaukar execute.

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Conscript Swordsman | 45 | 30 | 25 | 35 |
| Conscript Rifleman | 35 | 25 | 15 | 35 |
| Incinerator | 20 | 30 | 45 | 15 |
| Artillery Drone | 0 | 0 | 5 | 0 |
| Sardaukar | 0 | 15 | 5 | 15 |
| Hammer | 0 | 0 | 0 | 0 |
| Cronos | 0 | 0 | 5 | 0 |

## Ecaz

#### Style Court (65)
Squires front, musketeers (also stealth detection) behind, war banners strip armor, knights late (W); musketeers are
weak vs main bases.

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Squire | 40 | 25 | 30 | 30 |
| Musketeer | 40 | 35 | 20 | 40 |
| Fencer | 10 | 5 | 5 | 5 |
| War Banner | 10 | 10 | 20 | 10 |
| Knight | 0 | 25 | 25 | 15 |
| Siren | 0 | 0 | 0 | 0 |

#### Style Sky court (35)
W: mechanical ships + knights + musketeers; Sirens are anti-material air.

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Squire | 40 | 20 | 20 | 30 |
| Musketeer | 40 | 30 | 20 | 35 |
| Fencer | 10 | 0 | 0 | 5 |
| War Banner | 10 | 10 | 15 | 10 |
| Knight | 0 | 25 | 25 | 15 |
| Siren | 0 | 15 | 20 | 5 |

## Vernius

#### Style Foundry (60)
Suboids early (cheap), meks lock in melee while railgun drones focus-fire, fight-engineers repair (W: rail-heavy;
weak early, machines late).

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Suboid Soldier | 60 | 10 | 10 | 15 |
| Fighting Mek | 20 | 30 | 25 | 35 |
| Railgun Drone | 0 | 20 | 25 | 15 |
| Resonance Drone | 10 | 15 | 15 | 15 |
| Fight-Engineer | 10 | 25 | 20 | 20 |
| Spirit | 0 | 0 | 0 | 0 |
| Folder Relay | 0 | 0 | 5 | 0 |

#### Style Ghost wing (40)
Camouflaged Spirits screen a rail line; the Folder Relay carries the assault.

| Unit | Early | Late | Siege | Hold |
|---|---|---|---|---|
| Suboid Soldier | 60 | 10 | 10 | 15 |
| Fighting Mek | 20 | 25 | 20 | 30 |
| Railgun Drone | 0 | 25 | 25 | 20 |
| Resonance Drone | 10 | 10 | 10 | 15 |
| Fight-Engineer | 10 | 15 | 15 | 15 |
| Spirit | 0 | 15 | 15 | 5 |
| Folder Relay | 0 | 0 | 5 | 0 |
