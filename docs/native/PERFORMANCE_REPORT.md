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

Observed on the current Windows MSVC 19.42 Release toolchain from the current
tree: `5` repetitions of `100000` iterations (`400000` bytes each), min
`0.770000000`, median `0.774000000`, max `0.775000000` CPU seconds, median
`129198.966` steps/sec.
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
On the current Windows MSVC Release build from the current tree, five
repetitions of `10000` steps measured a Python median of `0.038588000` seconds
(`259147.922` steps/sec) and a native-FFI median of `0.065072700` seconds
(`153674.275` steps/sec).
This is not a complete simulator comparison: it includes FFI overhead and the
native checkpoint is still incomplete. It demonstrates that further native
performance claims require a larger migrated workload and measurement of the
boundary costs.

## Population checkpoint comparison

The same harness also supports `--population-size` and measures explicit
ID-ordered population orchestration. The workload below uses four organisms,
`256` logical steps, three repetitions, one shared `AB` payload on the first
step, and empty environment inputs thereafter. The first-step nutrition is
split equally across organisms so the benchmark preserves the Python
material-conservation invariant.

Reproduction:

```text
python tools/benchmark_native_backends.py --library <native-library> \
  --steps 256 --repetitions 3 --population-size 4
```

Observed on the current MSVC Release DLL:

```text
reference_population_median_seconds=0.016932800
native_population_ffi_median_seconds=0.081681400
reference_population_steps_per_second=15118.586
native_population_ffi_steps_per_second=3134.128
```

This is still a bounded checkpoint, not a complete world benchmark. It
demonstrates that the current Python orchestration and FFI boundary cost more
than the reference path for this workload; no native speedup claim is made.

## Representative workload matrix

`tools/benchmark_native_workloads.py` measures the currently exposed
digest, metabolism, structure, and division checkpoints with five repetitions
of 256 logical steps. It reports min/median/max wall time, steps/sec, and the
peak working set observed by the hosting process through Windows PSAPI. The
RSS value is process-level evidence (not an isolated allocator measurement),
so it is reported as a boundary metric rather than a native-only memory claim.

Reproduction:

```text
python tools/benchmark_native_workloads.py --library <native-library> \
  --steps 256 --repetitions 5
```

Current Windows MSVC Release evidence:

```text
workload       backend    median_seconds  steps_per_second  peak_rss_bytes
digest         python     0.008116300     31541.466         23707648
digest         native-ffi 0.011194500     22868.373         24162304
metabolism     python     0.013329900     19204.945         24199168
metabolism     native-ffi 0.009594500     26681.953         24379392
structure      python     0.016554800     15463.793         24416256
structure      native-ffi 0.005885100     43499.686         24518656
division       python     0.001250600     204701.745        24522752
division       native-ffi 0.007302900     35054.567         24645632
```

These are checkpoint workload measurements, not end-to-end simulator claims.
The division row measures the explicit native step-plus-division ABI and the
corresponding reference checkpoint; filesystem, corpse, full sandbox event
ordering, and parallel scheduling remain outside this matrix.
