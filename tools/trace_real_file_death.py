from __future__ import annotations

"""Diagnostic-only trace of the unchanged real-file feeding lifecycle.

The tracer reproduces ``ImplicitFileFeedingHarness.step`` but places snapshots
between the existing lifecycle calls.  It does not alter claims, DIGEST,
maintenance, resorption, division, configuration, or organism state.
"""

import argparse
from dataclasses import dataclass, asdict
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.food import ImplicitFileFeedingHarness  # noqa: E402
from mathematical_organism.lifecycle import LifecycleEvent, MathematicalLifeOrganism, OrganismStatus  # noqa: E402


StructureKey = tuple[str, str]


@dataclass(frozen=True, slots=True)
class StructureState:
    strength: float
    maintenance: float


@dataclass(frozen=True, slots=True)
class CycleTrace:
    cycle: int
    file_offset: int | None
    claimed_region: int | None
    bite_capacity: int
    actual_bite_size: int
    consumed: int
    assimilated: float
    waste: float
    reserve_before: float
    nutrition_gained: float
    maintenance_paid: float
    reserve_after: float
    structure_count_before: int
    structure_count_after: int
    structures_created: int
    structures_strengthened: int
    structures_resorbed: int
    relations_created: int
    relations_strengthened: int
    relations_resorbed: int
    weakest_structure_strength: float | None
    strongest_structure_strength: float | None
    strength_one_created: int
    strength_one_survive_end_cycle: int
    strength_one_resorbed_immediately: int
    strength_one_created_previous_cycle_surviving: int
    funded_formation_cost_paid: float
    consolidations: int
    death_condition: str | None


def _snapshot(organism: MathematicalLifeOrganism) -> dict[StructureKey, StructureState]:
    """Numeric snapshot only; payload bytes are never retained in this trace."""
    result: dict[StructureKey, StructureState] = {}
    for kind, collection in (
        ("ATOM", organism.atoms),
        ("RELATION", organism.relations),
        ("COMPOSITE", organism.composites),
    ):
        for key, structure in collection.items():
            result[(kind, repr(key))] = StructureState(structure.strength, structure.maintenance)
    return result


def _count(items: set[StructureKey], kind: str) -> int:
    return sum(item[0] == kind for item in items)


def _maintenance_due(organism: MathematicalLifeOrganism) -> float:
    return min(organism.reserve, sum(item.maintenance for item in organism._structures()))


def trace(path: Path, *, seed: int, parcel_size: int, context_overlap: int) -> tuple[list[CycleTrace], ImplicitFileFeedingHarness]:
    harness = ImplicitFileFeedingHarness(path, seed=seed, parcel_size=parcel_size, context_overlap=context_overlap)
    population = harness.population
    rows: list[CycleTrace] = []
    pending_strength_one: set[StructureKey] = set()
    original_fund_cost = population._fund_cost
    funded_costs_this_cycle: list[float] = []

    def observed_fund_cost(organism: MathematicalLifeOrganism, cost: float) -> bool:
        result = original_fund_cost(organism, cost)
        if result:
            funded_costs_this_cycle.append(cost)
        return result

    # Observational wrapper: it delegates the exact existing funding operation.
    population._fund_cost = observed_fund_cost  # type: ignore[method-assign]
    while harness.food.remaining and population.alive():
        # The observed run has exactly one organism; retain deterministic ID order
        # so this remains a faithful diagnostic if a future input divides.
        with harness.food.path.open("rb") as handle:
            for organism_id in sorted(tuple(population.organisms)):
                organism = population.organisms[organism_id]
                if organism.status is OrganismStatus.DEAD:
                    continue
                before = _snapshot(organism)
                prior_strength_one_surviving = len(pending_strength_one & set(before))
                reserve_before = organism.reserve
                capacity = organism.bite_limit(population.config)
                consumed_before = organism.consumed_total
                assimilated_before = organism.assimilated_total
                waste_before = organism.waste_total
                claim = harness._claim_next(organism)
                funded_costs_this_cycle.clear()
                if claim is not None:
                    bite, _context = harness.food.read(handle, claim)
                    population._digest(organism, bite, tuple(1.0 for _ in bite))
                    del bite
                after_digest = _snapshot(organism)
                digest_created = set(after_digest) - set(before)
                strengthened = {
                    key for key in set(before) & set(after_digest)
                    if after_digest[key].strength > before[key].strength
                }
                population._consolidate(organism)
                before_maintenance = _snapshot(organism)
                consolidation_created = set(before_maintenance) - set(after_digest)
                created = digest_created | consolidation_created
                maintenance_paid = _maintenance_due(organism)
                population._maintain_and_resorb(organism)
                after_maintenance = _snapshot(organism)
                resorbed = set(before_maintenance) - set(after_maintenance)
                strength_one_created = {
                    key for key in digest_created if after_digest[key].strength == 1.0
                }
                strength_one_end = strength_one_created & set(after_maintenance)
                organism.age_in_cycles += 1
                if organism.status is OrganismStatus.ALIVE:
                    population._divide_if_profitable(organism)
                death_condition = None
                if organism.size == 0 and organism.status is OrganismStatus.ALIVE:
                    organism.status = OrganismStatus.DEAD
                    organism.death_age = organism.age_in_cycles
                    death_condition = "no living structures"
                    population.result.events.append(LifecycleEvent(organism.id, 0, "DEATH", death_condition))
                if organism.total_strength > organism.peak_strength:
                    organism.peak_strength = organism.total_strength
                    organism.peak_age = organism.age_in_cycles
                strengths = [state.strength for state in after_maintenance.values()]
                rows.append(CycleTrace(
                    cycle=population.result.cycles + 1,
                    file_offset=claim.offset if claim else None,
                    claimed_region=claim.parcel if claim else None,
                    bite_capacity=capacity,
                    actual_bite_size=claim.length if claim else 0,
                    consumed=organism.consumed_total - consumed_before,
                    assimilated=float(organism.assimilated_total - assimilated_before),
                    waste=float(organism.waste_total - waste_before),
                    reserve_before=reserve_before,
                    nutrition_gained=float(organism.assimilated_total - assimilated_before),
                    maintenance_paid=maintenance_paid,
                    reserve_after=organism.reserve,
                    structure_count_before=len(before),
                    structure_count_after=organism.size,
                    structures_created=_count(created, "ATOM") + _count(created, "COMPOSITE"),
                    structures_strengthened=_count(strengthened, "ATOM") + _count(strengthened, "COMPOSITE"),
                    structures_resorbed=_count(resorbed, "ATOM") + _count(resorbed, "COMPOSITE"),
                    relations_created=_count(created, "RELATION"),
                    relations_strengthened=_count(strengthened, "RELATION"),
                    relations_resorbed=_count(resorbed, "RELATION"),
                    weakest_structure_strength=min(strengths) if strengths else None,
                    strongest_structure_strength=max(strengths) if strengths else None,
                    strength_one_created=len(strength_one_created),
                    strength_one_survive_end_cycle=len(strength_one_end),
                    strength_one_resorbed_immediately=len(strength_one_created - strength_one_end),
                    strength_one_created_previous_cycle_surviving=prior_strength_one_surviving,
                    funded_formation_cost_paid=sum(funded_costs_this_cycle),
                    consolidations=len(consolidation_created),
                    death_condition=death_condition,
                ))
                pending_strength_one = strength_one_created
        for organism in population.organisms.values():
            harness._ensure_navigation(organism)
        population.result.cycles += 1
        population.max_population = max(population.max_population, len(population.alive()))
    population._fund_cost = original_fund_cost  # type: ignore[method-assign]
    return rows, harness


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--seed", type=int, default=0xF00D)
    parser.add_argument("--parcel-size", type=int, default=64)
    parser.add_argument("--context-overlap", type=int, default=2)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "real-file-death-trace.json")
    args = parser.parse_args()
    rows, harness = trace(args.file, seed=args.seed, parcel_size=args.parcel_size, context_overlap=args.context_overlap)
    output = {
        "file": str(args.file),
        "seed": args.seed,
        "parcel_size": args.parcel_size,
        "context_overlap": args.context_overlap,
        "cycles": [asdict(row) for row in rows],
        "death_age": harness.population.organisms[0].death_age,
        "food_metrics": asdict(harness.food.metrics),
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"cycles": len(rows), "death_age": output["death_age"], "food_metrics": output["food_metrics"], "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
