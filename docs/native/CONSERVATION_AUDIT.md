# Conservation audit

## Scope

Prompt 6 requires division and reproduction to be checked independently of the
implementations. The current Python reference is the only implementation with
division semantics; the C core does not yet expose division. Therefore this
checkpoint audits the Python transaction and records the native gate as open.

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

`tests/test_skeleton_division.py`, `tests/test_structural_mass.py`, and
`tests/test_material_flow.py` are the current evidence set. The new canonical
oracle includes structural state and material-flow counters, so future native
differential failures can identify the first conservation field.

## Native status

`NOT READY`: C now exposes an independent material-conservation validator and a
selected-region partition transaction. The transaction transfers internal
atoms/edges without cloning, routes cross-split edge mass to parent resorption,
charges parent birth cost, initializes child reserve to zero, splits territory,
and records transferred mass. GCC/MSVC tests cover one cross-split fixture.
The deterministic two-way boundary selector is now also ported and tested;
energy/maintenance viability policy, adversarial fixture breadth, and Python/C
differential comparison remain pending, so the native gate is not allowed to
pass yet.

Required native fixtures before integration:

- minimum body, large body, no composites, many composites;
- dense and cross-split-heavy graphs;
- zero/high reserve, weak/equal members;
- repeated and deep-generation division;
- failed candidate rollback.
