# Native performance report

## Status

This is an initial direct-C smoke benchmark, not a claim about simulator
performance. Python reference and Python↔C FFI measurements are still pending.

## Workload

- executable: `compost_benchmark_digest`;
- build: C17 Release;
- operation: 100,000 deterministic 4-byte digest calls on one organism;
- input: `1,2,1,2`, nutrition `1.0` per byte;
- timing: C `clock()` CPU time;
- output: iterations, bytes, seconds, and steps/sec.

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

Observed on the current Windows GCC toolchain: `100000` iterations,
`400000` bytes, `0.558000000` CPU seconds, `179211.470` steps/sec. This is a
single run and must be repeated with spread reporting before comparative claims.

No Python or FFI number is recorded until the Python interpreter is available
and the native backend can be run against the same canonical workload. No
speedup claim is permitted from this report alone.
