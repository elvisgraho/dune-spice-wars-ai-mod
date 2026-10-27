# Smugglers

Tags as in [GENERAL.md](GENERAL.md) (T transcript, W wiki, D data, C code). Candidates: [CANDIDATES.md](CANDIDATES.md); overrides O1-O5: GENERAL "Core principle". Shared rules: GENERAL "Shared rules".

## Identity (T)
S tier, most tournament wins. **No weak phase**, forgiving, plays every win condition. Few villages (Stakhanov islands); much income from Underworld HQs in others' villages, so less exposed to the spice exchange rate. Strong early aggressor: uses a weak-early neighbor as a "piggy bank" (pillage cycles) and can base-kill by month 4.

## Reference (W unless tagged)
**Faction:** Underworld HQs in opponents' villages; units +10% speed outside combat; no Annex distance penalty (C: attribute 952 = 0); Annex cost grows **50% more per owned village** (a wide Smugglers empire gets expensive fast). **5k:** Bounties on resolutions (others get 10 Solari per vote on the chosen option); joins the Landsraad with 50 votes. **10k:** a Major UHQ in every enemy main base; +50% pillage resources.

**Underworld HQ:** escalating cost (D ability `InstallUWHeadquarter`: 50 Solari + 5 Authority per existing HQ, so 50/5, 100/10, 150/15, ...); vision of the village; +1 hegemony/day; 2 extension slots (D `extensionSlots` 2; Staban +1), 100 Solari each. **Extensions (D, building sheet; id when it differs from the name):** Harvesters' Union (`TraffickingStation`, +2% spice for us and allies) · Bootleg Market (30% of the village's Solari and Plascrete production as Solari) · Water Thieves (`WaterSmugglers`, 30% of its water) · Whisperers Lair (30% of its Intel and Influence as Intel) · Spyware (`Spywares`, 30% of its Knowledge) · Energy Diversions (30% of its Fuel Cells) · Corrupted Administrators (10% of its Solari upkeep) · Contraband Caches (stores 50% of its spice, taken on our pillage) · Scavenger Caches (zone trait) · Hidden Explosives (militia -50% life on our siege, then removed) · Covert Recruiters / Dead Drops (`EnrollmentStation`) (traits to allies) · Local Gang (+80 Manpower; 2 troopers on our siege) · Back-Alley Doctor (our units heal / resupply there) · Propaganda Cell (+1 Standing per council) · host-gain ones: Worker's Guild (host +20% production), Activist Quarters, Water Network / Water Seller (Lingar; +3 water / +15 Solari for us, host also gains). Vanilla AI: no per-extension scoring, cdb `aiWeights` only (Worker's Guild -5, a few +1, most 0). **Major UHQs** (10k, 2 per enemy main base, each kind once; 1000 Solari + 100 intel): Contraband Hub (+50% pillage on that faction), Spice Traffickers (15 spice per harvester of that faction), Laundering Network (+30 Solari per level of its biggest Economic district), Hidden Explosives (that main base can't attack for a day on our attack; 500 Solari), Beacon Network (+2 armor in its territory), Weapon Dealers (+5% power per level of its biggest Military district), Whisperers Hub (+1 infiltration cell), Scheme Lodge.

**Councillors:** Staban Tuek (+1 UHQ extension slot) · Lingar Bewt (+12 water; Water Network / Seller extensions) · Lashon Hara (+1 information level per completed trade with a faction; levels decay 50% slower; +15 Solari and +1 Influence per level) · Stakkanov (villages with no Smugglers neighbor: sieges take 100% longer, +20% production; 50% of the capture Authority refunded when a village is lost).

**Heroes:** Drisq (idle ground units -30% damage taken; detects stealth at very long range; units in her region are stealthy during Smuggler operations; Cutting Costs: next spying operation in the region isn't consumed, 10-day cooldown) · Bannerjee (units regenerate in villages with a UHQ; full supply after a successful siege; +3 power / armor outside Smugglers territory; Street Urchins: recruits 2 Scavengers).

**Units:** Scavengers (mercenary melee), Wreckers (chemical, spoil supplies), Sniper (ambush), Scavenging Drone (loot), Free Company (stealth assassins), Banshee (stealth recon air), Wraith (flagship: gas cloud).

**Developments:** Tinkerer Teams (+1 crew; Trafficking Station; Harvester Works) · Underworld Contacts (+2 crew; UHQs produce 20% of the village's spice) · Guerilla Tactics (+15 water; at night +20% damage and +20% speed out of combat) · Organized Looting (D: +30% pillage resources; Scavenging Drone) · Industrial Scavenging (-30% non-mech upkeep near a drone; 2nd gear slot; Fusion Plant) · Synchronized Heist (+10 CP; +20% speed for a day after a siege; pillage +100% faster with 2+ sieges on one faction) · Foot in the Door (-20% UHQ cost in truce partners' land; +1 Influence and intel per host faction; +100% agent recruitment) · Security Details (4 free mercenaries when a bountied choice passes; +1 counter-intel slot) · Underworld Bribes · Criminal Barons (-15% UHQ cost; +0.5 water per UHQ) · Underground Network (+5 Solari per UHQ in adjacent regions; Black Market Branch) · **Illicit Methods** (D id `AegisoftheUnderworld`: pillage Annex penalty × 0; Investment Office; +1 Arrakis slot).

**Buildings:** Trafficking Station (-20% spice for neighboring regions of any owner; 80% of it as Solari) · Black Market Branch (+1% spice / plascrete / manpower / intel per UHQ).

**Operations:** Poison the Reserves (100 intel, Arrakis 1: enemies losing supply -20% speed, -5% health/day) · Extraction Network (200/200, Guild 2: every unit near the region's village is extracted to the main base) · **Communication Jamming** (500/500, CHOAM 2: cancels all operations in the region and blocks new ones for 3 days).

## Expert play (T)
- Opening: capture spice, a special nearby, plascrete / fuel cell; pillage everything else; UHQs in every faction (research / spice / water extensions), truce everyone it won't attack.
- UHQ use (user, expert consensus): Harvesters' Union everywhere first, then the extension matching what the host village produces (no Whisperers Lair without Intel / Influence); host-gain extensions and the remaining ones are never built; one HQ per faction first; villages near the host's main base are rarely recaptured; don't over-build (Authority cost escalates).
- Aggressive line: pillage-cycle a weak neighbor with Hidden Explosives, Defense Sabotage on the main base, base kill by month 4; keep macro going meanwhile.
- Macro line: few Stakhanov specials, many UHQs, Black Market Branch, CHOAM if the economy allows.
- Comms Jam held for the enemy's key operation (Atreides ceasefire, Corrino orbital).

## Matchups (T)
Beats Corrino, Ecaz, Vernius; even with Harkonnen; Fremen beats sniper comps (melee comp + Bannerjee evens it).

## For our AI
**As Smugglers (defaults):**
- Pressure a weak-early neighbor (C7); raid future captures without the pillage penalty once Illicit Methods is researched (C2); far annex (built).
- Few villages: each owned village raises the next Annex cost by 50% more than for others (W), so the Annex value should prefer quality (specials, spice) over count; isolation-aware Annex only with Stakkanov (R2).

**Overrides / edge cases:**
- A base kill of a UHQ host costs its own UHQ income: weigh the kill against the UHQs there (UHQ count per host faction: structure `UWHeadquarters` in its zones).
- Far captures stretch defense: a far village without turrets is cheap for enemies; bunker / cover terms still apply.
- Comms Jam cancels our ops too if cast in a region where we have some (R1).

**Against Smugglers:**
- A Stakkanov village takes about twice as long to capture: contest / defense timing reads the observed progress rate (built: `_late`).
- Its army can leave via Extraction Network: a hunt on it can end with the prey gone (hunt target-invalid trigger covers it).
- UHQs in our villages feed it (vision, hegemony, resources): retaking / defending villages has extra value against a Smugglers leader (C6).

**Already covered:** far annex, UWHeadquarters excluded from our land, UHQ cap / placement / extensions (`uhq`, AI-POLICY §5a).
