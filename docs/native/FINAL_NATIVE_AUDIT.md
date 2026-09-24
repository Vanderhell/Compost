# COMPOST NATIVE CORE — FINAL AUDIT

This is the current release-readiness audit. `NOT READY` is intentional: the
bounded native core is validated, but the complete sandbox lifecycle has not
yet been migrated or proven equivalent to the Python oracle.

Architecture: PASS
Python reference compatibility: FAIL
C core correctness: PASS
Differential validation: FAIL
Determinism: PASS
Memory safety: PASS
Conservation invariants: PASS
Native ABI: PASS
Performance evidence: PASS
Parallel runtime: DEFERRED
CI: PASS
Documentation: PASS

Python tests:
`267 passed, 3 subtests passed` in the latest complete local run with the
ABI v4 native DLL configured (109.24s).

Native tests:
`8/8` CTest tests passed in the current MSVC 19.42 Debug build with the
width audit and fuzz target enabled (108.20s). The current MSVC Release,
GCC, and Clang strict results are recorded below.

Differential cases:
`67` Python/native differential tests pass, including bounded pure-rule,
external-gut, environment corpse-energy credit, partition transaction,
atomic division-boundary, step-plus-division lifecycle, territory predicate,
deterministic FOOD block-key, two-organism population, and population child
registration, replayable sandbox action-trace, idle/corpse action replay, and
physical-food lifecycle comparisons, public native checkpoint CLI, division/child-death replay, plus bounded
metabolic scheduling arithmetic, starvation/death replay, and opaque metabolic
progress accumulation and completed-lifecycle-step accounting, including the
dead-stop, single-handle, population action-rollback, and child-handle
rollback regressions. A multi-epoch sandbox trace campaign also replays
parent and child traces with per-epoch state comparison and corpse transfer,
plus the reusable `NativeSandboxReplay` host-boundary acceptance and ownership
validation tests, and local weakest-member reproduction component selection.
The sandbox adapter also invokes the native boundary-partition policy for the
historical local-division branch and compares its selected child atoms with
the Python oracle before accepting the epoch.
Each adapter epoch additionally runs native, per-organism Python, and
world-level conservation checks.
Its seed/configuration/epoch parameters are stored in
`tests/fixtures/native_replays.json`, and failures report the first field with
Python/native state digests.
The latest ABI v4 MSVC Debug DLL differential and sandbox run completed in
28.64s; the
earlier WSL GCC DLL run completed in 6.670s.

Long-run steps:
`1,000,000` single-organism Python/native steps pass with zero divergences in
the current ABI v4 replay campaign (`408.41s`).

Sanitizer result:
Current GCC 13.3 under WSL with ASan/UBSan: `8/8` tests passed in `414.45s`,
with no sanitizer diagnostics and leak detection enabled. Windows-mounted
filesystem clock-skew warnings were not present in this WSL run.

GCC result:
GCC 13.3 Release `-Werror` build and CTest pass: `8/8` in `14.04s`; the
native C fuzz target covers 10,000 deterministic public-API cases.

Clang result:
Linux Clang 18.1.3 Release `-Werror` build and full CTest pass (`8/8`, 13.91s) with
`-Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow` enabled.
The standalone Windows Clang CRT limitation remains irrelevant to the Linux
Clang CI evidence.

Performance evidence detail:
The direct-C, workload-matrix, Python/FFI, and four-organism population
checkpoint benchmarks are recorded in `docs/native/PERFORMANCE_REPORT.md`. The population checkpoint
measured lower native-through-FFI throughput than the reference path, so no
native speedup claim is made.

Known limitations:

- The native core does not yet own the complete `AutonomousOrganism.live_step`
  transition, including filesystem FOOD discovery/claims, territory scheduling,
  corpse lookup/storage, automatic metabolic scheduling, and full death/birth
  orchestration.
- Native metabolic threshold/quotient arithmetic, one empty-input
  consolidation/maintenance/age checkpoint are differential-tested, and
  opaque progress accumulation is transactional. Single-organism replay uses
  a transient division child, while the population adapter retains explicit
  child handles. Both adapters expose corpse requests and dead-snapshot
  transfer; automatic scheduling and complete sandbox event ordering remain
  outside the native action state machine. The explicit lifecycle endpoint now
  covers deficit-budget starvation, death transition, and terminal dead no-op.
- Corpse energy credit is exposed as an explicit environment-supplied ABI
  transfer; corpse selection, persistence, and territory lookup remain Python
  responsibilities.
- The Python/C differential campaign covers bounded single-organism state and
  selected transactions, not a full population/world snapshot after every
  environment event.
- Opaque-context allocation failure, custom allocator lifetime, failed-partition
  cleanup, selected `UINT64_MAX` transactional boundaries, and invalid-state
  snapshot output preservation are covered, but broader allocation-failure
  injection for every future/container path and leak tooling beyond sanitizer
  coverage remain release-gate work. A serialized snapshot parser does not
  exist in the current ABI; if introduced, it requires a separate fuzzing gate.
- The native parallel runtime is deliberately deferred. Existing Python
  multiprocessing behavior remains the compatibility implementation.
- Current performance measurements do not establish an end-to-end speedup;
  the native ctypes path is slower than the Python checkpoint because of FFI
  and incomplete-core boundary costs. The population checkpoint confirms the
  same limitation for four explicit ID-ordered native handles.

FINAL VERDICT:
NOT READY
