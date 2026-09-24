from __future__ import annotations

import sys
import tempfile
import unittest
import math
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.lifecycle import LifecycleConfig, LivingStructure, MathematicalLifePopulation  # noqa: E402
from mathematical_organism.backend import NativeAction, NativeActionKind  # noqa: E402
from mathematical_organism.sandbox_runtime import AutonomousOrganism, SandboxObserver, SandboxRuntime  # noqa: E402


class SandboxRuntimeTests(unittest.TestCase):
    def _write(self, path: Path, size: int) -> None:
        path.write_bytes(bytes(index % 251 for index in range(size)))

    def test_directories_root_and_no_population_manager(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            self.assertTrue(all(path.is_dir() for path in (runtime.inbox, runtime.food, runtime.organisms_dir, runtime.traces, runtime.results)))
            root = runtime.bootstrap()
            self.assertIsInstance(root, AutonomousOrganism)
            self.assertFalse(any(isinstance(value, MathematicalLifePopulation) for value in root.__dict__.values()))
            self.assertTrue(root.territory_state.territory.contains(10_000))

    def test_live_step_uses_organism_owned_lifecycle_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            organism = runtime.bootstrap()
            organism.live_step(runtime)
            self.assertIs(organism.body, organism.__dict__["body"])
            self.assertIs(organism.result, organism.__dict__["result"])
            self.assertIn("navigation", organism.__dict__)
            self.assertIn("local_claim_counter", organism.__dict__)
            self.assertNotIn("population", organism.__dict__)
            self.assertIn("metabolic_progress", organism.__dict__)

    def test_live_step_can_emit_replayable_host_action_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            organism = runtime.bootstrap()
            trace: list[NativeAction] = []
            organism.live_step(runtime, action_trace=trace)
            self.assertEqual(
                trace,
                [NativeAction.process_gut(capacity=organism.body.bite_limit(organism.config))],
            )

    def test_food_trace_marks_only_environment_prefix_before_metabolic_tail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=4)
            (runtime.inbox / "payload.bin").write_bytes(b"ABCD" * 64)
            organism = runtime.bootstrap()
            traces: list[list[NativeAction]] = []
            for _ in range(64):
                trace: list[NativeAction] = []
                organism.live_step(runtime, action_trace=trace)
                traces.append(trace)
                if organism.metabolic_steps:
                    break
            self.assertTrue(
                any(
                    [item.kind.value for item in trace]
                    == ["external_gut", "metabolic_progress", "lifecycle_step"]
                    for trace in traces
                )
            )
            self.assertGreaterEqual(organism.metabolic_steps, 1)

    def test_action_observer_runs_after_each_python_action_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=4)
            (runtime.inbox / "payload.bin").write_bytes(b"ABCD")
            organism = runtime.bootstrap()
            trace: list[NativeAction] = []
            observed: list[tuple[NativeActionKind, int]] = []

            def observe(action: NativeAction) -> None:
                observed.append((action.kind, organism.metabolic_progress))

            organism.live_step(
                runtime,
                action_trace=trace,
                action_observer=observe,
            )
            self.assertEqual([kind for kind, _progress in observed], [item.kind for item in trace])
            progress = [value for kind, value in observed if kind is NativeActionKind.METABOLIC_PROGRESS]
            self.assertEqual(progress, [4])

    def test_metabolism_is_charged_by_food_volume_not_each_bite(self) -> None:
        organism = AutonomousOrganism(config=LifecycleConfig(metabolic_minimum_work=64))
        self.assertEqual(organism.metabolic_work_threshold(), 64)
        organism.metabolic_progress = 63
        self.assertEqual(organism.metabolic_steps, 0)
        # A physical one-byte bite below a body-volume interval cannot trigger
        # a full maintenance/resorption scan on its own.
        self.assertLess(organism.metabolic_progress + 1, organism.metabolic_work_threshold() + 1)

    def test_larger_body_produces_larger_or_equal_bite(self) -> None:
        config = LifecycleConfig(bite_minimum=1)
        small = AutonomousOrganism(config=config)
        large = AutonomousOrganism(config=config)
        large.body.add_structure(
            large.body.relations,
            LivingStructure((1, 2), "RELATION", strength=32.0, maintenance=0.5),
        )
        self.assertGreater(large.body.body_mass, small.body.body_mass)
        self.assertGreaterEqual(large.body.bite_limit(config), small.body.bite_limit(config))

    def test_bite_growth_follows_existing_formula_and_is_population_independent(self) -> None:
        config = LifecycleConfig(bite_minimum=7)
        organism = AutonomousOrganism(config=config)
        before = organism.body.bite_limit(config)
        organism.body.add_structure(
            organism.body.relations,
            LivingStructure((3, 4), "RELATION", strength=64.0, maintenance=0.5),
        )
        self.assertEqual(organism.body.bite_limit(config), max(config.bite_minimum, organism.body.body_mass))
        self.assertGreaterEqual(organism.body.bite_limit(config), before)
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            runtime.organisms.extend([organism, organism.spawn_child()])
            self.assertEqual(organism.body.bite_limit(config), max(config.bite_minimum, organism.body.body_mass))

    def test_division_does_not_reset_parent_or_child_bite_incorrectly(self) -> None:
        parent = AutonomousOrganism(config=LifecycleConfig(reproduction_minimum_body=2, birth_cost=1.0))
        for symbol in "ABCD":
            parent.body.atoms[symbol] = LivingStructure(symbol, "ATOM", strength=20.0, maintenance=0.25, evidence=8.0, income_rate=4.0)
        parent.body.add_structure(parent.body.relations, LivingStructure(("A", "B"), "RELATION", strength=12.0, maintenance=0.5, evidence=6.0, income_rate=3.0))
        parent.body.add_structure(parent.body.relations, LivingStructure(("C", "D"), "RELATION", strength=12.0, maintenance=0.5, evidence=6.0, income_rate=3.0))
        child = parent._reproduce_conservatively()
        self.assertIsNotNone(child)
        self.assertEqual(parent.body.bite_limit(parent.config), max(parent.config.bite_minimum, parent.body.body_mass))
        self.assertEqual(child.body.bite_limit(child.config), max(child.config.bite_minimum, child.body.body_mass))  # type: ignore[union-attr]

    def test_conservative_reproduction_splits_strength_and_reserve(self) -> None:
        config = LifecycleConfig(reproduction_minimum_body=2, birth_cost=1.0)
        parent = AutonomousOrganism(config=config)
        parent.body.reserve = 40.0
        for symbol in "ABCD":
            parent.body.atoms[symbol] = LivingStructure(symbol, "ATOM", strength=20.0, maintenance=0.25, evidence=8.0, income_rate=4.0)
        parent.body.add_structure(parent.body.relations, LivingStructure(("A", "B"), "RELATION", strength=12.0, maintenance=0.5, evidence=6.0, income_rate=3.0))
        parent.body.add_structure(parent.body.relations, LivingStructure(("C", "D"), "RELATION", strength=12.0, maintenance=0.5, evidence=6.0, income_rate=3.0))
        before_strength = parent.body.total_strength
        before_reserve = parent.body.reserve
        child = parent._reproduce_conservatively()
        self.assertIsNotNone(child)
        self.assertEqual(child.body.generation, 1)  # type: ignore[union-attr]
        self.assertFalse(parent.territory_state.territory.overlaps(child.territory_state.territory))  # type: ignore[union-attr]
        self.assertTrue(math.isclose(before_strength, parent.body.total_strength + child.body.total_strength))  # type: ignore[union-attr]
        self.assertTrue(math.isclose(before_reserve, parent.body.reserve + config.birth_cost))  # type: ignore[union-attr]
        self.assertEqual(child.body.reserve, 0.0)  # type: ignore[union-attr]
        self.assertEqual({atom.strength for atom in child.body.atoms.values()}, {20.0})  # type: ignore[union-attr]

    def test_two_organisms_can_take_independent_life_steps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            parent = runtime.bootstrap()
            child = parent.spawn_child()
            runtime.organisms.append(child)
            parent.live_step(runtime)
            child.live_step(runtime)
            self.assertTrue(parent.alive)
            self.assertTrue(child.alive)
            self.assertIsNot(parent.navigation, child.navigation)

    def test_organism_discovers_ingests_and_consumes_inbox_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=64)
            root = runtime.bootstrap()
            source = runtime.inbox / "partition_3kib.bin"
            self._write(source, 3072)
            for _ in range(400):
                runtime.autonomous_step()
                if runtime.food_sources and not source.exists() and all(food.inbox_remaining == 0 and food.remaining == 0 for food in runtime.food_sources.values()):
                    break
            food = runtime.food_sources[source.name]
            self.assertFalse(source.exists())
            self.assertEqual(food.metrics.bytes_consumed, 3072)
            self.assertEqual(food.remaining, 0)
            self.assertEqual(food.metrics.duplicate_consumption, 0)
            self.assertEqual(list(food.food_dir.glob("*.food")), [])

    def test_child_is_independent_and_observer_is_read_only(self) -> None:
        observer = SandboxObserver()
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", observer=observer)
            parent = runtime.bootstrap()
            child = parent.spawn_child()
            runtime.organisms.append(child)
            self.assertIsNot(parent.body, child.body)
            self.assertNotEqual(parent.territory_state.territory, child.territory_state.territory)
            before = parent.body.size
            observer.observe("TEST", parent.name)
            self.assertEqual(parent.body.size, before)

    def test_live_organism_markers_reflect_registered_lives(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            parent = runtime.bootstrap()
            self.assertTrue(runtime.organism_directory(parent.name).is_dir())
            child = parent.spawn_child()
            runtime.register_child(parent, child)
            self.assertTrue(runtime.organism_directory(child.name).is_dir())
            child._die(runtime)
            self.assertTrue((runtime.organism_directory(child.name) / "DEAD").is_file())

    def test_local_division_creates_autonomous_child_with_disjoint_territory(self) -> None:
        parent = AutonomousOrganism()
        for symbol in "ABCD":
            parent.body.atoms[symbol] = LivingStructure(symbol, "ATOM", 12.0, 8.0, 0.25, 12.0, 3.0)
        parent.body.add_structure(parent.body.relations, LivingStructure(("A", "B"), "RELATION", 8.0, 4.0, 0.5, 8.0, 3.0))
        parent.body.add_structure(parent.body.relations, LivingStructure(("B", "C"), "RELATION", 2.0, 0.2, 0.5, 2.0, 1.0))
        parent.body.add_structure(parent.body.relations, LivingStructure(("C", "D"), "RELATION", 8.0, 4.0, 0.5, 8.0, 3.0))
        child = parent._divide_locally()
        self.assertIsNotNone(child)
        self.assertIsNot(parent.body, child.body)  # type: ignore[union-attr]
        self.assertFalse(parent.territory_state.territory.overlaps(child.territory_state.territory))  # type: ignore[union-attr]

    def test_new_file_is_detected_after_runtime_started(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=64)
            runtime.bootstrap()
            runtime.autonomous_step()
            source = runtime.inbox / "later.bin"
            self._write(source, 128)
            for _ in range(100):
                runtime.autonomous_step()
                if not source.exists() and "later.bin" in runtime.food_sources:
                    break
            self.assertIn("later.bin", runtime.food_sources)
            self.assertFalse(source.exists())

    def test_ingest_claim_is_an_atomic_inbox_rename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=64)
            organism = runtime.bootstrap()
            source = runtime.inbox / "atomic.bin"
            self._write(source, 128)
            organism.live_step(runtime)
            self.assertIn("atomic.bin", runtime.food_sources)
            self.assertFalse(source.exists())
            self.assertTrue((runtime.inbox / "atomic.bin.ingesting").exists())
            for _ in range(4):
                organism.live_step(runtime)
            self.assertFalse((runtime.inbox / "atomic.bin.ingesting").exists())

    def test_death_releases_territory_creates_neutral_corpse_and_preserves_food(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            parent = runtime.bootstrap()
            child = parent.spawn_child()
            runtime.organisms.append(child)
            child.body.reserve = 8.0
            child.body.atoms["A"] = LivingStructure("A", "ATOM", strength=7.0, maintenance=0.25)
            child.body.relations[("A", "A")] = LivingStructure(("A", "A"), "RELATION", strength=11.0, maintenance=0.5)
            reserve_before = child.body.reserve
            corpse = child._die(runtime)
            self.assertFalse(child.alive)
            self.assertIsNotNone(corpse)
            self.assertEqual(corpse.remaining_energy, reserve_before)  # type: ignore[union-attr]
            self.assertEqual(child.body.size, 0)
            self.assertFalse(hasattr(corpse, "relations"))
            self.assertTrue(corpse.territory.path)

    def test_corpse_reserve_transfer_is_exact_and_strength_is_not_energy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = LifecycleConfig(bite_minimum=30)
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            survivor = AutonomousOrganism(config=config)
            runtime.organisms.append(survivor)
            deceased = survivor.spawn_child()
            runtime.organisms.append(deceased)
            survivor.body.reserve = 20.0
            deceased.body.reserve = 100.0
            survivor.body.atoms["B"] = LivingStructure("B", "ATOM", strength=9.0, maintenance=0.25)
            deceased.body.atoms["A"] = LivingStructure("A", "ATOM", strength=10_000.0, maintenance=0.25)
            corpse = deceased._die(runtime)
            self.assertIsNotNone(corpse)
            self.assertEqual(corpse.remaining_energy, 100.0)  # type: ignore[union-attr]
            self.assertFalse(hasattr(corpse, "atoms"))
            self.assertTrue(survivor._reclaim_sibling_if_available(runtime))
            self.assertEqual(survivor._consume_corpse(runtime), 100.0)
            self.assertEqual(survivor.body.reserve, 120.0)
            self.assertEqual(corpse.remaining_energy, 0.0)  # type: ignore[union-attr]
            survivor.config = replace(survivor.config, bite_minimum=70)
            self.assertEqual(survivor._consume_corpse(runtime), 0.0)
            self.assertEqual(survivor.body.reserve, 120.0)
            self.assertEqual(corpse.remaining_energy, 0.0)  # type: ignore[union-attr]
            self.assertNotIn(corpse, runtime.corpses)

    def test_zero_reserve_death_releases_territory_without_a_corpse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            survivor = runtime.bootstrap()
            deceased = survivor.spawn_child()
            runtime.organisms.append(deceased)
            deceased.body.reserve = 0.0
            deceased.body.atoms["Z"] = LivingStructure("Z", "ATOM", strength=999.0, maintenance=0.25)
            self.assertIsNone(deceased._die(runtime))
            self.assertTrue(runtime.is_territory_unoccupied(deceased.territory_state.territory))
            self.assertTrue(survivor._reclaim_sibling_if_available(runtime))

    def test_live_sibling_reclaims_only_unoccupied_sibling_and_scavenges_energy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            parent = runtime.bootstrap()
            sibling = parent.spawn_child()
            runtime.organisms.append(sibling)
            parent.body.reserve = 4.0
            parent.body.atoms["A"] = LivingStructure("A", "ATOM", strength=2.0, maintenance=0.25)
            self.assertFalse(parent._reclaim_sibling_if_available(runtime))
            sibling.body.reserve = 6.0
            sibling.body.atoms["B"] = LivingStructure("B", "ATOM", strength=8.0, maintenance=0.25)
            corpse = sibling._die(runtime)
            before = corpse.energy
            parent.live_step(runtime)
            self.assertEqual(parent.territory_state.territory.path, ())
            self.assertGreater(parent.biomass_consumed, 0.0)
            self.assertLess(corpse.energy, before)
            while corpse in runtime.corpses:
                parent.live_step(runtime)
            self.assertNotIn(corpse, runtime.corpses)


if __name__ == "__main__":
    unittest.main()
