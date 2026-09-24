# Behavioral state model

## Scope

This is the proposed value-for-value state contract for the lifecycle core.
Fields marked derived are not authoritative, but their recomputation must be
deterministic and they may be checked as invariants. Telemetry is excluded.

## Configuration

The snapshot includes every `LifecycleConfig` value, in declared field order:

`bite_minimum`, `atom_income`, `relation_income`, `composite_income`,
`atom_maintenance`, `relation_maintenance`, `composite_maintenance`,
`atom_formation_cost`, `relation_formation_cost`,
`consolidation_formation_cost`, `birth_cost`, `division_horizon`,
`boundary_ratio_limit`, `income_decay`, `novelty_affinity`, `birth_reserve`,
`metabolic_minimum_work`, and `reproduction_minimum_body`.

## Organism snapshot

Serialize one organism as a tagged, versioned record containing:

- identity: `id`, `parent_id` or null, `birth_position`, `generation`;
- progression: `cursor`, `age_in_cycles`, `status`, `death_age` or null;
- reserve and body: `reserve`, `body_mass`, `size`, `peak_strength`, `peak_age`,
  `first_consolidation_age` or null;
- counters: `consumed_total`, `assimilated_total`, `waste_total`,
  `nutrition_consumed_total`, and `children_created`;
- receptors: fixed receptor domain and sorted `activated_receptors`;
- sorted atoms, relations, and composites. Each entry contains its canonical key,
  kind, strength, maintenance, evidence, income rate, members, and
  `last_metabolic_epoch`;
- activity ledger: all activity counters, `metabolic_debt`, `energy_spent`,
  and `settlements`;
- gut: FIFO chunks with mass, origin, payload bytes, and nutrition values;
- material flow: all integer totals in `MaterialFlow`;
- metabolic state: progress, current epoch, deficit, deficit total, paid total,
  weakening-event count, and full-scan count where those counters are part of
  the current reference transition.

Indexes such as the weakness heap, adjacency, incident lists, and maintenance
cache are exported only in a separate invariant section or rebuilt and checked;
they are not independent behavioral authorities. If a cache changes the
reference decision, its canonical source values and deterministic tie-breaks
must be included and the cache must be validated against them.

## World/environment snapshot

For a population comparison, include:

- logical cycle and next organism ID;
- organisms sorted by numeric ID;
- remaining nutrition per absolute payload position;
- ordered environment events/requests applied at the step boundary;
- corpse entries sorted by canonical territory path, with remaining energy and
  source identity;
- territory states sorted by organism tree ID: path, local birth counter, and
  alive flag;
- material/conservation totals.

Physical paths, file mtimes, worker IDs, process IDs, queue timing, and
telemetry timestamps are excluded. If a file source matters behaviorally, use a
stable source digest and logical byte/block content, not an OS path.

## Canonical encoding

The future Python oracle and C exporter must use the same schema, explicit field
names, stable type tags, sorted map/set entries, and a defined float encoding.
The preferred initial float encoding is exact IEEE-754 binary64 bit patterns
with explicit handling for signed zero, NaN, and infinity; every behavioral
configuration used by a reference organism is included in the canonical
snapshot. Normal simulation values should reject non-finite values. No `repr`, pointer,
object ID, address, unordered iteration, or locale-dependent formatting may
appear in the digest.

## Native import readiness

The C `compost_snapshot_t` is sufficient for native-to-native diagnostics and
the currently implemented bounded transitions. The Python adapter can now
transactionally import the C-representable subset of an evolved
`AutonomousOrganism`: body structures, reserve, lifecycle scalars, activity
and material ledgers, gut FIFO, receptors, territory path, and metabolic
backlog. Python name/birth metadata, cache validity and tie-break indexes,
navigation cursors, lifecycle diagnostics, and world-owned FOOD/corpse state
remain host-owned. They are not silently serialized into the native handle;
native-first planning must receive them explicitly or remain Python-owned.

## Legacy graph snapshot

The separate `MathematicalOrganism.snapshot()` contract must retain sorted nodes,
transitions, contexts, decayed values at the requested time, candidates, and
configuration where used. It is not silently merged with the lifecycle
snapshot. Its `LatticeGraph` atom/semantic indexes and candidate dictionary are
behavioral through IDs and rule selection; indexes must be validated against
sorted authoritative entries.
