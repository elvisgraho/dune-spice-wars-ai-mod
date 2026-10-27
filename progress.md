# Current work

Behavior rules and thresholds: [AI-POLICY.md](docs/AI-POLICY.md). Implementation facts:
[REVERSING.md](docs/REVERSING.md). Earlier match evidence:
[frozen archive](docs/archive/progress-log-2026-10.md).

## Status

- Base-kill campaigns reach attack windows, coordinate members, and cast Defense Breaches. A main base has not
  been razed in validation; the best recorded result left Arrakeen at 86% HP. Increasing sustained base damage
  remains the priority.
- Rule splits passed byte-identical build checks before logging changes. The rule-size check passes; module
  ownership and verification commands are in README.
- Logging validation: 31,520 events over 20:07 game time, no game exceptions or rule failures, and 40 passing tool
  tests. Strict reader replay checks 8,211 core records with no invalid rows. Evidence:
  [runtime](validation/logging-feedback.json), [reader/export](validation/logging-robustness.json).
  Unchecked event kinds are inventoried; event loss is not measured.
- Focus-fire `focus` events are observed. Their effect on combat, the one-objective wave policy and the turret
  occupation guard remain unverified and need targeted checks. Do not infer success from event presence.

## Next match checks

Use `raze`, `mod match 20`. Pass: remove the row. Fail: retain one evidence-linked issue.

| Check | Pass when |
|---|---|
| One wave objective (`dob`) | A member's wave attacks one target per pass; no army walks at the base while its wave fights elsewhere; base damage improves |
| Field hysteresis | A field target is taken/dropped at most once per minute per member |
| Focus fire | Targets per faction/zone concentrate on 1-2 enemies per 10 s, enemy losses improve, no trap |
| Turret guard | Occupation completes while a field army stands beyond BC_GUARD_R, without abandoning the village |
| Defense Breaches | `opcast` at the base coincides with the attack; damage per second improves during its effect |
| Far members | `farstage` members capture/stage rather than walk alone from more than 500 away |

## Active validation

- Fixed in source: minor-raid defense respects live claims on orderless campaign armies; the base Supply Drop
  step-in respects the selected wave objective. Both compiled-bytecode regressions fail before and pass after;
  42 tool tests pass, `bcheck` reports zero issues. Follow-up: 55:08 game time, 73,324 fully parsed events, no
  game exceptions or rule failures. No `dkeep` case or assault window occurred; Altar was taken by Fremen first,
  so capture/raid behavior and base-damage improvement remain unverified. Evidence:
  [campaign-capture-ownership.json](validation/campaign-capture-ownership.json).
- Altar reproduction: `testbed on --scenario altar`, `match 14`, map seed 5705907. Same geography does not guarantee
  identical combat. Check `dkeep` while Harkonnen occupies Altar, capture completion, and idle defenders remaining usable.

## Open issues: campaign and fights

- [ ] O-waz: the director canceled Harkonnen's liberation at 48:20 after counting about 230k nearby renegade
  raiders that were not targeting Harkonnen (179k reach vs 324k opposition). Check whether neutral-raid threat is
  too conservative before changing shared queries; the follow-up archive is in the capture-ownership record.
- [ ] Base damage remains too low. Diagnose time under the guns, Siege mix, operations and supply before adding
  attack exceptions. Main-base damage mechanics are in REVERSING.
- [ ] Defense estimate fluctuates with fog, including a 455k -> 979k reading, reopening/closing attack windows.
  Evaluate smoothing the shared estimate.
- [ ] Starving wave armies leave for vanilla Resupply through hostile land. Verify whether the one-objective wave
  fix resolves this before changing `doomed` or drop policy.
- [ ] Command conflicts, militia target changes and distant melee targets:
  [INPUT-SPAM-TODO.md](docs/INPUT-SPAM-TODO.md). Stable-ID evidence identifies hero #7729 receiving Move and
  ArmyFight within 0.5 s six times; competing ownership is still a hypothesis.
- [ ] `doomed` can keep far armies fighting to death in a lost base fight. Decide whether the raze balance should
  override it.
- [ ] Consider nearer footholds for members already at the base, improving drop/heal access.
- [ ] Dormant order-Raze path (`BC_ALL_DIRECT=False`) and BC_GO_WIN: remove after direct raze demonstrates a base kill.

## Older unresolved issues

- [ ] Siege supply starvation in militia fights (militia isn't in the warzone balance; no siege arrival budget).
- [ ] Rally timeout commit sends a strung-out force; conceded village at a near-even 0.9-1.0.
- [ ] Rebels never killed / Harkonnen rebellions (the cause, water / stability, is never fixed).
- [ ] Liberates win rarely (1 of 24 in one match): captures shrink in Action, where the armies go isn't traced.
- [ ] Harkonnen (Meat grinder) burns its army: 38-54 deaths on missions, Manpower 5 / day.
- [ ] Turreted enemy villages kill far more than measured (cover priced by turret power); warzone vs order balance
  disagree in captures; no reinforcement of a running siege; raid relief underestimated; lone army fights on after
  its hunt ends; harvester hunts inside enemy land.
- [ ] Order balance spikes after the militia dies (enemy 0 -> 138.5M); `fight` me% counts expiring temporaries.
- [ ] Resupply removeUnits rhythm (vanilla, low); CP cap (Command Post, low).

## Coverage still needed

These are carried-forward edge cases, not a claim that none of the associated rules has ever run. Deliberately
trigger a case before changing it; the historical pass criteria are in the archive.

- Late-scenario rules: coalition pressure (BK_SPLIT, two-sided truces), joint attack, task board step 1 (shadow),
  urgent attrition, ETA clamp, Corrino Pyre, hero rebuild + air / drone / artillery styles, modded content.
- Economy: water by wind (`water-rank`), stall ban, goal smoothing, wonder steer, airfield first / travel, faction
  buildings, value model Manpower 12, slot reserve (`tresv`), weak water, Underworld HQ neutral reserve.
- Armies: worn picks, desert chase / trips, disengage stand-down / vs contests, sabotage timing, liberate reach,
  resupply loop, task claims / rally claims, stealth at our village, anti-air counter, busy block, supply block,
  siege memory, far launches after a failed ride, stuck worm plans, untargetable targets, concession reopen, capture
  guard, raid `behind`, Defense gate + doomed stay, forecast migration, rally reach, capture top-up (`drain` hold),
  Patrol `there`, walkable snap.

## Next work

- [ ] Refactor, remaining review steps (each needs one raze match, they change emitted layout): the three target
  pickers as one scan (the field picker's double walk merged); the raze loop as classify-then-dispatch; micro.py one
  wrapper per site; `build_retreat` (heal/retreat.py) as stage emitters; strike / route / opsbrain cleanups; then per-go
  records for the campaign state.
- [ ] Safe trap logging (TRAP_LOG crashed the game at match start; bisect which handler).
- [ ] Activate task-board ranking for raids/sieges after a shadow comparison match
  ([ARCHITECTURE-PLAN.md](docs/ARCHITECTURE-PLAN.md), `BOARD_LIVE = ('raid', 'siege')`). Task values are already built.
- [ ] Operation reactions and DLC coverage ([docs/OPERATIONS-IMPL.md](docs/OPERATIONS-IMPL.md)); verify remaining
  base-kill operation timing and loadout purchase failures before changing agent assignment.
- [ ] Veteran Militia / Border Defense research under pressure; Supply Drop weight for Vernius; force peace for a
  besieged main base; contact tension step 3; threat weighting (BUSY_W, ETA); strategic director; intel memory;
  peace gate part 2; en-route re-evaluation; objectives over chasing.
- [ ] Strategy candidates from expert play: [docs/strategy/CANDIDATES.md](docs/strategy/CANDIDATES.md).

## Ruled-out approaches and constraints

- Launch patched games through Steam. Direct `D4X.exe` runs can report JIT failures even for working builds.
- Keep `TRAP_LOG` off: trap-handler logging caused native exits. Use step probes and frozen source maps.
- Use `AIEntityGroup` for ArmyFight and live order scans instead of `Unit.aiOrder`. Read contest state from the
  structure's siege component. Smuggler HQs in hostile zones do not count as home.
- Temporary armies leaving lost fights are deliberate vanilla behavior and remain unchanged by user choice.
- Do not revive data-only storm avoidance or power-loss cancel constants that no code reads. Console `report`
  is a static audit; shipped AI logging is stripped; release quickStart is disabled.
- A main base permits only one faction's siege. The lead/supporter Raze-order design was replaced by direct
  commands; members muster on their own land because waiting in enemy land drains supply.
- The retreat latch does not resolve per-army role changes. Historical raw micro-call percentages cannot be
  compared directly with change-only observations.
- Older investigations found no Smuggler micro-None anomaly, unbounded map leak, harvester re-entry into a hot field,
  or missing special-village reach. Evidence stays in the frozen archive; do not reopen without new evidence.
