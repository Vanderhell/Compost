# Native boundary

## KEEP IN PYTHON

- CLI parsing, presentation, compatibility commands, and experiment scripts.
- Experiment orchestration, population/world setup, and historical run modes.
- `NativePopulationBackend` orchestration of opaque native handles with
  explicit environment bites; it does not replace Python food allocation or
  world policy.
- Filesystem sandbox management: inbox discovery, FOOD copying, file reads and
  truncation, directory markers, JSON/telemetry persistence, and cleanup.
- Multiprocessing/worker process lifecycle, IPC, observer processes, and
  wall-clock termination.
- Human-readable diagnostics, audit logs, benchmark reporting, and analysis.
- The legacy `MathematicalOrganism` graph implementation and `ReplayOracle`.
- Python canonical snapshot/digest code used as the reference oracle.

Python owns environmental effects. It supplies bytes/nutrition, claims, corpse
energy, and territory metadata to the core and applies explicit requests after
the core returns.

## MOVE TO C CORE

The first C target is the lifecycle/sandbox behavioral core only:

- Fixed-width organism identity, lifecycle status, age, cursor, generation,
  parent/child relation, and reserve.
- Atoms, relations, composites, strengths, evidence, income, maintenance,
  members, and structural body mass.
- Activated receptors and activity ledger/counters.
- Gut FIFO and material-flow accounting.
- Bounded maintenance settlement, weakening, resorption, and deterministic
  weakest-member selection for explicit native transitions. The lifecycle
  endpoint owns the sandbox member policy; the legacy public `weaken_weakest`
  operation is only a bounded structure-level compatibility primitive and is
  not a replacement for Python `AutonomousCore.remove_weakest` (which also
  applies critical-bridge protection). Python `live_step` metabolic-progress
  scheduling remains host-owned until its event ordering is migrated and
  differentially proven.
- Pure biology rules: structural mass, costs, forgetting, maintenance budgets,
  reproduction eligibility, and conservation calculations.
- Consolidation, structural mutations, connected-component/bridge predicates,
  partition selection, division, child initialization, and death state.
- Pure territory path/state math and stable food address predicates.
- Metabolic progress/settled-step accounting through an explicit opaque
  context operation; lifecycle work triggered by due steps remains outside the
  native state machine until its ordering is migrated.
- A single deterministic step accepting an explicit environment view and
  returning state mutation plus explicit environment/action events.

The first core must not perform file I/O, inspect Python objects, consult a
clock, spawn threads, or make a scheduling decision based on hash iteration.

## DEFER / NOT YET COMPLETE

- Full Python ABI/FFI lifecycle integration until corpse, division, population,
  and sandbox-level gut snapshots match per step. The versioned opaque ABI now
  includes bounded external-gut enqueue/process operations, read-only material
  conservation validation, weakest-structure transition, and an atomic
  deterministic local-reproduction/component selection, `try_divide` and step-plus-division operations;
  native
  failures are not silently downgraded.
- Automatic metabolic lifecycle scheduling and the complete `live_step` tail
  (division/death orchestration) remain deferred; current action traces expose
  only the validated environment prefix.
- Native multiprocessing and any throughput-oriented parallel mode.
- Native physical FOOD storage, filesystem sandboxing, and telemetry.
- Porting the legacy graph learner before a compatibility decision and fixtures
  exist for that model.
- Large-scale allocator optimization, serialization optimization, and SIMD.
- Replacing Python experiment outputs or captured historical artifacts.

## DO NOT TOUCH

- Existing Python lifecycle semantics without a failing correctness test and a
  documented oracle update.
- Python tests, historical experiment evidence, and the replay oracle as part
  of the initial boundary work.
- Git author configuration or repository attribution.
- Biological terminology/claims: this remains a deterministic simulator, not a
  claim of biological realism.

## Proposed call boundary

Conceptually:

```text
Python environment view + ordered food/corpse inputs
                 -> C deterministic organism_step
C state delta + action/event list + behavioral snapshot
                 -> Python commits environment effects and telemetry
```

The C API should later use opaque handles or explicit buffers, not public C
struct layout exposed to Python. A versioned ABI and explicit status codes are
required. Native-requested failures must be visible; validation runs must never
silently fall back to Python.
