"""Shared AI tuning values (docs/AI-POLICY.md §4).

Keep derived values in dependency order. Bytecode emitters and mutable build state
belong in common.py; this module depends only on the game-data reader.
"""
from rules.game_data import no_building_factions


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
LIB_REACH = 450    # a Liberate target farther than this from our land is no candidate (no free drop / worm ride)
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
RETREAT_LATCH_T = 10  # s: a forced retreat of ours (heal.py disengage / trespass) holds its fight at 0 this long
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
BK_BAL_R = 400    # fight retreat: a fight this close to the main base our Raze order (Engage / Action) targets takes at
                  # least that order's live balance (heal.py `bkbal`), when one of its armies is within BK_BAL_NEAR
BK_BAL_NEAR = 160 # of the fight's centroid (match 39: Smugglers' 5:1 Raze cancelled by a fight 250 out)
BK_DR_LIVE = 15   # s: a direct raze (bkstate RAZE_ACT) that acted this recently is live: it holds the go (bkill)
                  # and fights near its base read the coalition (heal)
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
DEF_HOPE_IN = 1.0  # aimod_defend: skip a defense whose battle forecast side (defend, DEF_FC_T; = the dgate measure) is
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
DEF_GATE = 1.0     # vanilla Defense (checkStructures pick) goes only at this battle forecast with all our armies that can come (heal.py dgate)
DEF_FC_T = 60      # s: ... over this window
PICK_LOG_T = 30    # s: lowpick log throttle per army
RAID_LIFE = 0.6    # raid army life floor (a pillage is short; vanilla sieges want 0.9 and a full refill)
RAID_ARRIVE = SUP_DRAIN_S * 30  # raid: supply an army must still have on arrival: ~30 s of militia fight drain
                   # (absolute, *unverified*: Alwahad's fight drained 85 in ~50 s; a 25% share was 16-110 by faction)
REACT_R = 480      # raid: idle at-war armies this close can reach the village before a pillage ends (militia fight
                   # ~20 s + 2 days = 60 s, at ~6 u/s); fighting, besieging or elsewhere-bound ones don't count
RAID_FAR = round(1 / ENTER, 3)  # raid start: everything within REACT_R (with the village's side) needs only this x: an
                  # army away from the village commits only with ENTER x our raid; if it comes the abort pass decides
RAID_OWNED_FAR = 0.75  # ... an at-war village: everything within REACT_R x this (user: too safe harassing enemies;
                   # was ENTER: Fremen skipped Smugglers' Ad-Al'lab at 390k vs 408k); at the village still ENTER
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
WORM_SAFE_REACH = 65  # ... as is one whose path ends off the sand / in a worm-free zone within this (was 30, but our
                   # own flee points lie 20-60 away: an army walking to one was re-sent every WFLEE_T s to another as far,
                   # Atreides A_Elite 17 Moves in 80 s with the worm 3-16 away, match 2026-10-05 02:29)
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
STRIKE_END_K = 0.75  # ... a running strike ends `weak` only below this x the start test (hysteresis)
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
PATROL_AT = 100    # patrol-gate: an army this close to the patrolled village is already there (no new Patrol for it)
REMOTE_D = 350      # turret-steer / airfield-steer: a village this far (straight) from our main base is remote too, whatever
                    # its zone hops (Harkonnen's Odlab, 386 from Carthag, got no battery; Harur 309 is not remote)
AF_SPACING = 300    # airfield-steer: no Airfield within this of another of ours (range 80: neighbouring villages
                    # 100-200 apart don't both get one; user)
AF_BONUS = 100      # ... a remote village's Airfield scores vanilla + this (as STAND_BONUS for batteries)
TRANSIENT = ('IsInCombat', 'IsOccupied', 'StabilityTooLow')  # checkAddUpgrade results that pass: the battery /
                    # Airfield boost holds through them, so vanilla's reserved request is theirs, not a quirk building's
                    # picked while the new village was in combat (Atreides' Bir-ur: Data Center; Harkonnen's Aegnun, map
                    # centre: Data Center first; user, match 2026-10-23 19:32 / 20:1x). Not ConstructionInProgress:
                    # checkBuildings does nothing on it (no build request; verified 2026-10-24), a boosted pick would
                    # waste the faction's pick for the whole construction: turret-steer reserves the slot instead
AFW_T = 10          # s: ... and every other building there is dropped this long after its Airfield pair was boosted
WONDER_COST = {  # wonder-steer: cdb building (props.isWonder) -> base cost (sum of qty; the village's real cost / this
    'ExperimentalAlloyFurnace': 1500, 'ExperimentalAlloyFurnace_Fremen': 1500, 'MilitaryFactory': 1500,  # = discount)
    'MilitaryFactory_Fremen': 1500, 'ShaiHuludTemple': 1500, 'NuclearSilo': 3000, 'ResearchStation': 1500,
    'ResearchStation_Fremen': 1500, 'SpacingGuildBranch': 1500, 'RecyclingPlant': 1500}
WONDER_BOOST = {'SpacingGuildBranch': 'SpaceCruiserWreck', 'RecyclingPlant': 'SpaceCruiserWreck'}  # building ->
                   # zone kind prefix that boosts its production (cdb trait R_SpaceWreck: TBuilding_Built_TRes2Prod_Flat)
WONDER_BASE_R = 600  # wonder-steer: nearness to our main base 1 at it -> 0 at this distance ...
WONDER_DISC_W = 3.0  # ... a building discount d (1 - real / base cost) multiplies the score by 1 + this x d (large) ...
WONDER_BOOST_W = 1.3  # ... a production boost there by this (small)
WONDER_ADD = 10     # ... score = vanilla + this x m (additive: vanilla wonder scores are ~0 or below; ~ a building's
                    # own score at a good village, not above economy buildings)
WONDER_MIN_M = 0.75  # ... m below this (far from our base and towards the middle): not there (veto `far`)
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
GUARD_R = LOCAL     # capture guard (rules/hunt.py): an at-war army this close to a capture of ours in Action ...
GUARD_FC = 1.0      # ... whose battle forecast (with the capture's armies, GUARD_FC_T) is below this is huntable
GUARD_FC_T = 60     # s: ... however far from our land (user: Atreides' Taliel liberation thinned to 1 army)
GUARD_CW = 0.5      # its score + this x CONTEST_W: below our own villages' contests, above every chase
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
OPS_EXTRACT_HP = 0.5  # ... and those armies down to this share of their health (power-weighted): the last-moment escape
OPS_EXTRACT_MIN = 80000  # ... and the armies that would use its circle (still fighting, within 3 x EXTRACT_R of the village)
                         # worth this much (user: cast for one 29k S_Trooper walking home, out of the circle's reach)
OPS_EXTRACT_N = 3  # ... and at least this many armies (both triggers; user 2026-10-25: ~500 Intel, never for 1-2 units)
OPS_LATE = 0.75    # Cease Fire: only while the enemy capture of our village is below this progress
OPS_CF_MIN = 0.3   # ... and at least this (delay: the attacker commits first); never on a Pillage (user)
OPS_CF_HOPE = 0.9  # ... and the battle forecast there (defend, opsbrain.OPS_FC_T) is below this
OPS_BIGFIGHT = 120000  # fight ops: both sides' power together at least this (~3 armies; 250k skipped every Harkonnen-Fremen fight of match 23:36: 2-3 armies a side, 169-181k)
OPS_B_LO = 0.7     # combat ops in fights with balance (ours / theirs) in [OPS_B_LO, OPS_B_HI]: they swing it
OPS_B_HI = 2.0
OPS_DRUG_HI = 1.4  # Combat Drugs alone (no Sleeper held) only up to this balance
OPS_SCAV_B = 0.8  # Scavenger Team on a big fight from this balance (their dead pay; ours would too, but we lose less)
OPS_BOLD_K = 1.5   # fight retreat balance x this in a zone where our Sleeper Agent / Combat Drugs runs (0.65 -> ~0.43)
OPS_THUMP_PW = 150000  # deny thumper: their visible group in its zone at least this ...
OPS_THUMP_DEPTH = 200  # ... still this far from its path end (a long desert walk: it can't just step out) ...
OPS_THUMP_NEAR = 150   # ... which lies this close to a structure of ours ...
OPS_THUMP_HOPE = 1.0   # ... and the battle forecast there (defend, opsbrain.OPS_FC_T) below this
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
DWF_T = 20         # s: retreat lock: an army whose Defense vanilla cancelled in Waiting isn't picked for a Defense
RLOCK_FLEE_T = 15  # s: retreat lock: an army vanilla's micro set to Flee this recently isn't picked for a Defense
SD_NEED_SHARE = 0.34  # locked drop: the short armies at the target hold at least this share of the order's power there
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
SD_WIN = 1.0       # emergency drop for a fighting army: the battle forecast at it (over SD_FC_T) >= this (a lost fight
                   # retreats anyway: a drop there is wasted)
SD_FC_T = LOCAL // CONTEST_SPD  # s: ... the forecast window (the walk of LOCAL: the fight is now)
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
DMZ_HOME_R = 400  # a DMZ village farther than this from our main base whose Annex costs more Authority than we hold
                  # is a plain Pillage target (user: "never burnt" makes sense near our base)
DMZ_PREF = 0.5     # press: a DMZ village's distance x this (ranks first)
DMZ_BASE_R = 200   # a village of E this close to E's active main base is E's home, never a DMZ village (base guns
                   # COVER_R 130 + its defenders' reach; Tsimron 118 from Arrakeen; Fon-Al'lulah 233 was taken)
ENCL_N = 2         # enclave (rules/dmz.py aimod_encl): another faction's village whose region borders this many of ours is
                   # a DMZ village at war (any border count), pressable against a stronger owner, and breaks a truce
CROSS_R = RALLY_MIN  # a heal / strand / rally walk passing this close to our structure under at-war siege (or the
                     # rally's danger structure) goes through the enemy (Harkonnen walked past Fremen at Tsimlat)
RALLY_SAFE = 150   # ... and has no at-war power within this
RALLY_PT_MAX = RALLY_R  # ... and is at most this far from the danger structure (defenders come from within RALLY_R)
RALLY_MB = 150     # the main base counts this much closer (its guns fight with us)
RALLY_AT = 60      # a defender this close to the rally point has arrived (no move, not held)
RALLY_OFF = 40     # the gather point lies this far outside the rally structure's radius, on the danger side
RALLY_AT_HYST = 40  # ... once sent there (within RALLY_HYST_T s) it stays arrived this much farther out
RALLY_HYST_T = 120
RALLY_MOVE_T = 5   # s: a defender is re-sent at most this often
RALLY_HOLD = 5     # s: a rallying army stays out of vanilla's picks this long after the last pass saw it walking
RALLY_HYST = 1.15  # a running rally ends only at ENTER x this (no on / off flicker at the threshold)
RALLY_OFF_T = 10   # s: a running rally whose D misses a pass (active test flicker) holds this long while still short there
RALLY_RESUME = 30  # s: a rally back on this soon after its last qualifying pass keeps its RALLY_GIVEUP clock
RALLY_GIVEUP = 60  # s: a rally on the same danger structure still short after this concedes it ...
CONCEDE_DROP = 0.3  # a conceded structure reopens once the threat there is below this x the side it was conceded to
CONCEDE_HOLD = 45    # s: ... and never sooner than this after the concession (no reopen on one empty reading)
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
DR_HOLD_T = 20     # s: an army the base-kill direct raze sent this recently (bkill `bcdk`) gets no vanilla Resupply ...
DR_WAVE_T = 600     # s: ... only one that left with a wave this recently (bkill `bcdpa`)
DR_HOLD_SUP = 0.15  # ... unless below this supply share (= bkill.BC_DR_SUP) or LIFE_CRIT life
LIFE_CRIT = 0.25   # an army in a fight with others of ours leaves alone to heal only below this life (heal.py `stay`)
RS_GAP = 15        # s: vanilla's checkUnits Resupply for an army in a fight at most once per this (no 2 s re-issue loop)
HDEAD_N = 5        # heal-dead (rules/orders.py): this many Resupply / Patrol orders to one structure cancelled in Waiting ...
HDEAD_W = 60       # ... within this many s mark it dead (was 30: a jammed army re-ordered every 5-7 s
                   # made 4-5 per 30 s, Atreides x14-21 regroup loops, matches 2026-10-05 01:24 / 01:45) ...
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
MISSION_W = 0.5    # siege sizing (owner armies, siege._owner_armies): a seen owner army in a Military order on another
                   # structure counts this share (user: the threat read too large while the stack was out liberating)
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
RAID_RETRY = 150   # s: a village our raid left (aborted, or cancelled at once by vanilla) isn't raided again this soon
                   # (was 60: Atreides' Tab-Al'tar raid aborted `weak` 62:03 as Harkonnen's 423k came, relaunched 63:30 at
                   # 240k vs 230k and lost it, match 2026-10-04 23:14; a relief stays longer than a minute)
FRONT_R = 600      # director: enemy villages this close to our land are the front (policy §5b)
PRESS = KILL       # ... soft = the spare armies in reach have this x (armies in reach + cover + militia) / terrain
PRESS_R = HUNT_R   # ... spare armies this close to a village can take part (same reach as siege-join)
PRESS_KEEP = ABORT  # a press is dropped when our power there (any task) x terrain < this x their side
BK_PRESS = 1.2     # base-kill plan: the leader's villages are soft at this (not PRESS: the coalition shares the load;
                   # ENTER 1.5 still left 4-6 of 9 not soft, best 22-96%, match 2026-10-24 14:40; siege-join still sizes the launch;
                   # the forecast's leader side is split / net of partners; match 2026-10-24 14:20: best 13-84% vs 300%)
BK_PRESS_R = 2 * PRESS_R  # ... with our spare armies within this (a short walk; 3-4 of 9 leader villages had none in PRESS_R)
PRESS_MAX = 240    # s: a press not finished by then is dropped (`slow`); enemy Annex ~ walk + militia + 6 days
PRESS_RETRY = 120  # s: a dropped press target isn't pressed again this soon
ANNEX_SPECIAL = 30  # Annex score + this for a village in a special region (region aiWeight >= 20, vanilla adds that
                    # weight once; specials yield more hegemony), before the cost ratio
ANNEX_SIETCH = 10  # Annex score + this for a village whose zone has a sietch (Zone.getSietch), before the cost ratio
ANNEX_SPICE1 = 4    # Annex score x this for a spice village while we own none (vanilla +100 too), after the cost
                    # ratio and every other term (x2 could lose to a +50 special x centre x compactness): the first capture is a spice field
                    # ratio: the opening takes a spice field first. Not for SPICE_ANY factions (harvest anywhere)
AF_NONE = no_building_factions('Airfield')  # never get one (vanilla: Fremen, worm rides instead; modded factions by data)
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
CLAIM_R = 600       # ... with the battle forecast over the walk of this (claim.CLAIM_FC_T) at least ENTER; each
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
BEST_COUNT = 'AI_StructureScore_BestStructuresCount'  # constant id (const_index): vanilla picks its siege
                   # target at random among this many best scores (Insane 2 ... Easy 5)


FC_REACT_T = REACT_R // CONTEST_SPD  # s: the sizing window of `_fc_theirs` (the walk of REACT_R: who can come)


BK_SPLIT = 0.6     # base-kill plan: the leader's armies that aren't already at a place count this share there (user:
                   # the leader can be in one place only; its stack parked, every coalition member held home against all
                   # of it and none attacked: match 2026-10-24 12:2x)


BK_OPS = ('MDefenseSabotage', 'MAdministrativeBurden')  # base-kill ops (main base only, need 4; user: the base attack
# uses ops its members prepare, never stacked): Defense Breaches (the base takes 1.5 x damage, -3 armor, 3 days),
# Administrative Burden (the target trains units / builds base buildings at 40% speed, 3 days)
BK_AB_WIPE = 0.4  # Administrative Burden (user: only useful once the enemy army was dropped, it adds rebuild time):
BK_AB_PEAK_T = 300  # ... cast when the leader's army (fpow, as we last saw it) <= BK_AB_WIPE x its peak within BK_AB_PEAK_T
BK_AB_MIN = 300000  # ... a peak at least this (a small army's losses are no wipe)
BK_URG_ETA = 10    # days: the base-kill leader this close to winning makes the plan urgent (rules/bkill.py BC_URG_ETA)
BK_RAID_LEADER = 0.5   # urgent plan: a raid candidate of the leader's counts this x nearer ...
BK_RAID_NEUTRAL = 3.0  # ... a neutral one this x farther (bleed the leader, not the map)
BK_LIVE_T = 30  # s: base-kill ops are cast only while a member ran the campaign this recently (rules/bkill.py `bcseen`)
BK_OP_R = 150   # Defense Breaches: cast once a coalition army is this close to the leader's base (main base range 80)


# ---- task claims (rules/tasks.py, docs/ARCHITECTURE-PLAN.md step 2 stage 1)
CLAIM_TTL = 8     # s: a claim not refreshed this long has lapsed (refresher every TASK_T 2 s, rally every RALLY_T)
TASK_T = 2        # s between refresher passes per faction
P_MAINBASE, P_CONTEST, P_CAPTURE, P_DEFENSE, P_SIEGE, P_CHASE, P_HEAL, P_IDLE = 100, 80, 70, 60, 50, 40, 30, 10
P_RALLY = 65      # a rally gather walk (rules/rally.py claims it explicitly: no order); its own value, so `_rallying`
                  # tells it from a Defense (was the `rallied` lock map)
SIEGE_P, DEFENSE_P, MAINBASE_P, DISC_P = P_HEAL, P_RALLY, P_MAINBASE, P_IDLE  # what vanilla's picks ask; a Defense
                  # asks P_RALLY: a rallying army is still a defender (Atreides' Tuo-tar Defense found 0 candidates while
                  # all were held for Tuonah; next to the rally's D the defense extras drop it); a siege
                  # launch asks P_HEAL: any order's armies above Resupply stay (taking one before Action cancels that
                  # order: Fremen's 8-army Liberate of Tuonah died when a prio-3 Annex took one; was the `keepord` lock)
P_RAZE = 90       # the base-kill direct raze (rules/bkill.py): above contests, below our own main base (match 55: a
                  # contest hunt on Rebels at Harkonnen's Gurlat took its 11 campaign armies off the walk to Arrakeen)
FREE_P = P_CHASE  # what aimod_free asks: an army held above a chase isn't free
SX_MIN = 3        # siege memory (rules/tasks.py): an Action this big at least ...
SX_MEM = 600      # s: ... that lost half its armies marks its target lost for its faction this long (annex scoring drops it)
SX_FC = 1.0         # ... and the order's survivors read a battle forecast below this at the target (over SX_FC_T)
SX_FC_T = 60


__all__ = [name for name in globals() if name.isupper()]
