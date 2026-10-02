"""AI rules built on the enemy army awareness scan (testbed patch `aware-ai`, installed with `ai-log`): wiring only.
The code lives in tools/rules/: common (thresholds, bytecode helpers), world (shared queries), heal, hunt, siege, raid, strat, strand (+ patrol gate), memory, deploy, peace (+ treaty scope, force peace), build (turret steering), uhq (Underworld HQ cap, placement, extensions), army (army size: CP overflow, Manpower pick gate).
Thresholds and rationale: docs/AI-POLICY.md §4; mechanics and hook points: docs/REVERSING.md "AI rules".

Shared queries (appended functions): aimod_pw, aimod_threat(fac, p, r) (at-war power + neutral raiders targeting fac
within r, + movers heading there and arriving within HORIZON s; diplomacy read live), aimod_threat_now (FLEE_ETA
horizon), aimod_neutral (other neutral raiders), aimod_own(fac, p, r, exclude), aimod_terrain(fac,
zone), aimod_land (distance to our land), aimod_supok / aimod_short (supply budget for the way back), aimod_sieged,
aimod_free, aimod_unsafe, aimod_react (raid: + free at-war armies within REACT_R), aimod_hthreat (hunt: around the prey's faction; its rivals
skipped, its allies only if they arrive before the kill).
Rules: retreat-terrain (fight retreat balance x terrain x supply), safe-heal (healing-structure key penalties), hunt
(attack exposed at-war armies near our land, contest sieges near it, then neutral raiders; judged at the group's
core, early Engage),
annex-spacing (no parallel sieges on adjacent structures), turret/third-party-aware vanilla sizing, discovery-gate (no
lone world-event trips into superior at-war armies), siege-join (neutral targets need 1.25; the nearest idle armies
join a siege launch until 3x the defense), siege-engage (our siege orders leave Regroup once the armies near the
target suffice), strat (director: posture per faction, presses weak enemy villages next to us), raid (pillage with idle armies), strand (idle armies on hostile land walk home), undeploy (an
installed Fremen turret starving on hostile land gets mobile again), ability-gate (no emergency order abilities
without enemy power), memory (zone danger with cooldown; harvester field choice),
busy-siege
(vanilla null fix in the getUnits busy filter). Each logs its decisions: retreat, heal, hunt, space, bunker, disc, join, sengage, raid.
Entry and exit conditions of a rule measure the same quantity at the same place and are set apart (hysteresis), so a
plan can't start and stop on alternate checks."""
from rules.common import *  # noqa: F401,F403
from rules.world import *  # noqa: F401,F403
from rules.heal import *  # noqa: F401,F403
from rules.hunt import *  # noqa: F401,F403
from rules.siege import *  # noqa: F401,F403
from rules.raid import *  # noqa: F401,F403
from rules.strat import *  # noqa: F401,F403
from rules.strand import *  # noqa: F401,F403
from rules.memory import *  # noqa: F401,F403
from rules.deploy import *  # noqa: F401,F403
from rules.peace import *  # noqa: F401,F403
from rules.worm import *  # noqa: F401,F403
from rules.desert import *  # noqa: F401,F403
from rules.stage import *  # noqa: F401,F403
from rules.gather import *  # noqa: F401,F403
from rules.rally import *  # noqa: F401,F403
from rules.spos import *  # noqa: F401,F403
from rules.tension import *  # noqa: F401,F403
from rules.build import *  # noqa: F401,F403
from rules.uhq import *  # noqa: F401,F403
from rules.sdiag import *  # noqa: F401,F403
from rules.release import *  # noqa: F401,F403
from rules.dmz import *  # noqa: F401,F403
from rules.claim import *  # noqa: F401,F403
from rules.strike import *  # noqa: F401,F403
from rules.sweep import *  # noqa: F401,F403
from rules.army import *  # noqa: F401,F403
from rules.orders import *  # noqa: F401,F403


def install(cx, helpers, new_ids):
    """Rule builds with logging trap handlers (rules.common.make_trap_hook); the hook is cleared after, so the next
    boot file (other function ids) and inject's own wrappers never get it."""
    FB.trap_hook = make_trap_hook(helpers) if TRAP_LOG else None
    CRUMBS.clear()
    try:
        return _install(cx, helpers, new_ids)
    finally:
        FB.trap_hook = None
        import json
        from pathlib import Path
        import os
        out = Path(__file__).resolve().parents[1] / 'work' / 'crumbs.json'
        # `rfail` at -> source line (tools/aireport.py). Both boot files build the same table, in parallel processes
        # (mod.patch_boots): write a private temp file and swap it in; a swap blocked by the other writer is fine
        tmp = out.with_name(f'crumbs.{os.getpid()}.tmp')
        tmp.write_text(json.dumps(CRUMBS), encoding='utf-8')
        try:
            os.replace(tmp, out)
        except OSError:
            tmp.unlink(missing_ok=True)


def _install(cx, helpers, new_ids):
    """Build the queries, the redirects and the per-faction tick. Returns (report, tick findex): tick(mil, dt) runs
    memory (record danger events first), strat (posture / press), hunt, raid, siege-engage, undeploy, then strand (a new hunt / raid claims its armies
    before idle ones are sent home)."""
    busy = fix_busy_siege(cx)
    pw = build_pw(cx)
    threat = build_threat(cx, pw)
    neutral = build_neutral(cx, pw)
    own = build_own(cx, pw)
    free = build_free(cx, pw, min_supply=0)  # supply: the hunt's trip budget (absolute), not a share
    terrain = build_terrain(cx)
    # heal / retreat / strand safety: full threat, no busy / outside discounts (an army rests there)
    hsafe = build_threat(cx, pw, discount=False)
    threat_now = build_threat(cx, pw, FLEE_ETA, discount=False)
    unsafe = build_unsafe(cx, hsafe, own, pw, terrain)
    land = build_land(cx)
    supok = build_supok(cx)
    short = build_short(cx, land, supok)
    helpers['short'] = short  # vanilla Defense picks: absolute supply test (rules/heal.py pick-life)
    sieged = build_sieged(cx)
    cover = build_cover(cx, helpers)
    new_ids.add(helpers['cover1'])
    silence = build_silence(cx)
    defend = build_defend(cx, sieged, helpers, threat, neutral, own, cover, terrain)
    new_ids.update({pw, threat, hsafe, neutral, own, free, unsafe, land, terrain, threat_now, supok, short, sieged, cover, silence,
                    defend})
    report = safe_heal(cx, unsafe, new_ids, threat_now, own, pw, hsafe, helpers)
    mission = build_mission(cx)
    new_ids.add(mission)
    report.update(build_retreat(cx, terrain, new_ids, helpers, pw, short, mission, land))
    report.update(busy)
    helpers['ddclean'] = build_ddclean(cx)  # Fremen ring test: raid / pillage-press exclusion
    helpers['ddhold'] = build_ddclean(cx, strict=True)  # ... strict: Annex hold, launch-gate tries
    new_ids.update({helpers['ddclean'], helpers['ddhold']})
    home = build_home(cx, pw, land)
    homeown = build_home(cx, pw, land, own=True)
    spacing = build_spacing(cx, helpers, defend, land, home, homeown)
    new_ids.add(spacing)
    report['annex-spacing'] = 1
    threat_stats = build_threat(cx, pw, stats=True)
    new_ids.add(threat_stats)
    report.update(build_turret_stats(cx, cover, silence, threat_stats, new_ids))
    report['discovery-gate'] = build_discovery(cx, helpers, threat, pw, terrain, land, supok, new_ids)
    threat_far = build_threat(cx, pw, DISC_HORIZON)
    discabort = build_disc_abort(cx, helpers, pw, threat_far, terrain)
    militia = build_militia(cx)
    report.update(build_join(cx, helpers, supok, land, pw, threat, cover, militia, terrain, new_ids, neutral))
    helpers['tension'] = build_tension(cx)  # contact tension query (rules/tension.py): scoring, hunt, strat
    new_ids.add(helpers['tension'])
    helpers['dmzv'] = build_dmzv(cx)  # DMZ village test (rules/dmz.py): scoring, raid, strat
    new_ids.add(helpers['dmzv'])
    react = build_threat(cx, pw, reach=REACT_R)
    helpers['fclaim'] = build_fclaim(cx, own, react)  # free Annex gate (rules/claim.py): scoring
    new_ids.add(helpers['fclaim'])
    report.update(build_scoring(cx, new_ids, helpers))
    hthreat = build_threat(cx, pw, prey=True)
    ttick = build_tension_tick(cx, helpers, threat)
    new_ids.add(ttick)
    hunt = build_hunt(cx, helpers, pw, free, hthreat, land, terrain, supok, short, sieged, cover, defend, neutral,
                      react)
    raidable = build_free(cx, pw, RAID_LIFE, 0, resupply_ok=True)
    raidsup = build_raidsup(cx)
    relunits = build_relunits(cx, pw)  # rules/release.py: who leaves an occupation under way (release, raid split)
    new_ids.add(relunits)
    raid = build_raid(cx, helpers, pw, raidable, react, land, terrain, raidsup, cover, defend, militia, threat, free,
                      home, homeown, helpers['scores'], neutral, relunits)
    fpow = build_fpow(cx, pw)
    threat_in = build_threat(cx, pw, 0)  # strat keep: armies within r only (r = what arrives before our capture ends)
    new_ids.add(threat_in)
    strat = build_strat(cx, helpers, pw, fpow, raidable, react, land, terrain, cover, defend, militia, home,
                        short, neutral, threat, threat_in)
    report.update(strat_levers(cx, new_ids))
    dmz = build_dmz(cx, helpers, fpow, defend)  # rules/dmz.py: border counts, truce break
    report.update(build_peace_gate(cx, helpers, defend, new_ids))
    report.update(build_treaty_scope(cx, helpers, new_ids))
    # Underworld HQs (rules/uhq.py): cap, placement, extension scores (under turret-steer on the same scoring call)
    uhqval, uhqgain = build_uhq_value(cx), build_uhq_best_gain(cx)
    new_ids.update({uhqval, uhqgain})
    report.update(build_uhq_cap(cx, helpers, new_ids))
    report.update(build_uhq_place(cx, helpers, uhqgain, new_ids))
    uhqx = build_uhq_ext(cx, helpers, uhqval, new_ids)
    report['uhq-ext'] = 1
    spf = build_spice_first(cx, helpers, new_ids, uhqx)  # Refinery first on a spice village (rules/build.py)
    report['spice-first'] = 1
    report.update(build_turret_steer(cx, helpers, threat, cover, new_ids, inner=spf))
    sengage = build_siege_engage(cx, helpers, pw, threat, cover, militia, terrain, neutral)
    idle = build_free(cx, pw, 0, 0, patrol_ok=False)
    helpers['wormheld'] = build_wormheld(cx)  # worm-flee hold: out of vanilla's Resupply / mission picks
    helpers['wormonly'] = build_wormheld(cx, rally=False)  # ... worm part only: march skips (strike.py, _skip_striking)
    new_ids.update({helpers['wormheld'], helpers['wormonly']})
    report.update(pick_life(cx, helpers, idle, new_ids))
    report.update(no_regen_heal(cx, helpers, new_ids))
    report.update(build_cp_overflow(cx, helpers, new_ids))  # rules/army.py: CP overflow disbands temporaries first
    report.update(build_mp_gate(cx, helpers, new_ids))  # ... unit picks ignore the Manpower goals
    report.update(build_cp_need(cx, helpers, new_ids))  # ... CP building scored when the army is capped
    report.update(build_cp_defense(cx, helpers, new_ids))  # ... no all-in defense because CP is full
    report.update(build_term_probe(cx, helpers, new_ids))  # rules/orders.py (before order-keep, which redirects the closure's removeUnits): logs why an order dies at once (refused Shuttle step)
    report.update(build_order_keep(cx, helpers, new_ids))  # rules/orders.py: one dead unit doesn't scrap a siege before Action
    strand = build_strand(cx, helpers, idle, unsafe)
    report.update(build_patrol_gate(cx, helpers, hsafe, own, pw, new_ids))
    undeploy = build_undeploy(cx, helpers)
    report.update(build_ability_gate(cx, new_ids))
    danger = build_danger(cx)
    memory = build_memory(cx, helpers, danger, threat, own)
    report.update(harvest_fields(cx, danger, helpers, new_ids))
    report.update(harvest_flee(cx, danger, threat, helpers, new_ids))
    wormflee = build_worm_flee(cx, helpers)
    striking = build_striking(cx)  # en-route strike state (rules/strike.py): read by dstep / stage / gather / spos
    helpers['striking'] = striking
    report.update(strike_skip(cx, new_ids, striking, helpers['wormonly']))
    strike = build_strike(cx, helpers, pw, threat, cover, striking)
    new_ids.update({striking, strike})
    dstep = build_desert_step(cx, helpers)
    stage = build_stage(cx, helpers)
    gather = build_gather(cx, helpers)
    # rally: active threat at D and rally-point safety count movers only when they arrive there (not border shuffles)
    threat_arrive = build_threat(cx, pw, arrive=True)
    rally = build_rally(cx, helpers, pw, react, threat_arrive, terrain, cover, mission)
    fpeace = build_force_peace(cx, helpers)
    spos = build_spos(cx, helpers, cover)
    report.update(build_keep_capture(cx, helpers, new_ids))
    report.update(gather_busy(cx, new_ids))
    sact = build_sact(cx, helpers, pw, militia)  # diagnostics only (rules/sdiag.py)
    release = build_release(cx, helpers, relunits, threat, neutral, cover)  # rules/release.py
    sweep = sweep_stub(cx)  # the map sweep: swapped for the real one at the end (every map exists by then)
    new_ids.add(sweep)
    # next Annex choices kept from raid and vanilla's Pillage gauge (rules/raid.py; before raid, which reads them)
    akeep = build_annex_keep(cx, helpers, helpers['scores'])
    new_ids.add(akeep)
    tick = build_chain(cx, [memory, wormflee, ttick, dmz, strat, hunt, akeep, raid, rally, fpeace, sengage, strike, stage, gather, spos, dstep, discabort, undeploy, strand, release, sact, sweep])
    new_ids.update({dmz, sact, release, hthreat, hunt, raidable, raidsup, militia, react, home, homeown, raid, fpow, strat, sengage, threat_far, discabort, idle, strand, undeploy, danger, wormflee, dstep, stage, gather, rally, threat_arrive, fpeace, spos,
                    memory, tick})
    report['strand'] = 1
    report['worm-flee'] = 1
    report['desert-step'] = 1
    report['stage'] = 1
    report.update(log_worm_kill(cx, helpers, new_ids))
    report.update(build_wind_fallback(cx, helpers, new_ids))  # last: also redirects our own rules' calls
    report['undeploy'] = 1
    report['raid'] = 1
    report['strat'] = 1
    report.update(install_sweep(cx, helpers, new_ids, tick, sweep))  # last: sees every added map
    return report, tick
