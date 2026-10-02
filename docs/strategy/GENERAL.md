# Strategy knowledge: all factions

Expert play knowledge for AI work, distilled from `docs/transcripts/` (tournament player guides and coaching sessions, 2025-26 patch). Not a player guide: each item says what it means for the AI. Implementable work lives in [CANDIDATES.md](CANDIDATES.md) (ids `C#` / `R#`); per-faction detail in the faction files: [Atreides](Atreides.md), [Harkonnen](Harkonnen.md), [Smugglers](Smugglers.md), [Fremen](Fremen.md), [Corrino](Corrino.md), [Ecaz](Ecaz.md), [Vernius](Vernius.md). Armory gear sets and operation priorities per faction: [ARMORY-OPS.md](ARMORY-OPS.md).

**Reliability tags:** **T** = transcript claim (expert opinion, numbers may be off by a patch; verify before coding), **W** = [fandom wiki](https://dunespicewars.fandom.com/wiki/Factions) (descriptive, may lag patches; raw wikitext via `api.php?action=parse&page=<Page>&prop=wikitext&format=json`, the HTML pages answer 402 to fetch tools), **D** = checked in `work/data.original.cdb` (wins over W and T), **C** = checked in code (REVERSING). Untagged lines in the strategy sections are T; untagged lines in "Reference" sections are W.

## Shared rules (W unless tagged)

Mechanics every faction plays by; the faction files list only deviations.

- **Time:** 1 game day ≈ 30 s (derived: D `Pillaged` duration 2700 s = W 90 days). Landsraad Council every 20 days; operations last ~3 days, a spying mission (to acquire one) 3 days, 3 operation slots by default.
- **Hegemony sources:** village 600 (medium map) / 1000 (small map), special region +1000, spice tax paid 1000, completed event 300, crafts workshop 8/day, Research Center main-base building +20% on tax and daily hegemony. Milestones: 2.5k main-base buildings, 5k elite units / air units / major buildings (+ faction bonus), 10k hero (+ faction bonus), 30k win.
- **Siege actions** (owner units in the circle pause progress):

| Action | Neutral village | Enemy village | Result |
|---|---|---|---|
| Annex | 1.5 days | 6 days | ownership; Authority cost below |
| Pillage | 0.5 days, 500 Solari | 2 days, ~1.5k Solari + production-based extras | **Devastated** 20 days (untargetable, -50% production, blocks Peaceful Annex; D); **Pillaged** for the pillager only: +100% Annex Authority for 90 days (D `Pillaged`, val 1, 2700 s) |
| Liberate | – | 6 days | village turns neutral; **Just Freed** 20 days (untargetable) |
| Sietch pillage | 6 days, 3k Solari + 40 Authority | | sietch devastated (no raids); Fremen restore: 150 manpower + 1k Solari + 10 days |

- **Annex Authority cost:** 20 flat + distance 5-100 from the main base + owned-villages term ≈ T × (3.5 + D/6) + enemy-village term ≈ 15 + (D/20) × T (T = villages owned, D = the distance cost); special region +30; then faction / development / Pillaged modifiers. C REVERSING "Annex cost" has the code formula (distance × attribute 952).
- **Conflict / Truce:** Conflict is the default (= `War` in code). A Non-aggression Pact (Influence, cheaper the longer the conflict) gives Truce; not proposable within 10 days of the conflict start; cancelling costs 50 Influence and isn't possible within 10 days of the truce. **Betrayal** (attacking a truce partner's units / main base / villages, a hostile operation on them, or a nuke): -100 Landsraad standing and **Traitor** for 20 days (0 votes, -5 Influence production, -50% spice exchange rate, +20% damage against the betrayed). Faction deviations: Ecaz, Atreides (Jessica), Corrino, Fremen (see files).
- **Sietches:** pillage or ally only (no Annex). Allying needs trading 4 water per trade until relation 100 (≥ 50: no raids on you), then 4 water + (Fremen: 1 Authority; others: an agent, and only in their own territory). Each sietch has one specialty bonus: Arrakis Heart (+2% production per special), Commercial Hub (+10% Solari), Helping Hand (+10% village production), Tool Makers (-20% upkeep), Arrakis Harvesters (200% of the Power of units dying on own land as Solari), Heralds of the Revolution (+50% militia health), Scouts of the Secret Paths (+10% unit health), Training Grounds (-30% recruit time), Arrakis Collectors (+10 Solari per treaty), Fremen Agents (-20% mission cost / prep), Fremen Brotherhood (2 sibling agents), Fremen Scientists (+4 knowledge). Attacking a sietch breaks a truce with Fremen.
- **Militia** (basic): 10 manpower, 2 days, 300 health, 4 armor, power 11, melee; disorganized under 30% health (+2 armor, -50% damage).
- **Nukes:** a Nuclear Silo (not Fremen) loads a warhead for 5k Solari / 10 days; launch costs 500 Landsraad standing, 4000 damage near impact, villages Devastated 5 days + Irradiated (-50% production) 20 days, main bases -50% armor 20 days; the landing marker is visible to all ~half a day ahead; a minimum distance from the silo applies. W notes its use against an annex of your village when close to winning.
- **Operations** (common): Probe Setup 50 intel (reveals a region, advances sietch detection); Defense Sabotage 100 intel, Arrakis 1 (turrets / main base -30% power); Leave Order 100 intel, Landsraad 1 (enemies lose 100 Solari per unit in the region at the end); Supply Drop 100 intel, Guild 1 (+80 supply/day, no supply loss); Scavenger Team 100 intel, CHOAM 1 (25% of dying units' max health as Solari, +20% pillage); Decoy Thumper 200/200, Arrakis 2 (calls a worm here, protects neighbors); EMP Bomb 200/200, Guild 2 (mechanical units, batteries, main bases -50% attack speed, -20% speed); Administrative Burden 500/500, CHOAM 2 (target trains units and builds main-base buildings at -60% speed); Defense Breaches 500/500, Landsraad 2 (target main base +50% damage taken, -3 armor). Difficulty: all 30% detection; agent capture on detection 0 / 20 / 40% (easy / medium / hard). Infiltration Cell 100 intel; Cell Search 200 Solari (only while an assassination on you is detected); Assassination 500 intel + 1000 Solari, needs target info 3 + 1 in each other field.
- **Landsraad:** Great Houses vote by default; Smugglers join at 5k; Fremen don't take part. Charters sit in the middle slot.

**Where the transcripts don't transfer** (check each idea against these before coding):
- They describe 4-player FFA on Dune Medium between skilled humans. Our matches are AI vs AI plus one human, on testbed maps; other player counts, team modes and maps change the specials on offer (they rotate; Polar Sink is a Dune Medium constant), the spawn distances and the "3v1 the leader" dynamics.
- Plays often hinge on a councilor (Piter's cheap ops, Stakhanov's isolation, Jamis' liberation Authority, Paul's sietch Authority). Which councilors an AI faction has is unread (R2); a councilor-dependent idea is a no-op or harmful without that councilor.
- AI difficulty changes start resources and production (`faction@startResourcesByDifficulty`, `baseProductionsByDifficulty`): timings like "main base buildings by month 2" are human-Normal numbers.
- Humans read and exploit fixed behavior. A rule that always fires the same way (always turtle until X, always pressure Y at minute Z) is a free read for the human; keep vanilla's weighted random pick and hysteresis, and prefer graded weights to switches.

## Developments and treaties (W + D)

**Research cost (W):** knowledge for a development = 10 × 1.036^S × (1.036^(t+1) − 1) / 0.036, S = total development steps researched so far, t = the development's tier (T1 → 2). Every development makes all later ones dearer (×1.036 per step). Discounts: a Research Agreement (D: +2 knowledge, +20% research speed on developments the partner has), a Landsraad resolution (cheaper Economy / Military / Statecraft techs), a completed single-slot main-base district (-15% on its tree; the expert "single-slot color = next tree" rule, T).

**Generic tree** (D effects; tier T0-T3; factions replace many nodes, see the faction files). Vanilla picks by data `aiWeights` per AI type (D; selection code unread, presumably like gear / ops).

| Domain | Development (D id) | Effect (D) | AI relevance |
|---|---|---|---|
| Economy T0 | Composite Materials | +10 plascrete; Maintenance Center | opening |
| Economy T1 | Advanced Engineering | +2% village production per building; Mason Guild; Trade Agreement | unlocks a treaty |
| Economy T1 | Modular Parts | +1 crew; Spice Silos; Harvester Works | spice |
| Economy T2 | Geothermal Condensers (`EnergyMarkets`) | fuel cell factories +10 / +5 output, +10% village production with one | water / fuel |
| Economy T2 | Insulated Valley (`EconomicLobbying`) | low-wind villages: buildings -30% Solari upkeep, -1 water | upkeep |
| Economy T2 | Riches of Arrakis | +10 Solari and +2% Solari per special | specials |
| Economy T2 | CHOAM Integration (`GridexPlane`) | next spice rate visible; CHOAM Branch; +1 CHOAM agent | CHOAM |
| Economy T3 | CHOAM Support (`StructuredWarehouses`) | shares -15% buy price, +0.1 Solari rate per share | CHOAM win |
| Economy T3 | Crew Training Program (`VeteranCrews`) | +2 crew, +20% spice | spice |
| Military T0 | Survival Training | Armory (gear slot 1); Military Base | gear (ARMORY-OPS) |
| Military T1 | Army Logistics | +10 water; gear slot 2 (generic; replaced for Corrino, Vernius at T1, Smugglers / Fremen at T2, Harkonnen at T3) | gear |
| Military T1 | Mechanization (`DefenseSystems`) | Fusion Plant; each faction's drone unit | comp |
| Military T1 | Recruitment Initiative (`CalltoArms`) | +5 CP, +20% manpower; Command Post | army size |
| Military T2 | Energy Efficiency (`MilitaryThreat`) | +30% fuel cells, mech units -1 fuel | mech |
| Military T2 | Parallel Training (`GroundCommand`) | +2 training slots; Military Academy; +1 Guild agent | remax speed; Vernius obfuscation target |
| Military T3 | **Siege Incentives** (`SupportStructures`) | +50% damage vs main bases; Solari per main-base damage | base kills (ARMORY-OPS Siege set) |
| Military T3 | Parts Production (`AirCommand`) | mech +20% health, regen ×1.5, -30% regen cost | mech |
| Military T3 | Military Propaganda (`HighCommand`) | +10 CP; +20% Authority while no faction fields more CP | Authority |
| Statecraft T0 | Intelligence Network | +10 standing per council when a resolution goes our way; agent recruitment ×2 | – |
| Statecraft T1 | Diplomatic Maneuvers (`DiplomaticManoeuvers`) | Minor Houses donation after each council; Political Agreement; Landsraad Quarters | unlocks a treaty |
| Statecraft T1 | Spying Logistics (`SpyingLogistic`) | assassins; agent recruitment ×3; Intelligence Agency | experts take it early (T) |
| Statecraft T2 | Counter Measures | Landsraad soldiers per Influence spent (≤ 100); +1 counter-intel slot | assassination defence |
| Statecraft T2 | Landsraad Support (`PoliticalStrength`) | +50 max Influence per Landsraad agent; +1 slot | politics |
| Statecraft T2 | Nefarious Contacts (`NegotiationTactics`) | assassins -50% cost; +1 infiltration cell | assassination |
| Statecraft T2 | Stealth Gear | 20% intel refund on ops in an enemy's land; enemy detection × 0.5 | ops |
| Statecraft T3 | Insider Trading (`SandDiplomacy`) | shares sell ×1.2, +1 Influence per share sold | CHOAM |
| Statecraft T3 | Spying Mastery | agent recruitment penalty per agent ×0.5; +5 max agents | agents |
| Expansion T0 | Local Dialect Studies | Annex cost ×0.85; +1 water per village | expansion |
| Expansion T1 | Lay of the Land (`LayoftheLand`) | +0.5 knowledge per village; Research Agreement | experts take it early (T) |
| Expansion T1 | Local Hubs | village buildings -15% Solari / plascrete; Investment Office | economy |
| Expansion T1 | Native Customs (`Paracompass`) | +20% Authority from Arrakis agents; sietch-zone villages Annex ×0.7 | Authority |
| Expansion T2 | **Outpost Logistics** | owned-village Annex cost term ×0.7; +1 Arrakis agent | the late-game capture enabler (T) |
| Expansion T2 | Valuable Trinkets (`WaterSellersContacts`) | sietch trade ×2; **Crafts Workshop** | passive hegemony |
| Expansion T2 | Civilian Defense Force (`SpectralImaging`) | +1 militia slot, militia +150 health; airfield upkeep -50% | defense |
| Expansion T3 | Border Defense | +1 MissileBattery per village, militia +1 armor | defense (turret-steer's battery cap) |
| Expansion T3 | **Wonders of the Desert** (`WaterTrade`) | specials +30% production, Crafts +30%, no special-region Annex penalty | specials / hegemony |

**Treaties (D, W):**

| Treaty (D id) | Needs | Cost | Effect |
|---|---|---|---|
| Non-aggression Pact (`ImproveRelations`) | Conflict | 150 Influence (D; cheaper the longer the conflict, W) | Truce; **breaks current sieges**; +4 standing per council while active; breaking the truce in any way cancels all other treaties and returns to War (D) |
| Research Agreement | Truce, Lay of the Land | 10 Authority | +2 knowledge, +20% research speed on developments the partner has |
| Trade Agreement | Truce, Advanced Engineering | 10 Authority | +3 Solari per village, +3% Solari |
| Political Agreement | Truce, Diplomatic Maneuvers | 10 Authority | +2 Influence, treaty upkeep ×0.8 |
| Upkeep of each of the three above | – | – | **-10% Authority production per treaty** (D trait `TreatyUpkeep`); Atreides with Jessica: none |
| Imperial Mandate | Corrino, 5k | 500 Solari | 2 Sardaukar lent for 2 months; Corrino +50 Solari per kill by the receiver |
| Harmless Gadget | Vernius | 100 Solari | receiver loses 10 standing, gets an Analytical Machine agent (Vernius +1 info level on it) |
| Tributary (`MilitaryPressure`) | – | 100 Influence, 30-day cooldown, not to Corrino | cancels a NAP; relationship -50 (other effects unread) |
| Guarantee of Safety (`AssassinationTreaty`) | any status | force cost 500 Influence | cancels an assassination |

AI relevance: every economic treaty costs 10% of Authority income, so a faction with several treaties expands slower (check the treaty count when an AI is Authority-starved, e.g. the Atreides 28-minute Annex gap); a NAP cancels running sieges between the two (built: treaty scope); Guarantee of Safety is a paid answer to an assassination whose cells we can't find.

## Core principle: biases with overrides, not locks

Every faction can win on every condition and has to be able to hit an enemy on its own territory to stop that enemy from winning. A faction profile therefore changes **how much a choice is worth and how much margin it needs**, not whether the choice exists. In AI-POLICY terms a profile is a multiplier on the one ratio / one score (like the terrain factor), not a gate.

- **Comfort zone → ratio modifier.** Where a faction fights well (Vernius next to its nodes, Atreides and Harkonnen on their land, Fremen on sand in stealth) its power counts more; where it fights badly, less. Its armies then still attack outside the comfort zone, with more margin (C14).
- **Phase defaults expire on triggers.** "Turtle early" (Corrino, Ecaz, Vernius) holds until a milestone (5k / Border Defense) or an override; "pressure early" (Smugglers, Harkonnen, Fremen) fades once the target has its defensive tech.
- **Overrides** (each one lifts a profile bias; they don't lift supply budget or goal 1-2 survival rules):

| Id | Trigger | Effect |
|---|---|---|
| O1 Stop a win | an at-war faction is within one spice tax of 30k hegemony, near 50% CHOAM, or on a Governor countdown (R5) | its villages and armies get top value for everyone at war with it; offensive entry ratio relaxes from ENTER toward KEEP; comfort penalties waived (C6) |
| O2 Defend | our structure besieged | AI-POLICY goal 2 (built) outranks every profile |
| O3 Opportunity | the target's armies are wiped, far away, or tied up elsewhere, and our force passes KILL × at the target | comfort penalties waived (a 65 vs 40 CP fight snowballs: Lanchester) |
| O4 We lead | we lead hegemony by ≥ LEAD_GAP or are within one tax of 30k | expect containment: keep a home reserve, prefer holding to risky raids, protect close-out villages (C15) |
| O5 Stop a base kill | a leader is killing a third faction's main base (Corrino gets a 3rd base, Fremen a deep desert, the killer the specials) | that siege becomes a contest target for us even when not near our land (R5 for "leader") |

## Tiers and timing (meta consensus)

Smugglers S (no weak phase, best army micro, Comms Jam), Atreides ≈ Corrino A (Atreides: peaceful annex + ceasefire closes games; Corrino: quirk economy, strongest army mid/late), Harkonnen B (strong army and ops, weaker passive hegemony), Fremen / Ecaz / Vernius C-D (Fremen: no airfield / nuke, weak late mobility; Ecaz and Vernius: very weak early). Weak-early factions (Corrino, Ecaz, Vernius, partly Atreides) can be killed in month 2-3 by an aggressive neighbor (Smugglers, Harkonnen, Fremen) unless someone bails them out. Experts mostly don't do it: the aggressor falls behind the other two players while it fights (that cost is the counterweight to C7).

## Game phases (hegemony)

| Hegemony | What happens | AI relevance |
|---|---|---|
| 0-2.5k | 2-3 villages (spice, plascrete, fuel cell), pillage the rest, scout with 3-6 ornithopters | opening: built (`siege-join` EARLY_REQ, spice × 2) |
| 2.5k / first tax | main base buildings unlock: experts build one as soon as 1000 Solari + 500 Plascrete exist, ahead of more harvesters or villages | C10 |
| 5k | elite units, air units, major buildings; faction 5k bonus (W: Corrino main-base deployment, Vernius patents / tech skip, Ecaz champion + garden, Fremen deep-desert control + thumper regeneration, Smugglers Landsraad seat + bounties, Harkonnen intel per pillage, Atreides resolution bonuses) | R4 |
| 10k | hero; faction 10k bonus (W: Smugglers main-base UHQs + 50% pillage, Vernius obfuscation, Fremen sietch main-base building, Corrino 2nd deployment by base kill, Ecaz votes / Solari, Harkonnen agent bonuses, Atreides charter rule) | R4 |
| 15-23k mid game | craft workshops (passive hegemony), bunkers, choose a win condition | C6 |
| 23-30k late game | the leader gets 3v1'd; close-out: banked Authority + "back-cap" villages captured right before a spice tax | C13, O1, O4 |

## Win conditions

- **Hegemony 30k** is the main one; going CHOAM or Governor while staying in the hegemony race is the expert default, because a hegemony leader can end the game first.
- Passive hegemony = craft workshops (Harkonnen: Symbols of Authority instead; Smugglers: +1 per UHQ). Special regions host craft workshops; Scholarly on a special is the best passive source.
- **Close-out pattern:** keep 2-4 cheap captures in a safe backline (pillaged neutrals, blank villages; Harkonnen: instill-feared villages; Ecaz: sanctuaries), bank enough Authority for them (but don't sit at the 500 cap), capture them together + spice tax + a quest → over 30k before the others react. Counters: nuke the capture (irradiated 4 days, T), ceasefire, liberation, assassination forcing village abandonment. Edge cases: a capture finishing after the tax misses it; a nuke dropped late can be beaten by re-entering the capture circle as the capture unwinds (T).
- **CHOAM:** 50% of shares wins; Harkonnen and Smugglers are the best at it. ≥ 30% is worth holding anyway (votes; Corrino: military buff, D `CHOAMManipulation`). Each tax dilutes shares; a CHOAM leader loses % at every tax unless it keeps buying.
- **Governor (Landsraad):** the weakest condition; Ecaz (Vip immunity + charter lock) and Corrino (base votes) are the threats.

## Economy rules of thumb

- Plascrete is the early bottleneck and nearly worthless late (experts delete plascrete factories late to cut upkeep). Knowledge drives everything; "Lay of the Land" is taken early by every faction that has it.
- Main base buildings outrank harvesters and new villages. The single-slot building's color grants a research bonus to that tree: experts research the tree matching the building they just finished.
- Authority: sitting at the 500 cap wastes income (C1), except while saving for a planned close-out (C13). The Arrakis information field gets agents first (intendant / mentat traits there).
- Pillage gives Solari (Harkonnen: intel past 5k). Pillaging a village makes **our own** Annex of it cost +100% Authority for 90 days (D `Pillaged`, pillager only) and makes it untargetable for 20 days (Devastated); exceptions: Harkonnen with Instill Fear (no +100%, and -10% per pillage, stacking to 9: D), Smugglers with Illicit Methods (D `AegisoftheUnderworld`: penalty × 0). A third faction isn't taxed by our pillage, so pillaging a village we want can hand it to a neighbor (C2 edge).
- Running a Solari deficit stops research and can delete buildings (T); Fremen and Ecaz run near it all game.
- Spice tax: missing it is catastrophic; the exchange rate decides when to sell spice / buy CHOAM.

## Expansion

- **Bunker:** two or three villages close together share turrets (built: bunker score, `turret-steer`).
- **Contact villages** are fought over (built: tension).
- **Specials** (W: each +1000 hegemony when owned, +30 Authority to annex, the only place for Crafts Workshops; value differs per faction, C4). Specials rotate per map; risk depends on the actual spawn, not the region's usual place. W effects: Acid Lakes ground units -10% health/day; Worm Nest military units attract worms 50% faster; Moon Dew Vale (= "Mundu Veil") supply loss -50%, buildings use no water; Desolation +400% supply drain, -40% health/day, -40% speed, unownable; Space Wreck also spawns a wreck discovery periodically:

| Region | Bonus (T) | Best for | Typical risk |
|---|---|---|---|
| White Rift | 2× craft workshop production | all, Corrino most | its owner becomes a target |
| Sandfall | 6% of village upkeep as knowledge | all (put expensive buildings there) | usually backline |
| Worm's Nest | +25% spice; military units attract worms 50% faster (W: hurts any army parked there, attackers most) | all | low |
| Acid Lakes | 2× research hub; units on it lose 10% health/day unless in the owned village | a defensive bunker | hard to retake, also for us |
| Mount Idaho | 2× plascrete factory | early game | – |
| Observatory Mountain | listening post / data center without a neighbor | early intel / influence | – |
| Great Volcano | extra fuel cells; Fremen ceremonial cave 10% | Fremen, Corrino, Vernius | – |
| Polar Sink | water extractor +25 water (not Fremen); supply bubble in the middle | water-hungry (Atreides, Harkonnen), staging point | center: contested by everyone |
| Imperial Basin | 2× recruitment office | Smugglers | center, next to Polar Sink |
| Mundu Veil | -50% supply loss, buildings use no water | Fremen (recycling plant costs 10 water), Smugglers | usually backline |
| Shield Wall | -50% upkeep | low | center |
| Spacing Cruiser Wreck | +1 guild parts | Fremen (start with 0 parts) | – |
| Crescent Ridge | water per wind | Fremen (windtraps), water-short factions | low value |
| Well of Riches | 2× processing plant | low (Corrino with quirks) | – |
| Desolation | uncapturable, -40 health/day, -40% speed | protects a flank; a pathing obstacle | – |

- **Quirks** (2 per village; Investment Office doubles; Corrino up to ×5): best overall Versatile, Ingenious Minds (on spice / rare elements), Hard Workers, Scientists, Scholarly (on specials), Strong Network, Youthful Eagerness, Handymen (early). Building layout per quirk is out of scope (CANDIDATES "Rejected"); a quirk-value term in the Annex score is a possible later item.

## Combat knowledge

- Vetted units win; factions with tanky vetted armies (Atreides, Ecaz) lose a lot when they trade them early. Harkonnen armies are cheap to replace (fast re-recruit) and accept losses.
- Re-recruit while the fight runs, at the rally point nearest the fight.
- Own turrets / nodes multiply a defender; attacking under enemy turrets needs margin, a flagship to tank, or artillery (built: cover sizing). Under O1 a bunker attack can still be right.
- Kill the airfield first when attacking a region: it cuts reinforcement (tactical, out of scope).
- Worms: walk on rock; thumpers / decoy thumpers lock regions (built: worm reaction).
- Supply drop keeps an army in the field; running out of water wipes armies (built: supply budget).
- Stealth units (Fremen on own land, Smugglers Free Company, Vernius engineers via Satar) need a probe / scan. D: `MProbeSetup` is `aiProhibited` for every AI type and weighted -10, so no AI scans (R1).
- Nuke: D: `NukeTargeting` is aiProhibited for Economy / Military / Statecraft AI types; whether an Expansion-type AI nukes is unchecked.

## Diplomacy and politics

- Truce partners don't fight; breaking a truce (betrayal) costs Landsraad standing (Fremen: a spice-rate penalty instead) and grants a damage bonus.
- Vernius truce = its tech for free: lobbies tend to keep Vernius alive and trused; a faction at war with it loses that (weigh against C7).
- Atreides (Jessica) force truces; Atreides treaties carry no Authority cost, so they are accepted widely.
- Leader containment: whoever leads hegemony by ~3-4k or is about to close is attacked by the others; advancing your own win condition while "helping" breaks lobby trust (human lobbies). C6, O1, O4.
- Kill vs keep: killing a faction gives Corrino a third base, Fremen a deep desert, the killer the specials; the others usually stop a base kill by the leader (O5).

## Espionage

- Agents: Arrakis field (Authority) first; assassination needs info level 3 on the target + 1 everywhere, infiltration cells, 500 intel + refreshes. Defence: monitoring station + missile turret (kill assassins), counter-intel agents, cell search (searches a region + its neighbours), abandoning villages near the end. Harkonnen sacrificed-agent assassination is undetectable to 50%.
- AI scope: assassination offence is rejected (CANDIDATES); a cell-search response belongs to R1. Edge: a faction with many spread villages (Fremen, Vernius, Ecaz) needs several searches; abandoning a village to survive costs hegemony, which matters under O4.
