from __future__ import annotations

"""Diagnostic-only evaluation of unchanged DIVIDE decisions on real file food."""

from collections import defaultdict
from dataclasses import asdict, dataclass
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.food import ImplicitFileFeedingHarness  # noqa: E402
from mathematical_organism.lifecycle import MathematicalLifeOrganism, OrganismStatus  # noqa: E402


@dataclass(frozen=True, slots=True)
class DivisionTrace:
    cycle: int
    bytes_consumed_total: int
    organism_size: int
    atom_count: int
    edge_count: int
    baseline_component_count: int | None
    total_strength: float
    reserve: float
    division_candidate_exists: bool
    candidate_count: int
    valid_two_way_candidate_count: int
    candidate_region_size: int | None
    candidate_region_strength: float | None
    candidate_region_reserve: float | None
    remaining_parent_size: int | None
    remaining_parent_strength: float | None
    remaining_parent_reserve: float | None
    boundary_strength: float | None
    boundary_ratio: float | None
    child_viable: bool | None
    parent_viable_after_split: bool | None
    cost_before: float | None
    cost_after: float | None
    birth_cost: float
    division_gain: float | None
    division_accepted: bool
    division_reject_reason: str
    no_candidate_detail: str | None


def _strength(organism: MathematicalLifeOrganism, region: set[str]) -> float:
    edges = {**organism.relations, **organism.composites}
    return sum(item.strength for symbol, item in organism.atoms.items() if symbol in region) + sum(
        item.strength for pair, item in edges.items() if pair[0] in region and pair[1] in region
    )


def _evaluate(population: object, organism: MathematicalLifeOrganism, cycle: int) -> DivisionTrace:
    """Reference the exact predicate of `_divide_if_profitable`, without mutation."""
    config = population.config  # type: ignore[attr-defined]
    base = dict(
        cycle=cycle,
        bytes_consumed_total=organism.consumed_total,
        organism_size=organism.size,
        atom_count=len(organism.atoms),
        edge_count=len({**organism.relations, **organism.composites}),
        baseline_component_count=None,
        total_strength=organism.total_strength,
        reserve=organism.reserve,
        birth_cost=config.birth_cost,
    )
    edges = {**organism.relations, **organism.composites}
    if len(organism.atoms) < 2 or not edges:
        return DivisionTrace(**base, division_candidate_exists=False, candidate_count=0, valid_two_way_candidate_count=0,
            candidate_region_size=None, candidate_region_strength=None, candidate_region_reserve=None,
            remaining_parent_size=None, remaining_parent_strength=None, remaining_parent_reserve=None,
            boundary_strength=None, boundary_ratio=None, child_viable=None, parent_viable_after_split=None,
            cost_before=None, cost_after=None, division_gain=None, division_accepted=False,
            division_reject_reason="NO_CANDIDATE",
            no_candidate_detail="TOO_FEW_ATOMS" if len(organism.atoms) < 2 else "NO_EDGES")
    by_boundary: dict[tuple[str, str], list[object]] = defaultdict(list)
    for pair, edge in edges.items():
        if pair[0] != pair[1]:
            by_boundary[tuple(sorted(pair))].append(edge)
    baseline_components = population._components_without_boundary(organism, None)  # type: ignore[attr-defined]
    base["baseline_component_count"] = len(baseline_components)
    if len(baseline_components) != 1 or not by_boundary:
        return DivisionTrace(**base, division_candidate_exists=False, candidate_count=0, valid_two_way_candidate_count=0,
            candidate_region_size=None, candidate_region_strength=None, candidate_region_reserve=None,
            remaining_parent_size=None, remaining_parent_strength=None, remaining_parent_reserve=None,
            boundary_strength=None, boundary_ratio=None, child_viable=None, parent_viable_after_split=None,
            cost_before=None, cost_after=None, division_gain=None, division_accepted=False,
            division_reject_reason="NO_CANDIDATE",
            no_candidate_detail="NOT_CONNECTED" if len(baseline_components) != 1 else "ONLY_SELF_LOOPS")
    candidates = []
    for boundary, boundary_edges in by_boundary.items():
        regions = population._components_without_boundary(organism, boundary)  # type: ignore[attr-defined]
        if len(regions) != 2 or not all(regions):
            continue
        boundary_strength = sum(edge.strength for edge in boundary_edges)
        local_mass = organism.atoms[boundary[0]].strength + organism.atoms[boundary[1]].strength + boundary_strength
        ratio = boundary_strength / local_mass if local_mass else 1.0
        candidates.append((ratio, boundary, boundary_edges, regions))
    if not candidates:
        return DivisionTrace(**base, division_candidate_exists=False, candidate_count=len(by_boundary), valid_two_way_candidate_count=0,
            candidate_region_size=None, candidate_region_strength=None, candidate_region_reserve=None,
            remaining_parent_size=None, remaining_parent_strength=None, remaining_parent_reserve=None,
            boundary_strength=None, boundary_ratio=None, child_viable=None, parent_viable_after_split=None,
            cost_before=None, cost_after=None, division_gain=None, division_accepted=False,
            division_reject_reason="NO_VALID_TWO_WAY_BOUNDARY", no_candidate_detail=None)
    ratio, boundary, boundary_edges, regions = min(candidates, key=lambda item: (item[0], item[1]))
    if ratio >= config.boundary_ratio_limit:
        return DivisionTrace(**base, division_candidate_exists=True, candidate_count=len(by_boundary), valid_two_way_candidate_count=len(candidates),
            candidate_region_size=None, candidate_region_strength=None, candidate_region_reserve=None,
            remaining_parent_size=None, remaining_parent_strength=None, remaining_parent_reserve=None,
            boundary_strength=sum(edge.strength for edge in boundary_edges), boundary_ratio=ratio,
            child_viable=None, parent_viable_after_split=None,
            cost_before=config.division_horizon * sum(edge.maintenance for edge in boundary_edges),
            cost_after=config.birth_cost, division_gain=config.division_horizon * sum(edge.maintenance for edge in boundary_edges) - config.birth_cost,
            division_accepted=False, division_reject_reason="BOUNDARY_TOO_STRONG", no_candidate_detail=None)
    child = min(regions, key=lambda region: (len(region), tuple(sorted(region))))
    parent = next(region for region in regions if region is not child)
    child_income = population._region_expected_income(organism, child)  # type: ignore[attr-defined]
    parent_income = population._region_expected_income(organism, parent)  # type: ignore[attr-defined]
    child_maintenance = population._region_maintenance(organism, child)  # type: ignore[attr-defined]
    parent_maintenance = population._region_maintenance(organism, parent)  # type: ignore[attr-defined]
    child_reserve = 0.0
    parent_reserve = organism.reserve
    child_viable = child_income > child_maintenance
    parent_viable = parent_income > parent_maintenance and parent_reserve >= config.birth_cost
    cost_before = config.division_horizon * sum(edge.maintenance for edge in boundary_edges)
    gain = cost_before - config.birth_cost
    if not child_viable:
        reason = "CHILD_TOO_WEAK"
    elif not parent_viable:
        reason = "PARENT_TOO_WEAK"
    elif gain <= 0.0:
        reason = "BIRTH_COST_TOO_HIGH" if cost_before <= config.birth_cost else "NO_MATHEMATICAL_GAIN"
    else:
        reason = "ACCEPT"
    return DivisionTrace(**base, division_candidate_exists=True, candidate_count=len(by_boundary), valid_two_way_candidate_count=len(candidates),
        candidate_region_size=len(child), candidate_region_strength=_strength(organism, child), candidate_region_reserve=child_reserve,
        remaining_parent_size=len(parent), remaining_parent_strength=_strength(organism, parent), remaining_parent_reserve=parent_reserve,
        boundary_strength=sum(edge.strength for edge in boundary_edges), boundary_ratio=ratio,
        child_viable=child_viable, parent_viable_after_split=parent_viable,
        cost_before=cost_before, cost_after=config.birth_cost, division_gain=gain,
        division_accepted=False, division_reject_reason=reason, no_candidate_detail=None)


def trace(path: Path, *, seed: int, parcel_size: int, context_overlap: int) -> tuple[list[DivisionTrace], ImplicitFileFeedingHarness]:
    harness = ImplicitFileFeedingHarness(path, seed=seed, parcel_size=parcel_size, context_overlap=context_overlap)
    population = harness.population
    rows: list[DivisionTrace] = []
    while harness.food.remaining and population.alive():
        with harness.food.path.open("rb") as handle:
            for organism_id in sorted(tuple(population.organisms)):
                organism = population.organisms[organism_id]
                if organism.status is OrganismStatus.DEAD:
                    continue
                claim = harness._claim_next(organism)
                if claim is not None:
                    bite, _context = harness.food.read(handle, claim)
                    population._digest(organism, bite, tuple(1.0 for _ in bite))
                    del bite
                population._consolidate(organism)
                population._maintain_and_resorb(organism)
                organism.age_in_cycles += 1
                evaluation = _evaluate(population, organism, population.result.cycles + 1)
                births_before = len(population.result.births)
                if organism.status is OrganismStatus.ALIVE:
                    population._divide_if_profitable(organism)
                accepted = len(population.result.births) != births_before
                rows.append(DivisionTrace(**{**asdict(evaluation), "division_accepted": accepted,
                    "division_reject_reason": "ACCEPT" if accepted else evaluation.division_reject_reason}))
                if organism.size == 0 and organism.status is OrganismStatus.ALIVE:
                    organism.status = OrganismStatus.DEAD
                    organism.death_age = organism.age_in_cycles
                if organism.total_strength > organism.peak_strength:
                    organism.peak_strength = organism.total_strength
                    organism.peak_age = organism.age_in_cycles
        for organism in population.organisms.values():
            harness._ensure_navigation(organism)
        population.result.cycles += 1
        population.max_population = max(population.max_population, len(population.alive()))
    return rows, harness


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--seed", type=int, default=0xF00D)
    parser.add_argument("--parcel-size", type=int, default=64)
    parser.add_argument("--context-overlap", type=int, default=2)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "real-file-division-trace.json")
    args = parser.parse_args()
    rows, harness = trace(args.file, seed=args.seed, parcel_size=args.parcel_size, context_overlap=args.context_overlap)
    args.output.write_text(json.dumps({"rows": [asdict(row) for row in rows], "food_bytes": harness.food.metrics.bytes_consumed}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cycles": len(rows), "food_bytes": harness.food.metrics.bytes_consumed, "births": len(harness.population.result.births), "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
