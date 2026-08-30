from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.lifecycle import LifecycleConfig, LivingStructure  # noqa: E402
from mathematical_organism.sandbox_runtime import AutonomousOrganism  # noqa: E402


class OrganismReserveTests(unittest.TestCase):
    def _parent(self) -> AutonomousOrganism:
        parent = AutonomousOrganism(config=LifecycleConfig(reproduction_minimum_body=2, birth_cost=0.5))
        parent.body.reserve = 10.0
        for key in "ABCD":
            parent.body.add_structure(parent.body.atoms, LivingStructure(key, "ATOM", strength=8.0, maintenance=0.1))
        parent.body.add_structure(parent.body.relations, LivingStructure(("A", "B"), "RELATION", strength=8.0, maintenance=0.1))
        parent.body.add_structure(parent.body.relations, LivingStructure(("C", "D"), "RELATION", strength=8.0, maintenance=0.1))
        parent.rebuild_metabolic_indexes()
        return parent

    def test_living_structure_has_no_reserve_and_organism_has_one(self) -> None:
        organism = AutonomousOrganism()
        self.assertTrue(hasattr(organism.body, "reserve"))
        self.assertFalse(hasattr(LivingStructure("A", "ATOM"), "reserve"))

    def test_division_child_starts_zero_and_parent_alone_pays(self) -> None:
        parent = self._parent()
        before = parent.body.reserve
        child = parent._reproduce_conservatively()
        self.assertIsNotNone(child)
        assert child is not None
        self.assertEqual(child.body.reserve, 0.0)
        self.assertAlmostEqual(parent.body.reserve, before - parent.config.birth_cost)
        self.assertTrue(child.alive)

    def test_failed_division_preserves_parent_reserve(self) -> None:
        parent = AutonomousOrganism(config=LifecycleConfig(reproduction_minimum_body=2))
        parent.body.reserve = 3.0
        parent.body.add_structure(parent.body.atoms, LivingStructure("A", "ATOM", strength=4.0))
        parent.body.add_structure(parent.body.atoms, LivingStructure("B", "ATOM", strength=4.0))
        self.assertIsNone(parent._reproduce_conservatively())
        self.assertEqual(parent.body.reserve, 3.0)


if __name__ == "__main__":
    unittest.main()
