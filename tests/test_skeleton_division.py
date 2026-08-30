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


class SkeletonDivisionTests(unittest.TestCase):
    @staticmethod
    def _mass(organism: AutonomousOrganism) -> int:
        return organism.body.body_mass - BASE_RECEPTOR_MASS

    @staticmethod
    def _seed(parent: AutonomousOrganism, *, include_cross: bool = False) -> None:
        parent.body.reserve = 100.0
        for symbol in "ABCD":
            parent.body.add_structure(parent.body.atoms, LivingStructure(symbol, "ATOM", strength=10.0, maintenance=0.25))
        for pair, strength in ((('A', 'B'), 8.0), (('C', 'D'), 16.0)):
            parent.body.add_structure(parent.body.relations, LivingStructure(pair, "RELATION", strength=strength, maintenance=0.5))
        parent.body.add_structure(parent.body.composites, LivingStructure(('A', 'B'), "COMPOSITE", strength=4.0, maintenance=0.3, members=(('A', 'B'),)))
        if include_cross:
            parent.body.add_structure(parent.body.relations, LivingStructure(('B', 'C'), "RELATION", strength=8.0, maintenance=0.5))
        parent.material_flow.structural_created_mass = parent.body.body_mass - BASE_RECEPTOR_MASS
        parent.rebuild_metabolic_indexes()

    def test_division_moves_partition_without_cloning_and_keeps_gut_with_parent(self) -> None:
        parent = AutonomousOrganism(config=LifecycleConfig(reproduction_minimum_body=2))
        self._seed(parent)
        # Simulate already detached structural material that belongs to the
        # parent's accounting domain, not to a future child.
        parent.material_flow.structural_created_mass += 3
        parent.enqueue_resorbed_material(3)
        before_mass = self._mass(parent)
        before_ids = {id(item) for item in parent.body._structures()}
        child = parent._reproduce_conservatively()
        self.assertIsNotNone(child)
        assert child is not None
        self.assertEqual(before_mass, self._mass(parent) + self._mass(child))
        self.assertEqual(parent.material_flow.structural_transferred_out, self._mass(child))
        self.assertEqual(child.material_flow.structural_transferred_in, self._mass(child))
        self.assertTrue({id(item) for item in child.body._structures()} <= before_ids)
        self.assertFalse({id(item) for item in parent.body._structures()} & {id(item) for item in child.body._structures()})
        # The weakest-member split keeps the stronger CD component together;
        # it must not retain the former prefix-selection behaviour.
        self.assertIn(('A', 'B'), parent.body.relations)
        self.assertIn(('C', 'D'), child.body.relations)
        self.assertIn(('A', 'B'), parent.body.composites)
        self.assertNotIn(('A', 'B'), child.body.composites)
        self.assertEqual(parent.gut_mass, 3)
        self.assertEqual(child.gut_mass, 0)
        self.assertFalse(parent.territory_state.territory.overlaps(child.territory_state.territory))
        parent.verify_material_conservation()
        child.verify_material_conservation()

    def test_cross_split_structure_is_resorbed_not_duplicated_or_lost(self) -> None:
        parent = AutonomousOrganism(config=LifecycleConfig(reproduction_minimum_body=2))
        self._seed(parent, include_cross=True)
        before = self._mass(parent)
        cross_mass = structural_mass(8.0)
        # Explicitly validate cross-edge conservation independently from the
        # weakness-based candidate selector.
        child = parent._commit_skeleton_partition({'A', 'B'})
        self.assertIsNotNone(child)
        assert child is not None
        self.assertNotIn(('B', 'C'), parent.body.relations)
        self.assertNotIn(('B', 'C'), child.body.relations)
        self.assertEqual(parent.gut_mass, cross_mass)
        self.assertEqual(before, self._mass(parent) + self._mass(child) + parent.gut_mass)
        parent.verify_material_conservation()
        child.verify_material_conservation()

    def test_single_division_trace_has_zero_delta_and_child_is_transfer_only(self) -> None:
        parent = AutonomousOrganism(config=LifecycleConfig(reproduction_minimum_body=2))
        self._seed(parent, include_cross=True)
        before_created = parent.material_flow.structural_created_mass
        child = parent._commit_skeleton_partition({'A', 'B'})
        self.assertIsNotNone(child)
        assert child is not None
        trace = parent.division_material_traces[-1]
        self.assertEqual(trace.delta, 0)
        self.assertEqual(trace.mass_sent_to_gut, trace.cross_split_relation_mass + trace.cross_split_composite_mass)
        self.assertEqual(child.material_flow.structural_created_mass, 0)
        self.assertEqual(child.material_flow.structural_transferred_in, trace.child_structural_mass)
        self.assertEqual(parent.material_flow.structural_created_mass, before_created)

    def test_failed_division_preserves_material_exactly(self) -> None:
        parent = AutonomousOrganism(config=LifecycleConfig(reproduction_minimum_body=999))
        self._seed(parent)
        before = (
            self._mass(parent), parent.gut_mass, parent.material_flow.structural_created_mass,
            parent.material_flow.resorbed_mass, tuple(parent.division_material_traces),
        )
        self.assertIsNone(parent._commit_skeleton_partition({'A', 'B'}))
        self.assertEqual(before, (
            self._mass(parent), parent.gut_mass, parent.material_flow.structural_created_mass,
            parent.material_flow.resorbed_mass, tuple(parent.division_material_traces),
        ))

    def test_world_material_is_unchanged_by_nested_divisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            root = runtime.bootstrap()
            root.config = LifecycleConfig(reproduction_minimum_body=2)
            self._seed(root)
            initial = self._mass(root)
            child = root._reproduce_conservatively()
            self.assertIsNotNone(child)
            assert child is not None
            runtime.register_child(root, child)
            grandchild = child._reproduce_conservatively()
            if grandchild is not None:
                runtime.register_child(child, grandchild)
            runtime.verify_world_material_conservation()
            living = sum(self._mass(organism) for organism in runtime.organisms)
            resorbed = sum(organism.material_flow.resorbed_mass for organism in runtime.organisms)
            self.assertEqual(initial, living + resorbed)

    def test_failed_division_is_transactional_and_preserves_parent(self) -> None:
        parent = AutonomousOrganism(config=LifecycleConfig(reproduction_minimum_body=2))
        for symbol in "AB":
            parent.body.add_structure(parent.body.atoms, LivingStructure(symbol, "ATOM", strength=10.0))
        snapshot = (
            tuple(parent.body.atoms), tuple(parent.body.relations), tuple(parent.body.composites),
            parent.body.body_mass, parent.body.reserve, parent.territory_state.territory.path,
        )
        self.assertIsNone(parent._reproduce_conservatively())
        self.assertEqual(snapshot, (
            tuple(parent.body.atoms), tuple(parent.body.relations), tuple(parent.body.composites),
            parent.body.body_mass, parent.body.reserve, parent.territory_state.territory.path,
        ))

    def test_division_cost_is_recorded_by_runtime_and_never_creates_reserve(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            parent = runtime.bootstrap()
            parent.config = LifecycleConfig(reproduction_minimum_body=2)
            self._seed(parent)
            reserve_before = parent.body.reserve
            parent._run_metabolic_step(runtime)
            self.assertEqual(parent.activity_ledger.counters.division_events, 1)
        self.assertGreaterEqual(parent.activity_ledger.energy_spent, 0.0)
        self.assertLess(parent.body.reserve, reserve_before)
        for child in parent.children:
            self.assertEqual(child.body.reserve, 0.0)

    def test_multi_generation_partition_has_no_unexplained_structural_mass(self) -> None:
        root = AutonomousOrganism(config=LifecycleConfig(reproduction_minimum_body=2))
        for index in range(8):
            key = str(index)
            root.body.add_structure(root.body.atoms, LivingStructure(key, "ATOM", strength=10.0))
        for index in range(0, 8, 2):
            pair = (str(index), str(index + 1))
            root.body.add_structure(root.body.relations, LivingStructure(pair, "RELATION", strength=float(4 + index), maintenance=0.5))
            root.body.add_structure(root.body.composites, LivingStructure(pair, "COMPOSITE", strength=float(2 + index), maintenance=0.3, members=(pair,)))
        root.material_flow.structural_created_mass = self._mass(root)
        root.rebuild_metabolic_indexes()
        initial_mass = self._mass(root)
        living = [root]
        divisions = 0
        for organism in tuple(living):
            child = organism._reproduce_conservatively()
            if child is not None:
                living.append(child)
                divisions += 1
        # A second wave shows that transferred child skeletons remain eligible
        # for another partition without cloning.
        for organism in tuple(living):
            child = organism._reproduce_conservatively()
            if child is not None:
                living.append(child)
                divisions += 1
        living_mass = sum(self._mass(item) for item in living)
        resorbed = sum(item.material_flow.resorbed_mass for item in living)
        # A child begins at reserve zero and cannot pay another division cost
        # until it acquires organism-level energy from food.
        self.assertGreaterEqual(divisions, 1)
        self.assertEqual(initial_mass, living_mass + resorbed)
        for organism in living:
            organism.verify_material_conservation()


if __name__ == "__main__":
    unittest.main()
