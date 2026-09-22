"""Compare the current reference checkpoint with the native Python ABI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from statistics import median
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.backend import NativeBackend
from mathematical_organism.lifecycle import MathematicalLifePopulation


def _reference_run(payload: bytes, steps: int) -> float:
    population = MathematicalLifePopulation(payload.decode("ascii"))
    started = perf_counter()
    for _ in range(steps):
        population.cycle()
    return perf_counter() - started


def _native_ffi_run(library: Path, payload: bytes, steps: int) -> float:
    started = perf_counter()
    with NativeBackend(library, organism_id=0) as backend:
        for step in range(steps):
            current = payload if step == 0 else b""
            backend.step(current, (1.0,) * len(current))
    return perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=10_000)
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()
    if args.steps <= 0 or args.repetitions <= 0:
        raise SystemExit("--steps and --repetitions must be positive")
    payload = b"AB" * 128
    reference = [_reference_run(payload, args.steps) for _ in range(args.repetitions)]
    native_ffi = [_native_ffi_run(args.library, payload, args.steps) for _ in range(args.repetitions)]
    reference_median = median(reference)
    native_median = median(native_ffi)
    print(
        f"steps={args.steps} repetitions={args.repetitions} "
        f"reference_median_seconds={reference_median:.9f} "
        f"native_ffi_median_seconds={native_median:.9f} "
        f"reference_steps_per_second={args.steps / reference_median:.3f} "
        f"native_ffi_steps_per_second={args.steps / native_median:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
