# Compost native core checkpoints

This directory contains the C17 native foundation and bounded deterministic
simulation checkpoints. It is exposed through a versioned opaque ABI and has
an explicit Python ctypes adapter. The Python implementation remains the
behavioral oracle.

The current native behavior includes pure biology rules, byte digestion,
bounded external-gut payload enqueue/process, maintenance/forgetting,
resorption accounting, deterministic partition selection, selected structural
partition transactions, consolidation transitions, and a transactional
digest-plus-maintenance step. It also accepts an environment-supplied corpse
energy transfer; corpse lookup, storage, and territory selection remain in
Python. It is not yet the complete lifecycle engine:
step-level consolidation/viability integration, population scheduling, corpse
interaction, and full Python sandbox per-step differential validation remain
pending.

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

The gut uses a 128-entry FIFO chunk ring. Each external chunk owns up to 16
bytes and matching binary64 nutrition values; longer input is split into
ordered chunks. Enqueue and processing are transactional and preserve the
material-flow conservation equations.

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

Foundation value structs remain available for native unit tests. Python-facing
operations use the opaque context ABI (`compost_create`, `compost_step`,
`compost_context_partition`, `compost_context_try_divide`, snapshot/digest,
conservation validation, and destroy); Python does not
depend on internal organism layout.
