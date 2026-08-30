from __future__ import annotations

"""Prepare a raw binary file for the transparent FILE -> FOOD SPACE boundary."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.food_preparation import (  # noqa: E402
    DEFAULT_PARCEL_SIZE,
    HASH_CHUNK_SIZE,
    PreparedFood,
    streams_are_byte_identical,
)


def _boundary_checks(prepared: PreparedFood) -> dict[str, bool]:
    """Validate endpoints and every physical parcel boundary using small reads."""
    if prepared.file_size == 0:
        return {"empty_file": True, "first_byte": True, "last_byte": True, "parcel_boundaries": True}
    first_ok = last_ok = boundaries_ok = True
    with prepared.path.open("rb") as handle:
        handle.seek(0)
        expected_first = handle.read(1)
        first_ok = prepared.read_window(handle, 0, 1).nutrition == expected_first
        handle.seek(prepared.file_size - 1)
        expected_last = handle.read(1)
        last_ok = prepared.read_window(handle, prepared.file_size - 1, 1).nutrition == expected_last
        for parcel in range(1, prepared.parcel_count):
            boundary = parcel * prepared.parcel_size
            handle.seek(boundary - 1)
            expected = handle.read(min(2, prepared.file_size - boundary + 1))
            actual = prepared.read_window(handle, boundary - 1, len(expected)).nutrition
            if actual != expected:
                boundaries_ok = False
                break
    return {"empty_file": False, "first_byte": first_ok, "last_byte": last_ok, "parcel_boundaries": boundaries_ok}


def benchmark(path: Path, *, context_overlap: int) -> list[dict[str, object]]:
    """Measure metadata plus one streaming pass; it never retains source content."""
    results: list[dict[str, object]] = []
    for parcel_size in (64, 256, 1024, 4096):
        started = perf_counter()
        prepared = PreparedFood(path, parcel_size=parcel_size, context_overlap=context_overlap)
        metadata_seconds = perf_counter() - started
        started = perf_counter()
        reconstructed_hash = hashlib.sha256()
        max_chunk = 0
        parcel_count_seen = 0
        for block in prepared.iter_source_chunks():
            reconstructed_hash.update(block)
            max_chunk = max(max_chunk, len(block))
        for parcel in range(prepared.parcel_count):
            prepared.parcel_bounds(parcel)
            parcel_count_seen += 1
        scan_seconds = perf_counter() - started
        results.append({
            "parcel_size": parcel_size,
            "parcel_count": parcel_count_seen,
            "metadata_seconds": metadata_seconds,
            "stream_validation_seconds": scan_seconds,
            "max_raw_working_buffer": max_chunk,
            "hash_matches": reconstructed_hash.hexdigest() == prepared.metadata.source_hash,
            "claim_memory": {
                "byte_bitmap_bytes": prepared.state_memory(interval_count=prepared.parcel_count).byte_bitmap_bytes,
                "parcel_bitmap_bytes": prepared.state_memory(interval_count=prepared.parcel_count).parcel_bitmap_bytes,
                "interval_count": prepared.parcel_count,
                "interval_estimated_bytes": prepared.state_memory(interval_count=prepared.parcel_count).interval_estimated_bytes,
                "parcel_level_exact_for_partial_bites": False,
            },
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", type=Path)
    parser.add_argument("--parcel-size", type=int, default=DEFAULT_PARCEL_SIZE)
    parser.add_argument("--context-overlap", type=int, default=2)
    parser.add_argument("--benchmark", action="store_true", help="also compare 64/256/1024/4096-byte parcels")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "food-preparation-results.json")
    args = parser.parse_args()
    prepared = PreparedFood(args.input_file, parcel_size=args.parcel_size, context_overlap=args.context_overlap)
    metadata = prepared.metadata
    result: dict[str, object] = {
        "source_file": str(prepared.path),
        "metadata": {
            "file_size": metadata.file_size,
            "parcel_size": metadata.parcel_size,
            "parcel_count": metadata.parcel_count,
            "last_parcel_size": metadata.last_parcel_size,
            "source_hash": metadata.source_hash,
        },
        "context_size": prepared.context_overlap,
        "byte_for_byte_validation": streams_are_byte_identical(prepared),
        "boundary_validation": _boundary_checks(prepared),
        "food_state_memory": {
            "byte_bitmap_bytes": prepared.state_memory().byte_bitmap_bytes,
            "parcel_bitmap_bytes": prepared.state_memory().parcel_bitmap_bytes,
            "interval_estimated_bytes_for_one_range_per_parcel": prepared.state_memory(interval_count=prepared.parcel_count).interval_estimated_bytes,
            "parcel_level_exact_for_partial_bites": False,
        },
        "max_raw_working_buffer": HASH_CHUNK_SIZE,
    }
    if args.benchmark:
        result["parcel_benchmark"] = benchmark(args.input_file, context_overlap=args.context_overlap)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["byte_for_byte_validation"] and all(result["boundary_validation"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
