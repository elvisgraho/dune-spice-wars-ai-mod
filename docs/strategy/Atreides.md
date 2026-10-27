# Atreides

Tags as in [GENERAL.md](GENERAL.md) (T transcript, W wiki, D data, C code). Candidates: [CANDIDATES.md](CANDIDATES.md); overrides O1-O5: GENERAL "Core principle". Shared rules (siege durations, betrayal, ops): GENERAL "Shared rules".

## Identity (T)
A tier. Plays **inside out from home**: expands by peaceful annexation without leaving its territory, fights best on home turf, closes games with Ceasefire + peaceful annex (Smugglers' Comms Jam is the hard counter). Money-poor early (treaties and House Gifts carry it); strongest at closing out. Water-hungry (recycling vats in the main base, Polar Sink valued).

## Reference (W unless tagged)
**Faction:** Peaceful Annexation on non-devastated neutral villages; Atreides villages cost +10% Authority to annex and take 10% longer to liberate (for others); all Solari upkeep -10%; **cannot pillage neutral villages** (enemy villages and sietches allowed). **5k:** +10% Solari while under a positive targeted resolution, +10% unit power under a negative one. **10k:** ignores charter prerequisites except Landsraad standing; +2% production per positive resolution won (×20).

**Peaceful Annexation:** global range; the normal Annex Authority cost + 50 Influence; 5 days; keeps the village's militia; blocked on devastated (D `Devastated`), hostile (D `HostileVillage`) or occupied villages. Cultural Assimilation (D `EmbraceCulture`): -20% Authority and Influence for it, +1 Arrakis agent slot, Concord Chamber. Vanilla AI use: C REVERSING (≤ 3 zones, ≥ 1 refinery); ours: launch gate `pannex`.

**Councillors:** Thufir Hawat (agents +1 trait; Hasten missions / village construction for Solari) · Dr. Yueh (+2 knowledge; non-mech units +15% max health, +30% regeneration) · Lady Jessica (force Truce for Influence; Atreides treaties have no Authority upkeep; a betrayer of an Atreides truce loses an extra 50 standing) · Young Paul (+2 Authority per allied sietch; allying reveals another sietch; the first revealed sietch starts at relation 30).

**Heroes:** Duncan Idaho (Heroism +2 power / +1 armor per allied unit bonus; each death makes later Duncans +3 power, +150 health; Last Stand: uncontrollable berserk, +5 armor, enemies in melee -50% speed) · Gurney Halleck (melee +1 armor / ranged +5% attack speed per XP level above 1; +50% XP to nearby units; Forced March: +30% speed, +2 armor, can't attack, 2 days).

**Units:** Trooper (melee), Ranger (medium range), Heavy Weapon Squad (rockets, breaching), Support Drone (field support: carries wounded), Warden (elite tank), Hawk (air, harasses weakened), Kraken (flagship: carries wounded troops out).

**Developments:** Local Community (+5 plascrete; Maintenance Center, Investment Office) · Urban Planning (parallel village construction; Mason Guild; Trade Agreement) · Atreides Foremen (+2 crew; each tax paid +15% harvester rate for full crews, ×3) · Post-Trauma Reintegration (+5 CP, -30% non-mech regeneration cost, Command Post) · Proud Liberator (+1% max health per 20 standing; units liberating / annexing from a lower-standing faction heal 50%) · Atreides Sympathizers (+5 standing per Landsraad info level on council opening, +2 Influence) · Political Entente (4 free Landsraad Guards when betrayed; Council Chamber) · Sustainable Spying (+50% agent output on CHOAM / Landsraad / Guild fields; single traits apply twice) · Active Surveillance (+1 Influence and intel per counter-intel agent, +1 slot) · Air Network (airfields -70% cost and upkeep, shuttles +100% speed) · Veteran Militia (-15% damage received inside Atreides borders, +80% militia health) · Cultural Assimilation (above).

**Buildings:** Council Chamber (50% of failed vote spending refunded; -50% standing losses) · Concord Chamber (sietches nearby +200% relation speed; allied sietches nearby +20 Solari).

**Operations:** Support Intelligence (100 intel, Guild 1: -5% damage taken per operation launched on the zone) · Arrakis Diplomacy (200/200, Arrakis 2: disbands rebellions and raids; +200% sietch relation gain and trade) · **Cease Fire** (500/500, Landsraad 2: interrupts and prevents battles in the region for 2 days; D aiWeights Economy / Statecraft 10).

## Expert play (T)
- Opening: Atreides Sympathizers + tier-2 blue (House Gifts +500 Solari); maintenance center touching many villages; Lay of the Land early; urban planning.
- Treaty economy: treaties to everyone (no Authority cost for them), Jessica force-truces attackers; a lobby refusing Atreides treaties slows it a lot.
- Vet up the army on militia early; support drones in every comp; memoirs armory gear with high standing.
- Late: ceasefire a contested target, then peacefully annex it; keep 2-3 unannexed backline villages for the close-out; Paul builds can reach 20-27 Authority/day.

## Matchups (T)
Hard to beat on its own land; beaten early (poor, few red techs) or by sustained pressure before it vets up. Good vs Vernius (tanky ranged, EMP). Comms Jam (Smugglers) cancels its ceasefire.

## For our AI
**As Atreides (defaults):**
- Peaceful annex where usable (built); spend Authority above any close-out reserve (C1).
- Raids: enemy villages and sietches only (W: no neutral pillage; C3).
- Comfort on home land (C14: Veteran Militia, support drones); offensives off it with more margin, and at the normal ratio under O1 / O2.
- Keep its vetted army: trading it early costs more than for others (worn-army rules; no new rule).

**Overrides / edge cases:**
- Peaceful annex fails on devastated or hostile-flagged villages and on occupied ones; Influence can run dry in Landsraad-heavy phases. Built: armies first, peaceful only when the army launch fails, from 4 villages owned (Influence scarce in the opening) and never on a village bordering our main base; vanilla's own peaceful check is held to the same (`pannex-gate`).
- A neutral village pillaged by anyone is closed to peaceful annex for 20 days (D Devastated): enemies can deny it that way, and so can our own raids (exclude neutral villages for Atreides anyway).
- Treaty economy has an Authority price: each Research / Trade / Political Agreement costs 10 Authority to propose and -10% Authority production (D `TreatyUpkeep`) unless Jessica is the councillor; an Atreides AI with many treaties and no Jessica is Authority-starved (check against the 28-minute Annex gap).
- Arrakis Diplomacy disbands rebellions / raids: relevant if R1 lands (a cheap fix for raider sieges near Atreides land).

**Against Atreides:**
- Its peaceful annex needs a neutral, non-devastated village: pillaging a neutral village next to Atreides blocks it for 20 days (D).
- Its captures come with no army on the village; Ceasefire stops our fights there for 2 days.
- Attacking it at home needs margin (Veteran Militia, drones); under O1 / O3 still worth it.

**Already covered:** `pannex`, `fpeace`, `peace-gate`, treaty scope.
