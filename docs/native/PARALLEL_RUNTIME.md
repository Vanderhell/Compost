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

The existing Python parallel runtime remains unchanged and is still the
reference for historical experiments.
