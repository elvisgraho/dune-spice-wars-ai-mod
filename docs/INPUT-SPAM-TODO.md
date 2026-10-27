# Command conflicts and input spam

Open work on commands that get re-issued or overridden. Policy: [AI-POLICY.md](AI-POLICY.md).
Micro implementation: `tools/rules/micro.py`; current checks: [progress.md](../progress.md).

## Current safeguards

| Area | Implemented behavior |
|---|---|
| Flee | `fskip` suppresses redundant Move sends |
| Attack | `askip` suppresses same-target resends; `astick` keeps a viable current target |
| Retreat | `rlatch` holds forced and vanilla retreat balances at or below RETREAT |
| Our moves | `ohold` keeps micro from immediately undoing a held move |
| Rally | Arrival hysteresis avoids Patrol create/Success loops |
| Direct raze | ArmySiege sends only to idle armies; busy armies use BC_DR_BUSY_T |
| Focus fire | `ffoc` shares a nearby target per faction and zone; `focus` rows are observed, combat benefit unverified |

## Read the right evidence

Use `dact` for command attempts. `micro` records state/target/point changes in `mode=changes`, not input counts.
A full-call audit requires `micro_repeats=true` in `testbed/ailog.json` and `testbed on`.
Use stable entity IDs for army attribution; old kind/position tracking can merge armies standing together.
Old full-stream percentages are not directly comparable with current change-only logs.

```powershell
ai-mod\mod.cmd log --events-jsonl --entity 7729 --event dact --strict
ai-mod\mod.cmd log --entity 7729 --around 06:59 --event dact --event micro
```

The logging validation match contains six Move/ArmyFight conflicts within 0.5 seconds for Harkonnen hero #7729,
from 06:59 to 12:38. This identifies the army, not the cause. Check command sources and fight context before
changing behavior. Source identity and coverage are in [logging-robustness.json](../validation/logging-robustness.json).

## Open work

| Priority | Question or candidate change | Required evidence |
|---|---|---|
| 1 | Can overlapping fights command the same army? Consider one owner per tick, with retreat precedence. | Trace stable army IDs and both fight contexts; distinguish intended Reposition from competing ownership. |
| 2 | Militia target switching bypasses same-target suppression. Consider target hysteresis across one village's militia. | `adbg` target IDs and `dact` switches; compare focus fire and enemy losses. |
| 3 | Melee armies chase ranged targets more than 120 away. Consider a nearest-enemy target at the Attack site. | Command target distance, target changes and fight outcome. |
| 4 | Flee can be reset repeatedly even when its Move is suppressed. Consider preserving `lastMicroChangeTime` for an unchanged Flee point. | Full micro audit and Flee stuck-exit behavior; retreat outcomes must not worsen. |
| 5 | Strike and vanilla micro may choose different targets, then restart together after `done`. | `strike` start/end and `dact` sources for one stable army ID. |
| 6 | Verify our Move holds during worm flee, siege positioning, desert steps, leash and Resupply guard. | Per-army Move/ArmyFight alternation and hold expiry; extend ownership only for a reproduced conflict. |
| 7 | Check repeated Siege Action sends and Waiting/Resupply cancel loops. | `dact` plus order IDs; prove a resend changes movement before adding suppression. |

Historical Attack/Flee role flips persisted after the warzone retreat latch. Do not treat that observation as
proof the latch failed: per-army roles and warzone retreat are different decisions.

Vanilla `AIUnits.unitMicroManagement`, `changeArmyMicro`, `$HScoring.enemies` and
`Entity.getFightingTarget` are the relevant code paths. Resolve by name; function IDs and source line numbers
from the original investigation are stale after file splits. Hook details remain in [REVERSING.md](REVERSING.md).
