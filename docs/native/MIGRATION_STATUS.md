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
| Eager maintenance/forgetting slice | PORTING | `MathematicalLifePopulation._maintain_and_resorb` | Reserve settlement, forgetting, age, and empty-body death; weakest-member resorption deferred |
| Lazy metabolism delta | NOT_STARTED | `biology_rules.lazy_metabolism_delta` | Deferred until float/rounding contract is tested |
| Reproduction assessment | NOT_STARTED | `biology_rules.reproduction_allowed` | Requires lifecycle state representation |
| Material-flow accounting | NOT_STARTED | `sandbox_runtime.MaterialFlow` | Requires native container/state design |

## Domain decisions in this checkpoint

The C pure-rule API accepts finite IEEE-754 binary64 values and unsigned 64-bit
counts. It returns an explicit invalid-argument status instead of attempting to
represent Python's arbitrary-precision integer behavior or non-finite math.
This is a native input-domain boundary, not a change to Python semantics.

The checked C functions do not mutate outputs on validation or overflow failure
except where documented by the foundation API. Integer counter addition is
checked before committing the copied ledger.

## Evidence

The native Debug/Release MSVC and GCC builds compile the current tests. A true
Python-vs-C differential campaign remains blocked until the versioned ABI/FFI
layer is introduced. No Python rule was changed in this checkpoint.
