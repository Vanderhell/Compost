from __future__ import annotations

"""Deterministic random-HEX payload experiments; lifecycle logic is untouched."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.lifecycle import MathematicalLifePopulation, OrganismStatus  # noqa: E402


HEX = tuple("0123456789ABCDEF")
PATTERN = tuple("A7F3")
LENGTHS = (10_000, 100_000, 1_000_000)
SEEDS = tuple(range(10))
FREQUENCIES = (8, 16, 32, 64, 128, 256)


def random_hex(length: int, seed: int) -> tuple[str, ...]:
    """Return a cross-platform deterministic uniform HEX stream.

    The 64-bit LCG emits its high four bits per symbol.  It is intentionally
    defined here instead of relying on a runtime-specific random implementation.
    """
    if length < 0:
        raise ValueError("length must be non-negative")
    state = seed & ((1 << 64) - 1)
    output: list[str] = []
    for _ in range(length):
        state = (state * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        output.append(HEX[state >> 60])
    return tuple(output)


def hidden_pattern_hex(length: int, seed: int, frequency: int) -> tuple[str, ...]:
    """Overwrite every ``frequency``-th start with a motif, retaining length."""
    if frequency <= 0:
        raise ValueError("frequency must be positive")
    output = list(random_hex(length, seed))
    for start in range(0, length, frequency):
        for offset, symbol in enumerate(PATTERN):
            if start + offset < length:
                output[start + offset] = symbol
    return tuple(output)


def _top(collection: dict, *, limit: int = 5) -> list[tuple[str, float]]:
    return [
        (repr(key), item.strength)
        for key, item in sorted(collection.items(), key=lambda pair: (-pair[1].strength, repr(pair[0])))[:limit]
    ]


def _organism_row(organism) -> dict[str, object]:
    return {
        "id": organism.id,
        "parent_id": organism.parent_id,
        "generation": organism.generation,
        "status": organism.status.value,
        "size": organism.size,
        "strength": organism.total_strength,
        "reserve": organism.reserve,
        "nutrition_received": organism.nutrition_consumed_total,
        "top_structures": _top({**organism.atoms, **organism.composites}),
        "top_relations": _top({**organism.relations, **organism.composites}),
    }


def run_payload(payload: tuple[str, ...], *, seed: int, kind: str, frequency: int | None = None) -> dict[str, object]:
    population = MathematicalLifePopulation(payload)
    population.run_until_stream_exhausted(max_cycles=max(1, len(payload) * 2))
    population.settle(32)
    organisms = tuple(population.organisms.values())
    alive = tuple(item for item in organisms if item.status is OrganismStatus.ALIVE)
    ranked = sorted(organisms, key=lambda item: (-item.total_strength, -item.reserve, item.id))
    pattern_pairs = tuple(zip(PATTERN, PATTERN[1:]))
    pair_strengths = {
        repr(pair): sum(
            collection.get(pair).strength if pair in collection else 0.0
            for organism in organisms
            for collection in (organism.relations, organism.composites)
        )
        for pair in pattern_pairs
    }
    return {
        "kind": kind,
        "length": len(payload),
        "seed": seed,
        "frequency": frequency,
        "total_born": len(organisms),
        "alive": len(alive),
        "dead": len(organisms) - len(alive),
        "divisions": len(population.result.births),
        "max_generation": max((item.generation for item in organisms), default=0),
        "max_population": population.max_population,
        "total_strength": sum(item.total_strength for item in alive),
        "reserve": sum(item.reserve for item in alive),
        "nutrition_available": population.result.available_nutrition_total,
        "nutrition_consumed": population.result.consumed_nutrition_total,
        "strongest_organisms": [_organism_row(item) for item in ranked[:5]],
        "top_structures": _top({key: value for organism in organisms for key, value in {**organism.atoms, **organism.composites}.items()}),
        "top_relations": _top({key: value for organism in organisms for key, value in {**organism.relations, **organism.composites}.items()}),
        "inserted_pattern_pair_strength": pair_strengths,
    }


def main() -> int:
    pure = [
        run_payload(random_hex(length, seed), seed=seed, kind="pure_random")
        for length in LENGTHS
        for seed in SEEDS
    ]
    # Pattern-frequency comparison uses the middle length and all seeds.  The
    # baseline at this length is already present in ``pure``.
    hidden = [
        run_payload(hidden_pattern_hex(100_000, seed, frequency), seed=seed, kind="hidden_pattern", frequency=frequency)
        for frequency in FREQUENCIES
        for seed in SEEDS
    ]
    output = PROJECT_ROOT / "random-hex-experiment-results.json"
    output.write_text(json.dumps({"pure_random": pure, "hidden_pattern": hidden}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "pure_runs": len(pure),
        "hidden_runs": len(hidden),
        "pure_alive": sum(item["alive"] for item in pure),
        "hidden_alive": sum(item["alive"] for item in hidden),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
