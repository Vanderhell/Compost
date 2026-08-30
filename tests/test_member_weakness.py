from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.biology_rules import BASE_RECEPTOR_MASS, structural_mass  # noqa: E402
from mathematical_organism.lifecycle import LifecycleConfig, LivingStructure  # noqa: E402
from mathematical_organism.sandbox_runtime import AutonomousOrganism, SandboxRuntime  # noqa: E402


class MemberWeaknessTests(unittest.TestCase):
    def _organism(self) -> AutonomousOrganism:
        organism = AutonomousOrganism(config=LifecycleConfig(reproduction_minimum_body=2))
        organism.body.reserve = 20.0
        for key in "ABCD":
            organism.body.add_structure(
                organism.body.atoms,
                LivingStructure(key, "ATOM", strength=4.0, maintenance=1.0),
            )
        return organism

    @staticmethod
    def _relation(organism: AutonomousOrganism, left: str, right: str, strength: float) -> LivingStructure:
        relation = LivingStructure((left, right), "RELATION", strength=strength, maintenance=0.5)
        organism.body.add_structure(organism.body.relations, relation)
        return relation

    @staticmethod
    def _full_weights(organism: AutonomousOrganism) -> dict[object, float]:
        weights = {key: 0.0 for key in organism.body.atoms}
        for collection in (organism.body.relations, organism.body.composites):
            for (left, right), structure in collection.items():
                if left in weights:
                    weights[left] = structure.strength if weights[left] == 0.0 else min(weights[left], structure.strength)
                if right in weights:
                    weights[right] = structure.strength if weights[right] == 0.0 else min(weights[right], structure.strength)
        return weights

    def test_member_weight_is_derived_from_links(self) -> None:
        organism = self._organism()
        self._relation(organism, "A", "B", 5.0)
        self._relation(organism, "B", "C", 2.0)
        organism.recompute_weakness_cache()
        self.assertEqual(organism.member_weights, {"A": 5.0, "B": 2.0, "C": 2.0, "D": 0.0})

    def test_weakest_cache_matches_full_scan_and_reports_all_ties(self) -> None:
        organism = self._organism()
        self._relation(organism, "A", "B", 5.0)
        self._relation(organism, "C", "D", 5.0)
        organism.recompute_weakness_cache()
        expected = self._full_weights(organism)
        minimum = min(expected.values())
        self.assertEqual(organism.member_weights, expected)
        self.assertEqual(organism.weakest_weight, minimum)
        self.assertEqual(organism.get_weakest_members(), ("A", "B", "C", "D"))

    def test_cached_lookup_does_not_recompute_graph(self) -> None:
        organism = self._organism()
        self._relation(organism, "A", "B", 5.0)
        organism.recompute_weakness_cache()
        original = organism.recompute_weakness_cache
        organism.recompute_weakness_cache = lambda: self.fail("cached weakest lookup scanned graph")  # type: ignore[method-assign]
        self.assertEqual(organism.get_weakest_members(), ("C", "D"))
        organism.recompute_weakness_cache = original  # type: ignore[method-assign]

    def test_strength_and_relation_change_update_cache(self) -> None:
        organism = self._organism()
        relation = self._relation(organism, "A", "B", 5.0)
        organism.rebuild_metabolic_indexes()
        organism.body.set_strength(relation, 2.0)
        organism.note_structure_changed(relation)
        self.assertEqual(organism.member_weights["A"], 2.0)
        organism.body.remove_structure(organism.body.relations, relation.key)
        organism.recompute_weakness_cache()
        self.assertEqual(organism.member_weights["A"], 0.0)

    def test_maintenance_weakens_the_weakest_member(self) -> None:
        organism = self._organism()
        self._relation(organism, "A", "B", 10.0)
        self._relation(organism, "B", "C", 1.0)
        self._relation(organism, "C", "D", 10.0)
        organism.rebuild_metabolic_indexes()
        self.assertEqual(organism.get_weakest_members(), ("B", "C"))
        organism._apply_maintenance_deficit(1.0)
        self.assertEqual(organism.body.atoms["B"].strength, 3.0)
        self.assertEqual(organism.body.atoms["C"].strength, 4.0)

    def test_forgetting_removes_member_and_routes_incident_mass_to_gut(self) -> None:
        organism = self._organism()
        organism.body.atoms["C"].strength = 1.0
        self._relation(organism, "A", "B", 8.0)
        self._relation(organism, "B", "C", 1.0)
        organism.rebuild_metabolic_indexes()
        removed = organism._detach_member("C", "TEST")
        self.assertEqual(removed, structural_mass(1.0))
        self.assertNotIn("C", organism.body.atoms)
        self.assertNotIn(("B", "C"), organism.body.relations)
        self.assertIn(("A", "B"), organism.body.relations)
        self.assertEqual(organism.gut_mass, removed)
        self.assertTrue(any(event.kind == "RESORB_MEMBER" for event in organism.result.events))

    def test_weakness_division_preserves_strong_components_and_mass(self) -> None:
        organism = self._organism()
        self._relation(organism, "A", "B", 10.0)
        self._relation(organism, "B", "C", 1.0)
        self._relation(organism, "C", "D", 10.0)
        organism.material_flow.structural_created_mass = organism.body.body_mass - BASE_RECEPTOR_MASS
        organism.rebuild_metabolic_indexes()
        before = organism.body.body_mass - BASE_RECEPTOR_MASS
        child = organism._reproduce_conservatively()
        self.assertIsNotNone(child)
        assert child is not None
        self.assertTrue({"A", "B"}.issubset(organism.body.atoms) or {"A", "B"}.issubset(child.body.atoms))
        self.assertTrue({"C", "D"}.issubset(organism.body.atoms) or {"C", "D"}.issubset(child.body.atoms))
        after = organism.body.body_mass - BASE_RECEPTOR_MASS + child.body.body_mass - BASE_RECEPTOR_MASS + organism.gut_mass
        self.assertEqual(before, after)
        self.assertFalse(
            {id(item) for item in organism.body._structures()}
            & {id(item) for item in child.body._structures()}
        )

    def test_failed_weakness_split_is_transactional_and_weight_is_not_energy(self) -> None:
        organism = AutonomousOrganism(config=LifecycleConfig(reproduction_minimum_body=2))
        for key in "AB":
            organism.body.add_structure(organism.body.atoms, LivingStructure(key, "ATOM", strength=8.0))
        self._relation(organism, "A", "B", 1.0)
        organism.rebuild_metabolic_indexes()
        before = (tuple(organism.body.atoms), organism.body.reserve, organism.member_weights.copy())
        self.assertIsNone(organism._reproduce_conservatively())
        self.assertEqual(before, (tuple(organism.body.atoms), organism.body.reserve, organism.member_weights))

    def test_weakness_information_dies_with_organism(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            organism = runtime.bootstrap()
            organism.body.add_structure(organism.body.atoms, LivingStructure("A", "ATOM", strength=4.0))
            organism.recompute_weakness_cache()
            corpse = organism._die(runtime)
            self.assertEqual(organism.member_weights, {})
            self.assertEqual(organism.get_weakest_members(), ())
            self.assertFalse(hasattr(corpse, "member_weights"))


if __name__ == "__main__":
    unittest.main()
