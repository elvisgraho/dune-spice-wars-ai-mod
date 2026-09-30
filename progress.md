# Progress

Open work and checks. What exists is described in README / docs; this file lists only what is left to do or verify.

## Working (in-game confirmed)
- Tooling (`mod.cmd`), baseline/backup, testbed start flow (O in menu, P in game)
- `ai-log` events + `mod log` (HEALTH line, orders, fights, marks, `--around`), `aw` scan
- `hunt` runs without game exceptions; `busy-siege` removes the getUnits `.siege` crash

## Verify in-game (built, offline-checked only)
- [ ] `retreat` rows: holds at own villages at raw 0.5-0.65, retreats on enemy land up to ~0.8; no retreat/re-engage oscillation
- [ ] `heal` rows: `stay` at own villages with hostiles near; `flee`/`avoid` only with overwhelming, close threats; Resupply targets = nearest own village otherwise
- [ ] `hunt`: contest starts (`anc` = a village) when an enemy besieges near us; no start/abort alternation (30 s gap); `drift` rare; enemy-land hunts only at ≥ ~1.9:1
- [ ] `Annex spacing` rows; no parallel sieges on villages < 100 apart; Annexation gauge not decaying from refusals
- [ ] Expanded events: no FLOOD warnings; ~6 `aw`/faction/game-minute
- [ ] Which boot file the launcher uses (DX vs GL)
- [ ] Supply budget: hunt `abort-supply` fires before armies drop below ~15% supply; no army at 0 supply in a hunt (Atreides chased 400 units north and hit 0; Smugglers starved to 0% / 5% HP in Harkonnen land). Joining armies need 1.25 × the budget at the target
- [ ] `retreat` rows `retreat by supply` (sf < 100): starving armies disengage and walk home; no retreat/re-engage loop (a Resupply army is not free)
- [ ] Contests: hunt starts with `tgt`/`anc` = a village when an enemy besieges a neutral/own village ≤ 500 from our land (Harkonnen on Tadwan next to Smugglers' Tsimbu was ignored for 3.5 min); `abort-objective` rows switch chases to it
- [ ] Own-land distance: no Smugglers hunt with small `sd` deep in enemy land (UWHeadquarters no longer count)
- [ ] Turret cover in hunts: `T` > 0 on starts/aborts near enemy villages / main bases; chases there only in contact with 3× (Smugglers hunted armies ~110 from Carthag several times); `abort-turret` rows. Calibrate TURRET_H from `T` vs army `pw` (a MissileBattery should read ~1 army)
- [ ] Turret-aware sizing: vanilla Annex/Pillage on a village next to another enemy village sends more armies (pick `sel`, est power) and loses less; attacks on isolated turret villages are not scared off (own turret silenced). *Unverified:* that turrets really stop during Raze too (silenced for every siege kind)
- [ ] Bunker pairs: vanilla picks Annex/Liberate targets within 130 of our villages more often (score × 1.3)
- [ ] Defensive posture: while one of our villages is besieged, `space` rows why `defend` replace new Annex/Pillage launches (Smugglers annexed Pel-nit and Grim-dad while Fremen took Sad-mur and Tab-dad); `abort-defend` on chases; a contest hunt on our village once free power ≥ ~1.15× (gather radius 900). Watch for a faction frozen by a hopeless siege
- [ ] Bunker: `bunker` rows redirect Annex to a lost village ≤ 200 from our main base; the redirected action actually starts (occupation cost / enemy-owned target accepted by tryArmyAction?)
- [ ] Hunt `engage` rows: hunts leave Regroup within ~3 s once the armies near the prey suffice (Atreides sat 32 s in Regroup 100 from two Harkonnen armies while one A_Elite fought alone); no hunt order stuck in Regroup (`Rg` last phase) with the prey in contact
- [ ] Hunt core: no `weak` abort whose `tgt` is far from the prey (a group member walking home under its main base's guns aborted a 2:1 hunt); pruned members don't make the target jump (order `tgt` x/y follows the prey)
- [ ] Third-party sizing: pick `pw` enemy power includes rival armies near neutral targets (Harkonnen Annex Fon-no read 3.4:1 against militia only, with 5-7 Atreides armies ~70 away); fewer Annex orders launched into rival blobs; watch for gauges stuck by `NotEnoughArmies`
- [ ] `disc` rows: lone Discovery trips into at-war armies refused (Harkonnen sent single armies to Ruins / black market in Atreides land next to their 5-army blob); normal trips still happen (Discovery orders per minute not ~0)

- [ ] `raid` rows + Military Pillage orders: a stack next to a weakly held enemy village pillages instead of walking home (Fremen 6 armies 35 from Od-lulah, one H_Trooper near, walked 500 home); raid armies end with supply ≥ budget home; no Atreides raids (can't pillage); no raid into an army blob (H vs M)

## Open issues (evidence in logs)
- [ ] Hunt orders cancelled right after start (`src <none>`, Waiting or Preparation, 0.04-1 s), sometimes several in a row. With units left and a live group, the only remaining vanilla path is a refused Shuttle path step (`checkOrderTerminations`, Invalid/BlockedBy; paths planned with `AIOrders.getShuttleCost`). Costs the faction the 30 s hunt gap (Atreides lost 30 s against two Harkonnen armies on its land). Log the ability result, or keep hunts walking
- [ ] Fremen Annex loop: 43 orders cancelled at +0 s with `InsufficientSupply` in 8 min (Mimsud/Zapo)
- [ ] Siege supply starvation: armies died at 0 supply 41 units from a supplying zone. Occupying (in occupation range) doesn't drain, so the loss is before occupation (walk, militia fight, contested siege) or outside occupation range; siege orders never check own supply. Design a §4 trigger (step into supply / rotate) before code; don't cancel near-complete captures (the captured village supplies)
- [ ] Repeated failed defense picks every 0.5 s for one own structure (x77-x101): vanilla `checkStructures` re-rolls the required ratio (1.25-3.4) each time and finds no pick (Smugglers Tab-dad: sel=0 for minutes). Our contest hunt on own villages now covers it; consider a fixed ratio for vanilla defense too
- [ ] Resupply order bursts (40-90/game-minute for one faction in some matches); includes `checkRegroupOrder` cancelling Resupply orders whose armies are held in a fight, then re-issued
- [ ] `mod log` "Enemy siege actions near us" reads the besiegers' `aiOrder` (often null): switch it to village siege state (`aimod_sieged`)
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
- Traced `checkPeacefulAnnexation` (~186/min) and `tryLaunchOperationFromOrder` (~109/min, always False): flood the log.
