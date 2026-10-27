# Ecaz

Tags as in [GENERAL.md](GENERAL.md) (T transcript, W wiki, D data, C code). Candidates: [CANDIDATES.md](CANDIDATES.md); overrides O1-O5: GENERAL "Core principle". Shared rules: GENERAL "Shared rules".

## Identity (T)
C-D tier, high risk / high reward. **Very weak early** (expensive units, slow recruiting, poor), very strong late with a max-vet perfected army. Wins by a hegemony spike: champions farm hegemony from kills, then sanctuaries get captured together near 27k. The best Governor faction (Vipp immunity + Political Art charter lock).

## Reference (W unless tagged)
**Faction:** surrounded neutral villages become Sanctuaries (unattackable by others); +1 Authority per sanctuary; villages apply their quirks once more per neighboring sanctuary; betraying a truce gives Ecaz **no damage bonus and twice the standing loss**. **5k:** one Ecaz village can become a Garden Resort; one non-mech unit can be named Champion. **10k:** 0.2% of hegemony as Solari production; the first 30 votes on each resolution are free.

**Sanctuary** (D traits `Ecaz_Sanctuary*`): a neutral village surrounded by any mix of Ecaz regions, mountains, deep desert, the Desolation or the map edge. Ecaz units there can Tax Collection (300 Solari) or Military Parade (20 Influence + 20 XP for all Ecaz ground units), each locking the village for 30 days, or Annex it.

**Champion** (D ability `EcazChampion`): 1k Solari at 5k; max XP level, +20% health, +20% power, +2 armor, can't be executed; each enemy-faction unit it kills = a trophy = +100 hegemony, lost when it dies (T: buildings count too). Knights are the usual pick.

**Garden Resort:** 5k, 500 Solari, once, on an Ecaz village; +2 knowledge per adjacent sanctuary, +0.2 Influence per masterpiece nearby; can't be abandoned; **attacking it costs the attacker 100 standing and 100 Authority**; -5 water.

**Masterpiece** (D `Masterpiece_*`): counts as 2 buildings for quirks; survives liberation; destroying one costs 10 Authority and 10 standing.

**Councillors:** Sanya Ecaz (per sanctuary on the map: +15 Solari, -40% masterpiece cost) · Rivvy Dinari (max-level units no Solari upkeep; units start 1 level higher) · Ibbo Vipp (Landsraad Immunity: positive resolution immunity gives 30 Influence, negative costs 30 standing; +2 standing per masterpiece) · Mesa Ecaz (abandoning a village refunds 100% of its capture Authority; each masterpiece outside Ecaz land -15% siege duration on its village; masterpieces build 100% faster).

**Heroes:** Whitmore Bludd (a second Champion of another type; is a Champion; champions +1% health per trophy; Frightful Champion: +1 power / +0.5 armor per trophy, burns a trophy every 4 s) · Ilesa Ecaz (+20 manpower per masterpiece; killing her on Ecaz land costs 50 standing; +3% damage per masterpiece in neighboring villages; Saving Grace: fakes death and reappears at the rally point, 20-day cooldown).

**Units:** Squire (front, takes blows), Musketeer (hunter, ranged), Fencer (duelist), War Banner (buffs), Knight (elite), Siren (air, anti-material), Monument (flagship).

**Developments:** Artistic Aspirations (+80 Solari per masterpiece; -50% building slot cost; Mason Guild) · Cultural Tourism (D `CulturalTourism`: +10 Solari and +5 water per sanctuary) · National Mythos (War Banner; -10% damage taken near the Champion) · Inspiring Standard (banners +2 manpower; +100% regeneration near a banner; Fusion Plant) · **Martial Perfectionism** (D `MartialPerfectionism`: +5 CP; pay +100% to recruit in +50% time for permanent +20% health and power, +100% heal cost; Military Academy) · Logistical Flourish (champion death → +50% recruitment for 10 days; Command Post) · Political Art (+8 Influence per masterpiece; charters held by Ecaz can't be proposed to vote) · Influential Plots (Influence replaces missing intel for missions / assassinations; +1 infiltration cell) · Cosmopolitan Elegance (info levels move 50% faster; +50% output at max level) · Manichean Propaganda (+1 militia slot; others lose 5 Influence per Ecaz militia killed) · Prideful Crown (within 2 regions of the Garden: +40% Annex Authority cost (for enemies, presumably), +50% militia power and health) · Native Artists (masterpieces raise sietch relation; Museum of Unbound Arts).

**Buildings:** Museum of Unbound Arts (no masterpiece limit per village; +4 max Authority / Influence / manpower per masterpiece on the planet).

**Operations:** Epic Quest (100 intel, Arrakis 1: the strongest unit in the region deals +100% damage) · Live Performance (200/200, Landsraad 2: +5 Influence per enemy killed, -5 per own unit dying or leaving, all factions) · Elacca Fog (500/500, CHOAM 2: non-mech units in combat can't be controlled, all factions).

## Expert play (T)
- Opening: few villages, pillage the future sanctuaries as long as possible (pillage pays more than the tax), perfected units if unpressured, Vipp + Rivvy or Mesa.
- Mid: sanctuaries for Authority and quirk multipliers; the garden either as a deterrent on a contested village or touching sanctuaries; masterpieces for votes / quirks.
- Late: champions farm trophies on weak enemy villages / armies; Elacca Fog to lock a fight while champions kill; capture sanctuaries around 27k; pull champions out before they die.

## Matchups (T)
Weak vs Fremen and Harkonnen (they punish ranged-heavy comps); late strong vs most with a vetted stack.

## For our AI
**As Ecaz (defaults):**
- Early caution (C8); keep the expensive army alive early (worn-army rules); pre-sanctuary pillage (C12); check champions and the garden get used at all (R4).
- Late, a fight's value includes +100 hegemony per expected kill when a champion is present (R4, R5 to read champions).

**Overrides / edge cases:**
- Betrayal is costly for Ecaz (no damage bonus, double standing loss): tension step 3 (truce breaking) should weigh it higher for Ecaz.
- Our own Annex of a sanctuary ends its bonuses: keep sanctuaries out of the Annex value until the close-out (C13).
- Its Governor bid counts for O1 (R5).

**Against Ecaz:**
- Pressure early (C7); late, near 27k it is the containment target (C6): killing a champion deletes its trophies (thousands of hegemony); decapping villages around sanctuaries can end their sanctuary status (surround rule).
- The garden village costs 100 Authority + 100 standing to attack (W): its Annex / raid value needs that cost, except under O1.
- Elacca Fog locks our units in combat too: a fight that starts under it can't be left by retreat orders (*unverified* how vanilla's retreat behaves under it).

**Already covered:** nothing Ecaz-specific yet.
