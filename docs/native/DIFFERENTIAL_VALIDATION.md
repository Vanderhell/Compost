# Differential validation

## Current harness

`tests/test_native_differential.py` is an explicit ctypes differential harness
for the native units that currently have matching Python reference functions:

- structural mass;
- lazy metabolism composition;
- reproduction eligibility and score.

The test requires `COMPOST_NATIVE_LIBRARY`. If the variable is absent it is
skipped; if it names a missing file the test fails. There is no silent native
to Python fallback.

## Current status

The full per-step Python/C campaign is **NOT READY**. The native organism is
not yet a complete lifecycle engine, and this environment currently does not
provide a Python interpreter for executing the Python suite. No 1,000,000-step
claim is made. The selected partition transaction has native conservation
fixtures, but has not yet been compared field-by-field against the Python
division transaction.

The native-only paired replay test now executes 10,000 deterministic steps and
compares state digests and step counters after every step. It is a determinism
regression gate, not a substitute for Python/reference differential evidence.

## Acceptance requirement

Before the final audit, the campaign must record seed, configuration, logical
step count, both canonical digests, and the first divergent field for each
case. A final acceptance run requires zero unexplained behavioral divergences.
