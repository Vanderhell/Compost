# Native performance report

## Status

This is an initial direct-C smoke benchmark, not a claim about simulator
performance. Python reference and Python↔C FFI benchmark measurements remain
pending; the FFI test suite is now available for correctness checks.

## Workload

- executable: `compost_benchmark_digest`;
- build: C17 Release;
- operation: 100,000 deterministic 4-byte digest calls on one organism;
- input: `1,2,1,2`, nutrition `1.0` per byte;
- timing: C `clock()` CPU time;
- repetitions: 5 fresh organisms;
- output: iterations, bytes, min/median/max seconds, and median steps/sec.

This workload exercises the current bounded native digest checkpoint only. It
does not represent gut processing, maintenance, division, filesystem access,
telemetry, population growth, or multiprocessing.

## Reproduction

```text
cmake -S native -B native/build-release-bench -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=gcc \
  -DCOMPOST_BUILD_TESTS=OFF -DCOMPOST_BUILD_BENCHMARKS=ON
cmake --build native/build-release-bench
native/build-release-bench/compost_benchmark_digest
```

## Evidence boundary

Observed on the current Windows MinGW GCC toolchain: `5` repetitions of
`100000` iterations (`400000` bytes each), min `0.606000000`, median
`0.614000000`, max `0.623000000` CPU seconds, median `162866.450` steps/sec.
This measures only the bounded direct-C digest checkpoint.

No Python or FFI throughput number is recorded yet. No speedup claim is
permitted from this report alone.
