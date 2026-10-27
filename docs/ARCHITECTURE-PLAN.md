# Architecture plan: shared decisions

Binding for new behavior work together with [AI-POLICY.md](AI-POLICY.md).
Use the shared pieces below instead of adding a private world measure or ownership lock.

| Shared mechanism | Current state |
|---|---|
| `rules/forecast.py` | Used by planned-fight sizing/keep decisions, free Annex, operation fight gates and emergency Supply Drop |
| `rules/tasks.py` | Claims and priorities for order picks and rally gathering |
| `rules/value.py` | Task values and `tval` records; independent of live assignment |
| `rules/board.py` | Candidate ranking and would-yield logs; `BOARD_LIVE=()` keeps all kinds in shadow mode |
| `rules/econ.py` | Economy value model built |
| `mod log --score` | Outcome and task-board scorecard built |

Forecast sizing shares `common._fc_theirs`. Safety/posture queries and vanilla's live retreat balance retain their
own roles; they are not alternative planned-fight forecasts. Live task-board activation needs a comparison match.

## Why

Two causes of rule complexity:
1. **Every rule measures the world its own way.** `react`, `threat`, `hthreat`, `threat_arrive`, `own`, `cover`, each with
   its own radius, discounts and ratio, so two rules judge one fight differently (the rally commits, the hopeless test
   concedes; the raid launches, its abort says weak) and a new exception reconciles them.
2. **Several rules claim the same army** (rally, vanilla Defense, raid, release, hunt, picks); lock maps (`rallied`,
   `keepord`, `take-keep`, `rlock`, pick-life filters) exist to stop the tug-of-war.

## Step 1: one battle forecast

`aimod_forecast(fac, place, T, attack, units) -> ratio` (units: an order's armies; null: all ours) (maps `fco` / `fct` faction -> our / their side of the last call, for logs):
- **Their side:** hostile armies that can be at `place` within T (fog-aware `aimod_threat` with radius T x CONTEST_SPD:
  standing within it or moving towards `place`), + their turret cover at `place` (`aimod_cover`), + the village's
  militia / raiders (`aimod_militia`).
- **Our side:** our non-harvester armies with `aimod_eta(army, place)` <= T (walking or via our airfields), an army on
  a Military mission only if already within RALLY_HERE (it is in that fight), + our turret cover (mode defend: full;
  attack: x OWN_COVER_ATK), x terrain at `place`.
- **ratio** = ours / theirs (theirs 0: a large number).
- **T** is the time that matters: a capture's remaining time (`_cap_rem`, measured rates only), a raid's walk, a
  hunt's catch-up time. One entry ratio (ENTER) and one abort ratio (ABORT) for every decision.

For remaining migrations, replace one caller at a time and verify a match. Keep safety/posture reads distinct
from planned-fight sizing; do not replace the live retreat measure merely to eliminate a helper name.

## Step 2: one task market for armies

Each AI tick: candidate tasks (defend D, contest V, annex / raid V, chase G, heal, hold) with value (what's at stake:
village value, army value), forecast at their T and cost (time, supply, risk). Armies are assigned greedily to the
best-value tasks until each task's forecast clears ENTER; every army belongs to exactly one task. Vanilla still
executes orders; we decide who goes where. Replaces the lock maps and most "don't take this army" exceptions.

Build order (each stage a match, none breaks the rules still on the old path):
1. **Claim registry** (`rules/tasks.py`, built): maps `tkp` / `tkt` army -> priority / time, lapsing after CLAIM_TTL 8 s;
   `aimod_claim(a, prio)` takes a free / lapsed / lower claim; `aimod_held(a, prio)`; the refresher re-claims our
   orders' armies every 2 s by order kind, never lowering a live higher claim. Priorities are the `P_*` constants in
   `rules/thresholds.py`, including separate main-base, raze and rally priorities.
   Every rule that moves or orders an army claims first: rally gather, hunt group, raid pick, siege-join adds,
   release, leash, rsguard, strand and the vanilla pick wrappers.
   `keepord` and `rallied` are replaced. `rlock` remains a post-retreat cooldown; `take-keep` remains a share limit,
   not an ownership lock. Do not delete either merely because claims exist.
2. **Value per task** (`rules/value.py`, built; changes no decision yet): one scale, the economy model's
   Solari-equivalent at current resource values. `aimod_sval(fac, s)` = VAL_DAYS 20 x (its buildings' daily output
   x quirk factor x value - upkeep, >= 0, + VAL_VILLAGE_DAY 20), x VAL_ENEMY 2 for another faction's structure, a main
   base VAL_MB; `aimod_aval(a)` = power x VAL_PW_K 11 / 1000 (recruit cost: H_Trooper 480 at 43.6k). Decision record `tval` per
   Military / Defense order at first sight (claim refresher): V, A, forecast with its armies (TVAL_FC_T 60 s); the
   scorecard shows the medians per kind. Risk for stage 3 = max(0, ENTER - forecast) / ENTER x A.
   Values also count a spice field (VAL_SPICE_DAY 60 / day) and a special region (aiWeight x VAL_AIW_DAY 1 / day);
   a Defense record values the defended structure (its order target is the attacker group).
3. **Assignment pass:** first slice built: the capture guard (rules/hunt/ `hgrd`): a capture of ours the
   forecast says we lose becomes a task free armies are sent to (as a hunt of the threat, since an order can't take armies
   after addOrder: per-army paths / shuttle steps are built there), not a rule of its own. Next slices: rank a faction's
   open tasks (contests, guards, sieges, raids) by value / (time + risk) in one place before each rule picks armies.
   Original plan: every TASK_T s, sort candidate tasks by value / (time + risk), claim the cheapest armies that
   make the forecast clear ENTER; tasks that can't are dropped this pass (no partial launches). Existing rules
   become task generators and executors (they stop picking armies themselves).

### Stage 3b design: the task board (rank before launch)

Goal: one place answers "is this launch the best use of these armies right now?". Rules keep finding targets,
sizing and executing; only the *launch* decision is shared. No central assigner rewrite, no order surgery.

**Today's ad-hoc ranking it replaces (one by one, each a match):** raid `annexwait` (raids wait for a failed Annex),
raid `dfn` (no raid while a Defense holds armies), hunt "stake" (no armies to a pillage while we defend a capture),
the contest-over-chase score offset (CONTEST_W bands), `dkeep` (a pillage doesn't pull a Military order's armies),
the fixed claim priorities by kind for *launches* (claims stay for running orders).

**Board** (`rules/board.py`): map `tbd` faction -> ObjectMap target -> entry {k kind, V, A need, fc, T, sc, t seen,
ax / ay the anchor}. An entry lives BOARD_T 12 s unless refreshed. Producers post the candidate they evaluated,
whether or not they launch it, with numbers they already compute:
- hunt start pass: its best contest / guard / chase (V: the contested village's `aimod_sval`, the guarded capture's,
  the prey's `aimod_aval`; fc: its start forecast; T: the nearest free army's `aimod_eta`);
- raid launch pass: its final candidate (V: `aimod_sval`; fc: the launch forecast; T: the walk);
- vanilla siege launches (join.py pick wrapper, which already sees target, armies and the forecast side);
- vanilla Defense (heal/picks.py `dgate`, which already has the forecast with the picked armies);
- rally: its danger D (V: `aimod_sval(D)`; fc: the pick forecast; T: RALLY_FC_T);
- running orders are *not* candidates: commitment (user: finish what was started) is kept by never preempting.

**Score** (Solari-eq per second, one formula for every kind): p = clamp((fc - ABORT) / (ENTER - ABORT), 0, 1) (the
chance the fight is won as our ratios already define it); gain = V x p - A x (1 - p) x LOSS_K (A = the value of the
armies the task needs); sc = gain / (T + T0) (T0 30 s: no division blow-up for tasks next door). A task with gain
<= 0 is posted (visible in the log) but never ranks above anything.

**Gate** (`aimod_rank(fac, k, tgt, armies) -> bool`, one call before a launch): the launch yields when another open
entry Y (not this target, seen within BOARD_T) has sc_Y >= RANK_HYST 1.3 x sc_X and needs some of the same armies
(one of X's armies within Y's join radius of Y's anchor). Yielding launches nothing this pass; the armies stay free
for Y's own rule (its next pass, <= START s). Log `tyield` (f, k, tgt, sc, by k / tgt / sc).

**Not conflicting by construction:**
- only launches are gated; running orders, retreats, heals, drains and splits keep their own rules;
- hysteresis RANK_HYST plus expiry: a better task must be clearly better and still there; the same pair can't
  alternate (the yielding side launches nothing, the winner's own rule decides on its own gates);
- YIELD_MAX 3 yields of one target to the same winner within YIELD_WIN 120 s while the winner never launched: the
  board drops the winner's entry for YIELD_WIN (a winner that never acts can't block forever; log `tstale`);
- main-base defense, rally commits and the base-kill campaign never yield (posted for visibility only);
- fails open: any error / missing entry = launch as today.

**Implemented in shadow mode:** `rules/board.py` `aimod_board` (`BOARD_LIVE=()`); producers: hunt start (after its forecast gate; kind contest / guard / chase, target the village / guarded capture / prey), raid (after `fc`), siege-join (vanilla's final siege pick, forecast JOIN_FC_T), heal/picks.py `dgate` (a Defense that goes), rally (its danger D, post only). Logs `tpost`, `tyield` (live false), `tstale`; scorecard section 'task board (shadow)'. Also built: YIELD_WIN 120 s (a stale count starts over), the per-kind live switch BOARD_LIVE (a tuple of kinds; empty = all shadow), the yield branches at every launch point (hunt: no start; raid: refuse why board; siege-join: empty pick; dgate: no Defense this pass), base-kill leader tasks never yield. Strat press needs no producer of its own: its targets launch through raid / vanilla sieges. Step 2 is then `BOARD_LIVE = ('raid', 'siege')`.

**Build order (each a match, shadow first):**
1. board + producers + gate in *shadow* mode: the gate logs `tyield` would-yield rows but returns true. Scorecard:
   would-yields per kind pair, and the outcomes of launches that would have yielded (task records `tval`) vs the rest;
2. gate on for raids and vanilla sieges (lowest stakes); delete raid `annexwait` / `dfn` once the board covers them;
3. gate on for hunt chases; delete the hunt "stake" rule and CONTEST_W bands (contests rank by V);
4. vanilla Defense joins (replaces part of `dgate`'s role: a hopeless defense yields to a winnable one elsewhere).
Done when the listed ad-hoc rankings are gone and the scorecard shows fewer launches below fc 1 with no drop in
captures won.

## Step 3: one economy value model

Each resource gets a value from its scarcity (goals and stock, smoothed: `goal-smooth`); a building's score =
production x quirk factor x resource value - upkeep valued the same way, + defense / travel terms (front, remote
villages). A resource in surplus is worth ~0: the water / plascrete caps, intel bonus, demolition gate and stall logic
mostly fall out of it. Independent of steps 1-2 (building scores only).

## Step 4: tune, don't add

One decision record per task (forecast at start vs outcome) -> a per-match scorecard in `mod log` (losses per task
type, wasted walks, captures won / lost). Misbehavior then shows as a mis-tuned ratio, not a new rule.
