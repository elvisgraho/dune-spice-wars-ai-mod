# Worm rides: current design and checks

Offensive rides extend reach and help stop captures. Escape rides, thumper economy, return rides and reactions to
worms in transit remain out of scope. The implementation is in `tools/rules/ride.py`; binding behavior is in
[AI-POLICY.md](AI-POLICY.md), and vanilla mechanics are in [REVERSING.md](REVERSING.md).

## Implemented behavior

- A ride belongs to an existing order. Its sizing, supply and threat gates still decide whether that order goes.
  The ride gate replaces vanilla's size/priority choice for eligible sieges, contest hunts and Defense orders of
  factions with thumper access. Chases and neutral-village Pillage walk.
- A worthwhile trip needs a free thumper after claims. The last free thumper is reserved for a far trip, contest
  or Defense; shorter trips require spare stock. `RIDE_MIN`, `RIDE_FAR` and `RIDE_SPARE` live in
  `tools/rules/thresholds.py`.
- `wres` claims a thumper when the plan is chosen. Claims expire, release after a granted ride, or end on fallback.
  `wdone` prevents another request after success. Riders left on a Worm step walk the rest after the pickup timeout
  or on reaching the landing area.
- Repeated refusals past `RIDE_STALL_T` turn Worm steps into Walk steps in place. Failed plans use the order's walk
  completion path; refused plans also impose a faction cooldown. Orders stuck past Regroup have a walk fallback.
- A free ride extends target reach. Supply estimates count the walking legs; raid returns still walk. Contest
  arrival estimates use the same ride budget.
- Enemy riders count at their last sighting through shared threat memory. No rule tracks a worm's live position
  or predicts its destination. The `aw` scan still omits transported armies.

Vanilla has one active ride per faction and sweeps up nearby friendly ground armies. Thumpers start capped at three,
with no regeneration before 5k hegemony. Spend them on reach or arrival value.

The owning order judges destination threat; no separate landing gate or moved landing point is used.
Moving a landing point can leave valid sand. Constants and timeout values in source are authoritative.

## Verification

Rides and fallbacks have run in game. Further edge cases remain in [progress.md](../progress.md);
implementation is not proof that every branch was exercised.

| Evidence | Check |
|---|---|
| `wplan`, `tstk` | Choice respects stock, claims, distance and order kind |
| `wreq`, `wstall` | Refused or stuck orders walk without duplicate thumper spending or permanent Regroup |
| `wride` | Granted ride releases its claim; landed armies continue their order |
| Order timeline | Far launches after failed rides still have a viable walking supply budget |
| Shared threat queries | A seen enemy boarding transport remains remembered without revealing its landing point |
| Contest result | Ride ETA makes arrival useful; ridden attacks do not lose more than comparable walked attacks |

Use `mod log --around MM:SS --event wplan --event wride --event wstall` and inspect the affected order ID.
