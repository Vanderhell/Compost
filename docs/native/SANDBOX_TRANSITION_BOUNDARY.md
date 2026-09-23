# Sandbox transition boundary

The legacy `AutonomousOrganism.live_step` remains the behavioral reference for
the filesystem sandbox. It is intentionally not replaced by a native call as a
single operation: one call currently combines environment discovery, durable
food claims, gut processing, corpse lookup, maintenance settlement, metabolic
scheduling, division, and death.

## Safe native slices

The following operations already have an explicit native boundary and can be
called from Python with all environmental inputs supplied by the host:

| Slice | Python owner | Native input | Native output |
| --- | --- | --- | --- |
| External/resorbed gut FIFO | `AutonomousOrganism.process_gut` | bounded payload, nutrition, capacity | processed mass, flow counters, state |
| Corpse energy credit | `SandboxRuntime.take_corpse_energy` | validated energy amount | reserve delta or error |
| Structural partition | `_commit_skeleton_partition` | selected atom IDs, child ID, birth cost | parent/child states and transfer trace |
| Deterministic lifecycle step | `MathematicalLifePopulation._cycle_one` | explicit food/nutrition view | state, events, digest |

`NativeAction`/`NativeActionKind` in `backend.py` now provide the first
host-side action-plan adapter for these calls. It validates payload lengths,
finite nutrition, capacities, and energy before touching a native handle. The
adapter does not select a food source or infer a corpse; it only executes a
decision already made by the Python host. `PROCESS_GUT` represents the
backpressure branch where an existing FIFO is processed without claiming a new
FOOD range.

These slices do not perform filesystem I/O, inspect Python object identity, or
depend on worker scheduling.

## Host-owned operations

The Python host must continue to own:

- source discovery, copying, block claims, reads, and destructive commits;
- corpse lookup, storage, territory occupancy, and marker files;
- organism registration and population scheduling;
- telemetry, observer callbacks, and human-readable diagnostics.

The host supplies the result of those operations to the native core as explicit
inputs. Native code must not reopen paths, enumerate a Python dictionary, or
call back into the runtime to decide a biological action.

`NativePopulationBackend.apply_actions` applies a supplied subset of these
actions in ascending numeric organism-ID order. Unknown IDs and invalid action
objects are rejected before any handle changes; omitted IDs are explicit
no-ops for that epoch.

`NativeBackend.replay_actions` preflights a complete single-organism trace and
then replays it in list order. This is the differential-test entry point for
Python `live_step` action traces.

`AutonomousOrganism.live_step(..., action_trace=...)` can now emit the same
immutable action forms for replay. The trace is optional and observational;
the normal Python step remains unchanged. The metabolic-progress action
settles only bounded counter accounting. A due epoch may then emit an
empty-input `LIFECYCLE_STEP`, which covers the validated
consolidation/maintenance/age checkpoint. A validated `DIVISION` action can
then replay the parent partition and return a transient child snapshot;
Python still owns child registration, identity naming, corpse handling, and
filesystem state. Death remains outside the complete native action sequence.

The regression fixture for a multi-bite FOOD stream asserts this distinction:
the trace contains the external-gut environment prefix, bounded metabolic
accounting, validated lifecycle checkpoint, and (where child atom IDs fit the
ABI domain) the parent/child division transaction while the Python organism
still owns registration and the death tail. A
native replay must therefore not be treated as full `AutonomousOrganism`
equivalence until that tail has its own transaction and first-divergence
comparison.

## Remaining transition work

The next safe integration unit is a host-built `live_step` action plan. The
plan must record one deterministic environment decision (food bite, queued gut
work, corpse energy, or idle/maintenance work), then invoke the corresponding
native slice. The initial external-gut and corpse-energy action forms are now
available, and filesystem FOOD claim/read plus one physical-food lifecycle
checkpoint are differentially tested;
full live-step construction and event ordering remain pending. Each
action must be compared after execution against the Python oracle.

Automatic metabolic scheduling and division remain separate transactions until
that action-plan comparison covers their event ordering. A native
`live_step` function must not be introduced before this ordering is frozen.

## Acceptance rule

The Python sandbox remains the oracle. A native integration checkpoint is valid
only when the canonical snapshot matches after every supplied action, including
the first failure or rejected input. End-state-only agreement is insufficient.
