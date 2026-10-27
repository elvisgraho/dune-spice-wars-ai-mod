"""Base-kill campaign state (rules/bkill.py `build_bk_campaign`): every global map the campaign keeps, named once,
and typed accessors for the reads other rules make (rules/heal.py, strike.py, ...).

The map names are the strings the maps are stored under (logs, docs and the bcheck baseline refer to them), so the
strings stay as they are; the constants carry their meaning. B = the leader's main base (the campaign target), go =
one try (phase 2) from its go time `GO` on. Times are game seconds (State.time). The base-kill plan's own maps (`bkv`
level, `bkl` leader, `bkw` / `bke` / `bkc` / `bkh0` / `bkt0` / `bkr`: rules/bkill.py `build_bk_tick`, read by common
`_bk_target`) are not campaign state and are not listed here."""
from rules.common import _global_map, _map_val

# ---- per base B: the shared phase
PHASE = 'bcp'          # B -> phase (0 attrition, 1 muster, 2 go, 3 regroup)
PHASE_T = 'bcpt'       # B -> time of the last phase change
GO = 'bcgo'            # B -> the current go's start time
LEFT_ATT = 'bcat'      # B -> time the campaign last left attrition (BC_COMMIT)
SEEN = 'bcseen'        # B -> last campaign pass (stale -> starts over in attrition; opsbrain / sdrop read it)
STRIKE = 'bcsk'        # B -> time the go's strike was committed (BC_ALL_DIRECT)
COND_SINCE = 'bccs'    # per faction (_fac_map): B -> since when this member's phase-change condition holds
COND_PHASE = 'bccp'    # per faction (_fac_map): B -> the phase that condition started in
COND_TO = 'bccn'       # per faction (_fac_map): B -> the proposed destination phase

# ---- per member faction: readings posted each pass
D_OWN = 'bcd'          # faction -> its own defense reading D at B
D_OWN_T = 'bcdt'       # faction -> when D_OWN was posted
D_OWN_B = 'bcdb'       # faction -> the base D_OWN describes
D_SHARED = 'bcdsh'     # faction -> the shared (trimmed) D its last pass used (heal.py: the raze fight balance)
M_POST = 'bcmm'        # faction -> its mustered power M
M_POST_T = 'bcmmt'     # faction -> when M_POST was posted
M_POST_B = 'bcmmb'     # faction -> the base B its M_POST is for
NEAR_PW = 'bcpm'       # faction -> its power near B this pass (cleared each pass)
GO_PW = 'bcgp'         # faction -> its go power (armies that can launch: supply-filtered)
GO_PW_T = 'bcgpt'      # faction -> when GO_PW was posted
GO_PW_NOW = 'bcgpr'    # faction -> its present power at B
STAGING = 'bcsg'       # faction -> its staging structure
WALK = 'bcwd'          # faction -> its walk from the strike point to B (staggered departure)
WALK_T = 'bcwdt'       # faction -> when WALK was posted
GO_TIME = 'bcgt'       # faction -> the go time of its current go (heal.py's wave test)

# ---- per member faction: the go's launch / raze
LAUNCH = 'bcl'         # faction -> time it launched (or direct-razed) in this go
LAUNCH_ORDER = 'bclo'  # faction -> its Raze order of this go
CUT = 'bccut'          # faction -> supply-share cut after a Raze died in Waiting (sdrop reads it)
MIN_SUP = 'bcminr'     # faction -> the lowest army supply share of its launched order
RAZE_ACT = 'bcdr'      # faction -> last pass its direct raze acted (holds the go; heal.py: BK_DR_LIVE)
WAVE_GONE = 'bcdep'    # faction -> time this go's (last) wave left the strike point
WAVE_PW = 'bcdepw'     # faction -> the first wave's power (a second wave needs BC_WAVE2_K of it)
WORM_WAIT = 'bcpw'     # faction -> since when a worm-held walker holds the wave
FIELD = 'bcfa'         # faction -> the field-army target (sticky while alive, visible, in range)
TURRET = 'bctv'        # faction -> the turret-village target

# ---- per member faction / village: captures
FOOT_ANNEX = 'bcfan'   # faction -> its own foothold / step village (held through a go)
FOOT_CLAIM = 'bcffv'   # village -> the member faction that claimed it for a capture
FOOT_CLAIM_T = 'bcffvt'  # village -> when that claim was made / refreshed
FOOT_GO = 'bcffgo'     # village -> time the capture pack launched (BC_FF_GO_T)

# ---- per army
CLAIMED = 'bcmc'       # army -> last time the campaign claimed it (strike / strand / heal read it)
SENT = 'bcdk'          # army -> last time the direct raze sent / kept it (heal.py: the resupply hold)
WAVE_LEFT = 'bcdpa'    # army -> time it left with a wave (in this go when >= GO_TIME)
COH_WAIT = 'bccw'      # army -> since when it waits for the column
FIELD_SENT = 'bcdfe'   # army -> the field target it was last sent at

# ---- per order
FIGHT_ORDER = 'bcfo'   # order -> B (a supporter's fight order; hunt / tasks read it)


def wave_left(fb, b, cx, army, missing, dst=None):
    """The time `army` left with a wave (map WAVE_LEFT) in an f64 register; jump to `missing` when it never did."""
    return _map_val(fb, b, cx, _global_map(fb, b, cx, WAVE_LEFT), army, missing, dst)


def shared_defense(fb, b, cx, fac, missing, dst=None):
    """The shared (trimmed) defense reading D faction `fac`'s last pass used (map D_SHARED)."""
    return _map_val(fb, b, cx, _global_map(fb, b, cx, D_SHARED), fac, missing, dst)

