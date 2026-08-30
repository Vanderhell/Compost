from __future__ import annotations

"""Stream a real file into destructive FOOD blocks, then feed it unchanged."""

import argparse
import sys
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.destructive_ingest import DestructiveFeedingHarness, IngestEvent  # noqa: E402


def mib(value: int | float) -> str:
    return f"{value / (1024 * 1024):.2f} MiB"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--sandbox", type=Path, default=PROJECT_ROOT / "sandbox")
    parser.add_argument("--block-size", type=int, default=1024 * 1024)
    parser.add_argument("--technical-buffer-size", type=int, default=64 * 1024)
    parser.add_argument("--seed", type=int, default=0xF00D)
    parser.add_argument("--progress-every", type=int, default=1000)
    args = parser.parse_args()
    original_size = args.file.stat().st_size

    def ingest_progress(event: IngestEvent) -> None:
        print("INGEST\n"
              f"ORIGINAL: {mib(original_size)}\nINBOX LEFT: {mib(event.inbox_remaining)}\n"
              f"FOOD CREATED: {mib(event.food_created)}\nBLOCKS: {event.block_id + 1}\n"
              f"ACCOUNTED: {mib(event.inbox_remaining + event.food_created)}\n")

    started = perf_counter()
    harness = DestructiveFeedingHarness(args.file, args.sandbox, seed=args.seed, block_size=args.block_size, technical_buffer_size=args.technical_buffer_size, ingest_progress=ingest_progress)
    ingest_elapsed = perf_counter() - started
    food = harness.food
    print("INGEST\n"
          f"ORIGINAL: {mib(food.size)}\nINBOX LEFT: {mib(food.inbox_remaining)}\n"
          f"FOOD CREATED: {mib(food.food_created)}\nBLOCKS: {food.metrics.blocks_created}\n"
          f"ACCOUNTED: {mib(food.inbox_remaining + food.food_created)}\n")
    started = perf_counter()
    while food.remaining and harness.population.alive():
        harness.step()
        if harness.population.result.cycles % max(1, args.progress_every) == 0:
            print("FEEDING\n"
                  f"FOOD START: {mib(food.size)}\nEATEN: {mib(food.metrics.bytes_consumed)}\n"
                  f"FOOD LEFT: {mib(food.remaining)}\nALIVE: {len(harness.population.alive())}\n"
                  f"BORN: {len(harness.population.result.births)}\n"
                  f"DEAD: {sum(item.status.value == 'DEAD' for item in harness.population.organisms.values())}\n")
    feeding_elapsed = perf_counter() - started
    harness.assert_invariants()
    print("RESULT\n"
          f"INGEST MiB/s: {food.size / max(ingest_elapsed, 1e-12) / (1024 * 1024):.3f}\n"
          f"FEEDING MiB/s: {food.metrics.bytes_consumed / max(feeding_elapsed, 1e-12) / (1024 * 1024):.3f}\n"
          f"AVERAGE BODY / BITE: {sum(harness.body_sizes) / max(1, len(harness.body_sizes)):.2f} / {sum(harness.bite_sizes) / max(1, len(harness.bite_sizes)):.2f} B\n"
          f"MIN/MAX BITE: {min(harness.bite_sizes, default=0)} / {max(harness.bite_sizes, default=0)} B\n"
          f"DIGEST CYCLES: {len(harness.bite_sizes)}\n"
          f"PEAK RAW BITE / TECHNICAL BUFFER: {food.metrics.peak_raw_bite_bytes} / {food.metrics.peak_technical_buffer_bytes} B\n"
          f"FILESYSTEM OPS: {food.metrics.filesystem_operations}\n"
          f"FINAL FOOD: {food.remaining} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
