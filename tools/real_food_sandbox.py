from __future__ import annotations

"""Run a physical FILE -> food sandbox experiment without changing lifecycle rules."""

import argparse
from dataclasses import asdict
import json
import sys
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.food_sandbox import SandboxFeedingHarness  # noqa: E402


def _summary(harness: SandboxFeedingHarness, elapsed: float) -> dict[str, object]:
    population = harness.population
    food = harness.food
    alive = population.alive()
    structures = sum(item.size for item in alive)
    relations = sum(len(item.relations) + len(item.composites) for item in alive)
    return {
        "source": food.source.name,
        "source_size": food.size,
        "source_sha256": food.source_hash,
        "consumed": food.metrics.bytes_consumed,
        "remaining": food.remaining,
        "duplicates": food.metrics.duplicate_consumption,
        "missing_accounting": food.size - food.metrics.bytes_consumed - food.remaining,
        "parcels_created": food.metrics.parcels_created,
        "parcels_deleted": food.metrics.parcels_deleted,
        "fragmentation_peak": food.metrics.fragmentation_peak,
        "claims": food.metrics.claims,
        "navigation_rounds": max((state.round for state in harness.navigation.values()), default=0),
        "alive": len(alive),
        "born": len(population.result.births),
        "dead": sum(item.status.value == "DEAD" for item in population.organisms.values()),
        "divisions": len(population.result.births),
        "generations": max((item.generation for item in population.organisms.values()), default=0),
        "structures": structures,
        "relations": relations,
        "reserve": sum(item.reserve for item in alive),
        "total_strength": sum(item.total_strength for item in alive),
        "candidate_regions_visited": food.metrics.candidates_visited,
        "regions_skipped": food.metrics.regions_skipped,
        "bytes_read": food.metrics.bytes_read,
        "peak_working_memory": food.metrics.peak_working_memory,
        "elapsed_seconds": elapsed,
        "throughput_mib_s": food.metrics.bytes_consumed / max(elapsed, 1e-12) / (1024 * 1024),
        "cycles": population.result.cycles,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--sandbox", type=Path, default=PROJECT_ROOT / "sandbox")
    parser.add_argument("--seed", type=int, default=0xF00D)
    parser.add_argument("--parcel-size", type=int, default=64)
    parser.add_argument("--context-overlap", type=int, default=2)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--max-cycles", type=int)
    args = parser.parse_args()
    harness = SandboxFeedingHarness(args.file, args.sandbox, seed=args.seed, parcel_size=args.parcel_size, context_overlap=args.context_overlap)
    started = perf_counter()
    last_cycle = -1

    def progress(current: SandboxFeedingHarness) -> None:
        nonlocal last_cycle
        cycle = current.population.result.cycles
        if cycle == last_cycle or cycle % max(1, args.progress_every):
            return
        last_cycle = cycle
        result = _summary(current, perf_counter() - started)
        print(
            f"FILE: {result['source']}\nORIGINAL: {result['source_size']} B\n"
            f"EATEN: {result['consumed']} B\nREMAINING: {result['remaining']} B\n"
            f"FOOD: {100.0 * result['consumed'] / max(1, result['source_size']):.1f} %\n"
            f"ALIVE: {result['alive']}  BORN: {result['born']}  DEAD: {result['dead']}  DIVISIONS: {result['divisions']}\n"
            f"CLAIMS: {result['claims']}  ROUNDS: {result['navigation_rounds']}\n"
        )

    harness.run(max_cycles=args.max_cycles, progress=progress)
    elapsed = perf_counter() - started
    summary = _summary(harness, elapsed)
    trace_path = harness.food.trace_dir / f"{harness.food.source.name}.json"
    trace_path.write_text(json.dumps([asdict(trace) for trace in harness.trace], indent=2) + "\n", encoding="utf-8")
    result_path = harness.food.result_dir / f"{harness.food.source.name}.json"
    result_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if harness.food.remaining:
        return 2
    harness.assert_invariants()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
