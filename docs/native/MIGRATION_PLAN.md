# Native migration plan

This plan is intentionally incremental. Python remains the semantic authority
until a migrated unit has differential evidence.

## Phase 0 — freeze the reference

Add a canonical, immutable Python behavioral export and stable digest for the
lifecycle population/organism and, separately, the legacy graph organism. Sort
all maps/sets, encode floats explicitly, omit telemetry, and add compact replay
fixtures. Record the first divergent field in comparison helpers.

## Phase 1 — native foundation

Create `native/` as an ISO C17 subsystem with fixed-width types, explicit status
codes, no global mutable simulation state, strict warnings, sanitizer options,
centralized allocation policy, and init/destroy/snapshot scaffolding. This phase
must not change Python behavior.

## Phase 2 — pure rules and accounting

Port and differentially test, in small groups:

1. structural mass and bounded integer arithmetic;
2. activity ledger and cost settlement;
3. forgetting, lazy metabolism, maintenance weakening budget;
4. material-flow accounting and territory predicates;
5. reproduction eligibility and other pure lifecycle predicates.

Each unit gets domain/overflow/float/error documentation, boundary tests, and a
migration status of `NOT_STARTED`, `PORTING`, `DIFFERENTIAL_PASS`,
`INTEGRATED`, or `BLOCKED`.

## Phase 3 — state and single-organism step

Port authoritative organism state, FIFO gut, structural mutation, maintenance,
weakness selection, metabolism, lifecycle transitions, and explicit action/event
outputs. Inputs are supplied environment views; no file I/O or Python callbacks.
Compare snapshots after every step against `MathematicalLifePopulation` or the
equivalent sandbox reference path, locating the first divergent field.

## Phase 4 — conservation-critical partitioning

Port reproduction/division only after the preceding state path passes. Preserve
cross-split relation/composite behavior and transfer semantics. Independently
verify structural mass, gut, expelled material, parent/child reserve, and all
explicit transformations; no unexplained creation or loss is acceptable.

## Phase 5 — ABI integration

Expose a versioned, narrow ABI through opaque handles or explicit state buffers.
Add Python backend selection while retaining the reference backend. Explicit
native failures fail clearly; no validation fallback. Run the entire existing
suite against Python and a dedicated native acceptance/differential suite.

## Phase 6 — measure before optimizing

Benchmark direct C, C through the Python ABI, and Python using realistic
metabolism, structure, division, and population workloads. Attribute time to
core, FFI, serialization, filesystem, and IPC. Optimize only measured
bottlenecks.

## Phase 7 — parallel runtime decision

Only if the benchmark justifies it, design ownership-partitioned native workers
with deterministic epochs/messages. Keep the Python parallel runtime. Provide
separate deterministic and throughput modes if reproducibility cannot be
guaranteed under parallel scheduling.

## Do-not-cross gates

- Do not port filesystem orchestration with the organism rules.
- Do not remove or rewrite the Python oracle.
- Do not accept only end-state equivalence.
- Do not change biological rules for C convenience.
- Do not claim native performance before measured reports.
- Do not begin parallel native work before correctness, conservation, and
  sanitizer evidence.

## First native unit recommendation

The recommended first integrated unit is a pure structural-mass/material-flow
calculation plus a single-organism deterministic lifecycle step over a supplied
food/corpse/territory view. This is narrow enough to test exhaustively while
covering the state and accounting invariants that later division depends on.
