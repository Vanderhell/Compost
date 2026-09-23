# Native robustness audit

## Current evidence

The native test suite now checks null arguments, invalid floating-point input,
failed-operation state preservation, repeated destroy, opaque handle errors, and
bounded table behavior through the public C APIs. GCC Debug and MSVC Release builds run
these tests under CTest. The current Windows evidence includes GCC Debug,
GCC Release, and MSVC Release runs, with all seven tests passing in each run
where the fuzz target is enabled; the current MSVC Release run also enables
warnings-as-errors.
The opaque weakest-structure wrapper also preserves caller outputs when its
handle is invalid, and the Python adapter exposes the same explicit failure.
The combined step-and-division ABI test verifies that an invalid child identity
leaves the parent digest and every caller output sentinel unchanged.
The Python population orchestrator rejects unknown environment IDs, duplicate
or colliding child IDs, and reserves automatic IDs before scheduling an epoch.
It also preflights all bite/nutrition lengths and finite values before the
first handle mutates, preserving every population snapshot on input failure.
The explicit `NativeAction` adapter also rejects non-finite energy, mismatched
nutrition, negative capacities, and irrelevant fields before invoking the ABI;
the lifecycle action is compared with the direct step call and its state digest.
Territory address/contains predicates reject out-of-range depth, null paths,
and non-binary path bytes without modifying caller outputs.
The bounded food block-key API also rejects null input with a non-zero length
without modifying its output key.
The division fixture additionally verifies duplicate/whole-region rejection,
unchanged parent state, and an untouched child output on failed partition
calls.
The lifecycle fixtures additionally cover deterministic starvation resorption,
mass-ledger verification, and a dead-state step no-op with invalid-input
validation preserved. A critical-bridge fixture verifies that capacity
pressure rejects a novel structure without breaking the connected skeleton
and still accounts for the rejected byte.
The native source also passes a complete Linux Clang Release link and CTest
run with warnings-as-errors enabled; standalone Windows Clang remains limited
by the unavailable CRT libraries.

The deterministic C fuzz target executes 10,000 generated public-API cases,
including NaN inputs and invalid pointer/length combinations, and checks state
preservation after every failed call. It now exercises the combined
step-and-division ABI and the metabolic progress accumulator on two identical
contexts and compares status, digest, division plan, material result, due
steps, and remainder on every case.

The same seven-test suite was also built and executed from the current tree
with GCC 13.3 under WSL using AddressSanitizer and UndefinedBehaviorSanitizer
after the nested division fixture and population validation changes. All seven
tests passed in `284.37s`; the run emitted no sanitizer diagnostics. The Windows-mounted workspace did emit
CMake clock-skew warnings caused by filesystem timestamp differences; no test
or sanitizer failure was associated with those warnings.

The public robustness test now covers both sides of the allocator boundary:
forced context-allocation failure returns `COMPOST_STATUS_OUT_OF_MEMORY` without
an output handle, while successful custom allocation is released through the
same caller-supplied deallocator exactly once during `compost_destroy`.
It also exercises `UINT64_MAX` organism/configuration values and verifies that
an age-overflowing step is rejected transactionally without changing state.
Failed opaque partition creation is also checked to release its temporary child
context through that same allocator rather than a hard-coded system `free`.
The current fixture additionally forces allocation failure while creating a
valid division child and verifies `COMPOST_STATUS_OUT_OF_MEMORY`, a null child
handle, and unchanged parent state digest.
The nested division fixture also accepts `UINT64_MAX` as a child identity and
checks its parent, generation, territory, and conservation state.
The dense cross-split division fixture passes a current GCC 13.3
AddressSanitizer/UndefinedBehaviorSanitizer targeted run (`1/1`, `0.09s`) with
no diagnostics.
Invalid `try_divide` handles are checked to preserve all caller output sentinels.
The public status-name helper returns stable names for every defined status and
`UNKNOWN_STATUS` for an invalid enum value without terminating the process.

## Outstanding evidence

ASan/UBSan linking remains unavailable in the current MinGW installation because
`libasan` and `libubsan` are missing. Clang cannot link here because the Windows
CRT libraries are not available to its standalone driver. These are Windows
toolchain limitations; the WSL GCC sanitizer run above is local sanitizer
evidence, while CI still provides the release-platform Linux job. A release
gate still requires broader leak checks, allocation-failure injection across
every future/container path and serialized corrupt snapshot tests. Opaque-context allocation failure is now explicitly injected
and covered by the native robustness test; the successful custom allocator
lifetime path is covered there as well.

## Verdict

`NOT READY`: public foundation failure handling is covered, but the native
organism state and ABI are not yet complete enough for full hostile validation.
