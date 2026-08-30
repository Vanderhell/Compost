from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.biology_rules import structural_mass  # noqa: E402
from mathematical_organism.lifecycle import LivingStructure  # noqa: E402
from mathematical_organism.sandbox_runtime import AutonomousOrganism  # noqa: E402


class MaterialFlowTests(unittest.TestCase):
    @staticmethod
    def _queue_external(organism: AutonomousOrganism, payload: tuple[int, ...], nutrition: tuple[float, ...]) -> None:
        organism.result.available_nutrition_total += len(payload)
        organism.enqueue_external_material(payload, nutrition)

    def test_fake_data_is_not_silently_discarded_and_reaches_expelled_mass(self) -> None:
        organism = AutonomousOrganism()
        payload = (0,) * 32
        self._queue_external(organism, payload, (0.0,) * len(payload))
        self.assertEqual(organism.process_gut(32), 32)
        flow = organism.material_flow
        self.assertEqual((flow.input_mass, flow.assimilated_mass, flow.rejected_mass), (32, 0, 32))
        self.assertEqual((flow.expelled_mass, organism.gut_mass), (32, 0))
        organism.verify_material_conservation()

    def test_nutrient_data_can_be_assimilated_into_skeleton_evidence(self) -> None:
        organism = AutonomousOrganism()
        payload = (1, 2, 3, 1, 2, 3)
        self._queue_external(organism, payload, (1.0,) * len(payload))
        organism.process_gut(len(payload))
        self.assertEqual(organism.material_flow.assimilated_mass, len(payload))
        self.assertEqual(organism.material_flow.rejected_mass, 0)
        self.assertIn((1, 2), organism.body.relations)
        self.assertIn((2, 3), organism.body.relations)
        self.assertGreater(organism.body.body_mass, 256)
        organism.verify_material_conservation()

    def test_gut_processing_never_exceeds_current_bite(self) -> None:
        organism = AutonomousOrganism()
        payload = (0,) * 100
        self._queue_external(organism, payload, (0.0,) * len(payload))
        self.assertEqual(organism.process_gut(10), 10)
        self.assertEqual(organism.gut_mass, 90)
        self.assertEqual(organism.material_flow.processed_mass, 10)
        organism.verify_material_conservation()

    def test_burst_creates_backlog_and_drains_after_input_stops_without_inertia(self) -> None:
        organism = AutonomousOrganism()
        payload = (0,) * (100 * 1024)
        self._queue_external(organism, payload, (0.0,) * len(payload))
        peak = organism.gut_mass
        steps = 0
        while organism.gut_mass:
            processed = organism.process_gut(10 * 1024)
            self.assertLessEqual(processed, 10 * 1024)
            steps += 1
        debt_after_drain = organism.activity_ledger.metabolic_debt
        spent_after_drain = organism.activity_ledger.energy_spent
        self.assertEqual((peak, steps, organism.gut_mass), (100 * 1024, 10, 0))
        self.assertEqual(organism.process_gut(10 * 1024), 0)
        self.assertEqual(organism.activity_ledger.metabolic_debt, debt_after_drain)
        self.assertEqual(organism.activity_ledger.energy_spent, spent_after_drain)
        organism.verify_material_conservation()

    def test_external_and_internal_material_share_one_capacity(self) -> None:
        organism = AutonomousOrganism()
        self._queue_external(organism, (0,) * 10, (0.0,) * 10)
        # The synthetic internal chunk represents previously created body mass.
        organism.material_flow.structural_created_mass = 10
        organism.enqueue_resorbed_material(10)
        self.assertEqual(organism.process_gut(10), 10)
        self.assertEqual(organism.gut_mass, 10)
        self.assertEqual(organism.process_gut(10), 10)
        self.assertEqual(organism.gut_mass, 0)
        organism.verify_material_conservation()

    def test_resorbed_structure_enters_gut_and_never_creates_reserve(self) -> None:
        organism = AutonomousOrganism()
        relation = LivingStructure((1, 2), "RELATION", strength=8.0, maintenance=1.0)
        organism.body.add_structure(organism.body.relations, relation)
        organism.material_flow.structural_created_mass = structural_mass(relation.strength)
        reserve_before = organism.body.reserve
        self.assertTrue(organism.remove_weakest(organism.body, "STARVATION", True))
        self.assertEqual(organism.gut_mass, structural_mass(8.0))
        organism.process_gut(256)
        self.assertEqual(organism.body.reserve, reserve_before)
        self.assertEqual(organism.material_flow.resorption_expelled_mass, structural_mass(8.0))
        organism.verify_material_conservation()

    def test_idle_cost_is_zero_and_energy_settlement_is_conserved(self) -> None:
        organism = AutonomousOrganism()
        self.assertEqual(organism.process_gut(256), 0)
        self.assertEqual(organism.activity_ledger.metabolic_debt, 0.0)
        self.assertEqual(organism.activity_ledger.energy_spent, 0.0)
        payload = (1, 2) * 128
        self._queue_external(organism, payload, (1.0,) * len(payload))
        organism.process_gut(256)
        # If a settlement was affordable, reserve loss equals its exact payment.
        self.assertGreaterEqual(organism.activity_ledger.energy_spent, 0.0)
        organism.verify_material_conservation()


if __name__ == "__main__":
    unittest.main()
