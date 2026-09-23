# Conservation audit

## Scope

Prompt 6 requires division and reproduction to be checked independently of the
implementations. The Python reference remains the semantic authority, while
the C core now exposes a selected-region partition transaction and viability
plan. This checkpoint audits both implementations and keeps full lifecycle
integration open.

## Required transaction equation

For a committed skeleton partition, dynamic structural material must satisfy:

```text
created structural mass + inherited transferred-in mass
= parent dynamic mass after
  + child dynamic mass
  + resorbed/gut mass
  + transferred-out accounting
```

External FOOD is a separate ledger:

```text
input mass = assimilated mass + expelled external mass + external gut mass
```

Division must also preserve evidence/strength by transfer rather than copying,
charge birth cost only to the parent, initialize child reserve to zero, and
leave parent and child structure objects unaliased.

## Python evidence

The existing regression suites cover the reference transaction, including:

- cross-split relation/composite structures;
- parent/child body mass and strength conservation;
- child reserve zero and parent birth-cost payment;
- failed division transactional rollback;
- repeated/nested divisions and world material totals;
- no duplicate object identity after partition.

The independent cross-split audit distinguishes living structural mass from
resorbed material already present in the gut. Its verified equation is
`created = living_after + resorbed`; adding gut mass to `living_after` would
count the same resorbed material twice.

The native division fixture now checks this equation independently after the
partition transaction, using parent and child dynamic mass plus parent
resorption. The `structural_transferred_out` ledger field is intentionally not
added to this physical equation because the transferred mass is already
included in the child's dynamic mass.
The same fixture now performs a second-generation partition and repeats the
independent equation for the intermediate parent and grandchild.
It also includes a dense eight-atom case with five relations, five composites,
and both internal and cross-split edges; the parent/child equation and both
per-organism validators pass after that transaction.
The Python/C differential suite additionally covers an eight-byte dense
partition and checks the native ledger equation independently of the Python
body-mass result.

The native division test now adds 32 deterministic adversarial partitions with
4–8 atoms, mixed relation/composite chains, an additional cross edge, high
reserve, and varying strengths. Each case checks the independent dynamic-mass
equation before calling either implementation's validator; MSVC Debug and
GCC Release strict builds pass the campaign.

`tests/test_skeleton_division.py`, `tests/test_structural_mass.py`, and
`tests/test_material_flow.py` are the current evidence set. The new canonical
oracle includes structural state and material-flow counters, so future native
differential failures can identify the first conservation field.

The native boundary also exposes the read-only local reproduction component
selector used before a committed partition. It matches the Python weakest-
member/component ordering on the bounded differential fixture and has a
maximum-capacity isolated-component regression; selection itself mutates no
material or reserve state.

## Native status

`PARTIAL / NOT READY`: C exposes an independent material-conservation validator and a
selected-region partition transaction. The transaction transfers internal
atoms/edges without cloning, routes cross-split edge mass to parent resorption,
charges parent birth cost, initializes child reserve to zero, splits territory,
and records transferred mass. GCC/MSVC tests cover cross-split, minimum-body,
zero-reserve, and transactional-rejection fixtures. The deterministic two-way
boundary selector and native energy/maintenance viability plan are also ported
and tested; the independent adversarial partition campaign and bounded Python/C
differential comparison now pass. The native gate remains open because the
complete sandbox/world lifecycle and environment-event comparison are not yet
owned by the C core.

Required native fixtures before full integration (all currently covered by the
bounded native campaign):

- minimum body, large body, no composites, many composites;
- dense and cross-split-heavy graphs;
- zero/high reserve, weak/equal members;
- repeated and deep-generation division;
- failed candidate rollback.
