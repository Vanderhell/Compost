# Differential validation

## Current harness

`tests/test_native_differential.py` is an explicit ctypes differential harness
for the native units that currently have matching Python reference functions:

- structural mass;
- activity costs, forgetting, and maintenance weakening budget;
- lazy metabolism composition;
- reproduction eligibility and score;
- territory address/contains predicates and deterministic FOOD block keys;
- bounded external-gut FIFO processing against the sandbox oracle;
- a bounded simple lifecycle replay comparing native snapshot fields after each step.

Replay parameters are stored in the compact
`tests/fixtures/native_replays.json` manifest and are consumed by the harness.
It records the deterministic seed, payload patterns, population size, native
configuration boundary, and logical cycle count rather than relying only on
values duplicated in test code.

The test requires `COMPOST_NATIVE_LIBRARY`. If the variable is absent it is
skipped; if it names a missing file the test fails. There is no silent native
to Python fallback. The current bounded campaign contains twenty-nine tests,
including forty deterministic lifecycle replays (10,240 aggregate steps)
with field-by-field snapshot checks.

## Current status

The full per-step Python/C campaign is **NOT READY**. The native organism is
not yet a complete lifecycle engine. The current native-backed Python run is
green (`29 passed`), and the complete Python regression suite is green
(`222 passed, 3 subtests passed`). The selected partition
transaction now has a bounded Python/sandbox comparison, but the automatic
candidate policy is not yet fully integrated. The native checkpoint now
includes deterministic starvation removal, dead-step no-ops, and bounded
external-gut FIFO payload processing, and environment-supplied corpse-energy
credit; sandbox-level corpse lookup/storage and full division-policy campaign
remain open.

The campaign also includes a two-organism, sixty-four-cycle population boundary
case. Python performs deterministic nutrition allocation and supplies each
native handle's ordered bite; native snapshots are compared after every logical
organism transition. This validates orchestration at the bounded core boundary,
including empty-input lifecycle steps after the food stream is exhausted, not
filesystem or native parallel scheduling. The case now runs through the
reusable `NativePopulationBackend`, including deterministic handle ownership
and per-organism conservation checks.
It also verifies child registration and parent/child state after an allowed
division.

The native-only paired replay test now executes 10,000 deterministic steps and
compares state digests and step counters after every step. It is a determinism
regression gate, not a substitute for Python/reference differential evidence.

The current Python/reference campaign executes 40 deterministic payload
scenarios for 256 cycles each, for `10,240` aggregate steps. It compares
cursor, lifecycle status, age, body counts/mass, reserve, atoms, relations,
and composites after every step. This is bounded to the migrated
single-organism checkpoint and is not the required 1,000,000-step
full-population acceptance campaign.

A long-run replay was executed locally against the current ABI v3 MSVC Release
native DLL with `COMPOST_DIFFERENTIAL_CYCLES=25000`. It covered the same 40
deterministic scenarios for exactly `1,000,000` aggregate Python/native steps
and passed in `429.75s` with zero divergences. This is strong single-organism evidence, but
it is not yet the full population, sandbox environment, corpse, or
parallel-runtime campaign.

When a field comparison fails, the assertion reports the first divergent
field together with the Python `canonical_digest` and the native ABI
`state_digest` from that same logical step. The evidence message is lazy, so
successful campaigns do not pay the digest-construction cost.

## Acceptance requirement

Before the final audit, the campaign must record seed, configuration, logical
step count, both state digests, and the first divergent field for each case. A
final acceptance run requires zero unexplained behavioral divergences. The
native digest is currently an ABI-defined state digest rather than a claim
that the incomplete native lifecycle already implements the full Python
canonical schema.
