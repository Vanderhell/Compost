# Compost native foundation

This directory is the C17 foundation only. It does not implement simulation
rules and is not connected to Python.

## Ownership and allocation

The public organism currently owns only fixed-size value state, so initialization
does not allocate heap memory. The `compost_allocator_t` is nevertheless stored
with the organism as the single future allocation boundary. Any later dynamic
container must use that allocator, record ownership in its containing object,
and be released by `compost_organism_destroy` or a dedicated destroy function.
There are no hidden pools, globals, singletons, or process-lifetime allocations.

The current behavioral checkpoint uses explicit bounded arrays: 256 atoms and
512 relations/composites. These are validation limits, not the final population
capacity. They keep transactional state copies bounded while the allocator-backed
container design is still pending; exceeding a table returns an error and never
silently drops a structure.

A zeroed allocator selects the library's `malloc`/`free` adapter. A custom
allocator must provide both callbacks and remains owned by the caller; the core
only stores the callback pair and context. Initialization has no partial
allocation path today and destroy is idempotent for a zeroed object.

## Build

```text
cmake -S native -B native/build -G Ninja -DCMAKE_C_COMPILER=gcc
cmake --build native/build
ctest --test-dir native/build --output-on-failure
```

Set `COMPOST_ENABLE_SANITIZERS=ON` with GCC/Clang toolchains that provide the
AddressSanitizer and UBSan runtimes. On Windows, compiler runtime availability
is toolchain-specific; configuration must not be interpreted as evidence that a
sanitizer executable was produced.

The initial API uses public value structs for foundation testing. The eventual
Python ABI should use an opaque context or explicit serialized buffers rather
than exposing internal native layout.
