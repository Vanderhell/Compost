from __future__ import annotations

"""End-to-end lifecycle gates for the frozen public organism model.

These tests intentionally use the real sandbox transition methods.  They do
not inject a replacement scheduler or mutate a status flag to simulate a
biological outcome.
"""

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.biology_rules import BASE_RECEPTOR_MASS, structural_mass  # noqa: E402
from mathematical_organism.lifecycle import LifecycleConfig, LivingStructure  # noqa: E402
from mathematical_organism.parallel_runtime import AutonomousMultiprocessingRuntime  # noqa: E402
from mathematical_organism.sandbox_runtime import AutonomousOrganism, SandboxRuntime  # noqa: E402
from mathematical_organism.territory import FoodTerritory, assert_disjoint_live_territories  # noqa: E402


class PublicLifecycleGateTests(unittest.TestCase):
    @staticmethod
    def _add_relation(organism: AutonomousOrganism, pair: tuple[int, int], *, strength: float = 2.0) -> None:
        organism.body.add_structure(
            organism.body.relations,
            LivingStructure(pair, "RELATION", strength=strength, maintenance=1.0),
        )
        organism.material_flow.structural_created_mass += structural_mass(strength)

    @staticmethod
    def _seed_dividable(parent: AutonomousOrganism) -> None:
        parent.body.reserve = 10.0
        for symbol in (1, 2, 3, 4):
            parent.body.add_structure(
                parent.body.atoms,
                LivingStructure(symbol, "ATOM", strength=10.0, maintenance=0.1),
            )
        for pair, strength in (((1, 2), 8.0), ((3, 4), 8.0)):
            parent.body.add_structure(
                parent.body.relations,
                LivingStructure(pair, "RELATION", strength=strength, maintenance=0.2),
            )
        parent.material_flow.structural_created_mass = parent.body.body_mass - BASE_RECEPTOR_MASS
        parent.rebuild_metabolic_indexes()

    def test_ingest_eat_grows_skeleton_and_bite_with_exact_accounting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=64)
            root = runtime.bootstrap()
            initial_mass = root.body.body_mass
            initial_bite = root.body.bite_limit(root.config)
            payload = bytes((1, 2, 3, 1, 2, 3) * 64)
            (runtime.inbox / "growth.bin").write_bytes(payload)

            for _ in range(128):
                root.live_step(runtime)
                original, eaten, remaining, duplicates = runtime.food_accounting()
                if original and remaining == 0 and not any(runtime.inbox.iterdir()):
                    break

            original, eaten, remaining, duplicates = runtime.food_accounting()
            self.assertEqual((original, eaten, remaining, duplicates), (len(payload), len(payload), 0, 0))
            self.assertGreater(root.body.body_mass, initial_mass)
            self.assertGreaterEqual(root.body.bite_limit(root.config), initial_bite)
            self.assertGreater(root.successful_bites, 0)
            root.verify_material_conservation()
            runtime.verify_world_material_conservation()

    def test_division_moves_skeleton_to_zero_reserve_child_with_disjoint_territory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            parent = runtime.bootstrap()
            parent.config = LifecycleConfig(reproduction_minimum_body=2)
            self._seed_dividable(parent)
            before = parent.body.body_mass - BASE_RECEPTOR_MASS

            child = parent._commit_skeleton_partition({1, 2})
            self.assertIsNotNone(child)
            assert child is not None
            runtime.register_child(parent, child)

            self.assertEqual(child.body.reserve, 0.0)
            self.assertEqual(child.activity_ledger.metabolic_debt, 0.0)
            self.assertEqual(child.gut_mass, 0)
            self.assertFalse(parent.territory_state.territory.overlaps(child.territory_state.territory))
            self.assertEqual(
                before,
                parent.body.body_mass - BASE_RECEPTOR_MASS + child.body.body_mass - BASE_RECEPTOR_MASS,
            )
            assert_disjoint_live_territories([parent.territory_state, child.territory_state])
            parent.verify_material_conservation()
            child.verify_material_conservation()
            runtime.verify_world_material_conservation()

    def test_starvation_weakens_then_resorbs_and_dies_only_after_viability_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            organism = runtime.bootstrap()
            organism.body.reserve = 0.0
            self._add_relation(organism, (1, 2), strength=2.0)
            organism.rebuild_metabolic_indexes()

            organism.run_maintenance_settlement()
            self.assertTrue(organism.alive)
            self.assertEqual(organism.body.relations[(1, 2)].strength, 1.0)
            organism.live_step(runtime)
            self.assertTrue(organism.alive)
            organism.live_step(runtime)
            self.assertFalse(organism.alive)
            self.assertGreater(organism.material_flow.resorbed_mass, 0)
            self.assertGreaterEqual(organism.gut_mass, 0)
            self.assertTrue(runtime.is_territory_unoccupied(FoodTerritory()))

    def test_death_releases_territory_and_corpse_energy_is_neutral_and_conserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            parent = runtime.bootstrap()
            parent.body.reserve = 5.0
            self._add_relation(parent, (1, 2), strength=1.0)
            parent.rebuild_metabolic_indexes()
            territory = parent.territory_state.territory

            corpse = parent._die(runtime)
            self.assertIsNotNone(corpse)
            assert corpse is not None
            self.assertFalse(parent.alive)
            self.assertEqual(corpse.remaining_energy, 5.0)
            self.assertTrue(runtime.is_territory_unoccupied(territory))
            self.assertFalse(hasattr(corpse, "relations"))

            eater = AutonomousOrganism("ORG-EATER", territory=territory)
            reserve_before = eater.body.reserve
            gained = eater._consume_corpse(runtime)
            self.assertEqual(gained, 5.0)
            self.assertEqual(eater.body.reserve, reserve_before + gained)
            self.assertFalse(runtime.corpses)

    def test_nested_territory_release_and_reclaim_preserves_food_discoverability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=64)
            parent = runtime.bootstrap()
            first = parent.spawn_child()
            runtime.register_child(parent, first)
            second = parent.spawn_child()
            runtime.register_child(parent, second)
            # Parent is D00, while its two sibling branches are D01 and D1.
            self.assertEqual(parent.territory_state.territory.path, (0, 0))
            first._die(runtime)
            second._die(runtime)
            self.assertTrue(parent._reclaim_sibling_if_available(runtime))
            self.assertEqual(parent.territory_state.territory.path, (0,))
            self.assertTrue(parent._reclaim_sibling_if_available(runtime))
            self.assertEqual(parent.territory_state.territory.path, ())

            payload = bytes(range(64))
            (runtime.inbox / "reclaimed.bin").write_bytes(payload)
            for _ in range(64):
                parent.live_step(runtime)
                original, _eaten, remaining, _duplicates = runtime.food_accounting()
                if original and remaining == 0 and not any(runtime.inbox.iterdir()):
                    break
            original, eaten, remaining, duplicates = runtime.food_accounting()
            self.assertEqual((original, eaten, remaining, duplicates), (64, 64, 0, 0))

    def test_remote_initial_worker_placement_preserves_child_state_without_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = AutonomousMultiprocessingRuntime(Path(directory) / "sandbox", workers=2)
            parent = AutonomousOrganism("ORG-PARENT")
            child = parent.spawn_child()
            child.body.reserve = 0.0
            runtime.organism_workers[parent.name] = 0
            runtime.worker_organisms[0].add(parent.name)

            target = runtime._handle(
                "birth",
                (0, parent.name, parent.territory_state.territory.path,
                 child.name, child.territory_state.territory.path, child),
            )
            self.assertEqual(target, 1)
            kind, delivered = runtime.controls[1].get(timeout=1.0)
            self.assertEqual(kind, "NEWBORN")
            self.assertEqual(delivered.body.reserve, 0.0)
            self.assertEqual(delivered.gut_mass, 0)
            self.assertEqual(delivered.territory_state.territory, child.territory_state.territory)
            self.assertEqual(runtime.organism_workers[parent.name], 0)
            self.assertEqual(runtime.metrics().worker_migrations, 0)


if __name__ == "__main__":
    unittest.main()
