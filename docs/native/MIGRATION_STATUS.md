# Native migration status

| Unit | Status | Python reference | Notes |
| --- | --- | --- | --- |
| Foundation init/destroy/snapshot | PORTING | `compost_organism_init`, `compost_organism_snapshot` | Scalar foundation only; no simulation behavior yet |
| Structural mass | PORTING | `biology_rules.structural_mass` | C unit boundaries pass; Python/C differential harness is pending |
| Activity cost accounting | PORTING | `ActivityLedger.add_activity` | C unit tests pass; Python/C FFI differential campaign is pending |
| Settlement threshold/basal cost | PORTING | `ActivityLedger.settlement_threshold`, `basal_cost` | Pure functions added to C API |
| Forgetting delta | PORTING | `biology_rules.forgetting_delta` | Pure C delta, no organism mutation |
| Maintenance weakening budget | PORTING | `biology_rules.maintenance_weakening_budget` | Positive deficit guarantees at least one unit |
| Bounded organism structural state | PORTING | `MathematicalLifeOrganism` structures | 256 atoms and 512 relation/composite validation bounds |
| Deterministic byte digestion checkpoint | PORTING | `MathematicalLifePopulation._digest` | Explicit food/nutrition view; maintenance/gut/division tail not yet included |
| Composed deterministic step checkpoint | PORTING | `MathematicalLifePopulation._cycle_one` | Native digest+consolidation+maintenance transaction with explicit result; full gut and lifecycle policy remain pending |
| Consolidation transition | PORTING | `MathematicalLifePopulation._consolidate` | Deterministic relation-to-composite mutation added with explicit composite parameters; step integration and differential campaign remain pending |
| Eager maintenance/forgetting slice | PORTING | `MathematicalLifePopulation._maintain_and_resorb` | Reserve settlement, forgetting, age, and empty-body death; weakest-member resorption deferred |
| Resorption FIFO accounting | PORTING | `AutonomousOrganism.enqueue_resorbed_material`, `process_gut` | 128 bounded chunks; external payload FIFO remains pending |
| Weakest-structure transition | PORTING | `AutonomousCore.remove_weakest` | Deterministic tie-break; incident-member cleanup and critical-bridge protection pending |
| Opaque native ABI | PORTING | Python reference boundary | `compost_create/destroy/snapshot/digest/state_digest/select_partition/partition`; Python loader and backend selection pending |
| Python backend selector/loader | PORTING | Existing Python runtime | Explicit `python`/`native` handles plus native step adapter; CLI wiring and acceptance run pending |
| Direct-C benchmark | PORTING | Performance phase | Reproducible digest smoke benchmark; Python/FFI comparison pending |
| Public API robustness tests | PORTING | C API failure contract | Null, NaN, transactional failure, and idempotent destroy coverage |
| Lazy metabolism delta | PORTING | `biology_rules.lazy_metabolism_delta` | C logarithmic composition added; tolerance-based reference comparison and FFI campaign remain pending |
| Reproduction assessment | PORTING | `biology_rules.reproduction_allowed` | Pure eligibility/score function and selected-region native transaction added; automatic candidate policy remains pending |
| Material-flow accounting | PORTING | `sandbox_runtime.MaterialFlow` | Native conservation validator, FIFO accounting, cross-edge resorption, and division transfer added; external payload gut remains pending |

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
