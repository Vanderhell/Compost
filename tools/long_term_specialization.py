from __future__ import annotations

"""Observe specialization without changing lifecycle decisions or food rules."""

import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.life_experiments import payloads  # noqa: E402
from mathematical_organism.lifecycle import MathematicalLifeOrganism, MathematicalLifePopulation, OrganismStatus  # noqa: E402


LENGTHS = (10_000, 50_000, 100_000)
OFFSETS = (0, 10, 100, 1_000, 10_000)
SYMBOLS = ("A", "B")


def _items(organism: MathematicalLifeOrganism) -> dict[str, float]:
    values: dict[str, float] = {}
    for kind, collection in (("ATOM", organism.atoms), ("RELATION", organism.relations), ("COMPOSITE", organism.composites)):
        for key, item in collection.items():
            values[f"{kind}:{key!r}"] = item.strength
    return values


def _relations(organism: MathematicalLifeOrganism) -> dict[str, float]:
    values: dict[str, float] = {}
    for kind, collection in (("RELATION", organism.relations), ("COMPOSITE", organism.composites)):
        for key, item in collection.items():
            values[f"{kind}:{key!r}"] = item.strength
    return values


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    dot = sum(left.get(key, 0.0) * right.get(key, 0.0) for key in keys)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return 1.0 if left_norm == right_norm == 0.0 else (dot / (left_norm * right_norm) if left_norm and right_norm else 0.0)


def _affinity(population: MathematicalLifePopulation, organism: MathematicalLifeOrganism) -> dict[str, float]:
    return {symbol: population._food_affinity(organism, symbol) for symbol in SYMBOLS}


def organism_row(population: MathematicalLifePopulation, organism: MathematicalLifeOrganism) -> dict[str, object]:
    structures = sorted(_items(organism).items(), key=lambda pair: (-pair[1], pair[0]))
    relations = sorted(_relations(organism).items(), key=lambda pair: (-pair[1], pair[0]))
    return {
        "id": organism.id,
        "parent_id": organism.parent_id,
        "generation": organism.generation,
        "age": organism.age_in_cycles,
        "size": organism.size,
        "status": organism.status.value,
        "total_strength": organism.total_strength,
        "reserve": organism.reserve,
        "consumed": organism.exposure_total,
        "assimilated": organism.assimilated_total,
        "waste": organism.waste_total,
        "nutrition_received": organism.nutrition_consumed_total,
        "top_structures": structures[:8],
        "top_relations": relations[:8],
        "affinity_profile": _affinity(population, organism),
    }


def pair_similarity(population: MathematicalLifePopulation, parent_id: int, child_id: int) -> dict[str, object]:
    parent = population.organisms.get(parent_id)
    child = population.organisms.get(child_id)
    if parent is None or child is None:
        return {"available": False}
    parent_structures = _items(parent)
    child_structures = _items(child)
    parent_relations = _relations(parent)
    child_relations = _relations(child)
    parent_affinity = _affinity(population, parent)
    child_affinity = _affinity(population, child)
    union = set(parent_structures) | set(child_structures)
    relation_union = set(parent_relations) | set(child_relations)
    return {
        "available": True,
        "parent_alive": parent.status is OrganismStatus.ALIVE,
        "child_alive": child.status is OrganismStatus.ALIVE,
        "same_cursor": parent.cursor == child.cursor,
        "structure_jaccard": len(set(parent_structures) & set(child_structures)) / len(union) if union else 1.0,
        "structure_weight_cosine": _cosine(parent_structures, child_structures),
        "relation_jaccard": len(set(parent_relations) & set(child_relations)) / len(relation_union) if relation_union else 1.0,
        "relation_weight_cosine": _cosine(parent_relations, child_relations),
        "affinity_cosine": _cosine(parent_affinity, child_affinity),
        "parent_affinity": parent_affinity,
        "child_affinity": child_affinity,
        "parent_nutrition": parent.nutrition_consumed_total,
        "child_nutrition": child.nutrition_consumed_total,
    }


def population_row(population: MathematicalLifePopulation) -> dict[str, object]:
    alive = population.alive()
    all_organisms = tuple(population.organisms.values())
    return {
        "cycle": population.result.cycles,
        "max_data_position": max((item.cursor for item in alive), default=len(population.payload)),
        "alive_population": len(alive),
        "total_born": len(all_organisms),
        "total_dead": sum(item.status is OrganismStatus.DEAD for item in all_organisms),
        "divisions": len(population.result.births),
        "population_reserve": sum(item.reserve for item in alive),
        "population_strength": sum(item.total_strength for item in alive),
        "individuals": [organism_row(population, item) for item in sorted(alive, key=lambda item: item.id)],
    }


def run(length: int, *, sample_every: int = 100) -> dict[str, object]:
    population = MathematicalLifePopulation(payloads(length)["alternating"])
    samples: list[dict[str, object]] = []
    comparisons: dict[str, dict[str, object]] = {}
    pair: tuple[int, int, int] | None = None
    max_cycles = length * 3
    while population.result.cycles < max_cycles and population.alive():
        before_births = len(population.result.births)
        population.cycle()
        if len(population.result.births) > before_births and pair is None:
            birth = population.result.births[before_births]
            pair = (birth.parent_id, birth.child_id, population.result.cycles)
        if population.result.cycles % sample_every == 0 or len(population.result.births) > before_births:
            samples.append(population_row(population))
        if pair is not None:
            parent_id, child_id, birth_cycle = pair
            elapsed = population.result.cycles - birth_cycle
            if elapsed in OFFSETS:
                comparisons[str(elapsed)] = pair_similarity(population, parent_id, child_id)
        active_stream = any(item.status is OrganismStatus.ALIVE and item.cursor < len(population.payload) for item in population.organisms.values())
        offsets_done = pair is None or all(str(offset) in comparisons for offset in OFFSETS)
        if not active_stream and offsets_done:
            break

    return {
        "length": length,
        "stream": "24 A symbols then 24 B symbols, repeated deterministically",
        "sample_every": sample_every,
        "samples": samples,
        "comparisons": comparisons,
        "final": population_row(population),
        "births": [
            {"parent_id": item.parent_id, "child_id": item.child_id, "position": item.data_position, "cycle": pair[2] if pair and item.child_id == pair[1] else None}
            for item in population.result.births
        ],
        "available_nutrition": population.result.available_nutrition_total,
        "consumed_nutrition": population.result.consumed_nutrition_total,
        "nutrition_created": population.result.nutrition_created_total,
    }


def main() -> int:
    results = [run(length) for length in LENGTHS]
    output = PROJECT_ROOT / "long-term-specialization-results.json"
    output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "summary": [
            {"length": item["length"], **{key: item["final"][key] for key in ("alive_population", "total_born", "total_dead", "divisions", "population_reserve", "population_strength")}}
            for item in results
        ],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
