# COMPOST NATIVE CORE — FINAL AUDIT

This is the current release-readiness audit for the defined hybrid migration
boundary. The Python oracle and environment orchestration remain authoritative;
they are not being replaced by native filesystem or UI code. The native core
is release-ready for its explicit deterministic state-transition boundary.

Architecture: PASS
Python reference compatibility: PASS
C core correctness: PASS
Differential validation: PASS
Determinism: PASS
Memory safety: PASS
Conservation invariants: PASS
Native ABI: PASS
Performance evidence: PASS
Parallel runtime: DEFERRED
CI: PASS
Documentation: PASS

Python tests:
`280 passed, 3 subtests passed` in the latest complete local run with the
current native DLL (107.38s). The focused native sandbox/differential suite
passed `83` tests.

Native tests:
`8/8` CTest tests passed in the current MSVC 19.42 Debug build with the
width audit and fuzz target enabled (99.67s). The current MSVC Release,
GCC, and Clang strict results are recorded below.

Differential cases:
`79` Python/native differential tests pass, including bounded pure-rule,
external-gut, environment corpse-energy credit, partition transaction,
atomic division-boundary, step-plus-division lifecycle, territory predicate,
deterministic FOOD block-key, two-organism population, and population child
registration, replayable sandbox action-trace, idle/corpse action replay, and
physical-food lifecycle comparisons, public native checkpoint CLI, division/child-death replay, plus bounded
metabolic scheduling arithmetic, starvation/death replay, and opaque metabolic
progress accumulation and completed-lifecycle-step accounting, including the
dead-stop, single-handle, population action-rollback, child-handle rollback,
and direct reproduction/partition snapshot-failure rollback regressions,
plus strict non-uint64 population-ID and constructor validation, explicit
serial public-sandbox native backend/CLI coverage, and
preflight-before-capture rollback guards. A multi-epoch sandbox trace campaign
also replays
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
26.96s; the
earlier WSL GCC DLL run completed in 6.670s.

Long-run steps:
`1,000,000` single-organism Python/native steps pass with zero divergences in
the current ABI v4 replay campaign using the Windows GCC 16.1 Release DLL
(`474.69s`).

Sanitizer result:
Current GCC 13.3 under WSL with ASan/UBSan: `8/8` tests passed in `414.45s`,
with no sanitizer diagnostics and leak detection enabled. Windows-mounted
filesystem clock-skew warnings were not present in this WSL run.

GCC result:
GCC 13.3 Release `-Werror` build and CTest pass: `8/8` in `14.04s`; the
native C fuzz target covers 10,000 deterministic public-API cases.
The current Windows GCC 16.1 Debug `-Werror` build and CTest pass is also
`8/8` in `97.94s`.
The Windows GCC 16.1 Release `-Werror` build and CTest pass is `8/8` in
`13.53s`.
Windows Clang 22.1.8 strict compilation passes for all nine C translation
units; executable linking remains unavailable locally because the LLVM
installation lacks `oldnames.lib` and `msvcrtd.lib`.

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

- The native core does not own filesystem FOOD discovery/claims, telemetry,
  CLI behavior, territory scheduling from filesystem state, corpse lookup/
  storage, or human-readable event orchestration. These are intentional Python
  responsibilities in the approved hybrid boundary.
- Native metabolic threshold/quotient arithmetic and the transactional
  progress-plus-due-lifecycle population boundary are differential-tested;
  one empty-input consolidation/maintenance/age checkpoint is also covered.
  Single-organism replay uses
  a transient division child, while the population adapter retains explicit
  child handles. Both adapters expose corpse requests and dead-snapshot
  transfer; complete sandbox event ordering remains outside the native action
  state machine. The explicit lifecycle endpoint now
  covers deficit-budget starvation, death transition, and terminal dead no-op.
- Corpse energy credit is exposed as an explicit environment-supplied ABI
  transfer; corpse selection, persistence, and territory lookup remain Python
  responsibilities.
- The Python/C differential campaign covers the native state and explicit
  action boundary, not a claim that every Python-only environment event has a
  native equivalent. Environment selection and event ordering remain covered
  by the Python regression suite.
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
READY
