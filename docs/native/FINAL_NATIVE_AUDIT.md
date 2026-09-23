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
`189 passed, 7 skipped, 3 subtests passed` in the latest complete local run.

Native tests:
`7/7` CTest tests passed in the current MSVC Release build.

Differential cases:
`10` Python/native differential tests pass, including bounded external-gut,
environment corpse-energy credit, and partition transaction comparisons.

Long-run steps:
`1,000,000` single-organism Python/native steps pass with zero divergences in
the current ABI v3 replay campaign.

Sanitizer result:
GCC 13.3 under WSL with ASan/UBSan: `7/7` tests passed in `180.44s`, with no
sanitizer diagnostics. Windows-mounted filesystem clock-skew warnings were
observed during the build and were not test or sanitizer failures.

GCC result:
GCC 13.3 Debug sanitizer build and test pass; the native C fuzz target covers
10,000 deterministic public-API cases.

Clang result:
Strict C17 object compilation with `-Wall -Wextra -Wpedantic -Wconversion
-Wsign-conversion -Wshadow` passes for the MinGW target. A complete standalone
Windows Clang link/test run remains unavailable because its CRT libraries are
not installed.

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
- Opaque-context allocation failure is covered, but broader allocation-failure
  injection for every future/container path, leak tooling beyond sanitizer
  coverage, integer-extrema campaigns, and serialized snapshot parser fuzzing
  remain release-gate work.
- The native parallel runtime is deliberately deferred. Existing Python
  multiprocessing behavior remains the compatibility implementation.
- Current performance measurements do not establish an end-to-end speedup;
  the native ctypes path is slower than the Python checkpoint because of FFI
  and incomplete-core boundary costs.

FINAL VERDICT:
NOT READY
