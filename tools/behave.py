"""AI rules built on the enemy army awareness scan (testbed patch `aware-ai`, installed with `ai-log`): wiring only.
The code lives in tools/rules/: common (thresholds, bytecode helpers), world (shared queries), heal, hunt, siege, raid.
Thresholds and rationale: docs/AI-POLICY.md §4; mechanics and hook points: docs/REVERSING.md "AI rules".

Shared queries (appended functions): aimod_pw, aimod_threat(fac, p, r) (at-war power within r + movers arriving within
HORIZON s; diplomacy read live), aimod_threat_now (FLEE_ETA horizon), aimod_own(fac, p, r, exclude), aimod_terrain(fac,
zone), aimod_land (distance to our land), aimod_supok / aimod_short (supply budget for the way back), aimod_sieged,
aimod_free, aimod_unsafe.
Rules: retreat-terrain (fight retreat balance x terrain x supply), safe-heal (healing-structure key penalties), hunt
(attack exposed at-war armies near our land, contest sieges near it; judged at the group's core, early Engage),
annex-spacing (no parallel sieges on adjacent structures), turret/third-party-aware vanilla sizing, discovery-gate (no
lone world-event trips into superior at-war armies), raid (opportunistic pillage next to our armies), busy-siege
(vanilla null fix in the getUnits busy filter). Each logs its decisions: retreat, heal, hunt, space, bunker, disc, raid.
Entry and exit conditions of a rule measure the same quantity at the same place and are set apart (hysteresis), so a
plan can't start and stop on alternate checks."""
from rules.common import *  # noqa: F401,F403
from rules.world import *  # noqa: F401,F403
from rules.heal import *  # noqa: F401,F403
from rules.hunt import *  # noqa: F401,F403
from rules.siege import *  # noqa: F401,F403
from rules.raid import *  # noqa: F401,F403


def install(cx, helpers, new_ids):
    """Build the queries, the redirects and the per-faction tick. Returns (report, tick findex): tick(mil, dt) runs
    hunt, then raid (a new hunt claims its armies first)."""
    busy = fix_busy_siege(cx)
    pw = build_pw(cx)
    threat = build_threat(cx, pw)
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
    new_ids.update({pw, threat, own, free, unsafe, land, terrain, threat_now, supok, short, sieged, cover, silence,
                    defend})
    report = safe_heal(cx, unsafe, new_ids, threat_now, own, pw, threat, helpers)
    report.update(build_retreat(cx, terrain, new_ids, helpers, pw, short))
    report.update(busy)
    spacing = build_spacing(cx, helpers, defend)
    new_ids.add(spacing)
    report['annex-spacing'] = 1
    threat_stats = build_threat(cx, pw, stats=True)
    new_ids.add(threat_stats)
    report.update(build_turret_stats(cx, cover, silence, threat_stats, new_ids))
    report['discovery-gate'] = build_discovery(cx, helpers, threat, pw, terrain, new_ids)
    report.update(build_scoring(cx, new_ids))
    hunt = build_hunt(cx, helpers, pw, free, threat, land, terrain, supok, short, sieged, cover, defend)
    raidable = build_free(cx, pw, RAID_LIFE, 0, resupply_ok=True)
    raidsup = build_raidsup(cx)
    militia = build_militia(cx)
    raid = build_raid(cx, helpers, pw, raidable, threat, land, terrain, raidsup, cover, defend, militia)
    tick = build_chain(cx, [hunt, raid])
    new_ids.update({hunt, raidable, raidsup, militia, raid, tick})
    report['raid'] = 1
    return report, tick
