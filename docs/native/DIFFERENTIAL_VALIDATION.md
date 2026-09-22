# Differential validation

## Current harness

`tests/test_native_differential.py` is an explicit ctypes differential harness
for the native units that currently have matching Python reference functions:

- structural mass;
- lazy metabolism composition;
- reproduction eligibility and score;
- a bounded simple lifecycle replay comparing native snapshot fields after each step.

The test requires `COMPOST_NATIVE_LIBRARY`. If the variable is absent it is
skipped; if it names a missing file the test fails. There is no silent native
to Python fallback. The current bounded campaign contains five tests,
including an eight-step lifecycle replay with field-by-field snapshot checks.

## Current status

The full per-step Python/C campaign is **NOT READY**. The native organism is
not yet a complete lifecycle engine. The current native-backed Python run is
green (`5 passed`), and the complete Python regression suite is green
(`189 passed, 6 skipped, 3 subtests passed`), but the selected partition
transaction has not yet been compared field-by-field against the Python
division transaction. The bounded replay deliberately uses a long first food
stream so starvation-driven structural removal is outside this checkpoint's
current native scope; the full starvation/gut/division campaign remains open.

The native-only paired replay test now executes 10,000 deterministic steps and
compares state digests and step counters after every step. It is a determinism
regression gate, not a substitute for Python/reference differential evidence.

## Acceptance requirement

Before the final audit, the campaign must record seed, configuration, logical
step count, both canonical digests, and the first divergent field for each
case. A final acceptance run requires zero unexplained behavioral divergences.
