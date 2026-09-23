# Native performance report

## Status

This is an initial direct-C smoke benchmark, not a claim about simulator
performance. Python reference and Python/C FFI checkpoint measurements are now
available below; they do not represent the complete simulator.

## Workload

- executable: `compost_benchmark_digest`;
- build: C17 Release;
- operation: 100,000 deterministic 4-byte digest calls on one organism;
- input: `1,2,1,2`, nutrition `1.0` per byte;
- timing: C `clock()` CPU time;
- repetitions: 5 fresh organisms;
- output: iterations, bytes, min/median/max seconds, and median steps/sec.

This workload exercises the current bounded native digest checkpoint only. It
does not represent external-gut processing, maintenance, division, filesystem
access, telemetry, population growth, or multiprocessing.

## Reproduction

```text
cmake -S native -B native/build-release-bench -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=gcc \
  -DCOMPOST_BUILD_TESTS=OFF -DCOMPOST_BUILD_BENCHMARKS=ON
cmake --build native/build-release-bench
native/build-release-bench/compost_benchmark_digest
```

## Evidence boundary

Observed on the current Windows MSVC Release toolchain: `5` repetitions of
`100000` iterations (`400000` bytes each), min `0.801000000`, median
`0.808000000`, max `0.828000000` CPU seconds, median `123762.376` steps/sec.
This measures only the bounded direct-C digest checkpoint.

No speedup claim is permitted from the direct-C smoke benchmark alone.

## Current GCC cross-check

The same benchmark was rebuilt from the current tree with GCC Release and
`COMPOST_WARNINGS_AS_ERRORS=ON` under WSL after the step-plus-division and
territory predicate additions. It completed five repetitions of `100000`
iterations (`400000` bytes each): min `0.776119000`, median `0.786463000`,
max `0.802420000` CPU seconds, median `127151.563` steps/sec.

This remains a bounded digest microbenchmark and is reported as a cross-check,
not as an end-to-end performance claim.

## Python/FFI checkpoint comparison

`tools/benchmark_native_backends.py` runs the same bounded `AB` replay for
both the Python reference and the current native checkpoint through ctypes.
On the current Windows MSVC Release build, five repetitions of `10000` steps
measured a Python median of `0.038265100` seconds (`261334.741` steps/sec)
and a native-FFI median of `0.065498400` seconds (`152675.485` steps/sec).
This is not a complete simulator comparison: it includes FFI overhead and the
native checkpoint is still incomplete. It demonstrates that further native
performance claims require a larger migrated workload and measurement of the
boundary costs.
