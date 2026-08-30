from __future__ import annotations

"""Measure finite birth reserves without modifying food or division behavior."""

import json
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from mathematical_organism.lifecycle import LifecycleConfig, MathematicalLifePopulation, OrganismStatus  # noqa: E402
from tools.random_hex_experiment import hidden_pattern_hex, random_hex  # noqa: E402


SEEDS = tuple(range(10))


def run(payload: tuple[str, ...], config: LifecycleConfig, *, settle: int = 32) -> dict[str, object]:
    population = MathematicalLifePopulation(payload, config)
    population.run_until_stream_exhausted(max_cycles=max(1, len(payload) * 2))
    population.settle(settle)
    organisms = tuple(population.organisms.values())
    alive = tuple(item for item in organisms if item.status is OrganismStatus.ALIVE)
    return {
        "alive": len(alive),
        "dead": len(organisms) - len(alive),
        "born": len(organisms),
        "divisions": len(population.result.births),
        "max_population": population.max_population,
        "max_generation": max((item.generation for item in organisms), default=0),
        "strength": sum(item.total_strength for item in alive),
        "reserve": sum(item.reserve for item in alive),
        "nutrition_consumed": population.result.consumed_nutrition_total,
        "nutrition_available": population.result.available_nutrition_total,
        "top_relations": [
            (repr(key), value.strength)
            for item in sorted(organisms, key=lambda current: current.id)
            for key, value in sorted({**item.relations, **item.composites}.items(), key=lambda pair: (-pair[1].strength, repr(pair[0])))[:3]
        ][:5],
    }


def summary(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "runs": len(rows),
        "alive_runs": sum(bool(row["alive"]) for row in rows),
        "dead_runs": sum(not bool(row["alive"]) for row in rows),
        "total_divisions": sum(int(row["divisions"]) for row in rows),
        "max_population": max((int(row["max_population"]) for row in rows), default=0),
        "mean_reserve": sum(float(row["reserve"]) for row in rows) / len(rows) if rows else 0.0,
    }


def main() -> int:
    base = LifecycleConfig()
    before = replace(base, birth_reserve=0.0)
    after = base
    comparisons = {
        "before": [dict(seed=seed, **run(random_hex(100_000, seed), before)) for seed in SEEDS],
        "after": [dict(seed=seed, **run(random_hex(100_000, seed), after)) for seed in SEEDS],
        "critical_seeds": {
            "before": [dict(seed=seed, **run(random_hex(10_000, seed), before)) for seed in (2, 8, 9)],
            "after": [dict(seed=seed, **run(random_hex(10_000, seed), after)) for seed in (2, 8, 9)],
        },
    }
    sweep: list[dict[str, object]] = []
    for birth_reserve in (0.0, 0.25, 0.5, 1.0, 2.0):
        for maintenance_scale in (0.5, 1.0, 1.5, 2.0):
            config = replace(
                base,
                birth_reserve=birth_reserve,
                atom_maintenance=base.atom_maintenance * maintenance_scale,
                relation_maintenance=base.relation_maintenance * maintenance_scale,
                composite_maintenance=base.composite_maintenance * maintenance_scale,
            )
            rows = [run(random_hex(10_000, seed), config) for seed in SEEDS]
            sweep.append({
                "birth_reserve": birth_reserve,
                "maintenance_scale": maintenance_scale,
                **summary(rows),
            })
    hidden = {
        str(frequency): [dict(seed=seed, **run(hidden_pattern_hex(100_000, seed, frequency), after)) for seed in SEEDS]
        for frequency in (8, 256)
    }
    short_noise_resorption = [run(random_hex(512, seed), after, settle=1_000) for seed in SEEDS]
    result = {
        "comparison": comparisons,
        "sweep": sweep,
        "hidden_pattern": hidden,
        "short_noise_resorption": short_noise_resorption,
    }
    output = PROJECT_ROOT / "bootstrap-reserve-results.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "before": summary(comparisons["before"]),
        "after": summary(comparisons["after"]),
        "hidden": {key: summary(value) for key, value in hidden.items()},
        "short_noise_resorption": summary(short_noise_resorption),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
