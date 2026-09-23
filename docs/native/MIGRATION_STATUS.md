# Native migration status

| Unit | Status | Python reference | Notes |
| --- | --- | --- | --- |
| Foundation init/destroy/snapshot | DIFFERENTIAL_PASS | `compost_organism_init`, `compost_organism_snapshot` | Bounded scalar state, opaque ABI snapshots, cleanup, and per-step snapshot fields are covered; full lifecycle state remains pending |
| Structural mass | DIFFERENTIAL_PASS | `biology_rules.structural_mass` | C unit boundaries and Python/C differential cases pass |
| Activity cost accounting | DIFFERENTIAL_PASS | `ActivityLedger.add_activity` | C unit tests and bounded Python/C differential cases pass |
| Settlement threshold/basal cost | DIFFERENTIAL_PASS | `ActivityLedger.settlement_threshold`, `basal_cost` | Direct Python/C differential cases cover zero, small, and large body masses |
| Forgetting delta | DIFFERENTIAL_PASS | `biology_rules.forgetting_delta` | Direct Python/C differential cases cover dormant and active income paths |
| Maintenance weakening budget | DIFFERENTIAL_PASS | `biology_rules.maintenance_weakening_budget` | Direct Python/C differential cases cover zero, positive, and normalized deficits |
| Bounded organism structural state | DIFFERENTIAL_PASS | `MathematicalLifeOrganism` structures | Fixed 256-atom/512-edge bounds, deterministic ordering, structure snapshots, and bounded Python/C replay coverage pass; unbounded/full-population policy remains pending |
| Deterministic byte digestion checkpoint | DIFFERENTIAL_PASS | `MathematicalLifePopulation._digest` | Explicit food/nutrition view with Python formation-cost ordering, pressure-capacity removal, and bounded replay coverage; maintenance/gut/division tail not yet included |
| Composed deterministic step checkpoint | DIFFERENTIAL_PASS | `MathematicalLifePopulation._cycle_one` | Native digest+consolidation+maintenance transaction and explicit step-plus-division transition match bounded Python replay; full gut/population policy remains pending |
| Consolidation transition | DIFFERENTIAL_PASS | `MathematicalLifePopulation._consolidate` | Deterministic relation-to-composite mutation and capacity/bridge handling pass bounded differential coverage; full policy integration remains pending |
| Native deterministic replay | DIFFERENTIAL_PASS | Deterministic reference contract | Forty deterministic scenarios × 256 cycles pass in the default campaign; a local 1,000,000-step Python/native replay and bounded two-organism/sixteen-cycle population boundary also pass with first-step mismatch reporting; full lifecycle/reference scope remains pending |
| Eager maintenance/forgetting slice | DIFFERENTIAL_PASS | `MathematicalLifePopulation._maintain_and_resorb` | Reserve settlement, forgetting, deterministic starvation resorption, age, and empty-body death pass bounded differential coverage |
| Resorption/external FIFO accounting | DIFFERENTIAL_PASS | `AutonomousOrganism.enqueue_external_material`, `process_gut` | Native ABI v3 owns bounded payload/nutrition chunks, partial FIFO processing, resorption accounting, and Python adapter tests; full sandbox differential integration remains pending |
| Weakest-structure transition | PORTING | `AutonomousCore.remove_weakest` | Deterministic tie-break and capacity-pressure critical-bridge protection are covered; opaque ABI now exposes the bounded transition; full weakest-structure policy remains pending |
| Opaque native ABI | DIFFERENTIAL_PASS | Python reference boundary | ABI v3 `compost_create/destroy/snapshot/digest/state_digest/select_partition/plan_division/partition/try_divide/weaken_weakest`, external-gut enqueue/process, and read-only conservation validation; opaque Python adapter validates the returned version and exposes failures without fallback |
| Python backend selector/loader | PORTING | Existing Python runtime | Explicit `python`/`native` handles, shared lifecycle-config forwarding, native step/snapshot/partition/try-divide/step-plus-division adapters, `NativePopulationBackend` ID-ordered orchestration, and `checkpoint --backend` CLI mode; full lifecycle acceptance remains pending |
| Direct-C benchmark | PORTING | Performance phase | Reproducible digest smoke benchmark plus bounded Python/FFI comparison; no speedup claim yet |
| Public API robustness tests | PORTING | C API failure contract | Null, NaN, transactional failure, allocator lifetime/failure, integer extrema, and idempotent destroy coverage |
| Lazy metabolism delta | DIFFERENTIAL_PASS | `biology_rules.lazy_metabolism_delta` | Tolerance-based Python/C differential cases pass |
| Reproduction assessment | DIFFERENTIAL_PASS | `biology_rules.reproduction_allowed` | Pure eligibility/score differential cases pass; automatic candidate policy remains pending |
| Territory address and block-key predicates | DIFFERENTIAL_PASS | `territory.address_bit`, `FoodTerritory.contains`, `food_block_key` | Bounded C17 mix64/contains and portable SHA-256 block-key functions match Python vectors through depth 63, Unicode IDs, UINT64 boundaries, and invalid-input preservation |
| Material-flow accounting | DIFFERENTIAL_PASS | `sandbox_runtime.MaterialFlow` | Native conservation validator is available through the opaque ABI; external/resorption FIFO accounting, cross-edge resorption, and division transfer pass bounded tests; full sandbox ledger differential remains pending |
| Environment corpse-energy credit | DIFFERENTIAL_PASS | `AutonomousOrganism._consume_corpse` | Python-owned corpse lookup supplies an explicit energy amount to the native ABI; reserve credit and invalid-input rollback are differentially covered; corpse storage/territory lookup remain in Python |

| Selected structural partition | DIFFERENTIAL_PASS | `AutonomousOrganism._commit_skeleton_partition` | Selector, viability plan, and partition transaction pass native GCC/MSVC tests plus bounded Python/sandbox mass/reserve/body differential coverage; automatic candidate policy and full integration remain pending |
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
