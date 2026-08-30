from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.compost import CompostController  # noqa: E402
from mathematical_organism.territory import FoodTerritory, owner_of_block  # noqa: E402


class RuntimeTerritoryRegressionTests(unittest.TestCase):
    def test_dynamic_divisions_leave_every_block_owned_once_or_unoccupied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = CompostController(Path(directory) / "sandbox", block_size=1024)
            controller.add_organisms(4)
            controller.generate_food(8 * 1024, seed=77)
            controller.start()
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and controller.snapshot()["food_remaining"]:
                time.sleep(0.01)
            controller.stop()
            states = [organism.territory_state for organism in controller.runtime.organisms]
            for food in controller.runtime.food_sources.values():
                for block in food.blocks.values():
                    owner = owner_of_block(food.source_hash, block.block_id, states)
                    self.assertTrue(owner is None or owner.alive)
            view = controller.snapshot()
            self.assertEqual(view["food_missing"], 0)
            self.assertEqual(view["duplicates"], 0)

    def test_nested_reclaim_exposes_wider_territory_and_shutdown_joins_thread(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = CompostController(Path(directory) / "sandbox")
            parent = controller.runtime.bootstrap()
            child = parent.spawn_child()
            controller.runtime.register_child(parent, child)
            grandchild = parent.spawn_child()
            controller.runtime.register_child(parent, grandchild)
            # parent owns D00; after both sibling branches are released it can
            # reclaim D0 and then D.
            child._die(controller.runtime)
            grandchild._die(controller.runtime)
            self.assertTrue(parent._reclaim_sibling_if_available(controller.runtime))
            self.assertEqual(parent.territory_state.territory, FoodTerritory((0,)))
            controller.start()
            controller.stop()
            self.assertFalse(controller.running)
            self.assertIsNotNone(controller._thread)
            self.assertFalse(controller._thread.is_alive())  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
