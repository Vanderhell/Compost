from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.biology_rules import BASE_RECEPTOR_MASS, BYTE_RECEPTOR_COUNT, forgetting_delta, lazy_metabolism_delta, structural_mass  # noqa: E402
from mathematical_organism.lifecycle import LifecycleConfig, LivingStructure, MathematicalLifeOrganism  # noqa: E402
from mathematical_organism.sandbox_runtime import AutonomousOrganism  # noqa: E402


class StructuralMassTests(unittest.TestCase):
    def test_all_256_byte_receptors_exist_without_learned_strength(self) -> None:
        body = MathematicalLifeOrganism(0, None, 0, 0, 0)
        self.assertEqual(body.receptors, tuple(range(BYTE_RECEPTOR_COUNT)))
        self.assertEqual(body.body_mass, BASE_RECEPTOR_MASS)
        self.assertEqual(body.atoms, {})

    def test_relation_and_composite_are_materialized_mass_objects(self) -> None:
        body = MathematicalLifeOrganism(0, None, 0, 0, 0)
        relation = LivingStructure((1, 2), "RELATION", strength=4.0)
        composite = LivingStructure((1, 2), "COMPOSITE", strength=8.0, members=((1, 2),))
        body.add_structure(body.relations, relation); body.add_structure(body.composites, composite)
        self.assertEqual(composite.members, ((1, 2),))
        self.assertEqual(body.body_mass, BASE_RECEPTOR_MASS + 3 + 4)
        body.verify_body_mass()

    def test_structural_mass_formula_is_sublinear_and_strength_updates_incrementally(self) -> None:
        self.assertEqual([structural_mass(value) for value in (1, 2, 3, 4, 7, 8, 15, 16)], [1, 2, 2, 3, 3, 4, 4, 5])
        self.assertLess(structural_mass(1_000_000), 32)
        body = MathematicalLifeOrganism(0, None, 0, 0, 0)
        relation = LivingStructure((1, 2), "RELATION", strength=4.0)
        body.add_structure(body.relations, relation); before = body.body_mass
        body.set_strength(relation, 8.0)
        self.assertEqual(body.body_mass, before + 1)
        body.set_strength(relation, 1.0)
        self.assertEqual(relation.strength, 1.0)
        self.assertEqual(body.body_mass, BASE_RECEPTOR_MASS + 1)
        body.verify_body_mass()

    def test_bite_uses_mass_not_raw_object_count(self) -> None:
        config = LifecycleConfig(bite_minimum=1)
        body = MathematicalLifeOrganism(0, None, 0, 0, 0)
        relation = LivingStructure((1, 2), "RELATION", strength=1_000_000.0)
        body.add_structure(body.relations, relation)
        self.assertEqual(body.bite_limit(config), body.body_mass)
        self.assertLess(body.bite_limit(config), 300)

    def test_conservative_division_preserves_strength_reserve_and_mass_cache(self) -> None:
        parent = AutonomousOrganism(config=LifecycleConfig(reproduction_minimum_body=2))
        parent.body.reserve = 40.0
        for symbol in "ABCD":
            parent.body.atoms[symbol] = LivingStructure(symbol, "ATOM", strength=20.0, maintenance=0.25)
        parent.body.add_structure(parent.body.relations, LivingStructure(("A", "B"), "RELATION", strength=16.0, maintenance=0.5))
        parent.body.add_structure(parent.body.relations, LivingStructure(("C", "D"), "RELATION", strength=16.0, maintenance=0.5))
        strength_before, reserve_before = parent.body.total_strength, parent.body.reserve
        child = parent._reproduce_conservatively()
        self.assertIsNotNone(child)
        self.assertAlmostEqual(strength_before, parent.body.total_strength + child.body.total_strength)  # type: ignore[union-attr]
        self.assertAlmostEqual(reserve_before, parent.body.reserve + parent.config.birth_cost)  # type: ignore[union-attr]
        self.assertEqual(child.body.reserve, 0.0)  # type: ignore[union-attr]
        parent.body.verify_body_mass(); child.body.verify_body_mass()  # type: ignore[union-attr]

    def test_digest_materializes_receptor_relations_and_updates_mass(self) -> None:
        organism = AutonomousOrganism()
        bite = (1, 2, 3, 1, 2, 3)
        trace: dict[str, int] = {}
        organism.result.available_nutrition_total = float(len(bite))
        organism.digest(organism.body, bite, (1.0,) * len(bite), trace)
        mass_after_digest = organism.body.body_mass
        organism.consolidate(organism.body, trace)
        self.assertEqual(set(bite), organism.body.activated_receptors)
        self.assertGreaterEqual(trace["relation_evidence_generated"], 5)
        self.assertIn((1, 2), {**organism.body.relations, **organism.body.composites})
        self.assertIn((2, 3), {**organism.body.relations, **organism.body.composites})
        self.assertIn((3, 1), {**organism.body.relations, **organism.body.composites})
        self.assertGreater(mass_after_digest, BASE_RECEPTOR_MASS)
        self.assertGreaterEqual(trace["body_mass_after"], trace["body_mass_before"])
        self.assertEqual(trace["next_bite"], organism.body.bite_limit(organism.config))
        organism.body.verify_body_mass()

    def test_incremental_resource_cache_matches_reference_after_digest_and_metabolism(self) -> None:
        organism = AutonomousOrganism()
        bite = tuple(range(64)) * 2
        organism.result.available_nutrition_total = float(len(bite))
        organism.digest(organism.body, bite, (1.0,) * len(bite))
        self.assertAlmostEqual(organism.body.cached_maintenance(), sum(item.maintenance for item in organism.body._structures()))
        organism.consolidate(organism.body)
        organism.maintain_and_resorb(organism.body)
        self.assertAlmostEqual(organism.body.cached_maintenance(), sum(item.maintenance for item in organism.body._structures()))
        organism.body.verify_body_mass()

    def test_local_digest_index_and_caches_match_reference_recalculation(self) -> None:
        fast = AutonomousOrganism()
        reference = AutonomousOrganism()
        bites = ((1, 2, 3, 1, 2, 3), (3, 2, 1, 3, 2, 1))
        for bite in bites:
            for organism in (fast, reference):
                organism.result.available_nutrition_total += len(bite)
                organism.digest(organism.body, bite, (1.0,) * len(bite))
            reference.body.refresh_resource_cache()
        def state(organism: AutonomousOrganism) -> dict[tuple[int, int], tuple[float, float]]:
            return {key: (item.strength, item.evidence) for key, item in organism.body.relations.items()}
        self.assertEqual(state(fast), state(reference))
        self.assertEqual(fast.body.body_mass, fast.body.full_body_mass())
        self.assertEqual(fast.body.cached_maintenance(), sum(item.maintenance for item in fast.body._structures()))

    def test_digest_never_recalculates_full_body_mass(self) -> None:
        organism = AutonomousOrganism()
        organism.enable_hot_profile()
        organism.result.available_nutrition_total = 6.0
        with patch.object(MathematicalLifeOrganism, "full_body_mass", side_effect=AssertionError("full scan on digest path")):
            organism.digest(organism.body, (1, 2, 3, 1, 2, 3), (1.0,) * 6)
        self.assertGreater(organism.hot_metrics.calls.get("relation_lookup", 0), 0)  # type: ignore[union-attr]

    def test_forgetting_and_next_digest_are_not_commutative(self) -> None:
        """A bite between maintenance slices would change the current law.

        The counterexample is intentionally small: a dormant relation forgets
        at the boundary, whereas a preceding use raises its income above the
        forgetting predicate.  Therefore a cursor that lets the next bite run
        before the whole maintenance epoch completes cannot be mathematically
        equivalent without buffering/replaying that bite or changing time.
        """
        config = LifecycleConfig()
        relation = LivingStructure((1, 2), "RELATION", strength=5.0, maintenance=config.relation_maintenance, income_rate=0.0)
        boundary_then_bite = forgetting_delta(relation, config).strength_after + config.relation_income
        relation.strength += config.relation_income
        relation.income_rate += config.relation_income
        bite_then_boundary = forgetting_delta(relation, config).strength_after
        self.assertEqual(boundary_then_bite, 4.8)
        self.assertEqual(bite_then_boundary, 5.8)
        self.assertNotEqual(boundary_then_bite, bite_then_boundary)

    def test_lazy_local_metabolism_matches_eager_recurrence_and_mass_delta(self) -> None:
        config = LifecycleConfig(income_decay=0.8)
        for strength, income, epochs in ((5.0, 0.0, 7), (5.0, 3.0, 7), (64.0, 0.6, 30)):
            eager = LivingStructure((1, 2), "RELATION", strength=strength, maintenance=0.5, income_rate=income)
            for _ in range(epochs):
                delta = forgetting_delta(eager, config)
                eager.strength = delta.strength_after
                eager.income_rate = delta.income_rate_after
            lazy = lazy_metabolism_delta(strength=strength, income_rate=income, maintenance=0.5, income_decay=config.income_decay, epochs=epochs)
            self.assertAlmostEqual(lazy.strength_after, eager.strength)
            self.assertAlmostEqual(lazy.income_rate_after, eager.income_rate)
        organism = AutonomousOrganism(config=config)
        relation = LivingStructure((1, 2), "RELATION", strength=64.0, maintenance=0.5, income_rate=0.0)
        organism.body.add_structure(organism.body.relations, relation)
        mass_before = organism.body.body_mass
        organism.apply_pending_metabolism(organism.body, relation, 7, config.income_decay)
        self.assertEqual(relation.last_metabolic_epoch, 7)
        self.assertLess(organism.body.body_mass, mass_before)
        organism.body.verify_body_mass()


if __name__ == "__main__":
    unittest.main()
