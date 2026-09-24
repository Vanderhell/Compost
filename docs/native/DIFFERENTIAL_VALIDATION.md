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
to Python fallback. The current bounded campaign contains seventy-five tests,
including forty deterministic lifecycle replays (10,240 aggregate steps), a
differential configuration matrix (144 additional steps), a
differential starvation/death replay, a dense cross-split division replay, and
field-by-field snapshot checks.

## Current status

The full per-step Python/C campaign is **NOT READY**. The native organism is
not yet a complete lifecycle engine. The current native-backed differential
run is green (`75 passed`; the focused oracle/member-weakness validation run
is `75 passed` including the related Python tests), and the complete Python regression suite is green
(`272 passed, 3 subtests passed` in the latest ABI v4 run). The selected partition
transaction now has a bounded Python/sandbox comparison, and both native
reproduction policies are selected by the sandbox adapter and compared with
the Python child atom set. The native checkpoint now
includes deterministic starvation removal, dead-step no-ops, and bounded
external-gut FIFO payload processing, and environment-supplied corpse-energy
credit; filesystem environment selection, persistence, and complete event
ordering remain Python-owned, while native corpse snapshots are checked
against the Python corpse state at replay epochs.

The campaign also includes a two-organism, 256-cycle population boundary
case. Python performs deterministic nutrition allocation and supplies each
native handle's ordered bite; native snapshots are compared after every logical
organism transition. This validates orchestration at the bounded core boundary,
including empty-input lifecycle steps after the food stream is exhausted, not
filesystem or native parallel scheduling. The case now runs through the
reusable `NativePopulationBackend`, including deterministic handle ownership
and per-organism conservation checks.
It also verifies child registration, parent/child state after an allowed
division, and an eight-cycle division/death replay where the child becomes
dead while the parent remains alive.
The reusable sandbox epoch comparison now checks metabolic progress and
settled metabolic-step count at every checkpoint, so a future scheduling
divergence is reported at its first epoch rather than only at final state.
Host action observers additionally capture post-mutation Python states for
each native-replay action boundary; progress plus an immediately due lifecycle
checkpoint is intentionally compared as one scheduling group because the two
implementations commit the remainder at different intermediate points.
The metabolic progress accumulator reports due work without pre-crediting
completed lifecycle steps; only a successful non-dead lifecycle checkpoint
increments the settled step counter. A regression covers due work queued before
a dead stop.
Single-handle action traces are also transactional: an injected failure after
an earlier native action restores the exact opaque snapshot before the trace.
The sandbox replay boundary additionally closes a failed replay object after
native rollback, because the Python oracle has already been advanced while the
trace is being built and cannot safely be retried from the restored C state.
The bounded two-organism campaign also compares every relation and composite
key and its strength/evidence/income fields after each ordered epoch.

The native-only paired replay test now executes 10,000 deterministic steps and
compares state digests and step counters after every step. It is a determinism
regression gate, not a substitute for Python/reference differential evidence.

The native due-lifecycle batch endpoint is compared against the same number of
repeated single lifecycle calls from an exact native snapshot. The comparison
checks the complete native snapshot and state digest, including the dead-state
and zero-step status contract at the C ABI boundary.
The population adapter also runs these batches in ascending organism-ID order
with epoch-wide ID/count preflight, exact cross-handle rollback on execution
failure, atomic direct reproduction/partition child registration, strict
preflight before native capture, and
per-population conservation validation.

The current Python/reference campaign executes 40 deterministic payload
scenarios for 256 cycles each, for `10,240` aggregate steps, plus a three-case
configuration matrix for `144` additional steps. It compares
cursor, lifecycle status, age, body counts/mass, reserve, atoms, relations,
and composites after every step. This is bounded to the migrated
single-organism checkpoint and is not the required 1,000,000-step
full-population acceptance campaign.

A long-run replay was executed locally against the current ABI v4 MSVC Release
native DLL with `COMPOST_DIFFERENTIAL_CYCLES=25000`. It covered the same 40
deterministic scenarios for exactly `1,000,000` aggregate Python/native steps
and passed in `408.41s` with zero divergences. This is strong single-organism evidence, but
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

The long sandbox lifecycle regression runs 100 deterministic food-fed steps
and compares reserve, age, body mass, material-flow counters, all activity
counters, activity debt, energy spent, and settlement count after every step.
It covers both lifecycle-checkpoint settlement and the separate post-gut
settlement path.
An additional no-food replay covers repeated idle gut processing and
Python-owned corpse-energy selection through the explicit action boundary.

The multi-epoch sandbox action-trace campaign runs 128 deterministic epochs
through `NativePopulationBackend`. It compares parent and child state after
each epoch, including territory, material-flow accounting, activity counters,
activity debt, energy spent, settlements, ordered gut chunks, metabolic
progress, metabolic step count, generation, and activated receptors. The
campaign also exercises explicit corpse transfer and child-handle retention. Filesystem
FOOD selection and host event ordering remain Python-owned; the body cursor is
an adapter diagnostic and is intentionally not treated as behavioral state in
this campaign.
The replay parameters are declared in the `sandbox_trace` entry of
`tests/fixtures/native_replays.json`; assertion messages lazily include the
first field name plus Python canonical and native state digests.
The reusable adapter additionally compares every shared native/Python field
after each live epoch: lifecycle status, body structures and values, reserve,
gut FIFO, receptors, territory, material flow, and activity ledger/counters.
Its failure names the first divergent field; Python-only navigation, caches,
filesystem ownership, telemetry, native numeric-handle parent identity, and
the legacy body cursor remain explicitly outside this boundary. The cursor is
advanced by the native byte-digestion model but is not the Python sandbox's
physical FOOD cursor; comparing it here would report a false divergence.
