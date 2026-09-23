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

`NativePopulationBackend.replay_action_traces` extends that boundary to a
deterministic host-built population epoch: each trace is preflighted before
execution, organisms are scheduled by numeric ID, action order inside a trace
is preserved, and explicit division children remain registered for later
epochs. A native `ALIVE` to `DEAD` transition returns the one-shot
`store_corpse` request; the host remains responsible for corpse persistence,
territory release, and observer events. `NativePopulationBackend.take_corpse`
transfers the dead snapshot and closes/removes the native handle; it rejects
live organisms without mutation.

`NativeSandboxReplay` is the reusable host-built epoch adapter around this
primitive. It owns the native population handles, invokes the Python oracle's
`live_step(..., action_trace=...)`, registers explicit division children,
returns deterministic epoch snapshots, and transfers dead handles as corpse
snapshots. It does not change the default Python runtime or silently fall back
when native execution fails. For a division trace it first invokes the native
weakest-member local-reproduction transaction. If that policy reports no
viable component, the adapter invokes the native boundary-partition policy
(`try_divide`) corresponding to the Python oracle's historical
`_divide_locally` branch and labels the result `global_partition_policy`;
the host does not supply the selected child atom set. After each epoch it
independently checks the native population ledger, every Python organism
ledger, and the Python world-level ownership-transfer equation.
All traces for the epoch are materialized and preflighted before any native
prefix, reproduction policy, or suffix is committed; invalid later actions
therefore cannot leave an earlier organism partially advanced.

The same one-shot request is returned by `NativeBackend.replay_actions` when a
single-organism lifecycle trace crosses from alive to dead; a subsequent dead
no-op carries no repeated request. `NativeBackend.take_corpse` provides the
matching ownership transfer for that single handle and rejects live or already
closed handles.

`AutonomousOrganism.live_step(..., action_trace=...)` can now emit the same
immutable action forms for replay. The trace is optional and observational;
the normal Python step remains unchanged. The metabolic-progress action
settles only bounded counter accounting. A due epoch may then emit an
empty-input `LIFECYCLE_STEP`, which uses the explicit lifecycle-step ABI
endpoint including activity-debt settlement and covers the validated
consolidation/maintenance/age checkpoint. A validated `DIVISION` action can
then replay the parent partition and return a transient child snapshot;
this action-trace path is observational and Python still owns child
registration, identity naming, corpse handling, and filesystem state. The
separate `NativePopulationBackend.apply_actions` path transfers ownership of
an explicit child handle and registers it by numeric ID, with collision
preflight. Death remains outside the complete sandbox action sequence.

The regression fixture for a multi-bite FOOD stream asserts this distinction:
the trace contains the external-gut environment prefix, bounded metabolic
accounting, validated lifecycle checkpoint, and (where child atom IDs fit the
ABI domain) the parent/child division transaction while the Python organism
still owns registration and the death tail. A
native replay must therefore not be treated as full `AutonomousOrganism`
equivalence until that tail has its own transaction and first-divergence
comparison.

## Remaining transition work

The host-built `live_step` action-plan unit is now available through
`NativeSandboxReplay`. The plan records one deterministic environment decision
(food bite, queued gut work, corpse energy, or idle/maintenance work), then
invokes the corresponding native slice. Filesystem FOOD claim/read and the
physical-food lifecycle checkpoint remain Python-owned; each supplied action
is compared after execution against the Python oracle in the differential
campaign.

Automatic metabolic scheduling remains a separate transaction. Both native
reproduction policies and their deterministic selection are now exercised by
the adapter, while full event ordering remains separate until that action-plan
comparison covers it. A native
`live_step` function must not be introduced before this ordering is frozen.

## Acceptance rule

The Python sandbox remains the oracle. A native integration checkpoint is valid
only when the canonical snapshot matches after every supplied action, including
the first failure or rejected input. End-state-only agreement is insufficient.
