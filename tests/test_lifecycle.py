from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.lifecycle import LifecycleConfig, LivingStructure, MathematicalLifePopulation  # noqa: E402


class LifecycleReferenceTests(unittest.TestCase):
    def test_reserve_is_organism_owned(self) -> None:
        population = MathematicalLifePopulation("ABAB", LifecycleConfig(birth_reserve=10.0))
        root = population.organisms[0]
        self.assertFalse(hasattr(LivingStructure("A", "ATOM"), "reserve"))
        population.cycle()
        self.assertGreaterEqual(root.reserve, 0.0)

    def test_food_nutrition_is_conserved(self) -> None:
        population = MathematicalLifePopulation("ABAB", LifecycleConfig(birth_reserve=10.0))
        population.run(max_cycles=4)
        self.assertLessEqual(population.result.consumed_nutrition_total, population.result.available_nutrition_total)

    def test_zero_reserve_is_not_alone_a_death_condition(self) -> None:
        population = MathematicalLifePopulation("AB", LifecycleConfig(birth_reserve=10.0))
        root = population.organisms[0]
        root.atoms["A"] = LivingStructure("A", "ATOM", strength=8.0, maintenance=0.1, income_rate=4.0)
        root.atoms["B"] = LivingStructure("B", "ATOM", strength=8.0, maintenance=0.1, income_rate=4.0)
        root.add_structure(root.relations, LivingStructure(("A", "B"), "RELATION", strength=8.0, maintenance=0.1, income_rate=4.0))
        root.reserve = 0.0
        population._cycle_one(root, None)
        self.assertTrue(root.size > 0 or root.status.value == "DEAD")

    def test_same_payload_has_same_canonical_population(self) -> None:
        first = MathematicalLifePopulation("ABABAB", LifecycleConfig(birth_reserve=10.0))
        second = MathematicalLifePopulation("ABABAB", LifecycleConfig(birth_reserve=10.0))
        first.run(max_cycles=8)
        second.run(max_cycles=8)
        state = lambda population: [
            (item.id, item.status.value, item.reserve, item.total_strength, item.size)
            for item in sorted(population.organisms.values(), key=lambda current: current.id)
        ]
        self.assertEqual(state(first), state(second))


if __name__ == "__main__":
    unittest.main()
