from __future__ import annotations

"""Diagnostic-only skeleton metrics for the unchanged real-file feeding run."""

from dataclasses import asdict, dataclass
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.food import ImplicitFileFeedingHarness  # noqa: E402


@dataclass(frozen=True, slots=True)
class SkeletonCycle:
    cycle: int
    structures_created: int
    structures_at_strength_1: int
    structures_recovered_from_1: int
    structures_physically_removed: int
    relations_created: int
    relations_physically_removed: int
    connected_components: int
    largest_component_size: int
    boundary_candidates: int
    exact_two_way_division_candidates: int


def _snapshot(organism: object) -> tuple[dict[tuple[str, object], float], dict[object, float]]:
    structures = {("ATOM", key): value.strength for key, value in organism.atoms.items()}
    edges = {key: value.strength for key, value in {**organism.relations, **organism.composites}.items()}
    structures.update({("EDGE", key): value for key, value in edges.items()})
    return structures, edges


def _component_metrics(population: object, organism: object) -> tuple[int, int, int, int]:
    if not organism.atoms:
        return 0, 0, 0, 0
    components = population._components_without_boundary(organism, None)
    edges = {**organism.relations, **organism.composites}
    boundaries = sorted({tuple(sorted(pair)) for pair in edges if pair[0] != pair[1]})
    exact = sum(
        len(population._components_without_boundary(organism, boundary)) == 2
        for boundary in boundaries
    ) if len(components) == 1 else 0
    return len(components), max(map(len, components)), len(boundaries) if len(components) == 1 else 0, exact


def trace(path: Path, *, seed: int, parcel_size: int, context_overlap: int) -> tuple[list[SkeletonCycle], ImplicitFileFeedingHarness]:
    harness = ImplicitFileFeedingHarness(path, seed=seed, parcel_size=parcel_size, context_overlap=context_overlap)
    rows: list[SkeletonCycle] = []
    while harness.food.remaining and harness.population.alive():
        root = harness.population.organisms[0]
        before, before_edges = _snapshot(root)
        harness.step()
        root = harness.population.organisms[0]
        after, after_edges = _snapshot(root)
        components, largest, boundaries, exact = _component_metrics(harness.population, root)
        rows.append(SkeletonCycle(
            cycle=harness.population.result.cycles,
            structures_created=len(set(after) - set(before)),
            structures_at_strength_1=sum(value == 1.0 for value in after.values()),
            structures_recovered_from_1=sum(
                before[key] == 1.0 and after[key] > 1.0 for key in set(before) & set(after)
            ),
            structures_physically_removed=len(set(before) - set(after)),
            relations_created=len(set(after_edges) - set(before_edges)),
            relations_physically_removed=len(set(before_edges) - set(after_edges)),
            connected_components=components,
            largest_component_size=largest,
            boundary_candidates=boundaries,
            exact_two_way_division_candidates=exact,
        ))
    return rows, harness


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--seed", type=int, default=0xF00D)
    parser.add_argument("--parcel-size", type=int, default=64)
    parser.add_argument("--context-overlap", type=int, default=2)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "skeleton-stability-trace.json")
    args = parser.parse_args()
    rows, harness = trace(args.file, seed=args.seed, parcel_size=args.parcel_size, context_overlap=args.context_overlap)
    args.output.write_text(json.dumps({"rows": [asdict(row) for row in rows], "food_bytes": harness.food.metrics.bytes_consumed}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cycles": len(rows), "food_bytes": harness.food.metrics.bytes_consumed, "births": len(harness.population.result.births), "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
