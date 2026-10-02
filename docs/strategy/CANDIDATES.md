# Implementation candidates from expert play

Ideas from [GENERAL.md](GENERAL.md) and the faction files, filtered for the AI. AI-POLICY applies: **evidence first** (§1.1): each item names the log failure that justifies it; build it once a match shows that failure. When one is built, move it to progress.md "Verify" and delete it here.

Every item is a **bias** (weight or ratio modifier) with exits, per GENERAL "Core principle"; overrides O1-O5 are defined there. **Size:** S = a value / filter change inside an existing rule; M = a new rule on hooks we have; L = needs reversing or touches the tactical layer. **Clash** = the AI-POLICY section and rule it touches.

## Ready (S / M, existing hooks)

### C1 Authority near the cap · all · S
- **Idea:** at Authority ≥ AUTH_HI 450 (cap 500), `aswap` takes the best affordable candidate at once instead of waiting ASWAP_WAIT. Hook: `siege.py` aswap (`aswt`).
- **Evidence:** `Stocks` rows at 480-500 Authority with no Annex launched for 2+ min. The opposite failure (Authority-starved) has a known cause to check first: each economic treaty costs -10% Authority production (GENERAL "Developments and treaties").
- **Exits:** a running close-out plan (C13) reserves its Authority; C1 counts only Authority above that reserve.
- **Edge cases:** the best affordable can be a poor village (a junk capture is still better than wasted income, but the lone-candidate filter and spacing gate still apply); Authority can sit high because every candidate is blocked (spacing, `exposed`, stuck): then C1 changes nothing, and the log should say why (`space` / `stuck` rows).
- **Clash:** same aswap mechanism, only the wait changes (§5a Expansion).

### C2 Pillage-cost-aware raids · Harkonnen, Smugglers · S
- **Idea:** factions whose pillage cheapens or doesn't tax a later Annex (Harkonnen `InstillFear`, Smugglers Illicit Methods) may raid their own top-3 Annex picks; the others keep the RAID_KEEP exclusion. Hook: `raid` candidate filter.
- **Evidence:** Harkonnen / Smugglers raids skipping next-door villages they later annex at full cost.
- **Exits:** a village the faction plans to capture within its recovery time (close-out C13, press) is skipped: a devastated village can't be captured until it recovers.
- **Edge cases:** D-confirmed effects: Harkonnen development `InstillFear` blocks the +100% `Pillaged` cost and stacks -10% per pillage (×9); Smugglers `AegisoftheUnderworld` (Illicit Methods) sets the pillage penalty × 0. Before the development, a pillage doubles our own Annex cost for 90 days (D `Pillaged`): check the development, not the faction. A pillaged village is untargetable for 20 days (D `Devastated`), so the next capture waits; it also blocks Atreides' Peaceful Annex for those 20 days (D), a side benefit next to Atreides.
- **Clash:** one filter; raid sizing and aborts unchanged (§5a Raid).

### C3 Atreides village pillage check · Atreides · S
- **Idea:** W: Atreides "cannot pillage **neutral** villages" (enemy villages and sietches are allowed; the Pel-Al'ram raid on a Fremen village 49:10 was legal). Drop neutral villages from Atreides' raid candidates; check whether vanilla's pillage list already excludes them (the raid lifts vanilla's gates, so it may re-add them).
- **Evidence:** Atreides raid rows on a neutral village whose order ends `Invalid` or doesn't reach Action.
- **Edge cases:** the rule's data source isn't found yet (not in `siegeAction.Pillage`; look for an Atreides attribute / condition before coding); a neutral village pillaged by us would also block our own Peaceful Annex of it for 20 days (D `Devastated`), so excluding neutrals is right for Atreides either way.
- **Clash:** a filter, no behavior change elsewhere.

### C4 Per-faction special values · all · S
- **Idea:** replace the flat +30 special bonus in the Annex value with a faction × region table (GENERAL "Specials"). Hook: `_annex_value` (ANNEX_SPECIAL); region ids from the `region` sheet.
- **Evidence:** which specials each faction takes vs the table (baseline from 2-3 logs).
- **Edge cases:** a special's risk depends on the map (Polar Sink and Imperial Basin are central on Dune Medium, not necessarily elsewhere): use the existing threat / compactness terms for risk, the table for value only; a value high enough to drag a faction across the map is capped by the compactness term (not for Smugglers: cap the table bonus instead).
- **Clash:** value tuning only.

### C5 Harkonnen sietch timing · Harkonnen · S
- **Idea:** Savage Cleansing (D development `MonitoringNetworks`) pays Harkonnen +100 Authority the first time each sietch is pillaged (W: and reveals another sietch); every sietch pillage pays 3k Solari + 40 Authority (W). Before the development, sietch strikes score × 0.7; after it, a not-yet-pillaged sietch is worth its Authority when Authority ≤ 360 (room for 140), or when a close-out needs it. Hook: sietch strike gate (`annex-spacing` 1b).
- **Evidence:** Harkonnen PillageSietch before the tech; Authority overflow right after a strike.
- **Exits:** a sietch whose raiders threaten our villages, or a quest needing it, goes at normal value.
- **Edge cases:** others (Smugglers, Fremen enemies) may pillage the sietch first: a saved sietch is a bet, so the delay is a weight, not a hold; a sietch allied to Fremen is defended by Fremen raiders (sizing already counts militia).
- **Clash:** a condition on an existing gate (§5a launch gate).

### C6 Leader containment · all · M (needs R5)
- **Idea:** two tiers. (a) A faction leading hegemony by ≥ LEAD_GAP 3k gets × LEAD_W on raid / press / hunt scores from every faction at war with it, growing with the lead. (b) O1: within one tax of 30k (or near 50% CHOAM, Governor countdown): its villages get top value, entry ratio relaxes ENTER → KEEP, our peace offers to it stop, and its back-cap villages (pillaged / neutral villages in its backline) become raid targets to deny the close-out. Hooks: `raid` score, `strat` press choice, hunt score.
- **Evidence:** a leader closing out while the others idle or fight each other.
- **Exits:** the lead drops under LEAD_GAP × 0.75 (hysteresis); goal 2 defense first (O2); supply budget unchanged.
- **Edge cases:** the leader is us (then O4 / C15 instead); two factions within the gap (weight both by lead); the leader is a truce partner (no attack under truce; tension step 3 decides whether to break it); the leader is the human (same rule: humans are the most likely closers); a leader across the map out of supply range (raids can't reach; weight only reachable targets, don't drag armies across the map); hegemony estimates for humans are exact in game data, so no "hidden" leader issue.
- **Clash:** one weight on existing scores; ratio relaxation stays above KEEP (§4).

### C7 Early pressure on weak-early neighbors · Smugglers, Harkonnen, Fremen · M
- **Idea:** these three relax the press softness PRESS → ENTER on Corrino / Ecaz / Vernius villages before the target's milestone (5k; Vernius `AutomatedDefenses`). Hook: `strat` press (B(E), softness).
- **Evidence:** aggressive factions idle in months 1-3 next to a weak Corrino / Ecaz / Vernius at war with them.
- **Exits:** the target gets its milestone tech; our own posture is defend / recover; a third faction pulls ahead (C6) and fighting here would hand it the game.
- **Edge cases:** needs an at-war status (vanilla desiredStatus is often peace; this rule doesn't declare war: tension step 3 territory); a target turtled under its main-base turret (cover sizing keeps us off it; pillage around it instead); pressure on Vernius loses its tech truce (only applies while at war anyway); a human Corrino may bait with a weak-looking village under turrets (cover sizing).
- **Clash:** per-pair threshold; posture order and supply rules still win (§5b).

### C8 Weak-early caution · Corrino, Ecaz, Vernius · S
- **Idea:** before their milestone, raids beyond LOCAL from their land need RAID_FAR × 1.3 force, and villages within main-base turret reach score × 1.2 in the Annex value. Hooks: `raid` launch test, `_annex_value`.
- **Evidence:** early raids by these factions losing armies far from home.
- **Exits:** milestone reached; O1 (someone is about to win), O3 (the target's army is gone).
- **Edge cases:** a spawn with no villages near the main base (the × 1.2 just reorders; no ban); turtling hands the map to a human neighbor (graded margin keeps cheap opportunities open).
- **Clash:** margin only (§5a goal 1-2 first).

### C9 Vernius nodes as turrets · against Vernius · S
- **Idea:** confirm `aimod_cover` counts armed neural nodes (W: Automated Defenses makes connected nodes rapid-fire single-target defenses and adds 2 Automated Militia per connected village; D development `AutomatedDefenses`, traits `T_NeuralNodeAttack`, `Vernius_NeuralNode_Prism`). Cover sums structure combat stats with power, so it may already; militia sizing should see the extra militia. If not, add them.
- **Evidence:** sieges on Vernius villages sized without node fire, then lost.
- **Edge cases:** nodes in a different zone than the village (cover is distance-based, fine); W: only **connected** nodes shoot, so a node cut off from the network stops (and its village produces -50%): cutting the chain first is the cheap attack.
- **Clash:** improves the one cover measure (§1.3).

### C10 Main base buildings first · all · M
- **Idea:** in the building-score wrapper (`turret-steer` site) lift main base buildings above village buildings while Solari ≥ 1000, Plascrete ≥ 500 and a slot is free. Hook: `rules/build.py`.
- **Evidence:** add the main-base building count to the `Stocks` snapshot first; build this if slots stay empty with resources banked.
- **Exits:** a structure under threat (turret-steer's MissileBattery keeps its priority); a Solari deficit.
- **Edge cases:** vanilla may skip main-base buildings in that scoring call (`includeMB` flag): check before tuning; upkeep of a main-base building can push a poor faction (Fremen, Ecaz) into deficit.
- **Clash:** same wrapper, another building class.

### C11 Fremen liberation over pillage · Fremen · M
- **Idea:** a Fremen raid on an at-war village issues Liberate when the force can hold it for the 6 days (W: +500 Solari with Freedom Fighters, +70 Authority with Jamis, Stalwart Alliance raids from allied sietches next to it). Hook: `raid` order kind.
- **Evidence:** Fremen raids that pillage at-war villages where a liberation was affordable and safe.
- **Exits:** relief arrives before the liberation completes (raid `weak` / `home` aborts apply); pillage is chosen when the village is next to a third faction that would annex the liberated (neutral) village before us.
- **Edge cases:** liberation takes 6 days vs pillage 2 (Stakkanov villages twice that; Atreides villages +10%); the owner's units in the circle pause it (W); the result is Just Freed for 20 days (untargetable, W), then neutral and annexable by anyone, including an Atreides Peaceful Annex; without Freedom Fighters / Jamis the gain is mostly denial.
- **Clash:** raid sizing / aborts unchanged.

### C12 Ecaz pre-sanctuary pillage · Ecaz · M
- **Idea:** raid prefers neutral villages about to become Ecaz sanctuaries: a neutral pillage pays 500 Solari (W) and can repeat every 20 days, a sanctuary's Tax Collection 300 every 30 days (W); W: a sanctuary forms when a neutral village is surrounded by Ecaz regions, mountains, deep desert, the Desolation or the map edge (D traits `Ecaz_Eligible_Sanctuary` / `Ecaz_SanctuaryEligibility`). Hook: `raid` score.
- **Evidence:** Ecaz sanctuaries made from villages with no pillage before.
- **Edge cases:** read eligibility from the trait, not geometry; whether a devastated village can become a sanctuary is *unverified*; raids of a neutral village by Ecaz don't touch the Pillaged cost unless Ecaz annexes it later (sanctuaries are annexed at the close-out: the +100% would hit then if within 90 days).
- **Clash:** score weight only.

### C13 Close-out spike · all · M-L (needs R5)
- **Idea:** when hegemony + next tax + Σ hegemony of affordable captures + quest rewards ≥ 30k, reserve that Authority and launch those captures together so they finish just before the tax. The spacing gate exempts them.
- **Evidence:** an AI ending within reach of 30k with banked Authority.
- **Exits:** a capture is lost or nuked (re-plan); the tax would come before completion (wait for the next one, keep the reserve).
- **Edge cases:** W values: village 600 (medium map) / 1000 (small map), special +1000, tax 1000 (+20% with a Research Center), event 300 (R5 still has to read them live and confirm per map); captures finishing after the tax miss it; an O1 coalition against us (O4: hold a reserve at home); captures need armies free at the same time (Atreides peaceful annex doesn't).
- **Clash:** the spacing / `exposed` exemption has to be explicit; C1 respects the reserve.

### C14 Faction comfort profile · all · M
- **Idea:** a per-faction factor in the one ratio, like terrain: Vernius × 1.25 own power in or next to a noded zone and × 0.85 away from it; Atreides own land (vet militia, support drones); Harkonnen with an own op active in the zone (needs R1); Fremen on sand in stealth. Applies to entry and keep alike (§1.4), so overrides work by raising stakes (O1) or margin (O3), not by special cases.
- **Evidence:** fight outcomes by location per faction (`fight` rows: me% / them% vs where); a faction losing most fights off its comfort zone, or idling inside it.
- **Edge cases:** factor values are guesses until logs calibrate them; a factor that is too strong makes the faction passive (check that its offensive count stays near vanilla's); combined with terrain, the product gets a cap (a new constant) so it can't make a fight look free.
- **Clash:** extends the terrain factor (§4 ratios); one measure for start / keep.

### C15 Leader posture · all · M (needs R5)
- **Idea:** O4: while we lead by ≥ LEAD_GAP or are within one tax of 30k, `strat` holds a home reserve (spare force minus RESERVE_W × `aimod_home`), raids need the home race at enter × 1.3, and close-out villages are kept unpillaged by us and guarded.
- **Evidence:** a leading AI losing its lead to a 2-3 faction attack while its armies were out raiding.
- **Exits:** lead drops; a single attacker is weaker than our reserve (then normal posture).
- **Edge cases:** too much reserve = no close-out (the C13 plan is exempt); a leader that only defends lets the others catch up on passive income.
- **Clash:** a weight inside strat's spare-force formula (§5b).

### C16 Armory gear sets · all · S (data) → M (modes)
- **Idea:** stage 1 (data only): give each faction's Field-set gear an `aiWeights` value in `patches/data.json` (no aiType → every AI type), so vanilla's `checkEquipments` stops picking randomly among zero-score ties. Stage 2 (code): wrap the gear score closure (f@41010) to add +SET_W for gear in the active set (Field / Siege / Hold, [ARMORY-OPS.md](ARMORY-OPS.md)) and -SET_W off it; the set comes from `strat` posture / O1 / O4 with SET_HOLD hysteresis, plus counter swaps (anti-air, Shadow Scan, anti-mech) from the enemy army mix.
- **Evidence:** log the gear per unit kind in the `Stocks` snapshot first; stage 1 when the logged gear is visibly random (e.g. Ecaz knights without Heroism, Smugglers snipers without Barrel Cleaner); stage 2 when a siege / base attack fails against turrets with Field gear.
- **Exits:** a set's trigger off for SET_HOLD; Solari below changes × 500 + reserve (no switch).
- **Edge cases:** gear is faction-wide (one set for every army); fuel-cell gear can be unaffordable (then the next in-set gear); stage-1 weights alone also pick the Field set at home; vanilla's combo bonus / malus (`valueCache[1027]` / `[1028]`) still applies on top.
- **Clash:** economy-side; no combat rule reads gear. The data patch keeps row order / ids (only `aiWeights` values).

### C17 Operation priorities · all · M (needs the launch hook)
- **Idea:** acquisition: data `aiWeights` for each faction's priority ops (ARMORY-OPS "Operation priorities"), Supply Drop weighted for every AI type except Vernius. Launch: for ops with no vanilla path (Orbital Strike, Toxic Vapors outside Liberation, Hidden Thumpers, Hidden Backdoor, Elacca Fog, Epic Quest, Ambient Connection, Extraction Network, Defense Breaches outside Raze), our rules launch them at their trigger: our fight at balance 0.5-1.5 (combat ops), our siege on a main base / bunker (Defense Sabotage / Breaches, Orbital), a losing army that can't retreat (Extraction Network), our besieged village (Cease Fire, Toxic Vapors on the attackers).
- **Evidence:** `Stocks` / op log: ops held unused for many days; fights / sieges lost that a held op would have swung.
- **Exits:** op cost above the faction's Solari / intel reserve; a Comms Jam active in the region (W: blocks ops 3 days).
- **Edge cases:** all-faction ops (Elacca Fog, Comms Jam) hit us too; Orbital damages our units in the area; launch API is `useAbilityOn(op.getAbility().id, args)` like vanilla's f@8609 (args per op type: zone or struct); ops last ~3 days, so timing with the army's arrival matters.
- **Clash:** a new launcher beside vanilla's; only for ops vanilla has no launch path for, so no double use.

## Research first (unlocks several items)

| Id | Question | Unlocks |
|---|---|---|
| R1 | **Operations (mostly read, ARMORY-OPS "How vanilla does it"):** acquisition = data `aiWeights`; launch = 18 hand-written cases in `Spying.tryLaunchOperation` f@8609 + per-gauge order lists f@8406 / f@8407; 13 ops have no launch path. Left: why `tryLaunchOperationFromOrder` always returns False, and the args each op's ability expects | C17 |
| R2 | **AI type and councilors:** what sets a faction's AI type (Economy / Military / Statecraft / Expansion) and which councilors the AI gets | councilor-dependent items (Stakhanov isolation, Piter cheap ops, Jamis liberation Authority, Paul sietch Authority, Fenring POIs, Kudu) |
| R3 | **Diplomacy offers:** how the AI offers / accepts truces and treaties (also Next: peace gate part 2) | Vernius truces for tech, keeping Vernius trused, leader-containment alliances, C6 "no peace to the closer" |
| R4 | **Faction abilities:** does vanilla AI call each faction-only ability? (D: `DeployMainBase`, `Oppression`, `Sanctify` / `EcazChampion` / `EcazPride`, `PatentDev` / `BlackoutDev` / `NetworkNexus`, `RestoreSietch`, `InstallUWHeadquarter`, `Hasten*`). `mod find` each id for an AI caller; an uncalled one is a large gap | Corrino 2nd base, Vernius patents / obfuscation, Ecaz champions |
| R5 | **Hegemony and tax reads:** per-faction hegemony, the victory threshold, time to the next spice tax, CHOAM %, Governor countdown (W gives the per-capture values: GENERAL "Shared rules") | C6, C13, C15, O1, O4, O5 |
| R6 | **Militia and recruitment:** how the AI fills militia slots and re-recruits during fights | Harkonnen militia in every village, re-recruit during a fight |

## Interactions to keep consistent

- **C1 ↔ C13:** C13's reserve is protected from C1.
- **C2 ↔ C13:** a planned capture isn't pillaged inside its recovery window.
- **C7 / C8 ↔ C6:** the early biases lapse under O1; a turtling faction still joins containment.
- **C7 ↔ R3:** pressure on Vernius only while at war; peace with it is worth its tech.
- **C11 ↔ third parties:** a liberated village is neutral: prefer liberations where we, not a neighbor, annex next.
- **C14 ↔ terrain / cover:** one product, capped; cover still counted separately (nodes via C9, not twice).
- **C15 ↔ C13:** the reserve doesn't block our own close-out.

- **C16 ↔ C17:** the Siege gear set and siege ops follow the same plan trigger.
- **C16 ↔ C14:** gear changes the faction's real strength; the comfort factor stays a location factor, live power reads already include gear.

## Rejected (too much nuance or clashes with policy)

- Unit target priorities (airfield first, engineers / support drones / Fedaykin first, sidestepping orbitals, spread vs AoE, champions out of fights, hero preservation): tactical layer, vanilla `unitMicroManagement` (§2).
- Smugglers synchronized heist (two pillages of one faction at once): splits force (§1.6).
- Assassination offence (incl. Harkonnen's 50%-undetectable trick): long multi-system plan.
- Landsraad vote tactics, bounties, chat deals, lobby persuasion.
- Quirk / building layout optimization (Corrino quirk stacking, Vernius "rainbow" main base, Ecaz masterpiece placement): huge combinatorics; a quirk-value term in the Annex score is the most that fits.
- Nuke timing on captures: AI-prohibited op plus a micro trick (keep one unit to restart the capture).
- Smugglers night attacks (D `Night_Army`): small gain, needs the day-cycle read; revisit after R1.
- Parking a unit on back-cap villages to block Atreides peaceful annex: occupancy rules unclear; C6(b) raids those villages instead.
