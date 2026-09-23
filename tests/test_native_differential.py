from __future__ import annotations

import ctypes
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.biology_rules import (
    ACTIVITY_COSTS,
    ActivityCounters,
    ActivityLedger,
    forgetting_delta,
    lazy_metabolism_delta,
    maintenance_weakening_budget,
    structural_mass,
)
from mathematical_organism.backend import NativeBackend, NativeBackendError
from mathematical_organism.canonical import canonical_digest
from mathematical_organism.lifecycle import LifecycleConfig, LivingStructure, MathematicalLifeOrganism, MathematicalLifePopulation, OrganismStatus
from mathematical_organism.sandbox_runtime import AutonomousOrganism
from mathematical_organism.biology_rules import reproduction_allowed
from mathematical_organism.territory import address_bit, food_block_key


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


class _ActivityCosts(ctypes.Structure):
    _fields_ = [(name, ctypes.c_double) for name in (
        "byte", "digest_per_kib", "reject_per_kib", "resorption_per_kib",
        "relation_created", "relation_strengthened", "composite_created",
        "composite_strengthened", "structural_mass_delta", "resorption",
        "division", "basal_mass", "settlement_base", "settlement_mass_scale",
    )]


class _ActivityCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "bytes_eaten", "relations_created", "relations_strengthened",
        "composites_created", "composites_strengthened", "structural_mass_added",
        "structural_mass_lost", "resorption_events", "division_events",
        "processed_bytes", "rejected_bytes", "resorbed_processed_bytes",
    )]


class _ActivityLedger(ctypes.Structure):
    _fields_ = [
        ("metabolic_debt", ctypes.c_double),
        ("energy_spent", ctypes.c_double),
        ("settlements", ctypes.c_uint64),
        ("counters", _ActivityCounters),
    ]


class _ForgettingDelta(ctypes.Structure):
    _fields_ = [
        ("strength_after", ctypes.c_double),
        ("income_rate_after", ctypes.c_double),
    ]


class _FailureEvidence:
    def __init__(self, prefix: str, field: str, reference: MathematicalLifePopulation, backend: NativeBackend) -> None:
        self.prefix = prefix
        self.field = field
        self.reference = reference
        self.backend = backend

    def __str__(self) -> str:
        return (
            f"{self.prefix}: {self.field}; "
            f"reference_digest={canonical_digest(self.reference)}; "
            f"native_digest={self.backend.state_digest():016x}"
        )


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
        cls.library.compost_activity_settlement_threshold.argtypes = [
            ctypes.c_uint64, ctypes.POINTER(_ActivityCosts), ctypes.POINTER(ctypes.c_double)
        ]
        cls.library.compost_activity_settlement_threshold.restype = ctypes.c_int
        cls.library.compost_activity_basal_cost.argtypes = [
            ctypes.c_uint64, ctypes.POINTER(_ActivityCosts), ctypes.POINTER(ctypes.c_double)
        ]
        cls.library.compost_activity_basal_cost.restype = ctypes.c_int
        cls.library.compost_activity_ledger_add.argtypes = [
            ctypes.POINTER(_ActivityLedger), ctypes.POINTER(_ActivityCounters),
            ctypes.c_uint64, ctypes.POINTER(_ActivityCosts),
        ]
        cls.library.compost_activity_ledger_add.restype = ctypes.c_int
        cls.library.compost_forgetting_delta.argtypes = [
            ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.POINTER(_ForgettingDelta),
        ]
        cls.library.compost_forgetting_delta.restype = ctypes.c_int
        cls.library.compost_maintenance_weakening_budget.argtypes = [
            ctypes.c_double, ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64)
        ]
        cls.library.compost_maintenance_weakening_budget.restype = ctypes.c_int
        cls.library.compost_territory_address_bit.argtypes = [
            ctypes.c_uint64, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint8)
        ]
        cls.library.compost_territory_address_bit.restype = ctypes.c_int
        cls.library.compost_territory_contains.argtypes = [
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, ctypes.c_uint64,
            ctypes.POINTER(ctypes.c_bool),
        ]
        cls.library.compost_territory_contains.restype = ctypes.c_int
        cls.library.compost_territory_food_block_key.argtypes = [
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, ctypes.c_uint64,
            ctypes.POINTER(ctypes.c_uint64),
        ]
        cls.library.compost_territory_food_block_key.restype = ctypes.c_int

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

    def test_public_python_adapter_exposes_empty_weakest_transition(self) -> None:
        reference = AutonomousOrganism("ORG-EMPTY")
        self.assertFalse(reference.remove_weakest(reference.body, "STARVATION", True))
        with NativeBackend(self.library_path, organism_id=98) as backend:
            self.assertEqual(
                backend.weaken_weakest(),
                {"changed": False, "resorbed_mass": 0},
            )
            backend.verify_material_conservation()

    def test_public_python_adapter_try_divide_is_transactional_without_candidate(self) -> None:
        with NativeBackend(self.library_path, organism_id=101) as backend:
            before = backend.state_digest()
            child, plan = backend.try_divide(child_id=102)
            self.assertIsNone(child)
            self.assertFalse(plan["candidate_found"])
            self.assertFalse(plan["allowed"])
            self.assertEqual(backend.state_digest(), before)

    def test_public_python_adapter_try_divide_commits_allowed_candidate(self) -> None:
        config = LifecycleConfig(boundary_ratio_limit=0.5, birth_reserve=10.0)
        with NativeBackend(self.library_path, organism_id=110, config=config) as backend:
            backend.digest(b"\x04\x05", (1.0, 1.0))
            child, plan = backend.try_divide(child_id=111)
            self.assertIsNotNone(child)
            assert child is not None
            with child:
                self.assertTrue(plan["candidate_found"])
                self.assertTrue(plan["allowed"])
                self.assertEqual(plan["child_atoms"], (4,))
                self.assertGreater(plan["child_income"], plan["child_maintenance"])
                self.assertGreater(plan["parent_income"], plan["parent_maintenance"])
                self.assertGreater(plan["birth_gain"], 0.0)
                self.assertGreater(plan["division"]["cross_split_mass"], 0)
                backend.verify_material_conservation()
                child.verify_material_conservation()
                self.assertEqual(child.snapshot()["reserve"], 0.0)

    def test_step_and_try_divide_matches_python_lifecycle_boundary(self) -> None:
        config = LifecycleConfig(boundary_ratio_limit=0.5, birth_reserve=10.0)
        reference = MathematicalLifePopulation(chr(4) + chr(5), config)
        reference.cycle()
        reference_parent = reference.organisms[0]
        reference_child = reference.organisms[1]
        with NativeBackend(self.library_path, organism_id=0, config=config) as backend:
            child, cycle, plan = backend.step_and_try_divide(
                b"\x04\x05", child_id=1, nutrition=(1.0, 1.0)
            )
            self.assertIsNotNone(child)
            assert child is not None
            with child:
                parent = backend.snapshot()
                child_snapshot = child.snapshot()
                self.assertEqual(cycle["consumed_bytes"], reference_parent.cursor)
                self.assertTrue(plan["candidate_found"])
                self.assertTrue(plan["allowed"])
                self.assertEqual(parent["cursor"], reference_parent.cursor)
                self.assertEqual(child_snapshot["cursor"], reference_child.cursor)
                self.assertAlmostEqual(parent["reserve"], reference_parent.reserve, places=12)
                self.assertAlmostEqual(child_snapshot["reserve"], reference_child.reserve, places=12)
                self.assertEqual(parent["body"]["atom_count"], len(reference_parent.atoms))
                self.assertEqual(child_snapshot["body"]["atom_count"], len(reference_child.atoms))
                self.assertEqual(parent["body"]["relation_count"], len(reference_parent.relations))
                self.assertEqual(child_snapshot["body"]["relation_count"], len(reference_child.relations))
                backend.verify_material_conservation()
                child.verify_material_conservation()

    def test_native_backend_rejects_unrepresented_scheduling_config(self) -> None:
        with self.assertRaises(NativeBackendError):
            NativeBackend(
                self.library_path,
                config=LifecycleConfig(metabolic_minimum_work=32),
            )

    def test_public_python_adapter_runs_native_external_gut_fifo(self) -> None:
        with NativeBackend(self.library_path, organism_id=100) as backend:
            backend.enqueue_external(b"\x01\x02\x01", (1.0, 2.0, 3.0))
            queued = backend.snapshot()["gut"]
            self.assertEqual(queued, ((3, 0, b"\x01\x02\x01", (1.0, 2.0, 3.0)),))
            first = backend.process_gut(2)
            self.assertEqual(first, {
                "processed_mass": 2,
                "assimilated_mass": 2,
                "rejected_mass": 0,
                "expelled_mass": 0,
            })
            remaining = backend.snapshot()["gut"]
            self.assertEqual(remaining, ((1, 0, b"\x01", (3.0,)),))
            second = backend.process_gut(2)
            self.assertEqual(second["processed_mass"], 1)
            self.assertEqual(backend.snapshot()["gut"], ())
            backend.verify_material_conservation()

    def test_external_gut_processing_matches_sandbox_oracle(self) -> None:
        payload = (1, 2, 1)
        nutrition = (1.0, 2.0, 3.0)
        reference = AutonomousOrganism("ORG-ROOT")
        reference.enqueue_external_material(payload, nutrition)
        reference.result.available_nutrition_total += sum(nutrition)
        expected = reference.process_gut(2)
        with NativeBackend(self.library_path, organism_id=0) as backend:
            backend.enqueue_external(bytes(payload), nutrition)
            actual = backend.process_gut(2)
            snapshot = backend.snapshot()
        self.assertEqual(expected, 2)
        self.assertEqual(actual["processed_mass"], expected)
        self.assertEqual(actual["assimilated_mass"], reference.material_flow.assimilated_mass)
        self.assertEqual(actual["rejected_mass"], reference.material_flow.rejected_mass)
        self.assertEqual(actual["expelled_mass"], reference.material_flow.expelled_mass)
        self.assertEqual(snapshot["gut"], ((1, 0, bytes((1,)), (3.0,)),))
        for field in (
            "input_mass", "assimilated_mass", "rejected_mass", "resorbed_mass",
            "processed_mass", "expelled_mass", "external_expelled_mass",
            "resorption_expelled_mass", "structural_created_mass",
            "structural_transferred_in", "structural_transferred_out",
        ):
            self.assertEqual(snapshot["material_flow"][field], getattr(reference.material_flow, field), field)
        self.assertEqual(snapshot["body"]["atom_count"], len(reference.body.atoms))
        self.assertEqual(snapshot["body"]["relation_count"], len(reference.body.relations))
        self.assertEqual(snapshot["body"]["structural_mass"], reference.body.full_body_mass())
        reference.verify_material_conservation()
        with NativeBackend(self.library_path, organism_id=0) as checked_backend:
            checked_backend.enqueue_external(bytes(payload), nutrition)
            checked_backend.process_gut(2)
            checked_backend.verify_material_conservation()

    def test_environment_corpse_energy_transfer_matches_oracle(self) -> None:
        reference = AutonomousOrganism("ORG-ROOT")
        reference.body.adjust_reserve(2.5)
        with NativeBackend(self.library_path, organism_id=0) as backend:
            before = backend.state_digest()
            with self.assertRaises(NativeBackendError):
                backend.apply_corpse_energy(-1.0)
            self.assertEqual(backend.state_digest(), before)
            credited = backend.apply_corpse_energy(2.5)
            snapshot = backend.snapshot()
        self.assertEqual(credited, 2.5)
        self.assertAlmostEqual(snapshot["reserve"], reference.body.reserve, places=12)

    def test_partition_transaction_matches_sandbox_oracle(self) -> None:
        payload = (1, 2, 3, 4)
        nutrition = (10.0,) * len(payload)
        reference = AutonomousOrganism("ORG-ROOT")
        reference.result.available_nutrition_total += sum(nutrition)
        reference.enqueue_external_material(payload, nutrition)
        reference.process_gut(len(payload))
        reference_child = reference._commit_skeleton_partition({1, 2}, require_maturity=False)
        self.assertIsNotNone(reference_child)
        with NativeBackend(self.library_path, organism_id=0) as backend:
            backend.digest(bytes(payload), nutrition)
            native_child, native_result = backend.partition((1, 2), child_id=1, birth_cost=1.0)
            with native_child:
                native_parent = backend.snapshot()
                native_child_snapshot = native_child.snapshot()
        assert reference_child is not None
        reference_trace = reference.division_material_traces[-1]
        self.assertEqual(native_result["child_structural_mass"], reference_child.body.full_body_mass() - 256)
        self.assertEqual(native_result["cross_split_mass"], reference_trace.cross_split_relation_mass + reference_trace.cross_split_composite_mass)
        self.assertEqual(native_parent["body"]["structural_mass"], reference.body.full_body_mass())
        self.assertEqual(native_child_snapshot["body"]["structural_mass"], reference_child.body.full_body_mass())
        self.assertAlmostEqual(native_parent["reserve"], reference.body.reserve, places=12)
        self.assertEqual(native_child_snapshot["reserve"], reference_child.body.reserve)
        self.assertEqual(native_child_snapshot["body"]["relation_count"], len(reference_child.body.relations))
        self.assertEqual(native_child_snapshot["body"]["composite_count"], len(reference_child.body.composites))

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
                parent_dynamic_before + sum(item[0] for item in before["gut"]),
                parent_dynamic_after
                + child_dynamic_after
                + sum(item[0] for item in parent_after["gut"]),
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

    def test_activity_forgetting_and_weakening_rules_match_reference(self) -> None:
        costs = _ActivityCosts(*(
            getattr(ACTIVITY_COSTS, field)
            for field, _ctype in _ActivityCosts._fields_
        ))
        for body_mass in (0, 1, 256, 4096):
            threshold = ctypes.c_double()
            basal = ctypes.c_double()
            self.assertEqual(
                self.library.compost_activity_settlement_threshold(
                    body_mass, ctypes.byref(costs), ctypes.byref(threshold)
                ), 0
            )
            self.assertEqual(
                self.library.compost_activity_basal_cost(
                    body_mass, ctypes.byref(costs), ctypes.byref(basal)
                ), 0
            )
            self.assertAlmostEqual(threshold.value, ActivityLedger.settlement_threshold(body_mass), places=12)
            self.assertAlmostEqual(basal.value, ActivityLedger.basal_cost(body_mass), places=12)

        python_counters = ActivityCounters(
            bytes_eaten=11, relations_created=2, relations_strengthened=3,
            composites_created=4, composites_strengthened=5,
            structural_mass_added=6, structural_mass_lost=7,
            resorption_events=8, division_events=9, processed_bytes=10,
            rejected_bytes=12, resorbed_processed_bytes=13,
        )
        python_ledger = ActivityLedger()
        python_delta = python_ledger.add_activity(python_counters, 256)
        native_counters = _ActivityCounters(*(getattr(python_counters, field) for field, _ in _ActivityCounters._fields_))
        native_ledger = _ActivityLedger()
        native_delta = self.library.compost_activity_ledger_add(
            ctypes.byref(native_ledger), ctypes.byref(native_counters), 256, ctypes.byref(costs)
        )
        self.assertEqual(native_delta, 0)
        self.assertAlmostEqual(native_ledger.metabolic_debt, python_ledger.metabolic_debt, places=12)
        self.assertAlmostEqual(native_ledger.energy_spent, python_ledger.energy_spent, places=12)
        self.assertAlmostEqual(native_ledger.metabolic_debt, python_delta, places=12)
        self.assertEqual(tuple(getattr(native_ledger.counters, field) for field, _ in _ActivityCounters._fields_), tuple(getattr(python_ledger.counters, field) for field, _ in _ActivityCounters._fields_))

        for strength, income, maintenance, decay in ((5.0, 0.0, 0.5, 0.8), (5.0, 2.0, 0.5, 0.8)):
            structure = LivingStructure("A", "ATOM", maintenance=maintenance)
            structure.strength = strength
            structure.income_rate = income
            expected = forgetting_delta(structure, LifecycleConfig(income_decay=decay))
            actual = _ForgettingDelta()
            self.assertEqual(
                self.library.compost_forgetting_delta(
                    strength, income, maintenance, decay, ctypes.byref(actual)
                ), 0
            )
            self.assertAlmostEqual(actual.strength_after, expected.strength_after, places=12)
            self.assertAlmostEqual(actual.income_rate_after, expected.income_rate_after, places=12)

        for deficit, body_mass in ((0.0, 4), (1.0, 4), (4.1, 4), (9.0, 256)):
            budget = ctypes.c_uint64()
            self.assertEqual(
                self.library.compost_maintenance_weakening_budget(
                    deficit, body_mass, ctypes.byref(budget)
                ), 0
            )
            self.assertEqual(budget.value, maintenance_weakening_budget(deficit, body_mass))

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

    def test_territory_predicates_match_reference(self) -> None:
        addresses = (0, 1, 2, 255, 4096, (1 << 63) - 1, (1 << 64) - 1)
        for address in addresses:
            for depth in range(64):
                actual = ctypes.c_uint8(99)
                self.assertEqual(
                    self.library.compost_territory_address_bit(address, depth, ctypes.byref(actual)),
                    0,
                )
                self.assertEqual(actual.value, address_bit(address, depth))
            path = tuple(address_bit(address, depth) for depth in range(8))
            path_buffer = (ctypes.c_uint8 * len(path))(*path)
            contains = ctypes.c_bool(False)
            self.assertEqual(
                self.library.compost_territory_contains(
                    path_buffer, len(path), address, ctypes.byref(contains)
                ),
                0,
            )
            self.assertTrue(contains.value)
            opposite = (ctypes.c_uint8 * 1)((path[0] ^ 1))
            contains.value = True
            self.assertEqual(
                self.library.compost_territory_contains(
                    opposite, 1, address, ctypes.byref(contains)
                ),
                0,
            )
            self.assertFalse(contains.value)
        invalid_bit = ctypes.c_uint8(99)
        self.assertEqual(
            self.library.compost_territory_address_bit(0, 64, ctypes.byref(invalid_bit)),
            1,
        )
        self.assertEqual(invalid_bit.value, 99)
        invalid_contains = ctypes.c_bool(True)
        invalid_path = (ctypes.c_uint8 * 1)(2)
        self.assertEqual(
            self.library.compost_territory_contains(
                invalid_path, 1, 0, ctypes.byref(invalid_contains)
            ),
            1,
        )
        self.assertTrue(invalid_contains.value)

        for file_id in ("", "firmware-A", "unicode-ž", "x" * 127):
            encoded = file_id.encode("utf-8")
            file_buffer = (ctypes.c_uint8 * len(encoded))(*encoded)
            for block_index in (0, 1, 255, (1 << 63), (1 << 64) - 1):
                actual = ctypes.c_uint64()
                self.assertEqual(
                    self.library.compost_territory_food_block_key(
                        file_buffer, len(encoded), block_index, ctypes.byref(actual)
                    ),
                    0,
                )
                self.assertEqual(actual.value, food_block_key(file_id, block_index))
        invalid_key = ctypes.c_uint64(99)
        self.assertEqual(
            self.library.compost_territory_food_block_key(
                None, 1, 0, ctypes.byref(invalid_key)
            ),
            1,
        )
        self.assertEqual(invalid_key.value, 99)

    def test_simple_lifecycle_replay_reports_first_divergent_field(self) -> None:
        payloads = (
            "AB" * 128,
            "ABCD" * 64,
            "ABBA" * 64,
            "ABC" * 85,
        )
        cycles = int(os.environ.get("COMPOST_DIFFERENTIAL_CYCLES", "256"))
        if cycles <= 0:
            self.fail("COMPOST_DIFFERENTIAL_CYCLES must be positive")
        for scenario in range(40):
            payload = payloads[scenario % len(payloads)]
            population = MathematicalLifePopulation(payload)
            with NativeBackend(self.library_path, organism_id=scenario) as backend:
                for cycle in range(cycles):
                    population.cycle()
                    backend.step(payload.encode("ascii") if cycle == 0 else b"", (1.0,) * len(payload) if cycle == 0 else ())
                    reference = population.organisms[0]
                    native = backend.snapshot()
                    prefix = f"scenario {scenario} step {cycle}"
                    def evidence(field: str) -> _FailureEvidence:
                        return _FailureEvidence(prefix, field, population, backend)

                    self.assertEqual(native["status"], 0 if reference.status is OrganismStatus.ALIVE else 1, evidence("status"))
                    self.assertEqual(native["cursor"], reference.cursor, evidence("cursor"))
                    self.assertEqual(native["age_in_cycles"], reference.age_in_cycles, evidence("age"))
                    self.assertEqual(native["body"]["atom_count"], len(reference.atoms), evidence("atom_count"))
                    self.assertEqual(native["body"]["relation_count"], len(reference.relations), evidence("relation_count"))
                    self.assertEqual(native["body"]["composite_count"], len(reference.composites), evidence("composite_count"))
                    self.assertEqual(native["body"]["structural_mass"], reference.full_body_mass(), evidence("structural_mass"))
                    self.assertAlmostEqual(native["reserve"], reference.reserve, places=12, msg=evidence("reserve"))
                    native_atoms = {
                        chr(left): (strength, maintenance, evidence, income)
                        for left, _right, strength, maintenance, evidence, income in native["atoms"]
                    }
                    reference_atoms = {
                        key: (item.strength, item.maintenance, item.evidence, item.income_rate)
                        for key, item in reference.atoms.items()
                    }
                    self.assertEqual(set(native_atoms), set(reference_atoms), evidence("atom keys"))
                    for key in sorted(reference_atoms):
                        for index, (actual, expected) in enumerate(zip(native_atoms[key], reference_atoms[key])):
                            self.assertAlmostEqual(actual, expected, places=12, msg=evidence(f"atom {key} field {index}"))
                    native_relations = {
                        (chr(left), chr(right)): (strength, maintenance, evidence, income)
                        for left, right, strength, maintenance, evidence, income in native["relations"]
                    }
                    reference_relations = {
                        key: (item.strength, item.maintenance, item.evidence, item.income_rate)
                        for key, item in reference.relations.items()
                    }
                    self.assertEqual(set(native_relations), set(reference_relations), evidence("relation keys"))
                    for key in sorted(reference_relations):
                        for index, (actual, expected) in enumerate(zip(native_relations[key], reference_relations[key])):
                            self.assertAlmostEqual(actual, expected, places=12, msg=evidence(f"relation {key} field {index}"))
                    native_composites = {
                        (chr(left), chr(right)): (strength, maintenance, evidence, income)
                        for left, right, strength, maintenance, evidence, income in native["composites"]
                    }
                    reference_composites = {
                        key: (item.strength, item.maintenance, item.evidence, item.income_rate)
                        for key, item in reference.composites.items()
                    }
                    self.assertEqual(set(native_composites), set(reference_composites), evidence("composite keys"))
                    for key in sorted(reference_composites):
                        for index, (actual, expected) in enumerate(zip(native_composites[key], reference_composites[key])):
                            self.assertAlmostEqual(actual, expected, places=12, msg=evidence(f"composite {key} field {index}"))


if __name__ == "__main__":
    unittest.main()
