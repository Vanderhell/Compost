from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.biology_rules import BASE_RECEPTOR_MASS, structural_mass  # noqa: E402
from mathematical_organism.lifecycle import LifecycleConfig, LivingStructure  # noqa: E402
from mathematical_organism.sandbox_runtime import AutonomousOrganism  # noqa: E402


class IndependentConservationAuditTests(unittest.TestCase):
    @staticmethod
    def dynamic_mass(organism: AutonomousOrganism) -> int:
        return sum(
            structural_mass(item.strength)
            for collection in (organism.body.relations, organism.body.composites)
            for item in collection.values()
        )

    def test_cross_split_partition_preserves_independent_mass(self) -> None:
        parent = AutonomousOrganism(config=LifecycleConfig(reproduction_minimum_body=2))
        parent.body.reserve = 40.0
        for symbol in "ABCD":
            parent.body.add_structure(
                parent.body.atoms,
                LivingStructure(symbol, "ATOM", strength=8.0, maintenance=0.25),
            )
        for pair in (("A", "B"), ("B", "C"), ("C", "D")):
            parent.body.add_structure(
                parent.body.relations,
                LivingStructure(pair, "RELATION", strength=8.0, maintenance=0.5),
            )
        parent.material_flow.structural_created_mass = self.dynamic_mass(parent)
        before = self.dynamic_mass(parent) + parent.gut_mass
        child = parent._reproduce_conservatively()
        self.assertIsNotNone(child)
        assert child is not None
        after = self.dynamic_mass(parent) + self.dynamic_mass(child) + parent.gut_mass
        self.assertEqual(before, after)
        self.assertEqual(
            parent.material_flow.structural_created_mass,
            after + parent.material_flow.resorbed_mass,
        )
        self.assertEqual(child.body.reserve, 0.0)
        self.assertEqual(parent.body.reserve, 39.0)
        self.assertEqual(
            {id(item) for item in parent.body._structures()}
            & {id(item) for item in child.body._structures()},
            set(),
        )

    def test_empty_body_mass_is_only_fixed_receptor_mass(self) -> None:
        organism = AutonomousOrganism()
        self.assertEqual(organism.body.body_mass, BASE_RECEPTOR_MASS)
        self.assertEqual(self.dynamic_mass(organism), 0)


if __name__ == "__main__":
    unittest.main()
