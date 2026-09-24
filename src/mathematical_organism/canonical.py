"""Canonical behavioral snapshots for the Python reference implementation.

The output is deliberately made only from immutable tuples, strings, integers,
booleans, and tagged binary64 values.  It is an oracle format, not a telemetry
format: diagnostics, object identity, timing, and filesystem paths are omitted.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import fields
from enum import Enum
from typing import Any

from .lifecycle import MathematicalLifeOrganism, MathematicalLifePopulation
from .model import LatticeGraph
from .organism import MathematicalOrganism
from .sandbox_runtime import AutonomousOrganism, SandboxRuntime


# Version 2 includes the behaviorally relevant AutonomousOrganism config in
# its canonical state. Consumers must not compare digests across schemas.
SCHEMA_VERSION = 2


def _float(value: float) -> tuple[str, str]:
    """Encode binary64 bits, including signed zero, without locale or repr."""
    if not isinstance(value, float):
        raise TypeError(f"expected float, got {type(value).__name__}")
    return ("f64", struct.pack(">d", value).hex())


def _key(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple):
        return ("tuple", tuple(_key(item) for item in value))
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, int):
        return ("int", value)
    if value is None:
        return ("none",)
    raise TypeError(f"unsupported canonical key type: {type(value).__name__}")


def _config(config: Any) -> tuple[Any, ...]:
    return tuple((field.name, _value(getattr(config, field.name))) for field in fields(config))


def _value(value: Any) -> Any:
    if isinstance(value, float):
        return _float(value)
    if isinstance(value, Enum):
        return ("enum", type(value).__name__, value.value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, tuple):
        return tuple(_value(item) for item in value)
    if isinstance(value, list):
        return tuple(_value(item) for item in value)
    if isinstance(value, dict):
        return tuple(
            (_value(key), _value(item))
            for key, item in sorted(value.items(), key=lambda pair: repr(_value(pair[0])))
        )
    if isinstance(value, set):
        return tuple(sorted((_value(item) for item in value), key=repr))
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def _structure(structure: Any) -> tuple[Any, ...]:
    return (
        _key(structure.key),
        structure.kind,
        _float(structure.strength),
        _float(structure.maintenance),
        _float(structure.evidence),
        _float(structure.income_rate),
        _value(structure.members),
        structure.last_metabolic_epoch,
    )


def _structures(items: dict[Any, Any]) -> tuple[Any, ...]:
    return tuple(
        (_key(key), _structure(items[key]))
        for key in sorted(items, key=lambda item: repr(_key(item)))
    )


def _lifecycle_organism(organism: MathematicalLifeOrganism) -> tuple[Any, ...]:
    return (
        "lifecycle-organism",
        ("id", organism.id),
        ("parent_id", organism.parent_id),
        ("birth_position", organism.birth_position),
        ("generation", organism.generation),
        ("cursor", organism.cursor),
        ("atoms", _structures(organism.atoms)),
        ("relations", _structures(organism.relations)),
        ("composites", _structures(organism.composites)),
        ("receptors", tuple(organism.receptors)),
        ("activated_receptors", tuple(sorted(organism.activated_receptors))),
        ("body_mass", organism.body_mass),
        ("reserve", _float(organism.reserve)),
        ("maintenance_cache", _float(organism.maintenance_cache)),
        ("resource_cache_valid", organism.resource_cache_valid),
        ("age_in_cycles", organism.age_in_cycles),
        ("consumed_total", organism.consumed_total),
        ("assimilated_total", organism.assimilated_total),
        ("waste_total", organism.waste_total),
        ("nutrition_consumed_total", _float(organism.nutrition_consumed_total)),
        ("children_created", organism.children_created),
        ("status", _value(organism.status)),
        ("peak_strength", _float(organism.peak_strength)),
        ("peak_age", organism.peak_age),
        ("first_consolidation_age", organism.first_consolidation_age),
        ("death_age", organism.death_age),
    )


def _lifecycle_population(population: MathematicalLifePopulation) -> tuple[Any, ...]:
    result = population.result
    return (
        "lifecycle-population",
        ("payload", tuple(population.payload)),
        ("config", _config(population.config)),
        ("organisms", tuple(_lifecycle_organism(population.organisms[key]) for key in sorted(population.organisms))),
        ("next_id", population.next_id),
        ("max_population", population.max_population),
        ("nutrition_remaining", tuple(_float(value) for value in population._nutrition_remaining)),
        ("cycles", result.cycles),
        ("cycles_at_stream_end", result.cycles_at_stream_end),
        ("alive_at_stream_end", result.alive_at_stream_end),
        ("available_nutrition_total", _float(result.available_nutrition_total)),
        ("consumed_nutrition_total", _float(result.consumed_nutrition_total)),
        ("nutrition_created_total", _float(result.nutrition_created_total)),
    )


def _graph(graph: LatticeGraph, now: int, decay: float) -> tuple[Any, ...]:
    return _value(graph.snapshot(now, decay))


def _legacy_organism(organism: MathematicalOrganism) -> tuple[Any, ...]:
    return (
        "legacy-organism",
        ("config", _config(organism.config)),
        ("time", organism.time),
        ("graph", _graph(organism.graph, organism.time, organism.config.decay)),
        ("candidates", tuple(
            (_key(key), (
                candidate.kind.value,
                _value(candidate.signature),
                candidate.created_at,
                candidate.last_observed,
                _float(candidate.support.read(organism.time, organism.config.decay)),
                _value(candidate.status),
            ))
            for key, candidate in sorted(organism.candidates.items(), key=lambda item: repr(_key(item[0])))
        )),
    )


def _autonomous_organism(organism: AutonomousOrganism) -> tuple[Any, ...]:
    body = _lifecycle_organism(organism.body)
    gut = tuple(
        (chunk.mass, chunk.origin, tuple(chunk.payload), tuple(_float(value) for value in chunk.nutrition))
        for chunk in organism.gut_queue
    )
    navigation = tuple(
        (source, state.organism_id, state.seed, state.node_count, state.parcel_count,
         state.bite_index, state.round, state.index_in_round)
        for source, state in sorted(organism.navigation.items())
    )
    flow = tuple((field.name, getattr(organism.material_flow, field.name)) for field in fields(organism.material_flow))
    activity = (
        _float(organism.activity_ledger.metabolic_debt),
        _float(organism.activity_ledger.energy_spent),
        organism.activity_ledger.settlements,
        tuple((field.name, getattr(organism.activity_ledger.counters, field.name)) for field in fields(organism.activity_ledger.counters)),
    )
    territory = organism.territory_state
    return (
        "autonomous-organism",
        ("name", organism.name),
        ("config", _config(organism.config)),
        ("body", body),
        ("territory", (territory.organism_id, tuple(territory.territory.path), territory.local_birth_counter, territory.alive)),
        ("navigation", navigation),
        ("local_claim_counter", organism.local_claim_counter),
        ("biomass_consumed", _float(organism.biomass_consumed)),
        ("metabolic_progress", organism.metabolic_progress),
        ("metabolic_steps", organism.metabolic_steps),
        ("parent_name", organism.parent_name),
        ("activity", activity),
        ("gut", gut),
        ("material_flow", flow),
        ("current_metabolic_epoch", organism.current_metabolic_epoch),
        ("maintenance_deficit", _float(organism.maintenance_deficit)),
        ("maintenance_deficit_total", _float(organism.maintenance_deficit_total)),
        ("maintenance_paid_total", _float(organism.maintenance_paid_total)),
        ("weakening_events", organism.weakening_events),
        ("weakness_cache_valid", organism._weakness_cache_valid),
        ("weakest_weight", None if organism.weakest_weight is None else _float(organism.weakest_weight)),
        ("weakest_members", _value(organism.weakest_members)),
        ("member_weights", tuple((_key(key), _float(value)) for key, value in sorted(organism.member_weights.items(), key=lambda item: repr(_key(item[0]))))),
    )


def _runtime(runtime: SandboxRuntime) -> tuple[Any, ...]:
    corpses = tuple(
        (tuple(corpse.territory.path), _float(corpse.remaining_energy), corpse.source_organism_id)
        for corpse in sorted(runtime.corpses, key=lambda item: (item.territory.path, item.source_organism_id or ""))
    )
    return (
        "sandbox-runtime",
        ("block_size", runtime.block_size),
        ("food_sources", tuple(
            (name, food.source_hash, food.size, food.inbox_remaining, food.remaining,
             tuple((block_id, block.original_start, block.original_end)
                   for block_id, block in sorted(food.blocks.items())))
            for name, food in sorted(runtime.food_sources.items())
        )),
        ("organisms", tuple(_autonomous_organism(item) for item in sorted(runtime.organisms, key=lambda item: item.name))),
        ("corpses", corpses),
    )


def canonical_state(value: Any) -> tuple[Any, ...]:
    """Return an immutable behavioral snapshot for a supported reference value."""
    if isinstance(value, MathematicalLifePopulation):
        return ("canonical", SCHEMA_VERSION, _lifecycle_population(value))
    if isinstance(value, MathematicalOrganism):
        return ("canonical", SCHEMA_VERSION, _legacy_organism(value))
    if isinstance(value, AutonomousOrganism):
        return ("canonical", SCHEMA_VERSION, _autonomous_organism(value))
    if isinstance(value, SandboxRuntime):
        return ("canonical", SCHEMA_VERSION, _runtime(value))
    raise TypeError(f"unsupported canonical root type: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Serialize a canonical snapshot with one stable JSON encoding."""
    return json.dumps(canonical_state(value), ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


__all__ = ["SCHEMA_VERSION", "canonical_bytes", "canonical_digest", "canonical_state"]
