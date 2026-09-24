# Native robustness audit

## Current evidence

The native test suite now checks null arguments, invalid floating-point input,
failed-operation state preservation, repeated destroy, opaque handle errors, and
bounded table behavior through the public C APIs. GCC, Clang, and MSVC builds
run these tests under CTest. The current evidence has all eight tests passing,
including the fixed-width ABI audit and fuzz target; GCC and Clang strict
builds use warnings-as-errors.
The opaque weakest-structure wrapper also preserves caller outputs when its
handle is invalid, and the Python adapter exposes the same explicit failure.
The combined step-and-division ABI test verifies that an invalid child identity
leaves the parent digest and every caller output sentinel unchanged.
The local-reproduction transaction additionally verifies that a valid
no-candidate call returns a NULL child, zeroed division result, and unchanged
state digest.
The Python population orchestrator rejects unknown environment IDs, duplicate
or colliding child IDs, and reserves automatic IDs before scheduling an epoch.
It also preflights all bite/nutrition lengths and finite values before the
first handle mutates, preserving every population snapshot on input failure.
Due-lifecycle population batches additionally capture exact opaque snapshots
for every scheduled handle and restore all handles if a later execution fails;
this cross-handle rollback is covered by an injected-failure regression test.
Host-built action-trace epochs use the same exact rollback boundary, including
closing and removing children created before a later action fails; this is
covered by a separate injected-failure test.
The outer sandbox epoch transaction also recreates a stable native handle when
corpse transfer removed it before a later failure; this preserves the complete
native population boundary rather than only live handles.
The explicit environment-step API is protected by the same boundary and
restores earlier organisms when a later organism fails during its transition.
Sandbox action traces now have an epoch-wide preflight as well, including
action types and globally reserved division IDs, before any prefix or native
reproduction transaction commits.
The explicit `NativeAction` adapter also rejects non-finite energy, mismatched
nutrition, negative capacities, and irrelevant fields before invoking the ABI;
the lifecycle action invokes the explicit settlement-aware lifecycle endpoint
and its state digest is checked by replay tests.
The native robustness fixture also verifies that invalid lifecycle input leaves
both the context digest and caller result sentinels unchanged.
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

The metabolic accounting regression also verifies that progress accumulation
does not claim lifecycle steps before execution, and that queued due work stops
without incrementing the completed-step counter after an organism is dead.
The same hostile suite sets the completed-step counter to `UINT64_MAX` through
the native snapshot API and verifies that lifecycle overflow rejects the call
without changing either the context digest or caller result outputs.

The current eight-test suite was built and executed from the current tree with
GCC 13.3 under WSL using AddressSanitizer and UndefinedBehaviorSanitizer,
including leak detection. All eight tests passed in `414.45s`; the run emitted
no sanitizer diagnostics.

The same current tree also passed the strict GCC 13.3 Release suite (`8/8`,
`14.04s`) and strict Linux Clang 18.1.3 Release suite (`8/8`, `13.91s`),
both with warnings-as-errors enabled.

The Python ABI adapter also has a single-handle action-epoch regression: a
failure in a later action restores the earlier native mutation from the opaque
snapshot before propagating the error.

The current MSVC 19.42 Release tree also passes all eight CTest targets,
including the due-lifecycle ABI regression and fuzz target (`8/8`, `14.14s`).
The current MSVC 19.42 Debug tree independently passes all eight CTest targets
with the same fuzz and width checks (`8/8`, `98.98s`).

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
Direct population reproduction and boundary-partition registration also roll
back the parent and remove the transient child when child snapshot
materialization fails.
Population environment, action, due-lifecycle, and trace map keys now reject
non-uint64 values before native state capture or mutation.
The public status-name helper returns stable names for every defined status and
`UNKNOWN_STATUS` for an invalid enum value without terminating the process.

## Outstanding evidence

ASan/UBSan linking remains unavailable in the current MinGW installation because
`libasan` and `libubsan` are missing. Clang cannot link here because the Windows
CRT libraries are not available to its standalone driver. These are Windows
toolchain limitations; the WSL GCC sanitizer run above is local sanitizer
evidence, while CI still provides the release-platform Linux job. A release
gate still requires broader leak checks and allocation-failure injection across
every future/container path. The current ABI has no serialized-state parser,
so parser fuzzing is not applicable yet; it becomes a release gate if a wire
format is added. Opaque-context allocation failure is now explicitly injected
and covered by the native robustness test; the successful custom allocator
lifetime path is covered there as well. Invalid in-memory snapshot state also
has an output-preservation regression test.

## Verdict

The ABI also has a transactional native-snapshot restore gate. It rejects
wrong ABI versions, mismatched organism identity, invalid bounds/territory,
non-finite activity values, malformed structure/gut state, structural-mass
inconsistency, or failed conservation validation without changing the target
context; a valid snapshot plus metabolic backlog restores the native state
digest exactly.

`NOT READY`: public foundation failure handling is covered, but the native
organism state and ABI are not yet complete enough for full hostile validation.
