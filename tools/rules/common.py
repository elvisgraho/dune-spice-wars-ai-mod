"""Shared thresholds (docs/AI-POLICY.md §4) and bytecode-building helpers for the AI rules.
Every rules module does `from rules.common import *`; `__all__` exports the underscore helpers too."""
from inject import FB  # noqa: F401
from aware import B  # noqa: F401

SAFE_R = 300       # radius around a healing structure for the safety check
TEN_T = 10         # s: contact tension tick (rules/tension.py, AI-POLICY §5c)
TEN_R = 140        # a village within this of ours is a contact partner (one turret range + a little)
TEN_NEAR = 60      # ... at this distance or closer tension rises at full speed ...
TEN_FAR_W = 0.25   # ... and at TEN_R at this share of it (linear in between)
TEN_UP = 0.056     # tension per tick at full speed: full after ~3 min
TEN_HOT = 2        # x while anyone besieges the partner or at-war armies stand at our village
TEN_DOWN = 0.1     # tension lost per tick without a partner
TEN_LOG = 30       # s: `tension` log throttle per faction
TEN_ENTER = 1.0    # contest entry at full tension (ENTER at 0): a capture next to our village is fought even
                   # slightly ahead (Atreides let Fremen take Aid-Al'ha, 85 from Qal-nit, while short of 1.5x)
TEN_GATE = 0.99    # tension at the cap: an at-war owner's partner village is listed for vanilla Annex / Pillage even at
                   # desiredStatus 0 (its other villages stay unlisted); strength checks (siege-join, launch) still decide
TEN_FAIL = 0.5     # a vanilla launch on a tension partner that creates no order (too strong for us) x this on that pair
HEAL_COMMIT = 15   # s: a fight retreat keeps the heal structure it picked first this long (rules/heal.py)
RG_T = 30          # s: a fight retreat's committed structure is the faction's fall-back point for that area this long
RETREAT_CLEAR = 150  # a fight-retreat heal target this close to the fight's centre is in the fight (= RALLY_MIN)
INFIGHT_T = 30     # s: an army that left its own heal structure while losing a fight there judges it at OWN_T this long
STICKY = 2.0       # current resupply target is abandoned only when threat > own * STICKY
PENALTY = 1 << 28  # overwhelming threat: added to squared distance (map ~2000 -> 4e6), so any safe structure wins
DETOUR = 250       # contested threat: key + DETOUR^2, i.e. a safe structure wins only if not much farther
OVERWHELM = 2.0    # threat > (own + self) * OVERWHELM = overwhelming
HORIZON = 20       # s: moving hostile armies that can reach the circle within this count as threat (speed ~6 u/s)
HUNT_R = 450       # our free armies within this distance of the target join
LOCAL = 250        # threat radius around the target
DEFEND_R = 500     # enter: prey must be within this of one of our structures (defensive posture)
LIB_KEEP = 0.5     # spacing: a Liberate / Raze leaves about half our army home; the hostile armies that reach our land
                   # before we are back (x ENTER) must be held by that (x OWN_T)
LEASH = 650        # abort: nearest group member farther than this from all our structures
WON_R = 150        # abort `won`: contest whose village is no longer besieged, group core this far from it (= CONTACT)
CONTACT = 150      # "in contact" distance (supply trigger only fires when out of contact)
CHECK = 3          # s between abort passes
START = 10         # s between start passes
HOME_R = 300       # enter: an enemy on its own zone is huntable only this close to one of our structures
HOME_EXIT = 400    # abort: ... and the hunt is cancelled once it is farther than this from all of them
BASE_KEEP = 250    # hunt: an at-war main base this close to the prey adds its defense to the threat, x (1 - d / this)
                   # (soft: no leash; its guns reach 80, the rest is the walk back under them on draining supply)
CRUSH_T = 10       # s: hunt `supply` abort waived while we are on the prey and crush it, for this much of it running at most
DRIFT_R = 575      # abort `drift`: nearest group member farther than this from our structures, none of ours in CONTACT
HUNT_TO = 2.5      # hunt force: nearest free armies until this x their side (prey + armies free to come within
                   # REACT_R) / terrain (KILL where the start needed KILL); Smugglers sent all 8 armies (271k) at one 40k
                   # H_Soldier and left their front empty
HUNT_CAP = 2       # ... and past HUNT_CAP x (prey group size) + 1 armies, stop as soon as the entry ratio holds
                   # (a loner: 3, a pair: 5); contests of our besieged villages take every free army
CONTEST_W = 10 ** 9 # start score offset for a contest (prey besieging a structure near us): outranks every chase
CONTEST_NEAR = HOME_R  # a contest of a village not ours counts as an objective (CONTEST_W, `objective`) this close
DIST0 = 100        # start score = H / (distance of our nearest free army + DIST0)^2 (+ CONTEST_W for a contest)
ENTER = 1.5        # policy enter ratio
ABORT = 0.7        # policy abort ratio (buffer: an even-ish open-field fight, 1-2 armies down, is kept)
OWN_T = 1.3        # terrain factor on our own zone: we heal and resupply there, they drain (defender advantage)
ENEMY_T = 0.8      # terrain factor on an at-war faction's zone: they heal, we drain (attack there needs 1.5/0.8)
RETREAT = 0.65     # = data AI_WarzonePowerEstimation_RetreatRatio (patches/data.json); balance x terrain is compared
FLEE_ETA = 3       # s: 'imminent' = hostiles in contact range or able to get there within this
FLEE_R = 80        # contact range around a structure / army (warzone radius is 80)
AT_HOME_R = 120    # an army this close to a healing structure is 'at home': it stays unless attack is imminent
STRAND_NEAR_T = 15  # s: strand moves a supply-losing idle army next to our structure into it at most this often
HUNT_GAP = 30      # s between two hunt starts of one faction (policy commit; also covers vanilla early cancels)
MIN_LIFE = 0.9     # free army life ratio (= vanilla getUnits minLife)
MIN_SUPPLY = 0.9   # free army supply ratio (= vanilla getUnits minSupply)
SUP_U = 0.35       # supply budget per map unit to our land: drain 50/day (data Army_Supply_DailyDrain, 30 s day)
                   # = 1.67/s at ~6 u/s = 0.28/u, x1.25 margin
SUP_DRAIN_S = 50 / 30  # data Army_Supply_DailyDrain 50 per 30 s day: supply per second off our land (and in a fight)
SUP_RESERVE = SUP_DRAIN_S * 10  # ... plus this much in reserve (~10 s of drain, absolute: max supply ranges 65-440 by
                   # faction and upgrades, a share of it made the reserve 6-44). `short` = losing supply and below the budget
SUP_WALK = 0.28    # raw drain per map unit walked (SUP_U without the margin). Fight retreat: a short army with
                   # supply < SUP_WALK x distance to our land is `stranded`: fleeing starves it on the way anyway (and
                   # gets it shot in the back), so it isn't penalised and keeps a fight it is winning (Atreides left a
                   # 1.9:1 fight at 0 supply 250 from home: 4 of 5 armies died fleeing)
SUP_ENTER = 1.25   # hunt start: joining armies need this x the budget at the target (hysteresis vs abort `supply`)
SUP_PEN = 0.6      # fight retreat: balance x (1 - SUP_PEN x share of our fight power that is short on supply)
COVER_R = 130      # turret cover: a structure's turrets / main base guns reach this far from its centre (data: range
                   # 80 for MissileBattery and main bases, + turrets placed around the centre). Also the bunker pair
                   # distance: two villages this close cover each other
TURRET_SPREAD = 40 # a village turret covers a point within its own attack range of it in full, fading to 0 this much
                   # beyond (the fight's armies spread around the point); measured from the building, not the village
                   # centre: Ash-bat's battery (98 from Tuo-Al'waz) reached a few Atreides units yet counted in full
STAGE_R = COVER_R  # stage: a siege's regroup point stays this far from the target: out of its turrets (the militia
                   # trigger is almost at the village) and not loitering in it; Fremen's first 2 of 6 armies on Hadur
                   # stood 15-50 from it 150 s in Regroup and were shot down
STAGE_SEE = 320    # stage: a walking army is staged once this close (its own position then shows its approach side)
MB_GUN_W = 3       # main-base guns count this many times (our cover and vanilla's sizing): Fremen sized Sadnin, 113 from
                   # Arrakeen, at 1.7:1 and read 2-13 while the guns took 6 of 10 armies (provisional, one fight)
TURRET_H = 1500    # turret -> army power: offensivePotential x this HP (~one 3-unit army's health): a MissileBattery
                   # ~ one army, a main base ~ two ("feared more, not overwhelmingly"); calibrate from hunt `T`
SITE_WZ_R = 130    # fight retreat: a warzone whose centroid is this close to the sietch / renegade base of our running
                   # strike is that strike's fight (its garrison fights around the structure; = COVER_R)
OWN_COVER_ATK = 0.5  # our turret cover on an attack target (siege, raid, press) counts this share: a battery hits only
                     # units within ~80 of where it stands and doesn't follow the fight; in full when we defend.
                     # A sietch / renegade-base strike counts none (user rule; Harkonnen Tabmah: 1.39x passed, -98%)
KILL = 3.0         # "kill it on the way": a chase under enemy turret cover, or while we defend, only if the prey is
                   # in CONTACT of our free armies and we have KILL x (its threat + turret cover)
BUNKER_W = 1.3     # vanilla target score x this for a village that forms a bunker with ours (Annex / Liberate)
GATHER_R = 900     # contest of our OWN besieged village: free armies this far away join (vanilla Regroup gathers)
HOME_RING_R = 250  # a neutral village this close to our active main base, besieged by an at-war faction, is defended
                   # like our own (aimod_defend: posture, contest from GATHER_R, our walking Annexes released)
RENEGADE_R = 150   # aimod_defend: a Renegade_Drop raid army this close to a raider-besieged village = a Takeover
DEF_HOPE_IN = 1.0  # aimod_defend: skip a defense whose gathered force (all ours within GATHER_R + cover, x terrain) is
DEF_HOPE_OUT = 1.2 # ... below this x their side there; it counts again at this (hysteresis)
BUNKER_MB = 1.5    # Annex score x this for a neutral village within BUNKER_R of our main base (was a hard redirect:
                   # Fremen took 3 such villages before any deep-desert ring village); lost ones are still redirected
BUNKER_R = 110     # villages this close to our main base are its bunker (guns reach 80, + a 30 margin; 200 counted
                   # Ur-Al'nun, 181 away, as under the guns): a lost one is the Annex target first
MILITARY, DEFENSE, RESUPPLY, DISCOVERY, PATROL = 1, 2, 4, 5, 6  # AIOrderType: Basic Military Defense Protect Resupply Discovery Patrol ...
ADJ_R = 100        # annex-spacing: no second siege on a structure this close to one we already target
                   # (village nearest-neighbour median 110-155)
T_STRUCT, T_GROUP = 5, 6  # AIOrderTargetType: Entity Unit Army Ornithopter Harvester Structure Group
RAID_R = 400       # raid: our armies within this of a village may pillage it (~65 s walk; the supply budget and the
                   # home race bound it further). 250 left an army stack idle at home next to pillageable villages
RAID_TO = KILL     # raid force: nearest raid-ready armies first, until they have this x (threat + cover + militia)
                   # / terrain there (at least ENTER); the rest stays home or raids elsewhere
HOME_M = 100       # raid home race: hostile armies within (target's distance to our land + this) of our land get
                   # there before the raiders could return (~17 s reaction margin)
RECALL_R = DEFEND_R  # raid abort `defend`: a pillage this close to our besieged structure yields its armies
RELEASE_SUP = MIN_SUPPLY  # release (rules/release.py): an army below this supply share stays on an occupation under way
                   # (the pillage refill / the captured village resupplies it there; user). = vanilla's Resupply
                   # trigger: at 0.75 an army at 80% was released and at once sent home by vanilla to resupply
RELEASE_LIFE = MIN_LIFE  # ... on an Annex also one below this health (heals at the village once ours; vanilla Resupply)
RAID_GAP = 30      # s between two raid launches of one faction (commit, like HUNT_GAP)
PICK_LIFE = 0.5    # vanilla mission picks (sieges, Defense, Discovery) skip armies below this life unless fighting
PICK_LOG_T = 30    # s: lowpick log throttle per army
RAID_LIFE = 0.6    # raid army life floor (a pillage is short; vanilla sieges want 0.9 and a full refill)
RAID_ARRIVE = SUP_DRAIN_S * 30  # raid: supply an army must still have on arrival: ~30 s of militia fight drain
                   # (absolute, *unverified*: Alwahad's fight drained 85 in ~50 s; a 25% share was 16-110 by faction)
REACT_R = 480      # raid: idle at-war armies this close can reach the village before a pillage ends (militia fight
                   # ~20 s + 2 days = 60 s, at ~6 u/s); fighting, besieging or elsewhere-bound ones don't count
RAID_FAR = round(1 / ENTER, 3)  # raid start: everything within REACT_R (with the village's side) needs only this x: an
                  # army away from the village commits only with ENTER x our raid; if it comes the abort pass decides
DANGER_T = 180     # faction memory: a zone where our harvester was attacked stays dangerous this long (6 game days),
                   # linearly fading (cooldown); longer would strand good fields, shorter re-sends into the same raiders
GATHER_T = 1       # s: gather pass (Engage orders: leaders wait for the pack)
GATHER_ORD_R = 400 # armies of the order this close to the target count; farther ones are stragglers, not waited for
GATHER_GAP = 15    # an army more than this closer to the target than the farthest counted one waits (~2.5 s walk)
GATHER_MIN = 80    # ... unless already this close (in reach of the prey / militia) or fighting
GATHER_MAX = 20    # s: an order holds its leaders at most this long in all (a far laggard can't stall the attack;
                   # 10 released Atreides' fast A_Ship 17 ahead: it reached the renegade base alone, died, and its
                   # death as the only besieger cancelled the 9-army Dismantle)
DSTEP_R = 250      # desert step: our siege / raid armies in the deep desert within this of the target ...
DSTEP_IN = 40      # ... move to this far from the target on their side (the village's zone, still in the fight)
DSTEP_T = 8        # ... at most this often per army (micro re-engages; no move spam)
WORM_T = 1         # s: worm-flee pass (a targeted army has seconds before the worm arrives)
WFLEE_T = 3        # s: a worm-targeted army on sand is re-sent to rock at most this often (vanilla orders move it back)
WORM_HOLD = 20     # s: an army sent off the sand isn't free for hunts / raids / strand (no relaunch onto the same sand)
WORM_NEAR = 150    # an army moved off the sand waits there (out of vanilla's Resupply / mission picks) while a worm is
                   # this close, at most WORM_HOLD s; worm-flee moves the order's other armies on sand this close to it
WORM_STEP = 20     # rock search: ring step ...
WORM_R = 200       # ... up to this radius (none found: this far straight away from the worm)
WORM_DIRS = 16     # ... directions per ring
ZONE_NO_WORM = 1641  # attribute Zone_NoSandworm (trait WormCalling_Neighbors: regions next to a Decoy Thumper; vanilla
                     # canBeWormTarget: no worm target there)
HFLEE_T = 20       # s: an attacked team harvester is released to vanilla's re-route at most this often (it packs up)
RALLY_T = 2        # s: rally pass (rules/rally.py): gather strength when a structure faces more than we can beat
RALLY_MIN_H = 80000  # ... and that power is at least this (a lone raider is vanilla Defense's business)
HOME_MIN_H = RALLY_MIN_H  # aimod_home: hostile power free to strike our land below this counts 0 (a raider band the
                   # village militia hold; the rally ignores it too): 20k FremenRaids vs no army home aborted pillages at 10%
SWEEP_T = 60        # s: map sweep (rules/sweep.py): dead armies / ended orders / ended fights leave our maps
STRIKE_T = 2        # s: en-route strike tick (rules/strike.py): our siege armies on the march ...
STRIKE_R = 90       # ... react to an at-war army this close, like a turret (MissileBattery range 80 + a little; user)
STRIKE_RATIO = 1.0  # ... and fight it when the order's armies within LOCAL are at least this x (its side + cover):
                    # even or better starts the fight (user), the vanilla fight retreat still judges it after 5 s
STRIKE_MAX = 30     # s: ... a strike ends after this, then the march goes on
STRIKE_LEASH = 120  # ... or once the army is this far from where it started (a running enemy isn't chased; user)
STAND_R = 200      # turret steering (rules/build.py): at-war power within this of our village (turret range 80 +
                   # an idle stack at the next village, Gun-dah 115 from Annarekh) ...
STAND_MIN_H = RALLY_MIN_H  # ... at least this ...
STAND_T = 30       # s: ... standing there this long (a passing army is no standoff) ...
SPICE_FIRST_W = 100  # spice-first: a spice village's Refinery scores vanilla + this until it has one (rules/build.py)
STAND_BONUS = 100  # ... lifts MissileBattery there to vanilla score + this (vanilla building scores ~10-40)
TURRET_EXPOSED = 2  # turret-steer: our village whose zone borders this many zones held by at-war factions is a front
                    # village: it gets a MissileBattery (+STAND_BONUS) without waiting for a standing stack (user:
                    # Atreides, weakest, was overrun by Fremen through such villages with no battery built)
TURRET_REMOTE = 3   # ... also a village this many zones or more from our main base (Zone.getDistanceToPlayerBase; 1 =
                    # bordering it): too far for a relief to arrive in time if something happens (user)
TURRET_BASE_GATE = 1  # ... also a village bordering our main base's zone with this many zones of any other faction
                      # next to it (at war or not: treaties end): the way into our base (user)
TURRET_DEMOLISH = ('Marketplace', 'MaintenanceCenter', 'ResearchHub')  # ... a full front village frees a slot
                    # for it by demolishing the first of these present (Wholesale Market first), only when the battery
                    # is affordable now; none present: it stays as it is
TRES_T = 300        # s: after such a demolition, other buildings on that village are dropped from the scoring
                    # until its battery stands (vanilla would refill the slot and the next scoring demolish again)
ATTR_PEACE_FORCE = 30  # attribute row Allow_PeaceForce (Atreides): may impose ImproveRelations for Influence
CAP_EST = 90       # s: hunt contest: an occupation's full length before its progress rate is known (Fremen Annex of Tuoiel 72 s)
CAP_STALE = 300    # s: a progress record older than this is restarted
CONTEST_SPD = 6    # units/s: army speed for a contest's arrival time (aw spd 6-8.4)
CONTEST_SLACK = 10 # s: a contest still starts when it arrives this late (the capture may stall in the fight)
ASWAP_WAIT = 120   # s: Annex value: nothing affordable in the top 3 this long -> the best affordable candidate anywhere
RES_INFLUENCE = 10  # resource sheet index of Influence (ent.Faction.getResource)
RES_AUTHORITY = 6   # resource sheet index of Authority
ANNEX_RISE = 20     # Annex reserve: price rise per village we gain before the next capture starts (per owned outpost
                    # 10 x n^1.2: +18 at 8 villages, +21 at 16)
PANNEX_INF = 100   # peaceful annex (siege.py launch gate): Atreides use PeacefullyAnnex (50 Influence) only with at least
                   # this much Influence, so force peace / diplomacy keep a reserve
PANNEX_MIN_VILLAGES = 4  # ... and only once we own this many villages: the opening's idle armies annex for free
                   # while Influence is scarce (user: early peaceful annexes wasted it)
# Underworld HQs (rules/uhq.py; Smugglers). Vanilla installs whenever <= 1 HQ has an empty extension list (no cap: all
# Authority went into HQs) and scores regular extensions only by cdb aiWeights (Whisperers Lair on no-Intel villages).
UHQ_MIN = 3        # HQ cap = max(UHQ_MIN, UHQ_PER_VILLAGE x our villages); built ones are never removed
UHQ_PER_VILLAGE = 3
UHQ_AUTH = 5       # Annex reserve: next HQ's Authority = this x (HQs + 1) (data: InstallUWHeadquarter 5 + 5 per existing)
UHQ_RES_T = 120    # ... the cheapest Annex cost (siege.py `acmin`) counts this long after its last scoring
UHQ_MB_R = 500     # placement: a host village within this of its owner's main base scores up to ...
UHQ_MB_W = 1.0     # ... x (1 + this) at the base (falls linearly to x 1 at UHQ_MB_R): hardly ever recaptured there
UHQ_PLACE_W = 1.0  # placement: + this x the best production-extension gain at the village (vanilla score ~20-60)
UHQ_EXT_BASE = 10  # extension score = this (vanilla AI_BuildingScore_BaseValue) + gain (Solari-equivalent / day), only
                   # when the host produces at least one listed resource's minimum; else no score: the slot waits
UHQ_HU = 40        # Harvesters' Union (id TraffickingStation, +2% spice for us and allies): first everywhere
RES_SOLARI, RES_PLASCRETE, RES_FUEL, RES_WATER, RES_KNOWLEDGE, RES_INTEL = 1, 2, 4, 5, 9, 54  # resource sheet rows
# extension id -> flat score, or [(resource row, share of the host's production, Solari-equivalent weight, minimum host
# production / day for the extension to qualify: any one listed resource at its minimum)]; an id not
# listed scores nothing on a regular HQ (host-gain ones: Worker's Guild, Water Network / Seller, Activist Quarters;
# Contraband Caches, Scavenger Caches, Hidden Explosives, Covert Recruiters, Local Gang, Back-Alley Doctor,
# Propaganda Cell, Dead Drops, Corrupted Administrators: unused in expert play). Major HQs stay vanilla.
UHQ_EXT = {
    'TraffickingStation': UHQ_HU,
    'BootlegMarket': [(RES_SOLARI, 0.3, 1, 8), (RES_PLASCRETE, 0.3, 1, 8)],  # plascrete paid as Solari (user: >= 8)
    'WaterSmugglers': [(RES_WATER, 0.3, 3, 9)],  # user: >= 9 water
    'WhisperersLair': [(RES_INTEL, 0.3, 6, 2), (RES_INFLUENCE, 0.3, 6, 2)],  # influence paid as Intel
    'Spywares': [(RES_KNOWLEDGE, 0.3, 5, 1)],  # user: knowledge 1
    'EnergyDiversions': [(RES_FUEL, 0.3, 8, 2)],
}
FP_RETRY = 60      # s: force-peace (rules/peace.py) tries at most this often per faction
FP_SKIP = ('Fremen',)  # never forced: they break treaties at no Landsraad cost, the Influence is wasted
RALLY_R = 600      # our defenders within this of the danger structure count and are gathered
RALLY_MIN = 150    # the rally point is at least this far from the danger structure; structures this close aren't
                   # healed / fled to while the rally runs (aimod_unsafe overwhelming)
DMZ_T = 5          # s: DMZ pass (rules/dmz.py): border-village counts per faction pair, truce check
DMZ_WAR = 2        # at war: E holding this many villages in regions next to ours -> those are capture targets
DMZ_PEACE = 3      # at peace / truce: E holding this many (or one less while capturing another) -> declare war
DMZ_B = 1.0        # ... only when our army power >= this x E's
DMZ_B_FREMEN = 0.8 # ... Fremen (no Standing: breaking a truce costs them least)
DMZ_COOL = 120     # s: at most one declaration attempt per faction pair
DMZ_LOG = 60       # s: `dmz` act=on log period per pair
DMZ_W = 1.5        # vanilla Annex / Liberate score x this for a DMZ village
DMZ_PREF = 0.5     # press: a DMZ village's distance x this (ranks first)
CROSS_R = RALLY_MIN  # a heal / strand / rally walk passing this close to our structure under at-war siege (or the
                     # rally's danger structure) goes through the enemy (Harkonnen walked past Fremen at Tsimlat)
RALLY_SAFE = 150   # ... and has no at-war power within this
RALLY_MB = 150     # the main base counts this much closer (its guns fight with us)
RALLY_AT = 60      # a defender this close to the rally point has arrived (no move, not held)
RALLY_MOVE_T = 5   # s: a defender is re-sent at most this often
RALLY_HOLD = 5     # s: a rallying army stays out of vanilla's picks this long after the last pass saw it walking
RALLY_HYST = 1.15  # a running rally ends only at ENTER x this (no on / off flicker at the threshold)
RALLY_GIVEUP = 60  # s: a rally on the same danger structure still short after this concedes it ...
RALLY_COOL = 90    # s: ... for this long (not a danger structure; vanilla Defense of it gets no armies, aimod_defend skips it)
RALLY_HERE = LOCAL # defenders this close to the danger structure are already there: if they (+ turrets, x terrain) are
                   # at least DEF_HOPE_IN x its threat, commit at once instead of walking them away to gather. Armies
                   # within RALLY_AT of the running rally point never count: that is the gathered force, not D's
                   # (Fremen's point Tabr, 236 from Grim-po, made the rally commit at once; 5 of 6 went in at 0.17)
SPOS_CHECK = 2     # s: siege-position pass (rules/spos.py)
SPOS_R = 250       # Action: our siege armies this close to the target are kept off enemy guns (chasers pulled back)
SPOS_IN = 80       # Engage: only armies already this close (walkers aren't pulled forward)
SPOS_OFF = 25      # the safe point: this far from the target's centre, away from the nearest enemy structure (inside
                   # the occupation range: occupiers seen up to ~30 from the village)
SPOS_T = 4         # s: an army is re-sent at most this often (micro re-engages in between)
ALONE_HOLD = 60    # s: raid skips a village the Annex value dropped as a plain lone candidate this recently
DIST_COST_ATB = 952  # Outpost_DistanceCost_MRatio: Annex cost grows with distance (> 0); Smugglers don't have it
FAR_ZONES = 1      # extra zones of siege-target reach for a faction without that cost (vanilla AI: 1 zone total)
RAID_ZONES = 1     # ... and this many more for raid's own pillage scan (any faction): raids judge their trip by the
                   # supply budget, so vanilla's 1-zone list left too few candidates (all Devastated between waves)
KEEP_R = 60        # keep-capture (rules/spos.py): an army this close to a village we besiege / occupy isn't pulled off
                   # by vanilla micro's 'defend our vulnerable structure' Reposition (occupiers stand at 4-30)
STUCK_R = 30       # unstick (rules/spos.py): an Action siege army this close to the target's centre ...
STUCK_MOVE = 3     # ... that moved less than this ...
STUCK_T = 12       # s: ... for this long while the target is neither besieged nor occupied is stuck in the village
                   # footprint (Fremen F_Sneak 4 from Tabwan's centre, Idle/Attack every 0.5 s for 2.5 min, no siege)
DISC_RELAUNCH = 30  # s: a world event vanilla launched a Discovery on isn't launched again this soon (a trip cancelled
                    # in Waiting, e.g. supply, was re-picked every 1.5-7 s for a minute)
RAID_GAUGE = 85    # a raid doesn't start while our Annexation gauge is this full: vanilla's Annex fires within seconds
                   # and takes the raid's armies (Fremen raid on Damrekh cancelled 8 s after start)
RAID_GAUGE_T = 20  # ... unless it stayed that full this many s: the Annex isn't coming (unaffordable, no army, ...)
HRUN_T = 20        # s: an outgunned harvester under fire is sent to a safe field (or home) at most this often
BUSY_W = 0.25      # aimod_threat family: an at-war army occupying a structure more than BUSY_R from the query point
BUSY_R = 60        # counts this share (busy capturing elsewhere: no scare for defending another place)
OUT_W = 0.5        # ... a query point on our land: an idle at-war army standing off our land counts this share (it
                   # must walk in first; movers heading in count fully)
OUT_R = 100        # ... only beyond this from the query point (an idle army at the border is a threat as is)
RIDE_MAX = 60      # s: hunt / raid judgement is held at most this long while an army is in transit / hidden
OCC_W = 0.5        # aimod_react: an at-war army within REACT_R busy occupying / contesting a structure counts this much
                   # (it can break off: Fremen left Ars-ha and hunted Atreides at their harvester)
DANGER_KEY = 600 * 600  # harvester field choice: squared-distance penalty at full danger (a field up to ~600 farther wins)
ALLY_WIN = 150    # hunt: a third party allied / at peace with the prey counts only if it is within our nearest army's
                   # distance + this (~25 s of fight at ~6 u/s): farther ones arrive after the kill. A third party at
                   # war with the prey doesn't count (it fights the prey too). Log: Harkonnen hunt on 3 Fremen next
                   # to an Atreides stack at war with both
ENGAGE_R = STAGE_R + 30  # siege-engage: order armies this close to the target are at it (staged or in the fight); farther
                   # ones are still walking and would arrive one by one (Harkonnen raid on Har-Al'sud)
PART_X = 2.0      # siege-engage: an early Engage with only part of the order's armies at the target needs this x the
                  # normal ratio (else it waits for the rest: Fremen's 2 of 3 on Haykus at 2.4x est., vanilla 1.5, lost one)
OCC_REFILL = 0.5   # = data Army_Supply_Resupply_OccupationRatio: share of max supply a finished pillage refills
NEUTRAL_REQ = 1.25 # siege launch: required ratio on a neutral target (vanilla 1.0). Below ENTER: militia is known and
                   # never reinforced, and siege-join adds the idle armies nearby on top
EARLY_VILLAGES = 2  # opening: while we own fewer villages than this, a neutral target needs only EARLY_REQ (vanilla)
EARLY_REQ = 1.0    # ... at launch and at the target: the 2 armies of a normal start vs a 2-defense village fall between
                   # 1.0 and NEUTRAL_REQ, and the AI waited instead of taking its first villages
JOIN_R = HUNT_R    # siege launch: idle armies this close to the target may join (vanilla sends the minimum) ...
JOIN_TO = KILL    # ... nearest first, until we have this x their power there (KILL: a fight over in seconds)
SIETCH_ARMIES = 8  # sietch / renegade-base strike: at least as many armies as the garrison it always spawns ...
RENEGADE_ARMIES = 10  # ... (8 sietch defenders, 10 renegade-base defenders)
SITE_REQ = HUNT_TO  # sietch / renegade-base strike: our armies vs its garrison at launch, after joining and to engage
                   # (2.5). The garrison (< 8 sietch / < 10 renegade units) doesn't respawn, but the sietch's random harass
                   # tick (3 units, unrelated to the fight) can fire during a strike, on top of what the estimate counts (Harkonnen Ey-Al'wan
                   # 31:28: order balance 2.6 -> 0.52 in one tick, no army near, 9 armies at 1.53x, cancelled -4;
                   # Smugglers there 9:06, 11 at 1.58x, 3.05 -> 0.14, cancelled -4); ENTER 1.5 lost every logged strike
RETRY = 30         # s: a vanilla siege target launched again this soon after its last launch ended at once
                   # (e.g. InsufficientSupply at +0 s) is dropped from the target scores until then
RETRY_MAX = 240    # s: ... doubled per relaunch that came right after the block ran out (failing at once again), up
                   # to this; reset to RETRY once a launch lasted
FAIL_N = 3         # stuck: this many vanilla launches on one target ending without an order (ArmyNotStrongEnough,
FAIL_WIN = 120     # NotEnoughArmies, ...) within this many s drop it from the target scores for FAIL_BLOCK s, doubled
FAIL_BLOCK = 120   # up to FAIL_MAX while it keeps coming back (a thinking loop: the armies idle at a patrol meanwhile)
FAIL_MAX = 480
STUCK_IDLE = 0.5   # stuck counts only when vanilla's idle list held >= this x our free armies (else they were busy)
PURSUIT_T = 15    # s without progress that end a chase (hunt abort `chase`) or a mission-less fight (fight retreat
                   # `pursuit`): a fleeing army at our speed keeps its distance forever (~90 units per 15 s)
CATCH_T = 30      # s: closing in counts as chase progress only at a rate that reaches the prey within this (a raider
                   # running at ~4 u/s from 6 u/s hunters 205 away "closed" 30 per 15 s and was followed 57 s / 230 units)
CATCH_R = 40      # ... "reached" = this close (weapon range)
PROGRESS = 0.1     # progress = the enemy there lost this share of its power since the last progress ...
CLOSE = 30         # ... or (hunt) our nearest army got this much closer to the prey (~5 s of walking)
CHASE_LIFE = 0.35  # hunt: a prey running on its own land is followed only while a member is below this life (a kill is near)
HUNT_AREA_T = 60   # s: no chase / neutral hunt starts within LOCAL of where a hunt aborted on supply / weak / turret / desert
TRIVIAL = 0.1      # fight retreat `trivial`: off our zone, no mission, the enemy there worth < this x our power -> 0
WZB_T = 5          # s: diagnostic `wzb` row (fight balance raw / adjusted) per warzone at most this often
PURSUIT_STALE = 3  # s: a warzone record not refreshed for this long belongs to an earlier fight (the balance is read
                   # every tick while the fight runs)
GIVEUP_T = 90      # s: an army a chase gave up on (`chase` abort) isn't chased again for this long (it outruns us;
                   # a new chase would end the same way 45 s later)
DISCOVERY = 5      # AIOrderType index of Discovery (Basic Military Defense Protect Resupply Discovery Patrol)
DISC_HORIZON = 40  # s: a running Discovery trip counts hostile movers that can reach the event within this (2 x the
                   # launch HORIZON): the lone army leaves while it still has a lead (Harkonnen H_Soldier at a relic saw
                   # 8 Smugglers armies walk 290 units at it for ~40 s and only left in contact, 1v8)
DISC_RETRY = 60    # s: a world event whose Discovery trip we gave up isn't sent to again this soon (no launch/abort loop)
RAID_KEEP = 3      # raid never hits the top this many Annex choices (vanilla's scores), affordable or not: the next
                   # annexes; the rest of the map is fair game (vanilla's 2-5 + Devastated own pillages left Smugglers idle)
AKEEP_T = 240      # s: a top-RAID_KEEP Annex choice stays protected this long after the last `annex-keep` scan listed
                   # it (every START s per faction, rules/raid.py), from raid and from vanilla's Pillage gauge (Smugglers' gauge pillaged its top Annex choices Arslulah x3,
                   # Ya-lab; raid hit Haywaz just after it left the top 3: Devastated + our Annex cost doubled)
BEHIND_E = 0.25    # raid: a village is behind another faction's main base M (seen from our nearest main base B) when
                   # M is nearer B than it and d(B,M) + d(M,v) <= d(B,v) x (1 + this): never raided
RAID_RETRY = 60    # s: a village our raid left (aborted, or cancelled at once by vanilla) isn't raided again this soon
FRONT_R = 600      # director: enemy villages this close to our land are the front (policy §5b)
PRESS = KILL       # ... soft = the spare armies in reach have this x (armies in reach + cover + militia) / terrain
PRESS_R = HUNT_R   # ... spare armies this close to a village can take part (same reach as siege-join)
PRESS_KEEP = ABORT  # a press is dropped when our power there (any task) x terrain < this x their side
PRESS_MAX = 240    # s: a press not finished by then is dropped (`slow`); enemy Annex ~ walk + militia + 6 days
PRESS_RETRY = 120  # s: a dropped press target isn't pressed again this soon
ANNEX_SPECIAL = 30  # Annex score + this for a village in a special region (region aiWeight >= 20, vanilla adds that
                    # weight once; specials yield more hegemony), before the cost ratio
ANNEX_SIETCH = 10  # Annex score + this for a village whose zone has a sietch (Zone.getSietch), before the cost ratio
ANNEX_SPICE1 = 4    # Annex score x this for a spice village while we own none (vanilla +100 too), after the cost
                    # ratio and every other term (x2 could lose to a +50 special x centre x compactness): the first capture is a spice field
                    # ratio: the opening takes a spice field first. Not for SPICE_ANY factions (harvest anywhere)
SPICE_ANY = ('Fremen', 'Vernius')  # their first-spice bonus (vanilla +100) is removed
ANNEX_ZONES = 1    # Annex target reach: vanilla's 1 zone from our territory + this (every faction; Smugglers get FAR_ZONES
                   # too): vanilla offered 1-2 candidates per pick, so scores had nothing to choose from
VAN_HOPS_CAP = 3   # vanilla's -10 per zone from our main base (AI_StructureScore_PerZone_Distance_Weight) counts at most
                   # this many zones: a central / special village a zone or two farther out can still win on value
CENTER_W = 0.08    # Annex score x (1 + CENTER_W x closeness to the map centre (mean village position; 1 there, 0 at the
                   # farthest village)): the middle gives wider map access (strategy GENERAL "Expansion")
CENTER_BASE_R = 350  # ... no centre bonus within this of another faction's main base (access, not parking at a capital)
ANNEX_SP_EARLY_N = 4  # special table: "early" specials count their early bonus while we own fewer villages than this
CLAIM_HOPS = 2      # free Annex (cost 0: Water Subsidies on Polar Sink) only within this many zones of our territory
                    # (Zone.getDistanceToPlayerTerritory: 1 = bordering, 2 = one zone between): no march to the middle
CLAIM_R = 600       # ... with our armies within this of it at least ENTER x the at-war armies that can reach it; each
                    # AI judges only itself: a weak or far one stays out, two strong neighbours meet there
CLAIM_ADD = 20      # ... bonus (score + this) for an AI that passes: the free village is worth taking now
ANNEX_SP_SMUG_CAP = 40  # Smugglers' special bonus at most this (no distance cost: never dragged across the map)
# special region -> (bonus for every faction, {faction: bonus}); region ids from data `region` (variants listed).
# Strategy GENERAL "Specials" table (T). Unlisted specials (aiWeight >= 20) keep ANNEX_SPECIAL; Desolation is unownable
_SP_FREMEN = {'Fremen': 50}
ANNEX_SPECIALS = {
    'Pit': (50, {'Corrino': 70}), 'Pit_Polar': (50, {'Corrino': 70}), 'Pit_Volcanic': (50, {'Corrino': 70}),
    'SandFall': (50, {}), 'WormNest': (50, {}),
    'Pole': (20, {'Atreides': 50, 'Harkonnen': 50}),
    'ImperialBasin': (20, {'Smugglers': 50}),
    'MoonDewVale': (20, {'Fremen': 50, 'Smugglers': 50}), 'MoonDewVale_Volcanic': (20, {'Fremen': 50, 'Smugglers': 50}),
    'Volcano': (20, {'Fremen': 50, 'Corrino': 50, 'Vernius': 50}),
    'SpaceCruiserWreck': (20, _SP_FREMEN), 'SpaceCruiserWreck_Red': (20, _SP_FREMEN),
    'SpaceCruiserWreck_Polar': (20, _SP_FREMEN), 'SpaceCruiserWreck_Volcanic': (20, _SP_FREMEN),
    'CrescentRidge': (20, _SP_FREMEN), 'CrescentRidge_Red': (20, _SP_FREMEN), 'CrescentRidge_Idaho': (20, _SP_FREMEN),
    'CrescentRidge_Polar': (20, _SP_FREMEN),
    'ShieldWall': (10, {}), 'ShieldWall_Volcano': (10, {}), 'RichPit': (10, {}), 'RichPit_Volcanic': (10, {}),
    'RichPit_Red': (10, {}), 'AcidLake': (10, {}), 'AcidLake_Red': (10, {}), 'AcidLake_Volcanic': (10, {}),
}
ANNEX_SPECIALS_EARLY = {'MountIdaho': (40, 15), 'ObservatoryM': (40, 15)}  # (early, later)
NEAR_W = 0.25       # Annex score x (1 + NEAR_W x (NEAR_REF - d) / NEAR_REF), clamped to 1 +- NEAR_W, d = distance to our
NEAR_REF = 400      # nearest structure on our land: compact land, short walks to defend (factions with distance
                    # annex costs only: Smugglers (Outpost_DistanceCost_MRatio 0) cap far villages by design)
DD_ATB = 969       # attribute DeepDesert_Surounded_GainControl (Fremen_HegemonyBonus1): Zone.updateOwner gives a deep
                   # desert to the single owner of all its neighbours with a village or a main base
DD_W = 1.0         # Annex score x (1 + DD_W x sum over adjacent unowned deep deserts of chance / (1 + still missing
DD_W_PRE = 1.0     # after this one)), DD_W with the attribute, DD_W_PRE for Fremen before it (plan ahead: at 0.5
                   # the opening took a special and a spice village before the ring villages next door)
DD_ADD = 40        # + this x the best ring chance (contest-adjusted, x DD_LINK, x weight, x cmin / cost) for a ring
                   # village: a flat bonus like ANNEX_SPECIAL (the multiplier alone shrinks to ~x1 on big rings)
DD_FAR = 0.5       # a deep desert more zone hops from our main base than the nearest ringable one: its ring chance x this
DD_LINK = 0.5      # ring bonus x this when the candidate touches none of our zones except deep desert: reaching it
                   # means crossing desert (supply), so the ring grows outward from land we hold
DD_CAP = 2         # ... sum capped (completing one = x2, one away = x1.5)
DD_ENEMY = 0.5     # chance x this per missing neighbour owned by another faction or within DD_BASE_R of another
DD_BASE_R = 350    # faction's main base (contested: progress there stalls); an enemy main-base zone among them = 0
DD_HOLD_MISS = 2   # the Annex hold needs a ring this close: at most this many villages missing besides the candidate
DD_TRIES = 3       # an uncontested ring village launched this often (two Annex attempts failed: resistance) stops
                   # holding the other Annex targets (Fremen: off-ring villages are pillaged while the ring is open)
ANNEX_FLOOR = 0.1   # a positive score never drops below this (vanilla pickWeight draws by score)
ASCORE_T = 30       # s: `ascore` log throttle per faction
PRESS_W = 10       # Annex score x this for the pressed village (vanilla picks at random among the top scores)
GAUGE_FIRE = 100   # = data AI_Gauge_GoalValue: a military gauge fires at this value (failures x0.85 sink it)
RECOVER_IN = 0.5   # director RECOVER: more than this share of our army power is worn (life < RAID_LIFE or short of
                   # supply for the way home): nothing new (no press, no raid launch), heal and gather (policy §5b #2)
RECOVER_OUT = 0.35  # ... and it ends only below this share (hysteresis: healing armies cross the line one by one)
RECOVER_POST = 6   # posture index of RECOVER in rules/strat.py POSTURES (read by raid through map `spost`)
STRAT_LOG = 60     # s: a `strat` row per faction at least this often, and on every posture / target change
CANCEL = 2      # ent.ActionEndReason: Success Fail Cancel Override
REGROUP = 3        # AIOrder.phase: Paused Waiting Preparation Regroup Engage Action Retreat
ACTION = 5
BEST_COUNT = 877   # Const.fValuesCache index of AI_StructureScore_BestStructuresCount: vanilla picks its siege
                   # target at random among this many best scores (Insane 2 ... Easy 5)


def _fcache_int(fb, b, cx, idx, fac):
    """i32 = Const.fValuesCache[idx][fac.aiDifficulty] (per-difficulty data constant, read as tryAction does)."""
    c = fb.reg(cx.t('$Const'))
    fb.op('GetGlobal', dst=c, **{'global': cx.global_of('$Const')})
    out = b.const('i32', 0)
    done = _uid('fc')
    cache = b.field(c, 'fValuesCache')
    fb.op('JNull', reg=cache, offset=done)
    row = b.cast(b.call('hl.types.ArrayObj.getDyn', cache, b.const('i32', idx)), 'hl.types.ArrayBytes_Float')
    fb.op('JNull', reg=row, offset=done)
    v = b.call('hl.types.ArrayBytes_Float.getDyn', row, b.call('ent.Faction.get_aiDifficulty', fac))
    fb.op('JNull', reg=v, offset=done)
    f = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=f, src=v)
    fb.op('ToInt', dst=out, src=f)
    fb.label(done)
    return out


def _alloc_fn(cx):
    """Static ArrayObj.alloc (unnamed): the Call1 after `Type; Call2 alloc_array; UnsafeCast` in tryArmyAction.
    Returns (alloc_array, alloc, [type reg type, native array type, cast type]) copied from that site."""
    f = cx.fn('logic.ai.AIMilitary.tryArmyAction')
    ops = f.ops
    nat = {n.findex.value for n in cx.code.natives if n.name.resolve(cx.code) == 'alloc_array'}
    for i in range(len(ops) - 2):
        if ops[i].op == 'Call2' and ops[i].df['fun'].value in nat and ops[i + 1].op == 'UnsafeCast' \
                and ops[i + 2].op == 'Call1':
            c = ops[i].df
            regs = [f.regs[c['arg0'].value].value, f.regs[c['dst'].value].value, f.regs[ops[i + 1].df['dst'].value].value]
            return c['fun'].value, ops[i + 2].df['fun'].value, regs
    raise ValueError('behave: ArrayObj.alloc pattern not found')


def _ratio(fb, b, v):
    """f64 register = v (float constant via int/100; crashlink has no float constants)."""
    r = fb.reg(fb.cx.t('f64'))
    fb.op('SDiv', dst=r, a=b.const('f64', int(round(v * 100))), b=b.const('f64', 100))
    return r


def _state(fb, b, cx):
    gs = fb.reg(cx.t('$Game'))
    fb.op('GetGlobal', dst=gs, **{'global': cx.global_of('$Game')})
    return b.field(b.field(gs, 'inst'), 'state')


def _army_loop(fb, b, arr, alen, i, name, done):
    """Loop head: next live ent.Army from arr (skips null, militia, transported, dead). Returns the army register."""
    fb.op('Int', dst=i, ptr=b.code.add_i32(0).value)
    b.loop_head(name)
    fb.op('JSGte', a=i, b=alen, offset=done)
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', arr, i), 'ent.Army')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=a, offset=name)
    fb.op('JTrue', cond=b.field(a, 'isMilitia'), offset=name)
    fb.op('JTrue', cond=b.call('ent.Entity.isTransported', a), offset=name)
    fb.op('JTrue', cond=b.call('ent.Entity.isDead', a), offset=name)
    return a


def _defends(fb, b, cx, fac, a, ds, none):
    """ds = the entity fac's Defense order defends (AIOrderType 2 Defense(ent.Entity): a structure of ours) for
    the order army a is in; jump to `none` when a is in no Defense order."""
    ords = b.field(b.field(b.field(fac, 'aiController'), 'aiOrders'), 'orders')
    fb.op('JNull', reg=ords, offset=none)
    k, ix = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    lo = _uid('dfo')
    fb.op('Mov', dst=k, src=b.field(ords, 'length'))
    b.loop_head(lo)
    fb.op('JSLte', a=k, b=b.const('i32', 0), offset=none)
    fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', ords, k), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset=lo)
    ou = b.field(o, 'units')
    fb.op('JNull', reg=ou, offset=lo)
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', ou, fb.dyn(a)), offset=lo)
    ot = b.field(o, 'type')
    fb.op('EnumIndex', dst=ix, value=ot)
    fb.op('JNotEq', a=ix, b=b.const('i32', DEFENSE), offset=none)
    st = fb.reg(cx.t('ent.Entity'))
    fb.op('EnumField', dst=st, value=ot, construct=DEFENSE, field=0)
    fb.op('JNull', reg=st, offset=none)
    fb.op('Mov', dst=ds, src=st)


def _my_armies(fb, b, fac, fail):
    arr = b.cast(fb.get(fac, 'armies', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=arr, offset=fail)
    return arr, b.field(arr, 'length')


def _riding(fb, b, cx, helpers, fac, order, units, event, skip):
    """Jump to `skip` when an army of `units` is transported (worm ride, shuttle: _army_loop skips it, so an order's
    power reads 0 in transit); logs `event` (f, a) once per order per 10 s."""
    k = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    head, done, clr = _uid('rd'), _uid('rdd'), _uid('rdc')
    rm = _global_map(fb, b, cx, 'ride')
    b.loop_head(head)
    fb.op('JSGte', a=k, b=b.field(units, 'length'), offset=clr)
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', units, k), 'ent.Army')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=a, offset=head)
    fb.op('JFalse', cond=b.call('ent.Entity.isTransported', a), offset=head)
    # held at most RIDE_MAX s per order (map `ride` order -> first seen): a hidden army must not freeze it
    q = fb.reg(cx.t('f64'))
    rv = b.call('haxe.ds.ObjectMap.get', rm, fb.dyn(order))
    tnow = b.field(_state(fb, b, cx), 'time')
    first = _uid('rdf')
    fb.op('JNull', reg=rv, offset=first)
    fb.op('SafeCast', dst=q, src=rv)
    fb.op('Sub', dst=q, a=tnow, b=q)
    fb.op('JSGt', a=q, b=b.const('f64', RIDE_MAX), offset=done)
    fb.op('JAlways', offset=first + 'l')
    fb.label(first)
    b.call('haxe.ds.ObjectMap.set', rm, fb.dyn(order), fb.dyn(tnow))
    fb.label(first + 'l')
    _throttle(fb, b, cx, event, order, 10, skip)
    _log_ev(fb, b, cx, helpers, event, [('f', fb.get(fac, 'kind')), ('a', a)])
    fb.op('JAlways', offset=skip)
    fb.label(clr)  # nobody in transit: the next ride gets a fresh RIDE_MAX
    b.call('haxe.ds.ObjectMap.remove', rm, fb.dyn(order))
    fb.label(done)


def _redirect(cx, target, callers, wrapper):
    tid = cx.fn(target).findex.value
    n = 0
    for caller in callers:
        sites = [op for op in cx.fn(caller).ops if op.op.startswith('Call') and op.df.get('fun') is not None
                 and op.df['fun'].value == tid]
        if len(sites) != 1:
            raise ValueError(f'turret cover: expected 1 {target} call in {caller}, found {len(sites)}')
        sites[0].df['fun'].value = wrapper
        n += 1
    return n


def _new_array(fb, b, cx):
    """Empty hl.types.ArrayObj, built the way the compiler does it."""
    nat, alloc, (t_ty, t_raw, t_cast) = _alloc_fn(cx)
    ty = fb.reg(t_ty)
    fb.op('Type', dst=ty, ty=cx.t('ent.Unit'))
    raw, raw2 = fb.reg(t_raw), fb.reg(t_cast)
    fb.op('Call2', dst=raw, fun=nat, arg0=ty, arg1=b.const('i32', 0))
    fb.op('UnsafeCast', dst=raw2, src=raw)
    arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Call1', dst=arr, fun=alloc, arg0=raw2)
    return arr


def _tick(fb, b, cx, t, period, skip):
    """Jump to `skip` unless floor(t/period) != floor((t-dt)/period) (dt = reg 1)."""
    p = b.const('f64', period)
    q1, t2, q2 = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('SDiv', dst=q1, a=t, b=p)
    fb.op('Sub', dst=t2, a=t, b=1)
    fb.op('SDiv', dst=q2, a=t2, b=p)
    fb.op('JEq', a=b.to_int(q1), b=b.to_int(q2), offset=skip)


GLOBALS = {}       # name -> (code, global index): added globals, one set per boot file build


_UID = [0]


def _strong_site(fb, b, st, yes):
    """Jump to `yes` if structure st (ent.Structure reg, may be null) is a sietch or a renegade base."""
    no = _uid('_ss')
    fb.op('JNull', reg=st, offset=no)
    fb.op('JTrue', cond=b.call('ent.Structure.isSietch', st), offset=yes)
    fb.op('JTrue', cond=b.call('ent.Structure.isRenegadeBase', st), offset=yes)
    fb.label(no)


def _atk_cover(fb, b, m, st=None):
    """m = our turret cover at an attack target -> x OWN_COVER_ATK; 0 when st (the target structure, ent.Structure
    reg) is a sietch / renegade base: its garrison is fought at the target, not under our guns."""
    z, d = _uid('_acz'), _uid('_acd')
    if st is not None:
        _strong_site(fb, b, st, z)
    fb.op('Mul', dst=m, a=m, b=_ratio(fb, b, OWN_COVER_ATK))
    fb.op('JAlways', offset=d)
    fb.label(z)
    fb.op('Mov', dst=m, src=b.const('f64', 0))
    fb.label(d)


def _strong_tf(fb, b, tf, st):
    """tf = 1 when st is a sietch / renegade base: the terrain factor's reasons (we heal and resupply on our zone,
    they drain) don't hold for a garrison that needs neither (Tabmah lay in Harkonnen's zone: bar / 1.3)."""
    d = _uid('_stf')
    one = _uid('_st1')
    _strong_site(fb, b, st, one)
    fb.op('JAlways', offset=d)
    fb.label(one)
    fb.op('Mov', dst=tf, src=b.const('f64', 1))
    fb.label(d)


def _uid(prefix):
    _UID[0] += 1
    return f'{prefix}{_UID[0]}'


def _global_map(fb, b, cx, name):
    """Added global haxe.ds.ObjectMap `name` (state kept between calls; not saved with the game), created on
    first use. Maps: 'hunt' faction -> last hunt start time; 'heal'/'retreat' key -> last log time (throttle)."""
    om_t = cx.t('haxe.ds.ObjectMap')
    if name not in GLOBALS or GLOBALS[name][0] is not cx.code:
        from crashlink.core import tIndex
        ti = tIndex()
        ti.value = om_t
        cx.code.global_types.append(ti)
        GLOBALS[name] = (cx.code, len(cx.code.global_types) - 1)
    g = GLOBALS[name][1]
    r = fb.reg(om_t)
    have = _uid('havemap')
    fb.op('GetGlobal', dst=r, **{'global': g})
    fb.op('JNotNull', reg=r, offset=have)
    fb.op('New', dst=r)
    v = fb.reg(cx.t('void'))
    ctor = cx.fn('haxe.ds.$ObjectMap.__constructor__')
    fb.op('Call1', dst=v, fun=ctor.findex.value, arg0=r)
    fb.op('SetGlobal', src=r, **{'global': g})
    fb.label(have)
    return r


def _fac_map(fb, b, cx, name, fac):
    """Per-faction ObjectMap: global map `name` faction -> its own ObjectMap (created on first use). For state two
    factions must not overwrite (one-value-per-key maps flip when both write the same key)."""
    top = _global_map(fb, b, cx, name)
    om_t = cx.t('haxe.ds.ObjectMap')
    r = fb.reg(om_t)
    have, new = _uid('fmh'), _uid('fmn')
    cur = b.call('haxe.ds.ObjectMap.get', top, fb.dyn(fac))
    fb.op('JNull', reg=cur, offset=new)
    fb.op('Mov', dst=r, src=b.cast(cur, 'haxe.ds.ObjectMap'))
    fb.op('JAlways', offset=have)
    fb.label(new)
    fb.op('New', dst=r)
    v = fb.reg(cx.t('void'))
    fb.op('Call1', dst=v, fun=cx.fn('haxe.ds.$ObjectMap.__constructor__').findex.value, arg0=r)
    b.call('haxe.ds.ObjectMap.set', top, fb.dyn(fac), fb.dyn(r))
    fb.label(have)
    return r


def _throttle(fb, b, cx, name, key, period, skip):
    """Jump to `skip` if map `name` saw `key` less than `period` game seconds ago; else record now and fall through."""
    mp = _global_map(fb, b, cx, name)
    t = b.field(_state(fb, b, cx), 'time')
    last = b.call('haxe.ds.ObjectMap.get', mp, fb.dyn(key))
    go = _uid('thr')
    fb.op('JNull', reg=last, offset=go)
    lf = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=lf, src=last)
    fb.op('Sub', dst=lf, a=t, b=lf)
    fb.op('JSLt', a=lf, b=b.const('f64', period), offset=skip)
    fb.label(go)
    b.call('haxe.ds.ObjectMap.set', mp, fb.dyn(key), fb.dyn(t))


def _log_ev(fb, b, cx, helpers, event, fields):
    """Log one AIMOD event: fields = [(key, reg | str)]; f64 regs are logged x100 as ints when key ends with '%',
    entities through the entity describer, strings as given."""
    d = fb.reg(cx.t('dynobj'))
    fb.op('New', dst=d)
    b.put(d, 'e', fb.string(event))
    for k, r in fields:
        if isinstance(r, str):
            b.put(d, k, fb.string(r))
        elif k.endswith('%'):
            x = fb.reg(cx.t('f64'))
            fb.op('Mul', dst=x, a=r, b=b.const('f64', 100))
            b.put(d, k[:-1], b.to_int(x))
        elif fb.regs[r] == cx.t('f64'):
            b.put(d, k, b.to_int(r))
        elif fb.regs[r] in (cx.t('ent.Entity'), cx.t('ent.Army'), cx.t('ent.Structure')):
            er = fb.reg(cx.t('dyn'))
            src = r
            if fb.regs[r] != cx.t('ent.Entity'):
                src = fb.reg(cx.t('ent.Entity'))
                fb.op('Mov', dst=src, src=r)
            fb.op('Call1', dst=er, fun=helpers['ent'], arg0=fb.dyn(src))
            b.put(d, k, er)
        else:
            b.put(d, k, r)
    v = fb.reg(cx.t('void'))
    fb.op('Call1', dst=v, fun=helpers['log'], arg0=fb.dyn(d))


def field_name_t(cx, obj_type, index):
    return cx.code.types[obj_type].definition.resolve_fields(cx.code)[index].name.resolve(cx.code)



def _cap_rem(fb, b, cx, v, t, stalled):
    """Remaining s of the occupation at village v (anyone's: contest hunt, release): (1 - progress) / the progress
    rate since v was first judged (maps `cpgt` / `cpgp`; restarted when progress drops or the record is older than
    CAP_STALE), (1 - progress) x CAP_EST before a rate is known (< 5 s). Jumps to `stalled` when v has no siege or
    its occupation makes no progress. Returns the (remaining, progress) registers (0 on the stalled path)."""
    u = _uid('cr')
    sg = b.field(v, 'siege')
    lp, lq, lrem, lp0 = (fb.reg(cx.t('f64')) for _ in range(4))
    fb.op('Mov', dst=lrem, src=b.const('f64', 0))
    fb.op('Mov', dst=lp, src=b.const('f64', 0))
    fb.op('JNull', reg=sg, offset=stalled)
    fb.op('Mov', dst=lp, src=b.call('ent.comp.SiegeComponent.getOccupationActionProgress', sg))
    cpgt, cpgp = _global_map(fb, b, cx, 'cpgt'), _global_map(fb, b, cx, 'cpgp')
    vt = b.call('haxe.ds.ObjectMap.get', cpgt, fb.dyn(v))
    fb.op('JNull', reg=vt, offset=u + 'new')
    fb.op('SafeCast', dst=lp0, src=b.call('haxe.ds.ObjectMap.get', cpgp, fb.dyn(v)))
    fb.op('JSLt', a=lp, b=lp0, offset=u + 'new')  # a new capture there: restart
    fb.op('SafeCast', dst=lq, src=vt)
    fb.op('Sub', dst=lq, a=t, b=lq)
    fb.op('JSGt', a=lq, b=b.const('f64', CAP_STALE), offset=u + 'new')
    fb.op('JSLt', a=lq, b=b.const('f64', 5), offset=u + 'est')
    fb.op('Sub', dst=lp0, a=lp, b=lp0)
    fb.op('JSLte', a=lp0, b=b.const('f64', 0), offset=stalled)  # no progress: stalled
    fb.op('SDiv', dst=lp0, a=lp0, b=lq)  # rate per s
    fb.op('Sub', dst=lrem, a=b.const('f64', 1), b=lp)
    fb.op('SDiv', dst=lrem, a=lrem, b=lp0)
    fb.op('JAlways', offset=u + 'done')
    fb.label(u + 'new')
    b.call('haxe.ds.ObjectMap.set', cpgt, fb.dyn(v), fb.dyn(t))
    b.call('haxe.ds.ObjectMap.set', cpgp, fb.dyn(v), fb.dyn(lp))
    fb.label(u + 'est')
    fb.op('Sub', dst=lrem, a=b.const('f64', 1), b=lp)
    fb.op('Mul', dst=lrem, a=lrem, b=b.const('f64', CAP_EST))
    fb.label(u + 'done')
    return lrem, lp


def _crosses(fb, b, cx, ax, ay, sx, sy, px, py, r, yes):
    """Jump to `yes` when the straight walk (ax, ay) -> (sx, sy) passes within r of (px, py) on the way: the point
    projects strictly inside the segment and lies within r of it (f64 registers; a point behind the start or past
    the end is not on the way)."""
    no = _uid('cr')
    vx, vy, wx, wy, dt, ll = (fb.reg(cx.t('f64')) for _ in range(6))
    fb.op('Sub', dst=vx, a=sx, b=ax)
    fb.op('Sub', dst=vy, a=sy, b=ay)
    fb.op('Sub', dst=wx, a=px, b=ax)
    fb.op('Sub', dst=wy, a=py, b=ay)
    fb.op('Mul', dst=dt, a=vx, b=wx)
    fb.op('Mul', dst=ll, a=vy, b=wy)
    fb.op('Add', dst=dt, a=dt, b=ll)
    fb.op('JSLte', a=dt, b=b.const('f64', 0), offset=no)
    fb.op('Mul', dst=ll, a=vx, b=vx)
    fb.op('Mul', dst=vy, a=vy, b=vy)
    fb.op('Add', dst=ll, a=ll, b=vy)
    fb.op('JSGte', a=dt, b=ll, offset=no)
    # squared distance to the line: |w|^2 - (v.w)^2 / |v|^2
    fb.op('Mul', dst=dt, a=dt, b=dt)
    fb.op('SDiv', dst=dt, a=dt, b=ll)
    fb.op('Mul', dst=wx, a=wx, b=wx)
    fb.op('Mul', dst=wy, a=wy, b=wy)
    fb.op('Add', dst=wx, a=wx, b=wy)
    fb.op('Sub', dst=wx, a=wx, b=dt)
    fb.op('JSLt', a=wx, b=b.const('f64', r * r), offset=yes)
    fb.label(no)


def build_chain(cx, fns):
    """One (AIMilitary, dt) -> void function calling each of fns in order (each has its own throttle and trap)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    void = fb.reg(cx.t('void'))
    for f in fns:
        fb.op('Call2', dst=void, fun=f, arg0=0, arg1=1)
    fb.op('Ret', ret=void)
    return fb.build()


def _skip_striking(fb, b, cx, helpers, army, skip):
    """Jump to `skip` while army is in an en-route strike (aimod_striking, rules/strike.py) or waits on rock after a
    worm flee (aimod_wormonly, rules/worm.py: a siege army keeps its order there): rules that move order armies
    (gather, stage, desert-step, spos) leave it alone (desert-step ran right after worm-flee in the same tick and
    walked it back across the sand to the village)."""
    e = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=e, src=army)
    r = fb.reg(cx.t('bool'))
    fb.op('Call1', dst=r, fun=helpers['striking'], arg0=e)
    fb.op('JTrue', cond=r, offset=skip)
    fb.op('Call1', dst=r, fun=helpers['wormonly'], arg0=e)
    fb.op('JTrue', cond=r, offset=skip)




CRUMBS = []        # step id -> 'module.py:line' (_crumb_begin), reset per build, written to work/crumbs.json
CRUMB_LOG_T = 30   # s: `rfail` at most this often per rule and faction


def _crumb_src():
    import sys
    from pathlib import Path
    f = sys._getframe(2)
    while f is not None:
        stem = Path(f.f_code.co_filename).stem
        if stem not in ('inject', 'aware', 'common'):
            return f'{stem}.py:{f.f_lineno}'
        f = f.f_back
    return 'unknown'


def _crumb_begin(fb, b, cx, helpers, rule):
    """Step probe for a tick rule (reg 0 = AIMilitary), no exception handler involved (logging trap handlers
    crashed the game): map `crumb_<rule>` faction module -> step. A run sets 0, then before every Call op the step
    id of that call (CRUMBS: its source line), and _crumb_end sets -1. A run that finds a step >= 0 knows the last run
    died there (an exception its trap swallowed) and logs `rfail` {r, f, at = step id; mod log maps it to the line}."""
    name = 'crumb_' + rule
    m = _global_map(fb, b, cx, name)
    prev = b.call('haxe.ds.ObjectMap.get', m, fb.dyn(0))
    go = _uid('cbg')
    fb.op('JNull', reg=prev, offset=go)
    pi = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=pi, src=prev)
    fb.op('JSLt', a=pi, b=b.const('i32', 0), offset=go)
    _throttle(fb, b, cx, 'rfail_' + rule, 0, CRUMB_LOG_T, go)
    _log_ev(fb, b, cx, helpers, 'rfail', [('r', rule), ('f', fb.get(0, 'controller', 'owner', 'kind')),
                                          ('at', fb.dyn(pi))])
    fb.label(go)
    b.call('haxe.ds.ObjectMap.set', m, fb.dyn(0), fb.dyn(b.const('i32', 0)))
    gidx = GLOBALS[name][1]
    om_t = cx.t('haxe.ds.ObjectMap')

    def hook(fb_):
        cid = len(CRUMBS)
        CRUMBS.append(_crumb_src())
        bb = B(fb_)
        r = fb_.reg(om_t)
        fb_.op('GetGlobal', dst=r, **{'global': gidx})
        bb.call('haxe.ds.ObjectMap.set', r, fb_.dyn(0), fb_.dyn(bb.const('i32', cid)))
    fb.crumb = hook


def _crumb_end(fb, b, cx, rule):
    """Normal end of the probed run (after the rule's 'end' label, inside its trap): step -1."""
    fb.crumb = None
    r = fb.reg(cx.t('haxe.ds.ObjectMap'))
    fb.op('GetGlobal', dst=r, **{'global': GLOBALS['crumb_' + rule][1]})
    b.call('haxe.ds.ObjectMap.set', r, fb.dyn(0), fb.dyn(b.const('i32', -1)))


TRAP_LOG = False   # crash bisect: logging trap handlers off (the game quit at match start since they came in)
TRAP_LOG_T = 30    # s: a rule's caught exception is logged (`trap` src, err) at most this often per rule


def make_trap_hook(helpers):
    """FB.trap_hook for the rule builds (behave.install): a trap's handler logs `trap` {src: building function, err:
    the exception} at most every TRAP_LOG_T s per src, inside its own trap (the log can't throw into vanilla).
    Rule traps were silent: Atreides' strat and every rally stopped logging mid-match with no trace."""
    def hook(fb, exc, src):
        b = B(fb)
        cx = fb.cx
        iexc, ih, skip = fb.reg(cx.t('dyn')), _uid('trh'), _uid('trs')
        fb.op('Trap', exc=iexc, offset=ih)
        _throttle(fb, b, cx, 'trap_' + src, _state(fb, b, cx), TRAP_LOG_T, skip)
        err = fb.reg(cx.t('String'))
        fb.op('Call1', dst=err, fun=cx.fn('$Std.string').findex.value, arg0=exc)
        _log_ev(fb, b, cx, helpers, 'trap', [('src', src), ('err', err)])
        fb.label(skip)
        fb.op('EndTrap', exc=iexc)
        fb.label(ih)
    return hook


__all__ = [n for n in dir() if not n.startswith('__')]
