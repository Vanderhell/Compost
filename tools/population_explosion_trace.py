from __future__ import annotations

"""Measure, without changing, the lifecycle model's alternating-stream growth.

The payload is one immutable sequence held by ``MathematicalLifePopulation``.
This tool deliberately does not introduce shared-food accounting: it records
the consequence of the existing rule that every living organism may digest the
same remaining suffix independently.
"""

import argparse
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.life_experiments import payloads  # noqa: E402
from mathematical_organism.lifecycle import MathematicalLifeOrganism, MathematicalLifePopulation, OrganismStatus  # noqa: E402


def _vectors(organism: MathematicalLifeOrganism) -> dict[str, float]:
    """Return canonical strength vectors; reserve belongs to the organism."""
    strength: dict[str, float] = {}
    for kind, collection in (
        ("ATOM", organism.atoms),
        ("RELATION", organism.relations),
        ("COMPOSITE", organism.composites),
    ):
        for key, item in collection.items():
            identity = f"{kind}:{key!r}"
            strength[identity] = item.strength
    return strength


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    dot = sum(left.get(key, 0.0) * right.get(key, 0.0) for key in set(left) | set(right))
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 1.0 if left_norm == right_norm else 0.0
    return dot / (left_norm * right_norm)


def similarity(parent: MathematicalLifeOrganism | None, child: MathematicalLifeOrganism | None) -> dict[str, object]:
    """Compare only current derived structures; it never stores payload history."""
    if parent is None or child is None:
        return {"available": False, "reason": "organism missing"}
    parent_strength = _vectors(parent)
    child_strength = _vectors(child)
    parent_keys = set(parent_strength)
    child_keys = set(child_strength)
    union = parent_keys | child_keys
    return {
        "available": True,
        "parent_alive": parent.status is OrganismStatus.ALIVE,
        "child_alive": child.status is OrganismStatus.ALIVE,
        "same_cursor": parent.cursor == child.cursor,
        "parent_cursor": parent.cursor,
        "child_cursor": child.cursor,
        "topology_jaccard": len(parent_keys & child_keys) / len(union) if union else 1.0,
        "strength_cosine": _cosine(parent_strength, child_strength),
        "parent_reserve": parent.reserve,
        "child_reserve": child.reserve,
        "parent_size": parent.size,
        "child_size": child.size,
    }


def cycle_row(population: MathematicalLifePopulation) -> dict[str, object]:
    organisms = tuple(population.organisms.values())
    alive = tuple(item for item in organisms if item.status is OrganismStatus.ALIVE)
    return {
        "cycle": population.result.cycles,
        "data_position": max((item.cursor for item in alive), default=len(population.payload)),
        "alive_population": len(alive),
        "total_population_born": len(organisms),
        "population_reserve": sum(item.reserve for item in alive),
        "total_population_strength": sum(item.total_strength for item in alive),
        "total_consumed": sum(item.consumed_total for item in organisms),
        "total_assimilated": sum(item.assimilated_total for item in organisms),
        "total_waste": sum(item.waste_total for item in organisms),
    }


def trace(*, length: int, birth_limit: int, max_cycles: int) -> dict[str, object]:
    if length <= 0 or birth_limit <= 0 or max_cycles <= 0:
        raise ValueError("length, birth_limit, and max_cycles must be positive")
    population = MathematicalLifePopulation(payloads(length)["alternating"])
    cycles: list[dict[str, object]] = []
    observations: dict[int, dict[str, object]] = {}
    offsets = (0, 1, 2, 4, 8)

    while population.result.cycles < max_cycles:
        before_births = len(population.result.births)
        population.cycle()
        cycles.append(cycle_row(population))

        for event in population.result.births[before_births:]:
            if event.birth_index > birth_limit:
                continue
            parent = population.organisms[event.parent_id]
            child = population.organisms[event.child_id]
            observations[event.birth_index] = {
                "event": asdict(event),
                "birth_cycle": population.result.cycles,
                "same_future_payload_at_birth": parent.cursor == child.cursor,
                "similarity": {"0": similarity(parent, child)},
            }

        for entry in observations.values():
            elapsed = population.result.cycles - int(entry["birth_cycle"])
            if elapsed in offsets and str(elapsed) not in entry["similarity"]:
                event = entry["event"]
                entry["similarity"][str(elapsed)] = similarity(
                    population.organisms.get(int(event["parent_id"])),
                    population.organisms.get(int(event["child_id"])),
                )

        active_stream = any(
            item.status is OrganismStatus.ALIVE and item.cursor < len(population.payload)
            for item in population.organisms.values()
        )
        pending_similarity = any(
            population.result.cycles < int(entry["birth_cycle"]) + max(offsets)
            for entry in observations.values()
        )
        if not active_stream and not pending_similarity:
            break

    first_births = [observations[index] for index in sorted(observations)]
    final = cycle_row(population)
    unique_data_positions = max((int(row["data_position"]) for row in cycles), default=0)
    return {
        "payload": {"kind": "alternating_blocks", "length": length, "block_length": 24},
        "config": asdict(population.config),
        "cycles": cycles,
        "first_births": first_births,
        "final": final,
        "stream_positions_available": len(population.payload),
        "unique_data_positions_reached": unique_data_positions,
        "exposure_multiplier": final["total_consumed"] / unique_data_positions if unique_data_positions else 0.0,
        "births_recorded": len(first_births),
        "births_total": len(population.result.births),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--length", type=int, default=240)
    parser.add_argument("--birth-limit", type=int, default=30)
    parser.add_argument("--max-cycles", type=int, default=800)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "population-explosion-trace.json")
    args = parser.parse_args()
    result = trace(length=args.length, birth_limit=args.birth_limit, max_cycles=args.max_cycles)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "births_recorded": result["births_recorded"],
        "births_total": result["births_total"],
        "final": result["final"],
        "exposure_multiplier": result["exposure_multiplier"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
