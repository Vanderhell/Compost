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
`220 passed, 3 subtests passed` in the latest complete local run with the
native DLL configured (82.59s).

Native tests:
`7/7` CTest tests passed in the current MSVC 19.42 Release build with
warnings-as-errors enabled (10.12s); the same suite passed under GCC/WSL.

Differential cases:
`28` Python/native differential tests pass, including bounded pure-rule,
external-gut, environment corpse-energy credit, partition transaction,
atomic division-boundary, step-plus-division lifecycle, territory predicate,
deterministic FOOD block-key, two-organism population, and population child
registration comparisons. The latest MSVC DLL run completed in 6.20s; the
earlier WSL GCC DLL run completed in 6.670s.

Long-run steps:
`1,000,000` single-organism Python/native steps pass with zero divergences in
the current ABI v3 replay campaign.

Sanitizer result:
Current GCC 13.3 under WSL with ASan/UBSan: `7/7` tests passed in `284.37s`,
with no sanitizer diagnostics. Windows-mounted filesystem clock-skew warnings
were observed during the build and were not test or sanitizer failures.

GCC result:
GCC 13.3 Debug sanitizer build and test pass; the native C fuzz target covers
10,000 deterministic public-API cases.

Clang result:
Linux Clang 18.1.3 Release `-Werror` build and full CTest pass (`7/7`, 9.59s) with
`-Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow` enabled.
The standalone Windows Clang CRT limitation remains irrelevant to the Linux
Clang CI evidence.

Performance evidence detail:
The direct-C, Python/FFI, and four-organism population checkpoint benchmarks
are recorded in `docs/native/PERFORMANCE_REPORT.md`. The population checkpoint
measured lower native-through-FFI throughput than the reference path, so no
native speedup claim is made.

Known limitations:

- The native core does not yet own the complete `AutonomousOrganism.live_step`
  transition, including filesystem FOOD discovery/claims, territory scheduling,
  corpse lookup/storage, automatic metabolic scheduling, and full death/birth
  orchestration.
- Corpse energy credit is exposed as an explicit environment-supplied ABI
  transfer; corpse selection, persistence, and territory lookup remain Python
  responsibilities.
- The Python/C differential campaign covers bounded single-organism state and
  selected transactions, not a full population/world snapshot after every
  environment event.
- Opaque-context allocation failure, custom allocator lifetime, failed-partition
  cleanup, and selected `UINT64_MAX` transactional boundaries are covered, but
  broader allocation-failure injection for every future/container path, leak
  tooling beyond sanitizer coverage, and serialized snapshot parser fuzzing
  remain release-gate work.
- The native parallel runtime is deliberately deferred. Existing Python
  multiprocessing behavior remains the compatibility implementation.
- Current performance measurements do not establish an end-to-end speedup;
  the native ctypes path is slower than the Python checkpoint because of FFI
  and incomplete-core boundary costs. The population checkpoint confirms the
  same limitation for four explicit ID-ordered native handles.

FINAL VERDICT:
NOT READY
