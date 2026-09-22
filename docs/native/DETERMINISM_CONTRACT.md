# Determinism contract

## Required guarantee

For equal validated configuration, initial behavioral state, logical environment
inputs, and explicit step order, the Python reference and future C core must
produce equal behavioral snapshots after every logical step. Equality means
value-for-value under `STATE_MODEL.md`; it does not mean telemetry or physical
filesystem byte identity.

## Inputs that must be explicit

- Configuration and all numeric constants.
- Initial organisms and lineage IDs.
- Logical food bytes/nutrition and source digest.
- Food claim order and absolute positions.
- Corpse energy and territory paths.
- Population step order. The reference currently uses sorted numeric IDs for
  the population lifecycle path.
- Any deterministic seed used by the food navigation mapping.

The core must not read clocks, random globals, environment variables, process
IDs, filesystem enumeration order, thread scheduling, or Python hash values.

## Ordering rules

- Organisms: ascending numeric ID.
- Atoms: canonical symbol/key order.
- Pairs: tuple/key lexicographic order.
- Sets: sorted before traversal or serialization.
- Food positions: ascending absolute position.
- Heap choices: reproduce the complete Python key, including explicit serial
  tie-breaks; never use pointer order.
- Events: emitted and applied in defined transition order, not queue arrival
  order.

## Numeric rules

Python currently uses arbitrary-size integers, binary floating point, `min`/`max`,
ordered `sum`, proportional nutrition allocation, decay powers, and a final
residual claimant. Native integer widths, overflow policy, float operation order,
rounding mode, finite-value policy, and residual handling must be specified per
function before porting. Signed overflow is never an accepted behavior.

The reference's residual allocation and comparison tolerances are semantics,
not implementation details. Native tests must compare intermediate fields and
the first divergent step, not only final totals.

## Failure semantics

Invalid input, impossible lifecycle transitions, resource exhaustion, and
serialization errors are observable failures. A native operation must return an
explicit status and document whether state/output is unchanged. It must not
abort for an expected error and must not silently substitute Python behavior.

## Parallelism

The single-organism contract is deterministic independently of scheduling. The
existing multiprocessing runtime is an execution host and telemetry producer;
its wall-clock snapshots are not behavioral replay inputs. Any future parallel
mode must define deterministic epochs and ownership/message ordering, or be
advertised separately as throughput-only and non-reproducible.

## Acceptance evidence

Before ABI integration, the migration needs canonical Python snapshots, compact
fixtures covering feeding, metabolism, weakening, material flow, division,
death, corpses, territory, and boundary sizes, followed by per-step Python/C
comparisons. A final digest match without the first-divergence location is not
sufficient evidence.
