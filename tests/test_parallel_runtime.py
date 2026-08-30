from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.lifecycle import LivingStructure  # noqa: E402
from mathematical_organism.parallel_runtime import AutonomousMultiprocessingRuntime, _DirectFood  # noqa: E402
from mathematical_organism.sandbox_runtime import AutonomousOrganism  # noqa: E402
from mathematical_organism.territory import FoodTerritory  # noqa: E402


class ParallelRuntimeTests(unittest.TestCase):
    def _three_organisms(self) -> list[AutonomousOrganism]:
        first = AutonomousOrganism("ORG-A")
        second = first.spawn_child()
        third = second.spawn_child()
        return [first, second, third]

    def test_organisms_keep_bodies_worker_local_without_per_bite_transfer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = AutonomousMultiprocessingRuntime(Path(directory) / "sandbox", workers=2)
            organisms = self._three_organisms()
            runtime.start(organisms)
            runtime.run_for(0.20)
            metrics = runtime.metrics()
            self.assertIsNotNone(runtime.observer_process)
            self.assertTrue(runtime.observer_process.is_alive())  # type: ignore[union-attr]
            runtime.shutdown()
            self.assertEqual(metrics.body_transfers, 3)
            self.assertEqual(metrics.worker_migrations, 0)
            self.assertEqual(metrics.workers_used, 2)
            self.assertGreaterEqual(metrics.max_simultaneous_organisms, 3)

    def test_multiple_workers_run_autonomous_organisms_and_shutdown_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = AutonomousMultiprocessingRuntime(Path(directory) / "sandbox", workers=3)
            runtime.start(self._three_organisms())
            self.assertEqual(len(runtime.processes), 3)
            self.assertTrue(all(process.is_alive() for process in runtime.processes))
            runtime.run_for(0.20)
            runtime.shutdown()
            self.assertTrue(all(not process.is_alive() for process in runtime.processes))
            self.assertIsNotNone(runtime.observer_process)
            self.assertFalse(runtime.observer_process.is_alive())  # type: ignore[union-attr]

    def test_worker_has_no_population_loop_or_per_bite_body_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sandbox"
            runtime = AutonomousMultiprocessingRuntime(root, workers=2, block_size=64)
            (runtime.environment.inbox / "local.bin").write_bytes(bytes(range(128)) * 4)
            runtime.start(self._three_organisms())
            runtime.run_for(0.75)
            runtime.shutdown()
            metrics = runtime.metrics()
            self.assertEqual(metrics.worker_migrations, 0)
            self.assertEqual(metrics.parent_food_rpcs, 0)
            self.assertEqual(metrics.body_transfers, 3)
            self.assertGreater(metrics.direct_food_operations, 0)
            self.assertEqual(metrics.duplicates, 0)

    def test_least_loaded_newborn_placement_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = AutonomousMultiprocessingRuntime(Path(directory) / "sandbox", workers=4)
            runtime.worker_organisms[0].update({"a", "b"})
            runtime.worker_organisms[1].add("c")
            self.assertEqual(runtime._least_loaded_worker(), 2)
            runtime.worker_organisms[2].add("d")
            self.assertEqual(runtime._least_loaded_worker(), 3)

    def test_newborn_can_be_placed_remotely_once_with_exact_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = AutonomousMultiprocessingRuntime(Path(directory) / "sandbox", workers=2)
            parent = AutonomousOrganism("ORG-PARENT")
            child = parent.spawn_child()
            child.body.reserve = 0.0  # actual successful DIVIDE birth state
            runtime.organism_workers[parent.name] = 0
            runtime.worker_organisms[0].add(parent.name)
            target = runtime._handle("birth", (0, parent.name, parent.territory_state.territory.path, child.name, child.territory_state.territory.path, child))
            self.assertEqual(target, 1)
            command, delivered = runtime.controls[1].get(timeout=1.0)
            self.assertEqual(command, "NEWBORN")
            self.assertEqual(delivered.name, child.name)
            self.assertEqual(delivered.body.reserve, 0.0)
            self.assertEqual(delivered.gut_mass, 0)
            self.assertEqual(delivered.territory_state.territory, child.territory_state.territory)
            self.assertEqual(runtime.newborn_initial_placements, 1)
            self.assertEqual(runtime.newborn_remote_placements, 1)
            self.assertEqual(runtime.newborn_local_placements, 0)
            self.assertEqual(runtime.organism_workers[child.name], 1)

    def test_remote_placement_failure_falls_back_locally_without_ghost_child(self) -> None:
        class FailingQueue:
            def put(self, _value: object) -> None:
                raise OSError("delivery failed")

        with tempfile.TemporaryDirectory() as directory:
            runtime = AutonomousMultiprocessingRuntime(Path(directory) / "sandbox", workers=2)
            parent = AutonomousOrganism("ORG-PARENT")
            child = parent.spawn_child()
            runtime.organism_workers[parent.name] = 0
            runtime.worker_organisms[0].add(parent.name)
            runtime.controls[1] = FailingQueue()  # type: ignore[assignment]
            target = runtime._handle("birth", (0, parent.name, parent.territory_state.territory.path, child.name, child.territory_state.territory.path, child))
            self.assertEqual(target, 0)
            self.assertEqual(runtime.newborn_local_placements, 1)
            self.assertEqual(runtime.newborn_remote_placements, 0)
            self.assertEqual(runtime.organism_workers[child.name], 0)
            self.assertIn(child.name, runtime.worker_organisms[0])

    def test_multiple_births_spread_without_existing_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = AutonomousMultiprocessingRuntime(Path(directory) / "sandbox", workers=3)
            parent = AutonomousOrganism("ORG-PARENT")
            runtime.organism_workers[parent.name] = 0
            runtime.worker_organisms[0].add(parent.name)
            for index in range(4):
                child = AutonomousOrganism(f"ORG-CHILD-{index}")
                runtime._handle("birth", (0, parent.name, parent.territory_state.territory.path, child.name, child.territory_state.territory.path, child))
            self.assertEqual(runtime.organism_workers[parent.name], 0)
            self.assertEqual(runtime.newborn_initial_placements, 4)
            self.assertGreater(runtime.newborn_remote_placements, 0)
            self.assertLessEqual(max(len(items) for items in runtime.worker_organisms) - min(len(items) for items in runtime.worker_organisms), 1)

    def test_parallel_territories_consume_without_duplicate_food(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sandbox"
            runtime = AutonomousMultiprocessingRuntime(root, workers=2, block_size=64)
            (runtime.environment.inbox / "parallel.bin").write_bytes(bytes(index % 251 for index in range(4096)))
            runtime.start(self._three_organisms())
            runtime.run_for(1.00)
            runtime.shutdown()
            metrics = runtime.metrics()
            self.assertIn("parallel.bin", runtime.environment.food_sources)
            self.assertGreater(metrics.food_consumed, 0)
            self.assertEqual(metrics.duplicates, 0)
            self.assertGreaterEqual(metrics.max_simultaneous_organisms, 3)

    def test_worker_reads_and_truncates_only_its_owned_block_directly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sandbox"
            runtime = AutonomousMultiprocessingRuntime(root, workers=1, block_size=64)
            source = runtime.environment.inbox / "owned.bin"
            source.write_bytes(b"A" * 64)
            runtime.environment.ingest_one_available("setup")
            storage = runtime.environment.food_sources["owned.bin"]
            food = _DirectFood(root, "owned.bin", storage.source_hash, storage.block_count, storage.size, storage.block_size)
            left, right = FoodTerritory().split()
            owner = left if left.owns_block(storage.source_hash, 0) else right
            foreign = right if owner == left else left
            original = (food.food_dir / "block_000000.food").stat().st_size
            self.assertIsNone(food.claim(0, 5, skipped_regions=0, territory=foreign))
            self.assertEqual((food.food_dir / "block_000000.food").stat().st_size, original)
            claim = food.claim(0, 5, skipped_regions=0, territory=owner)
            self.assertIsNotNone(claim)
            bite = food.read(claim)  # type: ignore[arg-type]
            self.assertEqual(len(bite), 5)
            food.consume(claim)  # type: ignore[arg-type]
            second = food.claim_active(9, owner)
            self.assertIsNotNone(second)
            food.read(second)  # type: ignore[arg-type]
            food.consume(second)  # type: ignore[arg-type]
            self.assertEqual((food.food_dir / "block_000000.food").stat().st_size, original - 14)
            self.assertEqual(food.file_opens, 1)
            self.assertEqual(food.stat_calls, 1)
            self.assertEqual(food.flushes, 0)
            self.assertEqual(food.fsyncs, 0)
            self.assertEqual(food.truncates, 2)
            food.close()

    def test_failed_direct_digest_leaves_food_and_complete_run_has_no_missing_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sandbox"
            runtime = AutonomousMultiprocessingRuntime(root, workers=1, block_size=64)
            source = runtime.environment.inbox / "complete.bin"
            source.write_bytes(bytes(range(256)) * 2)
            runtime.environment.ingest_one_available("setup")
            storage = runtime.environment.food_sources["complete.bin"]
            food = _DirectFood(root, "complete.bin", storage.source_hash, storage.block_count, storage.size, storage.block_size)
            claim = food.claim(0, 5, skipped_regions=0, territory=FoodTerritory())
            self.assertIsNotNone(claim)
            food.read(claim)  # simulated failed DIGEST: deliberately no consume
            self.assertEqual((food.food_dir / "block_000000.food").stat().st_size, 64)
            food.close()
            runtime.start((AutonomousOrganism(),))
            for _ in range(80):
                runtime.run_for(0.05)
                if runtime.environment.food_sources and not list(runtime.environment.food.rglob("*.food")):
                    break
            runtime.shutdown()
            metrics = runtime.metrics()
            self.assertEqual(metrics.food_consumed, 512)
            self.assertEqual(metrics.duplicates, 0)
            self.assertEqual(metrics.missing, 0)
            self.assertEqual(metrics.parent_food_rpcs, 0)
            self.assertGreater(metrics.direct_food_operations, 0)
            self.assertEqual(metrics.file_opens, 8)
            self.assertEqual(metrics.stat_calls, 8)
            self.assertEqual(metrics.truncates, len(metrics.bite_sizes))
            self.assertTrue(metrics.bite_sizes)

    def test_idle_workers_do_not_pay_wall_clock_starvation_cost(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = AutonomousMultiprocessingRuntime(Path(directory) / "sandbox", workers=2)
            dying, surviving, other = self._three_organisms()
            dying.body.reserve = 0.0
            surviving.body.reserve = 5.0
            other.body.reserve = 5.0
            dying.body.atoms["X"] = LivingStructure("X", "ATOM", strength=1.0, maintenance=1.0)
            surviving.body.atoms["Y"] = LivingStructure("Y", "ATOM", strength=1.0, maintenance=0.25)
            other.body.atoms["Z"] = LivingStructure("Z", "ATOM", strength=1.0, maintenance=0.25)
            runtime.start((dying, surviving, other))
            runtime.run_for(1.00)
            metrics = runtime.metrics()
            runtime.shutdown()
            self.assertEqual(metrics.deaths, 0)
            self.assertGreaterEqual(metrics.max_simultaneous_organisms, 3)

    def test_idle_parent_does_not_divide_without_activity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = AutonomousOrganism("ORG-PARENT")
            for symbol in "AB":
                parent.body.atoms[symbol] = LivingStructure(symbol, "ATOM", 12.0, 8.0, 0.25, 12.0, 3.0)
            parent.body.relations[("A", "B")] = LivingStructure(("A", "B"), "RELATION", 2.0, 0.2, 0.5, 2.0, 1.0)
            runtime = AutonomousMultiprocessingRuntime(Path(directory) / "sandbox", workers=2)
            runtime.start((parent,))
            runtime.run_for(1.00)
            metrics = runtime.metrics()
            runtime.shutdown()
            self.assertEqual(metrics.births, 0)
            self.assertEqual(metrics.divisions, 0)
            self.assertEqual(metrics.max_simultaneous_organisms, 1)

    def test_atomic_ingest_is_shared_physical_environment_not_worker_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sandbox"
            runtime = AutonomousMultiprocessingRuntime(root, workers=4, block_size=64)
            source = runtime.environment.inbox / "once.bin"
            source.write_bytes(b"x" * 512)
            runtime.start(self._three_organisms())
            runtime.run_for(0.60)
            runtime.shutdown()
            self.assertIn("once.bin", runtime.environment.food_sources)
            self.assertFalse(source.exists())
            self.assertFalse((runtime.environment.inbox / "once.bin.ingesting").exists())
            self.assertEqual(len(runtime.environment.food_sources), 1)


if __name__ == "__main__":
    unittest.main()
