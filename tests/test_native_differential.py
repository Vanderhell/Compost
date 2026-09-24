from __future__ import annotations

import ctypes
from contextlib import redirect_stdout
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
NATIVE_REPLAY_FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "native_replays.json"


def _native_fixture(name: str) -> dict[str, object]:
    fixtures = json.loads(NATIVE_REPLAY_FIXTURES.read_text(encoding="utf-8"))
    return fixtures[name]

from mathematical_organism.biology_rules import (
    ACTIVITY_COSTS,
    ActivityCounters,
    ActivityLedger,
    forgetting_delta,
    lazy_metabolism_delta,
    maintenance_weakening_budget,
    structural_mass,
)
from mathematical_organism.backend import (
    NativeAction,
    NativeActionKind,
    NativeBackend,
    NativeBackendError,
    NativePopulationBackend,
    create_backend,
)
from mathematical_organism.canonical import canonical_digest
from mathematical_organism.cli import main as cli_main
from mathematical_organism.food_sandbox import SandboxFeedingHarness
from mathematical_organism.lifecycle import LifecycleConfig, LivingStructure, MathematicalLifeOrganism, MathematicalLifePopulation, OrganismStatus
from mathematical_organism.native_sandbox import NativeSandboxReplay
from mathematical_organism.sandbox_runtime import AutonomousOrganism, Corpse, GutChunk, SandboxRuntime
from mathematical_organism.biology_rules import reproduction_allowed
from mathematical_organism.territory import FoodTerritory, address_bit, food_block_key


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


class _SandboxFailureEvidence:
    def __init__(self, prefix: str, field: str, reference: AutonomousOrganism,
                 backend: NativePopulationBackend, organism_id: int) -> None:
        self.prefix = prefix
        self.field = field
        self.reference = reference
        self.backend = backend
        self.organism_id = organism_id

    def __str__(self) -> str:
        return (
            f"{self.prefix}: {self.field}; "
            f"reference_digest={canonical_digest(self.reference)}; "
            f"native_digest={self.backend.state_digests()[self.organism_id]:016x}"
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
        with NativePopulationBackend(self.library_path, organism_ids=(101,)) as population:
            before = population.state_digests()
            result = population.try_divide(101, child_id=102)
            self.assertIsNone(result["child"])
            self.assertEqual(tuple(population.organism_ids), (101,))
            self.assertEqual(population.state_digests(), before)

    def test_python_adapter_restores_exact_native_snapshot_between_handles(self) -> None:
        with NativeBackend(self.library_path, organism_id=900) as source:
            source.digest(b"AB", (1.0, 1.0))
            source.accumulate_metabolic_progress(65, 64, 4)
            expected_digest = source.state_digest()
            with NativeBackend(self.library_path, organism_id=900) as target:
                target.digest(b"A", (1.0,))
                target.restore_from(source)
                self.assertEqual(target.state_digest(), expected_digest)
                self.assertEqual(target.snapshot(), source.snapshot())

    def test_python_adapter_rejects_native_snapshot_identity_mismatch(self) -> None:
        with NativeBackend(self.library_path, organism_id=901) as source, \
                NativeBackend(self.library_path, organism_id=902) as target:
            before = target.state_digest()
            with self.assertRaises(NativeBackendError):
                target.restore_from(source)
            self.assertEqual(target.state_digest(), before)

    def test_native_sandbox_imports_an_evolved_representable_organism(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            organism = AutonomousOrganism()
            organism.body.add_structure(
                organism.body.atoms,
                LivingStructure(
                    65, "ATOM", strength=2.0, maintenance=0.25,
                    evidence=1.0, income_rate=2.0,
                ),
            )
            organism.body.add_structure(
                organism.body.atoms,
                LivingStructure(
                    66, "ATOM", strength=2.0, maintenance=0.25,
                    evidence=1.0, income_rate=2.0,
                ),
            )
            organism.body.add_structure(
                organism.body.relations,
                LivingStructure(
                    (65, 66), "RELATION", strength=2.0, maintenance=0.5,
                    evidence=1.0, income_rate=1.6,
                ),
            )
            organism.material_flow.structural_created_mass = 2
            organism.territory_state.territory = FoodTerritory((1, 0))
            organism.territory_state.local_birth_counter = 3
            organism.result.available_nutrition_total += 1.0
            organism.enqueue_external_material((65,), (1.0,))
            organism.metabolic_progress = 7
            organism.metabolic_steps = 2
            runtime.organisms.append(organism)
            with NativeSandboxReplay(self.library_path, runtime) as replay:
                imported = replay.population.snapshot(0)
            self.assertEqual(imported["territory"], (1, 0))
            self.assertEqual(imported["gut"], ((1, 0, b"A", (1.0,)),))
            self.assertEqual(imported["metabolic_progress"], 7)
            self.assertEqual(imported["metabolic_steps"], 2)
            self.assertEqual(imported["body"]["relation_count"], 1)

    def test_python_state_import_rejects_unknown_gut_origin_without_mutation(self) -> None:
        organism = AutonomousOrganism()
        organism.gut_queue.append(GutChunk(1, "unknown", (65,), (1.0,)))
        with NativeBackend(self.library_path, organism_id=903) as backend:
            before = backend.state_digest()
            with self.assertRaises(ValueError):
                backend.restore_from_python(organism)
            self.assertEqual(backend.state_digest(), before)

    def test_native_sandbox_imports_living_subset_with_python_owned_dead_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            dead = AutonomousOrganism("ORG-DEAD")
            dead.territory_state.die()
            live = AutonomousOrganism("ORG-LIVE")
            runtime.organisms.extend((dead, live))
            with NativeSandboxReplay(self.library_path, runtime, organism_ids=(0,)) as replay:
                epoch = replay.step()
                self.assertEqual(replay.organism_ids, (0,))
                self.assertEqual(tuple(item[0] for item in epoch.traces), (0,))

    def test_population_trace_preflight_is_epoch_wide_and_non_mutating(self) -> None:
        with NativePopulationBackend(self.library_path, organism_ids=(0, 1)) as population:
            before = population.state_digests()
            with self.assertRaises(TypeError):
                population.preflight_action_traces({
                    0: (NativeAction.external_gut(b"A", capacity=1),),
                    1: ("invalid",),  # type: ignore[dict-item]
                })
            self.assertEqual(population.state_digests(), before)

    def test_local_reproduction_selector_matches_deterministic_component_policy(self) -> None:
        config = LifecycleConfig(reproduction_minimum_body=4, birth_cost=1.0)
        reference = AutonomousOrganism("ORG-LOCAL", config=config)
        reference.result.available_nutrition_total += 40.0
        reference.enqueue_external_material((65, 66, 67, 68), (10.0,) * 4)
        reference.process_gut(4)
        reference_child = reference._reproduce_conservatively()
        self.assertIsNotNone(reference_child)
        assert reference_child is not None
        expected = tuple(sorted(reference_child.body.atoms))
        with NativeBackend(self.library_path, organism_id=103, config=config) as backend:
            backend.digest(b"ABCD", (10.0,) * 4)
            self.assertEqual(backend.select_local_reproduction(), expected)
            child, result = backend.try_local_reproduction(child_id=104)
            self.assertIsNotNone(child)
            assert child is not None
            with child:
                self.assertEqual(
                    child.snapshot()["body"]["structural_mass"],
                    reference_child.body.full_body_mass(),
                )
            self.assertEqual(
                backend.snapshot()["body"]["structural_mass"],
                reference.body.full_body_mass(),
            )
            self.assertAlmostEqual(backend.snapshot()["reserve"], reference.body.reserve, places=12)
            self.assertAlmostEqual(result["parent_reserve_after_cost"], reference.body.reserve, places=12)
        with NativePopulationBackend(
            self.library_path,
            organism_ids=(103,),
            config=config,
        ) as population:
            population.apply_actions({
                103: NativeAction.external_gut(
                    b"ABCD",
                    capacity=4,
                    nutrition=(10.0,) * 4,
                )
            })
            population.apply_actions({103: NativeAction.process_gut(capacity=4)})
            transaction = population.try_local_reproduction(103, child_id=104)
            self.assertEqual(tuple(population.organism_ids), (103, 104))
            self.assertIsNotNone(transaction["child"])
            self.assertEqual(
                transaction["child"]["body"]["structural_mass"],
                reference_child.body.full_body_mass(),
            )
            population.verify_material_conservation()

    def test_metabolic_schedule_matches_python_bounded_arithmetic(self) -> None:
        with NativeBackend(self.library_path, organism_id=88) as backend:
            for minimum_work, body_size, progress in (
                (1, 0, 0), (64, 4, 63), (64, 64, 65),
                (7, 31, 100), ((1 << 64) - 1, (1 << 64) - 1, (1 << 64) - 1),
            ):
                expected_threshold = max(minimum_work, body_size)
                expected_steps, expected_remaining = divmod(progress, expected_threshold)
                actual = backend.metabolic_schedule(minimum_work, body_size, progress)
                self.assertEqual(
                    actual,
                    {
                        "threshold": expected_threshold,
                        "due_steps": expected_steps,
                        "remaining_progress": expected_remaining,
                    },
                )
            with self.assertRaises(NativeBackendError):
                backend.metabolic_schedule(0, 1, 1)

    def test_metabolic_context_accumulator_matches_python_and_is_transactional(self) -> None:
        with NativeBackend(self.library_path, organism_id=89) as backend:
            self.assertEqual(backend.metabolic_snapshot(), {"progress": 0, "steps": 0})
            expected_progress = 0
            for amount in (1, 63, 65, 7):
                expected_progress += amount
                due, expected_progress = divmod(expected_progress, 64)
                actual = backend.accumulate_metabolic_progress(amount, 64, 4)
                self.assertEqual(
                    actual,
                    {"due_steps": due, "remaining_progress": expected_progress},
                )
                self.assertEqual(
                    backend.metabolic_snapshot(),
                    {"progress": expected_progress, "steps": 0},
                )
            before = backend.metabolic_snapshot()
            with self.assertRaises(NativeBackendError):
                backend.accumulate_metabolic_progress((1 << 64) - 1, 64, 4)
            self.assertEqual(backend.metabolic_snapshot(), before)

    def test_due_lifecycle_batch_matches_repeated_native_steps(self) -> None:
        with NativeBackend(self.library_path, organism_id=61) as batched:
            batched.digest(b"ABCD", (1.0, 1.0, 1.0, 1.0))
            with NativeBackend(self.library_path, organism_id=61) as repeated:
                repeated.restore_from(batched)
                batched_due = batched.accumulate_metabolic_progress(128, 64, 4)
                repeated_due = repeated.accumulate_metabolic_progress(128, 64, 4)
                self.assertEqual(batched_due, repeated_due)
                result = batched.run_due_lifecycle(batched_due["due_steps"])
                self.assertEqual(result["executed_steps"], batched_due["due_steps"])
                for _ in range(repeated_due["due_steps"]):
                    repeated.lifecycle_step(b"", ())
                self.assertEqual(batched.snapshot(), repeated.snapshot())
                self.assertEqual(batched.state_digest(), repeated.state_digest())

    def test_population_due_lifecycle_rolls_back_earlier_handles_on_failure(self) -> None:
        with NativePopulationBackend(self.library_path, organism_ids=(0, 1)) as population:
            before = population.snapshots()
            original = population._contexts[1].run_due_lifecycle

            def fail_after_first_handle(_count: int) -> dict[str, float | int]:
                raise NativeBackendError("injected due-lifecycle failure")

            population._contexts[1].run_due_lifecycle = fail_after_first_handle  # type: ignore[method-assign]
            with self.assertRaises(NativeBackendError):
                population.run_due_lifecycle({0: 1, 1: 1})
            population._contexts[1].run_due_lifecycle = original  # type: ignore[method-assign]
            self.assertEqual(population.snapshots(), before)

    def test_population_action_epoch_rolls_back_on_later_native_failure(self) -> None:
        with NativePopulationBackend(self.library_path, organism_ids=(0, 1)) as population:
            before = population.snapshots()
            original = population._contexts[1].apply_action

            def fail_after_first_action(_action: NativeAction) -> dict[str, object]:
                raise NativeBackendError("injected action-trace failure")

            population._contexts[1].apply_action = fail_after_first_action  # type: ignore[method-assign]
            traces = {
                0: (NativeAction.lifecycle_step(b"", nutrition=()),),
                1: (NativeAction.lifecycle_step(b"", nutrition=()),),
            }
            with self.assertRaises(NativeBackendError):
                population.replay_action_traces(traces)
            population._contexts[1].apply_action = original  # type: ignore[method-assign]
            self.assertEqual(population.snapshots(), before)

    def test_population_apply_actions_rolls_back_on_later_native_failure(self) -> None:
        with NativePopulationBackend(self.library_path, organism_ids=(0, 1)) as population:
            before = population.snapshots()
            original = population._contexts[1].apply_action

            def fail_after_first_handle(_action: NativeAction) -> dict[str, object]:
                raise NativeBackendError("injected apply-actions failure")

            population._contexts[1].apply_action = fail_after_first_handle  # type: ignore[method-assign]
            try:
                with self.assertRaises(NativeBackendError):
                    population.apply_actions({
                        0: NativeAction.external_gut(b"A", capacity=1),
                        1: NativeAction.lifecycle_step(b""),
                    })
            finally:
                population._contexts[1].apply_action = original  # type: ignore[method-assign]
            self.assertEqual(population.snapshots(), before)

    def test_population_apply_actions_removes_child_created_before_failure(self) -> None:
        config = LifecycleConfig(
            birth_reserve=10.0, boundary_ratio_limit=0.5,
            reproduction_minimum_body=2,
        )
        with NativePopulationBackend(self.library_path, organism_ids=(0, 2), config=config) as population:
            population.apply_actions({
                0: NativeAction.external_gut(b"\x04\x05", capacity=2, nutrition=(1.0, 1.0)),
            })
            before = population.snapshots()
            original = population._contexts[2].apply_action

            def fail_after_child_creation(_action: NativeAction) -> dict[str, object]:
                raise NativeBackendError("injected post-division action failure")

            population._contexts[2].apply_action = fail_after_child_creation  # type: ignore[method-assign]
            try:
                with self.assertRaises(NativeBackendError):
                    population.apply_actions({
                        0: NativeAction.division((4,), child_id=1, birth_cost=1.0),
                        2: NativeAction.lifecycle_step(b""),
                    })
            finally:
                population._contexts[2].apply_action = original  # type: ignore[method-assign]
            self.assertEqual(population.organism_ids, (0, 2))
            self.assertEqual(population.snapshots(), before)

    def test_direct_local_reproduction_rolls_back_when_child_snapshot_fails(self) -> None:
        config = LifecycleConfig(
            birth_reserve=10.0, boundary_ratio_limit=0.5,
            reproduction_minimum_body=2,
        )
        with NativePopulationBackend(self.library_path, organism_ids=(0,), config=config) as population:
            population.apply_actions({
                0: NativeAction.external_gut(
                    b"\x04\x05\x06\x07", capacity=4,
                    nutrition=(2.0, 2.0, 2.0, 2.0)
                ),
            })
            before = population.snapshots()
            with patch.object(
                NativeBackend,
                "snapshot",
                side_effect=NativeBackendError("injected child snapshot failure"),
            ):
                with self.assertRaises(NativeBackendError):
                    population.try_local_reproduction(0, child_id=1)
            self.assertEqual(population.organism_ids, (0,))
            self.assertEqual(population.snapshots(), before)

    def test_direct_boundary_division_rolls_back_when_child_snapshot_fails(self) -> None:
        config = LifecycleConfig(birth_reserve=10.0, boundary_ratio_limit=0.5)
        with NativePopulationBackend(self.library_path, organism_ids=(0,), config=config) as population:
            population.apply_actions({
                0: NativeAction.external_gut(
                    b"\x04\x05", capacity=2, nutrition=(1.0, 1.0)
                ),
            })
            before = population.snapshots()
            with patch.object(
                NativeBackend,
                "snapshot",
                side_effect=NativeBackendError("injected child snapshot failure"),
            ):
                with self.assertRaises(NativeBackendError):
                    population.try_divide(0, child_id=1)
            self.assertEqual(population.organism_ids, (0,))
            self.assertEqual(population.snapshots(), before)

    def test_single_action_epoch_rolls_back_on_later_native_failure(self) -> None:
        with NativeBackend(self.library_path, organism_id=2) as backend:
            before = backend.state_digest()
            original = backend.apply_action
            calls = [0]

            def fail_after_first_action(action: NativeAction) -> dict[str, object]:
                if calls[0] == 0:
                    calls[0] += 1
                    return original(action)
                raise NativeBackendError("injected single-handle action failure")

            backend.apply_action = fail_after_first_action  # type: ignore[method-assign]
            try:
                with self.assertRaises(NativeBackendError):
                    backend.replay_actions(
                        (
                            NativeAction.external_gut(b"A", capacity=1),
                            NativeAction.lifecycle_step(b""),
                        )
                    )
            finally:
                backend.apply_action = original  # type: ignore[method-assign]
            self.assertEqual(backend.state_digest(), before)

    def test_population_transaction_restores_handle_removed_during_failed_epoch(self) -> None:
        dead = AutonomousOrganism("ORG-DEAD")
        dead.territory_state.die()
        with NativePopulationBackend(self.library_path, organism_ids=(0,)) as population:
            population.restore_from_python(0, dead)
            before = population.snapshots()
            with self.assertRaises(RuntimeError):
                with population._native_transaction():
                    population.take_corpse(0)
                    raise RuntimeError("injected epoch failure")
            self.assertEqual(population.organism_ids, (0,))
            self.assertEqual(population.snapshots(), before)

    def test_population_environment_step_rolls_back_on_later_handle_failure(self) -> None:
        with NativePopulationBackend(self.library_path, organism_ids=(0, 1)) as population:
            before = population.snapshots()
            original = population._contexts[1].step_and_try_divide

            def fail_after_first_handle(
                _food: bytes,
                *,
                child_id: int,
                nutrition: tuple[float, ...] | None = None,
            ) -> tuple[None, dict[str, float | int], dict[str, object]]:
                raise NativeBackendError("injected environment-step failure")

            population._contexts[1].step_and_try_divide = fail_after_first_handle  # type: ignore[method-assign]
            with self.assertRaises(NativeBackendError):
                population.step({0: (b"A", (1.0,)), 1: (b"B", (1.0,))})
            population._contexts[1].step_and_try_divide = original  # type: ignore[method-assign]
            self.assertEqual(population.snapshots(), before)

    def test_metabolic_progress_action_replays_python_accounting(self) -> None:
        with NativeBackend(self.library_path, organism_id=90) as backend:
            actions = (
                NativeAction.metabolic_progress(63, minimum_work=64, body_size=4),
                NativeAction.metabolic_progress(65, minimum_work=64, body_size=4),
            )
            results = backend.replay_actions(actions)
            self.assertEqual(results[0], {"kind": "metabolic_progress", "due_steps": 0, "remaining_progress": 63})
            self.assertEqual(results[1], {"kind": "metabolic_progress", "due_steps": 2, "remaining_progress": 0})
            self.assertEqual(backend.metabolic_snapshot(), {"progress": 0, "steps": 0})

    def test_due_accounting_does_not_count_lifecycle_work_after_dead_stop(self) -> None:
        dead = AutonomousOrganism("ORG-DEAD")
        dead.territory_state.die()
        with NativeBackend(self.library_path, organism_id=91) as backend:
            backend.restore_from_python(dead)
            self.assertEqual(
                backend.accumulate_metabolic_progress(128, 64, 4),
                {"due_steps": 2, "remaining_progress": 0},
            )
            self.assertEqual(backend.metabolic_snapshot(), {"progress": 0, "steps": 0})
            result = backend.run_due_lifecycle(2)
            self.assertEqual(result["executed_steps"], 0)
            self.assertEqual(backend.metabolic_snapshot(), {"progress": 0, "steps": 0})

    def test_native_snapshot_exposes_replayed_metabolic_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=4)
            (runtime.inbox / "payload.bin").write_bytes(b"ABCD" * 32)
            organism = runtime.bootstrap()
            trace: list[NativeAction] = []
            organism.live_step(runtime, action_trace=trace)
            with NativeBackend(self.library_path, organism_id=0) as backend:
                backend.replay_actions(trace)
                snapshot = backend.snapshot()
                self.assertEqual(snapshot["metabolic_progress"], organism.metabolic_progress)
                self.assertEqual(snapshot["metabolic_steps"], organism.metabolic_steps)

    def test_due_metabolic_trace_replays_lifecycle_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=4)
            (runtime.inbox / "payload.bin").write_bytes(b"ABCD" * 64)
            organism = runtime.bootstrap()
            with NativeBackend(self.library_path, organism_id=0) as backend:
                for step in range(100):
                    trace: list[NativeAction] = []
                    organism.live_step(runtime, action_trace=trace)
                    backend.replay_actions(trace)
                    if organism.metabolic_steps == 0:
                        continue
                    native = backend.snapshot()
                    self.assertEqual(
                        [action.kind.value for action in trace],
                        ["external_gut", "metabolic_progress", "lifecycle_step"],
                        step,
                    )
                    self.assertEqual(native["age_in_cycles"], organism.body.age_in_cycles)
                    self.assertAlmostEqual(native["reserve"], organism.body.reserve, places=12)
                    self.assertEqual(native["body"]["structural_mass"], organism.body.full_body_mass())
                    self.assertEqual(native["body"]["atom_count"], len(organism.body.atoms))
                    self.assertEqual(native["body"]["relation_count"], len(organism.body.relations))
                    self.assertEqual(native["body"]["composite_count"], len(organism.body.composites))
                    self.assertEqual(native["metabolic_steps"], organism.metabolic_steps)
                    break
                else:
                    self.fail("metabolic lifecycle checkpoint was not reached")

    def test_long_lifecycle_trace_replays_activity_debt_and_settlement(self) -> None:
        """Lifecycle accounting must remain identical after repeated checkpoints."""
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=4)
            (runtime.inbox / "payload.bin").write_bytes(b"ABCD" * 1024)
            organism = AutonomousOrganism(config=LifecycleConfig(birth_reserve=100.0))
            runtime.organisms.append(organism)
            with NativeBackend(self.library_path, organism_id=0, config=organism.config) as backend:
                for step in range(100):
                    trace: list[NativeAction] = []
                    organism.live_step(runtime, action_trace=trace)
                    backend.replay_actions(trace)
                    native = backend.snapshot()
                    self.assertEqual(native["age_in_cycles"], organism.body.age_in_cycles, step)
                    self.assertEqual(native["metabolic_steps"], organism.metabolic_steps, step)
                    self.assertEqual(
                        native["reserve"],
                        organism.body.reserve,
                        f"reserve diverged at step {step}: native debt={native['activity']['metabolic_debt']}, "
                        f"python debt={organism.activity_ledger.metabolic_debt}, "
                        f"native mass={native['body']['structural_mass']}, python mass={organism.body.full_body_mass()}, "
                        f"trace={[action.kind.value for action in trace]}",
                    )
                    self.assertEqual(
                        native["body"]["structural_mass"], organism.body.full_body_mass(), step
                    )
                    for field in (
                        "input_mass", "assimilated_mass", "rejected_mass", "resorbed_mass",
                        "processed_mass", "expelled_mass", "external_expelled_mass",
                        "resorption_expelled_mass", "structural_created_mass",
                        "structural_transferred_in", "structural_transferred_out",
                    ):
                        self.assertEqual(
                            native["material_flow"][field],
                            getattr(organism.material_flow, field),
                            f"material flow {field} diverged at step {step}",
                        )
                    for field in (
                        "bytes_eaten", "relations_created", "relations_strengthened",
                        "composites_created", "composites_strengthened", "structural_mass_added",
                        "structural_mass_lost", "resorption_events", "division_events",
                        "processed_bytes", "rejected_bytes", "resorbed_processed_bytes",
                    ):
                        self.assertEqual(
                            native["activity"]["counters"][field],
                            getattr(organism.activity_ledger.counters, field),
                            f"activity counter {field} diverged at step {step}",
                        )
                    self.assertAlmostEqual(
                        native["activity"]["metabolic_debt"],
                        organism.activity_ledger.metabolic_debt,
                        places=12,
                        msg=f"metabolic debt diverged at step {step}",
                    )
                    self.assertAlmostEqual(
                        native["activity"]["energy_spent"],
                        organism.activity_ledger.energy_spent,
                        places=12,
                        msg=f"energy spent diverged at step {step}",
                    )
                    self.assertEqual(
                        native["activity"]["settlements"],
                        organism.activity_ledger.settlements,
                        step,
                    )

    def test_low_reserve_lifecycle_trace_replays_maintenance_pressure(self) -> None:
        config = LifecycleConfig(birth_reserve=0.0)
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=4)
            (runtime.inbox / "payload.bin").write_bytes(b"ABCD" * 128)
            organism = AutonomousOrganism(config=config)
            runtime.organisms.append(organism)
            with NativeBackend(self.library_path, organism_id=81, config=config) as backend:
                for step in range(64):
                    trace: list[NativeAction] = []
                    organism.live_step(runtime, action_trace=trace)
                    backend.replay_actions(trace)
                    native = backend.snapshot()
                    self.assertEqual(native["status"], 0 if organism.alive else 1, step)
                    self.assertEqual(
                        native["body"]["structural_mass"],
                        organism.body.full_body_mass(),
                        f"step {step} trace={[action.kind.value for action in trace]} "
                        f"native atoms={native['atoms']} native relations={native['relations']} "
                        f"python atoms={tuple(organism.body.atoms)} python relations={tuple(organism.body.relations)}",
                    )
                    self.assertEqual(native["body"]["atom_count"], len(organism.body.atoms), step)
                    self.assertEqual(native["body"]["relation_count"], len(organism.body.relations), step)
                    self.assertEqual(native["body"]["composite_count"], len(organism.body.composites), step)
                    self.assertAlmostEqual(native["reserve"], organism.body.reserve, places=12, msg=step)
                    native_atoms = {
                        left: (strength, maintenance, evidence, income)
                        for left, _right, strength, maintenance, evidence, income in native["atoms"]
                    }
                    expected_atoms = {
                        key: (item.strength, item.maintenance, item.evidence, item.income_rate)
                        for key, item in organism.body.atoms.items()
                    }
                    self.assertEqual(native_atoms.keys(), expected_atoms.keys(), step)
                    for key in expected_atoms:
                        for actual, expected in zip(native_atoms[key], expected_atoms[key]):
                            self.assertAlmostEqual(actual, expected, places=12, msg=f"step {step} atom {key}")
                    for field, collection in (
                        ("relations", organism.body.relations),
                        ("composites", organism.body.composites),
                    ):
                        actual_structures = {
                            (left, right): (strength, maintenance, evidence, income)
                            for left, right, strength, maintenance, evidence, income in native[field]
                        }
                        expected_structures = {
                            key: (item.strength, item.maintenance, item.evidence, item.income_rate)
                            for key, item in collection.items()
                        }
                        self.assertEqual(actual_structures.keys(), expected_structures.keys(), step)
                        for key in expected_structures:
                            for actual, expected in zip(actual_structures[key], expected_structures[key]):
                                self.assertAlmostEqual(
                                    actual, expected, places=12,
                                    msg=f"step {step} {field} {key}",
                                )
                    for field in (
                        "input_mass", "assimilated_mass", "rejected_mass", "resorbed_mass",
                        "processed_mass", "expelled_mass", "external_expelled_mass",
                        "resorption_expelled_mass", "structural_created_mass",
                        "structural_transferred_in", "structural_transferred_out",
                    ):
                        self.assertEqual(native["material_flow"][field], getattr(organism.material_flow, field), step)
                    for field in (
                        "bytes_eaten", "relations_created", "relations_strengthened",
                        "composites_created", "composites_strengthened", "structural_mass_added",
                        "structural_mass_lost", "resorption_events", "division_events",
                        "processed_bytes", "rejected_bytes", "resorbed_processed_bytes",
                    ):
                        self.assertEqual(
                            native["activity"]["counters"][field],
                            getattr(organism.activity_ledger.counters, field),
                            f"step {step} activity {field}",
                        )

    def test_starvation_lifecycle_replay_reaches_matching_death(self) -> None:
        config = LifecycleConfig(birth_reserve=0.0)
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=4)
            (runtime.inbox / "payload.bin").write_bytes(b"ABCD")
            organism = AutonomousOrganism(config=config)
            runtime.organisms.append(organism)
            with NativeBackend(self.library_path, organism_id=82, config=config) as backend:
                trace: list[NativeAction] = []
                organism.live_step(runtime, action_trace=trace)
                backend.replay_actions(trace)
                for epoch in range(128):
                    if not organism.alive:
                        break
                    organism._run_metabolic_step(runtime)
                    lifecycle_result = backend.apply_action(NativeAction.lifecycle_step(b""))
                    native = backend.snapshot()
                    self.assertEqual(
                        native["status"],
                        0 if organism.alive else 1,
                        f"epoch {epoch} native={native['body']} reserve={native['reserve']} "
                        f"python atoms={tuple(organism.body.atoms)} relations={tuple(organism.body.relations)} "
                        f"python reserve={organism.body.reserve}",
                    )
                    self.assertEqual(native["age_in_cycles"], organism.body.age_in_cycles, epoch)
                    self.assertEqual(
                        native["body"]["structural_mass"],
                        organism.body.full_body_mass(),
                        f"epoch {epoch} lifecycle={lifecycle_result} native={native['body']} reserve={native['reserve']} python reserve={organism.body.reserve} "
                        f"python atoms={tuple(organism.body.atoms)} "
                        f"relations={tuple(organism.body.relations)}",
                    )
                    self.assertEqual(native["body"]["atom_count"], len(organism.body.atoms), epoch)
                    self.assertEqual(native["body"]["relation_count"], len(organism.body.relations), epoch)
                    self.assertEqual(native["body"]["composite_count"], len(organism.body.composites), epoch)
                    self.assertAlmostEqual(native["reserve"], organism.body.reserve, places=12, msg=epoch)
                    self.assertEqual(native["material_flow"]["resorbed_mass"], organism.material_flow.resorbed_mass, epoch)
                    self.assertEqual(
                        native["activity"]["counters"]["resorption_events"],
                        organism.activity_ledger.counters.resorption_events,
                        epoch,
                    )
                    self.assertEqual(
                        lifecycle_result["requests"],
                        ("store_corpse",) if not organism.alive else (),
                        epoch,
                    )
                self.assertFalse(organism.alive)
                self.assertEqual(backend.snapshot()["status"], 1)
                before_dead_step = backend.state_digest()
                dead_result = backend.apply_action(NativeAction.lifecycle_step(b""))
                self.assertEqual(dead_result["consumed_bytes"], 0)
                self.assertEqual(dead_result["status_after"], 1)
                self.assertEqual(dead_result["requests"], ())
                self.assertEqual(backend.state_digest(), before_dead_step)
                corpse = backend.take_corpse()
                self.assertEqual(corpse["status"], 1)
                with self.assertRaises(NativeBackendError):
                    backend.snapshot()

    def test_sandbox_division_action_replays_parent_and_transient_child(self) -> None:
        config = LifecycleConfig(boundary_ratio_limit=0.5, birth_reserve=10.0)
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=2)
            (runtime.inbox / "payload.bin").write_bytes(bytes((4, 5)) * 64)
            organism = AutonomousOrganism(config=config)
            runtime.organisms.append(organism)
            with NativeBackend(self.library_path, organism_id=0, config=config) as backend:
                for step in range(100):
                    trace: list[NativeAction] = []
                    organism.live_step(runtime, action_trace=trace)
                    results = backend.replay_actions(trace)
                    if not any(action.kind is NativeActionKind.DIVISION for action in trace):
                        continue
                    native_parent = backend.snapshot()
                    native_child = results[-1]["child"]
                    assert isinstance(native_child, dict)
                    self.assertEqual(
                        [action.kind.value for action in trace],
                        ["external_gut", "metabolic_progress", "lifecycle_step", "division"],
                        step,
                    )
                    self.assertEqual(native_parent["body"]["structural_mass"], organism.body.full_body_mass())
                    self.assertEqual(native_parent["body"]["atom_count"], len(organism.body.atoms))
                    self.assertEqual(native_parent["body"]["relation_count"], len(organism.body.relations))
                    self.assertEqual(native_parent["body"]["composite_count"], len(organism.body.composites))
                    self.assertAlmostEqual(native_parent["reserve"], organism.body.reserve, places=12)
                    child = organism.children[-1]
                    self.assertEqual(native_child["body"]["structural_mass"], child.body.full_body_mass())
                    self.assertEqual(native_child["body"]["atom_count"], len(child.body.atoms))
                    self.assertEqual(native_child["body"]["relation_count"], len(child.body.relations))
                    self.assertEqual(native_child["body"]["composite_count"], len(child.body.composites))
                    self.assertEqual(native_child["reserve"], 0.0)
                    self.assertEqual(child.body.reserve, 0.0)
                    break
                else:
                    self.fail("sandbox division action was not reached")

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

    def test_two_organism_python_allocation_drives_native_steps(self) -> None:
        fixture = _native_fixture("population_boundary")
        organism_ids = tuple(int(value) for value in fixture["organism_ids"])
        config = LifecycleConfig(boundary_ratio_limit=float(fixture["boundary_ratio_limit"]))
        payload = str(fixture["payload_pattern"]) * int(fixture["payload_repeats"])
        reference = MathematicalLifePopulation(payload, config)
        for organism_id in organism_ids[1:]:
            reference.organisms[organism_id] = MathematicalLifeOrganism(
                organism_id, None, 0, 0, 0, reserve=config.birth_reserve
            )
        reference.next_id = max(organism_ids) + 1
        with NativePopulationBackend(
            self.library_path, organism_ids=organism_ids, config=config
        ) as native_population:
            with self.assertRaises(ValueError):
                native_population.step({99: (b"", ())})
            with self.assertRaises(ValueError):
                native_population.step(
                    {organism_id: (b"", ()) for organism_id in organism_ids},
                    child_ids={organism_id: 2 for organism_id in organism_ids},
                )
            before_invalid_epoch = native_population.snapshots()
            with self.assertRaises(ValueError):
                native_population.step(
                    {organism_ids[0]: (b"\x01", (1.0,)), organism_ids[1]: (b"\x02", (1.0, 2.0))},
                    child_ids={organism_id: 100 + organism_id for organism_id in organism_ids},
                )
            self.assertEqual(native_population.snapshots(), before_invalid_epoch)

            before_invalid_digests = native_population.state_digests()
            with self.assertRaises(ValueError):
                native_population.step(
                    {organism_ids[0]: (b"\x01", (float("nan"),)), organism_ids[1]: (b"\x02", (1.0,))},
                    child_ids={organism_id: 100 + organism_id for organism_id in organism_ids},
                )
            self.assertEqual(native_population.snapshots(), before_invalid_epoch)
            self.assertEqual(native_population.state_digests(), before_invalid_digests)
            for cycle in range(int(fixture["cycles"])):
                planned = reference._allocate_nutrition(organism_ids)
                step_results = native_population.step(
                    {
                        organism_id: (
                            bytes(ord(symbol) for symbol in planned.get(organism_id, ((), ()))[0]),
                            planned.get(organism_id, ((), ()))[1],
                        )
                        for organism_id in organism_ids
                    },
                    child_ids={organism_id: 100 + organism_id for organism_id in organism_ids},
                )
                for organism_id in organism_ids:
                    self.assertNotIn("child_id", step_results[organism_id])
                for organism_id in organism_ids:
                    organism = reference.organisms[organism_id]
                    bite, nutrition = planned.get(organism_id, ((), ()))
                    reference._cycle_one(organism, (bite, nutrition))
                    native = native_population.snapshot(organism_id)
                    prefix = f"population cycle {cycle} organism {organism_id}"
                    self.assertEqual(native["cursor"], organism.cursor, prefix)
                    self.assertEqual(native["age_in_cycles"], organism.age_in_cycles, prefix)
                    self.assertEqual(native["status"], 0 if organism.status is OrganismStatus.ALIVE else 1, prefix)
                    self.assertAlmostEqual(native["reserve"], organism.reserve, places=12, msg=prefix)
                    self.assertEqual(native["body"]["structural_mass"], organism.full_body_mass(), prefix)
                    self.assertEqual(native["body"]["atom_count"], len(organism.atoms), prefix)
                    self.assertEqual(native["body"]["relation_count"], len(organism.relations), prefix)
                    self.assertEqual(native["body"]["composite_count"], len(organism.composites), prefix)
                    native_atoms = {
                        chr(left): (strength, maintenance, evidence, income)
                        for left, _right, strength, maintenance, evidence, income in native["atoms"]
                    }
                    reference_atoms = {
                        key: (item.strength, item.maintenance, item.evidence, item.income_rate)
                        for key, item in organism.atoms.items()
                    }
                    self.assertEqual(set(native_atoms), set(reference_atoms), prefix)
                    for key in sorted(reference_atoms):
                        for actual, expected in zip(native_atoms[key], reference_atoms[key]):
                            self.assertAlmostEqual(actual, expected, places=12, msg=f"{prefix} atom {key}")
                    for native_field, reference_collection in (
                        ("relations", organism.relations),
                        ("composites", organism.composites),
                    ):
                        native_structures = {
                            (chr(left), chr(right)): (strength, maintenance, evidence, income)
                            for left, right, strength, maintenance, evidence, income
                            in native[native_field]
                        }
                        reference_structures = {
                            key: (item.strength, item.maintenance, item.evidence, item.income_rate)
                            for key, item in reference_collection.items()
                        }
                        self.assertEqual(set(native_structures), set(reference_structures), prefix)
                        for key in sorted(reference_structures):
                            for actual, expected in zip(native_structures[key], reference_structures[key]):
                                self.assertAlmostEqual(
                                    actual, expected, places=12,
                                    msg=f"{prefix} {native_field} {key}",
                                )
                native_population.verify_material_conservation()
                reference.result.cycles += 1

    def test_population_rejects_non_uint64_ids_before_mutation(self) -> None:
        with NativePopulationBackend(self.library_path, organism_ids=(0, 1)) as population:
            before = population.snapshots()
            with self.assertRaises(ValueError):
                population.step({"0": (b"", ())})  # type: ignore[dict-item]
            with self.assertRaises(ValueError):
                population.step({0: (b"", ())}, child_ids={0: "1"})  # type: ignore[dict-item]
            with self.assertRaises(ValueError):
                population.apply_actions({"0": NativeAction.lifecycle_step(b"")})  # type: ignore[dict-item]
            with self.assertRaises(ValueError):
                population.run_due_lifecycle({"0": 1})  # type: ignore[dict-item]
            with self.assertRaises(ValueError):
                population.replay_action_traces({"0": ()})  # type: ignore[dict-item]
            with self.assertRaises(ValueError):
                population.snapshot("0")  # type: ignore[arg-type]
            with self.assertRaises(ValueError):
                population.take_corpse(True)  # type: ignore[arg-type]
            with self.assertRaises(ValueError):
                population.restore_from_python(1.5, object())  # type: ignore[arg-type]
            self.assertEqual(population.snapshots(), before)

    def test_backend_constructors_reject_lossy_organism_ids(self) -> None:
        invalid_ids = ("0", 1.5, -1, 1 << 64, True)
        for organism_id in invalid_ids:
            with self.assertRaises(ValueError):
                NativeBackend(self.library_path, organism_id=organism_id)  # type: ignore[arg-type]
            with self.assertRaises(ValueError):
                NativePopulationBackend(
                    self.library_path, organism_ids=(organism_id,)
                )  # type: ignore[arg-type]
        with NativeBackend(self.library_path) as backend:
            for child_id in ("1", 1.5, -1, 1 << 64, True):
                with self.assertRaises(ValueError):
                    backend.try_divide(child_id=child_id)  # type: ignore[arg-type]

    def test_native_population_registers_division_child(self) -> None:
        config = LifecycleConfig(boundary_ratio_limit=0.5, birth_reserve=10.0)
        with NativePopulationBackend(
            self.library_path, organism_ids=(0,), config=config
        ) as population:
            result = population.step(
                {0: (b"\x04\x05", (1.0, 1.0))}, child_ids={0: 1}
            )
            self.assertEqual(result[0]["child_id"], 1)
            self.assertEqual(population.organism_ids, (0, 1))
            parent = population.snapshot(0)
            child = population.snapshot(1)
            self.assertEqual(parent["cursor"], 2)
            self.assertEqual(child["cursor"], 2)
            self.assertEqual(child["parent_id"], 0)
            self.assertTrue(child["has_parent"])
            self.assertEqual(child["reserve"], 0.0)
            population.verify_material_conservation()

    def test_native_population_replays_division_and_child_death(self) -> None:
        config = LifecycleConfig(boundary_ratio_limit=0.5, birth_reserve=10.0)
        reference = MathematicalLifePopulation(chr(4) + chr(5), config)
        with NativePopulationBackend(
            self.library_path, organism_ids=(0,), config=config
        ) as population:
            for cycle in range(8):
                environment = {
                    organism_id: (
                        (b"\x04\x05", (1.0, 1.0))
                        if cycle == 0 and organism_id == 0
                        else (b"", ())
                    )
                    for organism_id in population.organism_ids
                }
                status_before = {
                    organism_id: int(population.snapshot(organism_id)["status"])
                    for organism_id in population.organism_ids
                }
                step_results = population.step(environment)
                reference.cycle()
                self.assertEqual(population.organism_ids, tuple(sorted(reference.organisms)))
                for organism_id in population.organism_ids:
                    native = population.snapshot(organism_id)
                    oracle = reference.organisms[organism_id]
                    prefix = f"division/death cycle {cycle} organism {organism_id}"
                    self.assertEqual(native["cursor"], oracle.cursor, prefix)
                    self.assertEqual(native["age_in_cycles"], oracle.age_in_cycles, prefix)
                    self.assertEqual(
                        native["status"], 0 if oracle.status is OrganismStatus.ALIVE else 1, prefix
                    )
                    self.assertAlmostEqual(native["reserve"], oracle.reserve, places=12, msg=prefix)
                    self.assertEqual(native["body"]["structural_mass"], oracle.full_body_mass(), prefix)
                    self.assertEqual(native["body"]["atom_count"], len(oracle.atoms), prefix)
                    self.assertEqual(native["body"]["relation_count"], len(oracle.relations), prefix)
                    self.assertEqual(native["body"]["composite_count"], len(oracle.composites), prefix)
                    if organism_id in step_results:
                        expected_requests = (
                            ("store_corpse",)
                            if status_before.get(organism_id) == 0 and native["status"] == 1
                            else ()
                        )
                        self.assertEqual(step_results[organism_id]["requests"], expected_requests, prefix)
                population.verify_material_conservation()

    def test_native_population_transfers_dead_snapshot_to_host(self) -> None:
        config = LifecycleConfig(boundary_ratio_limit=0.5, birth_reserve=10.0)
        with NativePopulationBackend(self.library_path, organism_ids=(0,), config=config) as population:
            population.step({0: (b"\x04\x05", (1.0, 1.0))}, child_ids={0: 1})
            with self.assertRaises(NativeBackendError):
                population.take_corpse(0)
            for _ in range(16):
                before = population.organism_ids
                results = population.step({organism_id: (b"", ()) for organism_id in before})
                dead_id = next(
                    (organism_id for organism_id in before
                     if results[organism_id]["requests"] == ("store_corpse",)),
                    None,
                )
                if dead_id is None:
                    continue
                corpse = population.take_corpse(dead_id)
                self.assertEqual(corpse["status"], 1)
                self.assertNotIn(dead_id, population.organism_ids)
                return
            self.fail("native population did not emit a corpse request")

    def test_native_population_applies_host_actions_in_id_order(self) -> None:
        with NativePopulationBackend(self.library_path, organism_ids=(8, 2)) as population:
            result = population.apply_actions({8: NativeAction.corpse_energy(2.0), 2: NativeAction.corpse_energy(1.0)})
            self.assertEqual(tuple(result), (2, 8))
            self.assertAlmostEqual(population.snapshot(2)["reserve"], 2.0, places=12)
            self.assertAlmostEqual(population.snapshot(8)["reserve"], 3.0, places=12)
            before = population.state_digests()
            with self.assertRaises(ValueError):
                population.apply_actions({99: NativeAction.corpse_energy(1.0)})
            self.assertEqual(population.state_digests(), before)
            with self.assertRaises(TypeError):
                population.apply_actions({2: "not-an-action"})  # type: ignore[arg-type]
            self.assertEqual(population.state_digests(), before)

    def test_native_population_runs_due_lifecycle_batches_in_id_order(self) -> None:
        with NativePopulationBackend(self.library_path, organism_ids=(5, 2)) as population:
            population.apply_actions({
                2: NativeAction.external_gut(b"ABCD", capacity=4),
                5: NativeAction.external_gut(b"ABCD", capacity=4),
            })
            before_invalid = population.state_digests()
            with self.assertRaises(ValueError):
                population.run_due_lifecycle({99: 1})
            self.assertEqual(population.state_digests(), before_invalid)
            results = population.run_due_lifecycle({5: 1, 2: 2})
            self.assertEqual(tuple(results), (2, 5))
            self.assertEqual(results[2]["executed_steps"], 2)
            self.assertEqual(results[5]["executed_steps"], 1)
            population.verify_material_conservation()

    def test_native_population_registers_explicit_division_children(self) -> None:
        config = LifecycleConfig(birth_reserve=10.0, boundary_ratio_limit=0.5)
        with NativePopulationBackend(self.library_path, organism_ids=(0,), config=config) as population:
            population.apply_actions({
                0: NativeAction.external_gut(b"\x04\x05", capacity=2, nutrition=(1.0, 1.0)),
            })
            result = population.apply_actions({
                0: NativeAction.division((4,), child_id=1, birth_cost=1.0),
            })
            self.assertEqual(population.organism_ids, (0, 1))
            self.assertEqual(result[0]["child_id"], 1)
            self.assertEqual(population.snapshot(1)["parent_id"], 0)
            self.assertEqual(population.snapshot(1)["reserve"], 0.0)
            population.verify_material_conservation()
            before_collision = population.state_digests()
            with self.assertRaises(ValueError):
                population.apply_actions({
                    0: NativeAction.division((5,), child_id=1, birth_cost=1.0),
                })
            self.assertEqual(population.state_digests(), before_collision)

    def test_native_population_replays_host_action_trace_and_retains_child(self) -> None:
        config = LifecycleConfig(birth_reserve=10.0, boundary_ratio_limit=0.5)
        with NativePopulationBackend(self.library_path, organism_ids=(0,), config=config) as population:
            results = population.replay_action_traces({
                0: (
                    NativeAction.external_gut(b"\x04\x05", capacity=2, nutrition=(1.0, 1.0)),
                    NativeAction.division((4,), child_id=1, birth_cost=1.0),
                ),
            })
            self.assertEqual(tuple(item["kind"] for item in results[0]), ("external_gut", "division"))
            self.assertEqual(population.organism_ids, (0, 1))
            self.assertEqual(results[0][1]["child_id"], 1)
            population.verify_material_conservation()
            before = population.state_digests()
            with self.assertRaises(ValueError):
                population.replay_action_traces({
                    0: (NativeAction.division((5,), child_id=1, birth_cost=1.0),),
                })
            self.assertEqual(population.state_digests(), before)

    def test_python_live_step_trace_registers_native_child(self) -> None:
        config = LifecycleConfig(boundary_ratio_limit=0.5, birth_reserve=10.0)
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=2)
            (runtime.inbox / "payload.bin").write_bytes(bytes((4, 5)) * 64)
            organism = AutonomousOrganism(config=config)
            runtime.organisms.append(organism)
            with NativePopulationBackend(self.library_path, organism_ids=(0,), config=config) as population:
                for step in range(100):
                    trace: list[NativeAction] = []
                    organism.live_step(runtime, action_trace=trace)
                    population.replay_action_traces({0: tuple(trace)})
                    division = next(
                        (action for action in trace if action.kind is NativeActionKind.DIVISION),
                        None,
                    )
                    if division is None:
                        continue
                    child = organism.children[-1]
                    native_child = population.snapshot(division.child_id)
                    native_parent = population.snapshot(0)
                    self.assertEqual(population.organism_ids, (0, division.child_id))
                    self.assertEqual(native_parent["body"]["structural_mass"], organism.body.full_body_mass())
                    self.assertEqual(native_child["body"]["structural_mass"], child.body.full_body_mass())
                    self.assertEqual(native_child["body"]["atom_count"], len(child.body.atoms))
                    self.assertEqual(native_child["reserve"], 0.0)
                    population.verify_material_conservation()
                    break
                else:
                    self.fail("Python live_step did not emit a division trace")

    def test_python_sandbox_trace_campaign_replays_parent_and_children(self) -> None:
        fixture = _native_fixture("sandbox_trace")
        config = LifecycleConfig(
            boundary_ratio_limit=float(fixture["boundary_ratio_limit"]),
            birth_reserve=float(fixture["birth_reserve"]),
        )
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(
                Path(directory) / "sandbox", block_size=int(fixture["block_size"])
            )
            pattern = bytes(int(value) for value in fixture["payload_pattern"])
            (runtime.inbox / "payload.bin").write_bytes(
                pattern * int(fixture["payload_repeats"])
            )
            root = AutonomousOrganism(config=config)
            runtime.organisms.append(root)
            organism_ids = tuple(int(value) for value in fixture["organism_ids"])
            with NativePopulationBackend(
                self.library_path,
                organism_ids=organism_ids,
                config=config,
            ) as population:
                native_ids = {root.name: organism_ids[0]}
                for epoch in range(int(fixture["epochs"])):
                    traces: dict[int, tuple[NativeAction, ...]] = {}
                    for organism in tuple(runtime.organisms):
                        if not organism.alive:
                            continue
                        native_id = native_ids[organism.name]
                        trace: list[NativeAction] = []
                        organism.live_step(runtime, action_trace=trace)
                        traces[native_id] = tuple(trace)
                        division = next(
                            (action for action in trace if action.kind is NativeActionKind.DIVISION),
                            None,
                        )
                        if division is not None:
                            child = organism.children[-1]
                            native_ids[child.name] = division.child_id
                    population.replay_action_traces(traces)
                    for organism in tuple(runtime.organisms):
                        native_id = native_ids.get(organism.name)
                        if native_id is None or native_id not in population.organism_ids:
                            continue
                        native = population.snapshot(native_id)
                        prefix = f"sandbox trace epoch {epoch} organism {organism.name}"
                        def evidence(field: str) -> _SandboxFailureEvidence:
                            return _SandboxFailureEvidence(prefix, field, organism, population, native_id)

                        self.assertEqual(native["status"], 0 if organism.alive else 1, evidence("status"))
                        self.assertEqual(native["age_in_cycles"], organism.body.age_in_cycles, evidence("age_in_cycles"))
                        self.assertEqual(native["generation"], organism.body.generation, evidence("generation"))
                        self.assertEqual(native["metabolic_progress"], organism.metabolic_progress, evidence("metabolic_progress"))
                        self.assertEqual(native["metabolic_steps"], organism.metabolic_steps, evidence("metabolic_steps"))
                        self.assertEqual(
                            native["activated_receptors"],
                            tuple(sorted(organism.body.activated_receptors)),
                            evidence("activated_receptors"),
                        )
                        self.assertEqual(native["body"]["structural_mass"], organism.body.full_body_mass(), evidence("body.structural_mass"))
                        self.assertEqual(native["body"]["atom_count"], len(organism.body.atoms), evidence("body.atom_count"))
                        self.assertEqual(native["body"]["relation_count"], len(organism.body.relations), evidence("body.relation_count"))
                        self.assertEqual(native["body"]["composite_count"], len(organism.body.composites), evidence("body.composite_count"))
                        self.assertAlmostEqual(native["reserve"], organism.body.reserve, places=12, msg=evidence("reserve"))
                        self.assertEqual(native["territory"], organism.territory_state.territory.path, evidence("territory"))
                        for field in (
                            "input_mass", "assimilated_mass", "rejected_mass", "resorbed_mass",
                            "processed_mass", "expelled_mass", "external_expelled_mass",
                            "resorption_expelled_mass", "structural_created_mass",
                            "structural_transferred_in", "structural_transferred_out",
                        ):
                            self.assertEqual(native["material_flow"][field], getattr(organism.material_flow, field), evidence(f"material_flow.{field}"))
                        for field in (
                            "bytes_eaten", "relations_created", "relations_strengthened",
                            "composites_created", "composites_strengthened", "structural_mass_added",
                            "structural_mass_lost", "resorption_events", "division_events",
                            "processed_bytes", "rejected_bytes", "resorbed_processed_bytes",
                        ):
                            self.assertEqual(
                                native["activity"]["counters"][field],
                                getattr(organism.activity_ledger.counters, field),
                                evidence(f"activity.counters.{field}"),
                            )
                        self.assertAlmostEqual(
                            native["activity"]["metabolic_debt"],
                            organism.activity_ledger.metabolic_debt,
                            places=12,
                            msg=(
                                f"{evidence('activity.metabolic_debt')} native={native['activity']} "
                                f"python={organism.activity_ledger} trace="
                                f"{[action.kind.value for action in traces.get(native_id, ())]}"
                            ),
                        )
                        self.assertAlmostEqual(
                            native["activity"]["energy_spent"],
                            organism.activity_ledger.energy_spent,
                            places=12,
                            msg=evidence("activity.energy_spent"),
                        )
                        self.assertEqual(native["activity"]["settlements"], organism.activity_ledger.settlements, evidence("activity.settlements"))
                        expected_gut = tuple(
                            (
                                chunk.mass,
                                0 if chunk.origin == "external" else 1,
                                bytes(chunk.payload),
                                tuple(chunk.nutrition),
                            )
                            for chunk in organism.gut_queue
                        )
                        self.assertEqual(native["gut"], expected_gut, evidence("gut"))
                    for organism_name, native_id in tuple(native_ids.items()):
                        if native_id not in population.organism_ids:
                            continue
                        if population.snapshot(native_id)["status"] == 1:
                            population.take_corpse(native_id)
                            del native_ids[organism_name]
                    population.verify_material_conservation()

    def test_native_sandbox_replay_adapter_runs_fixture_epochs(self) -> None:
        fixture = _native_fixture("sandbox_trace")
        config = LifecycleConfig(
            boundary_ratio_limit=float(fixture["boundary_ratio_limit"]),
            birth_reserve=float(fixture["birth_reserve"]),
        )
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(
                Path(directory) / "sandbox", block_size=int(fixture["block_size"])
            )
            pattern = bytes(int(value) for value in fixture["payload_pattern"])
            (runtime.inbox / "payload.bin").write_bytes(
                pattern * int(fixture["payload_repeats"])
            )
            runtime.organisms.append(AutonomousOrganism(config=config))
            with NativeSandboxReplay(
                self.library_path,
                runtime,
                config=config,
                organism_ids=tuple(int(value) for value in fixture["organism_ids"]),
            ) as replay:
                saw_division = False
                division_policies: set[str] = set()
                for epoch_index in range(int(fixture["epochs"])):
                    epoch = replay.step()
                    self.assertEqual(epoch.index, epoch_index)
                    saw_division |= any(
                        action.kind is NativeActionKind.DIVISION
                        for _organism_id, trace in epoch.traces
                        for action in trace
                    )
                    division_policies.update(
                        str(result["policy"])
                        for _organism_id, results in epoch.results
                        for result in results
                        if result.get("kind") == "division" and "policy" in result
                    )
                    self.assertEqual(
                        tuple(organism_id for organism_id, _snapshot in epoch.snapshots),
                        tuple(sorted(organism_id for organism_id, _snapshot in epoch.snapshots)),
                    )
                self.assertTrue(saw_division)
                self.assertEqual(
                    division_policies,
                    {"global_partition_policy"},
                )

    def test_native_sandbox_replay_rejects_orphan_initial_handles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=2)
            runtime.organisms.append(AutonomousOrganism())
            with self.assertRaises(ValueError):
                NativeSandboxReplay(
                    self.library_path,
                    runtime,
                    organism_ids=(0, 1),
                )

    def test_backend_selector_exposes_native_population_without_fallback(self) -> None:
        backend = create_backend(
            "native-population", library=self.library_path, organism_ids=(0, 1)
        )
        self.assertIsInstance(backend, NativePopulationBackend)
        self.assertEqual(backend.organism_ids, (0, 1))
        backend.close()
        with self.assertRaises(NativeBackendError):
            backend.snapshots()

    def test_public_cli_checkpoint_uses_explicit_native_backend(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = cli_main([
                "checkpoint", "AB", "--backend", "native",
                "--library", str(self.library_path), "--steps", "2", "--json",
            ])
        self.assertEqual(status, 0)
        self.assertIn('"backend": "native"', output.getvalue())
        self.assertIn('"steps": 2', output.getvalue())

    def test_public_cli_native_failure_does_not_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing-native.dll"
            with self.assertRaises(NativeBackendError):
                cli_main([
                    "checkpoint", "AB", "--backend", "native",
                    "--library", str(missing), "--steps", "1",
                ])

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

    def test_explicit_host_action_plan_matches_native_primitives(self) -> None:
        payload = (1, 2, 1)
        nutrition = (1.0, 2.0, 3.0)
        reference = AutonomousOrganism("ORG-ROOT")
        reference.enqueue_external_material(payload, nutrition)
        reference.result.available_nutrition_total += sum(nutrition)
        expected_processed = reference.process_gut(2)
        with NativeBackend(self.library_path, organism_id=0) as backend:
            actual = backend.apply_action(
                NativeAction.external_gut(bytes(payload), nutrition=nutrition, capacity=2)
            )
            self.assertEqual(actual["kind"], "external_gut")
            self.assertEqual(actual["processed_mass"], expected_processed)
            self.assertEqual(actual["assimilated_mass"], reference.material_flow.assimilated_mass)
            self.assertEqual(actual["rejected_mass"], reference.material_flow.rejected_mass)
            backend.verify_material_conservation()

        with NativeBackend(self.library_path, organism_id=1) as backend:
            before = backend.state_digest()
            with self.assertRaises(ValueError):
                NativeAction.external_gut(b"AB", nutrition=(1.0,), capacity=1)
            self.assertEqual(backend.state_digest(), before)
            with self.assertRaises(ValueError):
                NativeAction.external_gut(b"A", capacity=-1)
            self.assertEqual(backend.state_digest(), before)
            with self.assertRaises(ValueError):
                NativeAction.process_gut(capacity=1 << 64)
            self.assertEqual(backend.state_digest(), before)
            with self.assertRaises(TypeError):
                backend.replay_actions((NativeAction.corpse_energy(1.0), "invalid"))  # type: ignore[arg-type]
            self.assertEqual(backend.state_digest(), before)

    def test_explicit_process_gut_action_preserves_backpressure_semantics(self) -> None:
        payload = (1, 2, 1)
        nutrition = (1.0, 2.0, 3.0)
        reference = AutonomousOrganism("ORG-ROOT")
        reference.enqueue_external_material(payload, nutrition)
        reference.result.available_nutrition_total += sum(nutrition)
        expected = reference.process_gut(2)
        with NativeBackend(self.library_path, organism_id=4) as backend:
            backend.enqueue_external(bytes(payload), nutrition)
            actual = backend.apply_action(NativeAction.process_gut(capacity=2))
            self.assertEqual(actual["kind"], "process_gut")
            self.assertEqual(actual["processed_mass"], expected)
            self.assertEqual(actual["assimilated_mass"], reference.material_flow.assimilated_mass)
            self.assertEqual(actual["rejected_mass"], reference.material_flow.rejected_mass)
            self.assertEqual(len(backend.snapshot()["gut"]), 1)

    def test_filesystem_food_claim_emits_replayable_external_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox", block_size=4)
            source = runtime.inbox / "payload.bin"
            source.write_bytes(b"ABCD")
            organism = runtime.bootstrap()
            trace: list[NativeAction] = []
            organism.live_step(runtime, action_trace=trace)
            external = [action for action in trace if action.kind.value == "external_gut"]
            self.assertEqual(len(external), 1)
            action = external[0]
            with NativeBackend(self.library_path, organism_id=77) as backend:
                result = backend.apply_action(action)
                self.assertEqual(result["kind"], "external_gut")
                self.assertEqual(result["processed_mass"], len(action.payload))
                backend.verify_material_conservation()

    def test_physical_food_host_drives_native_lifecycle_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.bin"
            source.write_bytes(b"ABCD")
            harness = SandboxFeedingHarness(source, root / "physical", parcel_size=4, context_overlap=0)
            reference = harness.population.organisms[0]
            claim = harness._claim_next(reference)
            self.assertIsNotNone(claim)
            assert claim is not None
            bite, _context = harness.food.read(claim)
            with NativeBackend(self.library_path, organism_id=0) as backend:
                native_result = backend.step(bytes(bite), (1.0,) * len(bite))
                reference.cursor += len(bite)
                harness.population._digest(reference, bite, (1.0,) * len(bite))
                harness.food.consume(claim)
                harness._post_digest_lifecycle(reference)
                self.assertEqual(native_result["consumed_bytes"], len(bite))
                native = backend.snapshot()
                self.assertEqual(native["cursor"], reference.cursor)
                self.assertEqual(native["age_in_cycles"], reference.age_in_cycles)
                self.assertEqual(native["body"]["structural_mass"], reference.full_body_mass())
                self.assertEqual(native["body"]["atom_count"], len(reference.atoms))
                self.assertEqual(native["body"]["relation_count"], len(reference.relations))
                self.assertAlmostEqual(native["reserve"], reference.reserve, places=12)
                backend.verify_material_conservation()

    def test_corpse_lookup_emits_replayable_energy_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            organism = runtime.bootstrap()
            runtime.add_corpse(Corpse(organism.territory_state.territory, 2.5), "ORG-CORPSE")
            trace: list[NativeAction] = []
            reserve_before = organism.body.reserve
            organism.live_step(runtime, action_trace=trace)
            corpse_actions = [action for action in trace if action.kind.value == "corpse_energy"]
            self.assertEqual(len(corpse_actions), 1)
            action = corpse_actions[0]
            with NativeBackend(self.library_path, organism_id=78) as backend:
                reserve_native_before = float(backend.snapshot()["reserve"])
                results = backend.replay_actions(trace)
                result = next(item for item in results if item["kind"] == "corpse_energy")
                self.assertAlmostEqual(
                    float(result["credited_energy"]), organism.body.reserve - reserve_before, places=12
                )
                self.assertAlmostEqual(
                    float(backend.snapshot()["reserve"]) - reserve_native_before,
                    float(result["credited_energy"]),
                    places=12,
                )

    def test_idle_and_corpse_action_trace_replays_without_food(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = SandboxRuntime(Path(directory) / "sandbox")
            organism = runtime.bootstrap()
            runtime.add_corpse(Corpse(organism.territory_state.territory, 2.5), "ORG-CORPSE")
            with NativeBackend(self.library_path, organism_id=79) as backend:
                for step in range(32):
                    trace: list[NativeAction] = []
                    organism.live_step(runtime, action_trace=trace)
                    backend.replay_actions(trace)
                    native = backend.snapshot()
                    self.assertEqual(native["status"], 0 if organism.alive else 1, step)
                    self.assertEqual(native["body"]["structural_mass"], organism.body.full_body_mass(), step)
                    self.assertEqual(native["gut"], (), step)
                    self.assertAlmostEqual(native["reserve"], organism.body.reserve, places=12, msg=step)
                    self.assertAlmostEqual(
                        native["activity"]["metabolic_debt"],
                        organism.activity_ledger.metabolic_debt,
                        places=12,
                        msg=f"activity debt diverged at idle step {step}",
                    )

    def test_explicit_corpse_energy_action_matches_oracle(self) -> None:
        reference = AutonomousOrganism("ORG-ROOT")
        with NativeBackend(self.library_path, organism_id=2) as backend:
            actual = backend.apply_action(NativeAction.corpse_energy(2.5))
            reference.body.adjust_reserve(2.5)
            self.assertEqual(actual["kind"], "corpse_energy")
            self.assertAlmostEqual(float(actual["credited_energy"]), 2.5, places=12)
            self.assertAlmostEqual(backend.snapshot()["reserve"], reference.body.reserve, places=12)

    def test_explicit_lifecycle_action_matches_step_and_rejects_invalid_plan(self) -> None:
        payload = b"ABCD"
        nutrition = (2.0,) * len(payload)
        with NativeBackend(self.library_path, organism_id=3) as direct, NativeBackend(
            self.library_path, organism_id=3
        ) as planned:
            before_corpse = planned.state_digest()
            with self.assertRaises(NativeBackendError):
                planned.take_corpse()
            self.assertEqual(planned.state_digest(), before_corpse)
            expected = direct.lifecycle_step(payload, nutrition)
            actual = planned.apply_action(NativeAction.lifecycle_step(payload, nutrition=nutrition))
            self.assertEqual(actual["kind"], "lifecycle_step")
            self.assertEqual(actual["consumed_bytes"], expected["consumed_bytes"])
            self.assertEqual(actual["assimilated_mass"], expected["assimilated_mass"])
            self.assertAlmostEqual(
                float(actual["maintenance_required"]),
                float(expected["maintenance_required"]),
                places=12,
            )
            self.assertEqual(planned.state_digest(), direct.state_digest())
            before = planned.state_digest()
            with self.assertRaises(ValueError):
                NativeAction.corpse_energy(float("nan"))
            with self.assertRaises(ValueError):
                NativeAction.lifecycle_step(payload, nutrition=(1.0,))
            self.assertEqual(planned.state_digest(), before)

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

    def test_dense_partition_matches_reference_conservation(self) -> None:
        payload = b"ABCDEFGH"
        nutrition = (10.0,) * len(payload)
        reference = AutonomousOrganism("ORG-DENSE")
        reference.result.available_nutrition_total += sum(nutrition)
        reference.enqueue_external_material(tuple(payload), nutrition)
        reference.process_gut(len(payload))
        reference_child = reference._commit_skeleton_partition(
            set(payload[:4]), require_maturity=False
        )
        self.assertIsNotNone(reference_child)
        with NativeBackend(self.library_path, organism_id=12) as backend:
            backend.digest(payload, nutrition)
            native_child, native_result = backend.partition(
                tuple(payload[:4]), child_id=13, birth_cost=1.0
            )
            with native_child:
                native_parent = backend.snapshot()
                native_child_snapshot = native_child.snapshot()
        assert reference_child is not None
        self.assertEqual(
            native_child_snapshot["body"]["structural_mass"],
            reference_child.body.full_body_mass(),
        )
        self.assertEqual(
            native_parent["body"]["structural_mass"], reference.body.full_body_mass()
        )
        self.assertGreater(native_result["cross_split_mass"], 0)
        self.assertEqual(native_child_snapshot["reserve"], 0.0)
        # The reference and native ledgers independently account for every
        # transferred/resorbed structural unit; no implementation is used as
        # the other's conservation oracle.
        self.assertEqual(
            native_parent["material_flow"]["structural_created_mass"]
            + native_parent["material_flow"]["structural_transferred_in"],
            native_parent["body"]["structural_mass"] - 256
            + native_parent["material_flow"]["resorbed_mass"]
            + native_parent["material_flow"]["structural_transferred_out"],
        )

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
        with NativeBackend(self.library_path, organism_id=123) as backend:
            self.assertEqual(backend.food_block_key("firmware-A", 7), food_block_key("firmware-A", 7))
            with self.assertRaises(ValueError):
                backend.food_block_key("firmware-A", -1)

    def test_simple_lifecycle_replay_reports_first_divergent_field(self) -> None:
        fixture = _native_fixture("single_lifecycle")
        payload_patterns = tuple(str(value) for value in fixture["payload_patterns"])
        payload_repeats = tuple(int(value) for value in fixture["payload_repeats"])
        payloads = tuple(pattern * repeat for pattern, repeat in zip(payload_patterns, payload_repeats))
        cycles = int(os.environ.get("COMPOST_DIFFERENTIAL_CYCLES", str(fixture["cycles"])))
        if cycles <= 0:
            self.fail("COMPOST_DIFFERENTIAL_CYCLES must be positive")
        for scenario in range(int(fixture["scenario_count"])):
            payload = payloads[scenario % len(payloads)]
            population = MathematicalLifePopulation(payload)
            with NativeBackend(self.library_path, organism_id=int(fixture["seed"]) + scenario) as backend:
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

    def test_configuration_matrix_replays_each_step(self) -> None:
        matrix = _native_fixture("configuration_matrix")
        if not isinstance(matrix, list):
            self.fail("configuration_matrix fixture must be a list")
        for case in matrix:
            self.assertIsInstance(case, dict)
            config_values = case["config"]
            self.assertIsInstance(config_values, dict)
            config = LifecycleConfig(**config_values)
            payload = str(case["payload"])
            population = MathematicalLifePopulation(payload, config=config)
            with NativeBackend(
                self.library_path,
                organism_id=int(case["organism_id"]),
                config=config,
            ) as backend:
                for cycle in range(int(case["cycles"])):
                    population.cycle()
                    backend.step(
                        payload.encode("ascii") if cycle == 0 else b"",
                        (1.0,) * len(payload) if cycle == 0 else (),
                    )
                    reference = population.organisms[0]
                    native = backend.snapshot()
                    prefix = f"configuration {case['name']} step {cycle}"
                    evidence = _FailureEvidence(prefix, "state", population, backend)
                    self.assertEqual(native["status"], 0 if reference.status is OrganismStatus.ALIVE else 1, evidence)
                    self.assertEqual(native["cursor"], reference.cursor, evidence)
                    self.assertEqual(native["age_in_cycles"], reference.age_in_cycles, evidence)
                    self.assertEqual(native["body"]["atom_count"], len(reference.atoms), evidence)
                    self.assertEqual(native["body"]["relation_count"], len(reference.relations), evidence)
                    self.assertEqual(native["body"]["composite_count"], len(reference.composites), evidence)
                    self.assertEqual(native["body"]["structural_mass"], reference.full_body_mass(), evidence)
                    self.assertAlmostEqual(native["reserve"], reference.reserve, places=12, msg=evidence)


if __name__ == "__main__":
    unittest.main()
