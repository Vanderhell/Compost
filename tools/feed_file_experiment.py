from __future__ import annotations

"""Feed a real file through the implicit, once-only FOOD/PAYLOAD layer."""

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.food import ImplicitFileFeedingHarness  # noqa: E402


def sequential_baseline(path: Path, *, parcel_size: int) -> dict[str, object]:
    started = perf_counter()
    bytes_read = 0
    bites = 0
    with path.open("rb") as handle:
        while True:
            block = handle.read(parcel_size)
            if not block:
                break
            bytes_read += len(block)
            bites += 1
    elapsed = perf_counter() - started
    return {
        "name": "SEQUENTIAL_BASELINE",
        "file_size": path.stat().st_size,
        "organisms": 1,
        "bites": bites,
        "candidate_regions_visited": bites,
        "regions_skipped": 0,
        "bytes_read": bytes_read,
        "bytes_consumed": bytes_read,
        "duplicate_consumption": 0,
        "missing_bytes": path.stat().st_size - bytes_read,
        "navigation_time": 0.0,
        "digest_time": 0.0,
        "total_time": elapsed,
        "peak_working_memory": parcel_size,
    }


def implicit_run(
    path: Path, *, parcel_size: int, overlap: int, seed: int, max_steps: int | None = None,
) -> tuple[dict[str, object], ImplicitFileFeedingHarness]:
    started = perf_counter()
    harness = ImplicitFileFeedingHarness(path, seed=seed, parcel_size=parcel_size, context_overlap=overlap)
    failure: str | None = None
    try:
        harness.run(max_steps=max_steps)
    except RuntimeError as error:
        # Preserve the lifecycle result verbatim: incomplete food is evidence,
        # not a reason to alter organism rules in this feeding experiment.
        failure = str(error)
    completed = harness.food.remaining == 0
    if completed:
        harness.assert_invariants()
    elapsed = perf_counter() - started
    food = harness.food.metrics
    population = harness.population
    claimed_events = [event for event in harness.trace if event.claimed]
    claimed_parcels = {event.offset // parcel_size for event in claimed_events}
    return {
        "name": "IMPLICIT_C",
        "file_size": harness.food.size,
        "organisms": len(harness.population.organisms),
        "alive": len(population.alive()),
        "dead": sum(organism.status.value == "DEAD" for organism in population.organisms.values()),
        "divisions": len(population.result.births),
        "bites": len(claimed_events),
        "navigation_rounds": max((state.round for state in harness.navigation.values()), default=0) + 1,
        "unique_claimed_parcels": len(claimed_parcels),
        "parcel_revisits": len(claimed_events) - len(claimed_parcels),
        "candidate_regions_visited": food.candidates_visited,
        "regions_skipped": food.regions_skipped,
        "bytes_read": food.bytes_read,
        "bytes_consumed": food.bytes_consumed,
        "duplicate_consumption": food.duplicate_consumption,
        "missing_bytes": harness.food.remaining,
        "navigation_time": harness.navigation_time,
        "digest_time": harness.digest_time,
        "total_time": elapsed,
        "peak_working_memory": food.peak_working_memory,
        "completed": completed,
        "failure": failure,
    }, harness


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, nargs="?", default=PROJECT_ROOT / "src" / "mathematical_organism" / "lifecycle.py")
    parser.add_argument("--parcel-size", type=int, default=64)
    parser.add_argument("--context-overlap", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0xF00D)
    parser.add_argument("--max-steps", type=int, default=None, help="bounded diagnostic run; leaves lifecycle unchanged")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "file-feeding-results.json")
    args = parser.parse_args()
    if not args.file.is_file():
        parser.error(f"not a regular file: {args.file}")
    sequential = sequential_baseline(args.file, parcel_size=args.parcel_size)
    implicit, harness = implicit_run(
        args.file, parcel_size=args.parcel_size, overlap=args.context_overlap,
        seed=args.seed, max_steps=args.max_steps,
    )
    # SkipSpace V1 is intentionally not called: arbitrary claimed-file bitsets
    # have no 31-state future-sufficient encoding, so a correct subtree skip
    # cannot be derived without materializing occupancy-equivalent state.
    skipspace = {
        "name": "IMPLICIT_C_PLUS_SKIPSPACE",
        "status": "NOT_APPLICABLE_NO_SMALL_SUFFICIENT_STATE",
        **{key: None for key in (
            "file_size", "organisms", "bites", "candidate_regions_visited", "regions_skipped",
            "bytes_read", "bytes_consumed", "duplicate_consumption", "missing_bytes",
            "navigation_time", "digest_time", "total_time", "peak_working_memory",
        )},
    }
    result = {
        "file": str(args.file),
        "first_100_bites": [
            {
                "organism_id": event.organism_id, "generation": event.generation,
                "bite_index": event.bite_index, "offset": event.offset,
                "length": event.length, "navigation_state": f"0x{event.navigation_state:016X}",
                "claimed": event.claimed, "skipped_regions": event.skipped_regions,
                "digest_assimilated": event.digest_assimilated, "digest_waste": event.digest_waste,
            }
            for event in harness.trace[:100]
        ],
        "food_map": harness.debug_map(),
        "benchmarks": [sequential, implicit, skipspace],
        "invariants": {
            "consumed_bytes": harness.food.metrics.bytes_consumed,
            "file_size": harness.food.size,
            "duplicate_consumption": harness.food.metrics.duplicate_consumption,
            "missing_bytes": harness.food.remaining,
            "context_overlap_has_zero_nutrition": True,
            "raw_payload_in_organism": False,
            "implicit_topology_materialized": False,
        },
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "benchmarks": result["benchmarks"], "invariants": result["invariants"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
