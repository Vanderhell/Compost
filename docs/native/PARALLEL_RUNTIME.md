# Native parallel runtime decision

## Decision

`DEFERRED`.

The native core currently has bounded deterministic checkpoints and selected
partition transactions, but it does not yet expose the complete logical step
including population food allocation, consolidation, external gut payloads,
death/corpse handling, and lifecycle policy. Designing worker ownership or
epoch scheduling before those semantics are frozen would risk encoding an
accidental scheduling rule.

## Required prerequisites

Before implementing a native parallel runtime, the project must have:

1. a complete single-organism native step with explicit environment inputs and
   emitted actions;
2. a Python/C per-step differential campaign with first-divergence reporting;
3. deterministic food allocation and territory ownership inputs;
4. independent mass and energy conservation checks across child creation and
   death;
5. a measured single-thread native baseline.

The intended design remains ownership partitioning with deterministic epochs,
worker-local organism state, shared immutable environment metadata, and explicit
queues for migration/actions. A throughput mode may be added only if it is
clearly separated from the reproducible deterministic mode.

## Required execution modes

Any future native runtime must expose two explicit modes rather than allowing
thread scheduling to become an accidental biological rule:

### `DETERMINISTIC`

- fixed worker ownership for each epoch;
- ascending organism-ID action ordering within an ownership partition;
- immutable environment metadata for the epoch;
- bounded, explicitly ordered migration/action queues committed at an epoch
  barrier;
- reproducible food ownership, territory ownership, mass, energy, and
  parent/child results for equal seed/configuration/input.

The acceptance gate is Python/C first-divergence comparison after every logical
epoch, repeated with 1, 2, 4, 8, and 16 workers where available. OS thread
interleaving must not affect the behavioral snapshot.

### `THROUGHPUT`

This mode may use work stealing or relaxed queue timing only when it is clearly
labelled non-reproducible. It must still preserve no-duplicate FOOD claims,
territory ownership, mass/energy conservation, valid child registration, and
no lost organism state. It must never be presented as equivalent to
`DETERMINISTIC` and must report its scheduling mode in telemetry.

The implementation should prefer worker-local ownership and message passing
over a global simulation lock or one mutex per organism structure. Scaling must
be reported at 1, 2, 4, 8, and 16 workers with efficiency, not only raw
steps/sec.

The existing Python parallel runtime remains unchanged and is still the
reference for historical experiments.
