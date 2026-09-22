# Native robustness audit

## Current evidence

The native test suite now checks null arguments, invalid floating-point input,
failed-operation state preservation, repeated destroy, opaque handle errors, and
bounded table behavior through the public C APIs. GCC and MSVC Debug builds run
these tests under CTest. The current Windows evidence includes GCC Debug,
GCC Release, and MSVC Debug runs, with all four tests passing in each run.

## Outstanding evidence

ASan/UBSan linking is unavailable in the current MinGW installation because
`libasan` and `libubsan` are missing. Clang cannot link here because the Windows
CRT libraries are not available to its standalone driver. These are environment
limitations, not sanitizer passes. A release gate still requires sanitizer
runs, leak checks, allocation-failure injection, integer-extrema campaigns,
corrupt snapshot tests, and fuzz replay once the corresponding APIs exist.

## Verdict

`NOT READY`: public foundation failure handling is covered, but the native
organism state and ABI are not yet complete enough for full hostile validation.
