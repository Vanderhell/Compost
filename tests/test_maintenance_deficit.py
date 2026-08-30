from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.biology_rules import structural_mass  # noqa: E402
from mathematical_organism.lifecycle import LivingStructure, MathematicalLifeOrganism  # noqa: E402
from mathematical_organism.sandbox_runtime import AutonomousOrganism, SandboxRuntime  # noqa: E402


class MaintenanceDeficitTests(unittest.TestCase):
    @staticmethod
    def _relation(organism: AutonomousOrganism, key: tuple[int, int], *, strength: float = 4.0, maintenance: float = 1.0) -> LivingStructure:
        relation = LivingStructure(key, "RELATION", strength=strength, maintenance=maintenance)
        organism.body.add_structure(organism.body.relations, relation)
        organism.material_flow.structural_created_mass += structural_mass(strength)
        return relation

    @staticmethod
    def _feed(organism: AutonomousOrganism, payload: tuple[int, ...]) -> None:
        organism.result.available_nutrition_total += len(payload)
        organism.enqueue_external_material(payload, (1.0,) * len(payload))
        organism.process_gut(organism.body.bite_limit(organism.config))

    def test_maintenance_deficit_causes_weakening_without_global_scan(self) -> None:
        organism = AutonomousOrganism()
        organism.body.reserve = 0.0
        relation = self._relation(organism, (1, 2), strength=5.0)
        organism.rebuild_metabolic_indexes()
        organism.body.cached_maintenance()
        with patch.object(MathematicalLifeOrganism, "_structures", side_effect=AssertionError("maintenance full scan")):
            required, paid, weakened, resorbed = organism.run_maintenance_settlement()
        self.assertEqual((required, paid, weakened, resorbed), (1.0, 0.0, 1, 0))
        self.assertEqual(relation.strength, 4.0)
        self.assertEqual(organism.maintenance_full_scans, 0)

    def test_short_deficit_is_recoverable(self) -> None:
        organism = AutonomousOrganism()
        organism.body.reserve = 0.0
        relation = self._relation(organism, (1, 2), strength=4.0)
        organism.rebuild_metabolic_indexes()
        organism.run_maintenance_settlement()
        weakened = relation.strength
        self._feed(organism, (1, 2, 1, 2))
        required, paid, weakened_count, _ = organism.run_maintenance_settlement()
        self.assertIn((1, 2), organism.body.relations)
        self.assertIsNot(organism.body.relations[(1, 2)], relation)
        self.assertEqual(weakened_count, 0)
        self.assertEqual(paid, required)
        self.assertEqual(organism.maintenance_deficit, 0.0)

    def test_long_starvation_progressively_resorbs_and_lowers_maintenance(self) -> None:
        organism = AutonomousOrganism()
        organism.body.reserve = 0.0
        for index in range(6):
            self._relation(organism, (index, index + 1), strength=2.0)
        start_mass = organism.body.body_mass
        start_maintenance = organism.body.cached_maintenance()
        organism.rebuild_metabolic_indexes()
        for _ in range(18):
            organism.run_maintenance_settlement()
            if organism.body.size == 0:
                break
        self.assertEqual(organism.body.size, 0)
        self.assertLess(organism.body.body_mass, start_mass)
        self.assertLess(organism.body.cached_maintenance(), start_maintenance)
        self.assertGreater(organism.gut_mass, 0)
        peak_gut = organism.gut_mass
        while organism.gut_mass:
            self.assertLessEqual(organism.process_gut(organism.body.bite_limit(organism.config)), organism.body.bite_limit(organism.config))
        self.assertGreater(organism.material_flow.resorption_expelled_mass, 0)
        self.assertGreater(peak_gut, 0)
        organism.verify_material_conservation()

    def test_zero_reserve_does_not_immediately_kill_but_viability_loss_does(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            organism = runtime.bootstrap()
            organism.body.reserve = 0.0
            self._relation(organism, (1, 2), strength=2.0)
            organism.rebuild_metabolic_indexes()
            organism.run_maintenance_settlement()
            self.assertTrue(organism.alive)
            self.assertEqual(organism.body.size, 1)
            organism.live_step(runtime)
            # The member-level rule keeps a zero-reserve organism alive until
            # its selected weakest member actually reaches detachment; the
            # first no-food step drains the mass lost during weakening.
            self.assertTrue(organism.alive)
            organism.live_step(runtime)
            self.assertFalse(organism.alive)
            self.assertEqual(organism.body.size, 0)

    def test_relearn_is_required_after_resorption_and_strength_never_becomes_energy(self) -> None:
        organism = AutonomousOrganism()
        organism.body.reserve = 0.0
        relation = self._relation(organism, (1, 2), strength=1.0)
        organism.rebuild_metabolic_indexes()
        reserve_before = organism.body.reserve
        organism.run_maintenance_settlement()
        self.assertNotIn((1, 2), organism.body.relations)
        self.assertEqual(organism.body.reserve, reserve_before)
        self._feed(organism, (1, 2, 1, 2))
        rebuilt = organism.body.relations[(1, 2)]
        self.assertIsNot(rebuilt, relation)
        self.assertGreater(rebuilt.strength, 0.0)
        self.assertGreater(organism.material_flow.resorption_expelled_mass, 0)
        organism.verify_material_conservation()

    def test_large_skeleton_resorption_is_incremental_and_uses_shared_gut_capacity(self) -> None:
        organism = AutonomousOrganism()
        organism.body.reserve = 0.0
        for index in range(300):
            self._relation(organism, (index, index + 1), strength=1.0)
        organism.rebuild_metabolic_indexes()
        start_size = organism.body.size
        organism.run_maintenance_settlement()
        self.assertLess(organism.body.size, start_size)
        self.assertGreater(organism.body.size, 0)
        # Continue the same deficit state; each settlement removes only its
        # heap-selected local candidate, accumulating a real resorption backlog.
        while organism.body.size:
            organism.run_maintenance_settlement()
        self.assertEqual(organism.gut_mass, 300)
        first = organism.process_gut(128)
        self.assertEqual(first, 128)
        self.assertEqual(organism.gut_mass, 172)
        while organism.gut_mass:
            organism.process_gut(128)
        organism.verify_material_conservation()


if __name__ == "__main__":
    unittest.main()
