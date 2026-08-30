from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from time import monotonic

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.biology_rules import forgetting_delta, reproduction_allowed  # noqa: E402
from mathematical_organism.lifecycle import LifecycleConfig, LivingStructure  # noqa: E402
from mathematical_organism.sandbox_runtime import AutonomousOrganism, SandboxRuntime  # noqa: E402
from tools.run_sandbox import _handle_command  # noqa: E402


class BiologyRulesAndCliTests(unittest.TestCase):
    def test_biology_rules_are_centralized_and_match_existing_forgetting(self) -> None:
        config = LifecycleConfig(income_decay=0.8)
        dormant = LivingStructure("A", "ATOM", strength=5.0, maintenance=0.25, income_rate=0.25)
        delta = forgetting_delta(dormant, config)
        self.assertEqual(delta.strength_after, 4.0)
        self.assertEqual(delta.income_rate_after, 0.2)

    def test_runtime_uses_shared_reproduction_formula(self) -> None:
        organism = AutonomousOrganism(config=LifecycleConfig(reproduction_minimum_body=2))
        organism.body.reserve = 10.0
        for symbol in "ABCD":
            organism.body.atoms[symbol] = LivingStructure(symbol, "ATOM", strength=4.0, maintenance=0.25)
        organism.body.add_structure(organism.body.relations, LivingStructure(("A", "B"), "RELATION", strength=4.0))
        organism.body.add_structure(organism.body.relations, LivingStructure(("C", "D"), "RELATION", strength=4.0))
        assessment = reproduction_allowed(organism.body, organism.config, selected_count=2)
        self.assertTrue(assessment.allowed)
        self.assertIsNotNone(organism._reproduce_conservatively())

    def test_cli_is_read_only_for_status_detail_and_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            parent = runtime.bootstrap()
            child = parent.spawn_child()
            runtime.register_child(parent, child)
            before = [(item.name, item.body.size, item.body.reserve, item.territory_state.territory.path) for item in runtime.organisms]
            with redirect_stdout(StringIO()):
                for command in ("status", "orgs", f"org {parent.name}", "top", "tree 3", "food", "births", "deaths", "corpses", "help"):
                    self.assertTrue(_handle_command(runtime, monotonic(), command))
            after = [(item.name, item.body.size, item.body.reserve, item.territory_state.territory.path) for item in runtime.organisms]
            self.assertEqual(before, after)

    def test_food_accounting_snapshot_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            view = runtime.observation_snapshot()
            self.assertEqual(view["food_original"], 0)
            self.assertEqual(view["food_eaten"], 0)
            self.assertEqual(view["food_remaining"], 0)


if __name__ == "__main__":
    unittest.main()
