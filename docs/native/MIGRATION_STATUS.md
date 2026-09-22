# Native migration status

| Unit | Status | Python reference | Notes |
| --- | --- | --- | --- |
| Foundation init/destroy/snapshot | PORTING | `compost_organism_init`, `compost_organism_snapshot` | Scalar foundation only; no simulation behavior yet |
| Structural mass | DIFFERENTIAL_PASS | `biology_rules.structural_mass` | C unit boundaries and Python/C differential cases pass |
| Activity cost accounting | DIFFERENTIAL_PASS | `ActivityLedger.add_activity` | C unit tests and bounded Python/C differential cases pass |
| Settlement threshold/basal cost | PORTING | `ActivityLedger.settlement_threshold`, `basal_cost` | Pure functions added to C API |
| Forgetting delta | PORTING | `biology_rules.forgetting_delta` | Pure C delta, no organism mutation |
| Maintenance weakening budget | PORTING | `biology_rules.maintenance_weakening_budget` | Positive deficit guarantees at least one unit |
| Bounded organism structural state | PORTING | `MathematicalLifeOrganism` structures | 256 atoms and 512 relation/composite validation bounds |
| Deterministic byte digestion checkpoint | DIFFERENTIAL_PASS | `MathematicalLifePopulation._digest` | Explicit food/nutrition view with Python formation-cost ordering, pressure-capacity removal, and bounded replay coverage; maintenance/gut/division tail not yet included |
| Composed deterministic step checkpoint | DIFFERENTIAL_PASS | `MathematicalLifePopulation._cycle_one` | Native digest+consolidation+maintenance transaction matches the bounded Python replay; full gut and lifecycle policy remain pending |
| Consolidation transition | DIFFERENTIAL_PASS | `MathematicalLifePopulation._consolidate` | Deterministic relation-to-composite mutation and capacity/bridge handling pass bounded differential coverage; full policy integration remains pending |
| Native deterministic replay | DIFFERENTIAL_PASS | Deterministic reference contract | Forty deterministic scenarios × 256 cycles pass in the default campaign; a local 1,000,000-step Python/native replay also passes with first-step mismatch reporting; full lifecycle/reference scope remains pending |
| Eager maintenance/forgetting slice | DIFFERENTIAL_PASS | `MathematicalLifePopulation._maintain_and_resorb` | Reserve settlement, forgetting, deterministic starvation resorption, age, and empty-body death pass bounded differential coverage |
| Resorption/external FIFO accounting | DIFFERENTIAL_PASS | `AutonomousOrganism.enqueue_external_material`, `process_gut` | Native ABI v3 owns bounded payload/nutrition chunks, partial FIFO processing, resorption accounting, and Python adapter tests; full sandbox differential integration remains pending |
| Weakest-structure transition | PORTING | `AutonomousCore.remove_weakest` | Deterministic tie-break and capacity-pressure critical-bridge protection are covered; full weakest-structure policy remains pending |
| Opaque native ABI | PORTING | Python reference boundary | `compost_create/destroy/snapshot/digest/state_digest/select_partition/plan_division/partition`; opaque Python adapter and ABI failure handling pass |
| Python backend selector/loader | PORTING | Existing Python runtime | Explicit `python`/`native` handles, native step/snapshot/partition adapters, and `checkpoint --backend` CLI mode; full lifecycle acceptance remains pending |
| Direct-C benchmark | PORTING | Performance phase | Reproducible digest smoke benchmark plus bounded Python/FFI comparison; no speedup claim yet |
| Public API robustness tests | PORTING | C API failure contract | Null, NaN, transactional failure, and idempotent destroy coverage |
| Lazy metabolism delta | DIFFERENTIAL_PASS | `biology_rules.lazy_metabolism_delta` | Tolerance-based Python/C differential cases pass |
| Reproduction assessment | DIFFERENTIAL_PASS | `biology_rules.reproduction_allowed` | Pure eligibility/score differential cases pass; automatic candidate policy remains pending |
| Material-flow accounting | DIFFERENTIAL_PASS | `sandbox_runtime.MaterialFlow` | Native conservation validator, external/resorption FIFO accounting, cross-edge resorption, and division transfer pass bounded tests; full sandbox ledger differential remains pending |

| Selected structural partition | PORTING | `AutonomousOrganism._commit_skeleton_partition` | Selector, viability plan, and partition transaction pass native GCC/MSVC tests; Python differential campaign and full policy integration remain pending |
| Native parallel runtime | DEFERRED | Existing Python parallel runtime | See `PARALLEL_RUNTIME.md`; single-thread semantic parity is required first |

## Domain decisions in this checkpoint

The C pure-rule API accepts finite IEEE-754 binary64 values and unsigned 64-bit
counts. It returns an explicit invalid-argument status instead of attempting to
represent Python's arbitrary-precision integer behavior or non-finite math.
This is a native input-domain boundary, not a change to Python semantics.

The checked C functions do not mutate outputs on validation or overflow failure
except where documented by the foundation API. Integer counter addition is
checked before committing the copied ledger.

The opaque ABI state digest uses explicit little-endian FNV-1a encoding of the
behavioral state and configuration. It does not hash C padding or addresses.
It is an integration aid for future per-step differential tests, not evidence
of Python/C equivalence while the native lifecycle remains incomplete.

## Evidence

The native Debug/Release MSVC and GCC builds compile and pass the current
CTest suite. The versioned ABI and Python pure-rule differential harness now
exist and are executed in the CI native compiler matrix. The full lifecycle
Python-vs-C campaign remains pending because the C lifecycle is incomplete.
No Python rule was changed in this checkpoint.
