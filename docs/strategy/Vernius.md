# Vernius

Tags as in [GENERAL.md](GENERAL.md) (T transcript, W wiki, D data, C code). Candidates: [CANDIDATES.md](CANDIDATES.md); overrides O1-O5: GENERAL "Core principle". Shared rules: GENERAL "Shared rules".

## Identity (T)
C-F tier (the hardest to win with). **Research faction, "bite and hold":** very weak in months 1-3 (Suboid soldiers; mech army costs Solari), hard to break once bunkered under neural nodes with Automated Defenses, strong in the mid game (fast re-recruit, healing), then gives up tiles slowly. Lives on truces: factions in truce with Vernius get its tech; Vernius gets knowledge and standing per truce. Easy to assassinate (many villages, several cell searches to clear).

## Reference (W unless tagged)
**Faction:** tethered Combine Harvester Drones harvest spice fields in neutral and owned regions; factions in Truce get the effects of developments Vernius researched and they didn't; mixed S-Vault districts are split for district bonuses; **villages not connected to the Nodal Network produce -50%**. **5k:** File Patent; research one development without its requirements. **10k:** Obfuscate one development; each knowledge point +0.2% to all other resources.

**Nodal Network:** the main base + villages with an active Neural Node (D `NeuralNode`) + deep deserts (with Sequential Thinking). A node can be built only where exactly 1 neighbor is directly connected. Connected village: drones in neighboring regions are tethered; village buildings -1 water. **Tethered:** mechanical units in or next to a node region; +0.5% attack speed per knowledge; also via Resonance Drone gear, Ambient Connection, the Folder Relay.

**File Patent:** 600 Solari, on a development only Vernius has; others pay Vernius 500 Solari to research it. **Obfuscate:** 20 standing; the development has no effect for anyone, Vernius included.

**Councillors:** Bolig Avati (several buildings at once per S-Vault district; removed S-Vault buildings fully refunded; +1 knowledge per district bonus) · Bronso Vernius (villages next to a single Vernius region -20% Annex Authority; the farthest connected node is an airfield) · Cammar Pilru (+5 max Influence per knowledge; +200 Influence on entering a conflict; +30 standing when an opponent imposes conflict) · Tessa Vernius (spy missions need 1 info level less; with no research running, 50% of knowledge becomes intel and Solari).

**Heroes:** Nuwa Cenva (+20% drone recruitment; spy ops in her region last 2 days longer; tethered units nearby +1 armor, +20% speed; Repair Station: nearby drones heal in combat, she can't move) · C'Tair Pilru (+1 armory gear slot per unit for +1 fuel cell each; stealthy; nearby non-mech allies stealthy; Evasion: next attack executes, then leaves combat in stealth, 6-day cooldown).

**Units:** Fighting Mek (melee drone), Suboid Soldier (cheap labor infantry), Railgun Drone (ranged), Resonance Drone (electrostatic AoE), Fight-Engineer (repairs drones, the army's backbone, T), Spirit (camouflaged air), Folder Relay (flagship: short-range teleport for retreat / maneuver).

**Developments:** Entropic Engineering (up to 2 fuel cells into harvester drones; Spice Silos; Spice Laboratory) · Spice Enlightenment (up to 4 fuel cells; +0.5% spice per knowledge) · Water Batteries (water replaces missing fuel cells; 2nd gear slot) · Guild Collaboration (+5 CP; Guild agents make 2 fuel cells; Command Post) · Automated Manufacture (+10 CP; +0.5% recruit and regeneration speed per knowledge) · Technological Exchange (+5 standing per truce at council opening; +2 knowledge per truce) · Heretical Computing (Analytical Machine agents, one free; Harmless Gadget treaty; Intelligence Agency) · **Holistic Thinking** (D `HolisticThinking`: +1 knowledge per information field with a machine; +1 info level in factions that accepted a Harmless Gadget) · Physical Wiring (infiltration cells next to a node: knowledge, Solari, intel; Assassins) · Sequential Thinking (nodes across deep desert; +0.5 knowledge and +2% Authority per node on the longest path) · **Automated Defenses** (D `AutomatedDefenses`, replaces the generic `BorderDefense`: connected villages +2 free Automated Militia; connected nodes attack enemy units in the region as rapid-fire single-target defenses) · **Neural Tropism** (D `NeuralTropism`: enemies pay +30% Authority to annex a village neighboring ≥ 2 connected regions; Neural Core).

**Buildings:** Spice Laboratory (+2 knowledge per exploited spice field; -2 fuel cells per harvester drone) · Neural Core (D `Main_NeuralCore`: connected nodes make 1 fuel cell; +2% knowledge per connected node) · Neural Node (connects a region).

**Operations:** Ambient Connection (100 intel, Landsraad 1: allied mechanical units tethered remotely) · Empirical Data (200/200, CHOAM 2: +1 knowledge per unit of any faction fighting in the region) · Hidden Backdoor (500/500, Guild 2: enemy mechanical units become uncontrollable and attack their allies).

## Expert play (T)
- Opening: plan the node chain before expanding; Technological Exchange → Heretical Computing → Holistic Thinking; buy machines for all info fields (they cost standing, keep ≥ 150-200); truce everyone.
- 5k: tech-skip into Automated Defenses; patent the red tree; spice laboratory and harvester drones on many fields.
- Mid: bunkers of node villages next to a rival; fight-engineers healing; C'Tair stealths them; Folder Relay in and out.
- 10k: obfuscate Parallel Training right after wiping a rival army (re-recruit race), or Crafts when far behind.

## Matchups (T)
Next to its nodes it beats most factions; in the open it loses to Fremen and Harkonnen; Corrino mass riflemen beat it in most places. Enemies scan and kill the engineers first; EMP and Hidden Backdoor hurt mech armies.

## For our AI
**As Vernius (defaults):**
- Early caution until Automated Defenses (C8).
- **Fights next to its nodes count stronger, fights away from them weaker** (C14: × 1.25 / × 0.85; W: tethering only adds attack speed per knowledge, so the factor comes mostly from node fire and Automated Militia, already in cover / militia sizing once C9 holds; keep the extra factor small). It's a margin, not a ban. It attacks off its nodes when:
  - O1: a rival is about to win and its army is the one in reach;
  - O3: the target's army is wiped, far away or tied up and its force passes KILL × at the target (the expert "wipe, then obfuscate Parallel Training" window);
  - the target touches its network, so a node can follow the capture (W: build rule "exactly 1 connected neighbor": check that the target qualifies);
  - the Folder Relay is ready to pull the army out (*unverified* whether the AI uses it, R4).
- Unconnected villages produce -50% (W): its Annex value should prefer villages that can take a node.
- Offer and keep truces (R3): its tech is its currency.

**Overrides / edge cases:**
- Losing a node village can disconnect villages behind it (-50% production): the defense value of a node village is higher than its own production suggests (`aimod_defend` treats all our villages alike today).
- Obfuscation also disables the tech for Vernius: pick one it doesn't use.
- Patent income needs rivals still researching: a patent on a tech nobody needs pays nothing.

**Against Vernius:**
- A siege into a node bunker: node fire counted via cover (C9), +2 Automated Militia per connected village; Neural Tropism makes villages next to 2+ connected regions cost +30% Authority. The efficient windows: before Automated Defenses, on an unconnected or cut-off village, or after its army is wiped.
- Peace with Vernius is usually worth more than its villages (R3); under O1 the leader rule wins over the tech.

**Already covered:** cover sizing (structure combat stats), worm reaction (T: its drones don't attract worms, *unverified*).
