# Corrino

Tags as in [GENERAL.md](GENERAL.md) (T transcript, W wiki, D data, C code). Candidates: [CANDIDATES.md](CANDIDATES.md); overrides O1-O5: GENERAL "Core principle". Shared rules: GENERAL "Shared rules".

## Identity (T)
A tier. **Tall, quirk-driven economy around up to three main bases**; strongest army mid/late; politically strong (base votes, Imperial Edict). Few villages; wants ~3 specials. Vulnerable in months 1-3 if an aggressive neighbor commits while its first villages lie outside the main-base turret (it then sits under the turret until 5k). Late Authority is poor (each Propaganda Office -1 Authority). Often the lobby's 3v1 target.

## Reference (W unless tagged)
**Faction:** villages +1 building slot; Imperial Edict switches a resolution's scope (20 Influence, not charters); cancelling a truce with Corrino costs +100% Influence; Annex Authority distance term +200% (C: attribute 952 = 3). **5k:** Main Base Deployment once; Imperial Mandate (give Sardaukar to another faction in a trade). **10k:** destroying the main base of a faction in conflict with Corrino for > 50 days gives a second deployment; +15 Influence per kill on a truce partner's territory.

**Main Base Deployment** (D ability `DeployMainBase`): razes a neutral or Corrino village and drops an Imperial Base; 3k Solari + 100 Authority; not on a special region or a village occupied by another faction; once (+1 per qualifying base kill). T: not on spice fields either; players pillage the drop site first.

**Councillors:** Princess Irulan (every building can be built once more anywhere: two Crafts Workshops / Investment Offices / Propaganda Offices in one village) · Zum Garon (+15% unit power per faction in Truce; Imperial Mandate free) · Gaius Helen Mohaim (votes on edicted resolutions count double; charter priority support counts double) · Hasimir Fenring (investigate discoveries anywhere quickly regardless of Arrakis agents; each resolved discovery advances agent recruitment by a day).

**Heroes:** Wensicia (+1 training slot while a conscript recruits; nearby conscripts +1 armor or power; -10% damage taken per nearby allied unit; Unexpected Reinforcements: heals nearby conscripts 50% for manpower, 15-day cooldown; 2 Laza Tigers) · Captain Aramsham (Sardaukar -20% manpower; Sardaukar execute threshold ≥ 25% near him; Killing Flow +1 power per execution; Finishing Move: 50% threshold).

**Units:** Conscript Swordsman, Conscript Rifleman (stronger with specialist support), Incinerator (napalm), Artillery Drone (deployable, vulnerable up close; D `C_Drone_Deployed`), Sardaukar (elite, executes), Hammer (bomber vs defenses), Cronos (flagship, flanking cannons, landing infrastructure: mobile airfield; D `C_Frigate_Deployed`).

**Developments:** Solid Materials (+15 plascrete; buildings +1000 health) · **CHOAM Manipulation** (D: per 1% CHOAM share +0.5% unit power and +1% operation detection) · Integrated Costs (villages next to the Imperial Base +10 Solari, -30% major-building upkeep) · Imperial Command (uses truce partners' airfields; no supply drain on their land; 2nd gear slot) · Imperial Protocols (+10 CP; -20% damage taken where Corrino has numerical superiority) · Absolute Power (Non-aggression Pact free while no truce is active; +5 standing per council with a truce; Landsraad Quarters) · Diplomatic Spying (+2 Influence per agent on a truce partner, +2 intel per agent on a conflict faction) · Emperor Eyes (3 unmovable counter-intel agents; -50% unit costs while betrayed) · Megalopolis (-10% construction in the Imperial Base; villages next to it +3 water, -10% construction) · Imperial Researchers (+1 knowledge per completed district) · Imperial Administration (quirks applied once more next to an Imperial Base; Investment Office) · Administrative Consolidation (-20% upkeep in villages with 4+ same-type buildings; Emperor Monument).

**Buildings:** Emperor Monument (D `Main_Monument`: +10 hegemony/day; doubles that Imperial Base's district bonuses) · Propaganda Office (+20% production, 1 Authority upkeep).

**Operations:** Consolidation (100 intel, CHOAM 1: +2 armor to allied mechanical units and structures) · Interdiction Zone (200/200, Landsraad 2: enemy airfields and carryalls unusable in the region) · Orbital Strike (500/500, Guild 2: heavy area damage to ground units, villages and main bases, ours included).

## Expert play (T)
- Opening: three villages tight around the main base with good quirks; 2000 Solari + 500 plascrete ready at the first tax; buy CHOAM early (military buff).
- 5k: drop the second base next to specials / a quirk village (pillage the site first); Monument in a main base for doubled district bonus.
- Mid / late: small-formation riflemen + Wensicia; flamers for base kills; artillery drones vs bunkers; orbital strikes and interdiction; nuke ready for the end.
- Enemies 3v1 it late; it holds with army + turrets.

## Matchups (T)
Beats Harkonnen (Sardaukar) and Vernius (mass riflemen). Weak vs Fremen (skirmishers on riflemen) and Smugglers (Free Company on drones). Early game vs any aggressor.

## For our AI
**As Corrino (defaults):**
- Early caution (C8) until 5k or the second base; Annex prefers villages near main bases (vanilla's ×3 distance cost does most of it).
- Check the second-base drop happens at all (R4); after it, the distance term counts from the nearest Imperial Base (C: `concatAnnexationCostDetails` uses the main-base distance; *unverified* which base).
- Mid/late its army is the strongest: normal offensive ratios; comfort where it has numerical superiority (Imperial Protocols: -20% damage taken) fits C14.

**Overrides / edge cases:**
- A spawn with no villages near the main base: C8 reorders, it doesn't block.
- Truce partners' airfields extend its reach: threat from Corrino can arrive via an ally's airfield (threat ETA uses walking paths; *unverified* for airfield hops).
- Zum Garon makes truces a combat stat (+15% per truce): diplomacy changes its army strength, our `B(F)` reads live power so it follows.

**Against Corrino:**
- Pressure before 5k (C7); after that, prefer its far villages (outside main-base guns, built: MB_GUN_W).
- Pre-capturing or pillaging a likely drop site (a neutral, non-special village) denies the second base: D says occupied villages are invalid targets.
- A Corrino near 50% CHOAM is an O1 target even with low hegemony.

**Already covered:** bunker under main base (BUNKER_R), main-base gun weight.
