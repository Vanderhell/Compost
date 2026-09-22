# Compost native migration architecture audit

## Scope and method

This audit covers the Python package, tests, experiment runners, tools, README,
packaging, and CI configuration present at the Prompt 1 migration boundary. The
repository contains two related deterministic models:

1. The legacy sequence organism: `MathematicalOrganism` in `organism.py`, with
   `LatticeGraph`, candidates, representation planning, energy scoring, and
   adaptive graph rules.
2. The current lifecycle/sandbox organism: `MathematicalLifePopulation`,
   `AutonomousOrganism`, `AutonomousCore`, `SandboxRuntime`, food adapters,
   material flow, territory, maintenance, and division.

The second model is the appropriate first native target because it contains the
requested organism/lifecycle/metabolism/material-flow behavior. The first model
is still working Python behavior and remains an oracle/historical compatibility
surface; it must not be silently replaced by the native core.

## Current architecture

### Behavioral core

- `lifecycle.py` owns the reference population scheduler, organism identity and
  lineage, atoms, relations, composites, reserve, body mass, cursor, lifecycle
  state, digestion, maintenance, division, death, and food allocation.
- `autonomous_core.py` factors digestion, activity accounting, consolidation,
  maintenance, weakening, graph connectivity, and reproduction helpers used by
  the sandbox organism.
- `sandbox_runtime.py` adds gut chunks, material-flow accounting, weakness
  indexes, metabolic epochs, corpse interaction, territory-mediated food access,
  and the `AutonomousOrganism.live_step` transition.
- `biology_rules.py` contains pure calculations and rule predicates, including
  structural mass, activity costs, forgetting, lazy metabolism, maintenance
  weakening, and reproduction assessment.

### Environment and orchestration

- `food.py` and `destructive_ingest.py` own file-backed FOOD claims, navigation,
  byte/block accounting, and physical consumption.
- `territory.py` owns pure territory predicates and stable address mapping.
- `sandbox_runtime.py`, `public_sandbox.py`, and `parallel_runtime.py` own
  filesystem layout, worker processes, request queues, marker files, corpse
  storage, and observation.
- `cli.py`, `compost.py`, and tools own user interaction and experiments.

### Legacy graph model

- `model.py`, `representation.py`, `rules.py`, `energy.py`, `organism.py`, and
  `oracle.py` form a separate deterministic graph-learning path. Its mutation
  selection uses explicit sorted keys and deep-copy trial graphs. It is pure
  Python and must remain available.

## Decision-state inventory

The following state can affect a future behavioral transition and therefore
belongs in a native state model or in an explicit environment input:

- Lifecycle identity: organism ID, parent ID, generation, birth position,
  cursor, status, age, child counter, and death age.
- Body: atom/relation/composite keys; kind; strength; maintenance; evidence;
  income rate; members; last metabolic epoch; body mass; reserve; activated
  receptor set; and cache validity only insofar as it is a derived consistency
  value.
- Activity/metabolism: `ActivityLedger`, counters, metabolic debt, energy spent,
  settlement count, metabolic progress/epoch, and maintenance deficit state.
- Material flow: gut queue order and each chunk's mass/origin/payload/nutrition,
  plus every `MaterialFlow` total. The queue is behavioral because processing is
  capacity-limited and FIFO.
- Weakness and scheduling indexes: their source state is behavioral; heaps and
  adjacency maps are derived indexes and must be rebuildable deterministically.
  Any heap tie-break key used to select a structure is part of the contract.
- Territory: path, organism tree ID, local birth counter, and alive flag.
- Environment input: ordered logical food claims, byte/nutrition values, source
  identity, block ownership, corpse locations and remaining energy, and the
  explicit order in which organisms are stepped.
- For the legacy graph path: nodes, transitions, indexes, candidates and all
  decayed counters, including timestamps used by decay.

Observations such as timing, worker number, filesystem operation counts, peak
memory, trace records, and human-readable audit notes do not influence biology
and are telemetry only. They must not be included in a behavioral native state
unless a test is explicitly checking an invariant.

## Operation classification

Pure or nearly pure operations include structural mass, activity cost,
forgetting, maintenance budget, reproduction assessment, territory predicates,
food address hashing, and legacy representation/energy calculations. They may
be ported first after their domains and float behavior are specified.

Mutating operations include digest, receptor activation, structure creation and
strengthening, consolidation, reserve withdrawal, weakening/resorption, gut
processing, corpse consumption, territory division, reproduction/partition,
death, and cursor/navigation advancement. These require transaction-oriented
native APIs and per-step differential tests.

Filesystem-dependent operations include source discovery, copying/truncating
FOOD, directory creation, marker files, JSON snapshots, corpse persistence,
and file reads. They remain outside the first C core. Process scheduling affects
worker servicing, telemetry timing, and queue delivery in the multiprocessing
runtime; the single-organism core must not depend on it.

## Primary hazards

- Python integers are arbitrary precision. C widths must be selected explicitly
  and bounds must reject or define values before arithmetic.
- Python floats are binary IEEE values but Python expressions, `sum`, `min`,
  residual allocation, `repr`, and exponentiation define observable details.
  Native comparisons need a documented representation and operation order.
- Dict insertion order is used in places, while other paths explicitly sort.
  No native hash-table iteration may drive a decision.
- Sets are used for graph connectivity and activated receptors. Decisions are
  safe only where the code sorts or where only membership matters.
- Heap entries intentionally contain tie-break fields such as strength,
  evidence, income, kind, textual key, and serial. Reproduce this ordering.
- Exceptions are control/error behavior in Python. C needs status codes and
  must leave outputs/state unchanged on failed public operations.
- `deepcopy` is used for legacy trial mutation; object identity is not a
  semantic value, but aliasing during a C transaction can change semantics.
- Recursive graph validation exists in the legacy decomposition DAG. The native
  core should use bounded iterative traversal or documented limits.
- `perf_counter`, `monotonic`, `sleep`, worker queues, and filesystem
  availability are non-behavioral runtime concerns and must not enter the
  deterministic state.

## Initial conclusion

The first native unit should be a single `AutonomousOrganism` transition over
an explicit environment view, with no filesystem calls, no Python callbacks,
and an exportable behavioral snapshot. `MathematicalLifePopulation` remains
the most direct executable reference for differential tests; the sandbox host
adapts physical FOOD and commits emitted environment requests.
