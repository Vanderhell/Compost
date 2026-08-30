from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from dataclasses import replace

from .lifecycle import LifecycleConfig, MathematicalLifePopulation, OrganismStatus


def payloads(length: int = 240) -> dict[str, tuple[str, ...]]:
    """Reproducible environments; the simulator assigns no text semantics."""
    noise_alphabet = tuple("QRSTUVWXYZ")
    noise = tuple(noise_alphabet[(index * 7 + 3) % len(noise_alphabet)] for index in range(length))
    return {
        "dominant": tuple("AB"[index % 2] for index in range(length)),
        "two_regions": tuple("ABXY"[index % 4] for index in range(length)),
        "dominant_noise": tuple("ABQAZABX"[index % 8] for index in range(length)),
        "phase_change": tuple("A" if index < length // 2 else "B" for index in range(length)),
        "alternating": tuple("A" if (index // 24) % 2 == 0 else "B" for index in range(length)),
        "uniform_noise": noise,
        "large": tuple("ABXY"[index % 4] for index in range(max(length, 4096))),
    }


def run_experiment(name: str, config: LifecycleConfig | None = None, *, length: int = 240) -> MathematicalLifePopulation:
    environment = payloads(length)[name]
    population = MathematicalLifePopulation(environment, config)
    population.run_until_stream_exhausted(max_cycles=len(environment) * 4)
    population.settle(32)
    return population


def population_report(population: MathematicalLifePopulation) -> dict:
    organisms = list(population.organisms.values())
    alive = [item for item in organisms if item.status is OrganismStatus.ALIVE]
    dead = [item for item in organisms if item.status is OrganismStatus.DEAD]
    by_generation: dict[int, Counter[str]] = defaultdict(Counter)
    for item in organisms:
        by_generation[item.generation][item.status.value] += 1
    sizes = [item.size for item in organisms]
    strengths = sorted(item.total_strength for item in organisms)
    def size_band(size: int) -> str:
        if size <= 4:
            return "1-4"
        if size <= 8:
            return "5-8"
        if size <= 16:
            return "9-16"
        if size <= 32:
            return "17-32"
        if size <= 64:
            return "33-64"
        return "65+"
    ranked = sorted(
        organisms,
        key=lambda item: (-item.total_strength, -item.reserve, item.id),
    )
    def organism_row(item):
        return {
            "id": item.id, "parent": item.parent_id, "generation": item.generation,
            "age": item.age_in_cycles, "size": item.size,
            "strength": item.total_strength, "reserve": item.reserve,
            "exposure": item.exposure_total, "consumed": item.consumed_total,
            "assimilated": item.assimilated_total, "nutrition_consumed": item.nutrition_consumed_total,
            "waste": item.waste_total, "assimilation_ratio": item.assimilation_ratio,
            "children": item.children_created,
            "strongest_structures": [
                (repr(structure.key), structure.kind, structure.strength)
                for structure in sorted(item._structures(), key=lambda value: (-value.strength, repr(value.key)))[:5]
            ],
        }
    lineage_children = Counter(event.parent_id for event in population.result.births)
    return {
        "total_data_consumed": sum(item.consumed_total for item in organisms),
        "total_exposure": sum(item.exposure_total for item in organisms),
        "total_available_nutrition": population.result.available_nutrition_total,
        "total_consumed_nutrition": population.result.consumed_nutrition_total,
        "nutrition_created": population.result.nutrition_created_total,
        "alive_at_stream_end": population.result.alive_at_stream_end,
        "cycles_at_stream_end": population.result.cycles_at_stream_end,
        "total_organisms_born": len(organisms),
        "alive": len(alive), "dead": len(dead), "divisions": len(population.result.births),
        "root_size": population.organisms[0].size,
        "max_generation": max((item.generation for item in organisms), default=0),
        "max_population_at_once": population.max_population,
        "population_by_generation": {str(key): dict(value) for key, value in sorted(by_generation.items())},
        "size_distribution": dict(Counter(size_band(size) for size in sizes)),
        "strength_quantiles": {
            "min": strengths[0] if strengths else 0.0,
            "median": strengths[len(strengths) // 2] if strengths else 0.0,
            "max": strengths[-1] if strengths else 0.0,
        },
        "strongest_organisms": [organism_row(item) for item in ranked[:20]],
        "most_successful_lineage_parent": min(lineage_children, key=lambda key: (-lineage_children[key], key), default=None),
        "most_prolific_organism": min(organisms, key=lambda item: (-item.children_created, item.id), default=None).id if organisms else None,
        "longest_lived_organism": min(organisms, key=lambda item: (-item.age_in_cycles, item.id), default=None).id if organisms else None,
        "best_assimilator": min(organisms, key=lambda item: (-item.assimilation_ratio, item.id), default=None).id if organisms else None,
        "births": [asdict(item) for item in population.result.births],
        "events": [asdict(item) for item in population.result.events],
    }


def sweep() -> list[dict]:
    """Small regime map, not a parameter search for a favourable outcome."""
    rows: list[dict] = []
    for maintenance_scale in (0.6, 1.2):
        for birth_cost in (0.5, 2.0):
            for consolidation_formation_cost in (1.0, 2.5):
                    for boundary_ratio_limit in (0.10, 0.25):
                        for bite_minimum in (1, 2):
                            base = LifecycleConfig()
                            config = replace(
                                base,
                                atom_maintenance=base.atom_maintenance * maintenance_scale,
                                relation_maintenance=base.relation_maintenance * maintenance_scale,
                                composite_maintenance=base.composite_maintenance * maintenance_scale,
                                birth_cost=birth_cost,
                                consolidation_formation_cost=consolidation_formation_cost,
                                boundary_ratio_limit=boundary_ratio_limit,
                                bite_minimum=bite_minimum,
                            )
                            population = run_experiment("alternating", config, length=96)
                            report = population_report(population)
                            if report["alive_at_stream_end"] == 0:
                                regime = "EXTINCTION"
                            elif report["max_population_at_once"] == 1:
                                regime = "STABLE_SINGLE"
                            elif report["divisions"] >= 16:
                                regime = "RUNAWAY_DIVISION"
                            else:
                                regime = "STABLE_POPULATION"
                            rows.append({
                                "maintenance_scale": maintenance_scale, "birth_cost": birth_cost,
                                "consolidation_formation_cost": consolidation_formation_cost,
                                "boundary_ratio_limit": boundary_ratio_limit,
                                "bite_minimum": bite_minimum, "regime": regime,
                                "alive_at_stream_end": report["alive_at_stream_end"], "alive_after_settle": report["alive"], "divisions": report["divisions"],
                                "max_population": report["max_population_at_once"],
                            })
    return rows
