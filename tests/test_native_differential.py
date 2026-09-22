from __future__ import annotations

import ctypes
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.biology_rules import lazy_metabolism_delta, structural_mass
from mathematical_organism.backend import NativeBackend
from mathematical_organism.lifecycle import LifecycleConfig, LivingStructure, MathematicalLifeOrganism, MathematicalLifePopulation
from mathematical_organism.biology_rules import reproduction_allowed


class _LazyDelta(ctypes.Structure):
    _fields_ = [
        ("strength_after", ctypes.c_double),
        ("income_rate_after", ctypes.c_double),
        ("strength_decay_epochs", ctypes.c_uint64),
    ]


class _ReproductionAssessment(ctypes.Structure):
    _fields_ = [
        ("score", ctypes.c_double),
        ("allowed", ctypes.c_bool),
        ("selected_count", ctypes.c_uint64),
        ("parent_reserve_after_cost", ctypes.c_double),
    ]


def _native_library() -> ctypes.CDLL | None:
    value = os.environ.get("COMPOST_NATIVE_LIBRARY")
    if not value:
        return None
    path = Path(value).resolve()
    if not path.is_file():
        raise AssertionError(f"COMPOST_NATIVE_LIBRARY does not exist: {path}")
    return ctypes.CDLL(str(path))


class NativePureRuleDifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        value = os.environ.get("COMPOST_NATIVE_LIBRARY")
        if not value:
            raise unittest.SkipTest("COMPOST_NATIVE_LIBRARY is not configured")
        cls.library_path = Path(value).resolve()
        cls.library = _native_library()
        cls.library.compost_structural_mass.argtypes = [ctypes.c_double, ctypes.POINTER(ctypes.c_uint64)]
        cls.library.compost_structural_mass.restype = ctypes.c_int
        cls.library.compost_lazy_metabolism_delta.argtypes = [
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_uint64,
            ctypes.POINTER(_LazyDelta),
        ]
        cls.library.compost_lazy_metabolism_delta.restype = ctypes.c_int
        cls.library.compost_reproduction_assessment.argtypes = [
            ctypes.c_uint64,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_uint64,
            ctypes.c_uint64,
            ctypes.POINTER(_ReproductionAssessment),
        ]
        cls.library.compost_reproduction_assessment.restype = ctypes.c_int

    def test_public_python_adapter_runs_native_step(self) -> None:
        with NativeBackend(self.library_path, organism_id=99) as backend:
            before = backend.state_digest()
            result = backend.step(b"\x04\x05", (1.0, 1.0))
            self.assertNotEqual(before, backend.state_digest())
            self.assertEqual(result["consumed_bytes"], 2)
            self.assertEqual(result["assimilated_mass"], 2)
            selected, ratio = backend.select_partition(0.5)
            self.assertEqual(selected, (4,))
            self.assertAlmostEqual(ratio, 1.0 / 3.0, places=12)
            plan = backend.division_plan()
            self.assertFalse(plan["candidate_found"])

    def test_native_partition_preserves_structural_mass_independently(self) -> None:
        with NativeBackend(self.library_path, organism_id=10) as parent:
            parent.digest(b"ABCD", (10.0,) * 4)
            before = parent.snapshot()
            child, result = parent.partition((ord("A"), ord("B")), child_id=11)
            with child:
                parent_after = parent.snapshot()
                child_after = child.snapshot()
            parent_dynamic_before = before["body"]["structural_mass"] - 256
            parent_dynamic_after = parent_after["body"]["structural_mass"] - 256
            child_dynamic_after = child_after["body"]["structural_mass"] - 256
            self.assertEqual(result["child_structural_mass"], child_dynamic_after)
            self.assertGreater(result["cross_split_mass"], 0)
            self.assertEqual(
                parent_dynamic_before + sum(mass for mass, _origin in before["gut"]),
                parent_dynamic_after
                + child_dynamic_after
                + sum(mass for mass, _origin in parent_after["gut"]),
            )
            self.assertEqual(
                parent_after["material_flow"]["structural_created_mass"]
                + parent_after["material_flow"]["structural_transferred_in"],
                parent_dynamic_after
                + parent_after["material_flow"]["resorbed_mass"]
                + parent_after["material_flow"]["structural_transferred_out"],
            )
            self.assertEqual(
                child_after["material_flow"]["structural_created_mass"]
                + child_after["material_flow"]["structural_transferred_in"],
                child_dynamic_after
                + child_after["material_flow"]["resorbed_mass"]
                + child_after["material_flow"]["structural_transferred_out"],
            )
            self.assertEqual(child_after["reserve"], 0.0)
            self.assertEqual(parent_after["reserve"], result["parent_reserve_after_cost"])

    def test_structural_mass_matches_reference(self) -> None:
        for strength in (0.0, 0.25, 1.0, 1.5, 4.0, 8.0, 16.0, 1024.0):
            native_mass = ctypes.c_uint64()
            status = self.library.compost_structural_mass(strength, ctypes.byref(native_mass))
            self.assertEqual(status, 0, strength)
            self.assertEqual(native_mass.value, structural_mass(strength), strength)

    def test_lazy_metabolism_matches_reference(self) -> None:
        cases = (
            (5.0, 0.0, 0.5, 0.8, 3),
            (5.0, 1.0, 0.5, 0.8, 10),
            (12.0, 2.0, 0.25, 0.9, 64),
        )
        for strength, income, maintenance, decay, epochs in cases:
            expected = lazy_metabolism_delta(
                strength=strength,
                income_rate=income,
                maintenance=maintenance,
                income_decay=decay,
                epochs=epochs,
            )
            actual = _LazyDelta()
            status = self.library.compost_lazy_metabolism_delta(
                strength, income, maintenance, decay, epochs, ctypes.byref(actual)
            )
            self.assertEqual(status, 0)
            self.assertAlmostEqual(actual.strength_after, expected.strength_after, places=12)
            self.assertAlmostEqual(actual.income_rate_after, expected.income_rate_after, places=12)
            self.assertEqual(actual.strength_decay_epochs, expected.strength_decay_epochs)

    def test_reproduction_assessment_matches_reference(self) -> None:
        config = LifecycleConfig(reproduction_minimum_body=4, birth_cost=1.0)
        for body_size, reserve, selected_count in ((4, 2.0, 2), (3, 2.0, 2), (4, 0.5, 2), (4, 2.0, 1)):
            organism = MathematicalLifeOrganism(1, None, 0, 0, 0, reserve=reserve)
            for index in range(body_size):
                organism.atoms[str(index)] = LivingStructure(str(index), "ATOM")
            expected = reproduction_allowed(organism, config, selected_count=selected_count)
            actual = _ReproductionAssessment()
            status = self.library.compost_reproduction_assessment(
                body_size,
                reserve,
                config.birth_cost,
                config.reproduction_minimum_body,
                selected_count,
                ctypes.byref(actual),
            )
            self.assertEqual(status, 0)
            self.assertEqual(bool(actual.allowed), expected.allowed)
            self.assertEqual(actual.selected_count, selected_count)
            self.assertAlmostEqual(actual.parent_reserve_after_cost, expected.parent_reserve_after_cost, places=12)
            if selected_count >= 2:
                self.assertEqual(actual.score, expected.score)
            else:
                self.assertTrue(actual.score < 0.0)

    def test_simple_lifecycle_replay_reports_first_divergent_field(self) -> None:
        payload = "AB" * 128
        population = MathematicalLifePopulation(payload)
        with NativeBackend(self.library_path, organism_id=0) as backend:
            for cycle in range(256):
                population.cycle()
                backend.step(payload.encode("ascii") if cycle == 0 else b"", (1.0,) * len(payload) if cycle == 0 else ())
                reference = population.organisms[0]
                native = backend.snapshot()
                self.assertEqual(native["cursor"], reference.cursor, f"step {cycle}: cursor")
                self.assertEqual(native["age_in_cycles"], reference.age_in_cycles, f"step {cycle}: age")
                self.assertEqual(native["body"]["atom_count"], len(reference.atoms), f"step {cycle}: atom_count")
                self.assertEqual(native["body"]["relation_count"], len(reference.relations), f"step {cycle}: relation_count")
                self.assertEqual(native["body"]["composite_count"], len(reference.composites), f"step {cycle}: composite_count")
                self.assertEqual(native["body"]["structural_mass"], reference.full_body_mass(), f"step {cycle}: structural_mass")
                self.assertAlmostEqual(native["reserve"], reference.reserve, places=12, msg=f"step {cycle}: reserve")
                native_atoms = {
                    chr(left): (strength, maintenance, evidence, income)
                    for left, _right, strength, maintenance, evidence, income in native["atoms"]
                }
                reference_atoms = {
                    key: (item.strength, item.maintenance, item.evidence, item.income_rate)
                    for key, item in reference.atoms.items()
                }
                self.assertEqual(set(native_atoms), set(reference_atoms), f"step {cycle}: atom keys")
                for key in sorted(reference_atoms):
                    for index, (actual, expected) in enumerate(zip(native_atoms[key], reference_atoms[key])):
                        self.assertAlmostEqual(actual, expected, places=12, msg=f"step {cycle}: atom {key} field {index}")
                native_relations = {
                    (chr(left), chr(right)): (strength, maintenance, evidence, income)
                    for left, right, strength, maintenance, evidence, income in native["relations"]
                }
                reference_relations = {
                    key: (item.strength, item.maintenance, item.evidence, item.income_rate)
                    for key, item in reference.relations.items()
                }
                self.assertEqual(set(native_relations), set(reference_relations), f"step {cycle}: relation keys")
                for key in sorted(reference_relations):
                    for index, (actual, expected) in enumerate(zip(native_relations[key], reference_relations[key])):
                        self.assertAlmostEqual(actual, expected, places=12, msg=f"step {cycle}: relation {key} field {index}")


if __name__ == "__main__":
    unittest.main()
