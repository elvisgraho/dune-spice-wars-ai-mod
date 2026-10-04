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
DECAY_ZONES = {'AcidLake': 0.1, 'AcidLake_Red': 0.1, 'AcidLake_Volcanic': 0.1, 'TheDesolation': 0.4}
                   # Zone.kind (region id) -> ground life lost per day there (cdb traits R_AcidLake / R_TheDesolation,
                   # Unit_Ground_LifeDecay_Flat): off our zone the terrain factor x max(DECAY_FLOOR, 1 - rate x DECAY_DAYS)
DECAY_DAYS = 2.5   # ... days (30 s) a fight / capture keeps us there (Fremen chased Smugglers through Acid Lakes past
                   # Aradah 24:12-25:09: balance 129 -> 0.06, retreat)
DECAY_FLOOR = 0.4  # ... never below this (The Desolation: 40% / day)
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
DEF_NEAR_R = 300   # aimod_defend / contest stake: a structure this close to our active main base is the home front
CONTEST_PIL_W = 0.5  # contest band (x CONTEST_W) of a pillage: below every capture contest, above every chase
CONTEST_HOME_W = 0.25  # ... + this for a contest within DEF_NEAR_R of our main base: home captures > far captures >
                     # home pillages > far pillages
HOME_RING_R = 250  # a neutral village this close to our active main base, besieged by an at-war faction, is defended
                   # like our own (aimod_defend: posture, contest from GATHER_R, our walking Annexes released)
RENEGADE_R = 150   # aimod_defend: a Renegade_Drop raid army this close to a raider-besieged village = a Takeover
DEF_HOPE_IN = 1.0  # aimod_defend: skip a defense whose gathered force (all ours within GATHER_R + cover, x terrain) is
DEF_HOPE_OUT = 1.2 # ... below this x their side there; it counts again at this (hysteresis)
DEF_HOPE_COMMIT = 0.7  # ... and within RALLY_COOL of a rally commit (map `rlyc`), below this only: the commit decided
                   # at >= even, a hopeless flip at even 10 s later dropped it (Harkonnen Eydak 8:55 commit 380k vs 312k,
                   # 9:05 dstop at 362k vs 363k: all armies fled, the 6 freed ones left for an Annex)
BUNKER_MB = 1.5    # Annex score x this for a neutral village within BUNKER_R of our main base (was a hard redirect:
                   # Fremen took 3 such villages before any deep-desert ring village); lost ones are still redirected
ANNEX_EBASE_R = 200  # Annex score x ANNEX_EBASE_W for another faction's village this close to its owner's active main base
ANNEX_EBASE_W = 0.5  # ... (its home under the base guns: Zayras 110 from Tuek ranked over Had-fir 183 out; = DMZ_BASE_R)
RENEG_HOPS = 2     # a renegade base this many zones or fewer from our main base (one village between) is a home threat ...
RENEG_ADD = 100    # ... its Dismantle score max(vanilla, 0) + this: the first strike target when the gauge fires
OPER_ATB = 1534    # attribute Village_NotAdjacentToSelfRegion_GainTTrait (Smugglers' Stakkanov, OperativePassive): a village
                   # with no region of ours next to it gets +20% production, enemy sieges there take x2
OPER_ADD = 25      # ... with it: Annex score + this for a candidate with no neighbour region of ours or next to our main base
                   # (flat, ~one more resource field: a top special still outranks it, user)
OPER_LOSS = 15     # ... and - this for one next to an isolated village of ours (that village loses its +20% production)
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
WORM_ESC_D = 60    # worm flee: an army walking whose path ends this much farther from the worm than it is now is left
                   # alone (it outruns it: aggro 30-60, strike <= 40 away, pre-attack 5-10 s; user: don't choke a move
                   # that makes it in time) ...
WORM_SAFE_REACH = 30  # ... as is one whose path ends off the sand / in a worm-free zone within this (~5 s walk)
WORM_LET_D = 80    # ... but walking away counts only while the worm is at least this far: closer, it has aggroed (30-60)
                   # and strikes within seconds (Atreides 83:17: 4 armies let run at 3-16 from the worm, 312-326 of
                   # path left, 3 eaten 10 s later): the nearest rock is the only escape
WFLEE_T = 3        # s: a worm-targeted army on sand is re-sent to rock at most this often (vanilla orders move it back)
WORM_HOLD = 20     # s: an army sent off the sand isn't free for hunts / raids / strand (no relaunch onto the same sand)
WORM_NEAR = 150    # an army moved off the sand waits there (out of vanilla's Resupply / mission picks) while a worm is
                   # this close, at most WORM_HOLD s; worm-flee moves the order's other armies on sand this close to it
WORM_STEP = 20     # rock search: ring step ...
WORM_R = 200       # ... up to this radius (none found: this far straight away from the worm)
WORM_DETOUR = 30   # ... rings up to this much beyond the nearest land ring count when the army has a destination and
                   # the worm is >= WORM_LET_D away: the land point with the least escape + onward walk wins (user: the
                   # map's rocky middle on the way beats the nearest rock behind)
WORM_DEST_MIN = 30 # a path end at least this far is the army's destination for that choice
WORM_DEST_T = 60   # s: ... remembered per army this long (map `wdest`): after one flee its path ends at our flee point
WORM_DIRS = 16     # ... directions per ring
ZONE_NO_WORM = 1641  # attribute Zone_NoSandworm (trait WormCalling_Neighbors: regions next to a Decoy Thumper; vanilla
                     # canBeWormTarget: no worm target there)
HFLEE_T = 20       # s: an attacked team harvester is released to vanilla's re-route at most this often (it packs up)
RALLY_T = 2        # s: rally pass (rules/rally.py): gather strength when a structure faces more than we can beat
RP_SNAP = 120      # rpoint: vanilla's recruit point belongs to our structure this close (its Airfield sits in the village)
RALLY_MIN_H = 80000  # ... and that power is at least this (a lone raider is vanilla Defense's business)
HOME_MIN_H = RALLY_MIN_H  # aimod_home: hostile power free to strike our land below this counts 0 (a raider band the
                   # village militia hold; the rally ignores it too): 20k FremenRaids vs no army home aborted pillages at 10%
SWEEP_T = 60        # s: map sweep (rules/sweep.py): dead armies / ended orders / ended fights leave our maps
STRIKE_T = 2        # s: en-route strike tick (rules/strike.py): our siege armies on the march ...
STRIKE_R = 90       # ... react to an at-war army this close, like a turret (MissileBattery range 80 + a little; user)
STRIKE_JOIN_R = 2 * STRIKE_R  # a strike counts and sends only order armies this close to the target (user: per army;
                   # Sad-po: 5 armies 220 back were sent at a target that ran 2 s later and turned back)
STRIKE_RATIO = 1.0  # ... and fight it when the order's armies within LOCAL are at least this x (its side + cover):
                    # even or better starts the fight (user), the vanilla fight retreat still judges it after 5 s
STRIKE_MAX = 30     # s: ... a strike ends after this, then the march goes on
STRIKE_LEASH = 120  # ... or once the army is this far from where it started (a running enemy isn't chased; user)
STRIKE_TO = 1.5     # ... joined nearest first until this x the target's side (not every order army in reach: the rest marches on)
AA_R = 120          # Fremen F_Special_2 is an anti-air turret (trait: can only attack flying units, attack plane 2,
                    # range 80): installed only with an at-war flying army within this (80 + 40), and undeployed
                    # when none is (rules/deploy.py; 3 installed at Arkwaz held an Annex at balance 0 for 15 min)
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
REMOTE_D = 350      # turret-steer / airfield-steer: a village this far (straight) from our main base is remote too, whatever
                    # its zone hops (Harkonnen's Odlab, 386 from Carthag, got no battery; Harur 309 is not remote)
AF_SPACING = 300    # airfield-steer: no Airfield within this of another of ours (range 80: neighbouring villages
                    # 100-200 apart don't both get one; user)
AF_BONUS = 100      # ... a remote village's Airfield scores vanilla + this (as STAND_BONUS for batteries)
WONDER_COST = {  # wonder-steer: cdb building (props.isWonder) -> base cost (sum of qty; the village's real cost / this
    'ExperimentalAlloyFurnace': 1500, 'ExperimentalAlloyFurnace_Fremen': 1500, 'MilitaryFactory': 1500,  # = discount)
    'MilitaryFactory_Fremen': 1500, 'ShaiHuludTemple': 1500, 'NuclearSilo': 3000, 'ResearchStation': 1500,
    'ResearchStation_Fremen': 1500, 'SpacingGuildBranch': 1500, 'RecyclingPlant': 1500}
WONDER_BOOST = {'SpacingGuildBranch': 'SpaceCruiserWreck', 'RecyclingPlant': 'SpaceCruiserWreck'}  # building ->
                   # zone kind prefix that boosts its production (cdb trait R_SpaceWreck: TBuilding_Built_TRes2Prod_Flat)
WONDER_BASE_R = 600  # wonder-steer: nearness to our main base 1 at it -> 0 at this distance ...
WONDER_DISC_W = 3.0  # ... a building discount d (1 - real / base cost) multiplies the score by 1 + this x d (large) ...
WONDER_BOOST_W = 1.3  # ... a production boost there by this (small)
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
CONTEST_R = 600    # contest candidates: an at-war capture this close to our land (DEFEND_R + a short run; user: Atreides
                   # annexed Tab-riyah / Aegkus / Ars-sud 496-548 from Fremen's villages unopposed)
CONTEST_RIDE_R = 800  # ... up to this far while a thumper is free (the contest rides, rules/ride.py); our armies
                   # within HUNT_R + RIDE_LEG of it may join
CONTEST_LEASH = CONTEST_RIDE_R + 50  # abort `leash` of a running contest (LEASH for chases); contests never `drift`
RING_IN = 10       # contest ring step: an army farther than village radius + this walks in (code: contenders stand within
                   # radius + Siege_Occupation_Distance 20; edge or centre distance *unverified*: 10 keeps a margin)
RING_K = 0.5       # ... to the point radius x this from the village centre, on its own side
RING_MOVE_T = 5    # s: a ring move is re-sent to one army at most this often (a walk needs time to progress)
ASWAP_WAIT = 120   # s: Annex value: nothing affordable in the top 3 this long -> the best affordable candidate anywhere
RES_INFLUENCE = 10  # resource sheet index of Influence (ent.Faction.getResource)
RES_AUTHORITY = 6   # resource sheet index of Authority
ANNEX_RISE = 20     # Annex reserve: price rise per village we gain before the next capture starts (per owned outpost
                    # 10 x n^1.2: +18 at 8 villages, +21 at 16)
PANNEX_INF = 100   # peaceful annex (siege.py launch gate): Atreides use PeacefullyAnnex (50 Influence) only with at least
                   # this much Influence, so force peace / diplomacy keep a reserve
PANNEX_MIN_VILLAGES = 4  # ... and only once we own this many villages: the opening's idle armies annex for free
                   # while Influence is scarce (user: early peaceful annexes wasted it)
OPS_CHECK = 2      # s: operations pass (rules/opsbrain.py) per AI faction holding an op
OPS_W = 100        # opsbuy: a wanted op scores this minus OPS_W_STEP x its loadout rank (vanilla data weights 0-10)
OPS_W_STEP = 15
OPS_EXTRACT_B = 0.45  # Extraction Network: our armies at the siege below this x their side there ...
OPS_EXTRACT_LAND = 300  # ... and the target at least this far from our land (a long walk home)
OPS_EXTRACT_MIN = 80000  # ... and the armies that would use its circle (still fighting, within 3 x EXTRACT_R of the village)
                         # worth this much (user: cast for one 29k S_Trooper walking home, out of the circle's reach)
OPS_LATE = 0.75    # Cease Fire: only while the enemy capture of our village is below this progress
OPS_CF_MIN = 0.3   # ... and at least this (delay: the attacker commits first); never on a Pillage (user)
OPS_CF_HOPE = 0.9  # ... and our power within RALLY_R (+ cover) is below this x theirs within LOCAL
OPS_BIGFIGHT = 120000  # fight ops: both sides' power together at least this (~3 armies; 250k skipped every Harkonnen-Fremen fight of match 23:36: 2-3 armies a side, 169-181k)
OPS_B_LO = 0.7     # combat ops in fights with balance (ours / theirs) in [OPS_B_LO, OPS_B_HI]: they swing it
OPS_B_HI = 2.0
OPS_DRUG_HI = 1.4  # Combat Drugs alone (no Sleeper held) only up to this balance
OPS_SCAV_B = 0.8  # Scavenger Team on a big fight from this balance (their dead pay; ours would too, but we lose less)
OPS_BOLD_K = 1.5   # fight retreat balance x this in a zone where our Sleeper Agent / Combat Drugs runs (0.65 -> ~0.43)
OPS_THUMP_PW = 150000  # deny thumper: their visible group in its zone at least this ...
OPS_THUMP_DEPTH = 200  # ... still this far from its path end (a long desert walk: it can't just step out) ...
OPS_THUMP_NEAR = 150   # ... which lies this close to a structure of ours ...
OPS_THUMP_HOPE = 1.0   # ... and our armies within RALLY_R + cover there below this x their group
OPS_WZB_T = 10      # s: our fight retreat's balance for a warzone counts for the fight ops this long
OPS_FIGHT_H = 60000  # fight ops: their visible side at least this (B is ours / theirs; a mop-up is no fight)
OPS_SCAV_H = 120000  # Scavenger Team on a fight: their side at least this (their dead pay)
OPS_DRUG_SITE = 1.2  # Harkonnen Combat Drugs on a sietch / renegade garrison fight only while winning by this
OPS_SAB_SHARE = 0.3  # Defense Sabotage: enemy turret cover at the target at least this share of their side
SD_OP = 'MSupplyDrop'  # Supply Drop operation (rules/sdrop.py): ability SupplyDrop, zone effect TSupplyDrop: allied
                   # non-mech units in the zone +80 supply / day and no supply loss, 3 days
SD_DUR = 90        # s: its duration (3 days x 30 s)
SD_LOW = 0.1       # Supply Drop: cast only for an army at most this share of its max supply (user: at ~5%)
SD_CHECK = 3       # s: sdrop pass period
SD_CAST_R = 150    # a locked task's drop is cast once an order army is this close to the target (Engage: the armies
                   # are entering the target zone; the militia fight follows)
SD_CAST_FIGHT = SUP_DRAIN_S * 20  # a locked drop is cast when an order army losing supply holds <= the walk home
                   # + this: ~20 s of fight drain left (earlier wastes the 3 days; a plain occupation never drains)
SD_EMERG = SUP_DRAIN_S * 20  # emergency drop: an army off our land with less supply than ~20 s of drain ...
SD_EMERG_LAND = 150  # ... at least this far from our land (and short for the walk home), staying in its zone
SD_FRESH = SD_CHECK * 2 + 1  # s: raid supply budget counts on a free (unlocked) drop seen this recently
SD_VAN_K = 0.7     # vanilla siege supply check (AIOrders.hx:1943): InsufficientSupply when the path cost > 0.7 x the
                   # lowest army supply (30% kept for the target fight and the way home: a drop at the target covers
                   # both, so with one the trip may use all but SUP_RESERVE; never more: at 0 supply an army loses up to
                   # 100% max health per day, data Army_Supply_NoSupplies_MaxHealthDamageRatio)
SD_REFILL = 80 * 2  # supply a drop refills during a 2-day pillage (TSupplyDrop_Armies +80 / day): the raid budget
                   # counts it toward the walk home
SD_ZONES = 1      # extra zones of siege-target reach while we hold a free (unlocked) drop: vanilla lists targets within
                   # ~1 zone of our land; the drop is what makes a far Annex / Liberation / pillage affordable (a leader's
                   # land, Smugglers' far Annexes). Locked or used: back to normal reach (`sdfree` stops)
DRY_DEATH_D = 180  # map units an army can walk at 0 supply before it has lost its whole health: up to 100% max health per
                   # day dry (Army_Supply_NoSupplies_MaxHealthDamageRatio) x 30 s per day x ~6 units / s (drain 50 / 30 s
                   # over SUP_WALK 0.28 per unit)
DOOM_SHARE = 0.5   # fight retreat: when doomed armies (the walk home's dry stretch >= DRY_DEATH_D x their health ratio:
DOOM_HOLD = 1.0    # ... fleeing kills them) hold this share of our power in the fight, its balance is at least DOOM_HOLD:
                   # they fight it out instead of dying on the way back (user: no turning back into death)
SD_WIN = 1.0       # emergency drop for a fighting army: our power within LOCAL >= this x the threat there (a lost fight
                   # retreats anyway: a drop there is wasted)
PANNEX_HOPS = 2   # ... and only on a village this many zones or more from our main base (Zone.getDistanceToPlayerBase:
                   # 1 = bordering it): one touching the base is an army's free walk (user: don't waste it there)
# Underworld HQs (rules/uhq.py; Smugglers). Vanilla installs whenever <= 1 HQ has an empty extension list (no cap: all
# Authority went into HQs) and scores regular extensions only by cdb aiWeights (Whisperers Lair on no-Intel villages).
UHQ_MIN = 3        # HQ cap = max(UHQ_MIN, UHQ_PER_VILLAGE x our villages); built ones are never removed
UHQ_PER_VILLAGE = 3
UHQ_AUTH = 5       # Annex reserve: next HQ's Authority = this x (HQs + 1) (data: InstallUWHeadquarter 5 + 5 per existing)
UHQ_SOFT_PER_VILLAGE = 2  # Annex reserve only from this x our villages HQs on (below: HQs go up while the Annex is far)
UHQ_NEAR_AU = 60  # ... or while Authority is within this of the cheapest Annex (~4 min of Smugglers income: about to launch)
UHQ_RES_T = 120    # ... the cheapest Annex cost (annex.py `acmin`) counts this long after its last scoring
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
DMZ_ANNEX_OUT = 0.7   # ... but its Annex score x this when it isn't inside our side (aimod_dmzin): the DMZ leans to Liberate
DMZ_BETWEEN_K = 1.2   # aimod_dmzin: v between our main base B and our village W when d(B,v) + d(v,W) <= this x d(B,W)
DMZ_PREF = 0.5     # press: a DMZ village's distance x this (ranks first)
DMZ_BASE_R = 200   # a village of E this close to E's active main base is E's home, never a DMZ village (base guns
                   # COVER_R 130 + its defenders' reach; Tsimron 118 from Arrakeen; Fon-Al'lulah 233 was taken)
ENCL_N = 2         # enclave (rules/dmz.py aimod_encl): another faction's village whose region borders this many of ours is
                   # a DMZ village at war (any border count), pressable against a stronger owner, and breaks a truce
CROSS_R = RALLY_MIN  # a heal / strand / rally walk passing this close to our structure under at-war siege (or the
                     # rally's danger structure) goes through the enemy (Harkonnen walked past Fremen at Tsimlat)
RALLY_SAFE = 150   # ... and has no at-war power within this
RALLY_MB = 150     # the main base counts this much closer (its guns fight with us)
RALLY_AT = 60      # a defender this close to the rally point has arrived (no move, not held)
RALLY_OFF = 40     # the gather point lies this far outside the rally structure's radius, on the danger side
RALLY_MOVE_T = 5   # s: a defender is re-sent at most this often
RALLY_HOLD = 5     # s: a rallying army stays out of vanilla's picks this long after the last pass saw it walking
RALLY_HYST = 1.15  # a running rally ends only at ENTER x this (no on / off flicker at the threshold)
RALLY_OFF_T = 10   # s: a running rally whose D misses a pass (active test flicker) holds this long while still short there
RALLY_RESUME = 30  # s: a rally back on this soon after its last qualifying pass keeps its RALLY_GIVEUP clock
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
SPOS_FIGHT_R = 60  # an army this close to an at-war army stays in its fight (no step away)
CAPL_R = 60        # capture leash (rules/spos.py): an Action occupier this far from the target with only fleeing
                   # at-war armies near it (moving, farther from the target) walks back to SPOS_OFF from it
CAPS_MIN = 100     # capture side fight (rules/heal.py): a losing fight this far (..LOCAL) from a capture of ours in Action
                   # whose armies at the target outweigh ours in it doesn't retreat (its cancel would end the capture)
BSPLIT_CHECK = 5   # s: bunker split pass (rules/bunker.py)
BSPLIT_K = 1.5     # ... armies sent to silence the bunker partner: until this x its militia (>= 1 army, <= half the order)
BSPLIT_R = 200     # ... only order armies within this of B (at the fight, not stragglers walking in)
HDEAD_N = 5        # heal-dead (rules/orders.py): this many Resupply / Patrol orders to one structure cancelled in Waiting ...
HDEAD_W = 30       # ... within this many s mark it dead ...
HDEAD_T = 300      # ... for this long: heal keys and strand skip it (Fremen's Sha-dad: 745 cancels, armies stuck at Wallon)
BSPLIT_PRIO = 4    # ... split order priority: above the capture's (Annex 3), so addOrder moves the armies itself
BSPLIT_KEEP_MIN = 4   # = orders.KEEP_MIN: before Action a split needs an order this big ...
BSPLIT_KEEP_SHARE = 4 # = orders.KEEP_SHARE: ... and takes at most 1 / this of it (take-keep; more cancels the capture)
SCOUT_NEED = {1: (2, 0), 2: (3, 2), 3: (2, 2)}  # scout wait (rules/annex.py): structures owned (main base included) ->
                   # Annex candidates needed (Fremen / Vernius, others) before an early village is taken ...
SCOUT_WAIT = 120   # s: ... at most this long, then take it
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
RAID_ANNEX_FRESH = 15  # s: ... but an Annex that ended NotEnoughArmies / ArmyNotStrongEnough / NoAvailableArmy this recently
                   # holds raids (its armies are coming free) ...
RAID_ANNEX_MAX = 150   # s: ... for at most this long per failure streak (until an Annex succeeds): then raids go again
HRUN_T = 20        # s: an outgunned harvester under fire is sent to a safe field (or home) at most this often
INTEL_T = 1        # s: fog of war (rules/intel.py): sighting pass per AI faction
SEEN_T = 90        # s: a hostile army unseen this long is no longer counted by the local queries (aimod_fpow keeps it)
SEEN_HOME_T = 300  # s: ... but one last seen within SEEN_HOME_R of our land this long (user: a capturing stack at our
SEEN_HOME_R = 150  # conceded village went into stealth; we never saw it leave)
GHOST_SPD = 3      # units/s: an unseen army is assumed this much closer per second since its sighting (half of
                   # CONTEST_SPD: worst case it walks our way, most don't) ...
GHOST_R_MAX = 90   # ... capped at this: a remembered stack is expected near where it was seen
BUSY_SEEN_T = 30   # s: an army last seen fighting / capturing counts as busy (BUSY_W where the query discounts) this long
BUSY_W = 0.25      # aimod_threat family: an at-war army occupying a structure more than BUSY_R from the query point
BUSY_R = 60        # counts this share (busy capturing elsewhere: no scare for defending another place)
OUT_W = 0.5        # ... a query point on our land: an idle at-war army standing off our land counts this share (it
                   # must walk in first; movers heading in count fully)
OUT_R = 100        # ... only beyond this from the query point (an idle army at the border is a threat as is)
RIDE_MAX = 60      # s: hunt / raid judgement is held at most this long while an army is in transit / hidden
# worm rides (rules/ride.py, docs/WORMRIDE-PLAN.md; user: Fremen ride offensively and reach farther)
RIDE_RES = 15      # resource sheet index of Thumper (vanilla addOrder's hasAccessToRes(15) / getResource(15))
RIDE_MIN = 200     # a trip at least this long rides (cdb AI_WormRiding_MinDist, read by no vanilla code); shorter walks
RIDE_FAR = 350     # ... a trip this long (reach), a contest or a Defense may take the last free thumper; shorter ones ride
RIDE_SPARE = 2     # ... only while this many are free (stock 3 at start, none back before 5k hegemony: 3 short early
                   # Annex rides spent the whole stock by 6 min)
RIDE_LEG = 400     # the ride's part of a trip (WormRiding_MaxTravelDist without the range bonus): no supply spent on it
RIDE_SPD = 25      # TransportWorm speed (x2 with TruePeople): contest arrival time of a ride
RIDE_OVER = 15     # s: walk to the thumper point + pickup + arrival of a ride (contest arrival time)
RIDE_STALL_T = 40  # s: a Worm step vanilla keeps re-requesting without success becomes a Walk step (vanilla: forever;
                   # one worm per faction at a time, a ride lasts ~20 s)
RIDE_GAP = 5       # s: refusals further apart than this restart the stall clock (the order wasn't waiting meanwhile)
RIDE_CHECK = 3     # s: ride tick (map `wfree` refresh, `tstk` stock log)
RIDE_FRESH = RIDE_CHECK * 2 + 1  # s: `wfree` counts this long
RIDE_ZONES = 1     # extra zones of military target reach while a ride is available (like SD_ZONES)
RIDE_LOG_T = 60    # s: `tstk` thumper stock row per faction
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
OWNED_REQ = 1.3    # siege launch: required ratio on an owned (at-war) village (vanilla's own often 1.05-1.2: those lost)
OWNED_D0 = 200     # ... raised x (1 + (distance from our land - OWNED_D0) / OWNED_DK) beyond that distance
OWNED_DK = 600     # (415 away: x1.36 = 1.77; 600+ away: the cap)
OWNED_REQ_MAX = 1.8  # ... never above this (user: double their side must still attack, however far)
OWNED_REQ_TOP = 2.0  # ... and vanilla's own random draw (Insane 1.0-3.5) never above this on an owned target (user: double their army attacks)
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
UNREACH_T = 300    # s: a target whose last order died in Waiting (vanilla's path supply check: InsufficientSupply, or a
                   # refused Shuttle step) is out of reach this long from that launch: vanilla picks armies at >= 90%
                   # supply, so the path itself costs > 0.7 x max supply (Fremen's ring village Alifgah across deep
                   # desert, 3 launches 0:35-0:58 each cancelled at +0.06 s, 50 s of cycling instead of expanding);
                   # not while we hold a free Supply Drop (sdrop-trip lifts that check)
LOST_T = 900       # s: a siege target whose last order of ours reached Engage and lost >= 1 / LOST_SHARE_DEN of
LOST_SHARE_DEN = 2 # ... its armies is out of our target scores this long (lost-siege memory: no second assault the same way)
SQ_MIN = 1.5       # square law vs militia (rules/sqlaw.py): (our dps sum x hp sum) / theirs at least this (743 fights:
                   # >= 1.5 won 97%, below 55-61%)
DRAIN_HP = 0.45    # siege drain (rules/drain.py): a siege in Action whose armies' mean life fell below this ...
DRAIN_DROP = 0.25  # ... and at least this much since Action began ...
DRAIN_PR = 0.15    # ... with the capture there below this progress (a capture under way: the fight was won; 0.6 cancelled two won pillages at 40%): cancelled, target into lost-siege memory
NBUMP_K = 1.25     # a neutral village whose militia beat us (no lost-siege block, user): the next siege / raid there
NBUMP_T = 900      # brings this much more (launch ratio and square law) for this long
LOST_WIN = 600     # s: ... judged only within this of that launch (a capture that succeeded and was lost later stays a target)
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
RAID_GROW_N = 3    # raid: while we own fewer villages, no neutral village within our Annex reach + RAID_GROW_ZONES (user:
RAID_GROW_ZONES = 1  # expansion room first; Harkonnen pillaged its 4 neighbours twice and sat at 1 village)
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
AF_NONE = ('Fremen',)  # cdb building Airfield notForFactions: they never get one (worm rides instead)
SPICE_ANY = ('Fremen', 'Vernius')  # their first-spice bonus (vanilla +100) is removed
ANNEX_SPICE_VAN = 40  # ... and vanilla's SpiceArea field value (+40) is removed for them too (they don't need spice fields)
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
    'Pit': (50, {'Corrino': 70, 'Fremen': 40}), 'Pit_Polar': (50, {'Corrino': 70, 'Fremen': 40}),
    'Pit_Volcanic': (50, {'Corrino': 70, 'Fremen': 40}),
    'SandFall': (50, {'Fremen': 40}), 'WormNest': (50, {'Fremen': 40}),  # Fremen 40: their deep desert first (user)
    'Pole': (20, {'Atreides': 50, 'Harkonnen': 50}),
    'ImperialBasin': (20, {'Smugglers': 50}),
    'MoonDewVale': (20, {'Fremen': 40, 'Smugglers': 50}), 'MoonDewVale_Volcanic': (20, {'Fremen': 40, 'Smugglers': 50}),
    'Volcano': (20, {'Fremen': 40, 'Corrino': 50, 'Vernius': 50}),
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
DD_W = 1.25        # Annex score x (1 + DD_W x sum over adjacent unowned deep deserts of chance / (1 + still missing
DD_W_PRE = 1.25    # after this one)), DD_W with the attribute, DD_W_PRE for Fremen before it (plan ahead: at 0.5
                   # the opening took a special and a spice village before the ring villages next door)
DD_ADD = 50        # + this x the best ring chance (contest-adjusted, x DD_LINK, x weight, x cmin / cost) for a ring
DD_ADD_UC = 100    # ... for an uncontested ring (no other faction's village / main base / at-war stack at its missing villages)
DD_MISS_K = 0.25   # uncontested ring: chance / (1 + this x (missing - 1)) instead of / missing (5 missing: 0.5, was 0.2)
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


def _army_loop(fb, b, arr, alen, i, name, done, transported=False):
    """Loop head: next live ent.Army from arr (skips null, militia, transported, dead). Returns the army register.
    transported=True keeps armies in transit (worm ride, shuttle): the hostile-army queries judge them by the fog
    memory only (rules/intel._ghost), where they were last seen boarding."""
    fb.op('Int', dst=i, ptr=b.code.add_i32(0).value)
    b.loop_head(name)
    fb.op('JSGte', a=i, b=alen, offset=done)
    a = b.cast(b.call('hl.types.ArrayObj.getDyn', arr, i), 'ent.Army')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=a, offset=name)
    fb.op('JTrue', cond=b.field(a, 'isMilitia'), offset=name)
    if not transported:
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


def _order_of(fb, b, cx, fac, a, dst, none):
    """dst = the live order of fac holding army a (highest priority, the newest on a tie: vanilla's hasOrder scan);
    jump to `none` when it is in none. Never read `Unit.aiOrder`: only AIOrders.init (controller start / save load)
    writes it, so it is null all match long and stale after a load."""
    fb.op('Null', dst=dst)
    fb.op('JNull', reg=fac, offset=none)
    ctl = b.field(fac, 'aiController')  # null for a human player
    fb.op('JNull', reg=ctl, offset=none)
    aio = b.field(ctl, 'aiOrders')
    fb.op('JNull', reg=aio, offset=none)
    ords = b.field(aio, 'orders')
    fb.op('JNull', reg=ords, offset=none)
    k, bp = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    fb.op('Mov', dst=bp, src=b.const('i32', -1))
    lo, dn = _uid('oof'), _uid('oofd')
    fb.op('Mov', dst=k, src=b.field(ords, 'length'))
    b.loop_head(lo)
    fb.op('JSLte', a=k, b=b.const('i32', 0), offset=dn)
    fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', ords, k), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset=lo)
    ou = b.field(o, 'units')
    fb.op('JNull', reg=ou, offset=lo)
    fb.op('JFalse', cond=b.call('hl.types.ArrayObj.contains', ou, fb.dyn(a)), offset=lo)
    pr = b.field(o, 'priority')
    fb.op('JSLte', a=pr, b=bp, offset=lo)  # newest first (backwards): a tie keeps the newer one
    fb.op('Mov', dst=bp, src=pr)
    fb.op('Mov', dst=dst, src=o)
    fb.op('JAlways', offset=lo)
    fb.label(dn)
    fb.op('JNull', reg=dst, offset=none)


def _unreach(fb, b, cx, s_e, t, yes, fac=None):
    """Jump to `yes` when siege target s_e is out of supply reach: our last order on it (map `aord`, set by the
    launch gate; fac given: only an order of fac's, the maps are keyed by target and another faction's launch must not
    block us) died in Waiting (phase < REGROUP, units emptied by stop: vanilla's path supply check or a refused
    Shuttle step), launched (map `alaunch`) less than UNREACH_T before t, and its faction holds no free Supply Drop
    (map `sdfree` within SD_FRESH: sdrop-trip lifts the check) or that launch already ran with one (map `asd`)."""
    no = _uid('unr')
    ov = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'aord'), fb.dyn(s_e))
    fb.op('JNull', reg=ov, offset=no)
    po = b.cast(ov, 'logic.ai.AIOrder')
    fb.op('JNull', reg=po, offset=no)
    pos = b.field(po, 'orders')
    fb.op('JNull', reg=pos, offset=no)
    pct = b.field(pos, 'controller')
    fb.op('JNull', reg=pct, offset=no)
    pfac = b.field(pct, 'owner')
    fb.op('JNull', reg=pfac, offset=no)
    if fac is not None:
        fb.op('JNotEq', a=pfac, b=fac, offset=no)
    fb.op('JSGte', a=b.field(po, 'phase'), b=b.const('i32', REGROUP), offset=no)
    pu = b.field(po, 'units')
    fb.op('JNull', reg=pu, offset=no + 'd')
    fb.op('JSGt', a=b.field(pu, 'length'), b=b.const('i32', 0), offset=no)  # still waiting, alive
    fb.label(no + 'd')
    lv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'alaunch'), fb.dyn(s_e))
    fb.op('JNull', reg=lv, offset=no)
    lq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=lq, src=lv)
    fb.op('Sub', dst=lq, a=t, b=lq)
    fb.op('JSGte', a=lq, b=b.const('f64', UNREACH_T), offset=no)
    # that launch already had a free drop's lift (map `asd`, siege.py launch record) and still died: the drop can't
    # make this trip, no waiver
    fb.op('JNotNull', reg=b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'asd'), fb.dyn(s_e)), offset=yes)
    sv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'sdfree'), fb.dyn(pfac))
    fb.op('JNull', reg=sv, offset=no + 'w')
    sq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=sq, src=sv)
    fb.op('Sub', dst=sq, a=t, b=sq)
    fb.op('JSLte', a=sq, b=b.const('f64', SD_FRESH), offset=no)
    # a worm ride available (rules/ride.py map `wfree`): the worm plan has no supply check and rides most of the way
    fb.label(no + 'w')
    _ride_free(fb, b, cx, pfac, t, yes)
    fb.label(no)


def _heal_dead(fb, b, cx, s, skip):
    """Jump to `skip` when structure s (entity reg) is a dead heal / home target (map `hbad` s -> until, set by
    rules/orders.build_heal_dead: Move orders to it keep being cancelled in Waiting)."""
    hv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'hbad'), fb.dyn(s))
    no = _uid('hdn')
    fb.op('JNull', reg=hv, offset=no)
    hq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=hq, src=hv)
    fb.op('JSGt', a=hq, b=b.field(_state(fb, b, cx), 'time'), offset=skip)
    fb.label(no)


def _box_true(fb, cx, dst):
    """dst (a Null<Bool> register, e.g. Zone.getDistanceToPlayerTerritory's considerAirfields) = boxed true. A raw
    Bool op into a Null<Bool> register leaves a non-pointer the callee dereferences: it threw inside our traps, and
    the rules calling it (Annex scores, the Supply Drop / worm reach in isInSupplyRange, raid expansion room, the
    sdrop trip lock) silently fell back to vanilla (bcheck `Bool ptr`)."""
    tb = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=tb, value=True)
    fb.op('ToDyn', dst=dst, src=tb)


def _ride_free(fb, b, cx, fac, t, no):
    """Jump to `no` unless fac can ride a worm now (rules/ride.py map `wfree`: a thumper not claimed by another
    order, refreshed every RIDE_CHECK s, fresh within RIDE_FRESH)."""
    rv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'wfree'), fb.dyn(fac))
    fb.op('JNull', reg=rv, offset=no)
    rq = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=rq, src=rv)
    fb.op('Sub', dst=rq, a=t, b=rq)
    fb.op('JSGt', a=rq, b=b.const('f64', RIDE_FRESH), offset=no)


def _ride_leg(fb, b, cx, fac, t, d, critical=False):
    """d (f64 reg) -> the walking part of a trip d long when fac's plan gate (rules/ride.py) would ride it, in place:
    a thumper free (_ride_free), d >= RIDE_MIN, and d >= RIDE_FAR or RIDE_SPARE free (map `wfreen`; critical=True: a
    contest, the last free one is enough). The ride covers RIDE_LEG of it at no supply. Unchanged otherwise."""
    u = _uid('rleg')
    fb.op('JSLt', a=d, b=b.const('f64', RIDE_MIN), offset=u)
    _ride_free(fb, b, cx, fac, t, u)
    if not critical:
        fb.op('JSGte', a=d, b=b.const('f64', RIDE_FAR), offset=u + 'f')
        fv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'wfreen'), fb.dyn(fac))
        fb.op('JNull', reg=fv, offset=u)
        fq = fb.reg(cx.t('f64'))
        fb.op('SafeCast', dst=fq, src=fv)
        fb.op('JSLt', a=fq, b=b.const('f64', RIDE_SPARE), offset=u)
        fb.label(u + 'f')
    fb.op('Sub', dst=d, a=d, b=b.const('f64', RIDE_LEG))
    fb.op('JSGte', a=d, b=b.const('f64', 0), offset=u)
    fb.op('Mov', dst=d, src=b.const('f64', 0))
    fb.label(u)


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


def _pillaging(fb, b, cx, s, yes):
    """Jump to `yes` when structure s's running occupation is a Pillage (`SiegeComponent.getOccupationActionKind`):
    a 20-day loss of production, while an Annex / Liberate / Takeover loses the village. A siege still in its militia
    fight (no occupation yet) isn't known to be one and counts as a capture."""
    sg = b.field(s, 'siege')
    no = _uid('pln')
    fb.op('JNull', reg=sg, offset=no)
    k = b.call('ent.comp.SiegeComponent.getOccupationActionKind', sg)
    fb.op('JNull', reg=k, offset=no)
    fb.op('JEq', a=b.call('String.__compare', k, fb.dyn(fb.string('Pillage'))), b=b.const('i32', 0), offset=yes)
    fb.label(no)


def _base_near(fb, b, cx, fac, e, r, yes):
    """Jump to `yes` when entity e is within r of one of fac's active main bases."""
    lo = _uid('bnr')
    k = fb.reg(cx.t('i32'))
    ee, me = fb.reg(cx.t('ent.Entity')), fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=ee, src=e)
    mbs = b.field(fac, 'mainBases')
    fb.op('JNull', reg=mbs, offset=lo + 'd')
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head(lo)
    fb.op('JSGte', a=k, b=b.field(mbs, 'length'), offset=lo + 'd')
    mb = b.cast(b.call('hl.types.ArrayObj.getDyn', mbs, k), 'ent.Structure')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=mb, offset=lo)
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', mb), offset=lo)
    fb.op('Mov', dst=me, src=mb)
    fb.op('JSLte', a=b.call('ent.Entity.getDistTo', ee, me), b=b.const('f64', r), offset=yes)
    fb.op('JAlways', offset=lo)
    fb.label(lo + 'd')


def _pannex_ok(fb, b, cx, fac, s, no):
    """Jump to `no` unless fac may spend PeacefullyAnnex on structure s (pannex fallback and vanilla's
    checkPeacefulAnnexation, rules/pannex.py): we own >= PANNEX_MIN_VILLAGES villages, hold >= PANNEX_INF Influence
    and s's zone lies >= PANNEX_HOPS zones from our main base (no main base: any distance)."""
    fb.op('JSLt', a=b.field(b.call('ent.Faction.getVillages', fac), 'length'), b=b.const('i32', PANNEX_MIN_VILLAGES),
          offset=no)
    inf = fb.reg(cx.t('f64'))
    fb.op('Call2', dst=inf, fun=cx.fn('ent.Faction.getResource').findex.value, arg0=fac,
          arg1=b.const('i32', RES_INFLUENCE))
    fb.op('JSLt', a=inf, b=b.const('f64', PANNEX_INF), offset=no)
    z = b.call('ent.Entity.get_zone', s)
    fb.op('JNull', reg=z, offset=no)
    gdb = cx.fn('ent.Zone.getDistanceToPlayerBase')
    gnull = fb.reg(cx.code.types[gdb.type.value].definition.args[2].value)
    fb.op('Null', dst=gnull)
    hops = fb.reg(cx.t('i32'))
    fb.op('Call3', dst=hops, fun=gdb.findex.value, arg0=z, arg1=fac, arg2=gnull)
    fb.op('JSLt', a=hops, b=b.const('i32', PANNEX_HOPS), offset=no)


def _base_dist(fb, b, s, fac):
    """Distance from structure s to fac's nearest active main base (1 << 30: none)."""
    cx = fb.cx
    d, bd = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    k = fb.reg(cx.t('i32'))
    se = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=se, src=s)
    fb.op('Mov', dst=bd, src=b.const('f64', 1 << 30))
    lo = _uid('bdl')
    mbs = b.field(fac, 'mainBases')
    fb.op('JNull', reg=mbs, offset=lo + 'd')
    fb.op('Mov', dst=k, src=b.const('i32', 0))
    b.loop_head(lo)
    fb.op('JSGte', a=k, b=b.field(mbs, 'length'), offset=lo + 'd')
    mb = b.cast(b.call('hl.types.ArrayObj.getDyn', mbs, k), 'ent.Structure')
    fb.op('Incr', dst=k)
    fb.op('JNull', reg=mb, offset=lo)
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', mb), offset=lo)
    me = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=me, src=mb)
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', se, me))
    fb.op('JSGte', a=d, b=bd, offset=lo)
    fb.op('Mov', dst=bd, src=d)
    fb.op('JAlways', offset=lo)
    fb.label(lo + 'd')
    return bd


def _af_remote(fb, b, cx, s, z, fac, yes, no, none):
    """Airfield-steer's remote test for village s (zone z) of fac: jump to `yes` when >= TURRET_REMOTE zones
    (Zone.getDistanceToPlayerBase) or >= REMOTE_D in a straight line from fac's nearest active main base, `none` when
    fac has no active main base (no measure), else `no`. Returns (db, hops) registers."""
    db = _base_dist(fb, b, s, fac)
    hops = fb.reg(cx.t('i32'))
    gdb = cx.fn('ent.Zone.getDistanceToPlayerBase')
    gnull = fb.reg(cx.code.types[gdb.type.value].definition.args[2].value)
    fb.op('Null', dst=gnull)
    fb.op('Call3', dst=hops, fun=gdb.findex.value, arg0=z, arg1=fac, arg2=gnull)
    fb.op('JSGte', a=db, b=b.const('f64', 1 << 29), offset=none)  # no main base of ours: no measure
    fb.op('JSGte', a=db, b=b.const('f64', REMOTE_D), offset=yes)
    fb.op('JSGte', a=hops, b=b.const('i32', 99), offset=no)
    fb.op('JSGte', a=hops, b=b.const('i32', TURRET_REMOTE), offset=yes)
    fb.op('JAlways', offset=no)
    return db, hops


def _af_behind(fb, b, cx, se, fac, fail):
    """Bool register: entity se lies behind fac's nearest active main base B (every other faction's active main base
    M has d(se, M) >= d(B, M): between us and the map border). `fail` when fac has no main base list / none active."""
    zi = b.const('i32', 0)
    L = {n: _uid('afb' + n) for n in ('mb', 'mbd', 'of', 'ofd', 'om', 'bhd')}
    bm = fb.reg(cx.t('ent.Entity'))  # our nearest active main base
    fb.op('Null', dst=bm)
    d, bd = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=bd, src=b.const('f64', 1 << 30))
    i, j = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
    me = fb.reg(cx.t('ent.Entity'))
    mbs = b.field(fac, 'mainBases')
    fb.op('JNull', reg=mbs, offset=fail)
    fb.op('Mov', dst=i, src=zi)
    b.loop_head(L['mb'])
    fb.op('JSGte', a=i, b=b.field(mbs, 'length'), offset=L['mbd'])
    mb = b.cast(b.call('hl.types.ArrayObj.getDyn', mbs, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=mb, offset=L['mb'])
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', mb), offset=L['mb'])
    fb.op('Mov', dst=me, src=mb)
    fb.op('Mov', dst=d, src=b.call('ent.Entity.getDistTo', se, me))
    fb.op('JSGte', a=d, b=bd, offset=L['mb'])
    fb.op('Mov', dst=bd, src=d)
    fb.op('Mov', dst=bm, src=me)
    fb.op('JAlways', offset=L['mb'])
    fb.label(L['mbd'])
    fb.op('JNull', reg=bm, offset=fail)
    behind = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=behind, value=False)
    facs = b.cast(fb.get(_state(fb, b, cx), 'factions', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=facs, offset=L['bhd'])
    nb = fb.reg(cx.t('i32'))  # other active main bases seen
    fb.op('Mov', dst=nb, src=zi)
    fb.op('Mov', dst=i, src=zi)
    b.loop_head(L['of'])
    fb.op('JSGte', a=i, b=b.field(facs, 'length'), offset=L['ofd'])
    of = b.cast(b.call('hl.types.ArrayObj.getDyn', facs, i), 'ent.Faction')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=of, offset=L['of'])
    fb.op('JEq', a=of, b=fac, offset=L['of'])
    ombs = b.field(of, 'mainBases')
    fb.op('JNull', reg=ombs, offset=L['of'])
    fb.op('Mov', dst=j, src=zi)
    b.loop_head(L['om'])
    fb.op('JSGte', a=j, b=b.field(ombs, 'length'), offset=L['of'])
    om = b.cast(b.call('hl.types.ArrayObj.getDyn', ombs, j), 'ent.Structure')
    fb.op('Incr', dst=j)
    fb.op('JNull', reg=om, offset=L['om'])
    fb.op('JFalse', cond=b.call('ent.Structure.get_isActiveMainBase', om), offset=L['om'])
    fb.op('Mov', dst=me, src=om)
    fb.op('Incr', dst=nb)
    # s nearer to this base than our base is: s is on the way somewhere, not behind us
    fb.op('JSLt', a=b.call('ent.Entity.getDistTo', se, me), b=b.call('ent.Entity.getDistTo', bm, me), offset=L['bhd'])
    fb.op('JAlways', offset=L['om'])
    fb.label(L['ofd'])
    fb.op('JSLte', a=nb, b=zi, offset=L['bhd'])  # nobody else: no "behind"
    fb.op('Bool', dst=behind, value=True)
    fb.label(L['bhd'])
    return behind


def _af_spaced(fb, b, cx, s, se, fac, airfield, gk, gkn, ku):
    """Bool register: another structure of fac (not s) within AF_SPACING of se holds an Airfield (built or going
    up: Upgrades.getKind)."""
    zi = b.const('i32', 0)
    lo = _uid('afs')
    i = fb.reg(cx.t('i32'))
    me = fb.reg(cx.t('ent.Entity'))
    spaced = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=spaced, value=False)
    mine = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=mine, offset=lo + 'd')
    fb.op('Mov', dst=i, src=zi)
    b.loop_head(lo)
    fb.op('JSGte', a=i, b=b.field(mine, 'length'), offset=lo + 'd')
    st = b.cast(b.call('hl.types.ArrayObj.getDyn', mine, i), 'ent.Structure')
    fb.op('Incr', dst=i)
    fb.op('JNull', reg=st, offset=lo)
    fb.op('JEq', a=st, b=s, offset=lo)
    fb.op('Mov', dst=me, src=st)
    fb.op('JSGte', a=b.call('ent.Entity.getDistTo', se, me), b=b.const('f64', AF_SPACING), offset=lo)
    sup = b.field(st, 'upgrades')
    fb.op('JNull', reg=sup, offset=lo)
    fb.op('CallN', dst=ku, fun=gk.findex.value, args=[sup, airfield] + gkn)
    fb.op('JNull', reg=ku, offset=lo)
    fb.op('Bool', dst=spaced, value=True)
    fb.label(lo + 'd')
    return spaced


def _neutral_village(fb, b, cx, s_e, no):
    """Jump to `no` unless s_e is a neutral village (no owner; not a sietch / renegade base, which keep the lost-siege
    memory and SITE_REQ: their garrison spawns harass units mid-strike)."""
    fb.op('JNotNull', reg=b.call('ent.Entity.get_owner', s_e), offset=no)
    ss = b.cast(fb.dyn(s_e), 'ent.Structure')
    fb.op('JNull', reg=ss, offset=no)
    _strong_site(fb, b, ss, no)


def _nbump_mark(fb, b, cx, fac, s_e, t):
    """Our siege of neutral village s_e lost to its militia: map `nbump` (per faction) s_e -> t (read by _nbump)."""
    b.call('haxe.ds.ObjectMap.set', _fac_map(fb, b, cx, 'nbump', fac), fb.dyn(s_e), fb.dyn(t))


def _nbump(fb, b, cx, fac, s_e, r):
    """r (f64 reg) x NBUMP_K in place while fac's siege of s_e lost to its militia within NBUMP_T (user: a neutral
    village that beat us gets a little more next time, no fear memory)."""
    u = _uid('nbp')
    fb.op('JNull', reg=fac, offset=u)
    v = b.call('haxe.ds.ObjectMap.get', _fac_map(fb, b, cx, 'nbump', fac), fb.dyn(s_e))
    fb.op('JNull', reg=v, offset=u)
    q = fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=q, src=v)
    fb.op('Sub', dst=q, a=b.field(_state(fb, b, cx), 'time'), b=q)
    fb.op('JSGt', a=q, b=b.const('f64', NBUMP_T), offset=u)
    fb.op('Mul', dst=r, a=r, b=_ratio(fb, b, NBUMP_K))
    fb.label(u)


def _recent_launch(fb, b, cx, s_e, t, recent, fac=None, helpers=None):
    """Jump to `recent` if vanilla launched a siege on s_e less than its block ago (map 'alaunch', set by the
    tryArmyAction wrapper; block = map 'ablk', RETRY doubling up to RETRY_MAX for a target relaunched right after
    its block ran out; at least UNREACH_T when its last order died in Waiting: out of supply reach).
    fac given: the records (keyed by target) count only when the last order on s_e (map `aord`) is fac's: another
    faction's failed launch on a village blocked ours too. Lost siege (fac given): that order reached Engage and
    ended with at least 1 / LOST_SHARE_DEN of the armies it launched with (map `aunits`, copied at launch) dead ->
    s_e is out for LOST_T s from when this is first seen within LOST_WIN of that launch, never on a village of
    ours (maps `slost` / `slostf`; log `slost`): Harkonnen lost 10
    armies under Mar-iel / Qartnin's batteries at Atreides' Yawan (28:16) and sent 14 more the same way at 43:47."""
    old = _uid('old')
    if fac is not None:
        ao = b.cast(b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'aord'), fb.dyn(s_e)), 'logic.ai.AIOrder')
        fb.op('JNull', reg=ao, offset=old + 'own')
        aos = b.field(ao, 'orders')
        fb.op('JNull', reg=aos, offset=old + 'own')
        fb.op('JNotEq', a=b.field(b.field(aos, 'controller'), 'owner'), b=fac, offset=old)
        fb.label(old + 'own')
        # lost siege memory
        slm, slf = _global_map(fb, b, cx, 'slost'), _global_map(fb, b, cx, 'slostf')
        lsv = b.call('haxe.ds.ObjectMap.get', slm, fb.dyn(s_e))
        fb.op('JNull', reg=lsv, offset=old + 'det')
        fb.op('JNotEq', a=b.call('haxe.ds.ObjectMap.get', slf, fb.dyn(s_e)), b=fb.dyn(fac), offset=old + 'det')
        lsq = fb.reg(cx.t('f64'))
        fb.op('SafeCast', dst=lsq, src=lsv)
        fb.op('Sub', dst=lsq, a=t, b=lsq)
        fb.op('JSLt', a=lsq, b=b.const('f64', LOST_T), offset=recent)
        fb.label(old + 'det')
        aum = _global_map(fb, b, cx, 'aunits')
        au = b.cast(b.call('haxe.ds.ObjectMap.get', aum, fb.dyn(s_e)), 'hl.types.ArrayObj')
        fb.op('JNull', reg=au, offset=old + 'n')
        fb.op('JNull', reg=ao, offset=old + 'n')
        aou = b.field(ao, 'units')
        fb.op('JNull', reg=aou, offset=old + 'nd')
        fb.op('JSGt', a=b.field(aou, 'length'), b=b.const('i32', 0), offset=old + 'n')  # still running
        fb.label(old + 'nd')
        fb.op('JSLte', a=b.field(ao, 'phase'), b=b.const('i32', REGROUP), offset=old + 'n')  # never fought there
        # judged only soon after it (LOST_WIN from its launch) and not on a village of ours: a costly capture that
        # succeeded and was lost much later must stay a target (the bunker retake)
        fb.op('JEq', a=b.call('ent.Entity.get_owner', s_e), b=fac, offset=old + 'n')
        alv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'alaunch'), fb.dyn(s_e))
        fb.op('JNull', reg=alv, offset=old + 'n')
        alq = fb.reg(cx.t('f64'))
        fb.op('SafeCast', dst=alq, src=alv)
        fb.op('Sub', dst=alq, a=t, b=alq)
        fb.op('JSGt', a=alq, b=b.const('f64', LOST_WIN), offset=old + 'n')
        an, ad, ai = fb.reg(cx.t('i32')), fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
        fb.op('Mov', dst=an, src=b.field(au, 'length'))
        fb.op('Mov', dst=ad, src=b.const('i32', 0))
        fb.op('Mov', dst=ai, src=b.const('i32', 0))
        b.loop_head(old + 'l')
        fb.op('JSGte', a=ai, b=an, offset=old + 'ld')
        ae = b.cast(b.call('hl.types.ArrayObj.getDyn', au, ai), 'ent.Entity')
        fb.op('Incr', dst=ai)
        fb.op('JNull', reg=ae, offset=old + 'l')
        fb.op('JFalse', cond=b.call('ent.Entity.isDead', ae), offset=old + 'l')
        fb.op('Incr', dst=ad)
        fb.op('JAlways', offset=old + 'l')
        fb.label(old + 'ld')
        b.call('haxe.ds.ObjectMap.remove', aum, fb.dyn(s_e))  # judged once
        aq = fb.reg(cx.t('i32'))
        fb.op('Mul', dst=aq, a=ad, b=b.const('i32', LOST_SHARE_DEN))
        fb.op('JSLt', a=aq, b=an, offset=old + 'n')
        # a neutral village (militia only) is no fear memory (user: we always bring enough for a neutral village; if
        # we got it wrong, a little more next time): `nbump`, no block
        _neutral_village(fb, b, cx, s_e, old + 'nn')
        _nbump_mark(fb, b, cx, fac, s_e, t)
        if helpers is not None:
            _log_ev(fb, b, cx, helpers, 'slost', [('f', fb.get(fac, 'kind')), ('tgt', s_e), ('why', 'bump')])
        fb.op('JAlways', offset=old + 'n')
        fb.label(old + 'nn')
        b.call('haxe.ds.ObjectMap.set', slm, fb.dyn(s_e), fb.dyn(t))
        b.call('haxe.ds.ObjectMap.set', slf, fb.dyn(s_e), fb.dyn(fac))
        if helpers is not None:
            anf, adf = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
            fb.op('ToSFloat', dst=anf, src=an)
            fb.op('ToSFloat', dst=adf, src=ad)
            _log_ev(fb, b, cx, helpers, 'slost', [('f', fb.get(fac, 'kind')), ('tgt', s_e), ('n', anf), ('dead', adf),
                                                  ('ph', fb.dyn(b.field(ao, 'phase')))])
        fb.op('JAlways', offset=recent)
        fb.label(old + 'n')
    last = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'alaunch'), fb.dyn(s_e))
    fb.op('JNull', reg=last, offset=old)
    lf, bl = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('SafeCast', dst=lf, src=last)
    fb.op('Sub', dst=lf, a=t, b=lf)
    fb.op('Mov', dst=bl, src=b.const('f64', RETRY))
    bv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'ablk'), fb.dyn(s_e))
    fb.op('JNull', reg=bv, offset=old + 'b')
    fb.op('SafeCast', dst=bl, src=bv)
    fb.label(old + 'b')
    # out of reach (common._unreach): at least UNREACH_T from that launch
    chk = old + 'c'
    _unreach(fb, b, cx, s_e, t, old + 'u', fac)
    fb.op('JAlways', offset=chk)
    fb.label(old + 'u')
    fb.op('JSGte', a=bl, b=b.const('f64', UNREACH_T), offset=chk)
    fb.op('Mov', dst=bl, src=b.const('f64', UNREACH_T))
    fb.label(chk)
    fb.op('JSLt', a=lf, b=bl, offset=recent)
    fb.label(old)


def _vfield(fb, b, obj, name):
    """Field of a virtual (anonymous struct) register by name -> (register of the field's type, field index)."""
    cx = fb.cx
    fields = cx.code.types[fb.regs[obj]].definition.fields
    idx = [i for i, f in enumerate(fields) if f.name.resolve(cx.code) == name]
    if len(idx) != 1:
        raise ValueError(f'siege-join: field {name} not found')
    dst = fb.reg(fields[idx[0]].type.value)
    fb.op('Field', dst=dst, obj=obj, field=idx[0])
    return dst, idx[0]


__all__ = [n for n in dir() if not n.startswith('__')]
