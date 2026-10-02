# Fremen

Tags as in [GENERAL.md](GENERAL.md) (T transcript, W wiki, D data, C code). Candidates: [CANDIDATES.md](CANDIDATES.md); overrides O1-O5: GENERAL "Core principle". Shared rules: GENERAL "Shared rules".

## Identity (T)
C tier in general, dangerous in expert hands. **Early aggressor, late struggler:** strongest army early (stealth, worm riding), relative power falls off; no airfields, no nuke silo (W), a poor economy (a Solari deficit most of the game). Hegemony is its practical win condition (no Landsraad seat, W; CHOAM weak). Encouraged to roam and liberate. Hard to close: needs 2-3 captures at the end; mobility depends on sand.

## Reference (W unless tagged)
**Faction:** spice fields in neutral and owned regions harvested by mobile Harvesting Teams (20 spice/day, 10 Solari upkeep, 500 health, 10 armor, no worm attraction); allies sietches outside its territory; Thumpers for wormriding (3 at start, sandy terrain only); villages -1 building slot. **5k:** surrounding a deep desert grants it (C REVERSING: zone owner); thumpers regenerate, larger worms travel farther. **10k:** sees enemy sietch alliances; allied sietches host 1 main-base building.

**Sietch alliance** (GENERAL "Shared rules"): Fremen pay 4 water + 1 Authority to ally and need no territory; allied sietches serve as resupply, rally and healing points.

**Councillors:** Shimoom (villages producing ≥ 12 water: -4% Solari upkeep globally and +4 plascrete each; 1 water per empty slot) · Jamis (+70 Authority per enemy village liberated; +10% damage outside Fremen territory; trade 10 Authority for 30 manpower) · Mother Ramallo (Incite Rebellion on a resolution for 50 Authority; +3 intel and +0.5 Authority per deployed Harvesting Team) · Stilgar (all sietches revealed at start; +1 Authority).

**Heroes:** Chani Kynes (undetected stealth units +30% speed and no worm attraction; she is invisible out of combat; enemies dying near her give 5 intel; Ambush: undetected stealth allies +100% power on the first attack) · Otheym (allies with no same-kind unit nearby +50% damage; enemies -3% damage per nearby enemy unit; damaged enemies -30% speed; Coordinated Strikes: ≤ 8 nearby ground units +20% damage, -20% damage taken, 2 days).

**Units:** Warrior (desert melee), Skirmisher (anti-vehicle demolition), Infiltrator (stealth melee, armor-piercing), Mobile Turret (anti-air artillery; D `F_Special` → deployed `F_Special_2`), Fedaykin (elite), Spire (air, from an ornithopter wreck), Altar (customizable flagship).

**Developments:** Arrakis Secrets (all spice fields revealed; teams heal / resupply when deployed, leave combat and gain stealth when packing up; Spice Silos) · Freedom Fighters (+0.5 Solari per neutral or Fremen village; **+500 Solari per liberation**; Trade Agreement) · Sand Brotherhood (+1% Solari per allied sietch; +10% production in an allied sietch's region and neighbors; Bazaar) · Shared Transcendence (ceremonial caves +10 Solari, +1 knowledge) · Sky Grazing (-20% damage from air; Mobile Turret) · Desert Trekkers (+10 water; +20% ground speed in neutral territory) · **Stalwart Alliance** (D `StalwartAlliance`: allied sietches next to an enemy village being liberated send a raid; 2nd gear slot; allied sietch militia +50% health) · Iday Alakrab (wormriding +100% faster and hidden; +10 damage first attack and stealth for a day on exit) · Fremen Solidarity (+60 relation with all sietches; +100% agent recruitment) · Sand Diplomats (+1 Influence per allied sietch; Al-Gaib Temple) · Sietch Network (+5% op detection per allied sietch; +1 counter-intel slot) · Heir of Arrakis (+20% Authority per controlled deep desert; neighboring villages: quirks applied 2 more times, +20% militia power; Investment Office) · Desert Wisdom (windtraps +0.1 knowledge per wind level; Mason Guild) · Desert Watchers (+1 militia slot; +50 militia health per neutral neighbor; allied units stealthy in Fremen territory and near allied sietches).

**Buildings:** Bazaar (counts as Economy + Military + Statecraft for district bonuses; +10 Solari and +2 water per active sietch trade) · Al-Gaib Temple (+50 max Influence per allied sietch; +50% sietch trade resources; in the main base or an allied sietch) · Ceremonial Caves (needs Energy Sources or Great Volcano; +5% unit power) · Shai-Hulud Temple (+100% thumper production, +2 max) · Recycling Plant (trade resources for spaceship parts; Spire and Altar).

**Operations:** Hiding Tracks (100 intel, Arrakis 1: allies stealthy, enemies -10% speed in the region and its neighbors) · Hidden Thumpers (200/200, Arrakis 2: rides to / from the region use no thumper; units there stealthy) · Awaken the People (500/500, CHOAM 2: starts a rebellion in the village).

## Expert play (T)
- Opening: high-wind villages near the main base, trade with every sietch, ally the knowledge sietches first; Desert Trekkers for water; maintenance center touching 4 villages.
- Early: punish a neighbor that expands toward it (liberate for Solari / Authority with Jamis); keep allied sietches unpillaged (they are its airfields).
- Mid: bunkers on contested borders; trade guild parts for Authority via the Recycling Plant; late, drop sietch alliances to free Authority, skip rebuilding a dead hero (150 Authority).
- Comp late ≈ 2 warriors, 4 mobile turrets, rest Fedaykin; Otheym preferred.

## Matchups (T)
Good vs Corrino (skirmishers on riflemen), Smugglers (dive on snipers), Ecaz, Vernius on open sand. Weak vs Harkonnen and vs Vernius under nodes.

## For our AI
**As Fremen (defaults):**
- Liberate rather than pillage where it can hold the village (C11: 6 days, +500 Solari with Freedom Fighters, +70 Authority with Jamis); deep desert ring (built); early pressure (C7).
- Bunker attacks carry a margin penalty (cover sizing, built) and a comfort penalty off sand / off its land (C14); they stay available under O1, or to break a rival's bunker pair.

**Overrides / edge cases:**
- Liberation value depends on Freedom Fighters (dev) and Jamis (councilor, R2); without both a liberation is mostly a denial move.
- A liberated village is Just Freed for 20 days (W: untargetable): nobody, Fremen included, can take it in that time; good for denial, slow for expansion.
- Worm rides need sand paths (rock blocks them); after 5k rides reach farther: threat ETAs from Fremen armies can be shorter than walking paths suggest (*unverified* in `aimod_threat`).
- A pillaged allied sietch stops serving as a rally / heal point; plans relying on it re-check after each pillage.

**Against Fremen:**
- Pillaging its allied sietches cuts reinforcement, healing and trade income; Fremen restore one for 150 manpower + 1k Solari + 10 days (W).
- Expect stealth in its territory and near its sietches (Desert Watchers): probes (R1) or contact-only detection.
- Its ring villages are left alone by our raids while the ring is uncontested (built rule); under O1 that exemption lapses.

**Already covered:** deep desert ring focus / ring first, `undeploy` for installed mobile turrets, worm reaction, FP_SKIP (no force peace on Fremen).
