"""Base-kill campaign (stage 3; docs/BASEKILL-PLAN.md 7b / 7c, docs/AI-POLICY.md): `build_bk_campaign` emits one
bytecode function per pass from its section emitters (one module each, in pass order): numbers, phase, member,
muster, go, raze. Campaign state: rules/bkstate.py; the base-kill plan (threat picture, leader, levels):
rules/bkill.py."""
from types import SimpleNamespace

from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules import bkstate as bks
from rules.worm import _do_on, _move_to
from rules.bkcamp.shared import *  # noqa: F401,F403
from rules.bkcamp.numbers import _emit_numbers
from rules.bkcamp.phase import _emit_phase
from rules.bkcamp.member import _emit_member
from rules.bkcamp.muster import _emit_muster
from rules.bkcamp.go import _emit_go
from rules.bkcamp.raze import _emit_raze

BC_STAGE_MIN = 90    # staging structure: ours, at least this far from the leader's base (out of its guns, range 80;
                     # a foothold at 150-250 counts) ...
BC_STAGE_MAX = 4000  # ... at most this far (the whole map: user 2026-10-25, match 59: Harkonnen had none within 1000 of
                     # Arrakeen, never mustered and its armies never counted in M; the campaign held off all match)
BC_TRACE = ('act', 'go', 'go_new', 'gad', 'lead_d', 'go_raze', 'go_ef', 'gap', 'gzd', 'go_nr', 'go_r', 'go_dr',
            'drd', 'mu_st')  # `bcpass`: the last of these a pass reached
BC_PASS_T = 10       # s: one `bcpass` row per faction this often


def build_bk_campaign(cx, helpers, pw, free):
    """aimod_bkcamp(mil, dt): the base-kill campaign (stage 3, first slice; BASEKILL-PLAN 7b / 7c). Every BC_T s per
    faction at level 2 (assault) against the leader L with a main base B:
    - the numbers (every member computes the same ones, so all reach the same phase without messaging): D = the
      battle forecast's their side at B (BC_FC_T: its guns, L's armies that can be there; common._fc_theirs; shared:
      the trimmed mean of the members' fresh readings), P = the power of every member's armies (members: level >= 2,
      at war with L, not with us), M = the part within BC_MUSTER_R of B or no farther from B than the member's
      staging structure (map `bcsg`, posted by each member) + BC_STAGE_AT + 50;
    - the phase, one per base (maps `bcp` phase, `bcpt` since, `bccs` since when the change's condition holds,
      `bcgo` go time): 0 attrition (level-1 tools bleed L: presses, joint attacks) -> 1 muster at P >= BC_POT x D;
      1 -> 2 go at M >= BC_KILL x D (the go time is recorded); urgent (the leader's ETA <= BC_URG_ETA days): BC_POT_URG,
      BC_KILL_URG, BC_POT_OUT_URG instead; after BC_MUSTER_MAX s of muster: go at M >= BC_EVEN x D,
      else 0; 1 -> 0 at P < BC_POT_OUT x D after BC_COMMIT;
      2 -> 3 regroup at M < BC_KEEP x D or after BC_GO_MAX s (one try); 3 -> 1 after BC_REGROUP s. A change needs its condition for BC_HOLD s;
    - this member's part (no movement code of its own, 7c): muster / regroup: each free army (aimod_free) farther than
      BC_STAGE_AT from our staging structure (ours, nearest B, BC_STAGE_MIN..BC_STAGE_MAX from it) gets a Patrol order
      there, at most every BC_MOVE_T s; every free army is claimed P_RALLY each pass (on its way or there); go: once per go time, within BC_GO_WIN, a Military ArmySiege
      Raze order on B (prio BC_PRIO) with our armies within BC_MUSTER_R of B by the lead only (the member with the most
      power near B: a structure holds one besieging faction), every other member an ArmyFight on L's armies it sees
      within BC_MUSTER_R of B (map `bcfo` order -> B: no hunt leash / home / drift abort), again whenever its last one
      ended, all go long; while it sees none, all go
      long, its free armies (claimed P_RALLY) march to BC_APPROACH from B on their side (log act approach) (map `bcl` faction -> the go
      it launched; tasks.py marks the siege: doctrine Siege mode). The fight is the existing rules' (retreat, drain,
      forecast).
    Logs `bcamp` act phase (from, to, D, M, P, hp) on a change; act muster (n sent, s staging) per 30 s; act go (n,
    ok). Fails safe: in a trap.
    Emitted as one function by the section emitters below the prologue, in order: _emit_numbers, _emit_phase,
    _emit_member, _emit_muster, _emit_go, _emit_raze. They share the context `c` (this function's locals): each takes
    the names it reads from earlier sections (`_take`) and hands on the ones later sections read (`_give`)."""
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    # per-pass trace (`bcpass`, every BC_PASS_T s per faction): the last BC_TRACE label this pass went through, so an
    # early exit shows where it left (7 matches went by with every direct-raze pass ending at one check, invisible)
    step = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=step, src=b.const('i32', 0))
    tfac = fb.reg(cx.t('ent.Faction'))
    fb.op('Null', dst=tfac)
    _label = fb.label

    def _traced(name):
        _label(name)
        if name in BC_TRACE:
            fb.op('Mov', dst=step, src=b.const('i32', BC_TRACE.index(name) + 1))
    fb.label = _traced
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    st = _state(fb, b, cx)
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(st, 'time'))
    _tick(fb, b, cx, t, BC_T, 'end')
    fb.op('Mov', dst=tfac, src=fac)  # a real pass: traced
    lv = b.call('haxe.ds.ObjectMap.get', _global_map(fb, b, cx, 'bkv'), fb.dyn(fac))
    fb.op('JNull', reg=lv, offset='end')
    li = fb.reg(cx.t('i32'))
    fb.op('SafeCast', dst=li, src=lv)
    fb.op('JSLt', a=li, b=b.const('i32', 2), offset='end')
    ld = _bk_target(fb, b, cx, fac, 'end')
    lb = b.call('ent.Faction.get_mainBase', ld)
    fb.op('JNull', reg=lb, offset='end')
    be = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=be, src=lb)
    zero = b.const('f64', 0)
    # our staging structure (ours, nearest the base, BC_STAGE_MIN..BC_STAGE_MAX from it), posted for every member's
    # muster count (map `bcsg` faction -> structure: armies at a member's staging point are mustered)
    stg = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=stg)
    sbd, sd = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Mov', dst=sbd, src=b.const('f64', BC_STAGE_MAX))
    ss = b.cast(fb.get(fac, 'structures', 'array'), 'hl.types.ArrayObj')
    fb.op('JNull', reg=ss, offset='sgd')
    si = fb.reg(cx.t('i32'))
    fb.op('Mov', dst=si, src=b.const('i32', 0))
    b.loop_head('sg')
    fb.op('JSGte', a=si, b=b.field(ss, 'length'), offset='sgd')
    s2 = b.cast(b.call('hl.types.ArrayObj.getDyn', ss, si), 'ent.Entity')
    fb.op('Incr', dst=si)
    fb.op('JNull', reg=s2, offset='sg')
    sz = b.call('ent.Entity.get_zone', s2)
    fb.op('JNull', reg=sz, offset='sg')
    fb.op('JNotEq', a=b.field(sz, 'owner'), b=fac, offset='sg')
    fb.op('Mov', dst=sd, src=b.call('ent.Entity.getDistTo', s2, be))
    fb.op('JSLt', a=sd, b=b.const('f64', BC_STAGE_MIN), offset='sg')
    fb.op('JSGte', a=sd, b=sbd, offset='sg')
    fb.op('Mov', dst=sbd, src=sd)
    fb.op('Mov', dst=stg, src=s2)
    fb.op('JAlways', offset='sg')
    fb.label('sgd')
    bcsg = _global_map(fb, b, cx, bks.STAGING)
    fb.op('JNull', reg=stg, offset='sg_rm')
    b.call('haxe.ds.ObjectMap.set', bcsg, fb.dyn(fac), fb.dyn(stg))
    fb.op('JAlways', offset='sg_ok')
    fb.label('sg_rm')
    b.call('haxe.ds.ObjectMap.remove', bcsg, fb.dyn(fac))
    fb.label('sg_ok')
    c = SimpleNamespace(**locals())  # the context the per-section emitters share (their locals)
    _emit_numbers(c)
    _emit_phase(c)
    _emit_member(c)
    _emit_muster(c)
    _emit_go(c)
    _emit_raze(c)
    fb.label('end')
    fb.end_try(guard)
    fb.label = _label
    gtr = fb.try_()
    fb.op('JNull', reg=tfac, offset='tr_d')
    _throttle(fb, b, cx, 'bcpass', tfac, BC_PASS_T, 'tr_d')
    stn = fb.reg(cx.t('String'))
    fb.op('Mov', dst=stn, src=fb.string('pass'))
    for k_, name_ in enumerate(BC_TRACE):
        u_ = f'tr{k_}'
        fb.op('JNotEq', a=step, b=b.const('i32', k_ + 1), offset=u_)
        fb.op('Mov', dst=stn, src=fb.string(name_))
        fb.label(u_)
    _log_ev(fb, b, cx, helpers, 'bcpass', [('f', fb.get(tfac, 'kind')), ('last', stn)])
    fb.label('tr_d')
    fb.end_try(gtr)
    fb.op('Ret', ret=void)
    return fb.build()
