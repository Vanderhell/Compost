from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.biology_rules import ActivityCounters, ActivityLedger  # noqa: E402
from mathematical_organism.lifecycle import MathematicalLifeOrganism  # noqa: E402
from mathematical_organism.sandbox_runtime import AutonomousOrganism, SandboxRuntime  # noqa: E402


class ActivityLedgerTests(unittest.TestCase):
    @staticmethod
    def _eat(organism: AutonomousOrganism, byte_count: int) -> None:
        bite = (1, 2) * 128
        organism.result.available_nutrition_total += byte_count
        remaining = byte_count
        while remaining:
            part = bite[:min(len(bite), remaining)]
            trace: dict[str, int] = {}
            organism.digest(organism.body, part, (1.0,) * len(part), trace)
            organism._record_digest_activity(trace, part)
            organism._settle_activity_debt()
            remaining -= len(part)

    def test_idle_organism_cost_is_minimal(self) -> None:
        organism = AutonomousOrganism()
        # A real idle step has no FOOD and produces no debt or payment.
        class IdleSandbox:
            def has_active_food(self) -> bool: return True
            def refresh_food_sources(self) -> None: return None
            food_sources: dict = {}
        organism.live_step(IdleSandbox())  # type: ignore[arg-type]
        self.assertEqual(organism.activity_ledger.metabolic_debt, 0.0)
        self.assertEqual(organism.activity_ledger.energy_spent, 0.0)

    def test_active_eating_costs_more_than_idle_and_scales_with_bytes(self) -> None:
        idle, ten_kib, hundred_kib = AutonomousOrganism(), AutonomousOrganism(), AutonomousOrganism()
        self._eat(ten_kib, 10 * 1024)
        self._eat(hundred_kib, 100 * 1024)
        self.assertEqual(idle.activity_ledger.energy_spent, 0.0)
        self.assertGreater(ten_kib.activity_ledger.energy_spent, idle.activity_ledger.energy_spent)
        self.assertGreater(hundred_kib.activity_ledger.energy_spent, ten_kib.activity_ledger.energy_spent)
        self.assertEqual(ten_kib.activity_ledger.counters.bytes_eaten, 10 * 1024)
        self.assertEqual(hundred_kib.activity_ledger.counters.bytes_eaten, 100 * 1024)

    def test_relation_growth_and_settlement_threshold_are_deterministic(self) -> None:
        organism = AutonomousOrganism()
        organism.result.available_nutrition_total = 6.0
        trace: dict[str, int] = {}
        organism.digest(organism.body, (1, 2, 3, 1, 2, 3), (1.0,) * 6, trace)
        organism._record_digest_activity(trace, (1, 2, 3, 1, 2, 3))
        self.assertGreater(organism.activity_ledger.counters.relations_created, 0)
        self.assertGreater(organism.activity_ledger.counters.structural_mass_added, 0)
        before = organism.activity_ledger.energy_spent
        settled = organism._settle_activity_debt()
        self.assertEqual(settled, organism.activity_ledger.energy_spent > before)
        self.assertGreaterEqual(organism.activity_ledger.settlements, 0)

    def test_settlement_reduces_reserve_exactly_and_strength_is_not_energy(self) -> None:
        organism = AutonomousOrganism()
        organism.result.available_nutrition_total = 512.0
        bite = (1, 2) * 128
        for _ in range(2):
            trace: dict[str, int] = {}
            organism.digest(organism.body, bite, (1.0,) * len(bite), trace)
            organism._record_digest_activity(trace, bite)
        reserve_before = organism.body.reserve
        spent_before = organism.activity_ledger.energy_spent
        organism._settle_activity_debt()
        paid = organism.activity_ledger.energy_spent - spent_before
        self.assertAlmostEqual(reserve_before, organism.body.reserve + paid)
        strength_before = organism.body.total_strength
        self.assertGreaterEqual(strength_before, 0.0)
        self.assertGreater(paid, 0.0)

    def test_energy_accounting_uses_no_full_body_scan(self) -> None:
        organism = AutonomousOrganism()
        organism.result.available_nutrition_total = 512.0
        bite = (1, 2) * 128
        for _ in range(2):
            trace: dict[str, int] = {}
            organism.digest(organism.body, bite, (1.0,) * len(bite), trace)
            organism._record_digest_activity(trace, bite)
        organism.body.ensure_resource_cache()
        with patch.object(MathematicalLifeOrganism, "_structures", side_effect=AssertionError("energy full scan")):
            organism._settle_activity_debt()
        self.assertGreater(organism.activity_ledger.energy_spent, 0.0)

    def test_same_activity_produces_same_debt_and_basal_cost_is_mass_o1(self) -> None:
        first, second = AutonomousOrganism(), AutonomousOrganism()
        counters = ActivityCounters(bytes_eaten=10, relations_created=2, structural_mass_added=3)
        self.assertEqual(first.activity_ledger.add_activity(counters, first.body.body_mass), second.activity_ledger.add_activity(counters, second.body.body_mass))
        self.assertEqual(first.activity_ledger.metabolic_debt, second.activity_ledger.metabolic_debt)
        self.assertLess(first.activity_ledger.basal_cost(first.body.body_mass), first.activity_ledger.settlement_threshold(first.body.body_mass))


if __name__ == "__main__":
    unittest.main()
