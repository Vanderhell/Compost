# Native robustness audit

## Current evidence

The native test suite now checks null arguments, invalid floating-point input,
failed-operation state preservation, repeated destroy, opaque handle errors, and
bounded table behavior through the public C APIs. GCC Debug and MSVC Release builds run
these tests under CTest. The current Windows evidence includes GCC Debug,
GCC Release, and MSVC Release runs, with all seven tests passing in each run
where the fuzz target is enabled.
The division fixture additionally verifies duplicate/whole-region rejection,
unchanged parent state, and an untouched child output on failed partition
calls.
The lifecycle fixtures additionally cover deterministic starvation resorption,
mass-ledger verification, and a dead-state step no-op with invalid-input
validation preserved. A critical-bridge fixture verifies that capacity
pressure rejects a novel structure without breaking the connected skeleton
and still accounts for the rejected byte.
The native source also passes the strict Clang C17 object compilation with the
MinGW target; a complete Clang link/test run remains unavailable because the
standalone Windows Clang environment lacks the required CRT libraries.

The deterministic C fuzz target executes 10,000 generated public-API cases,
including NaN inputs and invalid pointer/length combinations, and checks state
preservation after every failed call.

The same seven-test suite was also built and executed with GCC 13.3 under WSL
using AddressSanitizer and UndefinedBehaviorSanitizer. All seven tests passed;
the run emitted no sanitizer diagnostics. The Windows-mounted workspace did
emit CMake clock-skew warnings caused by filesystem timestamp differences; no
test or sanitizer failure was associated with those warnings.

## Outstanding evidence

ASan/UBSan linking remains unavailable in the current MinGW installation because
`libasan` and `libubsan` are missing. Clang cannot link here because the Windows
CRT libraries are not available to its standalone driver. These are Windows
toolchain limitations; the WSL GCC sanitizer run above is local sanitizer
evidence, while CI still provides the release-platform Linux job. A release
gate still requires leak checks, allocation-failure injection, integer-extrema
campaigns, and corrupt snapshot tests.

## Verdict

`NOT READY`: public foundation failure handling is covered, but the native
organism state and ABI are not yet complete enough for full hostile validation.
