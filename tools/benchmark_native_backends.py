"""Compare the current reference checkpoint with the native Python ABI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from statistics import median
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.backend import NativeBackend, NativePopulationBackend
from mathematical_organism.lifecycle import LifecycleConfig, MathematicalLifeOrganism, MathematicalLifePopulation


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


def _reference_population_run(payload: bytes, steps: int, population_size: int) -> float:
    config = LifecycleConfig(boundary_ratio_limit=0.01)
    population = MathematicalLifePopulation(payload.decode("ascii"), config)
    for organism_id in range(1, population_size):
        population.organisms[organism_id] = MathematicalLifeOrganism(
            organism_id, None, 0, 0, 0, reserve=config.birth_reserve
        )
    started = perf_counter()
    nutrition_per_byte = 1.0 / population_size
    for step in range(steps):
        for organism_id in range(population_size):
            organism = population.organisms[organism_id]
            if step == 0:
                bite = tuple(payload.decode("ascii"))
                nutrition = (nutrition_per_byte,) * len(bite)
            else:
                bite = ()
                nutrition = ()
            population._cycle_one(organism, (bite, nutrition))
        population.result.cycles += 1
    return perf_counter() - started


def _native_population_run(library: Path, payload: bytes, steps: int, population_size: int) -> float:
    config = LifecycleConfig(boundary_ratio_limit=0.01)
    organism_ids = tuple(range(population_size))
    with NativePopulationBackend(library, organism_ids=organism_ids, config=config) as population:
        started = perf_counter()
        nutrition_per_byte = 1.0 / population_size
        for step in range(steps):
            bite = payload if step == 0 else b""
            nutrition = (nutrition_per_byte,) * len(bite)
            population.step(
                {organism_id: (bite, nutrition) for organism_id in organism_ids},
                child_ids={organism_id: (1 << 32) + organism_id for organism_id in organism_ids},
            )
        return perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=10_000)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--population-size", type=int, default=1)
    args = parser.parse_args()
    if args.steps <= 0 or args.repetitions <= 0 or args.population_size <= 0:
        raise SystemExit("--steps, --repetitions, and --population-size must be positive")
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
    if args.population_size > 1:
        population_reference = [
            _reference_population_run(payload, args.steps, args.population_size)
            for _ in range(args.repetitions)
        ]
        population_native = [
            _native_population_run(args.library, payload, args.steps, args.population_size)
            for _ in range(args.repetitions)
        ]
        reference_population_median = median(population_reference)
        native_population_median = median(population_native)
        print(
            f"population_size={args.population_size} steps={args.steps} repetitions={args.repetitions} "
            f"reference_population_median_seconds={reference_population_median:.9f} "
            f"native_population_ffi_median_seconds={native_population_median:.9f} "
            f"reference_population_steps_per_second={args.steps / reference_population_median:.3f} "
            f"native_population_ffi_steps_per_second={args.steps / native_population_median:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
