"""AI rules built on the enemy army awareness scan (testbed patch `aware-ai`, installed with `ai-log`): wiring only.
The code lives in tools/rules/: common (thresholds, bytecode helpers), world (shared queries), heal, hunt, siege, raid, strat, strand, memory, deploy.
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


def install(cx, helpers, new_ids):
    """Build the queries, the redirects and the per-faction tick. Returns (report, tick findex): tick(mil, dt) runs
    memory (record danger events first), strat (posture / press), hunt, raid, siege-engage, undeploy, then strand (a new hunt / raid claims its armies
    before idle ones are sent home)."""
    busy = fix_busy_siege(cx)
    pw = build_pw(cx)
    threat = build_threat(cx, pw)
    neutral = build_neutral(cx, pw)
    own = build_own(cx, pw)
    free = build_free(cx, pw)
    terrain = build_terrain(cx)
    threat_now = build_threat(cx, pw, FLEE_ETA)
    unsafe = build_unsafe(cx, threat, own, pw, terrain)
    land = build_land(cx)
    supok = build_supok(cx)
    short = build_short(cx, land, supok)
    sieged = build_sieged(cx)
    cover = build_cover(cx)
    silence = build_silence(cx)
    defend = build_defend(cx, sieged)
    new_ids.update({pw, threat, neutral, own, free, unsafe, land, terrain, threat_now, supok, short, sieged, cover, silence,
                    defend})
    report = safe_heal(cx, unsafe, new_ids, threat_now, own, pw, threat, helpers)
    mission = build_mission(cx)
    new_ids.add(mission)
    report.update(build_retreat(cx, terrain, new_ids, helpers, pw, short, mission, land))
    report.update(busy)
    spacing = build_spacing(cx, helpers, defend)
    new_ids.add(spacing)
    report['annex-spacing'] = 1
    threat_stats = build_threat(cx, pw, stats=True)
    new_ids.add(threat_stats)
    report.update(build_turret_stats(cx, cover, silence, threat_stats, new_ids))
    report['discovery-gate'] = build_discovery(cx, helpers, threat, pw, terrain, new_ids)
    militia = build_militia(cx)
    report.update(build_join(cx, helpers, supok, land, pw, threat, cover, militia, terrain, new_ids))
    report.update(build_scoring(cx, new_ids, helpers))
    hthreat = build_threat(cx, pw, prey=True)
    hunt = build_hunt(cx, helpers, pw, free, hthreat, land, terrain, supok, short, sieged, cover, defend, neutral)
    raidable = build_free(cx, pw, RAID_LIFE, 0, resupply_ok=True)
    raidsup = build_raidsup(cx)
    react = build_threat(cx, pw, reach=REACT_R)
    home = build_home(cx, pw, land)
    homeown = build_home(cx, pw, land, own=True)
    raid = build_raid(cx, helpers, pw, raidable, react, land, terrain, raidsup, cover, defend, militia, threat, free,
                      home, homeown, helpers['scores'])
    fpow = build_fpow(cx, pw)
    strat = build_strat(cx, helpers, pw, fpow, raidable, react, land, terrain, cover, defend, militia, home)
    report.update(strat_levers(cx, new_ids))
    sengage = build_siege_engage(cx, helpers, pw, threat, cover, militia, terrain)
    idle = build_free(cx, pw, 0, 0, patrol_ok=False)
    strand = build_strand(cx, helpers, idle, unsafe)
    undeploy = build_undeploy(cx, helpers)
    report.update(build_ability_gate(cx, new_ids))
    danger = build_danger(cx)
    memory = build_memory(cx, helpers)
    report.update(harvest_fields(cx, danger, helpers, new_ids))
    tick = build_chain(cx, [memory, strat, hunt, raid, sengage, undeploy, strand])
    new_ids.update({hthreat, hunt, raidable, raidsup, militia, react, home, homeown, raid, fpow, strat, sengage, idle, strand, undeploy, danger,
                    memory, tick})
    report['strand'] = 1
    report['undeploy'] = 1
    report['raid'] = 1
    report['strat'] = 1
    return report, tick
