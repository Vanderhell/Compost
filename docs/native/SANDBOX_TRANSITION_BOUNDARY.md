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

## Remaining transition work

The next safe integration unit is a host-built `live_step` action plan. The
plan must record one deterministic environment decision (food bite, queued gut
work, corpse energy, or idle/maintenance work), then invoke the corresponding
native slice. It must be compared after each action against the Python oracle.

Automatic metabolic scheduling and division remain separate transactions until
that action-plan comparison covers their event ordering. A native
`live_step` function must not be introduced before this ordering is frozen.

## Acceptance rule

The Python sandbox remains the oracle. A native integration checkpoint is valid
only when the canonical snapshot matches after every supplied action, including
the first failure or rejected input. End-state-only agreement is insufficient.
