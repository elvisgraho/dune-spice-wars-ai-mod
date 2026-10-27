# Harkonnen

Tags as in [GENERAL.md](GENERAL.md) (T transcript, W wiki, D data, C code). Candidates: [CANDIDATES.md](CANDIDATES.md); overrides O1-O5: GENERAL "Core principle". Shared rules: GENERAL "Shared rules".

## Identity (T)
B tier. **Pillage machine with a cheap, fast-replaced army.** Wins by CHOAM (with Smugglers, the best) or a late hegemony spike from instill-feared villages. Weak at passive hegemony (crafts come from Symbols of Authority, so an obfuscated crafts tech doesn't hit it). Knowledge-hungry (30-40 by month 5). Central villages make it easy to 3v1.

## Reference (W unless tagged)
**Faction:** Oppression on own villages (+100% production; afterwards -20% local production and a daily chance to rebel); sacrifice an agent to cut a mission's cost and preparation; villages +5% production per active militia; villages -10% production base. **5k:** +50 intel per village pillaged; a free Brainwashed agent after killing 20 non-mech enemy units. **10k:** sacrificed agents may not consume the operation; +1 agent slot in each non-faction field.

**Sacrifice:** the agent dies; -30% Solari and intel cost, -100% preparation time, undetectable, no capture. **Rebellion:** rebels occupy the village, -100% production, buildings disabled until the rebels die (sources: oppression, Fremen Awaken the People, Mother Ramallo, Authority deficit).

**Councillors:** Cron Vatia (oppressed villages build 200% faster; +2 manpower per empty slot on oppression; +50 Solari per rebel killed) · Umman Kudu (+2 manpower; -30% recruit time; +1 armor with a Harkonnen operation active in the region) · Feyd-Rautha (Corruption: the elected enemy loses 30 standing, Harkonnen immune; +20% Influence and +100% agent recruitment while a village is oppressed) · Piter De Vries (each sacrifice permanently -15% mission costs; +60 Solari per current agent on sacrifice).

**Heroes:** Glossu Rabban (+1 heavy militia per village; uncontrollable units near him become Thralls: +20% damage, +1 armor, +20% speed, and buff him; Gladiator Drugs toggles nearby non-mech units uncontrollable) · Iakin Nefud (steals an ally's health instead of dying; Bloodthirsty per nearby death, ×20: +1 power, +0.5 armor; Cannon Fodder: nearby level-1 units lose upkeep / CP, refund 50% on death, can't regenerate).

**Units:** Trooper (rank and file), Gunner (explosives, stun), Cerberus (fanatic, stealthy splitting fodder, T), Combat Probe (light air, concealed), Executioner (heavy armor, regenerating shields; bloodthirst stacks revive it, T), Harpy (air, area missiles), Overlord (frigate with drone-ships; decimation protocol, T).

**Developments:** Work Ethics (+5 plascrete, +3 manpower; Maintenance Center) · Martial Economy (+1 militia slot; Office of Order) · Arrakis Butchers (+10 water; +50% damage vs militia / rebels; +5 manpower per militia / rebel killed) · Assembly Lines (Combat Probe / Harpy -30% cost and time) · Adrenaline Addiction (+10 CP; +1% attack speed per nearby death, ×50; 2nd gear slot) · Cruel Reputation (operations on a faction in conflict refund 25% of their Solari as Influence) · Landsraad Whispers (+2 intel per Landsraad agent, +1 slot; Landsraad Quarters) · Enhanced Questioning (+1 intel per oppressed village; Interrogation Center) · **Instill Fear** (D: each pillage adds a stack of -10% Annex Authority for that village, up to 9 stacks, and pillage doesn't apply the +100% `Pillaged` cost; -50% Annex cost on villages Harkonnen owned before) · **Savage Cleansing** (D id `MonitoringNetworks`: +100 Authority the first time a sietch is pillaged and reveals another sietch; a successful pillage resupplies 25% of max supply in the circle) · Symbols of Authority (+1 Authority per oppressed special; Crafts Workshop).

**Buildings:** Office of Order (D `OppressionHeadquarter`: oppresses continuously for free; militia fight rebellions) · Interrogation Center (+10 intel per enemy unit killed; captured agents always brainwashed).

**Operations:** Combat Drugs (100 intel, CHOAM 1: non-mech allies -10% health/day, +10% speed, +30% damage) · Sleeper Agent (200/200, Arrakis 2: dying non-temporary non-mech units spawn a sleeper agent 50% of the time; D aiWeight Military 10) · Toxic Vapors (500/500, Guild 2: non-mech units lose 30% health/day, no regeneration).

## Expert play (T)
- Pillage routes from minute 1; mark villages to take later and keep pillaging them (cost falls, D-confirmed); save sietch pillages (Authority) for the Authority spike; capture 4-7 feared villages at once before a tax.
- Fill militia in every village (+5% production each, W); Office of Order on spice fields and specials (its upkeep is high).
- Fight: Cerberus run in, executioners stack, Sleeper Agent + Combat Drugs + Toxic Vapors on the fight; re-recruit faster than the enemy (Kudu).
- Two pillage groups minimum; keep the pillage cycles in sync so villages come off cooldown together.

## Matchups (T)
Strong vs Smugglers, Ecaz, Fremen, Vernius in the open. Corrino is the hard counter (Sardaukar execute executioners): more gunners / troopers, vapors, bait orbitals.

## For our AI
**As Harkonnen (defaults):**
- Pillage future captures once Instill Fear is researched (C2; D-confirmed effect); sietch strikes valued by Savage Cleansing (C5: +100 Authority first time per sietch).
- Fights near own land / with own ops count stronger (C14), since its units are cheap to replace; the one retreat measure stays.
- Pressure weak-early neighbors (C7), stay in the CHOAM race.

**Overrides / edge cases:**
- Before Instill Fear, pillaging a future capture doubles its cost for 90 days (D `Pillaged`): C2 checks the development, not the faction name.
- A pillaged village is untargetable for 20 days (D `Devastated`): the close-out (C13) times the last pillage so the village is free at capture time.
- Rebellions from oppression are expected: vanilla Defense handles rebels; an at-war army at the same village still triggers the rally (built).
- Against Corrino the comfort factor stays neutral.

**Against Harkonnen:**
- Toxic Vapors: -30% health/day for non-mech units in the region; prefer waiting it out unless O1 / O2.
- Its feared backline is its close-out. Our pillage of one makes it untargetable for 20 days (D `Devastated`), which delays a Harkonnen capture right before a tax (C6(b)); taking the village removes it. The fear stacks sit on the village (D trait); whether they survive an owner change is *unverified*.
- Expect sacrifice-launched ops (undetectable) and assassination attempts.

**Already covered:** rebels vs rally (`rally standoff / raiders` row), `dstop`, raid.
