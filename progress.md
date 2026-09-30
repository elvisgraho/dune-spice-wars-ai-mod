# Progress

Open work and checks. What exists is described in README / docs; this file lists only what is left to do or verify.

## Working (in-game confirmed)
- Tooling (`mod.cmd`), baseline/backup, testbed start flow (O in menu, P in game)
- `ai-log` events + `mod log` (HEALTH line, orders, fights, marks, `--around`), `aw` scan
- `hunt` runs without game exceptions; `busy-siege` removes the getUnits `.siege` crash

## Verify in-game (built, offline-checked only)

**Pruning rule (every match analysis):** check each row against that match's `mod log` / archived log. Pass (the rule fired and the criterion holds) → delete the row; the docs already describe the behavior. Fail → move it to Open issues with the evidence (time, factions, numbers). Not exercised → keep it and bump `n/a`; at 3, make the scenario trigger it (testbed/scenario.json) or delete the row. New rows only for rules built in the same session; one row per rule, one line each.

| Check | Pass when (per match) | n/a |
|---|---|---|
| `retreat` terrain | holds at own villages at raw 0.5-0.65, leaves enemy land up to ~0.8; no retreat/re-engage loop | 1 |
| `recall` | `retreat act recall` rows after a hunt `abort supply` while the stack is still in contact; the stack reaches our land with supply > 0; no recall of armies in a siege / hunt (Military order); `stranded` rows (dm > 0) only for armies whose supply < 0.28 × distance home, and they win those fights (else stranded stacks die fighting: revisit) | 0 |
| `heal` | `stay` at own villages with hostiles near; `flee`/`avoid` only for overwhelming close threats; otherwise nearest own village | 0 |
| hunt start/abort | no start/abort alternation (30 s gap); `drift` rare; enemy-land hunts only at ≥ ~1.9:1; `engage` within ~3 s of enough armies near the prey; no hunt stuck in `Rg` with the prey in contact; no `weak` abort with `tgt` far from the prey | 0 |
| hunt `chase` / retreat `pursuit` | `abort chase` rows only for a prey pulling away unhurt (not while it loses power or we close in, never on contests); `retreat act pursuit` rows end micro chases after an order ended within ~15 s (no follow under turrets like Smugglers Larram → Grimpo), and right after a `chase` abort, not 15 s later; no pursuit retreat out of a fight the enemy is losing or on our own zone; no new chase on a given-up runner within 90 s; after a chase abort next to a pillageable village, a `raid start` there once the armies stop fighting | 0 |
| hunt contests / objective | `anc` = a village when an enemy besieges ≤ 500 from our land; `abort objective` switches chases to it | 1 |
| hunt turret cover | `T` > 0 near enemy villages / main bases; chases there only in contact at 3×; `abort turret` rows; TURRET_H: a MissileBattery ≈ 1 army `pw` | 1 |
| hunt own-land distance | no Smugglers hunt with small `sd` deep in enemy land | 1 |
| defensive posture | while our village is besieged: `space` why `defend`, `abort defend` on chases, a contest once free power ≥ ~1.15×; no faction frozen by a hopeless siege | 1 |
| `annex-spacing` / retry | no parallel sieges < 100 apart; no `InsufficientSupply` cancel loop on one target; Annexation gauge not decaying or stuck | 0 |
| turret / third-party sizing | Annex next to an enemy village or a rival blob sends more armies (pick `sel`, `pw` en) and loses less; isolated turret villages still attacked; no gauge stuck on `NotEnoughArmies` | 1 |
| `sengage` gathering | `near` = armies within 100 of the target; stacks arrive together (no 1-by-1 losses like Har-Al'sud); no stack pulled away from its target to a straggler | 0 |
| `raid` | an idle stack at home (Smugglers short of Authority) gets `raid start` rows on neutral / at-war villages within 400, `n` < all its armies (sizing), `ax` names a village never raided that match; no `refuse home` while no hostile army is nearer our land than the target (hh 0); `abort defend` only with our structure besieged ≤ 500 away, `abort home` when an enemy stack walks toward our land mid-raid; no abort at `pr` ≥ 50; no start/abort loop on one village; raid armies get home with supply; no Atreides raids; *unverified*: calling the target-score wrapper from raid may add `space retry` rows | 0 |
| `strand` | idle armies on hostile land get a `strand` Patrol within ~10 s; never a harvester (`F_Harvester*` rows seen before the fix); no row repeating every scan for one army (F_Trooper 59 from Tuo-rekh before the AT_HOME_R skip) | 0 |
| `memory` | `mem` rows when our harvester is attacked; `hfield` rows then steer the next harvester to another field (Fremen sent 2 harvesters to the same field at (840,1610) next to Kulur, both killed); *unverified:* an attacked deployed harvester packs up and moves (aw: F_Harvester → F_Harvester_Mobile after `hfield`) | 0 |
| `undeploy` / `ability-gate` | `undeploy` rows (ok, nm ≥ 1) for an installed F_Special_2 on hostile land once its fight ends; the turret then reaches occupation range (aw `oc` set) or walks home; no F_Special_2 at sup 0 with `ls` true; no undeploy row repeating every 20 s for one army (install/undeploy loop) | 0 |
| AI control trace | `!AI OFF` lines appear when you Tab to a faction / vote in the Landsraad, with `src` naming the path (Atreides lost its AI 11:40-13:24 while Harkonnen took Aishras next to it: log gap only, no trace yet), and end when P is pressed | 0 |
| threat movers | `raid refuse` / hunt H don't count a blob milling 300+ away; *unverified:* `currentPath` set while walking | 1 |
| launcher boot file | which of hlboot / hlbootdx the game loads (DX vs GL) | 1 |

## Open issues (evidence in logs)
- [ ] Raid sizing: raids now take the nearest armies until 3 × (militia + threat + cover) / terrain, from 400 (Harkonnen at Aynkhelon, ~320, couldn't join at 250). Judge with the `raid` row: if raids that arrive together still lose armies to militia, add a `siege-engage`-style gather check. `fpw` en counts every army of the owner via vanilla zone weighting: not a local ratio
- [ ] Hunt orders cancelled right after start (`src <none>`, Waiting or Preparation, 0.04-1 s), sometimes several in a row. With units left and a live group, the only remaining vanilla path is a refused Shuttle path step (`checkOrderTerminations`, Invalid/BlockedBy; paths planned with `AIOrders.getShuttleCost`). Costs the faction the 30 s hunt gap (Atreides lost 30 s against two Harkonnen armies on its land). Log the ability result, or keep hunts walking
- [ ] Siege supply starvation: armies died at 0 supply 41 units from a supplying zone. One cause found: an installed Fremen turret (F_Special_2, speed 0) never moves again (Fremen Annex Alwahad: turret at d35 starved while 3 armies stepped in to d11 and occupied; `undeploy` built, verify above). Still open for all armies: the militia fight itself drains (Alwahad: 5 armies 85 → 0-1 supply in ~50 s at d≈30, occupation only after the militia died). Occupying (in occupation range) doesn't drain, so the loss is before occupation (walk, militia fight, contested siege) or outside occupation range; siege orders never check own supply. Design a §4 trigger (step into supply / rotate) before code; don't cancel near-complete captures (the captured village supplies)
- [ ] Undersized neutral Annex (vanilla required 1.0): 2 armies per attempt (est 1.28-2.62, 2 of 4-5 available), the militia fight takes ~50 s, the armies drain supply the whole time (flags L/H: not in occupation range while the militia lives) and one army can be focused down (Fremen F_Sneak hp 100→13→dead on Ashdak, est 1.87). The `bunker` redirect then re-picks the same village with the same 2-army sizing (Fremen: 3 Ashdak attempts, 18 redirects, none captured). `siege-join` built (verify above). Still open: a fight retreat exemption for a capture in Action whose militia is nearly dead (policy §4 "nearly done capture"); an idle army that becomes free after a launch can't join it (no vanilla add-to-order; hand-rolling one means copying order bookkeeping: unit list, aiOrder link, reservations, attack steps, Regroup arrival count)
- [ ] Discovery ph1 cancel loop: Fremen re-issued Discovery → CrashedHarvester ~every 1-2 s for 26 s (n=1, ph 1, Cancel src `<none>`), later Success. Probably the refused Shuttle step (same path as hunt cancels). Related design ask: no lone Discovery trip for an army near a fight/siege of ours (it should stay for the conflict). At launch `siege-join` already takes Discovery armies (prio 0 < siege prio); a trip that starts after the launch is not covered
- [ ] Repeated failed defense picks every 0.5 s for one own structure (x37-x120): vanilla `checkStructures` re-rolls the required ratio each time from data `AI_PowerBalance_VillageDefense_Min/Max` (Insane 1.0-3.5; Smugglers Aliffir sel=0 for minutes). Our contest hunt on own villages covers it; a data patch (Min = Max) would fix the vanilla side
- [ ] Resupply order bursts (40-90/game-minute): ~45% are `n=0` rows = vanilla fight retreat re-issuing an empty Resupply every tick while the retreat condition holds (harmless); the rest includes `checkRegroupOrder` cancelling Resupply orders whose armies are held in a fight, then re-issued
- [ ] Resupply Success loop: one Fremen army at (437,1393) got Resupply → Odval, ended Success in phase 1 and was re-issued every ~0.5 s for minutes (vanilla `checkUnits`: life/supply < 0.9 but already "at" the structure?). Harmless but floods the log; check the army's life/supply and its distance to Odval
- [ ] `mod log` "Enemy siege actions near us" reads the besiegers' `aiOrder` (often null): switch it to village siege state (`aimod_sieged`)
- [ ] `mod log --around` ignores `--faction`; `aw` doesn't list neutral raiders (owner null), so neutral hunts can only be read from `hunt` rows
- [ ] Fremen Annexation gauge stuck near 100 with `NoStructuresWithSufficientWind` (wind filter, `valueCache[1185]`)

## Next (policy-ordered)
- [ ] **Intel memory (policy §3a):** remembered enemy armies with decaying confidence, `perceived(F)`; `aimod_threat` from memory. Storage: added-global maps (`rules.common._global_map`)
- [ ] **Peace gate (policy §3b):** wrap `Call2 tradeRequestReceived` in `AIController.callActionFunction`; refuse `ImproveRelations` from F while an order against F is in Engage/Action at ratio ≥ keep, or while we're in charge (`tradeManager.refuseTrade`)
- [ ] **En-route re-evaluation:** orders in Preparation/Regroup/Engage re-check hostile power near the army and cancel (vanilla never does: the live balance only triggers emergency abilities). Needed for sieges started before a rival army arrived; neutral targets still use required 1.0 (consider a margin)
- [ ] **Objectives over chasing:** annex weak enemy villages next to our strong free armies (`tryArmyAction` bypassing the aggressiveness gate); pillage is covered by `raid`
- [ ] Unit-level events inside `unitMicroManagement` (target choice, reposition)
- [ ] Trade decisions: who offers peace to whom (traces in `testbed/ailog.json`)
- [ ] Worm: hostile army on sand in a high-worm zone → `MDecoyThumper` (empty `aiWeights`); drop if too hard
- [ ] Baseline: 3+ testbed runs recorded in `validation/`; ability usage (`ability.props.ai`)

## Tried / ruled out
- `Main.quickStart` / `-conf`: dead in release (`Const.flags.quickStart` false). `newgame` from the menu: in-game console only.
- `admin` password: unnecessary (1-byte `isAdmin` patch). F4 `aiDebug`: not registered.
- crashlink CLI with several `-c` flags runs only the last; use `mod dec a b c`.
- Console `report`: static attribute audit, no match data.
- Shipped AI logging: stripped (7 warnings); decisions need injected logging.
- `mod dec $AIMilitary.getSiegeableVillages`: decompiler hangs; use `--asm`.
- Decompiling all appended functions at once takes > 10 min; decompile one by id.
- Plain army target for `ArmyFight`: vanilla `checkEngageOrder` throws every tick; use an `AIEntityGroup`.
- Hunt priority "largest threat" without distance: chased far groups; score by distance + objective.
- Contest detection from the prey's `Army.aiOrder`: null on many AI besiegers (and on humans); read the village's siege state.
- Hunt supply abort only out of contact at < 50%: armies chasing in contact starved to 0; use the distance-based budget.
- Distance to "our structures" over all `faction.structures`: Smugglers' UWHeadquarters in enemy villages made deep chases look local; use our land only.
- Flat "any safe structure wins" heal penalty: sent armies across the map to the base; use a finite detour.
- Data-only fix for the stuck turret (FSpecialLeave `ai.state` = Move/Resupply): fires only in Regroup/Engage/Resupply phases, never in the siege Action where it is stuck, and the order's `noMoveAbilities` would still block its Move.
- Traced `checkPeacefulAnnexation` (~186/min) and `tryLaunchOperationFromOrder` (~109/min, always False): flood the log.
