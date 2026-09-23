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
| Native deterministic replay | DIFFERENTIAL_PASS | Deterministic reference contract | Forty deterministic scenarios × 256 cycles pass in the default campaign; a local 1,000,000-step Python/native replay, bounded two-organism/256-cycle population boundary including post-stream empty-input steps, division/child-death replay, and population child-registration case also pass with first-step mismatch reporting; full lifecycle/reference scope remains pending |
| Eager maintenance/forgetting slice | DIFFERENTIAL_PASS | `MathematicalLifePopulation._maintain_and_resorb` | Reserve settlement, forgetting, deterministic starvation resorption, age, and empty-body death pass bounded differential coverage |
| Resorption/external FIFO accounting | DIFFERENTIAL_PASS | `AutonomousOrganism.enqueue_external_material`, `process_gut` | Native ABI v3 owns bounded payload/nutrition chunks, partial FIFO processing, resorption accounting, and Python adapter tests; full sandbox differential integration remains pending |
| Weakest-structure transition | PORTING | `AutonomousCore.remove_weakest`, `AutonomousOrganism._detach_member` | The native lifecycle endpoint matches the sandbox member-weakening path (budgeted weakest-member selection, local incident removal, resorption, and death follow-up). The legacy opaque `weaken_weakest` endpoint intentionally exposes only bounded structure-level weakening; it does not claim equivalence to `remove_weakest` because Python also applies critical-bridge protection and a separate member-cache policy. Full legacy/sandbox policy unification remains pending |
| Opaque native ABI | DIFFERENTIAL_PASS | Python reference boundary | ABI v3 `compost_create/destroy/snapshot/digest/state_digest/select_partition/select_local_reproduction/plan_division/partition/try_divide/try_local_reproduction/weaken_weakest`, pure step, explicit lifecycle-step settlement, external-gut enqueue/process, corpse-energy credit, read-only conservation validation, ID-ordered population state digests, explicit action traces, and dead-snapshot handle transfer; opaque Python adapter validates the returned version and exposes failures without fallback |
| Python backend selector/loader | PORTING | Existing Python runtime | Explicit `python`/`native`/`native-population` handles, top-level `NativePopulationBackend` export, shared lifecycle-config forwarding, native step/snapshot/partition/try-divide/step-plus-division adapters, ID-ordered orchestration, retained explicit-division child handles with collision preflight, corpse request/transfer operations, and `checkpoint --backend` CLI mode; full sandbox lifecycle acceptance remains pending |
| Native workload benchmark matrix | INTEGRATED | Performance phase | Reproducible digest, metabolism, structure, division, and population checkpoint measurements with median/spread and process peak-RSS reporting; CI executes the matrix and no speedup claim is made |
| Public API robustness tests | PORTING | C API failure contract | Null, NaN, transactional failure, allocator lifetime/failure, integer extrema, idempotent destroy, deterministic 10,000-case fuzzing, and fixed-width ABI audit coverage; hostile serialized-state coverage remains pending |
| Lazy metabolism delta | DIFFERENTIAL_PASS | `biology_rules.lazy_metabolism_delta` | Tolerance-based Python/C differential cases pass |
| Metabolic schedule arithmetic | DIFFERENTIAL_PASS | `AutonomousOrganism.metabolic_work_threshold` | Native bounded threshold/quotient/remainder helper matches Python max/divmod cases, including uint64 boundaries; automatic scheduling loop remains Python-owned |
| Native metabolic progress accumulator | DIFFERENTIAL_PASS | `AutonomousOrganism.metabolic_progress`, `metabolic_steps` | Opaque ABI v3 context owns explicit transactional progress/step accounting; overflow rollback and zeroed child state are covered; lifecycle work for each due step remains host-owned |
| Reproduction assessment | DIFFERENTIAL_PASS | `biology_rules.reproduction_allowed` | Pure eligibility/score differential cases pass; local weakest-member candidate selection is now ported separately, while the existing global `plan_division` policy remains unchanged |
| Local reproduction component selection | DIFFERENTIAL_PASS | `AutonomousOrganism._reproduce_conservatively` | Read-only C17 weakest-member/component selector and explicit `try_local_reproduction` transaction match the Python reference on deterministic graph cases, including maximum isolated-component capacity; the existing global `plan_division` policy remains separate and unchanged |
| Territory address and block-key predicates | DIFFERENTIAL_PASS | `territory.address_bit`, `FoodTerritory.contains`, `food_block_key` | Bounded C17 mix64/contains and portable SHA-256 block-key functions match Python vectors through depth 63, Unicode IDs, UINT64 boundaries, and invalid-input preservation |
| Material-flow accounting | DIFFERENTIAL_PASS | `sandbox_runtime.MaterialFlow` | Native conservation validator is available through the opaque ABI; external/resorption FIFO accounting, cross-edge resorption, and division transfer pass bounded tests; full sandbox ledger differential remains pending |
| Environment corpse-energy credit | DIFFERENTIAL_PASS | `AutonomousOrganism._consume_corpse` | Python-owned corpse lookup supplies an explicit energy amount to the native ABI; reserve credit and invalid-input rollback are differentially covered; corpse storage/territory lookup remain in Python |
| Sandbox `live_step` orchestration | PORTING | `AutonomousOrganism.live_step` | Reusable `NativeSandboxReplay` invokes host-built `NativeAction` plans, owns deterministic numeric parent/child handles, attempts native local-reproduction selection for division traces, preserves the explicit native partition fallback for Python's historical `_divide_locally` branch, returns epoch snapshots, emits one-shot `store_corpse` requests, and transfers dead snapshots; external-gut, queued-gut, corpse-credit, territory, material flow, full activity-ledger settlement, ordered gut state, metabolic progress/step count, generation, activated receptors, consolidation/maintenance/age, and starvation/death replay are covered; filesystem/environment selection, sandbox identity/corpse persistence, territory release, and complete event ordering remain Python-owned and are documented in `SANDBOX_TRANSITION_BOUNDARY.md` |

| Selected structural partition | DIFFERENTIAL_PASS | `AutonomousOrganism._commit_skeleton_partition` | Selector, viability plan, local reproduction transaction, explicit partition fallback, and conservation checks pass native GCC/MSVC tests plus bounded Python/sandbox mass/reserve/body differential coverage; the broader global `plan_division` policy remains separate |
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
