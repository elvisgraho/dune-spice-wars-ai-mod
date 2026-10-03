"""Release spare armies from an occupation under way (AI-POLICY §5a "Armies, positions, hazards").

Why: once our capture / pillage is in Action and the militia is beaten (occupation progress > 0), one army finishes it
(AIOrder.removeUnit cancels an order only before Action or when it empties), yet vanilla keeps every army of the
order standing there until it ends. User: "1 unit can always finish things"; free the rest whenever the place holds no
danger, and when a structure of ours needs them (raid.py `defend` / `home` split).

aimod_relunits(order, annex, keep) -> armies released. Who stays: an army below RELEASE_SUP supply (the pillage refill /
the captured village resupplies it there), on an Annex also one below RELEASE_LIFE health (it heals at the new
village), and always the keeper: the weakest permanent ground army occupying the target (Army.occupiedStructure ==
the order's target: only an army in occupation range holds the capture, and vanilla doesn't re-send an idle order
army into a village already under our siege; aimod_pw, hasSafeRegen: a temporary one disbands and the emptied order
is cancelled; the weakest occupying ground one if none is permanent; never a flyer: Unit.isFlying armies can't
occupy). No occupying ground army found: nothing is released. Everyone else is removed from the order
(idle: vanilla's Defense / our hunts / raid pick them up). Nothing is released from an order of one army or when all
need the refill. keep: power (aimod_pw) the staying armies must still hold; an army leaves only while the rest keep at
least that much (release: 0; raid split: ENTER x the enemy side at the target / terrain: Fremen's Liberate of Arknit,
95 from Arrakeen and winning 12:1, was split `home` at 22:24, 8 of 14 armies (96% of its power) left and the 6
weakest were wiped by Atreides' relief). The caller checks phase Action and progress > 0. Capture speed doesn't depend
on the army count (user).

aimod_release(mil, dt), tick chain every RELEASE_CHECK s: our Military Annex / Pillage / Liberate
orders on a structure in Action with progress > 0 and 2+ armies, when no danger reaches the target before
the occupation ends: aimod_threat within max(REACT_R, remaining time (_cap_rem) x CONTEST_SPD) (user: captures take
long, worth keeping the armies while an enemy army could come; busy armies count at their discounted weight, so any
enemy army in reach locks the order), neutral raiders there (aimod_neutral) and enemy turret cover (aimod_cover) all
0; a stalled occupation is never released. Logs `release` (tgt, sa, n released, of).
Rejoin (same pass, any army count): an occupation under way (progress > 0, or one started in this siege with no
militia alive and the siege still ours: a frozen capture may lose its progress) where no order army occupies the target
and none fights: the nearest ground order army gets doAction("ArmySiege", EEntity(target)) (vanilla Action's own
call; vanilla re-sends it only while the village isn't under our siege, so a capture whose occupier walked off
froze), at most once per order per REJOIN_T s; logs `rejoin` (tgt, a, d, pr, n). The keeper is protected from
vanilla picks (heal.py pick-life: the last army of an order in Action). Fails safe: in a trap."""
from rules.common import *  # noqa: F401,F403  thresholds (AI-POLICY §4) and bytecode helpers
from rules.worm import _do_on

RELEASE_CHECK = 5   # s: scan period
REJOIN_T = 10       # s: at most one rejoin per order this often (the walk in takes a few seconds)
RELEASE_KINDS = ('Annex', 'Pillage', 'Liberate')  # not sietch / renegade-base strikes: the sietch deploys its
# harass units mid-strike (SITE_REQ), a thinned force loses to them


def build_relunits(cx, pw):
    fb = FB(cx, [cx.t('logic.ai.AIOrder'), cx.t('bool'), cx.t('f64')], cx.t('i32'))
    b = B(fb)
    n = b.const('i32', 0)
    tp = fb.reg(cx.t('f64'))  # power of the armies still in the order
    zero, one = b.const('f64', 0), b.const('i32', 1)
    guard = fb.try_()
    fb.op('JNull', reg=0, offset='end')
    units = b.field(0, 'units')
    fb.op('JNull', reg=units, offset='end')
    un = b.field(units, 'length')
    fb.op('JSLte', a=un, b=one, offset='end')
    occ_s = b.cast(b.call('logic.ai.AIOrder.getTarget', 0), 'ent.Structure')
    fb.op('JNull', reg=occ_s, offset='end')
    j = fb.reg(cx.t('i32'))
    p, best, q = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    needy = fb.reg(cx.t('bool'))
    weak, weakr = fb.reg(cx.t('ent.Army')), fb.reg(cx.t('ent.Army'))
    fb.op('Null', dst=weak)
    fb.op('Null', dst=weakr)
    bestr = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=bestr, src=b.const('f64', 1 << 30))
    fb.op('Bool', dst=needy, value=False)
    fb.op('Mov', dst=best, src=b.const('f64', 1 << 30))
    rsup, rlife = _ratio(fb, b, RELEASE_SUP), _ratio(fb, b, RELEASE_LIFE)
    fb.op('Mov', dst=tp, src=zero)

    def needs(a, yes, no):
        """jump to `yes` when army a needs the occupation's refill, else to `no`."""
        ms = b.call('ent.Army.get_maxSupply', a)
        nl = _uid('nl')
        fb.op('JSLte', a=ms, b=zero, offset=nl)
        fb.op('SDiv', dst=q, a=b.call('ent.Army.get_supply', a), b=ms)
        fb.op('JSLt', a=q, b=rsup, offset=yes)
        fb.label(nl)
        fb.op('JFalse', cond=1, offset=no)
        fb.op('JSLt', a=b.call('ent.Entity.get_lifeRatio', a), b=rlife, offset=yes)
        fb.op('JAlways', offset=no)

    # pass 1: does any army need the refill; the weakest one (fallback keeper)
    a = _army_loop(fb, b, units, un, j, 'p1', 'p1d')
    needs(a, 'p1n', 'p1w')
    fb.label('p1n')
    fb.op('Bool', dst=needy, value=True)
    fb.label('p1w')
    fb.op('Call1', dst=p, fun=pw, arg0=a)
    fb.op('Add', dst=tp, a=tp, b=p)
    # the keeper must walk: flying armies (ships) can't occupy, a ship left alone stalls the occupation (Harkonnen's
    # Pillage of Tab-Al'lon kept its H_Ship, released the H_Elite at 23%: stuck 8+ min)
    fb.op('JTrue', cond=b.call('ent.Unit.isFlying', a), offset='p1')
    # ... and it must be the one occupying: only an army in occupation range holds the capture, vanilla re-sends
    # ArmySiege to idle order armies only while the village isn't under our siege (Smugglers' Annex of Aynno kept an
    # S_Sneak standing 53 out and released the occupying S_Trooper at 1%: nobody occupied, the capture froze)
    fb.op('JNotEq', a=b.field(a, 'occupiedStructure'), b=occ_s, offset='p1')
    fb.op('JSGte', a=p, b=best, offset='p1r')
    fb.op('Mov', dst=best, src=p)
    fb.op('Mov', dst=weak, src=a)
    fb.label('p1r')
    # the keeper should be permanent: a temporary unit (no safe regen: Discovery_* recruits) disbands, and an emptied
    # order is cancelled with the capture
    fb.op('JFalse', cond=b.call('ent.Unit.hasSafeRegen', a), offset='p1')
    fb.op('JSGte', a=p, b=bestr, offset='p1')
    fb.op('Mov', dst=bestr, src=p)
    fb.op('Mov', dst=weakr, src=a)
    fb.op('JAlways', offset='p1')
    fb.label('p1d')
    fb.op('JNull', reg=weakr, offset='p1k')
    fb.op('Mov', dst=weak, src=weakr)
    fb.label('p1k')
    fb.op('JNull', reg=weak, offset='end')  # no ground army occupying it: nobody could finish it alone, release none
    # pass 2, backwards (removeUnit shrinks the list): the keeper and the needy stay, the others go
    fb.op('Mov', dst=j, src=b.field(units, 'length'))
    b.loop_head('p2')
    fb.op('JSLte', a=j, b=b.const('i32', 0), offset='end')
    fb.op('Sub', dst=j, a=j, b=one)
    x = b.cast(b.call('hl.types.ArrayObj.getDyn', units, j), 'ent.Army')
    fb.op('JNull', reg=x, offset='p2')
    fb.op('JEq', a=x, b=weak, offset='p2')  # the keeper always stays (permanent if any)
    fb.op('JFalse', cond=needy, offset='p2go')
    needs(x, 'p2', 'p2go')
    fb.label('p2go')
    fb.op('JSLte', a=b.field(units, 'length'), b=one, offset='end')  # never the last one
    px = fb.reg(cx.t('f64'))
    fb.op('Call1', dst=px, fun=pw, arg0=x)
    fb.op('Sub', dst=q, a=tp, b=px)
    fb.op('JSLt', a=q, b=2, offset='p2')  # the rest would fall below `keep`: it stays
    fb.op('Mov', dst=tp, src=q)
    b.call('logic.ai.AIOrder.removeUnit', 0, x)
    fb.op('Incr', dst=n)
    fb.op('JAlways', offset='p2')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=n)
    return fb.build()


def build_release(cx, helpers, relunits, threat, neutral, cover):
    fb = FB(cx, [cx.t('logic.ai.AIMilitary'), cx.t('f64')], cx.t('void'))
    b = B(fb)
    void = fb.reg(cx.t('void'))
    guard = fb.try_()
    ctrl = b.field(0, 'controller')
    fac = b.field(ctrl, 'owner')
    fb.op('JNull', reg=fac, offset='end')
    t = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=t, src=b.field(_state(fb, b, cx), 'time'))
    _tick(fb, b, cx, t, RELEASE_CHECK, 'end')
    orders = b.field(b.field(ctrl, 'aiOrders'), 'orders')
    fb.op('JNull', reg=orders, offset='end')
    zero, local = b.const('f64', 0), b.const('f64', LOCAL)
    k, ix, rn, un = (fb.reg(cx.t('i32')) for _ in range(4))
    d, q, pr = fb.reg(cx.t('f64')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    anx = fb.reg(cx.t('bool'))
    ve = fb.reg(cx.t('ent.Entity'))
    no_ent = fb.reg(cx.t('ent.Entity'))
    fb.op('Null', dst=no_ent)
    t_false = fb.reg(cx.t('bool'))
    fb.op('Bool', dst=t_false, value=False)
    no_arr = fb.reg(cx.t('hl.types.ArrayObj'))
    fb.op('Null', dst=no_arr)
    kinds = [(kd, fb.dyn(fb.string(kd))) for kd in RELEASE_KINDS]
    unf0 = fb.reg(cx.t('f64'))
    fb.op('Mov', dst=k, src=b.field(orders, 'length'))
    b.loop_head('o')
    fb.op('JSLte', a=k, b=b.const('i32', 0), offset='end')
    fb.op('Sub', dst=k, a=k, b=b.const('i32', 1))
    o = b.cast(b.call('hl.types.ArrayObj.getDyn', orders, k), 'logic.ai.AIOrder')
    fb.op('JNull', reg=o, offset='o')
    fb.op('EnumIndex', dst=ix, value=b.field(o, 'type'))
    fb.op('JNotEq', a=ix, b=b.const('i32', MILITARY), offset='o')
    fb.op('JNotEq', a=b.field(o, 'phase'), b=b.const('i32', ACTION), offset='o')
    tt = b.field(o, 'targetType')
    fb.op('JNull', reg=tt, offset='o')
    fb.op('EnumIndex', dst=ix, value=tt)
    fb.op('JNotEq', a=ix, b=b.const('i32', T_STRUCT), offset='o')
    units = b.field(o, 'units')
    fb.op('JNull', reg=units, offset='o')
    fb.op('Mov', dst=un, src=b.field(units, 'length'))
    fb.op('JSLte', a=un, b=b.const('i32', 0), offset='o')
    fb.op('ToSFloat', dst=unf0, src=un)
    sa = b.cast(fb.get(o, 'siegeAction'), 'String')
    fb.op('JNull', reg=sa, offset='o')
    fb.op('Bool', dst=anx, value=False)
    for kd, kdyn in kinds:
        nxt = _uid('kd')
        fb.op('JNotEq', a=b.call('String.__compare', sa, kdyn), b=b.const('i32', 0), offset=nxt)
        if kd == 'Annex':
            fb.op('Bool', dst=anx, value=True)
        fb.op('JAlways', offset='kok')
        fb.label(nxt)
    fb.op('JAlways', offset='o')
    fb.label('kok')
    s = b.cast(b.call('logic.ai.AIOrder.getTarget', o), 'ent.Structure')
    fb.op('JNull', reg=s, offset='o')
    fb.op('Mov', dst=ve, src=s)
    sg = b.field(s, 'siege')
    fb.op('JNull', reg=sg, offset='o')
    fb.op('Mov', dst=pr, src=b.call('ent.comp.SiegeComponent.getOccupationActionProgress', sg))
    # rejoin also when the progress went back to 0 without an occupier: an occupation started in this siege
    # (occupationStartTime > 0), no militia alive and the siege is still ours
    fb.op('JSGt', a=pr, b=zero, offset='rj_go')
    fb.op('JSLte', a=b.field(sg, 'occupationStartTime'), b=zero, offset='o')  # militia fight still on
    fb.op('JTrue', cond=b.call('ent.comp.SiegeComponent.hasActiveMilitia', sg), offset='o')
    fb.op('JNotEq', a=b.field(sg, 'besiegingFaction'), b=fac, offset='o')
    fb.label('rj_go')
    # rejoin: nobody of the order occupies the target and nobody fights -> the nearest ground army gets vanilla's
    # ArmySiege again (vanilla re-sends it only while the village isn't under our siege, so a capture whose occupier
    # left freezes for good: Aynno 1% with an idle S_Sneak 53 out; Atreides' Gurlon with an A_Elite 35 out)
    rj, rjd, rjq = fb.reg(cx.t('ent.Army')), fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('Null', dst=rj)
    fb.op('Mov', dst=rjd, src=b.const('f64', 1 << 30))
    rji = fb.reg(cx.t('i32'))
    ra = _army_loop(fb, b, units, un, rji, 'rjl', 'rjd')
    fb.op('JEq', a=b.field(ra, 'occupiedStructure'), b=s, offset='rj_ok')  # held: carry on with release
    fb.op('JTrue', cond=b.call('ent.Entity.isFighting', ra), offset='rj_ok')  # a fight there: micro decides
    fb.op('JTrue', cond=b.call('ent.Unit.isFlying', ra), offset='rjl')
    fb.op('JNotNull', reg=b.field(ra, 'harvestComponent'), offset='rjl')
    fb.op('Mov', dst=rjq, src=b.call('ent.Entity.getDistTo', ra, ve))
    fb.op('JSGte', a=rjq, b=rjd, offset='rjl')
    fb.op('Mov', dst=rjd, src=rjq)
    fb.op('Mov', dst=rj, src=ra)
    fb.op('JAlways', offset='rjl')
    fb.label('rjd')
    fb.op('JNull', reg=rj, offset='o')  # nobody can occupy (flyers only): leave it to vanilla
    _throttle(fb, b, cx, 'rejoin', o, REJOIN_T, 'o')
    rje = fb.reg(cx.t('ent.Entity'))
    fb.op('Mov', dst=rje, src=rj)
    _do_on(fb, b, cx, rje, 'ArmySiege', ve, fac)
    _log_ev(fb, b, cx, helpers, 'rejoin', [('f', fb.get(fac, 'kind')), ('tgt', ve), ('a', rje), ('d', rjd), ('pr%', pr),
                                           ('n', unf0)])
    fb.op('JAlways', offset='o')
    fb.label('rj_ok')
    fb.op('JSLte', a=pr, b=zero, offset='o')  # release: only once the occupation runs
    fb.op('JSLt', a=un, b=b.const('i32', 2), offset='o')
    # danger: hostile armies that can walk in before the occupation ends (radius = its remaining time x CONTEST_SPD,
    # at least REACT_R: user, captures take long, worth keeping the armies while an enemy army could come; capture
    # speed doesn't depend on the army count), raiders there, enemy guns over it. A stalled occupation keeps all.
    rem, _ = _cap_rem(fb, b, cx, s, t, 'o')
    fb.op('Mul', dst=rem, a=rem, b=b.const('f64', CONTEST_SPD))
    fb.op('JSGte', a=rem, b=b.const('f64', REACT_R), offset='rad')
    fb.op('Mov', dst=rem, src=b.const('f64', REACT_R))
    fb.label('rad')
    fb.op('Call3', dst=d, fun=threat, arg0=fac, arg1=ve, arg2=rem)
    fb.op('Call3', dst=q, fun=neutral, arg0=fac, arg1=ve, arg2=local)
    fb.op('Add', dst=d, a=d, b=q)
    fb.op('CallN', dst=q, fun=cover, args=[fac, ve, no_ent, t_false, no_arr])
    fb.op('Add', dst=d, a=d, b=q)
    fb.op('JSGt', a=d, b=zero, offset='o')
    fb.op('Call3', dst=rn, fun=relunits, arg0=o, arg1=anx, arg2=zero)  # nothing in reach: no floor
    fb.op('JSLte', a=rn, b=b.const('i32', 0), offset='o')
    rnf, unf = fb.reg(cx.t('f64')), fb.reg(cx.t('f64'))
    fb.op('ToSFloat', dst=rnf, src=rn)
    fb.op('ToSFloat', dst=unf, src=un)
    _log_ev(fb, b, cx, helpers, 'release', [('f', fb.get(fac, 'kind')), ('tgt', ve), ('sa', sa), ('n', rnf),
                                            ('of', unf), ('pr%', pr)])
    fb.op('JAlways', offset='o')
    fb.label('end')
    fb.end_try(guard)
    fb.op('Ret', ret=void)
    return fb.build()
